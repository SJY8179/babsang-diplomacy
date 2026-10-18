"""회식 한 번(참석자 여럿) 기준 조율 + 탐색 + 이동 시간 + 점수.

점수 = 필수 50% · 이동 균형 30% · 선호 20% (선호 안에 모임 기억 포함). 화면에는 기준과 충족 여부를 그대로 보여 준다.
필수 조건을 못 지키면 후보에서 뺀다. 확인 못 한 항목은 '확인 필요'로 남긴다(지어내지 않음).
"""
from statistics import median

from app.agents.coordinator import AREAS, STATIONS
from app.agents.memory import ATTR_KO, Profile, memory_weight
from app.agents.scout import FIELDS
from app.agents.travel import geocode, travel_table
from app.config import settings
from app.events import EventBus
from app.geo import dist_m
from app.models import Candidate, Constraints, Evidence, Place
from app.yumi.client import YumiClient

FOOD = {"한식": ["korean", "gukbap_soup", "jjigae", "noodles"], "고기": ["korean_bbq", "gopchang"],
        "파스타": ["italian", "western"], "양식": ["western", "italian"], "이탈리안": ["italian"],
        "아시안": ["asian", "vietnamese"], "일식": ["japanese", "sushi_sashimi", "izakaya"],
        "중식": ["chinese"], "해산물": ["seafood"], "치킨": ["chicken"]}
MOOD_ATM = {"조용": "quiet", "아늑": "cozy", "활기": "lively", "넓": "spacious", "깔끔": "clean"}
ALLERGY_EXCLUDE = {"갑각류": ["새우", "게", "랍스터", "대게", "킹크랩"], "조개": ["조개", "굴", "꼬막"],
                   "생선": ["회", "생선"], "돼지": ["돼지", "삼겹살"]}
W_MUST, W_TRAVEL, W_PREF = 0.5, 0.3, 0.2


def _won(n: int) -> str:
    return f"{n / 10000:g}만원"


def aggregate(meeting: dict, parts: list[dict], relax: dict) -> tuple[Constraints, dict]:
    """참석자 입력 → 검색 조건 + 화면용 필수/선호/충돌."""
    c = Constraints(party=max(1, len(parts)), when=meeting.get("when_at"))
    must, nice, notes = [], [], []

    budgets = [p["budget"] for p in parts if p.get("budget")]
    if budgets:
        c.max_price = int(relax.get("max_price") or max(budgets))
        must.append(f"1인 {_won(c.max_price)} 이하 (메뉴 평균 기준)")

    diets = {p["name"]: (p.get("diet") or "") for p in parts}
    if any("비건" in d for d in diets.values()):
        c.dietary = ["mixed_group_suitable"]
        must.append("비건 식사 가능 (+일반 메뉴)")
    elif any(k in d for d in diets.values() for k in ("채식", "페스코", "락토")):
        c.dietary = ["vegetarian_mixed_group_suitable"]
        must.append("채식 메뉴 가능 (+일반 메뉴)")
    if any("글루텐" in d for d in diets.values()):
        c.dietary.append("gluten_free")
        must.append("글루텐프리 (매장 확인 필요)")

    for p in parts:
        a = p.get("allergy") or ""
        for k, words in ALLERGY_EXCLUDE.items():
            if k in a:
                c.exclude += words
                must.append(f"{k} 전문점 제외 ({p['name']}, 메뉴는 매장 확인)")
        if a and not any(k in a for k in ALLERGY_EXCLUDE) and a not in ("없음", "-"):
            notes.append(f"{p['name']}의 '{a}' 알레르기는 Yumi로 거를 수 없어 매장 확인이 필요해요")
    must.append(f"{c.party}인 좌석 예약 가능")

    foods = {f.strip() for p in parts for f in (p.get("food") or "").replace("/", ",").split(",") if f.strip()}
    for f in foods:
        for k, subs in FOOD.items():
            if k in f:
                c.subtypes += subs
    if foods:
        nice.append(f"{'·'.join(sorted(foods))} 중 하나")
    moods = " ".join(p.get("mood") or "" for p in parts)
    for k, atm in MOOD_ATM.items():
        if k in moods and atm not in relax.get("drop_atmosphere", []):
            c.atmosphere.append(atm)
            nice.append(f"{k}한 분위기" if k != "깔끔" else "깔끔한 곳")
    if "술" in moods:
        c.serves.append("alcohol")
        nice.append("주류 가능")
    if "룸" in moods or "칸막이" in moods:
        c.nice.append("private_room")
        nice.append("룸 또는 칸막이 좌석")
    if c.party >= 6:
        c.nice.append("group_friendly")

    conflicts = []
    if len(budgets) >= 2 and max(budgets) - min(budgets) >= 5000 and not relax.get("max_price"):
        lo = min(parts, key=lambda p: p.get("budget") or 10**9)
        hi = max(parts, key=lambda p: p.get("budget") or 0)
        mid = int(round(median(budgets) / 5000) * 5000)
        conflicts.append({"id": "budget", "title": "예산 차이",
                          "text": f"{lo['name']} {_won(lo['budget'])} vs {hi['name']} {_won(hi['budget'])}.",
                          "relax": {"max_price": mid}, "label": f"{_won(mid)} 기준으로 맞추기"})
    if "quiet" in c.atmosphere and "alcohol" in c.serves:
        conflicts.append({"id": "mood", "title": "분위기 충돌",
                          "text": "'조용한 분위기'와 '술 한잔'이 함께 확인된 곳은 적어요.",
                          "relax": {"drop_atmosphere": ["quiet"]}, "label": "조용한 분위기를 우선순위에서 빼기"})
    return c, {"must": must, "nice": nice, "conflicts": conflicts, "notes": notes}


