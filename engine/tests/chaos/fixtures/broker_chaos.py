"""
Broker failure simulators for chaos testing.

Provides fixtures for simulating broker-side failures:
- Intermittent timeouts
- Partial order fills
- Duplicate confirmations
- Stale position data
"""

import random
from typing import Any
from unittest.mock import AsyncMock

from solat_engine.domain.models import Fill, Order, Position


class BrokerChaos:
    """Broker failure simulation helpers."""

    @staticmethod
    def intermittent_timeout(mock_broker: AsyncMock, fail_rate: float = 0.3) -> None:
        """
        Configure broker mock to raise TimeoutError intermittently.

        Args:
            mock_broker: AsyncMock broker instance
            fail_rate: Probability of timeout (0.0-1.0)
        """

        async def _maybe_timeout(*args: Any, **kwargs: Any) -> Any:
            if random.random() < fail_rate:
                raise TimeoutError("Broker timeout simulation")
            return {"status": "success"}

        mock_broker.submit_order.side_effect = _maybe_timeout

    @staticmethod
    def partial_fill(
        mock_broker: AsyncMock, original_size: float, filled_size: float
    ) -> dict[str, Any]:
        """
        Simulate partial order fill.

        Args:
            mock_broker: AsyncMock broker instance
            original_size: Requested order size
            filled_size: Actually filled size (< original_size)

        Returns:
            Partial fill confirmation dict
        """
        confirmation = {
            "deal_id": f"DEAL_{random.randint(1000, 9999)}",
            "status": "PARTIAL",
            "size": filled_size,
            "requested_size": original_size,
            "reason": "PARTIAL_FILL",
        }

        async def _partial_fill(*args: Any, **kwargs: Any) -> dict[str, Any]:
            return confirmation

        mock_broker.submit_order.side_effect = _partial_fill
        return confirmation

    @staticmethod
    def duplicate_confirmation(
        mock_broker: AsyncMock, deal_id: str, call_count: int = 2
    ) -> None:
        """
        Simulate duplicate fill confirmations with same deal_id.

        Args:
            mock_broker: AsyncMock broker instance
            deal_id: Deal ID to duplicate
            call_count: Number of times to return same confirmation
        """
        confirmation = {
            "deal_id": deal_id,
            "status": "CONFIRMED",
            "size": 1.0,
        }

        responses = [confirmation] * call_count

        async def _duplicate(*args: Any, **kwargs: Any) -> dict[str, Any]:
            if responses:
                return responses.pop(0)
            return {"status": "ERROR"}

        mock_broker.submit_order.side_effect = _duplicate

    @staticmethod
    def stale_position_list(
        mock_broker: AsyncMock, stale_positions: list[dict[str, Any]]
    ) -> None:
        """
        Configure broker to return outdated position data.

        Args:
            mock_broker: AsyncMock broker instance
            stale_positions: List of position dicts (may not match reality)
        """

        async def _stale_positions(*args: Any, **kwargs: Any) -> list[dict[str, Any]]:
            return stale_positions

        mock_broker.list_positions.side_effect = _stale_positions

    @staticmethod
    def rate_limit_429(mock_broker: AsyncMock, retry_after: int = 5) -> None:
        """
        Simulate rate limiting with 429 response.

        Args:
            mock_broker: AsyncMock broker instance
            retry_after: Seconds to wait before retry
        """

        class RateLimitError(Exception):
            """Rate limit exceeded."""

            def __init__(self, retry_after: int):
                self.retry_after = retry_after
                super().__init__(f"Rate limit exceeded, retry after {retry_after}s")

        async def _rate_limit(*args: Any, **kwargs: Any) -> Any:
            raise RateLimitError(retry_after)

        mock_broker.submit_order.side_effect = _rate_limit
        mock_broker.list_positions.side_effect = _rate_limit
