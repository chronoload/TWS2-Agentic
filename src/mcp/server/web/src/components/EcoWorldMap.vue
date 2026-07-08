<template>
  <div class="eco-world-map" ref="containerRef">
    <div class="panel-header">
      <span class="panel-title">🌐 概念图谱</span>
      <div class="header-actions">
        <span class="stat-badge">tick {{ store.tick }}</span>
        <span class="stat-badge era">{{ store.era }}</span>
        <span class="stat-badge">S={{ store.globalEntropy.toFixed(2) }}</span>
        <button class="btn-sm" @click="runTick">⏱</button>
      </div>
    </div>

    <div v-if="conceptNodes.length === 0" class="empty-state">尚无概念</div>

    <svg v-else ref="svgRef" class="map-svg" :viewBox="`0 0 ${width} ${height}`"
         @mousedown="onBgDown" @mousemove="onDrag" @mouseup="onBgUp"
         @mouseleave="onBgUp">
      <!-- 连接线 -->
      <line v-for="(edge, i) in edges" :key="'e'+i"
            :x1="edge.x1" :y1="edge.y1" :x2="edge.x2" :y2="edge.y2"
            :style="'stroke: var(--border); stroke-width: ' + (edge.strength * 2 + 0.5) + '; opacity: ' + (edge.strength * 0.5 + 0.2)"/>
      <!-- 概念节点 -->
      <g v-for="node in conceptNodes" :key="node.id"
         :transform="'translate('+node.x+','+node.y+')'"
         @mousedown.prevent="startDrag(node, $event)">
        <circle :r="node.r" :fill="node.color" :stroke="node === selected ? '#fff' : 'transparent'" stroke-width="2"/>
        <text text-anchor="middle" dy="4" font-size="10" fill="#fff" style="pointer-events:none; user-select:none;">
          {{ node.label.length > 6 ? node.label.slice(0, 6) + '…' : node.label }}
        </text>
      </g>
    </svg>

    <div v-if="selected" class="concept-detail">
      <div class="detail-header">
        <strong>{{ selected.label }}</strong>
        <span class="detail-id">{{ selected.id.slice(0, 8) }}</span>
        <button class="btn-sm" @click="selected = null">✕</button>
      </div>
      <div class="detail-stats">
        <span>深度 {{ selected.depth.toFixed(1) }}</span>
        <span>新鲜 {{ (selected.freshness * 100).toFixed(0) }}%</span>
        <span>熵 {{ selected.entropy.toFixed(2) }}</span>
        <span>连接 {{ Object.keys(selected.related_ids).length }}</span>
      </div>
      <div class="detail-actions">
        <button class="btn-sm" @click="store.doDive(selected.id)">🔍 深潜</button>
      </div>
    </div>

    <div v-if="inspirations.length" class="inspirations">
      <div class="insp-title">💡 灵感</div>
      <div v-for="ins in inspirations" :key="ins.label" class="insp-item">
        <span class="insp-tag">{{ ins.action_type }}</span>
        <span class="insp-label">{{ ins.label }}</span>
        <span class="insp-desc">{{ ins.description }}</span>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, watch } from 'vue'
import { useEcosystemStore } from '../stores/ecosystem'

const store = useEcosystemStore()

const width = 600
const height = 400
const svgRef = ref<SVGSVGElement>()
const selected = ref<any>(null)
const inspirations = ref<any[]>([])

// Force simulation state
const nodes = ref<Map<string, { id: string; label: string; x: number; y: number; vx: number; vy: number; r: number; color: string; depth: number; freshness: number; entropy: number; related_ids: Record<string, number> }>>(new Map())
let dragNode: any = null
let dragOffX = 0, dragOffY = 0

const conceptNodes = computed(() => Array.from(nodes.value.values()))

const edges = computed(() => {
  const result: { x1: number; y1: number; x2: number; y2: number; strength: number }[] = []
  const ns = nodes.value
  for (const [cid, node] of ns) {
    for (const [otherId, strength] of Object.entries(node.related_ids)) {
      const other = ns.get(otherId)
      if (other && cid < otherId) {
        result.push({ x1: node.x, y1: node.y, x2: other.x, y2: other.y, strength })
      }
    }
  }
  return result
})

function buildGraph() {
  const concepts = store.concepts
  const entries = Object.entries(concepts)
  const w = width, h = height
  const newNodes = new Map<string, any>()

  entries.forEach(([id, c], i) => {
    const angle = (i / entries.length) * Math.PI * 2
    const radius = Math.min(w, h) * 0.35
    const r = 8 + c.depth * 3
    const hue = c.is_fossilized ? 0 : (c.entropy * 120 + 200) % 360
    newNodes.set(id, {
      id, label: c.label,
      x: w / 2 + Math.cos(angle) * radius,
      y: h / 2 + Math.sin(angle) * radius,
      vx: 0, vy: 0, r: Math.min(r, 30),
      color: c.is_fossilized ? '#666' : `hsl(${hue}, 60%, 50%)`,
      depth: c.depth, freshness: c.freshness,
      entropy: c.entropy, related_ids: c.related_ids ?? {},
    })
  })
  nodes.value = newNodes
  requestAnimationFrame(simulate)
}

