<template>
  <div class="chat-panel">
    <div class="chat-messages" ref="messagesRef">
      <div
        v-for="msg in messages"
        :key="msg.id"
        :class="['chat-message', `chat-message--${msg.role}`]"
      >
        <div class="chat-bubble">
          <div v-if="msg.role === 'tool'" class="chat-content chat-tool-result">
            <SubAgentCard v-if="msg.toolName === 'sub_agent' && parseSubAgent(msg.content)" :data="parseSubAgent(msg.content)!" />
            <template v-else>
              <div class="tool-result-label">🔧 {{ msg.toolName || '工具' }}</div>
              <div class="tool-result-text">{{ msg.content.substring(0, 300) }}{{ msg.content.length > 300 ? '...' : '' }}</div>
            </template>
          </div>
          <div v-else-if="msg.role === 'assistant'" class="chat-content" v-html="renderMarkdown(msg.content)" />
          <div v-else class="chat-content">{{ msg.content }}</div>
          <!-- 工具调用显示 -->
          <div v-if="msg.toolCalls && msg.toolCalls.length" class="chat-tools">
            <template v-for="(tool, idx) in msg.toolCalls" :key="idx">
              <SubAgentCard v-if="tool.name === 'sub_agent' && tool.result && parseSubAgent(tool.result)" :data="parseSubAgent(tool.result)!" />
              <div v-else class="tool-item" :class="tool.status">
                <div class="tool-header">
                  <span class="tool-icon">{{ tool.status === 'running' ? '⏳' : '✅' }}</span>
                  <span class="tool-name">{{ tool.name }}</span>
                  <span v-if="tool.checkpointHash" class="checkpoint-tag" :title="`检查点: ${tool.checkpointHash}`" @click.stop="emit('viewCheckpointDiff', tool.checkpointHash)">cp:{{ tool.checkpointHash.substring(0, 8) }}</span>
                </div>
                <div v-if="tool.result" class="tool-result">{{ tool.result.substring(0, 200) }}{{ tool.result.length > 200 ? '...' : '' }}</div>
              </div>
            </template>
          </div>
          <span class="chat-time">{{ formatTime(msg.timestamp) }}</span>
        </div>
      </div>

      <!-- 流式输出 -->
      <div v-if="streamingText || (loading && !streamingText)" class="chat-message chat-message--assistant">
        <div class="chat-bubble">
          <div v-if="streamingText" class="chat-content streaming" v-html="renderMarkdown(streamingText)" />
          <div v-else class="chat-typing">
            <span></span><span></span><span></span>
          </div>
          <!-- 实时工具调用 -->
          <div v-if="toolCalls && toolCalls.length" class="chat-tools">
            <template v-for="(tool, idx) in toolCalls" :key="idx">
              <SubAgentCard v-if="tool.name === 'sub_agent' && tool.result && parseSubAgent(tool.result)" :data="parseSubAgent(tool.result)!" />
              <div v-else class="tool-item" :class="tool.status">
                <div class="tool-header">
                  <span class="tool-icon">{{ tool.status === 'running' ? '⏳' : '✅' }}</span>
                  <span class="tool-name">{{ tool.name }}</span>
                  <span v-if="tool.checkpointHash" class="checkpoint-tag" :title="`检查点: ${tool.checkpointHash}`" @click.stop="emit('viewCheckpointDiff', tool.checkpointHash)">cp:{{ tool.checkpointHash.substring(0, 8) }}</span>
                </div>
                <div v-if="tool.result" class="tool-result">{{ tool.result.substring(0, 200) }}{{ tool.result.length > 200 ? '...' : '' }}</div>
              </div>
            </template>
          </div>
        </div>
      </div>
    </div>

    <div class="chat-input-area">
      <div v-if="attachments.length" class="media-preview-bar">
        <div v-for="att in attachments" :key="att.id" class="media-preview-item">
          <img v-if="att.kind === 'image'" :src="att.dataUrl" class="media-thumb" />
          <span v-else class="media-video-label">🎬 {{ att.filename }}</span>
          <span class="media-remove" @click="removeAttachment(att.id)">&times;</span>
        </div>
      </div>
      <div style="display:flex;align-items:flex-end;gap:8px;padding:12px">
        <textarea
          ref="inputRef"
          v-model="inputText"
          class="chat-input"
          :placeholder="loading ? '等待回复中...' : '输入消息... (可粘贴/拖拽图片或视频)'"
          :disabled="loading"
          rows="1"
          @keydown="onKeydown"
          @input="autoResize"
          @paste="onPaste"
          @dragover="onDragover"
          @drop="onDrop"
        />
        <button v-if="loading" class="chat-cancel-btn" @click="emit('cancel')">
          停止
        </button>
        <button
          v-else
          class="chat-send-btn"
          :disabled="!inputText.trim() && !attachments.length"
          @click="send"
        >
          发送
        </button>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, nextTick, watch } from 'vue'
