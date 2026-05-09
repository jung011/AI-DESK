<template>
  <div class="page_content">
    <div class="group_pageLocation">
      <h2 class="tit_h2">협업방</h2>
      <div class="descList_pageLocation">
        <a href="#">HOME</a>
        <a href="#"><em>협업방</em></a>
      </div>
      <div style="margin-left: auto;">
        <button type="button" class="btn normal type_v1" @click="newRoomOpen = true">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor" style="margin-right:6px"><path d="M19 13h-6v6h-2v-6H5v-2h6V5h2v6h6v2z" /></svg>
          새 방
        </button>
      </div>
    </div>

    <!-- 본문 — 좌 320 + 우 타임라인 -->
    <div class="rooms-wrap">
      <aside class="room-list">
        <div class="room-list-header">
          <label class="me-label">관점 AI</label>
          <select class="me-select" :value="store.meAgentId ?? ''" @change="onMeChange">
            <option value="">선택하세요…</option>
            <option v-for="a in selectableAgents" :key="a.agentId" :value="a.agentId">
              {{ a.agentName }} ({{ statusLabel(a.status) }})
            </option>
          </select>
        </div>

        <div class="room-list-body">
          <p v-if="!store.meAgentId" class="room-hint">
            관점 AI를 선택하면 그 AI가 속한 방이 보입니다.
          </p>
          <p v-else-if="store.rooms.length === 0" class="room-hint">
            아직 방이 없습니다. <span class="link" @click="newRoomOpen = true">+ 새 방</span> 으로 만드세요.
          </p>
          <div
            v-for="r in store.rooms"
            :key="r.roomId"
            class="room-item"
            :class="{ active: store.selectedRoomId === r.roomId }"
            @click="store.selectRoom(r.roomId)">
            <div class="room-item-name">{{ r.roomName }}</div>
            <div class="room-item-members">
              <span v-for="m in r.members" :key="m.agentId" class="member-chip" :class="{ coord: m.role === 'coordinator' }">
                {{ m.role === 'coordinator' ? '👑 ' : '' }}{{ m.agentName }}
              </span>
            </div>
          </div>
        </div>
      </aside>

      <section class="room-detail">
        <template v-if="store.selectedRoom">
          <div class="room-detail-header">
            <div>
              <div class="room-detail-title">{{ store.selectedRoom.roomName }}</div>
              <div class="room-detail-sub">
                <span>멤버 {{ store.selectedRoom.members.length }}명</span>
                <span>·</span>
                <span>생성: {{ store.selectedRoom.createdByName }}</span>
              </div>
            </div>
          </div>

          <div ref="timelineEl" class="room-timeline">
            <p v-if="store.messages.length === 0" class="room-hint">메시지가 없습니다.</p>
            <div
              v-for="m in store.messages"
              :key="m.messageId"
              class="msg-row"
              :class="m.fromAgentId === store.meAgentId ? 'outgoing' : 'incoming'">
              <div class="msg-stack">
                <span v-if="m.fromAgentId !== store.meAgentId" class="msg-author">{{ m.fromAgentName }}</span>
                <div class="msg-bubble">{{ m.content }}</div>
                <div class="msg-meta">{{ formatTime(m.createdAt) }}</div>
              </div>
            </div>
          </div>

          <div class="composer">
            <textarea
              v-model="composerText"
              :maxlength="1000"
              :placeholder="composerPlaceholder"
              :disabled="!isMember || sending"
              @keydown.enter.exact.prevent="onSend"
              @keydown.enter.shift.exact="" />
            <span class="composer-counter">{{ composerText.length }} / 1000</span>
            <button
              type="button"
              class="btn normal type_v1"
              :disabled="!canSend || sending"
              @click="onSend">
              {{ sending ? '보내는 중…' : '보내기' }}
            </button>
          </div>
        </template>
        <div v-else class="room-detail-empty">
          <p>좌측에서 방을 선택하면 메시지가 여기에 표시됩니다.</p>
        </div>
      </section>
    </div>

    <!-- 새 방 팝업 -->
    <Teleport to="body">
      <div v-if="newRoomOpen" class="popup-overlay" @click.self="closeNewRoom">
        <div class="popup-box">
          <header class="popup-head">
            <h3>새 방</h3>
            <button class="popup-close" type="button" @click="closeNewRoom">×</button>
          </header>
          <div class="popup-body">
            <div class="form_field">
              <label class="form_label">방 이름 <span class="required">*</span></label>
              <input v-model="newRoomForm.roomName" type="text" maxlength="50" placeholder="예: PR #42 협업방" />
            </div>
            <div class="form_field">
              <label class="form_label">방 생성자 <span class="required">*</span></label>
              <select v-model="newRoomForm.createdBy">
                <option value="">선택하세요…</option>
                <option v-for="a in selectableAgents" :key="a.agentId" :value="a.agentId">
                  {{ a.agentName }} ({{ statusLabel(a.status) }})
                </option>
              </select>
              <span class="form_help">자동으로 coordinator 로 합류합니다.</span>
            </div>
            <div class="form_field">
              <label class="form_label">초대할 AI</label>
              <div class="checkbox-list">
                <label
                  v-for="a in selectableAgents"
                  :key="a.agentId"
                  class="checkbox-row"
                  :class="{ disabled: a.agentId === newRoomForm.createdBy }">
                  <input
                    type="checkbox"
                    :value="a.agentId"
                    :checked="newRoomMembers.has(a.agentId)"
                    :disabled="a.agentId === newRoomForm.createdBy"
                    @change="onToggleMember(a.agentId, ($event.target as HTMLInputElement).checked)" />
                  <span>{{ a.agentName }} ({{ statusLabel(a.status) }})</span>
                </label>
              </div>
              <span class="form_help">방 생성자 외의 멤버를 선택하세요. 비워 두면 1인 방으로 만들어집니다.</span>
            </div>
            <p v-if="newRoomError" class="form_error">{{ newRoomError }}</p>
          </div>
          <footer class="popup-foot">
            <button class="btn normal type_v2" type="button" :disabled="newRoomSubmitting" @click="closeNewRoom">취소</button>
            <button class="btn normal type_v1" type="button" :disabled="!canCreateRoom || newRoomSubmitting" @click="onCreateRoom">
              {{ newRoomSubmitting ? '생성 중…' : '방 만들기' }}
            </button>
          </footer>
        </div>
      </div>
    </Teleport>
  </div>
