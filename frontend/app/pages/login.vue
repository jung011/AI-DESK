<template>
  <div class="login-shell">
  <div class="login-card">
    <div class="login-brand">
      <div class="login-logo">
        <svg viewBox="0 0 24 24"><path d="M12 2C6.48 2 2 6.48 2 12c0 4.41 2.86 8.16 6.84 9.5.5.08.66-.23.66-.5v-1.69c-2.77.6-3.36-1.34-3.36-1.34-.46-1.16-1.11-1.47-1.11-1.47-.91-.62.07-.6.07-.6 1 .07 1.53 1.03 1.53 1.03.87 1.52 2.34 1.07 2.91.83.09-.65.35-1.09.63-1.34-2.22-.25-4.55-1.11-4.55-4.94 0-1.11.38-2 1.03-2.71-.1-.25-.45-1.29.1-2.64 0 0 .84-.27 2.75 1.02.79-.22 1.65-.33 2.5-.33s1.71.11 2.5.33c1.91-1.29 2.75-1.02 2.75-1.02.55 1.35.2 2.39.1 2.64.65.71 1.03 1.6 1.03 2.71 0 3.84-2.34 4.68-4.57 4.93.36.31.69.92.69 1.85V21c0 .27.16.59.67.5C19.14 20.16 22 16.42 22 12c0-5.52-4.48-10-10-10z"/></svg>
      </div>
      <h1 class="login-title">AI 사무실</h1>
      <div class="login-subtitle">로그인하고 본인 작업 공간에 진입하세요</div>
    </div>

    <form class="login-form" @submit.prevent="onSubmit">
      <div class="form_field">
        <label class="form_label" for="login-email">이메일</label>
        <input
          v-model.trim="loginId"
          type="email"
          id="login-email"
          class="form_input"
          placeholder="name@kaflix.com"
          autocomplete="username"
          required
          :disabled="submitting"
          @input="errorMsg = ''">
      </div>

      <div class="form_field">
        <label class="form_label" for="login-password">비밀번호</label>
        <div class="input_with_toggle">
          <input
            v-model="password"
            :type="showPassword ? 'text' : 'password'"
            id="login-password"
            class="form_input"
            placeholder="비밀번호 입력"
            autocomplete="current-password"
            required
            :disabled="submitting"
            @input="errorMsg = ''">
          <button
            type="button"
            class="btn_pw_toggle"
            :class="{ 'is-shown': showPassword }"
            :aria-label="showPassword ? '비밀번호 숨기기' : '비밀번호 표시'"
            :aria-pressed="showPassword"
            :title="showPassword ? '비밀번호 숨기기' : '비밀번호 표시'"
            @click="togglePassword">
            <!-- 보이는 상태: 눈 가림 / 가려진 상태: 눈 -->
            <svg v-if="showPassword" viewBox="0 0 24 24" fill="currentColor"><path d="M12 7c2.76 0 5 2.24 5 5 0 .65-.13 1.26-.36 1.83l2.92 2.92c1.51-1.26 2.7-2.89 3.43-4.75-1.73-4.39-6-7.5-11-7.5-1.4 0-2.74.25-3.98.7l2.16 2.16C10.74 7.13 11.35 7 12 7zM2 4.27l2.28 2.28.46.46C3.08 8.3 1.78 10.02 1 12c1.73 4.39 6 7.5 11 7.5 1.55 0 3.03-.3 4.38-.84l.42.42L19.73 22 21 20.73 3.27 3 2 4.27zM7.53 9.8l1.55 1.55c-.05.21-.08.43-.08.65 0 1.66 1.34 3 3 3 .22 0 .44-.03.65-.08l1.55 1.55c-.67.33-1.41.53-2.2.53-2.76 0-5-2.24-5-5 0-.79.2-1.53.53-2.2zm4.31-.78l3.15 3.15.02-.16c0-1.66-1.34-3-3-3l-.17.01z"/></svg>
            <svg v-else viewBox="0 0 24 24" fill="currentColor"><path d="M12 5c-7 0-10 7-10 7s3 7 10 7 10-7 10-7-3-7-10-7zm0 12c-2.76 0-5-2.24-5-5s2.24-5 5-5 5 2.24 5 5-2.24 5-5 5zm0-8c-1.66 0-3 1.34-3 3s1.34 3 3 3 3-1.34 3-3-1.34-3-3-3z"/></svg>
          </button>
        </div>
      </div>

      <div class="login-error" role="alert">{{ errorMsg }}</div>

      <div class="login-actions">
        <button
          type="submit"
          class="btn normal type_v1"
          :disabled="submitting || !loginId || !password">
          {{ submitting ? '로그인 중…' : '로그인' }}
        </button>
      </div>
    </form>

    <div class="login-foot">
      회원가입은 <strong>관리자</strong>에게 문의하세요.<br>
      (회원가입 페이지는 제공하지 않음 — API <code>POST /api/auth/signup</code> 만 있음)
    </div>
  </div>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue';
