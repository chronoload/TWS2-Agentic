import { defineStore } from 'pinia'
import { ref } from 'vue'

const STORAGE_KEY = 'ts2_search_history'

export interface SearchHistoryEntry {
  query: string
  service: string
  timestamp: number
}

export const useSearchHistoryStore = defineStore('searchHistory', () => {
  const entries = ref<SearchHistoryEntry[]>([])

  function load() {
    try {
      const raw = localStorage.getItem(STORAGE_KEY)
      if (raw) entries.value = JSON.parse(raw)
    } catch { entries.value = [] }
  }

  function save() {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(entries.value.slice(0, 50)))
  }

  function add(query: string, service: string) {
    entries.value = entries.value.filter(e => e.query !== query)
    entries.value.unshift({ query, service, timestamp: Date.now() })
    if (entries.value.length > 50) entries.value = entries.value.slice(0, 50)
    save()
  }

  function remove(query: string) {
    entries.value = entries.value.filter(e => e.query !== query)
    save()
  }

  function clear() {
    entries.value = []
    localStorage.removeItem(STORAGE_KEY)
  }

  load()

  return { entries, add, remove, clear }
})
