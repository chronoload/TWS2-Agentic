<template>
  <div class="app">
    <!-- 连接状态提示条（仅在 server_disconnected 时显示） -->
    <div v-if="appMode === 'server_disconnected'" class="disconnected-banner">
      <span>⚠️ 服务器连接已断开</span>
      <router-link to="/settings" class="banner-link">前往设置重新连接</router-link>
    </div>

    <main class="app-content">
      <PushDashboard />
      <router-view />
    </main>

    <!-- 提醒 toast -->
    <Teleport to="body">
      <div v-if="reminderToast.show" class="reminder-toast" @click="dismissReminder">
        <span class="reminder-toast-icon">⏰</span>
        <span class="reminder-toast-text">{{ reminderToast.title }}</span>
        <button class="reminder-toast-close" @click.stop="dismissReminder">✕</button>
      </div>
    </Teleport>

  <div class="debug-panel" v-if="showDebug">
    <div class="debug-header" @click="showDebug = !showDebug">
      <span>🐞 调试日志</span>
  	<button @click.stop="clearDebugLogs">清空</button>
    </div>
    <div class="debug-body" ref="debugBody">
      <div v-for="(log, idx) in debugLogs" :key="idx" class="debug-line">{{ log }}</div>
    </div>
  </div>

    <nav class="bottom-nav">
      <div class="nav-section-status">
        <span v-if="appMode === 'server_disconnected'" class="offline-badge" @click="refreshFromServer">离线</span>
        <span v-else-if="lastCacheTime" class="cache-badge" title="可离线查看">{{ formatCacheTime(lastCacheTime) }}</span>
      </div>
      <router-link to="/files" class="nav-item" active-class="active">
        <span class="nav-icon">📁</span>
        <span class="nav-label">文件</span>
      </router-link>
      <router-link to="/tasks" class="nav-item" active-class="active">
        <span class="nav-icon">✅</span>
        <span class="nav-label">任务</span>
      </router-link>
      <router-link to="/bookmarks" class="nav-item" active-class="active">
        <span class="nav-icon">🔖</span>
        <span class="nav-label">书签</span>
      </router-link>
      <router-link to="/projects" class="nav-item" active-class="active">
        <span class="nav-icon">🚀</span>
        <span class="nav-label">项目</span>
      </router-link>
      <router-link to="/courses" class="nav-item" active-class="active">
        <span class="nav-icon">📚</span>
        <span class="nav-label">课程</span>
      </router-link>
      <router-link to="/timetable" class="nav-item" active-class="active">
        <span class="nav-icon">📅</span>
        <span class="nav-label">课表</span>
      </router-link>
      <router-link to="/execution" class="nav-item" active-class="active">
        <span class="nav-icon">▶️</span>
        <span class="nav-label">执行</span>
      </router-link>
      <router-link to="/slides" class="nav-item" active-class="active">
        <span class="nav-icon">📝</span>
        <span class="nav-label">笔记</span>
      </router-link>
      <router-link to="/agent" class="nav-item" active-class="active">
        <span class="nav-icon">🤖</span>
        <span class="nav-label">Agent</span>
      </router-link>
      <router-link to="/ecosystem" class="nav-item" active-class="active">
        <span class="nav-icon">🌱</span>
        <span class="nav-label">生态</span>
      </router-link>
      <router-link to="/game" class="nav-item" active-class="active">
        <span class="nav-icon">🎮</span>
        <span class="nav-label">游戏</span>
      </router-link>
      <router-link to="/videos" class="nav-item" active-class="active">
         <span class="nav-icon">🎬</span>
         <span class="nav-label">视频</span>
       </router-link>
      <router-link to="/resources" class="nav-item" active-class="active">
        <span class="nav-icon">📚</span>
        <span class="nav-label">资源</span>
      </router-link>
      <router-link to="/stats" class="nav-item" active-class="active">
        <span class="nav-icon">📊</span>
        <span class="nav-label">统计</span>
      </router-link>
      <router-link to="/settings" class="nav-item" active-class="active">
        <span class="nav-icon">⚙️</span>
        <span class="nav-label">设置</span>
      </router-link>
      <div class="nav-item" @click="showDebug = !showDebug">
 	<span class="nav-icon">🐞</span>
  	<span class="nav-label">调试</span>
      </div>
    </nav>
  </div>



</template>

