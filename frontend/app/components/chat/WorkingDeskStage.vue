<template>
  <Teleport to="body">
    <div class="wds-overlay" @click="$emit('close')">
      <div class="wds-panel" @click.stop>
        <header class="wds-head">
          <div class="wds-title">
            <span class="wds-avatar">🤖</span>
            <span>
              <div class="wds-name">{{ agentName }}</div>
              <div class="wds-sub">메시지를 받아 작업을 진행하고 있어요</div>
            </span>
          </div>
          <button class="wds-x" type="button" aria-label="닫기" @click="$emit('close')">✕</button>
        </header>
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
        <div class="wds-foot">
          <span class="wds-dot"></span>
          답신이 오면 이 화면은 자동으로 닫혀요
        </div>
      </div>
    </div>
  </Teleport>
</template>

<script setup lang="ts">
defineProps<{ agentName: string }>();
defineEmits<{ (e: 'close'): void }>();

onMounted(() => {
  if (typeof document !== 'undefined') {
    document.addEventListener('keydown', onEsc);
  }
});
onBeforeUnmount(() => {
  if (typeof document !== 'undefined') {
    document.removeEventListener('keydown', onEsc);
  }
});
function onEsc(e: KeyboardEvent) {
  if (e.key === 'Escape') {
    (document.activeElement as HTMLElement)?.blur();
    // emit via DOM event
    const evt = new CustomEvent('wds-close');
    document.dispatchEvent(evt);
  }
}
</script>

<style scoped>
.wds-overlay {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.55);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 9000;
  backdrop-filter: blur(4px);
}
.wds-panel {
  width: 420px;
  max-width: 92vw;
  background: #1E2738;
  border: 1px solid #2A3950;
  border-radius: 14px;
  box-shadow: 0 16px 40px rgba(0, 0, 0, 0.5);
  overflow: hidden;
}
.wds-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 14px 16px;
  border-bottom: 1px solid #2A3950;
}
.wds-title {
  display: flex;
  align-items: center;
  gap: 12px;
}
.wds-avatar {
  width: 36px; height: 36px;
  border-radius: 50%;
  background: linear-gradient(135deg, #6BB6FF, #B89AFF);
  display: flex; align-items: center; justify-content: center;
  font-size: 18px;
}
.wds-name {
  font-size: 14px; font-weight: 700; color: #E5EBF5;
}
.wds-sub {
  font-size: 11px; color: #94A3B8; margin-top: 2px;
}
.wds-x {
  width: 28px; height: 28px;
  background: transparent;
  border: 1px solid #2A3950;
  border-radius: 6px;
  color: #94A3B8;
  cursor: pointer;
  font-size: 14px;
}
.wds-x:hover { color: #E5EBF5; border-color: #475569; }

.wds-stage {
  position: relative;
  height: 240px;
  background: linear-gradient(180deg, #0B1220 0%, #0F1729 100%);
  display: flex; align-items: flex-end; justify-content: center;
  overflow: hidden;
}
.wds-floor {
  position: absolute; bottom: 0; left: 0; right: 0;
  height: 28px;
  background: linear-gradient(180deg, transparent 0%, rgba(107,182,255,0.06) 100%);
  border-top: 1px solid rgba(107,182,255,0.18);
}

.wds-desk {
  position: relative;
  width: 220px;
  height: 180px;
}
.wds-desk-top {
  position: absolute; bottom: 36px; left: 14px; right: 14px;
  height: 7px;
  background: linear-gradient(90deg, #2A3950, #4A5A78, #2A3950);
  border-radius: 2px;
}
.wds-leg {
  position: absolute; bottom: 0; width: 5px; height: 36px;
  background: #2A3950;
}
.wds-leg.left { left: 34px; }
.wds-leg.right { right: 34px; }

.wds-monitor {
  position: absolute;
  bottom: 43px; left: 48px;
  width: 130px; height: 85px;
  background: #050810;
  border: 3px solid #4A5A78;
  border-radius: 6px;
  overflow: hidden;
  box-shadow: 0 0 24px rgba(107,182,255,0.25);
}
.wds-monitor::after {
  content: '';
  position: absolute; bottom: -12px; left: 50%;
  transform: translateX(-50%);
  width: 34px; height: 10px;
  background: #4A5A78;
  border-radius: 0 0 4px 4px;
}
.wds-screen {
  position: absolute; inset: 0;
  background:
    repeating-linear-gradient(0deg, transparent 0px, transparent 5px, rgba(107,182,255,0.06) 5px, rgba(107,182,255,0.06) 6px),
    linear-gradient(180deg, #061025 0%, #0B1A35 100%);
}
.wds-codelines {
  position: absolute; inset: 8px;
  animation: wds-scroll 4s linear infinite;
}
@keyframes wds-scroll {
  0% { transform: translateY(70px); }
  100% { transform: translateY(-100%); }
}
.wds-line {
  height: 6px;
  margin-bottom: 4px;
  border-radius: 1px;
}
.wds-line.c1 { width: 70%; background: #6BB6FF; opacity: 0.7; }
.wds-line.c2 { width: 50%; background: #B89AFF; opacity: 0.6; }
.wds-line.c3 { width: 80%; background: #22C55E; opacity: 0.65; }
.wds-line.c4 { width: 40%; background: #FBBF24; opacity: 0.55; }
.wds-line.c5 { width: 65%; background: #6BB6FF; opacity: 0.7; }

.wds-keyboard {
  position: absolute; bottom: 38px; left: 56px;
  width: 110px; height: 5px;
  background: #4A5A78;
  border-radius: 2px;
}
.wds-chair {
  position: absolute; bottom: 24px; right: 22px;
  width: 24px; height: 32px;
  background: #2A3950;
  border-radius: 4px 4px 0 0;
}
.wds-character {
  position: absolute; bottom: 56px; right: 30px;
  width: 32px;
  animation: wds-bob 1.7s ease-in-out infinite;
}
@keyframes wds-bob {
  0%, 100% { transform: translateY(0); }
  50% { transform: translateY(-2px); }
}
.wds-head-c {
  width: 20px; height: 20px;
  border-radius: 50%;
  background: linear-gradient(135deg, #FBD38D, #F6AD55);
  margin: 0 auto;
  position: relative;
}
.wds-hair {
  position: absolute;
  top: -2px; left: 1px;
  width: 18px; height: 9px;
  background: linear-gradient(180deg, #4A3520, #2D1810);
  border-radius: 9px 9px 4px 4px;
}
.wds-body {
  width: 28px; height: 20px;
  background: linear-gradient(180deg, #6BB6FF, #4A8FCF);
  border-radius: 6px 6px 2px 2px;
  margin: -2px auto 0;
  position: relative;
}
.wds-arm {
  position: absolute;
  width: 5px; height: 15px;
  background: linear-gradient(180deg, #6BB6FF, #4A8FCF);
  border-radius: 3px;
  top: 4px;
}
.wds-arm.left {
  left: -3px;
  transform-origin: top center;
  animation: wds-arm-l 0.4s ease-in-out infinite;
}
.wds-arm.right {
  right: -3px;
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

.wds-foot {
  padding: 12px 16px;
  border-top: 1px solid #2A3950;
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 11px;
  color: #94A3B8;
}
.wds-dot {
  width: 6px; height: 6px;
  border-radius: 50%;
  background: #22C55E;
  box-shadow: 0 0 6px #22C55E;
  animation: wds-dot 1.4s ease-in-out infinite;
}
@keyframes wds-dot {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.4; }
}
</style>
