import asyncio

from app.agents import negotiator
from app.agents.afterparty import find_afterparty
from app.agents.coordinator import parse_rules
from app.agents.memory import build_profile
from app.agents.notice import build_notice
from app.agents.scout import scout
from app.models import Constraints, Feedback
from app.session import Session
from app.store import Store
from app.yumi.client import normalize_place
from app.yumi.fake import FakeYumi


def test_parse_rules():
    c = parse_rules("금요일 저녁 7시 을지로 12명 회식, 1인 3만원 이하, 룸 꼭 있어야 하고 팀장님 매운 거 못 드심")
    assert c.party == 12 and c.max_price == 30000 and c.area == "을지로"
    assert "private_room" in c.must and "매운" in c.avoid
    assert c.when and c.when[11:16] == "19:00"


def test_parse_now():
    from app.agents.negotiator import is_now
    c = parse_rules("지금 을지로에서 8명 바로 들어갈 수 있는 곳")
    assert c.party == 8 and is_now(c.when)


def test_normalize_place_variants():
    p = normalize_place({"placeId": 7, "title": "가", "location": {"lat": 1.0, "lng": 2.0},
                         "price": {"avg": 21000}, "attributes": {"private_room": True, "parking": False},
                         "freshnessScore": 0.9, "possiblyClosed": True})
    assert p.id == "7" and p.lat == 1.0 and p.price == 21000
    assert p.attrs == ["private_room"] and p.possibly_closed


def test_normalize_real_search_fixture():
    import json
    from pathlib import Path
    from app.yumi.client import _items
    d = json.loads((Path(__file__).parent / "fixtures" / "search_euljiro.json").read_text())
    places = [normalize_place(x) for x in _items(d)]
    p = places[0]
    assert p.id and p.name and p.lat and p.price and p.reservable_here
    assert p.review_count and p.station and isinstance(p.address, str)
    assert "group_friendly" in p.attrs


def test_memory_profile():
    v = [{"place_id": "a", "place_name": "A", "attrs": ["private_room"], "satisfaction": 5, "revisit": True, "per_person": 26000},
         {"place_id": "b", "place_name": "B", "attrs": [], "satisfaction": 2, "revisit": False, "per_person": 41000}]
    p = build_profile(v)
    assert p.price_center == 26000 and p.excluded_places == ["b"] and p.liked_places == ["a"]


def test_full_day_flow():
    async def run():
        yumi = FakeYumi(speed=0.01)
        st = Store(":memory:")
        st.add_visit(Feedback(group_id="g", place_id="demo-02", place_name="삼각지붕 한상",
                              attrs=["private_room", "group_friendly"], satisfaction=5, revisit=True, per_person=26000))
        st.add_visit(Feedback(group_id="g", place_id="demo-05", place_name="다동 해물포차",
                              attrs=[], satisfaction=2, revisit=False, per_person=41000))
        c = parse_rules("을지로 10명 회식 1인 3만원, 룸 있으면 좋고 매운 건 빼고 저녁 7시")
        c.when = negotiator.now_kst().isoformat(timespec="seconds")  # 지금 모드
        s = Session(group_id="g", constraints=c, profile=build_profile(st.visits("g")))
        s.candidates = await scout(yumi, c, s.profile, s.bus)
        ids = [x.place.id for x in s.candidates]
        assert ids and "demo-05" not in ids and "demo-09" not in ids and "demo-06" not in ids
        assert ids[0] == "demo-02"  # 기억 반영

        await negotiator.start_asking(yumi, s)
        assert s.state == "await_approval"
        first_ok = next(x for x in s.candidates if x.status in ("available", "limited"))
        s.phone = "010-1234-5678"
        await negotiator.reserve_loop(yumi, s, first_ok.place.id, c.when, c.party, auto_fallback=True)
        assert s.state == "confirmed" and s.reservation
        assert s.attempts == 2  # 데모: 첫 예약 거절 → 다음 후보 확정
        assert "1234-5678" not in str(s.bus.history)

        text = build_notice(s)
        assert s.reservation.place_name in text and "10명" in text

        await negotiator.change_headcount(yumi, s, 12)
        assert any(e["type"].startswith("headcount") for e in s.bus.history)

        await find_afterparty(yumi, s)
        assert any(e["agent"] == "afterparty" for e in s.bus.history)

    asyncio.run(run())


def test_constraints_default():
    assert Constraints().party == 8


def test_future_mode_reserves_in_order():
    async def run():
        yumi = FakeYumi(speed=0.01)
        c = parse_rules("을지로 10명 회식 1인 3만원 다음 주 금요일 저녁 7시")
        s = Session(group_id="g", constraints=c, profile=build_profile([]), now_mode=negotiator.is_now(c.when))
        assert not s.now_mode
        s.candidates = await scout(yumi, c, s.profile, s.bus)
        await negotiator.start_asking(yumi, s)
        assert s.state == "await_approval"
        s.phone = "01012345678"
        await negotiator.reserve_loop(yumi, s, s.candidates[0].place.id, c.when, c.party, auto_fallback=True)
        assert s.state == "confirmed" and s.reservation.place_id == s.candidates[1].place.id
    asyncio.run(run())


def test_actions_blocked_by_default():
    import pytest
    from app.yumi.client import ActionBlocked, RestYumi, make_client
    from app.config import settings
    assert settings.yumi_actions == "simulate" and not settings.yumi_live
    with pytest.raises(ActionBlocked):
        asyncio.run(RestYumi().reserve("x", "2026-10-23T19:00:00+09:00", 2, "010-0000-0000", "k"))
    with pytest.raises(ActionBlocked):
        asyncio.run(RestYumi().ask("x", "seats", "2명 입장"))


def test_rest_clients_construct():
    from app.yumi.client import HybridYumi, RestYumi
    for name in ("search", "nearby", "region", "ask", "ask_result", "reserve", "reservation_result"):
        assert hasattr(RestYumi(), name) and hasattr(HybridYumi(), name), name


def test_detail_from_real_fixture():
    import json
    from pathlib import Path
    from app.yumi.client import _items, normalize_detail
    d = json.loads((Path(__file__).parent / "fixtures" / "search_euljiro.json").read_text())
    det = normalize_detail(_items(d)[0])
    assert det["name"] and det["menu"] and det["menu"][0]["price"] == 35000
    assert det["placeUrl"].startswith("https://")


def test_meeting_plan_and_relax():
    from app.agents.meeting import plan_meeting
    m = {"id": "m", "when_at": "2026-10-23T19:00:00+09:00", "area": "을지로"}
    parts = [dict(name="김", origin="신촌", budget=25000, diet="없음", allergy="", food="한식", mood="조용한 분위기", done=1),
             dict(name="박", origin="이태원", budget=30000, diet="없음", allergy="갑각류", food="고기", mood="술 한잔", done=1),
             dict(name="이", origin="합정역", budget=20000, diet="채식(페스코)", allergy="", food="파스타", mood="아늑한", done=1)]
    from app.events import EventBus

    async def run(relax):
        return await plan_meeting(FakeYumi(speed=0.01), m, parts, build_profile([]), EventBus(), relax)
    c, s, cands = asyncio.run(run({}))
    assert c.max_price == 30000 and "새우" in c.exclude and s["conflicts"][0]["id"] == "budget"
    assert cands and set(cands[0].travel) == {"김", "박", "이"} and cands[0].total
    c2, s2, _ = asyncio.run(run({"max_price": 25000}))
    assert c2.max_price == 25000 and not any(cf["id"] == "budget" for cf in s2["conflicts"])
