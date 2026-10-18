"""실제 Hey Yumi 응답을 tests/fixtures/ 에 저장하고 키 목록을 출력한다.  python -m scripts.probe_yumi

검색만 한다(문의·예약 없음). 토큰: nearby 1회(4) + place 1회.
"""
import asyncio
import json
from pathlib import Path

import httpx

from app.config import settings
from app.yumi.client import _items, normalize_place

OUT = Path(__file__).resolve().parent.parent / "tests" / "fixtures"
LAT, LNG = 37.5660, 126.9826


async def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    h = {"Authorization": f"Bearer {settings.yumi_api_key}", "X-Map3-Sandbox": "1"}
    async with httpx.AsyncClient(base_url=settings.yumi_base_url, headers=h, timeout=40) as http:
        meta = (await http.get("/meta")).json()
        (OUT / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=1))
        print("meta keys:", list(meta)[:20] if isinstance(meta, dict) else type(meta))

        r = await http.get("/places/nearby", params={
            "lat": LAT, "lng": LNG, "radius": 1500, "recommended_for": "group_dining",
            "reservation_channel": "yumi", "fields": "core,quality,edge", "page_size": 30})
        print("nearby status:", r.status_code)
        data = r.json()
        (OUT / "nearby.json").write_text(json.dumps(data, ensure_ascii=False, indent=1))
        items = _items(data)
        print("top keys:", list(data)[:20] if isinstance(data, dict) else "list", "| items:", len(items))
        if items:
            print("first item keys:", sorted(items[0])[:60])
            print("normalized:", normalize_place(items[0]).model_dump())
            pid = normalize_place(items[0]).id
            one = (await http.get(f"/places/{pid}", params={"fields": "core,quality,edge"})).json()
            (OUT / "place.json").write_text(json.dumps(one, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    asyncio.run(main())
