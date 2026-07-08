<template>
  <div class="video-view">
    <div class="plugin-status" :class="{ error: !!pluginError }">
      {{ pluginStatus }}
      <div v-if="pluginError" class="plugin-error-detail">{{ pluginError }}</div>
    </div>

    <div class="tabs">
      <button class="tab" :class="{ active: activeTab === 'playlists' }" @click="activeTab = 'playlists'">收藏</button>
      <button class="tab" :class="{ active: activeTab === 'subs' }" @click="activeTab = 'subs'">订阅 ({{ subCount }})</button>
      <button class="tab" :class="{ active: activeTab === 'feed' }" @click="activeTab = 'feed'">最近更新 <span v-if="feedStore.newCount > 0" class="feed-badge">{{ feedStore.newCount }}</span></button>
      <button class="tab" :class="{ active: activeTab === 'search' }" @click="activeTab = 'search'">搜索</button>
    </div>

    <!-- 播放列表 Tab -->
    <div v-if="activeTab === 'playlists'" class="panel">
      <div class="add-bar">
        <input v-model="plUrl" class="add-input" placeholder="输入播放列表 URL..." @keyup.enter="addPlaylist" />
        <button class="add-btn" @click="addPlaylist" :disabled="plLoading">{{ plLoading ? '加载中...' : '添加' }}</button>
      </div>
      <div v-if="plError" class="error-msg">{{ plError }}</div>
      <div v-if="plInfo" class="playlist-preview">
        <div class="playlist-header">
          <img :src="proxied(plInfo.thumbnailUrl)" class="pl-thumb" loading="lazy" @error="e => { e.target.style.display = 'none' }" />
          <div class="pl-info">
            <h3>{{ plInfo.name }}</h3>
            <p class="pl-meta">
              <span v-if="plInfo.uploaderAvatarUrl" class="pl-uploader-avatar-wrap"><img :src="proxied(plInfo.uploaderAvatarUrl)" class="pl-uploader-avatar" loading="lazy" @click="openChannelFromPlaylist" @error="e => { e.target.style.display = 'none' }" /></span>
              <span class="pl-uploader-name clickable" @click="openChannelFromPlaylist">{{ plInfo.uploaderName }}</span> · {{ plInfo.streamCount }} 个视频
              <span v-if="playlistDuration > 0" class="pl-duration">{{ fmtDuration(playlistDuration) }}</span>
            </p>
            <div class="pl-actions" v-if="plItems.length > 0">
              <button class="action-btn-sm" @click="playAllPlaylist">▶ 全部播放</button>
              <button class="action-btn-sm" @click="enqueueAllPlaylist">📋 加入队列</button>
              <button class="action-btn-sm" @click="playAllBg">🎧 后台播放</button>
              <button class="bookmark-btn-sm" @click="toggleBookmark" :class="{ bookmarked: isBookmarked }">
                {{ isBookmarked ? '📑 已收藏' : '📑 收藏' }}
              </button>
            </div>
          </div>
        </div>
        <div v-if="plItems.length > 0" class="grid">
          <VideoCard
            v-for="(item, i) in plItems"
            :key="item.url"
            :item="item"
            @cardClick="onVideoClick(item)"
            @addToPlaylist="plStore.addFavorite"
            @touchstart.passive="onPlLongPressStart($event, item, i)"
            @touchend="onPlLongPressEnd"
            @touchmove="onPlLongPressEnd"
          />
        </div>
        <div v-if="plLoadingMore" class="loading">加载更多...</div>
        <div v-else-if="!plHasNext && plItems.length > 0" class="end-hint">已显示全部</div>
        <div ref="plScrollSentinel" class="scroll-sentinel"></div>
      </div>
      <div v-else class="bookmarks-section">
        <h3 class="section-title">已收藏的播放列表</h3>
        <div v-if="plStore.remotePlaylists.length === 0" class="placeholder">还没有收藏任何播放列表</div>
        <div v-else-if="plStore.remotePlaylists.length" class="bookmark-list">
          <div v-for="pl in plStore.remotePlaylists" :key="pl.url" class="bookmark-item" @click="openBookmark(pl.url)">
            <img :src="proxied(pl.thumbnailUrl)" class="bm-thumb" loading="lazy" @error="e => { e.target.style.display = 'none' }" />
            <div class="bm-info">
              <div class="bm-name">{{ pl.name }}</div>
              <div class="bm-meta">{{ pl.uploaderName }} · {{ pl.streamCount }} 视频</div>
            </div>
            <button class="remove-btn" @click.stop="plStore.unbookmarkRemote(pl.url)">✕</button>
          </div>
        </div>
      </div>
    </div>

    <!-- Context menu for playlist items -->
    <Teleport to="body">
      <div v-if="itemMenu.show" class="item-menu" :style="{ top: itemMenu.y + 'px', left: itemMenu.x + 'px' }" @click.stop @touchend.prevent.stop>
        <div class="item-menu-item" @click="playFromHere">▶ 从此处播放</div>
        <div class="item-menu-item" @click="enqueueFromHere">📋 从此处加入队列</div>
        <div class="item-menu-item" @click="itemMenu.show = false">取消</div>
      </div>
    </Teleport>

    <!-- 订阅 Tab -->
    <div v-if="activeTab === 'subs'" class="panel">
      <div class="subs-layout">
        <aside class="subs-sidebar">
          <SubscriptionList :list="subStore.sorted" active-url="" @select="openChannel" />
        </aside>
        <main class="subs-main">
          <div class="placeholder">选择一个订阅频道查看频道主页</div>
        </main>
      </div>
    </div>

    <!-- 动态 Tab -->
    <div v-if="activeTab === 'feed'" class="panel">
      <FeedView />
    </div>

    <!-- 搜索 Tab -->
    <div v-if="activeTab === 'search'" class="panel search-panel">
      <div v-if="searchError" class="error-msg">{{ searchError }}</div>
      <div class="search-bar">
        <select v-model="serviceName" class="service-select">
          <option value="YouTube">YouTube</option>
          <option value="BiliBili">BiliBili</option>
          <option value="SoundCloud">SoundCloud</option>
          <option value="Bandcamp">Bandcamp</option>
          <option value="PeerTube">PeerTube</option>
          <option value="NicoNico">NicoNico</option>
          <option value="MediaCCC">MediaCCC</option>
        </select>
        <input v-model="searchQuery" class="search-input" placeholder="搜索视频..." @keyup.enter="doSearch" />
        <button class="search-btn" @click="doSearch" :disabled="searching">{{ searching ? '搜索中...' : '搜索' }}</button>
      </div>
      <div class="filter-bar">
        <select v-model="contentFilter" class="filter-select">
          <option value="videos">视频</option>
          <option value="channels">频道</option>
          <option value="lives">直播</option>
          <option value="animes">番剧</option>
          <option value="movies_and_tv">影视</option>
        </select>
        <select v-model="sortFilter" class="filter-select">
          <option value="sort_overall">综合排序</option>
          <option value="sort_publish_time">最新发布</option>
          <option value="sort_view">最多播放</option>
          <option value="sort_bullet_comments">最多弹幕</option>
          <option value="sort_comments">最多评论</option>
          <option value="sort_bookmark">最多收藏</option>
        </select>
        <select v-model="durationFilter" class="filter-select">
          <option value="all">全部时长</option>
          <option value="short_video">短视频</option>
          <option value="medium_length">中等</option>
          <option value="long_video">长视频</option>
          <option value="extra_long">超长</option>
        </select>
      </div>
      <div v-if="searchItems.length > 0" class="results">
        <div class="grid">
          <VideoCard v-for="item in searchItems" :key="item.url" :item="item" @cardClick="onResultClick" />
        </div>
        <div v-if="loadingMore" class="loading">加载更多...</div>
        <div v-else-if="!hasNextPage && searchItems.length > 0" class="end-hint">已显示全部结果</div>
        <div ref="scrollSentinel" class="scroll-sentinel"></div>
      </div>
      <div v-else-if="!searching && !searchStarted" class="search-idle">
        <div v-if="searchHistory.entries.length" class="history-section">
          <h3 class="section-title">搜索历史</h3>
          <div class="history-list">
            <div v-for="entry in searchHistory.entries.slice(0, 10)" :key="entry.query + entry.timestamp" class="history-item" @click="searchQuery = entry.query; doSearch()">
              <span class="history-query">{{ entry.query }}</span>
              <span class="history-service">{{ entry.service }}</span>
              <button class="history-remove" @click.stop="searchHistory.remove(entry.query)">✕</button>
            </div>
          </div>
          <button v-if="searchHistory.entries.length > 0" class="clear-history-btn" @click="searchHistory.clear()">清空历史</button>
        </div>
        <div v-else class="placeholder">输入关键词搜索视频</div>
      </div>
      <div v-else-if="searching" class="loading">搜索中...</div>
      <div v-else-if="!hasNextPage && searchStarted" class="placeholder">没有找到结果</div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted, watch } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { useSubscriptionsStore, type Subscription } from '../stores/subscriptions'
