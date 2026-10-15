"""
Guided demo of the spec's 6-step story (section 26) against a running API.

    make api            # terminal 1
    python demo.py      # terminal 2      (set RISK_API_KEY if the server uses API_KEYS)
"""
import os

import requests

BASE = os.getenv("RISK_API_BASE", "http://localhost:8000")
HEADERS = {"X-API-Key": os.environ["RISK_API_KEY"]} if os.getenv("RISK_API_KEY") else {}


def call(method, path, **kw):
    r = requests.request(method, BASE + path, headers=HEADERS, timeout=60, **kw)
    r.raise_for_status()
    return r.json()


def banner(t):
    print(f"\n{'=' * 64}\n{t}\n{'=' * 64}")


def show(results):
    for i, r in enumerate(results, 1):
        print(f"  tx {i}: risk {r['risk_score']:.2f}  {r['risk_level']:<8} {r['decision']}")


banner("STEP 1: Normal activity")
show(call("POST", "/simulate", json={"scenario": "normal", "n": 3})["results"])

banner("STEP 2: Suspicious activity appears (card testing: rapid small purchases, then a big one)")
show(call("POST", "/simulate", json={"scenario": "velocity_burst", "n": 8})["results"])

banner("STEP 3: Coordinated behaviour (many new accounts on one device)")
ring = call("POST", "/simulate", json={"scenario": "fraud_ring", "n": 8})["results"]
show(ring)

banner("STEP 4: Explainability for the last ring transaction")
last = ring[-1]
print(f"Risk {last['risk_score']:.2f} -> {last['decision']}\nReasons:")
for i, reason in enumerate(last["reasons"], 1):
    print(f"  {i}. {reason}")
print("Top model attributions (SHAP):")
for c in last["contributions"][:4]:
    print(f"  {c['contribution']:+.3f}  {c['label']} = {c['value']:g}")

banner("STEP 5: Held-out test-set evaluation (never used for tuning)")
m = call("GET", "/metrics")
print(f"Model {m['model_name']} (calibrated: {m['calibration']}) at threshold {m['threshold']:.2f}")
print(f"Precision {m['precision']:.1%} | Recall {m['recall']:.1%} | F1 {m['f1']:.1%} | PR-AUC {m['pr_auc']:.3f} | FPR {m['false_positive_rate']:.2%}")
print(f"Calibration Brier score {m['brier_uncalibrated']:.4f} -> {m['brier_calibrated']:.4f}")
print(f"Note: {m['dataset_note']}")

banner("STEP 6: Business impact")
c = call("GET", "/model-comparison")
r, a = c["rule_based"], c["ml_model"]
print(f"Rule baseline expected loss: Rs {r['fp_cost'] + r['fn_cost']:,.0f}")
print(f"ML model expected loss:      Rs {a['fp_cost'] + a['fn_cost']:,.0f}")
print(f"Reduction:                   {c['cost_reduction_pct']}%")

banner("BONUS: linked-account networks found")
rings = call("GET", "/graph/rings?min_accounts=3&limit=3")
print(f"{rings['total']} networks; riskiest:")
for x in rings["rings"]:
    print(f"  {x['ring_id']}: {x['accounts']} accounts, {x['devices']} devices, {x['cards']} cards, avg risk {x['avg_risk']:.0%}")
