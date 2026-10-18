"""공개 배포에서 지켜야 할 것: 실제 요청 잠금 · 입력 제한 · 요청 수 제한 · API 흐름."""
import json
import os
import subprocess
import sys
from pathlib import Path

from fastapi.testclient import TestClient

from app import main
from app.store import Store
from scripts.seed_demo import seed

ROOT = Path(__file__).resolve().parent.parent


def _settings_with(env: dict) -> dict:
    code = ("import json; from app.config import settings as s; "
            "print(json.dumps({'actions': s.yumi_actions, 'live': s.yumi_live, 'public': s.public_demo}))")
    base = {k: v for k, v in os.environ.items() if not k.startswith(("YUMI_", "PUBLIC_DEMO"))}
    out = subprocess.run([sys.executable, "-c", code], cwd=ROOT, env=base | env, capture_output=True, text=True, check=True)
    return json.loads(out.stdout.strip().splitlines()[-1])


def test_public_demo_never_opens_real_requests():
    s = _settings_with({"PUBLIC_DEMO": "1", "YUMI_ACTIONS": "live", "YUMI_LIVE": "1", "YUMI_LIVE_PLACES": "1185547279"})
    assert s == {"actions": "simulate", "live": False, "public": True}


def test_live_needs_both_locks():
    assert _settings_with({"PUBLIC_DEMO": "0", "YUMI_ACTIONS": "live", "YUMI_LIVE": "0"})["live"] is False
    assert _settings_with({"PUBLIC_DEMO": "0", "YUMI_ACTIONS": "live", "YUMI_LIVE": "1"})["live"] is True


def _client(monkeypatch, public=False):
    st = Store(":memory:")
    seed(st)
    monkeypatch.setattr(main, "store", st)
    monkeypatch.setattr(main, "_PUB", public)
    main._HITS.clear()
    return TestClient(main.app)


def test_meeting_flow_through_api(monkeypatch):
    c = _client(monkeypatch)
    m = c.get("/api/groups/demo/meeting").json()
    assert m["participants"] and m["done"] >= 1
    s = c.post(f"/api/meetings/{m['id']}/plan", json={}).json()
    assert s["candidates"] and s["meeting"]["count"] >= 1
    assert c.get(f"/api/sessions/{s['id']}").status_code == 200


def test_input_limits(monkeypatch):
    c = _client(monkeypatch)
    m = c.get("/api/groups/demo/meeting").json()
    assert c.post(f"/api/meetings/{m['id']}/participants", json={"name": "가" * 21}).status_code == 422
    assert c.put(f"/api/p/{m['participants'][0]['token']}", json={"mood": "x" * 41}).status_code == 422
    assert c.patch(f"/api/meetings/{m['id']}", json={"group_id": "demo", "title": "회식", "when_at": "내일"}).status_code == 422
    assert c.post("/api/feedback", json={"group_id": "demo", "place_id": "p", "place_name": "x" * 61,
                                         "satisfaction": 4, "revisit": True}).status_code == 422


def test_public_demo_blocks_lab_and_rate_limits(monkeypatch):
    c = _client(monkeypatch, public=True)
    assert c.get("/api/lab/lookup", params={"q": "Hide Me Please"}).status_code == 403
    m = c.get("/api/groups/demo/meeting").json()
    codes = [c.post(f"/api/meetings/{m['id']}/plan", json={}).status_code for _ in range(14)]
    assert 429 in codes


def test_security_headers(monkeypatch):
    r = _client(monkeypatch).get("/api/config")
    assert r.headers["x-content-type-options"] == "nosniff"
    assert r.headers["x-frame-options"] == "DENY"
    assert "publicDemo" in r.json()


def test_sessions_do_not_grow_forever(monkeypatch):
    from app.session import SESSIONS, Session
    from app.agents.memory import Profile
    from app.models import Constraints
    for _ in range(main.MAX_SESSIONS + 20):
        main._remember(Session(group_id="g", constraints=Constraints(), profile=Profile()))
    assert len(SESSIONS) <= main.MAX_SESSIONS
