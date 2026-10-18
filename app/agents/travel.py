"""이동 시간 에이전트: 참석자 출발지 → 후보 가게.

- ODSAY_API_KEY 있으면 ODsay 대중교통 길찾기(실제 소요 시간)
- 없으면 직선거리 기반 추정(화면에 '추정'으로 표시). 지어낸 값이 아니라 공식이 정해진 근사다.
- 출발지(역 이름) 좌표: KAKAO_REST_KEY 있으면 카카오 로컬 검색, 없으면 아래 주요 역 좌표표.
"""
import asyncio

import httpx

from app.config import settings
from app.geo import dist_m

# 주요 역 좌표(근사). 표에 없는 역은 카카오 키가 있어야 찾을 수 있다.
STATION_XY: dict[str, tuple[float, float]] = {
    "서울역": (37.5547, 126.9707), "시청": (37.5657, 126.9769), "을지로입구": (37.5660, 126.9826),
    "을지로3가": (37.5663, 126.9910), "종각": (37.5702, 126.9831), "광화문": (37.5714, 126.9768),
    "안국": (37.5765, 126.9854), "명동": (37.5609, 126.9863), "충무로": (37.5612, 126.9942),
    "동대문역사문화공원": (37.5657, 127.0089), "신촌": (37.5552, 126.9369), "이대": (37.5567, 126.9460),
    "홍대입구": (37.5572, 126.9245), "합정": (37.5495, 126.9137), "상수": (37.5478, 126.9229),
    "마포": (37.5395, 126.9459), "공덕": (37.5443, 126.9516), "애오개": (37.5536, 126.9567),
    "용산": (37.5299, 126.9648), "삼각지": (37.5347, 126.9731), "이태원": (37.5345, 126.9946),
    "한강진": (37.5396, 127.0017), "녹사평": (37.5345, 126.9867), "여의도": (37.5216, 126.9243),
    "영등포구청": (37.5249, 126.8958), "강남": (37.4979, 127.0276), "역삼": (37.5006, 127.0364),
    "선릉": (37.5045, 127.0490), "삼성": (37.5089, 127.0631), "교대": (37.4934, 127.0141),
    "신논현": (37.5045, 127.0250), "잠실": (37.5133, 127.1001), "건대입구": (37.5404, 127.0692),
    "성수": (37.5446, 127.0559), "왕십리": (37.5612, 127.0371), "신당": (37.5658, 127.0176),
    "혜화": (37.5822, 127.0019), "사당": (37.4765, 126.9816), "신림": (37.4842, 126.9297),
    "구로디지털단지": (37.4852, 126.9015), "판교": (37.3948, 127.1112), "수원": (37.2664, 127.0001),
}


def _key(name: str) -> str:
    return name.strip().removesuffix("역").strip()


async def geocode(name: str) -> tuple[float, float] | None:
    k = _key(name)
    for cand in (name.strip(), k, f"{k}역"):
        if cand in STATION_XY:
            return STATION_XY[cand]
    if not settings.kakao_rest_key:
        return None
    try:
        async with httpx.AsyncClient(timeout=8) as http:
            r = await http.get("https://dapi.kakao.com/v2/local/search/keyword.json",
                               params={"query": name if name.endswith("역") else f"{name}역", "size": 1},
                               headers={"Authorization": f"KakaoAK {settings.kakao_rest_key}"})
            docs = r.json().get("documents", [])
            if docs:
                xy = (float(docs[0]["y"]), float(docs[0]["x"]))
                STATION_XY[k] = xy
                return xy
    except (httpx.HTTPError, ValueError, KeyError):
        return None
    return None


def estimate_min(a: tuple[float, float], b: tuple[float, float]) -> int:
    """직선거리 × 1.3(굴곡) ÷ 대중교통 평균 20km/h + 대기·도보 8분."""
    meters = dist_m(a[0], a[1], b[0], b[1]) * 1.3
    return max(5, round(meters / 333 + 8))


async def _odsay_min(a: tuple[float, float], b: tuple[float, float], http: httpx.AsyncClient) -> int | None:
    try:
        r = await http.get("https://api.odsay.com/v1/api/searchPubTransPathT",
                           params={"SX": a[1], "SY": a[0], "EX": b[1], "EY": b[0], "apiKey": settings.odsay_key})
        paths = r.json().get("result", {}).get("path", [])
        return int(paths[0]["info"]["totalTime"]) if paths else None
    except (httpx.HTTPError, ValueError, KeyError, IndexError, TypeError):
        return None


async def travel_table(origins: dict[str, tuple[float, float]], dest: tuple[float, float]) -> tuple[dict[str, int], str]:
    """{이름: 분}, 출처('대중교통 길찾기' | '직선거리 추정')."""
    if settings.odsay_key:
        async with httpx.AsyncClient(timeout=10) as http:
            names = list(origins)
            mins = await asyncio.gather(*(_odsay_min(origins[n], dest, http) for n in names))
        if all(m is not None for m in mins):
            return dict(zip(names, mins)), "대중교통 길찾기(ODsay)"
    return {n: estimate_min(xy, dest) for n, xy in origins.items()}, "직선거리 기반 추정"
