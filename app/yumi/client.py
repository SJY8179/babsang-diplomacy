"""Hey Yumi 접근은 이 파일에서만 한다.

응답 필드 이름은 문서에 다 나와 있지 않아서 normalize_* 함수가 여러 후보 키를 받아 준다.
`python scripts/probe_yumi.py` 로 실제 응답을 tests/fixtures 에 저장한 뒤, 맞지 않는 키가 있으면 여기만 고친다.
"""
import asyncio
from typing import Any, Protocol

import httpx

from app.config import settings
from app.models import Place

BOOL_ATTRS = {
    "private_room", "parking", "group_friendly", "wheelchair_accessible", "pet_friendly",
    "corkage_free", "power_outlets", "waiting_expected", "reservable", "late_night",
}


class YumiError(Exception):
    def __init__(self, status: int, code: str, msg: str = ""):
        super().__init__(f"{status} {code} {msg}")
        self.status, self.code = status, code


class YumiClient(Protocol):
    async def place(self, place_id: str) -> dict: ...
    async def search(self, region_name: str, params: dict) -> list[Place]: ...
    async def lookup(self, keyword: str) -> list[dict]: ...
    async def nearby(self, lat: float, lng: float, radius: int, params: dict) -> list[Place]: ...
    async def region(self, name: str) -> tuple[float, float] | None: ...
    async def ask(self, place_id: str, kind: str, topic: str, outcome: str | None = None) -> str: ...
    async def ask_result(self, query_id: str, wait: int = 25) -> dict: ...
    async def reserve(self, place_id: str, when: str, guests: int, phone: str, idem: str,
                      name: str | None = None, note: str | None = None, outcome: str | None = None) -> str: ...
    async def reservation_result(self, reservation_id: str, wait: int = 25) -> dict: ...


# ---------- 정규화 ----------

def _first(d: dict, *keys: str, default: Any = None) -> Any:
    for k in keys:
        cur: Any = d
        for part in k.split("."):
            if not isinstance(cur, dict) or part not in cur:
                cur = None
                break
            cur = cur[part]
        if cur not in (None, ""):
            return cur
    return default


def _items(payload: Any) -> list[dict]:
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict):
        for k in ("data", "places", "items", "results"):
            v = payload.get(k)
            if isinstance(v, list):
                return v
            if isinstance(v, dict):
                inner = _items(v)
                if inner:
                    return inner
    return []


def _price(raw: dict) -> int | None:
    v = _first(raw, "priceAvg", "avgPrice", "price.avg", "price.average", "pricePerPerson", "price")
    if isinstance(v, dict):
        v = _first(v, "avg", "average", "min")
    try:
        return int(float(v)) if v is not None else None
    except (TypeError, ValueError):
        return None


def _attrs(raw: dict) -> list[str]:
    found: set[str] = set()
    for src in (raw, raw.get("serviceAttributes") or {}, raw.get("attributes") or {}, raw.get("features") or {}):
        if isinstance(src, dict):
            found |= {k for k, v in src.items() if v is True and (k in BOOL_ATTRS or k.endswith("_friendly"))}
        elif isinstance(src, list):
            found |= {str(x) for x in src if isinstance(x, str)}
    for k in ("attributes", "features", "tags"):
        v = raw.get(k)
        if isinstance(v, list):
            found |= {str(x) for x in v if isinstance(x, str)}
    return sorted(found)


