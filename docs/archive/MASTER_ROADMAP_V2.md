# Master Roadmap V2

This file is the continuation of MASTER_ROADMAP.md after all 10 original phases
were completed and deployed on 2026-04-08.

V1 built the platform. V2 makes it earn its edge.

If multiple AI agents, operators, or future maintainers work on this project,
they must treat this file as the single source of truth for V2 direction.

Do not create alternate roadmap files.
Do not skip phases.
Do not optimize for novelty over measurable progress.

---

## 1. Program Definition

### 1.1 V1 Completion State (2026-04-08)

At V2 start, the system has:

- 10 phases complete and deployed to Azure
- `robust_paper` mode active, 77+ paper trades
- Risk OS, Execution OS, Promotion OS, Learning OS all live
- XGBoost and LightGBM running statistical fallbacks (no trained weights)
- LSTM and Transformer loaded from 2026-03-27 training run
- IC = NO_DATA (signal edge unproven)
- Shadow live: 0 comparisons (tiny_live gate closed)
- PromotionOS: 0 registered experiments
- LearningOS: 0 completed cycles
- Single asset: ETH/USDC only

### 1.2 V2 North Star

V1 built a durable platform. V2 answers the harder question:

**Does this system have real, measurable, promotable edge?**

V2 is complete when:

- ML models are trained, validated, and auto-refreshed
- Signal IC is measured and positive over 500+ trades
- At least one strategy has passed shadow_live gate
- Tiny_live is active with real capital under $250
- Multi-asset operation is live with correlation-aware sizing
- Alternative data sources are integrated and IC-attributed

### 1.3 What "Simons Direction" Means in V2

In V2, moving toward a Jim Simons-style system means:

- models that are actually trained, not falling back to hand-crafted weights
- IC measured on real decisions, not assumed from architecture
- signals that are retired when they stop working
- promotion that happens through evidence, not optimism
- diversity of uncorrelated alpha sources, not a single ETH signal

---

## 2. Non-Negotiables (inherited + extended)

All V1 non-negotiables carry forward unchanged.

Additional V2 rules:

### 2.1 Training Rule

No model inference result counts as evidence until the model has been trained
on at least 200 labeled samples from this system's feature pipeline.

Statistical fallbacks are acceptable during warm-up only. A phase cannot close
with a primary model in fallback mode.

### 2.2 IC Rule

No signal is declared "adding value" without a measured IC over at least 500
observations. Positive win rate alone is not sufficient.

### 2.3 Capital Rule

No real capital is deployed before shadow_live gate is passed and PromotionOS
has at least one experiment at SHADOW or higher stage.

### 2.4 Diversity Rule

No single asset or signal source may account for more than 60% of portfolio
risk at scaled_live stage.

---

## 3. Phase Dependency Map

```
Phase 11 - Model Training Pipeline
    ↓
Phase 12 - Signal Validation & IC Measurement
    ↓
Phase 13 - Live Promotion Path (shadow → tiny_live)
    ↓
Phase 14 - Multi-Asset Expansion
    ↓
Phase 15 - Alternative Data Layer
    ↓
Phase 16 - Tiny Live & First Real Capital
```

Phases 14 and 15 may overlap after Phase 13 is complete.

---

## 4. Phase 11 — Model Training Pipeline

### 4.1 Goal

Train XGBoost and LightGBM on real accumulated data and establish an
automated retraining loop that keeps all four models current.

### 4.2 Why It Matters

XGBoost and LightGBM are currently running hand-crafted statistical fallbacks.
The ensemble confidence numbers are partially meaningless because two of the
four models are not using learned weights. All downstream IC and promotion
decisions are built on sand until this is fixed.

### 4.3 Scope

- extract labeled training dataset from paper_trades.db and quant_analytics.db
- define feature-label schema: feature vector at signal time → realized return
  at exit
- train XGBoost and LightGBM with walk-forward cross-validation
- serialize trained models to ml_models/ following existing naming convention
- validate: compare fallback-mode vs trained-mode predictions on held-out data
- implement automated weekly retraining script
- integrate retraining trigger into LearningOS drift cycle

### 4.4 Primary File Zones