import { usePlaylistsStore } from '../stores/playlists'
import { usePlayQueueStore } from '../stores/playQueue'
import { useSearchHistoryStore } from '../stores/searchHistory'
import VideoCard from '../components/VideoCard.vue'
import SubscriptionList from '../components/SubscriptionList.vue'
import FeedView from '../components/FeedView.vue'
import PipePipe, { api, extractNextPage } from '../plugins/bridge'
import type { StreamInfoItem, PlaylistInfoResult, SearchResult, Page } from '../plugins/bridge'
import { useFeedStore } from '../stores/feed'
import { proxyImageUrl } from '../extractor/BilibiliImageProxy'

function proxied(url: string | undefined | null): string { return proxyImageUrl(url || '') }
const router = useRouter()
const route = useRoute()
const subStore = useSubscriptionsStore()
const plStore = usePlaylistsStore()
const queueStore = usePlayQueueStore()
const searchHistory = useSearchHistoryStore()
const feedStore = useFeedStore()

const pluginStatus = ref('')
const pluginError = ref('')
const activeTab = ref<'playlists' | 'favorites' | 'subs' | 'feed' | 'search'>('playlists')
const subCount = computed(() => subStore.subscriptions.length)
const favCount = computed(() => plStore.favoritesItems.length)
const sortedFavs = computed(() => [...plStore.favoritesItems].sort((a: any, b: any) => b.addedAt - a.addedAt))

