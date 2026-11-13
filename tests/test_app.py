import datetime as dt
import os
import tempfile

os.environ["BRANDLOOM_DB"] = os.path.join(tempfile.mkdtemp(), "t.db")
os.environ["SEED_DEMO"] = "0"

import pytest
from fastapi.testclient import TestClient

from app import engine, seed
from app.main import app

LIB = {"rules": [dict(r, active=1) for r in seed.RULES], "facts": seed.FACTS, "settings": seed.BRAND}
TODAY = dt.date(2026, 11, 13)


def ids(text, meta=None):
    return {f["rule_id"] for f in engine.review(text, LIB, meta, TODAY)}


def test_term_and_case_preserved():
    f = engine.review("Users love it. Our users too.", LIB, None, TODAY)
    fixes = [x["fix"]["text"] for x in f if x["rule_id"] == "BG-1.1"]
    assert fixes == ["Members", "members"]


def test_url_and_handle_not_flagged_as_lowercase_brand():
    assert "BG-1.3" not in ids("Visit lumora.com or email hi@lumora.com")


def test_fact_number_mismatch_has_fix_and_needs_human():
    f = [x for x in engine.review("The Lumora Hub connects up to 100 bulbs.", LIB, None, TODAY) if x["rule_id"] == "F-2"][0]
    assert f["fix"]["text"] == "64" and f["needs_human"]


def test_correct_fact_not_flagged():
    assert "F-2" not in ids("The Lumora Hub connects up to 64 bulbs.")


def test_expired_fact_flagged_only_after_expiry():
    assert "F-6" in ids("Spring Sale: 20% off all bulbs.")
    early = engine.review("Spring Sale: 20% off all bulbs.", LIB, None, dt.date(2026, 3, 1))
    assert "F-6" not in {x["rule_id"] for x in early}


def test_supported_claim_not_flagged_unsupported_is():
    assert "BG-3.1" not in ids("We are highly rated by members.")
    assert "BG-3.1" in ids("We are the best.")


def test_promo_requires_terms_apply():
    assert "BG-4.2" in ids("Big sale this week.")
    assert "BG-4.2" not in ids("Big sale this week. Terms apply.")


def test_contrast_and_palette():
    assert "BG-5.4" in ids("Hello.", {"fg": "#CCCCCC", "bg": "#FFFFFF"})
    assert "BG-5.4" not in ids("Hello.", {"fg": "#14213D", "bg": "#FFF8EC"})
    assert "BG-6.1" in ids("Hello.", {"fg": "#FF00FF", "bg": "#FFFFFF"})


def test_markdown_image_not_counted_as_exclamation():
    assert "BG-2.1" not in ids("![a](x.png) Nice.")


# ------------------------------------------------------------ workflow
@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


def H(u): return {"X-User": u}


def make(client, user, body, title="t"):
    r = client.post("/api/content", json={"title": title, "kind": "post", "body": body}, headers=H(user))
    assert r.status_code == 200, r.text
    return r.json()["id"]


def test_requires_user(client):
    assert client.get("/api/content").status_code == 401


def test_full_happy_path(client):
    cid = make(client, "u_alex", "Our users love Lumora.")
    d = client.get(f"/api/content/{cid}", headers=H("u_alex")).json()
    f = [x for x in d["findings"] if x["rule_id"] == "BG-1.1"][0]
    assert client.post(f"/api/findings/{f['id']}/accept", json={}, headers=H("u_alex")).status_code == 200
    d = client.get(f"/api/content/{cid}", headers=H("u_alex")).json()
    assert "members" in d["revision"]["body"] and d["revision"]["n"] == 2
    assert client.post(f"/api/content/{cid}/submit", headers=H("u_alex")).status_code == 200
    assert client.post(f"/api/content/{cid}/decision", json={"decision": "approve"}, headers=H("u_alex")).status_code == 403
    assert client.post(f"/api/content/{cid}/decision", json={"decision": "approve"}, headers=H("u_morgan")).json()["status"] == "approved"
    assert client.put(f"/api/content/{cid}/body", json={"body": "x"}, headers=H("u_alex")).status_code == 409


def test_high_severity_blocks_submit_until_dismissed_with_reason(client):
    cid = make(client, "u_sam", "We are the best.")
    assert client.post(f"/api/content/{cid}/submit", headers=H("u_sam")).status_code == 409
    f = [x for x in client.get(f"/api/content/{cid}", headers=H("u_sam")).json()["findings"] if x["rule_id"] == "BG-3.1"][0]
    assert client.post(f"/api/findings/{f['id']}/dismiss", json={"reason": "no"}, headers=H("u_sam")).status_code == 400
    assert client.post(f"/api/findings/{f['id']}/dismiss", json={"reason": "Legal approved in LEG-1"}, headers=H("u_sam")).status_code == 200
    assert client.post(f"/api/content/{cid}/submit", headers=H("u_sam")).status_code == 200
    # a manager cannot approve overridden claims; a reviewer can
    assert client.post(f"/api/content/{cid}/decision", json={"decision": "approve"}, headers=H("u_morgan")).status_code == 403
    assert client.post(f"/api/content/{cid}/decision", json={"decision": "approve"}, headers=H("u_riley")).status_code == 200


def test_dismissal_carries_over_to_next_revision(client):
    cid = make(client, "u_alex", "We are the best. Users rock.")
    d = client.get(f"/api/content/{cid}", headers=H("u_alex")).json()
    f = [x for x in d["findings"] if x["rule_id"] == "BG-3.1"][0]
    client.post(f"/api/findings/{f['id']}/dismiss", json={"reason": "Approved by legal"}, headers=H("u_alex"))
    client.put(f"/api/content/{cid}/body", json={"body": "We are the best. Members rock."}, headers=H("u_alex"))
    d = client.get(f"/api/content/{cid}", headers=H("u_alex")).json()
    assert [x["state"] for x in d["findings"] if x["rule_id"] == "BG-3.1"] == ["dismissed"]


def test_changes_requested_needs_comment_and_reopens_edit(client):
    cid = make(client, "u_alex", "Hello everyone.")
    client.post(f"/api/content/{cid}/submit", headers=H("u_alex"))
    assert client.post(f"/api/content/{cid}/decision", json={"decision": "changes"}, headers=H("u_morgan")).status_code == 400
    assert client.post(f"/api/content/{cid}/decision", json={"decision": "changes", "comment": "Add detail"}, headers=H("u_morgan")).status_code == 200
    assert client.put(f"/api/content/{cid}/body", json={"body": "Hello everyone, more detail."}, headers=H("u_alex")).status_code == 200


def test_only_manager_edits_library(client):
    body = {"category": "terminology", "title": "x", "text": "y", "kind": "term", "config": {"banned": ["foo"], "preferred": "bar", "map": {"foo": "bar"}}}
    assert client.post("/api/library/rules", json=body, headers=H("u_alex")).status_code == 403
    assert client.post("/api/library/rules", json=body, headers=H("u_morgan")).status_code == 200
    cid = make(client, "u_alex", "A foo here.")
    assert any(f["rule_id"].startswith("BG-9") for f in client.get(f"/api/content/{cid}", headers=H("u_alex")).json()["findings"])


def test_bad_regex_rejected(client):
    body = {"category": "tone", "title": "x", "text": "y", "kind": "pattern", "config": {"pattern": "(["}}
    assert client.post("/api/library/rules", json=body, headers=H("u_morgan")).status_code == 400


def test_insights_shape(client):
    d = client.get("/api/insights", headers=H("u_alex")).json()
    assert d["total_content"] >= 1 and "top_rules" in d
