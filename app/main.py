import json

from pydantic import BaseModel, Field
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from sse_starlette.sse import EventSourceResponse

from app.agents.afterparty import find_afterparty
from app.agents.coordinator import AREAS, STATIONS, coordinate
from app.agents.memory import ATTR_KO, build_profile
from app.agents.negotiator import change_headcount, is_now, reserve_loop, start_asking
from app.agents.notice import build_notice
from app.agents.meeting import plan_meeting
from app.agents.blog import draft
from app.agents.scout import scout
from app.config import settings
from app.models import POSITIVE, ApproveRequest, Candidate, Evidence, Place, Constraints, Feedback, HeadcountRequest, PlanRequest
from app.session import SESSIONS, Session
from app.store import Store
from app.yumi.client import YumiError, describe_mode, make_client, normalize_place

WEB = Path(__file__).resolve().parent.parent / "web"
app = FastAPI(title="밥상외교")
yumi = make_client()
store = Store()


def _local_only(req: Request) -> None:
    """실제 요청이 나갈 수 있는 동작은 이 맥에서 연 화면에서만. 터널(외부)로 들어온 요청은 막는다."""
    via_proxy = any(h in req.headers for h in ("cf-connecting-ip", "x-forwarded-for", "x-real-ip"))
    host = req.client.host if req.client else ""
    if via_proxy or host not in ("127.0.0.1", "::1", "localhost", "testclient"):
        raise HTTPException(403, "실매장 테스트는 서버를 켠 컴퓨터에서만 할 수 있어요")


def _guard_real(req: Request, s) -> None:
    real_here = any(c.place.id in settings.live_places for c in s.candidates + s.after)
    if settings.yumi_live and (s.lab or not settings.live_places or real_here):
        _local_only(req)


def _session(sid: str) -> Session:
    s = SESSIONS.get(sid)
    if not s:
        raise HTTPException(404, "세션이 없어요")
    return s


@app.get("/api/config")
def config() -> dict:
    return {"mode": settings.yumi_mode, "live": settings.yumi_live and not settings.live_places,
            "livePlaces": list(settings.live_places) if settings.yumi_live else [], "label": describe_mode()["label"],
            "actions": settings.yumi_actions, "llm": bool(settings.llm_api_key),
            "areas": list(AREAS)}


@app.get("/api/groups")
def groups() -> list[dict]:
    return store.groups()


class GroupIn(BaseModel):
    name: str = Field(min_length=1, max_length=30)


@app.post("/api/groups")
def add_group(g: GroupIn) -> dict:
    return store.add_group(g.name.strip())


class MeetingIn(BaseModel):
    group_id: str
    title: str = Field(min_length=1, max_length=40)
    when_at: str | None = None
    area: str | None = None


class ParticipantIn(BaseModel):
    name: str = Field(min_length=1, max_length=20)
    role: str | None = None
    origin: str | None = None
    budget: int | None = Field(default=None, ge=0, le=500000)
    diet: str | None = None
    allergy: str | None = None
    food: str | None = None
    mood: str | None = None


class ParticipantSelf(BaseModel):
    origin: str | None = None
    budget: int | None = Field(default=None, ge=0, le=500000)
    diet: str | None = None
    allergy: str | None = None
    food: str | None = None
    mood: str | None = None


def _public_p(p: dict) -> dict:
    return {k: v for k, v in p.items() if k != "id"} | {"link": f"{settings.public_base_url}/p/{p['token']}"}


def _meeting_view(m: dict) -> dict:
    parts = store.participants(m["id"])
    return {**m, "participants": [_public_p(p) for p in parts], "done": sum(p["done"] for p in parts),
            "visits": len(store.visits(m["group_id"]))}


@app.post("/api/meetings")
def create_meeting(m: MeetingIn) -> dict:
    return _meeting_view(store.add_meeting(m.group_id, m.title, m.when_at, m.area))


@app.get("/api/groups/{group_id}/meeting")
def latest_meeting(group_id: str) -> dict:
    m = store.latest_meeting(group_id)
    if not m:
        raise HTTPException(404, "아직 회식이 없어요")
    return _meeting_view(m)


@app.get("/api/meetings/{mid}")
def get_meeting(mid: str) -> dict:
    m = store.meeting(mid)
    if not m:
        raise HTTPException(404, "회식이 없어요")
    return _meeting_view(m)


@app.patch("/api/meetings/{mid}")
def patch_meeting(mid: str, m: MeetingIn) -> dict:
    store.update_meeting(mid, title=m.title, when_at=m.when_at, area=m.area)
    return get_meeting(mid)


