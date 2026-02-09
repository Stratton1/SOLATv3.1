"""
Tests for throttling and event compression.

Tests:
- Quote throttling at 10/sec per symbol
- ExecutionEventCompressor deduplication
- WSEventThrottler batching
"""

import asyncio
from datetime import UTC, datetime

import pytest

from solat_engine.market_data.models import Quote
from solat_engine.market_data.publisher import MarketDataPublisher, reset_publisher
from solat_engine.runtime.event_bus import Event, EventType, reset_event_bus
from solat_engine.runtime.ws_throttle import (
    ExecutionEventCompressor,
    WSEventThrottler,
    reset_ws_throttler,
)


@pytest.fixture(autouse=True)
def reset_globals() -> None:
    """Reset global instances before each test."""
    reset_publisher()
    reset_event_bus()
    reset_ws_throttler()


class TestQuoteThrottling:
    """Tests for MarketDataPublisher quote throttling."""

    @pytest.mark.asyncio
    async def test_first_quote_published(self) -> None:
        """Test that first quote is always published."""
        publisher = MarketDataPublisher(max_quotes_per_sec=10)

        quote = Quote.from_bid_ask(
            symbol="EURUSD",
            epic="CS.D.EURUSD.MINI.IP",
            bid=1.1000,
            ask=1.1002,
            ts_utc=datetime.now(UTC),
        )

        published = await publisher.publish_quote(quote)

        assert published is True
        stats = publisher.get_stats()
        assert stats["quotes_published"] == 1
        assert stats["quotes_throttled"] == 0

    @pytest.mark.asyncio
    async def test_rapid_quotes_throttled(self) -> None:
        """Test that rapid quotes are throttled."""
        publisher = MarketDataPublisher(max_quotes_per_sec=10)

        # Send 20 quotes rapidly (without sleep)
        for i in range(20):
            quote = Quote.from_bid_ask(
                symbol="EURUSD",
                epic="CS.D.EURUSD.MINI.IP",
                bid=1.1000 + i * 0.0001,
                ask=1.1002 + i * 0.0001,
                ts_utc=datetime.now(UTC),
            )
            await publisher.publish_quote(quote)

        stats = publisher.get_stats()
        # First quote published, rest throttled
        assert stats["quotes_published"] == 1
        assert stats["quotes_throttled"] == 19

    @pytest.mark.asyncio
    async def test_quotes_at_allowed_rate(self) -> None:
        """Test quotes at allowed rate are all published."""
        publisher = MarketDataPublisher(max_quotes_per_sec=10)

        # Send 3 quotes at 100ms intervals (10/sec allows 1 per 100ms)
        for i in range(3):
            quote = Quote.from_bid_ask(
                symbol="EURUSD",
                epic="CS.D.EURUSD.MINI.IP",
                bid=1.1000 + i * 0.0001,
                ask=1.1002 + i * 0.0001,
                ts_utc=datetime.now(UTC),
            )
            await publisher.publish_quote(quote)
            await asyncio.sleep(0.11)  # Slightly over 100ms

        stats = publisher.get_stats()
        assert stats["quotes_published"] == 3
        assert stats["quotes_throttled"] == 0

    @pytest.mark.asyncio
    async def test_different_symbols_independent(self) -> None:
        """Test that different symbols are throttled independently."""
        publisher = MarketDataPublisher(max_quotes_per_sec=10)

        # Send quotes for two different symbols
        for symbol in ["EURUSD", "GBPUSD"]:
            for i in range(5):
                quote = Quote.from_bid_ask(
                    symbol=symbol,
                    epic=f"CS.D.{symbol}.MINI.IP",
                    bid=1.1000 + i * 0.0001,
                    ask=1.1002 + i * 0.0001,
                    ts_utc=datetime.now(UTC),
                )
                await publisher.publish_quote(quote)

        stats = publisher.get_stats()
        # First quote for each symbol published, rest throttled
        assert stats["quotes_published"] == 2  # 1 per symbol
        assert stats["quotes_throttled"] == 8  # 4 per symbol

    @pytest.mark.asyncio
    async def test_stats_reset(self) -> None:
        """Test stats can be reset."""
        publisher = MarketDataPublisher(max_quotes_per_sec=10)

        quote = Quote.from_bid_ask(
            symbol="EURUSD",
            epic="CS.D.EURUSD.MINI.IP",
            bid=1.1000,
            ask=1.1002,
            ts_utc=datetime.now(UTC),
        )

        await publisher.publish_quote(quote)
        await publisher.publish_quote(quote)

        stats = publisher.get_stats()
        assert stats["quotes_published"] == 1
        assert stats["quotes_throttled"] == 1

        publisher.reset_stats()

        stats = publisher.get_stats()
        assert stats["quotes_published"] == 0
        assert stats["quotes_throttled"] == 0


