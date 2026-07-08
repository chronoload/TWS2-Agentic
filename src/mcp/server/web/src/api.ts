import { Capacitor } from '@capacitor/core'

// 调试日志收集器（供界面显示）
export const debugLogs: string[] = []
export function pushDebugLog(msg: string) {
  const timestamp = new Date().toISOString().slice(11, 23)
  debugLogs.unshift(`[${timestamp}] ${msg}`)
  if (debugLogs.length > 200) debugLogs.length = 200 // 限制数量
  // 触发自定义事件，通知界面更新
  if (typeof window !== 'undefined') {
    window.dispatchEvent(new CustomEvent('ts2-debug-update'))
  }
}
import axios from 'axios'

// 离线缓存模块（延迟加载）
let _offlineCache: any = null
async function _getCache() {
  if (isNativeApp()) return { getCache: async () => null, setCache: async () => {}, deleteCache: async () => {}, pushMutation: async () => {}, getTaskCache: async () => null, setTaskCache: async () => {}, invalidateTaskCache: async () => {}, getFileContentCache: async () => null, setFileContentCache: async () => {}, invalidateFileContentCache: async () => {}, getDirListingCache: async () => null, setDirListingCache: async () => {} }
  if (!_offlineCache) {
    const mod = await import('./stores/offlineCache')
    _offlineCache = mod.useOfflineCache()
  }
  return _offlineCache
}

function _isOffline(): boolean {
  return (window as any).__TS2_OFFLINE__?.value === false
}

// 带缓存的 API 包装：在线时请求+缓存，离线时读缓存
async function _withCache<T>(
  fetcher: () => Promise<{ data: any }>,
  cacheGetter: () => Promise<T | null>,
  cacheSetter: (data: T) => Promise<void>,
): Promise<{ data: any }> {
  if (_isOffline()) {
    const cached = await cacheGetter()
    return { data: cached ?? [] }
  }
  try {
    const res = await fetcher()
    const data = res.data?.data ?? res.data
    if (data !== undefined && data !== null) {
      await cacheSetter(data as T)
    }
    return res
  } catch {
    const cached = await cacheGetter()
    if (cached !== null) return { data: cached }
    throw new Error('Server unreachable')
  }
}

// 带缓存的写操作：在线时请求+失效缓存，离线时入队+失效缓存
async function _writeWithCache(
  cacheKey: string,  // 要失效的缓存 key
  url: string,       // API 路径
  body: unknown,
): Promise<{ data: any }> {
  const cache = await _getCache()
  if (_isOffline()) {
    await cache.deleteCache(cacheKey)
    await cache.pushMutation(cacheKey, url, body)
    return { data: { ok: true, queued: true } }
  }
  try {
    const res = await api.post(url, body)
    await cache.deleteCache(cacheKey)
    return res
  } catch {
    await cache.pushMutation(cacheKey, url, body)
    return { data: { ok: true, queued: true } }
  }
}

// 在 Capacitor 原生环境中，自动检测服务器地址
// 参考 siyuan-android：App 启动时连接本地内核服务器
function getServerBaseURL(): string {
  // 如果在浏览器中直接访问服务器（非 Capacitor），用相对路径
  if (window.location.protocol === 'http:' || window.location.protocol === 'https:') {
    return ''
  }
  // Capacitor 原生环境（file:// 协议）：从 localStorage 读取
  const savedURL = localStorage.getItem('ts2_server_url')
  if (savedURL) return savedURL

  // 没有默认地址，返回空，由连接界面处理
  return ''
}

// 原生环境（Android）绕过 IndexedDB 缓存，直接调 API

// ─── 鉴权管理（token + auth_code 分离，后端为与逻辑） ─────

const AUTH_CODE_KEY = 'ts2_auth_code'
const API_TOKEN_KEY = 'ts2_api_token'

export function getAuthCode(): string {
  return localStorage.getItem(AUTH_CODE_KEY) || ''
}
export function setCredentials(code: string, token: string) {
  pushDebugLog(`setCredentials: code=${code ? '***' : '空'}, token=${token ? '***' : '空'}`)
  if (code) localStorage.setItem(AUTH_CODE_KEY, code)
  if (token) localStorage.setItem(API_TOKEN_KEY, token)
  pushDebugLog(`localStorage 写入后: token=${localStorage.getItem(API_TOKEN_KEY) ? '存在' : '不存在'}`)
}

