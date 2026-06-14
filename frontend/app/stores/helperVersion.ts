import { defineStore } from 'pinia';

import type { ApiEnvelope } from '~/vo/agents/AgentVo';

interface HelperHealthRs { status?: string; version?: string }
interface HelperLatestRs { latest: string; filename: string }

/**
 * 본 PC 의 helper 버전(running) 과 backend 가 보유한 baked .pkg 버전(latest) 을 비교.
 * needsUpdate 일 때 default layout 의 배너가 사용자에게 업데이트 안내.
 *
 * - missing 은 helper 자체가 안 잡혔다는 신호로 auth.global.ts 가 /helper-install 로 redirect.
 * - default layout 이 5분마다 refresh() 폴링.
 */
export const useHelperVersionStore = defineStore('helperVersion', {
  state: () => ({
    running: '' as string,
    latest: '' as string,
    latestFilename: '' as string,
    missing: false as boolean,
    checkedAt: 0 as number,
  }),
  getters: {
    needsUpdate(): boolean {
      // running / latest 둘 다 있어야 비교 의미. missing 이면 별도 흐름이라 banner 안 띄움.
      if (this.missing) return false;
      if (!this.running || !this.latest) return false;
      return this.running !== this.latest;
    },
  },
  actions: {
    async refresh(): Promise<void> {
      const config = useRuntimeConfig();
      const helperBase = (config.public.helperBase as string) || 'http://localhost:30083';

      // 1) 본 PC 의 helper 가 살아있는지 + 버전
      let running = '';
      let missing = false;
      try {
        const ctrl = new AbortController();
        const t = setTimeout(() => ctrl.abort(), 2000);
        const res = await fetch(`${helperBase}/api/health`, { signal: ctrl.signal });
        clearTimeout(t);
        if (res.ok) {
          const body = (await res.json()) as HelperHealthRs;
          running = body.version || '';
        } else {
          missing = true;
        }
      } catch {
        missing = true;
      }

      // 2) backend 가 보유한 baked .pkg 버전
      let latest = '';
      let latestFilename = '';
      try {
        const { $api } = useNuxtApp();
        const env = await $api<ApiEnvelope<HelperLatestRs>>('/api/helper/version');
        if (env.result === 0 && env.data) {
          latest = env.data.latest || '';
          latestFilename = env.data.filename || '';
        }
      } catch {
        // backend 미도달 — version 비교 안 함
      }

      this.running = running;
      this.latest = latest;
      this.latestFilename = latestFilename;
      this.missing = missing;
      this.checkedAt = Date.now();
    },
  },
});
