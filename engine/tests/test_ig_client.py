"""
Tests for IG client with mocked HTTP responses.
"""

from unittest.mock import MagicMock

import pytest
import respx
from httpx import Response
from pydantic import SecretStr

from solat_engine.broker.ig.client import (
    AsyncIGClient,
    IGAuthError,
)
from solat_engine.broker.ig.rate_limit import RateLimiter, TokenBucket
from solat_engine.broker.ig.redaction import redact_dict, redact_headers
from solat_engine.broker.ig.types import (
    IGAccount,
    IGAccountStatus,
    IGAccountType,
    IGLoginResponse,
    IGMarketSearchItem,
)
from solat_engine.config import Settings, TradingMode
from solat_engine.logging import get_logger

# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def mock_settings() -> MagicMock:
    """Create mock settings for testing."""
    settings = MagicMock(spec=Settings)
    settings.ig_api_key = SecretStr("test-api-key")
    settings.ig_username = SecretStr("test-username")
    settings.ig_password = SecretStr("test-password")
    settings.ig_acc_type = TradingMode.DEMO
    settings.ig_base_url = "https://demo-api.ig.com/gateway/deal"
    settings.ig_request_timeout = 5
    settings.ig_max_retries = 1
    settings.ig_rate_limit_rps = 100.0  # High rate to avoid delays in tests
    settings.ig_rate_limit_burst = 100
    settings.has_ig_credentials = True
    return settings


@pytest.fixture
def ig_client(mock_settings: MagicMock) -> AsyncIGClient:
    """Create IG client for testing."""
    logger = get_logger("test")
    return AsyncIGClient(mock_settings, logger)


# =============================================================================
# Login Response Mock Data
# =============================================================================


def mock_login_response() -> dict:
    """Create mock login response data."""
    return {
        "clientId": "12345",
        "currentAccountId": "ABC123",
        "timezoneOffset": 0,
        "lightstreamerEndpoint": "https://apd.ig.com/push",
        "accounts": [
            {
                "accountId": "ABC123",
                "accountName": "Demo CFD",
                "accountType": "CFD",
                "status": "ENABLED",
                "currency": "GBP",
                "preferred": True,
            },
            {
                "accountId": "DEF456",
                "accountName": "Demo Spread",
                "accountType": "SPREADBET",
                "status": "ENABLED",
                "currency": "GBP",
                "preferred": False,
            },
        ],
    }


def mock_accounts_response() -> dict:
    """Create mock accounts response data."""
    return {
        "accounts": [
            {
                "accountId": "ABC123",
                "accountName": "Demo CFD",
                "accountType": "CFD",
                "status": "ENABLED",
                "currency": "GBP",
                "preferred": True,
            },
        ],
    }


def mock_market_search_response() -> dict:
    """Create mock market search response data."""
    return {
        "markets": [
            {
                "epic": "CS.D.EURUSD.CFD.IP",
                "instrumentName": "EUR/USD",
                "instrumentType": "CURRENCIES",
                "expiry": "-",
                "high": 1.0955,
                "low": 1.0923,
                "percentageChange": 0.05,
                "netChange": 0.0005,
                "bid": 1.0940,
                "offer": 1.0942,
                "marketStatus": "TRADEABLE",
            },
        ],
    }


def mock_market_details_response() -> dict:
    """Create mock market details response data."""
    return {
        "instrument": {
            "instrumentName": "EUR/USD",
            "instrumentType": "CURRENCIES",
            "expiry": "-",
            "lotSize": 1.0,
            "currency": "USD",
            "marginFactor": 3.33,
            "marginFactorUnit": "PERCENTAGE",
            "controlledRiskAllowed": True,
            "streamingPricesAvailable": True,
        },
        "dealingRules": {
            "minDealSize": {"value": 0.5},
            "maxDealSize": {"value": 200},
            "minSizeIncrement": {"value": 0.1},
            "minNormalStopOrLimitDistance": {"value": 5},
            "maxStopOrLimitDistance": {"value": 1000},
        },
        "snapshot": {
            "bid": 1.0940,
            "offer": 1.0942,
            "marketStatus": "TRADEABLE",
        },
    }


