"""Trade Quality Gate — net-cost-aware entry filter.

The directional signal (``should_enter_long``/``should_enter_short``) decides
*which way* to trade. This gate decides *whether the trade is worth taking* —
the missing piece that prevents over-trading on tiny edges that transaction
costs (gas + DEX fee + slippage) would erase.

A trade is allowed only when ALL hold:

1. **Conviction** — signal confidence >= ``min_conviction``.
2. **Net edge vs cost** — expected move (bps) >= ``net_edge_multiplier`` *
   estimated round-trip cost (bps).
3. **Cooldown** — at least ``cooldown_seconds`` since the last fired trade.
4. **Daily cap** — fewer than ``max_trades_per_day`` trades so far today (UTC).

Expected move is derived from the robust alpha:
``expected_edge_bps = abs(robust_alpha) * alpha_to_bps_scale``. The scale maps
a full-strength signal to an expected basis-point move and is meant to be
calibrated from backtest results.

All thresholds are configurable (see :class:`GateConfig` /
``GateConfig.from_settings``). Defaults are the "Balanced" profile.
"""
from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import UTC, datetime


@dataclass(frozen=True)
class GateConfig:
    """Tunable thresholds for the Trade Quality Gate (Balanced defaults)."""

    enabled: bool = True
    min_conviction: float = 0.55
    net_edge_multiplier: float = 2.0
    alpha_to_bps_scale: float = 50.0
    cooldown_seconds: float = 1800.0
    max_trades_per_day: int = 6

    @classmethod
    def from_settings(cls, settings: object) -> GateConfig:
        """Build a config from a Settings-like object, falling back to defaults."""
        return cls(
            enabled=bool(getattr(settings, "tqg_enabled", True)),
            min_conviction=float(getattr(settings, "tqg_min_conviction", 0.55)),
            net_edge_multiplier=float(getattr(settings, "tqg_net_edge_multiplier", 2.0)),
            alpha_to_bps_scale=float(getattr(settings, "tqg_alpha_to_bps_scale", 50.0)),
            cooldown_seconds=float(getattr(settings, "tqg_cooldown_seconds", 1800.0)),
            max_trades_per_day=int(getattr(settings, "tqg_max_trades_per_day", 6)),
        )


@dataclass(frozen=True)
class GateDecision:
    """Outcome of a gate evaluation.

    Attributes:
        allow: True if the trade may proceed.
        reason: One of PASS / DISABLED / LOW_CONVICTION / COOLDOWN /
            DAILY_CAP / EDGE_BELOW_COST.
        expected_edge_bps: Estimated move in basis points.
        cost_bps: Estimated round-trip cost in basis points.
        required_edge_bps: net_edge_multiplier * cost_bps.
    """

    allow: bool
    reason: str
    expected_edge_bps: float
    cost_bps: float
    required_edge_bps: float


class TradeQualityGate:
    """Stateful gate tracking cooldown and per-day trade count."""

    def __init__(self, config: GateConfig | None = None) -> None:
        self._cfg = config or GateConfig()
        self._last_trade_ts: float = 0.0
        self._day_key: str = ""
        self._trades_today: int = 0

    @property
    def config(self) -> GateConfig:
        return self._cfg

    @staticmethod
    def _day_of(now: float) -> str:
        return datetime.fromtimestamp(now, tz=UTC).strftime("%Y-%m-%d")

    def _trades_today_count(self, now: float) -> int:
        return self._trades_today if self._day_of(now) == self._day_key else 0

    def evaluate(
        self,
        *,
        robust_alpha: float,
        confidence: float,
        cost_bps: float,
        now: float | None = None,
    ) -> GateDecision:
        """Decide whether a directionally-valid trade is worth taking."""
        now = time.time() if now is None else now
        expected_edge_bps = abs(robust_alpha) * self._cfg.alpha_to_bps_scale
        required = self._cfg.net_edge_multiplier * max(cost_bps, 0.0)

        def decision(allow: bool, reason: str) -> GateDecision:
            return GateDecision(allow, reason, expected_edge_bps, cost_bps, required)

        if not self._cfg.enabled:
            return decision(True, "DISABLED")
        if confidence < self._cfg.min_conviction:
            return decision(False, "LOW_CONVICTION")
        if self._last_trade_ts > 0 and (now - self._last_trade_ts) < self._cfg.cooldown_seconds:
            return decision(False, "COOLDOWN")
        if self._trades_today_count(now) >= self._cfg.max_trades_per_day:
            return decision(False, "DAILY_CAP")
        if expected_edge_bps < required:
            return decision(False, "EDGE_BELOW_COST")
        return decision(True, "PASS")

    def record_trade(self, now: float | None = None) -> None:
        """Register that a trade fired — updates cooldown and daily counters."""
        now = time.time() if now is None else now
        day = self._day_of(now)
        if day != self._day_key:
            self._day_key = day
            self._trades_today = 0
        self._trades_today += 1
        self._last_trade_ts = now
