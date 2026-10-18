"""③ 교섭 에이전트: 사장님께 묻고(live-status), 승인 후 예약하고, 거절되면 다음 후보로 넘어간다.

규칙: 동시 문의 최대 3곳, 예약은 한 번에 한 곳, 422는 재시도 안 함, 전화번호는 로그에 남기지 않는다.
"""
import asyncio
import uuid
from collections.abc import Awaitable, Callable
from datetime import datetime

from app.config import settings
from app.events import now_kst
from app.models import POSITIVE, TERMINAL, Candidate, Evidence, Reservation
from app.session import Session
from app.yumi.client import ActionBlocked, YumiClient, YumiError

MAX_PARALLEL = 3
NOW_WINDOW_MIN = 90  # live-status는 '지금' 질문이라, 이보다 먼 시간은 예약 요청이 곧 사장님 확인
ASK_TIMEOUT_S = 360
STATUS_KO = {
    "available": "가능", "limited": "조금 남음", "unavailable": "불가", "soon": "곧 자리 남",
    "not_offered": "문의 미지원", "no_response": "답 없음", "closed_now": "영업 전·후", "error": "오류",
}
DEMO_ASK = ["unavailable", "available", "limited"]
DEMO_RESERVE = ["cancelled", "confirmed"]


def mask(phone: str) -> str:
    digits = "".join(ch for ch in phone if ch.isdigit())
    return f"{digits[:3]}-****-{digits[-4:]}" if len(digits) >= 7 else "***"


def is_now(when: str | None) -> bool:
    if not when:
        return True
    return (datetime.fromisoformat(when) - now_kst()).total_seconds() <= NOW_WINDOW_MIN * 60


def _demo(seq: list[str], i: int) -> str | None:
    if not settings.demo_script or (settings.yumi_live and not settings.live_places):
        return None
    return seq[i] if i < len(seq) else seq[-1]


async def ask_one(yumi: YumiClient, s: Session, c: Candidate, party: int, outcome: str | None,
                  agent: str = "negotiator") -> str:
    c.status = "asking"
    s.bus.emit(agent, "ask", f"{c.place.name} 사장님께 '{party}명 자리' 문의", placeId=c.place.id)
    t0 = asyncio.get_event_loop().time()
    try:
        qid = await yumi.ask(c.place.id, "seats", f"{party}명 입장", outcome)
        while True:
            res = await yumi.ask_result(qid, wait=25)
            if res["status"] in TERMINAL:
                c.status = res["status"]
                break
            if asyncio.get_event_loop().time() - t0 > ASK_TIMEOUT_S:
                c.status = "no_response"
                break
    except ActionBlocked as e:
        c.status = "error"
        s.bus.emit(agent, "error", str(e), placeId=c.place.id)
    except YumiError as e:
        c.status = "not_offered" if e.status == 422 else "error"
        s.bus.emit(agent, "error", f"{c.place.name}: 문의할 수 없는 가게예요 ({e.code})", placeId=c.place.id)
    secs = int(asyncio.get_event_loop().time() - t0)
    c.status_at = now_kst().strftime("%H:%M")
    c.evidence = [e for e in c.evidence if e.kind != "owner"]
    if c.status in POSITIVE:
        c.evidence.insert(0, Evidence(kind="owner", label=f"사장님 확인: {STATUS_KO[c.status]}", source=c.status_at))
    s.bus.emit(agent, "answer", f"{c.place.name} 사장님: {STATUS_KO.get(c.status, c.status)} ({secs}초)",
               placeId=c.place.id, status=c.status)
    return c.status


async def ask_many(yumi: YumiClient, s: Session, cands: list[Candidate], party: int, agent: str,
                   on_positive: Callable[[Candidate], Awaitable[None]] | None = None) -> None:
    targets = cands[:MAX_PARALLEL]

    async def run(i: int, c: Candidate) -> None:
        status = await ask_one(yumi, s, c, party, _demo(DEMO_ASK, i) if s.script else None, agent)
        if status in POSITIVE and on_positive:
            await on_positive(c)

    await asyncio.gather(*(run(i, c) for i, c in enumerate(targets)))


async def start_asking(yumi: YumiClient, s: Session) -> None:
    if not s.now_mode:
        # 사장님 실시간 문의는 '지금 자리' 질문이다. 다른 날·먼 시간은 예약 요청 자체가 사장님 확인이 된다.
        s.state = "await_approval"
        top = s.candidates[0]
        s.bus.emit("negotiator", "plan",
                   f"{s.constraints.when[5:16].replace('T', ' ')} 회식은 실시간 문의 대상이 아니라 예약 요청으로 사장님께 확인해요. " +
                   (f"{top.place.name} 한 곳에만 보내요." if s.lab else f"1순위 {top.place.name}부터 보내고, 거절되면 다음 순위로 넘어갈게요."),
                   placeId=top.place.id)
        s.bus.emit("negotiator", "approval", f"{top.place.name}에 예약 요청을 보낼까요?", placeId=top.place.id)
        return
    s.state = "asking"

    async def first_positive(c: Candidate) -> None:
        if s.state == "asking":
            s.state = "await_approval"
            s.bus.emit("negotiator", "approval", f"{c.place.name}에서 먼저 '가능'이라고 답했어요. 예약할까요?",
                       placeId=c.place.id)

    await ask_many(yumi, s, s.candidates, s.constraints.party, "negotiator", first_positive)
    if s.state == "asking":
        s.state = "exhausted"
        s.bus.emit("negotiator", "exhausted", "문의한 가게 모두 자리가 없어요. 조건을 조금 풀어 다시 찾아볼까요?")