</template>

<script setup lang="ts">
import { useRoomsStore } from '~/stores/rooms';
import type { AgentItem, AgentListResponse, ApiEnvelope, AgentStatus } from '~/vo/agents/AgentVo';

const store = useRoomsStore();
const { $api } = useNuxtApp();

const allAgents = ref<AgentItem[]>([]);
const composerText = ref('');
const sending = ref(false);
const timelineEl = ref<HTMLElement | null>(null);

const newRoomOpen = ref(false);
const newRoomSubmitting = ref(false);
const newRoomError = ref<string | null>(null);
const newRoomForm = reactive<{ roomName: string; createdBy: string }>({ roomName: '', createdBy: '' });
const newRoomMembers = reactive<Set<string>>(new Set());

const selectableAgents = computed(() =>
  allAgents.value.filter(a => a.status === 'active' || a.status === 'idle')
);

const isMember = computed(() => {
  if (!store.selectedRoom || !store.meAgentId) return false;
  return store.selectedRoom.members.some(m => m.agentId === store.meAgentId);
});

const composerPlaceholder = computed(() => {
  if (!store.meAgentId) return '관점 AI 를 먼저 선택하세요…';
  if (!isMember.value) return '이 방의 멤버가 아닙니다 — 메시지를 보낼 수 없습니다.';
  return '메시지를 입력하세요... (Shift+Enter 줄바꿈, Enter 전송)';
});

const canSend = computed(() =>
  Boolean(store.meAgentId) &&
  Boolean(store.selectedRoomId) &&
  isMember.value &&
  composerText.value.trim().length > 0
);

const canCreateRoom = computed(() =>
  newRoomForm.roomName.trim().length > 0 &&
  newRoomForm.createdBy.length > 0
);

async function loadAgents(): Promise<void> {
  const env = await $api<ApiEnvelope<AgentListResponse>>('/api/agents');
  allAgents.value = env.data.list ?? [];
}

async function onMeChange(e: Event): Promise<void> {
  const v = (e.target as HTMLSelectElement).value || null;
  await store.setMe(v);
}

async function onSend(): Promise<void> {
  if (!canSend.value || sending.value) return;
  sending.value = true;
  const text = composerText.value.trim();
  composerText.value = '';
  await store.sendMessage(text);
  sending.value = false;
  await nextTick();
  if (timelineEl.value) timelineEl.value.scrollTop = timelineEl.value.scrollHeight;
}

function onToggleMember(agentId: string, checked: boolean): void {
  if (checked) newRoomMembers.add(agentId);
  else newRoomMembers.delete(agentId);
}

function closeNewRoom(): void {
  if (newRoomSubmitting.value) return;
  newRoomOpen.value = false;
  newRoomForm.roomName = '';
  newRoomForm.createdBy = '';
  newRoomMembers.clear();
  newRoomError.value = null;
}