# =============================================================================
# Test Classes
# =============================================================================


class TestIGClientLogin:
    """Tests for IG client login."""

    @respx.mock
    @pytest.mark.asyncio
    async def test_login_success(self, ig_client: AsyncIGClient) -> None:
        """Successful login should store tokens and return response."""
        route = respx.post("https://demo-api.ig.com/gateway/deal/session").mock(
            return_value=Response(
                200,
                json=mock_login_response(),
                headers={
                    "CST": "mock-cst-token",
                    "X-SECURITY-TOKEN": "mock-security-token",
                },
            )
        )

        response = await ig_client.login()

        assert route.called
        assert ig_client.is_authenticated
        assert response.account_id == "ABC123"
        assert len(response.accounts) == 2
        assert response.lightstreamer_endpoint == "https://apd.ig.com/push"

    @respx.mock
    @pytest.mark.asyncio
    async def test_login_missing_tokens(self, ig_client: AsyncIGClient) -> None:
        """Login without tokens in response should raise IGAuthError."""
        respx.post("https://demo-api.ig.com/gateway/deal/session").mock(
            return_value=Response(
                200,
                json=mock_login_response(),
                headers={},  # No tokens
            )
        )

        with pytest.raises(IGAuthError, match="missing session tokens"):
            await ig_client.login()

    @respx.mock
    @pytest.mark.asyncio
    async def test_login_invalid_credentials(self, ig_client: AsyncIGClient) -> None:
        """Invalid credentials should raise IGAuthError."""
        respx.post("https://demo-api.ig.com/gateway/deal/session").mock(
            return_value=Response(
                401,
                json={"errorCode": "error.security.invalid-details"},
            )
        )

        with pytest.raises(IGAuthError, match="Authentication failed"):
            await ig_client.login()

    @pytest.mark.asyncio
    async def test_login_missing_credentials(self) -> None:
        """Login without credentials should raise IGAuthError."""
        settings = MagicMock(spec=Settings)
        settings.ig_api_key = None  # No API key
        settings.ig_username = None
        settings.ig_password = None
        settings.has_ig_credentials = False
        # Set required client initialization attributes
        settings.ig_base_url = "https://demo-api.ig.com/gateway/deal"
        settings.ig_request_timeout = 5
        settings.ig_max_retries = 1
        settings.ig_rate_limit_rps = 10.0
        settings.ig_rate_limit_burst = 5
        logger = get_logger("test")
        client = AsyncIGClient(settings, logger)

        with pytest.raises(IGAuthError, match="IG_API_KEY not configured"):
            await client.login()


class TestIGClientAccounts:
    """Tests for IG client accounts endpoint."""

    @respx.mock
    @pytest.mark.asyncio
    async def test_get_accounts(self, ig_client: AsyncIGClient) -> None:
        """Get accounts should return account list."""
        # Mock login first
        respx.post("https://demo-api.ig.com/gateway/deal/session").mock(
            return_value=Response(
                200,
                json=mock_login_response(),
                headers={
                    "CST": "mock-cst-token",
                    "X-SECURITY-TOKEN": "mock-security-token",
                },
            )
        )
        respx.get("https://demo-api.ig.com/gateway/deal/accounts").mock(
            return_value=Response(200, json=mock_accounts_response())
        )

        accounts = await ig_client.get_accounts()

        assert len(accounts) == 1
        assert accounts[0].account_id == "ABC123"
        assert accounts[0].account_type == IGAccountType.CFD