export function getApiToken(): string {
  const token = localStorage.getItem(API_TOKEN_KEY) || ''
  pushDebugLog(`getApiToken: ${token ? '存在 (长度 ' + token.length + ')' : '不存在'}`)
  return token
}
export function clearAuth() {
  localStorage.removeItem(AUTH_CODE_KEY)
  localStorage.removeItem(API_TOKEN_KEY)
}

export interface AuthInfo {
  needAuth: boolean
  hasAuthCode: boolean
  hasToken: boolean
  local: boolean
}

/** 检查服务器是否需要鉴权（用 axios 避免 CORS/fetch 问题） */
function _makeURL(baseURL: string, path: string): string {
  return `${baseURL.replace(/\/+$/, '')}${path}`
}

export async function getAuthInfo(baseURL?: string): Promise<AuthInfo> {
  const url = '/api/system/authInfo'
  if (baseURL) {
    const res = await axios.get(_makeURL(baseURL, url))
    const j = res.data
    return j.data ?? j
  }
  const res = await api.get(url)
  const j = res.data
  return j.data ?? j
}

/** 诊断登录全过程：测试 CORS / 网络 / 服务端，返回详细诊断文本 */
export async function diagnoseLogin(code: string, token: string, baseURL: string): Promise<string[]> {
  const lines: string[] = []
  const ts = (label: string) => lines.push(`[${new Date().toISOString().slice(11,19)}] ${label}`)
  try {
    ts(`平台: ${window.location.protocol === 'file:' ? 'Capacitor file://' : '浏览器 ' + window.location.origin}`)
    ts(`目标: ${baseURL}`)
    ts(`凭据: code=${code ? code.slice(0,3)+'***' : '(空)'} token=${token ? token.slice(0,3)+'***' : '(空)'}`)
    ts(`localStorage: code=${(localStorage.getItem('ts2_auth_code')||'').slice(0,3)+'***'} token=${(localStorage.getItem('ts2_api_token')||'').slice(0,3)+'***'}`)
  } catch {}

  // step 1: 基本连通性
  try {
    const u = _makeURL(baseURL, '/api/system/version')
    ts(`① 测试连通 ${u}`)
    const r = await fetch(u, { method: 'POST', signal: AbortSignal.timeout(5000) })
    ts(`   → status ${r.status} ${r.statusText}`)
    const j = await r.json()
    ts(`   → body code=${j.code}`)
  } catch (e: any) {
    ts(`   ⚠ 失败: ${e?.message || e}`)
  }

  // step 2: authInfo（无凭据）
  try {
    const u = _makeURL(baseURL, '/api/system/authInfo')
    ts(`② 查询 authInfo ${u}`)
    const r = await axios.get(u, { validateStatus: () => true })
    ts(`   → status ${r.status}, body=${JSON.stringify(r.data).slice(0,200)}`)
  } catch (e: any) {
    ts(`   ⚠ 失败: ${e?.message || e}`)
  }

  // step 3: loginAuth OPTIONS 预检（模拟浏览器 CORS 行为）
  try {
    const u = _makeURL(baseURL, '/api/system/loginAuth')
    ts(`③ OPTIONS ${u}`)
    const r = await fetch(u, {
      method: 'OPTIONS',
      headers: { 'Content-Type': 'application/json' },
    })
    const corsACAO = r.headers.get('Access-Control-Allow-Origin') || '(无)'
    const corsACAC = r.headers.get('Access-Control-Allow-Credentials') || '(无)'
    const corsACAM = r.headers.get('Access-Control-Allow-Methods') || '(无)'
    const corsACAH = r.headers.get('Access-Control-Allow-Headers') || '(无)'
    ts(`   ← status ${r.status}`)
    ts(`   ← ACAO=${corsACAO} ACAC=${corsACAC}`)
    ts(`   ← ACAM=${corsACAM} ACAH=${corsACAH}`)
    ts(`   ← Cookie in response: ${r.headers.get('set-cookie') || '(无)'}`)
  } catch (e: any) {
    ts(`   ⚠ CORS 预检失败: ${e?.message || e}`)
  }

  // step 4: 实际 loginAuth POST（携带凭据）
  try {
    const u = _makeURL(baseURL, '/api/system/loginAuth')
    ts(`④ POST ${u}`)
    const r = await axios.post(u, { code, token }, {
      withCredentials: window.location.protocol !== 'file:',
    })
    ts(`   → status ${r.status}, body=${JSON.stringify(r.data).slice(0,200)}`)
    ts(`   → Set-Cookie: ${(r.headers as any)['set-cookie'] || JSON.stringify(r.headers).slice(0,200)}`)
  } catch (e: any) {
    ts(`   ⚠ 登录失败`)
    ts(`   → message: ${e?.message || e}`)
    if (e?.response) {
      ts(`   → status: ${e.response.status}`)
      ts(`   → body: ${JSON.stringify(e.response.data).slice(0,200)}`)
    }
    if (e?.request) {
      ts(`   → request sent: yes (but no response — likely CORS/NetworkError)`)
    }
    if (e?.code === 'ERR_NETWORK') {
      ts(`   → CORS 被浏览器拦截: 服务端拒绝 Origin 或 credentials 不兼容`)
    }
  }
  return lines
}