- `scripts/train_models.py` (new)
- `wallet_manager/strategies/alpha_engine.py` (load path, validation)
- `wallet_manager/learning_os.py` (retraining trigger)
- `ml_models/xgb_alpha_model.json` (output artifact)
- `ml_models/lgbm_alpha_model.txt` (output artifact)

### 4.5 KPIs

- XGBoost and LightGBM loaded from trained weights at startup (no fallback log)
- Trained model AUC > 0.52 on held-out walk-forward fold
- Model training reproducible from explicit dataset version and script
- Retraining completes without manual intervention weekly

### 4.6 Exit Gate

Phase 11 is complete only when:

1. Both XGBoost and LightGBM start without fallback warning in Docker logs
2. A training report exists in `docs/phase11_model_training.md` with
   dataset version, validation metrics, and walk-forward fold results
3. Automated retraining script is documented and tested

### 4.7 Anti-Goals

Do not:

- train on paper trade labels alone without walk-forward validation
- use future data in training features (lookahead bias)
- declare models trained because they load without error (validate predictions)
- retrain more than weekly without evidence that higher frequency helps

---

## 5. Phase 12 — Signal Validation & IC Measurement

### 5.1 Goal

Prove or disprove that current signals have measurable edge by computing
Information Coefficient over 500+ real paper trade decisions.

### 5.2 Why It Matters

The signal scorecard shows `decay_status: NO_DATA` and `pending_ic_observations: 32`.
Win rate of 100% across 2 model cycles means nothing with this sample size.
IC is the foundational quality measure. Without it, all confidence numbers
are uncalibrated.

### 5.3 Scope

- accumulate 500+ closed paper trades (bot runs continuously)
- compute IC (Spearman rank correlation of predicted direction vs realized return)
- compute IR (IC / std(IC) over rolling 50-trade windows)
- compute IC decay curve: IC at 1-bar, 3-bar, 6-bar, 12-bar horizons
- identify which features contribute most to IC via SHAP or permutation importance
- retire or downweight signals with IC < 0.02 over 200+ observations
- document results in signal scorecard

### 5.4 Primary File Zones

- `wallet_manager/signal_intelligence.py` (IC computation)
- `wallet_manager/strategies/paper_engine.py` (decision journal, exit logging)
- `scripts/ic_report.py` (new — offline IC analysis script)
- `docs/phase12_signal_validation.md` (new)

### 5.5 KPIs

- 500+ closed paper trades in paper_trades.db
- IC computed and non-null for at least 2 signals
- IC decay curve available for primary signal
- Signal scorecard `decay_status` no longer NO_DATA
- At least one signal retirement or downweight decision made with evidence

### 5.6 Exit Gate

Phase 12 is complete only when:

1. `GET /api/signal_scorecard` returns non-null IC values
2. IC over 500 observations is documented in `docs/phase12_signal_validation.md`
3. A clear "signals adding value" vs "signals under review" split exists

### 5.7 Anti-Goals

Do not:

- confuse high win rate with high IC
- compute IC on paper trades without confirming exits are cleanly recorded
- retire signals based on fewer than 200 observations

---

## 6. Phase 13 — Live Promotion Path

### 6.1 Goal

Advance from paper-only operation to shadow_live, validate execution
assumptions, then open the gate to tiny_live through PromotionOS.

### 6.2 Why It Matters

Shadow live has 0 comparisons and needs 50 before the readiness gate passes.
PromotionOS has 0 experiments registered. LearningOS has 0 completed cycles.
The entire promotion infrastructure built in V1 Phases 7–10 has never been
used operationally.

### 6.3 Scope

- register first experiment in PromotionOS (strategy: robust_paper, stage: PAPER)
- trigger first LearningOS drift cycle manually, then configure scheduled run
- enable shadow_live mode: real price quotes, simulated fills
- accumulate 50 shadow comparisons against paper assumptions
- evaluate PromotionOS gate thresholds using accumulated evidence
- promote experiment from PAPER → SHADOW using PromotionOS if gate passes
- document shadow vs paper mismatch findings

### 6.4 Primary File Zones

- `wallet_manager/promotion_os.py` (experiment registration, gate evaluation)
- `wallet_manager/learning_os.py` (drift cycle scheduling)
- `wallet_manager/strategies/shadow_live.py` (shadow comparison)
- `wallet_manager/metrics_server.py` (API validation)

