<template>
  <div class="game-view">
    <svg class="world-map" :viewBox="`0 0 ${W} ${H}`"
         @mousedown="onPointerDown" @mousemove="onPointerMove" @mouseup="onPointerUp"
         @mouseleave="onPointerUp">
      <defs>
        <radialGradient id="bg-grad" cx="50%" cy="50%" r="60%">
          <stop offset="0%" stop-color="#0f0f1a"/>
          <stop offset="100%" stop-color="#06060e"/>
        </radialGradient>
      </defs>
      <rect width="100%" height="100%" fill="url(#bg-grad)"/>
      <!-- 世界 → 大陆 → 区域 -->
      <!-- 不活跃大陆：只显示区域名和入口光环 -->
      <g v-for="r in inactiveRegions" :key="r.id"
         :transform="`translate(${r.cx},${r.cy})`"
         class="region-glow" @click="travelTo(r.id)">
        <circle :r="r.r" fill="none" :stroke="r.color" stroke-width="1" opacity="0.3"/>
        <circle :r="6" :fill="r.color" opacity="0.6"/>
        <text text-anchor="middle" dy="14" :fill="r.color" font-size="11" font-weight="600"
              opacity="0.7" style="user-select:none;">{{ r.label }}</text>
        <text text-anchor="middle" dy="28" fill="rgba(255,255,255,0.25)" font-size="9"
              style="user-select:none;">{{ r.count }} 概念 · 点击旅行</text>
      </g>
      <!-- 活跃大陆连接线 -->
      <line v-for="(e, i) in edges" :key="'e'+i"
            :x1="e.x1" :y1="e.y1" :x2="e.x2" :y2="e.y2"
            :stroke="e.color" :stroke-width="e.w" :opacity="e.op"/>
      <!-- 活跃大陆概念节点 -->
      <g v-for="n in activeNodes" :key="n.id"
         :transform="`translate(${n.x},${n.y})`"
         :style="n.fossil ? 'opacity:0.2' : ''"
         @mousedown.prevent="onNodeDown(n, $event)">
        <circle :r="n.r" :fill="n.color"
                :stroke="n === selectedNode ? '#fff' : 'rgba(255,255,255,0.3)'"
                :stroke-width="n === selectedNode ? 2.5 : 0.5"
                :style="n.entropy > 0.7 ? 'animation:pulse-node 1.5s ease-in-out infinite;' : ''"/>
        <text text-anchor="middle" :dy="n.r > 10 ? 4 : 0" font-size="8" fill="rgba(255,255,255,0.85)"
              style="pointer-events:none; user-select:none;" v-if="n.r > 7">{{ labelShort(n.label) }}</text>
        <text v-if="n.fossil" text-anchor="middle" dy="0" font-size="13" fill="#f84"
              style="pointer-events:none; user-select:none;">💀</text>
      </g>
      <!-- 玩家标记 -->
      <text v-if="activeRegionId" :x="playerX" :y="playerY" text-anchor="middle" font-size="16"
            fill="#4fc3f7" style="pointer-events:none; user-select:none; filter:drop-shadow(0 0 6px #4fc3f7);">✦</text>
    </svg>

    <!-- 顶栏 -->
    <div class="top-bar">
      <span class="game-title">🎮 知识大陆</span>
      <span class="pill era">{{ store.era || '寒武纪' }}</span>
      <span class="pill">☯ {{ store.globalEntropy.toFixed(2) }}</span>
      <span class="pill">{{ activeRegionLabel }}</span>
      <span class="pill">🧬 {{ activeCount }}</span>
      <span class="pill">⏱ {{ store.tick }}</span>
      <span v-if="unprocessed > 0" class="pill alert">📡 {{ unprocessed }}</span>
    </div>

    <!-- 通知 -->
    <transition name="drop">
      <div v-if="toast" class="toast" @click="toast.action?.()">
        <span class="ti">{{ toast.icon }}</span>
        <div class="tb">
          <div class="tm">{{ toast.msg }}</div>
          <div v-if="toast.detail" class="td">{{ toast.detail }}</div>
          <span v-if="toast.btn" class="tbtn">{{ toast.btn }}→</span>
        </div>
      </div>
    </transition>

    <!-- 详情面板 -->
    <transition name="slide">
      <div v-if="selectedNode" class="detail">
        <div class="dh">
          <span class="dl">{{ selectedNode.label }}</span>
          <button class="dx" @click="selectedNode=null">✕</button>
        </div>
        <div class="ds">
          <span>深度 {{ selectedNode.depth.toFixed(1) }}</span>
          <span>新鲜 {{ (selectedNode.freshness*100).toFixed(0) }}%</span>
          <span :style="selectedNode.entropy > 0.6 ? 'color:#ff8a65;' : ''">熵 {{ selectedNode.entropy.toFixed(2) }}</span>
          <span v-if="selectedNode.fossil" class="fb">💀 化石</span>
        </div>
        <div v-if="nodeSources.length" class="dr">
          <div class="drh">📎 来源</div>
          <div v-for="s in nodeSources" :key="s.source_id || s.file_path" class="sl" @click="goSource(s)">
            <span class="sb" :class="s.source_type">{{ typeTag[s.source_type] || s.source_type }}</span>
            <span class="sx">{{ s.label || s.file_path || s.source_id }}</span>
            <span class="sa">↗</span>
          </div>
        </div>
        <div v-if="!selectedNode.fossil" class="da">
          <button class="ba" @click="doDive(selectedNode.id)">🔍 深潜</button>
          <button class="ba" @click="startCross(selectedNode.id)">🧬 交叉</button>
          <button class="ba" @click="doExpress([selectedNode.id])">✍️ 表达</button>
        </div>
        <div v-if="crossMode" class="ch">
          再点选一个概念完成交叉
          <button class="bc" @click="crossMode=''">取消</button>
        </div>
      </div>
    </transition>

    <!-- 底栏 -->
    <div class="bottom">
      <div class="bm">
        <input v-model="inputText" class="bi" placeholder="记录线下活动…" @keyup.enter="doRecord"/>
        <button class="bb" @click="doRecord" :disabled="!inputText.trim() || recording">📝 记录</button>
        <button class="bb" @click="doObserve" :disabled="observing">📡 {{ observing ? '…' : '导入' }}</button>
      </div>
      <div class="bt">
        <button class="btb" @click="doTick" :disabled="ticking">⏱ 演化</button>
        <button class="btb" @click="centerMap">⟲ 居中</button>
        <button class="btb" @click="doSyncFromCourse" :disabled="syncing">📚 同步</button>
        <span class="bt-hint" v-if="unprocessed > 0">📡 {{ unprocessed }} 条待导入</span>
        <span class="bt-hint region-name">📍 {{ activeRegionLabel }}</span>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, onMounted, onUnmounted } from 'vue'
