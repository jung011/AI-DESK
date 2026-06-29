"""desktop schemas — helper reporter payload."""
from pydantic import BaseModel, ConfigDict, Field


class WorkspaceItem(BaseModel):
    encoded_dir: str | None = Field(default=None, alias="encodedDir")
    workspace_dir: str | None = Field(default=None, alias="workspaceDir")
    latest_jsonl: str | None = Field(default=None, alias="latestJsonl")
    latest_mtime: str | None = Field(default=None, alias="latestMtime")
    age_sec: int | None = Field(default=None, alias="ageSec")
    status: str | None = None
    context_pct: int | None = Field(default=None, alias="contextPct")

    model_config = ConfigDict(populate_by_name=True)


class TmuxSessionItem(BaseModel):
    name: str | None = None
    created: int | None = None
    attached: bool | None = None
    # helper 0.8.57+ — session pane tree 안 claude process 살아있는지. False = claude
    # 종료됨 → status='offline' 강제 (zsh prompt 만 남은 tmux session 의 false idle 차단).
    claude_alive: bool | None = Field(default=None, alias="claudeAlive")

    model_config = ConfigDict(populate_by_name=True)


class DesktopLocalInfoRq(BaseModel):
    owner_employee_id: str | None = Field(default=None, alias="ownerEmployeeId")
    workspaces: list[WorkspaceItem] = Field(default_factory=list)
    tmux_sessions: list[TmuxSessionItem] = Field(default_factory=list, alias="tmuxSessions")
    # 옵션 B — helper 가 detect 박은 자기 LAN IP. 모바일 frontend 가 같은 wifi 박혀있을 때
    # helper 직접 호출 박을 IP. helper 가 0.0.0.0:30084 LISTEN 박혀있어 사용 가능.
    lan_ip: str | None = Field(default=None, alias="lanIp")

    model_config = ConfigDict(populate_by_name=True)


class DesktopLocalInfoRs(BaseModel):
    total_workspaces: int = Field(default=0, serialization_alias="totalWorkspaces")
    matched_agents: int = Field(default=0, serialization_alias="matchedAgents")
    updated_agents: int = Field(default=0, serialization_alias="updatedAgents")
    # B Phase 2 — broker subscribe list 동기화. helper 의 broker 가 backend ws 에
    # ?agentIds= 로 subscribe 할 agent_id 들. 매 reporter cycle 마다 갱신.
    matched_agent_ids: list[str] = Field(default_factory=list, serialization_alias="matchedAgentIds")

    model_config = ConfigDict(populate_by_name=True)