@app.post("/api/meetings/{mid}/participants")
def add_participant(mid: str, p: ParticipantIn) -> dict:
    if not store.meeting(mid):
        raise HTTPException(404, "회식이 없어요")
    return _public_p(store.add_participant(mid, p.name, p.role, **p.model_dump(exclude={"name", "role"}, exclude_none=True)))


@app.get("/api/p/{token}")
def get_self(token: str) -> dict:
    p = store.participant(token)
    if not p:
        raise HTTPException(404, "링크가 올바르지 않아요")
    m = store.meeting(p["meeting_id"])
    return {"participant": _public_p(p), "meeting": {"title": m["title"], "when_at": m["when_at"], "area": m["area"]}}


@app.put("/api/p/{token}")
def put_self(token: str, body: ParticipantSelf) -> dict:
    p = store.update_participant(token, **body.model_dump(exclude_none=True))
    if not p:
        raise HTTPException(404, "링크가 올바르지 않아요")
    return _public_p(p)


@app.delete("/api/p/{token}")
def delete_participant(token: str) -> dict:
    store.remove_participant(token)
    return {"ok": True}


@app.post("/api/meetings/{mid}/plan")
async def plan_for_meeting(mid: str, relax: dict | None = None) -> dict:
    m = store.meeting(mid)
    if not m:
        raise HTTPException(404, "회식이 없어요")
    parts = [p for p in store.participants(mid) if p["done"]]
    if not parts:
        raise HTTPException(400, "조건을 입력한 참석자가 아직 없어요")
    prof = build_profile(store.visits(m["group_id"]))
    s = Session(group_id=m["group_id"], constraints=Constraints(), profile=prof)
    c, summary, cands = await plan_meeting(yumi, m, parts, prof, s.bus, relax or {})
    s.constraints, s.candidates = c, cands
    s.now_mode = is_now(c.when)
    s.meeting = {"id": mid, "title": m["title"], **summary, "relax": relax or {}}
    SESSIONS[s.id] = s
    return s.view()


@app.post("/api/groups/{group_id}/blog")
async def blog(group_id: str) -> dict:
    v = store.visits(group_id)
    if not v:
        raise HTTPException(400, "방문 기록이 없어요")
    g = next((x["name"] for x in store.groups() if x["id"] == group_id), group_id)
    text, how = await draft(g, v[0])
    return {"text": text, "how": how}


@app.get("/p/{token}")
def participant_page(token: str) -> FileResponse:
    return FileResponse(WEB / "p.html")


PLACE_CACHE: dict[str, dict] = {}


@app.get("/api/places/{place_id}")
async def place_detail(place_id: str) -> dict:
    if place_id not in PLACE_CACHE:
        try:
            PLACE_CACHE[place_id] = await yumi.place(place_id)
        except YumiError as e:
            raise HTTPException(502, f"가게 정보를 불러오지 못했어요 ({e.code})")
    d = PLACE_CACHE[place_id]
    if not d:
        raise HTTPException(404, "가게가 없어요")
    return d


@app.get("/api/groups/{group_id}/memory")
def memory(group_id: str) -> dict:
    v = store.visits(group_id)
    return {"profile": build_profile(v).model_dump(), "visits": v}


@app.post("/api/plan")
async def plan(req: PlanRequest) -> dict:
    store.ensure_group(req.group_id)
    if req.text:
        c, how = await coordinate(req.text)
    else:
        c, how = (req.form or Constraints()), "form"
        if c.lat is None and c.area in AREAS:
            c.lat, c.lng = AREAS[c.area]
        c.region_name = c.region_name or STATIONS.get(c.area)
    s = Session(group_id=req.group_id, constraints=c, profile=build_profile(store.visits(req.group_id)))
    s.now_mode = is_now(c.when)
    SESSIONS[s.id] = s
    must = ", ".join(ATTR_KO.get(a, a) for a in c.must) or "없음"
    s.bus.emit("coordinator", "parsed",
               f"조건 정리({how}): {c.area} · {c.party}명 · {c.when[5:16].replace('T', ' ') if c.when else '시간 미정'}"
               f" · 1인 {f'{c.max_price // 10000}만 원 이하' if c.max_price else '예산 미정'} · 필수 {must}")
    for msg in c.conflicts:
        s.bus.emit("coordinator", "conflict", msg)
    s.candidates = await scout(yumi, c, s.profile, s.bus)
    return s.view()


@app.get("/api/sessions/{sid}")
def get_session(sid: str) -> dict:
    return _session(sid).view()


@app.get("/api/sessions/{sid}/events")
async def events(sid: str):
    s = _session(sid)
    q = s.bus.subscribe()

    async def gen():
        try:
            while True:
                ev = await q.get()
                yield {"event": "log", "data": json.dumps({"ev": ev, "session": s.view()}, ensure_ascii=False)}
        finally:
            s.bus.unsubscribe(q)

    return EventSourceResponse(gen())