def _next_positive(s: Session) -> Candidate | None:
    ok = (lambda c: True) if not s.now_mode else (lambda c: c.status in POSITIVE)
    return next((c for c in s.candidates[:MAX_PARALLEL + 1] if ok(c) and not c.tried_reservation), None)


async def reserve_loop(yumi: YumiClient, s: Session, place_id: str, when: str, guests: int,
                       auto_fallback: bool) -> None:
    target = s.find(place_id)
    while target:
        s.state = "reserving"
        target.tried_reservation = True
        s.bus.emit("negotiator", "reserve",
                   f"{target.place.name}에 예약 요청 ({guests}명, {when[11:16]}, 연락처 {mask(s.phone or '')})",
                   placeId=target.place.id)
        try:
            rid = await yumi.reserve(target.place.id, when, guests, s.phone or "", uuid.uuid4().hex,
                                     note="밥상외교 회식 예약", outcome=_demo(DEMO_RESERVE, s.attempts) if s.script else None)
            s.attempts += 1
            status = "pending"
            t0 = asyncio.get_event_loop().time()
            while status == "pending" and asyncio.get_event_loop().time() - t0 < ASK_TIMEOUT_S:
                status = (await yumi.reservation_result(rid, wait=25))["status"]
        except ActionBlocked as e:
            s.bus.emit("negotiator", "error", str(e))
            s.state = "exhausted"
            return
        except YumiError as e:
            rid, status = None, "cancelled"
            s.bus.emit("negotiator", "error", f"예약 요청 실패 ({e.code})")

        if status == "confirmed":
            s.state = "confirmed"
            s.reservation = Reservation(place_id=target.place.id, place_name=target.place.name, when=when,
                                        guests=guests, status="confirmed", reservation_id=rid)
            s.bus.emit("negotiator", "confirmed", f"{target.place.name} 예약 확정 · {when[5:10]} {when[11:16]} · {guests}명",
                       placeId=target.place.id)
            return
        s.bus.emit("negotiator", "rejected", f"{target.place.name} 예약이 성사되지 않았어요 ({status})",
                   placeId=target.place.id)
        target = _next_positive(s) if auto_fallback else None
        if target:
            s.bus.emit("negotiator", "fallback", f"다음 후보로 바로 넘어갈게요: {target.place.name}",
                       placeId=target.place.id)
    s.state = "await_approval" if _next_positive(s) else "exhausted"
    if s.state == "exhausted":
        s.bus.emit("negotiator", "exhausted", "예약 가능한 후보가 남지 않았어요.")


async def change_headcount(yumi: YumiClient, s: Session, guests: int) -> None:
    r = s.reservation
    if not r:
        return
    if not is_now(r.when):
        s.bus.emit("negotiator", "headcount_ok",
                   f"{r.place_name} 예약을 {r.guests}명 → {guests}명으로 바꾸려면 가게에 직접 요청해 주세요(예약 변경 API 없음). "
                   "당일 회식 직전이면 여기서 사장님께 바로 물어볼 수 있어요.")
        return
    s.bus.emit("negotiator", "headcount", f"인원 변경 {r.guests}명 → {guests}명, 확정한 가게부터 다시 물어볼게요")
    cur = s.find(r.place_id)
    status = await ask_one(yumi, s, cur, guests, _demo(["available"], 0)) if cur else "error"
    if status in POSITIVE:
        s.bus.emit("negotiator", "headcount_ok",
                   f"{r.place_name}에서 {guests}명도 가능하대요. 예약 인원 변경은 가게에 직접 요청해 주세요(변경 API 없음).")
        return
    others = [c for c in s.candidates if c.status in POSITIVE and c.place.id != r.place_id]
    for c in others:
        c.tried_reservation = False
    if not others:
        s.bus.emit("negotiator", "headcount_fail", "다른 후보도 없어요. 가게에 직접 상의가 필요해요.")
        return
    await ask_many(yumi, s, others, guests, "negotiator")
    nxt = _next_positive(s)
    if nxt:
        s.state = "await_approval"
        s.bus.emit("negotiator", "approval",
                   f"{nxt.place.name}은 {guests}명 가능해요. 새로 예약하려면 승인해 주세요. 기존 예약은 직접 취소해야 해요.",
                   placeId=nxt.place.id)
