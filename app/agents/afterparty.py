"""⑥ 2차 에이전트: 1차 가게 근처에서 지금 열린 곳을 찾아 사장님께 바로 묻는다. 예약은 하지 않고 안내만."""
from app.agents.negotiator import ask_many
from app.agents.scout import FIELDS
from app.events import now_kst
from app.geo import dist_m
from app.models import Candidate
from app.session import Session
from app.yumi.client import YumiClient

RADIUS_M = 400


async def find_afterparty(yumi: YumiClient, s: Session) -> None:
    r = s.reservation
    first = s.find(r.place_id) if r else None
    if not first or first.place.lat is None:
        s.bus.emit("afterparty", "error", "1차 가게 위치가 없어 2차를 찾을 수 없어요.")
        return
    lat, lng = first.place.lat, first.place.lng
    params = {"fields": FIELDS, "page_size": 30, "open_at": now_kst().strftime("%Y-%m-%d %H:%M"),
              "reservation_channel": "yumi", "recommended_for": "group_dining"}
    places = await yumi.nearby(lat, lng, RADIUS_M, params)
    taken = {c.place.id for c in s.candidates}
    pool = [p for p in places if p.id not in taken and not p.possibly_closed]
    pool.sort(key=lambda p: dist_m(lat, lng, p.lat, p.lng) if p.lat else 9999)
    s.after = [Candidate(place=p, distance_m=dist_m(lat, lng, p.lat, p.lng) if p.lat else None) for p in pool[:3]]
    s.bus.emit("afterparty", "search", f"1차 근처 {RADIUS_M}m 안 지금 열린 곳 {len(pool)}곳 → {len(s.after)}곳에 문의")
    if not s.after:
        return

    picked: list[str] = []

    async def first_positive(c: Candidate) -> None:
        if not picked:
            picked.append(c.place.id)
            s.bus.emit("afterparty", "pick", f"2차는 {c.place.name} · 도보 {c.distance_m}m · 사장님이 먼저 '가능'이라고 답했어요",
                       placeId=c.place.id)

    await ask_many(yumi, s, s.after, r.guests, "afterparty", first_positive)
    if not picked:
        s.bus.emit("afterparty", "none", "근처 2차 후보가 모두 자리가 없어요.")