### 6.5 KPIs

- PromotionOS: ≥1 experiment registered and at SHADOW stage or higher
- Shadow live: ≥50 comparisons recorded, mean_deviation_pct < 0.1%
- LearningOS: ≥1 completed drift cycle, results in `GET /api/learning_os`
- No manual capital deployment before gates pass

### 6.6 Exit Gate

Phase 13 is complete only when:

1. Shadow live readiness gate passes (`ready: true` in execution_os API)
2. At least one PromotionOS experiment is at SHADOW stage with evidence
3. LearningOS has at least one completed cycle with documented findings
4. `docs/phase13_promotion_path.md` exists with gate results

### 6.7 Anti-Goals

Do not:

- skip shadow_live and go directly to tiny_live
- lower PromotionOS gate thresholds to force a pass
- treat LearningOS "no drift" as a completed cycle without actual computation

---

## 7. Phase 14 — Multi-Asset Expansion

### 7.1 Goal

Extend from single-asset (ETH) to a 3-asset minimum portfolio with
correlation-aware position sizing.

### 7.2 Why It Matters

A single-asset bot is entirely exposed to ETH regime. Simons-style systems
derive much of their edge from operating across many uncorrelated instruments.
Adding even 2-3 assets dramatically improves diversification and IC stability.

### 7.3 Scope

- add BTC/USDC and SOL/USDC as additional instruments
- extend alpha_engine to operate independently per asset
- extend paper_engine to manage multi-asset paper portfolio
- implement correlation matrix tracking (rolling 30-day)
- implement correlation-aware position sizing: reduce size when correlation > 0.7
- extend signal_scorecard API to report per-asset IC
- extend risk_state API to report portfolio-level exposure

### 7.4 Primary File Zones

- `wallet_manager/strategies/alpha_engine.py` (per-asset instances)
- `wallet_manager/strategies/paper_engine.py` (multi-asset ledger)
- `wallet_manager/strategies/deep_kelly_risk.py` (correlation-aware sizing)
- `wallet_manager/portfolio_manager.py` (multi-asset allocation)

### 7.5 KPIs

- 3 assets running in paper mode simultaneously
- Correlation matrix updated each cycle
- Position sizing reduced automatically when inter-asset correlation > 0.7
- Per-asset IC tracked independently in signal scorecard

### 7.6 Exit Gate

Phase 14 is complete only when:

1. 3 assets have ≥100 paper trades each
2. Per-asset IC is visible in signal scorecard
3. Correlation-aware sizing is active and documented
4. `docs/phase14_multi_asset.md` exists

### 7.7 Anti-Goals

Do not:

- add assets without per-asset IC tracking
- apply single-asset Kelly sizing to a multi-asset portfolio without correlation adjustment
- add more than 5 assets before IC is proven on 3

---

## 8. Phase 15 — Alternative Data Layer

### 8.1 Goal

Extend the feature set with data sources that go beyond OHLCV price and
volume to capture structural market signals.

### 8.2 Why It Matters

Current features are entirely derived from price and volume. This means
the system is competing on the same features as every other momentum model.
Alternative data provides signals that are structurally earlier or orthogonal
to price action.

### 8.3 Scope

Priority 1 (implement first):
- Perpetual funding rates: positive funding = crowded longs = mean reversion bias
- On-chain exchange net flows: large inflows = potential sell pressure

Priority 2 (implement second):
- Real-time order book imbalance: bid/ask depth ratio at top 5 levels
- Gas price as market stress proxy: high gas = high activity = regime signal

For each new data source:
- define ingestion contract (source, frequency, latency)
- add to feature vector with explicit feature index
- measure IC contribution independently before including in ensemble
- document in signal contract

### 8.4 Primary File Zones

- `wallet_manager/data/funding_rates.py` (new)
- `wallet_manager/data/onchain_flows.py` (new)
- `wallet_manager/data/order_book.py` (new)
- `wallet_manager/strategies/alpha_engine.py` (feature vector extension)
- `wallet_manager/tick_collector.py` (ingestion scheduling)

### 8.5 KPIs

