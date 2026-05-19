<template>
  <div class="terminal-pane">
    <div class="terminal-host" ref="hostRef" />
    <div
      v-if="status !== 'open'"
      class="terminal-status"
      :class="status"
      @click="reconnect">
      <span v-if="status === 'connecting' && reconnectAttempts === 0">연결 중…</span>
      <span v-else-if="status === 'connecting'">재연결 중… ({{ reconnectAttempts }}/{{ MAX_RECONNECT_ATTEMPTS }})</span>
      <span v-else-if="status === 'closed'">연결 종료 — 클릭하여 재연결</span>
      <span v-else-if="status === 'error'">재연결 실패 — 클릭하여 재시도</span>
    </div>
  </div>
</template>

<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref, watch } from 'vue';
import { Terminal, type ITheme } from '@xterm/xterm';
import { FitAddon } from '@xterm/addon-fit';
import '@xterm/xterm/css/xterm.css';

/** AI Desk 디자인 토큰 기반 기본 다크 테마. defineProps 의 default 가 module scope 변수만
 *  참조 가능해서 컴포넌트 setup 위로 끌어올렸다. */
const DEFAULT_THEME: ITheme = {
  background: '#1E293B',
  foreground: '#E2E8F0',
  cursor: '#0062ff',
  cursorAccent: '#1E293B',
  selectionBackground: 'rgba(0, 98, 255, 0.30)',
  black: '#1E293B',
  red: '#FF6B6B',
  green: '#51CF66',
  yellow: '#FFD43B',
  blue: '#74C0FC',
  magenta: '#E599F7',
  cyan: '#3BC9DB',
  white: '#F1F3F5',
  brightBlack: '#475569',
  brightRed: '#FF8787',
  brightGreen: '#69DB7C',
  brightYellow: '#FFE066',
  brightBlue: '#91A7FF',
  brightMagenta: '#F783AC',
  brightCyan: '#66D9E8',
  brightWhite: '#FFFFFF',
};

interface Props {
  /** tmux 세션명 (예: aidesk-self-liki, aidesk-b1f44444). */
  session: string;
  /** 신규 세션일 때 cd 할 디렉토리. tmux 가 이미 있으면 무시. */
  workspaceDir?: string;
  /** claude / codex / hermes — 신규 세션일 때 자동 기동할 CLI. 기본 claude. */
  model?: string;
  /** 1pt = 1px. 기본 14. 부모에서 사용자 설정값을 내려준다. */
  fontSize?: number;
  fontFamily?: string;
  /** xterm.js ITheme. 미지정시 AI Desk 기본 다크 테마. */
  theme?: ITheme;
}

const props = withDefaults(defineProps<Props>(), {
  workspaceDir: undefined,
  model: undefined,
  fontSize: 14,
  fontFamily: 'JetBrains Mono, Menlo, Monaco, "D2Coding", monospace',
  // theme 의 default 는 defineProps 매크로 한계로 여기서 못 잡고, 사용 지점에서 ?? DEFAULT_THEME 로 폴백한다.
  theme: undefined,
});

const emit = defineEmits<{
  (e: 'connected'): void;
  (e: 'disconnected', reason: string): void;
}>();

const hostRef = ref<HTMLElement | null>(null);
const status = ref<'connecting' | 'open' | 'closed' | 'error'>('connecting');
const reconnectAttempts = ref(0);

/** 자동 재연결 — 지수 백오프(1s, 2s, 4s, …, max 30s) 로 최대 N번 재시도. */
const MAX_RECONNECT_ATTEMPTS = 8;
const MAX_BACKOFF_MS = 30_000;
/** 연결이 *진짜 안정* 됐다고 판단하는 시간. open 후 이 시간 안 끊겨야 attempts 리셋. */
const STABLE_CONNECTION_MS = 5_000;