class TestExecutionEventCompressor:
    """Tests for ExecutionEventCompressor."""

    def test_critical_events_always_delivered(self) -> None:
        """Test that critical events are never compressed."""
        compressor = ExecutionEventCompressor(dedup_window_s=2.0)

        critical_events = [
            EventType.EXECUTION_INTENT_CREATED,
            EventType.EXECUTION_ORDER_SUBMITTED,
            EventType.EXECUTION_ORDER_REJECTED,
            EventType.EXECUTION_ORDER_ACKNOWLEDGED,
            EventType.EXECUTION_KILL_SWITCH_ACTIVATED,
        ]

        for event_type in critical_events:
            event = Event(type=event_type, data={"test": "data"})

            # First and second should both be delivered
            assert compressor.should_deliver(event) is True
            assert compressor.should_deliver(event) is True

    def test_status_event_dedup(self) -> None:
        """Test that duplicate status events are compressed."""
        compressor = ExecutionEventCompressor(dedup_window_s=2.0)

        status_data = {
            "running": True,
            "paused": False,
            "kill_switch_active": False,
            "open_position_count": 1,
            "pending_intent_count": 0,
        }

        event = Event(type=EventType.EXECUTION_STATUS, data=status_data)

        # First should be delivered
        assert compressor.should_deliver(event) is True

        # Duplicate within window should be compressed
        assert compressor.should_deliver(event) is False

        stats = compressor.stats
        assert stats.events_delivered == 1
        assert stats.events_compressed == 1

    def test_status_event_with_change_delivered(self) -> None:
        """Test that status events with changes are delivered."""
        compressor = ExecutionEventCompressor(dedup_window_s=2.0)

        event1 = Event(
            type=EventType.EXECUTION_STATUS,
            data={
                "running": True,
                "paused": False,
                "open_position_count": 0,
            },
        )

        event2 = Event(
            type=EventType.EXECUTION_STATUS,
            data={
                "running": True,
                "paused": False,
                "open_position_count": 1,  # Changed!
            },
        )

        # Both should be delivered (different content)
        assert compressor.should_deliver(event1) is True
        assert compressor.should_deliver(event2) is True

    def test_positions_unchanged_compressed(self) -> None:
        """Test that unchanged position updates are compressed."""
        compressor = ExecutionEventCompressor(dedup_window_s=2.0)

        positions = {
            "EURUSD": {
                "size": 1.0,
                "side": "long",
                "entry_price": 1.1000,
            }
        }

        event = Event(
            type=EventType.EXECUTION_POSITIONS_UPDATED,
            data={"positions": positions},
        )

        # First delivered
        assert compressor.should_deliver(event) is True

        # Same positions - compressed
        assert compressor.should_deliver(event) is False

    def test_positions_changed_delivered(self) -> None:
        """Test that changed positions are delivered."""
        compressor = ExecutionEventCompressor(dedup_window_s=2.0)

        event1 = Event(
            type=EventType.EXECUTION_POSITIONS_UPDATED,
            data={
                "positions": {
                    "EURUSD": {"size": 1.0, "side": "long", "entry_price": 1.1000}
                }
            },
        )

        event2 = Event(
            type=EventType.EXECUTION_POSITIONS_UPDATED,
            data={
                "positions": {
                    "EURUSD": {"size": 2.0, "side": "long", "entry_price": 1.1000}  # Size changed
                }
            },
        )

        assert compressor.should_deliver(event1) is True
        assert compressor.should_deliver(event2) is True

    def test_compressor_reset(self) -> None:
        """Test compressor state can be reset."""
        compressor = ExecutionEventCompressor(dedup_window_s=2.0)

        event = Event(
            type=EventType.EXECUTION_STATUS,
            data={"running": True},
        )

        compressor.should_deliver(event)
        compressor.should_deliver(event)  # Compressed

        compressor.reset()

        # After reset, should deliver again
        assert compressor.should_deliver(event) is True

    def test_stats_reset(self) -> None:
        """Test stats can be reset."""
        compressor = ExecutionEventCompressor(dedup_window_s=2.0)

        event = Event(type=EventType.EXECUTION_STATUS, data={"running": True})

        compressor.should_deliver(event)
        compressor.should_deliver(event)

        stats = compressor.stats
        assert stats.events_received == 2

        compressor.reset_stats()

        stats = compressor.stats
        assert stats.events_received == 0


