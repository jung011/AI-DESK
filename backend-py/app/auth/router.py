"""auth router — endpoint stub. 실제 포팅 작업으로 채워짐."""
from fastapi import APIRouter

router = APIRouter()


@router.get("/_health")
async def health() -> dict[str, str]:
    """이 router 가 wire 됐는지 확인용. 도메인별 health probe."""
    return {"router": "auth", "status": "stub"}
