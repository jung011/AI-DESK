<template>
  <section class="conv-view" :style="{ '--cv-font-size': `${fontSizePx}px` }">
    <header v-if="partner" class="conv-head">
      <button v-if="showBack" class="cv-back" @click="$emit('back')" aria-label="뒤로">←</button>
      <span class="cv-avatar" :class="partner.status">{{ avatar(partner.status) }}</span>
      <div class="cv-title">
        <div class="cv-name">{{ partner.agentName }}</div>
        <div class="cv-meta">
          <span class="cv-status-dot" :class="partner.status"></span>
          <span>{{ statusLabel(partner.status) }}</span>
          <span class="cv-meta-sep">·</span>
          <span>{{ shortModel(partner.model) }}</span>
          <template v-if="partner.contextPct != null && partner.contextPct > 0">
            <span class="cv-meta-sep">·</span>
            <span class="cv-ctx" :class="ctxLevel(partner.contextPct)">{{ partner.contextPct }}% context</span>
          </template>
        </div>
      </div>
      <!-- 상단 ... 메뉴 — 클릭 시 폰트 사이즈 모달. iTerm 스타일 숫자 조절. -->
      <div class="cv-head-actions">
        <button class="cv-menu-btn" @click.stop="settingsOpen = true" aria-label="설정">⋯</button>
      </div>
    </header>
    <header v-else class="conv-head empty">
      <span class="cv-placeholder">대화할 AI 를 왼쪽에서 선택하세요</span>
    </header>

    <div v-if="partner" class="conv-body" ref="bodyRef">
      <div v-if="loading && messages.length === 0" class="cv-empty">로딩 중…</div>
      <div v-else-if="messages.length === 0" class="cv-empty">아직 메시지 없음 — 첫 대화를 시작해보세요</div>
      <ul v-else class="cv-msgs">
        <li
          v-for="m in visibleMessages"
          :key="m.messageId"
          class="cv-msg"
          :class="{
            mine: m.fromAgentId === meId,
            theirs: m.fromAgentId !== meId,
            failed: m.status === 'failed',
          }">
          <div class="cv-bubble">
            <!--
              발신자 이름 라벨 — contact-centric view 에서는 partner 와의 1:1 페어 외에도
              다른 AI 들이 partner 한테 보낸/받은 메시지가 섞이므로 누가 보낸지 명시.
              본인(휴먼) 발신 메시지는 라벨 생략.
            -->
            <div
              v-if="m.fromAgentId !== meId && partner && m.fromAgentId !== partner.agentId"
              class="cv-sender">
              {{ m.fromAgentName }} → {{ m.toAgentName }}
            </div>
            <div
              v-else-if="m.fromAgentId !== meId"
              class="cv-sender">
              {{ m.fromAgentName }}
            </div>
            <div v-if="m.content && m.content.trim()" class="cv-content">{{ m.content }}</div>
            <!--
              첨부 chip — 카카오톡 스타일. 파일명/크기 + 다운로드 아이콘.
              backend = permitAll (cookie auth 없음) 이라 단순 <a download> 로 충분.
              filename 은 backend content-disposition 에 박혀있어 다운로드 시 보존.
            -->
            <ul v-if="m.attachments && m.attachments.length > 0" class="cv-attachments">
              <li v-for="a in m.attachments" :key="a.attachmentId" class="cv-attachment">
                <a class="cv-att-chip" :href="`/api/attachments/${a.attachmentId}`" :download="a.originalFilename" :title="`${a.originalFilename} 다운로드`">
                  <span class="cv-att-icon">{{ attachmentIcon(a.contentType) }}</span>
                  <span class="cv-att-info">
                    <span class="cv-att-name">{{ a.originalFilename }}</span>
                    <span class="cv-att-size">{{ formatSize(a.sizeBytes) }}</span>
                  </span>
                  <span class="cv-att-download" aria-hidden="true">⬇</span>
                </a>
              </li>
            </ul>
            <div class="cv-foot">
              <span class="cv-time">{{ formatTime(m.createdAt) }}</span>
              <span
                v-if="m.fromAgentId === meId"
                class="cv-status"
                :class="m.status"
                :title="m.errorReason || ''">
                {{ statusBadge(m.status) }}
              </span>
            </div>
            <!-- AI 가 mark_read mcp tool 호출 → readAt 박힘. 그게 마지막 *내* 발신
                 메시지면 = AI 가 읽고 처리중 → 책상 작업중 chip 표시.
                 hover 시 chip 위에 inline stage popover (모달 X). -->
            <div
              v-if="m.messageId === workingOnMessageId && partner"
              class="cv-working-row">
              <div class="cv-working-wrap">
                <WorkingDeskChip :agent-name="partner.agentName" />
                <div class="cv-working-popover">
                  <WorkingDeskStage :agent-name="partner.agentName" />
                </div>
              </div>
            </div>
          </div>
        </li>
        <!-- AI 답신 작성중 placeholder bubble — workingOnMessageId 살아있는 동안 AI
             측 (좌측) 에 *답신 작성중* 표시. 답신 도착 시 workingOnMessageId null
             → bubble 사라짐 + 실제 메시지 표시. 점 plain X = "답신 작성중" 텍스트 +
             scanner 같은 progress bar. -->
        <li v-if="workingOnMessageId && partner" class="cv-msg theirs typing-placeholder">
          <div class="cv-bubble">
            <div class="cv-sender">{{ partner.agentName }}</div>
            <div class="cv-typing">
              <span class="cv-typing-text">답신 작성중</span>
              <span class="cv-typing-scanner"></span>
            </div>
          </div>
        </li>
      </ul>
    </div>

    <!-- 폰트 크기 모달 — iTerm 스타일 숫자 조절. 바깥 클릭 / X / Esc 로 닫기. -->
    <Teleport to="body">
      <div v-if="settingsOpen" class="cv-settings-overlay" @click="settingsOpen = false">
        <div class="cv-settings-modal" @click.stop>
          <header class="cv-settings-head">
            <h3>채팅 설정</h3>
            <button class="cv-settings-x" @click="settingsOpen = false" aria-label="닫기">✕</button>
          </header>
          <div class="cv-settings-body">
            <div class="cv-settings-field">
              <label class="cv-settings-label">폰트 크기 (px)</label>
              <div class="cv-settings-control">
                <button class="cv-stepper" @click="bumpFontSize(-1)" :disabled="fontSizePx <= 10" aria-label="감소">−</button>
                <input
                  class="cv-settings-num"
                  type="number"
                  v-model.number="fontSizePxInput"
                  min="10"
                  max="24"
                  @change="applyFontSizeInput"
                />
                <button class="cv-stepper" @click="bumpFontSize(1)" :disabled="fontSizePx >= 24" aria-label="증가">＋</button>
                <span class="cv-settings-range">10 — 24</span>
              </div>
              <div class="cv-settings-preview" :style="{ fontSize: `${fontSizePx}px` }">
                미리보기 — 안녕하세요, 채팅 글자 크기 샘플입니다.
              </div>
            </div>
            <div class="cv-settings-actions">
              <button class="cv-settings-reset" @click="resetFontSize">기본값으로</button>
              <button class="cv-settings-done" @click="settingsOpen = false">완료</button>
            </div>
          </div>
        </div>
      </div>
    </Teleport>

    <footer v-if="partner" class="conv-input">
      <!-- 선택된 첨부 chip (upload 전 또는 후) -->
      <div v-if="pendingAttachments.length > 0 || uploadingFiles" class="cv-pending-attachments">
        <span v-if="uploadingFiles" class="cv-pending-uploading">⏳ 업로드 중…</span>
        <span v-for="a in pendingAttachments" :key="a.attachmentId" class="cv-pending-chip">
          <span class="cv-att-icon">{{ attachmentIcon(a.contentType) }}</span>
          <span class="cv-pending-name">{{ a.originalFilename }}</span>
          <span class="cv-pending-size">{{ formatSize(a.sizeBytes) }}</span>
          <button class="cv-pending-x" @click="removePending(a.attachmentId)" aria-label="제거">✕</button>
        </span>
      </div>
      <div class="cv-composer-row">
        <button class="cv-attach-btn" :title="'파일 첨부'" :disabled="sending || uploadingFiles" @click="onAttachClick">📎</button>
        <input ref="fileInputRef" type="file" multiple class="cv-file-input" @change="onFileChange" />
        <textarea
          v-model="draft"
          class="cv-textarea"
          rows="2"
          :placeholder="`${partner.agentName} 에게 메시지…`"
          :disabled="sending"
          @keydown.enter.exact="onEnter"
        />
        <button
          class="cv-send"
          :disabled="(!draft.trim() && pendingAttachments.length === 0) || sending || uploadingFiles"
          @click="onSend">
          {{ sending ? '전송 중…' : '전송' }}
        </button>
      </div>
    </footer>
  </section>
