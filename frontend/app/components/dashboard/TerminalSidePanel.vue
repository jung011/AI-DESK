<template>
  <Teleport to="body">
    <div class="side-panel-root" :class="{ open }">
      <div class="side-panel-backdrop" @click="emit('close')" />
      <aside class="side-panel" role="dialog" aria-label="에이전트 터미널">
        <header class="side-panel-head">
          <div class="title-wrap">
            <h3 class="title">{{ agentName || '(에이전트 미지정)' }}</h3>
            <p v-if="subtitle" class="subtitle">{{ subtitle }}</p>
            <p class="session-tag">tmux: {{ tmuxSession || '—' }}</p>
          </div>
          <div class="head-actions">
            <button
              class="gear-btn"
              type="button"
              aria-label="터미널 설정"
              title="터미널 설정"
              :class="{ active: settingsOpen }"
              @click="settingsOpen = true">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">
                <circle cx="12" cy="12" r="3" />
                <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1 0 2.83 2 2 0 0 1-2.83 0l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83 0 2 2 0 0 1 0-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 0-2.83 2 2 0 0 1 2.83 0l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 0 2 2 0 0 1 0 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z" />
              </svg>
            </button>
            <button class="close-btn" type="button" aria-label="닫기" @click="emit('close')">×</button>
          </div>
        </header>

        <!-- 터미널 / VSCode 탭 스위치 -->
        <nav class="side-panel-tabs" role="tablist">
          <button
            type="button" role="tab"
            class="tab-btn"
            :class="{ active: activeTab === 'terminal' }"
            :aria-selected="activeTab === 'terminal'"
            @click="activeTab = 'terminal'">
            <svg class="tab-ico" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="4 17 10 11 4 5" /><line x1="12" y1="19" x2="20" y2="19" /></svg>
            터미널
          </button>
          <button
            type="button" role="tab"
            class="tab-btn"
            :class="{ active: activeTab === 'vscode' }"
            :aria-selected="activeTab === 'vscode'"
            @click="activeTab = 'vscode'">
            <svg class="tab-ico" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="16 18 22 12 16 6" /><polyline points="8 6 2 12 8 18" /></svg>
            VSCode
          </button>
        </nav>

        <div class="side-panel-body">
          <!-- 두 패널 모두 마운트 유지하고 v-show 로 토글 — 탭 전환시 WS/iframe 재연결 회피 -->
          <div v-show="activeTab === 'terminal'" class="pane-slot">
            <TerminalPane
              v-if="open && tmuxSession"
              :key="tmuxSession"
              :session="tmuxSession"
              :font-size="prefs.fontSize"
              :font-family="prefs.fontFamily"
              :theme="themeFor(prefs.themeName)" />
            <div v-else-if="open" class="empty">
              이 에이전트에는 연결할 tmux 세션이 없습니다.
            </div>
          </div>
          <div v-show="activeTab === 'vscode'" class="pane-slot">
            <VsCodePane
              v-if="open"
              :url="codeServer.url"
              :alive="codeServer.alive"
              :workspace="workspaceDir" />
          </div>
        </div>
      </aside>

      <!-- 설정 모달 (사이드 패널 위에 떠 있는 중앙 다이얼로그) -->
      <div v-if="settingsOpen" class="settings-modal-overlay" @click.self="settingsOpen = false">
        <div class="settings-modal" role="dialog" aria-label="터미널 설정">
          <header class="settings-modal-head">
            <h3>터미널 설정</h3>
            <button class="settings-modal-close" type="button" aria-label="닫기" @click="settingsOpen = false">×</button>
          </header>
          <div class="settings-modal-body">
            <label class="settings-row">
              <span class="lbl">폰트 크기</span>
              <input type="range" min="10" max="20" step="1" v-model.number="prefs.fontSize" />
              <span class="val">{{ prefs.fontSize }}px</span>
            </label>
            <label class="settings-row">
              <span class="lbl">폰트</span>
              <select v-model="prefs.fontFamily">
                <option v-for="f in fontFamilies" :key="f.value" :value="f.value">{{ f.label }}</option>
              </select>
            </label>
            <label class="settings-row">
              <span class="lbl">테마</span>
              <select v-model="prefs.themeName">
                <option v-for="t in themes" :key="t.name" :value="t.name">{{ t.label }}</option>
              </select>
            </label>
          </div>
          <footer class="settings-modal-foot">
            <button class="btn-done" type="button" @click="settingsOpen = false">완료</button>
          </footer>
        </div>
      </div>
    </div>
  </Teleport>
