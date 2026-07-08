<template>
  <div class="view agent-view">
    <header class="view-header">
      <h1>AI Agent</h1>
      <div class="header-actions">
        <span v-if="agentAvailable" class="agent-status available">就绪</span>
        <span v-else class="agent-status unavailable">未配置</span>
        <button class="btn-icon-sm" @click="showCheckpoints = true; hasNewCheckpoints = false" title="检查点">
          🔖<span v-if="hasNewCheckpoints" class="badge-dot"></span>
        </button>
        <button class="btn-icon-sm" @click="showSessions = true" title="历史会话">📋</button>
        <button class="btn-icon-sm" @click="newSession" title="新建会话">➕</button>
        <button class="btn-icon-sm" @click="resetChat" title="重置对话">🔄</button>
      </div>
    </header>
    <div class="agent-body">
      <ChatPanel
        :messages="messages"
        :loading="loading"
        :streaming-text="streamingText"
        :tool-calls="activeToolCalls"
        @send="onSend"
        @cancel="onCancel"
        @view-checkpoint-diff="showCheckpointFromTag"
      />
    </div>
    <SwarmPanel />
    <!-- 会话列表模态框 -->
    <div v-if="showSessions" class="session-overlay" @click.self="showSessions = false">
      <div class="session-modal">
        <div class="session-modal-header">
          <h3>历史会话</h3>
          <button class="modal-close-btn" @click="showSessions = false">✕</button>
        </div>
        <div class="session-list">
          <div v-if="sessions.length === 0" class="session-empty">暂无历史会话</div>
          <div v-for="s in sessions" :key="s.id" class="session-item">
            <div class="session-item-info" @click="loadSession(s.id)">
              <span class="session-preview">{{ (s.summary || s.preview || '(无预览)').substring(0, 50) }}</span>
              <span class="session-meta">{{ formatSessionTime(s.timestamp) }} · {{ s.message_count }}条</span>
            </div>
            <button class="session-del-btn" @click.stop="deleteSession(s.id)">✕</button>
          </div>
        </div>
      </div>
    </div>
    <!-- 检查点侧边栏 -->
    <div v-if="showCheckpoints" class="session-overlay" @click.self="showCheckpoints = false">
      <div class="session-modal">
          <div class="session-modal-header">
            <h3>🔖 检查点</h3>
            <button class="modal-close-btn" @click="showCheckpoints = false">✕</button>
          </div>
          <div class="session-list">
            <div v-if="checkpoints.length === 0" class="session-empty">暂无检查点 — 发送消息后系统会自动创建</div>
            <div v-for="cp in checkpoints" :key="cp.hash" class="checkpoint-item">
              <div class="checkpoint-item-info">
                <span v-if="cp.meta?.step" class="checkpoint-seq-badge">#{{ cp.meta.step }}</span>
                <span v-else-if="parseCheckpointMsg(cp.message).seqLabel" class="checkpoint-seq-badge">{{ parseCheckpointMsg(cp.message).seqLabel }}</span>
                <code class="checkpoint-hash">{{ cp.hash.substring(0, 8) }}</code>
                <span class="checkpoint-msg">{{ cp.meta?.tool || parseCheckpointMsg(cp.message).toolLabel }}</span>
                <span v-if="cp.meta?.source === 'baseline'" class="checkpoint-instance">baseline</span>
                <span v-else-if="cp.meta?.instance" class="checkpoint-instance">{{ cp.meta.instance }}</span>
                <span v-else-if="parseCheckpointMsg(cp.message).instanceLabel" class="checkpoint-instance">{{ parseCheckpointMsg(cp.message).instanceLabel }}</span>
                <span v-if="cp.diff_count" class="checkpoint-diff-count">{{ cp.diff_count }} files</span>
                <span class="checkpoint-time">{{ formatCheckpointTime(cp.timestamp) }}</span>
              </div>
              <div class="checkpoint-actions">
                <button class="checkpoint-action-btn" @click="showCheckpointDiff(cp.hash)" title="查看差异">📊 差异</button>
                <button class="checkpoint-action-btn primary" @click="restoreCheckpointModal(cp.hash, cp.message)" title="回退">↩️ 回退</button>
              </div>
              <!-- diff 展开 -->
            <div v-if="activeDiff === cp.hash" class="checkpoint-diff-panel">
              <div v-if="diffLoading" class="diff-loading">加载差异中...</div>
              <div v-else-if="diffData.length === 0" class="diff-empty">无差异</div>
              <div v-else>
                <div v-if="diffSummary" class="diff-summary">+{{ diffSummary.additions }} -{{ diffSummary.deletions }} ({{ diffSummary.files_changed }} files)</div>
                <div v-for="d in diffData" :key="d.path" class="diff-entry">
                  <div class="diff-entry-header">
                    <span :class="'diff-status diff-' + d.status">{{ d.status === 'A' ? '新增' : d.status === 'D' ? '删除' : '修改' }}</span>
                    <span class="diff-path">{{ d.path }}</span>
                    <span class="diff-stats">+{{ d.additions || 0 }} -{{ d.deletions || 0 }}</span>
                  </div>
                  <pre v-if="d.diff" class="diff-content">{{ d.diff.substring(0, 500) }}{{ d.diff.length > 500 ? '...' : '' }}</pre>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
    <!-- 恢复模式对话框 -->
    <div v-if="showRestoreModal" class="session-overlay" @click.self="showRestoreModal = false">
      <div class="session-modal" style="max-width:380px">
        <div class="session-modal-header">
          <div style="display:flex;align-items:center;gap:8px">
            <button class="modal-back-btn" @click="showRestoreModal = false">← 返回</button>
            <h3>↩️ 恢复模式</h3>
          </div>
          <button class="modal-close-btn" @click="showRestoreModal = false">✕</button>
        </div>
        <div style="padding:8px 12px">
          <div v-for="m in restoreModes" :key="m.id" class="restore-mode-card" @click="doRestoreCheckpoint(m.id)">
            <div class="restore-mode-icon">{{ m.icon }}</div>
            <div>
              <div class="restore-mode-label">{{ m.label }}</div>
              <div class="restore-mode-desc">{{ m.desc }}</div>
            </div>
          </div>
          <div style="font-size:11px;color:var(--fg-dim);margin-top:8px;padding:4px 0">⚠️ 恢复后当前工作区将被替换，不可撤销</div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, onUnmounted, watch } from 'vue'