<script setup lang="ts">
import { ref, onMounted, onUnmounted, onErrorCaptured, nextTick } from 'vue'
import api, { 
  getServerURL, 
  setServerURL, 
  testServerConnection, 
  isNativeApp, 
  mobileBootstrap, 
  getAuthInfo, 
  setAuthErrorCallback,
  loginAuth,          // ← 新增
  getAuthCode,        // ← 新增
  getApiToken,        // ← 新增
  setCredentials      // ← 新增
} from './api'
import { reconnectWebSocket } from './composables/useWebSocket'
import { useAppMode } from './composables/useAppMode'
import { useOfflineCache } from './stores/offlineCache'
import { useTasksStore } from './stores/tasks'
import { useTimetableStore } from './stores/timetable'
import PushDashboard from './components/PushDashboard.vue'
import { debugLogs, pushDebugLog } from './api'
import { injectErrorStyles, showErrorSnackbar, showErrorDialog, AppError, withRetry, debugToast } from './utils/error'

const { appMode, setAppMode } = useAppMode()

const online = ref(true)
const lastCacheTime = ref(0)

// 全局 Promise rejection 处理
window.addEventListener('unhandledrejection', (ev) => {
  pushDebugLog(`[UnhandledRejection] ${(ev.reason as any)?.message || ev.reason}`)
  if (!(ev.reason instanceof AppError)) {
    showErrorSnackbar((ev.reason as any)?.message || '未处理的 Promise 拒绝')
  }
})

// 全局图片加载失败处理（B站 CDN 需要 Referer 头，WebView <img> 不会有）
document.addEventListener('error', async (ev) => {
  const img = ev.target as HTMLImageElement | null
  if (!img || img.tagName !== 'IMG' || !img.src || img.src.startsWith('blob:') || img.src.startsWith('data:')) return
  let orig = img.getAttribute('data-orig-src') || img.src

  // 如果 orig 是代理 URL，提取原始 URL
  const proxyPrefix = '/proxy?url='
  if (orig.startsWith('http://127.0.0.1:') && orig.includes(proxyPrefix)) {
    const idx = orig.indexOf(proxyPrefix)
    if (idx >= 0) {
      const encoded = orig.substring(idx + proxyPrefix.length)
      try {
        orig = decodeURIComponent(encoded)
      } catch {}
    }
  }

  if (img.getAttribute('data-retry')) return
  img.setAttribute('data-retry', '1')
  pushDebugLog(`[ImgErr] ${img.src} → original: ${orig}`)
  // 直接走桥接预加载（CORS fetch 在 WebView 中必定失败，跳过）
  try {
    const { api: pipeApi } = await import('./plugins/bridge')
    const pre = await pipeApi.preloadImage(orig)
    if (pre.localUrl && pre.localUrl !== orig) { img.src = pre.localUrl; return }
  } catch {}
  img.style.display = 'none'
  pushDebugLog(`[ImgErr] 无法加载: ${orig}`)
}, true)

// 全局错误边界
onErrorCaptured((err, instance, info) => {
  pushDebugLog(`[ErrorBoundary] ${info}: ${(err as any)?.message || err}`)
  if (err instanceof AppError) {
    showErrorDialog(err)
  } else {
    showErrorSnackbar((err as any)?.message || String(err))
  }
  return false
})



const showDebug = ref(true)
const debugBody = ref<HTMLElement | null>(null)


function clearDebugLogs() {
  debugLogs.length = 0   // 清空数组，不重新赋值
}

// 提醒 toast
const reminderToast = ref({ show: false, title: '', id: '' })
let _reminderToastTimer: ReturnType<typeof setTimeout> | null = null
let _onlineCheckTimer: ReturnType<typeof setInterval> | null = null
// 全局暴露离线状态给各视图（server_disconnected 视为离线）
window.__TS2_OFFLINE__ = online

let _autoConnectDone = false

// ─── 连接逻辑 ────────────────────────────────

