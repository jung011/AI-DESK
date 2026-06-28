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

      <!-- Windows 전용: Node.js 필수 안내 (크게 명시) -->
      <div v-if="isWindows" class="node-req">
        <div class="node-req-title">⚠️ Node.js 필수</div>
        <p>
          Windows용 helper 는 <strong>Node.js</strong> 가 설치돼 있어야 동작합니다.
          (메시지 채널 MCP·사용량 statusLine 이 <code>node</code> 로 실행됩니다.)
          먼저 <a href="https://nodejs.org/" target="_blank" rel="noopener">nodejs.org</a> 에서
          <strong>LTS 버전</strong>을 설치한 뒤 아래를 진행하세요.
        </p>
      </div>

      <ol class="steps">
        <li>
          <div class="step-num">1</div>
          <div class="step-body">
            <h3>{{ isUpdate ? '새 패키지 다운로드' : '패키지 다운로드' }}</h3>
            <p v-if="isWindows" class="step-desc">
              아래 버튼으로 본인 PC 에 Windows 설치 관리자(<code>AIDeskHelper-Setup.exe</code>)를 받습니다.
            </p>
            <p v-else class="step-desc">
              {{ isUpdate
                  ? '아래 버튼으로 본인 mac 에 최신 .pkg 를 받습니다. 설치 시 기존 plist 환경변수는 보존됩니다.'
                  : '아래 버튼으로 본인 mac 에 .pkg 를 받습니다.' }}
            </p>
            <a class="btn-primary" :href="downloadUrl" download>
              {{ downloadLabel }} 다운로드
            </a>
          </div>
        </li>
        <li>
          <div class="step-num">2</div>
          <div class="step-body">
            <h3>{{ isWindows ? '설치 관리자 실행' : '패키지 실행 + 설치' }}</h3>
            <template v-if="isWindows">
              <p class="step-desc">
                받은 <code>AIDeskHelper-Setup.exe</code> 를 <strong>더블클릭</strong>하면 설치됩니다.
                helper 가 <strong>로그인 시 자동 시작</strong>으로 등록되고, "프로그램 추가/제거" 에서 제거할 수 있습니다.
              </p>
              <p class="step-desc small">
                미서명 앱이라 <strong>Windows Defender SmartScreen</strong> 경고가 뜨면
                <strong>"추가 정보" → "실행"</strong> 을 눌러주세요.
              </p>
            </template>
            <template v-else>
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
            </template>
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
              아직 helper 응답이 없습니다. 설치가 끝났는지 확인해주세요.
              <template v-if="isWindows">
                <br />PowerShell: <code>Get-Process win-helper</code> 로 실행 여부 확인 ·
                Node.js 설치 확인 <code>node -v</code>.
              </template>
              <template v-else>
                <br />터미널: <code>launchctl list | grep com.aidesk.agent</code>
              </template>
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

/** subpath 배포 (예: /ai-desk) 일 때 NUXT_PUBLIC_API_BASE 가 박혀 있어
 *  href 도 그 prefix 를 붙여야 ingress 가 라우팅한다. root 운영 시 빈 문자열 → 그대로. */
const isWindows = ref(false);

const downloadUrl = computed(() => {
  const config = useRuntimeConfig();
  const base = (config.public.apiBase as string) || '';
  return `${base}/api/helper/download?os=${isWindows.value ? 'win' : 'mac'}`;
});

const downloadLabel = computed(() =>
  isWindows.value
    ? 'AIDeskHelper Setup (Windows .exe)'
    : (helperVersion.latestFilename || 'AIDeskHelper .pkg'),
);

/** 페이지 진입 시 store 가 비어있을 수 있어 1회 새로 조회 — 업데이트 모드 / 미설치
 *  모드 판정에 필요. */
onMounted(async () => {
  isWindows.value = typeof navigator !== 'undefined' && /windows/i.test(navigator.userAgent);
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
  background: linear-gradient(135deg, #0B0F19 0%, #0F1729 100%);
  display: flex; align-items: flex-start; justify-content: center;
  padding: 60px 20px;
}
.install-box {
  width: 640px; max-width: 100%;
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: 12px;
  box-shadow: 0 8px 24px rgba(0, 0, 0, .35);
  padding: 36px 40px;
}
.install-head h2 {
  margin: 0 0 8px;
  font-size: 22px; font-weight: 700;
  background: linear-gradient(90deg, #6BB6FF, #B89AFF);
  -webkit-background-clip: text;
  background-clip: text;
  -webkit-text-fill-color: transparent;
}
.install-head .sub {
  margin: 0 0 28px;
  font-size: 13px; color: #94A3B8;
}
.install-head .sub strong { color: var(--text); }
.node-req {
  margin: 0 0 24px;
  padding: 16px 18px;
  background: rgba(248, 113, 113, 0.12);
  border: 1.5px solid rgba(248, 113, 113, 0.5);
  border-radius: 8px;
}
.node-req-title {
  font-size: 15px; font-weight: 800; color: #FCA5A5; margin-bottom: 6px;
}
.node-req p { margin: 0; font-size: 13px; color: #FCA5A5; line-height: 1.6; }
.node-req p strong { color: #FECACA; }
.node-req a { color: #FCA5A5; font-weight: 700; }
.node-req code {
  background: rgba(248, 113, 113, 0.18); padding: 1px 5px; border-radius: 3px;
  font-family: ui-monospace, SFMono-Regular, monospace; color: #FECACA;
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
  background: linear-gradient(135deg, #6BB6FF, #B89AFF); color: #fff;
  display: flex; align-items: center; justify-content: center;
  font-size: 14px; font-weight: 700;
  box-shadow: 0 2px 8px rgba(107, 182, 255, 0.35);
}
.step-body {
  flex: 1;
}
.step-body h3 {
  margin: 4px 0 8px;
  font-size: 15px; font-weight: 700; color: var(--text);
}
.step-desc {
  margin: 0 0 12px;
  font-size: 13px; color: #B0BCD0; line-height: 1.6;
}
.step-desc strong { color: var(--text); }
.step-desc.small { font-size: 12px; color: #94A3B8; }
.step-desc code, .check-failed code {
  background: var(--bg-input); padding: 1px 6px; border-radius: 4px;
  font-family: ui-monospace, SFMono-Regular, monospace; font-size: 12px; color: #93C5FD;
}
.btn-primary {
  display: inline-block;
  height: 38px; padding: 0 18px;
  line-height: 38px;
  background: linear-gradient(135deg, #6BB6FF, #B89AFF); color: #fff;
  border: none; border-radius: 6px;
  font-size: 13px; font-weight: 600;
  cursor: pointer;
  text-decoration: none;
  box-shadow: 0 2px 8px rgba(107, 182, 255, 0.35);
  transition: transform .15s, box-shadow .15s;
}
.btn-primary:hover:not(:disabled) {
  transform: translateY(-1px);
  box-shadow: 0 4px 12px rgba(107, 182, 255, 0.5);
}
.btn-primary:disabled { background: #475569; cursor: not-allowed; box-shadow: none; }
.check-failed {
  margin: 12px 0 0;
  padding: 10px 12px;
  background: rgba(251, 191, 36, 0.12); border: 1px solid rgba(251, 191, 36, 0.4);
  border-radius: 6px;
  font-size: 12px; color: #FCD34D; line-height: 1.5;
}
</style>
