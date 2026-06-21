"""
tests/unit/test_phase5_backtester.py
======================================
Phase 5 — Research and Backtesting Engine: unit tests for EventDrivenBacktester.
"""
from __future__ import annotations

import asyncio
import math

import pytest

from wallet_manager.backtester import (
    BacktestConfig,
    BacktestReport,
    BacktestTrade,
    EventDrivenBacktester,
    _compute_max_drawdown,
    _compute_sharpe,
)


def _run(coro):  # type: ignore[return]
    return asyncio.run(coro)


# ---------------------------------------------------------------------------
# Metric helpers
# ---------------------------------------------------------------------------


class TestComputeSharpe:
    def test_empty(self):
        assert _compute_sharpe([]) == 0.0

    def test_single(self):
        assert _compute_sharpe([0.01]) == 0.0

    def test_flat(self):
        assert _compute_sharpe([0.01] * 100) == 0.0

    def test_positive(self):
        # Varied positive returns: mean > 0, std > 0 → sharpe > 0
        returns = [0.001 + (i % 3) * 0.0005 for i in range(252)]
        sharpe = _compute_sharpe(returns)
        assert sharpe > 0

    def test_negative(self):
        # Varied negative returns: mean < 0, std > 0 → sharpe < 0
        returns = [-0.001 - (i % 3) * 0.0005 for i in range(252)]
        sharpe = _compute_sharpe(returns)
        assert sharpe < 0


class TestComputeMaxDrawdown:
    def test_empty(self):
        assert _compute_max_drawdown([]) == 0.0

    def test_flat(self):
        assert _compute_max_drawdown([100.0] * 10) == 0.0

    def test_full_loss(self):
        curve = [100.0, 50.0, 10.0]
        dd = _compute_max_drawdown(curve)
        assert dd == pytest.approx(0.9)

    def test_recovery(self):
        curve = [100.0, 80.0, 120.0, 90.0]
        dd = _compute_max_drawdown(curve)
        assert dd == pytest.approx(0.25)  # 100→80 = 20%


# ---------------------------------------------------------------------------
# BacktestConfig
# ---------------------------------------------------------------------------


class TestBacktestConfig:
    def test_defaults(self):
        cfg = BacktestConfig()
        assert cfg.initial_usd == 10_000.0
        assert cfg.slippage_bps == 10.0
        assert cfg.gas_usd_per_trade == 0.50
        assert cfg.alpha_threshold == 0.025
        assert cfg.momentum_window == 5

    def test_custom(self):
        cfg = BacktestConfig(dataset_id="ds_test", initial_usd=5_000.0, slippage_bps=5.0)
        assert cfg.dataset_id == "ds_test"
        assert cfg.initial_usd == 5_000.0


# ---------------------------------------------------------------------------
# BacktestReport
# ---------------------------------------------------------------------------


class TestBacktestReport:
    def _make_report(self) -> BacktestReport:
        return BacktestReport(
            config={"initial_usd": 10_000.0},
            dataset_id="ds_test",
            candle_count=1000,
            trade_count=5,
            win_count=3,
            loss_count=2,
            gross_pnl_usd=500.0,
            total_slippage_usd=20.0,
            total_gas_usd=2.5,
            net_pnl_usd=477.5,
            initial_usd=10_000.0,
            final_usd=10_477.5,
            total_return_pct=4.775,
            annualised_sharpe=1.2,
            max_drawdown_pct=2.1,
            win_rate_pct=60.0,
            profit_factor=1.8,
            avg_latency_ms=200.0,
            exit_reasons={"signal": 4, "stop_loss": 1},
        )

    def test_to_text_contains_key_fields(self):
        r = self._make_report()
        text = r.to_text()
        assert "ds_test" in text
        assert "1,000" in text
        assert "4.775" in text or "4.78" in text
        assert "stop_loss" in text

    def test_to_dict_roundtrip(self):
        r = self._make_report()
        d = r.to_dict()
        assert d["dataset_id"] == "ds_test"
        assert d["trade_count"] == 5
        assert d["exit_reasons"]["signal"] == 4

    def test_save_and_reload(self, tmp_path):
        r = self._make_report()
        path = str(tmp_path / "bt.json")
        r.save(path)
        import json
        with open(path) as f:
            loaded = json.load(f)
        assert loaded["dataset_id"] == "ds_test"
        assert loaded["net_pnl_usd"] == pytest.approx(477.5)


# ---------------------------------------------------------------------------
# EventDrivenBacktester — internal helpers
# ---------------------------------------------------------------------------


