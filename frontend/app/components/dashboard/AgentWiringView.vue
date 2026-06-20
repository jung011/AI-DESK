<template>
  <div class="wiring-canvas" ref="canvas">
    <svg class="wires" ref="wiresEl"></svg>
    <div class="ai-grid" ref="grid">
      <AgentCard
        v-for="agent in orderedAgents"
        :key="agent.agentId"
        :agent="agent"
        :ref="(el) => registerCard(agent.agentId, el)"
        @delete="$emit('delete', agent)"
        @select="$emit('select', agent)"
      />
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, onBeforeUnmount, watch, nextTick } from 'vue';
import AgentCard from '~/components/dashboard/AgentCard.vue';
import type { AgentItem, ApiEnvelope } from '~/vo/agents/AgentVo';

interface WiringLink {
  fromAgentId: string;
  toAgentId: string;
  count: number;
  lastAt: string;
}
interface WiringRs { links: WiringLink[]; windowMin: number }

const props = defineProps<{ agents: AgentItem[] }>();
defineEmits<{ (e: 'delete', a: AgentItem): void; (e: 'select', a: AgentItem): void }>();

const { $api } = useNuxtApp();
const wiringLinks = ref<WiringLink[]>([]);
const orderedAgents = ref<AgentItem[]>([]);
const cardRefs = new Map<string, HTMLElement>();
const canvas = ref<HTMLElement | null>(null);
const wiresEl = ref<SVGElement | null>(null);
const grid = ref<HTMLElement | null>(null);

const GRID_COLS = 5;
const WIRE_PALETTE = ['#4E79A7', '#F28E2C', '#E15759', '#76B7B2', '#59A14F', '#EDC949', '#AF7AA1', '#FF9DA7', '#9C755F', '#BAB0AC'];

function registerCard(id: string, el: unknown): void {
  const node = (el as { $el?: HTMLElement })?.$el ?? (el as HTMLElement | null);
  if (node && node instanceof HTMLElement) cardRefs.set(id, node);
}

// === Force simulation (vanilla) ===
interface SimNode { id: string; x: number; y: number; vx: number; vy: number }
function forceSim(agents: AgentItem[], links: WiringLink[]): SimNode[] {
  const ITERS = 300, LINK_DIST = 200, CHARGE = -800;
  const nodes: SimNode[] = agents.map(a => ({
    id: a.agentId, x: (Math.random() - 0.5) * 400, y: (Math.random() - 0.5) * 400, vx: 0, vy: 0,
  }));
  const maxCount = Math.max(1, ...links.map(l => l.count));
  for (let iter = 0; iter < ITERS; iter++) {
    const alpha = 1 - iter / ITERS;
    // repulsion
    for (let i = 0; i < nodes.length; i++) {
      for (let j = i + 1; j < nodes.length; j++) {
        const dx = nodes[j].x - nodes[i].x;
        const dy = nodes[j].y - nodes[i].y;
        const dist = Math.hypot(dx, dy) + 0.01;
        const f = (CHARGE / (dist * dist)) * alpha;
        nodes[i].vx -= (dx / dist) * f;
        nodes[i].vy -= (dy / dist) * f;
        nodes[j].vx += (dx / dist) * f;
        nodes[j].vy += (dy / dist) * f;
      }
    }
    // link attraction
    links.forEach(l => {
      const s = nodes.find(n => n.id === l.fromAgentId);
      const t = nodes.find(n => n.id === l.toAgentId);
      if (!s || !t) return;
      const intensity = l.count / maxCount;
      const dx = t.x - s.x, dy = t.y - s.y;
      const dist = Math.hypot(dx, dy) + 0.01;
      const targetDist = LINK_DIST - intensity * 120;
      const f = (dist - targetDist) * (0.2 + intensity * 0.5) * alpha;
      const fx = (dx / dist) * f, fy = (dy / dist) * f;
      s.vx += fx; s.vy += fy;
      t.vx -= fx; t.vy -= fy;
    });
    // centering
    nodes.forEach(n => { n.vx -= n.x * 0.05; n.vy -= n.y * 0.05; });
    // velocity apply + damping
    nodes.forEach(n => { n.x += n.vx * 0.5; n.y += n.vy * 0.5; n.vx *= 0.7; n.vy *= 0.7; });
  }
  return nodes;
}

