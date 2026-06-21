#!/usr/bin/env python3
"""Quick smoke-test for all module imports."""
import importlib
import sys

modules = [
    'wallet_manager.config',
    'wallet_manager.exceptions',
    'wallet_manager.actions',
    'wallet_manager.portfolio_manager',
    'wallet_manager.scheduler',
    'wallet_manager.orchestrator',
    'wallet_manager.orchestrator_lifecycle',
    'wallet_manager.orchestrator_gas',
    'wallet_manager.orchestrator_status',
    'wallet_manager.task_factories',
    'wallet_manager.trade_journal',
    'wallet_manager.tick_collector',
    'wallet_manager.signal_intelligence',
    'wallet_manager.signal_discovery',
    'wallet_manager.market_intelligence',
    'wallet_manager.risk_committee',
    'wallet_manager.risk_intelligence',
    'wallet_manager.risk_os',
    'wallet_manager.execution_os',
    'wallet_manager.promotion_os',
    'wallet_manager.learning_os',
    'wallet_manager.experiment_lab',
    'wallet_manager.continuous_learning',
    'wallet_manager.research_brain',
    'wallet_manager.reporting',
    'wallet_manager.alerting',
    'wallet_manager.metrics_server',
    'wallet_manager.ai_agents',
    'wallet_manager.env_loader',
    'wallet_manager.telegram_notifier',
    'wallet_manager.backtester',
    # strategies
    'wallet_manager.strategies.paper_engine',
    'wallet_manager.strategies.quantx_engine',
    'wallet_manager.strategies.robust_alpha',
    'wallet_manager.strategies.adaptive_ensemble',
    'wallet_manager.strategies.alpha_engine',
    'wallet_manager.strategies.bayesian_kelly',
    'wallet_manager.strategies.deep_kelly_risk',
    'wallet_manager.strategies.execution_quality',
    'wallet_manager.strategies.smart_order_router',
    'wallet_manager.strategies.shadow_live',
    'wallet_manager.strategies.model_registry',
    'wallet_manager.strategies.regime_filter',
    'wallet_manager.strategies.wf_validator',
    'wallet_manager.strategies.stochastic_stress_test',
    'wallet_manager.strategies.kelly_criterion',
    'wallet_manager.strategies.execution_logic',
    'wallet_manager.strategies.idle_sweep',
    'wallet_manager.strategies.flash_crash_detector',
    'wallet_manager.strategies.short_strategy',
    'wallet_manager.strategies.yield_strategy',
    'wallet_manager.strategies.airdrop_strategy',
    'wallet_manager.strategies.algo_strategy',
    'wallet_manager.strategies.liquidity_alpha',
    'wallet_manager.strategies.cross_asset',
    # network
    'wallet_manager.network.router',
    'wallet_manager.network.balance_provider',
    'wallet_manager.network.gas_monitor',
    'wallet_manager.network.session_factory',
    'wallet_manager.network.tx_broadcaster',
    'wallet_manager.network.tx_repair',
    # resilience
    'wallet_manager.resilience.analytics',
    'wallet_manager.resilience.circuit_breaker',
    'wallet_manager.resilience.retry',
    # security
    'wallet_manager.security.vault',
    'wallet_manager.security.vault_manager',
    'wallet_manager.security.logging_filter',
    'wallet_manager.security.telegram_manager',
    # data
    'wallet_manager.data.feature_registry',
    'wallet_manager.data.data_slice',
    'wallet_manager.data.dataset_manifest',
    'wallet_manager.data.data_quality',
    # core
    'wallet_manager.core.interfaces',
    'wallet_manager.core.manager',
    'wallet_manager.core.models',
    'wallet_manager.core.strategy',
]

ok = 0
failed = 0
for m in modules:
    try:
        importlib.import_module(m)
        ok += 1
        print(f'  OK: {m}')
    except Exception as e:
        failed += 1
        print(f'  FAIL: {m} -> {e}')

print(f'\n{ok}/{ok+failed} modules loaded successfully')
if failed > 0:
    sys.exit(1)
