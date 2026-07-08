<template>
  <div class="diag-panel">
    <div class="diag-tabs">
      <button v-for="t in tabs" :key="t.key" class="diag-tab" :class="{ active: activeTab === t.key }" @click="activeTab = t.key">{{ t.label }}</button>
    </div>

    <div v-if="activeTab === 'logs'" class="diag-body">
      <div class="diag-toolbar">
        <input v-model="logFilter" placeholder="过滤..." class="diag-filter" />
        <span class="diag-count">{{ filteredLogs.length }} / {{ logs.length }}</span>
        <button class="diag-btn" @click="logs.length = 0">清空</button>
      </div>
      <div class="diag-scroll" ref="logScroll">
        <div v-for="(log, i) in filteredLogs" :key="i" class="diag-line">{{ log }}</div>
      </div>
    </div>

    <div v-if="activeTab === 'network'" class="diag-body">
      <div class="diag-toolbar">
        <span class="diag-count">{{ networkRequests.length }} 个请求</span>
        <button class="diag-btn" @click="networkRequests.length = 0">清空</button>
      </div>
      <div class="diag-scroll">
        <div v-for="(req, i) in networkRequests" :key="i" class="diag-req">
          <span class="diag-req-method" :class="req.method">{{ req.method }}</span>
          <span class="diag-req-url">{{ req.url }}</span>
          <span class="diag-req-status" :class="{ ok: req.status < 400, err: req.status >= 400 }">{{ req.status }}</span>
          <span class="diag-req-time">{{ req.duration }}ms</span>
        </div>
      </div>
    </div>

    <div v-if="activeTab === 'errors'" class="diag-body">
      <div class="diag-toolbar">
        <span class="diag-count">{{ extractionErrors.length }} 个抽取错误</span>
        <button class="diag-btn" @click="extractionErrors.length = 0">清空</button>
      </div>
      <div class="diag-scroll">
        <div v-for="(err, i) in extractionErrors" :key="i" class="diag-err">{{ err }}</div>
      </div>
    </div>

    <div v-if="activeTab === 'stats'" class="diag-body">
      <div class="diag-stats-grid">
        <div class="diag-stat"><span class="diag-stat-label">加载次数</span><span class="diag-stat-val">{{ stats.loadCount }}</span></div>
        <div class="diag-stat"><span class="diag-stat-label">播放次数</span><span class="diag-stat-val">{{ stats.playCount }}</span></div>
        <div class="diag-stat"><span class="diag-stat-label">搜索次数</span><span class="diag-stat-val">{{ stats.searchCount }}</span></div>
        <div class="diag-stat"><span class="diag-stat-label">重试次数</span><span class="diag-stat-val">{{ stats.retryCount }}</span></div>
        <div class="diag-stat"><span class="diag-stat-label">错误次数</span><span class="diag-stat-val">{{ stats.errorCount }}</span></div>
        <div class="diag-stat"><span class="diag-stat-label">IndexedDB 大小</span><span class="diag-stat-val">{{ stats.dbSize }}</span></div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, reactive, onMounted, nextTick } from 'vue'
import { debugLogs, pushDebugLog } from '../api'

const tabs = [
  { key: 'logs', label: '日志' },
  { key: 'network', label: '网络' },
  { key: 'errors', label: '抽取错误' },
  { key: 'stats', label: '统计' },
] as const

const activeTab = ref<(typeof tabs)[number]['key']>('logs')
const logFilter = ref('')
const logScroll = ref<HTMLElement | null>(null)

const logs = debugLogs as unknown as string[]

const filteredLogs = computed(() => {
  if (!logFilter.value) return logs
  const f = logFilter.value.toLowerCase()
  return logs.filter(l => l.toLowerCase().includes(f))
})

const networkRequests = ref<{ method: string; url: string; status: number; duration: number }[]>([])

const extractionErrors = ref<string[]>([])

const stats = reactive({
  loadCount: 0,
  playCount: 0,
  searchCount: 0,
  retryCount: 0,
  errorCount: 0,
  dbSize: '计算中...',
})

