import dataclasses
import asyncio

from fastapi.testclient import TestClient

from app.config import settings
from app.yumi import client as yc
from app.yumi.fake import FakeYumi


class Spy(FakeYumi):
    def __init__(self):
        super().__init__(speed=0.01)
        self.calls = []

    async def ask(self, place_id, kind, topic, outcome=None):
        self.calls.append(("ask", place_id)); return await super().ask(place_id, kind, topic, outcome)

    async def reserve(self, place_id, when, guests, phone, idem, name=None, note=None, outcome=None):
        self.calls.append(("reserve", place_id)); return await super().reserve(place_id, when, guests, phone, idem, name, note, outcome)


def test_only_allowlisted_place_goes_real(monkeypatch):
    live = dataclasses.replace(settings, yumi_live=True, live_places=("1185547279",), yumi_api_key="hmp_test")
    monkeypatch.setattr(yc, "settings", live)
    r = yc.RoutedYumi()
    real = Spy(); r._real = real
    async def go():
        await r.reserve("mapo-01", "2026-10-18T15:00:00+09:00", 2, "010", "k")
        await r.ask("mapo-02", "seats", "2명 입장")
        rid = await r.reserve("1185547279", "2026-10-18T15:00:00+09:00", 2, "010", "k")
        assert (await r.reservation_result(rid, 1))["status"] in ("pending", "confirmed")
    asyncio.run(go())
    assert real.calls == [("reserve", "1185547279")]


def test_real_actions_blocked_through_tunnel(monkeypatch):
    from app import main
    monkeypatch.setattr(main, "settings", dataclasses.replace(settings, yumi_live=True, live_places=("1185547279",)))
    c = TestClient(main.app)
    r = c.post("/api/lab/session", json={"place_id": "x"}, headers={"cf-connecting-ip": "1.2.3.4"})
    assert r.status_code == 403