import { useRouter } from 'vue-router'
import { useEcosystemStore } from '../stores/ecosystem'

const router = useRouter()
const store = useEcosystemStore()

const W = 800, H = 500
const selectedNode = ref<any>(null)
const crossMode = ref('')
const activeRegionId = ref('')
const inputText = ref('')
const recording = ref(false)
const observing = ref(false)
const ticking = ref(false)
const syncing = ref(false)
let simTimer = 0

const toast = ref<{ icon: string; msg: string; detail?: string; btn?: string; action?: () => void } | null>(null)
let toastTimer = 0

const typeTag: Record<string, string> = {
  note: '📝', pdf: '📄', course: '🎓', checkpoint: '📌', project: '📁', code: '💻',
}

// ── 线程调色板 ──
const THREAD_PALETTE: Record<string, string> = {
  A: '#4fc3f7', P: '#ff8a65', CS: '#81c784', DE: '#ce93d8',
  SE: '#ffd54f', D: '#4dd0e1', M: '#e57373', N: '#a1887f',
  C: '#7986cb', S: '#4db6ac', LM: '#f06292', DS: '#aed581',
  BIO: '#ba68c8', UNKNOWN: '#78909c',
}

// ── 概念 → 线程映射 ──
function conceptThread(c: any): string {
  for (const [tid, t] of Object.entries(store.threads)) {
    if ((t as any).concept_ids?.includes(c.id)) return tid.replace('thread_', '')
  }
  return 'UNKNOWN'
}