@app.post("/api/sessions/{sid}/ask")
async def ask(sid: str, request: Request) -> dict:
    s = _session(sid)
    _guard_real(request, s)
    if s.state not in ("idle", "exhausted"):
        raise HTTPException(409, "이미 문의 중이에요")
    if not s.candidates:
        raise HTTPException(400, "후보가 없어요")
    s.spawn(start_asking(yumi, s))
    return {"ok": True}


@app.post("/api/sessions/{sid}/approve")
async def approve(sid: str, req: ApproveRequest, request: Request) -> dict:
    s = _session(sid)
    _guard_real(request, s)
    c = s.find(req.place_id)
    if not c or (s.now_mode and c.status not in POSITIVE):
        raise HTTPException(400, "사장님이 '가능'이라고 답한 가게만 예약할 수 있어요")
    if s.state == "reserving":
        raise HTTPException(409, "예약 진행 중이에요")
    s.phone = req.phone
    when = req.when or s.constraints.when
    guests = req.guests or s.constraints.party
    s.spawn(reserve_loop(yumi, s, req.place_id, when, guests, req.auto_fallback))
    return {"ok": True}


@app.get("/api/sessions/{sid}/notice")
def notice(sid: str) -> dict:
    return {"text": build_notice(_session(sid))}


@app.post("/api/sessions/{sid}/headcount")
async def headcount(sid: str, req: HeadcountRequest, request: Request) -> dict:
    s = _session(sid)
    _guard_real(request, s)
    if not s.reservation:
        raise HTTPException(400, "확정된 예약이 없어요")
    s.spawn(change_headcount(yumi, s, req.guests))
    return {"ok": True}


@app.post("/api/sessions/{sid}/afterparty")
async def afterparty(sid: str) -> dict:
    s = _session(sid)
    if not s.reservation:
        raise HTTPException(400, "1차 예약이 먼저 필요해요")
    s.spawn(find_afterparty(yumi, s))
    return {"ok": True}


@app.post("/api/feedback")
def feedback(fb: Feedback) -> dict:
    store.add_visit(fb)
    return {"profile": build_profile(store.visits(fb.group_id)).model_dump()}


# ---------- 실매장 테스트(예: 하이드미플리즈 을지로) ----------
LAB_PLACES: dict = {}


@app.get("/api/lab/lookup")
async def lab_lookup(q: str) -> dict:
    """이름으로 가게 하나 찾기. 읽기 전용이라 사장님께 아무것도 가지 않는다."""
    try:
        raw = await yumi.lookup(q.strip())
    except YumiError as e:
        raise HTTPException(502, f"검색 실패 ({e.code})")
    out = []
    for r in raw:
        p = Place.model_validate(r["_place"]) if "_place" in r else normalize_place(r)
        LAB_PLACES[p.id] = p
        out.append({"place": p.model_dump(), "hours": r.get("businessHours") or [],
                    "channels": r.get("reservationChannels") or [], "reservable": bool(r.get("yumiReservable", p.reservable_here)),
                    "placeUrl": r.get("placeUrl"), "demo": bool(r.get("demo"))})
    return {"results": out, "mode": describe_mode(), "live": settings.yumi_live}


class LabIn(BaseModel):
    place_id: str
    party: int = Field(default=2, ge=1, le=50)
    when: str | None = None
    group_id: str = "lab"


@app.post("/api/lab/session")
def lab_session(req: LabIn, request: Request) -> dict:
    if settings.yumi_live:
        _local_only(request)
    p = LAB_PLACES.get(req.place_id)
    if not p:
        raise HTTPException(404, "먼저 가게를 검색해 주세요")
    c = Constraints(area=p.station or "직접 지정", party=req.party, when=req.when, lat=p.lat, lng=p.lng)
    s = Session(group_id=req.group_id, constraints=c, profile=build_profile([]))
    s.candidates = [Candidate(place=p, evidence=[Evidence(kind="data", label="직접 고른 가게")])]
    s.now_mode, s.script, s.lab = is_now(req.when), False, True
    SESSIONS[s.id] = s
    s.bus.emit("negotiator", "plan", f"실매장 테스트: {p.name} 한 곳만, 다른 가게로 넘어가지 않아요 · {describe_mode()['label']}")
    return s.view()


app.mount("/static", StaticFiles(directory=WEB), name="static")


@app.get("/")
def index() -> FileResponse:
    return FileResponse(WEB / "index.html")


@app.get("/classic")
def classic() -> FileResponse:
    return FileResponse(WEB / "classic.html")
