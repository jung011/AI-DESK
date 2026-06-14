<template>
  <div class="page_content">
    <div class="group_pageLocation">
      <h2 class="tit_h2">콘솔 (검증용)</h2>
      <div class="descList_pageLocation">
        <a href="/dashboard">HOME</a>
        <a href="#"><em>콘솔</em></a>
      </div>
    </div>

    <!-- 세션 입력 / 빠른 선택 -->
    <div class="console-controls">
      <label class="session-input">
        <span>tmux 세션</span>
        <input
          v-model="sessionInput"
          type="text"
          placeholder="예: aidesk-self-liki"
          @keyup.enter="applySession" />
        <button class="btn" type="button" @click="applySession">연결</button>
      </label>

      <div class="quick-list">
        <span class="quick-label">빠른 선택</span>
        <button
          v-for="s in suggestions"
          :key="s"
          type="button"
          class="quick-chip"
          :class="{ active: s === activeSession }"
          @click="sessionInput = s; applySession()">
          {{ s }}
        </button>
      </div>
    </div>

    <!-- 임베드 터미널 -->
    <div class="console-terminal-wrap">
      <TerminalPane
        v-if="activeSession"
        :key="activeSession"
        :session="activeSession"
        :font-size="fontSize"
        @connected="onConnected"
        @disconnected="onDisconnected" />
      <div v-else class="empty">상단에서 tmux 세션명을 입력하거나 빠른 선택을 눌러주세요.</div>
    </div>

    <div class="console-meta">
      <span>상태: <em :class="statusClass">{{ statusText }}</em></span>
      <label class="font-size-ctl">
        폰트 크기
        <input type="range" min="10" max="20" v-model.number="fontSize" />
        <span class="font-size-val">{{ fontSize }}px</span>
      </label>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue';
import TerminalPane from '~/components/terminal/TerminalPane.vue';

// 자주 쓰는 세션 후보 (M6.1 검증 + 등록된 에이전트 일부 — M6.3 에서 동적 목록으로 교체)
const suggestions = ['aidesk-self-liki', 'aidesk-test-poc'];
const sessionInput = ref('');
const activeSession = ref('');
const fontSize = ref(14);
const statusText = ref('대기');
const statusClass = ref('');

function applySession(): void {
  const v = sessionInput.value.trim();
  if (!v) return;
  activeSession.value = v;
  statusText.value = '연결 중…';
  statusClass.value = 'connecting';
}
function onConnected(): void {
  statusText.value = '연결됨';
  statusClass.value = 'open';
}
function onDisconnected(reason: string): void {
  statusText.value = `연결 종료 (${reason})`;
  statusClass.value = 'closed';
}
</script>

<style scoped>
.page_content {
  padding: 28px;
  max-width: 1400px;
  margin: 0 auto;
}
.group_pageLocation {
  display: flex; align-items: center; gap: 16px; margin-bottom: 20px;
}
.tit_h2 { font-size: 20px; font-weight: 700; color: #101010; margin: 0; }
.descList_pageLocation {
  display: flex; align-items: center; gap: 6px;
  font-size: 12px; color: #94A3B8;
}
.descList_pageLocation a { color: #94A3B8; text-decoration: none; }
.descList_pageLocation a + a::before {
  content: '›'; margin-right: 6px; color: #CBD5E1;
}
.descList_pageLocation em { font-style: normal; color: #475569; font-weight: 600; }

.console-controls {
  background: #fff;
  border: 1px solid #E2E8F0;
  border-radius: 8px;
  padding: 14px 16px;
  margin-bottom: 14px;
  display: flex; flex-direction: column; gap: 10px;
}
.session-input {
  display: flex; align-items: center; gap: 8px;
  font-size: 12px; color: #475569;
}
.session-input span { font-weight: 600; }
.session-input input {
  flex: 1; height: 32px;
  padding: 0 10px;
  border: 1px solid #CBD5E1; border-radius: 6px;
  font-family: ui-monospace, SFMono-Regular, monospace; font-size: 13px;
}
.btn {
  height: 32px; padding: 0 14px;
  background: #0062ff; color: #fff;
  border: none; border-radius: 6px;
  font-size: 12px; font-weight: 600;
  cursor: pointer;
}
.btn:hover { background: #0052d9; }

.quick-list {
  display: flex; align-items: center; gap: 8px; flex-wrap: wrap;
}
.quick-label { font-size: 11px; font-weight: 600; color: #94A3B8; }
.quick-chip {
  padding: 4px 10px;
  background: #F1F5F9;
  border: 1px solid transparent;
  border-radius: 12px;
  font-family: ui-monospace, SFMono-Regular, monospace; font-size: 11px;
  color: #475569; cursor: pointer;
}
.quick-chip:hover { border-color: #CBD5E1; }
.quick-chip.active { background: #EEF2FF; color: #4338CA; border-color: #C7D2FE; }

.console-terminal-wrap {
  height: 520px;
  background: #1E293B;
  border-radius: 8px;
  overflow: hidden;
}
.empty {
  height: 100%;
  display: flex; align-items: center; justify-content: center;
  color: #94A3B8; font-size: 13px;
}

.console-meta {
  margin-top: 12px;
  display: flex; align-items: center; justify-content: space-between;
  font-size: 12px; color: #475569;
}
.console-meta em { font-style: normal; font-weight: 600; color: #475569; }
.console-meta em.open { color: #2E7D32; }
.console-meta em.connecting { color: #E65100; }
.console-meta em.closed { color: #6A1B9A; }
.font-size-ctl { display: inline-flex; align-items: center; gap: 8px; }
.font-size-val {
  font-family: ui-monospace, SFMono-Regular, monospace;
  color: #94A3B8;
  width: 36px; text-align: right;
}
</style>