// ── 区域列表 ──
const regions = computed(() => {
  const allThreads = store.threads ?? {}
  const threadKeys = Object.keys(allThreads).filter(k => k.startsWith('thread_'))
  if (!threadKeys.length) return []
  const conceptIdsByThread: Record<string, string[]> = {}
  for (const c of Object.values(store.concepts)) {
    const tid = conceptThread(c as any)
    if (!conceptIdsByThread[tid]) conceptIdsByThread[tid] = []
    conceptIdsByThread[tid].push((c as any).id)
  }
  const groups: Record<string, number> = {}
  for (const [, t] of Object.entries(allThreads)) {
    const short = (t as any).id?.replace('thread_', '') ?? 'UNKNOWN'
    groups[short] = (t as any).concept_ids?.length ?? conceptIdsByThread[short]?.length ?? 0
  }
  return Object.entries(groups)
    .filter(([_, n]) => n >= 1)
    .map(([tid, n], i, arr) => {
      const angle = (i / arr.length) * Math.PI * 2 - Math.PI / 2
      const dist = Math.min(W, H) * 0.30
      return {
        id: tid,
        label: allThreads[`thread_${tid}`]?.label ?? `${tid}域`,
        count: n,
        cx: W / 2 + Math.cos(angle) * dist,
        cy: H / 2 + Math.sin(angle) * dist,
        r: 30 + Math.min(n, 200) * 0.15,
        color: THREAD_PALETTE[tid] || '#78909c',
        conceptIds: conceptIdsByThread[tid] ?? [],
      }
    })
})

const inactiveRegions = computed(() => regions.value.filter(r => r.id !== activeRegionId.value))
const activeRegion = computed(() => regions.value.find(r => r.id === activeRegionId.value))
const activeRegionLabel = computed(() => activeRegion.value?.label ?? '未选择')
const activeCount = computed(() => activeRegion.value?.count ?? 0)
const conceptCount = computed(() => store.totalConceptCount || Object.keys(store.concepts).length)
const unprocessed = computed(() => (store as any).unprocessedEvents ?? 0)

// ── 活跃节点（力导向） ──
const activeNodes = ref<any[]>([])
let nodeMap: Record<string, any> = {}

function buildActiveGraph() {
  const region = activeRegion.value
  if (!region) { activeNodes.value = []; nodeMap = {}; return }

  // 使用已加载的概念（neighborhood）构建力导向图
  const concepts = Object.values(store.concepts) as any[]
  const N = concepts.length
  if (!N) { activeNodes.value = []; nodeMap = {}; return }

  const palette = ['#4fc3f7', '#26c6da', '#29b6f6', '#42a5f5', '#5c6bc0', '#7e57c2', '#ab47bc']
  const C = Math.min(concepts.length, 7)

  const ns = concepts.map((c: any, i: number) => {
    const angle = (i / N) * Math.PI * 2
    const cv = region.cx + Math.cos(angle) * 60 + (Math.random() - 0.5) * 40
    const cy = region.cy + Math.sin(angle) * 60 + (Math.random() - 0.5) * 40
    const r = 4 + Math.min(c.depth, 8) * 1.8 + (c.parent_ids?.length ? 2 : 0)
    return {
      id: c.id, label: c.label,
      x: cv, y: cy, vx: 0, vy: 0, r,
      depth: c.depth, freshness: c.freshness, entropy: c.entropy,
      fossil: c.is_fossilized, parent_ids: c.parent_ids ?? [],
      related_ids: c.related_ids ?? {},
      color: palette[i % C],
    }
  })
  nodeMap = Object.fromEntries(ns.map((n: any) => [n.id, n]))
  activeNodes.value = ns
  startSim()
}

