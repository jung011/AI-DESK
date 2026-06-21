<template>
  <section class="term-view">
    <header v-if="partner" class="tv-head">
      <button v-if="showBack" class="tv-back" @click="$emit('back')" aria-label="뒤로">←</button>
      <span class="tv-avatar" :class="partner.status">{{ avatar(partner.status) }}</span>
      <div class="tv-title">
        <div class="tv-name">{{ partner.agentName }}</div>
        <div class="tv-meta">
          <span class="tv-status-dot" :class="partner.status"></span>
          <span>{{ statusLabel(partner.status) }}</span>
          <span class="tv-meta-sep">·</span>
          <code class="tv-cwd">{{ partner.workspaceDir || '/' }}</code>
        </div>
      </div>
      <div class="tv-head-actions">
        <button class="tv-menu-btn" @click.stop="settingsOpen = true" aria-label="설정">⋯</button>
      </div>
    </header>
    <header v-else class="tv-head empty">
      <span class="tv-placeholder">터미널을 열 에이전트를 왼쪽에서 선택하세요</span>
    </header>

    <div v-if="partner" class="tv-body">
      <div class="tv-statusbar">
        <span class="tv-dots">
          <span class="d-red"></span><span class="d-yel"></span><span class="d-grn"></span>
        </span>
        <span class="tv-name-small">{{ partner.agentName }}</span>
        <span class="tv-meta-small">{{ partner.workspaceDir || '/' }} · {{ cols }}×{{ rows }}</span>
        <div class="tv-right">
          <span class="tv-conn" :class="connClass">{{ connText }}</span>
        </div>
      </div>
      <div ref="termHost" class="tv-term" :style="{ '--tv-font-size': `${fontSizePx}px` }"></div>
    </div>

    <!-- 폰트 사이즈 모달 (채팅 cv-settings-modal 와 동일 스타일) -->
    <Teleport to="body">
      <div v-if="settingsOpen" class="tv-settings-overlay" @click="settingsOpen = false">
        <div class="tv-settings-modal" @click.stop>
          <header class="tv-settings-head">
            <h3>터미널 설정</h3>
            <button class="tv-settings-x" @click="settingsOpen = false" aria-label="닫기">✕</button>
          </header>
          <div class="tv-settings-body">
            <div class="tv-settings-label">폰트 크기 (px)</div>
            <div class="tv-settings-control">
              <button class="tv-stepper" @click="bumpFontSize(-1)" :disabled="fontSizePx <= 10" aria-label="감소">−</button>
              <input
                class="tv-settings-num"
                type="number"
                v-model.number="fontSizePxInput"
                min="10"
                max="24"
                @change="applyFontSizeInput"
              />
              <button class="tv-stepper" @click="bumpFontSize(1)" :disabled="fontSizePx >= 24" aria-label="증가">＋</button>
              <span class="tv-settings-range">10 — 24</span>
            </div>
            <div class="tv-settings-actions">
              <button class="tv-settings-reset" @click="resetFontSize">기본값 14px</button>
              <button class="tv-settings-done" @click="settingsOpen = false">완료</button>
            </div>
          </div>
        </div>
      </div>
    </Teleport>
  </section>
</template>

<script setup lang="ts">
import type { AgentItem, AgentStatus } from '~/vo/agents/AgentVo';

const props = defineProps<{
  partner: AgentItem | null;
  showBack: boolean;
}>();

defineEmits<{ (e: 'back'): void }>();

const termHost = ref<HTMLElement | null>(null);
const settingsOpen = ref(false);
const FONT_DEFAULT_PX = 14;
const FONT_MIN_PX = 10;
const FONT_MAX_PX = 24;
const fontSizePx = ref<number>(FONT_DEFAULT_PX);
const fontSizePxInput = ref<number>(FONT_DEFAULT_PX);

const cols = ref(80);
const rows = ref(24);
const connClass = ref<'pending' | 'mock' | 'live' | 'down'>('mock');
const connText = computed(() => {
  return { pending: '준비 중', mock: 'mockup', live: '연결됨', down: '끊김' }[connClass.value];
});

// SSR 안전 — xterm.js 는 client only.
let term: any = null;
let fitAddon: any = null;
let webLinks: any = null;
let resizeObserver: ResizeObserver | null = null;
let ws: WebSocket | null = null;
let reconnectTimer: ReturnType<typeof setTimeout> | null = null;

