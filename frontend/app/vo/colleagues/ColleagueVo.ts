/**
 * 사내 동료 — 같은 backend 의 다른 user 의 (me) AI.
 * channel/channel_backend.md §3 의 GET /api/colleagues 응답 형식과 1:1 매칭.
 */
export interface ColleagueItem {
  accountSn: number;
  loginId: string;
  displayName: string;
  meAgentId: string | null;
  meAgentName: string | null;
  meStatus: string | null;
  meContextPct: number | null;
  meWorkspaceDir: string | null;
  meUpdatedAt: string | null;
  online: boolean;
}

export interface ColleagueListRs {
  list: ColleagueItem[];
}
