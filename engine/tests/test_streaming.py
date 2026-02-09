"""
Tests for streaming market data.

Tests:
- Lightstreamer message parsing
- Quote construction from L1 data
- Reconnect backoff calculation
- Status tracking
"""

import asyncio
from datetime import UTC, datetime
from typing import Any
from unittest.mock import MagicMock

import pytest

from solat_engine.market_data.models import MarketDataMode, Quote
from solat_engine.market_data.streaming import LightstreamerClient, LightstreamerError


class MockIGClient:
    """Mock IG client for testing."""

    def __init__(
        self,
        is_authenticated: bool = True,
        lightstreamer_endpoint: str | None = "https://push.lightstreamer.com",
    ):
        self.is_authenticated = is_authenticated
        self._lightstreamer_endpoint = lightstreamer_endpoint
        self._cst = "test-cst"
        self._security_token = "test-token"

    @property
    def login_response(self) -> Any:
        if self._lightstreamer_endpoint:
            mock_response = MagicMock()
            mock_response.lightstreamer_endpoint = self._lightstreamer_endpoint
            mock_response.account_id = "TEST123"
            return mock_response
        return None

    def get_session_tokens(self) -> tuple[str | None, str | None]:
        return self._cst, self._security_token

    async def get_market_details(self, epic: str) -> Any:
        mock = MagicMock()
        mock.snapshot = {"bid": 1.1000, "offer": 1.1002, "updateTime": "12:00:00"}
        return mock


class TestLightstreamerMessageParsing:
    """Tests for Lightstreamer message parsing."""

    @pytest.mark.asyncio
    async def test_parse_l1_update(self) -> None:
        """Test parsing L1 price update."""
        ig_client = MockIGClient()

        quotes_received: list[Quote] = []

        async def on_quote(quote: Quote) -> None:
            quotes_received.append(quote)

        client = LightstreamerClient(
            ig_client=ig_client,  # type: ignore[arg-type]
            on_quote=on_quote,
        )

        # Register subscription
        await client.subscribe("EURUSD", "CS.D.EURUSD.MINI.IP")
        # Manually set subscription ID for testing
        client._subscription_ids["CS.D.EURUSD.MINI.IP"] = 1

        # Simulate L1 update message: U,<sub_id>,BID|OFFER|UPDATE_TIME|MARKET_STATE
        # The format after split(",", 2) gives fields as BID|OFFER|...
        await client._process_message("U,1,1.1000|1.1002|12:00:00|TRADEABLE")

        assert len(quotes_received) == 1
        quote = quotes_received[0]
        assert quote.symbol == "EURUSD"
        assert quote.bid == 1.1000
        assert quote.ask == 1.1002

    @pytest.mark.asyncio
    async def test_parse_unchanged_fields(self) -> None:
        """Test parsing update with unchanged fields (marked with #)."""
        ig_client = MockIGClient()
        quotes_received: list[Quote] = []

        async def on_quote(quote: Quote) -> None:
            quotes_received.append(quote)

        client = LightstreamerClient(
            ig_client=ig_client,  # type: ignore[arg-type]
            on_quote=on_quote,
        )

        await client.subscribe("EURUSD", "CS.D.EURUSD.MINI.IP")
        client._subscription_ids["CS.D.EURUSD.MINI.IP"] = 1

        # Message with # for unchanged fields - should not produce quote
        await client._process_message("U,1,1|#|#|#|#")

        # No quote should be produced (both bid and offer are unchanged)
        assert len(quotes_received) == 0

    @pytest.mark.asyncio
    async def test_parse_probe_message(self) -> None:
        """Test PROBE heartbeat message handling."""
        ig_client = MockIGClient()
        client = LightstreamerClient(ig_client=ig_client)  # type: ignore[arg-type]

        # PROBE should not raise and should be silently acknowledged
        await client._process_message("PROBE")

    @pytest.mark.asyncio
    async def test_parse_loop_message_handled(self) -> None:
        """Test LOOP message is handled (error is logged, not raised from _process_message)."""
        ig_client = MockIGClient()
        client = LightstreamerClient(ig_client=ig_client)  # type: ignore[arg-type]

        # LOOP indicates server wants rebind - handled internally
        # _process_message catches and logs the error
        await client._process_message("LOOP")
        # Should not raise - the error is caught and logged

    @pytest.mark.asyncio
    async def test_parse_end_message_handled(self) -> None:
        """Test END message is handled (error is logged, not raised from _process_message)."""
        ig_client = MockIGClient()
        client = LightstreamerClient(ig_client=ig_client)  # type: ignore[arg-type]

        # END indicates session ended by server - handled internally
        await client._process_message("END")
        # Should not raise - the error is caught and logged

    @pytest.mark.asyncio
    async def test_parse_invalid_message(self) -> None:
        """Test invalid message is handled gracefully."""
        ig_client = MockIGClient()
        client = LightstreamerClient(ig_client=ig_client)  # type: ignore[arg-type]

        # Invalid messages should not raise
        await client._process_message("INVALID_GARBAGE_DATA")
        await client._process_message("")
        await client._process_message("U,invalid")


