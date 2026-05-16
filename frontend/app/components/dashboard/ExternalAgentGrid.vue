<template>
  <section class="external-section">
    <div class="external-head">
      <h3 class="external-title">사내 동료 AI</h3>
      <span class="external-summary">
        <span class="online-dot online" /> 온라인 {{ onlineCount }}
        <span class="external-sep">·</span>
        전체 {{ list.length }}
      </span>
    </div>

    <div v-if="list.length === 0" class="external-empty">
      등록된 외부 에이전트가 없습니다.
    </div>

    <div v-else class="external-grid">
      <button
        v-for="a in sorted"
        :key="a.employeeId"
        type="button"
        class="external-card"
        :class="{ offline: !a.online, 'is-me': a.me }"
        @click="openDetail(a)">
        <span class="online-dot" :class="{ online: a.online }" />
        <div class="external-name">
          {{ a.name || a.employeeId }}<span v-if="a.me" class="me-tag">(me)</span>
        </div>
        <div class="external-dept">{{ a.department || '—' }}</div>
      </button>
    </div>

    <Teleport to="body">
      <div v-if="selected" class="popup-overlay" @click.self="selected = null">
        <div class="popup-box" role="dialog">
          <header class="popup-head">
            <div class="popup-title-wrap">
              <span class="online-dot" :class="{ online: selected.online }" />
              <h3>
                {{ selected.name || selected.employeeId }}<span v-if="selected.me" class="me-tag">(me)</span>
              </h3>
            </div>
            <div class="popup-head-actions">
              <button
                v-if="selected.me"
                class="popup-action-btn"
                type="button"
                :disabled="!a2aWorkspace"
                :title="!a2aWorkspace ? '먼저 A2A 워크스페이스를 지정하세요' : ''"
                @click="openTerminal(selected)">
                터미널 열기
              </button>
              <button class="popup-close" type="button" @click="selected = null">×</button>
            </div>
          </header>
          <div class="popup-body">
            <div class="meta-row">
              <span class="meta-label">부서</span>
              <span class="meta-value">{{ selected.department || '—' }}</span>
            </div>
            <div class="meta-row">
              <span class="meta-label">상태</span>
              <span class="meta-value">{{ selected.online ? '온라인' : '오프라인' }}</span>
            </div>
            <div class="meta-row">
              <span class="meta-label">ID</span>
              <span class="meta-value mono">{{ selected.employeeId }}</span>
            </div>
            <div v-if="selected.me" class="a2a-section">
              <div class="a2a-title">A2A 워크스페이스</div>
              <div class="a2a-row">
                <span class="a2a-path" :class="{ unset: !a2aWorkspace }">
                  {{ a2aWorkspace || '미설정 — 사내 동료와 소통하려면 워크스페이스를 지정하세요' }}
                </span>
                <button
                  class="a2a-pick-btn"
                  type="button"
                  :disabled="workspaceBusy"
                  @click="chooseWorkspace">
                  {{ workspaceBusy ? '선택 중…' : '워크스페이스 지정' }}
                </button>
              </div>
              <p class="a2a-hint">
                선택한 폴더에서만 kaflix-a2a / kaflix-channel MCP 가 활성화됩니다.
                변경 후 새로 띄우는 (me) 터미널부터 반영됩니다.
              </p>
              <label v-if="a2aWorkspace" class="purge-row">
                <input type="checkbox" v-model="purgePreviousHistory">
                <span>
                  변경 시 옛 워크스페이스의 대화 기록(.jsonl) 과 (me) tmux 세션을 함께 정리
                  <span class="purge-hint">
                    같은 경로에 새 폴더를 만들었을 때 옛 대화가 자동 복원되는 걸 방지합니다.
                  </span>
                </span>
              </label>
            </div>

            <div class="skills-section">
              <div class="skills-title">스킬 ({{ selected.skills.length }})</div>
              <div v-if="selected.skills.length === 0" class="skills-empty">등록된 스킬 없음</div>
              <div v-else class="skills-list">
                <span v-for="s in selected.skills" :key="s" class="skill-chip">{{ s }}</span>
              </div>
            </div>
          </div>
        </div>
      </div>
    </Teleport>
  </section>
</template>

<script setup lang="ts">
import type { ApiEnvelope } from '~/vo/agents/AgentVo';
import type { ExternalAgentItem } from '~/vo/external/ExternalAgentVo';

const list = ref<ExternalAgentItem[]>([]);
const selected = ref<ExternalAgentItem | null>(null);
const workspaceBusy = ref(false);
const a2aWorkspace = ref('');
const purgePreviousHistory = ref(false);

interface A2aWorkspaceRs { path: string }

async function openDetail(a: ExternalAgentItem): Promise<void> {
  selected.value = a;
  if (a.me) await fetchA2aWorkspace();
}

