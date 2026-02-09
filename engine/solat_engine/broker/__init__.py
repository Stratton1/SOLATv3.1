"""
Broker adapters for SOLAT trading engine.

Currently supported:
- IG Markets (REST + Streaming)
"""

from solat_engine.broker.ig.client import AsyncIGClient

__all__ = ["AsyncIGClient"]
