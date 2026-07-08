<template>
  <div class="feed-view">
    <div class="feed-header">
      <h3 class="section-title">订阅动态</h3>
      <span v-if="feedStore.newCount > 0" class="new-count">{{ feedStore.newCount }} 条新内容</span>
      <div class="feed-actions">
        <button class="feed-btn" @click="feedStore.markAllSeen()" :disabled="feedStore.allItems.length === 0">全部标为已读</button>
        <button class="feed-btn" @click="refresh" :disabled="refreshing">{{ refreshing ? '刷新中...' : '刷新' }}</button>
      </div>
    </div>

    <div v-if="subStore.groups.length > 0" class="group-tabs">
      <button class="group-tab" :class="{ active: activeGroupId === undefined }" @click="activeGroupId = undefined">全部</button>
      <button class="group-tab" :class="{ active: activeGroupId === -2 }" @click="activeGroupId = -2">通知</button>
      <button
        v-for="g in subStore.sortedGroups"
        :key="g.id"
        class="group-tab"
        :class="{ active: activeGroupId === g.id }"
        @click="activeGroupId = g.id"
      >{{ g.name }}</button>
    </div>

    <div v-if="feedStore.allItems.length === 0 && !refreshing" class="placeholder">
      <p>暂无订阅动态</p>
      <p class="hint">订阅频道后，这里将显示他们的最新视频</p>
    </div>
    <div v-if="refreshing" class="refreshing-bar">刷新中...</div>
    <div v-if="filteredItems.length > 0" class="grid">
      <div
        v-for="item in filteredItems"
        :key="item.url"
        class="feed-card"
        :class="{ 'is-new': feedStore.isNew(item.url) }"
        @click="onItemClick(item)"
      >
        <div class="fc-thumb-wrap">
          <img :src="proxyImageUrl(item.thumbnailUrl) || ''" class="fc-thumb" loading="lazy" @error="onImgError" />
          <div v-if="feedStore.isNew(item.url)" class="new-badge">新</div>
          <div v-if="item.duration && item.duration > 0" class="fc-duration">{{ fmtDuration(item.duration) }}</div>
        </div>
        <div class="fc-body">
          <div class="fc-title">{{ item.name }}</div>
          <div class="fc-meta">
            <img :src="proxyImageUrl(getChannelAvatar(item))" class="fc-avatar" loading="lazy" @error="onImgError" />
            <span>{{ item.uploaderName || '' }}</span>
          </div>
          <div class="fc-views">{{ fmtCount(item.viewCount) }} 次观看</div>
        </div>
      </div>
    </div>
    <div v-if="loadingMore" class="refreshing-bar">加载更多...</div>
    <div ref="scrollSentinel" class="scroll-sentinel"></div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted, watch } from 'vue'
import { useRouter } from 'vue-router'
import { proxyImageUrl } from '../extractor/BilibiliImageProxy'
import { useFeedStore } from '../stores/feed'
import { useSubscriptionsStore } from '../stores/subscriptions'
import { api, extractNextPage } from '../plugins/bridge'
import type { StreamInfoItem, FeedInfoResult } from '../plugins/bridge'

const router = useRouter()
const feedStore = useFeedStore()
const subStore = useSubscriptionsStore()
const refreshing = ref(false)
const loadingMore = ref(false)
const scrollSentinel = ref<HTMLElement | null>(null)
const activeGroupId = ref<number | undefined>(undefined)
let observer: IntersectionObserver | null = null

const filteredItems = computed(() => {
  if (activeGroupId.value === undefined) return feedStore.allItems
  if (activeGroupId.value === -2) {
    return feedStore.allItems.filter(item => {
      if (!item.uploaderUrl) return false
      return subStore.getNotif(item.uploaderUrl)
    })
  }
  const groupSubs = subStore.getGroupSubscriptions(activeGroupId.value)
  const urls = new Set(groupSubs.map(s => s.url))
  return feedStore.allItems.filter(item => {
    if (!item.uploaderUrl) return false
    return urls.has(item.uploaderUrl)
  })
})

onMounted(() => {
  if (feedStore.channels.length === 0) refresh()
  setupSentinel()
})

onUnmounted(() => { observer?.disconnect() })

function setupSentinel() {
  if (typeof IntersectionObserver === 'undefined') return
  observer = new IntersectionObserver((entries) => {
    if (entries[0]?.isIntersecting && !refreshing.value && !loadingMore.value) {
      if (feedStore.hasMore()) loadMore()
      else if (feedStore.channels.length === 0) refresh()
    }
  }, { rootMargin: '300px' })
  watch(scrollSentinel, (el) => {
    if (observer && el) { observer.disconnect(); observer.observe(el) }
  })
}

async function refresh() {
  if (refreshing.value) return
  refreshing.value = true
  try {
    const subs = activeGroupId.value !== undefined && activeGroupId.value !== -2
      ? subStore.getGroupSubscriptions(activeGroupId.value)
      : subStore.sorted
    for (const sub of subs) {
      try {
        const sid = sub.serviceId
        if (sid == null || sid < 0) continue
        const channelInfo = await api.getFeedInfo(sub.url, sid)
        const items = (channelInfo.items || []).slice(0, 20)
        feedStore.updateChannel(sub.url, sub.name, sub.avatarUrl || '', items, extractNextPage(channelInfo), !!channelInfo._hasNextPage)
      } catch { /* skip */ }
    }
  } finally {
    refreshing.value = false
  }
}

