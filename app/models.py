from typing import Literal

from pydantic import BaseModel, Field

AskStatus = Literal[
    "idle", "asking", "available", "limited", "unavailable",
    "soon", "not_offered", "no_response", "closed_now", "error",
]
POSITIVE = {"available", "limited"}
TERMINAL = POSITIVE | {"unavailable", "soon", "not_offered", "no_response", "closed_now", "error"}


class Constraints(BaseModel):
    area: str = "을지로"
    region_name: str | None = None    # Yumi region_name (역·동·상권 이름)
    lat: float | None = None
    lng: float | None = None
    party: int = 8
    when: str | None = None          # ISO8601 +09:00
    max_price: int | None = None      # 1인 원
    context: str = "group_dining"     # recommended_for
    must: list[str] = Field(default_factory=list)   # 불리언 속성, 반드시
    nice: list[str] = Field(default_factory=list)   # 불리언 속성, 되면 좋음
    avoid: list[str] = Field(default_factory=list)  # 이름·카테고리에 들어가면 제외할 키워드
    dietary: list[str] = Field(default_factory=list)
    conflicts: list[str] = Field(default_factory=list)
    exclude: list[str] = Field(default_factory=list)      # Yumi exclude (전문점 제외: 알레르기 등)
    atmosphere: list[str] = Field(default_factory=list)   # 선호(정렬용): quiet, cozy, lively ...
    serves: list[str] = Field(default_factory=list)       # 선호: alcohol ...
    subtypes: list[str] = Field(default_factory=list)     # 선호 음식 종류: korean, italian ...


class Place(BaseModel):
    id: str
    name: str
    lat: float | None = None
    lng: float | None = None
    category: str | None = None
    price: int | None = None          # 1인 대략 가격(원)
    attrs: list[str] = Field(default_factory=list)
    recommended_for: list[str] = Field(default_factory=list)
    confidence: float | None = None
    freshness: float | None = None
    possibly_closed: bool = False
    closure_signal: bool = False
    station: str | None = None
    walk_min: int | None = None
    address: str | None = None
    review_count: int | None = None
    reservable_here: bool = False      # yumiReservable: 앱 안에서 예약·문의 가능한 파트너
    atmosphere: list[str] = Field(default_factory=list)
    subtype: str | None = None
    serves: list[str] = Field(default_factory=list)
    dietary: list[str] = Field(default_factory=list)


class Evidence(BaseModel):
    kind: Literal["data", "owner", "memory", "unknown"]
    label: str
    source: str | None = None


class Candidate(BaseModel):
    place: Place
    score: float = 0.0
    evidence: list[Evidence] = Field(default_factory=list)
    status: AskStatus = "idle"
    status_at: str | None = None
    distance_m: int | None = None
    tried_reservation: bool = False
    travel: dict[str, int] = Field(default_factory=dict)  # 참석자 이름 → 분
    travel_source: str | None = None
    reason: str | None = None
    checks: dict[str, str] = Field(default_factory=dict)  # 식단·예산·분위기·주류 → 충족/미충족/확인 필요
    total: int | None = None                              # 0~100


class Reservation(BaseModel):
    place_id: str
    place_name: str
    when: str
    guests: int
    status: str = "pending"
    reservation_id: str | None = None


class Feedback(BaseModel):
    group_id: str = Field(max_length=60)
    place_id: str = Field(max_length=60)
    place_name: str = Field(min_length=1, max_length=60)
    attrs: list[str] = Field(default_factory=list, max_length=20)
    satisfaction: float = Field(ge=1, le=5)
    revisit: bool
    per_person: int | None = Field(default=None, ge=0, le=1_000_000)


class PlanRequest(BaseModel):
    group_id: str = "demo"
    text: str | None = None
    form: Constraints | None = None


class ApproveRequest(BaseModel):
    place_id: str
    phone: str
    when: str | None = None
    guests: int | None = None
    auto_fallback: bool = True


class HeadcountRequest(BaseModel):
    guests: int = Field(ge=1, le=60)