// ── serviceId 解析 ──
const serviceId = ref(-1)
async function resolveServiceId(url: string) {
  try { const r = await api.resolveUrl(url); serviceId.value = r.serviceId } catch { serviceId.value = -1 }
}

onMounted(async () => {
  try {
    await PipePipe.echo()
    pluginStatus.value = '✓'
  } catch (e: any) {
    pluginStatus.value = '✗'
    pluginError.value = '插件: ' + (e.message || e)
  }
  const playlistUrl = route.query.playlistUrl as string
  if (playlistUrl) { activeTab.value = 'playlists'; loadPlaylist(playlistUrl) }
  if (typeof IntersectionObserver !== 'undefined') {
    observer = new IntersectionObserver((entries) => {
      for (const entry of entries) {
        if (entry.isIntersecting && hasNextPage.value && !loadingMore.value) loadMore()
      }
    }, { rootMargin: '200px' })
  }
})

watch(() => scrollSentinel.value, (el) => {
  if (observer && el) { observer.disconnect(); observer.observe(el) }
})

// ══════ 播放列表面 ══════
const plUrl = ref('')
const plItems = ref<StreamInfoItem[]>([])
const plInfo = ref<PlaylistInfoResult | null>(null)
const plLoading = ref(false)
const plLoadingMore = ref(false)
const plError = ref('')
const plNextPage = ref<Page | null>(null)
const plHasNext = ref(false)
const isBookmarked = ref(false)
const plScrollSentinel = ref<HTMLElement | null>(null)
const itemMenu = ref<{ show: boolean; x: number; y: number; item: StreamInfoItem | null; index: number }>({ show: false, x: 0, y: 0, item: null, index: -1 })
let plObserver: IntersectionObserver | null = null

