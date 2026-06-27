import type {
  AgentCreateRequest,
  AgentItem,
  AgentListResponse,
  AgentSummary,
  ApiEnvelope
} from '~/vo/agents/AgentVo';

/**
 * 대시보드 에이전트 목록·요약 조회 + 10초 폴링.
 *
 * 사용:
 *   const { list, summary, status, query, startPolling, stopPolling } = useAgents();
 *   onMounted(() => startPolling());
 *   onUnmounted(() => stopPolling());
 */
export function useAgents(initialStatus: string = 'all') {
  const { $api, $helper } = useNuxtApp();

  const list = ref<AgentItem[]>([]);
  const summary = ref<AgentSummary>({ total: 0, active: 0, waiting: 0, idle: 0, error: 0 });
  const status = ref<string>(initialStatus);
  const query = ref<string>('');
  const loading = ref<boolean>(false);
  const error = ref<string | null>(null);

  let timer: ReturnType<typeof setInterval> | null = null;
  let evtSource: EventSource | null = null;
  let refreshDebounce: ReturnType<typeof setTimeout> | null = null;

  function scheduleRefresh(): void {
    if (refreshDebounce) return;
    refreshDebounce = setTimeout(() => {
      refreshDebounce = null;
      void fetchAgents();
    }, 300);
  }

  // 3 layer 통합 — frontend 의 'online' tab 은 backend status 가 아니라서 client-side filter.
  // 'online' = active + waiting + idle 통합. backend 호출엔 status param 안 박음.
  const ONLINE_BACKEND_STATUSES = new Set(['active', 'waiting', 'idle']);

  /** 검색어 + status 통합 client-side 필터. */
  const filteredList = computed<AgentItem[]>(() => {
    const q = query.value.trim().toLowerCase();
    const st = status.value;
    return list.value.filter(a => {
      if (q && !a.agentName.toLowerCase().includes(q)) return false;
      if (st === 'all' || !st) return true;
      if (st === 'online') return ONLINE_BACKEND_STATUSES.has(a.status);
      return a.status === st;
    });
  });

  async function fetchAgents(): Promise<void> {
    loading.value = true;
    try {
      // status param 안 박음 — client-side filter 에서 처리 (3 layer 통합 대응).
      const env = await $api<ApiEnvelope<AgentListResponse>>('/api/agents');
      // 휴먼(model='human') 은 사용자 본인 entity. 대시보드는 AI 만 보여주므로 제외.
      // 외부 AI (type='external') 는 helper-환경이 아니라서 internal 카드 grid 가 아닌
      // 사내 동료 섹션에 표시. 메인 그리드에선 제외.
      list.value = (env.data.list ?? [])
        .filter(a => a.model !== 'human')
        .filter(a => a.type !== 'external');
      summary.value = env.data.summary ?? { total: 0, active: 0, waiting: 0, idle: 0, error: 0 };
      error.value = null;
    } catch (e) {
      error.value = e instanceof Error ? e.message : String(e);
    } finally {
      loading.value = false;
    }
  }

  /**
   * 폴링 + SSE subscribe 시작.
   * - SSE 가 살아있는 동안 즉시 갱신 (agent.changed event → debounced fetchAgents)
   * - polling 은 SSE 끊긴 동안 fallback. interval 기본 60s — SSE 정상이면 거의 무부하.
   */
  function startPolling(intervalMs: number = 60_000): void {
    void fetchAgents();
    if (timer === null) {
      timer = setInterval(fetchAgents, intervalMs);
    }
    if (typeof window !== 'undefined' && typeof EventSource !== 'undefined' && evtSource === null) {
      evtSource = new EventSource('/api/messages/events');
      evtSource.addEventListener('agent.changed', () => scheduleRefresh());
    }
  }

  function stopPolling(): void {
    if (timer !== null) {
      clearInterval(timer);
      timer = null;
    }
    if (refreshDebounce !== null) {
      clearTimeout(refreshDebounce);
      refreshDebounce = null;
    }
    evtSource?.close();
    evtSource = null;
  }

  /**
   * 새 에이전트 생성. 성공 시 즉시 목록 재조회.
   * 정책 거절(envelope.result !== 0)은 error 에 사유를 담아 전달한다.
   */
  async function createAgent(req: AgentCreateRequest): Promise<AgentItem | null> {
    try {
      const env = await $api<ApiEnvelope<AgentItem>>('/api/agents', {
        method: 'POST',
        body: req
      });
      if (env.result === 0) {
        // 부트스트랩 — 호스트의 .claude/settings.local.json 권한 주입 + headless tmux 시작.
        // 이 호출이 끝나야 사용자가 터미널을 안 열어도 신규 AI 가 메시지 수신 가능.
        // Helper 가 꺼져있어도 본문 작업은 끝났으니 에러는 콘솔 경고만, 사용자에겐 성공으로 표시.
        if (env.data?.workspaceDir && env.data?.tmuxSession) {
          // 공통 작업 규칙 문서 경로는 *brower 가 인증 cookie 가진 채* 조회해서
          // helper 에 함께 넘긴다. helper 가 직접 backend 를 인증 없이 호출하면
          // /api/settings/** 의 인증 가드에 막혀 항상 빈 문자열을 받았던 결함 회피.
          let workroleFile = '';
          try {
            const wrEnv = await $api<ApiEnvelope<{ path: string }>>('/api/settings/workrole-file');
            if (wrEnv.result === 0 && wrEnv.data) workroleFile = wrEnv.data.path || '';
          } catch {
            // workrole 조회 실패해도 bootstrap 자체는 진행 (identity prompt 만 주입됨).
          }
          try {
            await $helper<{ rc: number; message?: string }>('/api/agents/bootstrap', {
              method: 'POST',
              body: {
                workspaceDir: env.data.workspaceDir,
                tmuxSession: env.data.tmuxSession,
                agentName: env.data.agentName,
                agentId: env.data.agentId,
                workroleFile,
              },
            });
          } catch (bootErr) {
            // eslint-disable-next-line no-console
            console.warn('[createAgent] helper bootstrap 실패 — 사용자가 외부 터미널을 열어야 통신 가능:', bootErr);
          }
        }
        await fetchAgents();
        error.value = null;
        return env.data;
      }
      error.value = env.message ?? '생성에 실패했습니다.';
      return null;
    } catch (e) {
      error.value = e instanceof Error ? e.message : String(e);
      return null;
    }
  }

  /**
   * 단건 hard 딜리트. 백엔드 DELETE 전에 헬퍼에 tmux/Terminal 정리를 위임한다.
   * 헬퍼 정리는 비-치명적 — 실패해도 백엔드 삭제는 그대로 진행 (사용자는 더 이상 그
   * 에이전트의 카드가 안 보이는 게 우선이고, 떠도는 tmux 세션은 추후 청소 가능).
   *
   * @param agent 삭제할 에이전트. 헬퍼에 tmuxSession 을 넘기기 위해 객체 단위로 받는다.
   * @param opts.purgeHistory true 면 ~/.claude/projects/{escaped-cwd}/ 의 대화 jsonl 도 함께 삭제.
   *   같은 워크스페이스 경로로 새 에이전트 생성 시 옛 대화가 살아오는 걸 막는 용도.
   */
  async function deleteAgent(
    agent: AgentItem,
    opts: { purgeHistory?: boolean } = {},
  ): Promise<boolean> {
    // 1) 헬퍼에 OS 정리 위임 — best-effort
    try {
      // 2026-06-27 부활 — helper cleanup-agent 가 mac 자원 (tmux + ~/.claude.json
      // mcpServers entry + 옛 bot-adapter + 옵션 jsonl history) 정리. tmux 없어도
      // mcp config 만 박혀있을 수 있어 항상 호출.
      await $helper<{ rc: number; message?: string }>('/api/cleanup-agent', {
        method: 'POST',
        body: {
          agentId: agent.agentId,
          tmuxSession: agent.tmuxSession || '',
          workspaceDir: agent.workspaceDir || '',
          purgeHistory: !!opts.purgeHistory,
        },
      });
    } catch (e) {
      // 헬퍼 미가동/오류여도 백엔드 삭제는 진행
      console.warn('helper cleanup-agent failed (continuing with backend delete):', e);
    }

    // 2) 백엔드 DELETE — DB 레코드 + 메시지 cascade
    try {
      const env = await $api<ApiEnvelope<null>>(`/api/agents/${encodeURIComponent(agent.agentId)}`, {
        method: 'DELETE'
      });
      if (env.result === 0) {
        await fetchAgents();
        error.value = null;
        return true;
      }
      error.value = env.message ?? '삭제에 실패했습니다.';
      return false;
    } catch (e) {
      error.value = e instanceof Error ? e.message : String(e);
      return false;
    }
  }

  // status 가 변하면 즉시 재조회
  watch(status, () => { void fetchAgents(); });

  return {
    // state
    list,
    summary,
    status,
    query,
    loading,
    error,
    // computed
    filteredList,
    // actions
    fetchAgents,
    startPolling,
    stopPolling,
    createAgent,
    deleteAgent
  };
}
