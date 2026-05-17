/**
 * 채팅 페이지의 데이터 흐름 — 휴먼(사용자) ↔ AI 들.
 *
 * 휴먼 entity (model='human') 는 사용자 본인을 시스템 안에 표현하는 별도 agent row.
 * 사용자 입력 = 휴먼 → 상대 AI 메시지로 INSERT 됨. (me) liki 는 별도 독립 AI.
 *
 * Contact-centric view: partner 채팅창에는 *그 partner 가 관여한 모든 메시지* 가 보임.
 * 즉 (me) ↔ partner 페어 뿐 아니라 다른AI ↔ partner 메시지까지 통합.
 * → 위임된 일도 partner 채팅창에서 흔적 확인 가능 (= 임베디드 터미널과 유사한 시야).
 *
 * 메시지 수신은 polling 5초. SSE/WebSocket 으로 격상은 후속.
 */
import type { ApiEnvelope } from '~/vo/agents/AgentVo';
import type { AgentItem, AgentListResponse } from '~/vo/agents/AgentVo';
import type { MessageItem, MessageCreateRequest } from '~/vo/messages/MessageVo';

const POLL_INTERVAL_MS = 5000;

export function useChat() {
  const agents = ref<AgentItem[]>([]);
  const currentUser = ref<AgentItem | null>(null);  // 휴먼 entity
  const partnerId = ref<string>('');                // 선택된 상대 AI
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
        currentUser.value =
          env.data.list.find((a) => a.model === 'human') ?? null;
      }
    } catch (e) {
      error.value = `에이전트 조회 실패: ${e instanceof Error ? e.message : String(e)}`;
    } finally {
      loadingAgents.value = false;
    }
  }

  async function fetchMessages(): Promise<void> {
    if (!currentUser.value || !partnerId.value) {
      messages.value = [];
      return;
    }
    loadingMessages.value = true;
    try {
      const { $api } = useNuxtApp();
      // contact-centric: withId=partner 면 backend 가 partner 가 관여한 모든 메시지 반환.
      // agentId 는 안 쓰지만 API 시그니처상 필요 — currentUser 로 채움.
      const params = new URLSearchParams({
        agentId: currentUser.value.agentId,
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
    if (!currentUser.value || !partnerId.value || !content.trim()) return false;
    sending.value = true;
    error.value = null;
    try {
      const { $api } = useNuxtApp();
      const body: MessageCreateRequest = {
        fromAgentId: currentUser.value.agentId,
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
    currentUser,
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
