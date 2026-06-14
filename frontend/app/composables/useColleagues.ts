import { ref } from 'vue';
import type { ApiEnvelope } from '~/vo/agents/AgentVo';
import type { ColleagueItem, ColleagueListRs } from '~/vo/colleagues/ColleagueVo';

/**
 * 사내 동료 디렉토리 — /api/colleagues 폴링.
 * 같은 backend 의 다른 user 의 (me) AI 만 반환. 케플릭스 control-plane 의존 없음.
 */
export const useColleagues = () => {
  const { $api } = useNuxtApp();
  const list = ref<ColleagueItem[]>([]);
  const loading = ref(false);

  async function refresh(): Promise<void> {
    loading.value = true;
    try {
      const env = await $api<ApiEnvelope<ColleagueListRs>>('/api/colleagues');
      if (env.result === 0) {
        list.value = env.data?.list || [];
      }
    } catch {
      // 인증 만료 / 일시 오류 — 다음 poll 에서 재시도
    } finally {
      loading.value = false;
    }
  }

  return { list, loading, refresh };
};
