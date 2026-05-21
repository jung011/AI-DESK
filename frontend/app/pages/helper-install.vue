<template>
  <div class="install-page">
    <div class="install-box">
      <header class="install-head">
        <h2 v-if="isUpdate">AI Desk Helper 업데이트 가능</h2>
        <h2 v-else>AI Desk Helper 설치 필요</h2>
        <p v-if="isUpdate" class="sub">
          현재 <strong>{{ helperVersion.running || '?' }}</strong> →
          최신 <strong>{{ helperVersion.latest }}</strong>
        </p>
        <p v-else class="sub">본 PC 에 helper 가 설치되어 있지 않아 일부 기능이 동작하지 않습니다.</p>
      </header>

      <ol class="steps">
        <li>
          <div class="step-num">1</div>
          <div class="step-body">
            <h3>{{ isUpdate ? '새 패키지 다운로드' : '패키지 다운로드' }}</h3>
            <p class="step-desc">
              {{ isUpdate
                  ? '아래 버튼으로 본인 mac 에 최신 .pkg 를 받습니다. 설치 시 기존 plist 환경변수는 보존됩니다.'
                  : '아래 버튼으로 본인 mac 에 .pkg 를 받습니다.' }}
            </p>
            <a class="btn-primary" href="/api/helper/download" download>
              {{ helperVersion.latestFilename || 'AIDeskHelper .pkg' }} 다운로드
            </a>
          </div>
        </li>
        <li>
          <div class="step-num">2</div>
          <div class="step-body">
            <h3>패키지 실행 + 설치</h3>
            <p class="step-desc">
              다운로드 폴더에서 <code>AIDeskHelper-*.pkg</code> 더블클릭 →
              미서명 경고가 뜨면
              <strong>시스템 설정 → 개인정보 보호 및 보안 → 그래도 열기</strong>
              한 뒤 다시 실행.
            </p>
            <p class="step-desc small">
              Documents 폴더 접근 권한 다이얼로그가 뜨면 <strong>허용</strong>.
              helper 가 워크스페이스 스캔에 필요합니다.
            </p>
          </div>
        </li>
        <li>
          <div class="step-num">3</div>
          <div class="step-body">
            <h3>설치 확인</h3>
            <p class="step-desc">
              설치 끝나면 아래 버튼을 누르세요. helper 가 동작 중이면 대시보드로 진입합니다.
            </p>
            <button
              class="btn-primary"
              type="button"
              :disabled="checking"
              @click="recheck">
              {{ checking ? '확인 중…' : '설치 완료 — 다시 확인' }}
            </button>
            <p v-if="lastCheckFailed" class="check-failed">
              아직 helper 응답이 없습니다. 설치가 끝났는지, LaunchAgent 가 실행됐는지 확인해주세요.
              <br />터미널: <code>launchctl list | grep com.aidesk.agent</code>
            </p>
          </div>
        </li>
      </ol>
    </div>
  </div>
</template>

<script setup lang="ts">
import { useHelperVersionStore } from '~/stores/helperVersion';

const helperVersion = useHelperVersionStore();
const checking = ref(false);
const lastCheckFailed = ref(false);

/** 페이지 진입 시 store 가 비어있을 수 있어 1회 새로 조회 — 업데이트 모드 / 미설치
 *  모드 판정에 필요. */
onMounted(async () => {
  if (!helperVersion.running && !helperVersion.missing) {
    await helperVersion.refresh();
  }
});

/** helper 가 *살아있고* (= missing=false) latest 가 *다르면* 업데이트 모드. */
const isUpdate = computed(
  () => !helperVersion.missing && helperVersion.running && helperVersion.needsUpdate,
);

async function recheck(): Promise<void> {
  if (checking.value) return;
  checking.value = true;
  lastCheckFailed.value = false;
  try {
    await helperVersion.refresh();
    if (helperVersion.missing) {
      lastCheckFailed.value = true;
      return;
    }
    // 업데이트 모드는 *현재 running == latest* 가 되면 통과. 설치 모드는 helper 가
    // 살아있기만 하면 통과 (이 경우 needsUpdate 가 true 일 수 있는데, 그 안내는 배너로).
    await navigateTo('/dashboard');
  } finally {
    checking.value = false;
  }
}
</script>

<style scoped>
.install-page {
  min-height: 100vh;
  background: #F4F6FB;
  display: flex; align-items: flex-start; justify-content: center;
  padding: 60px 20px;
}
.install-box {
  width: 640px; max-width: 100%;
  background: #fff;
  border-radius: 12px;
  box-shadow: 0 8px 24px rgba(15, 23, 42, .08);
  padding: 36px 40px;
}
.install-head h2 {
  margin: 0 0 8px;
  font-size: 22px; font-weight: 700; color: #101010;
}
.install-head .sub {
  margin: 0 0 28px;
  font-size: 13px; color: #64748b;
}
.steps {
  list-style: none; padding: 0; margin: 0;
  display: flex; flex-direction: column; gap: 24px;
}
.steps > li {
  display: flex; gap: 16px; align-items: flex-start;
}
.step-num {
  flex-shrink: 0;
  width: 32px; height: 32px;
  border-radius: 50%;
  background: #0062ff; color: #fff;
  display: flex; align-items: center; justify-content: center;
  font-size: 14px; font-weight: 700;
}
.step-body {
  flex: 1;
}
.step-body h3 {
  margin: 4px 0 8px;
  font-size: 15px; font-weight: 700; color: #101010;
}
.step-desc {
  margin: 0 0 12px;
  font-size: 13px; color: #475569; line-height: 1.6;
}
.step-desc.small { font-size: 12px; color: #64748b; }
.step-desc code, .check-failed code {
  background: #F4F6FB; padding: 1px 6px; border-radius: 4px;
  font-family: ui-monospace, SFMono-Regular, monospace; font-size: 12px;
}
.btn-primary {
  display: inline-block;
  height: 38px; padding: 0 18px;
  line-height: 38px;
  background: #0062ff; color: #fff;
  border: none; border-radius: 6px;
  font-size: 13px; font-weight: 600;
  cursor: pointer;
  text-decoration: none;
}
.btn-primary:hover:not(:disabled) { background: #0052d4; }
.btn-primary:disabled { background: #94A3B8; cursor: not-allowed; }
.check-failed {
  margin: 12px 0 0;
  padding: 10px 12px;
  background: #FFF7E6; border: 1px solid #FFD591;
  border-radius: 6px;
  font-size: 12px; color: #8B5A1A; line-height: 1.5;
}
</style>
