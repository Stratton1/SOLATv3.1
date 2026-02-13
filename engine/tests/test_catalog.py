"""
Tests for instrument catalogue.
"""

import tempfile
from decimal import Decimal
from pathlib import Path

import pytest

from solat_engine.catalog.models import (
    AssetClass,
    CatalogueSeedItem,
    DealingRulesSummary,
    InstrumentCatalogueItem,
)
from solat_engine.catalog.seed import get_seed_instruments
from solat_engine.catalog.store import CatalogueStore


class TestCatalogueModels:
    """Tests for catalogue models."""

    def test_asset_class_enum(self) -> None:
        """AssetClass enum should have expected values."""
        assert AssetClass.FX.value == "fx"
        assert AssetClass.INDEX.value == "index"
        assert AssetClass.COMMODITY.value == "commodity"
        assert AssetClass.CRYPTO.value == "crypto"
        assert AssetClass.STOCK.value == "stock"

    def test_instrument_catalogue_item_minimal(self) -> None:
        """InstrumentCatalogueItem should accept minimal fields."""
        item = InstrumentCatalogueItem(
            symbol="EURUSD",
            display_name="EUR/USD",
            asset_class=AssetClass.FX,
        )
        assert item.symbol == "EURUSD"
        assert item.epic is None
        assert item.is_enriched is False

    def test_instrument_catalogue_item_full(self) -> None:
        """InstrumentCatalogueItem should accept all fields."""
        item = InstrumentCatalogueItem(
            symbol="EURUSD",
            epic="CS.D.EURUSD.CFD.IP",
            display_name="EUR/USD",
            asset_class=AssetClass.FX,
            currency="USD",
            pip_size=Decimal("0.0001"),
            lot_size=Decimal("100000"),
            margin_factor=Decimal("3.33"),
            dealing_rules=DealingRulesSummary(
                minDealSize=Decimal("0.5"),
                maxDealSize=Decimal("200"),
            ),
            is_enriched=True,
        )
        assert item.epic == "CS.D.EURUSD.CFD.IP"
        assert item.is_enriched is True
        assert item.dealing_rules is not None
        assert item.dealing_rules.min_deal_size == Decimal("0.5")

    def test_dealing_rules_summary_alias(self) -> None:
        """DealingRulesSummary should accept aliased field names."""
        rules = DealingRulesSummary(
            minDealSize=Decimal("0.5"),
            maxDealSize=Decimal("200"),
            minStopDistance=Decimal("5"),
        )
        assert rules.min_deal_size == Decimal("0.5")
        assert rules.max_deal_size == Decimal("200")
        assert rules.min_stop_distance == Decimal("5")

    def test_catalogue_seed_item(self) -> None:
        """CatalogueSeedItem should validate correctly."""
        seed = CatalogueSeedItem(
            symbol="EURUSD",
            display_name="EUR/USD",
            asset_class=AssetClass.FX,
            search_hint="EUR/USD",
            pip_size=Decimal("0.0001"),
        )
        assert seed.symbol == "EURUSD"
        assert seed.currency == "USD"  # default


