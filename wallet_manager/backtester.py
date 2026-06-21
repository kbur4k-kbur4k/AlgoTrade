"""
wallet_manager/backtester.py
============================
Phase 5 — Research and Backtesting Engine.

EventDrivenBacktester: replays historical candles one-by-one and simulates
trades with realistic cost modelling (slippage, gas, latency).

Every run is pinned to a ``dataset_id`` so the same ID always produces the
same result — satisfying the Phase 4 Data Contract and Phase 5 exit gate
("every promoted behavior has reproducible research evidence behind it").

Usage::

    from wallet_manager.backtester import EventDrivenBacktester, BacktestConfig

    cfg = BacktestConfig(
        dataset_id="ds_eth_5m_2024Q1_v1",
        initial_usd=10_000.0,
        alpha_threshold=0.025,
        slippage_bps=10.0,
        gas_usd_per_trade=0.50,
        latency_ms=200.0,
    )
    engine = EventDrivenBacktester(cfg)
    report = await engine.run()
    print(report.to_text())
    report.save("results/bt_2024Q1.json")
"""
from __future__ import annotations

import json
import math
import os
import time
from dataclasses import asdict, dataclass, field
from typing import Any

from wallet_manager.security.logging_filter import build_logger

log = build_logger(__name__)


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------


@dataclass
class BacktestConfig:
    """Parameters that fully determine a backtest run.

    All fields are serialised into ``BacktestReport.config`` so the run is
    self-describing and reproducible.

    Attributes:
        dataset_id: DatasetManifest ID to load.  ``None`` loads all candles.
        initial_usd: Starting capital.
        alpha_threshold: Minimum |alpha| to trigger a trade.
        slippage_bps: One-way slippage in basis points (applied on every fill).
        gas_usd_per_trade: Fixed gas cost subtracted on every fill.
        latency_ms: Simulated execution latency in milliseconds (logged only;
            does not affect fill price in this model).
        momentum_window: Number of bars used for the momentum alpha signal.
        stop_loss_pct: Exit long if unrealised loss exceeds this fraction.
        take_profit_pct: Exit long if unrealised gain exceeds this fraction.
    """

    dataset_id: str | None = None
    initial_usd: float = 10_000.0
    alpha_threshold: float = 0.025
    slippage_bps: float = 10.0
    gas_usd_per_trade: float = 0.50
    latency_ms: float = 200.0
    momentum_window: int = 5
    stop_loss_pct: float = 0.05
    take_profit_pct: float = 0.10


# ---------------------------------------------------------------------------
# Trade record
# ---------------------------------------------------------------------------


@dataclass
class BacktestTrade:
    """One completed round-trip trade."""

    entry_ts: int
    exit_ts: int
    entry_price: float
    exit_price: float
    size_usd: float
    slippage_cost_usd: float
    gas_cost_usd: float
    latency_ms: float
    pnl_usd: float
    pnl_net_usd: float          # after slippage + gas
    exit_reason: str            # signal | stop_loss | take_profit | end_of_data

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------


