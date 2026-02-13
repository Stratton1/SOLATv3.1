"""
BrokerAdapter interface.

Defines the contract for broker connectivity implementations.
"""

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from decimal import Decimal
from typing import Any

from solat_engine.domain import (
    Fill,
    Instrument,
    Order,
    OrderSide,
    Position,
)


class BrokerAdapter(ABC):
    """
    Abstract base class for broker connectivity.

    Implementations handle authentication, order management,
    position tracking, and market data streaming.
    """

    # =========================================================================
    # Connection Management
    # =========================================================================

    @abstractmethod
    async def connect(self) -> bool:
        """
        Establish connection to the broker.

        Returns:
            True if connection successful, False otherwise.
        """
        pass

    @abstractmethod
    async def disconnect(self) -> None:
        """Close connection to the broker."""
        pass

    @abstractmethod
    async def is_connected(self) -> bool:
        """Check if currently connected to the broker."""
        pass

    # =========================================================================
    # Account Information
    # =========================================================================

    @abstractmethod
    async def get_account_info(self) -> dict[str, Any]:
        """
        Get account information.

        Returns:
            Dict with account details (balance, margin, etc.)
        """
        pass

    @abstractmethod
    async def get_balance(self) -> Decimal:
        """Get current account balance."""
        pass

    @abstractmethod
    async def get_available_margin(self) -> Decimal:
        """Get available margin for new positions."""
        pass

    # =========================================================================
    # Instrument Information
    # =========================================================================

    @abstractmethod
    async def get_instrument(self, symbol: str) -> Instrument | None:
        """
        Get instrument details by symbol.

        Args:
            symbol: Canonical symbol (e.g., "EURUSD")

        Returns:
            Instrument if found, None otherwise.
        """
        pass

    @abstractmethod
    async def search_instruments(self, query: str) -> list[Instrument]:
        """
        Search for instruments by name or symbol.

        Args:
            query: Search query

        Returns:
            List of matching instruments.
        """
        pass

    # =========================================================================
    # Order Management
    # =========================================================================

    @abstractmethod
    async def submit_order(self, order: Order) -> Order:
        """
        Submit an order to the broker.

        Args:
            order: Order to submit

        Returns:
            Updated order with broker ID and status.
        """
        pass

    @abstractmethod
    async def cancel_order(self, order_id: str) -> bool:
        """
        Cancel an open order.

        Args:
            order_id: Broker order ID

        Returns:
            True if cancelled, False if failed.
        """
        pass

    @abstractmethod
    async def modify_order(
        self,
        order_id: str,
        *,
        limit_price: Decimal | None = None,
        stop_loss: Decimal | None = None,
        take_profit: Decimal | None = None,
    ) -> Order:
        """
        Modify an existing order.

        Args:
            order_id: Broker order ID
            limit_price: New limit price (optional)
            stop_loss: New stop loss (optional)
            take_profit: New take profit (optional)

        Returns:
            Updated order.
        """
        pass

    @abstractmethod
    async def get_order(self, order_id: str) -> Order | None:
        """
        Get order by broker ID.

        Args:
            order_id: Broker order ID

        Returns:
            Order if found, None otherwise.
        """
        pass

    @abstractmethod
    async def get_open_orders(self, symbol: str | None = None) -> list[Order]:
        """
        Get all open orders.

        Args:
            symbol: Filter by symbol (optional)

        Returns:
            List of open orders.
        """
        pass

    # =========================================================================
    # Position Management
    # =========================================================================

    @abstractmethod
    async def get_positions(self, symbol: str | None = None) -> list[Position]:
        """
        Get all open positions.

        Args:
            symbol: Filter by symbol (optional)

        Returns:
            List of open positions.
        """
        pass

    @abstractmethod
    async def close_position(
        self,
        position_id: str,
        quantity: Decimal | None = None,
    ) -> Fill:
        """
        Close a position (fully or partially).

        Args:
            position_id: Broker position ID
            quantity: Quantity to close (None = full close)

        Returns:
            Fill from the close order.
        """
        pass

    @abstractmethod
    async def modify_position(
        self,
        position_id: str,
        *,
        stop_loss: Decimal | None = None,
        take_profit: Decimal | None = None,
    ) -> Position:
        """
        Modify stop loss/take profit on a position.

        Args:
            position_id: Broker position ID
            stop_loss: New stop loss (optional)
            take_profit: New take profit (optional)

        Returns:
            Updated position.
        """
        pass

    # =========================================================================
    # Market Data
    # =========================================================================

    @abstractmethod
    async def get_quote(self, symbol: str) -> dict[str, Any]:
        """
        Get current quote for a symbol.

        Args:
            symbol: Instrument symbol

        Returns:
            Dict with bid, ask, spread, etc.
        """
        pass

    @abstractmethod
    async def subscribe_quotes(
        self, symbols: list[str]
    ) -> AsyncIterator[dict[str, Any]]:
        """
        Subscribe to real-time quotes.

        Args:
            symbols: List of symbols to subscribe to

        Yields:
            Quote updates as they arrive.
        """
        pass

    # =========================================================================
    # Utility Methods
    # =========================================================================

    @abstractmethod
    async def create_market_order(
        self,
        symbol: str,
        side: OrderSide,
        quantity: Decimal,
        *,
        stop_loss: Decimal | None = None,
        take_profit: Decimal | None = None,
    ) -> Order:
        """
        Convenience method to create and submit a market order.

        Args:
            symbol: Instrument symbol
            side: BUY or SELL
            quantity: Order size
            stop_loss: Stop loss price (optional)
            take_profit: Take profit price (optional)

        Returns:
            Submitted order.
        """
        pass

    @abstractmethod
    async def create_limit_order(
        self,
        symbol: str,
        side: OrderSide,
        quantity: Decimal,
        limit_price: Decimal,
        *,
        stop_loss: Decimal | None = None,
        take_profit: Decimal | None = None,
    ) -> Order:
        """
        Convenience method to create and submit a limit order.

        Args:
            symbol: Instrument symbol
            side: BUY or SELL
            quantity: Order size
            limit_price: Limit price
            stop_loss: Stop loss price (optional)
            take_profit: Take profit price (optional)

        Returns:
            Submitted order.
        """
        pass
