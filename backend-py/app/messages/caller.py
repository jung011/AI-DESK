"""caller account_sn 해결 — 보안 sweep 의 핵심 helper.

cookie-less 인 mcp daemon 호출도 *caller 의 own data 만* 보이게 만들기 위해, 두 경로 지원:
- cookie 인증된 user 가 있으면 user.account_sn 사용
- 그렇지 않으면 caller_agent_id (query) 의 agent 의 owner_account_sn 조회

둘 다 없으면 None — endpoint 가 fail(401) 처리.

옛 *caller filter 없음* 의 sameUser leak (task /recent rc88 / 이번 messages /audit 등)
의 공통 fix path.
"""
from sqlalchemy.orm import Session

from app.agents.repository import AgentRepository
from app.auth.schemas import AuthenticatedUser


def resolve_caller_account_sn(
    db: Session,
    user: AuthenticatedUser | None,
    caller_agent_id: str | None,
) -> int | None:
    """returns caller 의 account_sn 또는 None.

    우선순위:
      1. user (cookie/header JWT 인증) — 가장 신뢰
      2. caller_agent_id (mcp 의 query param) — agent 의 owner_account_sn 조회
      3. None — 인증 불가

    None 반환 시 caller 호출이 *익명* 이거나 *invalid agent_id* — endpoint 가 거부 처리.
    """
    if user is not None:
        return user.account_sn
    if caller_agent_id:
        agent_repo = AgentRepository(db)
        agent = agent_repo.find_by_agent_id_any_owner(caller_agent_id)
        if agent is not None:
            return agent.owner_account_sn
    return None
