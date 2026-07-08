<template>
  <div
    class="channel-view"
    @touchstart="onTouchStart"
    @touchmove="onTouchMove"
    @touchend="onTouchEnd"
    :style="{ transform: swipeOffset > 0 ? `translateY(${swipeOffset}px)` : '', opacity: swipeOpacity, transition: swiping ? 'none' : 'transform 0.2s, opacity 0.2s' }"
  >
    <div v-if="loading" class="loading">加载频道...</div>
    <template v-else-if="channel">
      <div class="channel-header">
        <img :src="proxied(channel?.avatarUrl)" :alt="channel.name" class="channel-avatar" loading="lazy" referrerpolicy="no-referrer" @error="hideOnError" />
        <div class="channel-info">
          <h1 class="channel-name">
            {{ channel.name || '(无名称)' }}
            <span v-if="channel.verified" class="verified-badge">✓</span>
          </h1>
          <p class="channel-meta">{{ fmtCount(channel.subscriberCount) }} 订阅者</p>
          <p v-if="channel.description" class="channel-desc" :class="{ expanded: descExpanded }" @click="descExpanded = !descExpanded">
            {{ channel.description }}
            <span v-if="!descExpanded && channel.description.length > 80" class="desc-more">...更多</span>
          </p>
          <div class="ch-actions">
            <button class="sub-btn" :class="{ subscribed: isSubscribed }" @click="toggleSub">
              {{ isSubscribed ? '已订阅' : '订阅' }}
            </button>
            <button
              v-if="isSubscribed"
              class="notif-btn"
              :class="{ enabled: notifEnabled }"
              @click="toggleNotif"
              :title="notifEnabled ? '通知已开启' : '通知已关闭'"
            >{{ notifEnabled ? '🔔' : '🔕' }}</button>
            <button v-if="tabItems.length > 0" class="play-all-btn" @click="playAllChannel">▶ 全部播放</button>
          </div>
        </div>
      </div>

      <div v-if="channel.tabs && channel.tabs.length > 0" class="channel-tabs">
        <button
          v-for="tab in channel.tabs"
          :key="tab.name"
          class="ch-tab"
          :class="{ active: activeTabName === tab.name }"
          @click="switchTab(tab)"
        >{{ tabLabel(tab.name) }}</button>
      </div>

      <div class="tab-content">
        <!-- 正在查看某个合集时显示合集内视频 -->
        <template v-if="viewingPlaylist">
          <div class="playlist-subheader">
            <button class="back-btn" @click="viewingPlaylist = null">← 返回</button>
            <img :src="proxied(viewingPlaylist.thumbnailUrl)" class="pl-thumb-sm" loading="lazy" @error="hideOnError" />
            <div class="pl-info-sm">
              <strong>{{ viewingPlaylist.name }}</strong>
              <span class="pl-meta-sm">{{ viewingPlaylist.uploaderName }} · {{ viewingPlaylist.streamCount || 0 }} 视频</span>
            </div>
            <button class="action-btn-sm" @click="playAllPlaylistItems">▶ 全部播放</button>
          </div>
          <div class="grid">
            <VideoCard
              v-for="item in playlistItems"
              :key="item.url"
              :item="item"
              @cardClick="onVideoClick(item)"
            />
          </div>
          <div v-if="loadingMorePlaylist" class="loading">加载更多...</div>
          <div v-else-if="!playlistHasMore && playlistItems.length > 0" class="end-hint">已显示全部</div>
          <div v-else-if="playlistItems.length === 0" class="placeholder">合集为空</div>
          <div ref="plBottomSentinel" class="scroll-sentinel"></div>
        </template>

        <!-- 正常 tab 内容 -->
        <template v-else>
          <div class="grid">
            <VideoCard
              v-for="(item, i) in tabItems"
              :key="item.url"
              :item="item"
              @cardClick="onItemClick(item)"
              @touchstart.passive="onLongPressStart($event, item, i)"
              @touchend="onLongPressEnd"
              @touchmove="onLongPressEnd"
            />
          </div>
          <div v-if="tabLoading" class="loading">加载中...</div>
          <div v-else-if="!tabHasNext && tabItems.length > 0" class="end-hint">已显示全部</div>
          <div v-else-if="tabItems.length === 0 && !tabLoading" class="placeholder">该分类暂无内容<template v-if="tabError"> ({{ tabError }})</template></div>
          <div ref="scrollSentinel" class="scroll-sentinel"></div>
        </template>
      </div>
    </template>

    <div v-if="error" class="error-panel">
      <div class="error-header" @click="showRaw = !showRaw">
        <span class="err-icon">⚠️</span>
        <span>{{ error }}</span>
        <span class="err-toggle">{{ showRaw ? '▲' : '▼' }}</span>
      </div>
      <div v-if="showRaw" class="error-detail">
        <div class="diag-row" v-if="rawResult"><span class="diag-key">原生结果:</span><pre class="diag-pre">{{ JSON.stringify(rawResult, null, 2) }}</pre></div>
        <div class="diag-row" v-if="rawError"><span class="diag-key">原生错误:</span><pre class="diag-pre">{{ rawError }}</pre></div>
      </div>
    </div>

    <Teleport to="body">
      <div v-if="itemMenu.show" class="item-menu" :style="{ top: itemMenu.y + 'px', left: itemMenu.x + 'px' }" @click.stop @touchend.prevent.stop>
        <div class="item-menu-item" @click="playFromHere">▶ 从此处播放</div>
        <div class="item-menu-item" @click="enqueueFromHere">📋 从此处加入队列</div>
        <div class="item-menu-item" @click="itemMenu.show = false">取消</div>
      </div>
    </Teleport>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, onUnmounted, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useSubscriptionsStore } from '../stores/subscriptions'