import { agentChatStreamFetch, getAgentStatus, resetAgent, getAgentSessions, createAgentSession, switchAgentSession, deleteAgentSession, getAgentCheckpoints, getAgentCheckpointDiff, restoreAgentCheckpoint } from '../api'
import { useWebSocket } from '../composables/useWebSocket'
import ChatPanel from '../components/ChatPanel.vue'
import SwarmPanel from '../components/agent/SwarmPanel.vue'

interface ToolCallInfo {
  name: string
  args: Record<string, unknown>
  result?: string
  status: 'running' | 'done'
  checkpointHash?: string
}

interface ChatMessage {
  id: number
  role: 'user' | 'assistant' | 'tool'
  content: string
  timestamp: number
  toolCalls?: ToolCallInfo[]
  toolName?: string
}

const messages = ref<ChatMessage[]>([])
const loading = ref(false)
const agentAvailable = ref(false)
const streamingText = ref('')
const activeToolCalls = ref<ToolCallInfo[]>([])
let msgId = 0
let abortController: AbortController | null = null

// ─── session_id 持久化（参考 Crush Session.ID）──────────
// 刷新后仍能读取同一会话的检查点
const SESSION_ID_KEY = 'ts2_agent_session_id'
function _loadSessionId(): string {
  const saved = localStorage.getItem(SESSION_ID_KEY)
  if (saved) return saved
  // 首次访问：生成稳定 ID 并持久化
  const id = 'sess_' + Date.now().toString(36) + '_' + Math.random().toString(36).substring(2, 8)
  localStorage.setItem(SESSION_ID_KEY, id)
  return id
}
const sessionId = ref(_loadSessionId())

