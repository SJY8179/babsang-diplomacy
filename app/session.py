import asyncio
import uuid
from dataclasses import dataclass, field
from typing import Literal

from app.agents.memory import Profile
from app.events import EventBus
from app.models import Candidate, Constraints, Reservation

State = Literal["idle", "asking", "await_approval", "reserving", "confirmed", "exhausted"]


@dataclass
class Session:
    group_id: str
    constraints: Constraints
    profile: Profile
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:10])
    bus: EventBus = field(default_factory=EventBus)
    candidates: list[Candidate] = field(default_factory=list)
    after: list[Candidate] = field(default_factory=list)
    state: State = "idle"
    reservation: Reservation | None = None
    phone: str | None = None  # 메모리에만, 로그·DB 금지
    attempts: int = 0
    now_mode: bool = True  # True면 지금 자리 문의(live-status), False면 예약 요청으로 확인
    meeting: dict | None = None  # 회식 모드: {id, title, must, nice, conflicts, count, area, travel_source}
    script: bool = True  # DEMO_SCRIPT 순서(불가→가능)를 쓸지. 실매장 테스트에서는 끈다
    lab: bool = False
    tasks: set[asyncio.Task] = field(default_factory=set)

    def spawn(self, coro) -> None:
        t = asyncio.create_task(coro)
        self.tasks.add(t)
        t.add_done_callback(self.tasks.discard)

    def find(self, place_id: str) -> Candidate | None:
        return next((c for c in self.candidates + self.after if c.place.id == place_id), None)

    def view(self) -> dict:
        return {
            "id": self.id, "groupId": self.group_id, "state": self.state, "nowMode": self.now_mode,
            "constraints": self.constraints.model_dump(), "profile": self.profile.model_dump(),
            "candidates": [c.model_dump() for c in self.candidates],
            "after": [c.model_dump() for c in self.after],
            "reservation": self.reservation.model_dump() if self.reservation else None,
            "meeting": self.meeting, "lab": self.lab,
        }


SESSIONS: dict[str, Session] = {}
