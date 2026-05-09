import type {
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
    stopPolling
  };
}
