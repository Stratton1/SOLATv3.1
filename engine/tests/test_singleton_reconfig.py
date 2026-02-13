from dataclasses import dataclass
from pathlib import Path

from solat_engine.api import execution_routes
from solat_engine.api import ig_routes
from solat_engine.execution.models import ExecutionConfig, ExecutionMode


@dataclass
class DummySettings:
    data_dir: Path
    ig_base_url: str = "https://demo-api.ig.com/gateway/deal"
    ig_request_timeout: float = 10.0
    ig_max_retries: int = 2
    ig_rate_limit_rps: float = 5.0
    ig_rate_limit_burst: int = 5
    ig_api_key: None = None
    ig_username: None = None
    ig_password: None = None


def test_execution_router_singleton_updates_config(tmp_path: Path) -> None:
    execution_routes._execution_router = None

    settings = DummySettings(data_dir=tmp_path / "data")
    config_initial = ExecutionConfig(mode=ExecutionMode.DEMO, max_position_size=1.0)
    config_updated = ExecutionConfig(mode=ExecutionMode.DEMO, max_position_size=2.5)

    router_initial = execution_routes.get_execution_router(settings=settings, config=config_initial)
    router_updated = execution_routes.get_execution_router(settings=settings, config=config_updated)

    assert router_initial is router_updated
    assert router_updated._config.max_position_size == 2.5


def test_ig_client_singleton_updates_runtime_settings(tmp_path: Path) -> None:
    execution_routes._ig_client = None
    ig_routes._ig_client = None

    settings_a = DummySettings(data_dir=tmp_path / "a", ig_base_url="https://demo-a")
    settings_b = DummySettings(data_dir=tmp_path / "b", ig_base_url="https://demo-b")

    client_a = execution_routes.get_ig_client(settings=settings_a)
    client_b = execution_routes.get_ig_client(settings=settings_b)

    assert client_a is client_b
    assert client_b._base_url == "https://demo-b"

    # Verify shared behavior for IG API routes singleton accessor as well.
    api_client = ig_routes.get_ig_client(settings=settings_b)
    assert api_client._base_url == "https://demo-b"