onMounted(async () => {
  injectErrorStyles()
  debugToast('TS2 已启动 — DB/选择器/Toast 就绪', 4000)
  // 初始化主题
  const savedTheme = localStorage.getItem('ts2_theme')
  if (savedTheme) {
    document.documentElement.setAttribute('data-theme', savedTheme)
  }
 // 添加调试面板的监听
  window.addEventListener('ts2-debug-update', () => {
    nextTick(() => {
      if (debugBody.value) {
        debugBody.value.scrollTop = 0
      }
    })
  })
  // 注册鉴权错误回调：仅在 server_connected 时触发
  setAuthErrorCallback(() => {
    if (appMode.value !== 'server_connected') return
    setAppMode('server_disconnected')
    online.value = false
  })

  // ─── 提醒检测 ────────────────────────────
  const taskStore = useTasksStore()
  // 浏览器中 Notification.requestPermission() 需用户手势触发，惰性等待首次点击
  const _lazyPerm = () => {
    taskStore.requestNotifyPermission()
    window.removeEventListener('click', _lazyPerm)
  }
  window.addEventListener('click', _lazyPerm, { once: true })
  // 重启后重新调度所有原生提醒
  taskStore.scheduleNativeReminders()
  // 监听应用内提醒事件
  window.addEventListener('ts2-reminder', ((e: CustomEvent) => {
    const { title } = e.detail
    reminderToast.value = { show: true, title, id: e.detail.id }
    if (_reminderToastTimer) clearTimeout(_reminderToastTimer)
    _reminderToastTimer = setTimeout(() => {
      reminderToast.value.show = false
    }, 5000)
  }) as EventListener)
  // 每30秒检测一次提醒
  setInterval(() => {
    taskStore.checkReminders()
  }, 30000)
  // 首次立即检测
  setTimeout(() => taskStore.checkReminders(), 2000)

  // ─── 浏览器网络状态监听 ────────────────────────────
  window.addEventListener('online', () => {
    pushDebugLog('[Network] 网络已恢复')
    showErrorSnackbar('网络已恢复', { duration: 3000 })
    if (appMode.value === 'server_disconnected') tryAutoConnect(getServerURL() || window.location.origin)
  })
  window.addEventListener('offline', () => {
    pushDebugLog('[Network] 网络已断开')
    showErrorNotification('网络断开', '部分功能可能不可用')
    setAppMode('server_disconnected')
    online.value = false
  })

  // Capacitor 原生：后台尝试连接已保存服务器（不阻塞）
  if (isNativeApp()) {
    const savedURL = getServerURL()
    if (savedURL) {
      tryAutoConnect(savedURL)
    }
  }
  // 浏览器：后台尝试同源服务器
  else {
    tryAutoConnect(window.location.origin)
  }
})

async function tryAutoConnect(url: string) {
  if (_autoConnectDone) return
  try {
    const ok = await testServerConnection(url)
    if (!ok) return
    const info = await getAuthInfo(url)
    if (!info.needAuth) {
      await _enterServerMode(url)
      return
    }
    if (isNativeApp()) {
      const code = getAuthCode()
      const token = getApiToken()
      if (code || token) {
        const loginResult = await loginAuth(code, token, url)
        if (loginResult.ok) {
          setCredentials(code, token)
          await _enterServerMode(url)
          return
        } else {
          // 自动登录失败，静默记录日志，不弹窗
          console.warn('自动登录失败:', loginResult.detail)
          // 可以根据 errorType 决定是否重试或提示用户去设置页
          // 保持 local 模式，用户可手动在设置页连接
          return
        }
      }
    }
  } catch {
    // 静默失败
  }
}

async function _enterServerMode(url: string) {
  _autoConnectDone = true
  setAppMode('server_connected')
  online.value = true
  setServerURL(url)
  // 同步切换各 store 到服务端数据源
  const tasksStore = useTasksStore()
  const timetableStore = useTimetableStore()
  await Promise.all([tasksStore.switchToServer(), timetableStore.switchToServer()])
  reconnectWebSocket()
  fillCache()
  startOnlineCheck()
}

function dismissReminder() {
  reminderToast.value.show = false
  if (_reminderToastTimer) {
    clearTimeout(_reminderToastTimer)
    _reminderToastTimer = null
  }
}

// ─── 离线缓存 ────────────────────────────────

async function fillCache() {
  const cache = useOfflineCache()
  try {
    const res = await mobileBootstrap()
    const data: any = res.data?.data ?? res.data
    if (data) {
      window.__TS2_BOOTSTRAP__ = data
      await cache.fillAllFromBootstrap(data as Record<string, unknown>)
      lastCacheTime.value = Date.now()
    }
  } catch { /* 后台静默填充 */ }
}

async function flushPendingMutations() {
  const cache = useOfflineCache()
  const qLen = await cache.queueLength()
  if (qLen === 0) return
  const { ok } = await cache.flushQueue()
  if (ok > 0) {
    lastCacheTime.value = Date.now()
    // 刷新最新数据到缓存
    fillCache()
  }
}

function startOnlineCheck() {
  if (_onlineCheckTimer) clearInterval(_onlineCheckTimer)
  _onlineCheckTimer = setInterval(async () => {
    if (appMode.value !== 'server_connected') return
    try {
      await api.get('/api/system/version')
      // disconnected → connected（类型已收敛）
      setAppMode('server_connected')
      online.value = true
    } catch {
      setAppMode('server_disconnected')
      online.value = false
    }
  }, 15000)
}

async function refreshFromServer() {
  if (appMode.value !== 'server_connected' && appMode.value !== 'server_disconnected') return
  setAppMode('server_disconnected')
  online.value = false
  await flushPendingMutations()
  await fillCache()
  setAppMode('server_connected')
  online.value = true
}

