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
              :class="{ active: settingsOpen }"
              @click="settingsOpen = !settingsOpen">
              ⚙
            </button>
            <button class="close-btn" type="button" aria-label="닫기" @click="emit('close')">×</button>
          </div>
        </header>

        <div v-if="settingsOpen" class="settings-bar">
          <label class="settings-row">
            <span class="lbl">폰트 크기</span>
            <input
              type="range" min="10" max="20" step="1"
              v-model.number="prefs.fontSize" />
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

        <div class="side-panel-body">
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
      </aside>
    </div>
  </Teleport>
</template>

<script setup lang="ts">
import { ref } from 'vue';
import TerminalPane from '~/components/terminal/TerminalPane.vue';
import { useTerminalPrefs } from '~/composables/useTerminalPrefs';

defineProps<{
  open: boolean;
  /** 헤더에 표시할 에이전트 이름. */
  agentName?: string;
  /** 헤더 보조 라벨 (예: 모델, 워크스페이스). */
  subtitle?: string;
  /** 연결할 tmux 세션명. 없으면 빈 상태. */
  tmuxSession?: string;
}>();
const emit = defineEmits<{ (e: 'close'): void }>();

const { prefs, themes, fontFamilies, themeFor } = useTerminalPrefs();
const settingsOpen = ref(false);
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
.head-actions { display: inline-flex; align-items: center; gap: 4px; flex-shrink: 0; }
.gear-btn {
  width: 32px; height: 32px;
  background: none; border: none;
  font-size: 16px; color: #94A3B8;
  cursor: pointer; line-height: 1;
  border-radius: 6px;
}
.gear-btn:hover { background: #F1F5F9; color: #475569; }
.gear-btn.active { background: #EEF2FF; color: #4338CA; }

.close-btn {
  width: 32px; height: 32px;
  background: none; border: none; font-size: 24px;
  color: #94A3B8; cursor: pointer; line-height: 1;
  flex-shrink: 0;
}
.close-btn:hover { color: #475569; }

.settings-bar {
  display: flex; flex-direction: column; gap: 8px;
  padding: 12px 20px;
  background: #F8FAFC;
  border-bottom: 1px solid #F0F2F5;
}
.settings-row {
  display: flex; align-items: center; gap: 10px;
  font-size: 12px; color: #475569;
}
.settings-row .lbl { width: 64px; font-weight: 600; flex-shrink: 0; }
.settings-row input[type="range"] { flex: 1; min-width: 0; }
.settings-row select {
  flex: 1; min-width: 0;
  height: 28px;
  padding: 0 8px;
  border: 1px solid #CBD5E1; border-radius: 6px;
  background: #fff;
  font-size: 12px;
}
.settings-row .val {
  width: 38px; text-align: right;
  font-family: ui-monospace, SFMono-Regular, monospace;
  font-size: 11px; color: #94A3B8;
}

.side-panel-body {
  flex: 1; min-height: 0;
  padding: 12px;
}
.empty {
  height: 100%;
  display: flex; align-items: center; justify-content: center;
  color: #94A3B8; font-size: 13px;
}
</style>
