"""
Phase 14 — Real Order Flow Imbalance (OFI)

Kaynak: Binance spot order book REST (public, auth gerekmez)
Güncelleme: her alpha_engine cycle (60s)
Mantık: bid depth >> ask depth → alım baskısı → bullish
        ask depth >> bid depth → satım baskısı → bearish

IC beklentisi: 0.04-0.08 (en hızlı sinyal)

Mevcut kod placeholder kullanıyordu.
Bu modül gerçek bid/ask depth hesaplar.
"""

from __future__ import annotations

import logging
import time
from collections import deque
from dataclasses import dataclass

import aiohttp

log = logging.getLogger(__name__)

BINANCE_DEPTH_URL = "https://api.binance.com/api/v3/depth"
SYMBOL = "ETHUSDT"
DEPTH_LEVELS = 10              # top 10 bid/ask level
CACHE_TTL_SECONDS = 30         # 30s cache — her cycle'da çok sık çağrılmasın
HISTORY_WINDOW = 60            # 60 gözlem rolling


@dataclass
class OFISnapshot:
    timestamp: float
    ofi_raw: float             # (bid_depth - ask_depth) / total_depth [-1, +1]
    ofi_weighted: float        # fiyata yakın seviyelere ağırlık verilmiş
    ofi_momentum: float        # son 5 OFI ortalaması — trend
    signal: float              # [0, 1] — 0=güçlü bearish, 0.5=nötr, 1=güçlü bullish
    bid_depth_usd: float
    ask_depth_usd: float
    spread_bps: float


class OrderFlowSignal:
    """
    Real-time OFI hesaplama.
    Singleton — alpha_engine her cycle'da query eder.
    """

    _instance: OrderFlowSignal | None = None

    def __init__(self) -> None:
        self._history: deque[float] = deque(maxlen=HISTORY_WINDOW)
        self._last_snapshot: OFISnapshot | None = None
        self._last_fetch: float = 0.0

    @classmethod
    def get(cls) -> OrderFlowSignal:
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def current(self) -> OFISnapshot | None:
        age = time.time() - self._last_fetch
        if age > CACHE_TTL_SECONDS:
            await self._refresh()
        return self._last_snapshot

    def current_sync(self) -> OFISnapshot | None:
        return self._last_snapshot

    # ------------------------------------------------------------------
    # Fetch + compute
    # ------------------------------------------------------------------

    async def _refresh(self) -> None:
        try:
            snap = await self._fetch_and_compute()
            if snap is not None:
                self._history.append(snap.ofi_raw)
                # momentum: son 5 OFI ortalaması
                if len(self._history) >= 5:
                    snap = OFISnapshot(
                        timestamp=snap.timestamp,
                        ofi_raw=snap.ofi_raw,
                        ofi_weighted=snap.ofi_weighted,
                        ofi_momentum=sum(list(self._history)[-5:]) / 5,
                        signal=snap.signal,
                        bid_depth_usd=snap.bid_depth_usd,
                        ask_depth_usd=snap.ask_depth_usd,
                        spread_bps=snap.spread_bps,
                    )
                self._last_snapshot = snap
                self._last_fetch = time.time()
                log.debug(
                    "OFI updated: raw=%.3f weighted=%.3f signal=%.3f",
                    snap.ofi_raw, snap.ofi_weighted, snap.signal,
                )
        except Exception as exc:
            log.warning("OFI fetch failed (non-critical): %s", exc)

    async def _fetch_and_compute(self) -> OFISnapshot | None:
        params = {"symbol": SYMBOL, "limit": DEPTH_LEVELS}
        timeout = aiohttp.ClientTimeout(total=5)

        async with aiohttp.ClientSession(timeout=timeout) as session, session.get(BINANCE_DEPTH_URL, params=params) as resp:
            if resp.status != 200:
                return None
            data = await resp.json()

        bids = data.get("bids", [])  # [[price, qty], ...]
        asks = data.get("asks", [])

        if not bids or not asks:
            return None

        best_bid = float(bids[0][0])
        best_ask = float(asks[0][0])
        mid_price = (best_bid + best_ask) / 2
        spread_bps = (best_ask - best_bid) / mid_price * 10000

        # Depth USD hesapla — fiyata yakın seviyelere daha fazla ağırlık
        bid_depth = 0.0
        bid_depth_weighted = 0.0
        for i, (price_s, qty_s) in enumerate(bids[:DEPTH_LEVELS]):
            price, qty = float(price_s), float(qty_s)
            usd = price * qty
            weight = 1.0 / (i + 1)            # 1, 0.5, 0.33, 0.25...
            bid_depth += usd
            bid_depth_weighted += usd * weight

        ask_depth = 0.0
        ask_depth_weighted = 0.0
        for i, (price_s, qty_s) in enumerate(asks[:DEPTH_LEVELS]):
            price, qty = float(price_s), float(qty_s)
            usd = price * qty
            weight = 1.0 / (i + 1)
            ask_depth += usd
            ask_depth_weighted += usd * weight

        total = bid_depth + ask_depth
        total_w = bid_depth_weighted + ask_depth_weighted

        if total < 1e-8:
            return None

        ofi_raw = (bid_depth - ask_depth) / total                     # [-1, +1]
        ofi_weighted = (bid_depth_weighted - ask_depth_weighted) / max(total_w, 1e-8)

        # Signal: ofi > 0 → bullish, ofi < 0 → bearish
        signal = (ofi_weighted + 1.0) / 2.0                           # map [-1,1] → [0,1]
        signal = max(0.0, min(1.0, signal))

        return OFISnapshot(
            timestamp=time.time(),
            ofi_raw=round(ofi_raw, 4),
            ofi_weighted=round(ofi_weighted, 4),
            ofi_momentum=0.0,              # history'den doldurulur
            signal=round(signal, 4),
            bid_depth_usd=round(bid_depth, 2),
            ask_depth_usd=round(ask_depth, 2),
            spread_bps=round(spread_bps, 2),
        )


def get_ofi_signal() -> OrderFlowSignal:
    return OrderFlowSignal.get()
