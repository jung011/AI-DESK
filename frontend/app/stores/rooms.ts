import { defineStore } from 'pinia';
import type {
  RoomCreateRequest,
  RoomItem,
  RoomMessageCreateRequest,
  RoomMessageItem
} from '~/vo/rooms/RoomVo';
import type { ApiEnvelope } from '~/vo/agents/AgentVo';

/**
 * 협업방 (룸) 상태.
 *
 * meAgentId 는 messages 와 별개로 둔다 — 룸 페이지의 관점 AI 선택은
 * 그 페이지에서만 의미가 있다.
 */
export const useRoomsStore = defineStore('rooms', () => {
  const meAgentId = ref<string | null>(null);
  const rooms = ref<RoomItem[]>([]);
  const selectedRoomId = ref<string | null>(null);
  const messages = ref<RoomMessageItem[]>([]);
  const loading = ref(false);
  const error = ref<string | null>(null);

  const selectedRoom = computed<RoomItem | null>(() => {
    if (!selectedRoomId.value) return null;
    return rooms.value.find(r => r.roomId === selectedRoomId.value) ?? null;
  });

  function api() {
    return useNuxtApp().$api;
  }

  async function setMe(agentId: string | null): Promise<void> {
    meAgentId.value = agentId;
    selectedRoomId.value = null;
    messages.value = [];
    if (agentId) {
      await fetchRooms();
    } else {
      rooms.value = [];
    }
  }

  async function fetchRooms(): Promise<void> {
    if (!meAgentId.value) return;
    try {
      const env = await api()<ApiEnvelope<RoomItem[]>>('/api/rooms', {
        params: { agentId: meAgentId.value }
      });
      rooms.value = env.data ?? [];
      error.value = null;
    } catch (e) {
      error.value = e instanceof Error ? e.message : String(e);
    }
  }

  async function selectRoom(roomId: string): Promise<void> {
    selectedRoomId.value = roomId;
    await fetchMessages();
  }

  async function fetchMessages(): Promise<void> {
    if (!selectedRoomId.value) return;
    try {
      const env = await api()<ApiEnvelope<RoomMessageItem[]>>(
        `/api/rooms/${encodeURIComponent(selectedRoomId.value)}/messages`,
        { params: { limit: 200 } }
      );
      messages.value = env.data ?? [];
      error.value = null;
    } catch (e) {
      error.value = e instanceof Error ? e.message : String(e);
    }
  }

  async function createRoom(req: RoomCreateRequest): Promise<RoomItem | null> {
    try {
      const env = await api()<ApiEnvelope<RoomItem>>('/api/rooms', {
        method: 'POST',
        body: req
      });
      if (env.result === 0 && env.data) {
        await fetchRooms();
        error.value = null;
        return env.data;
      }
      error.value = env.message ?? '방 생성 실패';
      return null;
    } catch (e) {
      error.value = e instanceof Error ? e.message : String(e);
      return null;
    }
  }

  async function sendMessage(content: string): Promise<RoomMessageItem | null> {
    if (!meAgentId.value || !selectedRoomId.value) return null;
    const body: RoomMessageCreateRequest = {
      fromAgentId: meAgentId.value,
      content
    };
    try {
      const env = await api()<ApiEnvelope<RoomMessageItem>>(
        `/api/rooms/${encodeURIComponent(selectedRoomId.value)}/messages`,
        { method: 'POST', body }
      );
      if (env.result === 0 && env.data) {
        await fetchMessages();
        error.value = null;
        return env.data;
      }
      error.value = env.message ?? '발신 실패';
      return null;
    } catch (e) {
      error.value = e instanceof Error ? e.message : String(e);
      return null;
    }
  }

  return {
    meAgentId,
    rooms,
    selectedRoomId,
    messages,
    loading,
    error,
    selectedRoom,
    setMe,
    fetchRooms,
    selectRoom,
    fetchMessages,
    createRoom,
    sendMessage
  };
});
