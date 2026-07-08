<template>
  <div class="pdf-reader-view">
    <header class="pdf-header">
      <button class="btn-back" @click="goBack">← 返回</button>
      <span class="file-name">{{ fileName }}</span>
      <div class="header-actions">
        <button class="btn-index" @click="buildIndex" :disabled="indexing">
          {{ indexing ? '索引中...' : '建立索引' }}
        </button>
        <button class="btn-chat-toggle" @click="showChat = !showChat">
          {{ showChat ? '关闭问答' : 'AI问答' }}
        </button>
      </div>
    </header>

    <div class="pdf-body">
      <div class="pdf-area">
        <PdfViewer
          :src="pdfUrl"
          @pageChange="onPageChange"
          @textSelect="onTextSelect"
          @loaded="onLoaded"
        />
      </div>
      <PdfChatPanel
        v-if="showChat"
        :pdfPath="pdfPath"
        @close="showChat = false"
      />
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { pdfIndex, getServerURL } from '../api'
import PdfViewer from '../components/PdfViewer.vue'
import PdfChatPanel from '../components/PdfChatPanel.vue'

const route = useRoute()
const router = useRouter()

const pdfPath = computed(() => {
  const p = route.params.path as string | string[]
  const raw = Array.isArray(p) ? p.join('/') : (p || '')
  // Vue Router 会自动解码，但路径中的中文等需要保留原始编码用于 API 请求
  return raw
})

const fileName = computed(() => {
  const parts = pdfPath.value.split('/')
  return parts[parts.length - 1] || 'PDF'
})

const pdfUrl = computed(() => {
  // 逐段编码，保留 /
  const encoded = pdfPath.value.split('/').map(s => encodeURIComponent(s)).join('/')
  // APP 端需要拼接服务器 baseURL
  const base = getServerURL().replace(/\/+$/, '')
  return `${base}/api/file/download/${encoded}`
})

const showChat = ref(false)
const indexing = ref(false)

function goBack() {
  router.back()
}

async function buildIndex() {
  if (indexing.value) return
  indexing.value = true
  try {
    await pdfIndex(pdfPath.value)
    alert('索引建立完成')
  } catch (e: any) {
    alert('索引建立失败: ' + (e.message || '未知错误'))
  } finally {
    indexing.value = false
  }
}

function onPageChange(page: number) {
  // page change handler
}

function onTextSelect(text: string, page: number) {
  // text selection handler
}

function onLoaded(totalPages: number) {
  // PDF loaded handler
}
</script>

<style scoped>
.pdf-reader-view {
  display: flex;
  flex-direction: column;
  height: 100%;
  background: var(--bg);
}

.pdf-header {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 8px 16px;
  background: var(--bg-secondary);
  border-bottom: 1px solid var(--border);
  flex-shrink: 0;
}

.btn-back {
  background: transparent;
  color: var(--accent);
  padding: 4px 12px;
  font-size: 14px;
  border: 1px solid var(--border);
  border-radius: 6px;
  cursor: pointer;
  transition: all 0.15s;
}

.btn-back:hover {
  background: rgba(255, 255, 255, 0.06);
}

.file-name {
  flex: 1;
  font-size: 14px;
  font-weight: 500;
  color: var(--fg);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.header-actions {
  display: flex;
  gap: 8px;
}

.btn-index {
  background: transparent;
  border: 1px solid var(--accent);
  color: var(--accent);
  padding: 5px 14px;
  border-radius: 6px;
  font-size: 13px;
  cursor: pointer;
  transition: all 0.15s;
}

.btn-index:hover:not(:disabled) {
  background: var(--accent);
  color: #fff;
}

.btn-index:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.btn-chat-toggle {
  background: var(--accent);
  color: #fff;
  border: none;
  padding: 5px 14px;
  border-radius: 6px;
  font-size: 13px;
  font-weight: 500;
  cursor: pointer;
  transition: filter 0.15s;
}

.btn-chat-toggle:hover {
  filter: brightness(1.1);
}

.pdf-body {
  flex: 1;
  display: flex;
  min-height: 0;
  overflow: hidden;
}

.pdf-area {
  flex: 1;
  min-width: 0;
  overflow: hidden;
}
</style>