import SubAgentCard from './agent/SubAgentCard.vue'

export interface ToolCallInfo {
  name: string
  args: Record<string, unknown>
  result?: string
  status: 'running' | 'done'
  checkpointHash?: string
}

export interface ChatMessage {
  id: number
  role: 'user' | 'assistant' | 'tool'
  content: string
  timestamp: number
  toolCalls?: ToolCallInfo[]
  toolName?: string
}

export interface MediaAttachment {
  id: number
  kind: 'image' | 'video'
  dataUrl: string
  mime: string
  filename: string
}

const props = defineProps<{
  messages: ChatMessage[]
  loading: boolean
  streamingText?: string
  toolCalls?: ToolCallInfo[]
}>()

const emit = defineEmits<{
  send: [message: string, attachments?: MediaAttachment[]]
  cancel: []
  viewCheckpointDiff: [hash: string]
}>()

const inputText = ref('')
const messagesRef = ref<HTMLElement | null>(null)
const inputRef = ref<HTMLTextAreaElement | null>(null)
const attachments = ref<MediaAttachment[]>([])
let _attachId = 0

function parseSubAgent(resultStr: string): { __sub_agent__: boolean; agent_name?: string; role?: string; status?: string; content?: string; reasoning_content?: string; error?: string; tool_calls_count?: number; prompt_tokens?: number; completion_tokens?: number; duration_ms?: number } | null {
  try {
    const data = JSON.parse(resultStr)
    if (data && data.__sub_agent__) return data
  } catch { /* not JSON */ }
  return null
}