class TestWSEventThrottler:
    """Tests for WSEventThrottler."""

    @pytest.mark.asyncio
    async def test_non_execution_events_pass_through(self) -> None:
        """Test that non-execution events pass through."""
        throttler = WSEventThrottler()

        delivered: list[Event] = []

        async def capture(event: Event) -> None:
            delivered.append(event)

        throttler.set_delivery_callback(capture)
        await throttler.start()

        event = Event(type=EventType.QUOTE_RECEIVED, data={"symbol": "EURUSD"})
        accepted = await throttler.process_event(event)

        assert accepted is True
        assert len(delivered) == 1

        await throttler.stop()

    @pytest.mark.asyncio
    async def test_execution_events_compressed(self) -> None:
        """Test that execution status events are compressed."""
        throttler = WSEventThrottler(execution_dedup_window_s=2.0)

        delivered: list[Event] = []

        async def capture(event: Event) -> None:
            delivered.append(event)

        throttler.set_delivery_callback(capture)
        await throttler.start()

        event = Event(
            type=EventType.EXECUTION_STATUS,
            data={"running": True, "paused": False},
        )

        # First delivered
        await throttler.process_event(event)
        assert len(delivered) == 1

        # Second compressed (same status)
        await throttler.process_event(event)
        assert len(delivered) == 1

        await throttler.stop()

    @pytest.mark.asyncio
    async def test_batching_mode(self) -> None:
        """Test batching mode accumulates events."""
        throttler = WSEventThrottler(
            enable_batching=True,
            batch_flush_interval_ms=50,
        )

        delivered: list[Event] = []

        async def capture(event: Event) -> None:
            delivered.append(event)

        throttler.set_delivery_callback(capture)
        await throttler.start()

        # Send multiple events quickly
        for i in range(3):
            event = Event(
                type=EventType.QUOTE_RECEIVED,
                data={"symbol": f"SYM{i}"},
            )
            await throttler.process_event(event)

        # Wait for batch flush
        await asyncio.sleep(0.1)

        # Should have one batch event containing all 3
        assert len(delivered) >= 1
        batch_data = delivered[0].data
        assert "batch" in batch_data
        assert batch_data["count"] == 3

        await throttler.stop()

    @pytest.mark.asyncio
    async def test_stats_tracking(self) -> None:
        """Test stats are tracked correctly."""
        throttler = WSEventThrottler(execution_dedup_window_s=2.0)

        async def noop(event: Event) -> None:
            pass

        throttler.set_delivery_callback(noop)
        await throttler.start()

        # Send critical event (always delivered)
        critical = Event(type=EventType.EXECUTION_ORDER_SUBMITTED, data={})
        await throttler.process_event(critical)

        # Send compressible events
        status = Event(type=EventType.EXECUTION_STATUS, data={"running": True})
        await throttler.process_event(status)
        await throttler.process_event(status)  # Compressed

        stats = throttler.get_stats()
        assert stats["total_received"] == 3
        assert stats["execution_events"]["compressed"] == 1

        await throttler.stop()

    @pytest.mark.asyncio
    async def test_stats_reset(self) -> None:
        """Test stats can be reset."""
        throttler = WSEventThrottler()

        event = Event(type=EventType.QUOTE_RECEIVED, data={})
        await throttler.process_event(event)

        stats = throttler.get_stats()
        assert stats["total_received"] == 1

        throttler.reset_stats()

        stats = throttler.get_stats()
        assert stats["total_received"] == 0

