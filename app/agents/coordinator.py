"""① 조율 에이전트: 단톡방 텍스트 → Constraints.

규칙 기반 파서가 기본이고, LLM_API_KEY가 있으면 LLM 결과로 덮어쓴다(실패하면 규칙 결과 유지).
가게 사실은 여기서 만들지 않는다. 조건만 뽑는다.
"""
import json
import re
from datetime import datetime, timedelta

import httpx

from app.config import settings
from app.events import KST, now_kst
from app.models import Constraints

AREAS = {
    "을지로": (37.5660, 126.9826), "종로": (37.5704, 126.9921), "광화문": (37.5714, 126.9768),
    "시청": (37.5657, 126.9769), "명동": (37.5609, 126.9863), "서울역": (37.5547, 126.9707),
    "강남": (37.4979, 127.0276), "역삼": (37.5006, 127.0364), "홍대": (37.5572, 126.9245),
    "성수": (37.5446, 127.0559), "여의도": (37.5216, 126.9243), "판교": (37.3948, 127.1112),
    "마포·용산": (37.5443, 126.9516), "공덕": (37.5443, 126.9516), "합정": (37.5495, 126.9137), "신촌": (37.5552, 126.9369),
    "용산": (37.5299, 126.9648), "이태원": (37.5345, 126.9946), "마포": (37.5395, 126.9459),
}
STATIONS = {"을지로": "을지로입구역", "종로": "종각역", "광화문": "광화문역", "시청": "시청역", "명동": "명동역",
            "서울역": "서울역", "강남": "강남역", "역삼": "역삼역", "홍대": "홍대입구역", "성수": "성수역",
            "여의도": "여의도역", "판교": "판교역", "마포·용산": "공덕역", "공덕": "공덕역", "합정": "합정역", "신촌": "신촌역",
            "용산": "용산역", "이태원": "이태원역", "마포": "마포역"}
WEEKDAYS = {"월": 0, "화": 1, "수": 2, "목": 3, "금": 4, "토": 5, "일": 6}


def _when(text: str, lunch: bool) -> str:
    base = now_kst()
    if re.search(r"지금|바로|당장|곧", text) and not re.search(r"\d{1,2}\s*시", text):
        return (base + timedelta(minutes=10)).replace(second=0, microsecond=0).isoformat(timespec="seconds")
    day = base.date()
    if "내일" in text:
        day += timedelta(days=1)
    elif "모레" in text:
        day += timedelta(days=2)
    else:
        m = re.search(r"([월화수목금토일])요일", text)
        if m:
            delta = (WEEKDAYS[m.group(1)] - base.weekday()) % 7
            if "다음 주" in text or "다음주" in text:
                delta += 7 if delta else 7
            day += timedelta(days=delta)
    hour, minute = (12, 0) if lunch else (19, 0)
    m = re.search(r"(오전|오후|저녁|점심)?\s*(\d{1,2})\s*시\s*(반|(\d{1,2})\s*분)?", text)
    if m:
        hour = int(m.group(2))
        if m.group(1) in ("오후", "저녁") and hour < 12:
            hour += 12
        elif m.group(1) is None and not lunch and hour <= 10:
            hour += 12
        minute = 30 if m.group(3) == "반" else int(m.group(4) or 0)
    dt = datetime(day.year, day.month, day.day, hour, minute, tzinfo=KST)
    if dt < base:
        dt += timedelta(days=1)
    return dt.isoformat(timespec="seconds")


def parse_rules(text: str) -> Constraints:
    t = text.replace(",", " ")
    c = Constraints()
    for name, (lat, lng) in AREAS.items():
        if name in t:
            c.area, c.lat, c.lng, c.region_name = name, lat, lng, STATIONS[name]
            break
    if m := re.search(r"(\d{1,2})\s*(명|인)", t):
        c.party = int(m.group(1))
    if m := re.search(r"(?:1인|인당|한\s*사람)?\s*(\d+(?:\.\d+)?)\s*만\s*원?", t):
        c.max_price = int(float(m.group(1)) * 10000)
    lunch = "점심" in t
    if re.search(r"거래처|접대|미팅|클라이언트", t):
        c.context = "business_meeting"
    c.when = _when(t, lunch)

    def want(attr: str, pattern: str) -> None:
        if not re.search(pattern, t):
            return
        strong = re.search(pattern + r".{0,6}(필수|꼭|무조건|있어야)", t) or re.search(r"(꼭|무조건|필수).{0,6}" + pattern, t)
        (c.must if strong else c.nice).append(attr)

    want("private_room", r"(룸|방|프라이빗)")
    want("parking", r"주차")
    want("corkage_free", r"콜키지")
    if c.party >= 8 and "group_friendly" not in c.must:
        c.nice.append("group_friendly")
    if re.search(r"매운|맵", t):
        c.avoid.append("매운")
    if re.search(r"비건|채식", t):
        c.dietary.append("vegan_options")
    if c.max_price and c.max_price < 25000 and "private_room" in c.must:
        c.conflicts.append("1인 2.5만 원 미만에서 룸 필수 조건은 후보가 적을 수 있어요.")
    return c


SYSTEM = (
    "너는 회식 조건 정리기다. 사용자가 붙여 넣은 단톡방 대화에서 조건만 뽑아 JSON 하나로만 답한다. "
    "키: area(동네 이름), party(int), max_price(1인 원, int|null), context(group_dining|business_meeting|family), "
    "must(배열, 값은 private_room|parking|group_friendly|corkage_free 중), nice(같은 값), avoid(이름·카테고리 제외 키워드 배열), "
    "dietary(vegan_options|vegetarian_options|gluten_free 중), conflicts(서로 충돌하는 조건 설명 문장 배열). "
    "대화에 없는 값은 지어내지 말고 null 또는 빈 배열로 둔다."
)


async def parse_llm(text: str) -> dict | None:
    if not settings.llm_api_key:
        return None
    try:
        async with httpx.AsyncClient(timeout=30) as http:
            r = await http.post(
                "https://api.anthropic.com/v1/messages",
                headers={"x-api-key": settings.llm_api_key, "anthropic-version": "2023-06-01"},
                json={"model": settings.llm_model, "max_tokens": 600, "temperature": 0, "system": SYSTEM,
                      "messages": [{"role": "user", "content": text}]},
            )
            r.raise_for_status()
            raw = "".join(b.get("text", "") for b in r.json().get("content", []))
            m = re.search(r"\{.*\}", raw, re.S)
            return json.loads(m.group(0)) if m else None
    except (httpx.HTTPError, json.JSONDecodeError, ValueError):
        return None


async def coordinate(text: str) -> tuple[Constraints, str]:
    """(조건, 사용한 방식)"""
    c = parse_rules(text)
    llm = await parse_llm(text)
    if not llm:
        return c, "rules"
    allowed = {"private_room", "parking", "group_friendly", "corkage_free"}
    if llm.get("area") in AREAS:
        c.area = llm["area"]
        c.lat, c.lng = AREAS[c.area]
        c.region_name = STATIONS[c.area]
    for k in ("party", "max_price"):
        if isinstance(llm.get(k), int) and llm[k] > 0:
            setattr(c, k, llm[k])
    if llm.get("context") in ("group_dining", "business_meeting", "family"):
        c.context = llm["context"]
    for k in ("must", "nice"):
        if isinstance(llm.get(k), list):
            setattr(c, k, [a for a in llm[k] if a in allowed])
    for k in ("avoid", "dietary", "conflicts"):
        if isinstance(llm.get(k), list):
            setattr(c, k, [str(x) for x in llm[k]][:5])
    return c, "llm"