@dataclass
class BacktestReport:
    """Standardised research output package for one backtest run.

    Attributes match the Phase 5 KPIs:
    - realistic cost-adjusted strategy comparison
    - reproducible research output (pinned to dataset_id)
    """

    config: dict[str, Any]
    dataset_id: str | None
    run_at: float = field(default_factory=time.time)
    candle_count: int = 0
    trade_count: int = 0
    win_count: int = 0
    loss_count: int = 0

    # Cost-adjusted metrics
    gross_pnl_usd: float = 0.0
    total_slippage_usd: float = 0.0
    total_gas_usd: float = 0.0
    net_pnl_usd: float = 0.0

    # Ratios
    initial_usd: float = 0.0
    final_usd: float = 0.0
    total_return_pct: float = 0.0
    annualised_sharpe: float = 0.0
    max_drawdown_pct: float = 0.0
    win_rate_pct: float = 0.0
    profit_factor: float = 0.0
    avg_latency_ms: float = 0.0

    trades: list[dict[str, Any]] = field(default_factory=list)
    equity_curve: list[float] = field(default_factory=list)

    # Exit reason breakdown
    exit_reasons: dict[str, int] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        return d

    def to_text(self) -> str:
        lines = [
            "=" * 60,
            "  BACKTEST REPORT — Phase 5",
            "=" * 60,
            f"  dataset_id       : {self.dataset_id or '(all candles)'}",
            f"  run_at           : {time.strftime('%Y-%m-%d %H:%M UTC', time.gmtime(self.run_at))}",
            f"  candles          : {self.candle_count:,}",
            f"  trades           : {self.trade_count}",
            "",
            "  --- Returns ---",
            f"  initial_usd      : ${self.initial_usd:,.2f}",
            f"  final_usd        : ${self.final_usd:,.2f}",
            f"  total_return     : {self.total_return_pct:+.2f}%",
            f"  annualised_sharpe: {self.annualised_sharpe:.3f}",
            f"  max_drawdown     : {self.max_drawdown_pct:.2f}%",
            "",
            "  --- Trade Quality ---",
            f"  win_rate         : {self.win_rate_pct:.1f}%",
            f"  profit_factor    : {self.profit_factor:.2f}",
            f"  avg_latency_ms   : {self.avg_latency_ms:.0f} ms",
            "",
            "  --- Costs (drag on returns) ---",
            f"  gross_pnl        : ${self.gross_pnl_usd:+,.2f}",
            f"  total_slippage   : ${self.total_slippage_usd:.2f}",
            f"  total_gas        : ${self.total_gas_usd:.2f}",
            f"  net_pnl          : ${self.net_pnl_usd:+,.2f}",
            "",
            "  --- Exit Reasons ---",
        ]
        for reason, count in sorted(self.exit_reasons.items()):
            lines.append(f"  {reason:<20}: {count}")
        lines.append("=" * 60)
        return "\n".join(lines)

    def save(self, path: str) -> None:
        """Persist report to JSON file, creating parent dirs as needed."""
        out_dir = os.path.dirname(path)
        if out_dir:
            os.makedirs(out_dir, exist_ok=True)
        with open(path, "w") as f:
            json.dump(self.to_dict(), f, indent=2)
        log.info("BacktestReport saved to %s", path)


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------