async function loadMore() {
  if (loadingMore.value || !feedStore.hasMore()) return
  loadingMore.value = true
  try {
    const subs = activeGroupId.value !== undefined && activeGroupId.value !== -2
      ? subStore.getGroupSubscriptions(activeGroupId.value)
      : subStore.sorted
    for (const sub of subs) {
      const cache = feedStore.getChannelCache(sub.url)
      if (!cache || !cache.hasNextPage || !cache.nextPage) continue
      try {
        const sid = sub.serviceId
        if (sid == null || sid < 0) continue
        const r = await api.getMoreChannelItems(sub.url, sid, undefined, cache.nextPage)
        feedStore.appendChannelItems(sub.url, r.items || [], extractNextPage(r), !!r._hasNextPage)
      } catch { /* skip */ }
    }
  } finally {
    loadingMore.value = false
  }
}

function getChannelAvatar(item: StreamInfoItem): string {
  if (item.uploaderAvatarUrl) return item.uploaderAvatarUrl
  if (item.uploaderUrl) {
    const sub = subStore.getByUrl(item.uploaderUrl)
    if (sub?.avatarUrl) return sub.avatarUrl
  }
  return ''
}

function onItemClick(item: StreamInfoItem) {
  feedStore.markSeen(item.url)
  router.push({ name: 'video-player', query: { url: item.url } })
}

function fmtCount(n?: number): string {
  if (!n || n < 0) return '未知'
  if (n >= 10000) return (n / 10000).toFixed(1) + '万'
  if (n >= 1000) return (n / 1000).toFixed(1) + 'k'
  return String(n)
}

function onImgError(e: Event) {
  const el = e.target as HTMLElement
  el.style.display = 'none'
}

function fmtDuration(seconds?: number): string {
  if (!seconds || seconds < 0) return ''
  const h = Math.floor(seconds / 3600)
  const m = Math.floor((seconds % 3600) / 60)
  const s = seconds % 60
  if (h > 0) return `${h}:${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`
  return `${m}:${String(s).padStart(2, '0')}`
}
</script>

<style scoped>
.feed-view { position: relative; }
.feed-header { display: flex; align-items: center; gap: 8px; margin-bottom: 12px; flex-wrap: wrap; }
.feed-actions { display: flex; gap: 6px; margin-left: auto; }
.feed-btn { padding: 4px 10px; background: var(--bg-secondary); border: 1px solid var(--border); border-radius: 6px; color: var(--fg); font-size: 12px; cursor: pointer; white-space: nowrap; }
.feed-btn:hover { border-color: var(--accent); }
.feed-btn:disabled { opacity: 0.4; cursor: default; }
.new-count { font-size: 11px; color: var(--accent); font-weight: 600; }
.refreshing-bar { text-align: center; padding: 8px; font-size: 12px; color: var(--fg-muted); }
.section-title { font-size: 14px; font-weight: 600; color: var(--fg); margin: 0; }
.scroll-sentinel { height: 1px; }
.placeholder { text-align: center; padding: 48px 16px; color: var(--fg-muted); font-size: 14px; }
.placeholder .hint { font-size: 12px; margin-top: 8px; }

.group-tabs { display: flex; gap: 4px; margin-bottom: 10px; overflow-x: auto; flex-shrink: 0; }
.group-tab { padding: 4px 12px; font-size: 12px; border: 1px solid var(--border); border-radius: 16px; background: none; color: var(--fg-muted); cursor: pointer; white-space: nowrap; }
.group-tab.active { border-color: var(--accent); color: var(--accent); background: rgba(var(--accent-rgb, 59,130,246),0.1); }

.grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(160px, 1fr)); gap: 10px; }
.feed-card { background: var(--bg-secondary); border-radius: 8px; overflow: hidden; cursor: pointer; transition: transform 0.1s; border: 2px solid transparent; }
.feed-card:hover { transform: translateY(-1px); }
.feed-card.is-new { border-color: var(--accent); }
.fc-thumb-wrap { position: relative; aspect-ratio: 16/9; background: #000; }
.fc-thumb { width: 100%; height: 100%; object-fit: cover; }
.new-badge { position: absolute; top: 4px; left: 4px; background: var(--accent); color: #fff; font-size: 10px; padding: 1px 5px; border-radius: 3px; font-weight: 600; }
.fc-duration { position: absolute; right: 4px; bottom: 4px; background: rgba(0,0,0,0.7); color: #fff; font-size: 11px; padding: 1px 4px; border-radius: 3px; }
.fc-body { padding: 8px; }
.fc-title { font-size: 13px; font-weight: 600; color: var(--fg); overflow: hidden; text-overflow: ellipsis; display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; margin-bottom: 6px; }
.fc-meta { display: flex; align-items: center; gap: 6px; font-size: 11px; color: var(--fg-muted); margin-bottom: 4px; }
.fc-avatar { width: 18px; height: 18px; border-radius: 50%; object-fit: cover; }
.fc-views { font-size: 11px; color: var(--fg-muted); }
</style>
