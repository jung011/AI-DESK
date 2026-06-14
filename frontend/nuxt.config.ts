// https://nuxt.com/docs/api/configuration/nuxt-config
export default defineNuxtConfig({
  compatibilityDate: '2025-07-15',
  devtools: { enabled: true },

  // 사내 관리자 도구 — SEO 불필요, 인증 뒤에 위치하므로 SPA 모드로 운영
  ssr: false,

  modules: [
    '@pinia/nuxt'
  ],

  css: [
    '~/assets/css/reset.css',
    '~/assets/css/common.css',
    '~/assets/css/layout.css'
  ],

  app: {
    // K8s 등에서 subpath (예: /ai-desk/) 로 노출할 때 build 시점에 NUXT_APP_BASE_URL 로
    // 주입. router 와 asset 모두 그 prefix 가 박힌 채 생성된다. 기본값 '/' = root.
    baseURL: process.env.NUXT_APP_BASE_URL || '/',
    head: {
      title: 'AI 사무실',
      htmlAttrs: { lang: 'ko' },
      meta: [
        { charset: 'utf-8' },
        { name: 'viewport', content: 'width=device-width, initial-scale=1' },
        { name: 'description', content: 'Claude Code AI 에이전트 모니터링 + 협업 채널' },
        { name: 'theme-color', content: '#3B5BDB' },
        { name: 'mobile-web-app-capable', content: 'yes' },
        { name: 'apple-mobile-web-app-capable', content: 'yes' },
        { name: 'apple-mobile-web-app-status-bar-style', content: 'default' },
        { name: 'apple-mobile-web-app-title', content: 'AI Desk' }
      ],
      link: [
        // baseURL 기반 절대 경로 — subpath 배포 (예: /ai-desk/) 에선 자동으로 /ai-desk/manifest.webmanifest.
        { rel: 'manifest', href: `${process.env.NUXT_APP_BASE_URL ?? '/'}manifest.webmanifest` }
      ],
      script: [
        // runtime 환경변수 주입용 — nginx entrypoint 가 envsubst 로 치환한 결과를 서빙.
        // window.__APP_CONFIG__ 로 SPA 코드가 참조. SPA module script 보다 먼저 평가되도록
        // <head> body 안에 둔다 (defer 없음).
        { src: `${process.env.NUXT_APP_BASE_URL ?? '/'}config.js` }
      ]
    }
  },

  devServer: {
    // NodePort 대역(30000-32767) 안의 포트 사용 — 운영 환경 시뮬레이션용
    port: 30080
  },

  runtimeConfig: {
    public: {
      // 백엔드 베이스 URL — .env 의 NUXT_PUBLIC_API_BASE 로 오버라이드 가능
      apiBase: 'http://localhost:30081',
      // 데스크톱 헬퍼 (각 사용자 PC 의 localhost) — 로컬 OS 조작 (터미널/VSCode/폴더 다이얼로그).
      // 백엔드가 Docker 화돼도 이건 사용자 PC 그대로 가리킴.
      helperBase: 'http://localhost:30083',
      // 메타버스 3D 사무실 외부 BE URL — env NUXT_PUBLIC_METAVERSE_URL 로 주입.
      // 미설정 (빈 문자열) 시 헤더의 🌐 METAVERSE 버튼이 hide 됨.
      metaverseUrl: ''
    }
  }
})