import { usePlayQueueStore } from '../stores/playQueue'
import { debugToast } from '../utils/error'
import { pushDebugLog } from '../api'
import PipePipe, { api, extractNextPage } from '../plugins/bridge'
import type { ChannelInfoResult, ChannelTabInfoResult, StreamInfoItem, Page } from '../plugins/bridge'
import VideoCard from '../components/VideoCard.vue'
import { proxyImageUrl } from '../extractor/BilibiliImageProxy'

function proxied(url: string | undefined | null): string { return proxyImageUrl(url || '') }

const route = useRoute()
const router = useRouter()
const subStore = useSubscriptionsStore()
const queueStore = usePlayQueueStore()

const channel = ref<ChannelInfoResult | null>(null)
const loading = ref(true)
const error = ref('')
const channelUrl = ref('')
const serviceId = ref(-1)
const isSubscribed = ref(false)
const notifEnabled = ref(false)
const descExpanded = ref(false)
const showRaw = ref(false)
const rawResult = ref<any>(null)
const rawError = ref<string | null>(null)

const activeTabName = ref('videos')
const activeTabUrl = ref('')
const activeTabId = ref('')
const scrollSentinel = ref<HTMLElement | null>(null)

const tabItems = ref<StreamInfoItem[]>([])
const tabLoading = ref(false)
const tabLoadingMore = ref(false)
const tabError = ref('')
const tabNextPage = ref<Page | null>(null)
const tabHasNext = ref(false)

const itemMenu = ref<{ show: boolean; x: number; y: number; item: StreamInfoItem | null; index: number }>({ show: false, x: 0, y: 0, item: null, index: -1 })

let observer: IntersectionObserver | null = null
const swipeStartY = ref(0)
const swipeOffset = ref(0)
const swipeOpacity = ref(1)
const swiping = ref(false)
let _swipeAnimFrame: number | null = null

function hideOnError(e: Event) {
  const el = e.target as HTMLElement
  el.style.display = 'none'
}

