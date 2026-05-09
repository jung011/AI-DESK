import { defineStore } from 'pinia';
import type {
  ConversationItem,
  MessageItem,
  MessageListResponse,
  UnreadCountResponse
} from '~/vo/messages/MessageVo';
import type { ApiEnvelope } from '~/vo/agents/AgentVo';

/**
 * 메시지 화면 상태.
 *
 * "내 AI" (관점 AI) 는 1단계에선 사용자가 직접 선택한다.
 * 선택 후 conversations / messages / unread 가 그 AI 기준으로 채워진다.
 */
export const useMessagesStore = defineStore('messages', () => {
  const meAgentId = ref<string | null>(null);
  const conversations = ref<ConversationItem[]>([]);
  const selectedPartnerId = ref<string | null>(null);
  const messages = ref<MessageItem[]>([]);
  const unread = ref<UnreadCountResponse>({ totalUnread: 0, byAgent: [] });
  const loading = ref(false);
  const error = ref<string | null>(null);

  const selectedConversation = computed<ConversationItem | null>(() => {
    if (!selectedPartnerId.value) return null;
    return conversations.value.find(c => c.partnerAgentId === selectedPartnerId.value) ?? null;
  });

  function api() {
    return useNuxtApp().$api;
  }

  /** 관점 AI 변경 시 — 대화 목록 재조회. */
  async function setMe(agentId: string | null): Promise<void> {
    meAgentId.value = agentId;
    selectedPartnerId.value = null;
    messages.value = [];
    if (agentId) {
      await fetchConversations();
    } else {
      conversations.value = [];
    }
  }

  async function fetchConversations(): Promise<void> {
    if (!meAgentId.value) return;
    try {
      const env = await api()<ApiEnvelope<ConversationItem[]>>(
        '/api/messages/conversations',
        { params: { agentId: meAgentId.value } }
      );
      conversations.value = env.data ?? [];
      error.value = null;
    } catch (e) {
      error.value = e instanceof Error ? e.message : String(e);
    }
  }

  async function fetchMessages(): Promise<void> {
    if (!meAgentId.value || !selectedPartnerId.value) return;
    try {
      const env = await api()<ApiEnvelope<MessageListResponse>>('/api/messages', {
        params: {
          agentId: meAgentId.value,
          withId: selectedPartnerId.value,
          limit: 200
        }
      });
      messages.value = env.data.list ?? [];
      error.value = null;
    } catch (e) {
      error.value = e instanceof Error ? e.message : String(e);
    }
  }

  async function selectConversation(partnerId: string): Promise<void> {
    selectedPartnerId.value = partnerId;
    await fetchMessages();
    await markConversationRead();
  }

  async function markConversationRead(): Promise<void> {
    if (!meAgentId.value || !selectedPartnerId.value) return;
    const me = meAgentId.value;
    const partner = selectedPartnerId.value;
    const unreadFromPartner = messages.value.filter(m =>
      m.toAgentId === me &&
      m.fromAgentId === partner &&
      m.readAt === null
    );
    if (unreadFromPartner.length === 0) return;
    await Promise.all(unreadFromPartner.map(m =>
      api()(`/api/messages/${encodeURIComponent(m.messageId)}/read`, {
        method: 'PATCH',
        params: { agentId: me }
      }).catch(() => null)
    ));
    // 읽음 처리 후 카운트와 대화 목록 갱신
    await fetchUnreadCount();
    await fetchConversations();
  }

  async function fetchUnreadCount(): Promise<void> {
    try {
      const env = await api()<ApiEnvelope<UnreadCountResponse>>('/api/messages/unread-count');
      unread.value = env.data;
    } catch (e) {
      error.value = e instanceof Error ? e.message : String(e);
    }
  }

  return {
    // state
    meAgentId,
    conversations,
    selectedPartnerId,
    messages,
    unread,
    loading,
    error,
    // computed
    selectedConversation,
    // actions
    setMe,
    fetchConversations,
    fetchMessages,
    selectConversation,
    markConversationRead,
    fetchUnreadCount
  };
});
