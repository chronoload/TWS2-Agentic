import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import type { StreamInfoItem, Page } from '../plugins/bridge'
import { feedRepo, FeedRepository } from '../db'

const STORAGE_KEY = 'ts2_feed'

export interface FeedChannelCache {
  channelUrl: string
  channelName: string
  channelAvatar: string
  items: StreamInfoItem[]
  lastFetched: number
  nextPage?: Page | null
  hasNextPage?: boolean
}

export const useFeedStore = defineStore('feed', () => {
  const channels = ref<FeedChannelCache[]>([])
  const refreshing = ref(false)

  const allItems = computed(() => {
    const flat: (StreamInfoItem & { channelName: string; channelUrl: string })[] = []
    for (const ch of channels.value) {
      for (const item of ch.items) {
        flat.push({ ...item, channelName: ch.channelName, channelUrl: ch.channelUrl })
      }
    }
    flat.sort((a, b) => (b.textualUploadDate || '').localeCompare(a.textualUploadDate || ''))
    return flat
  })

  const newCount = computed(() => {
    let count = 0
    for (const ch of channels.value) {
      for (const item of ch.items) {
        const seenKey = `feed_seen_${item.url}`
        const seen = localStorage.getItem(seenKey)
        if (!seen) count++
      }
    }
    return count
  })

  function load() {
    try {
      const raw = localStorage.getItem(STORAGE_KEY)
      if (raw) channels.value = JSON.parse(raw)
    } catch { channels.value = [] }
  }

  function save() {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(channels.value))
  }

  function getChannelCache(channelUrl: string): FeedChannelCache | undefined {
    return channels.value.find(c => c.channelUrl === channelUrl)
  }

  function updateChannel(channelUrl: string, channelName: string, channelAvatar: string, items: StreamInfoItem[], nextPage?: Page | null, hasNextPage?: boolean) {
    const existing = channels.value.findIndex(c => c.channelUrl === channelUrl)
    const entry: FeedChannelCache = { channelUrl, channelName, channelAvatar, items, lastFetched: Date.now(), nextPage: nextPage || null, hasNextPage: !!hasNextPage }
    if (existing >= 0) {
      channels.value[existing] = entry
    } else {
      channels.value.push(entry)
    }
    save()
    syncFeedToDB(channelUrl, channelName, channelUrl, items)

    const lastPrune = Number(localStorage.getItem('ts2_feed_last_prune') || '0')
    if (FeedRepository.isPruneDue(lastPrune)) {
      feedRepo.pruneStale().then(n => { if (n > 0) localStorage.setItem('ts2_feed_last_prune', String(Date.now())) })
    }
  }

  async function syncFeedToDB(channelUrl: string, channelName: string, _channelAvatar: string, items: StreamInfoItem[]) {
    await feedRepo.upsertAll(channelUrl, channelName, channelUrl, items.map(item => ({
      url: item.url,
      title: item.name,
      streamType: item.streamType || 'VIDEO_STREAM',
      duration: item.duration || 0,
      uploader: item.uploaderName || channelName,
      thumbnailUrl: item.thumbnailUrl,
      viewCount: item.viewCount,
      textualUploadDate: item.textualUploadDate,
    })))
  }

  function appendChannelItems(channelUrl: string, newItems: StreamInfoItem[], nextPage?: Page | null, hasNextPage?: boolean) {
    const ch = channels.value.find(c => c.channelUrl === channelUrl)
    if (!ch) return
    const existing = new Set(ch.items.map(i => i.url))
    for (const item of newItems) {
      if (!existing.has(item.url)) {
        ch.items.push(item)
        existing.add(item.url)
      }
    }
    ch.nextPage = nextPage || null
    ch.hasNextPage = !!hasNextPage
    save()
  }

  function hasMore(): boolean {
    return channels.value.some(c => c.hasNextPage && c.nextPage)
  }

  function removeChannel(channelUrl: string) {
    channels.value = channels.value.filter(c => c.channelUrl !== channelUrl)
    save()
  }

  function markSeen(url: string) {
    localStorage.setItem(`feed_seen_${url}`, String(Date.now()))
  }

  function markAllSeen() {
    const now = String(Date.now())
    for (const ch of channels.value) {
      for (const item of ch.items) {
        localStorage.setItem(`feed_seen_${item.url}`, now)
      }
    }
  }

  function isNew(url: string): boolean {
    return !localStorage.getItem(`feed_seen_${url}`)
  }

  function clear() {
    channels.value = []
    save()
  }

  load()

  return {
    channels, refreshing, allItems, newCount,
    getChannelCache, updateChannel, appendChannelItems, removeChannel, hasMore,
    markSeen, markAllSeen, isNew, clear, save
  }
})
