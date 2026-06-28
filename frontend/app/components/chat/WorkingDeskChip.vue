<template>
  <span
    class="wd-chip"
    tabindex="0"
    :title="`${agentName} 가 책상에서 작업중 — 호버하면 자세히 보기`"
  >
    <span class="wd-mini">
      <span class="wd-monitor"><span class="wd-cursor"></span></span>
      <span class="wd-desk"></span>
      <span class="wd-head"></span>
    </span>
    <span class="wd-label">{{ agentName }} 가 책상에서 작업중</span>
  </span>
</template>

<script setup lang="ts">
defineProps<{ agentName: string }>();
</script>

<style scoped>
.wd-chip {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  padding: 4px 12px;
  background: rgba(107, 182, 255, 0.12);
  border: 1px solid rgba(107, 182, 255, 0.25);
  border-radius: 14px;
  cursor: default;
  font-size: 11px;
  color: #6BB6FF;
  transition: background .15s, border-color .15s;
  font-family: inherit;
  outline: none;
}
.wd-chip:hover,
.wd-chip:focus {
  background: rgba(107, 182, 255, 0.2);
  border-color: rgba(107, 182, 255, 0.5);
}
.wd-mini {
  position: relative;
  width: 18px;
  height: 14px;
  flex-shrink: 0;
}
.wd-monitor {
  position: absolute;
  top: 0;
  left: 1px;
  width: 11px;
  height: 8px;
  background: #050810;
  border: 1px solid #6BB6FF;
  border-radius: 1px;
}
.wd-cursor {
  position: absolute;
  top: 2px;
  left: 2px;
  width: 3px;
  height: 1.5px;
  background: #22C55E;
  animation: wd-blink 0.7s steps(2) infinite;
}
@keyframes wd-blink {
  0%, 50% { opacity: 1; }
  51%, 100% { opacity: 0; }
}
.wd-desk {
  position: absolute;
  bottom: 0;
  left: 0;
  width: 18px;
  height: 1.5px;
  background: #6BB6FF;
  border-radius: 1px;
}
.wd-head {
  position: absolute;
  bottom: 1.5px;
  right: 0;
  width: 4px;
  height: 4px;
  background: linear-gradient(135deg, #FBD38D, #F6AD55);
  border-radius: 50%;
  animation: wd-bob 1.5s ease-in-out infinite;
}
@keyframes wd-bob {
  0%, 100% { transform: translateY(0); }
  50% { transform: translateY(-1px); }
}
.wd-label {
  white-space: nowrap;
}
</style>
