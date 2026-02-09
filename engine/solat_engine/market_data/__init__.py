"""
Market data subsystem for realtime price streaming and bar building.

Provides:
- Quote streaming via Lightstreamer (or polling fallback)
- Bar builder for 1m + derived timeframes
- WS event broadcasting for UI
"""

from solat_engine.market_data.backfill import (
    BackfillService,
    create_backfill_callback,
)
from solat_engine.market_data.bar_builder import BarBuilder, MultiSymbolBarBuilder
from solat_engine.market_data.controller import (
    ControllerConfig,
    ControllerState,
    ControllerStats,
    MarketDataController,
)
from solat_engine.market_data.models import (
    BarBuffer,
    BarUpdate,
    MarketDataMode,
    MarketStreamStatus,
    Quote,
    QuoteCache,
    SubscriptionRequest,
)
from solat_engine.market_data.polling import MockPollingSource, PollingMarketSource
from solat_engine.market_data.publisher import (
    MarketDataPublisher,
    get_publisher,
    reset_publisher,
)
from solat_engine.market_data.streaming import (
    LightstreamerClient,
    StreamingMarketSource,
)

__all__ = [
    # Models
    "Quote",
    "MarketStreamStatus",
    "SubscriptionRequest",
    "BarUpdate",
    "MarketDataMode",
    "QuoteCache",
    "BarBuffer",
    # Bar Builder
    "BarBuilder",
    "MultiSymbolBarBuilder",
    # Sources
    "PollingMarketSource",
    "MockPollingSource",
    "StreamingMarketSource",
    "LightstreamerClient",
    # Publisher
    "MarketDataPublisher",
    "get_publisher",
    "reset_publisher",
    # Controller
    "MarketDataController",
    "ControllerConfig",
    "ControllerState",
    "ControllerStats",
    # Backfill
    "BackfillService",
    "create_backfill_callback",
]
