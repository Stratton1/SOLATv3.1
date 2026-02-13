"""
Stress test for emergency Kill Switch activation (Phase 7.3).
Verifies parallel liquidation and fail-closed behavior.
"""

import asyncio
import pytest
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock
from pathlib import Path

from solat_engine.execution.router import ExecutionRouter
from solat_engine.execution.models import ExecutionConfig, ExecutionMode, OrderIntent, OrderSide, OrderStatus, PositionView

@pytest.fixture
def mock_broker():
    broker = AsyncMock()
    # Simulate a slow but successful close (200ms)
    async def slow_close(*args, **kwargs):
        print(f"DEBUG: slow_close called for {args} {kwargs}")
        await asyncio.sleep(0.2)
        return {"dealId": "DEAL_CLOSED", "dealStatus": "ACCEPTED"}
    
    broker.close_position = AsyncMock(side_effect=slow_close)
    broker.list_accounts = AsyncMock(return_value=[{
        "accountId": "TEST_ACC",
        "balance": {"balance": 10000.0}
    }])
    
    # Mock list_positions to return the positions we expect
    broker.list_positions = AsyncMock(return_value=[]) 
    
    # Fix the verify_account_for_live issue
    broker.verify_account_for_live = AsyncMock(return_value={
        "verified": False,
        "is_live": False
    })
    return broker

@pytest.mark.asyncio
async def test_kill_switch_parallel_liquidation(mock_broker, tmp_path):
    """Verify that Kill Switch closes multiple positions in parallel, not one by one."""
    config = ExecutionConfig(
        mode=ExecutionMode.DEMO,
        close_on_kill_switch=True,
        require_arm_confirmation=False
    )
    
    router = ExecutionRouter(config, tmp_path)
    await router.connect(mock_broker)
    
    # Stop reconciliation service to prevent it from interfering with our manually injected positions
    await router.reconciliation.stop()
    
    await router.arm()
    
    # 1. Manually populate position store with 5 positions
    positions = []
    for i in range(5):
        pos = PositionView(
            deal_id=f"DEAL_{i}",
            symbol="EURUSD",
            epic=f"EPIC_{i}",
            direction=OrderSide.BUY,
            size=1.0,
            open_level=1.1000,
            timestamp=datetime.now(UTC)
        )
        positions.append(pos)
    
    router.position_store.update_from_broker(positions)
    
    assert len(router.get_positions()) == 5
    
    # 2. Activate Kill Switch and time the liquidation
    start_time = asyncio.get_event_loop().time()
    await router.activate_kill_switch(reason="Stress Test")
    end_time = asyncio.get_event_loop().time()
    
    duration = end_time - start_time
    
    # Each close takes 200ms. 
    # If sequential: 5 * 200ms = 1.0s+
    # If parallel: ~200ms + overhead
    print(f"\nLiquidation duration: {duration:.4f}s")
    
    assert duration < 0.6, f"Liquidation too slow ({duration:.4f}s), likely sequential!"
    assert router.state.kill_switch_active is True
    assert router.state.armed is False
    
    # 3. Verify fail-closed (new orders rejected)
    intent = OrderIntent(
        symbol="EURUSD",
        side=OrderSide.BUY,
        size=1.0,
        bot="Test"
    )
    ack = await router.route_intent(intent)
    assert ack.status == OrderStatus.REJECTED
    assert "Kill switch" in ack.rejection_reason
