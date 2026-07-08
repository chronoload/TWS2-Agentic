<template>
  <div class="download-dialog-overlay" v-if="visible" @click.self="close">
    <div class="download-dialog">
      <div class="dd-header">
        <h3 class="dd-title">下载</h3>
        <button class="dd-close" @click="close">✕</button>
      </div>

      <div class="dd-body">
        <label class="dd-label">文件名</label>
        <input v-model="fileName" class="dd-input" type="text" maxlength="200" />

        <div class="dd-tabs">
          <button
            v-for="tab in availableTabs"
            :key="tab.key"
            class="dd-tab"
            :class="{ active: activeTab === tab.key }"
            @click="switchTab(tab.key)"
          >{{ tab.label }}</button>
        </div>

        <label class="dd-label">画质 / 码率</label>
        <select v-model="selectedStreamIdx" class="dd-select" :disabled="activeStreams.length === 0">
          <option v-for="(s, i) in activeStreams" :key="i" :value="i">
            {{ streamLabel(s) }}
          </option>
        </select>

        <div v-if="selectedSize" class="dd-size">
          文件大小: {{ formatSize(selectedSize) }}
        </div>

        <template v-if="activeTab !== 'subtitle'">
          <label class="dd-label">下载线程数</label>
          <div class="dd-threads-row">
            <span class="dd-threads-count">{{ threads }}</span>
            <input v-model.number="threads" type="range" min="1" max="32" class="dd-slider" />
          </div>
        </template>
      </div>

      <div class="dd-footer">
        <button class="dd-btn dd-btn-secondary" @click="close">取消</button>
        <button class="dd-btn dd-btn-primary" @click="startDownload" :disabled="!canDownload">
          下载
        </button>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, onUnmounted } from 'vue'
import type { StreamInfoResult, VideoStreamInfo, AudioStreamInfo, SubtitlesStreamInfo } from '../plugins/bridge'
import { getDefaultVideoIndex, getDefaultAudioIndex, getStreamLabel as selectorLabel } from '../utils/streamSelector'

const props = defineProps<{
  visible: boolean
  info: StreamInfoResult | null
}>()

const emit = defineEmits<{
  close: []
  download: [{ url: string; filename: string; type: string }]
}>()

const activeTab = ref<'video' | 'audio' | 'subtitle'>('video')
const fileName = ref('')
const selectedStreamIdx = ref(0)
const threads = ref(3)
const streamSizes = ref<Record<string, number | null>>({})
const fetchingSize = ref(false)

watch(() => props.info, (info) => {
  if (info) {
    fileName.value = sanitizeFilename(info.name || 'video')
    activeTab.value = info.videoStreams?.length ? 'video' : info.audioStreams?.length ? 'audio' : 'subtitle'
    const allVideo = info.sortedVideoStreams || info.videoStreams || []
    selectedStreamIdx.value = getDefaultVideoIndex(allVideo, 'highest')
  }
})

watch(() => activeTab.value, () => {
  selectedStreamIdx.value = 0
})

watch(() => selectedStreamIdx.value, () => {
  const s = activeStreams.value[selectedStreamIdx.value]
  if (s && 'url' in s && s.url && !(s.url in streamSizes.value)) {
    fetchStreamSize(s.url)
  }
})

const sizeFetchController = ref<AbortController | null>(null)
onUnmounted(() => sizeFetchController.value?.abort())

async function fetchStreamSize(url: string) {
  if (streamSizes.value[url] !== undefined || fetchingSize.value) return
  fetchingSize.value = true
  sizeFetchController.value?.abort()
  const ctrl = new AbortController()
  sizeFetchController.value = ctrl
  try {
    const resp = await fetch(url, { method: 'HEAD', signal: ctrl.signal })
    const cl = resp.headers.get('Content-Length')
    streamSizes.value[url] = cl ? parseInt(cl, 10) || null : null
  } catch {
    streamSizes.value[url] = null
  } finally {
    fetchingSize.value = false
  }
}

function close() {
  emit('close')
}