onMounted(async () => {
  const url = route.query.url as string
  if (!url) { error.value = '缺少频道 URL'; loading.value = false; return }
  channelUrl.value = url
  isSubscribed.value = subStore.isSubscribed(url)
  notifEnabled.value = subStore.getNotif(url)
  try { const r = await api.resolveUrl(url); serviceId.value = r.serviceId } catch (e: any) {
    error.value = '解析URL失败(' + url + '): ' + (e.message || e)
    loading.value = false
    return
  }
  if (serviceId.value < 0) { error.value = '无法解析 serviceId: ' + url; loading.value = false; return }

  try {
    pushDebugLog(`[Channel] fetching info url=${url}`)
    const info = await api.getChannelInfo(url, serviceId.value)
    rawResult.value = info
    channel.value = info
    pushDebugLog(`[Channel] name=${info.name} avatar=${info.avatarUrl ? '存在' : '空'} subs=${info.subscriberCount} items=${info.items?.length || 0} tabs=${info.tabs?.length || 0} _error=${info._error || '(none)'}`)
    subStore.updateInfo(url, {
      name: info.name,
      avatarUrl: info.avatarUrl,
      subscriberCount: info.subscriberCount,
      description: info.description,
    })
    const extractionFailed = !info.name && !info.avatarUrl && info.subscriberCount === 0
    if (!info.items && (!info.tabs || info.tabs.length === 0)) {
      error.value = '频道数据为空 (items=' + (info.items?.length || 0) + ', tabs=' + (info.tabs?.length || 0) + ')' +
        (extractionFailed ? ' [提取器返回空字段，可能API响应异常]' : '')
      pushDebugLog(`[Channel] empty: ${error.value}`)
      loading.value = false
      return
    }
    if (extractionFailed && (!info.tabs || info.tabs.length === 0)) {
      debugToast('频道提取可能失败: name/avatar/subscriber 全空', 5000)
    }
    tabItems.value = info.items || []
    tabHasNext.value = !!info._hasNextPage
    if (info.tabs && info.tabs.length > 0) {
      const firstTab = info.tabs[0]
      activeTabName.value = firstTab.name
      activeTabUrl.value = firstTab.url
      activeTabId.value = firstTab.tabId || ''
      pushDebugLog(`[Channel] firstTab name=${firstTab.name} url=${firstTab.url}`)
      try {
        await loadTab(firstTab.url)
        if (tabError.value && tabItems.value.length === 0) {
          error.value = 'Tab加载失败(' + tabError.value + ')'
          pushDebugLog(`[Channel] tabError: ${tabError.value}`)
        } else if (tabError.value) {
          debugToast('Tab加载部分失败: ' + tabError.value, 3000)
        }
      } catch (e: any) {
        error.value = 'Tab加载失败(' + (e.message || e) + ')'
        pushDebugLog(`[Channel] tab catch: ${e.message || e}`)
      }
    } else {
      pushDebugLog(`[Channel] no tabs, direct items=${tabItems.value.length}`)
    }
  } catch (e: any) {
    error.value = '加载频道失败: ' + (e.message || e)
    rawError.value = e.stack || e.toString()
    pushDebugLog(`[Channel] catch: ${e.message || e}`)
  } finally {
    loading.value = false
    pushDebugLog(`[Channel] done error=${error.value || '(none)'} tabItems=${tabItems.value.length}`)
  }
  
  if (typeof IntersectionObserver !== 'undefined') {
    observer = new IntersectionObserver((entries) => {
      if (entries[0]?.isIntersecting && tabHasNext.value && !tabLoadingMore.value) loadMoreTab()
    }, { rootMargin: '200px' })
  }
})

watch(scrollSentinel, (el) => {
  if (observer && el) { observer.disconnect(); observer.observe(el) }
})

onUnmounted(() => { observer?.disconnect() })

function tabLabel(name: string): string {
  const map: Record<string, string> = {
    videos: '视频', playlists: '播放列表', channels: '频道',
    articles: '专栏', about: '关于',
  }
  return map[name] || name
}

async function switchTab(tab: ChannelTabInfoResult) {
  if (activeTabName.value === tab.name) return
  activeTabName.value = tab.name
  activeTabUrl.value = tab.url
  activeTabId.value = tab.tabId || ''
  await loadTab(tab.url)
  if (tabError.value && channel.value) {
    tabItems.value = channel.value.items || []
    tabHasNext.value = !!channel.value._hasNextPage
  }
}

