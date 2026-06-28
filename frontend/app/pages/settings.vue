<template>
  <div class="page_content">
    <div class="group_pageLocation">
      <h2 class="tit_h2">설정</h2>
      <div class="descList_pageLocation">
        <a href="#">HOME</a>
        <a href="#"><em>설정</em></a>
      </div>
    </div>

    <!-- (me) 워크스페이스 -->
    <section class="card">
      <header class="card-head">
        <h3 class="card-title">(me) 워크스페이스</h3>
        <p class="card-desc">
          본인의 (me) AI 가 동작할 *주 작업 폴더*. 그 폴더의 claude 가 사내 동료들로부터 메시지를
          수신합니다. 변경 시 (me) 에이전트가 새 워크스페이스로 이동합니다.
        </p>
      </header>
      <div class="card-body">
        <div class="path-row">
          <span class="path-value" :class="{ unset: !mePath }">
            {{ mePath || '미지정 — 폴더를 선택하세요' }}
          </span>
          <button
            type="button"
            class="btn-secondary"
            :disabled="mePicking || meSaving"
            @click="pickMeFolder">
            {{ mePicking ? '선택 중…' : '폴더 선택' }}
          </button>
        </div>
        <label v-if="showMePurgeOption" class="purge-option">
          <input
            type="checkbox"
            :checked="mePurgePrevious"
            :disabled="meSaving"
            @change="mePurgePrevious = ($event.target as HTMLInputElement).checked" />
          <span>기존 워크스페이스의 Claude 대화 기록도 함께 삭제</span>
        </label>
        <div class="card-actions">
          <span v-if="meSavedMsg" class="status-msg">{{ meSavedMsg }}</span>
          <button
            type="button"
            class="btn-save"
            :disabled="meLoading || meSaving || !mePath || mePath === meSavedPath"
            @click="saveMe">
            {{ meSaving ? '저장 중…' : '저장' }}
          </button>
        </div>
      </div>
    </section>

    <!-- 공통 작업 규칙 문서 -->
    <section class="card">
      <header class="card-head">
        <h3 class="card-title">공통 작업 규칙 문서</h3>
        <p class="card-desc">
          신규 AI 가 처음 기동될 때 자동으로 읽어 숙지할 공통 작업 규칙 문서 파일. Helper 가 tmux 안의
          claude 에 "먼저 {경로} 를 읽고 거기 안내된 작업 규칙들을 순서대로 숙지하세요." 라고 주입합니다.
          미지정 상태면 주입 생략.
        </p>
      </header>
      <div class="card-body">
        <div class="path-row">
          <span class="path-value" :class="{ unset: !path }">
            {{ path || '미지정 — 파일을 선택하세요' }}
          </span>
          <button
            type="button"
            class="btn-secondary"
            :disabled="picking || saving"
            @click="pickFile">
            {{ picking ? '선택 중…' : '파일 선택' }}
          </button>
        </div>
        <div class="card-actions">
          <span v-if="lastSavedMsg" class="status-msg">{{ lastSavedMsg }}</span>
          <button
            v-if="path"
            type="button"
            class="btn-tertiary"
            :disabled="saving"
            @click="clearPath">
            지정 해제
          </button>
          <button
            type="button"
            class="btn-save"
            :disabled="loading || saving || path === savedPath"
            @click="save">
            {{ saving ? '저장 중…' : '저장' }}
          </button>
        </div>
      </div>
    </section>
  </div>
</template>

<script setup lang="ts">
import type { ApiEnvelope } from '~/vo/agents/AgentVo';

interface WorkroleFileRs { path: string }
interface A2aWorkspaceRs { path: string }
interface HelperBrowseRs { rc: number; path?: string; message?: string }

const path = ref('');
const savedPath = ref('');
const loading = ref(true);
const saving = ref(false);
const picking = ref(false);
const lastSavedMsg = ref('');

const mePath = ref('');
const meSavedPath = ref('');
const meLoading = ref(true);
const meSaving = ref(false);
const mePicking = ref(false);
const meSavedMsg = ref('');
/** 변경 모드(옛 path 있고 새 path 다름)에서만 의미. AI 삭제 다이얼로그와 동일 default true. */
const mePurgePrevious = ref(true);
const showMePurgeOption = computed(
  () => !!meSavedPath.value && meSavedPath.value !== mePath.value,
);