const playlistDuration = computed(() =>
  plItems.value.reduce((sum, i) => sum + (i.duration || 0), 0))

async function loadPlaylist(url: string) {
  plLoading.value = true; plError.value = ''
  try {
    await resolveServiceId(url)
    const r = await api.getPlaylistInfo(url, serviceId.value)
    plInfo.value = r
    plItems.value = r.items || []
    plNextPage.value = extractNextPage(r)
    plHasNext.value = !!r._hasNextPage
    isBookmarked.value = plStore.isBookmarked(url)
  } catch (e: any) { plError.value = '加载失败: ' + (e.message || e) }
  finally { plLoading.value = false }
  setupPlSentinel()
}

function addPlaylist() {
  const url = plUrl.value.trim()
  if (!url) return
  loadPlaylist(url)
  plUrl.value = ''
}

async function loadMorePlaylist() {
  if (plLoadingMore.value || !plHasNext.value || !plNextPage.value) return
  plLoadingMore.value = true
  try {
    const r = await api.getMorePlaylistItems(plInfo.value!.url, serviceId.value, undefined, plNextPage.value)
    const existing = new Set(plItems.value.map(i => i.url))
    for (const item of (r.items || [])) { if (!existing.has(item.url)) plItems.value.push(item) }
    plNextPage.value = extractNextPage(r)
    plHasNext.value = !!r._hasNextPage
  } catch (e: any) { plError.value = '加载更多失败: ' + (e.message || e) }
  finally { plLoadingMore.value = false }
}

function toggleBookmark() {
  const r = plInfo.value
  if (!r) return
  if (isBookmarked.value) { plStore.unbookmarkRemote(r.url); isBookmarked.value = false }
  else { plStore.bookmarkRemote({ url: r.url, name: r.name, thumbnailUrl: r.thumbnailUrl, uploaderName: r.uploaderName, uploaderAvatarUrl: r.uploaderAvatarUrl || '', streamCount: r.streamCount }); isBookmarked.value = true }
}

function setupPlSentinel() {
  plObserver?.disconnect()
  if (typeof IntersectionObserver === 'undefined') return
  plObserver = new IntersectionObserver((entries) => {
    if (entries[0]?.isIntersecting && plHasNext.value && !plLoadingMore.value) loadMorePlaylist()
  }, { rootMargin: '200px' })
  watch(plScrollSentinel, (el) => { if (plObserver && el) { plObserver.disconnect(); plObserver.observe(el) } }, { immediate: true })
}

onUnmounted(() => { plObserver?.disconnect() })

function playAllPlaylist() {
  if (!plItems.value.length) return
  queueStore.replaceWith(plItems.value.map(item => ({ url: item.url, title: item.name, thumbnailUrl: item.thumbnailUrl, duration: item.duration || 0, uploaderName: item.uploaderName || '' })))
  router.push({ name: 'video-player', query: { url: plItems.value[0].url } })
}

function enqueueAllPlaylist() {
  for (const item of plItems.value) queueStore.add({ url: item.url, title: item.name, thumbnailUrl: item.thumbnailUrl, duration: item.duration || 0, uploaderName: item.uploaderName || '' })
}

function playAllBg() {
  if (!plItems.value.length) return
  queueStore.replaceWith(plItems.value.map(item => ({ url: item.url, title: item.name, thumbnailUrl: item.thumbnailUrl, duration: item.duration || 0, uploaderName: item.uploaderName || '' })))
}

function openChannelFromPlaylist() {
  const r = plInfo.value
  if (r?.uploaderUrl) router.push({ name: 'channel', query: { url: r.uploaderUrl } })
}