async function loadTab(tabUrl: string) {
  tabLoading.value = true; tabError.value = ''
  try {
    const isVideos = activeTabName.value === 'videos'
    if (isVideos && channel.value?.items?.length) {
      pushDebugLog(`[ChannelTab] videos tab: use channel direct items=${channel.value.items.length}`)
      tabItems.value = channel.value.items
      tabNextPage.value = extractNextPage(channel.value)
      tabHasNext.value = !!channel.value._hasNextPage
      return
    }
    pushDebugLog(`[ChannelTab] loading tabUrl=${tabUrl} tabId=${activeTabId.value}`)
    const r = await api.getChannelTabPage({ tabUrl, tabId: activeTabId.value || undefined, serviceId: serviceId.value })
    const itemCount = r?.items?.length || 0
    pushDebugLog(`[ChannelTab] items=${itemCount} _error=${r?._error || '(none)'}`)
    if (r._error) {
      tabError.value = 'Tab加载失败: ' + r._error
      if (channel.value) { tabItems.value = channel.value.items || []; tabHasNext.value = !!channel.value._hasNextPage }
      return
    }
    tabItems.value = r.items || []
    tabNextPage.value = extractNextPage(r)
    tabHasNext.value = !!r._hasNextPage
    if (itemCount === 0) {
      pushDebugLog(`[ChannelTab] 0 items — tabUrl=${tabUrl} serviceId=${serviceId.value} channelName=${channel.value?.name || '(空)'}`)
      debugToast('Tab 提取返回 0 项', 4000)
    }
  } catch (e: any) {
    tabError.value = 'Tab加载失败: ' + (e.message || e)
    pushDebugLog(`[ChannelTab] catch: ${e.message || e}`)
    if (channel.value) { tabItems.value = channel.value.items || []; tabHasNext.value = !!channel.value._hasNextPage }
  }
  finally { tabLoading.value = false; pushDebugLog(`[ChannelTab] done items=${tabItems.value.length}`) }
}

async function loadMoreTab() {
  if (tabLoadingMore.value || !tabHasNext.value || !tabNextPage.value) return
  tabLoadingMore.value = true
  try {
    const isVideos = activeTabName.value === 'videos'
    const page = tabNextPage.value
    const r = isVideos
      ? await api.getMoreChannelItems(channelUrl.value, serviceId.value, undefined, page)
      : await api.getChannelTabPage({ tabUrl: activeTabUrl.value, tabId: activeTabId.value || undefined, serviceId: serviceId.value, tabName: activeTabName.value, page })
    const existing = new Set(tabItems.value.map(i => i.url))
    for (const item of (r.items || [])) { if (!existing.has(item.url)) tabItems.value.push(item) }
    tabNextPage.value = extractNextPage(r)
    tabHasNext.value = !!r._hasNextPage
  } catch (e: any) { tabError.value = '加载更多失败: ' + (e.message || e) }
  finally { tabLoadingMore.value = false }
}

function playAllChannel() {
  if (!tabItems.value.length) return
  queueStore.replaceWith(tabItems.value.map(item => ({ url: item.url, title: item.name, thumbnailUrl: item.thumbnailUrl, duration: item.duration || 0, uploaderName: item.uploaderName || '' })))
  router.push({ name: 'video-player', query: { url: tabItems.value[0].url } })
}

let _longPressTimer: ReturnType<typeof setTimeout> | null = null

function onLongPressStart(e: TouchEvent, item: StreamInfoItem, index: number) {
  _longPressTimer = setTimeout(() => {
    _longPressTimer = null
    const touch = e.touches[0]
    itemMenu.value = { show: true, x: touch.clientX, y: touch.clientY, item, index }
    const close = (ev: Event) => {
      if (!(ev.target as HTMLElement)?.closest?.('.item-menu')) {
        itemMenu.value.show = false
        document.removeEventListener('click', close)
        document.removeEventListener('touchend', close)
      }
    }
    setTimeout(() => {
      document.addEventListener('click', close)
      document.addEventListener('touchend', close)
    }, 0)
  }, 500)
}

