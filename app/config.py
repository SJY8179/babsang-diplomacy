import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")


# 공개 배포(누구나 접속)용. 켜면 .env에 무엇을 적어도 사장님께 가는 요청은 열리지 않는다.
_PUBLIC = os.getenv("PUBLIC_DEMO", "0") == "1"


@dataclass(frozen=True)
class Settings:
    yumi_mode: str = os.getenv("YUMI_MODE", "mock")
    yumi_api_key: str = os.getenv("YUMI_API_KEY", "")
    yumi_base_url: str = os.getenv("YUMI_BASE_URL", "https://api.heyyumi.ai/api/v1")
    # 사장님께 가는 요청(자리 문의·예약)을 어떻게 처리할지. 기본은 simulate = Yumi로 아예 보내지 않음.
    # simulate | sandbox | live.  live는 YUMI_LIVE=1 까지 같이 있어야 열린다(이중 잠금).
    yumi_actions: str = "simulate" if _PUBLIC else os.getenv("YUMI_ACTIONS", "simulate")
    yumi_live: bool = (not _PUBLIC) and os.getenv("YUMI_ACTIONS", "simulate") == "live" and os.getenv("YUMI_LIVE", "0") == "1"
    public_demo: bool = _PUBLIC
    # 실제 요청을 이 가게들에만 허용(쉼표 구분 placeId). 나머지는 전부 시뮬레이션.
    live_places: tuple = tuple(x.strip() for x in os.getenv("YUMI_LIVE_PLACES", "").split(",") if x.strip())
    demo_script: bool = os.getenv("DEMO_SCRIPT", "1") == "1"
    odsay_key: str = os.getenv("ODSAY_API_KEY", "")
    kakao_rest_key: str = os.getenv("KAKAO_REST_KEY", "")
    public_base_url: str = os.getenv("PUBLIC_BASE_URL", "http://localhost:8000")
    llm_api_key: str = os.getenv("LLM_API_KEY", "")
    llm_model: str = os.getenv("LLM_MODEL", "claude-sonnet-5-5")
    db_path: Path = ROOT / "data" / "yumi.db"


settings = Settings()
