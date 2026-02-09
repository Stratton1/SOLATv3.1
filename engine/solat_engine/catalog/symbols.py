"""
Symbol resolution and aliasing for SOLAT.

Maps catalogue symbols to storage keys (e.g., Parquet partition names).
"""

# Mapping: Catalogue Symbol -> Storage Key
# This should match the mapping used in import scripts (e.g., import_histdata.py)
STORAGE_ALIAS_MAP = {
    # Commodities
    "XAUUSD": "GOLD",
    "XAGUSD": "SILVER",
    # Indices
    "GER40": "DAX",
    "UK100": "FTSE100",
    "US500": "SP500",
    "NAS100": "NASDAQ",
    "JP225": "NIKKEI",
    "AUS200": "ASX200",
}


def resolve_storage_symbol(symbol: str) -> str:
    """
    Resolve a catalogue symbol to its storage key (alias).

    Args:
        symbol: Input symbol from catalogue or UI

    Returns:
        The symbol to use for storage lookups (Parquet partitions)
    """
    upper_symbol = symbol.upper()
    return STORAGE_ALIAS_MAP.get(upper_symbol, upper_symbol)
