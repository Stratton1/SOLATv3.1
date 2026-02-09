"""
IG broker API routes.

All routes handle IG REST API interactions with proper error handling
and never expose sensitive tokens.
"""

from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from solat_engine.broker.ig.client import AsyncIGClient, IGAPIError, IGAuthError
from solat_engine.broker.ig.types import IGMarketSearchItem, IGTestLoginResult
from solat_engine.config import Settings, get_settings_dep
from solat_engine.logging import get_logger

router = APIRouter(prefix="/ig", tags=["IG Broker"])
logger = get_logger(__name__)

# Lazy-initialized client
_ig_client: AsyncIGClient | None = None


def get_ig_client(settings: Settings = Depends(get_settings_dep)) -> AsyncIGClient:
    """Get or create IG client singleton."""
    global _ig_client
    # In tests, if settings changed, we might need to recreate or reconfigure the client
    if _ig_client is None:
        _ig_client = AsyncIGClient(settings, logger)
    else:
        # Update settings reference in case it's overridden
        _ig_client.settings = settings
    return _ig_client


# =============================================================================
# Response Models
# =============================================================================


class IGAccountResponse(BaseModel):
    """Redacted account info for API response."""

    account_id: str
    account_name: str
    account_type: str
    currency: str | None = None  # Optional - not always returned by IG
    preferred: bool


class IGAccountsResponse(BaseModel):
    """List of accounts response."""

    accounts: list[IGAccountResponse]
    count: int
    fetched_at: datetime


class IGMarketSearchResponse(BaseModel):
    """Market search response."""

    markets: list[IGMarketSearchItem]
    count: int
    query: str


class IGErrorResponse(BaseModel):
    """Error response."""

    ok: bool = False
    error: str
    error_code: str | None = None


# =============================================================================
# Routes
# =============================================================================


@router.post("/test-login", response_model=IGTestLoginResult)
async def test_ig_login(
    settings: Settings = Depends(get_settings_dep),
    client: AsyncIGClient = Depends(get_ig_client),
) -> IGTestLoginResult:
    """
    Test IG login with configured credentials.

    Attempts to authenticate with IG and returns account info.
    Never returns session tokens.
    """
    # Check for missing credentials
    if not settings.ig_api_key:
        return IGTestLoginResult(
            ok=False,
            mode=settings.ig_acc_type.value,
            message="IG_API_KEY not configured",
        )

    if not settings.ig_username:
        return IGTestLoginResult(
            ok=False,
            mode=settings.ig_acc_type.value,
            message="IG_USERNAME not configured",
        )

    if not settings.ig_password:
        return IGTestLoginResult(
            ok=False,
            mode=settings.ig_acc_type.value,
            message="IG_PASSWORD not configured",
        )

    try:
        login_response = await client.login()

        return IGTestLoginResult(
            ok=True,
            mode=settings.ig_acc_type.value,
            accounts_count=len(login_response.accounts),
            current_account_id=login_response.account_id,
            lightstreamer_endpoint=login_response.lightstreamer_endpoint,
            fetched_at=datetime.utcnow(),
            message="Login successful",
        )

    except IGAuthError as e:
        logger.warning("IG login failed: %s", str(e))
        return IGTestLoginResult(
            ok=False,
            mode=settings.ig_acc_type.value,
            message=f"Authentication failed: {str(e)}",
        )

    except IGAPIError as e:
        logger.error("IG API error during login: %s", str(e))
        return IGTestLoginResult(
            ok=False,
            mode=settings.ig_acc_type.value,
            message=f"API error: {str(e)}",
        )

    except Exception as e:
        logger.exception("Unexpected error during IG login")
        return IGTestLoginResult(
            ok=False,
            mode=settings.ig_acc_type.value,
            message=f"Unexpected error: {str(e)}",
        )


@router.get("/accounts", response_model=IGAccountsResponse)
async def get_accounts(
    settings: Settings = Depends(get_settings_dep),
    client: AsyncIGClient = Depends(get_ig_client),
) -> IGAccountsResponse:
    """
    Get list of IG accounts.

    Requires valid session (will auto-login if needed).
    """
    if not settings.has_ig_credentials:
        raise HTTPException(
            status_code=400,
            detail="IG credentials not configured",
        )

    try:
        accounts = await client.get_accounts()

        return IGAccountsResponse(
            accounts=[
                IGAccountResponse(
                    account_id=acc.account_id,
                    account_name=acc.account_name,
                    account_type=acc.account_type.value,
                    currency=acc.currency,
                    preferred=acc.preferred,
                )
                for acc in accounts
            ],
            count=len(accounts),
            fetched_at=datetime.utcnow(),
        )

    except IGAuthError as e:
        raise HTTPException(status_code=401, detail=str(e))

    except IGAPIError as e:
        raise HTTPException(status_code=502, detail=str(e))


@router.get("/markets/search", response_model=IGMarketSearchResponse)
async def search_markets(
    q: str = Query(..., min_length=1, max_length=100, description="Search query"),
    limit: int = Query(default=20, ge=1, le=50, description="Max results"),
    settings: Settings = Depends(get_settings_dep),
    client: AsyncIGClient = Depends(get_ig_client),
) -> IGMarketSearchResponse:
    """
    Search IG markets by name/symbol.

    Requires valid session (will auto-login if needed).
    """
    if not settings.has_ig_credentials:
        raise HTTPException(
            status_code=400,
            detail="IG credentials not configured",
        )

    try:
        markets = await client.search_markets(q, max_results=limit)

        return IGMarketSearchResponse(
            markets=markets,
            count=len(markets),
            query=q,
        )

    except IGAuthError as e:
        raise HTTPException(status_code=401, detail=str(e))

    except IGAPIError as e:
        raise HTTPException(status_code=502, detail=str(e))


@router.get("/status")
async def ig_status(
    settings: Settings = Depends(get_settings_dep),
    client: AsyncIGClient = Depends(get_ig_client),
) -> dict[str, Any]:
    """
    Get IG client status (no auth required).

    Returns connection state and rate limiter stats.
    """
    return {
        "configured": settings.has_ig_credentials,
        "mode": settings.ig_acc_type.value,
        "base_url": settings.ig_base_url,
        "authenticated": client.is_authenticated,
        "session_age_seconds": client.session_age_seconds,
        "rate_limiter": client.rate_limiter_stats,
    }
