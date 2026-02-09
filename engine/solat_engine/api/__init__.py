"""
FastAPI route modules for SOLAT engine.
"""

from solat_engine.api.catalog_routes import router as catalog_router
from solat_engine.api.ig_routes import router as ig_router

__all__ = ["catalog_router", "ig_router"]