const availableTabs = computed(() => {
  const tabs: { key: typeof activeTab.value; label: string }[] = []
  if (videoStreams.value.length) tabs.push({ key: 'video', label: '视频' })
  if (audioStreams.value.length) tabs.push({ key: 'audio', label: '音频' })
  if (subtitleStreams.value.length) tabs.push({ key: 'subtitle', label: '字幕' })
  return tabs
})

const videoStreams = computed<VideoStreamInfo[]>(() => {
  const all = props.info?.sortedVideoStreams || props.info?.videoStreams || []
  const videoOnly = props.info?.videoOnlyStreams || []
  const combined = all.filter(s => !s.isVideoOnly)
  if (combined.length > 0) return combined
  if (all.length > 0) return all
  return videoOnly
})

const audioStreams = computed<AudioStreamInfo[]>(() => {
  return props.info?.audioStreams || []
})

const subtitleStreams = computed<SubtitlesStreamInfo[]>(() => {
  return props.info?.subtitles || []
})

const activeStreams = computed<(VideoStreamInfo | AudioStreamInfo | SubtitlesStreamInfo)[]>(() => {
  if (activeTab.value === 'video') return videoStreams.value
  if (activeTab.value === 'audio') return audioStreams.value
  return subtitleStreams.value
})

const canDownload = computed(() => {
  return activeStreams.value.length > 0 && selectedStreamIdx.value >= 0
})

const selectedSize = computed(() => {
  const s = activeStreams.value[selectedStreamIdx.value]
  if (!s || !('url' in s) || !s.url) return null
  return streamSizes.value[s.url] ?? null
})

function switchTab(tab: typeof activeTab.value) {
  activeTab.value = tab
}

function getExtension(s: VideoStreamInfo | AudioStreamInfo | SubtitlesStreamInfo): string {
  const mime = (s as any).mimeType || ''
  if (mime.includes('mp4') || mime.includes('mpeg4')) return '.mp4'
  if (mime.includes('webm')) return '.webm'
  if (mime.includes('ogg')) return '.ogg'
  if (mime.includes('mp3')) return '.mp3'
  if (mime.includes('wav')) return '.wav'
  if (mime.includes('srt') || mime.includes('subrip')) return '.srt'
  if (mime.includes('vtt')) return '.vtt'
  if (mime.includes('ttml')) return '.ttml'
  return '.bin'
}

function streamLabel(s: VideoStreamInfo | AudioStreamInfo | SubtitlesStreamInfo): string {
  if ('resolution' in s || 'averageBitrate' in s) return selectorLabel(s as VideoStreamInfo | AudioStreamInfo)
  if ('languageCode' in s) {
    const ss = s as SubtitlesStreamInfo
    return `${ss.displayName || ss.languageCode}${ss.autoGenerated ? ' (自动)' : ''}`
  }
  return (s as any).quality || (s as any).bitrate || '未知'
}

function formatSize(bytes: number): string {
  if (!bytes || bytes <= 0) return '未知'
  if (bytes < 1024) return bytes + ' B'
  if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB'
  if (bytes < 1024 * 1024 * 1024) return (bytes / (1024 * 1024)).toFixed(1) + ' MB'
  return (bytes / (1024 * 1024 * 1024)).toFixed(2) + ' GB'
}