export interface LoginResult {
  ok: boolean
  detail?: string
  errorType?: 'network' | 'cors' | 'timeout' | 'server' | 'auth_failed' | 'unknown'
  status?: number
}

/** 登录鉴权（code=授权码, token=API Token，后端与逻辑） */
export async function loginAuth(code: string, token: string, baseURL?: string): Promise<LoginResult> {
  const isFile = window.location.protocol === 'file:'
  try {
    let res: any
    if (baseURL) {
      const url = `${baseURL.replace(/\/+$/, '')}/api/system/loginAuth`
      const headers: Record<string, string> = { 'Content-Type': 'application/json' }
      if (isFile) {
        if (token) headers['Authorization'] = `Token ${token}`
        if (code) headers['X-Auth-Code'] = code
      }
      res = await axios.post(url, { code, token }, {
        withCredentials: !isFile,
        headers,
        timeout: 10000,
      })
    } else {
      res = await api.post('/api/system/loginAuth', { code, token })
    }

    const d = res.data
    if (d && d.code === 0) {
      return { ok: true }
    }
    const detail = d ? `服务器返回 code=${d.code}, msg=${d.msg}` : `响应格式异常: ${JSON.stringify(res.data).slice(0, 200)}`
    return { ok: false, detail, errorType: 'auth_failed', status: res.status }
  } catch (e: any) {
        let errorType: LoginResult['errorType'] = 'unknown'
        let detail = ''
        let status: number | undefined

        if (e.code === 'ECONNABORTED' || e.message?.includes('timeout')) {
            errorType = 'timeout'
            detail = '连接超时，请检查服务器是否正常运行或网络是否畅通'
        } else if (e.message?.includes('NetworkError') || e.message?.includes('Failed to fetch') || e.code === 'ERR_NETWORK') {
            errorType = 'network'
            detail = '网络请求失败，可能原因：\n- 服务器未启动\n- IP地址或端口不正确\n- 防火墙阻止了连接\n- CORS策略拦截（请检查服务器CORS设置）'
            if (isFile) {
                detail += '\n- Capacitor环境下，请确保服务器地址与设备IP正确'
            }
        } else if (e.response) {
            status = e.response.status
            const body = JSON.stringify(e.response.data || {}).slice(0, 200)
            if (status !== undefined) {
                if (status === 401) {
                    errorType = 'auth_failed'
                    detail = `鉴权失败 (401): 请检查授权码或Token是否正确${body ? '\n' + body : ''}`
                } else if (status === 403) {
                    errorType = 'auth_failed'
                    detail = `访问被拒绝 (403): 无权访问该工作区${body ? '\n' + body : ''}`
                } else if (status >= 500) {
                    errorType = 'server'
                    detail = `服务器内部错误 (${status})${body ? '\n' + body : ''}`
                } else {
                    errorType = 'server'
                    detail = `请求失败 (${status})${body ? '\n' + body : ''}`
                }
            } else {
                errorType = 'server'
                detail = `请求失败（状态码未知）${body ? '\n' + body : ''}`
            }
        } else if (e.request) {
            errorType = 'network'
            detail = '请求已发出但未收到响应，可能由于CORS策略阻止或服务器无响应'
        } else {
            detail = e.message || '未知错误'
        }

        return { ok: false, detail, errorType, status }
    }
}

/** 登出 */
export async function logoutAuth(): Promise<void> {
  try {
    await api.post('/api/system/logoutAuth')
  } catch { /* ignore */ }
  clearAuth()
}