let _plLongPressTimer: ReturnType<typeof setTimeout> | null = null
function onPlLongPressStart(e: TouchEvent, item: StreamInfoItem, index: number) {
  _plLongPressTimer = setTimeout(() => {
    _plLongPressTimer = null
    const touch = e.touches[0]
    itemMenu.value = { show: true, x: touch.clientX, y: touch.clientY, item, index }
    const close = (ev: Event) => {
      if (!(ev.target as HTMLElement)?.closest?.('.item-menu')) { itemMenu.value.show = false; document.removeEventListener('click', close); document.removeEventListener('touchend', close) }
    }
    setTimeout(() => { document.addEventListener('click', close); document.addEventListener('touchend', close) }, 0)
  }, 500)
}
function onPlLongPressEnd() { if (_plLongPressTimer) { clearTimeout(_plLongPressTimer); _plLongPressTimer = null } }

function playFromHere() {
  if (!itemMenu.value.item || !plItems.value.length) return
  const itemsFrom = plItems.value.slice(itemMenu.value.index)
  queueStore.replaceWith(itemsFrom.map(item => ({ url: item.url, title: item.name, thumbnailUrl: item.thumbnailUrl, duration: item.duration || 0, uploaderName: item.uploaderName || '' })))
  itemMenu.value.show = false
  router.push({ name: 'video-player', query: { url: itemMenu.value.item.url } })
}

function enqueueFromHere() {
  if (!itemMenu.value.item) return
  for (const item of plItems.value.slice(itemMenu.value.index)) queueStore.add({ url: item.url, title: item.name, thumbnailUrl: item.thumbnailUrl, duration: item.duration || 0, uploaderName: item.uploaderName || '' })
  itemMenu.value.show = false
}

function fmtDuration(seconds: number): string {
  if (!seconds || seconds <= 0) return ''
  const h = Math.floor(seconds / 3600)
  const m = Math.floor((seconds % 3600) / 60)
  if (h > 0) return `· ${h}小时${m}分钟`
  return `· ${m}分钟`
}

function openBookmark(url: string) { loadPlaylist(url) }

// ══════ 订阅 tab ══════
function openChannel(sub: Subscription) { router.push({ name: 'channel', query: { url: sub.url } }) }

// ══════ 搜索 tab ══════
const searchServiceId = ref(-1)
const searchQuery = ref('')
const serviceName = ref('BiliBili')
const searching = ref(false)
const searchStarted = ref(false)
const searchItems = ref<StreamInfoItem[]>([])
const searchError = ref('')
const hasNextPage = ref(false)
const nextPage = ref<Page | null>(null)
const loadingMore = ref(false)
const scrollSentinel = ref<HTMLElement | null>(null)
const contentFilter = ref('videos')
const sortFilter = ref('sort_overall')
const durationFilter = ref('all')

// 服务名称 → serviceId 映射
const SERVICE_ID_MAP: Record<string, number> = { YouTube: 0, BiliBili: 5, SoundCloud: 1, Bandcamp: 4, PeerTube: 3, NicoNico: 6, MediaCCC: 2 }

async function doSearch() {
  const q = searchQuery.value.trim()
  if (!q) return
  const sid = SERVICE_ID_MAP[serviceName.value]
  if (sid == null) { searchError.value = '不支持的服务: ' + serviceName.value; return }
  searchServiceId.value = sid
  searching.value = true; searchStarted.value = true
  searchItems.value = []; searchError.value = ''
  hasNextPage.value = false; nextPage.value = null
  searchHistory.add(q, serviceName.value)
  try {
    const res: SearchResult = await api.search(q, searchServiceId.value, contentFilter.value, sortFilter.value, durationFilter.value)
    searchItems.value = res.items || []
    hasNextPage.value = !!res._hasNextPage
    nextPage.value = extractNextPage(res)
  } catch (e: any) { searchItems.value = []; searchError.value = '搜索失败: ' + (e.message || e) }
  finally { searching.value = false }
}