class TestIGClientMarketSearch:
    """Tests for IG client market search."""

    @respx.mock
    @pytest.mark.asyncio
    async def test_search_markets(self, ig_client: AsyncIGClient) -> None:
        """Search markets should return market list."""
        # Mock login
        respx.post("https://demo-api.ig.com/gateway/deal/session").mock(
            return_value=Response(
                200,
                json=mock_login_response(),
                headers={
                    "CST": "mock-cst-token",
                    "X-SECURITY-TOKEN": "mock-security-token",
                },
            )
        )
        respx.get("https://demo-api.ig.com/gateway/deal/markets").mock(
            return_value=Response(200, json=mock_market_search_response())
        )

        markets = await ig_client.search_markets("EUR/USD")

        assert len(markets) == 1
        assert markets[0].epic == "CS.D.EURUSD.CFD.IP"
        assert markets[0].instrument_name == "EUR/USD"

    @respx.mock
    @pytest.mark.asyncio
    async def test_search_markets_max_results(self, ig_client: AsyncIGClient) -> None:
        """Search markets should cap results at 50."""
        # Mock login
        respx.post("https://demo-api.ig.com/gateway/deal/session").mock(
            return_value=Response(
                200,
                json=mock_login_response(),
                headers={
                    "CST": "mock-cst-token",
                    "X-SECURITY-TOKEN": "mock-security-token",
                },
            )
        )
        # Return many results
        many_markets = {
            "markets": [{"epic": f"EPIC{i}", "instrumentName": f"Market {i}"} for i in range(100)]
        }
        respx.get("https://demo-api.ig.com/gateway/deal/markets").mock(
            return_value=Response(200, json=many_markets)
        )

        # Request 100 but should cap at 50
        markets = await ig_client.search_markets("test", max_results=100)
        assert len(markets) == 50


class TestIGClientMarketDetails:
    """Tests for IG client market details."""

    @respx.mock
    @pytest.mark.asyncio
    async def test_get_market_details(self, ig_client: AsyncIGClient) -> None:
        """Get market details should return details."""
        # Mock login
        respx.post("https://demo-api.ig.com/gateway/deal/session").mock(
            return_value=Response(
                200,
                json=mock_login_response(),
                headers={
                    "CST": "mock-cst-token",
                    "X-SECURITY-TOKEN": "mock-security-token",
                },
            )
        )
        respx.get("https://demo-api.ig.com/gateway/deal/markets/CS.D.EURUSD.CFD.IP").mock(
            return_value=Response(200, json=mock_market_details_response())
        )

        details = await ig_client.get_market_details("CS.D.EURUSD.CFD.IP")

        assert details is not None
        assert details.epic == "CS.D.EURUSD.CFD.IP"
        assert details.instrument_name == "EUR/USD"
        assert details.dealing_rules is not None

    @respx.mock
    @pytest.mark.asyncio
    async def test_get_market_details_not_found(self, ig_client: AsyncIGClient) -> None:
        """Get market details for non-existent market should return None."""
        # Mock login
        respx.post("https://demo-api.ig.com/gateway/deal/session").mock(
            return_value=Response(
                200,
                json=mock_login_response(),
                headers={
                    "CST": "mock-cst-token",
                    "X-SECURITY-TOKEN": "mock-security-token",
                },
            )
        )
        respx.get("https://demo-api.ig.com/gateway/deal/markets/NONEXISTENT").mock(
            return_value=Response(404, json={"errorCode": "error.market.not-found"})
        )

        details = await ig_client.get_market_details("NONEXISTENT")
        assert details is None


