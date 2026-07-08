const DB_NAME = 'ts2_cache'
const DB_VERSION = 1
const STORE_NAME = 'cache'

interface CacheEntry {
  key: string
  data: unknown
  timestamp: number
}

function openDB(): Promise<IDBDatabase> {
  return new Promise((resolve, reject) => {
    const req = indexedDB.open(DB_NAME, DB_VERSION)
    req.onupgradeneeded = () => {
      const db = req.result
      if (!db.objectStoreNames.contains(STORE_NAME)) {
        db.createObjectStore(STORE_NAME, { keyPath: 'key' })
      }
    }
    req.onsuccess = () => resolve(req.result)
    req.onerror = () => reject(req.error)
  })
}

async function getCache(key: string): Promise<{ data: unknown; timestamp: number } | null> {
  try {
    const db = await openDB()
    return new Promise((resolve, reject) => {
      const tx = db.transaction(STORE_NAME, 'readonly')
      const store = tx.objectStore(STORE_NAME)
      const req = store.get(key)
      req.onsuccess = () => {
        const entry = req.result as CacheEntry | undefined
        resolve(entry ? { data: entry.data, timestamp: entry.timestamp } : null)
      }
      req.onerror = () => reject(req.error)
      tx.oncomplete = () => db.close()
    })
  } catch {
    return null
  }
}

async function setCache(key: string, data: unknown): Promise<void> {
  try {
    const db = await openDB()
    return new Promise((resolve, reject) => {
      const tx = db.transaction(STORE_NAME, 'readwrite')
      const store = tx.objectStore(STORE_NAME)
      store.put({ key, data, timestamp: Date.now() })
      tx.oncomplete = () => { db.close(); resolve() }
      tx.onerror = () => reject(tx.error)
    })
  } catch { /* silent */ }
}

async function clearCache(): Promise<void> {
  try {
    const db = await openDB()
    return new Promise((resolve, reject) => {
      const tx = db.transaction(STORE_NAME, 'readwrite')
      const store = tx.objectStore(STORE_NAME)
      store.clear()
      tx.oncomplete = () => { db.close(); resolve() }
      tx.onerror = () => reject(tx.error)
    })
  } catch { /* silent */ }
}

async function deleteCache(key: string): Promise<void> {
  try {
    const db = await openDB()
    return new Promise((resolve, reject) => {
      const tx = db.transaction(STORE_NAME, 'readwrite')
      const store = tx.objectStore(STORE_NAME)
      store.delete(key)
      tx.oncomplete = () => { db.close(); resolve() }
      tx.onerror = () => reject(tx.error)
    })
  } catch { /* silent */ }
}

const CACHE_KEYS = {
  TASKS: 'tasks',
  COURSES: 'courses',
  COURSE_PROGRESS: 'course_progress:',
  BOOKMARKS: 'bookmarks',
  PROJECTS: 'projects',
  STATS: 'stats',
  PUSH_DASHBOARD: 'push_dashboard',
  BOOTSTRAP: 'bootstrap',
  FILE_CONTENT: 'file_content:',
  DIR_LISTING: 'dir_listing:',
  NOTEBOOK: 'notebook:',
  NOTEBOOK_LIST: 'notebook_list',
}

// 缓存过期时间配置（毫秒）
const CACHE_TTL: Record<string, number> = {
  tasks: 5 * 60 * 1000,           // 5 分钟
  courses: 10 * 60 * 1000,        // 10 分钟
  bookmarks: 10 * 60 * 1000,      // 10 分钟
  projects: 10 * 60 * 1000,       // 10 分钟
  stats: 30 * 60 * 1000,          // 30 分钟
  push_dashboard: 5 * 60 * 1000,  // 5 分钟
  bootstrap: 30 * 60 * 1000,      // 30 分钟
  file_content: 30 * 60 * 1000,   // 30 分钟
  dir_listing: 2 * 60 * 1000,     // 2 分钟
  notebook: 10 * 60 * 1000,       // 10 分钟
  notebook_list: 5 * 60 * 1000,   // 5 分钟
}

function courseProgressKey(courseId: string): string {
  return CACHE_KEYS.COURSE_PROGRESS + courseId
}

function isStale(timestamp: number, maxAgeMs: number = 5 * 60 * 1000): boolean {
  return Date.now() - timestamp > maxAgeMs
}

