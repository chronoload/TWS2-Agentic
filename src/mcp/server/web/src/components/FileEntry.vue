<template>
  <div class="file-entry">
    <div
      class="entry-row"
      :style="{ paddingLeft: depth * 16 + 'px' }"
      @click="handleClick"
      @contextmenu.prevent="!entry.is_dir && showCtxMenu($event)"
    >
      <span v-if="entry.is_dir" class="entry-arrow">
        {{ expanded ? '▼' : '▶' }}
      </span>
      <span v-else class="entry-arrow-spacer"></span>
      <span class="entry-icon">{{ entry.is_dir ? '📁' : fileIcon }}</span>
      <span class="entry-name">{{ entry.name }}</span>
      <span v-if="!entry.is_dir && entry.size" class="entry-size">{{ formatSize(entry.size) }}</span>
    </div>
    <!-- 右键菜单 -->
    <div
      v-if="ctxVisible"
      class="context-menu"
      :style="{ left: ctxX + 'px', top: ctxY + 'px' }"
      @click.stop
      @contextmenu.prevent
    >
      <div v-if="isHtmlFile" class="ctx-item" @click="ctxOpenInBrowser">在浏览器中打开</div>
      <div v-if="isHtmlFile" class="ctx-item" @click="ctxEditSource">编辑源码</div>
      <div v-if="!isHtmlFile" class="ctx-item" @click="ctxOpenInEditor">在编辑器中打开</div>
      <div class="ctx-item" @click="ctxDownload">下载</div>
      <div class="ctx-item" @click="ctxCopyPath">复制路径</div>
    </div>
    <div v-if="entry.is_dir && expanded" class="entry-children">
      <div v-if="loading" class="loading-item">加载中...</div>
      <div v-else-if="error" class="error-item">加载失败</div>
      <template v-else>
        <FileEntry
          v-for="child in children"
          :key="child.path || child.name"
          :entry="child"
          :base-path="fullPath"
          :depth="depth + 1"
          @navigate="$emit('navigate', $event)"
          @open-file="$emit('openFile', $event)"
        />
      </template>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { readDir, downloadFile, getServerURL } from '../api'

interface DirEntry {
  path: string
  name: string
  is_dir: boolean
  ext?: string
  size?: number
  modified?: number
}

const props = defineProps<{
  entry: DirEntry
  basePath: string
  depth: number
}>()

const emit = defineEmits<{
  navigate: [path: string]
  openFile: [path: string]
}>()

const expanded = ref(false)
const loading = ref(false)
const error = ref(false)
const children = ref<DirEntry[]>([])

const fullPath = computed(() => {
  if (props.entry.path) return props.entry.path
  const sep = props.basePath.endsWith('/') ? '' : '/'
  return `${props.basePath}${sep}${props.entry.name}`
})

const fileIcon = computed(() => {
  const ext = (props.entry.ext || '').toLowerCase()
  const name = props.entry.name.toLowerCase()
  if (ext === '.md' || name.endsWith('.md')) return '📝'
  if (ext === '.json' || name.endsWith('.json')) return '📋'
  if (ext === '.txt' || name.endsWith('.txt')) return '📄'
  if (['.py', '.ts', '.js', '.vue', '.r', '.lua'].includes(ext)) return '💻'
  if (['.csv', '.xlsx'].includes(ext)) return '📊'
  if (['.png', '.jpg', '.jpeg', '.svg', '.gif'].includes(ext)) return '🖼️'
  if (ext === '.pdf') return '📕'
  if (ext === '.rmd') return '📄'
  return '📄'
})

async function handleClick() {
  if (props.entry.is_dir) {
    expanded.value = !expanded.value
    if (expanded.value && children.value.length === 0) {
      await loadChildren()
    }
    emit('navigate', fullPath.value)
  } else {
    emit('openFile', fullPath.value)
  }
}

async function loadChildren() {
  loading.value = true
  error.value = false
  try {
    const res = await readDir(fullPath.value)
    const apiData = res.data?.data ?? res.data
    children.value = Array.isArray(apiData) ? apiData : []
  } catch {
    error.value = true
  } finally {
    loading.value = false
  }
}

function formatSize(bytes: number): string {
  if (bytes < 1024) return `${bytes}B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)}KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)}MB`
}

// 右键菜单
const ctxVisible = ref(false)
const ctxX = ref(0)
const ctxY = ref(0)

function showCtxMenu(event: MouseEvent) {
  ctxVisible.value = true
  ctxX.value = event.clientX
  ctxY.value = event.clientY
}

function closeCtxMenu() {
  ctxVisible.value = false
}

const isHtmlFile = computed(() => {
  const ext = (props.entry.ext || '').toLowerCase()
  return !props.entry.is_dir && (ext === '.html' || ext === '.htm')
})

function ctxOpenInBrowser() {
  const encodedPath = fullPath.value.split('/').map(s => encodeURIComponent(s)).join('/')
  const base = getServerURL().replace(/\/+$/, '')
  window.open(base + '/api/file/download/' + encodedPath + '?preview=true', '_blank')
  closeCtxMenu()
}

function ctxEditSource() {
  emit('openFile', fullPath.value)
  closeCtxMenu()
}

function ctxOpenInEditor() {
  emit('openFile', fullPath.value)
  closeCtxMenu()
}

function ctxDownload() {
  downloadFile(fullPath.value)
  closeCtxMenu()
}

function ctxCopyPath() {
  navigator.clipboard.writeText(fullPath.value).catch(() => {})
  closeCtxMenu()
}

function onCtxClickAway() {
  if (ctxVisible.value) closeCtxMenu()
}

onMounted(() => {
  document.addEventListener('click', onCtxClickAway)
})

onUnmounted(() => {
  document.removeEventListener('click', onCtxClickAway)
})
</script>

<style scoped>
.entry-row {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 10px 16px;
  cursor: pointer;
  transition: background 0.15s;
}

.entry-row:hover {
  background: rgba(255, 255, 255, 0.04);
}

.entry-arrow {
  font-size: 10px;
  color: var(--fg-muted);
  width: 14px;
  text-align: center;
  flex-shrink: 0;
}

.entry-arrow-spacer {
  width: 14px;
  flex-shrink: 0;
}

.entry-icon {
  font-size: 16px;
  flex-shrink: 0;
}

.entry-name {
  font-size: 14px;
  color: var(--fg);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  flex: 1;
}

.entry-size {
  font-size: 11px;
  color: var(--fg-muted);
  flex-shrink: 0;
}

.entry-children {
  padding-left: 0;
}

.loading-item,
.error-item {
  padding: 8px 16px;
  font-size: 13px;
  color: var(--fg-muted);
}

.error-item {
  color: var(--danger);
}

/* 右键上下文菜单 */
.context-menu {
  position: fixed;
  z-index: 1000;
  min-width: 140px;
  background: var(--bg-secondary);
  border: 1px solid var(--border);
  border-radius: 8px;
  box-shadow: 0 4px 16px rgba(0,0,0,0.3);
  padding: 4px 0;
  overflow: hidden;
}

.ctx-item {
  padding: 10px 16px;
  font-size: 13px;
  color: var(--fg);
  cursor: pointer;
  transition: background 0.1s;
  user-select: none;
}

.ctx-item:hover {
  background: rgba(var(--accent-rgb, 59, 130, 246), 0.12);
  color: var(--accent);
}
</style>
