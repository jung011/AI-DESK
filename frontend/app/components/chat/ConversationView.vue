<template>
  <section class="conv-view" :style="{ '--cv-font-size': `${fontSizePx}px`, '--cv-font-family': fontFamilyCss }">
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
            <!-- 채팅 메시지 markdown 렌더 — table / code / list / strong 등 시각 요소.
                 marked + dompurify 로 sanitize. XSS 차단 + 표 같은 풍부한 표현. -->
            <div
              v-if="m.content && m.content.trim()"
              class="cv-content cv-md"
              v-html="renderMd(m.content)"
            ></div>
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
              <!-- 실패 시 ↻ 버튼 박혀 사용자가 다시 보낼 수 있음.
                   status='failed' (backend 가 명시 failed 박은 거) 외 에도,
                   status='sent' 인데 *15초+ 지나도 deliveredAt null* 박혀있으면
                   stale 박힘 → 사용자가 ↻ 박아 다시 보낼 수 있도록 박음. backend 가
                   helper online 인 한 *failed 안 박는* 패턴 의 보완. -->
              <button
                v-if="m.fromAgentId === meId && isResendable(m)"
                type="button"
                class="cv-resend"
                title="다시 보내기"
                @click="onResend(m)">↻</button>
            </div>
          </div>
        </li>
        <!-- AI 답신 작성중 placeholder — 3 phase 분기:
             1) deliveredAwaitingReadId (helper PTY 도달, AI mark_read 전) → "답신중..." 텍스트
             2) workingOnMessageId (AI mark_read 후, 답신 전) → 책상 stage 애니메이션
             3) partner 답신 도착 → 둘 다 null → 실제 메시지 표시 -->
        <li v-if="deliveredAwaitingReadId && partner && !workingOnMessageId" class="cv-msg theirs typing-placeholder">
          <div class="cv-bubble">
            <div class="cv-sender">{{ partner.agentName }}</div>
            <div class="cv-typing">
              <em class="cv-typing-text">메세지 전송중</em>
              <span class="cv-typing-scanner"></span>
            </div>
          </div>
        </li>
        <li v-else-if="workingOnMessageId && partner" class="cv-msg theirs typing-placeholder">
          <div class="cv-bubble cv-bubble-stage">
            <div class="cv-sender">{{ partner.agentName }}</div>
            <WorkingDeskStage :agent-name="partner.agentName" />
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
            </div>
            <div class="cv-settings-field">
              <label class="cv-settings-label">폰트</label>
              <div class="cv-settings-control">
                <select class="cv-settings-select" v-model="fontFamilyKey" @change="setFontFamily(fontFamilyKey)">
                  <option v-for="f in FONT_OPTIONS" :key="f.key" :value="f.key" :style="{ fontFamily: f.css }">
                    {{ f.label }}
                  </option>
                </select>
              </div>
            </div>
            <div class="cv-settings-preview" :style="{ fontSize: `${fontSizePx}px`, fontFamily: fontFamilyCss }">
              미리보기 — 안녕하세요, 채팅 글자 크기 / 폰트 샘플입니다. The quick brown fox jumps over the lazy dog.
            </div>
            <div class="cv-settings-actions">
              <button class="cv-settings-reset" @click="resetSettings">기본값으로</button>
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
import WorkingDeskStage from '~/components/chat/WorkingDeskStage.vue';
import { renderMarkdown } from '~/utils/renderMarkdown';
import { useInputDrafts } from '~/composables/useInputDrafts';

const renderMd = renderMarkdown;

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
  (e: 'resend', m: MessageItem): void;
}>();

// 옵션 — failed / stale-sent 메시지 재전송. parent (chat.vue) 가 같은 partner 로
// 새 message 박을 거. 사용자가 ↻ 클릭 시 trigger.
function onResend(m: MessageItem): void {
  emit('resend', m);
}

// stale-sent — backend 가 helper online 박혀있는 한 *failed 안 박는* 패턴 의 보완.
// status='sent' + deliveredAt null + 15초+ 지나면 사용자한테 ↻ 노출 박음.
// 시계 박힌 거 reactivity 위해 1초 cycle ref 박음 — Date.now() 직접 박으면 reactive X.
const _now = ref(Date.now());
setInterval(() => { _now.value = Date.now(); }, 1000);
function isResendable(m: MessageItem): boolean {
  if (m.status === 'failed') return true;
  if (m.status === 'sent' && !m.deliveredAt) {
    // 8초 = backend 의 retryAckTimeoutSec(5s) + buffer(3s). 한 backend retry 사이클
    // 박힌 후에도 안 박힌 거 = stale 박은 거 판단 OK.
    const age = _now.value - new Date(m.createdAt).getTime();
    return age > 8000;
  }
  return false;
}

