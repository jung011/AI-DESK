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
 * 메시지 수신은 polling 5초 + WebSocket push dual-path (Phase 0 — per-AI 봇 어댑터 plan 의 첫 단추).
 * WS 가 새 메시지 push 받으면 즉시 fetchMessages 호출 — polling 과 같은 흐름 재사용.
 * WS 끊김 시 polling fallback 자동 동작.
 */
import type { ApiEnvelope } from '~/vo/agents/AgentVo';
import type { AgentItem, AgentListResponse } from '~/vo/agents/AgentVo';
import type { AttachmentUploadResponse, MessageItem, MessageCreateRequest } from '~/vo/messages/MessageVo';

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
  let ws: WebSocket | null = null;
  let wsReconnectTimer: ReturnType<typeof setTimeout> | null = null;

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
        // backend = createdAt DESC (최신 first). 채팅 UI 는 최신이 *하단* — reverse.
        messages.value = (env.data.list ?? []).slice().reverse();
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

  async function send(content: string, attachmentIds: string[] = []): Promise<boolean> {
    if (!currentUser.value || !partnerId.value) return false;
    // 첨부만 보내는 케이스는 허용 — 빈 content 는 backend min_length=1 이라 한 칸 공백.
    const trimmed = content.trim();
    if (!trimmed && attachmentIds.length === 0) return false;
    sending.value = true;
    error.value = null;
    try {
      const { $api } = useNuxtApp();
      const body: MessageCreateRequest = {
        fromAgentId: currentUser.value.agentId,
        toAgentId: partnerId.value,
        content: trimmed || ' ',
      };
      if (attachmentIds.length > 0) body.attachmentIds = attachmentIds;
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

  async function uploadAttachment(file: File): Promise<AttachmentUploadResponse | null> {
    if (!currentUser.value) return null;
    const { $api } = useNuxtApp();
    const fd = new FormData();
    fd.append('file', file);
    fd.append('ownerAgentId', currentUser.value.agentId);
    try {
      const env = await $api<ApiEnvelope<AttachmentUploadResponse>>('/api/attachments', {
        method: 'POST',
        body: fd,
      });
      if (env.result === 0 && env.data) return env.data;
      error.value = env.message ?? '첨부 업로드 실패';
      return null;
    } catch (e) {
      error.value = `첨부 업로드 실패: ${e instanceof Error ? e.message : String(e)}`;
      return null;
    }
  }

  function startPolling(): void {
    stopPolling();
    pollTimer = setInterval(() => {
      void fetchMessages();
    }, POLL_INTERVAL_MS);
    // WS 도 함께 시작 — push 받으면 즉시 fetchMessages 호출 → 5초 polling 대기 안 하고 반영.
    startWebSocket();
  }

  function stopPolling(): void {
    if (pollTimer) {
      clearInterval(pollTimer);
      pollTimer = null;
    }
    stopWebSocket();
  }

  /**
   * Backend WebSocket 채널 (/ws/messages) 구독.
   * message.deliver 이벤트 수신 시 fetchMessages() — polling 흐름 재사용.
   * 연결 끊김 시 지수 백오프 없이 단순 3초 후 재시도. polling 이 fallback 이라 OK.
   */
  function startWebSocket(): void {
    if (import.meta.server) return;
    stopWebSocket();
    try {
      const proto = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
      const url = `${proto}//${window.location.host}/ws/messages`;
      ws = new WebSocket(url);
      ws.addEventListener('message', (e) => {
        try {
          const evt = JSON.parse(e.data as string);
          if (evt?.type === 'message.deliver') {
            // 어떤 partner 와 관여된 메시지든 일단 fetchMessages 가 contact-centric 으로 필터.
            void fetchMessages();
          }
        } catch { /* malformed payload — ignore */ }
      });
      ws.addEventListener('close', () => {
        ws = null;
        // pollTimer 가 살아있는 동안만 재시도 — stopPolling 호출 후엔 silent.
        if (pollTimer) {
          wsReconnectTimer = setTimeout(() => startWebSocket(), 3000);
        }
      });
      ws.addEventListener('error', () => {
        // close 가 따라옴 — 그쪽에서 처리.
      });
    } catch { /* WebSocket 미지원 환경 — polling 만으로 동작 */ }
  }

  function stopWebSocket(): void {
    if (wsReconnectTimer) {
      clearTimeout(wsReconnectTimer);
      wsReconnectTimer = null;
    }
    if (ws) {
      try { ws.close(); } catch { /* noop */ }
      ws = null;
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
    uploadAttachment,
    startPolling,
    stopPolling,
  };
}