def normalize_place(raw: dict) -> Place:
    rec = _first(raw, "recommendedFor", "recommended_for", default=[])
    station = _first(raw, "nearestStation.station", "nearestStation.name", "nearest_station")
    address = _first(raw, "address.road", "address.jibun", "roadAddress", "address")
    walk = _first(raw, "nearestStation.walkMin")
    reviews = _first(raw, "reviewCount")
    return Place(
        id=str(_first(raw, "id", "placeId", "place_id")),
        name=str(_first(raw, "name", "title", default="(이름 없음)")),
        lat=_first(raw, "lat", "latitude", "location.lat", "coordinates.lat"),
        lng=_first(raw, "lng", "lon", "longitude", "location.lng", "coordinates.lng"),
        category=_first(raw, "categoryLabel", "category", "cuisine", "categoryName"),
        price=_price(raw),
        attrs=_attrs(raw),
        recommended_for=rec if isinstance(rec, list) else [str(rec)],
        confidence=_first(raw, "confidence", "dataQuality.confidence"),
        freshness=_first(raw, "freshnessScore", "quality.freshnessScore", "freshness"),
        possibly_closed=bool(_first(raw, "possiblyClosed", "quality.possiblyClosed", default=False)),
        closure_signal=bool(_first(raw, "closureSignal", "quality.closureSignal", default=False)),
        station=station if isinstance(station, str) else None,
        walk_min=int(walk) if isinstance(walk, (int, float)) else None,
        address=address if isinstance(address, str) else None,
        review_count=int(reviews) if isinstance(reviews, (int, float)) else None,
        reservable_here=bool(_first(raw, "yumiReservable", default=False)),
        atmosphere=[str(a) for a in (raw.get("atmosphere") or []) if isinstance(a, str)],
        subtype=_first(raw, "serviceAttributes.venue_subtype", "subtype"),
        serves=[str(a) for a in (_first(raw, "serviceAttributes.serves", default=[]) or []) if isinstance(a, str)],
        dietary=_dietary(raw),
    )


def _dietary(raw: dict) -> list[str]:
    d = _first(raw, "serviceAttributes.dietary", "dietary", default=None)
    if isinstance(d, list):
        return [str(x) for x in d]
    if isinstance(d, dict):
        return [k for k, v in d.items() if v is True]
    return []


def _photo_url(x) -> str | None:
    if isinstance(x, str):
        return x if x.startswith("http") else None
    if isinstance(x, dict):
        v = _first(x, "url", "src", "thumbnailUrl", "originalUrl", "imageUrl")
        return v if isinstance(v, str) and v.startswith("http") else None
    return None


def normalize_detail(raw: dict) -> dict:
    """사진·메뉴·연락처. 없는 값은 비워 둔다(지어내지 않음)."""
    body = raw.get("data", raw) if isinstance(raw.get("data"), dict) else raw
    p = normalize_place(body)
    photos_raw = _first(body, "photos", "media.photos", "images", default=[]) or []
    photos = [u for u in (_photo_url(x) for x in photos_raw if photos_raw) if u][:8]
    menu_raw = body.get("menu")
    menu: list[dict] = []
    if isinstance(menu_raw, list):
        for m in menu_raw[:30]:
            if isinstance(m, dict) and m.get("name"):
                price = m.get("price")
                if isinstance(price, str):
                    digits = "".join(ch for ch in price if ch.isdigit())
                    price = int(digits) if digits else None
                menu.append({"name": str(m["name"]), "price": int(price) if isinstance(price, (int, float)) else None,
                             "recommend": bool(m.get("recommend") or m.get("isRecommended"))})
            elif isinstance(m, str):
                menu.append({"name": m, "price": None, "recommend": False})
    if not menu:
        items = _first(body, "menuSummary.items", default=[]) or []
        menu = [{"name": str(n), "price": None, "recommend": False} for n in items if isinstance(n, str)]
    return {**p.model_dump(), "photos": photos, "menu": menu, "phone": _first(body, "phone"),
            "placeUrl": _first(body, "placeUrl"), "summary": _first(body, "aiSummary", "ownerIntro")}


def normalize_status(raw: dict) -> dict:
    """live-status / reservation 결과를 {status, reused, blocked, raw} 로."""
    body = raw.get("data", raw) if isinstance(raw.get("data"), dict) else raw
    status = _first(body, "status", "answer", "result", "state", default="pending")
    blocked = _first(body, "blocked")
    if blocked == "closed_now":
        status = "closed_now"
    return {"status": str(status).lower(), "reused": bool(_first(body, "reused", default=False)),
            "blocked": blocked, "raw": body}


# ---------- REST ----------

class ActionBlocked(Exception):
    """YUMI_ACTIONS가 sandbox/live가 아닌데 사장님께 가는 요청을 보내려 할 때."""