async function fetchOnce(): Promise<void> {
  loading.value = true;
  try {
    const { $api } = useNuxtApp();
    const env = await $api<ApiEnvelope<WorkroleFileRs>>('/api/settings/workrole-file');
    if (env.result === 0 && env.data) {
      path.value = env.data.path || '';
      savedPath.value = path.value;
    }
  } catch (e) {
    lastSavedMsg.value = `조회 실패: ${e instanceof Error ? e.message : String(e)}`;
  } finally {
    loading.value = false;
  }
}

async function pickFile(): Promise<void> {
  if (picking.value) return;
  picking.value = true;
  try {
    const { $helper } = useNuxtApp();
    const res = await $helper<HelperBrowseRs>('/api/browse-file', {
      method: 'POST',
      body: { prompt: '공통 작업 규칙 문서 파일을 선택하세요' },
    });
    if (res.rc !== 0) {
      lastSavedMsg.value = res.message || '파일 선택 실패';
      return;
    }
    if (res.path) path.value = res.path; // 빈 문자열이면 사용자 취소 — 기존 값 유지
  } catch (e) {
    lastSavedMsg.value = `파일 선택 호출 실패: ${e instanceof Error ? e.message : String(e)}`;
  } finally {
    picking.value = false;
  }
}

function clearPath(): void {
  path.value = '';
}

async function save(): Promise<void> {
  if (saving.value) return;
  saving.value = true;
  lastSavedMsg.value = '';
  try {
    const { $api } = useNuxtApp();
    const env = await $api<ApiEnvelope<WorkroleFileRs>>('/api/settings/workrole-file', {
      method: 'PUT',
      body: { path: path.value },
    });
    if (env.result === 0 && env.data) {
      savedPath.value = env.data.path || '';
      path.value = savedPath.value;
      lastSavedMsg.value = '저장됨';
      setTimeout(() => { lastSavedMsg.value = ''; }, 2500);
    } else {
      lastSavedMsg.value = env.message || '저장 실패';
    }
  } catch (e) {
    lastSavedMsg.value = `저장 실패: ${e instanceof Error ? e.message : String(e)}`;
  } finally {
    saving.value = false;
  }
}

async function fetchMeOnce(): Promise<void> {
  meLoading.value = true;
  try {
    const { $api } = useNuxtApp();
    const env = await $api<ApiEnvelope<A2aWorkspaceRs>>('/api/settings/a2a-workspace');
    if (env.result === 0 && env.data) {
      mePath.value = env.data.path || '';
      meSavedPath.value = mePath.value;
    }
  } catch (e) {
    meSavedMsg.value = `조회 실패: ${e instanceof Error ? e.message : String(e)}`;
  } finally {
    meLoading.value = false;
  }
}

async function pickMeFolder(): Promise<void> {
  if (mePicking.value) return;
  mePicking.value = true;
  meSavedMsg.value = '';
  try {
    const { $helper } = useNuxtApp();
    const res = await $helper<HelperBrowseRs>('/api/browse-workspace', { method: 'POST' });
    if (res.rc !== 0) {
      meSavedMsg.value = res.message || '폴더 선택을 사용할 수 없습니다.';
      return;
    }
    if (res.path) mePath.value = res.path;
  } catch (e) {
    meSavedMsg.value = `폴더 선택 호출 실패: ${e instanceof Error ? e.message : String(e)}`;
  } finally {
    mePicking.value = false;
  }
}

interface HelperScopeRs { rc: number; message?: string; absolutePath?: string }

