<template>
  <div class="cleanup-page">
    <header class="cleanup-header">
      <h1>리소스 정리</h1>
      <p class="subtitle">옛 mcp daemon 잔재 cleanup + 시스템 누적 모니터링</p>
    </header>

    <div class="cleanup-body">
      <!-- 시스템 상태 카드 -->
      <section class="card">
        <div class="card-head">
          <h2>시스템 상태</h2>
          <button class="btn-ghost" :disabled="loading" @click="refreshStatus">
            새로고침
          </button>
        </div>
        <div v-if="status" class="status-grid">
          <div class="status-row">
            <span class="label">macOS uptime</span>
            <span class="value" :class="{ warn: (status.uptimeDays ?? 0) > 14 }">
              {{ formatUptime(status.uptimeDays) }}
            </span>
          </div>
          <div class="status-row">
            <span class="label">옛 mcp daemon 갯수</span>
            <span class="value" :class="{ warn: status.staleDaemonCount >= 3 }">
              {{ status.staleDaemonCount }} 개
            </span>
          </div>
          <div class="status-row">
            <span class="label">mac restart 권고</span>
            <span class="value" :class="{ warn: status.restartRecommended }">
              {{ status.restartRecommended ? '⚠️ 권장 (kernel state 누적)' : '불필요' }}
            </span>
          </div>
        </div>
        <div v-else-if="statusError" class="error">
          helper 응답 실패 — {{ statusError }}
        </div>
        <div v-else class="muted">불러오는 중…</div>

        <details v-if="status?.staleDaemons?.length" class="detail">
          <summary>daemon 목록 ({{ status.staleDaemons.length }})</summary>
          <ul class="daemon-list">
            <li v-for="d in status.staleDaemons" :key="d.pid">
              <code>{{ d.pid }}</code> · {{ d.etime }}
              <span class="cmd">{{ d.command }}</span>
            </li>
          </ul>
        </details>
      </section>

      <!-- 시간 추이 차트 — 최근 24h uptime% / daemon% line chart -->
      <ResourceHistoryChart />

      <!-- 정리 액션 카드 -->
      <section class="card">
        <div class="card-head">
          <h2>정리 액션</h2>
        </div>
        <div class="action-row">
          <label class="check">
            <input v-model="flushDns" type="checkbox" />
            <span>DNS cache 도 flush (sudo 권한 필요)</span>
          </label>
        </div>
        <div class="action-row">
          <button class="btn-primary" :disabled="loading" @click="onCleanup">
            {{ loading ? '정리 중…' : '리소스 정리 실행' }}
          </button>
        </div>
        <p class="hint">
          ⚠️ 현재 작업 중인 claude code 의 자식 mcp daemon 도 같이 종료될 수 있어.
          정상 path 에선 claude code 가 자동 재spawn 해. 작업 중이면 끝낸 후 실행 권장.
        </p>

        <!-- 결과 표시 -->
        <div v-if="result" class="result">
          <h3>실행 결과</h3>
          <div class="result-row">
            <span class="label">kill 된 daemon</span>
            <span class="value">{{ result.kill.killedPids.length }} 개</span>
          </div>
          <div v-if="result.kill.killedPids.length" class="result-row">
            <span class="label">pid 목록</span>
            <span class="value code">{{ result.kill.killedPids.join(', ') }}</span>
          </div>
          <div v-if="result.kill.failed.length" class="result-row warn">
            <span class="label">실패</span>
            <span class="value">{{ result.kill.failed.length }} 개 (권한 부족 등)</span>
          </div>
          <div v-if="result.dns" class="result-row">
            <span class="label">DNS flush</span>
            <span class="value" :class="{ warn: !result.dns.ok }">
              {{ result.dns.ok ? '성공' : '실패 (sudo 권한 없음 가능)' }}
            </span>
          </div>
        </div>
      </section>

      <!-- 한계 안내 -->
      <section class="card info">
        <h2>알아두기 — 한계</h2>
        <ul class="limits">
          <li>이 정리는 <b>process 잔재</b> + 옵션 DNS cache 만 reset 함.</li>
          <li>
            <b>kernel state 누적</b> (pf table / NAT / TIME_WAIT socket) 은 어떤
            cleanup 으로도 해소 X — <b>mac restart 만 답</b>.
          </li>
          <li>uptime 14일 초과 + agent 다수 호스팅이면 주기 restart 권장.</li>
          <li>장기적으로 agent 수가 더 늘면 별도 호스팅 mac 분리가 근본 fix.</li>
        </ul>
      </section>
    </div>
  </div>
</template>

<script setup lang="ts">
import ResourceHistoryChart from '~/components/dashboard/ResourceHistoryChart.vue';
interface SystemStatus {
  uptimeSeconds: number | null;
  uptimeDays: number | null;
  staleDaemonCount: number;
  staleDaemons: Array<{ pid: number; etime: string; command: string }>;
  restartRecommended: boolean;
}

interface CleanupResult {
  kill: {
    killedPids: number[];
    failed: Array<{ pid: number; reason: string }>;
    totalFound: number;
  };
  dns: { ok: boolean; results: Array<{ cmd: string; ok: boolean; stderr: string }> } | null;
  status: SystemStatus;
}

const { $helper } = useNuxtApp();

const status = ref<SystemStatus | null>(null);
const statusError = ref<string>('');
const result = ref<CleanupResult | null>(null);
const loading = ref(false);
const flushDns = ref(false);