def _area_for(meeting: dict, origins: dict[str, tuple[float, float]]) -> tuple[str, str, tuple[float, float]]:
    area = meeting.get("area")
    if area in AREAS:
        return area, STATIONS.get(area, f"{area}역"), AREAS[area]
    if origins:  # 참석자 출발지 중심에서 가장 가까운 상권
        lat = sum(x[0] for x in origins.values()) / len(origins)
        lng = sum(x[1] for x in origins.values()) / len(origins)
        best = min(AREAS, key=lambda a: dist_m(lat, lng, *AREAS[a]))
        return best, STATIONS.get(best, f"{best}역"), AREAS[best]
    return "을지로", "을지로입구역", AREAS["을지로"]


def _hard_fail(p: Place, c: Constraints, prof: Profile) -> str | None:
    if p.possibly_closed or p.closure_signal:
        return "폐업 의심"
    if p.freshness is not None and p.freshness < 0.2:
        return "최근 활동 신호 약함"
    if p.id in prof.excluded_places:
        return "지난 회식 재방문 안 함"
    if c.max_price and p.price and p.price > c.max_price * 1.2:
        return "예산 20% 이상 초과"
    if any(w in f"{p.name} {p.category or ''}" for w in c.exclude):
        return "알레르기 제외"
    return None


def _checks(p: Place, c: Constraints) -> dict[str, str]:
    ck = {}
    if c.dietary:  # 실제 모드에서는 Yumi가 dietary 필터로 이미 거른 결과
        ck["식단"] = "충족" if (settings.yumi_mode == "rest" or p.dietary) else "확인 필요"
    if c.max_price:
        ck["예산"] = "확인 필요" if not p.price else ("충족" if p.price <= c.max_price else "미충족")
    if c.atmosphere:
        ck["분위기"] = "확인 필요" if not p.atmosphere else ("충족" if set(p.atmosphere) & set(c.atmosphere) else "미충족")
    if c.serves:
        ck["주류"] = "확인 필요" if not p.serves else ("충족" if set(p.serves) & set(c.serves) else "미충족")
    return ck


