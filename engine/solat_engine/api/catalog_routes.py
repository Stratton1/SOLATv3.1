"""
Instrument catalogue API routes.
"""

from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from solat_engine.broker.ig.client import IGAPIError, IGAuthError
from solat_engine.catalog.models import (
    AssetClass,
    DealingRulesSummary,
    InstrumentCatalogueItem,
)
from solat_engine.catalog.seed import get_seed_instruments
from solat_engine.catalog.store import CatalogueStore
from solat_engine.config import Settings, get_settings_dep
from solat_engine.logging import get_logger

router = APIRouter(prefix="/catalog", tags=["Catalogue"])
logger = get_logger(__name__)

# Lazy-initialized store
_catalogue_store: CatalogueStore | None = None


def get_catalogue_store() -> CatalogueStore:
    """Get or create catalogue store singleton."""
    global _catalogue_store
    if _catalogue_store is None:
        _catalogue_store = CatalogueStore()
    return _catalogue_store


# =============================================================================
# Response Models
# =============================================================================


class BootstrapResponse(BaseModel):
    """Response from bootstrap operation."""

    ok: bool = True
    created: int = 0
    updated: int = 0
    enriched: int = 0
    failed_enrichment: int = 0
    total: int = 0
    warnings: list[str] = Field(default_factory=list)
    message: str = ""


class CatalogueListResponse(BaseModel):
    """List of catalogue instruments."""

    instruments: list[InstrumentCatalogueItem]
    count: int
    enriched_count: int


class CatalogueSummaryResponse(BaseModel):
    """Summary of catalogue."""

    total: int
    enriched: int
    by_asset_class: dict[str, int]


# =============================================================================
# Routes
# =============================================================================


@router.post("/bootstrap", response_model=BootstrapResponse)
async def bootstrap_catalogue(
    enrich: bool = Query(
        default=True,
        description="Attempt to enrich from IG API if credentials available",
    ),
    settings: Settings = Depends(get_settings_dep),
    store: CatalogueStore = Depends(get_catalogue_store),
) -> BootstrapResponse:
    """
    Bootstrap the instrument catalogue from seed data.

    This is idempotent - can be run multiple times safely.
    If IG credentials are configured and enrich=True, will attempt
    to look up each instrument and fill in epic/dealing rules.
    """
    # First, bootstrap from seed
    seed_items = get_seed_instruments()
    bootstrap_result = store.bootstrap(seed_items)

    created = bootstrap_result["created"]
    enriched = 0
    failed_enrichment = 0
    warnings: list[str] = []

    # Attempt enrichment if requested and credentials available
    if enrich and settings.has_ig_credentials:
        logger.info("Attempting catalogue enrichment from IG API")

        try:
            from solat_engine.api.ig_routes import get_ig_client

            client = get_ig_client(settings=settings)

            # Get unenriched items
            unenriched = store.get_unenriched()
            logger.info("Found %d unenriched instruments", len(unenriched))

            for item in unenriched:
                try:
                    # Search for the instrument
                    search_query = item.search_hint or item.display_name
                    markets = await client.search_markets(search_query, max_results=5)

                    if not markets:
                        item.enrichment_error = f"No markets found for '{search_query}'"
                        item.updated_at = datetime.utcnow()
                        store.upsert(item)
                        failed_enrichment += 1
                        warnings.append(f"{item.symbol}: No markets found")
                        continue

                    # Pick best match (first result for now)
                    best_match = markets[0]
                    epic = best_match.epic

                    # Get detailed market info
                    details = await client.get_market_details(epic)

                    if details:
                        # Update item with IG data
                        item.epic = epic
                        item.display_name = details.instrument_name or item.display_name
                        item.currency = details.currency or item.currency
                        item.lot_size = details.lot_size
                        item.margin_factor = details.margin_factor

                        if details.dealing_rules:
                            item.dealing_rules = DealingRulesSummary(
                                minDealSize=details.dealing_rules.min_deal_size,
                                maxDealSize=details.dealing_rules.max_deal_size,
                                minSizeIncrement=details.dealing_rules.min_size_increment,
                                minStopDistance=details.dealing_rules.min_normal_stop_or_limit_distance,
                                maxStopDistance=details.dealing_rules.max_stop_or_limit_distance,
                            )

                        item.is_enriched = True
                        item.enrichment_error = None
                        item.updated_at = datetime.utcnow()
                        store.upsert(item)
                        enriched += 1
                        logger.debug("Enriched %s -> %s", item.symbol, epic)
                    else:
                        item.epic = epic
                        item.enrichment_error = "Could not fetch market details"
                        item.updated_at = datetime.utcnow()
                        store.upsert(item)
                        failed_enrichment += 1
                        warnings.append(f"{item.symbol}: Could not fetch details for {epic}")

                except IGAPIError as e:
                    item.enrichment_error = str(e)
                    item.updated_at = datetime.utcnow()
                    store.upsert(item)
                    failed_enrichment += 1
                    warnings.append(f"{item.symbol}: API error - {e}")

                except Exception as e:
                    item.enrichment_error = str(e)
                    item.updated_at = datetime.utcnow()
                    store.upsert(item)
                    failed_enrichment += 1
                    warnings.append(f"{item.symbol}: Error - {e}")
                    logger.exception("Error enriching %s", item.symbol)

        except IGAuthError as e:
            warnings.append(f"IG authentication failed: {e}")
            logger.warning("IG auth failed during enrichment: %s", e)

        except Exception as e:
            warnings.append(f"Enrichment error: {e}")
            logger.exception("Unexpected error during enrichment")

    elif enrich and not settings.has_ig_credentials:
        warnings.append("IG credentials not configured - skipping enrichment")

    # Get final count
    final_total = store.count()

    return BootstrapResponse(
        ok=True,
        created=created,
        updated=0,  # Bootstrap doesn't update existing
        enriched=enriched,
        failed_enrichment=failed_enrichment,
        total=final_total,
        warnings=warnings,
        message=f"Bootstrap complete: {created} created, {enriched} enriched",
    )