class TestCatalogueStore:
    """Tests for CatalogueStore."""

    @pytest.fixture
    def store(self) -> CatalogueStore:
        """Create a store with temp directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            store = CatalogueStore(data_dir=Path(tmpdir))
            yield store

    def test_store_initializes_empty(self, store: CatalogueStore) -> None:
        """Store should start empty."""
        assert store.load() == []
        assert store.count() == 0

    def test_store_file_path(self, store: CatalogueStore) -> None:
        """Store should have correct file path."""
        assert store.file_path.name == "instruments.json"

    def test_store_upsert_new(self, store: CatalogueStore) -> None:
        """Upsert should insert new item."""
        item = InstrumentCatalogueItem(
            symbol="EURUSD",
            display_name="EUR/USD",
            asset_class=AssetClass.FX,
        )
        was_update = store.upsert(item)

        assert was_update is False
        assert store.count() == 1
        loaded = store.get("EURUSD")
        assert loaded is not None
        assert loaded.symbol == "EURUSD"

    def test_store_upsert_existing(self, store: CatalogueStore) -> None:
        """Upsert should update existing item."""
        item1 = InstrumentCatalogueItem(
            symbol="EURUSD",
            display_name="EUR/USD",
            asset_class=AssetClass.FX,
            is_enriched=False,
        )
        store.upsert(item1)

        item2 = InstrumentCatalogueItem(
            symbol="EURUSD",
            display_name="EUR/USD Updated",
            asset_class=AssetClass.FX,
            is_enriched=True,
        )
        was_update = store.upsert(item2)

        assert was_update is True
        assert store.count() == 1
        loaded = store.get("EURUSD")
        assert loaded is not None
        assert loaded.display_name == "EUR/USD Updated"
        assert loaded.is_enriched is True

    def test_store_get_case_insensitive(self, store: CatalogueStore) -> None:
        """Get should be case-insensitive."""
        item = InstrumentCatalogueItem(
            symbol="EURUSD",
            display_name="EUR/USD",
            asset_class=AssetClass.FX,
        )
        store.upsert(item)

        assert store.get("EURUSD") is not None
        assert store.get("eurusd") is not None
        assert store.get("EurUsd") is not None

    def test_store_get_not_found(self, store: CatalogueStore) -> None:
        """Get should return None for missing item."""
        assert store.get("NONEXISTENT") is None

    def test_store_delete(self, store: CatalogueStore) -> None:
        """Delete should remove item."""
        item = InstrumentCatalogueItem(
            symbol="EURUSD",
            display_name="EUR/USD",
            asset_class=AssetClass.FX,
        )
        store.upsert(item)
        assert store.count() == 1

        deleted = store.delete("EURUSD")
        assert deleted is True
        assert store.count() == 0
        assert store.get("EURUSD") is None

    def test_store_delete_not_found(self, store: CatalogueStore) -> None:
        """Delete should return False for missing item."""
        deleted = store.delete("NONEXISTENT")
        assert deleted is False

    def test_store_bootstrap(self, store: CatalogueStore) -> None:
        """Bootstrap should create items from seed."""
        seeds = [
            CatalogueSeedItem(
                symbol="EURUSD",
                display_name="EUR/USD",
                asset_class=AssetClass.FX,
                search_hint="EUR/USD",
            ),
            CatalogueSeedItem(
                symbol="GBPUSD",
                display_name="GBP/USD",
                asset_class=AssetClass.FX,
                search_hint="GBP/USD",
            ),
        ]
        result = store.bootstrap(seeds)

        assert result["created"] == 2
        assert result["skipped"] == 0
        assert result["total"] == 2
        assert store.count() == 2

    def test_store_bootstrap_idempotent(self, store: CatalogueStore) -> None:
        """Bootstrap should be idempotent."""
        seeds = [
            CatalogueSeedItem(
                symbol="EURUSD",
                display_name="EUR/USD",
                asset_class=AssetClass.FX,
                search_hint="EUR/USD",
            ),
        ]

        result1 = store.bootstrap(seeds)
        assert result1["created"] == 1

        result2 = store.bootstrap(seeds)
        assert result2["created"] == 0
        assert result2["skipped"] == 1
        assert result2["total"] == 1

    def test_store_bootstrap_is_live(self, store: CatalogueStore) -> None:
        """Bootstrap should use live epics when is_live=True."""
        seeds = [
            CatalogueSeedItem(
                symbol="EURUSD",
                display_name="EUR/USD",
                asset_class=AssetClass.FX,
                search_hint="EUR/USD",
                demo_epic="DEMO_EPIC",
                live_epic="LIVE_EPIC",
            ),
        ]
        
        # Test LIVE bootstrap
        store.clear()
        store.bootstrap(seeds, is_live=True)
        item = store.get("EURUSD")
        assert item.epic == "LIVE_EPIC"
        
        # Test DEMO bootstrap
        store.clear()
        store.bootstrap(seeds, is_live=False)
        item = store.get("EURUSD")
        assert item.epic == "DEMO_EPIC"

    def test_store_get_by_asset_class(self, store: CatalogueStore) -> None:
        """Get by asset class should filter correctly."""
        items = [
            InstrumentCatalogueItem(
                symbol="EURUSD",
                display_name="EUR/USD",
                asset_class=AssetClass.FX,
            ),
            InstrumentCatalogueItem(
                symbol="SPX500",
                display_name="S&P 500",
                asset_class=AssetClass.INDEX,
            ),
            InstrumentCatalogueItem(
                symbol="GBPUSD",
                display_name="GBP/USD",
                asset_class=AssetClass.FX,
            ),
        ]
        for item in items:
            store.upsert(item)

        fx_items = store.get_by_asset_class(AssetClass.FX)
        assert len(fx_items) == 2

        index_items = store.get_by_asset_class(AssetClass.INDEX)
        assert len(index_items) == 1

    def test_store_get_unenriched(self, store: CatalogueStore) -> None:
        """Get unenriched should filter correctly."""
        items = [
            InstrumentCatalogueItem(
                symbol="EURUSD",
                display_name="EUR/USD",
                asset_class=AssetClass.FX,
                is_enriched=True,
            ),
            InstrumentCatalogueItem(
                symbol="GBPUSD",
                display_name="GBP/USD",
                asset_class=AssetClass.FX,
                is_enriched=False,
            ),
        ]
        for item in items:
            store.upsert(item)

        unenriched = store.get_unenriched()
        assert len(unenriched) == 1
        assert unenriched[0].symbol == "GBPUSD"

    def test_store_clear(self, store: CatalogueStore) -> None:
        """Clear should remove all items."""
        item = InstrumentCatalogueItem(
            symbol="EURUSD",
            display_name="EUR/USD",
            asset_class=AssetClass.FX,
        )
        store.upsert(item)
        assert store.count() == 1

        store.clear()
        assert store.count() == 0


class TestSeedData:
    """Tests for seed data."""

    def test_seed_instruments_returns_list(self) -> None:
        """get_seed_instruments should return a list."""
        seeds = get_seed_instruments()
        assert isinstance(seeds, list)
        assert len(seeds) > 0

    def test_seed_instruments_have_required_fields(self) -> None:
        """All seed instruments should have required fields."""
        seeds = get_seed_instruments()
        for seed in seeds:
            assert seed.symbol
            assert seed.display_name
            assert seed.asset_class
            assert seed.search_hint

    def test_seed_instruments_have_expected_count(self) -> None:
        """Should have expected number of seed instruments (28)."""
        seeds = get_seed_instruments()
        assert len(seeds) == 28

    def test_seed_instruments_cover_asset_classes(self) -> None:
        """Seed instruments should cover all asset classes."""
        seeds = get_seed_instruments()
        asset_classes = {seed.asset_class for seed in seeds}

        assert AssetClass.FX in asset_classes
        assert AssetClass.INDEX in asset_classes
        assert AssetClass.COMMODITY in asset_classes
        assert AssetClass.CRYPTO in asset_classes
