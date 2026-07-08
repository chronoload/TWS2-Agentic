import { ref, onUnmounted } from 'vue'
import { getApiToken, getAuthCode } from '../api'

interface WSMessage {
  cmd: string
  data?: any
  msg?: string
  code?: number
}

const wsConnected = ref(false)
let ws: WebSocket | null = null
let reconnectTimer: ReturnType<typeof setTimeout> | null = null
let reconnectAttempts = 0
const BASE_RECONNECT_DELAY = 2000
const listeners: Array<(msg: WSMessage) => void> = []

function getReconnectDelay(): number {
  const delay = Math.min(BASE_RECONNECT_DELAY * Math.pow(1.5, reconnectAttempts), 30000)
  reconnectAttempts++
  return delay
}

function getWsURL(): string | null {
  const token = getApiToken()
  const code = getAuthCode()
  // 浏览器 WebSocket 不支持自定义 header；CORS 又让 Set-Cookie 在跨域场景失效
  // → 凭据必须放 query param 里，与后端 _check_ws_auth 配合
  const authQS: string[] = []
  if (token) authQS.push(`token=${encodeURIComponent(token)}`)
  if (code) authQS.push(`auth_code=${encodeURIComponent(code)}`)
  const authPart = authQS.length ? `&${authQS.join('&')}` : ''

  // Capacitor 原生环境（file:// 协议）：从 localStorage 读取服务器地址
  if (location.protocol === 'file:') {
    const savedURL = localStorage.getItem('ts2_server_url')
    if (!savedURL) return null
    try {
      const u = new URL(savedURL)
      const proto = u.protocol === 'https:' ? 'wss:' : 'ws:'
      return `${proto}//${u.host}/ws?app=ts2-vue&type=main${authPart}`
    } catch {
      return null
    }
  }
  // 浏览器环境：使用当前页面 host
  if (!location.host) return null
  const proto = location.protocol === 'https:' ? 'wss:' : 'ws:'
  return `${proto}//${location.host}/ws?app=ts2-vue&type=main${authPart}`
}

function connect() {
  const url = getWsURL()
  if (!url) {
    // 没有可用的服务器地址，延迟重试
    scheduleReconnect()
    return
  }

  try {
    ws = new WebSocket(url)
  } catch {
    scheduleReconnect()
    return
  }

  ws.onopen = () => {
    console.log('[WS] open', url.replace(/token=[^&]+/, 'token=***').replace(/auth_code=[^&]+/, 'auth_code=***'))
    wsConnected.value = true
    reconnectAttempts = 0
  }

  ws.onclose = (ev) => {
    console.log('[WS] close', { code: ev.code, reason: ev.reason, wasClean: ev.wasClean })
    wsConnected.value = false
    scheduleReconnect()
  }

  ws.onerror = (ev) => {
    console.warn('[WS] error', ev)
    wsConnected.value = false
  }

  ws.onmessage = (event) => {
    try {
      const msg: WSMessage = JSON.parse(event.data)
      console.debug('[WS] msg', msg.cmd)
      listeners.forEach(fn => fn(msg))
    } catch { /* ignore */ }
  }
}

function scheduleReconnect() {
  if (reconnectTimer) clearTimeout(reconnectTimer)
  const delay = getReconnectDelay()
  reconnectTimer = setTimeout(() => connect(), delay)
}

export function reconnectWebSocket() {
  if (ws && ws.readyState === WebSocket.OPEN) {
    ws.send(JSON.stringify({ cmd: 'ping', reqId: Date.now() }))
    return
  }
  if (ws) {
    try { ws.close() } catch { /* ignore */ }
    ws = null
  }
  reconnectAttempts = 0
  connect()
}

function send(cmd: string, param: Record<string, unknown> = {}) {
  if (ws && ws.readyState === WebSocket.OPEN) {
    ws.send(JSON.stringify({ cmd, reqId: Date.now(), param }))
  }
}

function addListener(fn: (msg: WSMessage) => void) {
  listeners.push(fn)
  return () => {
    const idx = listeners.indexOf(fn)
    if (idx >= 0) listeners.splice(idx, 1)
  }
}

// 延迟自动连接：等 DOM 就绪后再连接，避免模块初始化时 crash
if (typeof window !== 'undefined') {
  // 不在模块级立即 connect，而是等第一个 tick
  // Capacitor file:// 环境下，如果还没有保存的服务器地址，不连接
  setTimeout(() => {
    if (location.protocol === 'file:') {
      // 原生环境：只有保存了服务器地址才连接
      if (localStorage.getItem('ts2_server_url')) {
        connect()
      }
    } else if (location.host) {
      // 浏览器环境：直接连接
      connect()
    }
  }, 100)

  document.addEventListener('visibilitychange', () => {
    if (document.visibilityState === 'visible') {
      reconnectWebSocket()
    }
  })
}

export function useWebSocket() {
  const removeFns: Array<() => void> = []

  function onMessage(fn: (msg: WSMessage) => void) {
    const remove = addListener(fn)
    removeFns.push(remove)
  }

  onUnmounted(() => {
    removeFns.forEach(fn => fn())
  })

  return {
    wsConnected,
    send,
    onMessage,
    reconnectWebSocket,
  }
}
