<template>
  <div class="act-wrap" ref="hostRef">
    <span class="act-overlay">LIVE</span>
  </div>
</template>

<script setup lang="ts">
/**
 * AgentCard mini terminal preview — read-only xterm.js + helper /ws/terminal attach.
 *
 * 동작:
 *   - mount 시 helper /ws/terminal?agentId=...&tmux=...&cols=56&rows=9 connect
 *   - xterm disableStdin=true — 키보드 input 차단 (read-only)
 *   - ws message (binary 또는 text) → term.write()
 *   - unmount 시 ws close + term dispose
 *
 * 부담:
 *   - 카드 N개 = N ws connect to helper.
 *   - 카드가 viewport 밖이어도 ws active — IntersectionObserver lazy 는 후속.
 */
import { onBeforeUnmount, onMounted, ref } from 'vue';

const props = defineProps<{
  agentId: string;
  tmuxSession: string;
  workspaceDir?: string;
  agentName?: string;
}>();

const hostRef = ref<HTMLElement | null>(null);
let term: any = null;
let ws: WebSocket | null = null;
let reconnectTimer: ReturnType<typeof setTimeout> | null = null;
let disposed = false;

// dev = 30084 / prod = 30083 (WebTerminal.vue 와 동일 패턴)
// mini preview — fontSize 작게 + cols/rows 크게 (사용자 가시 정보량 ↑). tmux
// attach 시 *작은 client 의 grid 가 master* 라 *큰 화면 client* 의 wrap 영향.
// helper web_pty 의 tmux session 에 aggressive-resize=on 자동 박혀있어야 *각
// client 별 grid 분리* — wrap 영향 작아짐.
const MINI_COLS = 100;
const MINI_ROWS = 14;

// 옵션 B MVP — 모바일 prod 박혀있으면 /api/helper/lan-ip 박은 IP 사용. async 분기 박힘.
async function helperWsUrlAsync(): Promise<string> {
  const params = new URLSearchParams({
    agentId: props.agentId,
    tmuxSession: props.tmuxSession,
    background: '1',
  });
  if (props.workspaceDir) params.set('cwd', props.workspaceDir);
  if (props.agentName) params.set('agentName', props.agentName);
  let wsBase: string;
  if (import.meta.dev) {
    wsBase = `ws://${window.location.hostname}:30084`;
  } else {
    const { getMobileHelperBase } = await import('~/utils/mobileHelperBase');
    const lanIp = await getMobileHelperBase();
    wsBase = lanIp ? `ws://${lanIp}:30084` : 'ws://127.0.0.1:30083';
  }
  return `${wsBase}/ws/terminal?${params.toString()}`;
}

async function ensureXterm(): Promise<void> {
  if (import.meta.server) return;
  if (term) return;
  const [{ Terminal }] = await Promise.all([
    import('@xterm/xterm'),
  ]);
  await import('@xterm/xterm/css/xterm.css' as string).catch(() => null);
  term = new Terminal({
    cursorBlink: false,
    cursorStyle: 'bar',
    fontFamily: "ui-monospace, SFMono-Regular, Menlo, monospace",
    fontSize: 7,
    lineHeight: 1.1,
    cols: MINI_COLS,
    rows: MINI_ROWS,
    scrollback: 200,
    disableStdin: true,  // read-only — 키보드 차단
    allowProposedApi: true,
    theme: {
      background: '#000000',
      foreground: '#E5E9EE',
      cursor: '#000000',
      cursorAccent: '#000000',
      selectionBackground: 'rgba(79, 127, 255, 0.3)',
      black: '#0E1424', red: '#F87171', green: '#10B981', yellow: '#F59E0B',
      blue: '#4F7FFF', magenta: '#B89AFF', cyan: '#6BB6FF', white: '#C5CDD8',
      brightBlack: '#4B5563', brightRed: '#FCA5A5', brightGreen: '#34D399',
      brightYellow: '#FBBF24', brightBlue: '#6BB6FF', brightMagenta: '#D8B4FE',
      brightCyan: '#7DD3FC', brightWhite: '#FFFFFF',
    },
  });
  // FitAddon 안 씀 — act-wrap 의 작은 height 가 rows 줄여 *status bar 보이는* 사고.
  // fixed grid (MINI_COLS × MINI_ROWS) 그대로 + overflow:hidden 로 bottom 잘라냄.
  if (hostRef.value) {
    term.open(hostRef.value);
  }
  // wheel 차단 — 카드 안 mini terminal 의 scroll 은 page scroll 위임
  if (typeof term.attachCustomWheelEventHandler === 'function') {
    term.attachCustomWheelEventHandler(() => false);
  }
}

