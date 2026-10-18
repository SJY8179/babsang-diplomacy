"""② 탐색 에이전트: 검색 → 신뢰 필터 → 점수. LLM 없음."""
from app.agents.memory import ATTR_KO, Profile, memory_weight
from app.events import EventBus
from app.models import Candidate, Constraints, Evidence, Place
from app.yumi.client import YumiClient
from app.geo import dist_m

W_PREF, W_TRUST, W_PRICE, W_MEMORY = 0.35, 0.25, 0.20, 0.20
FIELDS = "core,quality,edge,contact_hours"  # 요청당 최고 등급(edge 4)만 차감, contact_hours에 yumiReservable


def _search_params(c: Constraints, relax: int) -> dict:
    p: dict = {"fields": FIELDS, "page_size": 50, "reservation_channel": "yumi", "reservable": "true"}
    if relax < 2:
        p["recommended_for"] = c.context
    if relax < 1 and c.when:
        p["open_at"] = c.when[:16].replace("T", " ")
    for a in c.must:
        p[a] = "true"
    if c.dietary:
        p["dietary"] = c.dietary[0]
    return p


def _drop_reason(p: Place, c: Constraints, prof: Profile) -> str | None:
    if not p.reservable_here:
        return "헤이유미 예약·문의 불가"
    if p.possibly_closed or p.closure_signal:
        return "폐업 의심"
    if p.freshness is not None and p.freshness < 0.2:
        return "최근 활동 신호 약함"
    if p.id in prof.excluded_places:
        return "지난 회식에서 재방문 안 함"
    if any(a not in p.attrs for a in c.must):
        return "필수 조건 불충족"
    text = f"{p.name} {p.category or ''}"
    if any(k in text for k in c.avoid):
        return "피할 메뉴"
    return None


def _score(p: Place, c: Constraints, prof: Profile) -> tuple[float, list[Evidence]]:
    ev: list[Evidence] = []
    nice_hit = [a for a in c.nice if a in p.attrs]
    pref = len(nice_hit) / len(c.nice) if c.nice else 0.5
    for a in c.must + nice_hit:
        ev.append(Evidence(kind="data", label=ATTR_KO.get(a, a), source=a))

    conf = p.confidence if p.confidence is not None else 0.5
    fresh = p.freshness if p.freshness is not None else 0.5
    trust = 0.6 * conf + 0.4 * fresh
    if p.freshness is None:
        ev.append(Evidence(kind="unknown", label="최근 활동 정보 없음", source="freshnessScore"))
    elif p.freshness >= 0.8:
        ev.append(Evidence(kind="data", label="최근 활동 활발", source=f"freshnessScore {p.freshness:.2f}"))
    if p.confidence is not None and p.confidence < 0.6:
        ev.append(Evidence(kind="unknown", label="정보 교차 확인 필요", source=f"confidence {p.confidence:.2f}"))

    if c.max_price and p.price:
        price_fit = 1.0 if p.price <= c.max_price else max(0.0, 1 - (p.price - c.max_price) / c.max_price)
        ev.append(Evidence(kind="data", label=f"메뉴 평균 {p.price / 10000:.1f}만 원", source="price.avg"))
    elif c.max_price:
        price_fit = 0.5
        ev.append(Evidence(kind="unknown", label="가격 확인 필요", source="price"))
    else:
        price_fit = 0.5

    if p.review_count:
        ev.append(Evidence(kind="data", label=f"리뷰 {p.review_count:,}건", source="reviewCount"))
    if p.station and p.walk_min:
        ev.append(Evidence(kind="data", label=f"{p.station}역 도보 {p.walk_min}분", source="nearestStation"))

    mem = memory_weight(p.id, p.attrs, p.price, prof)
    if p.id in prof.liked_places:
        ev.insert(0, Evidence(kind="memory", label="지난 회식 만족 · 재방문 희망", source="visits"))
    elif prof.visits and mem >= 0.4:
        ev.insert(0, Evidence(kind="memory", label="우리 팀 취향과 비슷", source="visits"))

    score = W_PREF * pref + W_TRUST * trust + W_PRICE * price_fit + W_MEMORY * mem
    return round(score, 4), ev


async def scout(yumi: YumiClient, c: Constraints, prof: Profile, bus: EventBus, top: int = 5,
                radius: int = 1500) -> list[Candidate]:
    if c.region_name is None and (c.lat is None or c.lng is None):
        coords = await yumi.region(c.area)
        if coords:
            c.lat, c.lng = coords
    if c.region_name is None and c.lat is None:
        bus.emit("scout", "error", f"'{c.area}' 위치를 찾지 못했어요.")
        return []

    if prof.visits:
        bus.emit("memory", "applied", f"모임 기억 반영 · {prof.summary}")

    places: list[Place] = []
    relax_msgs = ["", "시간 조건을 풀고 다시 찾아요", "모임 유형 조건까지 풀고 다시 찾아요"]
    for relax in range(3):
        if relax:
            bus.emit("scout", "relax", relax_msgs[relax])
        params = _search_params(c, relax)
        if c.region_name:
            places = await yumi.search(c.region_name, params)
            where = f"{c.region_name} 주변"
        else:
            places = await yumi.nearby(c.lat, c.lng, radius, params)
            where = f"반경 {radius}m"
        bus.emit("scout", "search", f"헤이유미로 예약 가능한 가게 {len(places)}곳 검색 ({where})")
        kept = [p for p in places if _drop_reason(p, c, prof) is None]
        if len(kept) >= 3:
            break

    dropped: dict[str, int] = {}
    cands: list[Candidate] = []
    for p in places:
        reason = _drop_reason(p, c, prof)
        if reason:
            dropped[reason] = dropped.get(reason, 0) + 1
            continue
        score, ev = _score(p, c, prof)
        d = dist_m(c.lat, c.lng, p.lat, p.lng) if p.lat and p.lng and c.lat and c.lng else None
        cands.append(Candidate(place=p, score=score, evidence=ev, distance_m=d))
    if dropped:
        bus.emit("scout", "filter", "제외: " + ", ".join(f"{k} {v}곳" for k, v in dropped.items()))
    cands.sort(key=lambda x: x.score, reverse=True)
    bus.emit("scout", "ranked", f"후보 {min(top, len(cands))}곳을 골랐어요", ids=[x.place.id for x in cands[:top]])
    return cands[:top]
