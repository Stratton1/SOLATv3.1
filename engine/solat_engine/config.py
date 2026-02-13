"""
Configuration management for SOLAT trading engine.

Uses pydantic-settings for type-safe environment variable handling.
Secrets are loaded from environment variables only - never from files in repo.
"""

from enum import Enum
from functools import lru_cache
from pathlib import Path

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class TradingMode(str, Enum):
    """Trading mode: DEMO for paper trading, LIVE for real money."""

    DEMO = "DEMO"
    LIVE = "LIVE"


class AppEnvironment(str, Enum):
    """Application environment."""

    DEVELOPMENT = "development"
    STAGING = "staging"
    PRODUCTION = "production"


class Settings(BaseSettings):
    """
    Application settings loaded from environment variables.

    All sensitive values use SecretStr to prevent accidental logging.
    """

    model_config = SettingsConfigDict(
        env_prefix="SOLAT_",
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Application mode
    mode: TradingMode = Field(
        default=TradingMode.DEMO,
        description="Trading mode: DEMO (paper) or LIVE (real money)",
    )
    env: AppEnvironment = Field(
        default=AppEnvironment.DEVELOPMENT,
        description="Application environment",
    )

    # Server configuration
    host: str = Field(default="127.0.0.1", description="Server host")
    port: int = Field(default=8765, ge=1024, le=65535, description="Server port")

    # Data paths
    data_dir: Path = Field(
        default=Path("./data"),
        description="Root directory for data storage",
    )

    # Logging
    log_level: str = Field(
        default="INFO",
        description="Logging level",
    )

    # IG Broker credentials (loaded from env, never from files)
    ig_api_key: SecretStr | None = Field(
        default=None,
        alias="IG_API_KEY",
        description="IG API key",
    )
    ig_username: SecretStr | None = Field(
        default=None,
        alias="IG_USERNAME",
        description="IG username",
    )
    ig_password: SecretStr | None = Field(
        default=None,
        alias="IG_PASSWORD",
        description="IG password",
    )
    ig_account_id: str | None = Field(
        default=None,
        alias="IG_ACCOUNT_ID",
        description="IG account ID",
    )

    # IG API configuration
    ig_acc_type: TradingMode = Field(
        default=TradingMode.DEMO,
        alias="IG_ACC_TYPE",
        description="IG account type (DEMO or LIVE)",
    )
    ig_base_url_demo: str = Field(
        default="https://demo-api.ig.com/gateway/deal",
        alias="IG_BASE_URL_DEMO",
        description="IG Demo API base URL",
    )
    ig_base_url_live: str = Field(
        default="https://api.ig.com/gateway/deal",
        alias="IG_BASE_URL_LIVE",
        description="IG Live API base URL",
    )
    ig_request_timeout: int = Field(
        default=20,
        alias="IG_REQUEST_TIMEOUT_S",
        description="IG API request timeout in seconds",
        ge=5,
        le=120,
    )
    ig_max_retries: int = Field(
        default=3,
        alias="IG_MAX_RETRIES",
        description="Maximum retry attempts for IG API requests",
        ge=0,
        le=10,
    )
    ig_rate_limit_rps: float = Field(
        default=2.0,
        alias="IG_RATE_LIMIT_RPS",
        description="IG API rate limit (requests per second)",
        gt=0,
        le=10,
    )
    ig_rate_limit_burst: int = Field(
        default=5,
        alias="IG_RATE_LIMIT_BURST",
        description="IG API rate limit burst allowance",
        ge=1,
        le=20,
    )

    # Historical data settings
    history_default_days: int = Field(
        default=30,
        alias="HISTORY_DEFAULT_DAYS",
        description="Default number of days for historical data sync",
        ge=1,
        le=365,
    )
    history_max_rows_per_call: int = Field(
        default=5000,
        alias="HISTORY_MAX_ROWS_PER_CALL",
        description="Maximum rows to return per data API call",
        ge=100,
        le=50000,
    )
    quality_gap_tolerance_multiplier: float = Field(
        default=1.5,
        alias="QUALITY_GAP_TOLERANCE_MULTIPLIER",
        description="Multiplier for gap tolerance (1.5 = 150% of expected interval)",
        ge=1.0,
        le=10.0,
    )

    # Execution settings
    execution_mode: str = Field(
        default="DEMO",
        alias="EXECUTION_MODE",
        description="Execution mode: DEMO or LIVE",
    )

    # LIVE trading gates (all default to safe/disabled)
    live_trading_enabled: bool = Field(
        default=False,
        alias="LIVE_TRADING_ENABLED",
        description="Master switch for LIVE trading (must be explicitly enabled)",
    )
    live_enable_token: SecretStr | None = Field(
        default=None,
        alias="LIVE_ENABLE_TOKEN",
        description="Second-factor token required to enable LIVE trading (no default)",
    )
    live_account_id: str | None = Field(
        default=None,
        alias="LIVE_ACCOUNT_ID",
        description="Locked account ID for LIVE trading (must match broker account)",
    )
    live_max_order_size: float | None = Field(
        default=None,
        alias="LIVE_MAX_ORDER_SIZE",
        description="Maximum order size for LIVE trading (mandatory for LIVE, no default)",
        gt=0,
    )
    live_confirmation_ttl_s: int = Field(
        default=600,
        alias="LIVE_CONFIRMATION_TTL_S",
        description="TTL for UI LIVE confirmation in seconds (default 10 minutes)",
        ge=60,
        le=3600,
    )
    live_prelive_max_age_s: int = Field(
        default=300,
        alias="LIVE_PRELIVE_MAX_AGE_S",
        description="Maximum age of prelive check for LIVE arming (default 5 minutes)",
        ge=60,
        le=1800,
    )
    execution_reconcile_interval_s: int = Field(
        default=5,
        alias="EXECUTION_RECONCILE_INTERVAL_S",
        description="Reconciliation interval in seconds",
        ge=1,
        le=60,
    )
    max_position_size: float = Field(
        default=1.0,
        alias="MAX_POSITION_SIZE",
        description="Maximum position size per trade",
        gt=0,
    )
    max_concurrent_positions: int = Field(
        default=5,
        alias="MAX_CONCURRENT_POSITIONS",
        description="Maximum concurrent open positions",
        ge=1,
        le=100,
    )
    max_daily_loss_pct: float = Field(
        default=5.0,
        alias="MAX_DAILY_LOSS_PCT",
        description="Maximum daily loss percentage before trading halts",
        ge=0.1,
        le=100,
    )
    max_trades_per_hour: int = Field(
        default=20,
        alias="MAX_TRADES_PER_HOUR",
        description="Maximum trades per hour",
        ge=1,
        le=1000,
    )
    per_symbol_exposure_cap: float = Field(
        default=10000.0,
        alias="PER_SYMBOL_EXPOSURE_CAP",
        description="Maximum exposure per symbol",
        gt=0,
    )
    require_sl: bool = Field(
        default=False,
        alias="REQUIRE_SL",
        description="Require stop loss on all trades",
    )
    close_on_kill_switch: bool = Field(
        default=False,
        alias="CLOSE_ON_KILL_SWITCH",
        description="Close all positions when kill switch activates",
    )
    require_arm_confirmation: bool = Field(
        default=True,
        alias="REQUIRE_ARM_CONFIRMATION",
        description="Require explicit confirmation to arm execution",
    )

    # Market data settings
    market_data_mode: str = Field(
        default="stream",
        alias="MARKET_DATA_MODE",
        description="Default market data mode: stream or poll",
    )
    market_data_poll_interval_ms: int = Field(
        default=1500,
        alias="MARKET_DATA_POLL_INTERVAL_MS",
        description="Poll interval in milliseconds (poll mode only)",
        ge=500,
        le=10000,
    )
    market_data_max_quotes_per_sec: int = Field(
        default=10,
        alias="MARKET_DATA_MAX_QUOTES_PER_SEC",
        description="Maximum quote updates per second per symbol (WS throttling)",
        ge=1,
        le=100,
    )
    market_data_max_subscriptions: int = Field(
        default=20,
        alias="MARKET_DATA_MAX_SUBSCRIPTIONS",
        description="Maximum concurrent symbol subscriptions",
        ge=1,
        le=50,
    )
    market_data_persist_bars: bool = Field(
        default=True,
        alias="MARKET_DATA_PERSIST_BARS",
        description="Persist realtime bars to Parquet store",
    )
    market_data_stale_threshold_s: int = Field(
        default=10,
        alias="MARKET_DATA_STALE_THRESHOLD_S",
        description="Seconds without ticks before feed considered stale",
        ge=5,
        le=60,
    )

    @field_validator("log_level")
    @classmethod
    def validate_log_level(cls, v: str) -> str:
        """Validate log level is valid."""
        valid_levels = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
        upper_v = v.upper()
        if upper_v not in valid_levels:
            raise ValueError(f"Invalid log level: {v}. Must be one of {valid_levels}")
        return upper_v

    @field_validator("data_dir")
    @classmethod
    def ensure_data_dir_exists(cls, v: Path) -> Path:
        """Ensure data directory exists."""
        v.mkdir(parents=True, exist_ok=True)
        return v.resolve()

    @property
    def is_demo(self) -> bool:
        """Check if running in demo mode."""
        return self.mode == TradingMode.DEMO

    @property
    def is_live(self) -> bool:
        """Check if running in live mode."""
        return self.mode == TradingMode.LIVE

    @property
    def ig_base_url(self) -> str:
        """Get the IG API base URL based on account type."""
        if self.ig_acc_type == TradingMode.DEMO:
            return self.ig_base_url_demo
        return self.ig_base_url_live

    @property
    def has_ig_credentials(self) -> bool:
        """Check if IG credentials are configured."""
        return all(
            [
                self.ig_api_key is not None,
                self.ig_username is not None,
                self.ig_password is not None,
            ]
        )

    @property
    def has_live_token(self) -> bool:
        """Check if LIVE enable token is configured."""
        return self.live_enable_token is not None

    @property
    def has_live_account_lock(self) -> bool:
        """Check if LIVE account is locked to specific ID."""
        return self.live_account_id is not None

    @property
    def has_live_risk_config(self) -> bool:
        """Check if all mandatory LIVE risk settings are configured."""
        return all([
            self.live_max_order_size is not None,
            self.max_daily_loss_pct > 0,
            self.max_concurrent_positions > 0,
            self.per_symbol_exposure_cap > 0,
            self.max_trades_per_hour > 0,
        ])

    def get_live_risk_blockers(self) -> list[str]:
        """Get list of missing LIVE risk configuration items."""
        blockers = []
        if self.live_max_order_size is None:
            blockers.append("LIVE_MAX_ORDER_SIZE not set")
        if self.max_daily_loss_pct <= 0:
            blockers.append("MAX_DAILY_LOSS_PCT must be positive")
        if self.max_concurrent_positions <= 0:
            blockers.append("MAX_CONCURRENT_POSITIONS must be positive")
        if self.per_symbol_exposure_cap <= 0:
            blockers.append("PER_SYMBOL_EXPOSURE_CAP must be positive")
        if self.max_trades_per_hour <= 0:
            blockers.append("MAX_TRADES_PER_HOUR must be positive")
        return blockers

    def get_redacted_config(self) -> dict[str, str | int | bool]:
        """
        Get configuration dict with sensitive values redacted.
        Safe for logging and API responses.
        """
        return {
            "mode": self.mode.value,
            "env": self.env.value,
            "host": self.host,
            "port": self.port,
            "data_dir": str(self.data_dir),
            "log_level": self.log_level,
            "ig_configured": self.has_ig_credentials,
            "ig_base_url": self.ig_base_url,
        }


@lru_cache
def get_settings() -> Settings:
    """
    Get cached settings instance.

    Uses lru_cache to ensure single instance throughout application.
    """
    return Settings()


def get_settings_dep() -> Settings:
    """
    Dependency for FastAPI routes to get settings.
    Allows for easy dependency override in tests.
    """
    return get_settings()