@router.get("/instruments", response_model=CatalogueListResponse)
async def list_instruments(
    asset_class: AssetClass | None = Query(default=None, description="Filter by asset class"),
    enriched_only: bool = Query(default=False, description="Only return enriched instruments"),
    store: CatalogueStore = Depends(get_catalogue_store),
) -> CatalogueListResponse:
    """
    Get list of instruments in the catalogue.
    """
    if asset_class:
        instruments = store.get_by_asset_class(asset_class)
    else:
        instruments = store.load()

    if enriched_only:
        instruments = [i for i in instruments if i.is_enriched]

    enriched_count = sum(1 for i in instruments if i.is_enriched)

    return CatalogueListResponse(
        instruments=instruments,
        count=len(instruments),
        enriched_count=enriched_count,
    )


@router.get("/instruments/{symbol}", response_model=InstrumentCatalogueItem)
async def get_instrument(
    symbol: str,
    store: CatalogueStore = Depends(get_catalogue_store),
) -> InstrumentCatalogueItem:
    """
    Get a single instrument by symbol.
    """
    item = store.get(symbol)

    if not item:
        raise HTTPException(status_code=404, detail=f"Instrument '{symbol}' not found")

    return item


@router.get("/summary", response_model=CatalogueSummaryResponse)
async def catalogue_summary(
    store: CatalogueStore = Depends(get_catalogue_store)
) -> CatalogueSummaryResponse:
    """
    Get catalogue summary statistics.
    """
    instruments = store.load()

    by_asset_class: dict[str, int] = {}
    enriched = 0

    for item in instruments:
        asset_class = item.asset_class.value
        by_asset_class[asset_class] = by_asset_class.get(asset_class, 0) + 1
        if item.is_enriched:
            enriched += 1

    return CatalogueSummaryResponse(
        total=len(instruments),
        enriched=enriched,
        by_asset_class=by_asset_class,
    )


@router.delete("/instruments/{symbol}")
async def delete_instrument(
    symbol: str,
    store: CatalogueStore = Depends(get_catalogue_store),
) -> dict[str, Any]:
    """
    Delete an instrument from the catalogue.
    """
    if store.delete(symbol):
        return {"ok": True, "deleted": symbol}

    raise HTTPException(status_code=404, detail=f"Instrument '{symbol}' not found")