// partner 별 draft 보존 (per-partner). 옛 단일 ref('') 패턴 박혔는데 partner 전환 시
// 옛 draft 가 새 partner 채팅창에 *공유* 박히는 사고 → 사용자가 다른 사람한테 보낼 메시지
// 안 박힌 채로 잘못된 partner 한테 발사 위험. [[feedback-input-shared-on-partner-switch]]
// 패턴 (옛 WebTerminal 의 :key + useInputDrafts 패턴 정합).
const inputDrafts = useInputDrafts();
const draft = ref(props.partner?.agentId ? inputDrafts.get(props.partner.agentId) : '');
watch(draft, (v) => {
  if (props.partner?.agentId) inputDrafts.set(props.partner.agentId, v);
});
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
/**
 * 마지막 내 발신 메시지의 *delivery / read* 상태 추적. 3 phase 분기:
 *  - lastSentMessage 가 *delivered (helper push 박힘) but readAt 안 박힘* → "답신중..." 텍스트 (간단한 typing indicator)
 *  - lastSentMessage 의 *readAt 박힘* (AI 가 mark_read mcp 호출) → WorkingDeskStage (책상 애니메이션)
 *  - partner 답신 도착 → null (placeholder 사라짐)
 *  - status=failed → 별개 resend 박힘 (cv-status 옆 ↻ 버튼)
 */
const lastSentToPartner = computed<MessageItem | null>(() => {
  if (!props.partner) return null;
  const list = visibleMessages.value;
  for (let i = list.length - 1; i >= 0; i--) {
    const m = list[i] as MessageItem;
    if (!m) continue;
    if (m.fromAgentId === props.partner.agentId && m.toAgentId === props.meId) {
      // partner → me 메시지가 더 최신 → 이미 답신 옴 → placeholder X
      return null;
    }
    if (m.fromAgentId === props.meId && m.toAgentId === props.partner.agentId) {
      return m;
    }
  }
  return null;
});
// helper PTY 박힘 + AI mark_read 박은 후 — 책상 애니메이션 (옛 동작)
const workingOnMessageId = computed<string | null>(() => {
  const m = lastSentToPartner.value;
  return m && m.readAt ? m.messageId : null;
});
// 사용자 보낸 마지막 메시지 = mark_read 직전까지 "메세지 전송중" 표시.
// 단 stale-sent (>8s deliveredAt null) 상태이면 placeholder 숨김 — ↻ 와 중복 회피.
// 사용자 의도: 둘 중 하나만 — 정상 진행 중이면 placeholder, 지연되면 resend.
const deliveredAwaitingReadId = computed<string | null>(() => {
  const m = lastSentToPartner.value;
  if (!m || m.readAt) return null;
  if (isResendable(m)) return null;  // stale → ↻ 만 표시, placeholder 숨김
  return m.messageId;
});
const FONT_DEFAULT_PX = 13;
const FONT_MIN_PX = 10;
const FONT_MAX_PX = 24;
const fontSizePx = ref<number>(FONT_DEFAULT_PX);
const fontSizePxInput = ref<number>(FONT_DEFAULT_PX);