const api = axios.create({
  baseURL: getServerBaseURL(),
  timeout: 30000,
  // 浏览器（含同域/跨域）：withCredentials=true，配合服务端反射 Origin + credentials
  // Capacitor file://：不应尝试带 cookie（没有），设为 false 避免 WebView 额外 CORS 校验
  withCredentials: window.location.protocol !== 'file:',
})

// 请求拦截：仅 Capacitor file:// 加 header 鉴权（无 cookie）
// 浏览器：依赖 HttpOnly cookie（安全，防 XSS），不发送原始凭据
api.interceptors.request.use((config) => {
  // 服务器地址检查（只在 Capacitor 环境下需要）
  if (!api.defaults.baseURL && window.location.protocol === 'file:') {
    return Promise.reject(new Error('Server not configured'))
  }
  // 所有环境统一添加 token（如果存在）
  const token = getApiToken()
  if (token && !config.headers['Authorization']) {
    config.headers['Authorization'] = `Token ${token}`
  }
  // 不需要添加 X-Auth-Code
  return config
})

let _authErrorCallback: (() => void) | null = null

export function setAuthErrorCallback(cb: () => void) {
  _authErrorCallback = cb
}

// 响应拦截：401/403 自动触发鉴权回调
api.interceptors.response.use(
  (response) => {
    // 某些后端在 200 中返回 code !== 0
    if (response.data && response.data.code === 401) {
      clearAuth()
      if (_authErrorCallback) _authErrorCallback()
      return Promise.reject(new Error(response.data.msg || '未授权'))
    }
    return response
  },
  (error) => {
    if (error.response) {
      const status = error.response.status
      if (status === 401 || status === 403) {
        clearAuth()
        if (_authErrorCallback) _authErrorCallback()
      }
    }
    return Promise.reject(error)
  }
)

// 获取当前服务器基础 URL（用于构造直接下载链接）
function getBaseURL(): string {
  const base = api.defaults.baseURL || ''
  return base.replace(/\/+$/, '')
}

// 触发文件下载：统一走 fetch + blob，带上鉴权 header（避免 <a> 标签不带鉴权）
export async function downloadFile(filePath: string) {
  const base = getBaseURL()
  const url = `${base}/api/file/download/${encodeURIComponent(filePath)}`
  const token = getApiToken()
  const code = getAuthCode()
  const headers: Record<string, string> = {}
  if (token) headers['Authorization'] = `Token ${token}`
  if (code) headers['X-Auth-Code'] = code
  try {
    const res = await fetch(url, { headers })
    if (!res.ok) throw new Error(`下载失败: ${res.status}`)
    const blob = await res.blob()
    const objUrl = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = objUrl
    a.download = filePath.split('/').pop() || filePath
    a.style.display = 'none'
    document.body.appendChild(a)
    a.click()
    document.body.removeChild(a)
    setTimeout(() => URL.revokeObjectURL(objUrl), 60000)
  } catch (e) {
    console.error('下载文件失败:', e)
  }
}

// 服务器地址管理
export function getServerURL(): string {
  return api.defaults.baseURL || ''
}

export function setServerURL(url: string) {
  const baseURL = url.endsWith('/') ? url.slice(0, -1) : url
  api.defaults.baseURL = baseURL
  localStorage.setItem('ts2_server_url', baseURL)
}

export function isNativeApp(): boolean {
  if (typeof window !== 'undefined' && window.location.protocol === 'file:') return true
  try { return Capacitor.isNativePlatform() } catch { return false }
}

export async function testServerConnection(url: string): Promise<boolean> {
  try {
    const testURL = url.endsWith('/') ? url.slice(0, -1) : url
    const res = await fetch(`${testURL}/api/system/version`, {
      method: 'POST',
      signal: AbortSignal.timeout(5000),
    })
    const data = await res.json()
    return data.code === 0
  } catch {
    return false
  }
}

// 文件操作
export async function getFile(path: string) {
  if (isNativeApp()) return api.post('/api/file/getFile', { path })
  const cache = await _getCache()
  return _withCache(
    () => api.post('/api/file/getFile', { path }),
    () => cache.getFileContentCache(path),
    (d) => cache.setFileContentCache(path, typeof d === 'string' ? d : JSON.stringify(d)),
  )
}