class TestRateLimiter:
    """Tests for rate limiter."""

    @pytest.mark.asyncio
    async def test_token_bucket_initial_tokens(self) -> None:
        """Token bucket should start with full tokens."""
        bucket = TokenBucket(rate=10, burst=5)
        assert bucket.available() == 5

    @pytest.mark.asyncio
    async def test_token_bucket_acquire_no_wait(self) -> None:
        """Acquire with available tokens should not wait."""
        bucket = TokenBucket(rate=10, burst=5)
        wait_time = await bucket.acquire(1)
        assert wait_time == 0.0
        assert bucket.tokens == 4

    @pytest.mark.asyncio
    async def test_rate_limiter_stats(self) -> None:
        """Rate limiter should track statistics."""
        limiter = RateLimiter(requests_per_second=10, burst=5)

        await limiter.acquire()
        await limiter.acquire()

        stats = limiter.stats
        assert stats["total_requests"] == 2
        assert stats["rate_limit_rps"] == 10
        assert stats["burst_limit"] == 5


class TestRedaction:
    """Tests for credential redaction."""

    def test_redact_headers_cst(self) -> None:
        """Should redact CST header."""
        headers = {"CST": "secret-token", "Content-Type": "application/json"}
        redacted = redact_headers(headers)

        assert redacted["CST"] == "[REDACTED]"
        assert redacted["Content-Type"] == "application/json"

    def test_redact_headers_security_token(self) -> None:
        """Should redact X-SECURITY-TOKEN header."""
        headers = {"X-SECURITY-TOKEN": "secret-token", "Accept": "application/json"}
        redacted = redact_headers(headers)

        assert redacted["X-SECURITY-TOKEN"] == "[REDACTED]"
        assert redacted["Accept"] == "application/json"

    def test_redact_headers_api_key(self) -> None:
        """Should redact API key header."""
        headers = {"X-IG-API-KEY": "my-api-key", "Host": "api.ig.com"}
        redacted = redact_headers(headers)

        assert redacted["X-IG-API-KEY"] == "[REDACTED]"
        assert redacted["Host"] == "api.ig.com"

    def test_redact_headers_case_insensitive(self) -> None:
        """Should redact headers case-insensitively."""
        headers = {"cst": "secret", "x-security-token": "secret", "x-ig-api-key": "secret"}
        redacted = redact_headers(headers)

        assert all(v == "[REDACTED]" for v in redacted.values())

    def test_redact_dict_password(self) -> None:
        """Should redact password in dict."""
        data = {"username": "user", "password": "secret123"}
        redacted = redact_dict(data)

        assert redacted["username"] == "user"
        assert redacted["password"] == "[REDACTED]"

    def test_redact_dict_nested(self) -> None:
        """Should redact nested sensitive values."""
        data = {"auth": {"password": "secret", "token": "abc123"}}
        redacted = redact_dict(data)

        assert redacted["auth"]["password"] == "[REDACTED]"


class TestIGTypes:
    """Tests for IG type models."""

    def test_ig_account_from_api_response(self) -> None:
        """IGAccount should parse from API response."""
        data = {
            "accountId": "ABC123",
            "accountName": "Demo CFD",
            "accountType": "CFD",
            "status": "ENABLED",
            "currency": "GBP",
            "preferred": True,
        }
        account = IGAccount.model_validate(data)

        assert account.account_id == "ABC123"
        assert account.account_type == IGAccountType.CFD
        assert account.status == IGAccountStatus.ENABLED

    def test_ig_login_response_excludes_tokens(self) -> None:
        """IGLoginResponse should not include token fields."""
        response = IGLoginResponse(
            client_id="123",
            account_id="ABC123",
            accounts=[],
        )
        # Tokens should not be serializable
        data = response.model_dump()
        assert "cst" not in data
        assert "security_token" not in data

    def test_ig_market_search_item(self) -> None:
        """IGMarketSearchItem should parse from API response."""
        data = {
            "epic": "CS.D.EURUSD.CFD.IP",
            "instrumentName": "EUR/USD",
            "instrumentType": "CURRENCIES",
            "bid": "1.0940",
            "offer": "1.0942",
        }
        item = IGMarketSearchItem.model_validate(data)

        assert item.epic == "CS.D.EURUSD.CFD.IP"
        assert item.instrument_name == "EUR/USD"
