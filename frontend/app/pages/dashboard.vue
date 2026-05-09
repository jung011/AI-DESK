<template>
  <div class="page_content">
    <!-- 페이지 헤더 -->
    <div class="group_pageLocation">
      <h2 class="tit_h2">대시보드</h2>
      <div class="descList_pageLocation">
        <a href="#">HOME</a>
        <a href="#"><em>대시보드</em></a>
      </div>
      <div style="margin-left: auto;">
        <button type="button" class="btn normal type_v1" disabled title="Phase 2 후속 단계">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor" style="margin-right:6px"><path d="M19 13h-6v6h-2v-6H5v-2h6V5h2v6h6v2z" /></svg>
          AI 생성
        </button>
      </div>
    </div>

    <!-- 요약 카드 -->
    <SummaryCardGrid :summary="summary" />

    <!-- 필터 탭 + 이름 검색 -->
    <FilterBar
      :status="status"
      :query="query"
      @update:status="status = $event"
      @update:query="query = $event" />

    <div v-if="error" class="error-box">
      백엔드 호출 실패: {{ error }}
    </div>

    <!-- AI 카드 그리드 -->
    <AgentCardGrid :agents="filteredList" />
  </div>
</template>

<script setup lang="ts">
import { useAgents } from '~/composables/useAgents';
import SummaryCardGrid from '~/components/dashboard/SummaryCardGrid.vue';
import FilterBar from '~/components/dashboard/FilterBar.vue';
import AgentCardGrid from '~/components/dashboard/AgentCardGrid.vue';

const {
  summary,
  status,
  query,
  filteredList,
  error,
  startPolling,
  stopPolling
} = useAgents();

onMounted(() => startPolling(10_000));
onUnmounted(() => stopPolling());
</script>

<style scoped>
.page_content {
  padding: 28px;
  max-width: 1400px;
  margin: 0 auto;
}
.group_pageLocation {
  display: flex;
  align-items: center;
  gap: 16px;
  margin-bottom: 20px;
}
.tit_h2 {
  font-size: 20px;
  font-weight: 700;
  color: #101010;
  margin: 0;
}
.descList_pageLocation {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  color: #94A3B8;
}
.descList_pageLocation a {
  color: #94A3B8;
  text-decoration: none;
}
.descList_pageLocation a + a::before {
  content: '›';
  margin-right: 6px;
  color: #CBD5E1;
}
.descList_pageLocation em {
  font-style: normal;
  color: #475569;
  font-weight: 600;
}
.btn.normal {
  display: inline-flex;
  align-items: center;
  height: 34px;
  padding: 0 14px;
  border-radius: 6px;
  font-size: 13px;
  font-weight: 600;
  border: 1px solid transparent;
  cursor: pointer;
}
.btn.normal.type_v1 {
  background: #0062ff;
  color: #fff;
}
.btn.normal.type_v1:hover { background: #0052d4; }
.btn.normal.type_v1:disabled { background: #94A3B8; cursor: not-allowed; }

.error-box {
  margin-bottom: 20px;
  padding: 12px 16px;
  border-radius: 6px;
  background: #FFE5E9;
  border: 1px solid #FFB4BD;
  color: #B22B45;
  font-size: 13px;
}
</style>