import { useAuth } from '~/composables/useAuth';

// /login 은 헤더/사이드메뉴 없는 단독 풀스크린 — 기본 layout 끔.
definePageMeta({ layout: false });

const loginId = ref('');
const password = ref('');
const showPassword = ref(false);
const submitting = ref(false);
const errorMsg = ref('');

const route = useRoute();
const router = useRouter();
const { signIn } = useAuth();

const togglePassword = () => {
  showPassword.value = !showPassword.value;
};

const onSubmit = async () => {
  if (submitting.value) return;
  if (!loginId.value || !password.value) return;
  submitting.value = true;
  errorMsg.value = '';
  try {
    await signIn({ loginId: loginId.value, password: password.value });
    // 로그인 성공 직후 redirect — 절대 URL (http/https) 이고 whitelist 통과면 *외부 browser navigation*.
    // 미들웨어의 resolveRedirect 와 동일 정책 (auth.global.ts) — `isExternalRedirectAllowed` 공유.
    // Whitelist 는 runtime config (ConfigMap env) — 코드에 도메인 hardcode X.
    const raw = (route.query.redirect as string) || '/dashboard';
    const isAbsolute = /^https?:\/\//i.test(raw);
    if (isAbsolute) {
      try {
        const url = new URL(raw);
        if (isExternalRedirectAllowed(url.hostname)) {
          window.location.href = raw;
          return;
        }
      } catch { /* malformed URL — fallback */ }
      await router.replace('/dashboard');
    } else {
      await router.replace(raw);
    }
  } catch (e) {
    errorMsg.value = e instanceof Error
      ? e.message
      : '이메일 또는 비밀번호가 올바르지 않습니다.';
  } finally {
    submitting.value = false;
  }
};
</script>

<style scoped>
/* 로그인 화면은 헤더/사이드메뉴 없는 단독 풀스크린.
   layout: false 라 외부 레이아웃 padding 영향 없음. */
