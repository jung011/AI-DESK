import { ref } from 'vue';

/**
 * agent-scoped textarea draft store — terminal 페이지의 WebTerminal 가 partner 전환
 * 시 컴포넌트 destroy + remount (`:key="agentId"`) 라 내부 inputDraft 가 매번 빈
 * ref('') 로 init. 다만 tmux pty 의 line buffer 는 *server-side 유지* 라 사용자
 * 가 다시 돌아오면 xterm 에는 옛 입력 보이는데 textarea 는 비어 desync.
 *
 * → module-scoped singleton store 로 agent 별 draft 보존. WebTerminal 가 mount
 *   시 store.get(agentId) 로 복원 + 변경 시 store.set 으로 갱신.
 */
const drafts = ref<Record<string, string>>({});

export function useInputDrafts() {
  return {
    get(agentId: string): string {
      return drafts.value[agentId] || '';
    },
    set(agentId: string, text: string): void {
      drafts.value[agentId] = text;
    },
    clear(agentId: string): void {
      delete drafts.value[agentId];
    },
  };
}
