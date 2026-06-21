"""Tests for the Trade Quality Gate — net-cost-aware entry filter.

The gate only allows a trade when, beyond direction, the expected edge clears
all of: conviction, net-edge-vs-cost, cooldown, and daily-cap. All thresholds
are configurable; defaults are the "Balanced" profile.
"""
from __future__ import annotations

from wallet_manager.strategies.trade_quality_gate import (
    GateConfig,
    TradeQualityGate,
)

# Balanced defaults: alpha_to_bps_scale=50 → |alpha|*50 = expected bps.
# net_edge_multiplier=2 → required = 2 * cost_bps.


def _gate(**overrides) -> TradeQualityGate:
    cfg = GateConfig(**overrides)
    return TradeQualityGate(config=cfg)


def test_disabled_passes_through_even_when_edge_below_cost():
    g = _gate(enabled=False)
    d = g.evaluate(robust_alpha=0.001, confidence=0.0, cost_bps=100.0, now=1000.0)
    assert d.allow is True
    assert d.reason == "DISABLED"


def test_low_conviction_blocks():
    g = _gate(min_conviction=0.55)
    d = g.evaluate(robust_alpha=0.9, confidence=0.40, cost_bps=5.0, now=1000.0)
    assert d.allow is False
    assert d.reason == "LOW_CONVICTION"


def test_edge_below_cost_blocks():
    # expected = 0.10*50 = 5 bps; required = 2*10 = 20 bps → blocked
    g = _gate(net_edge_multiplier=2.0, alpha_to_bps_scale=50.0, min_conviction=0.5)
    d = g.evaluate(robust_alpha=0.10, confidence=0.9, cost_bps=10.0, now=1000.0)
    assert d.allow is False
    assert d.reason == "EDGE_BELOW_COST"
    assert d.expected_edge_bps == 5.0
    assert d.required_edge_bps == 20.0


def test_edge_above_cost_passes():
    # expected = 0.90*50 = 45 bps; required = 2*10 = 20 bps → pass
    g = _gate(net_edge_multiplier=2.0, alpha_to_bps_scale=50.0, min_conviction=0.5)
    d = g.evaluate(robust_alpha=0.90, confidence=0.9, cost_bps=10.0, now=1000.0)
    assert d.allow is True
    assert d.reason == "PASS"


def test_cooldown_blocks_then_expires():
    g = _gate(cooldown_seconds=1800.0, min_conviction=0.5,
              alpha_to_bps_scale=50.0, net_edge_multiplier=2.0)
    # First trade passes and is recorded
    d0 = g.evaluate(robust_alpha=0.9, confidence=0.9, cost_bps=5.0, now=1000.0)
    assert d0.allow is True
    g.record_trade(now=1000.0)
    # 10 min later → still in cooldown
    d1 = g.evaluate(robust_alpha=0.9, confidence=0.9, cost_bps=5.0, now=1000.0 + 600)
    assert d1.allow is False
    assert d1.reason == "COOLDOWN"
    # 31 min later → cooldown expired
    d2 = g.evaluate(robust_alpha=0.9, confidence=0.9, cost_bps=5.0, now=1000.0 + 1860)
    assert d2.allow is True
    assert d2.reason == "PASS"


def test_daily_cap_blocks_and_resets_next_day():
    g = _gate(max_trades_per_day=2, cooldown_seconds=0.0, min_conviction=0.5,
              alpha_to_bps_scale=50.0, net_edge_multiplier=2.0)
    base = 1_700_000_000.0  # some UTC day
    g.record_trade(now=base)
    g.record_trade(now=base + 10)
    # Third within same day → capped
    d = g.evaluate(robust_alpha=0.9, confidence=0.9, cost_bps=5.0, now=base + 20)
    assert d.allow is False
    assert d.reason == "DAILY_CAP"
    # Next day → reset
    d2 = g.evaluate(robust_alpha=0.9, confidence=0.9, cost_bps=5.0, now=base + 86_400 + 20)
    assert d2.allow is True
    assert d2.reason == "PASS"


def test_expected_edge_scales_linearly_with_alpha():
    g = _gate(alpha_to_bps_scale=80.0)
    d = g.evaluate(robust_alpha=-0.5, confidence=0.9, cost_bps=1.0, now=1.0)
    # uses |alpha|
    assert d.expected_edge_bps == 40.0
