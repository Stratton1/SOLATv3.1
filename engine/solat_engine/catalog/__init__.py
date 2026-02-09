"""
Instrument catalogue management.

Provides:
- Local storage for canonical instrument list
- Seed data for the 28 core assets
- Enrichment from IG API
"""

from solat_engine.catalog.models import AssetClass, InstrumentCatalogueItem
from solat_engine.catalog.store import CatalogueStore

__all__ = [
    "AssetClass",
    "CatalogueStore",
    "InstrumentCatalogueItem",
]