def _pref(p: Place, c: Constraints, prof: Profile) -> float:
    parts = []
    if c.subtypes:
        parts.append(1.0 if p.subtype in c.subtypes else 0.0)
    if c.atmosphere:
        parts.append(1.0 if set(p.atmosphere) & set(c.atmosphere) else 0.3 if not p.atmosphere else 0.0)
    if c.serves:
        parts.append(1.0 if set(p.serves) & set(c.serves) else 0.3)
    for a in c.nice:
        parts.append(1.0 if a in p.attrs else 0.0)
    base = sum(parts) / len(parts) if parts else 0.5
    return 0.7 * base + 0.3 * memory_weight(p.id, p.attrs, p.price, prof)


def _travel_score(mins: dict[str, int]) -> float:
    if not mins:
        return 0.5
    worst, spread = max(mins.values()), max(mins.values()) - min(mins.values())
    return max(0.0, min(1.0, 1 - (worst - 15) / 35 - spread / 80))


def _reason(p: Place, c: Constraints, ck: dict, mins: dict[str, int]) -> str:
    bits = []
    if c.dietary and ck.get("식단") == "충족":
        bits.append("식단 조건이 확인됐고")
    if mins:
        worst = max(mins.values())
        far = [n for n, m in mins.items() if m >= 25]
        bits.append(f"{len(mins)}명 모두 이동 {worst}분 이내예요" if not far
                    else f"{'·'.join(far)} 이동이 {max(mins[n] for n in far)}분 안팎이에요")
    if ck.get("예산") == "미충족":
        bits.append("예산을 조금 넘어요")
    if ck.get("식단") == "확인 필요":
        bits.append("채식 메뉴는 매장 확인이 필요해요")
    if ck.get("예산") == "확인 필요":
        bits.append("가격은 매장 확인이 필요해요")
    return " ".join(bits) or "조건을 고르게 맞춘 곳이에요."