async function onCreateRoom(): Promise<void> {
  if (!canCreateRoom.value || newRoomSubmitting.value) return;
  newRoomSubmitting.value = true;
  newRoomError.value = null;
  const created = await store.createRoom({
    roomName: newRoomForm.roomName.trim(),
    createdBy: newRoomForm.createdBy,
    initialMemberAgentIds: Array.from(newRoomMembers).filter(id => id !== newRoomForm.createdBy)
  });
  newRoomSubmitting.value = false;
  if (created) {
    closeNewRoom();
    if (store.meAgentId === created.createdBy ||
        created.members.some(m => m.agentId === store.meAgentId)) {
      await store.selectRoom(created.roomId);
    }
  } else {
    newRoomError.value = store.error ?? '방 생성 실패';
  }
}

function statusLabel(s: AgentStatus | string): string {
  if (s === 'active') return '작업중';
  if (s === 'idle') return '쉬는 중';
  return '완료';
}
function formatTime(iso: string): string {
  const d = new Date(iso);
  const hh = String(d.getHours()).padStart(2, '0');
  const mm = String(d.getMinutes()).padStart(2, '0');
  return `${hh}:${mm}`;
}

onMounted(async () => {
  await loadAgents();
});
watch(() => store.messages.length, async () => {
  await nextTick();
  if (timelineEl.value) timelineEl.value.scrollTop = timelineEl.value.scrollHeight;
});
</script>