function formatCacheTime(ts: number): string {
  const diffMin = Math.floor((Date.now() - ts) / 60000)
  if (diffMin < 1) return '刚刚缓存'
  if (diffMin < 60) return `${diffMin}分钟前缓存`
  const diffHr = Math.floor(diffMin / 60)
  if (diffHr < 24) return `${diffHr}小时前缓存`
  return `${Math.floor(diffHr / 24)}天前缓存`
}

// ─── 生命周期 ────────────────────────────────

onUnmounted(() => {
  if (_onlineCheckTimer) clearInterval(_onlineCheckTimer)
})

</script>

<style scoped>
.app {
  display: flex;
  flex-direction: column;
  min-height: 100vh;
  min-height: 100dvh;
}

.app-content {
  flex: 1;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  position: relative;
}

.bottom-nav {
  position: fixed;
  bottom: 0;
  left: 0;
  right: 0;
  display: flex;
  justify-content: flex-start;
  align-items: center;
  height: 56px;
  background: var(--bg-secondary);
  border-top: 1px solid var(--border);
  z-index: 100;
  overflow-x: auto;
  -webkit-overflow-scrolling: touch;
  scrollbar-width: none;
  padding-left: 8px;
}

.nav-section-status {
  flex-shrink: 0;
  margin-right: 2px;
}

.offline-badge {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  font-size: 10px;
  font-weight: 600;
  color: var(--danger);
  border: 1px solid var(--danger);
  border-radius: 10px;
  padding: 2px 8px;
  cursor: pointer;
  white-space: nowrap;
  transition: all 0.2s;
}

.offline-badge:hover {
  background: var(--danger);
  color: var(--bg);
}

.cache-badge {
  font-size: 9px;
  color: var(--fg-muted);
  white-space: nowrap;
  padding: 2px 6px;
  cursor: default;
}

.bottom-nav::-webkit-scrollbar {
  display: none;
}

.nav-item {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 1px;
  text-decoration: none;
  color: var(--fg-muted);
  font-size: 10px;
  padding: 4px 6px;
  border-radius: 6px;
  transition: color 0.2s, background 0.2s;
  flex-shrink: 0;
}

.nav-item.active { color: var(--accent); }
.nav-icon { font-size: 18px; line-height: 1; }
.nav-label { line-height: 1.2; }

.disconnected-banner {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 8px 16px;
  background: rgba(239, 68, 68, 0.1);
  border-bottom: 1px solid rgba(239, 68, 68, 0.3);
  font-size: 13px;
  color: #ef4444;
}

.banner-link {
  color: var(--accent);
  text-decoration: underline;
  cursor: pointer;
  margin-left: auto;
  font-size: 12px;
}

/* 提醒 toast */
.reminder-toast {
  position: fixed;
  top: 16px;
  left: 50%;
  transform: translateX(-50%);
  z-index: 999;
  display: flex;
  align-items: center;
  gap: 8px;
  background: var(--bg-secondary);
  border: 1px solid var(--accent);
  border-radius: 10px;
  padding: 10px 16px;
  box-shadow: 0 4px 20px rgba(0,0,0,0.4);
  animation: reminderSlideIn 0.3s ease;
  max-width: 90vw;
  cursor: pointer;
}

@keyframes reminderSlideIn {
  from { opacity: 0; transform: translateX(-50%) translateY(-20px); }
  to { opacity: 1; transform: translateX(-50%) translateY(0); }
}

.reminder-toast-icon {
  font-size: 20px;
  flex-shrink: 0;
}

.reminder-toast-text {
  font-size: 14px;
  font-weight: 600;
  color: var(--fg);
  flex: 1;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.reminder-toast-close {
  background: transparent;
  border: none;
  color: var(--fg-muted);
  font-size: 14px;
  cursor: pointer;
  padding: 2px 4px;
  flex-shrink: 0;
}

.reminder-toast-close:hover {
  color: var(--fg);
}
.debug-panel {
  position: fixed;
  bottom: 80px;
  left: 8px;
  right: 8px;
  max-height: 40vh;
  background: rgba(0,0,0,0.9);
  color: #0f0;
  font-family: monospace;
  font-size: 11px;
  border-radius: 8px;
  padding: 8px;
  overflow: hidden;
  z-index: 9999;
  border: 1px solid #333;
}
.debug-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  cursor: pointer;
  padding-bottom: 4px;
  border-bottom: 1px solid #333;
  margin-bottom: 4px;
}
.debug-body {
  max-height: calc(40vh - 40px);
  overflow-y: auto;
  white-space: pre-wrap;
  word-break: break-all;
}
.debug-line {
  padding: 2px 0;
  border-bottom: 1px solid rgba(255,255,255,0.05);
}

</style>







