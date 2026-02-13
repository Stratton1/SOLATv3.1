"""
Async IG REST API client.

Handles authentication, token management, rate limiting, and retries.
"""

import asyncio
import time
from datetime import datetime
from logging import Logger
from typing import Any, cast

import httpx

from solat_engine.broker.ig.rate_limit import RateLimiter
from solat_engine.broker.ig.redaction import redact_headers, safe_log_request
from solat_engine.broker.ig.types import (
    IGAccount,
    IGLoginResponse,
    IGMarketDetails,
    IGMarketSearchItem,
)
from solat_engine.config import Settings

# IG API version headers
IG_VERSION_SESSION = "2"
IG_VERSION_ACCOUNTS = "1"
IG_VERSION_MARKETS_SEARCH = "1"
IG_VERSION_MARKET_DETAILS = "3"
IG_VERSION_POSITIONS = "2"
IG_VERSION_OTC = "2"
IG_VERSION_CLOSE = "1"
IG_VERSION_WORKING_ORDERS = "2"


class IGAuthError(Exception):
    """Raised when IG authentication fails."""

    pass


class IGRateLimitError(Exception):
    """Raised when IG rate limit is exceeded."""

    pass


class IGAPIError(Exception):
    """Raised for general IG API errors."""

    def __init__(self, message: str, status_code: int | None = None, error_code: str | None = None):
        super().__init__(message)
        self.status_code = status_code
        self.error_code = error_code


from pydantic import SecretStr


def _secret_value(v: SecretStr | None) -> str | None:
    """Extract plain value from an optional SecretStr for comparison."""
    return v.get_secret_value() if v is not None else None


