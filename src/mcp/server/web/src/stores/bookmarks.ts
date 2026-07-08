import { defineStore } from 'pinia'
import { ref } from 'vue'

const LOCAL_KEY = 'ts2_bookmarks_cache'

export interface Bookmark {
  id: string
  name?: string
  title?: string
  url?: string
  link?: string
  category?: string
  group?: string
  icon?: string
}

export const useBookmarksStore = defineStore('bookmarks', () => {
  const bookmarks = ref<Bookmark[]>([])
  const loading = ref(false)

  function _saveCache() {
    try { localStorage.setItem(LOCAL_KEY, JSON.stringify(bookmarks.value)) } catch {}
  }
  function _loadCache() {
    try {
      const raw = localStorage.getItem(LOCAL_KEY)
      if (raw) bookmarks.value = JSON.parse(raw)
    } catch {}
  }

  async function load() {
    loading.value = true
    // 1. bootstrap 数据
    const bootstrap = (window as any).__TS2_BOOTSTRAP__
    if (bootstrap?.bookmarks) {
      bookmarks.value = Array.isArray(bootstrap.bookmarks) ? bootstrap.bookmarks : []
      _saveCache()
      delete bootstrap.bookmarks
      loading.value = false
      return
    }
    // 2. 本地缓存
    _loadCache()
    if (bookmarks.value.length > 0) {
      loading.value = false
    }
    // 3. 异步获取服务端最新数据（后端为 POST）
    try {
      const { default: api } = await import('../api')
      const res = await api.post('/api/data/bookmarks', {})
      const raw = res.data?.data ?? res.data ?? []
      const data = Array.isArray(raw) ? raw : (raw.bookmarks || raw.items || [])
      if (data.length > 0) {
        bookmarks.value = data
        _saveCache()
      }
    } catch { /* 保留缓存 */ }
    finally { loading.value = false }
  }

  async function add(bm: Omit<Bookmark, 'id'>): Promise<boolean> {
    try {
      const { default: api } = await import('../api')
      const res = await api.post('/api/data/bookmarks/add', { ...bm })
      if (res.status !== 200 || res.data?.code !== 0) return false
      if (res.data?.data?.id) {
        bookmarks.value.push(res.data.data)
      } else {
        await load()
      }
      _saveCache()
      return true
    } catch { return false }
  }

  async function remove(id: string): Promise<boolean> {
    try {
      const { default: api } = await import('../api')
      const res = await api.post('/api/data/bookmarks/delete', { id })
      if (res.status !== 200 || res.data?.code !== 0) return false
      bookmarks.value = bookmarks.value.filter((b: any) => b.id !== id && b.url !== id && b.link !== id)
      _saveCache()
      return true
    } catch { return false }
  }

  function byCategory(cat: string) {
    return bookmarks.value.filter((b: any) => (b.category || b.group || '') === cat)
  }

  return { bookmarks, loading, load, add, remove, byCategory }
})
