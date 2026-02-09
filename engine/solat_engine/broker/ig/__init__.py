"""
IG Markets broker integration.

Provides:
- AsyncIGClient: Async REST client for IG API
- Rate limiting and retry logic
- Token management (CST, X-SECURITY-TOKEN)
"""

from solat_engine.broker.ig.client import AsyncIGClient
from solat_engine.broker.ig.types import (
    IGAccount,
    IGLoginResponse,
    IGMarketDetails,
    IGMarketSearchItem,
    IGMarketSearchResponse,
)

__all__ = [
    "AsyncIGClient",
    "IGAccount",
    "IGLoginResponse",
    "IGMarketDetails",
    "IGMarketSearchItem",
    "IGMarketSearchResponse",
]
