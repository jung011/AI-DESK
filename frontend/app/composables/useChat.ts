/**
 * 채팅 페이지의 데이터 흐름 — AI 목록 + 1:1 대화 + 발신.
 *
 * 사용자 = (me) liki 에이전트로 동일시. 즉 사용자가 입력 = (me) 가 보낸 거.
 * 받는 측 AI 들은 backend 의 메시지 시스템 그대로 활용 (preflight + ACK + retry).
 *
 * 메시지 수신은 polling 5초. SSE/WebSocket 으로 격상은 후속.
 */
import type { ApiEnvelope } from '~/vo/agents/AgentVo';
import type { AgentItem, AgentListResponse } from '~/vo/agents/AgentVo';
import type { MessageItem, MessageCreateRequest } from '~/vo/messages/MessageVo';

const POLL_INTERVAL_MS = 5000;

export function useChat() {
  const agents = ref<AgentItem[]>([]);
  const meAgent = ref<AgentItem | null>(null);
  const partnerId = ref<string>('');         // 선택된 상대 AI
  const messages = ref<MessageItem[]>([]);
  const loadingAgents = ref(false);
  const loadingMessages = ref(false);
  const sending = ref(false);
  const error = ref<string | null>(null);

  let pollTimer: ReturnType<typeof setInterval> | null = null;

  async function fetchAgents(): Promise<void> {
    loadingAgents.value = true;
    try {
      const { $api } = useNuxtApp();
      const env = await $api<ApiEnvelope<AgentListResponse>>('/api/agents');
      if (env.result === 0 && env.data) {
        agents.value = env.data.list;
        meAgent.value = env.data.list.find((a) => a.agentName.endsWith('(me)')) ?? null;
      }
    } catch (e) {
      error.value = `에이전트 조회 실패: ${e instanceof Error ? e.message : String(e)}`;
    } finally {
      loadingAgents.value = false;
    }
  }

  async function fetchMessages(): Promise<void> {
    if (!meAgent.value || !partnerId.value) {
      messages.value = [];
      return;
    }
    loadingMessages.value = true;
    try {
      const { $api } = useNuxtApp();
      const params = new URLSearchParams({
        agentId: meAgent.value.agentId,
        withId: partnerId.value,
        direction: 'all',
        limit: '100',
      });
      const env = await $api<ApiEnvelope<{ list: MessageItem[]; hasMore: boolean }>>(
        `/api/messages?${params}`
      );
      if (env.result === 0 && env.data) {
        messages.value = env.data.list ?? [];
      }
    } catch (e) {
      error.value = `메시지 조회 실패: ${e instanceof Error ? e.message : String(e)}`;
    } finally {
      loadingMessages.value = false;
    }
  }

  /** 상대 AI 선택. 이전 상대의 메시지 목록을 새 상대 거로 교체. */
  async function selectPartner(agentId: string): Promise<void> {
    partnerId.value = agentId;
    await fetchMessages();
  }

  async function send(content: string): Promise<boolean> {
    if (!meAgent.value || !partnerId.value || !content.trim()) return false;
    sending.value = true;
    error.value = null;
    try {
      const { $api } = useNuxtApp();
      const body: MessageCreateRequest = {
        fromAgentId: meAgent.value.agentId,
        toAgentId: partnerId.value,
        content: content.trim(),
      };
      const env = await $api<ApiEnvelope<MessageItem>>('/api/messages', {
        method: 'POST',
        body,
      });
      if (env.result === 0 && env.data) {
        // 옵티미스틱: 즉시 화면에 추가. 다음 polling 시 status 갱신.
        messages.value = [...messages.value, env.data];
        return true;
      }
      error.value = env.message ?? '전송 실패';
      return false;
    } catch (e) {
      error.value = `전송 실패: ${e instanceof Error ? e.message : String(e)}`;
      return false;
    } finally {
      sending.value = false;
    }
  }

  function startPolling(): void {
    stopPolling();
    pollTimer = setInterval(() => {
      void fetchMessages();
    }, POLL_INTERVAL_MS);
  }

  function stopPolling(): void {
    if (pollTimer) {
      clearInterval(pollTimer);
      pollTimer = null;
    }
  }

  return {
    agents,
    meAgent,
    partnerId,
    messages,
    loadingAgents,
    loadingMessages,
    sending,
    error,
    fetchAgents,
    fetchMessages,
    selectPartner,
    send,
    startPolling,
    stopPolling,
  };
}