function addMessage(role: 'user' | 'assistant' | 'tool', content: string, toolCalls?: ToolCallInfo[], toolName?: string): number {
  const id = ++msgId
  messages.value.push({ id, role, content, timestamp: Date.now(), toolCalls, toolName })
  return id
}

async function onSend(text: string, mediaAttachments?: any[]) {
  addMessage('user', text)
  loading.value = true
  streamingText.value = ''
  activeToolCalls.value = []

  // 构建附件 payload
  const attachments = mediaAttachments?.map(a => ({
    kind: a.kind,
    data_url: a.dataUrl,
    path: a.filename || '',
  }))

  // 环境感知：收集当前 UI 状态注入到上下文
  const context: Record<string, unknown> = {
    source: 'web-mobile',
    ui_state: {
      current_page: window.location.pathname,
      timestamp: new Date().toISOString(),
      viewport: `${window.innerWidth}x${window.innerHeight}`,
      online: navigator.onLine,
    },
  }

  // 尝试获取当前页面的上下文信息（如课程/任务等）
  try {
    const bootstrap = (window as any).__TS2_BOOTSTRAP__
    if (bootstrap) {
      // 如果用户在课程/执行页面，注入当前课程信息
      if (bootstrap.courses && Array.isArray(bootstrap.courses)) {
        context.ui_state.available_courses = bootstrap.courses.length
      }
      if (bootstrap.tasks) {
        context.ui_state.available_tasks = Array.isArray(bootstrap.tasks) ? bootstrap.tasks.length : 0
      }
    }
  } catch { /* 静默 */ }

  abortController = await agentChatStreamFetch(
    text,
    context,
    // onToken
    (token) => {
      streamingText.value += token
    },
    // onToolCall
    (name, args) => {
      activeToolCalls.value.push({ name, args, status: 'running' })
    },
    // onToolResult
    (name, result, checkpointHash) => {
      const tool = activeToolCalls.value.find(t => t.name === name && t.status === 'running')
      if (tool) {
        tool.result = result
        tool.status = 'done'
        if (checkpointHash) {
          tool.checkpointHash = checkpointHash
        }
      }
    },
    // onDone
    (reply) => {
      // 防止重复调用（done 事件和 [DONE] 都可能触发）
      if (!loading.value) return
      const finalContent = streamingText.value || reply
      addMessage('assistant', finalContent, [...activeToolCalls.value])
      streamingText.value = ''
      activeToolCalls.value = []
      loading.value = false
    },
    // onError
    (err) => {
      addMessage('assistant', `错误: ${err}`)
      streamingText.value = ''
      activeToolCalls.value = []
      loading.value = false
    },
    // sessionId — 传递持久化的会话 ID
    sessionId.value,
    attachments,
  )
}

function onCancel() {
  if (abortController) {
    abortController.abort()
    abortController = null
  }
  if (streamingText.value) {
    addMessage('assistant', streamingText.value + '\n\n[已取消]')
    streamingText.value = ''
  }
  activeToolCalls.value = []
  loading.value = false
}

async function resetChat() {
  onCancel()
  loading.value = false
  streamingText.value = ''
  activeToolCalls.value = []
  try {
    await resetAgent()
  } catch { /* ignore */ }
  messages.value = []
  msgId = 0
  // 重置时生成新 session_id
  const newId = 'sess_' + Date.now().toString(36) + '_' + Math.random().toString(36).substring(2, 8)
  sessionId.value = newId
  localStorage.setItem(SESSION_ID_KEY, newId)
  addMessage('assistant', '对话已重置。你好！我是 TS2 学习助手。')
}