async function loadMore() {
  if (loadingMore.value || !hasNextPage.value || !nextPage.value) return
  loadingMore.value = true
  try {
    const res: SearchResult = await api.searchMore(searchQuery.value, searchServiceId.value, nextPage.value, contentFilter.value, sortFilter.value, durationFilter.value)
    const existing = new Set(searchItems.value.map(i => i.url))
    for (const item of (res.items || [])) { if (!existing.has(item.url)) searchItems.value.push(item) }
    hasNextPage.value = !!res._hasNextPage
    nextPage.value = extractNextPage(res)
  } catch (e: any) { searchError.value = '加载更多失败: ' + (e.message || e) }
  finally { loadingMore.value = false }
}

let observer: IntersectionObserver | null = null

function onVideoClick(item: StreamInfoItem) {
  if (item.type === 'channel') router.push({ name: 'channel', query: { url: item.url || item.uploaderUrl } })
  else router.push({ name: 'video-player', query: { url: item.url } })
}

function onResultClick(item: StreamInfoItem) {
  if (item.type === 'channel') router.push({ name: 'channel', query: { url: item.url || item.uploaderUrl } })
  else if (item.type === 'playlist') { activeTab.value = 'playlists'; loadPlaylist(item.url) }
  else router.push({ name: 'video-player', query: { url: item.url } })
}
</script>

<style scoped>
.video-view { display: flex; flex-direction: column; height: 100%; overflow: hidden; }

