import io

import pytest

NORMAL = {"customer_id": "T-NORMAL", "amount": 800, "device_id": "T-DEV", "payment_id": "T-PAY", "account_age_days": 400, "ip_region": "Chennai"}


def _simulate(client, scenario, n=8):
    r = client.post("/simulate", json={"scenario": scenario, "n": n})
    assert r.status_code == 200
    return r.json()["results"]


def test_health(client):
    assert client.get("/health").json()["status"] == "ok"


def test_predict_returns_score_decision_reasons(client):
    r = client.post("/predict", json=NORMAL)
    assert r.status_code == 200
    j = r.json()
    assert 0 <= j["risk_score"] <= 1 and j["decision"] in {"ALLOW", "MONITOR", "REVIEW", "HOLD_FOR_VERIFICATION"}
    assert j["reasons"] and "anomaly_score" in j


@pytest.mark.parametrize("bad", [{**NORMAL, "amount": 0}, {**NORMAL, "amount": -5}, {"amount": 10}])
def test_predict_validates_input(client, bad):
    assert client.post("/predict", json=bad).status_code == 422


def test_duplicate_transaction_id_is_rejected(client):
    body = {**NORMAL, "transaction_id": "DUP-1"}
    assert client.post("/predict", json=body).status_code == 200
    assert client.post("/predict", json=body).status_code == 409


def test_fraud_ring_escalates_while_normal_traffic_is_allowed(client):
    ring = _simulate(client, "fraud_ring")
    assert ring[-1]["decision"] in {"REVIEW", "HOLD_FOR_VERIFICATION"} and ring[-1]["risk_score"] > ring[0]["risk_score"] - 0.2
    assert all(r["decision"] == "ALLOW" for r in _simulate(client, "normal", 5))


@pytest.mark.parametrize("scenario", ["velocity_burst", "multi_device_ring", "account_takeover"])
def test_every_attack_scenario_is_flagged(client, scenario):
    assert any(r["decision"] in {"REVIEW", "HOLD_FOR_VERIFICATION"} for r in _simulate(client, scenario))


def test_alert_queue_detail_and_pagination(client):
    q = client.get("/alerts?limit=5&min_level=HIGH").json()
    assert q["total"] >= len(q["items"]) > 0
    scores = [a["risk_score"] for a in q["items"]]
    assert scores == sorted(scores, reverse=True)
    page2 = client.get("/alerts?limit=5&offset=5&min_level=HIGH").json()["items"]
    assert not {a["transaction_id"] for a in q["items"]} & {a["transaction_id"] for a in page2}
    d = client.get(f"/alerts/{q['items'][0]['transaction_id']}").json()
    assert d["contributions"] and "customer_timeline" in d and "related_accounts" in d and "review_history" in d
    assert client.get("/alerts/NOPE").status_code == 404


def test_review_workflow_updates_status_and_label(client):
    tx = client.get("/alerts?limit=1&min_level=HIGH&status=NEW").json()["items"][0]["transaction_id"]
    assert client.post(f"/alerts/{tx}/review", json={}).status_code == 422
    r = client.post(f"/alerts/{tx}/review", json={"action": "ESCALATE", "label": "FRAUD", "note": "looks coordinated"}).json()
    assert r["status"] == "ESCALATED" and r["label"] == "FRAUD"
    assert client.get(f"/alerts/{tx}").json()["status"] == "ESCALATED"
    assert tx not in {a["transaction_id"] for a in client.get("/alerts?limit=200&status=NEW").json()["items"]}


def test_live_feedback_label_teaches_the_feature_store(client):
    sim = _simulate(client, "fraud_ring", 3)[0]
    from app.api.state import S, tx_record
    rec = tx_record(sim["transaction_id"])
    before = S.store.dev[rec["device_id"]]["fraud"]
    client.post(f"/alerts/{sim['transaction_id']}/review", json={"label": "FRAUD"})
    client.post(f"/alerts/{sim['transaction_id']}/review", json={"label": "FRAUD"})   # second label must not double count
    assert S.store.dev[rec["device_id"]]["fraud"] == before + 1


def test_costs_and_threshold_config_and_audit(client):
    assert client.put("/config/costs", json={"cost_fp": 0, "cost_fn": 10}).status_code == 422
    assert client.put("/config/costs", json={"cost_fp": 100, "cost_fn": 5000}).json()["cost_fn"] == 5000
    assert client.put("/config/threshold", json={"threshold": 0.4}).json()["threshold"] == 0.4
    assert client.get("/dashboard/summary").json()["threshold"] == 0.4
    assert client.put("/config/threshold", json={"threshold": None}).json()["threshold"] == client.get("/config").json()["trained_threshold"]
    actions = {a["action"] for a in client.get("/audit?limit=500").json()}
    assert {"CONFIG_COSTS", "CONFIG_THRESHOLD", "PREDICT_SIM", "REVIEW"} <= actions


