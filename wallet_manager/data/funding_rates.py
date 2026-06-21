"""
Phase 14 — Funding Rate Signal

Kaynak: Binance USDM Futures public API (auth gerekmez)
Güncelleme: 8 saatte bir (Binance settlement: 00:00, 08:00, 16:00 UTC)
Mantık: yüksek pozitif funding = crowded long = mean reversion bias
        düşük/negatif funding = crowded short = squeeze riski

IC beklentisi: 0.04-0.07
"""

from __future__ import annotations

import asyncio
import logging
import statistics
import time
from collections import deque
from dataclasses import dataclass

import aiohttp

log = logging.getLogger(__name__)

BINANCE_FUNDING_URL = "https://fapi.binance.com/fapi/v1/fundingRate"
SYMBOL = "ETHUSDT"
CACHE_TTL_SECONDS = 300        # 5 dakika cache — API rate limit önlemi
HISTORY_WINDOW = 90            # 90 gözlem (~30 gün, 8h settlement)
ZSCORE_WINDOW = 30             # 30 gözlem zscore için


@dataclass
class FundingRateSnapshot:
    timestamp: float
    rate: float                # ham oran (örn. 0.0001 = 0.01%)
    rate_annualized: float     # yıllık baz (3 settlement/gün × 365)
    zscore_30: float           # 30-gözlem z-score
    signal: float              # [0, 1] — 0=güçlü bearish, 0.5=nötr, 1=güçlü bullish
    regime: str                # "crowded_long" | "crowded_short" | "neutral"


class FundingRateSignal:
    """
    Singleton — alpha_engine her cycle'da query eder.
    Arka planda 5 dakikada bir Binance'den günceller.
    """

    _instance: FundingRateSignal | None = None

    def __init__(self) -> None:
        self._history: deque[float] = deque(maxlen=HISTORY_WINDOW)
        self._last_snapshot: FundingRateSnapshot | None = None
        self._last_fetch: float = 0.0
        self._lock = asyncio.Lock()
        self._fetch_task: asyncio.Task | None = None

    @classmethod
    def get(cls) -> FundingRateSignal:
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def current(self) -> FundingRateSnapshot | None:
        """Cache'den döner. Bayatsa arka planda günceller."""
        age = time.time() - self._last_fetch
        if age > CACHE_TTL_SECONDS:
            await self._refresh()
        return self._last_snapshot

    def current_sync(self) -> FundingRateSnapshot | None:
        """Sync wrapper — alpha_engine'den çağrılabilir."""
        return self._last_snapshot

    # ------------------------------------------------------------------
    # Fetch
    # ------------------------------------------------------------------

    async def _refresh(self) -> None:
        async with self._lock:
            # Double-check after lock
            if time.time() - self._last_fetch < CACHE_TTL_SECONDS:
                return
            try:
                rate = await self._fetch_latest()
                if rate is not None:
                    self._history.append(rate)
                    self._last_snapshot = self._compute_snapshot(rate)
                    self._last_fetch = time.time()
                    log.debug(
                        "FundingRate updated: rate=%.6f signal=%.3f regime=%s",
                        rate,
                        self._last_snapshot.signal,
                        self._last_snapshot.regime,
                    )
            except Exception as exc:
                log.warning("FundingRate fetch failed (non-critical): %s", exc)

    async def _fetch_latest(self) -> float | None:
        """Binance USDM son funding rate."""
        params = {"symbol": SYMBOL, "limit": 1}
        timeout = aiohttp.ClientTimeout(total=5)
        async with aiohttp.ClientSession(timeout=timeout) as session, session.get(BINANCE_FUNDING_URL, params=params) as resp:
            if resp.status != 200:
                log.warning("Binance funding API status=%d", resp.status)
                return None
            data = await resp.json()
            if not data:
                return None
            return float(data[0]["fundingRate"])

    # ------------------------------------------------------------------
    # Signal computation
    # ------------------------------------------------------------------

    def _compute_snapshot(self, rate: float) -> FundingRateSnapshot:
        annualized = rate * 3 * 365  # 3 settlement/gün

        # Z-score
        if len(self._history) >= 5:
            window = list(self._history)[-ZSCORE_WINDOW:]
            mean = statistics.mean(window)
            std = statistics.stdev(window) if len(window) > 1 else 1e-8
            zscore = (rate - mean) / max(std, 1e-8)
        else:
            zscore = 0.0

        # Signal: yüksek pozitif funding → bearish (mean reversion)
        # Sigmoid: zscore -3..+3 → signal 1..0
        import math
        signal = 1.0 / (1.0 + math.exp(zscore * 1.5))  # inverse sigmoid
        signal = max(0.0, min(1.0, signal))

        # Regime
        if zscore > 1.5:
            regime = "crowded_long"    # funding yüksek → longs kalabalık → düşüş riski
        elif zscore < -1.5:
            regime = "crowded_short"   # funding negatif → shorts kalabalık → squeeze riski
        else:
            regime = "neutral"

        return FundingRateSnapshot(
            timestamp=time.time(),
            rate=rate,
            rate_annualized=annualized,
            zscore_30=round(zscore, 3),
            signal=round(signal, 4),
            regime=regime,
        )

    # ------------------------------------------------------------------
    # Background loop
    # ------------------------------------------------------------------

    async def start_background_refresh(self, interval: float = 300.0) -> None:
        """Orchestrator'dan başlatılır. 5 dakikada bir günceller."""
        log.info("FundingRateSignal background refresh started (interval=%.0fs)", interval)
        while True:
            try:
                await self._refresh()
            except Exception as exc:
                log.warning("FundingRate background error: %s", exc)
            await asyncio.sleep(interval)

    async def warmup(self) -> None:
        """Startup'ta çağrılır — ilk veriyi çeker."""
        try:
            params = {"symbol": SYMBOL, "limit": HISTORY_WINDOW}
            timeout = aiohttp.ClientTimeout(total=10)
            async with aiohttp.ClientSession(timeout=timeout) as session, session.get(BINANCE_FUNDING_URL, params=params) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    for item in data:
                        self._history.append(float(item["fundingRate"]))
                    if self._history:
                        self._last_snapshot = self._compute_snapshot(
                            self._history[-1]
                        )
                        self._last_fetch = time.time()
                        log.info(
                            "FundingRate warmup: %d records loaded, "
                            "current=%.6f signal=%.3f regime=%s",
                            len(self._history),
                            self._history[-1],
                            self._last_snapshot.signal,
                            self._last_snapshot.regime,
                        )
        except Exception as exc:
            log.warning("FundingRate warmup failed (non-critical): %s", exc)


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

def get_funding_signal() -> FundingRateSignal:
    return FundingRateSignal.get()
