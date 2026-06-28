/**
 * 대시보드 상단 task 패널 의 reactive state + API.
 *
 * - SSE event `agent.task.changed` 받으면 list 재조회 (debounced)
 * - polling fallback (60s) — SSE 끊긴 동안
 */
import type { TaskCreateRq, TaskItem, TaskListRs } from '~/vo/tasks/TaskVo';

interface ApiEnvelope<T> { result: number; message: string; data: T }

export function useTasks() {
  const { $api } = useNuxtApp();
  const list = useState<TaskItem[]>('aidesk.tasks.list', () => []);
  const loading = useState<boolean>('aidesk.tasks.loading', () => false);
  const error = useState<string | null>('aidesk.tasks.error', () => null);

  let timer: ReturnType<typeof setInterval> | null = null;
  let evtSource: EventSource | null = null;
  let refreshDebounce: ReturnType<typeof setTimeout> | null = null;

  function scheduleRefresh(): void {
    if (refreshDebounce) return;
    refreshDebounce = setTimeout(() => {
      refreshDebounce = null;
      void fetchRecent();
    }, 300);
  }

  async function fetchRecent(): Promise<void> {
    loading.value = true;
    try {
      const env = await $api<ApiEnvelope<TaskListRs>>('/api/tasks/recent');
      list.value = env.data.items ?? [];
      error.value = null;
    } catch (e) {
      error.value = e instanceof Error ? e.message : String(e);
    } finally {
      loading.value = false;
    }
  }

  async function createTask(req: TaskCreateRq): Promise<TaskItem | null> {
    try {
      const env = await $api<ApiEnvelope<TaskItem>>('/api/tasks', {
        method: 'POST',
        body: req,
      });
      if (env.result === 0) {
        await fetchRecent();
        return env.data;
      }
      error.value = env.message || 'create failed';
      return null;
    } catch (e) {
      error.value = e instanceof Error ? e.message : String(e);
      return null;
    }
  }

  async function cancelTask(taskId: string): Promise<boolean> {
    try {
      const env = await $api<ApiEnvelope<null>>(`/api/tasks/${encodeURIComponent(taskId)}/cancel`, {
        method: 'POST',
      });
      if (env.result === 0) {
        await fetchRecent();
        return true;
      }
      return false;
    } catch {
      return false;
    }
  }

  function startPolling(intervalMs: number = 60_000): void {
    void fetchRecent();
    if (timer === null) {
      timer = setInterval(fetchRecent, intervalMs);
    }
    if (typeof window !== 'undefined' && typeof EventSource !== 'undefined' && evtSource === null) {
      evtSource = new EventSource('/api/messages/events');
      evtSource.addEventListener('agent.task.changed', () => scheduleRefresh());
    }
  }

  function stopPolling(): void {
    if (timer !== null) { clearInterval(timer); timer = null; }
    if (refreshDebounce !== null) { clearTimeout(refreshDebounce); refreshDebounce = null; }
    evtSource?.close();
    evtSource = null;
  }

  return { list, loading, error, fetchRecent, createTask, cancelTask, startPolling, stopPolling };
}
