"""
Streaming market data source via Lightstreamer.

Real implementation using HTTP streaming to IG's Lightstreamer endpoint.
Includes reconnection with exponential backoff and jitter.
"""

import asyncio
import random
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

import httpx

from solat_engine.logging import get_logger
from solat_engine.market_data.models import MarketDataMode, MarketStreamStatus, Quote

if TYPE_CHECKING:
    from solat_engine.broker.ig.client import AsyncIGClient

logger = get_logger(__name__)


# Lightstreamer protocol constants
LS_CREATE_SESSION = "create_session.txt"
LS_BIND_SESSION = "bind_session.txt"
LS_CONTROL = "control.txt"


class LightstreamerError(Exception):
    """Lightstreamer-specific error."""

    pass


class LightstreamerClient:
    """
    Production Lightstreamer client for IG streaming API.

    Uses HTTP streaming (long-polling) to receive real-time price updates.
    IG's Lightstreamer endpoint requires:
    - CST and X-SECURITY-TOKEN from REST API login
    - Account ID for subscription context
    - MARKET:{epic} item subscriptions for L1 prices
    """

    # L1 price fields from IG Lightstreamer
    L1_FIELDS = ["BID", "OFFER", "UPDATE_TIME", "MARKET_STATE"]

    def __init__(
        self,
        ig_client: "AsyncIGClient",
        on_quote: Any = None,
        on_status_change: Any = None,
    ):
        """
        Initialize Lightstreamer client.

        Args:
            ig_client: IG REST client (for auth tokens and endpoint)
            on_quote: Async callback(Quote) for price updates
            on_status_change: Async callback(status) for connection changes
        """
        self._ig_client = ig_client
        self._on_quote = on_quote
        self._on_status_change = on_status_change

        # Connection state
        self._connected = False
        self._running = False
        self._session_id: str | None = None
        self._control_address: str | None = None

        # Subscriptions: symbol -> epic
        self._subscriptions: dict[str, str] = {}
        self._subscription_ids: dict[str, int] = {}  # epic -> subscription id
        self._next_sub_id = 1

        # Connection health
        self._last_tick_ts: datetime | None = None
        self._reconnect_attempts = 0
        self._max_reconnect_attempts = 10
        self._reconnect_delay_base = 1.0
        self._reconnect_delay_max = 60.0
        self._stale_threshold_s = 10
        self._last_error: str | None = None

        # HTTP client
        self._http_client: httpx.AsyncClient | None = None

        # Task handles
        self._stream_task: asyncio.Task[None] | None = None
        self._heartbeat_task: asyncio.Task[None] | None = None

    @property
    def is_connected(self) -> bool:
        """Check if connected to Lightstreamer."""
        return self._connected

    @property
    def is_running(self) -> bool:
        """Check if running (may be reconnecting)."""
        return self._running

    @property
    def mode(self) -> MarketDataMode:
        """Get mode."""
        return MarketDataMode.STREAM

    def get_status(self) -> MarketStreamStatus:
        """Get current status."""
        stale = False
        if self._last_tick_ts:
            age = (datetime.now(UTC) - self._last_tick_ts).total_seconds()
            stale = age > self._stale_threshold_s

        return MarketStreamStatus(
            connected=self._connected,
            mode=MarketDataMode.STREAM,
            last_tick_ts=self._last_tick_ts,
            stale=stale,
            stale_threshold_s=self._stale_threshold_s,
            subscriptions=list(self._subscriptions.keys()),
            reconnect_attempts=self._reconnect_attempts,
            last_error=self._last_error,
        )

    async def subscribe(self, symbol: str, epic: str) -> None:
        """
        Subscribe to a symbol.

        Args:
            symbol: Canonical symbol (e.g., EURUSD)
            epic: IG epic identifier
        """
        self._subscriptions[symbol] = epic
        logger.info("Streaming: subscribed to %s (%s)", symbol, epic)

        # If connected, add subscription to active session
        if self._connected and self._session_id:
            await self._send_subscription(symbol, epic)

    async def unsubscribe(self, symbol: str) -> None:
        """Unsubscribe from a symbol."""
        if symbol in self._subscriptions:
            epic = self._subscriptions[symbol]
            del self._subscriptions[symbol]
            logger.info("Streaming: unsubscribed from %s", symbol)

            if self._connected and self._session_id:
                await self._send_unsubscription(epic)

    async def unsubscribe_all(self) -> None:
        """Unsubscribe from all symbols."""
        self._subscriptions.clear()
        self._subscription_ids.clear()
        logger.info("Streaming: unsubscribed from all symbols")

    async def start(self) -> None:
        """Start streaming connection."""
        if self._running:
            logger.warning("Streaming already running")
            return

        self._running = True
        self._reconnect_attempts = 0

        # Initialize HTTP client
        self._http_client = httpx.AsyncClient(timeout=httpx.Timeout(30.0))

        self._stream_task = asyncio.create_task(self._stream_loop())
        self._heartbeat_task = asyncio.create_task(self._heartbeat_loop())

        logger.info("Streaming market source started")

    async def stop(self) -> None:
        """Stop streaming connection."""
        self._running = False
        self._connected = False

        # Cancel tasks
        if self._stream_task:
            self._stream_task.cancel()
            try:
                await self._stream_task
            except asyncio.CancelledError:
                pass
            self._stream_task = None

        if self._heartbeat_task:
            self._heartbeat_task.cancel()
            try:
                await self._heartbeat_task
            except asyncio.CancelledError:
                pass
            self._heartbeat_task = None

        # Close HTTP client
        if self._http_client:
            await self._http_client.aclose()
            self._http_client = None

        self._session_id = None
        self._control_address = None

        logger.info("Streaming market source stopped")

    # -------------------------------------------------------------------------
    # Internal: Stream Loop
    # -------------------------------------------------------------------------

    async def _stream_loop(self) -> None:
        """Main streaming loop with reconnection logic."""
        while self._running:
            try:
                await self._connect()
                self._connected = True
                self._reconnect_attempts = 0
                self._last_error = None

                if self._on_status_change:
                    await self._on_status_change(self.get_status())

                # Subscribe to all symbols
                for symbol, epic in self._subscriptions.items():
                    await self._send_subscription(symbol, epic)

                # Enter receive loop
                await self._receive_loop()

            except asyncio.CancelledError:
                break

            except Exception as e:
                self._connected = False
                self._last_error = str(e)
                self._reconnect_attempts += 1

                logger.error(
                    "Streaming error (attempt %d/%d): %s",
                    self._reconnect_attempts,
                    self._max_reconnect_attempts,
                    e,
                )

                if self._on_status_change:
                    await self._on_status_change(self.get_status())

                if self._reconnect_attempts >= self._max_reconnect_attempts:
                    logger.error("Max reconnect attempts reached, stopping streaming")
                    self._running = False
                    break

                # Exponential backoff with jitter
                delay = min(
                    self._reconnect_delay_base * (2**self._reconnect_attempts),
                    self._reconnect_delay_max,
                )
                jitter = random.uniform(0, delay * 0.1)
                logger.info("Reconnecting in %.1fs...", delay + jitter)
                await asyncio.sleep(delay + jitter)

    async def _connect(self) -> None:
        """
        Establish Lightstreamer session.

        1. Get Lightstreamer endpoint from IG login response
        2. Create session with CST/X-SECURITY-TOKEN
        3. Bind to session for receiving updates
        """
        logger.debug("Connecting to Lightstreamer...")

        # Ensure IG client is authenticated
        if not self._ig_client.is_authenticated:
            raise ConnectionError("IG client not authenticated")

        # Get Lightstreamer endpoint
        login_response = self._ig_client.login_response
        if not login_response or not login_response.lightstreamer_endpoint:
            # Fallback to simulation mode for demo/testing
            logger.warning("No Lightstreamer endpoint available, using simulation mode")
            await self._connect_simulation()
            return

        endpoint = login_response.lightstreamer_endpoint
        account_id = login_response.account_id

        # Get auth tokens
        cst, security_token = self._ig_client.get_session_tokens()
        if not cst or not security_token:
            raise ConnectionError("Missing session tokens")

        # Create session request
        create_params = {
            "LS_op2": "create",
            "LS_cid": "mgQkwtwdysogQz2BJ4Ji kOj2Bg",  # IG client ID
            "LS_adapter_set": "DEFAULT",
            "LS_user": account_id,
            "LS_password": f"CST-{cst}|XST-{security_token}",
        }

        assert self._http_client is not None

        try:
            response = await self._http_client.post(
                f"{endpoint}/{LS_CREATE_SESSION}",
                data=create_params,
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )

            if response.status_code != 200:
                raise LightstreamerError(f"Session creation failed: {response.status_code}")

            # Parse session response
            await self._parse_session_response(response.text)

            logger.info(
                "Lightstreamer connected (session=%s)",
                self._session_id[:8] if self._session_id else "unknown",
            )

        except httpx.RequestError as e:
            raise ConnectionError(f"HTTP error connecting to Lightstreamer: {e}") from e

    async def _connect_simulation(self) -> None:
        """Fallback simulation mode when Lightstreamer endpoint unavailable."""
        self._session_id = "SIMULATION"
        self._control_address = None
        logger.info("Lightstreamer connected (simulation mode)")

    async def _parse_session_response(self, response_text: str) -> None:
        """Parse Lightstreamer create_session response."""
        lines = response_text.strip().split("\r\n")

        for line in lines:
            if line.startswith("SessionId:"):
                self._session_id = line.split(":", 1)[1].strip()
            elif line.startswith("ControlAddress:"):
                self._control_address = line.split(":", 1)[1].strip()
            elif line.startswith("ERROR"):
                raise LightstreamerError(f"Session error: {line}")

        if not self._session_id:
            raise LightstreamerError("No session ID in response")

    async def _receive_loop(self) -> None:
        """Receive and process streaming messages."""
        if self._session_id == "SIMULATION":
            await self._receive_loop_simulation()
            return

        login_response = self._ig_client.login_response
        if not login_response or not login_response.lightstreamer_endpoint:
            await self._receive_loop_simulation()
            return

        endpoint = login_response.lightstreamer_endpoint
        bind_url = f"{endpoint}/{LS_BIND_SESSION}"

        bind_params = {
            "LS_session": self._session_id,
        }

        assert self._http_client is not None

        async with self._http_client.stream(
            "POST",
            bind_url,
            data=bind_params,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        ) as response:
            if response.status_code != 200:
                raise LightstreamerError(f"Bind failed: {response.status_code}")

            async for line in response.aiter_lines():
                if not self._running:
                    break

                if line:
                    await self._process_message(line)

    async def _receive_loop_simulation(self) -> None:
        """Simulation mode: poll for prices."""
        poll_interval = 0.5

        while self._running and self._connected:
            try:
                for symbol, epic in list(self._subscriptions.items()):
                    quote = await self._fetch_quote_simulated(symbol, epic)
                    if quote:
                        self._last_tick_ts = quote.ts_utc
                        if self._on_quote:
                            await self._on_quote(quote)

                await asyncio.sleep(poll_interval)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.warning("Simulation receive error: %s", e)
                raise

    async def _fetch_quote_simulated(self, symbol: str, epic: str) -> Quote | None:
        """Fetch quote in simulation mode."""
        try:
            market_details = await self._ig_client.get_market_details(epic)
            if market_details is None or market_details.snapshot is None:
                return None

            snapshot = market_details.snapshot
            bid = snapshot.get("bid")
            offer = snapshot.get("offer")

            if bid is None or offer is None:
                return None

            return Quote.from_bid_ask(
                symbol=symbol,
                epic=epic,
                bid=float(bid),
                ask=float(offer),
                ts_utc=datetime.now(UTC),
                update_time=snapshot.get("updateTime"),
            )
        except Exception:
            return None

    async def _process_message(self, line: str) -> None:
        """Process a Lightstreamer message line."""
        try:
            # Lightstreamer TLCP protocol format
            # U,<sub_id>,<item_idx>|<field1>|<field2>|...
            if line.startswith("U,"):
                parts = line.split(",", 2)
                if len(parts) >= 3:
                    sub_id = int(parts[1])
                    data_parts = parts[2].split("|")
                    await self._handle_update(sub_id, data_parts)

            elif line.startswith("PROBE"):
                # Heartbeat probe, just acknowledge
                pass

            elif line.startswith("LOOP"):
                # Server requesting rebind
                raise LightstreamerError("Server requested rebind")

            elif line.startswith("END"):
                # Session ended
                raise LightstreamerError("Session ended by server")

        except Exception as e:
            logger.warning("Error processing message '%s': %s", line[:50], e)

    async def _handle_update(self, sub_id: int, fields: list[str]) -> None:
        """Handle a price update."""
        # Find which symbol this subscription is for
        symbol = None
        epic = None
        for sym, ep in self._subscriptions.items():
            if self._subscription_ids.get(ep) == sub_id:
                symbol = sym
                epic = ep
                break

        if not symbol or not epic:
            return

        # Parse L1 fields: BID, OFFER, UPDATE_TIME, MARKET_STATE
        if len(fields) >= 2:
            try:
                bid_str = fields[0] if fields[0] and fields[0] != "#" else None
                offer_str = fields[1] if len(fields) > 1 and fields[1] and fields[1] != "#" else None

                if bid_str and offer_str:
                    bid = float(bid_str)
                    offer = float(offer_str)
                    update_time = fields[2] if len(fields) > 2 else None

                    quote = Quote.from_bid_ask(
                        symbol=symbol,
                        epic=epic,
                        bid=bid,
                        ask=offer,
                        ts_utc=datetime.now(UTC),
                        update_time=update_time,
                    )

                    self._last_tick_ts = quote.ts_utc

                    if self._on_quote:
                        await self._on_quote(quote)

            except (ValueError, IndexError) as e:
                logger.debug("Failed to parse update: %s", e)

    # -------------------------------------------------------------------------
    # Internal: Subscriptions
    # -------------------------------------------------------------------------

    async def _send_subscription(self, symbol: str, epic: str) -> None:
        """Send subscription to Lightstreamer."""
        if self._session_id == "SIMULATION":
            return
        if not self._session_id:
            return

        sub_id = self._next_sub_id
        self._next_sub_id += 1
        self._subscription_ids[epic] = sub_id

        params = {
            "LS_session": self._session_id,
            "LS_op": "add",
            "LS_subId": str(sub_id),
            "LS_mode": "MERGE",
            "LS_group": f"MARKET:{epic}",
            "LS_schema": " ".join(self.L1_FIELDS),
        }

        await self._send_control(params)
        logger.debug("Sent subscription for %s (sub_id=%d)", symbol, sub_id)

    async def _send_unsubscription(self, epic: str) -> None:
        """Send unsubscription to Lightstreamer."""
        if self._session_id == "SIMULATION":
            return
        if not self._session_id:
            return

        sub_id = self._subscription_ids.pop(epic, None)
        if sub_id is None:
            return

        params = {
            "LS_session": self._session_id,
            "LS_op": "delete",
            "LS_subId": str(sub_id),
        }

        await self._send_control(params)
        logger.debug("Sent unsubscription for epic %s (sub_id=%d)", epic, sub_id)

    async def _send_control(self, params: dict[str, str]) -> None:
        """Send control request to Lightstreamer."""
        if not self._http_client:
            return

        login_response = self._ig_client.login_response
        if not login_response or not login_response.lightstreamer_endpoint:
            return

        # Use control address if available
        base = self._control_address or login_response.lightstreamer_endpoint
        control_url = f"https://{base}/{LS_CONTROL}" if self._control_address else f"{base}/{LS_CONTROL}"

        try:
            await self._http_client.post(
                control_url,
                data=params,
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
        except httpx.RequestError as e:
            logger.warning("Control request failed: %s", e)

    # -------------------------------------------------------------------------
    # Internal: Heartbeat
    # -------------------------------------------------------------------------

    async def _heartbeat_loop(self) -> None:
        """Monitor connection health and detect stale feeds."""
        while self._running:
            try:
                await asyncio.sleep(5)

                if self._connected and self._last_tick_ts:
                    age = (datetime.now(UTC) - self._last_tick_ts).total_seconds()
                    if age > self._stale_threshold_s:
                        logger.warning("Feed stale: no ticks for %.1fs", age)
                        if self._on_status_change:
                            await self._on_status_change(self.get_status())

            except asyncio.CancelledError:
                break


class StreamingMarketSource:
    """
    High-level streaming market source.

    Wraps LightstreamerClient with additional management.
    """

    def __init__(
        self,
        ig_client: "AsyncIGClient",
        on_quote: Any = None,
        on_status_change: Any = None,
    ):
        """
        Initialize streaming source.

        Args:
            ig_client: IG client
            on_quote: Quote callback
            on_status_change: Status change callback
        """
        self._client = LightstreamerClient(
            ig_client=ig_client,
            on_quote=on_quote,
            on_status_change=on_status_change,
        )

    @property
    def is_running(self) -> bool:
        """Check if running."""
        return self._client.is_running

    @property
    def is_connected(self) -> bool:
        """Check if connected."""
        return self._client.is_connected

    @property
    def mode(self) -> MarketDataMode:
        """Get mode."""
        return MarketDataMode.STREAM

    def get_status(self) -> MarketStreamStatus:
        """Get status."""
        return self._client.get_status()

    async def subscribe(self, symbol: str, epic: str) -> None:
        """Subscribe to symbol."""
        await self._client.subscribe(symbol, epic)

    async def unsubscribe(self, symbol: str) -> None:
        """Unsubscribe from symbol."""
        await self._client.unsubscribe(symbol)

    async def unsubscribe_all(self) -> None:
        """Unsubscribe all."""
        await self._client.unsubscribe_all()

    async def start(self) -> None:
        """Start streaming."""
        await self._client.start()

    async def stop(self) -> None:
        """Stop streaming."""
        await self._client.stop()
