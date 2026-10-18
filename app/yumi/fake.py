"""YUMI_MODE=mock 일 때 쓰는 가짜 Yumi. 가게 이름은 모두 지어낸 데모용이다.

실제 API와 같은 인터페이스라서 화면·에이전트 흐름을 키 없이 끝까지 돌려 볼 수 있다.
"""
import asyncio
import uuid

from app.geo import dist_m
from app.models import Place

ANCHOR = (37.5660, 126.9826)  # 을지로입구역 부근


EXTRA = {  # 데모용 분위기·종류·주류·식단
    1: (["lively"], "korean_bbq", ["alcohol"], []), 2: (["quiet", "clean"], "korean", ["alcohol"], ["vegetarian_options"]),
    3: (["lively"], "hof_beer", ["alcohol"], []), 4: (["quiet", "traditional"], "korean", ["alcohol"], []),
    5: (["lively"], "seafood", ["alcohol"], []), 6: (["lively"], "chinese", ["alcohol"], ["vegetarian_options"]),
    7: (["clean", "quiet"], "noodles", ["alcohol"], ["vegetarian_options"]), 8: (["spacious"], "korean_bbq", ["alcohol"], []),
    9: ([], "korean", [], []), 10: (["quiet", "cozy"], "wine_bar", ["alcohol"], ["vegetarian_options"]),
    11: (["lively"], "hof_beer", ["alcohol"], []), 12: (["cozy", "quiet"], "izakaya", ["alcohol"], ["vegetarian_options"]),
}


def _p(i: int, name: str, cat: str, dlat: float, dlng: float, price: int, attrs: list[str],
       rec: list[str], conf: float, fresh: float | None, closed: bool = False) -> Place:
    atm, sub, serves, diet = EXTRA[i]
    return Place(atmosphere=atm, subtype=sub, serves=serves, dietary=diet,id=f"demo-{i:02d}", name=name, category=cat, lat=ANCHOR[0] + dlat, lng=ANCHOR[1] + dlng,
                 price=price, attrs=attrs, recommended_for=rec, confidence=conf, freshness=fresh,
                 possibly_closed=closed, station="을지로입구", walk_min=3, review_count=120 + i * 37, reservable_here=True)


GONGDEOK = (37.5443, 126.9516)


def _m(i: str, name: str, cat: str, lat: float, lng: float, price: int, station: str, walk: int, attrs: list[str],
       atm: list[str], sub: str, serves: list[str], diet: list[str], conf: float = 0.9, fresh: float = 0.85) -> Place:
    return Place(id=f"mapo-{i}", name=name, category=cat, lat=lat, lng=lng, price=price, attrs=attrs,
                 recommended_for=["group_dining"], confidence=conf, freshness=fresh, station=station, walk_min=walk,
                 review_count=200 + len(name) * 37, reservable_here=True, atmosphere=atm, subtype=sub, serves=serves, dietary=diet)