async function fetchA2aWorkspace(): Promise<void> {
  try {
    const { $api } = useNuxtApp();
    const env = await $api<ApiEnvelope<A2aWorkspaceRs>>('/api/settings/a2a-workspace');
    if (env.result === 0 && env.data) a2aWorkspace.value = env.data.path || '';
  } catch { /* 무시 — 모달에서 재시도 가능 */ }
}

async function chooseWorkspace(): Promise<void> {
  if (workspaceBusy.value) return;
  workspaceBusy.value = true;
  try {
    const { $api, $helper } = useNuxtApp();
    // macOS 폴더 선택 다이얼로그 — 로컬 헬퍼가 처리 (백엔드가 Docker 화돼도 동작)
    const pickEnv = await $helper<{ rc: number; message?: string; path?: string }>(
      '/api/browse-workspace',
      { method: 'POST' }
    );
    if (pickEnv.rc !== 0) {
      alert(pickEnv.message || '폴더 선택을 지원하지 않습니다.');
      return;
    }
    const chosen = (pickEnv.path || '').trim();
    if (!chosen) return; // 사용자 취소

    const putEnv = await $api<ApiEnvelope<A2aWorkspaceRs>>('/api/settings/a2a-workspace', {
      method: 'PUT',
      body: { path: chosen, purgePreviousHistory: purgePreviousHistory.value },
    });
    if (putEnv.result !== 0) {
      alert(putEnv.message || '워크스페이스 설정에 실패했습니다.');
      return;
    }
    a2aWorkspace.value = putEnv.data?.path || chosen;
    purgePreviousHistory.value = false; // 다음번 변경 위해 기본값 복원
  } catch (e) {
    const msg = e instanceof Error ? e.message : String(e);
    alert(`워크스페이스 설정 중 오류가 발생했습니다 (헬퍼 가동 확인).\n${msg}`);
  } finally {
    workspaceBusy.value = false;
  }
}

const emit = defineEmits<{
  /** (me) 카드의 [터미널 보기] 클릭 → 부모(dashboard)가 임베드 사이드 패널 오픈. */
  (e: 'select-me', agent: ExternalAgentItem): void;
}>();

function openTerminal(a: ExternalAgentItem): void {
  if (!a.me) return;
  if (!a2aWorkspace.value) return; // 워크스페이스 미설정 시 비활성 (버튼 disabled 가드)
  emit('select-me', a);
  selected.value = null; // 모달 닫고 사이드 패널로 전환
}

const onlineCount = computed(() => list.value.filter((a) => a.online).length);

/** 온라인 우선 + 이름 오름차순 */
const sorted = computed(() => {
  return [...list.value].sort((a, b) => {
    if (a.online !== b.online) return a.online ? -1 : 1;
    return (a.name || a.employeeId).localeCompare(b.name || b.employeeId);
  });
});

let timer: ReturnType<typeof setInterval> | null = null;

async function fetchOnce(): Promise<void> {
  try {
    const { $api } = useNuxtApp();
    const env = await $api<ApiEnvelope<ExternalAgentItem[]>>('/api/external-agents');
    if (env.result === 0 && Array.isArray(env.data)) list.value = env.data;
  } catch {
    /* swallow — 다음 폴링에서 재시도 */
  }
}

onMounted(() => {
  void fetchOnce();
  timer = setInterval(fetchOnce, 30_000);
});
onUnmounted(() => {
  if (timer) clearInterval(timer);
});
</script>