const showSessions = ref(false)
const sessions = ref<any[]>([])
const showCheckpoints = ref(false)
const showRestoreModal = ref(false)
const restoreTarget = ref('')
const checkpoints = ref<any[]>([])
const activeDiff = ref('')
const diffData = ref<any[]>([])
const diffSummary = ref<{ additions: number; deletions: number; files_changed: number } | null>(null)
const diffLoading = ref(false)
const checkpointVersion = ref(0)  // Crush VersionedMap: 前端按需刷新
const hasNewCheckpoints = ref(false)  // 红点标记：有新检查点未查看

// ─── WebSocket 事件监听（参考 Crush PubSub）──────────
const { onMessage } = useWebSocket()
onMessage((msg) => {
  if (msg.cmd === 'checkpoint_created' && msg.data) {
    const newVersion = msg.data.version || 0
    if (newVersion > checkpointVersion.value) {
      checkpointVersion.value = newVersion
      if (showCheckpoints.value) {
        // 侧边栏已打开，自动刷新
        loadCheckpointList()
      } else {
        // 侧边栏未打开，显示红点
        hasNewCheckpoints.value = true
      }
    }
  }
})

async function loadSessionList() {
  try {
    const res = await getAgentSessions()
    sessions.value = res.data?.data ?? res.data ?? []
  } catch { /* ignore */ }
}

async function newSession() {
  // 先取消当前正在进行的对话
  onCancel()
  loading.value = false
  streamingText.value = ''
  activeToolCalls.value = []
  // 生成新 session_id
  const newId = 'sess_' + Date.now().toString(36) + '_' + Math.random().toString(36).substring(2, 8)
  sessionId.value = newId
  localStorage.setItem(SESSION_ID_KEY, newId)
  try {
    const res = await createAgentSession()
    const data = res.data?.data ?? res.data
    if (data?.created) {
      messages.value = []
      msgId = 0
      addMessage('assistant', '新会话已创建。你好！我是 TS2 学习助手。')
    } else {
      // 创建失败时手动重置
      await resetAgent()
      messages.value = []
      msgId = 0
      addMessage('assistant', '新会话已创建。你好！我是 TS2 学习助手。')
    }
  } catch {
    // 降级：直接重置
    try { await resetAgent() } catch { /* ignore */ }
    messages.value = []
    msgId = 0
    addMessage('assistant', '新会话已创建。你好！我是 TS2 学习助手。')
  }
}

async function loadSession(sessionId: string) {
  try {
    const res = await switchAgentSession(sessionId)
    const data = res.data?.data ?? res.data
    if (data?.switched) {
      showSessions.value = false
      messages.value = []
      msgId = 0
      // 从服务端返回的消息列表还原 UI（包含 tool 消息细节）
      const restoredMessages = data.messages || []
      if (restoredMessages.length > 0) {
        for (const msg of restoredMessages) {
          if (msg.role === 'tool') {
            addMessage('tool', msg.content || '', undefined, msg.tool_name || '')
          } else if (msg.role === 'assistant') {
            // 将 tool_calls 转为 ToolCallInfo 格式
            const toolCalls: ToolCallInfo[] | undefined = msg.tool_calls?.map((tc: any) => {
              const tcDict = typeof tc === 'object' ? tc : {}
              const func = tcDict.function || {}
              let args = {}
              try {
                args = typeof func.arguments === 'string' ? JSON.parse(func.arguments) : (func.arguments || {})
              } catch { /* ignore */ }
              return { name: func.name || '', args, status: 'done' as const }
            })
            addMessage('assistant', msg.content || '', toolCalls?.length ? toolCalls : undefined)
          } else if (msg.role === 'user') {
            addMessage('user', msg.content || '')
          }
        }
      } else {
        addMessage('assistant', '已载入历史会话。')
      }
    } else {
      alert(data?.error || '载入会话失败')
    }
  } catch {
    alert('载入会话失败')
  }
}

