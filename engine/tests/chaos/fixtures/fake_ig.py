"""
Deterministic Fake IG Client for integration testing.

Satisfies the broker adapter interface used by ExecutionRouter.connect()
and _submit_to_broker() without making any real HTTP calls.
"""

from datetime import UTC, datetime
from uuid import uuid4


class FakeIGClient:
    """
    Fake IG broker client for integration tests.

    Configurable balance, order responses, and failure injection.
    """

    def __init__(
        self,
        balance: float = 10000.0,
        account_id: str = "FAKE_DEMO_001",
        currency: str = "USD",
    ):
        self._balance = balance
        self._account_id = account_id
        self._currency = currency
        self._positions: list[dict] = []
        self._order_response: dict | None = None
        self._fail_next: Exception | None = None
        self._order_count = 0
        self._login_count = 0
        self._list_accounts_count = 0
        # Satisfy attribute checks
        self.is_authenticated = True
        self.session_age_seconds = 0
        self.rate_limiter_stats = {}
        self.settings = None

    # -- Configuration --

    def set_balance(self, amount: float) -> None:
        """Set the balance returned by list_accounts."""
        self._balance = amount

    def set_order_response(self, response: dict) -> None:
        """Override the response from place_market_order."""
        self._order_response = response

    def fail_next_order(self, error: Exception) -> None:
        """Make the next place_market_order call raise this error."""
        self._fail_next = error

    def set_positions(self, positions: list[dict]) -> None:
        """Set positions returned by list_positions."""
        self._positions = positions

    # -- Broker adapter interface --

    async def login(self) -> dict:
        self._login_count += 1
        return {"ok": True}

    async def list_accounts(self) -> list[dict]:
        self._list_accounts_count += 1
        return [
            {
                "accountId": self._account_id,
                "accountType": "CFD",
                "balance": {
                    "balance": self._balance,
                    "available": self._balance,
                },
                "currency": self._currency,
            }
        ]

    async def place_market_order(
        self,
        epic: str,
        direction: str,
        size: float,
        stop_level: float | None = None,
        limit_level: float | None = None,
        deal_reference: str | None = None,
        **kwargs,
    ) -> dict:
        if self._fail_next is not None:
            err = self._fail_next
            self._fail_next = None
            raise err

        self._order_count += 1

        if self._order_response is not None:
            return self._order_response

        deal_id = f"FAKE_DEAL_{self._order_count:04d}"
        return {
            "dealId": deal_id,
            "dealReference": deal_reference or f"REF_{deal_id}",
            "dealStatus": "ACCEPTED",
            "reason": "SUCCESS",
            "status": "OPEN",
            "affectedDeals": [{"dealId": deal_id, "status": "OPENED"}],
        }

    async def list_positions(self) -> list[dict]:
        return self._positions

    async def close_position(
        self,
        deal_id: str,
        direction: str = "SELL",
        size: float = 1.0,
        **kwargs,
    ) -> dict:
        self._positions = [
            p for p in self._positions if p.get("dealId") != deal_id
        ]
        return {
            "dealId": deal_id,
            "dealStatus": "ACCEPTED",
            "reason": "SUCCESS",
        }

    async def verify_account_for_live(self, account_id: str | None = None) -> dict:
        return {"verified": False, "is_live": False}

    async def close(self) -> None:
        pass

    # Convenience for tests
    async def search_markets(self, *args, **kwargs) -> list:
        return []

    async def get_market_details(self, *args, **kwargs) -> dict:
        return {}

    async def get_accounts(self, *args, **kwargs) -> list:
        return await self.list_accounts()
