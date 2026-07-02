# Azure Runtime

This file is the canonical operational handoff for Azure access and runtime truth.

## Current Azure Target

- VM name: `walletbot-vm`
- resource group: `walletbot-rg-westeurope`
- region: `West Europe`
- public IP: `51.124.156.116`
- SSH user: `azureuser`
- local SSH key path: `C:\Users\ASUS\.ssh\id_rsa`

## Primary Endpoints

- dashboard: `http://51.124.156.116:9090/`
- dashboard direct: `http://51.124.156.116:9090/dashboard`
- health: `http://51.124.156.116:9090/health`
- runtime API: `http://51.124.156.116:9090/api/runtime`
- research API: `http://51.124.156.116:9090/api/research`
- paper health: `http://51.124.156.116:9090/api/paper_health`
- signal scorecard: `http://51.124.156.116:9090/api/signal_scorecard`
- risk state: `http://51.124.156.116:9090/api/risk_state`
- execution os: `http://51.124.156.116:9090/api/execution_os`
- promotion os: `http://51.124.156.116:9090/api/promotion_os`
- learning os: `http://51.124.156.116:9090/api/learning_os`
- metrics: `http://51.124.156.116:9090/metrics`

## Canonical Access Commands

```powershell
ssh -i C:\Users\ASUS\.ssh\id_rsa azureuser@51.124.156.116
```

```powershell
ssh -i C:\Users\ASUS\.ssh\id_rsa azureuser@51.124.156.116 "cd ~/walletbot; sudo docker compose ps"
```

```powershell
ssh -i C:\Users\ASUS\.ssh\id_rsa azureuser@51.124.156.116 "cd ~/walletbot; sudo docker compose logs --tail 120 wallet_manager"
```

```powershell
curl.exe -s http://51.124.156.116:9090/health
curl.exe -s http://51.124.156.116:9090/api/runtime
curl.exe -s http://51.124.156.116:9090/api/research
curl.exe -s http://51.124.156.116:9090/api/paper_health
curl.exe -s http://51.124.156.116:9090/api/signal_scorecard
```

## Last Confirmed Runtime Truth

Confirmed on 2026-04-08 after rebuild/restart (ALL 10 phases deployed):

- health endpoint returned `ok`
- `/api/paper_health` is live
- `/api/signal_scorecard` is live
- `/api/risk_state` is live (Phase 7)
- `/api/execution_os` is live (Phase 8)
- `/api/promotion_os` is live (Phase 9)
- `/api/learning_os` is live (Phase 10)
- execution mode remains `robust_paper`
- live trading guard inactive
- container rebuilt and restarted on 2026-04-08 around 18:45 +03:00

## Last Confirmed Behavioral Findings

**Risk committee deploy status**

- Azure VM was still on the old paper thresholds before this session
- `wallet_manager/risk_committee.py` now contains:
  - `min_confidence=0.05`
  - `max_model_disagreement=0.5`

**Paper health snapshot after redeploy (2026-04-08)**

- `sample_starved=false`
- `total_decisions=1378`
- `executed_decisions=67`
- `trade_rate_pct=4.86`
- dominant skip reason: `RISK_BLOCKED:normal`
- `RISK_COMMITTEE:ModelDisagreement` still appears in history but is not dominant

**Signal scorecard status after redeploy**

- `/api/signal_scorecard` returns 200 OK
- current scorecard is structurally live even if signal/model histories are still warming up after restart

## Deployment Notes

This session uploaded and deployed:

- `wallet_manager/risk_committee.py`
- `wallet_manager/signal_intelligence.py`
- `wallet_manager/strategies/model_registry.py`
- `wallet_manager/metrics_server.py`

Remote backups created before overwrite:

- `wallet_manager/risk_committee.py.bak_20260408`
- `wallet_manager/signal_intelligence.py.bak_20260408`
- `wallet_manager/strategies/model_registry.py.bak_20260408`
- `wallet_manager/metrics_server.py.bak_20260408`

Deploy command used:

```powershell
ssh -i C:\Users\ASUS\.ssh\id_rsa azureuser@51.124.156.116 "cd ~/walletbot; sudo docker compose up -d --build wallet_manager"
```

## Deployment Rule

If Azure runtime facts change, update this file in the same work session.

Do not store secret contents here.