.plugin-status { padding: 6px 12px; font-size: 12px; color: var(--fg-muted); background: var(--bg-secondary); border-bottom: 1px solid var(--border); }
.plugin-status.error { color: #e74c3c; background: #fdf0ef; }

.tabs { display: flex; border-bottom: 1px solid var(--border); flex-shrink: 0; }
.tab { flex: 1; padding: 12px; background: none; border: none; color: var(--fg-muted); font-size: 14px; font-weight: 600; cursor: pointer; border-bottom: 2px solid transparent; transition: all 0.15s; }
.tab.active { color: var(--accent); border-bottom-color: var(--accent); }

.panel { flex: 1; overflow-y: auto; padding: 12px; }

.plugin-error-detail { font-size: 11px; margin-top: 2px; }

.error-msg { padding: 8px 12px; margin-bottom: 8px; font-size: 13px; color: #e74c3c; background: #fdf0ef; border-radius: 6px; border: 1px solid #f5c6cb; }

/* --- Playlist tab --- */
.add-bar { display: flex; gap: 8px; margin-bottom: 12px; }
.add-input { flex: 1; padding: 8px 12px; border: 1px solid var(--border); border-radius: 8px; background: var(--bg-secondary); color: var(--fg); font-size: 14px; }
.add-input:focus { outline: none; border-color: var(--accent); }
.add-btn { padding: 8px 16px; background: var(--accent); color: var(--bg); border: none; border-radius: 8px; font-size: 14px; font-weight: 600; cursor: pointer; }
.add-btn:disabled { opacity: 0.5; }

.playlist-header { display: flex; gap: 12px; margin-bottom: 16px; padding-bottom: 12px; border-bottom: 1px solid var(--border); }
.pl-thumb { width: 120px; height: 68px; border-radius: 8px; object-fit: cover; background: var(--border); flex-shrink: 0; }
.pl-info h3 { font-size: 16px; font-weight: 700; margin: 0 0 4px; color: var(--fg); }
.pl-meta { font-size: 12px; color: var(--fg-muted); margin: 0 0 8px; }
.pl-duration { color: var(--fg-muted); font-size: 11px; }
.pl-actions { display: flex; gap: 6px; flex-wrap: wrap; }
.action-btn-sm { padding: 4px 10px; font-size: 11px; border-radius: 6px; border: 1px solid var(--border); background: var(--bg-secondary); color: var(--fg); cursor: pointer; white-space: nowrap; }
.action-btn-sm:hover { border-color: var(--accent); color: var(--accent); }
.bookmark-btn-sm { padding: 4px 10px; font-size: 11px; border-radius: 6px; border: 1px solid var(--accent); background: none; color: var(--accent); cursor: pointer; white-space: nowrap; }
.bookmark-btn-sm.bookmarked { background: var(--accent); color: var(--bg); }

/* Context menu for playlist items */
.item-menu { position: fixed; z-index: 9999; background: var(--bg); border: 1px solid var(--border); border-radius: 8px; box-shadow: 0 4px 16px rgba(0,0,0,0.3); padding: 4px 0; min-width: 160px; }
.item-menu-item { padding: 10px 16px; font-size: 13px; color: var(--fg); cursor: pointer; white-space: nowrap; }
.item-menu-item:hover { background: var(--border); }
.item-menu-item:first-child { border-radius: 8px 8px 0 0; }
.item-menu-item:last-child { border-radius: 0 0 8px 8px; border-top: 1px solid var(--border); color: var(--fg-muted); }

.section-title { font-size: 14px; font-weight: 600; color: var(--fg); margin: 0 0 12px; }
.bookmark-list { display: flex; flex-direction: column; gap: 8px; }
.bookmark-item { display: flex; align-items: center; gap: 10px; padding: 8px; border-radius: 8px; border: 1px solid var(--border); cursor: pointer; transition: background 0.15s; }
.bookmark-item:hover { background: var(--bg-secondary); }
.bm-thumb { width: 80px; height: 45px; border-radius: 4px; object-fit: cover; background: var(--border); flex-shrink: 0; }
.bm-info { flex: 1; min-width: 0; }
.bm-name { font-size: 13px; font-weight: 600; color: var(--fg); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.bm-meta { font-size: 11px; color: var(--fg-muted); }
.remove-btn { background: none; border: none; color: var(--fg-muted); font-size: 16px; cursor: pointer; padding: 4px; border-radius: 4px; flex-shrink: 0; }
.remove-btn:hover { background: var(--border); }

/* --- Search tab --- */

.feed-badge { background: var(--accent); color: #fff; font-size: 10px; padding: 1px 5px; border-radius: 8px; margin-left: 4px; }
.search-bar { display: flex; gap: 8px; margin-bottom: 12px; }
.filter-bar { display: flex; gap: 6px; margin-bottom: 12px; flex-wrap: wrap; }
.filter-select { padding: 6px 8px; border: 1px solid var(--border); border-radius: 6px; background: var(--bg-secondary); color: var(--fg); font-size: 12px; cursor: pointer; }
.filter-select:focus { outline: none; border-color: var(--accent); }
.service-select { padding: 8px 10px; border: 1px solid var(--border); border-radius: 8px; background: var(--bg-secondary); color: var(--fg); font-size: 13px; cursor: pointer; }
.search-input { flex: 1; padding: 8px 12px; border: 1px solid var(--border); border-radius: 8px; background: var(--bg-secondary); color: var(--fg); font-size: 14px; }
.search-input:focus { outline: none; border-color: var(--accent); }
.search-btn { padding: 8px 16px; background: var(--accent); color: var(--bg); border: none; border-radius: 8px; font-size: 14px; font-weight: 600; cursor: pointer; }
.search-btn:disabled { opacity: 0.5; }

.suggestion { font-size: 13px; color: var(--fg-muted); margin: 0 0 12px; }
.grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(180px, 1fr)); gap: 12px; }
.placeholder { text-align: center; padding: 48px 16px; color: var(--fg-muted); font-size: 14px; }
.loading { text-align: center; padding: 32px; color: var(--fg-muted); }
.end-hint { text-align: center; padding: 16px; font-size: 12px; color: var(--fg-muted); }
.scroll-sentinel { height: 1px; }

/* --- Subscription tab --- */
.subs-layout { display: flex; gap: 16px; height: 100%; }
.subs-sidebar { width: 220px; flex-shrink: 0; overflow-y: auto; border-right: 1px solid var(--border); padding-right: 8px; }
.subs-main { flex: 1; overflow-y: auto; display: flex; align-items: center; justify-content: center; }

@media (max-width: 600px) {
  .subs-layout { flex-direction: column; }
  .subs-sidebar { width: 100%; border-right: none; border-bottom: 1px solid var(--border); padding-right: 0; padding-bottom: 8px; max-height: 200px; }
}
</style>