export async function putFile(path: string, content: string) {
  if (isNativeApp()) return api.post('/api/file/putFile', { path, content })
  const cache = await _getCache()
  // 写入成功后失效对应缓存
  try {
    const res = await api.post('/api/file/putFile', { path, content })
    await cache.invalidateFileContentCache(path)
    return res
  } catch {
    // 离线时入队
    await cache.invalidateFileContentCache(path)
    await cache.pushMutation('file_content:' + path, '/api/file/putFile', { path, content })
    return { data: { ok: true, queued: true } }
  }
}

export async function readDir(path: string = '') {
  if (isNativeApp()) return api.post('/api/file/readDir', { path })
  const cache = await _getCache()
  return _withCache(
    () => api.post('/api/file/readDir', { path }),
    () => cache.getDirListingCache(path),
    (d) => cache.setDirListingCache(path, d as any[]),
  )
}

export function search(query: string) {
  return api.post('/api/file/search', { query })
}

export function upload(formData: FormData) {
  return api.post('/api/file/upload', formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
  })
}

export function removeFile(path: string) {
  return api.post('/api/file/removeFile', { path })
}

export function renameFile(oldPath: string, newPath: string) {
  return api.post('/api/file/renameFile', { old_path: oldPath, new_path: newPath })
}

// 任务
export async function getTasks() {
  const cache = await _getCache()
  return _withCache(
    () => api.post('/api/data/tasks', {}),
    () => cache.getTaskCache(),
    (d) => cache.setTaskCache(d),
  )
}

export async function updateTask(id: string, data: Record<string, unknown>) {
  return _writeWithCache('tasks', '/api/data/tasks/update', { id, ...data })
}

export async function createTask(data: Record<string, unknown>) {
  return _writeWithCache('tasks', '/api/data/tasks/create', data)
}

export async function deleteTask(id: string) {
  return _writeWithCache('tasks', '/api/data/tasks/delete', { id })
}

// 课程
export async function getCourses() {
  const cache = await _getCache()
  return _withCache(
    () => api.post('/api/data/courses', {}),
    () => cache.getCourseCache(),
    (d) => cache.setCourseCache(d),
  )
}

export async function getCourseProgress(courseId: string) {
  const cache = await _getCache()
  return _withCache(
    () => api.post('/api/data/courses/progress', { course_id: courseId }),
    () => cache.getCourseProgressCache(courseId),
    (d) => cache.setCourseProgressCache(courseId, d),
  )
}

export async function updateLessonStatus(courseId: string, lessonNumber: number, status: string) {
  const cache = await _getCache()
  const cacheKey = 'course_progress:' + courseId
  if (_isOffline()) {
    await cache.deleteCache(cacheKey)
    await cache.pushMutation(cacheKey, '/api/data/courses/lessonStatus', { course_id: courseId, lesson_number: lessonNumber, status })
    return { data: { ok: true, queued: true } }
  }
  try {
    const res = await api.post('/api/data/courses/lessonStatus', { course_id: courseId, lesson_number: lessonNumber, status })
    await cache.deleteCache(cacheKey)
    return res
  } catch {
    await cache.pushMutation(cacheKey, '/api/data/courses/lessonStatus', { course_id: courseId, lesson_number: lessonNumber, status })
    return { data: { ok: true, queued: true } }
  }
}

// 书签
export async function getBookmarks() {
  const cache = await _getCache()
  return _withCache(
    () => api.post('/api/data/bookmarks', {}),
    () => cache.getBookmarkCache(),
    (d) => cache.setBookmarkCache(d),
  )
}

// 资源索引
export function getResources(query: string = '') {
  const url = query ? `/api/data/resources?query=${encodeURIComponent(query)}` : '/api/data/resources'
  return api.get(url)
}

export function getCourseResources(courseId: string) {
  return api.get(`/api/data/resources/${encodeURIComponent(courseId)}`)
}

// 项目
export async function getProjects() {
  const cache = await _getCache()
  return _withCache(
    () => api.post('/api/data/projects', {}),
    () => cache.getProjectCache(),
    (d) => cache.setProjectCache(d),
  )
}

export function readProjectDir(path: string = '') {
  return api.post('/api/data/projects/readDir', { path })
}

export function readProjectFile(path: string) {
  return api.post('/api/data/projects/readFile', { path })
}

// Agent
// Agent 聊天（非流式）
export function agentChat(message: string, context?: Record<string, unknown>, sessionId?: string) {
  return api.post('/api/agent/chat', { message, context, session_id: sessionId || '' })
}

// 网络设置（参考思源笔记的网络访问控制）
export function getNetworkSettings() {
  return api.post('/api/system/getNetworkSettings', {})
}

