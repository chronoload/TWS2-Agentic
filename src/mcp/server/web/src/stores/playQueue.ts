import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import type { StreamInfoResult } from '../plugins/bridge'
import { streamStateRepo } from '../db'

const STORAGE_KEY = 'ts2_playqueue'

export interface PlayQueueItem {
  url: string
  title: string
  thumbnailUrl: string
  duration: number
  uploaderName: string
  streamInfo?: StreamInfoResult
}

export type RepeatMode = 'none' | 'one' | 'all'

export const usePlayQueueStore = defineStore('playQueue', () => {
  const items = ref<PlayQueueItem[]>([])
  const currentIndex = ref(-1)
  const repeatMode = ref<RepeatMode>('none')
  const shuffle = ref(false)

  const current = computed(() =>
    currentIndex.value >= 0 && currentIndex.value < items.value.length
      ? items.value[currentIndex.value]
      : null
  )

  const isEmpty = computed(() => items.value.length === 0)
  const length = computed(() => items.value.length)

  const hasNext = computed(() => {
    if (repeatMode.value === 'one') return true
    if (repeatMode.value === 'all') return items.value.length > 0
    return currentIndex.value < items.value.length - 1
  })

  const hasPrev = computed(() => {
    if (repeatMode.value === 'one') return true
    if (repeatMode.value === 'all') return items.value.length > 0
    return currentIndex.value > 0
  })

  function load() {
    try {
      const raw = localStorage.getItem(STORAGE_KEY)
      if (raw) {
        const data = JSON.parse(raw)
        items.value = data.items || []
        currentIndex.value = data.currentIndex ?? -1
        repeatMode.value = data.repeatMode || 'none'
        shuffle.value = data.shuffle || false
      }
    } catch {
      items.value = []
      currentIndex.value = -1
    }
  }

  function save() {
    localStorage.setItem(STORAGE_KEY, JSON.stringify({
      items: items.value,
      currentIndex: currentIndex.value,
      repeatMode: repeatMode.value,
      shuffle: shuffle.value
    }))
  }

  function add(item: PlayQueueItem) {
    items.value.push(item)
    if (currentIndex.value === -1) currentIndex.value = 0
    save()
  }

  function replaceWith(newItems: PlayQueueItem[]) {
    items.value = newItems
    currentIndex.value = newItems.length > 0 ? 0 : -1
    save()
  }

  function addNext(item: PlayQueueItem) {
    const insertAt = currentIndex.value + 1
    items.value.splice(insertAt, 0, item)
    save()
  }

  function remove(index: number) {
    items.value.splice(index, 1)
    if (index < currentIndex.value) currentIndex.value--
    else if (index === currentIndex.value) {
      if (items.value.length === 0) currentIndex.value = -1
      else if (currentIndex.value >= items.value.length) currentIndex.value = 0
    }
    save()
  }

  function clear() {
    items.value = []
    currentIndex.value = -1
    save()
  }

  async function getSavedPosition(url: string): Promise<number> {
    try {
      const state = await streamStateRepo.getByUrl(url)
      if (state && state.progressMillis > 0) return state.progressMillis / 1000
    } catch {}
    return 0
  }

  async function playAt(index: number) {
    if (index >= 0 && index < items.value.length) {
      currentIndex.value = index
      save()
    }
  }

  function playNext(): PlayQueueItem | null {
    if (items.value.length === 0) return null
    if (repeatMode.value === 'one') return items.value[currentIndex.value]
    if (shuffle.value) {
      const next = Math.floor(Math.random() * items.value.length)
      currentIndex.value = next
      save()
      return items.value[next]
    }
    if (currentIndex.value < items.value.length - 1) {
      currentIndex.value++
      save()
      return items.value[currentIndex.value]
    }
    if (repeatMode.value === 'all') {
      currentIndex.value = 0
      save()
      return items.value[0]
    }
    return null
  }

  function playPrev(): PlayQueueItem | null {
    if (items.value.length === 0) return null
    if (repeatMode.value === 'one') return items.value[currentIndex.value]
    if (shuffle.value) {
      const prev = Math.floor(Math.random() * items.value.length)
      currentIndex.value = prev
      save()
      return items.value[prev]
    }
    if (currentIndex.value > 0) {
      currentIndex.value--
      save()
      return items.value[currentIndex.value]
    }
    if (repeatMode.value === 'all') {
      currentIndex.value = items.value.length - 1
      save()
      return items.value[items.value.length - 1]
    }
    return null
  }

  function move(from: number, to: number) {
    const [removed] = items.value.splice(from, 1)
    items.value.splice(to, 0, removed)
    if (from === currentIndex.value) currentIndex.value = to
    else if (from < currentIndex.value && to >= currentIndex.value) currentIndex.value--
    else if (from > currentIndex.value && to <= currentIndex.value) currentIndex.value++
    save()
  }

  function toggleShuffle() {
    shuffle.value = !shuffle.value
    save()
  }

  function setRepeatMode(mode: RepeatMode) {
    repeatMode.value = mode
    save()
  }

  load()

  return {
    items, currentIndex, repeatMode, shuffle,
    current, isEmpty, length, hasNext, hasPrev,
    add, addNext, replaceWith, remove, clear, playAt, getSavedPosition, playNext, playPrev,
    move, toggleShuffle, setRepeatMode, save
  }
})
