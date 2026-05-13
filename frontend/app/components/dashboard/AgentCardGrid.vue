<template>
  <div v-if="agents.length === 0" class="ai-grid-empty">
    표시할 AI가 없습니다.
  </div>
  <div v-else class="ai-grid">
    <AgentCard
      v-for="agent in agents"
      :key="agent.agentId"
      :agent="agent"
      @delete="emit('delete', $event)"
      @select="emit('select', $event)" />
  </div>
</template>

<script setup lang="ts">
import type { AgentItem } from '~/vo/agents/AgentVo';
import AgentCard from '~/components/dashboard/AgentCard.vue';

defineProps<{ agents: AgentItem[] }>();
const emit = defineEmits<{
  (e: 'delete', agent: AgentItem): void;
  (e: 'select', agent: AgentItem): void;
}>();
</script>

<style scoped>
.ai-grid {
  display: grid;
  /* minmax 240px — viewport 가 좁아져도 4 카드가 한 줄에 유지되어 dropdown 펼침으로 인한 reflow를 안정화 */
  grid-template-columns: repeat(auto-fill, minmax(240px, 1fr));
  gap: 16px;
}
.ai-grid-empty {
  padding: 60px 28px;
  text-align: center;
  color: #94A3B8;
  font-size: 13px;
  background: #fff;
  border: 1px dashed #D4DCE4;
  border-radius: 6px;
}
</style>