def _guard_action() -> None:
    if settings.yumi_actions not in ("sandbox", "live"):
        raise ActionBlocked("YUMI_ACTIONS=simulate: 자리 문의·예약은 Yumi로 보내지 않습니다")
    if settings.yumi_actions == "live" and not settings.yumi_live:
        raise ActionBlocked("실제 요청은 YUMI_ACTIONS=live 와 YUMI_LIVE=1 이 모두 필요합니다")


class RestYumi:
    def __init__(self) -> None:
        headers = {"Authorization": f"Bearer {settings.yumi_api_key}"}
        if not settings.yumi_live:
            headers["X-Map3-Sandbox"] = "1"
        self._http = httpx.AsyncClient(base_url=settings.yumi_base_url, headers=headers, timeout=40)

    async def _req(self, method: str, path: str, **kw) -> Any:
        for _ in range(3):
            r = await self._http.request(method, path, **kw)
            if r.status_code == 429:
                await asyncio.sleep(float(r.headers.get("Retry-After", "2")))
                continue
            if r.status_code >= 400:
                try:
                    body = r.json()
                except ValueError:
                    body = {}
                code = str(_first(body, "error.code", "code", "error", default="error"))
                raise YumiError(r.status_code, code, r.text[:200])
            return r.json()
        raise YumiError(429, "rate_limited")

    async def place(self, place_id: str) -> dict:
        # media 등급(8토큰)이라 상세를 열 때만 부르고, 앱이 캐시한다
        data = await self._req("GET", f"/places/{place_id}", params={"fields": "core,contact_hours,edge,media"})
        return normalize_detail(data)

    async def search(self, region_name: str, params: dict) -> list[Place]:
        try:
            data = await self._req("GET", "/places", params={"region_name": region_name, **params})
            return [normalize_place(x) for x in _items(data)]
        except YumiError as e:
            if e.status not in (400, 404, 422):
                raise
        # REST가 region_name을 받지 않으면 좌표로 바꿔 주변 검색
        coords = await self.region(region_name.removesuffix("역"))
        if not coords:
            return []
        return await self.nearby(coords[0], coords[1], 1000, params)

    async def lookup(self, keyword: str) -> list[dict]:
        """이름으로 한 가게 찾기(영문·로마자 이름 가능). 읽기 전용."""
        data = await self._req("GET", "/places", params={"keyword": keyword, "fields": "core,contact_hours", "page_size": 5})
        return _items(data)

    async def nearby(self, lat: float, lng: float, radius: int, params: dict) -> list[Place]:
        # MCP 도구는 radius_m, REST 문서는 radius — probe 결과 보고 하나로 정리
        q = {"lat": lat, "lng": lng, "radius": radius, "radius_m": radius, "sort": "discovery", **params}
        data = await self._req("GET", "/places/nearby", params=q)
        return [normalize_place(x) for x in _items(data)]

    async def region(self, name: str) -> tuple[float, float] | None:
        try:
            data = await self._req("GET", "/regions", params={"dong": name})
        except YumiError:
            return None
        items = _items(data) or ([data] if isinstance(data, dict) else [])
        for it in items:
            lat, lng = _first(it, "lat", "latitude", "center.lat"), _first(it, "lng", "longitude", "center.lng")
            if lat and lng:
                return float(lat), float(lng)
        return None

    async def ask(self, place_id: str, kind: str, topic: str, outcome: str | None = None) -> str:
        _guard_action()
        body: dict = {"placeId": place_id, "kind": kind, "topic": topic,
                      "question": f"지금 {topic} 가능할까요?" if kind == "seats" else None}
        body = {k: v for k, v in body.items() if v is not None}
        if outcome and not settings.yumi_live:
            body["sandboxOutcome"] = outcome  # 위치(바디/헤더)는 문서로 확인
        data = await self._req("POST", "/live-status", json=body)
        return str(_first(data, "queryId", "id", "data.queryId", "data.id"))

    async def ask_result(self, query_id: str, wait: int = 25) -> dict:
        return normalize_status(await self._req("GET", f"/live-status/{query_id}", params={"wait": wait}))

    async def reserve(self, place_id: str, when: str, guests: int, phone: str, idem: str,
                      name: str | None = None, note: str | None = None, outcome: str | None = None) -> str:
        _guard_action()
        body: dict = {"placeId": place_id, "reservationTime": when, "guestCount": guests,
                      "guestPhone": phone, "idempotencyKey": idem}
        if name:
            body["guestName"] = name
        if note:
            body["note"] = note
        if outcome and not settings.yumi_live:
            body["sandboxOutcome"] = outcome
        data = await self._req("POST", "/reservations", json=body)
        return str(_first(data, "id", "reservationId", "data.id", "data.reservationId"))

    async def reservation_result(self, reservation_id: str, wait: int = 25) -> dict:
        return normalize_status(await self._req("GET", f"/reservations/{reservation_id}", params={"wait": wait}))