</template>

<script setup lang="ts">
import type { AgentItem, AgentStatus } from '~/vo/agents/AgentVo';
import type { AttachmentRef, AttachmentUploadResponse, MessageItem } from '~/vo/messages/MessageVo';
import WorkingDeskChip from '~/components/chat/WorkingDeskChip.vue';
import WorkingDeskStage from '~/components/chat/WorkingDeskStage.vue';

const props = defineProps<{
  partner: AgentItem | null;
  messages: MessageItem[];
  meId: string;
  loading: boolean;
  sending: boolean;
  showBack: boolean;
  /** 첨부 업로드 함수 — useChat.uploadAttachment 주입. */
  uploadFn?: (file: File) => Promise<AttachmentUploadResponse | null>;
}>();

const emit = defineEmits<{
  (e: 'send', content: string, attachmentIds: string[]): void;
  (e: 'back'): void;
}>();

const draft = ref('');
const bodyRef = ref<HTMLElement | null>(null);
const fileInputRef = ref<HTMLInputElement | null>(null);
const pendingAttachments = ref<AttachmentRef[]>([]);
const uploadingFiles = ref(false);
const settingsOpen = ref(false);

/**
 * 채팅 vs task 큐 분리 — task 메시지 (`[task:UUID]` 시작) 는 대시보드 TaskPanel
 * 의 책임. 채팅 페이지에서는 제외 = 두 path 가 시각적으로 안 섞임.
 *
 * mark_read 도 task 메시지의 readAt 패치 받지만 chip 계산에선 task 메시지 무시.
 * → 채팅창 chip = *채팅에서 보낸 메시지의 읽음* 만 trigger. task 의 lifecycle 은
 * 대시보드의 TaskPanel 배지 (in_progress / done) 가 책임.
 */