async function saveMe(): Promise<void> {
  if (meSaving.value || !mePath.value) return;
  meSaving.value = true;
  meSavedMsg.value = '';
  try {
    // MeWorkspaceDialog 와 동일한 2단계 — helper scope 후 backend PUT.
    // 옛엔 backend 만 호출해 ~/.claude.json scope 처리가 누락됐었음.
    const { $api, $helper } = useNuxtApp();
    const scope = await $helper<HelperScopeRs>('/api/scope-workspace', {
      method: 'POST',
      body: {
        newWorkspace: mePath.value,
        oldWorkspace: meSavedPath.value,
        purgePreviousHistory: showMePurgeOption.value && mePurgePrevious.value,
        meTmuxSession: '',
      },
    });
    if (scope.rc !== 0) {
      meSavedMsg.value = scope.message || '폴더 검증 실패';
      return;
    }
    const absolute = scope.absolutePath || mePath.value;
    const env = await $api<ApiEnvelope<A2aWorkspaceRs>>('/api/settings/a2a-workspace', {
      method: 'PUT',
      body: { path: absolute, purgePreviousHistory: false },
    });
    if (env.result === 0 && env.data) {
      meSavedPath.value = env.data.path || '';
      mePath.value = meSavedPath.value;
      meSavedMsg.value = '저장됨';
      setTimeout(() => { meSavedMsg.value = ''; }, 2500);
    } else {
      meSavedMsg.value = env.message || '저장 실패';
    }
  } catch (e) {
    meSavedMsg.value = `저장 실패: ${e instanceof Error ? e.message : String(e)}`;
  } finally {
    meSaving.value = false;
  }
}

onMounted(() => {
  void fetchOnce();
  void fetchMeOnce();
});
</script>

<style scoped>
.page_content {
  padding: 28px;
  max-width: 1400px;
  margin: 0 auto;
}
.group_pageLocation {
  display: flex;
  align-items: center;
  gap: 16px;
  margin-bottom: 20px;
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

.card {
  background: var(--bg-card);
  border: 1px solid #E2E8F0;
  border-radius: 8px;
  margin-bottom: 20px;
  box-shadow: 0 3px 10px 0 rgba(67, 87, 103, .08);
}
.card-head {
  padding: 18px 22px;
  border-bottom: 1px solid #F0F2F5;
}
.card-title { font-size: 15px; font-weight: 700; color: #101010; margin: 0 0 6px; }
.card-desc { font-size: 12px; color: #94A3B8; margin: 0; line-height: 1.6; }
.card-body { padding: 18px 22px; }

.path-row {
  display: flex; align-items: center; gap: 12px;
}
.path-value {
  flex: 1;
  padding: 10px 14px;
  background: #F8FAFC;
  border: 1px solid #E2E8F0;
  border-radius: 6px;
  font-family: ui-monospace, SFMono-Regular, monospace;
  font-size: 12px;
  color: #1E293B;
  word-break: break-all;
}
.path-value.unset { color: #94A3B8; font-family: inherit; font-style: italic; }

.btn-secondary {
  height: 36px; padding: 0 16px;
  background: var(--bg-card); color: #475569;
  border: 1px solid #D4DCE4; border-radius: 6px;
  font-size: 13px; font-weight: 600; cursor: pointer;
  white-space: nowrap;
}
.btn-secondary:hover:not(:disabled) { background: #F8FAFC; border-color: #0062ff; color: #0062ff; }
.btn-secondary:disabled { opacity: .6; cursor: not-allowed; }

.purge-option {
  display: flex; align-items: center; gap: 8px;
  margin-top: 14px; padding-top: 12px;
  border-top: 1px solid #F0F2F5;
  font-size: 12px; color: #475569;
  cursor: pointer; user-select: none;
}
.purge-option input[type=checkbox] {
  appearance: auto;
  -webkit-appearance: auto;
  width: 14px; height: 14px;
  margin: 0;
  cursor: pointer;
  accent-color: #0062ff;
}
.purge-option:has(input:disabled) { cursor: not-allowed; opacity: .6; }

.card-actions {
  display: flex; align-items: center; justify-content: flex-end;
  gap: 12px; margin-top: 14px;
}
.status-msg { font-size: 12px; color: #475569; margin-right: auto; }
.btn-tertiary {
  height: 32px; padding: 0 12px;
  background: transparent; color: #94A3B8;
  border: none; border-radius: 6px;
  font-size: 12px; cursor: pointer;
}
.btn-tertiary:hover:not(:disabled) { color: #E83667; }
.btn-save {
  height: 34px; padding: 0 18px;
  background: #0062ff; color: #fff;
  border: none; border-radius: 6px;
  font-size: 13px; font-weight: 600;
  cursor: pointer;
  transition: background .15s, opacity .15s;
}
.btn-save:hover:not(:disabled) { background: #0052d4; }
.btn-save:disabled { background: #CBD5E1; cursor: not-allowed; }
</style>