</template>

<script setup lang="ts">
import { ref, watch } from 'vue';
import TerminalPane from '~/components/terminal/TerminalPane.vue';
import VsCodePane from '~/components/terminal/VsCodePane.vue';
import { useTerminalPrefs } from '~/composables/useTerminalPrefs';
import type { ApiEnvelope } from '~/vo/agents/AgentVo';

const props = defineProps<{
  open: boolean;
  /** 헤더에 표시할 에이전트 이름. */
  agentName?: string;
  /** 헤더 보조 라벨 (예: 모델, 워크스페이스). */
  subtitle?: string;
  /** 연결할 tmux 세션명. 없으면 빈 상태. */
  tmuxSession?: string;
  /** VSCode iframe `?folder=` 에 들어갈 절대 경로. */
  workspaceDir?: string;
}>();
const emit = defineEmits<{ (e: 'close'): void }>();

const { prefs, themes, fontFamilies, themeFor } = useTerminalPrefs();
const settingsOpen = ref(false);

const activeTab = ref<'terminal' | 'vscode'>('terminal');

interface CodeServerRs { url: string; alive: boolean }
const codeServer = ref<CodeServerRs>({ url: '', alive: false });

async function fetchCodeServer(): Promise<void> {
  try {
    const { $api } = useNuxtApp();
    const env = await $api<ApiEnvelope<CodeServerRs>>('/api/settings/code-server');
    if (env.result === 0 && env.data) codeServer.value = env.data;
  } catch { /* 무시 — VsCodePane 이 빈 상태로 빠진 안내 표시 */ }
}

// 패널 열릴 때 헬스 상태 갱신 (오래 열어둔 사이 code-server 가 죽었을 수도 있어서)
watch(() => props.open, (v) => { if (v) void fetchCodeServer(); }, { immediate: true });
</script>

<style scoped>
.side-panel-root {
  position: fixed; inset: 0;
  pointer-events: none;     /* 닫혔을 때 클릭 통과 */
  z-index: 1200;
}
.side-panel-root.open { pointer-events: auto; }

.side-panel-backdrop {
  position: absolute; inset: 0;
  background: rgba(15, 23, 42, 0.35);
  opacity: 0;
  transition: opacity .18s ease;
}
.side-panel-root.open .side-panel-backdrop { opacity: 1; }

.side-panel {
  position: absolute; top: 0; right: 0; bottom: 0;
  width: 720px; max-width: 90vw;
  background: #fff;
  box-shadow: -12px 0 30px rgba(15, 23, 42, .18);
  transform: translateX(100%);
  transition: transform .22s ease;
  display: flex; flex-direction: column;
}
.side-panel-root.open .side-panel { transform: translateX(0); }