<style scoped>
.page_content { padding: 28px; max-width: 1400px; margin: 0 auto; }
.group_pageLocation { display: flex; align-items: center; gap: 16px; margin-bottom: 20px; }
.tit_h2 { font-size: 20px; font-weight: 700; color: #101010; margin: 0; }
.descList_pageLocation { display: flex; align-items: center; gap: 6px; font-size: 12px; color: #94A3B8; }
.descList_pageLocation a { color: #94A3B8; text-decoration: none; }
.descList_pageLocation a + a::before { content: '›'; margin-right: 6px; color: #CBD5E1; }
.descList_pageLocation em { font-style: normal; color: #475569; font-weight: 600; }

.rooms-wrap {
  display: grid; grid-template-columns: 320px 1fr; gap: 16px;
  height: calc(100vh - 240px); min-height: 540px;
}

.room-list {
  background: #fff; border: 1px solid #D4DCE4; border-radius: 6px;
  box-shadow: 0 3px 10px 0 rgba(67, 87, 103, .12);
  display: flex; flex-direction: column; overflow: hidden;
}
.room-list-header {
  padding: 12px 14px; border-bottom: 1px solid #F0F2F5; background: #FAFBFD;
  display: flex; flex-direction: column; gap: 6px;
}
.me-label { font-size: 11px; font-weight: 600; color: #475569; letter-spacing: .04em; }
.me-select {
  height: 34px; padding: 0 10px; border: 1px solid #D4DCE4; border-radius: 6px;
  font-size: 13px; color: #333; background: #fff; width: 100%;
}
.me-select:focus { outline: none; border-color: #0062ff; }

.room-list-body { flex: 1; overflow-y: auto; }
.room-hint {
  padding: 28px 18px; font-size: 12px; color: #94A3B8;
  text-align: center; line-height: 1.6;
}
.room-hint .link { color: #0062ff; cursor: pointer; text-decoration: underline; }

.room-item {
  padding: 12px 14px; border-bottom: 1px solid #F0F2F5; cursor: pointer;
  transition: background .15s;
}
.room-item:hover { background: #F8FAFC; }
.room-item.active {
  background: #EEF2FF; border-left: 3px solid #0062ff; padding-left: 11px;
}
.room-item-name { font-size: 13px; font-weight: 700; color: #101010; }
.room-item-members {
  display: flex; flex-wrap: wrap; gap: 4px; margin-top: 4px;
}
.member-chip {
  font-size: 11px; padding: 1px 7px; border-radius: 10px;
  background: #F1F5F9; color: #475569;
}
.member-chip.coord { background: #FFF8E1; color: #B45309; }

.room-detail {
  background: #fff; border: 1px solid #D4DCE4; border-radius: 6px;
  box-shadow: 0 3px 10px 0 rgba(67, 87, 103, .12);
  display: flex; flex-direction: column; overflow: hidden;
}
.room-detail-empty {
  flex: 1; display: flex; align-items: center; justify-content: center;
  color: #94A3B8; font-size: 13px;
}
.room-detail-header {
  padding: 14px 18px; border-bottom: 1px solid #F0F2F5; background: #FAFBFD;
}
.room-detail-title { font-size: 14px; font-weight: 700; color: #101010; }
.room-detail-sub {
  font-size: 11px; color: #666; margin-top: 2px;
  display: flex; gap: 8px;
}
.room-timeline { flex: 1; overflow-y: auto; padding: 18px; background: #FAFBFD; }

.msg-row { display: flex; margin-bottom: 14px; align-items: flex-start; }
.msg-row.outgoing { justify-content: flex-end; }
.msg-row.incoming { justify-content: flex-start; }
.msg-stack {
  display: flex; flex-direction: column; max-width: 70%;
}
.msg-row.outgoing .msg-stack { align-items: flex-end; }
.msg-row.incoming .msg-stack { align-items: flex-start; }
.msg-author {
  font-size: 11px; color: #475569; font-weight: 600;
  margin-bottom: 3px; padding-left: 4px;
}
.msg-bubble {
  padding: 10px 14px; border-radius: 12px;
  font-size: 13px; line-height: 1.55;
  word-break: break-word; white-space: pre-wrap;
}
.msg-row.incoming .msg-bubble {
  background: #fff; color: #333;
  border: 1px solid #E0E5EC; border-top-left-radius: 4px;
}
.msg-row.outgoing .msg-bubble {
  background: #0062ff; color: #fff;
  border-top-right-radius: 4px;
}
.msg-meta { font-size: 11px; color: #AAB4BE; margin-top: 4px; }

.composer {
  border-top: 1px solid #F0F2F5; padding: 12px 14px;
  display: flex; gap: 8px; align-items: flex-end; background: #fff;
}
.composer textarea {
  flex: 1; min-height: 40px; max-height: 120px;
  padding: 10px 12px; border: 1px solid #D4DCE4; border-radius: 6px;
  font-size: 13px; resize: none; font-family: inherit;
}
.composer textarea:focus { outline: none; border-color: #0062ff; }
.composer textarea:disabled { background: #F8FAFC; color: #94A3B8; }
.composer-counter { font-size: 11px; color: #AAB4BE; align-self: center; }

.btn.normal {
  display: inline-flex; align-items: center; height: 40px;
  padding: 0 18px; border-radius: 6px;
  font-size: 13px; font-weight: 600; cursor: pointer;
  border: 1px solid transparent;
}
.btn.normal.type_v1 { background: #0062ff; color: #fff; }
.btn.normal.type_v1:hover:not(:disabled) { background: #0052d4; }
.btn.normal.type_v1:disabled { background: #94A3B8; cursor: not-allowed; }
.btn.normal.type_v2 { background: #fff; color: #475569; border-color: #D4DCE4; }
.btn.normal.type_v2:hover:not(:disabled) { background: #F8FAFC; }

/* 새 방 팝업 */
.popup-overlay {
  position: fixed; inset: 0;
  background: rgba(15, 23, 42, 0.45);
  display: flex; align-items: center; justify-content: center;
  z-index: 1000;
}
.popup-box {
  width: 480px; max-width: calc(100vw - 40px);
  background: #fff; border-radius: 10px;
  box-shadow: 0 20px 50px rgba(15, 23, 42, .2);
  display: flex; flex-direction: column;
}
.popup-head { display: flex; align-items: center; justify-content: space-between; padding: 16px 20px; border-bottom: 1px solid #F0F2F5; }
.popup-head h3 { font-size: 15px; font-weight: 700; color: #101010; margin: 0; }
.popup-close { width: 28px; height: 28px; background: none; border: none; font-size: 22px; color: #94A3B8; cursor: pointer; line-height: 1; }
.popup-close:hover { color: #475569; }
.popup-body { padding: 20px; max-height: 70vh; overflow-y: auto; }
.popup-foot { display: flex; justify-content: flex-end; gap: 8px; padding: 14px 20px; border-top: 1px solid #F0F2F5; }
.popup-foot .btn.normal { height: 36px; }

.form_field { display: flex; flex-direction: column; gap: 8px; margin-bottom: 16px; }
.form_label { font-size: 13px; font-weight: 600; color: #333; }
.form_label .required { color: #E53935; }
.form_help { font-size: 12px; color: #AAB4BE; }
.form_error { margin: 0; padding: 8px 12px; border-radius: 6px; background: #FFE5E9; color: #B22B45; font-size: 12px; }
.form_field input[type="text"], .form_field select {
  height: 36px; padding: 0 12px;
  border: 1px solid #D4DCE4; border-radius: 6px;
  font-size: 13px; color: #333; background: #fff;
}
.form_field select { cursor: pointer; }
.form_field input[type="text"]:focus, .form_field select:focus { outline: none; border-color: #0062ff; }

.checkbox-list {
  display: flex; flex-direction: column; gap: 4px;
  border: 1px solid #D4DCE4; border-radius: 6px;
  padding: 8px 6px; background: #fff; max-height: 180px; overflow-y: auto;
}
.checkbox-row {
  display: flex; align-items: center; gap: 8px;
  padding: 6px 8px; border-radius: 4px; cursor: pointer; user-select: none;
  font-size: 13px;
}
.checkbox-row:hover:not(.disabled) { background: #F8FAFC; }
.checkbox-row.disabled { cursor: not-allowed; color: #94A3B8; }
</style>