const visibleMessages = computed<MessageItem[]>(() => {
  return props.messages.filter((m) => {
    const c = (m.content || '').trimStart();
    return !c.startsWith('[task:');
  });
});

/**
 * AI 가 책상에서 작업중 chip 박을 messageId.
 *
 * 조건:
 *  - 마지막 내 발신 메시지 (fromAgentId === meId, toAgentId === partner)
 *  - readAt 이 박혀있음 (AI 가 mark_read mcp tool 호출 완료)
 *  - 그 뒤로 partner 의 답신 (fromAgentId === partner) 메시지가 *아직* 없음
 *
 * 답신 오면 chip 자동 사라짐. hover 시 stage popover (CSS only — Vue state X).
 *
 * visibleMessages 기반 — task 메시지 무시 (chat vs task 분리 정합).
 */
const workingOnMessageId = computed<string | null>(() => {
  if (!props.partner) return null;
  const list = visibleMessages.value;
  // 최신 → 옛 순으로 뒤에서부터 — partner 답신 있으면 chip 표시 X
  for (let i = list.length - 1; i >= 0; i--) {
    const m = list[i] as MessageItem;
    if (!m) continue;
    if (m.fromAgentId === props.partner.agentId && m.toAgentId === props.meId) {
      // partner → me 메시지가 더 최신 → 이미 답신 옴
      return null;
    }
    if (m.fromAgentId === props.meId && m.toAgentId === props.partner.agentId) {
      // 마지막 내 발신 메시지
      return m.readAt ? m.messageId : null;
    }
  }
  return null;
});
const FONT_DEFAULT_PX = 13;
const FONT_MIN_PX = 10;
const FONT_MAX_PX = 24;
const fontSizePx = ref<number>(FONT_DEFAULT_PX);
const fontSizePxInput = ref<number>(FONT_DEFAULT_PX);

// iTerm 스타일 — 숫자(px) 단위 직접 조절. localStorage 저장.
onMounted(() => {
  if (typeof window === 'undefined') return;
  const saved = window.localStorage.getItem('aidesk.chat.fontSizePx');
  const n = saved ? Number(saved) : NaN;
  if (Number.isFinite(n) && n >= FONT_MIN_PX && n <= FONT_MAX_PX) {
    fontSizePx.value = n;
    fontSizePxInput.value = n;
  }
  document.addEventListener('keydown', onSettingsKey);
  // 새로고침 / 첫 mount 시 — parent 가 미리 fetch 한 messages 가 박혀있을 수 있음.
  // watch source 가 *변화 없으면* 발사 안 하므로 mount 시점에도 명시적 scroll 박음.
  scrollToBottomDeferred();
});
onBeforeUnmount(() => {
  if (typeof document !== 'undefined') document.removeEventListener('keydown', onSettingsKey);
});

function onSettingsKey(e: KeyboardEvent): void {
  if (e.key === 'Escape' && settingsOpen.value) {
    settingsOpen.value = false;
  }
}

function setFontSizePx(n: number): void {
  const clamped = Math.max(FONT_MIN_PX, Math.min(FONT_MAX_PX, Math.round(n)));
  fontSizePx.value = clamped;
  fontSizePxInput.value = clamped;
  if (typeof window !== 'undefined') {
    window.localStorage.setItem('aidesk.chat.fontSizePx', String(clamped));
  }
}

function bumpFontSize(delta: number): void {
  setFontSizePx(fontSizePx.value + delta);
}

