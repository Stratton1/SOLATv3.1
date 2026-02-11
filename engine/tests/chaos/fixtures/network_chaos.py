"""
Network failure simulators for chaos testing.

Provides fixtures for simulating network-related failures:
- Connection refused
- Timeouts after delay
- Rate limiting (429)
- Intermittent 500 errors
"""

import random
from typing import Any

import httpx
import respx
from respx import MockRouter


class NetworkChaos:
    """Network failure simulation helpers using respx."""

    @staticmethod
    def connection_refused(router: MockRouter, url_pattern: str) -> None:
        """
        Simulate connection refused for URL pattern.

        Args:
            router: respx MockRouter instance
            url_pattern: URL pattern to match (e.g., "https://api.example.com/*")

        Usage:
            @respx.mock
            def test_connection_refused(respx_mock):
                NetworkChaos.connection_refused(respx_mock, "https://api.ig.com/*")
                # HTTP calls will raise ConnectError
        """
        router.route(url=url_pattern).mock(side_effect=httpx.ConnectError("Connection refused"))

    @staticmethod
    def timeout_after_delay(router: MockRouter, url_pattern: str, delay: float = 5.0) -> None:
        """
        Simulate timeout after delay.

        Args:
            router: respx MockRouter instance
            url_pattern: URL pattern to match
            delay: Seconds before timeout (simulated, not real wait)

        Usage:
            @respx.mock
            def test_timeout(respx_mock):
                NetworkChaos.timeout_after_delay(respx_mock, "https://api.ig.com/*")
                # HTTP calls will raise ReadTimeout
        """
        router.route(url=url_pattern).mock(side_effect=httpx.ReadTimeout("Request timed out"))

    @staticmethod
    def rate_limit_429(
        router: MockRouter, url_pattern: str, retry_after: int = 5, body: str | None = None
    ) -> None:
        """
        Simulate rate limiting with 429 response.

        Args:
            router: respx MockRouter instance
            url_pattern: URL pattern to match
            retry_after: Seconds to wait (in Retry-After header)
            body: Optional response body JSON

        Usage:
            @respx.mock
            def test_rate_limit(respx_mock):
                NetworkChaos.rate_limit_429(respx_mock, "https://api.ig.com/*")
                # HTTP calls will receive 429 with Retry-After header
        """
        if body is None:
            body = '{"error": "Rate limit exceeded"}'

        router.route(url=url_pattern).mock(
            return_value=httpx.Response(
                status_code=429, headers={"Retry-After": str(retry_after)}, content=body
            )
        )

    @staticmethod
    def intermittent_500(
        router: MockRouter, url_pattern: str, fail_rate: float = 0.3
    ) -> None:
        """
        Simulate intermittent 500 errors.

        Args:
            router: respx MockRouter instance
            url_pattern: URL pattern to match
            fail_rate: Probability of 500 error (0.0-1.0)

        Usage:
            @respx.mock
            def test_intermittent_error(respx_mock):
                NetworkChaos.intermittent_500(respx_mock, "https://api.ig.com/*", 0.5)
                # 50% of HTTP calls will receive 500 error
        """

        def _maybe_error(request: httpx.Request) -> httpx.Response:
            if random.random() < fail_rate:
                return httpx.Response(
                    status_code=500, content='{"error": "Internal server error"}'
                )
            return httpx.Response(status_code=200, content='{"status": "success"}')

        router.route(url=url_pattern).mock(side_effect=_maybe_error)

    @staticmethod
    def stale_data_response(
        router: MockRouter, url_pattern: str, stale_data: dict[str, Any]
    ) -> None:
        """
        Return stale/outdated data for requests.

        Args:
            router: respx MockRouter instance
            url_pattern: URL pattern to match
            stale_data: Outdated data to return

        Usage:
            @respx.mock
            def test_stale_positions(respx_mock):
                NetworkChaos.stale_data_response(
                    respx_mock,
                    "https://api.ig.com/positions",
                    {"positions": []}  # Empty, but broker actually has positions
                )
        """
        import json

        router.route(url=url_pattern).mock(
            return_value=httpx.Response(status_code=200, content=json.dumps(stale_data))
        )

    @staticmethod
    def partial_response_disconnect(router: MockRouter, url_pattern: str) -> None:
        """
        Simulate connection dropping mid-response.

        Args:
            router: respx MockRouter instance
            url_pattern: URL pattern to match

        Usage:
            @respx.mock
            def test_partial_response(respx_mock):
                NetworkChaos.partial_response_disconnect(respx_mock, "https://api.ig.com/*")
                # Response will be incomplete, simulating connection drop
        """
        router.route(url=url_pattern).mock(
            side_effect=httpx.RemoteProtocolError("Connection closed during response")
        )

    @staticmethod
    def dns_resolution_failure(router: MockRouter, url_pattern: str) -> None:
        """
        Simulate DNS resolution failure.

        Args:
            router: respx MockRouter instance
            url_pattern: URL pattern to match

        Usage:
            @respx.mock
            def test_dns_failure(respx_mock):
                NetworkChaos.dns_resolution_failure(respx_mock, "https://api.ig.com/*")
                # HTTP calls will raise ConnectError (name resolution failed)
        """
        router.route(url=url_pattern).mock(
            side_effect=httpx.ConnectError("Name or service not known")
        )
