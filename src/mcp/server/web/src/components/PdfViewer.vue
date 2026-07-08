<template>
  <div class="pdf-viewer">
    <div class="pdf-toolbar">
      <button class="toolbar-btn" @click="prevPage" :disabled="currentPage <= 1">‹</button>
      <span class="page-info">{{ currentPage }} / {{ totalPages }}</span>
      <button class="toolbar-btn" @click="nextPage" :disabled="currentPage >= totalPages">›</button>
      <span class="toolbar-sep"></span>
      <button class="toolbar-btn" @click="zoomOut" :disabled="scale <= 0.5">−</button>
      <span class="zoom-info">{{ Math.round(scale * 100) }}%</span>
      <button class="toolbar-btn" @click="zoomIn" :disabled="scale >= 3">+</button>
      <button class="toolbar-btn" @click="fitWidth" title="适应宽度">⊞</button>
    </div>
    <div class="pdf-canvas-wrapper" ref="wrapperRef" @scroll="onScroll">
      <div class="pdf-page-container" ref="pageContainerRef">
        <canvas ref="canvasRef"></canvas>
        <div class="text-layer" ref="textLayerRef"></div>
      </div>
    </div>
    <div v-if="loading" class="pdf-loading">加载中...</div>
    <div v-if="errorMsg" class="pdf-error">{{ errorMsg }}</div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, onUnmounted, watch, nextTick } from 'vue'

// PDF.js 加载：本地动态导入优先 → CDN 降级
const PDFJS_VERSION = '3.11.174'
const PDFJS_CDN = `https://cdnjs.cloudflare.com/ajax/libs/pdf.js/${PDFJS_VERSION}`

let pdfjsLib: any = null
let pdfjsLoading: Promise<void> | null = null

async function ensurePdfjs(): Promise<any> {
  if (pdfjsLib) return pdfjsLib
  if (pdfjsLoading) return pdfjsLoading.then(() => pdfjsLib)

  pdfjsLoading = new Promise<void>(async (resolve, reject) => {
    // 1. 本地动态导入（npm 包）
    try {
      const mod = await import('pdfjs-dist')
      await import('pdfjs-dist/web/pdf_viewer.css')
      pdfjsLib = mod
      pdfjsLib.GlobalWorkerOptions.workerSrc = new URL('pdfjs-dist/build/pdf.worker.min.js', import.meta.url).href
      resolve()
      return
    } catch (e) {
      console.warn('pdfjs-dist 本地导入失败，尝试 CDN:', e)
    }

    // 2. CDN 降级
    try {
      const script = document.createElement('script')
      script.src = `${PDFJS_CDN}/pdf.min.js`
      script.onload = () => {
        pdfjsLib = (window as any).pdfjsLib
        if (pdfjsLib) {
          pdfjsLib.GlobalWorkerOptions.workerSrc = `${PDFJS_CDN}/pdf.worker.min.js`
          resolve()
        } else {
          reject(new Error('pdfjsLib not found on window'))
        }
      }
      script.onerror = () => reject(new Error('Failed to load pdf.js'))
      document.head.appendChild(script)
    } catch (e) {
      reject(e)
    }
  })
  return pdfjsLoading.then(() => pdfjsLib)
}

const props = defineProps<{
  src: string
}>()

const emit = defineEmits<{
  pageChange: [page: number]
  textSelect: [text: string, page: number]
  loaded: [totalPages: number]
}>()

const canvasRef = ref<HTMLCanvasElement | null>(null)
const textLayerRef = ref<HTMLDivElement | null>(null)
const wrapperRef = ref<HTMLDivElement | null>(null)
const pageContainerRef = ref<HTMLDivElement | null>(null)

const currentPage = ref(1)
const totalPages = ref(0)
const scale = ref(1.2)
const loading = ref(false)
const errorMsg = ref('')

let pdfDoc: any = null
let rendering = false
let pendingPage: number | null = null

async function renderPage(num: number) {
  if (!pdfDoc || rendering) {
    pendingPage = num
    return
  }
  rendering = true

  try {
    const page = await pdfDoc.getPage(num)
    const viewport = page.getViewport({ scale: scale.value })

    const canvas = canvasRef.value
    if (!canvas) return
    const ctx = canvas.getContext('2d')
    if (!ctx) return

    canvas.width = viewport.width
    canvas.height = viewport.height

    await page.render({ canvasContext: ctx, viewport }).promise

    // Render text layer
    const textContent = await page.getTextContent()
    const textLayer = textLayerRef.value
    if (textLayer) {
      textLayer.innerHTML = ''
      textLayer.style.width = viewport.width + 'px'
      textLayer.style.height = viewport.height + 'px'

      const textItems = textContent.items as any[]
      for (const item of textItems) {
        if (!item.str) continue
        const tx = pdfjsLib.Util.transform(viewport.transform, item.transform)
        const span = document.createElement('span')
        span.textContent = item.str
        span.style.position = 'absolute'
        span.style.left = tx[4] + 'px'
        span.style.top = tx[5] - item.height + 'px'
        span.style.fontSize = Math.sqrt(tx[0] * tx[0] + tx[1] * tx[1]) + 'px'
        span.style.fontFamily = item.fontName || 'sans-serif'
        span.style.color = 'transparent'
        span.style.whiteSpace = 'pre'
        textLayer.appendChild(span)
      }
    }

    if (pageContainerRef.value) {
      pageContainerRef.value.style.width = viewport.width + 'px'
      pageContainerRef.value.style.height = viewport.height + 'px'
    }

    currentPage.value = num
    emit('pageChange', num)
  } catch (e) {
    console.error('PDF render error:', e)
  } finally {
    rendering = false
    if (pendingPage !== null) {
      const p = pendingPage
      pendingPage = null
      renderPage(p)
    }
  }
}