class EventDrivenBacktester:
    """Replay candles event-by-event with realistic cost simulation.

    Args:
        config: ``BacktestConfig`` controlling all run parameters.
        db_path: Override for ``HistoricalDataPipeline`` DB path.
    """

    def __init__(
        self,
        config: BacktestConfig | None = None,
        db_path: str | None = None,
    ) -> None:
        self._cfg = config or BacktestConfig()
        self._db_path = db_path

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def run(self) -> BacktestReport:
        """Execute the full backtest and return a ``BacktestReport``.

        Steps:
        1. Load candles (pinned to dataset_id if provided).
        2. Compute momentum alpha signal for each bar.
        3. Simulate BUY/SELL events with slippage + gas deducted.
        4. Apply stop-loss and take-profit rules.
        5. Aggregate metrics.
        """

        candles = await self._load_candles()
        if candles.empty:
            log.warning("EventDrivenBacktester: no candles loaded — returning empty report")
            return self._empty_report()

        closes = candles["close"].tolist()
        timestamps = candles["timestamp"].tolist()

        report = await self._simulate(closes, timestamps)
        log.info(
            "EventDrivenBacktester: %d candles | %d trades | net_pnl=$%.2f sharpe=%.3f",
            report.candle_count, report.trade_count, report.net_pnl_usd, report.annualised_sharpe,
        )
        return report

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    async def _load_candles(self):  # type: ignore[return]
        try:
            import pandas as pd

            from scripts.data.historical_data_pipeline import HistoricalDataPipeline
            pipeline = HistoricalDataPipeline(db_path=self._db_path) if self._db_path else HistoricalDataPipeline()
            df = await pipeline.load_for_training(dataset_id=self._cfg.dataset_id)
            if df.empty:
                return df
            if "close" not in df.columns:
                return pd.DataFrame()
            return df[["timestamp", "close"]].dropna().sort_values("timestamp").reset_index(drop=True)
        except Exception as exc:
            log.warning("EventDrivenBacktester: candle load failed: %s", exc)
            import pandas as pd
            return pd.DataFrame()

    async def _simulate(
        self,
        closes: list[float],
        timestamps: list[int],
    ) -> BacktestReport:
        cfg = self._cfg
        w = cfg.momentum_window
        equity = cfg.initial_usd
        equity_curve: list[float] = [equity]
        trades: list[BacktestTrade] = []

        in_position = False
        entry_price = 0.0
        entry_ts = 0
        position_usd = 0.0

        for i in range(w, len(closes)):
            price = closes[i]
            ts = int(timestamps[i])

            # --- Alpha: log-momentum over window ---
            prev_price = closes[i - w]
            if prev_price <= 0:
                equity_curve.append(equity)
                continue
            alpha = math.log(price / prev_price)

            # --- Stop-loss / take-profit while in position ---
            if in_position:
                unrealised_pct = (price - entry_price) / entry_price
                if unrealised_pct <= -cfg.stop_loss_pct:
                    trade = self._close_trade(
                        entry_ts, ts, entry_price, price,
                        position_usd, cfg, "stop_loss",
                    )
                    equity += trade.pnl_net_usd
                    trades.append(trade)
                    in_position = False
                    equity_curve.append(max(equity, 0.01))
                    continue
                if unrealised_pct >= cfg.take_profit_pct:
                    trade = self._close_trade(
                        entry_ts, ts, entry_price, price,
                        position_usd, cfg, "take_profit",
                    )
                    equity += trade.pnl_net_usd
                    trades.append(trade)
                    in_position = False
                    equity_curve.append(max(equity, 0.01))
                    continue

            # --- Signal-driven entry / exit ---
            if not in_position and alpha > cfg.alpha_threshold:
                slippage_cost = equity * (cfg.slippage_bps / 10_000)
                entry_cost = slippage_cost + cfg.gas_usd_per_trade
                position_usd = equity - entry_cost
                entry_price = price * (1 + cfg.slippage_bps / 10_000)
                entry_ts = ts
                in_position = True
                equity -= entry_cost  # slippage + gas debited immediately

            elif in_position and alpha < -cfg.alpha_threshold:
                trade = self._close_trade(
                    entry_ts, ts, entry_price, price,
                    position_usd, cfg, "signal",
                )
                equity += trade.pnl_net_usd
                trades.append(trade)
                in_position = False

            equity_curve.append(max(equity, 0.01))

        # Close any open position at end of data
        if in_position and closes:
            trade = self._close_trade(
                entry_ts, int(timestamps[-1]), entry_price, closes[-1],
                position_usd, cfg, "end_of_data",
            )
            equity += trade.pnl_net_usd
            trades.append(trade)
            equity_curve.append(max(equity, 0.01))

        return self._build_report(trades, equity_curve, len(closes))

    @staticmethod
    def _close_trade(
        entry_ts: int,
        exit_ts: int,
        entry_price: float,
        exit_price: float,
        position_usd: float,
        cfg: BacktestConfig,
        exit_reason: str,
    ) -> BacktestTrade:
        """Compute net PnL after slippage and gas on the exit leg."""
        fill_price = exit_price * (1 - cfg.slippage_bps / 10_000)
        price_return = (fill_price - entry_price) / entry_price if entry_price > 0 else 0.0
        gross_pnl = position_usd * price_return
        slip_cost = position_usd * (cfg.slippage_bps / 10_000)
        gas_cost = cfg.gas_usd_per_trade
        net_pnl = gross_pnl - slip_cost - gas_cost
        return BacktestTrade(
            entry_ts=entry_ts,
            exit_ts=exit_ts,
            entry_price=entry_price,
            exit_price=fill_price,
            size_usd=round(position_usd, 4),
            slippage_cost_usd=round(slip_cost, 4),
            gas_cost_usd=round(gas_cost, 4),
            latency_ms=cfg.latency_ms,
            pnl_usd=round(gross_pnl, 4),
            pnl_net_usd=round(net_pnl, 4),
            exit_reason=exit_reason,
        )

    def _build_report(
        self,
        trades: list[BacktestTrade],
        equity_curve: list[float],
        candle_count: int,
    ) -> BacktestReport:
        cfg = self._cfg
        final_equity = equity_curve[-1] if equity_curve else cfg.initial_usd
        net_pnl = final_equity - cfg.initial_usd

        gross_pnl = sum(t.pnl_usd for t in trades)
        total_slip = sum(t.slippage_cost_usd for t in trades)
        total_gas = sum(t.gas_cost_usd for t in trades)

        wins = [t for t in trades if t.pnl_net_usd > 0]
        losses = [t for t in trades if t.pnl_net_usd <= 0]
        gross_profit = sum(t.pnl_net_usd for t in wins)
        gross_loss = abs(sum(t.pnl_net_usd for t in losses))
        profit_factor = (gross_profit / gross_loss) if gross_loss > 0 else (float("inf") if gross_profit > 0 else 1.0)

        # Daily returns from equity curve (bars every 300 s → 288 bars/day)
        bars_per_day = 288
        daily_returns: list[float] = []
        for i in range(bars_per_day, len(equity_curve), bars_per_day):
            prev = equity_curve[i - bars_per_day]
            curr = equity_curve[i]
            if prev > 0:
                daily_returns.append((curr - prev) / prev)

        sharpe = _compute_sharpe(daily_returns)
        mdd = _compute_max_drawdown(equity_curve)

        exit_reasons: dict[str, int] = {}
        for t in trades:
            exit_reasons[t.exit_reason] = exit_reasons.get(t.exit_reason, 0) + 1

        avg_latency = (
            sum(t.latency_ms for t in trades) / len(trades) if trades else cfg.latency_ms
        )

        return BacktestReport(
            config=asdict(cfg),
            dataset_id=cfg.dataset_id,
            candle_count=candle_count,
            trade_count=len(trades),
            win_count=len(wins),
            loss_count=len(losses),
            gross_pnl_usd=round(gross_pnl, 4),
            total_slippage_usd=round(total_slip, 4),
            total_gas_usd=round(total_gas, 4),
            net_pnl_usd=round(net_pnl, 4),
            initial_usd=cfg.initial_usd,
            final_usd=round(final_equity, 4),
            total_return_pct=round((final_equity - cfg.initial_usd) / cfg.initial_usd * 100, 4),
            annualised_sharpe=round(sharpe, 4),
            max_drawdown_pct=round(mdd * 100, 4),
            win_rate_pct=round(len(wins) / max(len(trades), 1) * 100, 4),
            profit_factor=round(profit_factor, 4),
            avg_latency_ms=round(avg_latency, 2),
            trades=[t.to_dict() for t in trades],
            equity_curve=[round(v, 4) for v in equity_curve],
            exit_reasons=exit_reasons,
        )

    def _empty_report(self) -> BacktestReport:
        return BacktestReport(
            config=asdict(self._cfg),
            dataset_id=self._cfg.dataset_id,
            initial_usd=self._cfg.initial_usd,
            final_usd=self._cfg.initial_usd,
            equity_curve=[self._cfg.initial_usd],
        )


# ---------------------------------------------------------------------------
# Metric helpers (standalone, testable)
# ---------------------------------------------------------------------------


def _compute_sharpe(daily_returns: list[float], risk_free: float = 0.0) -> float:
    if len(daily_returns) < 2:
        return 0.0
    n = len(daily_returns)
    mean_r = sum(daily_returns) / n
    variance = sum((r - mean_r) ** 2 for r in daily_returns) / (n - 1)
    std_r = math.sqrt(variance) if variance > 0 else 0.0
    if std_r == 0.0:
        return 0.0
    return (mean_r - risk_free) / std_r * math.sqrt(252)


def _compute_max_drawdown(equity_curve: list[float]) -> float:
    if not equity_curve:
        return 0.0
    peak = equity_curve[0]
    max_dd = 0.0
    for v in equity_curve:
        if v > peak:
            peak = v
        dd = (peak - v) / peak if peak > 0 else 0.0
        if dd > max_dd:
            max_dd = dd
    return max_dd