async def plan_meeting(yumi: YumiClient, meeting: dict, parts: list[dict], prof: Profile, bus: EventBus,
                       relax: dict | None = None, top: int = 5) -> tuple[Constraints, dict, list[Candidate]]:
    relax = relax or {}
    c, summary = aggregate(meeting, parts, relax)
    bus.emit("coordinator", "parsed",
             f"참석자 {len(parts)}명 조건 정리 · 필수 {len(summary['must'])} · 선호 {len(summary['nice'])} · 충돌 {len(summary['conflicts'])}")
    for n in summary["notes"]:
        bus.emit("coordinator", "conflict", n)

    origins: dict[str, tuple[float, float]] = {}
    for p in parts:
        if p.get("origin"):
            xy = await geocode(p["origin"])
            if xy:
                origins[p["name"]] = xy
            else:
                bus.emit("travel", "error", f"{p['name']}의 출발지 '{p['origin']}' 위치를 찾지 못했어요")
    c.area, c.region_name, (c.lat, c.lng) = _area_for(meeting, origins)
    summary["area"] = c.area
    if prof.visits:
        bus.emit("memory", "applied", f"모임 기억 반영 · {prof.summary}")

    params = {"fields": FIELDS, "page_size": 50, "reservation_channel": "yumi", "reservable": "true",
              "recommended_for": c.context}
    if c.when:
        params["open_at"] = c.when[:16].replace("T", " ")
    if c.dietary:
        params["dietary"] = ",".join(c.dietary)
    if c.exclude:
        params["exclude"] = ",".join(dict.fromkeys(c.exclude))
    if c.atmosphere:
        params["atmosphere"] = ",".join(c.atmosphere)
    places = await yumi.search(c.region_name, params)
    bus.emit("scout", "search", f"{c.region_name} 주변 헤이유미 예약 가능 {len(places)}곳 검색")
    if sum(1 for p in places if _hard_fail(p, c, prof) is None) < 5:
        # 파트너·식단·영업시간 필터가 겹치면 후보가 너무 적다 → 필터를 빼고 넓혀 찾은 뒤 우리 쪽에서 점수로 거른다
        loose = {k: v for k, v in params.items() if k in ("fields", "page_size", "exclude", "atmosphere")} | {"business_category": "restaurant"}
        more = await yumi.search(c.region_name, loose)
        seen = {p.id for p in places}
        places += [p for p in more if p.id not in seen]
        bus.emit("scout", "search", f"후보가 적어 조건을 넓혀 다시 검색 · 총 {len(places)}곳 (식단·예약 가능 여부는 카드에서 확인)")

    dropped: dict[str, int] = {}
    kept: list[Place] = []
    for p in places:
        r = _hard_fail(p, c, prof)
        if r:
            dropped[r] = dropped.get(r, 0) + 1
        else:
            kept.append(p)
    if dropped:
        bus.emit("scout", "filter", "제외: " + ", ".join(f"{k} {v}곳" for k, v in dropped.items()))
    summary["count"] = len(kept)

    # 완화했을 때 후보 수(추가 검색 없이 같은 풀에서 계산)
    for cf in summary["conflicts"]:
        if "max_price" in cf["relax"]:
            c2 = c.model_copy(update={"max_price": cf["relax"]["max_price"]})
            n2 = sum(1 for p in places if _hard_fail(p, c2, prof) is None)
            cf["text"] += f" {cf['label'].replace(' 기준으로 맞추기', '')} 기준으로 맞추면 후보가 {len(kept)}곳 → {n2}곳이 돼요."
        else:
            both = sum(1 for p in kept if "quiet" in p.atmosphere and "alcohol" in p.serves)
            either = sum(1 for p in kept if "quiet" in p.atmosphere or "alcohol" in p.serves)
            cf["text"] += f" 둘 다 확인된 곳 {both}곳, 하나라도 맞는 곳 {either}곳이에요."

    pre = sorted(kept, key=lambda p: _pref(p, c, prof), reverse=True)[:8]
    cands: list[Candidate] = []
    src = None
    for p in pre:
        mins, src = (await travel_table(origins, (p.lat, p.lng))) if origins and p.lat else ({}, None)
        ck = _checks(p, c)
        must_ok = 1.0 - 0.3 * sum(v == "확인 필요" for k, v in ck.items() if k in ("식단", "예산")) \
            - 0.4 * sum(v == "미충족" for k, v in ck.items() if k in ("식단", "예산"))
        total = round(100 * (W_MUST * must_ok + W_TRAVEL * _travel_score(mins) + W_PREF * _pref(p, c, prof)))
        ev = [Evidence(kind="data", label=ATTR_KO.get(a, a), source=a) for a in p.attrs if a in ATTR_KO]
        if p.review_count:
            ev.append(Evidence(kind="data", label=f"리뷰 {p.review_count:,}건", source="reviewCount"))
        if p.id in prof.liked_places:
            ev.insert(0, Evidence(kind="memory", label="지난 회식 만족 · 재방문 희망", source="visits"))
        cands.append(Candidate(place=p, score=total / 100, total=total, evidence=ev, travel=mins, travel_source=src,
                               checks=ck, reason=_reason(p, c, ck, mins),
                               distance_m=dist_m(c.lat, c.lng, p.lat, p.lng) if p.lat else None))
    if origins:
        bus.emit("travel", "computed", f"참석자 {len(origins)}명 × 후보 {len(cands)}곳 이동 시간 계산 ({src})")
    cands.sort(key=lambda x: x.total or 0, reverse=True)
    bus.emit("scout", "ranked", f"점수 기준 필수 50% · 이동 30% · 선호 20%로 {min(top, len(cands))}곳을 골랐어요")
    summary["travel_source"] = src
    return c, summary, cands[:top]