export function setNetworkSettings(settings: { allow_lan?: boolean; allow_public_network?: boolean; allow_usb?: boolean }) {
  return api.post('/api/system/setNetworkSettings', settings)
}

export function configureFirewall(allow: boolean = true) {
  return api.post('/api/system/configureFirewall', { allow })
}

export function setNetworkPrivate() {
  return api.post('/api/system/setNetworkPrivate', {})
}

export function checkNetworkAccess() {
  return api.post('/api/system/checkNetworkAccess', {})
}

// ─── FRP 隧道 API ───────────────────────────────────────

export function tunnelStatus() {
  return api.get('/api/tunnel/status')
}

export function tunnelStart() {
  return api.post('/api/tunnel/start', {})
}

export function tunnelStop() {
  return api.post('/api/tunnel/stop', {})
}

export function tunnelRestart() {
  return api.post('/api/tunnel/restart', {})
}

export function tunnelSettingsGet() {
  return api.get('/api/tunnel/settings')
}

export function tunnelSettingsUpdate(settings: Record<string, unknown>) {
  return api.post('/api/tunnel/settings', settings)
}

// 统计
export async function getStats() {
  const cache = await _getCache()
  return _withCache(
    () => api.get('/api/system/stats'),
    () => cache.getStatsCache(),
    (d) => cache.setStatsCache(d),
  )
}

// Agent 流式聊天（SSE）
export function agentChatStream(_message: string, _context?: Record<string, unknown>): EventSource | null {
  // SSE 需要 GET 请求，但我们需要 POST body，所以用 fetch + ReadableStream
  return null // 不用 EventSource，在组件中用 fetch
}

// Agent 流式聊天（fetch + ReadableStream）
export async function agentChatStreamFetch(
  message: string,
  context: Record<string, unknown> | undefined,
  onToken: (token: string) => void,
  onToolCall: (name: string, args: Record<string, unknown>) => void,
  onToolResult: (name: string, result: string, checkpointHash?: string) => void,
  onDone: (reply: string) => void,
  onError: (err: string) => void,
  sessionId?: string,
  attachments?: Record<string, unknown>[],
): Promise<AbortController> {
  const controller = new AbortController()
  const baseURL = api.defaults.baseURL || ''
  const url = `${baseURL}/api/agent/chat/stream`

  try {
    const payload: Record<string, unknown> = { message, context, session_id: sessionId || '' }
    if (attachments && attachments.length > 0) payload.attachments = attachments
    const headers: Record<string, string> = { 'Content-Type': 'application/json' }
    const token = getApiToken()
    if (token) {
    headers['Authorization'] = `Token ${token}`
    }
    const response = await fetch(url, {
      method: 'POST',
      headers,
      body: JSON.stringify(payload),
      signal: controller.signal,
    })

    if (!response.ok || !response.body) {
      onError(`HTTP ${response.status}`)
      return controller
    }


    const reader = response.body.getReader()
    const decoder = new TextDecoder()
    let buffer = ''

    while (true) {
      const { done, value } = await reader.read()
      if (done) break

      buffer += decoder.decode(value, { stream: true })

      // 按 \n\n 分割 SSE 事件块
      while (true) {
        const eventEnd = buffer.indexOf('\n\n')
        if (eventEnd === -1) break
        const eventBlock = buffer.substring(0, eventEnd)
        buffer = buffer.substring(eventEnd + 2)

        const lines = eventBlock.split('\n')
        for (const line of lines) {
          if (!line.startsWith('data: ')) continue
          const data = line.slice(6).trim()
          if (data === '[DONE]') {
            // 流结束：确保 onDone 被调用（如果之前没有收到 done 事件）
            onDone('')
            return controller
          }
          try {
            const msg = JSON.parse(data)
            if (msg.type === 'token') onToken(msg.content || '')
            else if (msg.type === 'tool_call') onToolCall(msg.name, msg.args || {})
            else if (msg.type === 'tool_result') onToolResult(msg.name, msg.result || '', msg.checkpoint_hash || '')
            else if (msg.type === 'done') onDone(msg.content || '')
            else if (msg.type === 'error') onError(msg.content || '未知错误')
          } catch { /* ignore parse error */ }
        }
      }
    }
  } catch (e: any) {
    if (e.name !== 'AbortError') onError(e.message || '网络错误')
  }

  return controller
}

