<template>
  <div class="wds-inline" role="status" :aria-label="`${agentName} 가 책상에서 작업중`">
    <div class="wds-stage">
      <div class="wds-desk">
        <div class="wds-monitor">
          <div class="wds-screen">
            <div class="wds-codelines">
              <div class="wds-line c1"></div>
              <div class="wds-line c2"></div>
              <div class="wds-line c3"></div>
              <div class="wds-line c4"></div>
              <div class="wds-line c5"></div>
              <div class="wds-line c1"></div>
              <div class="wds-line c2"></div>
              <div class="wds-line c3"></div>
            </div>
          </div>
        </div>
        <div class="wds-desk-top"></div>
        <div class="wds-leg left"></div>
        <div class="wds-leg right"></div>
        <div class="wds-keyboard"></div>
        <div class="wds-chair"></div>
        <div class="wds-character">
          <div class="wds-head-c"><div class="wds-hair"></div></div>
          <div class="wds-body">
            <div class="wds-arm left"></div>
            <div class="wds-arm right"></div>
          </div>
        </div>
      </div>
      <div class="wds-floor"></div>
    </div>
    <div class="wds-caption">
      <span class="wds-dot"></span>
      <span><strong>{{ agentName }}</strong> 가 책상에서 작업중</span>
    </div>
  </div>
</template>

<script setup lang="ts">
defineProps<{ agentName: string }>();
</script>

<style scoped>
.wds-inline {
  width: 240px;
  border: 1px solid #2A3950;
  border-radius: 10px;
  overflow: hidden;
  background: #1E2738;
  box-shadow: 0 6px 18px rgba(0, 0, 0, 0.35);
}
.wds-stage {
  position: relative;
  height: 160px;
  background: linear-gradient(180deg, #0B1220 0%, #0F1729 100%);
  display: flex; align-items: flex-end; justify-content: center;
  overflow: hidden;
}
.wds-floor {
  position: absolute; bottom: 0; left: 0; right: 0;
  height: 20px;
  background: linear-gradient(180deg, transparent 0%, rgba(107,182,255,0.06) 100%);
  border-top: 1px solid rgba(107,182,255,0.18);
}

.wds-desk {
  position: relative;
  width: 160px;
  height: 130px;
}
.wds-desk-top {
  position: absolute; bottom: 26px; left: 10px; right: 10px;
  height: 5px;
  background: linear-gradient(90deg, #2A3950, #4A5A78, #2A3950);
  border-radius: 2px;
}
.wds-leg {
  position: absolute; bottom: 0; width: 4px; height: 26px;
  background: #2A3950;
}
.wds-leg.left { left: 26px; }
.wds-leg.right { right: 26px; }

.wds-monitor {
  position: absolute;
  bottom: 31px; left: 34px;
  width: 96px; height: 62px;
  background: #050810;
  border: 2.5px solid #4A5A78;
  border-radius: 5px;
  overflow: hidden;
  box-shadow: 0 0 18px rgba(107,182,255,0.25);
}
.wds-monitor::after {
  content: '';
  position: absolute; bottom: -9px; left: 50%;
  transform: translateX(-50%);
  width: 26px; height: 7px;
  background: #4A5A78;
  border-radius: 0 0 3px 3px;
}
.wds-screen {
  position: absolute; inset: 0;
  background:
    repeating-linear-gradient(0deg, transparent 0px, transparent 4px, rgba(107,182,255,0.06) 4px, rgba(107,182,255,0.06) 5px),
    linear-gradient(180deg, #061025 0%, #0B1A35 100%);
}
.wds-codelines {
  position: absolute; inset: 6px;
  animation: wds-scroll 4s linear infinite;
}
@keyframes wds-scroll {
  0% { transform: translateY(50px); }
  100% { transform: translateY(-100%); }
}
.wds-line {
  height: 4px;
  margin-bottom: 3px;
  border-radius: 1px;
}
.wds-line.c1 { width: 70%; background: #6BB6FF; opacity: 0.7; }
.wds-line.c2 { width: 50%; background: #B89AFF; opacity: 0.6; }
.wds-line.c3 { width: 80%; background: #22C55E; opacity: 0.65; }
.wds-line.c4 { width: 40%; background: #FBBF24; opacity: 0.55; }
.wds-line.c5 { width: 65%; background: #6BB6FF; opacity: 0.7; }

.wds-keyboard {
  position: absolute; bottom: 28px; left: 40px;
  width: 80px; height: 4px;
  background: #4A5A78;
  border-radius: 2px;
}
.wds-chair {
  position: absolute; bottom: 16px; right: 16px;
  width: 18px; height: 24px;
  background: #2A3950;
  border-radius: 3px 3px 0 0;
}
.wds-character {
  position: absolute; bottom: 42px; right: 22px;
  width: 24px;
  animation: wds-bob 1.7s ease-in-out infinite;
}
@keyframes wds-bob {
  0%, 100% { transform: translateY(0); }
  50% { transform: translateY(-2px); }
}
.wds-head-c {
  width: 16px; height: 16px;
  border-radius: 50%;
  background: linear-gradient(135deg, #FBD38D, #F6AD55);
  margin: 0 auto;
  position: relative;
}
.wds-hair {
  position: absolute;
  top: -1px; left: 1px;
  width: 14px; height: 7px;
  background: linear-gradient(180deg, #4A3520, #2D1810);
  border-radius: 7px 7px 3px 3px;
}
.wds-body {
  width: 22px; height: 16px;
  background: linear-gradient(180deg, #6BB6FF, #4A8FCF);
  border-radius: 5px 5px 2px 2px;
  margin: -2px auto 0;
  position: relative;
}
.wds-arm {
  position: absolute;
  width: 4px; height: 12px;
  background: linear-gradient(180deg, #6BB6FF, #4A8FCF);
  border-radius: 2px;
  top: 3px;
}
.wds-arm.left {
  left: -2px;
  transform-origin: top center;
  animation: wds-arm-l 0.4s ease-in-out infinite;
}
.wds-arm.right {
  right: -2px;
  transform-origin: top center;
  animation: wds-arm-r 0.4s ease-in-out infinite;
  animation-delay: 0.2s;
}
@keyframes wds-arm-l {
  0%, 100% { transform: rotate(22deg); }
  50% { transform: rotate(32deg); }
}
@keyframes wds-arm-r {
  0%, 100% { transform: rotate(-22deg); }
  50% { transform: rotate(-32deg); }
}

.wds-caption {
  padding: 8px 12px;
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 11px;
  color: #94A3B8;
  border-top: 1px solid #2A3950;
}
.wds-caption strong {
  color: #6BB6FF;
  font-weight: 600;
}
.wds-dot {
  width: 6px; height: 6px;
  border-radius: 50%;
  background: #22C55E;
  box-shadow: 0 0 6px #22C55E;
  animation: wds-dot 1.4s ease-in-out infinite;
  flex-shrink: 0;
}
@keyframes wds-dot {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.4; }
}
</style>