function connectWs() {
  if (disposed) return;
  // 옵션 B MVP — 모바일 prod 분기 박혀있어 helper LAN IP async resolve. fire-and-forget
  // 안에서 ws 연결.
  void helperWsUrlAsync().then((url) => {
    if (!url || disposed) return;
    _doConnect(url);
  });
}

function _doConnect(url: string) {
  // reconnect 시 옛 화면 비움 — helper 가 ws connect 마다 tmux capture-pane
  // -S -3000 dump 하여 *옛 출력 같이 남아* xterm 안 cumulative append 사고. 옛
  // shuttle agent 의 zsh plain text 의 *prompt line 누적* 사고 — alt-screen 을
  // 쓰는 claude TUI 와 차이. WebTerminal 과 같은 패턴 (옛 dot 누적 사고 f02732f).
  if (term) {
    try { term.reset(); } catch { /* ignore */ }
  }
  ws = new WebSocket(url);
  ws.binaryType = 'arraybuffer';
  ws.onmessage = (ev) => {
    if (!term) return;
    if (ev.data instanceof ArrayBuffer) {
      const bytes = new Uint8Array(ev.data);
      term.write(bytes);
    } else if (typeof ev.data === 'string') {
      // 옵션 F = helper 의 background polling path 의 첫 message = JSON
      // {type:'info', cols, rows} — 원본 tmux grid 의 cols. xterm 의 cols 를 그
      // 값으로 재박음 + fontSize 자동 축소 (카드 width 안 fit). wrap 사고 차단.
      try {
        const msg = JSON.parse(ev.data);
        if (msg && msg.type === 'info' && typeof msg.cols === 'number') {
          const newCols = Math.max(20, Math.min(500, msg.cols));
          term.resize(newCols, MINI_ROWS);
          // fontSize 자동 축소 — 카드 width 측정 후 cols 에 fit. cell ratio ≈ 0.6.
          if (hostRef.value) {
            const w = hostRef.value.clientWidth - 8;
            const fit = Math.max(2, Math.floor(w / (newCols * 0.6)));
            try { term.options.fontSize = fit; } catch { /* ignore */ }
          }
          return;
        }
      } catch { /* JSON 아니면 그냥 write */ }
      term.write(ev.data);
    }
  };
  ws.onclose = () => {
    if (disposed) return;
    // 5s 후 재연결 (helper restart / network blip 대비)
    reconnectTimer = setTimeout(() => { if (!disposed) connectWs(); }, 5000);
  };
  ws.onerror = () => { /* close 이어짐 */ };
}

onMounted(async () => {
  await ensureXterm();
  connectWs();
});

onBeforeUnmount(() => {
  disposed = true;
  if (reconnectTimer) { clearTimeout(reconnectTimer); reconnectTimer = null; }
  if (ws) { try { ws.close(); } catch { /* ignore */ } ws = null; }
  if (term) { try { term.dispose(); } catch { /* ignore */ } term = null; }
});
</script>

<style scoped>
.act-wrap {
  position: relative;
  background: #000;
  border-radius: 6px;
  padding: 4px;
  /* xterm grid = 14 rows × ~7.7px = ~108px. tmux status bar = *xterm grid 의
     마지막 1 row* (`[aidesk-... 23:56 26-`). height 를 *13 rows + padding*
     으로 잘라 status bar 만 안 보이게. `← for agents` 같은 model row 까지 표시. */
  height: 116px;
  overflow: hidden;
  pointer-events: none;  /* 클릭은 카드 전체로 위임 */
}
.act-overlay {
  position: absolute;
  top: 4px; right: 6px;
  font-size: 9px; color: #FFB300;
  background: rgba(0, 0, 0, 0.6);
  padding: 1px 5px; border-radius: 2px;
  letter-spacing: 0.04em;
  z-index: 10;
  font-weight: 600;
}
.act-wrap :deep(.xterm) { padding: 2px; }
.act-wrap :deep(.xterm-viewport)::-webkit-scrollbar { width: 3px; }
.act-wrap :deep(.xterm-viewport)::-webkit-scrollbar-thumb { background: #334155; }

</style>