function sanitizeFilename(name: string): string {
  return name.replace(/[<>:"/\\|?*]/g, '_').substring(0, 200)
}

async function startDownload() {
  const stream = activeStreams.value[selectedStreamIdx.value]
  if (!stream) return

  const url = (stream as any).url || ''
  if (!url) return

  let finalName = fileName.value.trim() || sanitizeFilename(props.info?.name || 'download')
  finalName += getExtension(stream)

  if (activeTab.value === 'subtitle') {
    const ss = stream as SubtitlesStreamInfo
    const lang = ss.languageCode || 'unknown'
    finalName = sanitizeFilename(`${props.info?.name || 'subtitle'}_${lang}`) + (ss.suffix || '.srt')
  }

  emit('download', { url, filename: finalName, type: activeTab.value })

  triggerBrowserDownload(url, finalName)
}

function triggerBrowserDownload(url: string, filename: string) {
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  a.rel = 'noopener noreferrer'
  a.style.display = 'none'
  document.body.appendChild(a)
  a.click()
  document.body.removeChild(a)
}
</script>

<style scoped>
.download-dialog-overlay {
  position: fixed;
  inset: 0;
  z-index: 1100;
  background: rgba(0,0,0,0.5);
  display: flex;
  align-items: center;
  justify-content: center;
}

.download-dialog {
  background: var(--bg);
  border: 1px solid var(--border);
  border-radius: 12px;
  width: min(420px, 90vw);
  max-height: 85vh;
  display: flex;
  flex-direction: column;
  box-shadow: 0 8px 32px rgba(0,0,0,0.3);
}

.dd-header {
  display: flex;
  align-items: center;
  padding: 16px 20px;
  border-bottom: 1px solid var(--border);
}

.dd-title {
  flex: 1;
  margin: 0;
  font-size: 16px;
  font-weight: 700;
  color: var(--fg);
}

.dd-close {
  background: none;
  border: none;
  color: var(--fg-muted);
  font-size: 18px;
  cursor: pointer;
  padding: 4px 8px;
  border-radius: 4px;
}

.dd-close:hover {
  background: var(--bg-secondary);
  color: var(--fg);
}

.dd-body {
  flex: 1;
  overflow-y: auto;
  padding: 16px 20px;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.dd-label {
  font-size: 12px;
  font-weight: 600;
  color: var(--fg-muted);
  margin-top: 4px;
}

.dd-input {
  width: 100%;
  padding: 8px 12px;
  border: 1px solid var(--border);
  border-radius: 8px;
  background: var(--bg-secondary);
  color: var(--fg);
  font-size: 13px;
  box-sizing: border-box;
}

.dd-tabs {
  display: flex;
  gap: 0;
  margin: 8px 0 4px;
  border: 1px solid var(--border);
  border-radius: 8px;
  overflow: hidden;
}

.dd-tab {
  flex: 1;
  padding: 8px 12px;
  background: var(--bg-secondary);
  border: none;
  color: var(--fg-muted);
  font-size: 13px;
  cursor: pointer;
  transition: all 0.15s;
}

.dd-tab:not(:last-child) {
  border-right: 1px solid var(--border);
}

.dd-tab.active {
  background: var(--accent);
  color: #fff;
  font-weight: 600;
}

.dd-select {
  width: 100%;
  padding: 8px 12px;
  border: 1px solid var(--border);
  border-radius: 8px;
  background: var(--bg-secondary);
  color: var(--fg);
  font-size: 13px;
}

.dd-select:disabled {
  opacity: 0.5;
}

.dd-size {
  font-size: 12px;
  color: var(--fg-muted);
  padding: 2px 0;
}

.dd-threads-row {
  display: flex;
  align-items: center;
  gap: 12px;
}

.dd-threads-count {
  min-width: 24px;
  text-align: center;
  font-size: 14px;
  font-weight: 600;
  color: var(--accent);
}

.dd-slider {
  flex: 1;
  accent-color: var(--accent);
}

.dd-footer {
  display: flex;
  gap: 8px;
  padding: 12px 20px;
  border-top: 1px solid var(--border);
  justify-content: flex-end;
}

.dd-btn {
  padding: 8px 20px;
  border-radius: 8px;
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
  border: 1px solid var(--border);
  transition: all 0.15s;
}

.dd-btn-secondary {
  background: var(--bg-secondary);
  color: var(--fg);
}

.dd-btn-secondary:hover {
  background: var(--bg);
  border-color: var(--fg-muted);
}

.dd-btn-primary {
  background: var(--accent);
  color: #fff;
  border-color: var(--accent);
}

.dd-btn-primary:hover {
  opacity: 0.9;
}

.dd-btn-primary:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}
</style>
