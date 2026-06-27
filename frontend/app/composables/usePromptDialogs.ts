/**
 * agent 별 *claude TUI yes/no option dialog* 의 latest state.
 *
 * helper 가 매 reporter cycle (30s) 에 capture-pane 결과 안 dialog 검출 → backend
 * desktop service 가 변화 감지 시 SSE `agent.prompt-dialog` event publish → 이 composable
 * 이 subscribe 해서 reactive map 갱신. 채팅 페이지의 ConversationView 가 현재 partner 의
 * dialog state 보고 dynamic 버튼 표시.
 *
 * [[project-prompt-dialog-respond]] (TBD).
 */
export interface PromptOption {
  index: number;
  label: string;
}

interface AgentPromptDialogEvent {
  agentId: string;
  tmuxSession: string;
  options: PromptOption[] | null;
}

export function usePromptDialogs() {
  const { $api } = useNuxtApp();
  // 글로벌 shared state — 페이지 변경에도 유지.
  const byAgentId = useState<Record<string, PromptOption[] | null>>(
    'aidesk.promptDialogs',
    () => ({})
  );

  // SSE singleton — 글로벌 1회 만 subscribe. dev hot-reload 시 옛 source 정리.
  const subscribed = useState<boolean>('aidesk.promptDialogs.subscribed', () => false);

  function ensureSubscribed(): void {
    if (subscribed.value) return;
    if (typeof window === 'undefined' || typeof EventSource === 'undefined') return;
    const es = new EventSource('/api/messages/events');
    es.addEventListener('agent.prompt-dialog', (e: MessageEvent) => {
      try {
        const data = JSON.parse(e.data) as AgentPromptDialogEvent;
        if (!data.agentId) return;
        const next = { ...byAgentId.value };
        if (data.options && data.options.length > 0) {
          next[data.agentId] = data.options;
        } else {
          delete next[data.agentId];
        }
        byAgentId.value = next;
      } catch (err) {
        // ignore — malformed event
      }
    });
    subscribed.value = true;
  }

  function getDialog(agentId: string | null | undefined): PromptOption[] | null {
    if (!agentId) return null;
    return byAgentId.value[agentId] ?? null;
  }

  async function respond(agentId: string, index: number): Promise<boolean> {
    try {
      const env = await $api<{ result: number; message: string }>(
        `/api/agents/${encodeURIComponent(agentId)}/prompt-respond`,
        { method: 'POST', body: { index } }
      );
      if (env.result === 0) {
        // optimistic clear — 다음 reporter cycle 의 backend event 가 정정해줄 거.
        const next = { ...byAgentId.value };
        delete next[agentId];
        byAgentId.value = next;
        return true;
      }
      return false;
    } catch {
      return false;
    }
  }

  return { byAgentId, ensureSubscribed, getDialog, respond };
}