// 移动端启动引导（一次请求获取所有模块数据）
export function mobileBootstrap() {
  return api.get('/api/mobile/bootstrap')
}

// Agent 状态
export function getAgentStatus() {
  return api.get('/api/agent/status')
}

// Agent 重置
export function resetAgent() {
  return api.post('/api/agent/reset')
}

// Agent 会话管理
export function getAgentSessions() {
  return api.get('/api/agent/sessions')
}

export function createAgentSession() {
  return api.post('/api/agent/sessions/create')
}

export function switchAgentSession(sessionId: string) {
  return api.post('/api/agent/sessions/switch', { session_id: sessionId })
}

export function deleteAgentSession(sessionId: string) {
  return api.post('/api/agent/sessions/delete', { session_id: sessionId })
}

// Agent 检查点管理
export function getAgentCheckpoints(sessionId?: string) {
  const params = sessionId ? `?session_id=${encodeURIComponent(sessionId)}` : ''
  return api.get(`/api/agent/checkpoints${params}`)
}

export function getAgentCheckpointDiff(commitHash: string) {
  return api.get(`/api/agent/checkpoints/${commitHash}/diff`)
}

export function restoreAgentCheckpoint(commitHash: string, restoreType: string) {
  return api.post(`/api/agent/checkpoints/${commitHash}/restore`, { restore_type: restoreType })
}

// 推送
export async function getPushDashboard() {
  const cache = await _getCache()
  return _withCache(
    () => api.get('/api/push/dashboard'),
    () => cache.getPushDashboardCache(),
    (d) => cache.setPushDashboardCache(d),
  )
}

// ─── 数据同步 API ─────────────────────────────────────

export function syncFull(tasks: any[], bookmarks: any[], projects: any[] = []) {
  return api.post('/api/sync/full', { tasks, bookmarks, projects })
}

export function syncCompare(tasks: any[], bookmarks: any[], projects: any[] = []) {
  return api.post('/api/sync/compare', { tasks, bookmarks, projects })
}

export function syncPush(tasks: any[], bookmarks: any[], projects: any[] = []) {
  return api.post('/api/sync/push', { tasks, bookmarks, projects })
}

// ─── 关键路径检测 ──────────────────────────────────────────

export function criticalPath() {
  return api.get('/api/tasks/critical-path')
}

// ─── 多实例集群 ──────────────────────────────────────────

// ─── 分页笔记 API ──────────────────────────────────────────

export async function listNotebooks() {
  const cache = await _getCache()
  return _withCache(
    () => api.get('/api/notebooks'),
    () => cache.getNotebookListCache(),
    (d) => cache.setNotebookListCache(d as any[]),
  )
}

export async function getNotebook(notebookId: string) {
  const cache = await _getCache()
  return _withCache(
    () => api.get(`/api/notebooks/${notebookId}`),
    () => cache.getNotebookCache(notebookId),
    (d) => cache.setNotebookCache(notebookId, d),
  )
}

export async function saveNotebook(notebookId: string, data: Record<string, unknown>) {
  const cache = await _getCache()
  try {
    const res = await api.post(`/api/notebooks/${notebookId}`, data)
    await cache.invalidateNotebookCache(notebookId)
    await cache.invalidateFileContentCache(`Notes/${data.title || 'notebook'}.md`)
    return res
  } catch {
    await cache.invalidateNotebookCache(notebookId)
    await cache.pushMutation('notebook:' + notebookId, `/api/notebooks/${notebookId}`, data)
    return { data: { ok: true, queued: true } }
  }
}

export async function deleteNotebook(notebookId: string) {
  const cache = await _getCache()
  try {
    const res = await api.delete(`/api/notebooks/${notebookId}`)
    await cache.invalidateNotebookCache(notebookId)
    return res
  } catch {
    await cache.invalidateNotebookCache(notebookId)
    await cache.pushMutation('notebook:' + notebookId, `/api/notebooks/${notebookId}`, { _method: 'DELETE' })
    return { data: { ok: true, queued: true } }
  }
}

export function clusterInstances() {
  return api.get('/api/cluster/instances')
}

export function clusterRemoteReadDir(remoteUrl: string, path: string = '') {
  return api.post('/api/cluster/remote/readDir', { remote_url: remoteUrl, path })
}

export function clusterRemoteSearch(remoteUrl: string, query: string, subdir: string = '') {
  return api.post('/api/cluster/remote/search', { remote_url: remoteUrl, query, subdir })
}