// helper WS URL — 사용자 mac 의 helper 직접 연결.
// dev 분리 인스턴스 = 30084 (별도 process, AIDESK_HUB_URL=localhost:30081).
// prod = 30083 (LaunchAgent, AIDESK_HUB_URL=aidesk.kaflix.internal).
// Vite tree-shake 으로 prod build 에는 30083 만 남음.
const HELPER_WS_URL = import.meta.dev
  ? 'ws://127.0.0.1:30084/ws/terminal'
  : 'ws://127.0.0.1:30083/ws/terminal';

async function ensureXterm(): Promise<void> {
  if (import.meta.server) return;
  if (term) return;
  const [{ Terminal }, { FitAddon }, { WebLinksAddon }] = await Promise.all([
    import('@xterm/xterm'),
    import('@xterm/addon-fit'),
    import('@xterm/addon-web-links'),
  ]);
  // xterm CSS — entry 가 따로 export. dynamic import 시 plugin 으로 처리.
  await import('@xterm/xterm/css/xterm.css' as string).catch(() => null);

  term = new Terminal({
    cursorBlink: true,
    cursorStyle: 'bar',
    fontFamily: "ui-monospace, SFMono-Regular, Menlo, 'Apple SD Gothic Neo', monospace",
    fontSize: fontSizePx.value,
    lineHeight: 1.2,
    scrollback: 5000,
    allowProposedApi: true,
    theme: {
      background: '#0E1424',
      foreground: '#E5E9EE',
      cursor: '#B89AFF',
      cursorAccent: '#0E1424',
      selectionBackground: 'rgba(79, 127, 255, 0.35)',
      black:        '#0E1424',
      red:          '#F87171',
      green:        '#10B981',
      yellow:       '#F59E0B',
      blue:         '#4F7FFF',
      magenta:      '#B89AFF',
      cyan:         '#6BB6FF',
      white:        '#C5CDD8',
      brightBlack:  '#4B5563',
      brightRed:    '#FCA5A5',
      brightGreen:  '#34D399',
      brightYellow: '#FBBF24',
      brightBlue:   '#6BB6FF',
      brightMagenta:'#D8B4FE',
      brightCyan:   '#7DD3FC',
      brightWhite:  '#FFFFFF',
    },
  });
  fitAddon = new FitAddon();
  webLinks = new WebLinksAddon();
  term.loadAddon(fitAddon);
  term.loadAddon(webLinks);
  if (termHost.value) {
    term.open(termHost.value);
    requestAnimationFrame(() => doFit());
  }
  // claude TUI 가 application mouse mode (CSI ?1000h 등) 박으면 xterm 의 wheel handler
  // 가 escape sequence 로 application 에 전달 → claude 입력창에 paste 사고.
  // attachCustomWheelEventHandler 의 return false = xterm 의 wheel 처리 *완전 차단*
  // → browser default (page scroll) 만 작동. scrollback 도 같이 차단되지만 claude TUI
  // alt screen 에서는 scrollback 무의미 → 사용자 가치 큼.
  if (typeof term.attachCustomWheelEventHandler === 'function') {
    term.attachCustomWheelEventHandler(() => false);
  }
  term.onData((data: string) => {
    if (ws && ws.readyState === WebSocket.OPEN) {
      // binary frame — utf-8 encode 후 ArrayBuffer 로 전송.
      const buf = new TextEncoder().encode(data);
      ws.send(buf);
    }
  });

  resizeObserver = new ResizeObserver(() => {
    doFit();
    sendResize();
  });
  if (termHost.value) resizeObserver.observe(termHost.value);
}

function sendResize(): void {
  if (!term) return;
  if (!ws || ws.readyState !== WebSocket.OPEN) return;
  try {
    ws.send(JSON.stringify({ type: 'resize', cols: term.cols, rows: term.rows }));
  } catch { /* ignore */ }
}

