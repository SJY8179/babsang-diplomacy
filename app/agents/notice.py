"""⑤ 공지문: 확정된 값만 템플릿에 넣는다. 없는 값은 그 줄을 뺀다. LLM 없음."""
from datetime import datetime
from urllib.parse import quote

from app.session import Session

WEEK = "월화수목금토일"


def build_notice(s: Session) -> str:
    r = s.reservation
    if not r:
        return ""
    c = s.find(r.place_id)
    dt = datetime.fromisoformat(r.when)
    lines = [f"{dt.month}월 {dt.day}일({WEEK[dt.weekday()]}) 회식 장소 공유드립니다.",
             f"· 장소: {r.place_name}",
             f"· 시간: {dt.hour}시{f' {dt.minute}분' if dt.minute else ''}",
             f"· 인원: {r.guests}명 (예약 확정)"]
    if c:
        if "private_room" in c.place.attrs:
            lines.append("· 룸으로 잡았습니다")
        if c.place.price:
            lines.append(f"· 메뉴 평균 {c.place.price / 10000:.1f}만 원대")
        if c.place.station:
            walk = f" 도보 {c.place.walk_min}분" if c.place.walk_min else ""
            lines.append(f"· 가까운 역: {c.place.station}역{walk}")
        elif c.place.address:
            lines.append(f"· 주소: {c.place.address}")
        if c.place.lat and c.place.lng:
            lines.append(f"· 지도: https://map.kakao.com/link/map/{quote(c.place.name)},{c.place.lat:.6f},{c.place.lng:.6f}")
    lines.append("변경 사항 있으시면 말씀 부탁드립니다.")
    return "\n".join(lines)
