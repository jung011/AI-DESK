// https://nuxt.com/docs/api/configuration/nuxt-config
export default defineNuxtConfig({
  compatibilityDate: '2025-07-15',
  devtools: { enabled: true },

  // 사내 관리자 도구 — SEO 불필요, 인증 뒤에 위치하므로 SPA 모드로 운영
  ssr: false,

  app: {
    head: {
      title: 'AI 사무실',
      htmlAttrs: { lang: 'ko' },
      meta: [
        { charset: 'utf-8' },
        { name: 'viewport', content: 'width=device-width, initial-scale=1' },
        { name: 'description', content: 'Claude Code AI 에이전트 모니터링 + 협업 채널' }
      ]
    }
  },

  devServer: {
    port: 3000
  },

  runtimeConfig: {
    public: {
      // 백엔드 베이스 URL — .env 의 NUXT_PUBLIC_API_BASE 로 오버라이드 가능
      // 8080은 다른 프로세스 점유 가능성이 있어 기본 8081 사용
      apiBase: 'http://localhost:8081'
    }
  }
})