async function deleteSession(sessionId: string) {
  try {
    await deleteAgentSession(sessionId)
    sessions.value = sessions.value.filter(s => s.id !== sessionId)
  } catch { /* ignore */ }
}

function formatSessionTime(ts: number): string {
  const d = new Date(ts * 1000)
  // ts 可能已经是毫秒级（>1e12），不需要再乘1000
  const date = ts > 1e12 ? new Date(ts) : d
  return `${date.getMonth()+1}/${date.getDate()} ${date.getHours()}:${String(date.getMinutes()).padStart(2, '0')}`
}

watch(showSessions, (val) => {
  if (val) loadSessionList()
})

watch(showCheckpoints, (val) => {
  if (val) loadCheckpointList()
})

async function loadCheckpointList() {
  try {
    const res = await getAgentCheckpoints(sessionId.value)
    const data = res.data?.data
    checkpoints.value = data?.checkpoints ?? []
    // 记录服务端 version，下次打开时可按需刷新
    if (data?.version) checkpointVersion.value = data.version
  } catch { checkpoints.value = [] }
}

const restoreModes = [
  { id: 'taskAndFiles', icon: '🔃', label: '对话 + 文件', desc: '同时恢复对话历史和工作区文件（推荐）' },
  { id: 'task', icon: '💬', label: '仅对话', desc: '只恢复对话历史，保留当前文件' },
  { id: 'files', icon: '📁', label: '仅文件', desc: '只恢复工作区文件，保留当前对话' },
]

function restoreCheckpointModal(commitHash: string, _message: string) {
  restoreTarget.value = commitHash
  showRestoreModal.value = true
}

async function doRestoreCheckpoint(restoreType: string) {
  showRestoreModal.value = false
  const commitHash = restoreTarget.value
  if (!commitHash) return
  try {
    const res = await restoreAgentCheckpoint(commitHash, restoreType)
    if (res.data?.data?.restored) {
      showCheckpoints.value = false
      activeDiff.value = ''
      diffData.value = []
      // 重建前端消息列表
      const uiMsgs = res.data?.data?.ui_messages ?? []
      if (uiMsgs.length > 0) {
        messages.value = []
        msgId = 0
        for (const m of uiMsgs) {
          if (m.role === 'tool') {
            addMessage('tool', m.content || '', undefined, m.tool_name)
          } else {
            addMessage(m.role as 'user' | 'assistant', m.content || '')
          }
        }
      }
      alert('已恢复检查点')
    } else {
      alert('恢复失败: ' + (res.data?.data?.error || '未知错误'))
    }
  } catch (e: any) {
    alert('恢复失败: ' + (e.message || '网络错误'))
  }
}

async function showCheckpointDiff(commitHash: string) {
  if (activeDiff.value === commitHash) {
    activeDiff.value = ''
    return
  }
  activeDiff.value = commitHash
  diffLoading.value = true
  diffData.value = []
  diffSummary.value = null
  try {
    const res = await getAgentCheckpointDiff(commitHash)
    diffData.value = res.data?.data?.diff ?? []
    diffSummary.value = res.data?.data?.summary ?? null
  } catch { diffData.value = [] }
  diffLoading.value = false
}

function formatCheckpointTime(ts: number): string {
  const date = ts > 1e12 ? new Date(ts) : new Date(ts * 1000)
  return `${date.getMonth()+1}/${date.getDate()} ${date.getHours()}:${String(date.getMinutes()).padStart(2, '0')}`
}

function parseCheckpointMsg(raw: string): { instanceLabel: string; seqLabel: string; toolLabel: string } {
  const clean = raw.replace('TS2 checkpoint: ', '')
  const m = clean.match(/^\[([^\]]+)\]\[(\d+)\]\s*(.*)/)
  if (m) {
    return {
      instanceLabel: `[${m[1]}]`,
      seqLabel: `#${parseInt(m[2], 10)}`,
      toolLabel: m[3],
    }
  }
  return { instanceLabel: '', seqLabel: '', toolLabel: clean }
}

