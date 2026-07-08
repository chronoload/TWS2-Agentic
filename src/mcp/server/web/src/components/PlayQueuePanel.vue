<template>
  <div class="queue-panel" :class="{ open: visible }">
    <div class="queue-overlay" @click="$emit('close')" />
    <div class="queue-drawer">
      <div class="queue-header">
        <span class="queue-title">播放队列 ({{ store.length }})</span>
        <div class="queue-controls">
          <button class="q-btn" :class="{ active: store.shuffle }" @click="store.toggleShuffle()" title="随机播放">🔀</button>
          <button class="q-btn" :class="{ active: store.repeatMode !== 'none' }" @click="cycleRepeat" title="循环模式">
            <template v-if="store.repeatMode === 'one'">🔂</template>
            <template v-else-if="store.repeatMode === 'all'">🔁</template>
            <template v-else>🔁</template>
          </button>
          <button class="q-btn" @click="store.clear()" title="清空队列" :disabled="store.isEmpty">🗑</button>
          <button class="q-btn close-btn" @click="$emit('close')">✕</button>
        </div>
      </div>
      <div v-if="store.isEmpty" class="queue-empty">队列为空</div>
      <div v-else class="queue-list" ref="listEl">
        <div
          v-for="(item, i) in store.items"
          :key="item.url"
          class="queue-item"
          :class="{ active: i === store.currentIndex, 'drag-over': dragOverIndex === i }"
          :draggable="i !== store.currentIndex"
          @dragstart="onDragStart(i)"
          @dragover.prevent="onDragOver(i)"
          @dragend="onDragEnd"
          @drop.prevent="onDrop(i)"
          @click="playItem(i)"
        >
          <img :src="proxyImageUrl(item.thumbnailUrl)" class="qi-thumb" loading="lazy" @error="e => { (e.target as HTMLElement).style.display = 'none' }" />
          <div class="qi-info">
            <div class="qi-title">{{ item.title }}</div>
            <div class="qi-uploader">{{ item.uploaderName }}</div>
          </div>
          <button class="qi-remove" @click.stop="store.remove(i)" title="移除">✕</button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { proxyImageUrl } from '../extractor/BilibiliImageProxy'
import { usePlayQueueStore } from '../stores/playQueue'

defineProps<{ visible: boolean }>()
const emit = defineEmits<{ close: [] }>()

const store = usePlayQueueStore()
const listEl = ref<HTMLElement | null>(null)
const dragOverIndex = ref(-1)
let dragFrom = -1

function cycleRepeat() {
  const modes = ['none', 'one', 'all'] as const
  const idx = modes.indexOf(store.repeatMode)
  store.setRepeatMode(modes[(idx + 1) % modes.length])
}

function playItem(i: number) {
  store.playAt(i)
}

function onDragStart(i: number) {
  dragFrom = i
}

function onDragOver(i: number) {
  dragOverIndex.value = i
}

function onDragEnd() {
  dragOverIndex.value = -1
  dragFrom = -1
}

function onDrop(to: number) {
  if (dragFrom >= 0 && dragFrom !== to) {
    store.move(dragFrom, to)
  }
  dragOverIndex.value = -1
  dragFrom = -1
}
</script>

<style scoped>
.queue-panel {
  position: fixed;
  inset: 0;
  z-index: 1000;
  pointer-events: none;
}
.queue-panel.open { pointer-events: auto; }

.queue-overlay {
  position: absolute;
  inset: 0;
  background: rgba(0,0,0,0.4);
  opacity: 0;
  transition: opacity 0.25s;
}
.queue-panel.open .queue-overlay { opacity: 1; }

.queue-drawer {
  position: absolute;
  right: 0;
  top: 0;
  bottom: 0;
  width: min(380px, 85vw);
  background: var(--bg);
  border-left: 1px solid var(--border);
  display: flex;
  flex-direction: column;
  transform: translateX(100%);
  transition: transform 0.25s ease;
}
.queue-panel.open .queue-drawer { transform: translateX(0); }

.queue-header {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 12px;
  border-bottom: 1px solid var(--border);
}
.queue-title { flex: 1; font-size: 1rem; font-weight: 600; color: var(--fg); }
.queue-controls { display: flex; gap: 4px; }

.q-btn {
  background: none;
  border: 1px solid var(--border);
  border-radius: 6px;
  cursor: pointer;
  padding: 4px 8px;
  font-size: 1rem;
  color: var(--fg);
}
.q-btn:hover { background: var(--bg-secondary); }
.q-btn.active { background: var(--accent); color: #fff; border-color: var(--accent); }
.q-btn:disabled { opacity: 0.3; cursor: default; }
.close-btn { font-size: 0.85rem; }

.queue-empty {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--fg-muted);
  font-size: 0.9rem;
}

.queue-list {
  flex: 1;
  overflow-y: auto;
  padding: 4px 0;
}

.queue-item {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 8px 12px;
  cursor: pointer;
  border-left: 3px solid transparent;
  transition: background 0.15s;
}
.queue-item:hover { background: var(--bg-secondary); }
.queue-item.active { background: var(--bg-secondary); border-left-color: var(--accent); }
.queue-item.drag-over { border-top: 2px solid var(--accent); }

.qi-thumb {
  width: 48px;
  height: 27px;
  border-radius: 4px;
  object-fit: cover;
  flex-shrink: 0;
  background: var(--bg-secondary);
}

.qi-info {
  flex: 1;
  min-width: 0;
}
.qi-title {
  font-size: 0.85rem;
  color: var(--fg);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.qi-uploader {
  font-size: 0.75rem;
  color: var(--fg-muted);
  margin-top: 2px;
}

.qi-remove {
  background: none;
  border: none;
  cursor: pointer;
  color: var(--fg-muted);
  font-size: 0.8rem;
  padding: 4px;
  flex-shrink: 0;
}
.qi-remove:hover { color: var(--danger); }
</style>