let term: Terminal | null = null;
let fit: FitAddon | null = null;
let ws: WebSocket | null = null;
let resizeObserver: ResizeObserver | null = null;
let reconnectTimer: ReturnType<typeof setTimeout> | null = null;
let stabilityTimer: ReturnType<typeof setTimeout> | null = null;
/** 의도된 종료 플래그 — onBeforeUnmount / 세션 교체 시 set 해서 auto-reconnect 차단. */
let intentionalClose = false;

function buildWsUrl(session: string): string {
  // 임베드 터미널은 로컬 Helper(데스크톱 앱) 의 PTY 를 사용한다 — 백엔드가 Docker 화되어도
  // tmux/PTY 는 사용자 Mac 의 Helper 가 그대로 띄움.
  const conf = useRuntimeConfig().public as { helperBase?: string };
  const base = conf.helperBase || `${location.protocol}//${location.hostname}:30083`;
  const wsBase = base.replace(/^http/, 'ws');
  const params = new URLSearchParams({ session });
  if (props.workspaceDir) params.set('workspaceDir', props.workspaceDir);
  if (props.model) params.set('model', props.model);
  return `${wsBase}/api/terminal?${params.toString()}`;
}

function connect(): void {
  if (!term || !fit) return;
  status.value = 'connecting';
  ws = new WebSocket(buildWsUrl(props.session));

  ws.onopen = () => {
    status.value = 'open';
    // 카운터 즉시 리셋하면 open → 즉시 close 패턴이 backoff 폭주 (매번 1s) 를 일으킴.
    // 대신 STABLE_CONNECTION_MS 동안 안 끊겨야 *진짜 안정* 으로 보고 리셋.
    if (stabilityTimer) clearTimeout(stabilityTimer);
    stabilityTimer = setTimeout(() => {
      reconnectAttempts.value = 0;
      stabilityTimer = null;
    }, STABLE_CONNECTION_MS);
    // open 직후 한 번 fit + resize 통보 — xterm 초기 size 와 PTY size 동기화
    syncSize();
    emit('connected');
  };
  ws.onmessage = (ev) => {
    if (typeof ev.data === 'string') term?.write(ev.data);
  };
  ws.onclose = (ev) => {
    emit('disconnected', ev.reason || `code=${ev.code}`);
    // stability timer 가 살아있으면 = open 후 5초 안 끊긴 거 → 카운터 리셋 취소
    if (stabilityTimer) {
      clearTimeout(stabilityTimer);
      stabilityTimer = null;
    }
    // 의도된 종료(언마운트/세션교체)면 그대로 멈춤. 그 외엔 자동 재연결 스케줄.
    if (intentionalClose) {
      status.value = 'closed';
      return;
    }
    scheduleReconnect();
  };
  ws.onerror = () => {
    // 에러 후엔 onclose 가 따라 호출되므로 거기서 reconnect 처리. 여기선 표시만.
  };
}

function scheduleReconnect(): void {
  if (intentionalClose) return;
  if (reconnectAttempts.value >= MAX_RECONNECT_ATTEMPTS) {
    status.value = 'error';
    return;
  }
  // 지수 백오프: 1s, 2s, 4s, 8s, 16s, 30s, 30s, 30s
  const delay = Math.min(1000 * 2 ** reconnectAttempts.value, MAX_BACKOFF_MS);
  reconnectAttempts.value++;
  status.value = 'connecting';
  reconnectTimer = setTimeout(() => {
    reconnectTimer = null;
    connect();
  }, delay);
}

function syncSize(): void {
  if (!term || !fit || !ws || ws.readyState !== WebSocket.OPEN) return;
  fit.fit();
  const { cols, rows } = term;
  // fit-addon 이 DOM layout 전에 측정되면 cols ~6 같은 비정상 값이 나옴.
  // 이걸 PTY 에 보내면 tmux 가 그 좁은 cols 로 wrap 해 scrollback 에 영구 박힘.
  // 임계값 미만이면 다음 frame 에 다시 시도.
  if (cols < 40 || rows < 5) {
    requestAnimationFrame(() => syncSize());
    return;
  }
  ws.send(JSON.stringify({ type: 'resize', cols, rows }));
}