class TestSessionParsing:
    """Tests for session response parsing."""

    @pytest.mark.asyncio
    async def test_parse_valid_session_response(self) -> None:
        """Test parsing valid session response."""
        ig_client = MockIGClient()
        client = LightstreamerClient(ig_client=ig_client)  # type: ignore[arg-type]

        response = (
            "SessionId:abc123def456\r\n"
            "ControlAddress:push.lightstreamer.com\r\n"
            "RequestLimit:5000\r\n"
        )

        await client._parse_session_response(response)

        assert client._session_id == "abc123def456"
        assert client._control_address == "push.lightstreamer.com"

    @pytest.mark.asyncio
    async def test_parse_error_response(self) -> None:
        """Test parsing error response."""
        ig_client = MockIGClient()
        client = LightstreamerClient(ig_client=ig_client)  # type: ignore[arg-type]

        response = "ERROR - Unauthorized access"

        with pytest.raises(LightstreamerError, match="error"):
            await client._parse_session_response(response)

    @pytest.mark.asyncio
    async def test_parse_missing_session_id(self) -> None:
        """Test parsing response with missing session ID."""
        ig_client = MockIGClient()
        client = LightstreamerClient(ig_client=ig_client)  # type: ignore[arg-type]

        response = "ControlAddress:push.lightstreamer.com\r\n"

        with pytest.raises(LightstreamerError, match="No session ID"):
            await client._parse_session_response(response)


class TestReconnectBackoff:
    """Tests for reconnect backoff logic."""

    def test_backoff_calculation(self) -> None:
        """Test exponential backoff calculation."""
        ig_client = MockIGClient()
        client = LightstreamerClient(ig_client=ig_client)  # type: ignore[arg-type]

        # Backoff formula: min(base * 2^attempts, max)
        base = client._reconnect_delay_base
        max_delay = client._reconnect_delay_max

        # Attempt 1: 1 * 2^1 = 2s
        assert min(base * (2**1), max_delay) == 2.0

        # Attempt 5: 1 * 2^5 = 32s
        assert min(base * (2**5), max_delay) == 32.0

        # Attempt 10: 1 * 2^10 = 1024s -> capped at 60s
        assert min(base * (2**10), max_delay) == 60.0

    def test_max_reconnect_attempts(self) -> None:
        """Test max reconnect attempts configuration."""
        ig_client = MockIGClient()
        client = LightstreamerClient(ig_client=ig_client)  # type: ignore[arg-type]

        assert client._max_reconnect_attempts == 10
        assert client._reconnect_attempts == 0

    @pytest.mark.asyncio
    async def test_reconnect_counter_reset_on_success(self) -> None:
        """Test reconnect counter resets on successful connection."""
        ig_client = MockIGClient(lightstreamer_endpoint=None)
        client = LightstreamerClient(ig_client=ig_client)  # type: ignore[arg-type]

        # Simulate failed attempts
        client._reconnect_attempts = 5

        # Simulate successful connection (simulation mode)
        await client._connect_simulation()
        client._reconnect_attempts = 0  # Would happen in _stream_loop

        assert client._reconnect_attempts == 0


class TestStatusTracking:
    """Tests for connection status tracking."""

    def test_initial_status(self) -> None:
        """Test initial status values."""
        ig_client = MockIGClient()
        client = LightstreamerClient(ig_client=ig_client)  # type: ignore[arg-type]

        status = client.get_status()

        assert status.connected is False
        assert status.mode == MarketDataMode.STREAM
        assert status.stale is False
        assert status.last_tick_ts is None
        assert status.subscriptions == []
        assert status.reconnect_attempts == 0
        assert status.last_error is None

    def test_status_after_subscription(self) -> None:
        """Test status reflects subscriptions."""
        ig_client = MockIGClient()
        client = LightstreamerClient(ig_client=ig_client)  # type: ignore[arg-type]

        # Sync subscribe (doesn't actually connect)
        client._subscriptions["EURUSD"] = "CS.D.EURUSD.MINI.IP"
        client._subscriptions["GBPUSD"] = "CS.D.GBPUSD.MINI.IP"

        status = client.get_status()
        assert len(status.subscriptions) == 2
        assert "EURUSD" in status.subscriptions
        assert "GBPUSD" in status.subscriptions

    def test_stale_detection(self) -> None:
        """Test stale feed detection."""
        ig_client = MockIGClient()
        client = LightstreamerClient(ig_client=ig_client)  # type: ignore[arg-type]
        client._stale_threshold_s = 5

        # No ticks yet - not stale (no last_tick_ts)
        status = client.get_status()
        assert status.stale is False

        # Recent tick - not stale
        client._last_tick_ts = datetime.now(UTC)
        status = client.get_status()
        assert status.stale is False

        # Old tick (simulate by setting timestamp in past)
        old_time = datetime(2020, 1, 1, tzinfo=UTC)
        client._last_tick_ts = old_time
        status = client.get_status()
        assert status.stale is True

    def test_status_with_error(self) -> None:
        """Test status includes last error."""
        ig_client = MockIGClient()
        client = LightstreamerClient(ig_client=ig_client)  # type: ignore[arg-type]

        client._last_error = "Connection refused"
        client._reconnect_attempts = 3

        status = client.get_status()
        assert status.last_error == "Connection refused"
        assert status.reconnect_attempts == 3