// ── 力导向 ──
function startSim() {
  cancelAnimationFrame(simTimer)
  const step = () => {
    const ns = activeNodes.value
    if (!ns.length) return
    const reg = activeRegion.value
    let moved = false
    for (const a of ns) {
      // 向区域中心拉力
      if (reg) {
        a.vx += (reg.cx - a.x) * 0.0015
        a.vy += (reg.cy - a.y) * 0.0015
      }
      // 节点间库仑力
      for (const b of ns) {
        if (a.id >= b.id) continue
        const dx = a.x - b.x, dy = a.y - b.y
        const d = Math.sqrt(dx * dx + dy * dy) || 1
        const f = 80 / (d * d + 10)
        a.vx += dx / d * f; a.vy += dy / d * f
        b.vx -= dx / d * f; b.vy -= dy / d * f
      }
      // 连接弹簧力
      for (const [oid, str] of Object.entries(a.related_ids)) {
        const b = nodeMap[oid]
        if (!b) continue
        const dx = b.x - a.x, dy = b.y - a.y
        const k = (str as number) * 0.008
        a.vx += dx * k; a.vy += dy * k
        b.vx -= dx * k; b.vy -= dy * k
      }
      // 父节点吸引力（子靠近父）
      for (const pid of a.parent_ids) {
        const p = nodeMap[pid]
        if (!p) continue
        a.vx += (p.x - a.x) * 0.01
        a.vy += (p.y - a.y) * 0.01
      }
      a.vx *= 0.88; a.vy *= 0.88
      if (Math.abs(a.vx) > 0.05 || Math.abs(a.vy) > 0.05) moved = true
      a.x += a.vx; a.y += a.vy
      if (reg) {
        const bound = reg.r + 40
        a.x = Math.max(reg.cx - bound, Math.min(reg.cx + bound, a.x))
        a.y = Math.max(reg.cy - bound, Math.min(reg.cy + bound, a.y))
      }
    }
    if (moved) simTimer = requestAnimationFrame(step)
  }
  simTimer = requestAnimationFrame(step)
}

const edges = computed(() => {
  const es: any[] = []
  const ns = activeNodes.value
  const seen = new Set<string>()
  for (const e of store.neighborEdges) {
    const a = nodeMap[e.source], b = nodeMap[e.target]
    if (!a || !b) continue
    const key = [e.source, e.target].sort().join(':')
    if (seen.has(key)) continue
    seen.add(key)
    es.push({
      x1: a.x, y1: a.y, x2: b.x, y2: b.y,
      w: e.strength * 1.5 + 0.2, op: e.strength * 0.2 + 0.05,
      color: a.color,
    })
  }
  for (const n of ns) {
    for (const [oid, str] of Object.entries(n.related_ids)) {
      const m = nodeMap[oid]
      if (!m) continue
      const key = [n.id, oid].sort().join(':')
      if (seen.has(key)) continue
      seen.add(key)
      es.push({
        x1: n.x, y1: n.y, x2: m.x, y2: m.y,
        w: (str as number) * 1.5 + 0.2, op: (str as number) * 0.2 + 0.05,
        color: n.color,
      })
    }
  }
  return es
})

const playerX = computed(() => activeNodes.value.length ? activeNodes.value[0]?.x ?? W / 2 : W / 2)
const playerY = computed(() => activeNodes.value.length ? activeNodes.value[0]?.y ?? H / 2 : H / 2)

const nodeSources = computed(() => {
  if (!selectedNode.value) return []
  return (store.concepts[selectedNode.value.id] as any)?.source_refs ?? []
})

function labelShort(label: string) {
  return label.length > 5 ? label.slice(0, 5) + '…' : label
}

function displayLabel(cid: string) {
  return store.concepts[cid]?.label ?? cid.slice(0, 8)
}