function onLongPressEnd() {
  if (_longPressTimer) {
    clearTimeout(_longPressTimer)
    _longPressTimer = null
  }
}

function playFromHere() {
  if (!itemMenu.value.item) return
  const idx = itemMenu.value.index
  const itemsFrom = tabItems.value.slice(idx)
  queueStore.replaceWith(itemsFrom.map(item => ({
    url: item.url, title: item.name, thumbnailUrl: item.thumbnailUrl,
    duration: item.duration || 0, uploaderName: item.uploaderName || '',
  })))
  itemMenu.value.show = false
  router.push({ name: 'video-player', query: { url: itemMenu.value.item.url } })
}

function enqueueFromHere() {
  if (!itemMenu.value.item) return
  const idx = itemMenu.value.index
  const itemsFrom = tabItems.value.slice(idx)
  for (const item of itemsFrom) {
    queueStore.add({ url: item.url, title: item.name, thumbnailUrl: item.thumbnailUrl,
      duration: item.duration || 0, uploaderName: item.uploaderName || '' })
  }
  itemMenu.value.show = false
}

function onTouchStart(e: TouchEvent) {
  swipeStartY.value = e.touches[0].clientY
  swipeOffset.value = 0
  swipeOpacity.value = 1
  swiping.value = true
}

function onTouchMove(e: TouchEvent) {
  if (!swiping.value) return
  const dy = e.touches[0].clientY - swipeStartY.value
  if (dy > 0) {
    _swipeAnimFrame && cancelAnimationFrame(_swipeAnimFrame)
    _swipeAnimFrame = requestAnimationFrame(() => {
      swipeOffset.value = dy * 0.6
      swipeOpacity.value = Math.max(0.4, 1 - dy / 500)
    })
  }
}

function onTouchEnd(e: TouchEvent) {
  swiping.value = false
  const dy = e.changedTouches[0].clientY - swipeStartY.value
  swipeOffset.value = 0
  swipeOpacity.value = 1
  if (dy > 150) {
    router.back()
  }
}

async function toggleSub() {
  if (isSubscribed.value) {
    subStore.unsubscribe(channelUrl.value)
    isSubscribed.value = false
    notifEnabled.value = false
  } else if (channel.value) {
    let serviceId = subStore.guessServiceId(channelUrl.value)
    try { const resolved = await api.resolveUrl(channelUrl.value); serviceId = resolved.serviceId } catch {}
    subStore.subscribe({
      url: channelUrl.value,
      name: channel.value.name || '',
      avatarUrl: channel.value.avatarUrl || '',
      subscriberCount: channel.value.subscriberCount || 0,
      description: channel.value.description || '',
      serviceId,
      notifEnabled: false,
    })
    isSubscribed.value = true
  }
}

function toggleNotif() {
  notifEnabled.value = !notifEnabled.value
  subStore.setNotif(channelUrl.value, notifEnabled.value)
}

function onItemClick(item: StreamInfoItem) {
  if (item.type === 'channel') {
    router.push({ name: 'channel', query: { url: item.url || item.uploaderUrl } })
  } else if (item.type === 'playlist') {
    openPlaylist(item)
  } else {
    router.push({ name: 'video-player', query: { url: item.url } })
  }
}

function onVideoClick(item: StreamInfoItem) {
  if (item.type === 'channel') {
    router.push({ name: 'channel', query: { url: item.url || item.uploaderUrl } })
  } else {
    router.push({ name: 'video-player', query: { url: item.url } })
  }
}

const viewingPlaylist = ref<StreamInfoItem | null>(null)
const playlistItems = ref<StreamInfoItem[]>([])
const loadingMorePlaylist = ref(false)
const playlistHasMore = ref(false)
const playlistNextPage = ref<Page | null>(null)
const plBottomSentinel = ref<HTMLElement | null>(null)
let plBottomObserver: IntersectionObserver | null = null