function connectWs(): void {
  if (!term) return;
  if (ws) { try { ws.close(); } catch { /* ignore */ } ws = null; }

  const cwd = props.partner?.workspaceDir || '';
  const agentId = props.partner?.agentId || '';
  const tmuxSession = props.partner?.tmuxSession || '';
  const cols = term.cols || 80;
  const rows = term.rows || 24;
  // dev 전용 — claude 의 aidesk-channel mcp 가 *현재 페이지의 backend* 와 통신하도록
  // helper 가 workspace mcp env 의 AIDESK_API_URL override.
  const apiUrl = import.meta.dev
    ? `${window.location.protocol}//${window.location.hostname}:30081`
    : '';
  let url = `${HELPER_WS_URL}?cwd=${encodeURIComponent(cwd)}&agentId=${encodeURIComponent(agentId)}&cols=${cols}&rows=${rows}`;
  if (apiUrl) url += `&apiUrl=${encodeURIComponent(apiUrl)}`;
  // tmuxSession — helper 가 tmux attach 패턴 사용. ws 끊김 = detach, claude 상태 유지.
  if (tmuxSession) url += `&tmuxSession=${encodeURIComponent(tmuxSession)}`;
  connClass.value = 'pending';

  let s: WebSocket;
  try {
    s = new WebSocket(url);
  } catch (e) {
    term.writeln(`\r\n\x1b[38;2;248;113;113m✗ helper WS 연결 실패: ${e}\x1b[0m`);
    connClass.value = 'down';
    return;
  }
  s.binaryType = 'arraybuffer';
  ws = s;

  s.onopen = () => {
    connClass.value = 'live';
    sendResize();
  };
  s.onmessage = (ev) => {
    if (typeof ev.data === 'string') {
      // control TEXT (pong 등) 은 무시 — 출력은 binary 만.
      return;
    }
    const data = ev.data instanceof ArrayBuffer ? new Uint8Array(ev.data) : ev.data;
    if (term && data) term.write(data);
  };
  s.onerror = () => {
    if (term) term.writeln('\r\n\x1b[38;2;248;113;113m✗ helper WS 오류\x1b[0m');
    connClass.value = 'down';
  };
  s.onclose = (ev) => {
    connClass.value = 'down';
    if (term) {
      term.writeln(`\r\n\x1b[38;2;245;158;11m[연결 끊김]\x1b[0m code=${ev.code} — 3초 후 자동 재연결 시도…`);
    }
    // 같은 partner 면 3s 후 자동 reconnect. 사용자가 agent 바꾸면 watch 가 disconnect 후 새로 연결.
    if (ws === s && props.partner?.agentId) {
      const sameAgentId = props.partner.agentId;
      reconnectTimer = setTimeout(() => {
        if (props.partner?.agentId === sameAgentId && term) {
          term.writeln('\x1b[38;2;107;117;133m[재연결 시도]\x1b[0m');
          connectWs();
        }
      }, 3000);
    }
  };
}

function disconnectWs(): void {
  if (reconnectTimer) {
    clearTimeout(reconnectTimer);
    reconnectTimer = null;
  }
  if (ws) {
    try { ws.close(); } catch { /* ignore */ }
    ws = null;
  }
  connClass.value = 'pending';
}

function doFit(): void {
  if (!term || !fitAddon) return;
  try {
    fitAddon.fit();
    cols.value = term.cols;
    rows.value = term.rows;
  } catch { /* ignore */ }
}

function resetAndConnect(): void {
  if (!term) return;
  term.clear();
  const name = props.partner?.agentName ?? '(선택 없음)';
  const cwd = props.partner?.workspaceDir ?? '/';
  term.writeln('\x1b[1;38;2;107;182;255mAI Desk\x1b[0m 웹 터미널 — \x1b[38;2;184;154;255m' + name + '\x1b[0m');
  term.writeln('cwd: \x1b[38;2;107;182;255m' + cwd + '\x1b[0m');
  term.writeln('\x1b[38;2;107;117;133mhelper 에 연결 중…\x1b[0m');
  connectWs();
}

// 폰트 사이즈
function applyFontSize(n: number): void {
  const clamped = Math.max(FONT_MIN_PX, Math.min(FONT_MAX_PX, Math.round(n)));
  fontSizePx.value = clamped;
  fontSizePxInput.value = clamped;
  if (term) {
    term.options.fontSize = clamped;
    doFit();
  }
  if (typeof window !== 'undefined') {
    window.localStorage.setItem('aidesk.term.fontSizePx', String(clamped));
  }
}
function bumpFontSize(delta: number): void { applyFontSize(fontSizePx.value + delta); }
function applyFontSizeInput(): void {
  const n = Number(fontSizePxInput.value);
  if (Number.isFinite(n)) applyFontSize(n);
  else fontSizePxInput.value = fontSizePx.value;
}
function resetFontSize(): void { applyFontSize(FONT_DEFAULT_PX); }

// Esc 로 모달 닫기
function onSettingsKey(e: KeyboardEvent): void {
  if (e.key === 'Escape' && settingsOpen.value) settingsOpen.value = false;
}