// ── 旅行 ──
function travelTo(regionId: string) {
  if (regionId === activeRegionId.value) return
  activeRegionId.value = regionId
  cancelAnimationFrame(simTimer)
  // 到达新大陆时异步加载周围概念
  const tid = `thread_${regionId}`
  const firstConcept = store.threads[tid]?.concept_ids?.[0]
  if (firstConcept) {
    store.fetchNeighborhood(firstConcept)
  }
  showToast('🚀', `已到达 ${regions.value.find(r => r.id === regionId)?.label ?? regionId}`,
    `${activeRegion.value?.count ?? 0} 个概念待探索`)
}

// ── 交互 ──
function onPointerDown() {}
function onPointerUp() {}
function onPointerMove() {}

function onNodeDown(n: any, _ev: MouseEvent) {
  if (crossMode.value) {
    doCross(crossMode.value, n.id)
    crossMode.value = ''
    return
  }
  selectedNode.value = n
  // 玩家跟随
  const idx = activeNodes.value.findIndex(a => a.id === n.id)
  if (idx > 0) {
    const [item] = activeNodes.value.splice(idx, 1)
    activeNodes.value.unshift(item)
  }
}

function centerMap() {
  if (regions.value.length) {
    travelTo(regions.value[0].id)
  }
}

// ── 通知 ──
function showToast(icon: string, msg: string, detail?: string, btn?: string, action?: () => void) {
  clearTimeout(toastTimer)
  toast.value = { icon, msg, detail, btn, action }
  toastTimer = window.setTimeout(() => { toast.value = null }, 5000)
}

// ── 操作 ──
async function doRecord() {
  if (!inputText.value.trim() || recording.value) return
  const text = inputText.value
  inputText.value = ''
  recording.value = true
  try {
    const res = await store.doRecord(text)
    const data = res || {}
    showToast('📝', data.narrative || '已记录')
    buildActiveGraph()
  } catch { showToast('⚠️', '记录失败') }
  finally { recording.value = false }
}

async function doObserve() {
  observing.value = true
  try {
    const res = await store.doObserve()
    showToast('📡', `已导入 ${res?.processed ?? 0} 条TS2活动`)
    buildActiveGraph()
  } catch { showToast('⚠️', '导入失败') }
  finally { observing.value = false }
}

async function doTick() {
  ticking.value = true
  try {
    const res = await store.doTick()
    showToast('⏱', res?.message || '演化完成')
    await store.fetchInspirations()
    if (store.inspirations.length) {
      const top = store.inspirations[0]
      showToast('💡', `灵感: ${top.label}`, top.description)
    }
    buildActiveGraph()
  } catch { showToast('⚠️', '演化失败') }
  finally { ticking.value = false }
}

async function doDive(cid: string) {
  const res = await store.doDive(cid)
  if (res) showToast('🔍', res.narrative || `深潜: ${displayLabel(cid)}`)
  buildActiveGraph()
}

async function doSyncFromCourse() {
  syncing.value = true
  try {
    const res = await store.doSync()
    if (res?.synced) showToast('📚', `已同步 ${res.synced} 个概念`)
    else showToast('💬', '已是最新')
    buildActiveGraph()
  } catch { showToast('⚠️', '同步失败') }
  finally { syncing.value = false }
}

async function doCross(a: string, b: string) {
  const res = await store.doCross(a, b)
  if (res) showToast('🧬', res.narrative || `交叉: ${displayLabel(a)} × ${displayLabel(b)}`)
  buildActiveGraph()
}

function startCross(cid: string) { crossMode.value = cid }

async function doExpress(cids: string[]) {
  const lbl = cids.length === 1 ? displayLabel(cids[0]) : `${cids.length}个概念`
  const res = await store.doExpress(cids)
  if (res) showToast('✍️', res.narrative || `表达: ${lbl}`)
  buildActiveGraph()
}

function goSource(s: any) {
  const fp = s.file_path || ''
  const sid = s.source_id || ''
  switch (s.source_type) {
    case 'pdf': router.push(`/pdf?file=${encodeURIComponent(fp)}`); break
    case 'note': router.push(`/slides?file=${encodeURIComponent(fp)}`); break
    case 'course': router.push(`/courses?highlight=${encodeURIComponent(sid)}`); break
    case 'project': router.push(`/projects?highlight=${encodeURIComponent(sid)}`); break
    case 'checkpoint': router.push(`/agent/checkpoints/${encodeURIComponent(sid)}`); break
    case 'code': router.push(`/files?path=${encodeURIComponent(fp)}`); break
    default: if (fp) router.push(`/files?path=${encodeURIComponent(fp)}`)
  }
}