class HybridYumi:
    """검색은 실제 Yumi, 자리 문의·예약은 가짜(네트워크 없음). 실제 가게로 화면을 만들되 사장님께는 아무것도 안 간다."""

    def __init__(self) -> None:
        from app.yumi.fake import FakeYumi
        self._real, self._fake = RestYumi(), FakeYumi()
        self.search, self.nearby, self.region = self._real.search, self._real.nearby, self._real.region
        self.place, self.lookup = self._real.place, self._real.lookup
        self.ask, self.ask_result = self._fake.ask, self._fake.ask_result
        self.reserve, self.reservation_result = self._fake.reserve, self._fake.reservation_result


class RoutedYumi:
    """검색은 실제. 문의·예약은 YUMI_LIVE_PLACES에 있는 가게만 실제로, 나머지는 가짜로 보낸다."""

    def __init__(self) -> None:
        from app.yumi.fake import FakeYumi
        self._real, self._fake = RestYumi(), FakeYumi()
        self.search, self.nearby, self.region = self._real.search, self._real.nearby, self._real.region
        self.place, self.lookup = self._real.place, self._real.lookup
        self._real_ids: set[str] = set()

    def _is_real(self, place_id: str) -> bool:
        return settings.yumi_live and place_id in settings.live_places

    async def ask(self, place_id: str, kind: str, topic: str, outcome: str | None = None) -> str:
        if not self._is_real(place_id):
            return await self._fake.ask(place_id, kind, topic, outcome)
        qid = await self._real.ask(place_id, kind, topic)
        self._real_ids.add(qid)
        return qid

    async def ask_result(self, query_id: str, wait: int = 25) -> dict:
        src = self._real if query_id in self._real_ids else self._fake
        return await src.ask_result(query_id, wait)

    async def reserve(self, place_id: str, when: str, guests: int, phone: str, idem: str,
                      name: str | None = None, note: str | None = None, outcome: str | None = None) -> str:
        if not self._is_real(place_id):
            return await self._fake.reserve(place_id, when, guests, phone, idem, name, note, outcome)
        rid = await self._real.reserve(place_id, when, guests, phone, idem, name, note)
        self._real_ids.add(rid)
        return rid

    async def reservation_result(self, reservation_id: str, wait: int = 25) -> dict:
        src = self._real if reservation_id in self._real_ids else self._fake
        return await src.reservation_result(reservation_id, wait)


def make_client() -> YumiClient:
    from app.yumi.fake import FakeYumi
    if settings.yumi_mode != "rest":
        return FakeYumi()
    if settings.yumi_live and settings.live_places:
        return RoutedYumi()
    if settings.yumi_actions in ("sandbox", "live"):
        return RestYumi()
    return HybridYumi()


def describe_mode() -> dict:
    if settings.yumi_mode != "rest":
        return {"search": "데모", "actions": "시뮬레이션", "label": "데모 데이터"}
    if settings.yumi_live and settings.live_places:
        return {"search": "실제", "actions": "시뮬레이션", "label": f"검색 실제 · 문의·예약 시뮬레이션 (실매장 {len(settings.live_places)}곳만 실제)"}
    actions = {"simulate": "시뮬레이션", "sandbox": "샌드박스"}.get(settings.yumi_actions, "실제 요청" if settings.yumi_live else "차단")
    return {"search": "실제", "actions": actions, "label": f"검색 실제 · 문의·예약 {actions}"}