export function useOfflineCache() {
  async function getTaskCache() {
    const entry = await getCache(CACHE_KEYS.TASKS)
    return entry ? entry.data : null
  }

  async function setTaskCache(data: unknown) {
    await setCache(CACHE_KEYS.TASKS, data)
  }

  async function invalidateTaskCache() {
    await deleteCache(CACHE_KEYS.TASKS)
  }

  async function getCourseCache() {
    const entry = await getCache(CACHE_KEYS.COURSES)
    return entry ? entry.data : null
  }

  async function setCourseCache(data: unknown) {
    await setCache(CACHE_KEYS.COURSES, data)
  }

  async function getCourseProgressCache(courseId: string) {
    const entry = await getCache(courseProgressKey(courseId))
    return entry ? entry.data : null
  }

  async function setCourseProgressCache(courseId: string, data: unknown) {
    await setCache(courseProgressKey(courseId), data)
  }

  async function invalidateCourseProgressCache(courseId: string) {
    await deleteCache(courseProgressKey(courseId))
  }

  async function getBookmarkCache() {
    const entry = await getCache(CACHE_KEYS.BOOKMARKS)
    return entry ? entry.data : null
  }

  async function setBookmarkCache(data: unknown) {
    await setCache(CACHE_KEYS.BOOKMARKS, data)
  }

  async function getProjectCache() {
    const entry = await getCache(CACHE_KEYS.PROJECTS)
    return entry ? entry.data : null
  }

  async function setProjectCache(data: unknown) {
    await setCache(CACHE_KEYS.PROJECTS, data)
  }

  async function getStatsCache() {
    const entry = await getCache(CACHE_KEYS.STATS)
    return entry ? entry.data : null
  }

  async function setStatsCache(data: unknown) {
    await setCache(CACHE_KEYS.STATS, data)
  }

  async function getPushDashboardCache() {
    const entry = await getCache(CACHE_KEYS.PUSH_DASHBOARD)
    return entry ? entry.data : null
  }

  async function setPushDashboardCache(data: unknown) {
    await setCache(CACHE_KEYS.PUSH_DASHBOARD, data)
  }

  async function getBootstrapCache() {
    const entry = await getCache(CACHE_KEYS.BOOTSTRAP)
    return entry ? entry.data : null
  }

  async function setBootstrapCache(data: unknown) {
    await setCache(CACHE_KEYS.BOOTSTRAP, data)
  }

  async function fillAllFromBootstrap(bootstrapData: Record<string, unknown>) {
    const promises: Promise<void>[] = []
    if (bootstrapData.tasks) promises.push(setCache(CACHE_KEYS.TASKS, bootstrapData.tasks))
    if (bootstrapData.courses) promises.push(setCache(CACHE_KEYS.COURSES, bootstrapData.courses))
    if (bootstrapData.bookmarks) promises.push(setCache(CACHE_KEYS.BOOKMARKS, bootstrapData.bookmarks))
    if (bootstrapData.projects) promises.push(setCache(CACHE_KEYS.PROJECTS, bootstrapData.projects))
    if (bootstrapData.agent) promises.push(setCache('agent', bootstrapData.agent))
    if (bootstrapData.push_dashboard) promises.push(setCache(CACHE_KEYS.PUSH_DASHBOARD, bootstrapData.push_dashboard))
    promises.push(setCache(CACHE_KEYS.BOOTSTRAP, bootstrapData))
    await Promise.allSettled(promises)
  }

  async function isOnline(): Promise<boolean> {
    try {
      const baseURL = (await import('../api')).getServerURL()
      if (!baseURL) return false
      const res = await fetch(`${baseURL}/api/system/version`, {
        method: 'POST',
        signal: AbortSignal.timeout(3000),
      })
      return res.ok
    } catch {
      return false
    }
  }

  async function isStaleCache(key: string, maxAgeMs?: number): Promise<boolean> {
    const entry = await getCache(key)
    if (!entry) return true
    return isStale(entry.timestamp, maxAgeMs)
  }

  // ─── 带过期检查的缓存读取 ────────────────────────────

  async function getCacheWithTTL<T>(key: string, fallback: () => Promise<T>): Promise<T> {
    const prefix = key.split(':')[0]
    const ttl = CACHE_TTL[prefix] || 5 * 60 * 1000
    const entry = await getCache(key)
    if (entry && !isStale(entry.timestamp, ttl)) {
      return entry.data as T
    }
    // 缓存不存在或已过期，从网络获取
    const data = await fallback()
    await setCache(key, data)
    return data
  }

  // ─── 文件内容缓存 ────────────────────────────

  function fileContentKey(path: string): string {
    return CACHE_KEYS.FILE_CONTENT + path
  }

  async function getFileContentCache(path: string): Promise<string | null> {
    const entry = await getCache(fileContentKey(path))
    return entry ? (entry.data as string) : null
  }

  async function setFileContentCache(path: string, content: string): Promise<void> {
    await setCache(fileContentKey(path), content)
  }

  async function invalidateFileContentCache(path: string): Promise<void> {
    await deleteCache(fileContentKey(path))
  }

  // ─── 目录列表缓存 ────────────────────────────

  function dirListingKey(path: string): string {
    return CACHE_KEYS.DIR_LISTING + path
  }

  async function getDirListingCache(path: string): Promise<any[] | null> {
    const entry = await getCache(dirListingKey(path))
    return entry ? (entry.data as any[]) : null
  }

  async function setDirListingCache(path: string, entries: any[]): Promise<void> {
    await setCache(dirListingKey(path), entries)
  }

  async function invalidateDirListingCache(path: string): Promise<void> {
    await deleteCache(dirListingKey(path))
  }

  // ─── 笔记本缓存 ────────────────────────────

  function notebookKey(id: string): string {
    return CACHE_KEYS.NOTEBOOK + id
  }

  async function getNotebookCache(id: string): Promise<any | null> {
    const entry = await getCache(notebookKey(id))
    return entry ? entry.data : null
  }

  async function setNotebookCache(id: string, data: any): Promise<void> {
    await setCache(notebookKey(id), data)
  }

  async function invalidateNotebookCache(id: string): Promise<void> {
    await deleteCache(notebookKey(id))
  }

  async function getNotebookListCache(): Promise<any[] | null> {
    const entry = await getCache(CACHE_KEYS.NOTEBOOK_LIST)
    return entry ? (entry.data as any[]) : null
  }

  async function setNotebookListCache(list: any[]): Promise<void> {
    await setCache(CACHE_KEYS.NOTEBOOK_LIST, list)
  }

  // ─── 批量清理过期缓存 ────────────────────────────

  async function pruneStaleEntries(): Promise<number> {
    try {
      const db = await openDB()
      return new Promise((resolve, reject) => {
        const tx = db.transaction(STORE_NAME, 'readwrite')
        const store = tx.objectStore(STORE_NAME)
        const req = store.openCursor()
        let pruned = 0
        req.onsuccess = (event: any) => {
          const cursor = event.target.result
          if (cursor) {
            const entry = cursor.value as CacheEntry
            const prefix = entry.key.split(':')[0]
            const ttl = CACHE_TTL[prefix]
            if (ttl && isStale(entry.timestamp, ttl)) {
              cursor.delete()
              pruned++
            }
            cursor.continue()
          }
        }
        tx.oncomplete = () => { db.close(); resolve(pruned) }
        tx.onerror = () => reject(tx.error)
      })
    } catch {
      return 0
    }
  }

  // ─── 离线操作队列 ────────────────────────────

  interface QueuedMutation {
    id: number
    key: string  // 缓存 key（用于失效）
    url: string  // API 路径
    body: unknown
    timestamp: number
  }

  const QUEUE_KEY = 'offline_queue'
  let _queueIdCounter = 0

  async function initQueueIdCounter() {
    const queue = await getQueue()
    _queueIdCounter = queue.reduce((max, m) => Math.max(max, m.id), 0)
  }
  initQueueIdCounter()

  async function pushMutation(key: string, url: string, body: unknown): Promise<void> {
    const queue = await getQueue()
    queue.push({ id: ++_queueIdCounter, key, url, body, timestamp: Date.now() })
    await setCache(QUEUE_KEY, queue)
  }

  async function getQueue(): Promise<QueuedMutation[]> {
    const entry = await getCache(QUEUE_KEY)
    return (entry?.data as QueuedMutation[]) ?? []
  }

  let _axiosInstance: any = null
  async function _getAxios() {
    if (!_axiosInstance) {
      const mod = await import('axios')
      _axiosInstance = mod.default
    }
    return _axiosInstance
  }

  async function flushQueue(): Promise<{ ok: number; fail: number }> {
    const queue = await getQueue()
    if (!queue.length) return { ok: 0, fail: 0 }
    const axios = await _getAxios()
    const { getServerURL } = await import('../api')
    const base = getServerURL().replace(/\/+$/, '')
    const remaining: QueuedMutation[] = []
    let ok = 0
    for (const m of queue) {
      try {
        await axios.post(`${base}${m.url}`, m.body, { timeout: 10000 })
        await deleteCache(m.key)
        ok++
      } catch {
        remaining.push(m)
      }
    }
    if (remaining.length === 0) await deleteCache(QUEUE_KEY)
    else await setCache(QUEUE_KEY, remaining)
    return { ok, fail: remaining.length }
  }

  async function queueLength(): Promise<number> {
    return (await getQueue()).length
  }

  return {
    getTaskCache, setTaskCache, invalidateTaskCache,
    getCourseCache, setCourseCache,
    getCourseProgressCache, setCourseProgressCache, invalidateCourseProgressCache,
    getBookmarkCache, setBookmarkCache,
    getProjectCache, setProjectCache,
    getStatsCache, setStatsCache,
    getPushDashboardCache, setPushDashboardCache,
    getBootstrapCache, setBootstrapCache,
    fillAllFromBootstrap,
    isOnline, clearCache, deleteCache, isStaleCache,
    getCacheWithTTL,
    getFileContentCache, setFileContentCache, invalidateFileContentCache,
    getDirListingCache, setDirListingCache, invalidateDirListingCache,
    getNotebookCache, setNotebookCache, invalidateNotebookCache,
    getNotebookListCache, setNotebookListCache,
    pruneStaleEntries,
    pushMutation, flushQueue, queueLength,
  }
}
