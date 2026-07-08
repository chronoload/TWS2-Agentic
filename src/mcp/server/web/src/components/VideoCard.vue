<template>
  <div class="video-card" @click="$emit('cardClick', item)">
    <div class="thumbnail-wrap">
      <img
        :src="thumbSrc"
        :alt="item.name"
        class="thumbnail"
        loading="lazy"
        referrerpolicy="no-referrer"
      />
      <span v-if="durationStr" class="duration-badge">{{ durationStr }}</span>
      <button class="pl-add-btn" @click.stop="$emit('addToPlaylist', item)" title="添加到合集">📋</button>
    </div>
    <div class="info">
      <div class="title-row">
        <img
          v-if="item.uploaderAvatarUrl"
          :src="avatarSrc"
          class="uploader-avatar"
          loading="lazy"
          @click.stop="$emit('cardClick', { ...item, type: 'channel', url: item.uploaderUrl })"
        />
        <p class="title">{{ item.name }}</p>
      </div>
      <p class="meta">
        <span v-if="item.uploaderName" class="uploader">{{ item.uploaderName }}</span>
        <span v-if="item.viewCount !== undefined && item.viewCount >= 0" class="views">
          {{ formatCount(item.viewCount) }} 次观看
        </span>
      </p>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import type { StreamInfoItem } from '../plugins/bridge'
import { proxyImageUrl } from '../extractor/BilibiliImageProxy'

const props = defineProps<{ item: StreamInfoItem }>()
defineEmits<{ cardClick: [item: any]; addToPlaylist: [item: StreamInfoItem] }>()

const thumbSrc = ref(proxyImageUrl(props.item.thumbnailUrl || ''))
const avatarSrc = ref(proxyImageUrl(props.item.uploaderAvatarUrl || ''))

const durationStr = computed(() => props.item.duration ? formatDuration(props.item.duration) : '')

function formatDuration(seconds: number): string {
  const h = Math.floor(seconds / 3600)
  const m = Math.floor((seconds % 3600) / 60)
  const s = seconds % 60
  if (h > 0) return `${h}:${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`
  return `${m}:${String(s).padStart(2, '0')}`
}

function formatCount(n: number): string {
  if (n >= 10000) return (n / 10000).toFixed(1) + '万'
  if (n >= 1000) return (n / 1000).toFixed(1) + 'k'
  return String(n)
}
</script>

<style scoped>
.video-card {
  cursor: pointer;
  border-radius: 10px;
  overflow: hidden;
  background: var(--bg-secondary);
  transition: transform 0.15s, box-shadow 0.15s;
}
.video-card:hover {
  transform: translateY(-2px);
  box-shadow: 0 4px 16px rgba(0,0,0,0.3);
}
.thumbnail-wrap {
  position: relative;
  aspect-ratio: 16 / 9;
  background: var(--border);
}
.thumbnail {
  width: 100%;
  height: 100%;
  object-fit: cover;
  display: block;
}
.duration-badge {
  position: absolute;
  bottom: 6px;
  right: 6px;
  background: rgba(0,0,0,0.8);
  color: #fff;
  font-size: 12px;
  font-weight: 600;
  padding: 2px 6px;
  border-radius: 4px;
}
.info {
  padding: 8px 10px 10px;
}
.title-row {
  display: flex;
  align-items: flex-start;
  gap: 6px;
  margin-bottom: 4px;
}
.uploader-avatar {
  width: 24px;
  height: 24px;
  border-radius: 50%;
  flex-shrink: 0;
  margin-top: 1px;
  background: var(--border);
  cursor: pointer;
  object-fit: cover;
}
.title {
  font-size: 13px;
  font-weight: 600;
  color: var(--fg);
  margin: 0;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
  line-height: 1.3;
  flex: 1;
  min-width: 0;
}
.meta {
  font-size: 11px;
  color: var(--fg-muted);
  margin: 0;
  display: flex;
  flex-wrap: wrap;
  gap: 4px 8px;
  padding-left: 30px;
}
.uploader {
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  max-width: 100%;
}
.pl-add-btn {
  position: absolute;
  top: 6px;
  right: 6px;
  background: rgba(0,0,0,0.7);
  color: #fff;
  border: none;
  border-radius: 4px;
  padding: 2px 6px;
  font-size: 12px;
  cursor: pointer;
  opacity: 0;
  transition: opacity 0.15s;
}
.video-card:hover .pl-add-btn { opacity: 1; }
</style>
