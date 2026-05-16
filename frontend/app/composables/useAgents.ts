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
  const summary = ref<AgentSummary>({ total: 0, active: 0, idle: 0, done: 0 });
  const status = ref<string>(initialStatus);
  const query = ref<string>('');
  const loading = ref<boolean>(false);
  const error = ref<string | null>(null);

  let timer: ReturnType<typeof setInterval> | null = null;

  /** 검색어를 추가로 적용한 클라이언트 측 필터 결과 */
  const filteredList = computed<AgentItem[]>(() => {
    const q = query.value.trim().toLowerCase();
    if (!q) return list.value;
    return list.value.filter(a => a.agentName.toLowerCase().includes(q));
  });

  async function fetchAgents(): Promise<void> {
    loading.value = true;
    try {
      const params: Record<string, string> = {};
      if (status.value && status.value !== 'all') params.status = status.value;

      const env = await $api<ApiEnvelope<AgentListResponse>>('/api/agents', { params });
      list.value = env.data.list ?? [];
      summary.value = env.data.summary ?? { total: 0, active: 0, idle: 0, done: 0 };
      error.value = null;
    } catch (e) {
      error.value = e instanceof Error ? e.message : String(e);
    } finally {
      loading.value = false;
    }
  }

  function startPolling(intervalMs: number = 10_000): void {
    void fetchAgents();
    if (timer === null) {
      timer = setInterval(fetchAgents, intervalMs);
    }
  }

  function stopPolling(): void {
    if (timer !== null) {
      clearInterval(timer);
      timer = null;
    }
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
          try {
            await $helper<{ rc: number; message?: string }>('/api/agents/bootstrap', {
              method: 'POST',
              body: {
                workspaceDir: env.data.workspaceDir,
                tmuxSession: env.data.tmuxSession,
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
   */
  async function deleteAgent(agent: AgentItem): Promise<boolean> {
    // 1) 헬퍼에 OS 정리 위임 — best-effort
    try {
      if (agent.tmuxSession) {
        await $helper<{ rc: number; message?: string }>('/api/cleanup-agent', {
          method: 'POST',
          body: { tmuxSession: agent.tmuxSession },
        });
      }
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