async function loadPdf() {
  if (!props.src) return
  loading.value = true
  errorMsg.value = ''

  if (!props.src || (!props.src.startsWith('http') && !props.src.startsWith('/') && !props.src.startsWith('blob:'))) {
    errorMsg.value = 'PDF 地址无效，请先连接服务器'
    loading.value = false
    return
  }

  try {
    await ensurePdfjs()
    const response = await fetch(props.src)
    if (!response.ok) {
      throw new Error(`HTTP ${response.status}: ${response.statusText}`)
    }
    const data = await response.arrayBuffer()
    const loadingTask = pdfjsLib.getDocument({ data })
    pdfDoc = await loadingTask.promise
    totalPages.value = pdfDoc.numPages
    emit('loaded', pdfDoc.numPages)
    await renderPage(1)
  } catch (e: any) {
    console.error('PDF load error:', e)
    errorMsg.value = 'PDF 加载失败: ' + (e?.message || '未知错误')
  } finally {
    loading.value = false
  }
}

function prevPage() {
  if (currentPage.value > 1) renderPage(currentPage.value - 1)
}

function nextPage() {
  if (currentPage.value < totalPages.value) renderPage(currentPage.value + 1)
}

function zoomIn() {
  if (scale.value < 3) {
    scale.value = Math.min(3, scale.value + 0.2)
    renderPage(currentPage.value)
  }
}

function zoomOut() {
  if (scale.value > 0.5) {
    scale.value = Math.max(0.5, scale.value - 0.2)
    renderPage(currentPage.value)
  }
}

function fitWidth() {
  if (!wrapperRef.value || !pdfDoc) return
  const wrapperWidth = wrapperRef.value.clientWidth - 20
  pdfDoc.getPage(currentPage.value).then((page) => {
    const viewport = page.getViewport({ scale: 1 })
    scale.value = wrapperWidth / viewport.width
    renderPage(currentPage.value)
  })
}

function onScroll() {
  // placeholder for scroll-based page tracking
}

// Text selection
function onTextSelect() {
  const selection = window.getSelection()
  if (selection && selection.toString().trim()) {
    emit('textSelect', selection.toString().trim(), currentPage.value)
  }
}

watch(() => props.src, () => {
  loadPdf()
})

onMounted(() => {
  loadPdf()
  document.addEventListener('mouseup', onTextSelect)
})

onUnmounted(() => {
  if (pdfDoc) {
    pdfDoc.destroy()
    pdfDoc = null
  }
  document.removeEventListener('mouseup', onTextSelect)
})
</script>

<style scoped>
.pdf-viewer {
  display: flex;
  flex-direction: column;
  height: 100%;
  background: var(--bg);
}

.pdf-toolbar {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 6px 12px;
  background: var(--bg-secondary);
  border-bottom: 1px solid var(--border);
  flex-shrink: 0;
}

.toolbar-btn {
  background: transparent;
  border: 1px solid var(--border);
  color: var(--fg-muted);
  padding: 4px 10px;
  border-radius: 4px;
  font-size: 14px;
  cursor: pointer;
  transition: all 0.15s;
}

.toolbar-btn:hover:not(:disabled) {
  color: var(--accent);
  border-color: var(--accent);
}

.toolbar-btn:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}

.page-info,
.zoom-info {
  font-size: 13px;
  color: var(--fg-muted);
  min-width: 50px;
  text-align: center;
}

.toolbar-sep {
  width: 1px;
  height: 20px;
  background: var(--border);
  margin: 0 4px;
}

.pdf-canvas-wrapper {
  flex: 1;
  overflow: auto;
  display: flex;
  justify-content: center;
  padding: 10px;
}

.pdf-page-container {
  position: relative;
  box-shadow: 0 2px 12px rgba(0, 0, 0, 0.3);
}

.pdf-page-container canvas {
  display: block;
}

.text-layer {
  position: absolute;
  top: 0;
  left: 0;
  overflow: hidden;
  opacity: 0.2;
  line-height: 1;
}

.text-layer span {
  cursor: text;
  user-select: text;
}

.pdf-loading {
  position: absolute;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  background: rgba(0, 0, 0, 0.4);
  color: var(--fg);
  font-size: 16px;
  z-index: 10;
}

.pdf-error {
  position: absolute;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--bg);
  color: #ef4444;
  font-size: 14px;
  padding: 20px;
  text-align: center;
  z-index: 10;
}
</style>
