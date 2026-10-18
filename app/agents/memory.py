"""④ 기억 에이전트: 다녀온 평가를 모임 프로필로 바꾼다. LLM을 쓰지 않는다."""
from collections import Counter
from statistics import median

from pydantic import BaseModel, Field

ATTR_KO = {"private_room": "룸", "parking": "주차", "group_friendly": "단체석", "corkage_free": "콜키지 프리"}


class Profile(BaseModel):
    visits: int = 0
    good: int = 0
    price_center: int | None = None
    liked_attrs: list[str] = Field(default_factory=list)
    liked_places: list[str] = Field(default_factory=list)
    excluded_places: list[str] = Field(default_factory=list)
    excluded_names: list[str] = Field(default_factory=list)
    summary: str = "아직 기록된 회식이 없어요."


def build_profile(visits: list[dict]) -> Profile:
    if not visits:
        return Profile()
    good = [v for v in visits if v["satisfaction"] >= 4]
    prices = [v["per_person"] for v in good if v.get("per_person")]
    attrs = Counter(a for v in good for a in v["attrs"])
    excluded = [v for v in visits if not v["revisit"] and v["satisfaction"] < 3]  # '보류'(3점 이상)는 빼지 않음
    p = Profile(
        visits=len(visits),
        good=len(good),
        price_center=int(median(prices)) if prices else None,
        liked_attrs=[a for a, n in attrs.most_common() if n >= 1],
        liked_places=sorted({v["place_id"] for v in visits if v["revisit"] and v["satisfaction"] >= 4}),
        excluded_places=sorted({v["place_id"] for v in excluded}),
        excluded_names=sorted({v["place_name"] for v in excluded}),
    )
    p.summary = summarize(p)
    return p


def summarize(p: Profile) -> str:
    parts = [f"지난 회식 {p.visits}건 중 만족 {p.good}건"]
    if p.price_center:
        parts.append(f"만족한 회식은 1인 {p.price_center / 10000:.1f}만 원 안팎")
    if p.liked_attrs:
        parts.append("좋았던 조건: " + ", ".join(ATTR_KO.get(a, a) for a in p.liked_attrs[:3]))
    if p.excluded_names:
        parts.append("다시 안 갈 곳: " + ", ".join(p.excluded_names[:2]))
    text = " · ".join(parts)
    if p.visits < 3:
        text += " (기록이 적어 참고만 합니다)"
    return text


def memory_weight(place_id: str, attrs: list[str], price: int | None, p: Profile) -> float:
    """0~1. 기록이 없으면 0.5(중립)."""
    if p.visits == 0:
        return 0.5
    w = 0.0
    if place_id in p.liked_places:
        w += 0.5
    if p.liked_attrs:
        w += 0.3 * len(set(attrs) & set(p.liked_attrs)) / len(p.liked_attrs)
    if p.price_center and price:
        w += 0.2 * max(0.0, 1 - abs(price - p.price_center) / (p.price_center * 0.4))
    return min(1.0, w)