- At least 2 alternative data sources integrated and IC-attributed
- Each new feature has a documented IC contribution (positive or negative)
- Feature vector extension does not break existing model inference
- No new data source added to ensemble before standalone IC > 0.02

### 8.6 Exit Gate

Phase 15 is complete only when:

1. ≥2 alternative data sources have documented IC contributions
2. At least one source shows IC improvement over price-only baseline
3. `docs/phase15_alternative_data.md` exists with per-source IC tables

### 8.7 Anti-Goals

Do not:

- add data sources because they sound sophisticated
- include in ensemble before IC is measured
- ingest data without a defined freshness/staleness policy

---

## 9. Phase 16 — Tiny Live & First Real Capital

### 9.1 Goal

Deploy first real capital under full PromotionOS control following the
shadow_live gate and evidence-backed promotion decision.

### 9.2 Why It Matters

Paper mode has no real friction. Live execution has gas, slippage, timing,
and liquidity realities that paper cannot fully simulate. Tiny_live is the
controlled environment for learning these gaps cheaply before scaling.

### 9.3 Scope

- PromotionOS gate review: confirm SHADOW stage experiment has enough evidence
- promote experiment from SHADOW → TINY_LIVE via PromotionOS
- enable live_trading_enabled with live_max_total_capital_usd = 250.0
- run live execution in tiny_live mode for ≥4 weeks
- compare realized vs paper/shadow P&L and execution quality
- document all deviations (slippage, gas, timing) vs paper assumptions
- define explicit scale-up threshold before advancing to SCALED_LIVE

### 9.4 Primary File Zones

- `wallet_manager/promotion_os.py` (TINY_LIVE stage)
- `wallet_manager/config.py` (live_trading_enabled, live_max_total_capital_usd)
- `wallet_manager/strategies/shadow_live.py` (live comparison)
- `wallet_manager/execution_os.py` (real TCA records)

### 9.5 KPIs

- PromotionOS experiment at TINY_LIVE stage with documented gate passage
- ≥4 weeks of live operation with zero kill-switch triggers
- Realized Sharpe > 0.5 over live period
- Slippage deviation vs paper < 20% on average
- Drawdown never exceeds 3% of tiny_live capital

### 9.6 Exit Gate

Phase 16 is complete only when:

1. 4 weeks of live data exists with documented P&L
2. PromotionOS has an auditable promotion decision from SHADOW → TINY_LIVE
3. Execution OS TCA records show calibrated slippage assumptions
4. `docs/phase16_tiny_live.md` exists with full period analysis

### 9.7 Anti-Goals

Do not:

- increase capital beyond $250 before 4-week live gate is reviewed
- disable the live_guard during tiny_live
- treat tiny_live losses as bugs without first ruling out paper assumption errors

---

## 10. Global V2 Scorecard

Judge progress continuously against these dimensions.

| Dimension | V1 Exit State | V2 Target |
|---|---|---|
| Model quality | 2 of 4 in fallback | All 4 trained, auto-refreshed |
| Signal IC | NO_DATA | IC > 0.02 over 500+ obs |
| Shadow live | 0 comparisons | ≥50, deviation < 0.1% |
| Promotion stage | 0 experiments | ≥1 at TINY_LIVE |
| Asset count | 1 (ETH) | ≥3 with per-asset IC |
| Alt data sources | 0 | ≥2 with measured IC |
| Real capital deployed | $0 | $250, 4-week track record |

---

## 11. Definition of V2 Strategic Success

V2 is succeeding if, at its end, the system can demonstrate:

- models that are trained and auto-refreshed without manual intervention
- signals with measured IC proving real edge, not assumed edge
- a completed promotion from paper → shadow → tiny_live with documented evidence
- a diversified multi-asset portfolio with correlation-aware risk management
- at least one alternative data source adding measurable IC
- a 4-week live track record that validates paper-mode assumptions

---

## 12. Permanent V2 Anti-Patterns

Do not:

- add more models before proving IC on existing models
- skip the shadow_live gate to save time
- treat IC on 100 trades as sufficient evidence for promotion
- add assets without per-asset IC tracking infrastructure
- add alternative data to the ensemble before standalone IC measurement
- increase live capital beyond $250 without PromotionOS gate review
- retrain models intraday without evidence that it improves IC
