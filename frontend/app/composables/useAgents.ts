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
  const { $api } = useNuxtApp();

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
   * 단건 소프트 딜리트. 성공 시 즉시 목록 재조회.
   */
  async function deleteAgent(agentId: string): Promise<boolean> {
    try {
      const env = await $api<ApiEnvelope<null>>(`/api/agents/${encodeURIComponent(agentId)}`, {
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
