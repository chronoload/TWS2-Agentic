<template>
  <div class="chat-panel">
    <div class="chat-header">
      <span class="chat-title">AI 问答</span>
      <button class="chat-close" @click="$emit('close')">✕</button>
    </div>

    <div class="chat-messages" ref="messagesRef">
      <div
        v-for="(msg, idx) in messages"
        :key="idx"
        class="chat-msg"
        :class="msg.role"
      >
        <div class="msg-avatar">{{ msg.role === 'user' ? '👤' : '🤖' }}</div>
        <div class="msg-body">
          <div class="msg-content" v-html="renderMarkdown(msg.content)"></div>
          <div v-if="msg.sources && msg.sources.length" class="msg-sources">
            <div class="source-label">来源：</div>
            <div v-for="(src, si) in msg.sources" :key="si" class="source-item">
              📄 {{ src.file_name }} (第{{ src.page }}页)
            </div>
          </div>
        </div>
      </div>
      <div v-if="streaming" class="chat-msg assistant">
        <div class="msg-avatar">🤖</div>
        <div class="msg-body">
          <div class="msg-content" v-html="renderMarkdown(streamingText)"></div>
          <span class="streaming-cursor">▌</span>
        </div>
      </div>
    </div>

    <div class="chat-input-area">
      <textarea
        v-model="inputText"
        class="chat-input"
        placeholder="输入问题，回车发送..."
        rows="2"
        @keydown.enter.exact.prevent="sendMessage"
      ></textarea>
      <button class="chat-send-btn" @click="sendMessage" :disabled="!inputText.trim() || streaming">
        发送
      </button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, nextTick, onMounted } from 'vue'
import { agentChatStreamFetch } from '../api'

const props = defineProps<{
  pdfPath: string
}>()

defineEmits<{
  close: []
}>()

interface Source {
  file_name: string
  page: number
}

interface ChatMessage {
  role: 'user' | 'assistant'
  content: string
  sources?: Source[]
}

const messages = ref<ChatMessage[]>([])
const inputText = ref('')
const streaming = ref(false)
const streamingText = ref('')
const messagesRef = ref<HTMLDivElement | null>(null)
let abortController: AbortController | null = null

function renderMarkdown(text: string): string {
  if (!text) return ''
  return text
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
    .replace(/`(.+?)`/g, '<code>$1</code>')
    .replace(/\n/g, '<br>')
}

function scrollToBottom() {
  nextTick(() => {
    if (messagesRef.value) {
      messagesRef.value.scrollTop = messagesRef.value.scrollHeight
    }
  })
}

async function sendMessage() {
  const text = inputText.value.trim()
  if (!text || streaming.value) return

  messages.value.push({ role: 'user', content: text })
  inputText.value = ''
  streaming.value = true
  streamingText.value = ''
  scrollToBottom()

  try {
    abortController = await agentChatStreamFetch(
      text,
      { pdf_path: props.pdfPath },
      (token: string) => {
        streamingText.value += token
        scrollToBottom()
      },
      () => {},
      () => {},
      (reply: string) => {
        messages.value.push({ role: 'assistant', content: reply || streamingText.value })
        streaming.value = false
        streamingText.value = ''
        scrollToBottom()
      },
      (err: string) => {
        messages.value.push({ role: 'assistant', content: `错误: ${err}` })
        streaming.value = false
        streamingText.value = ''
        scrollToBottom()
      },
    )
  } catch (e: any) {
    messages.value.push({ role: 'assistant', content: `请求失败: ${e.message || '未知错误'}` })
    streaming.value = false
    streamingText.value = ''
    scrollToBottom()
  }
}

onMounted(() => {
  messages.value.push({
    role: 'assistant',
    content: '你好！我可以帮你回答关于这份 PDF 的问题。请输入你的问题。',
  })
})
</script>

<style scoped>
.chat-panel {
  display: flex;
  flex-direction: column;
  width: 360px;
  height: 100%;
  background: var(--bg-secondary);
  border-left: 1px solid var(--border);
  flex-shrink: 0;
}

.chat-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 10px 14px;
  border-bottom: 1px solid var(--border);
  flex-shrink: 0;
}

.chat-title {
  font-size: 14px;
  font-weight: 600;
  color: var(--fg);
}

.chat-close {
  background: transparent;
  border: none;
  color: var(--fg-muted);
  font-size: 16px;
  cursor: pointer;
  padding: 2px 6px;
  border-radius: 4px;
}

.chat-close:hover {
  color: var(--fg);
  background: var(--bg);
}

.chat-messages {
  flex: 1;
  overflow-y: auto;
  padding: 12px;
}

.chat-msg {
  display: flex;
  gap: 8px;
  margin-bottom: 14px;
}

.chat-msg.user {
  flex-direction: row-reverse;
}

.msg-avatar {
  font-size: 18px;
  flex-shrink: 0;
  width: 28px;
  text-align: center;
}

.msg-body {
  max-width: 85%;
}

.chat-msg.user .msg-body {
  text-align: right;
}

.msg-content {
  display: inline-block;
  padding: 8px 12px;
  border-radius: 10px;
  font-size: 13px;
  line-height: 1.6;
  word-break: break-word;
}

.chat-msg.user .msg-content {
  background: var(--accent);
  color: #fff;
  border-bottom-right-radius: 3px;
}

.chat-msg.assistant .msg-content {
  background: var(--bg);
  color: var(--fg);
  border-bottom-left-radius: 3px;
}

.msg-content :deep(code) {
  background: rgba(255, 255, 255, 0.1);
  padding: 1px 4px;
  border-radius: 3px;
  font-size: 12px;
}

.msg-sources {
  margin-top: 6px;
  font-size: 11px;
  color: var(--fg-muted);
}

.source-label {
  font-weight: 600;
  margin-bottom: 2px;
}

.source-item {
  padding: 2px 0;
}

.streaming-cursor {
  color: var(--accent);
  animation: blink 0.8s infinite;
}

@keyframes blink {
  0%, 50% { opacity: 1; }
  51%, 100% { opacity: 0; }
}

.chat-input-area {
  display: flex;
  gap: 8px;
  padding: 10px 12px;
  border-top: 1px solid var(--border);
  flex-shrink: 0;
}

.chat-input {
  flex: 1;
  padding: 8px 10px;
  border: 1px solid var(--border);
  border-radius: 8px;
  background: var(--bg);
  color: var(--fg);
  font-size: 13px;
  resize: none;
  font-family: inherit;
  line-height: 1.4;
}

.chat-input:focus {
  outline: none;
  border-color: var(--accent);
}

.chat-input::placeholder {
  color: var(--fg-muted);
}

.chat-send-btn {
  background: var(--accent);
  color: #fff;
  border: none;
  border-radius: 8px;
  padding: 8px 16px;
  font-size: 13px;
  font-weight: 500;
  cursor: pointer;
  white-space: nowrap;
  transition: filter 0.15s;
}

.chat-send-btn:hover:not(:disabled) {
  filter: brightness(1.1);
}

.chat-send-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}
</style>