async function openPlaylist(item: StreamInfoItem) {
  viewingPlaylist.value = item
  playlistItems.value = []
  playlistHasMore.value = false
  playlistNextPage.value = null
  try {
    const res = await api.getPlaylistInfo(item.url, serviceId.value)
    playlistItems.value = res.items || []
    playlistHasMore.value = !!res._hasNextPage
    playlistNextPage.value = extractNextPage(res)
  } catch (e: any) {
    console.warn('openPlaylist failed', e)
    playlistItems.value = []
  }
  setupPlaylistScroll()
}

async function loadMorePlaylistItems() {
  if (loadingMorePlaylist.value || !playlistHasMore.value || !playlistNextPage.value) return
  loadingMorePlaylist.value = true
  try {
    const res = await api.getMorePlaylistItems(viewingPlaylist.value!.url, serviceId.value, undefined, playlistNextPage.value)
    const existingUrls = new Set(playlistItems.value.map(i => i.url))
    for (const item of (res.items || [])) {
      if (!existingUrls.has(item.url)) {
        playlistItems.value.push(item)
        existingUrls.add(item.url)
      }
    }
    playlistHasMore.value = !!res._hasNextPage
    playlistNextPage.value = extractNextPage(res)
  } catch (e: any) {
    console.warn('loadMorePlaylistItems failed', e)
  }
  finally { loadingMorePlaylist.value = false }
}

function setupPlaylistScroll() {
  plBottomObserver?.disconnect()
  if (typeof IntersectionObserver === 'undefined') return
  plBottomObserver = new IntersectionObserver((entries) => {
    if (entries[0]?.isIntersecting && playlistHasMore.value && !loadingMorePlaylist.value) {
      loadMorePlaylistItems()
    }
  }, { rootMargin: '200px' })
  watch(plBottomSentinel, (el) => {
    if (plBottomObserver && el) { plBottomObserver.disconnect(); plBottomObserver.observe(el) }
  }, { immediate: true })
}

function playAllPlaylistItems() {
  if (!playlistItems.value.length) return
  queueStore.replaceWith(playlistItems.value.map(item => ({
    url: item.url, title: item.name, thumbnailUrl: item.thumbnailUrl,
    duration: item.duration || 0, uploaderName: item.uploaderName || '',
  })))
  router.push({ name: 'video-player', query: { url: playlistItems.value[0].url } })
}

function fmtCount(n: number): string {
  if (!n || n < 0) return '未知'
  if (n >= 10000) return (n / 10000).toFixed(1) + '万'
  if (n >= 1000) return (n / 1000).toFixed(1) + 'k'
  return String(n)
}
</script>

<style scoped>
.channel-view { display: flex; flex-direction: column; height: 100%; overflow: hidden; }
.loading { text-align: center; padding: 48px; color: var(--fg-muted); }
.channel-header { display: flex; gap: 16px; align-items: flex-start; padding: 16px; border-bottom: 1px solid var(--border); flex-shrink: 0; }
.channel-avatar { width: 80px; height: 80px; border-radius: 50%; object-fit: cover; background: var(--border); flex-shrink: 0; }
.channel-info { flex: 1; min-width: 0; }
.channel-name { font-size: 22px; font-weight: 700; margin: 0 0 4px; color: var(--fg); display: flex; align-items: center; gap: 6px; }
.verified-badge { font-size: 14px; color: var(--accent); }
.channel-meta { font-size: 13px; color: var(--fg-muted); margin: 0 0 8px; }
.channel-desc { font-size: 13px; color: var(--fg-muted); line-height: 1.5; margin: 0 0 12px; white-space: pre-wrap; max-height: 80px; overflow: hidden; cursor: pointer; }
.channel-desc.expanded { max-height: none; }
.desc-more { color: var(--accent); font-size: 12px; }
.ch-actions { display: flex; gap: 6px; flex-wrap: wrap; align-items: center; }
.sub-btn { padding: 6px 16px; font-size: 13px; border-radius: 6px; border: 1px solid var(--accent); background: none; color: var(--accent); cursor: pointer; font-weight: 600; }
.sub-btn.subscribed { background: var(--accent); color: var(--bg); }
.notif-btn { background: none; border: 1px solid var(--border); border-radius: 6px; cursor: pointer; font-size: 16px; padding: 4px 8px; }
.notif-btn.enabled { border-color: var(--accent); }
.play-all-btn { padding: 6px 14px; font-size: 12px; border-radius: 6px; border: 1px solid var(--border); background: var(--bg-secondary); color: var(--fg); cursor: pointer; }
.play-all-btn:hover { border-color: var(--accent); color: var(--accent); }