<style scoped>
.external-section {
  margin-top: 24px;
  background: #fff;
  border: 1px solid #E2E8F0;
  border-radius: 8px;
  padding: 16px 18px;
}
.external-head {
  display: flex; align-items: baseline; justify-content: space-between;
  margin-bottom: 12px;
}
.external-title {
  margin: 0; font-size: 14px; font-weight: 700; color: #101010;
}
.external-summary {
  font-size: 12px; color: #475569;
  display: inline-flex; align-items: center; gap: 6px;
}
.external-sep { color: #CBD5E1; }

.external-empty {
  padding: 24px 0; text-align: center;
  color: #94A3B8; font-size: 13px;
}

.external-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(180px, 1fr));
  gap: 10px;
}
.external-card {
  display: flex; align-items: center; gap: 8px;
  padding: 10px 12px;
  border: 1px solid #E2E8F0; border-radius: 6px;
  background: #fff;
  font: inherit; color: inherit; text-align: left;
  cursor: pointer;
  transition: border-color .15s, background .15s, transform .08s;
}
.external-card.offline { background: #FAFBFD; }
.external-card.is-me { border-color: #0062ff; background: #F0F6FF; }
.external-card:hover { border-color: #0062ff; background: #F8FAFC; }
.external-card:active { transform: scale(.98); }

.me-tag {
  display: inline-block;
  margin-left: 4px;
  padding: 1px 5px;
  border-radius: 4px;
  background: #0062ff;
  color: #fff;
  font-size: 10px;
  font-weight: 700;
  vertical-align: 1px;
}

.online-dot {
  width: 8px; height: 8px; border-radius: 50%;
  background: #CBD5E1;
  flex-shrink: 0;
}
.online-dot.online { background: #00C853; }

.external-name {
  font-size: 13px; font-weight: 600; color: #1E293B;
  flex: 1; min-width: 0;
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}
.external-dept {
  font-size: 11px; color: #94A3B8;
  flex-shrink: 0;
}

/* === 스킬 모달 === */
.popup-overlay {
  position: fixed; inset: 0;
  background: rgba(15, 23, 42, 0.45);
  display: flex; align-items: center; justify-content: center;
  z-index: 1100;
}
.popup-box {
  width: 440px; max-width: calc(100vw - 40px); max-height: calc(100vh - 80px);
  background: #fff; border-radius: 10px;
  box-shadow: 0 20px 50px rgba(15, 23, 42, .2);
  display: flex; flex-direction: column;
}
.popup-head {
  display: flex; align-items: center; justify-content: space-between;
  padding: 16px 20px; border-bottom: 1px solid #F0F2F5;
}
.popup-title-wrap { display: inline-flex; align-items: center; gap: 8px; }
.popup-head h3 { margin: 0; font-size: 15px; font-weight: 700; color: #101010; }
.popup-head-actions {
  display: inline-flex; align-items: center; gap: 8px;
}
.popup-action-btn {
  height: 28px; padding: 0 12px;
  background: #0062ff; color: #fff;
  border: none; border-radius: 6px;
  font-size: 12px; font-weight: 600;
  cursor: pointer;
  transition: background .15s, opacity .15s;
}
.popup-action-btn:hover:not(:disabled) { background: #0052d9; }
.popup-action-btn:disabled { opacity: .55; cursor: progress; }
.popup-close {
  width: 28px; height: 28px;
  background: none; border: none; font-size: 22px;
  color: #94A3B8; cursor: pointer; line-height: 1;
}
.popup-close:hover { color: #475569; }
.popup-body { padding: 18px 20px; overflow-y: auto; }

.meta-row {
  display: flex; gap: 12px; padding: 5px 0;
  font-size: 13px;
}
.meta-label {
  flex-shrink: 0; width: 60px;
  color: #94A3B8; font-weight: 600;
}
.meta-value { color: #1E293B; }
.meta-value.mono { font-family: ui-monospace, SFMono-Regular, monospace; font-size: 12px; }

.a2a-section {
  margin-top: 14px; padding-top: 14px;
  border-top: 1px solid #F0F2F5;
}
.a2a-title {
  font-size: 12px; font-weight: 700; color: #475569;
  margin-bottom: 8px;
}
.a2a-row {
  display: flex; align-items: center; gap: 10px;
}
.a2a-path {
  flex: 1; min-width: 0;
  font-size: 12px;
  color: #1E293B;
  font-family: ui-monospace, SFMono-Regular, monospace;
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
  padding: 6px 10px;
  background: #F8FAFC;
  border: 1px solid #E2E8F0;
  border-radius: 4px;
}
.a2a-path.unset { color: #94A3B8; font-family: inherit; font-style: italic; }
.a2a-pick-btn {
  flex-shrink: 0;
  height: 28px; padding: 0 12px;
  background: #fff; color: #0062ff;
  border: 1px solid #0062ff; border-radius: 6px;
  font-size: 12px; font-weight: 600;
  cursor: pointer;
  transition: background .15s;
}
.a2a-pick-btn:hover:not(:disabled) { background: #F0F6FF; }
.a2a-pick-btn:disabled { opacity: .55; cursor: progress; }
.a2a-hint {
  margin: 8px 0 0; font-size: 11px; color: #94A3B8; line-height: 1.5;
}

.purge-row {
  display: flex; align-items: flex-start; gap: 8px;
  margin-top: 10px; padding: 8px 10px;
  background: #FEF3C7; border-radius: 6px;
  font-size: 12px; color: #78350F; line-height: 1.4;
  cursor: pointer;
}
.purge-row input[type="checkbox"] {
  appearance: auto; -webkit-appearance: auto;
  width: 14px; height: 14px; margin-top: 2px; flex-shrink: 0;
}
.purge-hint {
  display: block; margin-top: 3px;
  font-size: 11px; color: #92400E; opacity: 0.85;
}

.skills-section {
  margin-top: 14px; padding-top: 14px;
  border-top: 1px solid #F0F2F5;
}
.skills-title {
  font-size: 12px; font-weight: 700; color: #475569;
  margin-bottom: 8px;
}
.skills-empty { font-size: 12px; color: #94A3B8; }
.skills-list { display: flex; flex-wrap: wrap; gap: 6px; }
.skill-chip {
  display: inline-flex; align-items: center;
  padding: 4px 10px; border-radius: 12px;
  background: #EEF2FF; color: #4338CA;
  font-size: 11px; font-weight: 600;
}
</style>
