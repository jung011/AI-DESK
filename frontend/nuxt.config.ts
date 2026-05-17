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
        { rel: 'manifest', href: '/manifest.webmanifest' }
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
      helperBase: 'http://localhost:30083'
    }
  }
})