def test_threshold_analysis_responds_to_costs(client):
    cheap = client.get("/analysis/threshold?cost_fp=100&cost_fn=200").json()
    dear = client.get("/analysis/threshold?cost_fp=100&cost_fn=20000").json()
    assert dear["optimal_threshold"] <= cheap["optimal_threshold"]          # costly misses -> flag more aggressively
    assert dear["cost"]["total_cost"] >= 0 and dear["cost_if_no_model"] > dear["optimal_cost"]
    assert client.get("/analysis/threshold?split=train").status_code == 422


def test_chart_endpoints(client):
    assert client.get("/analytics/timeseries").json()
    assert client.get("/analytics/breakdown?by=merchant_category").json()
    pr = client.get("/analytics/pr-curve").json()
    assert 0 < pr["average_precision"] <= 1 and pr["points"]
    c = client.get("/analytics/confusion").json()
    assert c["true_positives"] + c["false_negatives"] > 0
    assert client.get("/analytics/breakdown?by=password").status_code == 422


def test_rings_and_ring_graph(client):
    _simulate(client, "fraud_ring", 6)
    rings = client.get("/graph/rings?min_accounts=3").json()
    assert rings["total"] > 0
    g = client.get(f"/graph/rings/{rings['rings'][0]['ring_id']}").json()
    assert g["nodes"] and g["edges"] and g["summary"]
    assert client.get("/graph/rings/RING-missing").status_code == 404


def test_monitoring_and_comparison(client):
    m = client.get("/monitoring/summary").json()
    assert "score_psi" in m and m["features"] and "feedback" in m
    c = client.get("/model-comparison").json()
    assert c["ml_model"]["fn"] <= c["rule_based"]["fn"] and c["cost_reduction_pct"] > 0


def test_batch_scoring_and_download(client):
    csv = "customer_id,amount,device_id,timestamp\n" + "\n".join(f"U{i % 4},{900 + i},DV{i % 2},2026-09-01 10:{i % 60:02d}:00" for i in range(60))
    r = client.post("/predict/batch", files={"file": ("t.csv", csv, "text/csv")})
    assert r.status_code == 200 and r.json()["rows"] == 60
    assert client.get(f"/predict/batch/{r.json()['result_id']}/download").text.splitlines()[0].endswith("decision")
    assert client.post("/predict/batch", files={"file": ("t.csv", "a,b\n1,2", "text/csv")}).status_code == 422
    assert client.post("/predict/batch", files={"file": ("t.csv", b"\x00\x01garbage", "text/csv")}).status_code in (422, 200)


def test_batch_with_labels_reports_metrics(client):
    rows = ["customer_id,amount,device_id,timestamp,is_fraud"]
    rows += [f"N{i},{500 + i},ND{i},2026-09-02 09:{i % 60:02d}:00,0" for i in range(40)]
    rows += [f"R{i},5000,RINGDEV,2026-09-02 11:{i:02d}:00,1" for i in range(8)]
    j = client.post("/predict/batch", files={"file": ("l.csv", "\n".join(rows), "text/csv")}).json()
    assert "metrics" in j and "cost" in j


def test_export_csv(client):
    r = client.get("/alerts/export.csv?min_level=CRITICAL")
    assert r.status_code == 200 and r.text.startswith("transaction_id,")


def test_rate_limiting(client, monkeypatch):
    from app.core import security
    monkeypatch.setattr(security, "RATE_LIMIT_PER_MIN", 3)
    codes = [client.get("/config").status_code for _ in range(5)]
    assert codes[:3] == [200, 200, 200] and codes[3] == 429


def test_auth_and_roles(client, monkeypatch):
    from app.core import security
    monkeypatch.setattr(security, "API_KEYS", {"analyst-key": "analyst", "admin-key": "admin"})
    assert client.get("/metrics").status_code == 401
    assert client.get("/metrics", headers={"X-API-Key": "wrong"}).status_code == 401
    a, adm = {"X-API-Key": "analyst-key"}, {"X-API-Key": "admin-key"}
    assert client.get("/metrics", headers=a).status_code == 200
    assert client.put("/config/costs", json={"cost_fp": 1, "cost_fn": 2}, headers=a).status_code == 403
    assert client.get("/audit", headers=a).status_code == 403
    assert client.put("/config/costs", json={"cost_fp": 150, "cost_fn": 2500}, headers=adm).status_code == 200
    assert client.get("/health").status_code == 200       # health stays public
    monkeypatch.setattr(security, "API_KEYS", {})
    assert "AUTH_FAILED" in {x["action"] for x in client.get("/audit?limit=500").json()}


def test_retrain_endpoint_runs_and_reloads_model(client):
    import time
    assert client.post("/admin/retrain").status_code == 202
    for _ in range(120):
        st = client.get("/admin/retrain/status").json()
        if st["state"] != "running":
            break
        time.sleep(1)
    assert st["state"] == "done", st
    assert client.post("/predict", json={**NORMAL, "transaction_id": "AFTER-RETRAIN"}).status_code == 200