onMounted(async () => {
  if (typeof window !== 'undefined') {
    const saved = window.localStorage.getItem('aidesk.term.fontSizePx');
    const n = saved ? Number(saved) : NaN;
    if (Number.isFinite(n) && n >= FONT_MIN_PX && n <= FONT_MAX_PX) {
      fontSizePx.value = n;
      fontSizePxInput.value = n;
    }
    document.addEventListener('keydown', onSettingsKey);
  }
  if (props.partner) {
    await ensureXterm();
    resetAndConnect();
  }
});
onBeforeUnmount(() => {
  if (typeof document !== 'undefined') document.removeEventListener('keydown', onSettingsKey);
  disconnectWs();
  if (resizeObserver) { resizeObserver.disconnect(); resizeObserver = null; }
  if (term) { try { term.dispose(); } catch { /* ignore */ } term = null; }
});

watch(() => props.partner?.agentId, async (id) => {
  if (!id) {
    disconnectWs();
    return;
  }
  if (!term) await ensureXterm();
  disconnectWs();
  resetAndConnect();
});

function statusLabel(s: AgentStatus): string {
  return { active: '작업중', waiting: '응답 대기', idle: '대기중', offline: '오프라인', compacting: '압축 중', error: '오류' }[s] ?? s;
}
function avatar(s: AgentStatus): string {
  return { active: '🤖', waiting: '🙋', idle: '📝', error: '⚠️' }[s] ?? '📝';
}
</script>

<style scoped>
.term-view {
  display: flex; flex-direction: column;
  background: rgba(15, 23, 41, 0.4);
  flex: 1; min-width: 0; min-height: 0;
}

