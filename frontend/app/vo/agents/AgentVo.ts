/**
 * 백엔드 com.jsh.aidesk.serverapi.agents.vo 와 1:1 대응되는 타입.
 * 응답 envelope (ResponseJson<T>) 의 data 필드 타입.
 */

export type AgentStatus = 'active' | 'idle' | 'done';

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
}

export interface AgentSummary {
  total: number;
  active: number;
  idle: number;
  done: number;
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
