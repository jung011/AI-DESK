<template>
  <div class="vscode-pane">
    <iframe
      v-if="iframeUrl"
      :src="iframeUrl"
      class="vscode-iframe"
      title="VSCode (code-server)"
      sandbox="allow-scripts allow-same-origin allow-forms allow-downloads allow-popups allow-clipboard-write"
      allow="clipboard-read; clipboard-write" />
    <div v-else class="vscode-empty">
      <p v-if="!url" class="msg">code-server URL 이 설정되어 있지 않습니다.</p>
      <p v-else-if="!alive" class="msg">
        code-server({{ url }}) 가 응답하지 않습니다.<br>
        <code>./start.sh</code> 로 재기동하거나 직접 <code>brew services start code-server</code> 로 띄워주세요.
      </p>
      <p v-else class="msg">워크스페이스가 지정되어 있지 않습니다.</p>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue';

interface Props {
  /** 백엔드 `/api/settings/code-server` 가 반환한 베이스 URL (예: http://localhost:30082). */
  url: string;
  /** 백엔드의 TCP 헬스 결과 — false 면 iframe 띄우지 않고 안내. */
  alive: boolean;
  /** 열고 싶은 워크스페이스 절대 경로. 빈 값이면 code-server 의 기본 환영 화면. */
  workspace?: string;
}

const props = defineProps<Props>();

const iframeUrl = computed(() => {
  if (!props.url || !props.alive) return '';
  const base = props.url.replace(/\/$/, '');
  if (!props.workspace) return base + '/';
  return base + '/?folder=' + encodeURIComponent(props.workspace);
});
</script>

<style scoped>
.vscode-pane {
  position: relative;
  width: 100%;
  height: 100%;
  background: #1E1E1E;
  border-radius: 6px;
  overflow: hidden;
}
.vscode-iframe {
  width: 100%;
  height: 100%;
  border: 0;
  display: block;
}
.vscode-empty {
  height: 100%;
  display: flex; align-items: center; justify-content: center;
  padding: 20px; text-align: center;
}
.vscode-empty .msg {
  font-size: 13px; color: #94A3B8; line-height: 1.6;
  margin: 0;
}
.vscode-empty code {
  font-family: ui-monospace, SFMono-Regular, monospace;
  background: rgba(0,0,0,.35);
  color: #E2E8F0;
  padding: 2px 6px;
  border-radius: 4px;
  font-size: 12px;
}
</style>