function applyFontSizeInput(): void {
  const n = Number(fontSizePxInput.value);
  if (Number.isFinite(n)) setFontSizePx(n);
  else fontSizePxInput.value = fontSizePx.value;
}

function resetFontSize(): void {
  setFontSizePx(FONT_DEFAULT_PX);
}

function onAttachClick(): void {
  fileInputRef.value?.click();
}

async function onFileChange(e: Event): Promise<void> {
  const target = e.target as HTMLInputElement;
  const files = Array.from(target.files ?? []);
  target.value = ''; // 같은 파일 다시 선택 가능하게.
  if (files.length === 0 || !props.uploadFn) return;
  uploadingFiles.value = true;
  try {
    for (const f of files) {
      const result = await props.uploadFn(f);
      if (result) pendingAttachments.value.push(result);
    }
  } finally {
    uploadingFiles.value = false;
  }
}

function removePending(attachmentId: string): void {
  pendingAttachments.value = pendingAttachments.value.filter((a) => a.attachmentId !== attachmentId);
}

async function onSend(): Promise<void> {
  const text = draft.value.trim();
  if (!text && pendingAttachments.value.length === 0) return;
  const ids = pendingAttachments.value.map((a) => a.attachmentId);
  emit('send', text, ids);
  draft.value = '';
  pendingAttachments.value = [];
  await nextTick();
  scrollToBottom();
}

// IME (한글/일본어) 조합 중 Enter 는 무시 — 조합 완료 후 다음 Enter 가 전송.
// 조합 중 Enter 를 잡으면 send 직후 composition end 결과가 textarea 에 다시 들어가 초기화가 안 보임.
function onEnter(e: KeyboardEvent): void {
  if (e.isComposing) return;
  e.preventDefault();
  void onSend();
}

function scrollToBottom(): void {
  if (!bodyRef.value) return;
  bodyRef.value.scrollTop = bodyRef.value.scrollHeight;
}

// nextTick 만으로는 *async render component (image / syntax-highlight 등)* 의 layout shift
// 후 scroll 위치가 상단으로 보이는 사고. 2 frames 후 한 번 더 박음 — render 완료 보장.
function scrollToBottomDeferred(): void {
  void nextTick().then(() => {
    scrollToBottom();
    requestAnimationFrame(() => {
      requestAnimationFrame(scrollToBottom);
    });
  });
}

// 마지막 메시지 ID watch — length 대신. fetchMessages 가 array 새로 박을 때 limit=100
// 초과 conversation 에서 옛 1 빠지고 새 1 추가되면 length 변화 없어 옛 watch 미발화 사고 fix.
watch(() => props.messages[props.messages.length - 1]?.messageId, scrollToBottomDeferred);
// partner 변경 시 scroll-to-bottom — agent 클릭 → 다른 conversation 의 message list 받음.
// 새 partner 의 마지막 메시지 ID 도 위 watch 가 잡지만, 빈 conversation 같은 edge 도 cover.
watch(() => props.partner?.agentId, scrollToBottomDeferred);

function statusLabel(s: AgentStatus): string {
  // 3 layer 통합: 온라인 / 오프라인 / 압축중.
  return { active: '온라인', waiting: '온라인', idle: '온라인', offline: '오프라인', compacting: '압축중', error: '오류' }[s] ?? s;
}
function avatar(s: AgentStatus): string {
  return { active: '🤖', waiting: '🙋', idle: '📝', error: '⚠️' }[s] ?? '📝';
}
function shortModel(m: string | null | undefined): string {
  if (!m) return '';
  return m.toLowerCase().startsWith('claude') ? 'claude' : m;
}
function ctxLevel(pct: number): string {
  if (pct >= 85) return 'red';
  if (pct >= 60) return 'orange';
  return 'green';
}

function statusBadge(status: string): string {
  return { sent: '⏳', delivered: '✓', replied: '✓✓', failed: '⚠' }[status] ?? '';
}

function formatTime(iso: string): string {
  const d = new Date(iso);
  const hh = String(d.getHours()).padStart(2, '0');
  const mm = String(d.getMinutes()).padStart(2, '0');
  return `${hh}:${mm}`;
}

function attachmentIcon(contentType: string | null | undefined): string {
  const ct = (contentType ?? '').toLowerCase();
  if (ct.startsWith('image/')) return '🖼';
  if (ct.startsWith('video/')) return '🎬';
  if (ct.startsWith('audio/')) return '🎵';
  if (ct === 'application/pdf') return '📄';
  if (ct.includes('zip') || ct.includes('tar') || ct.includes('gzip')) return '🗜';
  if (ct.startsWith('text/')) return '📝';
  return '📎';
}

function formatSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}
</script>

<style scoped>
.conv-view {
  display: flex; flex-direction: column;
  background: rgba(15, 23, 41, 0.4);
  flex: 1; min-width: 0; min-height: 0;
}

.conv-head {
  display: flex; align-items: center; gap: 12px;
  padding: 14px 22px;
  background: rgba(20, 28, 48, 0.3);
  border-bottom: 1px solid #1E2738;
  flex-shrink: 0;
}
.conv-head.empty { justify-content: center; color: #6B7785; }
.cv-placeholder { font-size: 13px; }
.cv-back {
  display: none; padding: 6px 10px;
  background: transparent; border: none; cursor: pointer;
  font-size: 18px; color: #8B95A5;
}
.cv-avatar {
  width: 38px; height: 38px; border-radius: 50%;
  background: linear-gradient(135deg, #2A3447, #1A2030);
  border: 1px solid #2A3447;
  display: flex; align-items: center; justify-content: center; font-size: 18px;
}
.cv-title { display: flex; flex-direction: column; gap: 2px; min-width: 0; }
.cv-name { font-size: 14px; font-weight: 700; color: #E5E9EE; }
.cv-meta {
  font-size: 11px; color: #8B95A5;
  display: inline-flex; align-items: center; gap: 5px;
}
.cv-meta-sep { color: #4B5563; }
.cv-status-dot {
  width: 7px; height: 7px; border-radius: 50%;
  background: #4B5563; flex-shrink: 0;
}
.cv-status-dot.active    { background: #10B981; box-shadow: 0 0 6px rgba(16, 185, 129, 0.6); }
.cv-status-dot.waiting   { background: #4F7FFF; box-shadow: 0 0 6px rgba(79, 127, 255, 0.6); }
.cv-status-dot.idle      { background: #F59E0B; }
.cv-status-dot.offline   { background: #4B5563; }
.cv-status-dot.error     { background: #F87171; }
.cv-status-dot.compacting{ background: #B89AFF; box-shadow: 0 0 6px rgba(184, 154, 255, 0.6); }
.cv-ctx { font-weight: 600; }
.cv-ctx.green  { color: #10B981; }
.cv-ctx.orange { color: #F59E0B; }
.cv-ctx.red    { color: #F87171; }

.conv-body { flex: 1; overflow-y: auto; padding: 24px 28px; }
.cv-empty { color: #6B7785; font-size: 13px; text-align: center; margin-top: 40px; }

.cv-msgs { list-style: none; padding: 0; margin: 0; display: flex; flex-direction: column; gap: 14px; }
.cv-msg { display: flex; animation: fadeIn .2s ease-out; }
.cv-msg.mine { justify-content: flex-end; }
.cv-msg.theirs { justify-content: flex-start; }
@keyframes fadeIn {
  from { opacity: 0; transform: translateY(8px); }
  to   { opacity: 1; transform: translateY(0); }
}

.cv-bubble {
  max-width: 70%;
  padding: 10px 14px;
  border-radius: 14px;
  font-size: 13px; line-height: 1.55;
  word-break: break-word; white-space: pre-wrap;
}
.cv-msg.mine .cv-bubble {
  background: linear-gradient(135deg, #4F7FFF, #7C5CFF);
  color: #fff;
  border-bottom-right-radius: 4px;
  box-shadow: 0 4px 14px rgba(79, 127, 255, 0.25);
}
.cv-msg.theirs .cv-bubble {
  background: #1F2937; color: #E5E9EE;
  border: 1px solid #2A3447;
  border-bottom-left-radius: 4px;
}
.cv-sender {
  font-size: 11px; color: #8B95A5; font-weight: 600;
  margin-bottom: 3px;
}
.cv-content { font-size: 13px; line-height: 1.55; }
.cv-foot { display: flex; gap: 6px; align-items: center; margin-top: 4px; font-size: 10px; color: #6B7785; }
.cv-working-row { margin-top: 6px; display: flex; justify-content: flex-end; }
/* 본인 (mine) 박는 메시지 = 우측 정렬. cv-msg.theirs 면 좌측. WorkingDeskChip
   은 *내가 보낸 메시지의 아래* 박히므로 우측 정렬 박음. */

/* AI 답신 작성중 placeholder — workingOnMessageId 살아있는 동안. answer 도착 시 사라짐. */
.cv-msg.typing-placeholder { animation: tpFade .25s ease; }
@keyframes tpFade {
  0% { opacity: 0; transform: translateY(4px); }
  100% { opacity: 1; transform: translateY(0); }
}
.cv-typing {
  display: flex;
  align-items: center;
  gap: 10px;
  font-size: 12px;
  color: #B0BCD0;
}
.cv-typing-text {
  font-style: italic;
}
/* progress bar — *흔한 dots 애니메이션* 회피. 좌→우 scanner stripe. */
.cv-typing-scanner {
  position: relative;
  width: 56px;
  height: 4px;
  background: rgba(107, 182, 255, 0.15);
  border-radius: 3px;
  overflow: hidden;
}
.cv-typing-scanner::before {
  content: '';
  position: absolute;
  top: 0;
  left: -20px;
  width: 20px;
  height: 100%;
  background: linear-gradient(90deg, transparent 0%, #6BB6FF 50%, transparent 100%);
  animation: tpScan 1.4s linear infinite;
}
@keyframes tpScan {
  0%   { left: -20px; }
  100% { left: 56px; }
}

/* hover popover — chip 위에 inline stage 박음. 모달 X. */
.cv-working-wrap { position: relative; display: inline-block; }
.cv-working-popover {
  position: absolute;
  bottom: calc(100% + 6px);   /* chip 위에 박힘 */
  right: 0;                    /* 우측 정렬 chip 와 일치 */
  z-index: 50;
  opacity: 0;
  pointer-events: none;
  transform: translateY(4px) scale(0.96);
  transform-origin: bottom right;
  transition: opacity .15s ease, transform .15s ease;
}
.cv-working-wrap:hover .cv-working-popover,
.cv-working-wrap:focus-within .cv-working-popover {
  opacity: 1;
  pointer-events: auto;
  transform: translateY(0) scale(1);
}
.cv-status.sent     { color: #6B7785; }
.cv-status.delivered{ color: #6BB6FF; }
.cv-status.replied  { color: #6BB6FF; font-weight: 700; }
.cv-status.failed   { color: #F87171; font-weight: 700; }

/* 차단/실패 메시지 — bubble 자체 highlight (옛 차단 표시 통일). policy block (context
   guard / hop / rate / canCommunicate) 또는 ws delivery fail 시 status=failed. */
.cv-msg.failed.mine .cv-bubble {
  background: linear-gradient(135deg, #B73E55, #A03048);
  box-shadow: 0 4px 14px rgba(183, 62, 85, 0.35);
  border: 1px solid rgba(248, 113, 113, 0.5);
}
.cv-msg.failed.theirs .cv-bubble {
  background: rgba(127, 29, 29, 0.25);
  border: 1px solid rgba(248, 113, 113, 0.5);
  color: #FECACA;
}

/* code block (markdown 또는 사용자 입력) */
.cv-bubble :deep(pre) {
  background: rgba(0, 0, 0, 0.3); border: 1px solid #2A3447;
  padding: 8px 10px; border-radius: 6px;
  font-family: ui-monospace, SFMono-Regular, monospace; font-size: 12px;
  overflow-x: auto; margin: 6px 0;
}
.cv-msg.mine .cv-bubble :deep(pre) { background: rgba(0,0,0,0.2); border-color: rgba(255,255,255,0.15); }
.cv-bubble :deep(code) {
  background: rgba(0, 0, 0, 0.3); padding: 1px 5px; border-radius: 3px;
  font-family: ui-monospace, SFMono-Regular, monospace; font-size: 11.5px;
}
.cv-msg.mine .cv-bubble :deep(code) { background: rgba(0,0,0,0.2); }

.conv-input {
  border-top: 1px solid #1E2738;
  padding: 16px 22px;
  background: rgba(15, 23, 41, 0.6);
  backdrop-filter: blur(8px);
  flex-shrink: 0;
  display: flex; flex-direction: column; gap: 8px;
}
.cv-textarea {
  flex: 1; resize: none; padding: 10px 14px;
  font-size: 13px; line-height: 1.55; font-family: inherit;
  background: #1A2030; border: 1px solid #2A3447; border-radius: 12px;
  color: #E5E9EE;
  transition: border-color .15s, box-shadow .15s;
}
.cv-textarea::placeholder { color: #4B5563; }
.cv-textarea:focus {
  outline: none; border-color: #4F7FFF;
  box-shadow: 0 0 0 3px rgba(79, 127, 255, 0.15);
}
.cv-textarea:disabled { background: #161B26; }
.cv-send {
  padding: 10px 20px; font-size: 13px; font-weight: 600;
  background: linear-gradient(135deg, #4F7FFF, #7C5CFF);
  color: #fff; border: none; border-radius: 10px;
  cursor: pointer;
  box-shadow: 0 4px 12px rgba(79, 127, 255, 0.3);
  transition: transform .1s, box-shadow .15s;
}
.cv-send:hover:not(:disabled) {
  box-shadow: 0 6px 18px rgba(79, 127, 255, 0.5);
  transform: translateY(-1px);
}
.cv-send:active:not(:disabled) { transform: translateY(0); }
.cv-send:disabled {
  background: #2A3447; color: #6B7785;
  cursor: not-allowed; box-shadow: none;
}

/* scrollbar */
.conv-body::-webkit-scrollbar { width: 10px; }
.conv-body::-webkit-scrollbar-track { background: transparent; }
.conv-body::-webkit-scrollbar-thumb { background: #2A3447; border-radius: 5px; border: 2px solid transparent; background-clip: padding-box; }
.conv-body::-webkit-scrollbar-thumb:hover { background: #3A4A66; background-clip: padding-box; }

/* 폰트 사이즈 — root section 의 --cv-font-size cssvar 가 메시지 본문/입력창 일괄 조정.
   사용자가 설정 모달에서 숫자 조절 (10-24px). chip / header / status 같은 보조 요소는 고정. */
.conv-view .cv-content { font-size: var(--cv-font-size, 13px); }
.conv-view .cv-textarea { font-size: var(--cv-font-size, 13px); }

/* 헤더의 ... 메뉴 */
.cv-head-actions { margin-left: auto; position: relative; }
.cv-menu-btn {
  background: transparent; border: none; cursor: pointer;
  color: #8B95A5; font-size: 22px; font-weight: 700; line-height: 1;
  padding: 4px 10px; border-radius: 8px;
  transition: background .1s, color .12s;
}
.cv-menu-btn:hover { background: rgba(79, 127, 255, 0.1); color: #E5E9EE; }
/* 설정 모달 — iTerm 스타일 폰트 크기 조절. body 에 Teleport 됨. */
.cv-settings-overlay {
  position: fixed; inset: 0;
  background: rgba(7, 11, 22, 0.6); backdrop-filter: blur(6px);
  display: flex; align-items: center; justify-content: center;
  z-index: 1000;
  animation: settingsFadeIn .15s ease-out;
}
@keyframes settingsFadeIn {
  from { opacity: 0; } to { opacity: 1; }
}
.cv-settings-modal {
  width: 380px; max-width: 90vw;
  background: #141C30; border: 1px solid #2A3447;
  border-radius: 14px;
  box-shadow: 0 20px 60px rgba(0, 0, 0, 0.6);
  color: #E5E9EE;
  animation: settingsSlideIn .18s ease-out;
}
@keyframes settingsSlideIn {
  from { opacity: 0; transform: translateY(8px) scale(0.98); }
  to { opacity: 1; transform: translateY(0) scale(1); }
}
.cv-settings-head {
  display: flex; align-items: center; justify-content: space-between;
  padding: 14px 18px;
  border-bottom: 1px solid #1E2738;
}
.cv-settings-head h3 {
  margin: 0; font-size: 14px; font-weight: 700;
  background: linear-gradient(90deg, #6BB6FF, #B89AFF);
  -webkit-background-clip: text; background-clip: text;
  -webkit-text-fill-color: transparent;
}
.cv-settings-x {
  background: transparent; border: none; cursor: pointer;
  color: #8B95A5; font-size: 14px; padding: 4px 8px; border-radius: 6px;
  transition: background .12s, color .12s;
}
.cv-settings-x:hover { background: rgba(248, 113, 113, 0.15); color: #FCA5A5; }
.cv-settings-body { padding: 18px; }
.cv-settings-field { display: flex; flex-direction: column; gap: 10px; }
.cv-settings-label {
  font-size: 11px; color: #8B95A5;
  text-transform: uppercase; letter-spacing: 0.06em; font-weight: 600;
}
.cv-settings-control { display: flex; align-items: center; gap: 8px; }
.cv-stepper {
  width: 32px; height: 32px;
  background: #1A2030; color: #B89AFF;
  border: 1px solid #2A3447; border-radius: 8px;
  font-size: 16px; font-weight: 700; cursor: pointer;
  transition: background .12s, color .12s, border-color .12s;
}
.cv-stepper:hover:not(:disabled) {
  background: #232C42; border-color: #4F7FFF; color: #fff;
}
.cv-stepper:disabled { opacity: 0.4; cursor: not-allowed; }
.cv-settings-num {
  width: 70px; padding: 6px 10px;
  background: #0F1729; border: 1px solid #2A3447; border-radius: 8px;
  color: #E5E9EE; font-size: 14px; font-family: ui-monospace, SFMono-Regular, monospace;
  text-align: center;
}
.cv-settings-num:focus {
  outline: none; border-color: #4F7FFF;
  box-shadow: 0 0 0 3px rgba(79, 127, 255, 0.15);
}
.cv-settings-range {
  font-size: 11px; color: #6B7785;
  margin-left: 6px; font-family: ui-monospace, SFMono-Regular, monospace;
}
.cv-settings-preview {
  margin-top: 4px; padding: 14px 16px;
  background: #1F2937; border: 1px solid #2A3447; border-radius: 10px;
  color: #C5CDD8; line-height: 1.55;
}
.cv-settings-actions {
  display: flex; justify-content: flex-end; gap: 8px;
  margin-top: 18px;
}
.cv-settings-reset {
  padding: 8px 14px; font-size: 12px;
  background: transparent; color: #8B95A5;
  border: 1px solid #2A3447; border-radius: 8px; cursor: pointer;
  transition: background .12s, color .12s;
}
.cv-settings-reset:hover { background: #1A2030; color: #E5E9EE; }
.cv-settings-done {
  padding: 8px 18px; font-size: 12px; font-weight: 600;
  background: linear-gradient(135deg, #4F7FFF, #7C5CFF);
  color: #fff; border: none; border-radius: 8px; cursor: pointer;
  transition: transform .1s, box-shadow .15s;
}
.cv-settings-done:hover {
  box-shadow: 0 4px 14px rgba(79, 127, 255, 0.4);
  transform: translateY(-1px);
}

/* 첨부 chip — 메시지 버블 안. 카카오톡 느낌 — 파일 아이콘 + 이름 + 크기 + 다운 아이콘 */
.cv-attachments { list-style: none; padding: 0; margin: 6px 0 0; display: flex; flex-direction: column; gap: 4px; }
.cv-att-chip {
  display: flex; align-items: center; gap: 8px;
  padding: 8px 10px;
  background: rgba(0, 0, 0, 0.18); border: 1px solid rgba(255, 255, 255, 0.06);
  border-radius: 8px;
  color: inherit; text-decoration: none;
  transition: background .12s, transform .1s;
  min-width: 200px;
}
.cv-msg.mine .cv-att-chip { background: rgba(0, 0, 0, 0.15); border-color: rgba(255, 255, 255, 0.18); }
.cv-msg.theirs .cv-att-chip { background: rgba(255, 255, 255, 0.04); border-color: #2A3447; }
.cv-att-chip:hover {
  background: rgba(79, 127, 255, 0.18);
  transform: translateY(-1px);
}
.cv-att-icon { font-size: 22px; line-height: 1; flex-shrink: 0; }
.cv-att-info { display: flex; flex-direction: column; min-width: 0; flex: 1; }
.cv-att-name {
  font-size: 13px; font-weight: 600;
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
  max-width: 240px;
}
.cv-att-size { font-size: 11px; color: #8B95A5; margin-top: 1px; }
.cv-msg.mine .cv-att-size { color: rgba(255, 255, 255, 0.7); }
.cv-att-download {
  flex-shrink: 0;
  font-size: 16px;
  width: 28px; height: 28px;
  display: flex; align-items: center; justify-content: center;
  border-radius: 50%;
  background: rgba(255, 255, 255, 0.1);
  transition: background .12s;
}
.cv-att-chip:hover .cv-att-download { background: rgba(255, 255, 255, 0.22); }

/* composer pending chips */
.cv-pending-attachments {
  display: flex; flex-wrap: wrap; gap: 6px; align-items: center;
  margin-bottom: 8px;
}
.cv-pending-uploading {
  font-size: 12px; color: #8B95A5;
  padding: 4px 10px; background: #1A2030; border-radius: 12px;
}
.cv-pending-chip {
  display: inline-flex; align-items: center; gap: 6px;
  padding: 4px 8px;
  background: #1A2030; border: 1px solid #2A3447; border-radius: 14px;
  font-size: 12px;
}
.cv-pending-name { max-width: 160px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.cv-pending-size { color: #8B95A5; font-size: 11px; }
.cv-pending-x {
  background: transparent; border: none; cursor: pointer;
  color: #8B95A5; font-size: 13px; padding: 0 2px;
}
.cv-pending-x:hover { color: #F87171; }

.cv-composer-row { display: flex; gap: 8px; align-items: flex-end; width: 100%; }
.cv-attach-btn {
  background: #1A2030; color: #B89AFF;
  border: 1px solid #2A3447; border-radius: 10px;
  width: 40px; height: 40px;
  font-size: 18px; cursor: pointer;
  transition: background .12s, transform .1s, border-color .12s;
  flex-shrink: 0;
}
.cv-attach-btn:hover:not(:disabled) {
  background: #232C42; border-color: #4F7FFF;
  transform: translateY(-1px);
}
.cv-attach-btn:disabled { opacity: 0.5; cursor: not-allowed; }
.cv-file-input { display: none; }

/* 모바일 */
@media (max-width: 768px) {
  .cv-back { display: block; }
  .cv-att-name { max-width: 160px; }
}
</style>