.login-shell {
  min-height: 100vh;
  display: grid;
  place-items: center;
  background: linear-gradient(135deg, #f0f2f8 0%, #F4F6FB 100%);
  padding: 24px;
}

.login-card {
  width: 380px;
  max-width: 100%;
  background: #fff;
  border: 1px solid #D4DCE4;
  border-radius: 10px;
  padding: 40px 36px 32px;
  box-shadow: 0 10px 30px 0 rgba(67, 87, 103, .12);
}

/* 브랜드 */
.login-brand { text-align: center; margin-bottom: 28px; }
.login-logo {
  width: 56px; height: 56px;
  background: #0062ff; border-radius: 12px;
  display: inline-flex; align-items: center; justify-content: center;
  margin-bottom: 14px;
}
.login-logo svg { width: 32px; height: 32px; fill: #fff; }
.login-title { font-size: 20px; font-weight: 700; color: #101010; letter-spacing: -.02em; margin: 0 0 4px; }
.login-subtitle { font-size: 12px; color: #999; letter-spacing: .02em; }

/* 폼 */
.login-form { display: flex; flex-direction: column; gap: 14px; }
.form_field { display: flex; flex-direction: column; gap: 6px; }
.form_label { font-size: 12px; font-weight: 600; color: #444; }
.form_input {
  height: 40px; padding: 0 12px;
  border: 1px solid #D4DCE4; border-radius: 6px;
  font-size: 13px; color: #222; background: #fff;
  outline: none; transition: border-color .15s;
  width: 100%; box-sizing: border-box;
  /* 외부 reset.css 의 input[type=email/password] 가 color 미정의지만, 일부 브라우저 매니저가
     ‘유출 비밀번호 경고’ 색을 덮어쓰는 케이스가 있어서 명시. */
  -webkit-text-fill-color: #222;
}
.form_input:focus { border-color: #0062ff; }
.form_input::placeholder { color: #BCC4D0; }
.form_input:disabled { background: #F4F6FB; color: #999; -webkit-text-fill-color: #999; }

/* common.css 의 글로벌 룰 `input:invalid { border-color/color: #E83667 !important; }` 가
   :invalid 상태(빈 값 + required, 잘못된 email 형식 등)에서 input 을 빨갛게 만든다. 로그인
   화면은 .login-error 의 단일 한국어 문구로만 에러를 표시하므로 :invalid 빨강은 끄고
   디자인 시스템의 기본 회색 / 포커스 파란색을 유지한다. */
.form_input:invalid,
.form_input:required:invalid,
input.form_input:invalid {
  border-color: #D4DCE4 !important;
  color: #222 !important;
  -webkit-text-fill-color: #222 !important;
  box-shadow: none !important;
  outline: none !important;
}
.form_input:focus:invalid,
input.form_input:focus:invalid {
  border-color: #0062ff !important;
}

/* Chrome / Safari autofill 노란 박스 + 텍스트 색 덮어쓰기 강제 회피.
   autofill 적용 시 -webkit-text-fill-color 를 우리 색으로, box-shadow 로 흰 배경 강제. */
.form_input:-webkit-autofill,
.form_input:-webkit-autofill:hover,
.form_input:-webkit-autofill:focus,
.form_input:-webkit-autofill:active {
  -webkit-text-fill-color: #222 !important;
  -webkit-box-shadow: 0 0 0 1000px #fff inset !important;
  caret-color: #222;
  transition: background-color 5000s ease-in-out 0s;
}

/* 비밀번호 토글 */
.input_with_toggle { position: relative; }
.input_with_toggle .form_input { padding-right: 40px; }
.btn_pw_toggle {
  position: absolute; top: 50%; right: 8px;
  transform: translateY(-50%);
  width: 28px; height: 28px;
  display: inline-flex; align-items: center; justify-content: center;
  background: transparent; border: none; cursor: pointer;
  color: #AAB4BE; border-radius: 4px;
  transition: color .15s, background .15s;
}
.btn_pw_toggle:hover { color: #444; background: #F4F6FB; }
.btn_pw_toggle:focus { outline: 2px solid #0062ff33; outline-offset: 1px; }
.btn_pw_toggle svg { width: 18px; height: 18px; }
.btn_pw_toggle.is-shown { color: #0062ff; }

/* 에러 */
.login-error {
  min-height: 16px;
  font-size: 12px; color: #E83667;
  padding-left: 2px; line-height: 1.4;
}

/* 로그인 버튼 */
.login-actions { margin-top: 8px; }
.login-actions .btn { width: 100%; height: 44px; font-size: 14px; }

/* 푸터 */
.login-foot {
  margin-top: 24px; padding-top: 18px;
  border-top: 1px solid #EEF0F4;
  font-size: 11px; color: #AAB4BE; text-align: center; line-height: 1.6;
}
.login-foot strong { color: #666; font-weight: 600; }
.login-foot code {
  background: #F4F6FB; padding: 1px 4px; border-radius: 3px;
  font-family: monospace; color: #666;
}
</style>
