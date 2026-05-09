/**
 * 백엔드 REST 호출용 $fetch 인스턴스.
 * runtimeConfig.public.apiBase 를 baseURL 로 주입한다.
 *
 * 사용:
 *   const { $api } = useNuxtApp();
 *   const res = await $api<MyType>('/api/agents');
 */
export default defineNuxtPlugin(() => {
  const config = useRuntimeConfig();
  const api = $fetch.create({
    baseURL: config.public.apiBase
  });
  return {
    provide: { api }
  };
});
