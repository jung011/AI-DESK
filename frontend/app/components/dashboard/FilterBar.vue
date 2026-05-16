<template>
  <div class="filter-bar">
    <div class="filter-tabs">
      <button
        v-for="tab in tabs"
        :key="tab.value"
        type="button"
        class="filter-tab"
        :class="{ active: status === tab.value }"
        @click="emit('update:status', tab.value)">
        {{ tab.label }}
      </button>
    </div>

    <div class="filter-right">
      <div class="search-input-wrap">
        <svg class="search-icon" viewBox="0 0 24 24" fill="currentColor">
          <path d="M15.5 14h-.79l-.28-.27A6.471 6.471 0 0 0 16 9.5 6.5 6.5 0 1 0 9.5 16c1.61 0 3.09-.59 4.23-1.57l.27.28v.79l5 4.99L20.49 19l-4.99-5zm-6 0C7.01 14 5 11.99 5 9.5S7.01 5 9.5 5 14 7.01 14 9.5 11.99 14 9.5 14z"/>
        </svg>
        <input
          type="text"
          placeholder="AI 이름 검색..."
          :value="query"
          @input="emit('update:query', ($event.target as HTMLInputElement).value)" />
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
defineProps<{
  status: string;
  query: string;
}>();

const emit = defineEmits<{
  (e: 'update:status', v: string): void;
  (e: 'update:query',  v: string): void;
}>();

const tabs = [
  { label: '전체',      value: 'all' },
  { label: '작업중',    value: 'active' },
  { label: '응답 대기', value: 'waiting' },
  { label: '쉬는 중',   value: 'idle' },
  { label: '완료',      value: 'done' },
  { label: '오류',      value: 'error' }
] as const;
</script>

<style scoped>
.filter-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 16px;
  gap: 16px;
}
.filter-tabs { display: flex; gap: 4px; }
.filter-tab {
  height: 34px; padding: 0 14px; border-radius: 20px;
  font-size: 13px; font-weight: 500; color: #666;
  border: 1px solid transparent; background: transparent;
  cursor: pointer; transition: background .12s, color .12s;
}
.filter-tab:hover { background: #F1F5F9; }
.filter-tab.active {
  background: #0062ff; color: #fff; border-color: #0062ff;
}

.filter-right { display: flex; align-items: center; gap: 8px; }
.search-input-wrap { position: relative; }
.search-input-wrap input[type="text"] {
  height: 34px; width: 200px;
  padding: 0 12px 0 34px;
  border: 1px solid #D4DCE4; border-radius: 6px;
  font-size: 13px; color: #333; background: #fff;
}
.search-input-wrap input[type="text"]:focus {
  outline: none; border-color: #0062ff;
}
.search-icon {
  position: absolute; left: 10px; top: 50%; transform: translateY(-50%);
  width: 15px; height: 15px; color: #999;
}
</style>
