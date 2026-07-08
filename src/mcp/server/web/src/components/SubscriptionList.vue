<template>
  <div class="sub-list">
    <div v-if="list.length === 0" class="empty">
      <p>还没有订阅任何频道</p>
      <p class="hint">在搜索中点击频道名可订阅</p>
    </div>
    <div
      v-for="sub in list"
      :key="sub.url"
      class="sub-item"
      :class="{ active: sub.url === activeUrl }"
      @click="$emit('select', sub)"
    >
      <img :src="proxyImageUrl(sub.avatarUrl)" :alt="sub.name" class="avatar" loading="lazy" @error="hideAvatar" />
      <div class="sub-info">
        <span class="sub-name">{{ sub.name }}</span>
        <span v-if="sub.subscriberCount > 0" class="sub-count">
          {{ formatCount(sub.subscriberCount) }} 订阅
        </span>
      </div>
      <button class="unsub-btn" @click.stop="store.unsubscribe(sub.url)" title="取消订阅">✕</button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { proxyImageUrl } from '../extractor/BilibiliImageProxy'
import type { Subscription } from '../stores/subscriptions'
import { useSubscriptionsStore } from '../stores/subscriptions'

defineProps<{ list: Subscription[]; activeUrl?: string }>()
defineEmits<{ select: [sub: Subscription] }>()

const store = useSubscriptionsStore()

function hideAvatar(e: Event) {
  const el = e.target as HTMLElement
  el.style.display = 'none'
}

function formatCount(n: number): string {
  if (n >= 10000) return (n / 10000).toFixed(1) + '万'
  if (n >= 1000) return (n / 1000).toFixed(1) + 'k'
  return String(n)
}
</script>

<style scoped>
.sub-list {
  display: flex;
  flex-direction: column;
  gap: 2px;
}
.empty {
  text-align: center;
  padding: 32px 16px;
  color: var(--fg-muted);
  font-size: 14px;
}
.empty .hint {
  font-size: 12px;
  margin-top: 8px;
}
.sub-item {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px 12px;
  border-radius: 8px;
  cursor: pointer;
  transition: background 0.15s;
}
.sub-item:hover, .sub-item.active {
  background: var(--border);
}
.avatar {
  width: 40px;
  height: 40px;
  border-radius: 50%;
  object-fit: cover;
  flex-shrink: 0;
  background: var(--border);
}
.sub-info {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 2px;
}
.sub-name {
  font-size: 14px;
  font-weight: 600;
  color: var(--fg);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.sub-count {
  font-size: 11px;
  color: var(--fg-muted);
}
.unsub-btn {
  background: none;
  border: none;
  color: var(--fg-muted);
  font-size: 14px;
  cursor: pointer;
  padding: 4px 6px;
  border-radius: 4px;
  opacity: 0;
  transition: opacity 0.15s;
}
.sub-item:hover .unsub-btn {
  opacity: 1;
}
.unsub-btn:hover {
  color: var(--danger);
  background: var(--border);
}
</style>
