<template>
  <div class="terminal-pane">
    <div class="terminal-host" ref="hostRef" />
    <div v-if="status !== 'open'" class="terminal-status" :class="status">
      <span v-if="status === 'connecting'">연결 중…</span>
      <span v-else-if="status === 'closed'">연결 종료 — 클릭하여 재연결</span>
      <span v-else-if="status === 'error'">연결 오류</span>
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

let term: Terminal | null = null;
let fit: FitAddon | null = null;
let ws: WebSocket | null = null;
let resizeObserver: ResizeObserver | null = null;

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
    // open 직후 한 번 fit + resize 통보 — xterm 초기 size 와 PTY size 동기화
    syncSize();
    emit('connected');
  };
  ws.onmessage = (ev) => {
    if (typeof ev.data === 'string') term?.write(ev.data);
  };
  ws.onclose = (ev) => {
    status.value = 'closed';
    emit('disconnected', ev.reason || `code=${ev.code}`);
  };
  ws.onerror = () => {
    status.value = 'error';
  };
}

function syncSize(): void {
  if (!term || !fit || !ws || ws.readyState !== WebSocket.OPEN) return;
  fit.fit();
  const { cols, rows } = term;
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

  resizeObserver = new ResizeObserver(() => syncSize());
  resizeObserver.observe(hostRef.value);

  connect();
});

onBeforeUnmount(() => {
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
  ws?.close();
  term?.clear();
  connect();
});

function reconnect(): void {
  if (status.value === 'closed' || status.value === 'error') connect();
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