function showCheckpointFromTag(hash: string) {
  showCheckpoints.value = true
  // 触发 diff 加载
  showCheckpointDiff(hash)
}

onMounted(async () => {
  try {
    const res = await getAgentStatus()
    const data = res.data?.data ?? res.data
    agentAvailable.value = data?.available ?? false
  } catch {
    agentAvailable.value = false
  }
  addMessage('assistant', '你好！我是 TS2 学习助手，可以帮你管理课程、回答问题、制定学习计划。')
})
</script>

<style scoped>
.agent-view {
  height: 100%;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.agent-body {
  flex: 1;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.header-actions {
  display: flex;
  align-items: center;
  gap: 8px;
}

.agent-status {
  font-size: 11px;
  padding: 2px 8px;
  border-radius: 10px;
  font-weight: 500;
}

.agent-status.available {
  background: rgba(74, 222, 128, 0.15);
  color: #4ade80;
}

.agent-status.unavailable {
  background: rgba(239, 68, 68, 0.15);
  color: #ef4444;
}

.btn-icon-sm {
  background: transparent;
  border: 1px solid var(--border);
  color: var(--fg-muted);
  font-size: 14px;
  padding: 4px 8px;
  border-radius: 6px;
  cursor: pointer;
}

.btn-icon-sm:hover {
  color: var(--accent);
  border-color: var(--accent);
}

.badge-dot {
  position: absolute;
  top: -2px;
  right: -2px;
  width: 8px;
  height: 8px;
  background: #ef4444;
  border-radius: 50%;
  display: inline-block;
}

.btn-icon-sm {
  position: relative;
}

.session-overlay {
  position: fixed;
  inset: 0;
  background: rgba(0,0,0,0.5);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 200;
}

.session-modal {
  background: var(--bg);
  border: 1px solid var(--border);
  border-radius: 12px;
  width: 90%;
  max-width: 400px;
  max-height: 70vh;
  overflow: hidden;
  display: flex;
  flex-direction: column;
}

.session-modal-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 12px 16px;
  border-bottom: 1px solid var(--border);
}

.session-modal-header h3 {
  font-size: 15px;
  margin: 0;
}

.modal-close-btn {
  background: transparent;
  border: none;
  color: var(--fg-muted);
  font-size: 16px;
  cursor: pointer;
}

.modal-back-btn {
  background: transparent;
  border: 1px solid var(--border);
  color: var(--accent);
  font-size: 12px;
  padding: 3px 10px;
  border-radius: 6px;
  cursor: pointer;
}
.modal-back-btn:hover {
  background: rgba(var(--accent-rgb, 59, 130, 246), 0.1);
}

.session-list {
  overflow-y: auto;
  padding: 8px;
}

.session-empty {
  text-align: center;
  color: var(--fg-muted);
  padding: 24px;
  font-size: 13px;
}

.session-item {
  display: flex;
  align-items: center;
  padding: 10px;
  border-bottom: 1px solid var(--border);
}

.session-item:last-child {
  border-bottom: none;
}

.session-item-info {
  flex: 1;
  min-width: 0;
  cursor: pointer;
}

.session-preview {
  display: block;
  font-size: 13px;
  color: var(--fg);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.session-meta {
  display: block;
  font-size: 11px;
  color: var(--fg-muted);
  margin-top: 2px;
}

.session-del-btn {
  background: transparent;
  border: 1px solid var(--border);
  color: var(--fg-muted);
  font-size: 12px;
  padding: 2px 6px;
  border-radius: 4px;
  cursor: pointer;
  margin-left: 8px;
}

.session-del-btn:hover {
  color: #ef4444;
  border-color: #ef4444;
}

.checkpoint-item {
  border-bottom: 1px solid var(--border);
  padding: 8px 10px;
}

.checkpoint-item:last-child {
  border-bottom: none;
}

.checkpoint-item-info {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 6px;
}

.checkpoint-hash {
  font-size: 10px;
  color: var(--accent);
  background: rgba(var(--accent-rgb, 59, 130, 246), 0.1);
  padding: 1px 6px;
  border-radius: 4px;
}

.checkpoint-seq-badge {
  font-size: 10px;
  color: #fff;
  background: var(--accent);
  padding: 0 5px;
  border-radius: 4px;
  font-weight: 600;
}

.checkpoint-instance {
  font-size: 10px;
  color: var(--fg-muted);
  font-family: monospace;
}

.checkpoint-diff-count {
  font-size: 10px;
  color: var(--accent);
  background: var(--accent-dim, rgba(122,162,247,0.08));
  padding: 1px 5px;
  border-radius: 4px;
}

.diff-summary {
  font-size: 11px;
  color: var(--fg-muted);
  padding: 4px 8px;
  border-bottom: 1px solid var(--border);
  margin-bottom: 4px;
}

.checkpoint-msg {
  font-size: 12px;
  color: var(--fg);
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.checkpoint-time {
  font-size: 10px;
  color: var(--fg-muted);
}

.checkpoint-actions {
  display: flex;
  gap: 4px;
  margin-top: 4px;
}

.checkpoint-action-btn {
  background: transparent;
  border: 1px solid var(--border);
  font-size: 12px;
  padding: 2px 6px;
  border-radius: 4px;
  cursor: pointer;
  transition: border-color 0.15s;
}
.checkpoint-action-btn:hover {
  border-color: var(--accent);
}
.checkpoint-action-btn.primary {
  background: var(--accent);
  color: #fff;
  border-color: var(--accent);
  font-weight: 600;
}
.checkpoint-action-btn.primary:hover {
  opacity: 0.85;
}

.checkpoint-diff-panel {
  margin-top: 6px;
  padding: 8px;
  background: var(--bg-secondary);
  border-radius: 6px;
  max-height: 500px;
  overflow-y: auto;
}

.diff-loading {
  font-size: 11px;
  color: var(--fg-muted);
  padding: 4px;
}

.diff-empty {
  font-size: 11px;
  color: var(--fg-muted);
  padding: 4px;
}

.diff-entry {
  margin-bottom: 6px;
}

.diff-entry:last-child {
  margin-bottom: 0;
}

.diff-entry-header {
  display: flex;
  gap: 6px;
  align-items: center;
  margin-bottom: 2px;
}

.diff-status {
  font-size: 9px;
  font-weight: 600;
  padding: 1px 4px;
  border-radius: 3px;
}
.diff-status.M { background: rgba(250, 204, 21, 0.2); color: #facc15; }
.diff-status.A { background: rgba(74, 222, 128, 0.2); color: #4ade80; }
.diff-status.D { background: rgba(239, 68, 68, 0.2); color: #ef4444; }

.diff-path {
  font-size: 11px;
  font-family: monospace;
  color: var(--fg);
}

.diff-stats {
  font-size: 10px;
  color: var(--fg-muted);
  margin-left: auto;
}

.diff-content {
  font-size: 10px;
  font-family: monospace;
  color: var(--fg-muted);
  white-space: pre;
  overflow-x: auto;
  margin: 0;
  padding: 4px;
  background: rgba(0, 0, 0, 0.1);
  border-radius: 4px;
  max-height: 300px;
  overflow-y: auto;
}

.restore-mode-card {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px;
  border: 1px solid var(--border);
  border-radius: 8px;
  margin-bottom: 6px;
  cursor: pointer;
  background: var(--bg-secondary);
  transition: background 0.15s;
}
.restore-mode-card:hover {
  background: rgba(122, 162, 247, 0.08);
}
.restore-mode-icon {
  font-size: 22px;
  flex-shrink: 0;
}
.restore-mode-label {
  font-size: 13px;
  font-weight: 600;
}
.restore-mode-desc {
  font-size: 11px;
  color: var(--fg-muted);
  margin-top: 2px;
}
</style>