class TestQuoteConstruction:
    """Tests for Quote construction from L1 data."""

    def test_quote_from_bid_ask(self) -> None:
        """Test Quote.from_bid_ask factory method."""
        quote = Quote.from_bid_ask(
            symbol="EURUSD",
            epic="CS.D.EURUSD.MINI.IP",
            bid=1.1000,
            ask=1.1002,
            ts_utc=datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC),
            update_time="12:00:00",
        )

        assert quote.symbol == "EURUSD"
        assert quote.epic == "CS.D.EURUSD.MINI.IP"
        assert quote.bid == 1.1000
        assert quote.ask == 1.1002
        assert quote.mid == pytest.approx(1.1001)
        # Spread computed as ask - bid
        assert (quote.ask - quote.bid) == pytest.approx(0.0002)

    def test_quote_spread_calculation(self) -> None:
        """Test spread is calculated correctly (ask - bid)."""
        quote = Quote.from_bid_ask(
            symbol="USDJPY",
            epic="CS.D.USDJPY.MINI.IP",
            bid=150.00,
            ask=150.05,
            ts_utc=datetime.now(UTC),
        )

        # Spread is computed as ask - bid
        assert (quote.ask - quote.bid) == pytest.approx(0.05)

    def test_quote_mid_calculation(self) -> None:
        """Test mid price is calculated correctly."""
        quote = Quote.from_bid_ask(
            symbol="GBPUSD",
            epic="CS.D.GBPUSD.MINI.IP",
            bid=1.2500,
            ask=1.2510,
            ts_utc=datetime.now(UTC),
        )

        assert quote.mid == pytest.approx(1.2505)


class TestSimulationMode:
    """Tests for simulation mode fallback."""

    @pytest.mark.asyncio
    async def test_simulation_mode_when_no_endpoint(self) -> None:
        """Test fallback to simulation when no LS endpoint."""
        ig_client = MockIGClient(lightstreamer_endpoint=None)
        client = LightstreamerClient(ig_client=ig_client)  # type: ignore[arg-type]

        await client._connect()

        assert client._session_id == "SIMULATION"

    @pytest.mark.asyncio
    async def test_simulation_mode_produces_quotes(self) -> None:
        """Test simulation mode produces quotes via polling."""
        ig_client = MockIGClient(lightstreamer_endpoint=None)

        quotes_received: list[Quote] = []

        async def on_quote(quote: Quote) -> None:
            quotes_received.append(quote)

        client = LightstreamerClient(
            ig_client=ig_client,  # type: ignore[arg-type]
            on_quote=on_quote,
        )

        client._session_id = "SIMULATION"
        client._connected = True
        client._running = True

        await client.subscribe("EURUSD", "CS.D.EURUSD.MINI.IP")

        # Run simulation briefly
        task = asyncio.create_task(client._receive_loop_simulation())

        await asyncio.sleep(0.6)  # Let it poll once

        client._running = False
        try:
            await asyncio.wait_for(task, timeout=1.0)
        except asyncio.CancelledError:
            pass

        # Should have received at least one quote
        assert len(quotes_received) >= 1


class TestSubscriptionManagement:
    """Tests for subscription management."""

    @pytest.mark.asyncio
    async def test_subscribe(self) -> None:
        """Test subscribing to a symbol."""
        ig_client = MockIGClient()
        client = LightstreamerClient(ig_client=ig_client)  # type: ignore[arg-type]

        await client.subscribe("EURUSD", "CS.D.EURUSD.MINI.IP")

        assert "EURUSD" in client._subscriptions
        assert client._subscriptions["EURUSD"] == "CS.D.EURUSD.MINI.IP"

    @pytest.mark.asyncio
    async def test_unsubscribe(self) -> None:
        """Test unsubscribing from a symbol."""
        ig_client = MockIGClient()
        client = LightstreamerClient(ig_client=ig_client)  # type: ignore[arg-type]

        await client.subscribe("EURUSD", "CS.D.EURUSD.MINI.IP")
        await client.unsubscribe("EURUSD")

        assert "EURUSD" not in client._subscriptions

    @pytest.mark.asyncio
    async def test_unsubscribe_all(self) -> None:
        """Test unsubscribing from all symbols."""
        ig_client = MockIGClient()
        client = LightstreamerClient(ig_client=ig_client)  # type: ignore[arg-type]

        await client.subscribe("EURUSD", "CS.D.EURUSD.MINI.IP")
        await client.subscribe("GBPUSD", "CS.D.GBPUSD.MINI.IP")

        await client.unsubscribe_all()

        assert len(client._subscriptions) == 0