function computeOrder(): AgentItem[] {
  if (props.agents.length === 0) return [];
  const sim = forceSim(props.agents, wiringLinks.value);
  // x 좌표 sort → 5 column binning → 같은 column 안 y 정렬 → row-major flatten
  const byX = sim.slice().sort((a, b) => a.x - b.x);
  const perCol = Math.ceil(byX.length / GRID_COLS);
  const cols: SimNode[][] = [];
  for (let c = 0; c < GRID_COLS; c++) {
    const slice = byX.slice(c * perCol, (c + 1) * perCol);
    slice.sort((a, b) => a.y - b.y);
    cols.push(slice);
  }
  const rows = Math.max(...cols.map(c => c.length));
  const result: AgentItem[] = [];
  for (let r = 0; r < rows; r++) {
    for (let c = 0; c < GRID_COLS; c++) {
      const n = cols[c][r];
      if (!n) continue;
      const a = props.agents.find(x => x.agentId === n.id);
      if (a) result.push(a);
    }
  }
  return result;
}

// === Wire SVG (orthogonal + detour) ===
function getBox(el: HTMLElement) {
  const r = el.getBoundingClientRect();
  const ww = canvas.value!.getBoundingClientRect();
  return { x: r.left - ww.left, y: r.top - ww.top, w: r.width, h: r.height, cx: r.left - ww.left + r.width / 2, cy: r.top - ww.top + r.height / 2 };
}
type Box = ReturnType<typeof getBox>;
function lineHitsBox(x1: number, y1: number, x2: number, y2: number, box: Box, pad = 6): boolean {
  const bx1 = box.x - pad, by1 = box.y - pad, bx2 = box.x + box.w + pad, by2 = box.y + box.h + pad;
  if (y1 === y2) {
    if (y1 < by1 || y1 > by2) return false;
    return !(Math.max(x1, x2) < bx1 || Math.min(x1, x2) > bx2);
  }
  if (x1 === x2) {
    if (x1 < bx1 || x1 > bx2) return false;
    return !(Math.max(y1, y2) < by1 || Math.min(y1, y2) > by2);
  }
  return false;
}
function countHits(segs: number[][], boxes: Map<string, Box>, excludeIds: string[]): number {
  let hits = 0;
  boxes.forEach((b, id) => {
    if (excludeIds.includes(id)) return;
    segs.forEach(s => { if (lineHitsBox(s[0], s[1], s[2], s[3], b)) hits++; });
  });
  return hits;
}
function pathCandidates(s: Box, t: Box): number[][][] {
  const dx = t.cx - s.cx, dy = t.cy - s.cy;
  const sPxH = dx > 0 ? s.x + s.w : s.x, sPyH = s.cy, tPxH = dx > 0 ? t.x : t.x + t.w, tPyH = t.cy;
  const midXH = (sPxH + tPxH) / 2;
  const H = [[sPxH, sPyH, midXH, sPyH], [midXH, sPyH, midXH, tPyH], [midXH, tPyH, tPxH, tPyH]];
  const sPxV = s.cx, sPyV = dy > 0 ? s.y + s.h : s.y, tPxV = t.cx, tPyV = dy > 0 ? t.y : t.y + t.h;
  const midYV = (sPyV + tPyV) / 2;
  const V = [[sPxV, sPyV, sPxV, midYV], [sPxV, midYV, tPxV, midYV], [tPxV, midYV, tPxV, tPyV]];
  const detour = 60;
  const midXZ = dx > 0 ? Math.max(sPxH, tPxH) + detour : Math.min(sPxH, tPxH) - detour;
  const Z = [[sPxH, sPyH, midXZ, sPyH], [midXZ, sPyH, midXZ, tPyH], [midXZ, tPyH, tPxH, tPyH]];
  return [H, V, Z];
}
function segsToPath(segs: number[][]): string {
  const r = 8;
  let d = `M${segs[0][0]},${segs[0][1]}`;
  for (let i = 0; i < segs.length; i++) {
    const [x1, y1, x2, y2] = segs[i];
    if (i < segs.length - 1) {
      const next = segs[i + 1];
      const dirX = Math.sign(x2 - x1), dirY = Math.sign(y2 - y1);
      d += ` L${x2 - dirX * r},${y2 - dirY * r}`;
      const nDirX = Math.sign(next[2] - next[0]), nDirY = Math.sign(next[3] - next[1]);
      d += ` Q${x2},${y2} ${x2 + nDirX * r},${y2 + nDirY * r}`;
    } else {
      d += ` L${x2},${y2}`;
    }
  }
  return d;
}
function drawWires(): void {
  if (!wiresEl.value || !canvas.value) return;
  const ww = canvas.value.getBoundingClientRect();
  wiresEl.value.setAttribute('width', String(ww.width));
  wiresEl.value.setAttribute('height', String(ww.height));
  // 모든 카드 박스 캡쳐
  const boxes = new Map<string, Box>();
  cardRefs.forEach((el, id) => { if (el.isConnected) boxes.set(id, getBox(el)); });
  // 옛 path 모두 제거 + 새로 그림
  while (wiresEl.value.firstChild) wiresEl.value.removeChild(wiresEl.value.firstChild);
  wiringLinks.value.forEach((link, i) => {
    const sBox = boxes.get(link.fromAgentId);
    const tBox = boxes.get(link.toAgentId);
    if (!sBox || !tBox) return;
    const cands = pathCandidates(sBox, tBox);
    let best = cands[0], bestHits = Infinity;
    cands.forEach(c => {
      const hits = countHits(c, boxes, [link.fromAgentId, link.toAgentId]);
      if (hits < bestHits) { bestHits = hits; best = c; }
    });
    const maxCount = Math.max(1, ...wiringLinks.value.map(l => l.count));
    const intensity = link.count / maxCount;
    const path = document.createElementNS('http://www.w3.org/2000/svg', 'path');
    path.setAttribute('d', segsToPath(best));
    path.setAttribute('stroke', WIRE_PALETTE[i % WIRE_PALETTE.length]);
    path.setAttribute('stroke-opacity', '0.85');
    path.setAttribute('stroke-width', String(2 + intensity * 4));
    path.setAttribute('fill', 'none');
    path.setAttribute('stroke-linecap', 'round');
    path.setAttribute('stroke-linejoin', 'round');
    path.setAttribute('data-key', `${link.fromAgentId}->${link.toAgentId}`);
    wiresEl.value!.appendChild(path);
  });
}

