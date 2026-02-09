"""
Seed data for the instrument catalogue.

Defines the 28 core assets for SOLAT trading.
"""

from decimal import Decimal

from solat_engine.catalog.models import AssetClass, CatalogueSeedItem

# =============================================================================
# SEED DATA: 28 Core Assets
# =============================================================================

SEED_INSTRUMENTS: list[CatalogueSeedItem] = [
    # =========================================================================
    # FOREX (10 pairs)
    # =========================================================================
    CatalogueSeedItem(
        symbol="EURUSD",
        display_name="EUR/USD",
        asset_class=AssetClass.FX,
        search_hint="EUR/USD",
        currency="USD",
        pip_size=Decimal("0.0001"),
        demo_epic="CS.D.EURUSD.MINI.IP",
        live_epic="CS.D.EURUSD.TODAY.IP",
    ),
    CatalogueSeedItem(
        symbol="GBPUSD",
        display_name="GBP/USD",
        asset_class=AssetClass.FX,
        search_hint="GBP/USD",
        currency="USD",
        pip_size=Decimal("0.0001"),
        demo_epic="CS.D.GBPUSD.MINI.IP",
        live_epic="CS.D.GBPUSD.TODAY.IP",
    ),
    CatalogueSeedItem(
        symbol="USDJPY",
        display_name="USD/JPY",
        asset_class=AssetClass.FX,
        search_hint="USD/JPY",
        currency="JPY",
        pip_size=Decimal("0.01"),
        demo_epic="CS.D.USDJPY.MINI.IP",
        live_epic="CS.D.USDJPY.TODAY.IP",
    ),
    CatalogueSeedItem(
        symbol="USDCHF",
        display_name="USD/CHF",
        asset_class=AssetClass.FX,
        search_hint="USD/CHF",
        currency="CHF",
        pip_size=Decimal("0.0001"),
        demo_epic="CS.D.USDCHF.MINI.IP",
        live_epic="CS.D.USDCHF.TODAY.IP",
    ),
    CatalogueSeedItem(
        symbol="AUDUSD",
        display_name="AUD/USD",
        asset_class=AssetClass.FX,
        search_hint="AUD/USD",
        currency="USD",
        pip_size=Decimal("0.0001"),
        demo_epic="CS.D.AUDUSD.MINI.IP",
        live_epic="CS.D.AUDUSD.TODAY.IP",
    ),
    CatalogueSeedItem(
        symbol="USDCAD",
        display_name="USD/CAD",
        asset_class=AssetClass.FX,
        search_hint="USD/CAD",
        currency="CAD",
        pip_size=Decimal("0.0001"),
        demo_epic="CS.D.USDCAD.MINI.IP",
        live_epic="CS.D.USDCAD.TODAY.IP",
    ),
    CatalogueSeedItem(
        symbol="NZDUSD",
        display_name="NZD/USD",
        asset_class=AssetClass.FX,
        search_hint="NZD/USD",
        currency="USD",
        pip_size=Decimal("0.0001"),
        demo_epic="CS.D.NZDUSD.MINI.IP",
        live_epic="CS.D.NZDUSD.TODAY.IP",
    ),
    CatalogueSeedItem(
        symbol="EURGBP",
        display_name="EUR/GBP",
        asset_class=AssetClass.FX,
        search_hint="EUR/GBP",
        currency="GBP",
        pip_size=Decimal("0.0001"),
        demo_epic="CS.D.EURGBP.MINI.IP",
        live_epic="CS.D.EURGBP.TODAY.IP",
    ),
    CatalogueSeedItem(
        symbol="EURJPY",
        display_name="EUR/JPY",
        asset_class=AssetClass.FX,
        search_hint="EUR/JPY",
        currency="JPY",
        pip_size=Decimal("0.01"),
        demo_epic="CS.D.EURJPY.MINI.IP",
        live_epic="CS.D.EURJPY.TODAY.IP",
    ),
    CatalogueSeedItem(
        symbol="GBPJPY",
        display_name="GBP/JPY",
        asset_class=AssetClass.FX,
        search_hint="GBP/JPY",
        currency="JPY",
        pip_size=Decimal("0.01"),
        demo_epic="CS.D.GBPJPY.MINI.IP",
        live_epic="CS.D.GBPJPY.TODAY.IP",
    ),
    # =========================================================================
    # INDICES (8)
    # =========================================================================
    CatalogueSeedItem(
        symbol="US500",
        display_name="S&P 500",
        asset_class=AssetClass.INDEX,
        search_hint="US 500",
        currency="USD",
        pip_size=Decimal("0.1"),
    ),
    CatalogueSeedItem(
        symbol="NAS100",
        display_name="NASDAQ 100",
        asset_class=AssetClass.INDEX,
        search_hint="US Tech 100",
        currency="USD",
        pip_size=Decimal("0.1"),
    ),
    CatalogueSeedItem(
        symbol="US30",
        display_name="Dow Jones 30",
        asset_class=AssetClass.INDEX,
        search_hint="Wall Street",
        currency="USD",
        pip_size=Decimal("1"),
    ),
    CatalogueSeedItem(
        symbol="GER40",
        display_name="Germany 40 (DAX)",
        asset_class=AssetClass.INDEX,
        search_hint="Germany 40",
        currency="EUR",
        pip_size=Decimal("0.1"),
    ),
    CatalogueSeedItem(
        symbol="UK100",
        display_name="UK 100 (FTSE)",
        asset_class=AssetClass.INDEX,
        search_hint="UK 100",
        currency="GBP",
        pip_size=Decimal("0.1"),
    ),
    CatalogueSeedItem(
        symbol="FRA40",
        display_name="France 40 (CAC)",
        asset_class=AssetClass.INDEX,
        search_hint="France 40",
        currency="EUR",
        pip_size=Decimal("0.1"),
    ),
    CatalogueSeedItem(
        symbol="JP225",
        display_name="Japan 225 (Nikkei)",
        asset_class=AssetClass.INDEX,
        search_hint="Japan 225",
        currency="JPY",
        pip_size=Decimal("1"),
    ),
    CatalogueSeedItem(
        symbol="AUS200",
        display_name="Australia 200",
        asset_class=AssetClass.INDEX,
        search_hint="Australia 200",
        currency="AUD",
        pip_size=Decimal("0.1"),
    ),
    # =========================================================================
    # COMMODITIES (6)
    # =========================================================================
    CatalogueSeedItem(
        symbol="XAUUSD",
        display_name="Gold",
        asset_class=AssetClass.COMMODITY,
        search_hint="Gold",
        currency="USD",
        pip_size=Decimal("0.01"),
    ),
    CatalogueSeedItem(
        symbol="XAGUSD",
        display_name="Silver",
        asset_class=AssetClass.COMMODITY,
        search_hint="Silver",
        currency="USD",
        pip_size=Decimal("0.001"),
    ),
    CatalogueSeedItem(
        symbol="USOIL",
        display_name="US Crude Oil",
        asset_class=AssetClass.COMMODITY,
        search_hint="Oil - US Crude",
        currency="USD",
        pip_size=Decimal("0.01"),
    ),
    CatalogueSeedItem(
        symbol="UKOIL",
        display_name="UK Brent Oil",
        asset_class=AssetClass.COMMODITY,
        search_hint="Oil - Brent Crude",
        currency="USD",
        pip_size=Decimal("0.01"),
    ),
    CatalogueSeedItem(
        symbol="NATGAS",
        display_name="Natural Gas",
        asset_class=AssetClass.COMMODITY,
        search_hint="Natural Gas",
        currency="USD",
        pip_size=Decimal("0.001"),
    ),
    CatalogueSeedItem(
        symbol="COPPER",
        display_name="Copper",
        asset_class=AssetClass.COMMODITY,
        search_hint="Copper",
        currency="USD",
        pip_size=Decimal("0.0001"),
    ),
    # =========================================================================
    # CRYPTO (4)
    # =========================================================================
    CatalogueSeedItem(
        symbol="BTCUSD",
        display_name="Bitcoin",
        asset_class=AssetClass.CRYPTO,
        search_hint="Bitcoin",
        currency="USD",
        pip_size=Decimal("0.01"),
    ),
    CatalogueSeedItem(
        symbol="ETHUSD",
        display_name="Ethereum",
        asset_class=AssetClass.CRYPTO,
        search_hint="Ethereum",
        currency="USD",
        pip_size=Decimal("0.01"),
    ),
    CatalogueSeedItem(
        symbol="LTCUSD",
        display_name="Litecoin",
        asset_class=AssetClass.CRYPTO,
        search_hint="Litecoin",
        currency="USD",
        pip_size=Decimal("0.01"),
    ),
    CatalogueSeedItem(
        symbol="XRPUSD",
        display_name="Ripple",
        asset_class=AssetClass.CRYPTO,
        search_hint="Ripple",
        currency="USD",
        pip_size=Decimal("0.00001"),
    ),
]


def get_seed_instruments() -> list[CatalogueSeedItem]:
    """Get the list of seed instruments."""
    return SEED_INSTRUMENTS.copy()
