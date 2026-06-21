"""
wallet_manager/data
===================
Phase 4 — Data Layer

Provides quant-grade data infrastructure:

- DatasetManifest / DatasetRegistry  — versioned, named dataset records
- DataSlice                          — replayable, labeled data windows
- FeatureRegistry / FeatureSpec      — feature contracts and persistence
- DataQualityMonitor / DataQualitySLA — governance and SLO enforcement

Phase 14 — On-Chain Intelligence:
- FundingRateSignal    — Binance USDM funding rate (crowded long/short detection)
- OrderFlowSignal      — real-time OFI from Binance spot order book
- OnChainFlowSignal    — exchange net flow (CryptoCompare; graceful degradation)
"""
from wallet_manager.data.data_quality import DataQualityMonitor, DataQualitySLA
from wallet_manager.data.data_slice import DataSlice, SliceRegistry
from wallet_manager.data.dataset_manifest import DatasetManifest, DatasetRegistry
from wallet_manager.data.feature_registry import FeatureRegistry, FeatureSpec, FeatureStore
from wallet_manager.data.funding_rates import FundingRateSignal, get_funding_signal
from wallet_manager.data.onchain_flows import OnChainFlowSignal, get_onchain_flow_signal
from wallet_manager.data.order_book import OrderFlowSignal, get_ofi_signal

__all__ = [
    "DataQualityMonitor",
    "DataQualitySLA",
    "DataSlice",
    "DatasetManifest",
    "DatasetRegistry",
    "FeatureRegistry",
    "FeatureSpec",
    "FeatureStore",
    # Phase 14
    "FundingRateSignal",
    "OnChainFlowSignal",
    "OrderFlowSignal",
    "SliceRegistry",
    "get_funding_signal",
    "get_ofi_signal",
    "get_onchain_flow_signal",
]