.side-panel-head {
  display: flex; align-items: flex-start; gap: 12px;
  padding: 16px 20px;
  border-bottom: 1px solid #F0F2F5;
}
.title-wrap { flex: 1; min-width: 0; }
.title {
  margin: 0 0 4px;
  font-size: 16px; font-weight: 700; color: #101010;
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}
.subtitle {
  margin: 0;
  font-size: 12px; color: #475569;
}
.session-tag {
  margin: 4px 0 0;
  font-family: ui-monospace, SFMono-Regular, monospace;
  font-size: 11px; color: #94A3B8;
}
.head-actions { display: inline-flex; align-items: center; gap: 6px; flex-shrink: 0; }
.gear-btn {
  display: inline-flex; align-items: center; justify-content: center;
  width: 34px; height: 34px;
  background: none;
  border: none;
  color: #64748B; cursor: pointer;
  transition: color .15s, transform .15s;
}
.gear-btn:hover { color: #4338CA; transform: rotate(30deg); }
.gear-btn:active { transform: rotate(30deg) scale(.96); }
.gear-btn.active { color: #4338CA; }
.gear-btn svg { width: 20px; height: 20px; }

.close-btn {
  width: 34px; height: 34px;
  background: none; border: none; font-size: 24px;
  color: #94A3B8; cursor: pointer; line-height: 1;
  border-radius: 8px;
  flex-shrink: 0;
}
.close-btn:hover { color: #475569; background: #F1F5F9; }

/* === 설정 모달 === */
.settings-modal-overlay {
  position: absolute; inset: 0;
  background: rgba(15, 23, 42, 0.45);
  display: flex; align-items: center; justify-content: center;
  z-index: 1;
  animation: fadeIn .15s ease;
}
@keyframes fadeIn { from { opacity: 0; } to { opacity: 1; } }
.settings-modal {
  width: 400px; max-width: calc(100% - 40px);
  background: #fff; border-radius: 12px;
  box-shadow: 0 20px 50px rgba(15, 23, 42, .25);
  display: flex; flex-direction: column;
  animation: slideIn .18s ease;
}
@keyframes slideIn {
  from { opacity: 0; transform: translateY(-6px) scale(.98); }
  to   { opacity: 1; transform: translateY(0) scale(1); }
}
.settings-modal-head {
  display: flex; align-items: center; justify-content: space-between;
  padding: 14px 18px;
  border-bottom: 1px solid #F0F2F5;
}
.settings-modal-head h3 { margin: 0; font-size: 14px; font-weight: 700; color: #101010; }
.settings-modal-close {
  width: 28px; height: 28px;
  background: none; border: none; font-size: 20px;
  color: #94A3B8; cursor: pointer; line-height: 1;
  border-radius: 6px;
}
.settings-modal-close:hover { color: #475569; background: #F1F5F9; }

.settings-modal-body {
  display: flex; flex-direction: column; gap: 14px;
  padding: 18px;
}
.settings-row {
  display: flex; align-items: center; gap: 12px;
  font-size: 13px; color: #475569;
}
.settings-row .lbl { width: 72px; font-weight: 600; flex-shrink: 0; color: #475569; }
.settings-row input[type="range"] {
  flex: 1; min-width: 0;
  accent-color: #0062ff;
}
.settings-row select {
  flex: 1; min-width: 0;
  height: 32px; padding: 0 10px;
  border: 1px solid #CBD5E1; border-radius: 6px;
  background: #fff; font-size: 13px; color: #1E293B;
  cursor: pointer;
}
.settings-row select:focus { outline: 2px solid #0062ff; outline-offset: -1px; border-color: #0062ff; }
.settings-row .val {
  width: 42px; text-align: right;
  font-family: ui-monospace, SFMono-Regular, monospace;
  font-size: 12px; color: #94A3B8;
}

.settings-modal-foot {
  display: flex; justify-content: flex-end;
  padding: 12px 18px;
  border-top: 1px solid #F0F2F5;
}
.btn-done {
  height: 32px; padding: 0 18px;
  background: #0062ff; color: #fff;
  border: none; border-radius: 6px;
  font-size: 13px; font-weight: 600;
  cursor: pointer;
  transition: background .15s;
}
.btn-done:hover { background: #0052d9; }

.side-panel-tabs {
  display: flex; gap: 4px;
  padding: 8px 16px 0;
  border-bottom: 1px solid #F0F2F5;
  background: #fff;
}
.tab-btn {
  display: inline-flex; align-items: center; gap: 6px;
  padding: 8px 14px;
  background: none; border: none;
  border-bottom: 2px solid transparent;
  color: #64748B;
  font-size: 13px; font-weight: 600;
  cursor: pointer;
  transition: color .15s, border-color .15s;
}
.tab-btn:hover { color: #4338CA; }
.tab-btn.active {
  color: #0062ff;
  border-bottom-color: #0062ff;
}
.tab-ico { width: 14px; height: 14px; }

.side-panel-body {
  flex: 1; min-height: 0;
  padding: 12px;
  display: flex; flex-direction: column;
}
.pane-slot {
  flex: 1; min-height: 0;
  display: flex;
}
.pane-slot > * { flex: 1; min-height: 0; }
.empty {
  height: 100%;
  display: flex; align-items: center; justify-content: center;
  color: #94A3B8; font-size: 13px;
}
</style>