// === FLIP slide reorder ===
function reorder(newOrder: AgentItem[]): void {
  const first = new Map<string, DOMRect>();
  cardRefs.forEach((el, id) => first.set(id, el.getBoundingClientRect()));
  orderedAgents.value = newOrder;
  nextTick(() => {
    cardRefs.forEach((el, id) => {
      const last = el.getBoundingClientRect();
      const f = first.get(id);
      if (!f) return;
      const dx = f.left - last.left, dy = f.top - last.top;
      if (dx === 0 && dy === 0) return;
      el.style.transform = `translate(${dx}px, ${dy}px)`;
      el.style.transition = 'none';
    });
    void grid.value?.offsetHeight;
    requestAnimationFrame(() => {
      cardRefs.forEach(el => {
        el.style.transition = 'transform .9s cubic-bezier(.25,.8,.25,1), box-shadow .15s';
        el.style.transform = '';
      });
      // wire 도 매 frame 갱신
      let raf: number;
      const animateWires = () => { drawWires(); raf = requestAnimationFrame(animateWires); };
      raf = requestAnimationFrame(animateWires);
      setTimeout(() => {
        cancelAnimationFrame(raf);
        cardRefs.forEach(el => { el.style.transition = ''; el.style.transform = ''; });
        drawWires();
      }, 950);
    });
  });
}

// === fetch wiring ===
async function fetchWiring(): Promise<void> {
  try {
    const env = await $api<ApiEnvelope<WiringRs>>('/api/agents/wiring?windowMin=30');
    if (env.result === 0) {
      wiringLinks.value = env.data.links;
      const newOrder = computeOrder();
      reorder(newOrder);
    }
  } catch { /* silent */ }
}

let pollTimer: ReturnType<typeof setInterval> | null = null;
let evtSource: EventSource | null = null;

onMounted(() => {
  orderedAgents.value = [...props.agents];
  nextTick(() => fetchWiring());
  pollTimer = setInterval(fetchWiring, 30_000);
  if (typeof EventSource !== 'undefined') {
    evtSource = new EventSource('/api/messages/events');
    evtSource.addEventListener('message.deliver', () => { void fetchWiring(); });
    evtSource.addEventListener('agent.changed', () => { void fetchWiring(); });
  }
  window.addEventListener('resize', drawWires);
});
onBeforeUnmount(() => {
  if (pollTimer) clearInterval(pollTimer);
  evtSource?.close();
  window.removeEventListener('resize', drawWires);
});
watch(() => props.agents, () => {
  const newOrder = computeOrder();
  reorder(newOrder);
}, { deep: true });
</script>

<style scoped>
.wiring-canvas { position: relative; padding: 20px 0; }
svg.wires { position: absolute; top: 0; left: 0; width: 100%; height: 100%; pointer-events: none; z-index: 1; }
.ai-grid {
  display: grid;
  grid-template-columns: repeat(5, 200px);
  justify-content: center;
  gap: 24px;
  position: relative;
  z-index: 2;
}
.ai-grid > :deep(.ai-card) { will-change: transform; }
</style>