# Readdy 시안 후보(소반 마포점·트라토리아 루체·숯불집 연남) + 같은 동네 데모 가게. 모두 데모용 이름.
MAPO: list[Place] = [
    _m("01", "소반 마포점", "모던 한식", 37.5450, 126.9530, 24000, "공덕", 3, ["group_friendly", "private_room"],
       ["quiet", "clean"], "korean", [], ["vegetarian_options"]),
    _m("02", "트라토리아 루체", "이탈리안", 37.5502, 126.9150, 27000, "합정", 5, ["group_friendly"],
       ["cozy", "quiet"], "italian", ["alcohol"], ["vegetarian_options"]),
    _m("03", "숯불집 연남", "한식 고기", 37.5590, 126.9230, 31000, "홍대입구", 7, ["group_friendly"],
       ["lively"], "korean_bbq", ["alcohol"], []),
    _m("04", "공덕 국수당", "한식", 37.5438, 126.9505, 15000, "공덕", 2, ["group_friendly"],
       ["clean"], "noodles", [], ["vegetarian_options"]),
    _m("05", "마포 포차 골목", "포차", 37.5400, 126.9470, 22000, "마포", 4, ["group_friendly"],
       ["lively"], "pocha", ["alcohol"], []),
    _m("06", "용산 쌀국수 하우스", "베트남", 37.5305, 126.9660, 19000, "용산", 4, ["group_friendly"],
       ["clean", "cozy"], "vietnamese", ["alcohol"], ["vegetarian_options"]),
    _m("07", "합정 이자카야 소요", "이자카야", 37.5490, 126.9125, 29000, "합정", 3, ["private_room", "group_friendly"],
       ["quiet", "cozy"], "izakaya", ["alcohol"], ["vegetarian_options"]),
    _m("08", "애오개 한우 정육식당", "고기구이", 37.5530, 126.9570, 38000, "애오개", 4, ["private_room", "group_friendly"],
       ["spacious"], "korean_bbq", ["alcohol"], []),
    _m("09", "신촌 마라 골목", "중식", 37.5560, 126.9375, 21000, "신촌", 3, ["group_friendly"],
       ["lively"], "chinese", ["alcohol"], ["vegetarian_options"]),
    _m("10", "공덕 비스트로 담", "양식", 37.5447, 126.9522, 28000, "공덕", 2, ["group_friendly"],
       ["quiet", "cozy"], "western", ["alcohol"], []),
]

PLACES: list[Place] = [
    _p(1, "골목숯불 을지점", "고기구이", 0.0012, 0.0010, 32000, ["private_room", "group_friendly"], ["group_dining"], 0.91, 0.88),
    _p(2, "삼각지붕 한상", "한식", -0.0008, 0.0021, 24000, ["private_room", "group_friendly", "parking"], ["group_dining", "business_meeting"], 0.86, 0.74),
    _p(3, "을지 노가리 2층", "호프", 0.0020, -0.0011, 18000, ["group_friendly"], ["group_dining"], 0.79, 0.93),
    _p(4, "청계 수육집", "한식", -0.0015, -0.0018, 29000, ["private_room"], ["group_dining", "family"], 0.83, 0.65),
    _p(5, "다동 해물포차", "해산물", 0.0026, 0.0030, 35000, ["group_friendly"], ["group_dining"], 0.72, 0.41),
    _p(6, "명동 마라골목", "중식(매운)", 0.0031, -0.0025, 22000, ["group_friendly"], ["group_dining"], 0.81, 0.90),
    _p(7, "을지로 오래된 냉면", "한식", -0.0022, 0.0006, 15000, [], ["family"], 0.95, 0.97),
    _p(8, "수표교 바베큐", "고기구이", 0.0005, -0.0032, 38000, ["private_room", "group_friendly", "corkage_free"], ["group_dining", "business_meeting"], 0.88, 0.80),
    _p(9, "닫힌 간판 식당", "한식", 0.0009, 0.0002, 20000, ["group_friendly"], ["group_dining"], 0.55, 0.12, closed=True),
    _p(10, "을지 와인 바", "와인바", 0.0016, 0.0014, 19500, ["group_friendly"], ["group_dining"], 0.84, 0.86),
    _p(11, "충무로 생맥 창고", "호프", 0.0011, 0.0017, 17000, ["group_friendly"], ["group_dining"], 0.80, 0.77),
    _p(12, "저동 이자카야", "이자카야", -0.0006, 0.0013, 19000, ["group_friendly", "private_room"], ["group_dining"], 0.82, 0.83),
]