// 폰트 family — 유명한 sans / serif / mono 박음. *CSS 우선순위 stack* 으로 fallback.
// 한국어 우선 (Pretendard / Noto Sans KR / Spoqa) + 영문 mainstream + serif + mono.
const FONT_OPTIONS = [
  { key: 'system', label: '시스템 기본', css: '-apple-system, BlinkMacSystemFont, "Helvetica Neue", "Segoe UI", "Apple SD Gothic Neo", "Malgun Gothic", "Nanum Gothic", sans-serif' },
  { key: 'pretendard', label: 'Pretendard', css: '"Pretendard Variable", Pretendard, -apple-system, BlinkMacSystemFont, "Helvetica Neue", sans-serif' },
  { key: 'noto-sans-kr', label: 'Noto Sans KR', css: '"Noto Sans KR", "Noto Sans CJK KR", -apple-system, sans-serif' },
  { key: 'spoqa', label: 'Spoqa Han Sans Neo', css: '"Spoqa Han Sans Neo", -apple-system, sans-serif' },
  { key: 'inter', label: 'Inter', css: 'Inter, -apple-system, BlinkMacSystemFont, sans-serif' },
  { key: 'roboto', label: 'Roboto', css: 'Roboto, -apple-system, sans-serif' },
  { key: 'ibm-plex', label: 'IBM Plex Sans', css: '"IBM Plex Sans", "IBM Plex Sans KR", -apple-system, sans-serif' },
  { key: 'sf-pro', label: 'SF Pro Display', css: '"SF Pro Display", -apple-system, BlinkMacSystemFont, sans-serif' },
  { key: 'helvetica', label: 'Helvetica Neue', css: '"Helvetica Neue", Helvetica, Arial, sans-serif' },
  { key: 'nanum-gothic', label: '나눔고딕', css: '"Nanum Gothic", -apple-system, sans-serif' },
  { key: 'malgun', label: '맑은 고딕', css: '"Malgun Gothic", "맑은 고딕", -apple-system, sans-serif' },
  { key: 'noto-serif-kr', label: 'Noto Serif KR', css: '"Noto Serif KR", "Noto Serif", Georgia, serif' },
  { key: 'georgia', label: 'Georgia', css: 'Georgia, "Noto Serif KR", serif' },
  { key: 'jetbrains-mono', label: 'JetBrains Mono', css: '"JetBrains Mono", ui-monospace, SFMono-Regular, Menlo, Consolas, monospace' },
  { key: 'sf-mono', label: 'SF Mono', css: 'ui-monospace, SFMono-Regular, "SF Mono", Menlo, monospace' },
] as const;
type FontKey = typeof FONT_OPTIONS[number]['key'];
const FONT_DEFAULT_KEY: FontKey = 'system';
const fontFamilyKey = ref<FontKey>(FONT_DEFAULT_KEY);
const fontFamilyCss = computed(() => FONT_OPTIONS.find((f) => f.key === fontFamilyKey.value)?.css || FONT_OPTIONS[0].css);