async function estimateDbSize() {
  try {
    if (!indexedDB) return
    const dbs = await indexedDB.databases()
    const db = dbs.find(d => d.name === 'ts2_app')
    if (!db) { stats.dbSize = '0 B'; return }
    const req = indexedDB.open('ts2_app', 1)
    req.onsuccess = () => {
      const conn = req.result
      let total = 0
      for (const name of conn.objectStoreNames) {
        const tx = conn.transaction(name)
        const store = tx.objectStore(name)
        const countReq = store.count()
        countReq.onsuccess = () => { total += countReq.result }
      }
      setTimeout(() => {
        stats.dbSize = total > 0 ? `${total} 条记录` : '空'
      }, 500)
    }
    req.onerror = () => { stats.dbSize = '未知' }
  } catch { stats.dbSize = '不可用' }
}

onMounted(() => {
  estimateDbSize()
})

function recordNetwork(method: string, url: string, status: number, duration: number) {
  networkRequests.value.unshift({ method, url, status, duration })
  if (networkRequests.value.length > 200) networkRequests.value.length = 200
}

function recordExtractionError(err: string) {
  extractionErrors.value.unshift(err)
  if (extractionErrors.value.length > 100) extractionErrors.value.length = 100
}

function recordStat(key: keyof typeof stats) {
  if (key === 'loadCount') stats.loadCount++
  else if (key === 'playCount') stats.playCount++
  else if (key === 'searchCount') stats.searchCount++
  else if (key === 'retryCount') stats.retryCount++
  else if (key === 'errorCount') stats.errorCount++
}

window.__TS2_DIAG__ = { recordNetwork, recordExtractionError, recordStat }
</script>

<style scoped>
.diag-panel { font-family: monospace; font-size: 11px; color: var(--fg); }
.diag-tabs { display: flex; border-bottom: 1px solid var(--border); }
.diag-tab { flex: 1; padding: 6px 8px; background: none; border: none; border-bottom: 2px solid transparent; color: var(--fg-muted); cursor: pointer; font-size: 11px; }
.diag-tab.active { color: var(--accent); border-bottom-color: var(--accent); }
.diag-body { padding: 4px 0; }
.diag-toolbar { display: flex; gap: 4px; align-items: center; padding: 4px 8px; border-bottom: 1px solid var(--border); }
.diag-filter { flex: 1; background: var(--bg-secondary); border: 1px solid var(--border); border-radius: 4px; padding: 2px 6px; color: var(--fg); font-size: 11px; }
.diag-count { color: var(--fg-muted); font-size: 10px; }
.diag-btn { background: var(--bg-secondary); border: 1px solid var(--border); border-radius: 4px; padding: 2px 8px; color: var(--fg-muted); cursor: pointer; font-size: 10px; }
.diag-btn:hover { border-color: var(--accent); }
.diag-scroll { max-height: 300px; overflow-y: auto; padding: 4px 8px; }
.diag-line { padding: 2px 0; color: var(--fg-muted); word-break: break-all; border-bottom: 1px solid var(--border); }
.diag-req { display: flex; gap: 6px; padding: 2px 0; align-items: center; border-bottom: 1px solid var(--border); }
.diag-req-method { font-weight: 600; min-width: 40px; }
.diag-req-method.GET { color: #27ae60; }
.diag-req-method.POST { color: #2980b9; }
.diag-req-method.PUT { color: #e67e22; }
.diag-req-method.DELETE { color: #e74c3c; }
.diag-req-url { flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; color: var(--fg-muted); }
.diag-req-status { font-weight: 600; min-width: 32px; }
.diag-req-status.ok { color: #27ae60; }
.diag-req-status.err { color: #e74c3c; }
.diag-req-time { min-width: 50px; text-align: right; color: var(--fg-muted); }
.diag-err { padding: 2px 0; color: #e67e22; word-break: break-all; border-bottom: 1px solid var(--border); }
.diag-stats-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 4px; padding: 8px; }
.diag-stat { display: flex; justify-content: space-between; padding: 6px 8px; background: var(--bg-secondary); border-radius: 4px; }
.diag-stat-label { color: var(--fg-muted); }
.diag-stat-val { font-weight: 600; color: var(--fg); }
</style>
