<template>
  <div class="view">
    <header class="view-header">
      <h1>资源索引</h1>
    </header>
    <div class="view-body">
      <div class="resource-toolbar">
        <input
          v-model="searchQuery"
          class="resource-search"
          placeholder="搜索资源..."
          autocomplete="off"
          @input="onSearchInput"
        />
        <button class="resource-refresh-btn" @click="loadResources" :disabled="loading">刷新</button>
      </div>
      <div class="resource-stats" v-if="!loading && allItems.length > 0">
        <span class="resource-count">{{ allItems.length }} 个资源</span>
      </div>
      <div v-if="loading" class="loading">加载中...</div>
      <div v-else-if="allItems.length === 0 && !searchQuery" class="empty">暂无资源</div>
      <div v-else-if="filteredItems.length === 0" class="empty">无匹配资源</div>
      <div v-else class="resource-list">
        <div
          v-for="(item, idx) in filteredItems"
          :key="idx"
          class="resource-item"
          @click="openResource(item)"
        >
          <span class="resource-icon">{{ resourceIcon(item.type) }}</span>
          <div class="resource-info">
            <span class="resource-label">{{ item.label || item.url || item.path || '未命名' }}</span>
            <span class="resource-meta">
              <span class="resource-course">{{ item.course_id }}</span>
              <span v-if="item.lesson_number" class="resource-lesson">L{{ item.lesson_number }}</span>
            </span>
          </div>
          <span v-if="item.type" class="resource-type-tag">{{ item.type }}</span>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, watch } from 'vue'
import { useRouter } from 'vue-router'
import { getResources } from '../api'

const router = useRouter()

interface ResourceItem {
  type: string
  label: string
  path: string
  url: string
  course_id: string
  lesson_number?: number
}

const allItems = ref<ResourceItem[]>([])
const loading = ref(true)
const searchQuery = ref('')
let searchTimer: ReturnType<typeof setTimeout> | null = null

const filteredItems = computed(() => {
  const q = searchQuery.value.trim().toLowerCase()
  if (!q) return allItems.value
  return allItems.value.filter(item => {
    const label = (item.label || '').toLowerCase()
    const path = (item.path || '').toLowerCase()
    const url = (item.url || '').toLowerCase()
    const course = (item.course_id || '').toLowerCase()
    return label.includes(q) || path.includes(q) || url.includes(q) || course.includes(q)
  })
})

function resourceIcon(type?: string): string {
  const icons: Record<string, string> = {
    pdf: '📄', url: '🌐', video: '🎬', image: '🖼️',
    note: '📝', code: '💻',
  }
  return icons[type || ''] || '📄'
}

function isNativeApp(): boolean {
  return !!(window as any).Capacitor || location.protocol === 'file:'
}

function openResource(item: ResourceItem) {
  const type = item.type || 'url'
  const filePath = item.path || ''
  const url = item.url || ''

  if (type === 'pdf' && filePath) {
    if (isNativeApp()) {
      router.push(`/pdf/${filePath}`)
    } else {
      router.push(`/pdf/${filePath}`)
    }
  } else if (type === 'url' && url) {
    window.open(url, '_blank')
  } else if (type === 'video') {
    if (url) window.open(url, '_blank')
    else if (filePath) router.push(`/pdf/${filePath}`)
  } else if (filePath) {
    // 尝试作为文件打开
    router.push(`/pdf/${filePath}`)
  } else if (url) {
    window.open(url, '_blank')
  }
}

function onSearchInput() {
  if (searchTimer) clearTimeout(searchTimer)
  const q = searchQuery.value.trim()
  if (!q) return
  searchTimer = setTimeout(() => loadResources(q), 300)
}

async function loadResources(query?: string) {
  loading.value = true
  try {
    const res = await getResources(query || '')
    const data = res.data?.data ?? res.data ?? []
    allItems.value = Array.isArray(data) ? data as ResourceItem[] : []
  } catch {
    allItems.value = []
  } finally {
    loading.value = false
  }
}

onMounted(() => {
  loadResources()
})
</script>

<style scoped>
.resource-toolbar {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 16px;
  background: var(--bg-secondary);
  border-bottom: 1px solid var(--border);
  flex-shrink: 0;
}

.resource-search {
  flex: 1;
  padding: 7px 12px;
  border: 1px solid var(--border);
  border-radius: 6px;
  background: var(--bg);
  color: var(--fg);
  font-size: 14px;
}

.resource-search:focus {
  outline: none;
  border-color: var(--accent);
}

.resource-refresh-btn {
  background: var(--accent);
  color: #fff;
  border: none;
  border-radius: 6px;
  padding: 6px 14px;
  font-size: 12px;
  font-weight: 500;
  cursor: pointer;
  white-space: nowrap;
}

.resource-refresh-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.resource-stats {
  padding: 4px 16px;
  font-size: 11px;
  color: var(--fg-muted);
  border-bottom: 1px solid var(--border);
}

.resource-list {
  flex: 1;
  overflow-y: auto;
}

.resource-item {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px 16px;
  border-bottom: 1px solid var(--border);
  cursor: pointer;
  transition: background 0.15s;
}

.resource-item:hover {
  background: rgba(255, 255, 255, 0.04);
}

.resource-icon {
  font-size: 18px;
  flex-shrink: 0;
  width: 22px;
  text-align: center;
}

.resource-info {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.resource-label {
  font-size: 14px;
  color: var(--fg);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.resource-meta {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 11px;
  color: var(--fg-muted);
}

.resource-course {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.resource-lesson {
  flex-shrink: 0;
}

.resource-type-tag {
  font-size: 10px;
  padding: 2px 6px;
  border-radius: 4px;
  background: var(--bg-secondary);
  color: var(--fg-muted);
  border: 1px solid var(--border);
  flex-shrink: 0;
  text-transform: uppercase;
}

.loading,
.empty {
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 40px;
  color: var(--fg-muted);
  font-size: 14px;
}
</style>