function simulate() {
  const ns = nodes.value
  const list = Array.from(ns.values())
  const centerX = width / 2, centerY = height / 2
  let moved = false

  for (const a of list) {
    // center gravity
    a.vx += (centerX - a.x) * 0.001
    a.vy += (centerY - a.y) * 0.001

    // repulsion
    for (const b of list) {
      if (a.id === b.id) continue
      const dx = a.x - b.x, dy = a.y - b.y
      const dist = Math.sqrt(dx * dx + dy * dy) || 1
      const force = 50 / (dist * dist)
      a.vx += dx / dist * force
      a.vy += dy / dist * force
    }

    // attraction along edges
    for (const [otherId, strength] of Object.entries(a.related_ids)) {
      const b = ns.get(otherId)
      if (!b) continue
      const dx = b.x - a.x, dy = b.y - a.y
      const force = strength * 0.01
      a.vx += dx * force
      a.vy += dy * force
    }

    // damping
    a.vx *= 0.9
    a.vy *= 0.9

    // apply
    if (Math.abs(a.vx) > 0.01 || Math.abs(a.vy) > 0.01) moved = true
    a.x += a.vx
    a.y += a.vy
    a.x = Math.max(10, Math.min(width - 10, a.x))
    a.y = Math.max(10, Math.min(height - 10, a.y))
  }

  if (moved) requestAnimationFrame(simulate)
}

function startDrag(node: any, ev: MouseEvent) {
  dragNode = node
  const rect = svgRef.value!.getBoundingClientRect()
  const scaleX = width / rect.width
  const scaleY = height / rect.height
  dragOffX = ev.clientX - rect.left - node.x / scaleX
  dragOffY = ev.clientY - rect.top - node.y / scaleY
}

function onDrag(ev: MouseEvent) {
  if (!dragNode || !svgRef.value) return
  const rect = svgRef.value.getBoundingClientRect()
  const scaleX = width / rect.width
  const scaleY = height / rect.height
  dragNode.x = (ev.clientX - rect.left - dragOffX) * scaleX
  dragNode.y = (ev.clientY - rect.top - dragOffY) * scaleY
}

function onBgDown() { selected.value = null }
function onBgUp() { dragNode = null }

async function runTick() {
  await store.doTick()
  await loadInspirations()
}

async function loadInspirations() {
  await store.fetchInspirations()
  inspirations.value = store.inspirations.slice(0, 5)
}

watch(() => store.concepts, () => buildGraph(), { deep: true })

onMounted(async () => {
  await store.fetchState()
  buildGraph()
  await loadInspirations()
})
</script>

<style scoped>
.eco-world-map { background: var(--bg-secondary); border-radius: 8px; padding: 12px; }
.panel-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; }
.panel-title { font-weight: 600; font-size: 14px; }
.header-actions { display: flex; gap: 6px; align-items: center; }
.stat-badge { background: var(--bg); padding: 2px 6px; border-radius: 4px; font-size: 11px; color: var(--fg-muted); }
.stat-badge.era { background: var(--accent); color: #fff; }
.btn-sm { background: none; border: 1px solid var(--border); border-radius: 4px; color: var(--fg); padding: 2px 8px; font-size: 12px; cursor: pointer; }
.btn-sm:hover { background: var(--bg); }
.empty-state { color: var(--fg-muted); font-size: 13px; text-align: center; padding: 60px 0; }
.map-svg { width: 100%; height: auto; background: var(--bg); border-radius: 6px; cursor: grab; }
.concept-detail {
  margin-top: 8px; padding: 8px; background: var(--bg); border-radius: 6px; font-size: 12px;
}
.detail-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 4px; }
.detail-id { color: var(--fg-muted); font-size: 10px; }
.detail-stats { display: flex; gap: 10px; margin-bottom: 6px; color: var(--fg-muted); font-size: 11px; }
.detail-actions { display: flex; gap: 4px; }
.inspirations { margin-top: 8px; padding: 8px; background: var(--bg); border-radius: 6px; }
.insp-title { font-size: 12px; font-weight: 600; margin-bottom: 6px; }
.insp-item { display: flex; gap: 6px; align-items: center; padding: 3px 0; font-size: 12px; }
.insp-tag { background: var(--accent); color: #fff; padding: 1px 5px; border-radius: 3px; font-size: 10px; }
.insp-label { font-weight: 500; }
.insp-desc { color: var(--fg-muted); font-size: 11px; }
</style>
