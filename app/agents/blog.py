"""블로그 초안: 방문 기록에 있는 사실만 쓴다. LLM_API_KEY가 있으면 문장만 다듬고, 없으면 템플릿."""
import httpx

from app.config import settings

SYSTEM = ("너는 회식 후기 초안을 쓰는 사람이다. 주어진 사실(가게, 날짜, 1인 지출, 만족도, 재방문 여부, 메뉴)만 써라. "
          "없는 메뉴·맛 평가·숫자를 만들지 마라. 4문장 이내, 담백한 존댓말, 과장 금지.")


def template(group: str, v: dict) -> str:
    date = v["visited_at"][5:].replace("-", "월 ").lstrip("0") + "일"
    lines = [f"{date}, {group}은 {v['place_name']}에서 모였습니다."]
    if v.get("per_person"):
        lines.append(f"1인 {v['per_person']:,}원 정도 나왔습니다.")
    lines.append(f"만족도는 5점 중 {v['satisfaction']:g}점이었고, "
                 + ("다음에도 다시 가고 싶다는 의견이 많았습니다." if v["revisit"] else "다음에는 다른 곳을 찾아보기로 했습니다."))
    return " ".join(lines)


async def draft(group: str, v: dict) -> tuple[str, str]:
    base = template(group, v)
    if not settings.llm_api_key:
        return base, "template"
    try:
        async with httpx.AsyncClient(timeout=20) as http:
            r = await http.post("https://api.anthropic.com/v1/messages",
                                headers={"x-api-key": settings.llm_api_key, "anthropic-version": "2023-06-01"},
                                json={"model": settings.llm_model, "max_tokens": 400, "temperature": 0.3,
                                      "system": SYSTEM, "messages": [{"role": "user", "content": f"사실: {base}"}]})
            r.raise_for_status()
            text = "".join(b.get("text", "") for b in r.json().get("content", [])).strip()
            return (text or base), "llm"
    except (httpx.HTTPError, ValueError):
        return base, "template"