// ── 生命周期 ──
watch(() => store.concepts, () => {
  if (Object.keys(store.concepts).length) buildActiveGraph()
}, { deep: true })

onMounted(async () => {
  await store.fetchState()
  // 加载玩家当前位置的邻域
  const playerCid = store.player.current_concept_id
  if (playerCid) {
    await store.fetchNeighborhood(playerCid)
  }
  // 确定活跃区域
  if (regions.value.length) {
    const playerTid = store.player.current_thread_id
    const startId = playerTid?.replace('thread_', '')
      ?? (regions.value.find(r => {
        const tid = `thread_${r.id}`
        const cids = store.threads[tid]?.concept_ids ?? []
        return playerCid && cids.includes(playerCid)
      })?.id)
      ?? regions.value[0].id
    activeRegionId.value = startId
    buildActiveGraph()
    showToast('🌱', `知识大陆 · ${conceptCount.value} 个概念`,
      `发现 ${regions.value.length} 个区域，点击其他区域旅行`)
  } else {
    showToast('💬', '知识大陆还是空的', '点 📚 同步从课程加载', '同步', doSyncFromCourse)
  }
})

onUnmounted(() => { cancelAnimationFrame(simTimer); clearTimeout(toastTimer) })
</script>

<style scoped>
.game-view { position: relative; width: 100%; height: 100%; background: #0a0a12; overflow: hidden; }
.world-map { width: 100%; height: 100%; display: block; cursor: grab; }
.world-map:active { cursor: grabbing; }

.top-bar {
  position: absolute; top: 0; left: 0; right: 0; display: flex; align-items: center;
  gap: 6px; padding: 8px 12px;
  background: linear-gradient(180deg, rgba(0,0,0,0.8) 0%, transparent 100%);
  pointer-events: none; z-index: 10;
}
.game-title { font-weight: 700; font-size: 14px; color: #fff; margin-right: 4px; }
.pill { font-size: 10px; color: rgba(255,255,255,0.6); background: rgba(255,255,255,0.08); padding: 2px 7px; border-radius: 4px; white-space: nowrap; }
.pill.era { background: #4fc3f7; color: #000; font-weight: 600; }
.pill.alert { background: #ff5252; color: #fff; animation: pulse 1.5s infinite; }
@keyframes pulse { 0%,100% { opacity: 1; } 50% { opacity: 0.6; } }
@keyframes pulse-node { 0%,100% { opacity: 1; } 50% { opacity: 0.5; } }

.region-glow { cursor: pointer; transition: opacity 0.2s; }
.region-glow:hover { opacity: 1 !important; }
.region-glow:hover circle:first-child { stroke-width: 2; }

.toast {
  position: absolute; top: 42px; left: 12px; right: 12px; z-index: 20;
  display: flex; gap: 8px; align-items: flex-start;
  background: rgba(0,0,0,0.88); backdrop-filter: blur(8px);
  border: 1px solid rgba(255,255,255,0.1); border-radius: 8px;
  padding: 10px 12px; cursor: pointer;
}
.ti { font-size: 18px; line-height: 1.4; }
.tb { flex: 1; min-width: 0; }
.tm { font-size: 13px; color: #fff; }
.td { font-size: 11px; color: rgba(255,255,255,0.5); margin-top: 2px; }
.tbtn { font-size: 11px; color: #4fc3f7; font-weight: 600; margin-top: 4px; display: inline-block; }
.drop-enter-active, .drop-leave-active { transition: all 0.3s ease; }
.drop-enter-from, .drop-leave-to { opacity: 0; transform: translateY(-16px); }

.detail {
  position: absolute; bottom: 76px; left: 12px; right: 12px; z-index: 15;
  background: rgba(16,16,30,0.95); backdrop-filter: blur(12px);
  border: 1px solid rgba(255,255,255,0.1); border-radius: 10px; padding: 14px;
  max-height: 45vh; overflow-y: auto;
}
.dh { display: flex; justify-content: space-between; align-items: center; margin-bottom: 6px; }
.dl { font-weight: 700; font-size: 16px; color: #fff; }
.dx { background: none; border: none; color: rgba(255,255,255,0.3); font-size: 16px; cursor: pointer; }
.ds { display: flex; gap: 8px; font-size: 11px; color: rgba(255,255,255,0.5); margin-bottom: 6px; flex-wrap: wrap; }
.fb { color: #ff8a65; }
.dr { margin-bottom: 6px; }
.drh { font-size: 11px; color: rgba(255,255,255,0.4); margin-bottom: 3px; }
.sl { display: flex; align-items: center; gap: 5px; padding: 3px 0; cursor: pointer; font-size: 12px; border-radius: 4px; }
.sl:hover { background: rgba(255,255,255,0.05); }
.sb { font-size: 10px; padding: 0 4px; }
.sb.pdf { color: #ff5252; } .sb.note { color: #448aff; } .sb.course { color: #69f0ae; }
.sb.project { color: #ff8a65; } .sb.checkpoint { color: #b388ff; } .sb.code { color: #4dd0e1; }
.sx { color: rgba(255,255,255,0.7); flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.sa { color: #4fc3f7; font-size: 13px; }
.da { display: flex; gap: 6px; flex-wrap: wrap; }
.ba {
  background: rgba(255,255,255,0.06); border: 1px solid rgba(255,255,255,0.15);
  border-radius: 6px; padding: 5px 10px; font-size: 11px; cursor: pointer;
  color: #fff; transition: all 0.15s;
}
.ba:hover { background: #4fc3f7; border-color: #4fc3f7; color: #000; }
.ch { font-size: 11px; color: #4fc3f7; margin-top: 6px; display: flex; gap: 8px; align-items: center; }
.bc { background: none; border: 1px solid rgba(255,255,255,0.15); color: rgba(255,255,255,0.5); border-radius: 4px; padding: 2px 8px; font-size: 10px; cursor: pointer; }

.bottom {
  position: absolute; bottom: 0; left: 0; right: 0;
  background: rgba(8,8,16,0.92); backdrop-filter: blur(8px);
  border-top: 1px solid rgba(255,255,255,0.06); padding: 8px 12px; z-index: 10;
}
.bm { display: flex; gap: 6px; }
.bi {
  flex: 1; background: rgba(255,255,255,0.06); border: 1px solid rgba(255,255,255,0.1);
  border-radius: 6px; padding: 7px 10px; color: #fff; font-size: 13px; font-family: inherit;
}
.bi::placeholder { color: rgba(255,255,255,0.25); }
.bi:focus { outline: none; border-color: #4fc3f7; }
.bb {
  background: #4fc3f7; color: #000; border: none; border-radius: 6px;
  padding: 7px 12px; font-size: 12px; cursor: pointer; font-weight: 600; white-space: nowrap;
}
.bb:disabled { opacity: 0.35; }
.bt { display: flex; gap: 6px; align-items: center; margin-top: 6px; flex-wrap: wrap; }
.btb {
  background: rgba(255,255,255,0.04); border: 1px solid rgba(255,255,255,0.08);
  border-radius: 4px; padding: 3px 9px; font-size: 11px; cursor: pointer; color: rgba(255,255,255,0.5);
}
.btb:hover { background: rgba(255,255,255,0.1); }
.btb:disabled { opacity: 0.3; }
.bt-hint { font-size: 10px; color: #ff5252; margin-left: auto; }
.bt-hint.region-name { color: #4fc3f7; margin-left: 0; }

.slide-enter-active, .slide-leave-active { transition: all 0.2s ease; }
.slide-enter-from, .slide-leave-to { opacity: 0; transform: translateY(12px); }
</style>