function renderMarkdown(text: string): string {
  let html = text
  html = html.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
  html = html.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
  html = html.replace(/`([^`]+)`/g, '<code>$1</code>')
  html = html.replace(/^- (.+)$/gm, '<li>$1</li>')
  html = html.replace(/(<li>.*<\/li>\n?)+/g, (match) => `<ul>${match}</ul>`)
  html = html.replace(/\n/g, '<br>')
  return html
}

function formatTime(ts: number): string {
  const d = new Date(ts)
  return `${d.getHours().toString().padStart(2, '0')}:${d.getMinutes().toString().padStart(2, '0')}`
}

function scrollToBottom() {
  nextTick(() => {
    if (messagesRef.value) {
      messagesRef.value.scrollTop = messagesRef.value.scrollHeight
    }
  })
}

function send() {
  const text = inputText.value.trim()
  if (!text && !attachments.value.length) return
  const atts = attachments.value.length > 0 ? [...attachments.value] : undefined
  emit('send', text, atts)
  inputText.value = ''
  attachments.value = []
  _attachId = 0
  nextTick(() => {
    if (inputRef.value) {
      inputRef.value.style.height = 'auto'
    }
  })
}

function removeAttachment(id: number) {
  attachments.value = attachments.value.filter(a => a.id !== id)
}

function fileToDataUrl(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader()
    reader.onload = () => resolve(reader.result as string)
    reader.onerror = reject
    reader.readAsDataURL(file)
  })
}

async function addMediaFile(file: File) {
  const mime = file.type || ''
  if (!mime.startsWith('image/') && !mime.startsWith('video/')) return
  const dataUrl = await fileToDataUrl(file)
  const kind = mime.startsWith('image/') ? 'image' as const : 'video' as const
  attachments.value.push({
    id: ++_attachId,
    kind,
    dataUrl,
    mime,
    filename: file.name,
  })
}

async function onPaste(e: ClipboardEvent) {
  const items = e.clipboardData?.items
  if (!items) return
  for (const item of items) {
    if (item.type.startsWith('image/')) {
      e.preventDefault()
      const file = item.getAsFile()
      if (file) await addMediaFile(file)
    }
  }
}

function onKeydown(e: KeyboardEvent) {
  if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) {
    e.preventDefault()
    send()
  }
}

// 拖拽支持
function onDragover(e: DragEvent) {
  e.preventDefault()
  e.stopPropagation()
}
async function onDrop(e: DragEvent) {
  e.preventDefault()
  e.stopPropagation()
  const files = e.dataTransfer?.files
  if (files) {
    for (const file of files) {
      await addMediaFile(file)
    }
  }
}

function autoResize() {
  nextTick(() => {
    if (inputRef.value) {
      inputRef.value.style.height = 'auto'
      inputRef.value.style.height = Math.min(inputRef.value.scrollHeight, 120) + 'px'
    }
  })
}

watch(() => props.messages.length, scrollToBottom)
watch(() => props.loading, scrollToBottom)
watch(() => props.streamingText, scrollToBottom)
</script>

<style scoped>
.chat-panel {
  display: flex;
  flex-direction: column;
  height: 100%;
  overflow: hidden;
}

.chat-messages {
  flex: 1;
  overflow-y: auto;
  padding: 12px;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.chat-message {
  display: flex;
}

.chat-message--user {
  justify-content: flex-end;
}

.chat-message--assistant {
  justify-content: flex-start;
}

.chat-bubble {
  max-width: 85%;
  padding: 10px 14px;
  border-radius: 12px;
  position: relative;
  word-break: break-word;
  line-height: 1.5;
}

.chat-message--user .chat-bubble {
  background: var(--accent);
  color: var(--bg);
  border-bottom-right-radius: 4px;
}

.chat-message--assistant .chat-bubble {
  background: var(--bg-secondary);
  color: var(--fg);
  border-bottom-left-radius: 4px;
}

.chat-message--tool .chat-bubble {
  background: var(--bg-secondary);
  color: var(--fg);
  border-bottom-left-radius: 4px;
  border-left: 3px solid var(--accent);
}

.chat-tool-result {
  font-size: 13px;
}

.tool-result-label {
  font-weight: 500;
  font-size: 12px;
  color: var(--accent);
  margin-bottom: 4px;
  font-family: monospace;
}

.tool-result-text {
  font-family: monospace;
  font-size: 11px;
  color: var(--fg-muted);
  white-space: pre-wrap;
  word-break: break-all;
  max-height: 120px;
  overflow-y: auto;
}

.chat-content :deep(ul) {
  padding-left: 20px;
  margin: 4px 0;
}

.chat-content :deep(li) {
  margin: 2px 0;
}

.chat-content :deep(code) {
  background: rgba(255, 255, 255, 0.1);
  padding: 1px 5px;
  border-radius: 4px;
  font-size: 13px;
}

.chat-content.streaming {
  min-height: 20px;
}

.chat-content.streaming::after {
  content: '▌';
  animation: blink 1s infinite;
  color: var(--accent);
}

@keyframes blink {
  0%, 50% { opacity: 1; }
  51%, 100% { opacity: 0; }
}

/* 工具调用 */
.chat-tools {
  margin-top: 8px;
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.tool-item {
  font-size: 12px;
  padding: 4px 8px;
  border-radius: 6px;
  background: rgba(255, 255, 255, 0.05);
  border: 1px solid var(--border);
}

.tool-item.running {
  border-color: var(--accent);
  background: rgba(var(--accent-rgb, 59, 130, 246), 0.08);
}

.tool-item.done {
  border-color: rgba(74, 222, 128, 0.3);
}

.tool-header {
  display: flex;
  align-items: center;
  gap: 4px;
}

.tool-icon {
  font-size: 11px;
}

.tool-name {
  font-weight: 500;
  color: var(--fg);
  font-family: monospace;
}

.tool-result {
  margin-top: 4px;
  font-size: 11px;
  color: var(--fg-muted);
  max-height: 60px;
  overflow: hidden;
  font-family: monospace;
}

.chat-time {
  display: block;
  font-size: 11px;
  margin-top: 4px;
  opacity: 0.6;
}

.chat-message--user .chat-time {
  text-align: right;
}

.chat-typing {
  display: flex;
  gap: 4px;
  padding: 4px 0;
}

.chat-typing span {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--fg-muted);
  animation: typing 1.2s infinite;
}

.chat-typing span:nth-child(2) { animation-delay: 0.2s; }
.chat-typing span:nth-child(3) { animation-delay: 0.4s; }

@keyframes typing {
  0%, 60%, 100% { opacity: 0.3; transform: scale(0.8); }
  30% { opacity: 1; transform: scale(1); }
}

.chat-input-area {
  display: flex;
  flex-direction: column;
  gap: 0;
  border-top: 1px solid var(--border);
  background: var(--bg-secondary);
}

.media-preview-bar {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
  padding: 4px 12px;
  max-height: 80px;
  overflow-y: auto;
}

.media-preview-item {
  position: relative;
  display: inline-block;
}

.media-thumb {
  height: 48px;
  border-radius: 4px;
  border: 1px solid var(--border);
}

.media-video-label {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 4px 8px;
  background: var(--bg);
  border-radius: 4px;
  border: 1px solid var(--border);
  font-size: 11px;
}

.media-remove {
  position: absolute;
  top: -4px;
  right: -4px;
  background: var(--danger, #e53e3e);
  color: #fff;
  border-radius: 50%;
  width: 16px;
  height: 16px;
  font-size: 10px;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  line-height: 1;
}

.chat-input {
  flex: 1;
  resize: none;
  min-height: 40px;
  max-height: 120px;
  line-height: 1.5;
  padding: 8px 12px;
  font-size: 14px;
  background: var(--bg);
  color: var(--fg);
  border: 1px solid var(--border);
  border-radius: 8px;
  outline: none;
  transition: border-color 0.2s;
}

.chat-input:focus {
  border-color: var(--accent);
}

.chat-input:disabled {
  opacity: 0.5;
}

.chat-send-btn {
  height: 40px;
  padding: 0 16px;
  font-size: 14px;
  font-weight: 500;
  background: var(--accent);
  color: var(--bg);
  border: none;
  border-radius: 8px;
  cursor: pointer;
  transition: background 0.2s, opacity 0.2s;
  white-space: nowrap;
}

.chat-send-btn:hover:not(:disabled) {
  background: var(--accent-hover);
}

.chat-send-btn:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}

.chat-cancel-btn {
  height: 40px;
  padding: 0 16px;
  font-size: 14px;
  font-weight: 500;
  background: var(--danger);
  color: #fff;
  border: none;
  border-radius: 8px;
  cursor: pointer;
  white-space: nowrap;
}

.checkpoint-tag {
  font-size: 9px;
  font-family: monospace;
  color: var(--accent);
  background: rgba(var(--accent-rgb, 59, 130, 246), 0.12);
  padding: 1px 5px;
  border-radius: 4px;
  margin-left: auto;
  cursor: pointer;
  transition: background 0.15s;
}
.checkpoint-tag:hover {
  background: rgba(var(--accent-rgb, 59, 130, 246), 0.25);
}
</style>