onMounted(() => {
  if (!hostRef.value) return;

  term = new Terminal({
    fontFamily: props.fontFamily,
    fontSize: props.fontSize,
    lineHeight: 1.2,
    cursorBlink: true,
    cursorStyle: 'bar',
    scrollback: 5000,
    theme: props.theme ?? DEFAULT_THEME,
    allowProposedApi: true,
  });
  fit = new FitAddon();
  term.loadAddon(fit);
  term.open(hostRef.value);
  fit.fit();

  term.onData((data) => {
    if (ws && ws.readyState === WebSocket.OPEN) ws.send(data);
  });

  // copy-on-select: 드래그 선택 즉시 클립보드 복사. xterm 의 selection 은 PTY redraw 나
  // size 재조정 시 풀려서 사용자가 Cmd+C 눌 틈을 놓치는 경우가 많음 (특히 claude TUI 의
  // spinner 가 도는 동안). 선택 변경 이벤트 시점에 자동 복사해 둬서 풀려도 클립보드는 살아있게.
  term.onSelectionChange(() => {
    const sel = term?.getSelection();
    if (sel && sel.length > 0 && navigator.clipboard) {
      // 권한 거부나 비-secure context 면 조용히 fallback — 사용자가 Cmd+C 로 재시도 가능.
      void navigator.clipboard.writeText(sel).catch(() => {});
    }
  });

  resizeObserver = new ResizeObserver(() => syncSize());
  resizeObserver.observe(hostRef.value);

  connect();
});

onBeforeUnmount(() => {
  intentionalClose = true;
  if (reconnectTimer) {
    clearTimeout(reconnectTimer);
    reconnectTimer = null;
  }
  if (stabilityTimer) {
    clearTimeout(stabilityTimer);
    stabilityTimer = null;
  }
  resizeObserver?.disconnect();
  ws?.close();
  term?.dispose();
});

// 폰트/테마 props 가 바뀌면 런타임 즉시 반영
watch(() => props.fontSize, (v) => {
  if (term) {
    term.options.fontSize = v;
    syncSize();
  }
});
watch(() => props.fontFamily, (v) => {
  if (term) {
    term.options.fontFamily = v;
    syncSize();
  }
});
watch(() => props.theme, (v) => {
  if (term) term.options.theme = v ?? DEFAULT_THEME;
}, { deep: true });

// 부모가 세션을 갈아끼우면 재연결
watch(() => props.session, () => {
  intentionalClose = true;          // 기존 ws 의 onclose 가 auto-reconnect 안 일으키게
  if (reconnectTimer) {
    clearTimeout(reconnectTimer);
    reconnectTimer = null;
  }
  ws?.close();
  term?.clear();
  intentionalClose = false;
  reconnectAttempts.value = 0;
  connect();
});

/** 사용자가 오버레이를 클릭했을 때 — backoff 대기를 건너뛰고 즉시 재시도. */
function reconnect(): void {
  // 백오프 대기 중이면 타이머 취소하고 즉시 시도
  if (reconnectTimer) {
    clearTimeout(reconnectTimer);
    reconnectTimer = null;
  }
  // max 도달했더라도 사용자 명시 의지면 다시 시작
  if (status.value === 'closed' || status.value === 'error') {
    reconnectAttempts.value = 0;
    connect();
  }
}
defineExpose({ reconnect });
</script>

<style scoped>
.terminal-pane {
  position: relative;
  width: 100%;
  height: 100%;
  background: #1E293B;
  border-radius: 6px;
  overflow: hidden;
}
.terminal-host {
  width: 100%;
  height: 100%;
  padding: 8px;
  box-sizing: border-box;
}
.terminal-status {
  position: absolute; inset: 0;
  display: flex; align-items: center; justify-content: center;
  background: rgba(15, 23, 42, 0.78);
  color: #E2E8F0;
  font-size: 13px;
  pointer-events: none;
}
.terminal-status.closed,
.terminal-status.error {
  cursor: pointer;
  pointer-events: auto;
}
</style>
