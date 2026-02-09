"""
File-backed storage for instrument catalogue.
"""

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from solat_engine.catalog.models import (
    AssetClass,
    CatalogueSeedItem,
    InstrumentCatalogueItem,
)
from solat_engine.logging import get_logger

logger = get_logger(__name__)


class CatalogueStore:
    """
    JSON file-backed catalogue storage.

    Provides CRUD operations for the instrument catalogue.
    """

    def __init__(self, data_dir: Path | None = None) -> None:
        """
        Initialize catalogue store.

        Args:
            data_dir: Directory for catalogue file. Defaults to module's data/ folder.
        """
        if data_dir is None:
            # Default to engine/solat_engine/catalog/data/
            data_dir = Path(__file__).parent / "data"

        self._data_dir = data_dir
        self._data_dir.mkdir(parents=True, exist_ok=True)
        self._file_path = self._data_dir / "instruments.json"

        logger.debug("CatalogueStore initialized at %s", self._file_path)

    @property
    def file_path(self) -> Path:
        """Get the catalogue file path."""
        return self._file_path

    def load(self) -> list[InstrumentCatalogueItem]:
        """
        Load catalogue from file.

        Returns:
            List of catalogue items, or empty list if file doesn't exist.
        """
        if not self._file_path.exists():
            logger.debug("Catalogue file not found, returning empty list")
            return []

        try:
            with open(self._file_path, encoding="utf-8") as f:
                data = json.load(f)

            items = [InstrumentCatalogueItem.model_validate(item) for item in data]
            logger.debug("Loaded %d instruments from catalogue", len(items))
            return items

        except Exception as e:
            logger.error("Failed to load catalogue: %s", e)
            return []

    def save(self, items: list[InstrumentCatalogueItem]) -> None:
        """
        Save catalogue to file.

        Args:
            items: List of catalogue items to save.
        """
        try:
            # Convert to JSON-serializable format
            data = [json.loads(item.model_dump_json()) for item in items]

            with open(self._file_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, sort_keys=True)

            logger.debug("Saved %d instruments to catalogue", len(items))

        except Exception as e:
            logger.error("Failed to save catalogue: %s", e)
            raise

    def get(self, symbol: str) -> InstrumentCatalogueItem | None:
        """
        Get a single instrument by symbol.

        Args:
            symbol: Instrument symbol

        Returns:
            Catalogue item or None if not found
        """
        items = self.load()
        for item in items:
            if item.symbol.upper() == symbol.upper():
                return item
        return None

    def upsert(self, item: InstrumentCatalogueItem) -> bool:
        """
        Insert or update an instrument.

        Args:
            item: Instrument to upsert

        Returns:
            True if updated existing, False if inserted new
        """
        items = self.load()
        item.updated_at = datetime.utcnow()

        # Check for existing
        for i, existing in enumerate(items):
            if existing.symbol.upper() == item.symbol.upper():
                items[i] = item
                self.save(items)
                return True

        # Insert new
        items.append(item)
        self.save(items)
        return False

    def delete(self, symbol: str) -> bool:
        """
        Delete an instrument by symbol.

        Args:
            symbol: Symbol to delete

        Returns:
            True if deleted, False if not found
        """
        items = self.load()
        original_count = len(items)
        items = [item for item in items if item.symbol.upper() != symbol.upper()]

        if len(items) < original_count:
            self.save(items)
            return True
        return False

    def bootstrap(
        self,
        seed_items: list[CatalogueSeedItem],
    ) -> dict[str, Any]:
        """
        Bootstrap catalogue from seed items.

        This is idempotent - existing items are preserved, new ones added.

        Args:
            seed_items: List of seed items

        Returns:
            Summary of bootstrap operation
        """
        existing = self.load()
        existing_symbols = {item.symbol.upper() for item in existing}

        created = 0
        skipped = 0

        for seed in seed_items:
            if seed.symbol.upper() in existing_symbols:
                skipped += 1
                continue

            # Create new catalogue item from seed
            item = InstrumentCatalogueItem(
                symbol=seed.symbol,
                epic=None,  # Will be filled by enrichment
                display_name=seed.display_name,
                asset_class=seed.asset_class,
                currency=seed.currency,
                pip_size=seed.pip_size,
                search_hint=seed.search_hint,
                is_enriched=False,
                updated_at=datetime.utcnow(),
            )
            existing.append(item)
            created += 1

        self.save(existing)

        return {
            "created": created,
            "skipped": skipped,
            "total": len(existing),
        }

    def get_by_asset_class(self, asset_class: AssetClass) -> list[InstrumentCatalogueItem]:
        """
        Get instruments by asset class.

        Args:
            asset_class: Asset class to filter by

        Returns:
            List of matching instruments
        """
        items = self.load()
        return [item for item in items if item.asset_class == asset_class]

    def get_unenriched(self) -> list[InstrumentCatalogueItem]:
        """
        Get instruments that haven't been enriched.

        Returns:
            List of unenriched instruments
        """
        items = self.load()
        return [item for item in items if not item.is_enriched]

    def count(self) -> int:
        """Get total number of instruments."""
        return len(self.load())

    def clear(self) -> None:
        """Clear all instruments (use with caution)."""
        self.save([])
        logger.warning("Catalogue cleared")