async function refreshStatus(): Promise<void> {
  statusError.value = '';
  try {
    status.value = await $helper<SystemStatus>('/api/system/status');
  } catch (e: unknown) {
    statusError.value = e instanceof Error ? e.message : String(e);
  }
}

async function onCleanup(): Promise<void> {
  if (loading.value) return;
  if (!confirm('옛 mcp daemon 을 kill 합니다. 현재 작업 중인 claude code 의 자식도 포함될 수 있어요. 진행할까요?')) {
    return;
  }
  loading.value = true;
  try {
    result.value = await $helper<CleanupResult>('/api/cleanup', {
      method: 'POST',
      body: { flushDns: flushDns.value },
    });
    status.value = result.value.status;
  } catch (e: unknown) {
    statusError.value = e instanceof Error ? e.message : String(e);
  } finally {
    loading.value = false;
  }
}

function formatUptime(days: number | null | undefined): string {
  if (days == null) return '확인 불가';
  if (days < 1) return `${Math.round(days * 24)} 시간`;
  return `${days.toFixed(1)} 일`;
}

onMounted(refreshStatus);
</script>

<style scoped>
.cleanup-page {
  padding: 24px 28px;
  max-width: 880px;
  margin: 0 auto;
  color: #E5E9EE;
}
.cleanup-header { margin-bottom: 18px; }
.cleanup-header h1 {
  font-size: 22px; font-weight: 700; margin: 0 0 4px;
  background: linear-gradient(90deg, #6BB6FF, #B89AFF);
  -webkit-background-clip: text; background-clip: text;
  -webkit-text-fill-color: transparent;
}
.subtitle { font-size: 13px; color: #6B7785; margin: 0; }

.cleanup-body { display: flex; flex-direction: column; gap: 16px; }

.card {
  background: rgba(15, 23, 41, 0.6);
  border: 1px solid #1E2738;
  border-radius: 12px;
  padding: 18px 20px;
}
.card.info { background: rgba(20, 30, 50, 0.4); }
.card-head {
  display: flex; align-items: center; justify-content: space-between;
  margin-bottom: 12px;
}
.card h2 { font-size: 14px; font-weight: 600; margin: 0; color: #B7C2D0; }

.status-grid { display: flex; flex-direction: column; gap: 8px; }
.status-row {
  display: flex; justify-content: space-between; align-items: center;
  padding: 8px 0;
  border-bottom: 1px dashed #1E2738;
}
.status-row:last-child { border-bottom: none; }
.label { font-size: 13px; color: #6B7785; }
.value { font-size: 13px; color: #E5E9EE; font-weight: 500; }
.value.warn { color: #FFB454; }

.action-row { margin-bottom: 10px; }
.check { display: flex; align-items: center; gap: 8px; font-size: 13px; color: #B7C2D0; cursor: pointer; }

.btn-primary {
  background: linear-gradient(90deg, #6BB6FF, #B89AFF);
  color: #0B0F19;
  border: none;
  border-radius: 8px;
  padding: 10px 18px;
  font-size: 14px; font-weight: 600;
  cursor: pointer;
  transition: opacity .15s, transform .1s;
}
.btn-primary:hover:not(:disabled) { transform: translateY(-1px); }
.btn-primary:disabled { opacity: 0.5; cursor: not-allowed; }

.btn-ghost {
  background: transparent;
  border: 1px solid #334155;
  color: #94A3B8;
  border-radius: 6px;
  padding: 5px 12px;
  font-size: 12px;
  cursor: pointer;
}
.btn-ghost:hover:not(:disabled) { background: #1E2738; color: #E5E9EE; }

.hint {
  font-size: 12px; color: #6B7785;
  margin: 8px 0 0;
  padding: 8px 10px;
  background: rgba(255, 180, 84, 0.06);
  border-left: 2px solid #FFB454;
  border-radius: 4px;
}

.result {
  margin-top: 14px; padding-top: 12px;
  border-top: 1px dashed #1E2738;
}
.result h3 { font-size: 13px; color: #94A3B8; margin: 0 0 8px; font-weight: 600; }
.result-row {
  display: flex; justify-content: space-between; align-items: center;
  padding: 4px 0;
}
.result-row.warn .value { color: #FFB454; }
.value.code { font-family: ui-monospace, monospace; font-size: 12px; }

.detail { margin-top: 12px; font-size: 12px; }
.detail summary { cursor: pointer; color: #94A3B8; padding: 4px 0; }
.daemon-list { list-style: none; padding: 0; margin: 6px 0 0; max-height: 160px; overflow-y: auto; }
.daemon-list li {
  padding: 6px 8px;
  border-bottom: 1px dashed #1E2738;
  font-size: 12px;
  display: flex; gap: 8px; align-items: center;
}
.daemon-list code {
  font-family: ui-monospace, monospace;
  background: #1E2738; padding: 2px 6px; border-radius: 4px;
  color: #6BB6FF;
}
.daemon-list .cmd { color: #6B7785; font-family: ui-monospace, monospace; flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }

.error { color: #FF6B6B; font-size: 13px; }
.muted { color: #6B7785; font-size: 13px; }

.limits {
  margin: 8px 0 0;
  padding-left: 20px;
  font-size: 13px;
  color: #B7C2D0;
  line-height: 1.7;
}
.limits b { color: #E5E9EE; }
</style>