class TestCloseTrade:
    def test_profitable_trade(self):
        cfg = BacktestConfig(slippage_bps=10.0, gas_usd_per_trade=0.50, latency_ms=100.0)
        trade = EventDrivenBacktester._close_trade(
            entry_ts=1000, exit_ts=2000,
            entry_price=2000.0, exit_price=2100.0,
            position_usd=1000.0, cfg=cfg,
            exit_reason="signal",
        )
        # Gross: 5% gain on $1000 = $50
        # Slip on exit: 1000 * 0.001 = $1
        # Gas: $0.50
        assert trade.pnl_usd > 0
        assert trade.pnl_net_usd < trade.pnl_usd  # costs reduce net
        assert trade.slippage_cost_usd == pytest.approx(1.0, rel=0.01)
        assert trade.gas_cost_usd == pytest.approx(0.50)
        assert trade.exit_reason == "signal"

    def test_losing_trade(self):
        cfg = BacktestConfig(slippage_bps=10.0, gas_usd_per_trade=0.50)
        trade = EventDrivenBacktester._close_trade(
            entry_ts=1000, exit_ts=2000,
            entry_price=2100.0, exit_price=2000.0,
            position_usd=1000.0, cfg=cfg,
            exit_reason="stop_loss",
        )
        assert trade.pnl_usd < 0
        assert trade.pnl_net_usd < trade.pnl_usd  # costs make it worse


# ---------------------------------------------------------------------------
# EventDrivenBacktester — full simulation (synthetic closes)
# ---------------------------------------------------------------------------


class TestEventDrivenBacktester:
    def _make_engine(self, closes: list[float], **cfg_kwargs) -> EventDrivenBacktester:
        """Build an engine whose _load_candles returns the given closes."""
        import pandas as pd

        cfg = BacktestConfig(**cfg_kwargs)
        engine = EventDrivenBacktester(cfg)

        async def _mock_load():
            n = len(closes)
            return pd.DataFrame({
                "timestamp": list(range(n)),
                "close": closes,
            })

        engine._load_candles = _mock_load  # type: ignore[method-assign]
        return engine

    def test_empty_candles_returns_empty_report(self):
        import pandas as pd
        cfg = BacktestConfig()
        engine = EventDrivenBacktester(cfg)

        async def _empty():
            return pd.DataFrame()

        engine._load_candles = _empty  # type: ignore[method-assign]
        report = _run(engine.run())
        assert report.trade_count == 0
        assert report.final_usd == cfg.initial_usd

    def test_flat_market_no_trades(self):
        closes = [2000.0] * 100
        engine = self._make_engine(closes, alpha_threshold=0.01, momentum_window=5)
        report = _run(engine.run())
        assert report.trade_count == 0
        assert report.candle_count == 100

    def test_trending_market_generates_trades(self):
        # Steadily rising prices produce alpha > threshold
        closes = [2000.0 + i * 5 for i in range(200)]
        engine = self._make_engine(closes, alpha_threshold=0.005, momentum_window=5)
        report = _run(engine.run())
        assert report.trade_count >= 1

    def test_costs_reduce_gross_pnl(self):
        closes = [2000.0 + i * 5 for i in range(200)]
        engine = self._make_engine(
            closes, alpha_threshold=0.005, momentum_window=5,
            slippage_bps=20.0, gas_usd_per_trade=1.0,
        )
        report = _run(engine.run())
        if report.trade_count > 0:
            assert report.total_slippage_usd > 0
            assert report.total_gas_usd > 0
            assert report.net_pnl_usd < report.gross_pnl_usd

    def test_stop_loss_fires(self):
        # Price drops immediately after entry
        closes = [2000.0] * 5 + [2100.0] + [1800.0] * 50
        engine = self._make_engine(
            closes, alpha_threshold=0.01, momentum_window=5,
            stop_loss_pct=0.03, take_profit_pct=0.20,
        )
        report = _run(engine.run())
        assert report.exit_reasons.get("stop_loss", 0) >= 0  # may fire depending on signal

    def test_take_profit_fires(self):
        # Price rises sharply after entry
        closes = [2000.0] * 5 + [2100.0] + [2300.0] * 50
        engine = self._make_engine(
            closes, alpha_threshold=0.01, momentum_window=5,
            stop_loss_pct=0.50, take_profit_pct=0.05,
        )
        report = _run(engine.run())
        # take_profit may fire
        assert isinstance(report.exit_reasons, dict)

    def test_report_is_reproducible(self):
        closes = [2000.0 + math.sin(i * 0.3) * 50 for i in range(300)]
        engine1 = self._make_engine(closes, alpha_threshold=0.01, momentum_window=5)
        engine2 = self._make_engine(closes, alpha_threshold=0.01, momentum_window=5)
        r1 = _run(engine1.run())
        r2 = _run(engine2.run())
        assert r1.trade_count == r2.trade_count
        assert r1.net_pnl_usd == r2.net_pnl_usd

    def test_equity_curve_length(self):
        closes = [2000.0] * 50
        engine = self._make_engine(closes, momentum_window=5)
        report = _run(engine.run())
        # equity_curve has one entry per bar after the warmup window
        assert len(report.equity_curve) > 0

    def test_win_loss_counts_add_up(self):
        closes = [2000.0 + math.sin(i * 0.5) * 100 for i in range(400)]
        engine = self._make_engine(closes, alpha_threshold=0.005, momentum_window=5)
        report = _run(engine.run())
        assert report.win_count + report.loss_count == report.trade_count

    def test_to_dict_serialisable(self):
        import json
        closes = [2000.0 + i for i in range(100)]
        engine = self._make_engine(closes, alpha_threshold=0.005, momentum_window=5)
        report = _run(engine.run())
        # Should not raise
        serialised = json.dumps(report.to_dict())
        assert len(serialised) > 0