.channel-tabs { display: flex; border-bottom: 1px solid var(--border); flex-shrink: 0; overflow-x: auto; }
.ch-tab { padding: 10px 16px; background: none; border: none; color: var(--fg-muted); font-size: 13px; font-weight: 600; cursor: pointer; border-bottom: 2px solid transparent; white-space: nowrap; }
.ch-tab.active { color: var(--accent); border-bottom-color: var(--accent); }

.tab-content { flex: 1; overflow-y: auto; padding: 12px; }
.grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(180px, 1fr)); gap: 12px; }
.placeholder, .end-hint { text-align: center; padding: 32px; color: var(--fg-muted); font-size: 14px; }
.scroll-sentinel { height: 1px; }

.error-panel { border: 1px solid #e74c3c; background: rgba(231,76,60,0.08); border-radius: 8px; margin: 8px; overflow: hidden; flex-shrink: 0; }
.error-header { display: flex; align-items: center; gap: 8px; padding: 10px 12px; cursor: pointer; color: #e74c3c; font-size: 13px; font-weight: 600; }
.err-icon { font-size: 16px; }
.err-toggle { margin-left: auto; font-size: 12px; }
.error-detail { padding: 8px 12px 12px; }
.diag-row { margin-bottom: 8px; word-break: break-all; }
.diag-key { font-size: 11px; font-weight: 600; color: var(--fg-muted); display: block; margin-bottom: 2px; }
.diag-pre { font-size: 11px; background: rgba(0,0,0,0.2); padding: 8px; border-radius: 4px; max-height: 200px; overflow: auto; white-space: pre-wrap; word-break: break-all; margin: 0; }

.item-menu { position: fixed; z-index: 9999; background: var(--bg); border: 1px solid var(--border); border-radius: 8px; box-shadow: 0 4px 16px rgba(0,0,0,0.3); padding: 4px 0; min-width: 160px; }
.item-menu-item { padding: 10px 16px; font-size: 13px; color: var(--fg); cursor: pointer; white-space: nowrap; }
.item-menu-item:hover { background: var(--border); }
.item-menu-item:first-child { border-radius: 8px 8px 0 0; }
.item-menu-item:last-child { border-radius: 0 0 8px 8px; border-top: 1px solid var(--border); color: var(--fg-muted); }

.playlist-subheader { display: flex; gap: 8px; align-items: center; padding: 8px 0; border-bottom: 1px solid var(--border); margin-bottom: 12px; }
.back-btn { padding: 4px 10px; font-size: 12px; border-radius: 4px; border: 1px solid var(--border); background: var(--bg-secondary); color: var(--fg); cursor: pointer; }
.pl-thumb-sm { width: 40px; height: 24px; object-fit: cover; border-radius: 3px; background: var(--border); flex-shrink: 0; }
.pl-info-sm { flex: 1; min-width: 0; }
.pl-info-sm strong { font-size: 12px; color: var(--fg); display: block; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.pl-meta-sm { font-size: 11px; color: var(--fg-muted); }
.action-btn-sm { padding: 4px 10px; font-size: 11px; border-radius: 4px; border: 1px solid var(--accent); background: none; color: var(--accent); cursor: pointer; white-space: nowrap; }
</style>