class FakeYumi:
    def __init__(self, speed: float = 1.0) -> None:
        self.speed = speed
        self._asks: dict[str, dict] = {}
        self._res: dict[str, dict] = {}
        self._order = 0

    async def nearby(self, lat: float, lng: float, radius: int, params: dict) -> list[Place]:
        await asyncio.sleep(0.3 * self.speed)
        out = []
        for p in PLACES + MAPO:
            if dist_m(lat, lng, p.lat, p.lng) > radius:
                continue
            if any(params.get(a) and a not in p.attrs for a in ("private_room", "parking", "group_friendly")):
                continue
            rec = params.get("recommended_for")
            if rec and rec not in p.recommended_for:
                continue
            out.append(p)
        return out

    async def place(self, place_id: str) -> dict:
        p = next((x for x in PLACES + MAPO if x.id == place_id), None)
        if not p:
            return {}
        base = (p.price or 20000) // 1000 * 1000
        menu = [{"name": f"{p.category} 대표 메뉴", "price": base, "recommend": True},
                {"name": "계절 한정 메뉴", "price": base + 4000, "recommend": False},
                {"name": "단체 세트(4인)", "price": base * 4 - 8000, "recommend": False}]
        return {**p.model_dump(), "photos": [], "menu": menu, "phone": None,
                "placeUrl": None, "summary": "데모 데이터입니다. 실제 모드에서는 Yumi 상세 정보가 나옵니다."}

    async def search(self, region_name: str, params: dict) -> list[Place]:
        from app.agents.coordinator import AREAS, STATIONS
        area = next((a for a, st in STATIONS.items() if st == region_name), None)
        lat, lng = AREAS.get(area, ANCHOR)
        if area in ("마포·용산", "마포", "공덕", "합정", "신촌", "용산"):
            return [p for p in MAPO if not params.get("private_room") or "private_room" in p.attrs]
        return await self.nearby(lat, lng, 800, params)

    async def lookup(self, keyword: str) -> list[dict]:
        k = keyword.replace(" ", "").lower()
        hits = [p for p in PLACES + MAPO if k in p.name.replace(" ", "").lower()]
        return [{"_place": p.model_dump(), "demo": True} for p in hits[:5]]

    async def region(self, name: str) -> tuple[float, float] | None:
        return ANCHOR

    async def ask(self, place_id: str, kind: str, topic: str, outcome: str | None = None) -> str:
        qid = f"q-{uuid.uuid4().hex[:8]}"
        # 순서마다 응답 시간을 다르게 해서 '먼저 답한 곳'이 보이게 한다
        delays = [4.0, 2.5, 6.0, 5.0, 3.5]
        delay = delays[self._order % len(delays)] * self.speed
        self._order += 1
        self._asks[qid] = {"outcome": outcome or "available", "ready": asyncio.get_event_loop().time() + delay}
        return qid

    async def ask_result(self, query_id: str, wait: int = 25) -> dict:
        q = self._asks[query_id]
        remain = q["ready"] - asyncio.get_event_loop().time()
        if remain > 0:
            await asyncio.sleep(min(remain, wait))
        if asyncio.get_event_loop().time() < q["ready"]:
            return {"status": "pending", "reused": False, "blocked": None, "raw": {}}
        return {"status": q["outcome"], "reused": False, "blocked": None, "raw": {}}

    async def reserve(self, place_id: str, when: str, guests: int, phone: str, idem: str,
                      name: str | None = None, note: str | None = None, outcome: str | None = None) -> str:
        rid = f"r-{uuid.uuid4().hex[:8]}"
        self._res[rid] = {"outcome": outcome or "confirmed", "ready": asyncio.get_event_loop().time() + 3.0 * self.speed}
        return rid

    async def reservation_result(self, reservation_id: str, wait: int = 25) -> dict:
        r = self._res[reservation_id]
        remain = r["ready"] - asyncio.get_event_loop().time()
        if remain > 0:
            await asyncio.sleep(min(remain, wait))
        if asyncio.get_event_loop().time() < r["ready"]:
            return {"status": "pending", "reused": False, "blocked": None, "raw": {}}
        return {"status": r["outcome"], "reused": False, "blocked": None, "raw": {}}