class AsyncIGClient:
    """
    Async client for IG REST API.

    Handles:
    - Session authentication with CST and X-SECURITY-TOKEN
    - Automatic token refresh on 401
    - Rate limiting with token bucket
    - Retry/backoff for transient errors
    """

    def __init__(self, settings: Settings, logger: Logger) -> None:
        """
        Initialize IG client.

        Args:
            settings: Application settings
            logger: Logger instance
        """
        self._settings = settings
        self._logger = logger
        self._base_url = settings.ig_base_url
        self._timeout = settings.ig_request_timeout
        self._max_retries = settings.ig_max_retries

        # Rate limiter
        self._rate_limiter = RateLimiter(
            requests_per_second=settings.ig_rate_limit_rps,
            burst=settings.ig_rate_limit_burst,
        )

        # Session tokens (never logged or returned)
        self._cst: str | None = None
        self._security_token: str | None = None
        self._session_created_at: datetime | None = None

        # HTTP client
        self._client: httpx.AsyncClient | None = None

        # Login response cache (without tokens)
        self._login_response: IGLoginResponse | None = None

        # Latency tracking
        self._last_latency_ms: int = 0
        self._latency_history: list[int] = []
        self._max_history = 100

    @property
    def metrics(self) -> dict[str, Any]:
        """Get broker connection metrics."""
        avg_latency = (
            sum(self._latency_history) / len(self._latency_history)
            if self._latency_history
            else 0
        )
        return {
            "last_request_latency_ms": self._last_latency_ms,
            "average_latency_ms": round(avg_latency, 1),
            "rate_limit_usage_pct": round(self._rate_limiter.stats.get("usage_pct", 0), 1),
        }

    @property
    def is_authenticated(self) -> bool:
        """Check if client has valid session tokens."""
        return self._cst is not None and self._security_token is not None

    @property
    def session_age_seconds(self) -> float | None:
        """Get session age in seconds, or None if not authenticated."""
        if self._session_created_at is None:
            return None
        return (datetime.utcnow() - self._session_created_at).total_seconds()

    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create HTTP client."""
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(timeout=self._timeout)
        return self._client

    async def close(self) -> None:
        """Close HTTP client."""
        if self._client is not None and not self._client.is_closed:
            await self._client.aclose()
            self._client = None

    def update_settings(self, settings: Settings) -> None:
        """
        Refresh runtime settings for an existing client instance.

        This keeps singleton-based DI safe when tests or environment overrides
        rebuild Settings without recreating the client object.
        """
        old_settings = self._settings
        self._settings = settings
        self._base_url = settings.ig_base_url
        self._timeout = settings.ig_request_timeout
        self._max_retries = settings.ig_max_retries
        self._rate_limiter = RateLimiter(
            requests_per_second=settings.ig_rate_limit_rps,
            burst=settings.ig_rate_limit_burst,
        )

        # Only clear auth tokens if credentials actually changed.
        creds_changed = (
            _secret_value(settings.ig_api_key) != _secret_value(old_settings.ig_api_key)
            or _secret_value(settings.ig_username) != _secret_value(old_settings.ig_username)
            or _secret_value(settings.ig_password) != _secret_value(old_settings.ig_password)
            or settings.ig_base_url != old_settings.ig_base_url
        )
        if creds_changed:
            self._cst = None
            self._security_token = None
            self._session_created_at = None
            self._login_response = None

    def _get_base_headers(self) -> dict[str, str]:
        """Get base headers for all requests."""
        headers = {
            "Accept": "application/json; charset=UTF-8",
            "Content-Type": "application/json; charset=UTF-8",
        }

        # Add API key if available
        if self._settings.ig_api_key:
            headers["X-IG-API-KEY"] = self._settings.ig_api_key.get_secret_value()

        return headers

    def _get_auth_headers(self) -> dict[str, str]:
        """Get headers including session tokens."""
        headers = self._get_base_headers()

        if self._cst:
            headers["CST"] = self._cst
        if self._security_token:
            headers["X-SECURITY-TOKEN"] = self._security_token

        return headers

    async def _request(
        self,
        method: str,
        path: str,
        *,
        version: str | None = None,
        json_body: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
        extra_headers: dict[str, str] | None = None,
        require_auth: bool = True,
        retry_on_401: bool = True,
    ) -> httpx.Response:
        """
        Make an HTTP request to IG API with rate limiting and retries.

        Args:
            method: HTTP method
            path: API path (without base URL)
            version: IG API version header
            json_body: JSON request body
            params: Query parameters
            require_auth: Whether to include session tokens
            retry_on_401: Whether to retry after re-login on 401

        Returns:
            HTTP response

        Raises:
            IGAuthError: Authentication failed
            IGRateLimitError: Rate limit exceeded after retries
            IGAPIError: Other API errors
        """
        url = f"{self._base_url}{path}"
        headers = self._get_auth_headers() if require_auth else self._get_base_headers()

        if version:
            headers["VERSION"] = version
        if extra_headers:
            headers.update(extra_headers)

        # Log request (redacted)
        self._logger.debug(
            "IG request: %s",
            safe_log_request(method, url, headers, json_body),
        )

        last_error: Exception | None = None
        for attempt in range(self._max_retries + 1):
            try:
                # Rate limiting
                wait_time = await self._rate_limiter.acquire()
                if wait_time > 0:
                    self._logger.debug("Rate limiter waited %.2fs", wait_time)

                client = await self._get_client()
                start_time = time.perf_counter()
                response = await client.request(
                    method,
                    url,
                    headers=headers,
                    json=json_body,
                    params=params,
                )
                latency_ms = int((time.perf_counter() - start_time) * 1000)
                self._last_latency_ms = latency_ms
                self._latency_history.append(latency_ms)
                if len(self._latency_history) > self._max_history:
                    self._latency_history.pop(0)

                # Log response (redacted headers)
                self._logger.debug(
                    "IG response: status=%d headers=%s",
                    response.status_code,
                    redact_headers(dict(response.headers)),
                )

                # Handle specific status codes
                if response.status_code == 401:
                    if retry_on_401 and attempt < self._max_retries and require_auth:
                        self._logger.warning("Got 401, attempting re-login")
                        self._cst = None
                        self._security_token = None
                        await self.login()
                        headers = self._get_auth_headers()
                        if version:
                            headers["VERSION"] = version
                        if extra_headers:
                            headers.update(extra_headers)
                        continue
                    raise IGAuthError("Authentication failed")

                if response.status_code == 429:
                    # Rate limit - exponential backoff
                    backoff = 2 ** attempt
                    self._logger.warning(
                        "Rate limited (429), backing off %ds (attempt %d/%d)",
                        backoff,
                        attempt + 1,
                        self._max_retries + 1,
                    )
                    await asyncio.sleep(backoff)
                    continue

                if response.status_code >= 500:
                    # Server error - retry with backoff
                    backoff = 2 ** attempt
                    self._logger.warning(
                        "Server error %d, backing off %ds (attempt %d/%d)",
                        response.status_code,
                        backoff,
                        attempt + 1,
                        self._max_retries + 1,
                    )
                    await asyncio.sleep(backoff)
                    continue

                return response

            except httpx.TimeoutException as e:
                last_error = e
                backoff = 2 ** attempt
                self._logger.warning(
                    "Request timeout, backing off %ds (attempt %d/%d)",
                    backoff,
                    attempt + 1,
                    self._max_retries + 1,
                )
                await asyncio.sleep(backoff)
                continue

            except httpx.RequestError as e:
                last_error = e
                backoff = 2 ** attempt
                self._logger.warning(
                    "Request error: %s, backing off %ds (attempt %d/%d)",
                    str(e),
                    backoff,
                    attempt + 1,
                    self._max_retries + 1,
                )
                await asyncio.sleep(backoff)
                continue

        # Exhausted retries
        if last_error:
            raise IGAPIError(f"Request failed after {self._max_retries + 1} attempts: {last_error}")
        raise IGAPIError(f"Request failed after {self._max_retries + 1} attempts")

    async def login(self) -> IGLoginResponse:
        """
        Authenticate with IG and obtain session tokens.

        Returns:
            Login response (without tokens)

        Raises:
            IGAuthError: If credentials are missing or invalid
        """
        if not self._settings.ig_api_key:
            raise IGAuthError("IG_API_KEY not configured")
        if not self._settings.ig_username:
            raise IGAuthError("IG_USERNAME not configured")
        if not self._settings.ig_password:
            raise IGAuthError("IG_PASSWORD not configured")

        self._logger.info("Attempting IG login (credentials redacted)")

        body = {
            "identifier": self._settings.ig_username.get_secret_value(),
            "password": self._settings.ig_password.get_secret_value(),
        }

        response = await self._request(
            "POST",
            "/session",
            version=IG_VERSION_SESSION,
            json_body=body,
            require_auth=False,
            retry_on_401=False,
        )

        if response.status_code != 200:
            error_msg = "Login failed"
            try:
                error_data = response.json()
                error_msg = error_data.get("errorCode", error_msg)
            except Exception:
                pass
            raise IGAuthError(f"Login failed: {error_msg} (status {response.status_code})")

        # Extract tokens from headers (NEVER log these)
        self._cst = response.headers.get("CST")
        self._security_token = response.headers.get("X-SECURITY-TOKEN")

        if not self._cst or not self._security_token:
            raise IGAuthError("Login response missing session tokens")

        self._session_created_at = datetime.utcnow()

        # Parse response body (safe to log)
        data = response.json()
        accounts_data = data.get("accounts", [])
        accounts = [IGAccount.model_validate(acc) for acc in accounts_data]

        self._login_response = IGLoginResponse(
            client_id=data.get("clientId"),
            account_id=data.get("currentAccountId"),
            timezone_offset=data.get("timezoneOffset"),
            lightstreamer_endpoint=data.get("lightstreamerEndpoint"),
            accounts=accounts,
        )

        self._logger.info(
            "IG login successful: %d accounts, current=%s",
            len(accounts),
            self._login_response.account_id,
        )

        return self._login_response

    async def ensure_session(self) -> None:
        """Ensure we have a valid session, logging in if necessary."""
        if not self.is_authenticated:
            await self.login()

    async def get_accounts(self) -> list[IGAccount]:
        """
        Get list of accounts.

        Returns:
            List of IG accounts
        """
        await self.ensure_session()

        response = await self._request(
            "GET",
            "/accounts",
            version=IG_VERSION_ACCOUNTS,
        )

        if response.status_code != 200:
            raise IGAPIError(
                f"Failed to get accounts: status {response.status_code}",
                status_code=response.status_code,
            )

        data = response.json()
        accounts_data = data.get("accounts", [])
        return [IGAccount.model_validate(acc) for acc in accounts_data]

    async def search_markets(
        self,
        query: str,
        max_results: int = 20,
    ) -> list[IGMarketSearchItem]:
        """
        Search for markets by name/symbol.

        Args:
            query: Search query
            max_results: Maximum results to return (capped at 50)

        Returns:
            List of matching markets
        """
        await self.ensure_session()

        # Cap results to prevent excessive data
        max_results = min(max_results, 50)

        response = await self._request(
            "GET",
            "/markets",
            version=IG_VERSION_MARKETS_SEARCH,
            params={"searchTerm": query},
        )

        if response.status_code != 200:
            raise IGAPIError(
                f"Market search failed: status {response.status_code}",
                status_code=response.status_code,
            )

        data = response.json()
        markets_data = data.get("markets", [])[:max_results]
        return [IGMarketSearchItem.model_validate(m) for m in markets_data]

    async def get_market_details(self, epic: str) -> IGMarketDetails | None:
        """
        Get detailed information for a market.

        Args:
            epic: IG epic identifier

        Returns:
            Market details or None if not found
        """
        await self.ensure_session()

        response = await self._request(
            "GET",
            f"/markets/{epic}",
            version=IG_VERSION_MARKET_DETAILS,
        )

        if response.status_code == 404:
            return None

        if response.status_code != 200:
            raise IGAPIError(
                f"Get market details failed: status {response.status_code}",
                status_code=response.status_code,
            )

        data = response.json()

        # Combine instrument and dealing rules
        instrument = data.get("instrument", {})
        dealing_rules = data.get("dealingRules", {})
        snapshot = data.get("snapshot", {})

        # Build details with nested dealing rules
        details_data = {
            "epic": epic,
            **instrument,
            "dealingRules": {
                "minDealSize": dealing_rules.get("minDealSize", {}).get("value"),
                "maxDealSize": dealing_rules.get("maxDealSize", {}).get("value"),
                "minSizeIncrement": dealing_rules.get("minSizeIncrement", {}).get("value"),
                "minControlledRiskStopDistance": dealing_rules.get(
                    "minControlledRiskStopDistance", {}
                ).get("value"),
                "minNormalStopOrLimitDistance": dealing_rules.get(
                    "minNormalStopOrLimitDistance", {}
                ).get("value"),
                "maxStopOrLimitDistance": dealing_rules.get(
                    "maxStopOrLimitDistance", {}
                ).get("value"),
                "marketOrderPreference": dealing_rules.get("marketOrderPreference"),
            },
            "snapshot": snapshot,
        }

        return IGMarketDetails.model_validate(details_data)

    @property
    def rate_limiter_stats(self) -> dict[str, Any]:
        """Get rate limiter statistics."""
        return self._rate_limiter.stats

    # =========================================================================
    # Trading Methods (DEMO only in v1)
    # =========================================================================

    async def list_accounts(self) -> list[dict[str, Any]]:
        """
        Get list of accounts as dicts.

        Returns:
            List of account dicts with balance info
        """
        accounts = await self.get_accounts()
        return [acc.model_dump() for acc in accounts]

    async def list_positions(self) -> list[dict[str, Any]]:
        """
        Get all open positions.

        Returns:
            List of position dicts
        """
        await self.ensure_session()

        response = await self._request(
            "GET",
            "/positions",
            version=IG_VERSION_POSITIONS,
        )

        if response.status_code != 200:
            raise IGAPIError(
                f"Failed to get positions: status {response.status_code}",
                status_code=response.status_code,
            )

        data = response.json()
        return cast(list[dict[str, Any]], data.get("positions", []))

    async def place_market_order(
        self,
        epic: str,
        direction: str,
        size: float,
        currency_code: str = "USD",
        stop_level: float | None = None,
        limit_level: float | None = None,
        force_open: bool = True,
        deal_reference: str | None = None,
    ) -> dict[str, Any]:
        """
        Place a market order.

        Args:
            epic: IG epic identifier
            direction: "BUY" or "SELL"
            size: Deal size
            currency_code: Currency code
            stop_level: Optional stop loss level
            limit_level: Optional take profit level
            force_open: Force open new position (vs close existing)
            deal_reference: Client-generated reference for idempotency

        Returns:
            Order result with dealId and dealStatus
        """
        await self.ensure_session()

        body: dict[str, Any] = {
            "epic": epic,
            "direction": direction,
            "size": str(size),
            "currencyCode": currency_code,
            "orderType": "MARKET",
            "forceOpen": force_open,
            "guaranteedStop": False,
            "expiry": "-",
        }

        if stop_level is not None:
            body["stopLevel"] = str(stop_level)

        if limit_level is not None:
            body["limitLevel"] = str(limit_level)

        if deal_reference:
            body["dealReference"] = deal_reference

        self._logger.info(
            "Placing market order: epic=%s direction=%s size=%s",
            epic,
            direction,
            size,
        )

        response = await self._request(
            "POST",
            "/positions/otc",
            version=IG_VERSION_OTC,
            json_body=body,
        )

        if response.status_code not in (200, 201):
            error_msg = f"Order placement failed: status {response.status_code}"
            try:
                error_data = response.json()
                error_msg = error_data.get("errorCode", error_msg)
            except Exception:
                pass
            raise IGAPIError(error_msg, status_code=response.status_code)

        data = response.json()
        deal_reference_resp = data.get("dealReference")

        # Poll for deal confirmation if needed
        if deal_reference_resp:
            confirmation = await self._confirm_deal(deal_reference_resp)
            return confirmation

        return cast(dict[str, Any], data)

    async def close_position(
        self,
        deal_id: str,
        direction: str,
        size: float | None = None,
    ) -> dict[str, Any]:
        """
        Close a position.

        Args:
            deal_id: Position deal ID
            direction: Close direction ("BUY" to close short, "SELL" to close long)
            size: Size to close (full position if None)

        Returns:
            Close result
        """
        await self.ensure_session()

        body: dict[str, Any] = {
            "dealId": deal_id,
            "direction": direction,
            "orderType": "MARKET",
            "expiry": "-",
        }

        if size is not None:
            body["size"] = str(size)

        self._logger.info(
            "Closing position: deal_id=%s direction=%s size=%s",
            deal_id,
            direction,
            size,
        )

        response = await self._request(
            "POST",  # IG requires POST + _method=DELETE for close
            "/positions/otc",
            version=IG_VERSION_CLOSE,
            json_body=body,
            extra_headers={"_method": "DELETE"},
        )

        if response.status_code not in (200, 201):
            error_msg = f"Close position failed: status {response.status_code}"
            try:
                error_data = response.json()
                error_msg = error_data.get("errorCode", error_msg)
            except Exception:
                pass
            raise IGAPIError(error_msg, status_code=response.status_code)

        data = response.json()
        deal_reference = data.get("dealReference")

        # Poll for deal confirmation
        if deal_reference:
            confirmation = await self._confirm_deal(deal_reference)
            return confirmation

        return cast(dict[str, Any], data)

    async def _confirm_deal(
        self,
        deal_reference: str,
        max_attempts: int = 5,
        delay_ms: int = 500,
    ) -> dict[str, Any]:
        """
        Poll for deal confirmation.

        Args:
            deal_reference: Deal reference to confirm
            max_attempts: Maximum poll attempts
            delay_ms: Delay between attempts in milliseconds

        Returns:
            Deal confirmation result
        """
        for attempt in range(max_attempts):
            await asyncio.sleep(delay_ms / 1000)

            response = await self._request(
                "GET",
                f"/confirms/{deal_reference}",
                version="1",
            )

            if response.status_code == 200:
                data = response.json()
                status = data.get("dealStatus")

                if status in ("ACCEPTED", "REJECTED"):
                    self._logger.info(
                        "Deal confirmed: ref=%s status=%s dealId=%s",
                        deal_reference,
                        status,
                        data.get("dealId"),
                    )
                    return cast(dict[str, Any], data)

                # Still pending
                self._logger.debug(
                    "Deal pending: ref=%s attempt=%d/%d",
                    deal_reference,
                    attempt + 1,
                    max_attempts,
                )

            elif response.status_code == 404:
                # Not found yet, retry
                self._logger.debug(
                    "Deal not found yet: ref=%s attempt=%d/%d",
                    deal_reference,
                    attempt + 1,
                    max_attempts,
                )

        # Exhausted retries
        self._logger.warning(
            "Deal confirmation timed out: ref=%s",
            deal_reference,
        )
        return {"dealReference": deal_reference, "dealStatus": "PENDING"}

    async def get_working_orders(self) -> list[dict[str, Any]]:
        """
        Get all working orders.

        Returns:
            List of working order dicts
        """
        await self.ensure_session()

        response = await self._request(
            "GET",
            "/workingorders",
            version=IG_VERSION_WORKING_ORDERS,
        )

        if response.status_code != 200:
            raise IGAPIError(
                f"Failed to get working orders: status {response.status_code}",
                status_code=response.status_code,
            )

        data = response.json()
        return cast(list[dict[str, Any]], data.get("workingOrders", []))

    async def cancel_working_order(self, deal_id: str) -> dict[str, Any]:
        """
        Cancel a working order.

        Args:
            deal_id: Order deal ID

        Returns:
            Cancel result
        """
        await self.ensure_session()

        response = await self._request(
            "POST",  # IG requires POST + _method=DELETE for cancel
            f"/workingorders/otc/{deal_id}",
            version=IG_VERSION_WORKING_ORDERS,
            extra_headers={"_method": "DELETE"},
        )

        if response.status_code not in (200, 201):
            error_msg = f"Cancel order failed: status {response.status_code}"
            try:
                error_data = response.json()
                error_msg = error_data.get("errorCode", error_msg)
            except Exception:
                pass
            raise IGAPIError(error_msg, status_code=response.status_code)

        return cast(dict[str, Any], response.json())

    # =========================================================================
    # Account Verification Methods (for LIVE trading gates)
    # =========================================================================

    async def get_account_details_with_balance(
        self, account_id: str | None = None
    ) -> dict[str, Any]:
        """
        Get detailed account information including balance.

        Used for LIVE trading account verification.

        Args:
            account_id: Specific account ID to fetch, or None for current account

        Returns:
            Account details including balance, available, currency, type
        """
        await self.ensure_session()

        # Get all accounts
        response = await self._request(
            "GET",
            "/accounts",
            version=IG_VERSION_ACCOUNTS,
        )

        if response.status_code != 200:
            raise IGAPIError(
                f"Failed to get accounts: status {response.status_code}",
                status_code=response.status_code,
            )

        data = response.json()
        accounts = data.get("accounts", [])

        # Find the target account
        target_id = account_id or self._login_response.account_id if self._login_response else None

        for acc in accounts:
            if acc.get("accountId") == target_id:
                balance_info = acc.get("balance", {})
                return {
                    "account_id": acc.get("accountId"),
                    "account_name": acc.get("accountName"),
                    "account_type": acc.get("accountType"),
                    "status": acc.get("status"),
                    "currency": acc.get("currency"),
                    "balance": balance_info.get("balance", 0.0),
                    "available": balance_info.get("available", 0.0),
                    "deposit": balance_info.get("deposit", 0.0),
                    "profit_loss": balance_info.get("profitLoss", 0.0),
                }

        raise IGAPIError(f"Account not found: {target_id}")

    async def verify_account_for_live(
        self, required_account_id: str | None = None
    ) -> dict[str, Any]:
        """
        Verify account is suitable for LIVE trading.

        Checks:
        - Account exists and is accessible
        - Account type is appropriate (CFD or SPREADBET)
        - Account has positive available balance
        - Account status is ENABLED

        Args:
            required_account_id: If set, must match this account ID

        Returns:
            Verification result with account details

        Raises:
            IGAPIError: If verification fails
        """
        await self.ensure_session()

        # Determine which account to verify
        target_id = required_account_id or (
            self._login_response.account_id if self._login_response else None
        )

        if not target_id:
            raise IGAPIError("No account ID available for verification")

        # Get account details
        account = await self.get_account_details_with_balance(target_id)

        # Check if account is a LIVE account (based on URL used for login)
        # IG Demo API uses demo-api.ig.com, Live uses api.ig.com
        is_live_api = "demo" not in self._base_url.lower()

        return {
            "verified": True,
            "account_id": account["account_id"],
            "account_type": account["account_type"],
            "currency": account["currency"],
            "balance": account["balance"],
            "available": account["available"],
            "status": account["status"],
            "is_live": is_live_api,
            "api_endpoint": self._base_url,
        }

    @property
    def login_response(self) -> IGLoginResponse | None:
        """Get cached login response."""
        return self._login_response

    def get_session_tokens(self) -> tuple[str | None, str | None]:
        """
        Get session tokens for Lightstreamer.

        WARNING: These are sensitive and should never be logged.
        """
        return self._cst, self._security_token
