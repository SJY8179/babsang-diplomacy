import asyncio
from datetime import datetime, timedelta, timezone

KST = timezone(timedelta(hours=9))


def now_kst() -> datetime:
    return datetime.now(KST)


class EventBus:
    """세션 하나의 작업 로그. 새로 붙은 구독자에게도 지난 이벤트를 다시 보낸다."""

    def __init__(self) -> None:
        self.history: list[dict] = []
        self._subs: list[asyncio.Queue] = []

    def emit(self, agent: str, type_: str, msg: str, **data) -> dict:
        ev = {"t": now_kst().strftime("%H:%M:%S"), "agent": agent, "type": type_, "msg": msg, "data": data}
        self.history.append(ev)
        for q in self._subs:
            q.put_nowait(ev)
        return ev

    def subscribe(self) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue()
        for ev in self.history:
            q.put_nowait(ev)
        self._subs.append(q)
        return q

    def unsubscribe(self, q: asyncio.Queue) -> None:
        if q in self._subs:
            self._subs.remove(q)