// iTerm 스타일 — 숫자(px) 단위 직접 조절. localStorage 저장.
onMounted(() => {
  if (typeof window === 'undefined') return;
  const saved = window.localStorage.getItem('aidesk.chat.fontSizePx');
  const n = saved ? Number(saved) : NaN;
  if (Number.isFinite(n) && n >= FONT_MIN_PX && n <= FONT_MAX_PX) {
    fontSizePx.value = n;
    fontSizePxInput.value = n;
  }
  // 폰트 family 복원
  const savedFont = window.localStorage.getItem('aidesk.chat.fontFamilyKey');
  if (savedFont && FONT_OPTIONS.some((f) => f.key === savedFont)) {
    fontFamilyKey.value = savedFont as FontKey;
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

function setFontFamily(key: FontKey): void {
  fontFamilyKey.value = key;
  if (typeof window !== 'undefined') {
    window.localStorage.setItem('aidesk.chat.fontFamilyKey', key);
  }
}

function resetSettings(): void {
  setFontSizePx(FONT_DEFAULT_PX);
  setFontFamily(FONT_DEFAULT_KEY);
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

// duplicate send 차단 — onSend 호출 시점에 *이미 sending* 박혀있거나, *방금 emit
// 박은 거 처리 중* 박혀있으면 skip. 옛 사고 = 사용자가 빠르게 두번 클릭 / Enter
// 박을 때 props.sending 박힌 거 *update 박기 전* 의 race window 박혀 두 번 emit 박힘.
// 로컬 in-flight guard 박아 race window 0 박음.
let sendInFlight = false;
async function onSend(): Promise<void> {
  if (props.sending || sendInFlight) return;
  const text = draft.value.trim();
  if (!text && pendingAttachments.value.length === 0) return;
  sendInFlight = true;
  const ids = pendingAttachments.value.map((a) => a.attachmentId);
  emit('send', text, ids);
  draft.value = '';
  // store 도 비움 — 옛 watch(draft) 가 store.set 박지만 timing safety
  if (props.partner?.agentId) inputDrafts.clear(props.partner.agentId);
  pendingAttachments.value = [];
  await nextTick();
  scrollToBottom();
  // 짧은 grace — props.sending 박힘이 update 박힐 시점 (parent → child reactive)
  setTimeout(() => { sendInFlight = false; }, 300);
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
// partner 전환 시 draft 복원 + pendingAttachments 비움.
// draft = per-partner store 박혀있어 *그 partner 박은 옛 입력* 복원.
// pendingAttachments = 업로드 박은 거 partner 별 분리 X (session-bound) → 비움.
watch(() => props.partner?.agentId, (newId) => {
  draft.value = newId ? inputDrafts.get(newId) : '';
  pendingAttachments.value = [];
});
// AI 답신 작성중 placeholder bubble 이 추가 / 제거되면 scroll 도 따라옴. 옛에는
// workingOnMessageId 가 새로 set 되도 messages array 자체는 안 변해 위 messageId
// watch 미발화 → 사용자가 *placeholder 안 보임* 사고. visibleMessages 의 마지막
// messageId 외 *workingOnMessageId 변화* 도 scroll trigger 박음.
watch(workingOnMessageId, scrollToBottomDeferred);
// "메세지 전송중" placeholder 박힐 때 layout 변경 → 사용자 자동 스크롤 박혀야 input box
// 자리 박힘. 옛 rc120 의 fix 박은 거 (duplicate send 사고와 무관 박힘, 재 적용 박음).
watch(deliveredAwaitingReadId, scrollToBottomDeferred);

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
/* markdown 규칙은 별 non-scoped <style> 블록 (파일 끝). v-html injected content 는
   Vue 의 scoped data attribute 안 박혀 .cv-md table {...} (scoped) 미적용 사고 fix. */
/* 다크모드 — 옛 #6B7785 박힌 거 어두운 bubble 위 안 보임 사고. #E5EBF5 (옛 다크모드 의
   primary body text 색) + bold 박아 가독성 확실. */
.cv-foot { display: flex; gap: 6px; align-items: center; margin-top: 4px; font-size: 10px; color: #E5EBF5; font-weight: 600; }

/* AI 답신 작성중 placeholder — workingOnMessageId 살아있는 동안 stage bubble.
   답신 도착 시 자동 사라짐 + 실제 메시지로 교체. */
.cv-msg.typing-placeholder { animation: tpFade .25s ease; }
@keyframes tpFade {
  0% { opacity: 0; transform: translateY(4px); }
  100% { opacity: 1; transform: translateY(0); }
}
/* stage bubble — 옛 text bubble 스타일과 다름. stage 자체가 내부 background +
   border 박혀있으니 wrapper 의 padding/background 최소화. sender 만 위에 박음. */
.cv-bubble-stage {
  padding: 0 !important;
  background: transparent !important;
  border: none !important;
}
.cv-bubble-stage .cv-sender {
  padding: 0 4px 4px 4px;
}
.cv-status.sent     { color: #E5EBF5; font-weight: 600; }

/* failed 메시지 의 ↻ 재전송 버튼 — cv-status 옆 박힘. 사용자 클릭 시 onResend(m). */
.cv-resend {
  display: inline-flex; align-items: center; justify-content: center;
  width: 18px; height: 18px;
  padding: 0; margin-left: 2px;
  background: transparent; border: 1px solid #F87171;
  border-radius: 50%;
  color: #F87171; font-size: 11px; font-weight: 700;
  line-height: 1; cursor: pointer;
}
.cv-resend:hover { background: #F87171; color: #fff; }

/* 답신 작성중 indicator — helper PTY 도달 박혔지만 AI mark_read 전 상태.
   옛 commit b78d4a3 박힌 "답신 작성중" 텍스트 + 좌→우 scanner stripe (흔한 dots 회피).
   HTML 시안 (working-desk-as-placeholder-preview.html) 의 옛 scene 박은 거 정합.
   AI 가 mark_read mcp 호출 후 full stage 박혀 교체. */
.cv-typing {
  display: flex; align-items: center; gap: 10px;
  font-size: 12px; color: #B0BCD0;
}
.cv-typing-text { font-style: italic; }
.cv-typing-scanner {
  position: relative;
  width: 56px; height: 4px;
  background: rgba(107, 182, 255, 0.15);
  border-radius: 3px; overflow: hidden;
}
.cv-typing-scanner::before {
  content: '';
  position: absolute;
  top: 0; left: -20px;
  width: 20px; height: 100%;
  background: linear-gradient(90deg, transparent 0%, #6BB6FF 50%, transparent 100%);
  animation: cvTpScan 1.4s linear infinite;
}
@keyframes cvTpScan {
  0%   { left: -20px; }
  100% { left: 56px; }
}
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

/* 폰트 사이즈 + family — root section 의 cssvar 가 메시지 본문/입력창 일괄 조정.
   사용자가 설정 모달에서 숫자 조절 (10-24px) + 폰트 family 선택 (시스템 / Pretendard / Inter 등).
   chip / header / status 같은 보조 요소는 고정. */
.conv-view .cv-content { font-size: var(--cv-font-size, 13px); font-family: var(--cv-font-family, inherit); }
.conv-view .cv-textarea { font-size: var(--cv-font-size, 13px); font-family: var(--cv-font-family, inherit); }
.conv-view .cv-sender { font-family: var(--cv-font-family, inherit); }

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
.cv-settings-select {
  flex: 1; min-width: 0;
  padding: 8px 12px;
  background: #0F1729; border: 1px solid #2A3447; border-radius: 8px;
  color: #E5E9EE; font-size: 13px;
  cursor: pointer;
  appearance: none;
  -webkit-appearance: none;
  background-image: url("data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 12 12'><path fill='%236BB6FF' d='M2 4l4 4 4-4z'/></svg>");
  background-repeat: no-repeat;
  background-position: right 10px center;
  background-size: 12px;
  padding-right: 32px;
}
.cv-settings-select:focus {
  outline: none; border-color: #6BB6FF;
  box-shadow: 0 0 0 3px rgba(107, 182, 255, 0.15);
}
.cv-settings-select option {
  background: #1E2738; color: #E5E9EE;
  padding: 6px;
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

<!--
  markdown 렌더 규칙은 *non-scoped* 박음. v-html 로 injected HTML 은 Vue 의 scoped
  data-v-xxx attribute 안 박혀, 위의 <style scoped> 안 .cv-md table {...} 규칙이
  적용 안 되는 사고. non-scoped 로 글로벌 박아 v-html 자식 element 도 정상 매칭.
-->
<style>
.cv-md, .cv-md * { color: #FFFFFF; }
.cv-md p { margin: 0 0 6px; }
.cv-md p:last-child { margin: 0; }
.cv-md strong { font-weight: 800; color: #FFFFFF; }
.cv-md em { font-style: italic; color: #FFFFFF; }
.cv-md del, .cv-md s { text-decoration: line-through; opacity: 0.7; }
.cv-md code {
  background: rgba(107, 182, 255, 0.22);
  color: #E0EFFF;
  padding: 1px 6px;
  border-radius: 3px;
  font-family: ui-monospace, SFMono-Regular, monospace;
  font-size: 0.92em;
  border: 1px solid rgba(107, 182, 255, 0.35);
}
.cv-md pre {
  background: #050810;
  border: 2px solid #6BB6FF;
  border-radius: 6px;
  padding: 10px 12px;
  margin: 8px 0;
  overflow-x: auto;
}
.cv-md pre code {
  background: transparent;
  padding: 0;
  border: none;
  color: #FFFFFF;
  font-size: 12px;
  white-space: pre;
}
.cv-md ul, .cv-md ol { margin: 4px 0 6px; padding-left: 22px; color: #FFFFFF; }
.cv-md li { margin: 2px 0; color: #FFFFFF; }
.cv-md blockquote {
  margin: 8px 0;
  padding: 6px 12px;
  border-left: 4px solid #6BB6FF;
  background: rgba(107, 182, 255, 0.1);
  color: #FFFFFF;
}
.cv-md h1, .cv-md h2, .cv-md h3, .cv-md h4 {
  margin: 12px 0 8px;
  font-weight: 800;
  color: #FFFFFF;
  border-bottom: 2px solid #6BB6FF;
  padding-bottom: 6px;
}
.cv-md h1 { font-size: 1.3em; }
.cv-md h2 { font-size: 1.18em; }
.cv-md h3 { font-size: 1.1em; }
.cv-md h4 { font-size: 1em; border-bottom: 2px solid #4A5A78; }
.cv-md a { color: #93C5FD; text-decoration: underline; }
.cv-md a:hover { color: #BFDBFE; }
.cv-md hr {
  border: none;
  border-top: 2px solid #6BB6FF;
  margin: 12px 0;
}
.cv-md table {
  width: 100%;
  border-collapse: collapse;
  margin: 12px 0;
  font-size: 14px;
  background: #050810;
  border: 3px solid #6BB6FF;
}
.cv-md thead {
  background: linear-gradient(135deg, rgba(107, 182, 255, 0.4), rgba(184, 154, 255, 0.4));
}
.cv-md th {
  padding: 10px 12px;
  text-align: left;
  font-weight: 800;
  color: #FFFFFF;
  border: 2px solid #6BB6FF;
}
.cv-md td {
  padding: 10px 12px;
  border: 2px solid #6BB6FF;
  color: #FFFFFF;
  vertical-align: top;
}
.cv-md tbody tr:hover { background: rgba(107, 182, 255, 0.15); }
</style>