export function clusterTransfer(remoteUrl: string, remotePath: string, localPath?: string) {
  return api.post('/api/cluster/transfer', {
    remote_url: remoteUrl,
    remote_path: remotePath,
    local_path: localPath || remotePath,
  })
}

export function clusterTransferBatch(remoteUrl: string, files: Array<{ remote_path: string; local_path?: string }>) {
  return api.post('/api/cluster/transfer/batch', { remote_url: remoteUrl, files })
}

// ─── PDF 智能阅读 API ──────────────────────────────────────

export function pdfExtract(filePath: string) {
  return api.post('/api/pdf/extract', { file_path: filePath })
}

export function pdfIndex(filePath: string) {
  return api.post('/api/pdf/index', { file_path: filePath })
}

export function pdfQuery(query: string, topK: number = 4) {
  return api.post('/api/pdf/query', { query, top_k: topK })
}

export function pdfChat(message: string, context?: Record<string, unknown>) {
  return api.post('/api/pdf/chat', { message, context })
}

// ─── Swarm API ──────────────────────────────────────────────

export function swarmGetAgents() {
  return api.get('/api/swarm/agents')
}

export function swarmGetAgentDetail(agentName: string) {
  return api.get(`/api/swarm/agents/${encodeURIComponent(agentName)}`)
}

export function swarmRunAgent(agentName: string, prompt: string, background: boolean = false) {
  return api.post('/api/swarm/run', { agent_name: agentName, prompt, background })
}

export function swarmCancelAgent(agentName: string) {
  return api.post(`/api/swarm/cancel/${encodeURIComponent(agentName)}`)
}

export function swarmGetTasks() {
  return api.get('/api/swarm/tasks')
}

export function swarmPollTask(taskId: string) {
  return api.post(`/api/swarm/poll/${encodeURIComponent(taskId)}`)
}

export function swarmEnableCluster(reason: string) {
  return api.post('/api/swarm/enable', { reason })
}

export function swarmDisableCluster() {
  return api.post('/api/swarm/disable')
}

// ─── Ecosystem API ──────────────────────────────────────────

export function ecoState() {
  return api.get('/api/ecosystem/state')
}

export function ecoNeighborhood(conceptId?: string) {
  const params = conceptId ? `?concept_id=${encodeURIComponent(conceptId)}` : ''
  return api.get(`/api/ecosystem/neighborhood${params}`)
}

export function ecoRecord(text: string) {
  return api.post('/api/ecosystem/record', { text })
}

export function ecoDive(conceptId: string) {
  return api.post('/api/ecosystem/dive', { concept_id: conceptId })
}

export function ecoCross(conceptIdA: string, conceptIdB: string) {
  return api.post('/api/ecosystem/cross', { concept_id_a: conceptIdA, concept_id_b: conceptIdB })
}

export function ecoExpress(conceptIds: string[]) {
  return api.post('/api/ecosystem/express', { concept_ids: conceptIds })
}

export function ecoTick() {
  return api.post('/api/ecosystem/tick')
}

export function ecoInspirations() {
  return api.get('/api/ecosystem/inspirations')
}

export function ecoObserve() {
  return api.post('/api/ecosystem/observe')
}

export function ecoSpeciationScan() {
  return api.post('/api/ecosystem/speciation-scan')
}

export function ecoSync() {
  return api.post('/api/ecosystem/sync')
}

// ─── 课程表 API ──────────────────────────────────────────

export function getTimetables() {
  return api.get('/api/data/timetable')
}

export function createTimetable(name: string, semesterStart: string = '', semesterEnd: string = '') {
  return api.post('/api/data/timetable/create', { name, semester_start: semesterStart, semester_end: semesterEnd })
}

export function setActiveTimetable(timetableId: string) {
  return api.post('/api/data/timetable/setActive', { timetable_id: timetableId })
}

export function deleteTimetable(timetableId: string) {
  return api.post('/api/data/timetable/delete', { timetable_id: timetableId })
}

export function addTimetableSlot(data: {
  timetable_id?: string
  course_name: string
  day_of_week: number
  start_time: string
  end_time: string
  location?: string
  teacher?: string
  period_idx?: number
  color?: string
}) {
  return api.post('/api/data/timetable/slot/add', data)
}

export function deleteTimetableSlot(slotId: string, timetableId: string = '') {
  return api.post('/api/data/timetable/slot/delete', { slot_id: slotId, timetable_id: timetableId })
}

export default api









