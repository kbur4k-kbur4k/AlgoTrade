#!/usr/bin/env python3
import json, os
p1 = '/app/wallet_manager/ml_models/training_report.json'
p2 = '/home/wallet/.local/lib/python3.11/site-packages/wallet_manager/ml_models/training_report.json'
print(f'/app exists: {os.path.exists(p1)}')
print(f'site-packages exists: {os.path.exists(p2)}')
for p in [p1, p2]:
    if os.path.exists(p):
        r = json.loads(open(p).read())
        print(f'{p}: models={list(r.get("models", {}).keys())}')
        break
