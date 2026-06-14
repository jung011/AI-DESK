/**
 * 데스크톱 헬퍼 (각 사용자 PC 의 localhost:30083) 호출용 $fetch 인스턴스.
 *
 * 백엔드(`$api`) 는 메시지/에이전트 등 데이터 관리, 헬퍼(`$helper`) 는 본인 Mac 의
 * 로컬 OS 조작 (Terminal/VSCode/폴더 다이얼로그/임베드 PTY) 을 담당한다.
 *
 * 사용:
 *   const { $helper } = useNuxtApp();
 *   await $helper('/api/open-terminal', { method: 'POST', body: { workspaceDir, tmuxSession } });
 */
export default defineNuxtPlugin(() => {
  const config = useRuntimeConfig();
  const helper = $fetch.create({
    baseURL: config.public.helperBase as string,
  });
  return {
    provide: { helper },
  };
});
