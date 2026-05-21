/**
 * 백엔드 com.jsh.aidesk.serverapi.agents.vo 와 1:1 대응되는 타입.
 * 응답 envelope (ResponseJson<T>) 의 data 필드 타입.
 */

export type AgentStatus = 'active' | 'idle' | 'waiting' | 'error';

/** channel/channel_backend.md §4 의 agent type 분류. */
export type AgentType = 'self' | 'me' | 'internal' | 'human' | 'colleague';

export interface AgentItem {
  agentId: string;
  agentName: string;
  workspaceDir: string;
  tmuxSession: string;
  status: AgentStatus;
  taskDesc: string | null;
  model: string;
  contextPct: number | null;
  startedAt: string;          // ISO 8601
  updatedAt: string | null;
  /** 소유 사용자 (멀티유저). 자체 채널 모델 도입 후 응답에 동봉. */
  ownerAccountSn?: number | null;
  /** 발신자의 시점에서 본 type. caller 정보 없으면 backend 가 기본 분류만 부여. */
  type?: AgentType | null;
}

export interface AgentSummary {
  total: number;
  active: number;
  waiting: number;
  idle: number;
  error: number;
}

export interface AgentListResponse {
  list: AgentItem[];
  summary: AgentSummary;
}

export interface AgentCreateRequest {
  agentName: string;
  workspaceDir: string;
  model: 'claude' | 'codex' | 'hermes';
}

/**
 * 공통 응답 envelope.
 */
export interface ApiEnvelope<T> {
  result: number;
  message: string;
  data: T;
  timestamp: string;
}