.tv-head {
  display: flex; align-items: center; gap: 12px;
  padding: 14px 22px;
  background: rgba(20, 28, 48, 0.3);
  border-bottom: 1px solid #1E2738;
  flex-shrink: 0;
}
.tv-head.empty { justify-content: center; color: #6B7785; }
.tv-placeholder { font-size: 13px; }
.tv-back {
  display: none; padding: 6px 10px;
  background: transparent; border: none; cursor: pointer;
  font-size: 18px; color: #8B95A5;
}
.tv-avatar {
  width: 38px; height: 38px; border-radius: 50%;
  background: linear-gradient(135deg, #2A3447, #1A2030);
  border: 1px solid #2A3447;
  display: flex; align-items: center; justify-content: center; font-size: 18px;
}
.tv-title { display: flex; flex-direction: column; gap: 2px; min-width: 0; }
.tv-name { font-size: 14px; font-weight: 700; color: #E5E9EE; }
.tv-meta {
  font-size: 11px; color: #8B95A5;
  display: inline-flex; align-items: center; gap: 5px;
}
.tv-meta-sep { color: #4B5563; }
.tv-cwd {
  font-family: ui-monospace, SFMono-Regular, monospace;
  font-size: 11px; color: #6BB6FF;
  background: rgba(79, 127, 255, 0.08);
  padding: 1px 6px; border-radius: 4px;
}
.tv-status-dot {
  width: 7px; height: 7px; border-radius: 50%;
  background: #4B5563; flex-shrink: 0;
}
.tv-status-dot.active   { background: #10B981; box-shadow: 0 0 6px rgba(16, 185, 129, 0.6); }
.tv-status-dot.waiting  { background: #4F7FFF; box-shadow: 0 0 6px rgba(79, 127, 255, 0.6); }
.tv-status-dot.idle     { background: #F59E0B; }
.tv-status-dot.offline  { background: #4B5563; }
.tv-status-dot.error    { background: #F87171; }

.tv-head-actions { margin-left: auto; }
.tv-menu-btn {
  background: transparent; border: none; cursor: pointer;
  color: #8B95A5; font-size: 22px; font-weight: 700; line-height: 1;
  padding: 4px 10px; border-radius: 8px;
  transition: background .12s, color .12s;
}
.tv-menu-btn:hover { background: rgba(79, 127, 255, 0.1); color: #E5E9EE; }

.tv-body {
  flex: 1; min-height: 0;
  padding: 24px 28px;
  display: flex; flex-direction: column;
}

.tv-statusbar {
  display: flex; align-items: center; gap: 10px;
  padding: 10px 16px;
  background: rgba(20, 28, 48, 0.6);
  border: 1px solid #1F2738;
  border-bottom: none;
  border-radius: 14px 14px 0 0;
  font-size: 12px; color: #8B95A5;
}
.tv-dots { display: flex; gap: 6px; }
.tv-dots span { width: 11px; height: 11px; border-radius: 50%; }
.tv-dots .d-red { background: #F87171; }
.tv-dots .d-yel { background: #F59E0B; }
.tv-dots .d-grn { background: #10B981; }
.tv-name-small { font-weight: 600; color: #E5E9EE; }
.tv-meta-small { color: #6B7785; font-size: 11px; font-family: ui-monospace, SFMono-Regular, monospace; }
.tv-right { margin-left: auto; }
.tv-conn { font-size: 11px; }
.tv-conn.pending { color: #F59E0B; }
.tv-conn.mock    { color: #F59E0B; }
.tv-conn.live    { color: #10B981; }
.tv-conn.down    { color: #F87171; }

.tv-term {
  flex: 1; min-height: 0;
  background: #0E1424;
  border: 1px solid #1F2738;
  border-top: none;
  border-radius: 0 0 14px 14px;
  padding: 12px 14px;
}
:deep(.xterm) { height: 100%; }
:deep(.xterm-viewport)::-webkit-scrollbar { width: 10px; }
:deep(.xterm-viewport)::-webkit-scrollbar-track { background: transparent; }
:deep(.xterm-viewport)::-webkit-scrollbar-thumb { background: #2A3447; border-radius: 5px; }
:deep(.xterm-viewport)::-webkit-scrollbar-thumb:hover { background: #3A4A66; }

/* 폰트 사이즈 모달 (채팅과 동일) */
.tv-settings-overlay {
  position: fixed; inset: 0;
  background: rgba(7, 11, 22, 0.6); backdrop-filter: blur(6px);
  display: flex; align-items: center; justify-content: center;
  z-index: 1000;
  animation: settingsFadeIn .15s ease-out;
}
@keyframes settingsFadeIn { from { opacity: 0; } to { opacity: 1; } }
.tv-settings-modal {
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
.tv-settings-head {
  display: flex; align-items: center; justify-content: space-between;
  padding: 14px 18px;
  border-bottom: 1px solid #1E2738;
}
.tv-settings-head h3 {
  margin: 0; font-size: 14px; font-weight: 700;
  background: linear-gradient(90deg, #6BB6FF, #B89AFF);
  -webkit-background-clip: text; background-clip: text;
  -webkit-text-fill-color: transparent;
}
.tv-settings-x {
  background: transparent; border: none; cursor: pointer;
  color: #8B95A5; font-size: 14px; padding: 4px 8px; border-radius: 6px;
}
.tv-settings-x:hover { background: rgba(248, 113, 113, 0.15); color: #FCA5A5; }
.tv-settings-body { padding: 18px; }
.tv-settings-label {
  font-size: 11px; color: #8B95A5;
  text-transform: uppercase; letter-spacing: 0.06em; font-weight: 600;
}
.tv-settings-control { display: flex; align-items: center; gap: 8px; margin-top: 10px; }
.tv-stepper {
  width: 32px; height: 32px;
  background: #1A2030; color: #B89AFF;
  border: 1px solid #2A3447; border-radius: 8px;
  font-size: 16px; font-weight: 700; cursor: pointer;
  transition: background .12s, color .12s, border-color .12s;
}
.tv-stepper:hover:not(:disabled) { background: #232C42; border-color: #4F7FFF; color: #fff; }
.tv-stepper:disabled { opacity: 0.4; cursor: not-allowed; }
.tv-settings-num {
  width: 70px; padding: 6px 10px;
  background: #0F1729; border: 1px solid #2A3447; border-radius: 8px;
  color: #E5E9EE; font-size: 14px; font-family: ui-monospace, SFMono-Regular, monospace;
  text-align: center;
}
.tv-settings-num:focus { outline: none; border-color: #4F7FFF; box-shadow: 0 0 0 3px rgba(79, 127, 255, 0.15); }
.tv-settings-range {
  font-size: 11px; color: #6B7785;
  margin-left: 6px; font-family: ui-monospace, SFMono-Regular, monospace;
}
.tv-settings-actions {
  display: flex; justify-content: flex-end; gap: 8px;
  margin-top: 18px;
}
.tv-settings-reset {
  padding: 8px 14px; font-size: 12px;
  background: transparent; color: #8B95A5;
  border: 1px solid #2A3447; border-radius: 8px; cursor: pointer;
}
.tv-settings-reset:hover { background: #1A2030; color: #E5E9EE; }
.tv-settings-done {
  padding: 8px 18px; font-size: 12px; font-weight: 600;
  background: linear-gradient(135deg, #4F7FFF, #7C5CFF);
  color: #fff; border: none; border-radius: 8px; cursor: pointer;
  transition: transform .1s, box-shadow .15s;
}
.tv-settings-done:hover {
  box-shadow: 0 4px 14px rgba(79, 127, 255, 0.4);
  transform: translateY(-1px);
}

/* 모바일 */
@media (max-width: 768px) { .tv-back { display: block; } }
</style>
