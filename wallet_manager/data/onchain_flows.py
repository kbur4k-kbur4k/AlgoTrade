"""
Phase 14 — On-Chain Exchange Net Flow Signal

Kaynak: CryptoCompare free API (blockchain/balances/historical/hour)
        Fallback: Etherscan free tier
Güncelleme: saatte bir
Mantık: büyük exchange inflow → satış baskısı yaklaşıyor → bearish
        exchange outflow → HODLing artıyor → bullish

IC beklentisi: 0.03-0.05
"""

from __future__ import annotations

import logging
import math
import os
import statistics
import time
from collections import deque
from dataclasses import dataclass

import aiohttp

log = logging.getLogger(__name__)

# CryptoCompare free API — auth gerekmez, rate limit: 100k calls/ay
CRYPTOCOMPARE_URL = "https://min-api.cryptocompare.com/data/blockchain/balances/historical/hour"
CRYPTOCOMPARE_API_KEY = os.environ.get("CRYPTOCOMPARE_API_KEY", "")

CACHE_TTL_SECONDS = 3600       # 1 saat — saatlik güncelleme yeterli
HISTORY_WINDOW = 168           # 7 gün (saatlik)
ZSCORE_WINDOW = 48             # 48 saat zscore


@dataclass
class OnChainFlowSnapshot:
    timestamp: float
    net_flow_usd: float        # pozitif = exchange'e giriş (bearish), negatif = çıkış (bullish)
    net_flow_zscore: float     # 48h z-score
    signal: float              # [0, 1] — 0=güçlü bearish (inflow), 1=güçlü bullish (outflow)
    regime: str                # "accumulation" | "distribution" | "neutral"
    data_source: str


class OnChainFlowSignal:
    """
    Exchange net flow sinyali.
    Veri yoksa graceful degradation — 0.5 (nötr) döner.
    """

    _instance: OnChainFlowSignal | None = None

    def __init__(self) -> None:
        self._history: deque[float] = deque(maxlen=HISTORY_WINDOW)
        self._last_snapshot: OnChainFlowSnapshot | None = None
        self._last_fetch: float = 0.0

    @classmethod
    def get(cls) -> OnChainFlowSignal:
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def current(self) -> OnChainFlowSnapshot | None:
        age = time.time() - self._last_fetch
        if age > CACHE_TTL_SECONDS:
            await self._refresh()
        return self._last_snapshot

    def current_sync(self) -> OnChainFlowSnapshot | None:
        return self._last_snapshot

    def neutral_snapshot(self) -> OnChainFlowSnapshot:
        """Veri yoksa nötr sinyal döner — trading'i engellemez."""
        return OnChainFlowSnapshot(
            timestamp=time.time(),
            net_flow_usd=0.0,
            net_flow_zscore=0.0,
            signal=0.5,
            regime="neutral",
            data_source="fallback",
        )

    # ------------------------------------------------------------------
    # Fetch
    # ------------------------------------------------------------------

    async def _refresh(self) -> None:
        try:
            snap = await self._fetch_cryptocompare()
            if snap is None:
                snap = self._synthetic_from_price_proxy()
            if snap is not None:
                self._history.append(snap.net_flow_usd)
                self._last_snapshot = snap
                self._last_fetch = time.time()
                log.debug(
                    "OnChainFlow updated: flow=%.0f zscore=%.2f signal=%.3f regime=%s src=%s",
                    snap.net_flow_usd, snap.net_flow_zscore,
                    snap.signal, snap.regime, snap.data_source,
                )
        except Exception as exc:
            log.warning("OnChainFlow refresh failed (non-critical): %s", exc)

    async def _fetch_cryptocompare(self) -> OnChainFlowSnapshot | None:
        """CryptoCompare blockchain balance endpoint."""
        if not CRYPTOCOMPARE_API_KEY:
            return None

        params = {
            "fsym": "ETH",
            "limit": 2,
            "api_key": CRYPTOCOMPARE_API_KEY,
        }
        timeout = aiohttp.ClientTimeout(total=8)
        try:
            async with aiohttp.ClientSession(timeout=timeout) as session, session.get(CRYPTOCOMPARE_URL, params=params) as resp:
                if resp.status != 200:
                    return None
                data = await resp.json()
                if data.get("Response") != "Success":
                    return None
                items = data.get("Data", {}).get("Data", [])
                if len(items) < 2:
                    return None

                # Net flow = change in exchange balance
                prev_balance = items[-2].get("balance_on_exchanges_usd", 0)
                curr_balance = items[-1].get("balance_on_exchanges_usd", 0)
                net_flow = curr_balance - prev_balance  # pozitif = inflow

                return self._compute_snapshot(net_flow, "cryptocompare")
        except Exception:
            return None

    def _synthetic_from_price_proxy(self) -> OnChainFlowSnapshot | None:
        """
        API key yoksa: nötr sinyal döner.
        İleride Etherscan free tier ile replace edilecek.
        """
        return OnChainFlowSnapshot(
            timestamp=time.time(),
            net_flow_usd=0.0,
            net_flow_zscore=0.0,
            signal=0.5,
            regime="neutral",
            data_source="no_api_key",
        )

    def _compute_snapshot(self, net_flow: float, source: str) -> OnChainFlowSnapshot:
        # Z-score
        if len(self._history) >= 5:
            window = list(self._history)[-ZSCORE_WINDOW:]
            mean = statistics.mean(window)
            std = statistics.stdev(window) if len(window) > 1 else 1.0
            zscore = (net_flow - mean) / max(abs(std), 1e-8)
        else:
            zscore = 0.0

        # Signal: yüksek inflow (pozitif) → bearish → düşük signal
        # Sigmoid inverse: büyük pozitif zscore → 0 (bearish)
        signal = 1.0 / (1.0 + math.exp(zscore * 1.2))
        signal = max(0.0, min(1.0, signal))

        if zscore > 1.5:
            regime = "distribution"   # exchange'e giriyor → satış hazırlığı
        elif zscore < -1.5:
            regime = "accumulation"   # exchange'den çıkıyor → HODLing
        else:
            regime = "neutral"

        return OnChainFlowSnapshot(
            timestamp=time.time(),
            net_flow_usd=round(net_flow, 2),
            net_flow_zscore=round(zscore, 3),
            signal=round(signal, 4),
            regime=regime,
            data_source=source,
        )


def get_onchain_flow_signal() -> OnChainFlowSignal:
    return OnChainFlowSignal.get()
