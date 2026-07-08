<template>
  <div class="subscriptions-view">
    <div class="subs-layout">
      <aside class="subs-sidebar">
        <div class="add-bar">
          <input v-model="subscribeUrl" class="add-input" placeholder="输入频道 URL..." @keyup.enter="subscribeChannel" />
          <select v-model="serviceName" class="service-select">
            <option value="YouTube">YouTube</option>
            <option value="BiliBili">BiliBili</option>
          </select>
          <button class="add-btn" @click="subscribeChannel" :disabled="subscribing">{{ subscribing ? '添加中...' : '订阅' }}</button>
        </div>
        <div v-if="subError" class="error-msg">{{ subError }}</div>
        <SubscriptionList :list="subStore.sorted" :active-url="selectedSub?.url" @select="onSubSelect" />
      </aside>
      <main class="subs-main">
        <div v-if="!selectedSub" class="placeholder">选择一个订阅频道查看最新视频</div>
        <div v-else-if="channelLoading" class="loading">加载中...</div>
        <div v-else-if="channelError" class="error-msg">{{ channelError }}</div>
        <template v-else>
          <div class="channel-header">
            <img :src="proxyImageUrl(selectedSub.avatarUrl)" :alt="selectedSub.name" class="channel-avatar" loading="lazy" @error="onAvatarError" />
            <div class="channel-info">
              <h2>{{ selectedSub.name }}</h2>
              <p class="channel-meta">{{ formatCount(selectedSub.subscriberCount) }} 订阅者</p>
              <p v-if="selectedSub.description" class="channel-desc">{{ selectedSub.description }}</p>
            </div>
          </div>
          <div class="grid">
            <VideoCard v-for="item in channelItems" :key="item.url" :item="item" @cardClick="onVideoClick" />
          </div>
        </template>
      </main>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import PipePipe, { api } from '../plugins/bridge'
import type { ChannelInfoResult, StreamInfoItem } from '../plugins/bridge'
import { proxyImageUrl } from '../extractor/BilibiliImageProxy'
import { useSubscriptionsStore } from '../stores/subscriptions'
import VideoCard from '../components/VideoCard.vue'
import SubscriptionList from '../components/SubscriptionList.vue'

const router = useRouter()
const subStore = useSubscriptionsStore()

const subCount = computed(() => subStore.subscriptions.length)

const subscribeUrl = ref('')
const serviceName = ref('YouTube')
const subscribing = ref(false)
const subError = ref('')

const selectedSub = ref(subStore.subscriptions[0] || undefined)
const channelLoading = ref(false)
const channelError = ref('')
const channelItems = ref<StreamInfoItem[]>([])

function onAvatarError(e: Event) {
  (e.target as HTMLImageElement).style.display = 'none'
}

onMounted(async () => {
  if (subStore.subscriptions.length > 0 && !selectedSub.value) {
    selectedSub.value = subStore.subscriptions[0]
  }
  if (selectedSub.value) {
    await loadChannelInfo(selectedSub.value)
  }
})

async function subscribeChannel() {
  const url = subscribeUrl.value.trim()
  if (!url) return
  subscribing.value = true
  subError.value = ''
  try {
    const resolved = await api.resolveUrl(url)
    const info: ChannelInfoResult = await api.getChannelInfo(url, resolved.serviceId)
    subStore.subscribe({
      serviceId: resolved.serviceId,
      url,
      name: info.name,
      avatarUrl: info.avatarUrl,
      subscriberCount: info.subscriberCount,
      description: info.description,
    })
    const sub = subStore.getByUrl(url)
    if (sub) {
      selectedSub.value = sub
      channelItems.value = info.items
    }
    subscribeUrl.value = ''
  } catch (e: any) {
    subError.value = '订阅失败: ' + (e.message || e)
  } finally {
    subscribing.value = false
  }
}

async function loadChannelInfo(sub: any) {
  channelLoading.value = true
  channelError.value = ''
  channelItems.value = []
  try {
    let sid = sub.serviceId ?? -1
    if (sid < 0) { try { const r = await api.resolveUrl(sub.url); sid = r.serviceId } catch {} }
    if (sid < 0) { channelError.value = '无法解析 serviceId: ' + sub.url; channelLoading.value = false; return }
    const info = await api.getChannelInfo(sub.url, sid)
    subStore.updateInfo(sub.url, {
      name: info.name,
      avatarUrl: info.avatarUrl,
      subscriberCount: info.subscriberCount,
      description: info.description,
    })
    channelItems.value = info.items
  } catch (e: any) {
    channelError.value = '加载频道信息失败: ' + (e.message || e)
  } finally {
    channelLoading.value = false
  }
}

async function onSubSelect(sub: any) {
  selectedSub.value = sub
  await loadChannelInfo(sub)
}

function onVideoClick(item: StreamInfoItem) {
  router.push({ name: 'video-player', query: { url: item.url } })
}

function formatCount(n: number): string {
  if (n >= 10000) return (n / 10000).toFixed(1) + '万'
  if (n >= 1000) return (n / 1000).toFixed(1) + 'k'
  return String(n)
}
</script>

<style scoped>
.subscriptions-view { height: 100%; overflow: hidden; }

.subs-layout { display: flex; gap: 16px; height: 100%; }

.subs-sidebar { width: 280px; flex-shrink: 0; display: flex; flex-direction: column; overflow: hidden; border-right: 1px solid var(--border); padding-right: 8px; }

.subs-main { flex: 1; overflow-y: auto; }

.add-bar { display: flex; gap: 6px; margin-bottom: 8px; flex-shrink: 0; }
.add-input { flex: 1; padding: 8px 12px; border: 1px solid var(--border); border-radius: 8px; background: var(--bg-secondary); color: var(--fg); font-size: 13px; min-width: 0; }
.add-input:focus { outline: none; border-color: var(--accent); }
.service-select { padding: 8px 8px; border: 1px solid var(--border); border-radius: 8px; background: var(--bg-secondary); color: var(--fg); font-size: 12px; cursor: pointer; }
.add-btn { padding: 8px 12px; background: var(--accent); color: var(--bg); border: none; border-radius: 8px; font-size: 13px; font-weight: 600; cursor: pointer; white-space: nowrap; }
.add-btn:disabled { opacity: 0.5; }

.error-msg { padding: 6px 10px; margin-bottom: 8px; font-size: 12px; color: #e74c3c; background: #fdf0ef; border-radius: 6px; border: 1px solid #f5c6cb; flex-shrink: 0; }

.channel-header { display: flex; align-items: center; gap: 12px; margin-bottom: 16px; padding-bottom: 12px; border-bottom: 1px solid var(--border); }
.channel-avatar { width: 56px; height: 56px; border-radius: 50%; object-fit: cover; background: var(--border); }
.channel-info h2 { font-size: 18px; font-weight: 700; margin: 0 0 4px; color: var(--fg); }
.channel-meta { font-size: 12px; color: var(--fg-muted); margin: 0 0 4px; }
.channel-desc { font-size: 12px; color: var(--fg-muted); margin: 0; display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; }

.grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(180px, 1fr)); gap: 12px; }

.placeholder { text-align: center; padding: 48px 16px; color: var(--fg-muted); font-size: 14px; }
.loading { text-align: center; padding: 32px; color: var(--fg-muted); }

@media (max-width: 600px) {
  .subs-layout { flex-direction: column; }
  .subs-sidebar { width: 100%; border-right: none; border-bottom: 1px solid var(--border); padding-right: 0; padding-bottom: 8px; max-height: 200px; }
  .grid { grid-template-columns: repeat(2, 1fr); }
}
</style>
