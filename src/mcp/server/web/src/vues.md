

================================================
FILE: C:\Users\qu\Desktop\物理科学与技术论题\TS2\mcp\server\web\src\views\AgentView.vue
================================================

``vue
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

``



================================================
FILE: C:\Users\qu\Desktop\物理科学与技术论题\TS2\mcp\server\web\src\views\BookmarksView.vue
================================================

```vue
<template>
  <div class="view">
    <header class="view-header">
      <h1>书签</h1>
    </header>
    <div class="view-body">
      <!-- toolbar -->
      <div v-if="store.bookmarks.length > 0" class="bookmark-toolbar">
        <div class="bookmark-actions">
          <input v-model="searchQuery" class="bookmark-search" placeholder="搜索书签..." autocomplete="off" />
          <button class="add-btn" @click="showAddDialog">➕ 添加</button>
        </div>
        <div class="bookmark-categories">
          <span class="cat-btn" :class="{ active: activeCategory === '' }" @click="activeCategory = ''">全部</span>
          <span v-for="cat in categories" :key="cat" class="cat-btn" :class="{ active: activeCategory === cat }" @click="activeCategory = cat">{{ catLabel(cat) }}</span>
        </div>
      </div>

      <div v-if="store.loading" class="loading">加载中...</div>
      <div v-else-if="store.bookmarks.length === 0" class="empty">暂无书签</div>
      <div v-else-if="filteredBookmarks.length === 0" class="empty">无匹配书签</div>
      <div v-else class="bookmark-list">
        <div v-for="bm in filteredBookmarks" :key="bm.id || bm.url || bm.link" class="bookmark-item" @click="openBookmark(bm)">
          <span class="bookmark-icon">{{ bm.icon || '🔗' }}</span>
          <div class="bookmark-info">
            <span class="bookmark-title">{{ bm.title || bm.name || bm.path || '未命名' }}</span>
            <span v-if="bm.url || bm.link" class="bookmark-path">{{ bm.url || bm.link }}</span>
            <span v-else-if="bm.path" class="bookmark-path">{{ bm.path }}</span>
          </div>
          <span class="bookmark-cat-tag">{{ catLabel(bm.category || bm.group || '') }}</span>
          <button class="bm-remove" @click.stop="removeBookmark(bm)">✕</button>
        </div>
      </div>
    </div>

    <!-- Add Dialog -->
    <div v-if="showDialog" class="dialog-overlay" @click.self="cancelAdd">
      <div class="dialog-box">
        <h3 class="dialog-title">添加书签</h3>
        <div class="form-row">
          <input v-model="form.name" class="form-input" placeholder="名称" ref="nameInput" />
        </div>
        <div class="form-row">
          <div class="url-row">
            <input v-model="form.url" class="form-input" placeholder="URL..." style="flex:1" />
            <button class="paste-btn" @click="pasteUrl" title="从剪贴板粘贴">📋</button>
          </div>
        </div>
        <div class="form-row radio-row">
          <label v-for="cat in allCategories" :key="cat" class="radio-label">
            <input type="radio" v-model="form.category" :value="cat" />
            <span>{{ catLabel(cat) }}</span>
          </label>
        </div>
        <p v-if="addError" class="error-msg">{{ addError }}</p>
        <div class="dialog-actions">
          <button class="dialog-btn cancel" @click="cancelAdd">取消</button>
          <button class="dialog-btn save" @click="saveBookmark">保存</button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, nextTick } from 'vue'
import { useBookmarksStore } from '../stores/bookmarks'

const store = useBookmarksStore()
store.load()

const searchQuery = ref('')
const activeCategory = ref('')
const showDialog = ref(false)
const addError = ref('')
const nameInput = ref<HTMLInputElement | null>(null)
const form = ref({ name: '', url: '', category: 'tool', icon: '' })

const CAT_LABELS: Record<string, string> = {
  preprint: '预印本', search: '学术搜索', journal: '期刊',
  database: '数据库', tool: '工具', other: '其他',
}

const allCategories = ['preprint', 'search', 'journal', 'database', 'tool', 'other']

const categories = computed(() => {
  const set = new Set<string>()
  for (const bm of store.bookmarks) {
    const cat = (bm as any).category || (bm as any).group || ''
    if (cat) set.add(cat)
  }
  return [...set].sort()
})

const filteredBookmarks = computed(() => {
  let list = store.bookmarks
  if (activeCategory.value) {
    list = list.filter((bm: any) => (bm.category || bm.group || '') === activeCategory.value)
  }
  const q = searchQuery.value.trim().toLowerCase()
  if (q) {
    list = list.filter((bm: any) => {
      const title = (bm.title || bm.name || '').toLowerCase()
      const url = (bm.url || bm.link || '').toLowerCase()
      const cat = (bm.category || bm.group || '').toLowerCase()
      return title.includes(q) || url.includes(q) || cat.includes(q)
    })
  }
  return list
})

function catLabel(cat: string): string {
  return CAT_LABELS[cat] || cat
}

function openBookmark(bm: any) {
  const url = bm.url || bm.link
  if (url) {
    window.open(url, '_blank')
  } else if (bm.path) {
    window.location.hash = '/files'
  }
}

async function removeBookmark(bm: any) {
  const id = bm.id || bm.url || bm.link
  if (id) await store.remove(id)
}

function showAddDialog() {
  form.value = { name: '', url: '', category: 'tool', icon: '' }
  addError.value = ''
  showDialog.value = true
  nextTick(() => nameInput.value?.focus())
}

function cancelAdd() {
  showDialog.value = false
  addError.value = ''
}

async function pasteUrl() {
  try {
    const text = await navigator.clipboard.readText()
    if (text && (text.startsWith('http://') || text.startsWith('https://'))) {
      form.value.url = text
      if (!form.value.name) {
        try { form.value.name = new URL(text).hostname } catch {}
      }
    }
  } catch {}
}

async function saveBookmark() {
  addError.value = ''
  if (!form.value.name.trim()) { addError.value = '请输入名称'; return }
  if (!form.value.url.trim()) { addError.value = '请输入 URL'; return }
  let url = form.value.url.trim()
  if (!url.startsWith('http://') && !url.startsWith('https://')) url = 'https://' + url
  const ok = await store.add({
    name: form.value.name.trim(),
    url,
    category: form.value.category,
  })
  if (!ok) { addError.value = '添加失败'; return }
  showDialog.value = false
  addError.value = ''
}
</script>

<style scoped>
.bookmark-toolbar {
  padding: 8px 12px;
  border-bottom: 1px solid var(--border);
  background: var(--bg-secondary);
  position: sticky;
  top: 0;
  z-index: 1;
}
.bookmark-actions {
  display: flex;
  gap: 6px;
}
.bookmark-search {
  flex: 1;
  padding: 8px 12px;
  border: 1px solid var(--border);
  border-radius: 6px;
  background: var(--bg);
  color: var(--fg);
  font-size: 13px;
  outline: none;
  box-sizing: border-box;
}
.bookmark-search:focus { border-color: var(--accent); }
.bookmark-search::placeholder { color: var(--fg-muted); }

.add-btn {
  padding: 8px 12px;
  background: var(--accent);
  color: var(--bg);
  border: none;
  border-radius: 6px;
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
  white-space: nowrap;
  flex-shrink: 0;
}

.bookmark-categories {
  display: flex;
  gap: 6px;
  margin-top: 8px;
  overflow-x: auto;
  flex-wrap: nowrap;
  -webkit-overflow-scrolling: touch;
}
.cat-btn {
  flex-shrink: 0;
  padding: 3px 10px;
  border: 1px solid var(--border);
  border-radius: 12px;
  font-size: 12px;
  color: var(--fg-muted);
  cursor: pointer;
  transition: all 0.15s;
  user-select: none;
}
.cat-btn:hover { border-color: var(--accent); color: var(--fg); }
.cat-btn.active { background: var(--accent); color: var(--bg); border-color: var(--accent); }

.bookmark-list {
  padding: 4px 12px;
}
.bookmark-item {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px 12px;
  border-bottom: 1px solid var(--border);
  cursor: pointer;
  transition: background 0.15s;
  position: relative;
}
.bookmark-item:hover { background: rgba(255, 255, 255, 0.04); }

.bookmark-icon { font-size: 18px; flex-shrink: 0; }
.bookmark-info { flex: 1; min-width: 0; }
.bookmark-title {
  display: block;
  font-size: 14px;
  color: var(--fg);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.bookmark-path {
  display: block;
  font-size: 11px;
  color: var(--fg-muted);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  margin-top: 2px;
}
.bookmark-cat-tag {
  flex-shrink: 0;
  font-size: 10px;
  padding: 2px 6px;
  border-radius: 8px;
  background: rgba(122, 162, 247, 0.1);
  color: var(--accent);
  white-space: nowrap;
}

.bm-remove {
  width: 20px;
  height: 20px;
  border: none;
  background: none;
  color: var(--fg-muted);
  font-size: 12px;
  cursor: pointer;
  border-radius: 4px;
  flex-shrink: 0;
  display: none;
}
.bookmark-item:hover .bm-remove { display: flex; align-items: center; justify-content: center; }
.bm-remove:hover { background: var(--border); color: #e74c3c; }

.loading, .empty {
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 200px;
  color: var(--fg-muted);
  font-size: 14px;
}

.dialog-overlay { position: fixed; inset: 0; background: rgba(0,0,0,0.4); z-index: 1000; display: flex; align-items: center; justify-content: center; }
.dialog-box { background: var(--bg); border-radius: 12px; padding: 20px; width: 360px; max-width: 90vw; max-height: 80vh; overflow-y: auto; }
.dialog-title { font-size: 16px; font-weight: 700; margin: 0 0 16px; color: var(--fg); }
.form-row { margin-bottom: 12px; }
.form-input { width: 100%; padding: 8px 12px; border: 1px solid var(--border); border-radius: 8px; background: var(--bg-secondary); color: var(--fg); font-size: 13px; box-sizing: border-box; }
.form-input:focus { outline: none; border-color: var(--accent); }
.url-row { display: flex; gap: 4px; }
.paste-btn { padding: 8px; background: none; border: 1px solid var(--border); border-radius: 8px; cursor: pointer; font-size: 14px; }
.radio-row { display: flex; flex-wrap: wrap; gap: 8px; }
.radio-label { display: flex; align-items: center; gap: 4px; font-size: 13px; color: var(--fg); cursor: pointer; }
.error-msg { font-size: 12px; color: #e74c3c; margin: 4px 0; }
.dialog-actions { display: flex; gap: 8px; justify-content: flex-end; margin-top: 16px; }
.dialog-btn { padding: 8px 20px; border-radius: 8px; font-size: 14px; font-weight: 600; cursor: pointer; border: none; }
.dialog-btn.cancel { background: var(--bg-secondary); color: var(--fg); }
.dialog-btn.save { background: var(--accent); color: var(--bg); }
</style>

```



================================================
FILE: C:\Users\qu\Desktop\物理科学与技术论题\TS2\mcp\server\web\src\views\ChannelView.vue
================================================

``vue
<template>
  <div
    class="channel-view"
    @touchstart="onTouchStart"
    @touchmove="onTouchMove"
    @touchend="onTouchEnd"
    :style="{ transform: swipeOffset > 0 ? `translateY(${swipeOffset}px)` : '', opacity: swipeOpacity, transition: swiping ? 'none' : 'transform 0.2s, opacity 0.2s' }"
  >
    <div v-if="loading" class="loading">加载频道...</div>
    <template v-else-if="channel">
      <div class="channel-header">
        <img :src="channel?.avatarUrl" :alt="channel.name" class="channel-avatar" loading="lazy" @error="hideOnError" />
        <div class="channel-info">
          <h1 class="channel-name">
            {{ channel.name || '(无名称)' }}
            <span v-if="channel.verified" class="verified-badge">✓</span>
          </h1>
          <p class="channel-meta">{{ fmtCount(channel.subscriberCount) }} 订阅者</p>
          <p v-if="channel.description" class="channel-desc" :class="{ expanded: descExpanded }" @click="descExpanded = !descExpanded">
            {{ channel.description }}
            <span v-if="!descExpanded && channel.description.length > 80" class="desc-more">...更多</span>
          </p>
          <div class="ch-actions">
            <button class="sub-btn" :class="{ subscribed: isSubscribed }" @click="toggleSub">
              {{ isSubscribed ? '已订阅' : '订阅' }}
            </button>
            <button
              v-if="isSubscribed"
              class="notif-btn"
              :class="{ enabled: notifEnabled }"
              @click="toggleNotif"
              :title="notifEnabled ? '通知已开启' : '通知已关闭'"
            >{{ notifEnabled ? '🔔' : '🔕' }}</button>
            <button v-if="tabItems.length > 0" class="play-all-btn" @click="playAllChannel">▶ 全部播放</button>
          </div>
        </div>
      </div>

      <div v-if="channel.tabs && channel.tabs.length > 0" class="channel-tabs">
        <button
          v-for="tab in channel.tabs"
          :key="tab.name"
          class="ch-tab"
          :class="{ active: activeTabName === tab.name }"
          @click="switchTab(tab)"
        >{{ tabLabel(tab.name) }}</button>
      </div>

      <div class="tab-content">
        <!-- 正在查看某个合集时显示合集内视频 -->
        <template v-if="viewingPlaylist">
          <div class="playlist-subheader">
            <button class="back-btn" @click="viewingPlaylist = null">← 返回</button>
            <img :src="viewingPlaylist.thumbnailUrl" class="pl-thumb-sm" loading="lazy" @error="hideOnError" />
            <div class="pl-info-sm">
              <strong>{{ viewingPlaylist.name }}</strong>
              <span class="pl-meta-sm">{{ viewingPlaylist.uploaderName }} · {{ viewingPlaylist.streamCount || 0 }} 视频</span>
            </div>
            <button class="action-btn-sm" @click="playAllPlaylistItems">▶ 全部播放</button>
          </div>
          <div class="grid">
            <VideoCard
              v-for="item in playlistItems"
              :key="item.url"
              :item="item"
              @cardClick="onVideoClick(item)"
            />
          </div>
          <div v-if="loadingMorePlaylist" class="loading">加载更多...</div>
          <div v-else-if="!playlistHasMore && playlistItems.length > 0" class="end-hint">已显示全部</div>
          <div v-else-if="playlistItems.length === 0" class="placeholder">合集为空</div>
          <div ref="plBottomSentinel" class="scroll-sentinel"></div>
        </template>

        <!-- 正常 tab 内容 -->
        <template v-else>
          <div class="grid">
            <VideoCard
              v-for="(item, i) in tabItems"
              :key="item.url"
              :item="item"
              @cardClick="onItemClick(item)"
              @touchstart.passive="onLongPressStart($event, item, i)"
              @touchend="onLongPressEnd"
              @touchmove="onLongPressEnd"
            />
          </div>
          <div v-if="tabLoading" class="loading">加载中...</div>
          <div v-else-if="!tabHasNext && tabItems.length > 0" class="end-hint">已显示全部</div>
          <div v-else-if="tabItems.length === 0 && !tabLoading" class="placeholder">该分类暂无内容</div>
          <div ref="scrollSentinel" class="scroll-sentinel"></div>
        </template>
      </div>
    </template>

    <div v-if="error" class="error-panel">
      <div class="error-header" @click="showRaw = !showRaw">
        <span class="err-icon">⚠️</span>
        <span>{{ error }}</span>
        <span class="err-toggle">{{ showRaw ? '▲' : '▼' }}</span>
      </div>
      <div v-if="showRaw" class="error-detail">
        <div class="diag-row" v-if="rawResult"><span class="diag-key">原生结果:</span><pre class="diag-pre">{{ JSON.stringify(rawResult, null, 2) }}</pre></div>
        <div class="diag-row" v-if="rawError"><span class="diag-key">原生错误:</span><pre class="diag-pre">{{ rawError }}</pre></div>
      </div>
    </div>

    <Teleport to="body">
      <div v-if="itemMenu.show" class="item-menu" :style="{ top: itemMenu.y + 'px', left: itemMenu.x + 'px' }" @click.stop @touchend.prevent.stop>
        <div class="item-menu-item" @click="playFromHere">▶ 从此处播放</div>
        <div class="item-menu-item" @click="enqueueFromHere">📋 从此处加入队列</div>
        <div class="item-menu-item" @click="itemMenu.show = false">取消</div>
      </div>
    </Teleport>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, onUnmounted, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useSubscriptionsStore } from '../stores/subscriptions'
import { usePlayQueueStore } from '../stores/playQueue'
import PipePipe, { extractNextPage } from '../plugins/bridge'
import type { ChannelInfoResult, ChannelTabInfoResult, StreamInfoItem, Page } from '../plugins/bridge'
import VideoCard from '../components/VideoCard.vue'

const route = useRoute()
const router = useRouter()
const subStore = useSubscriptionsStore()
const queueStore = usePlayQueueStore()

const channel = ref<ChannelInfoResult | null>(null)
const loading = ref(true)
const error = ref('')
const channelUrl = ref('')
const serviceId = ref(-1)
const isSubscribed = ref(false)
const notifEnabled = ref(false)
const descExpanded = ref(false)
const showRaw = ref(false)
const rawResult = ref<any>(null)
const rawError = ref<string | null>(null)

const activeTabName = ref('videos')
const activeTabUrl = ref('')
const scrollSentinel = ref<HTMLElement | null>(null)

const tabItems = ref<StreamInfoItem[]>([])
const tabLoading = ref(false)
const tabLoadingMore = ref(false)
const tabError = ref('')
const tabNextPage = ref<Page | null>(null)
const tabHasNext = ref(false)

const itemMenu = ref<{ show: boolean; x: number; y: number; item: StreamInfoItem | null; index: number }>({ show: false, x: 0, y: 0, item: null, index: -1 })

let observer: IntersectionObserver | null = null
const swipeStartY = ref(0)
const swipeOffset = ref(0)
const swipeOpacity = ref(1)
const swiping = ref(false)
let _swipeAnimFrame: number | null = null

function hideOnError(e: Event) {
  const el = e.target as HTMLElement
  el.style.display = 'none'
}

onMounted(async () => {
  const url = route.query.url as string
  if (!url) { error.value = '缺少频道 URL'; loading.value = false; return }
  channelUrl.value = url
  isSubscribed.value = subStore.isSubscribed(url)
  notifEnabled.value = subStore.getNotif(url)
  try { const r = await PipePipe.resolveUrl({ url }); serviceId.value = r.serviceId } catch {}
  if (serviceId.value < 0) { error.value = '无法解析 serviceId: ' + url; loading.value = false; return }
  
  try {
    const result = await PipePipe.getChannelTabs({ url, serviceId: serviceId.value })
    rawResult.value = result
    channel.value = result
    subStore.updateInfo(url, {
      name: result.name,
      avatarUrl: result.avatarUrl,
      subscriberCount: result.subscriberCount,
      description: result.description,
    })

    if (!result.name && !result.avatarUrl && (!result.items || result.items.length === 0)) {
      error.value = '频道数据为空 (tabs=' + (result.tabs?.length || 0) + ', items=' + (result.items?.length || 0) + ')'
      loading.value = false
      return
    }

    if (result.tabs && result.tabs.length > 0) {
      const firstTab = result.tabs[0]
      activeTabName.value = firstTab.name
      activeTabUrl.value = firstTab.url
      try {
        await loadTab(firstTab.url)
        if (tabError.value) {
          tabItems.value = result.items || []
          tabHasNext.value = !!result._hasNextPage
          error.value = 'Tab加载失败(' + tabError.value + ')，已回退到频道默认列表'
        }
      } catch (e: any) {
        tabItems.value = result.items || []
        tabHasNext.value = !!result._hasNextPage
        error.value = 'Tab加载失败(' + (e.message || e) + ')，已回退到频道默认列表'
      }
    } else {
      tabItems.value = result.items || []
      tabHasNext.value = !!result._hasNextPage
    }
  } catch (e: any) {
    error.value = '加载频道失败: ' + (e.message || e)
    rawError.value = e.stack || e.toString()
  } finally {
    loading.value = false
  }
  
  if (typeof IntersectionObserver !== 'undefined') {
    observer = new IntersectionObserver((entries) => {
      if (entries[0]?.isIntersecting && tabHasNext.value && !tabLoadingMore.value) loadMoreTab()
    }, { rootMargin: '200px' })
  }
})

watch(scrollSentinel, (el) => {
  if (observer && el) { observer.disconnect(); observer.observe(el) }
})

onUnmounted(() => { observer?.disconnect() })

function tabLabel(name: string): string {
  const map: Record<string, string> = {
    videos: '视频', playlists: '播放列表', channels: '频道',
    articles: '专栏', about: '关于',
  }
  return map[name] || name
}

async function switchTab(tab: ChannelTabInfoResult) {
  if (activeTabName.value === tab.name) return
  activeTabName.value = tab.name
  activeTabUrl.value = tab.url
  await loadTab(tab.url)
  if (tabError.value && channel.value) {
    tabItems.value = channel.value.items || []
    tabHasNext.value = !!channel.value._hasNextPage
  }
}

async function loadTab(tabUrl: string) {
  tabLoading.value = true; tabError.value = ''
  try {
    const r = await PipePipe.getChannelTabPage({ tabUrl, serviceId: serviceId.value })
    tabItems.value = r.items || []
    tabNextPage.value = extractNextPage(r)
    tabHasNext.value = !!r._hasNextPage
  } catch (e: any) {
    tabError.value = 'Tab加载失败: ' + (e.message || e)
    if (channel.value) { tabItems.value = channel.value.items || []; tabHasNext.value = !!channel.value._hasNextPage }
  }
  finally { tabLoading.value = false }
}

async function loadMoreTab() {
  if (tabLoadingMore.value || !tabHasNext.value || !tabNextPage.value) return
  tabLoadingMore.value = true
  try {
    const isVideos = activeTabName.value === 'videos'
    const opts: any = { serviceId: serviceId.value, page: tabNextPage.value }
    const r = isVideos
      ? await PipePipe.getMoreChannelItems({ ...opts, url: channelUrl.value })
      : await PipePipe.getChannelTabPage({ ...opts, tabUrl: activeTabUrl.value, tabName: activeTabName.value })
    const existing = new Set(tabItems.value.map(i => i.url))
    for (const item of (r.items || [])) { if (!existing.has(item.url)) tabItems.value.push(item) }
    tabNextPage.value = extractNextPage(r)
    tabHasNext.value = !!r._hasNextPage
  } catch (e: any) { tabError.value = '加载更多失败: ' + (e.message || e) }
  finally { tabLoadingMore.value = false }
}

function playAllChannel() {
  if (!tabItems.value.length) return
  queueStore.replaceWith(tabItems.value.map(item => ({ url: item.url, title: item.name, thumbnailUrl: item.thumbnailUrl, duration: item.duration || 0, uploaderName: item.uploaderName || '' })))
  router.push({ name: 'video-player', query: { url: tabItems.value[0].url } })
}

let _longPressTimer: ReturnType<typeof setTimeout> | null = null

function onLongPressStart(e: TouchEvent, item: StreamInfoItem, index: number) {
  _longPressTimer = setTimeout(() => {
    _longPressTimer = null
    const touch = e.touches[0]
    itemMenu.value = { show: true, x: touch.clientX, y: touch.clientY, item, index }
    const close = (ev: Event) => {
      if (!(ev.target as HTMLElement)?.closest?.('.item-menu')) {
        itemMenu.value.show = false
        document.removeEventListener('click', close)
        document.removeEventListener('touchend', close)
      }
    }
    setTimeout(() => {
      document.addEventListener('click', close)
      document.addEventListener('touchend', close)
    }, 0)
  }, 500)
}

function onLongPressEnd() {
  if (_longPressTimer) {
    clearTimeout(_longPressTimer)
    _longPressTimer = null
  }
}

function playFromHere() {
  if (!itemMenu.value.item) return
  const idx = itemMenu.value.index
  const itemsFrom = tabItems.value.slice(idx)
  queueStore.replaceWith(itemsFrom.map(item => ({
    url: item.url, title: item.name, thumbnailUrl: item.thumbnailUrl,
    duration: item.duration || 0, uploaderName: item.uploaderName || '',
  })))
  itemMenu.value.show = false
  router.push({ name: 'video-player', query: { url: itemMenu.value.item.url } })
}

function enqueueFromHere() {
  if (!itemMenu.value.item) return
  const idx = itemMenu.value.index
  const itemsFrom = tabItems.value.slice(idx)
  for (const item of itemsFrom) {
    queueStore.add({ url: item.url, title: item.name, thumbnailUrl: item.thumbnailUrl,
      duration: item.duration || 0, uploaderName: item.uploaderName || '' })
  }
  itemMenu.value.show = false
}

function onTouchStart(e: TouchEvent) {
  swipeStartY.value = e.touches[0].clientY
  swipeOffset.value = 0
  swipeOpacity.value = 1
  swiping.value = true
}

function onTouchMove(e: TouchEvent) {
  if (!swiping.value) return
  const dy = e.touches[0].clientY - swipeStartY.value
  if (dy > 0) {
    _swipeAnimFrame && cancelAnimationFrame(_swipeAnimFrame)
    _swipeAnimFrame = requestAnimationFrame(() => {
      swipeOffset.value = dy * 0.6
      swipeOpacity.value = Math.max(0.4, 1 - dy / 500)
    })
  }
}

function onTouchEnd(e: TouchEvent) {
  swiping.value = false
  const dy = e.changedTouches[0].clientY - swipeStartY.value
  swipeOffset.value = 0
  swipeOpacity.value = 1
  if (dy > 150) {
    router.back()
  }
}

async function toggleSub() {
  if (isSubscribed.value) {
    subStore.unsubscribe(channelUrl.value)
    isSubscribed.value = false
    notifEnabled.value = false
  } else if (channel.value) {
    let serviceId = subStore.guessServiceId(channelUrl.value)
    try { const resolved = await PipePipe.resolveUrl({ url: channelUrl.value }); serviceId = resolved.serviceId } catch {}
    subStore.subscribe({
      url: channelUrl.value,
      name: channel.value.name || '',
      avatarUrl: channel.value.avatarUrl || '',
      subscriberCount: channel.value.subscriberCount || 0,
      description: channel.value.description || '',
      serviceId,
      notifEnabled: false,
    })
    isSubscribed.value = true
  }
}

function toggleNotif() {
  notifEnabled.value = !notifEnabled.value
  subStore.setNotif(channelUrl.value, notifEnabled.value)
}

function onItemClick(item: StreamInfoItem) {
  if (item.type === 'channel') {
    router.push({ name: 'channel', query: { url: item.url || item.uploaderUrl } })
  } else if (item.type === 'playlist') {
    openPlaylist(item)
  } else {
    router.push({ name: 'video-player', query: { url: item.url } })
  }
}

function onVideoClick(item: StreamInfoItem) {
  if (item.type === 'channel') {
    router.push({ name: 'channel', query: { url: item.url || item.uploaderUrl } })
  } else {
    router.push({ name: 'video-player', query: { url: item.url } })
  }
}

const viewingPlaylist = ref<StreamInfoItem | null>(null)
const playlistItems = ref<StreamInfoItem[]>([])
const loadingMorePlaylist = ref(false)
const playlistHasMore = ref(false)
const playlistNextPage = ref<Page | null>(null)
const plBottomSentinel = ref<HTMLElement | null>(null)
let plBottomObserver: IntersectionObserver | null = null

async function openPlaylist(item: StreamInfoItem) {
  viewingPlaylist.value = item
  playlistItems.value = []
  playlistHasMore.value = false
  playlistNextPage.value = null
  try {
    const res = await PipePipe.getPlaylistInfo({ url: item.url, serviceId: serviceId.value })
    playlistItems.value = res.items || []
    playlistHasMore.value = !!res._hasNextPage
    playlistNextPage.value = extractNextPage(res)
  } catch {}
  setupPlaylistScroll()
}

async function loadMorePlaylistItems() {
  if (loadingMorePlaylist.value || !playlistHasMore.value || !playlistNextPage.value) return
  loadingMorePlaylist.value = true
  try {
    const res = await PipePipe.getMorePlaylistItems({ url: viewingPlaylist.value!.url, page: playlistNextPage.value, serviceId: serviceId.value })
    const existingUrls = new Set(playlistItems.value.map(i => i.url))
    for (const item of (res.items || [])) {
      if (!existingUrls.has(item.url)) {
        playlistItems.value.push(item)
        existingUrls.add(item.url)
      }
    }
    playlistHasMore.value = !!res._hasNextPage
    playlistNextPage.value = extractNextPage(res)
  } catch {}
  finally { loadingMorePlaylist.value = false }
}

function setupPlaylistScroll() {
  plBottomObserver?.disconnect()
  if (typeof IntersectionObserver === 'undefined') return
  plBottomObserver = new IntersectionObserver((entries) => {
    if (entries[0]?.isIntersecting && playlistHasMore.value && !loadingMorePlaylist.value) {
      loadMorePlaylistItems()
    }
  }, { rootMargin: '200px' })
  watch(plBottomSentinel, (el) => {
    if (plBottomObserver && el) { plBottomObserver.disconnect(); plBottomObserver.observe(el) }
  }, { immediate: true })
}

function playAllPlaylistItems() {
  if (!playlistItems.value.length) return
  queueStore.replaceWith(playlistItems.value.map(item => ({
    url: item.url, title: item.name, thumbnailUrl: item.thumbnailUrl,
    duration: item.duration || 0, uploaderName: item.uploaderName || '',
  })))
  router.push({ name: 'video-player', query: { url: playlistItems.value[0].url } })
}

function fmtCount(n: number): string {
  if (!n || n < 0) return '未知'
  if (n >= 10000) return (n / 10000).toFixed(1) + '万'
  if (n >= 1000) return (n / 1000).toFixed(1) + 'k'
  return String(n)
}
</script>

<style scoped>
.channel-view { display: flex; flex-direction: column; height: 100%; overflow: hidden; }
.loading { text-align: center; padding: 48px; color: var(--fg-muted); }
.channel-header { display: flex; gap: 16px; align-items: flex-start; padding: 16px; border-bottom: 1px solid var(--border); flex-shrink: 0; }
.channel-avatar { width: 80px; height: 80px; border-radius: 50%; object-fit: cover; background: var(--border); flex-shrink: 0; }
.channel-info { flex: 1; min-width: 0; }
.channel-name { font-size: 22px; font-weight: 700; margin: 0 0 4px; color: var(--fg); display: flex; align-items: center; gap: 6px; }
.verified-badge { font-size: 14px; color: var(--accent); }
.channel-meta { font-size: 13px; color: var(--fg-muted); margin: 0 0 8px; }
.channel-desc { font-size: 13px; color: var(--fg-muted); line-height: 1.5; margin: 0 0 12px; white-space: pre-wrap; max-height: 80px; overflow: hidden; cursor: pointer; }
.channel-desc.expanded { max-height: none; }
.desc-more { color: var(--accent); font-size: 12px; }
.ch-actions { display: flex; gap: 6px; flex-wrap: wrap; align-items: center; }
.sub-btn { padding: 6px 16px; font-size: 13px; border-radius: 6px; border: 1px solid var(--accent); background: none; color: var(--accent); cursor: pointer; font-weight: 600; }
.sub-btn.subscribed { background: var(--accent); color: var(--bg); }
.notif-btn { background: none; border: 1px solid var(--border); border-radius: 6px; cursor: pointer; font-size: 16px; padding: 4px 8px; }
.notif-btn.enabled { border-color: var(--accent); }
.play-all-btn { padding: 6px 14px; font-size: 12px; border-radius: 6px; border: 1px solid var(--border); background: var(--bg-secondary); color: var(--fg); cursor: pointer; }
.play-all-btn:hover { border-color: var(--accent); color: var(--accent); }

.channel-tabs { display: flex; border-bottom: 1px solid var(--border); flex-shrink: 0; overflow-x: auto; }
.ch-tab { padding: 10px 16px; background: none; border: none; color: var(--fg-muted); font-size: 13px; font-weight: 600; cursor: pointer; border-bottom: 2px solid transparent; white-space: nowrap; }
.ch-tab.active { color: var(--accent); border-bottom-color: var(--accent); }

.tab-content { flex: 1; overflow-y: auto; padding: 12px; }
.grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(180px, 1fr)); gap: 12px; }
.placeholder, .end-hint { text-align: center; padding: 32px; color: var(--fg-muted); font-size: 14px; }
.scroll-sentinel { height: 1px; }

.error-panel { border: 1px solid #e74c3c; background: rgba(231,76,60,0.08); border-radius: 8px; margin: 8px; overflow: hidden; flex-shrink: 0; }
.error-header { display: flex; align-items: center; gap: 8px; padding: 10px 12px; cursor: pointer; color: #e74c3c; font-size: 13px; font-weight: 600; }
.err-icon { font-size: 16px; }
.err-toggle { margin-left: auto; font-size: 12px; }
.error-detail { padding: 8px 12px 12px; }
.diag-row { margin-bottom: 8px; word-break: break-all; }
.diag-key { font-size: 11px; font-weight: 600; color: var(--fg-muted); display: block; margin-bottom: 2px; }
.diag-pre { font-size: 11px; background: rgba(0,0,0,0.2); padding: 8px; border-radius: 4px; max-height: 200px; overflow: auto; white-space: pre-wrap; word-break: break-all; margin: 0; }

.item-menu { position: fixed; z-index: 9999; background: var(--bg); border: 1px solid var(--border); border-radius: 8px; box-shadow: 0 4px 16px rgba(0,0,0,0.3); padding: 4px 0; min-width: 160px; }
.item-menu-item { padding: 10px 16px; font-size: 13px; color: var(--fg); cursor: pointer; white-space: nowrap; }
.item-menu-item:hover { background: var(--border); }
.item-menu-item:first-child { border-radius: 8px 8px 0 0; }
.item-menu-item:last-child { border-radius: 0 0 8px 8px; border-top: 1px solid var(--border); color: var(--fg-muted); }

.playlist-subheader { display: flex; gap: 8px; align-items: center; padding: 8px 0; border-bottom: 1px solid var(--border); margin-bottom: 12px; }
.back-btn { padding: 4px 10px; font-size: 12px; border-radius: 4px; border: 1px solid var(--border); background: var(--bg-secondary); color: var(--fg); cursor: pointer; }
.pl-thumb-sm { width: 40px; height: 24px; object-fit: cover; border-radius: 3px; background: var(--border); flex-shrink: 0; }
.pl-info-sm { flex: 1; min-width: 0; }
.pl-info-sm strong { font-size: 12px; color: var(--fg); display: block; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.pl-meta-sm { font-size: 11px; color: var(--fg-muted); }
.action-btn-sm { padding: 4px 10px; font-size: 11px; border-radius: 4px; border: 1px solid var(--accent); background: none; color: var(--accent); cursor: pointer; white-space: nowrap; }
</style>

``



================================================
FILE: C:\Users\qu\Desktop\物理科学与技术论题\TS2\mcp\server\web\src\views\CoursesView.vue
================================================

```vue
<template>
  <div class="view">
    <header class="view-header">
      <h1>课程表</h1>
    </header>
    <div class="courses-layout">
      <div class="courses-layout__list">
        <div v-if="loading" class="courses-layout__empty">加载中...</div>
        <div v-else-if="courses.length === 0" class="courses-layout__empty">暂无课程</div>
        <CourseCard
          v-for="course in courses"
          :key="course.note_id"
          :course="course"
          :progress="progressMap[course.note_id] ?? {}"
          :active="selectedCourseId === course.note_id"
          @select="selectCourse"
        />
      </div>
      <div class="courses-layout__detail">
        <div v-if="!selectedCourse" class="courses-layout__empty">请选择一门课程</div>
        <template v-else>
          <div class="courses-layout__detail-header">
            <h2>{{ selectedCourse.course_title }}</h2>
            <span class="courses-layout__detail-hours">{{ selectedCourse.total_hours }} 学时</span>
          </div>
          <LessonTimeline
            :lessons="selectedCourse.lessons"
            :sections="selectedCourse.sections"
            :course-id="selectedCourse.note_id"
            :progress="progressMap[selectedCourse.note_id] ?? {}"
            @status-changed="refreshProgress"
          />
        </template>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { getCourses, getCourseProgress } from '../api'
import CourseCard from '../components/CourseCard.vue'
import LessonTimeline from '../components/LessonTimeline.vue'

interface CourseData {
  filename: string
  note_id: string
  course_title: string
  total_hours: number
  sections: Array<{ section_number: number; section_title: string; section_hours: number; lesson_range: string }>
  lessons: Array<{ lesson_number: number; lesson_title: string; section: number; description: string; central_question: string; references: string[]; estimated_hours: number }>
}

const courses = ref<CourseData[]>([])
const loading = ref(false)
const selectedCourseId = ref<string | null>(null)
const progressMap = ref<Record<string, Record<string, { status: string; updated_at: string }>>>({})

const selectedCourse = ref<CourseData | null>(null)

onMounted(async () => {
  // 优先从 bootstrap 缓存加载
  const bootstrap = (window as any).__TS2_BOOTSTRAP__
  if (bootstrap?.courses) {
    const apiData = bootstrap.courses
    courses.value = apiData?.courses ?? (Array.isArray(apiData) ? apiData : [])
    delete bootstrap.courses
  }
  // 后台刷新
  loading.value = true
  try {
    const res = await getCourses()
    const apiData = res.data?.data ?? res.data
    courses.value = apiData?.courses ?? (Array.isArray(apiData) ? apiData : [])
  } finally {
    loading.value = false
  }
})

async function selectCourse(course: CourseData) {
  selectedCourseId.value = course.note_id
  selectedCourse.value = course
  await loadProgress(course.note_id)
}

async function loadProgress(courseId: string) {
  try {
    const res = await getCourseProgress(courseId)
    const apiData = res.data?.data ?? res.data
    progressMap.value[courseId] = apiData?.lessons ?? {}
  } catch {
    progressMap.value[courseId] = {}
  }
}

async function refreshProgress() {
  if (selectedCourseId.value) {
    await loadProgress(selectedCourseId.value)
  }
}
</script>

<style scoped>
.courses-layout {
  display: flex;
  flex: 1;
  min-height: 0;
  padding: 12px;
  gap: 12px;
}

.courses-layout__list {
  width: 320px;
  flex-shrink: 0;
  display: flex;
  flex-direction: column;
  gap: 10px;
  overflow-y: auto;
  padding-right: 4px;
}

.courses-layout__detail {
  flex: 1;
  min-width: 0;
  overflow-y: auto;
  padding: 16px;
  background: var(--card);
  border-radius: 10px;
  border: 1px solid var(--border);
}

.courses-layout__detail-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 20px;
  padding-bottom: 12px;
  border-bottom: 1px solid var(--border);
}

.courses-layout__detail-header h2 {
  font-size: 18px;
  font-weight: 600;
  color: var(--fg);
}

.courses-layout__detail-hours {
  font-size: 13px;
  color: var(--fg-muted);
  background: var(--bg);
  padding: 4px 10px;
  border-radius: 10px;
}

.courses-layout__empty {
  display: flex;
  align-items: center;
  justify-content: center;
  height: 100%;
  min-height: 120px;
  color: var(--fg-muted);
  font-size: 14px;
}

@media (max-width: 768px) {
  .courses-layout {
    flex-direction: column;
  }

  .courses-layout__list {
    width: 100%;
    max-height: 240px;
    flex-shrink: 0;
  }

  .courses-layout__detail {
    flex: 1;
  }
}
</style>

```



================================================
FILE: C:\Users\qu\Desktop\物理科学与技术论题\TS2\mcp\server\web\src\views\EcosystemView.vue
================================================

```vue
<template>
  <div class="ecosystem-view">
    <div class="left-col">
      <EcoRecordPanel />
      <EcoThreadPanel style="margin-top: 12px;" />
    </div>
    <div class="right-col">
      <EcoWorldMap />
    </div>
  </div>
</template>

<script setup lang="ts">
import EcoRecordPanel from '../components/EcoRecordPanel.vue'
import EcoThreadPanel from '../components/EcoThreadPanel.vue'
import EcoWorldMap from '../components/EcoWorldMap.vue'
</script>

<style scoped>
.ecosystem-view {
  display: grid; grid-template-columns: 340px 1fr; gap: 12px;
  padding: 12px; height: 100%; box-sizing: border-box; overflow: auto;
}
.left-col { display: flex; flex-direction: column; }
.right-col { min-width: 0; }
</style>

```



================================================
FILE: C:\Users\qu\Desktop\物理科学与技术论题\TS2\mcp\server\web\src\views\EditorView.vue
================================================

```vue
<template>
  <div class="view editor-view-root">
    <div class="editor-header">
      <button class="btn-back" @click="goBack">← 返回</button>
      <span class="editor-path">{{ filePath }}</span>
      <span v-if="dirty" class="edit-modified">●</span>
      <div class="header-spacer"></div>
      <button class="btn-save" @click="saveFile" :disabled="saving || !dirty">
        {{ saving ? '保存中...' : '保存' }}
      </button>
    </div>
    <div v-if="loading" class="loading-editor">加载中...</div>
    <div v-else-if="error" class="error-editor">{{ error }}</div>
    <template v-else>
      <div v-if="!useTextarea" ref="vditorRef" class="vditor-container"></div>
      <textarea
        v-else
        ref="textareaRef"
        class="fallback-textarea"
        @input="dirty = true"
      ></textarea>
    </template>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, onUnmounted, nextTick } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { getFile, putFile } from '../api'
import { loadAutocompleteConfig, buildHintExtends } from '../autocomplete'

const route = useRoute()
const router = useRouter()

const filePath = ref('')
const loading = ref(true)
const error = ref('')
const saving = ref(false)
const dirty = ref(false)
const vditorRef = ref<HTMLDivElement | null>(null)
const textareaRef = ref<HTMLTextAreaElement | null>(null)
const useTextarea = ref(false)

let vditorInstance: any = null
let originalContent = ''
let _vditorLoaded: 'local' | 'cdn' | null = null
const VDITOR_CDN = 'https://unpkg.com/vditor'

async function loadVditor(): Promise<any> {
  if ((window as any).Vditor) return (window as any).Vditor

  // 1. 本地动态导入
  try {
    const mod = await import('vditor')
    await import('vditor/dist/index.css')
    _vditorLoaded = 'local'
    return mod.default
  } catch (e) {
    console.warn('Vditor 本地导入失败，尝试 CDN:', e)
  }

  // 2. CDN 降级
  try {
    await new Promise<void>((resolve, reject) => {
      const link = document.createElement('link')
      link.rel = 'stylesheet'
      link.href = VDITOR_CDN + '/dist/index.css'
      document.head.appendChild(link)
      const script = document.createElement('script')
      script.src = VDITOR_CDN + '/dist/index.min.js'
      script.onload = () => resolve()
      script.onerror = () => reject(new Error('CDN JS load failed'))
      document.head.appendChild(script)
    })
    _vditorLoaded = 'cdn'
    return (window as any).Vditor
  } catch (e) {
    console.warn('Vditor CDN 加载失败，使用纯文本编辑:', e)
  }
  return null
}

async function resolveVditorCdn(): Promise<string> {
  return _vditorLoaded === 'cdn' ? VDITOR_CDN : import.meta.env.BASE_URL + 'vditor'
}

onMounted(async () => {
  const path = (route.params.path as string[])?.join('/') || ''
  if (!path) {
    error.value = '未指定文件路径'
    loading.value = false
    return
  }
  filePath.value = path

  try {
    const res = await getFile(path)
    const apiData = res.data?.data ?? res.data
    const content = apiData?.content ?? ''
    originalContent = content

    await nextTick()

    const Vditor = await loadVditor()
    if (Vditor && vditorRef.value) {
      const isTouch = 'ontouchstart' in window
      const acConfig = loadAutocompleteConfig()
      const currentTheme = document.documentElement.getAttribute('data-theme') || 'dark'
      const vditorCdn = await resolveVditorCdn()
      let vditorReady = false
      try {
        vditorInstance = new Vditor(vditorRef.value, {
          value: content,
          mode: 'ir',
          theme: currentTheme === 'light' ? 'classic' : 'dark',
          placeholder: '开始编辑...',
          cache: { enable: false },
          tab: '\t',
          cdn: vditorCdn,
          hint: {
            delay: 200,
            parse: false,
            extend: buildHintExtends(acConfig),
          },
          input: () => {
            if (vditorInstance) {
              dirty.value = vditorInstance.getValue() !== originalContent
            }
          },
          after: () => { vditorReady = true },
          toolbar: isTouch
            ? ['headings', 'bold', 'italic', 'strike', '|', 'quote', 'inline-code', '|', 'list', 'ordered-list', 'check', '|', 'undo', 'redo', '|', 'edit-mode', 'preview']
            : ['headings', 'bold', 'italic', 'strike', '|', 'quote', 'inline-code', 'code', '|', 'list', 'ordered-list', 'check', '|', 'link', 'table', '|', 'undo', 'redo', '|', 'edit-mode', 'preview', 'fullscreen'],
        })
        await new Promise<void>((resolve) => setTimeout(resolve, 6000))
        if (!vditorReady) {
          console.warn('Vditor 子资源加载超时，回退纯文本编辑')
          try { vditorInstance.destroy() } catch { /* ignore */ }
          vditorInstance = null
          useTextarea.value = true
          await nextTick()
          if (textareaRef.value) textareaRef.value.value = content
        }
      } catch (initErr) {
        console.warn('Vditor 初始化失败，回退纯文本编辑:', initErr)
        vditorInstance = null
        useTextarea.value = true
        await nextTick()
        if (textareaRef.value) textareaRef.value.value = content
      }
    } else {
      useTextarea.value = true
      await nextTick()
      if (textareaRef.value) textareaRef.value.value = content
    }
  } catch {
    error.value = '无法读取文件'
  } finally {
    loading.value = false
  }
})

onUnmounted(() => {
  if (vditorInstance) {
    try { vditorInstance.destroy() } catch { /* ignore */ }
    vditorInstance = null
  }
})

async function saveFile() {
  if (!filePath.value) return
  saving.value = true
  try {
    let content = ''
    if (useTextarea.value && textareaRef.value) {
      content = textareaRef.value.value
    } else if (vditorInstance) {
      content = vditorInstance.getValue()
    }
    await putFile(filePath.value, content)
    originalContent = content
    dirty.value = false
  } catch {
    alert('保存失败')
  } finally {
    saving.value = false
  }
}

function goBack() {
  if (dirty.value) {
    const action = confirm('文件已修改但未保存，是否保存？\n\n确定 = 保存并关闭\n取消 = 不保存直接关闭')
    if (action) {
      saveFile()
    }
  }
  if (vditorInstance) {
    try { vditorInstance.destroy() } catch { /* ignore */ }
    vditorInstance = null
  }
  if (window.history.length > 1) {
    router.back()
  } else {
    router.push('/files')
  }
}
</script>

<style scoped>
.editor-view-root {
  display: flex;
  flex-direction: column;
  height: 100%;
  overflow: hidden;
}

.editor-header {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 12px;
  background: var(--bg-secondary);
  border-bottom: 1px solid var(--border);
  flex-shrink: 0;
}

.editor-path {
  font-size: 12px;
  color: var(--fg-muted);
  font-family: monospace;
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.header-spacer {
  flex: 1;
}

.edit-modified {
  color: var(--accent);
  font-size: 16px;
}

.btn-back {
  background: none;
  border: 1px solid var(--border);
  color: var(--fg);
  font-size: 12px;
  padding: 4px 10px;
  border-radius: 6px;
  cursor: pointer;
  white-space: nowrap;
}

.btn-back:hover {
  background: var(--bg-tertiary);
}

.btn-save {
  padding: 6px 16px;
  background: var(--accent);
  color: var(--bg);
  border: none;
  border-radius: 6px;
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
  white-space: nowrap;
}

.btn-save:disabled {
  opacity: 0.5;
}

.vditor-container {
  flex: 1;
  min-height: 0;
}

.fallback-textarea {
  flex: 1;
  min-height: 0;
  width: 100%;
  padding: 12px;
  background: var(--bg);
  color: var(--fg);
  border: none;
  font-family: monospace;
  font-size: 13px;
  line-height: 1.6;
  resize: none;
  outline: none;
}

.loading-editor,
.error-editor {
  display: flex;
  align-items: center;
  justify-content: center;
  flex: 1;
  color: var(--fg-muted);
  font-size: 14px;
}
</style>

```



================================================
FILE: C:\Users\qu\Desktop\物理科学与技术论题\TS2\mcp\server\web\src\views\ExecutionView.vue
================================================

```vue
<template>
  <div class="view">
    <header class="view-header">
      <h1>课程执行</h1>
    </header>
    <div class="view-body exec-body">
      <div class="exec-selectors">
        <div class="exec-field">
          <label class="exec-field__label">选择课程</label>
          <select v-model="selectedCourseId" class="exec-field__select" @change="onCourseChange">
            <option value="">-- 请选择课程 --</option>
            <option v-for="course in courses" :key="course.note_id" :value="course.note_id">
              {{ course.course_title }}
            </option>
          </select>
        </div>
        <div class="exec-field">
          <label class="exec-field__label">选择课时</label>
          <select v-model="selectedLessonNum" class="exec-field__select" @change="onLessonChange">
            <option value="">-- 请选择课时 --</option>
            <option v-for="lesson in currentLessons" :key="lesson.lesson_number" :value="lesson.lesson_number">
              第{{ lesson.lesson_number }}课 - {{ lesson.lesson_title }}
            </option>
          </select>
        </div>
      </div>

      <div v-if="currentLesson" class="exec-lesson">
        <div class="exec-lesson__header">
          <h2 class="exec-lesson__title">{{ currentLesson.lesson_title }}</h2>
          <span class="exec-lesson__hours">{{ getSafeEstimatedHours(currentLesson) }} 学时</span>
        </div>

        <div v-if="currentLesson.central_question" class="exec-lesson__question">
          <span class="exec-lesson__question-label">核心问题</span>
          {{ currentLesson.central_question }}
        </div>

        <div v-if="currentLesson.description" class="exec-lesson__desc">
          {{ currentLesson.description }}
        </div>

        <div v-if="currentLesson.references?.length" class="exec-lesson__refs">
          <span class="exec-lesson__refs-label">参考资料</span>
          <ul>
            <li v-for="(ref, i) in currentLesson.references" :key="i">{{ ref }}</li>
          </ul>
        </div>

        <ExecTimer :duration="(currentLesson.estimated_hours || 0) * 60" />

        <button class="exec-lesson__complete" @click="completeLesson">
          完成课时
        </button>
      </div>

      <div v-else class="exec-lesson__empty">
        请选择课程和课时开始学习
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import { getCourses, getCourseProgress, updateLessonStatus } from '../api'
import ExecTimer from '../components/ExecTimer.vue'

interface LessonData {
  lesson_number: number
  lesson_title: string
  section: number
  description: string
  central_question: string
  references: string[]
  estimated_hours: number
}

interface CourseData {
  filename: string
  note_id: string
  course_title: string
  total_hours: number
  sections: Array<{ section_number: number; section_title: string; section_hours: number; lesson_range: string }>
  lessons: LessonData[]
}

// 安全获取课时学时
function getSafeEstimatedHours(lesson: LessonData): number {
  let val = lesson.estimated_hours
  if (val === null || val === undefined || val === '') {
    return 1
  }
  const num = Number(val)
  return Number.isFinite(num) && num >= 0 ? num : 1
}

const courses = ref<CourseData[]>([])
const selectedCourseId = ref('')
const selectedLessonNum = ref<number | string>('')
const progress = ref<Record<string, { status: string; updated_at: string }>>({})
const route = useRoute()

const currentCourse = computed(() => courses.value.find(c => c.note_id === selectedCourseId.value) ?? null)
const currentLessons = computed(() => currentCourse.value?.lessons ?? [])
const currentLesson = computed(() => {
  if (!selectedLessonNum.value) return null
  return currentLessons.value.find(l => l.lesson_number === Number(selectedLessonNum.value)) ?? null
})

onMounted(async () => {
  try {
    const res = await getCourses()
    const apiData = res.data?.data ?? res.data
    courses.value = apiData?.courses ?? (Array.isArray(apiData) ? apiData : [])
  } catch {
    courses.value = []
  }
  // 如果有 query 参数 course，自动选中对应课程
  const courseName = route.query.course as string | undefined
  if (courseName && courses.value.length > 0) {
    const match = courses.value.find(c => c.course_title === courseName || c.note_id === courseName)
    if (match) {
      selectedCourseId.value = match.note_id
      await onCourseChange()
    }
  }
})

async function onCourseChange() {
  selectedLessonNum.value = ''
  if (!selectedCourseId.value) return
  try {
    const res = await getCourseProgress(selectedCourseId.value)
    const apiData = res.data?.data ?? res.data
    progress.value = apiData?.lessons ?? {}
  } catch {
    progress.value = {}
  }
  autoSelectNextLesson()
}

function onLessonChange() {
  // lesson changed
}

function autoSelectNextLesson() {
  if (!currentCourse.value) return
  const lessons = currentCourse.value.lessons
  const next = lessons.find(l => progress.value[String(l.lesson_number)]?.status !== 'completed')
  if (next) {
    selectedLessonNum.value = next.lesson_number
  } else if (lessons.length > 0) {
    selectedLessonNum.value = lessons[0].lesson_number
  }
}

async function completeLesson() {
  if (!selectedCourseId.value || !selectedLessonNum.value) return
  await updateLessonStatus(selectedCourseId.value, Number(selectedLessonNum.value), 'completed')
  // refresh progress
  try {
    const res = await getCourseProgress(selectedCourseId.value)
    progress.value = res.data?.lessons ?? res.data ?? {}
  } catch {
    progress.value = {}
  }
  // auto advance to next lesson
  if (currentCourse.value) {
    const lessons = currentCourse.value.lessons
    const currentIdx = lessons.findIndex(l => l.lesson_number === Number(selectedLessonNum.value))
    // find next uncompleted after current
    let next = lessons.slice(currentIdx + 1).find(l => progress.value[String(l.lesson_number)]?.status !== 'completed')
    if (!next) {
      next = lessons.slice(0, currentIdx).find(l => progress.value[String(l.lesson_number)]?.status !== 'completed')
    }
    if (next) {
      selectedLessonNum.value = next.lesson_number
    }
  }
}
</script>

<style scoped>
.exec-body {
  max-width: 600px;
  margin: 0 auto;
}

.exec-selectors {
  display: flex;
  flex-direction: column;
  gap: 12px;
  margin-bottom: 20px;
}

.exec-field {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.exec-field__label {
  font-size: 13px;
  color: var(--fg-muted);
  font-weight: 500;
}

.exec-field__select {
  width: 100%;
  padding: 10px 12px;
  font-size: 14px;
}

.exec-lesson {
  background: var(--card);
  border: 1px solid var(--border);
  border-radius: 10px;
  padding: 20px;
}

.exec-lesson__header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 10px;
  margin-bottom: 16px;
}

.exec-lesson__title {
  font-size: 18px;
  font-weight: 600;
  color: var(--fg);
}

.exec-lesson__hours {
  font-size: 12px;
  color: var(--fg-muted);
  background: var(--bg);
  padding: 3px 10px;
  border-radius: 10px;
  white-space: nowrap;
}

.exec-lesson__question {
  background: rgba(122, 162, 247, 0.08);
  border-left: 3px solid var(--accent);
  padding: 10px 14px;
  border-radius: 0 8px 8px 0;
  margin-bottom: 14px;
  font-size: 14px;
  line-height: 1.6;
  color: var(--fg);
}

.exec-lesson__question-label {
  display: block;
  font-size: 11px;
  color: var(--accent);
  font-weight: 600;
  margin-bottom: 4px;
  text-transform: uppercase;
  letter-spacing: 1px;
}

.exec-lesson__desc {
  font-size: 14px;
  line-height: 1.7;
  color: var(--fg-muted);
  margin-bottom: 14px;
}

.exec-lesson__refs {
  margin-bottom: 16px;
}

.exec-lesson__refs-label {
  display: block;
  font-size: 12px;
  color: var(--fg-muted);
  font-weight: 600;
  margin-bottom: 6px;
}

.exec-lesson__refs ul {
  list-style: none;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.exec-lesson__refs li {
  font-size: 13px;
  color: var(--fg-muted);
  padding-left: 14px;
  position: relative;
}

.exec-lesson__refs li::before {
  content: '•';
  position: absolute;
  left: 0;
  color: var(--accent);
}

.exec-lesson__complete {
  width: 100%;
  padding: 12px;
  font-size: 15px;
  font-weight: 600;
  background: var(--success);
  color: var(--bg);
  border-radius: 8px;
  margin-top: 8px;
}

.exec-lesson__complete:hover {
  background: #b5e88c;
}

.exec-lesson__empty {
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 200px;
  color: var(--fg-muted);
  font-size: 14px;
}
</style>

```



================================================
FILE: C:\Users\qu\Desktop\物理科学与技术论题\TS2\mcp\server\web\src\views\FavoritesView.vue
================================================

``vue
<template>
  <div class="lpl-view">
    <div class="lpl-header">
      <h3 class="section-title">我的合集</h3>
      <button class="create-btn" @click="showCreateDialog = true">＋ 新建合集</button>
    </div>
    <div v-if="store.localPlaylists.length === 0 && store.remotePlaylists.length === 0 && store.favoritesItems.length === 0" class="placeholder">还没有任何合集或收藏的视频</div>

    <!-- 收藏视频 -->
    <div v-if="store.favoritesItems.length" class="remote-section">
      <h4 class="subsection-title">收藏视频 ({{ store.favoritesItems.length }})</h4>
      <div class="grid">
        <VideoCard v-for="item in store.favoritesItems" :key="item.url" :item="item" @cardClick="onVideoClick(item)" />
      </div>
    </div>

    <!-- 远程播放列表 -->
    <div v-if="store.remotePlaylists.length" class="remote-section">
      <h4 class="subsection-title">收藏的播放列表</h4>
      <div class="remote-list">
        <div v-for="pl in store.remotePlaylists" :key="pl.url" class="remote-item" @click="router.push({ name: 'video-player', query: { url: pl.url } })">
          <img :src="pl.thumbnailUrl" class="remote-thumb" loading="lazy" @error="hideThumb" />
          <div class="remote-info">
            <div class="remote-name">{{ pl.name }}</div>
            <div class="remote-meta">{{ pl.uploaderName }} · {{ pl.streamCount }} 视频</div>
          </div>
          <button class="remove-btn" @click.stop="store.unbookmarkRemote(pl.url)">✕</button>
        </div>
      </div>
    </div>
    <div v-for="pl in store.localPlaylists" :key="pl.id" class="lpl-card">
      <div class="lpl-title-row">
        <span class="lpl-name" @click="toggleExpand(pl.id)">{{ pl.name }}</span>
        <span class="lpl-count">{{ pl.items.length }} 个视频</span>
        <div class="lpl-actions">
          <button class="lpl-btn rename-btn" @click="startRename(pl)">✏️</button>
          <button class="lpl-btn" @click="playAll(pl)">▶ 全部播放</button>
          <button class="lpl-btn danger" @click="deletePlaylist(pl)">🗑</button>
        </div>
      </div>
      <template v-if="expanded[pl.id]">
        <div v-if="pl.items.length === 0" class="sub-placeholder">合集为空</div>
        <div v-else class="grid">
          <VideoCard v-for="item in pl.items" :key="item.url" :item="item" @cardClick="onVideoClick(item)" @addToPlaylist="e => store.addToLocalPlaylist(pl.id, e)" />
        </div>
      </template>
    </div>

    <!-- Create dialog -->
    <div v-if="showCreateDialog" class="dialog-overlay" @click.self="showCreateDialog = false">
      <div class="dialog-box">
        <h3 class="dialog-title">新建合集</h3>
        <input v-model="newName" class="form-input" placeholder="合集名称" ref="nameInput" @keyup.enter="createPlaylist" />
        <div class="dialog-actions">
          <button class="dialog-btn cancel" @click="showCreateDialog = false">取消</button>
          <button class="dialog-btn save" @click="createPlaylist" :disabled="!newName.trim()">创建</button>
        </div>
      </div>
    </div>

    <!-- Rename dialog -->
    <div v-if="renameTarget" class="dialog-overlay" @click.self="renameTarget = null">
      <div class="dialog-box">
        <h3 class="dialog-title">重命名合集</h3>
        <input v-model="renameName" class="form-input" placeholder="合集名称" @keyup.enter="doRename" />
        <div class="dialog-actions">
          <button class="dialog-btn cancel" @click="renameTarget = null">取消</button>
          <button class="dialog-btn save" @click="doRename">保存</button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, nextTick } from 'vue'
import { useRouter } from 'vue-router'
import { usePlaylistsStore } from '../stores/playlists'
import { usePlayQueueStore } from '../stores/playQueue'
import type { StreamInfoItem } from '../plugins/bridge'
import VideoCard from '../components/VideoCard.vue'

const router = useRouter()
const store = usePlaylistsStore()
const queueStore = usePlayQueueStore()

const expanded = ref<Record<string, boolean>>({})
const showCreateDialog = ref(false)
const newName = ref('')
const nameInput = ref<HTMLInputElement | null>(null)
const renameTarget = ref<{ id: string; name: string } | null>(null)
const renameName = ref('')

function hideThumb(e: Event) {
  const el = e.target as HTMLElement
  el.style.display = 'none'
}

function toggleExpand(id: string) { expanded.value[id] = !expanded.value[id] }

async function createPlaylist() {
  const name = newName.value.trim()
  if (!name) return
  store.createLocalPlaylist(name)
  newName.value = ''
  showCreateDialog.value = false
}

function startRename(pl: { id: string; name: string }) {
  renameTarget.value = pl
  renameName.value = pl.name
}

function doRename() {
  if (renameTarget.value && renameName.value.trim()) {
    store.renameLocalPlaylist(renameTarget.value.id, renameName.value.trim())
  }
  renameTarget.value = null
}

function deletePlaylist(pl: { id: string; name: string }) {
  if (confirm(`删除合集"${pl.name}"？`)) store.deleteLocalPlaylist(pl.id)
}

function playAll(pl: { id: string; items: StreamInfoItem[] }) {
  if (!pl.items.length) return
  queueStore.replaceWith(pl.items.map(item => ({ url: item.url, title: item.name, thumbnailUrl: item.thumbnailUrl, duration: item.duration || 0, uploaderName: item.uploaderName || '' })))
  router.push({ name: 'video-player', query: { url: pl.items[0].url } })
}

function onVideoClick(item: StreamInfoItem) {
  if (item.type === 'channel') router.push({ name: 'channel', query: { url: item.url || item.uploaderUrl } })
  else router.push({ name: 'video-player', query: { url: item.url } })
}
</script>

<style scoped>
.lpl-view { padding: 4px 12px; }
.lpl-header { display: flex; justify-content: space-between; align-items: center; padding: 8px 0; }
.create-btn { padding: 6px 14px; background: var(--accent); color: var(--bg); border: none; border-radius: 6px; font-size: 13px; font-weight: 600; cursor: pointer; }

.remote-section { margin-bottom: 12px; }
.subsection-title { font-size: 13px; font-weight: 600; color: var(--fg-muted); margin: 0 0 6px; }
.remote-list { display: flex; flex-direction: column; gap: 6px; }
.remote-item { display: flex; align-items: center; gap: 10px; padding: 8px; border-radius: 8px; border: 1px solid var(--border); cursor: pointer; }
.remote-item:hover { background: var(--bg-secondary); }
.remote-thumb { width: 40px; height: 40px; border-radius: 4px; object-fit: cover; flex-shrink: 0; background: var(--border); }
.remote-info { flex: 1; min-width: 0; }
.remote-name { font-size: 13px; color: var(--fg); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.remote-meta { font-size: 11px; color: var(--fg-muted); }
.remove-btn { width: 20px; height: 20px; border: none; background: none; color: var(--fg-muted); font-size: 12px; cursor: pointer; border-radius: 4px; flex-shrink: 0; }
.remote-item:hover .remove-btn { display: flex; align-items: center; justify-content: center; }
.remove-btn:hover { background: var(--border); color: #e74c3c; }

.lpl-card { border: 1px solid var(--border); border-radius: 8px; margin-bottom: 10px; overflow: hidden; }
.lpl-title-row { display: flex; align-items: center; gap: 8px; padding: 10px 12px; background: var(--bg-secondary); }
.lpl-name { font-size: 14px; font-weight: 600; color: var(--fg); cursor: pointer; flex: 1; }
.lpl-count { font-size: 11px; color: var(--fg-muted); white-space: nowrap; }
.lpl-actions { display: flex; gap: 4px; }
.lpl-btn { padding: 3px 8px; font-size: 11px; border: 1px solid var(--border); border-radius: 4px; background: var(--bg); color: var(--fg); cursor: pointer; }
.lpl-btn.danger { color: #e74c3c; }
.sub-placeholder { text-align: center; padding: 24px; color: var(--fg-muted); font-size: 13px; }
.grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(180px, 1fr)); gap: 12px; padding: 12px; }
.placeholder { text-align: center; padding: 48px; color: var(--fg-muted); font-size: 14px; }
.dialog-overlay { position: fixed; inset: 0; background: rgba(0,0,0,0.4); z-index: 1000; display: flex; align-items: center; justify-content: center; }
.dialog-box { background: var(--bg); border-radius: 12px; padding: 20px; width: 320px; }
.dialog-title { font-size: 16px; font-weight: 700; margin: 0 0 12px; color: var(--fg); }
.form-input { width: 100%; padding: 8px 12px; border: 1px solid var(--border); border-radius: 8px; background: var(--bg-secondary); color: var(--fg); font-size: 13px; box-sizing: border-box; }
.dialog-actions { display: flex; gap: 8px; justify-content: flex-end; margin-top: 16px; }
.dialog-btn { padding: 8px 20px; border-radius: 8px; font-size: 14px; font-weight: 600; cursor: pointer; border: none; }
.dialog-btn.cancel { background: var(--bg-secondary); color: var(--fg); }
.dialog-btn.save { background: var(--accent); color: var(--bg); }
</style>

``



================================================
FILE: C:\Users\qu\Desktop\物理科学与技术论题\TS2\mcp\server\web\src\views\FilesView.vue
================================================

``vue
<template>
  <div class="view">
    <header class="view-header">
      <h1>文件</h1>
      <div class="header-actions">
        <span class="ws-status" :class="{ connected: wsConnected }" :title="wsConnected ? '已连接' : '未连接'">●</span>
      </div>
    </header>
    <div class="view-body files-body">
      <!-- 文本编辑器（Vditor） -->
      <div v-if="editingFile" class="editor-view">
        <div class="editor-header">
          <button class="btn-back" @click="closeEditor">← 返回</button>
          <span class="editor-path">{{ editingFile }}</span>
          <span v-if="editModified" class="edit-modified">●</span>
        </div>
        <div v-if="!useTextarea" ref="vditorRef" class="vditor-container"></div>
        <template v-else>
          <div class="md-toolbar">
            <button @click="insertMd('**', '**')" title="粗体">B</button>
            <button @click="insertMd('*', '*')" title="斜体">I</button>
            <button @click="insertMd('## ', '')" title="标题">H</button>
            <button @click="insertMd('- ', '')" title="列表">-</button>
            <button @click="insertMd('1. ', '')" title="有序列表">1.</button>
            <button @click="insertMd('- [ ] ', '')" title="待办">☐</button>
            <button @click="insertMd('`', '`')" title="代码">code</button>
            <button @click="insertMd('[', '](url)')" title="链接">🔗</button>
          </div>
          <textarea
            ref="textareaRef"
            class="fallback-textarea"
            @input="editModified = true"
          ></textarea>
        </template>
        <div class="editor-actions">
          <button class="btn-save" @click="saveFile" :disabled="saving || !editModified">
            {{ saving ? '保存中...' : '保存' }}
          </button>
        </div>
      </div>

      <!-- Office 文档预览（docx/excel/pptx/pdf） -->
      <div v-else-if="previewFile" class="editor-view">
        <div class="editor-header">
          <button class="btn-back" @click="closePreview">← 返回</button>
          <span class="editor-path">{{ previewFile }}</span>
          <button v-if="previewType === 'pdf' && fileSource === 'server'" class="btn-ai-read" @click="openPdfReader" title="AI 智能阅读（建立索引、AI问答）">AI 阅读</button>
        </div>
        <div class="office-preview-container">
          <VueOfficeDocx v-if="previewType === 'docx'" :src="previewUrl" style="height:100%;width:100%" />
          <VueOfficeExcel v-else-if="previewType === 'xlsx'" :src="previewUrl" style="height:100%;width:100%" />
          <VueOfficePptx v-else-if="previewType === 'pptx'" :src="previewUrl" style="height:100%;width:100%" />
          <VueOfficePdf v-else-if="previewType === 'pdf'" :src="previewUrl" style="height:100%;width:100%" />
          <div v-else class="preview-error">不支持的文档格式</div>
        </div>
      </div>

      <!-- 文件浏览视图 -->
      <div v-else class="browser-view">

        <!-- 新建文件对话框 -->
        <div v-if="showNewFile" class="newfile-bar">
          <input
            v-model="newFileName"
            class="newfile-input"
            placeholder="文件名（如 note.md）"
            @keyup.enter="createFile"
            ref="newFileInputRef"
          />
          <button class="btn-newfile" @click="createFile" :disabled="creatingFile">创建</button>
          <button class="btn-newfile-cancel" @click="cancelNewFile">取消</button>
        </div>

        <!-- 搜索过滤框 -->
        <div class="search-bar">
          <input
            v-model="searchQuery"
            class="search-input"
            :placeholder="fileSource === 'local' ? '本地搜索...' : '搜索文件...'"
            @input="onSearchInput"
          />
          <button v-if="searchQuery" class="search-clear" @click="clearSearch">✕</button>
          <!-- 文件源切换 -->
          <div class="source-toggle">
            <button
              class="source-btn"
              :class="{ active: fileSource === 'server' }"
              @click="switchFileSource('server')"
            >服务端</button>
            <button
              class="source-btn"
              :class="{ active: fileSource === 'local' }"
              @click="switchFileSource('local')"
            >本地</button>
          </div>
        </div>

        <!-- 面包屑 -->
        <div class="breadcrumb">
          <div class="breadcrumb-links">
            <span class="breadcrumb-item" @click="navigateTo('')">根目录</span>
            <template v-for="(seg, idx) in pathSegments" :key="idx">
              <span class="breadcrumb-sep">/</span>
              <span
                class="breadcrumb-item"
                :class="{ active: idx === pathSegments.length - 1 }"
                @click="navigateTo(pathSegments.slice(0, idx + 1).join('/'))"
              >{{ seg }}</span>
            </template>
          </div>
          <button class="btn-newfile-breadcrumb" @click="startNewFile" :title="currentPath ? '在当前目录新建文件' : '请先进入子目录'" v-if="fileSource === 'server'">+ 新建</button>
          <template v-else>
            <button class="btn-newfile-breadcrumb" @click="doCreateLocalFile">+ 文件</button>
            <button class="btn-newfile-breadcrumb" @click="doCreateLocalDir">+ 目录</button>
            <button class="btn-newfile-breadcrumb" @click="doImportFromServer" :disabled="importExportBusy" title="从服务端导入当前目录">↓ 导入</button>
            <button class="btn-newfile-breadcrumb" @click="doExportToServer" :disabled="importExportBusy" title="导出当前目录到服务端">↑ 导出</button>
            <span v-if="importExportMsg" class="import-export-msg">{{ importExportMsg }}</span>
            <span class="local-stats" v-if="localStats.files > 0">{{ localStats.files }}文件 {{ formatSize(localStats.totalSize) }}</span>
          </template>
        </div>

        <!-- 目录列表 / 搜索结果 -->
        <div v-if="searching" class="loading-root">搜索中...</div>
        <div v-else-if="loading" class="loading-root">加载中...</div>
        <div v-else-if="filteredEntries.length === 0" class="empty-dir">{{ searchQuery ? '没有匹配的文件' : '空目录' }}</div>
        <div v-else class="entry-list">
          <!-- 返回上级（仅在非搜索模式下） -->
          <div v-if="!searchQuery && currentPath" class="entry-row entry-up" @click="goUp">
            <span class="entry-icon">📁</span>
            <span class="entry-name">..</span>
          </div>
          <div
            v-for="entry in filteredEntries"
            :key="entry.path || entry.name"
            class="entry-row"
            @click="handleEntryClick(entry)"
            @contextmenu.prevent="!entry.is_dir && showCtxMenu(entry, $event)"
          >
            <span class="entry-icon">{{ entry.is_dir ? '📁' : fileIcon(entry.ext) }}</span>
            <span class="entry-name" :class="{ 'is-dir': entry.is_dir }">{{ entry.name }}</span>
            <span v-if="searchQuery && !entry.is_dir" class="entry-path" :title="entry.path">{{ entry.path.includes('/') ? entry.path.substring(0, entry.path.lastIndexOf('/')) + '/' : '' }}</span>
            <span v-if="!entry.is_dir && entry.size" class="entry-size">{{ formatSize(entry.size) }}</span>
            <!-- 服务端模式：单文件导入到本地 -->
            <button v-if="fileSource === 'server' && !entry.is_dir" class="btn-import-single" @click.stop="importSingleFromServer(entry)" title="导入到本地">↓</button>
            <!-- 本地模式：单文件导出到服务端 -->
            <button v-if="fileSource === 'local' && !entry.is_dir" class="btn-export-single" @click.stop="exportSingleToServer(entry)" title="导出到服务端">↑</button>
            <button v-if="fileSource === 'local'" class="btn-delete-local" @click.stop="doDeleteLocal(entry)" title="删除">✕</button>
          </div>
        </div>

        <!-- 上传区域（仅服务端模式） -->
        <div
          v-if="fileSource === 'server'"
          class="upload-section"
          @dragenter.prevent="dragOver = true"
          @dragover.prevent="dragOver = true"
          @dragleave.prevent="dragOver = false"
          @drop.prevent="handleDrop"
          :class="{ 'drag-over': dragOver, 'uploading': uploading }"
        >
          <div class="upload-row">
            <label class="btn-upload">
              上传文件
              <input type="file" ref="fileInputRef" multiple @change="handleUpload" style="display:none" />
            </label>
            <label class="btn-upload btn-upload-folder">
              上传文件夹
              <input type="file" ref="folderInputRef" webkitdirectory @change="handleFolderUpload" style="display:none" />
            </label>
            <button class="btn-upload btn-cluster-import" @click="openClusterImport">从其他实例导入</button>
          </div>
          <div v-if="!uploading && !dragOver" class="upload-hint">拖拽文件到此处上传</div>
          <div v-if="dragOver && !uploading" class="upload-hint upload-hint-active">释放以上传文件</div>
          <div v-if="uploading" class="upload-progress-bar">
            <div class="upload-progress-fill" :style="{ width: uploadProgress + '%' }"></div>
            <span class="upload-progress-text">{{ uploadProgressText }}</span>
          </div>
        </div>
      </div>
    </div>

    <!-- 右键菜单 -->
    <div
      v-if="ctxMenu.visible"
      class="context-menu"
      :style="{ left: ctxMenu.x + 'px', top: ctxMenu.y + 'px' }"
      @click.stop
      @contextmenu.prevent
    >
      <div class="ctx-item" @click="ctxDownload">下载</div>
      <div class="ctx-item" @click="ctxCopyPath">复制路径</div>
      <div class="ctx-item" @click="ctxOpenInEditor" v-if="ctxMenu.entry && !ctxMenu.entry.is_dir">在独立编辑器中打开</div>
    </div>

    <!-- 多实例导入弹窗 -->
    <div v-if="clusterModal" class="cluster-modal-overlay" @click.self="clusterModal = false">
      <div class="cluster-modal">
        <div class="cluster-modal-header">
          <h3>从其他实例导入</h3>
          <button class="cluster-close" @click="clusterModal = false">✕</button>
        </div>

        <!-- 实例选择 -->
        <div v-if="!clusterSelectedUrl" class="cluster-instances">
          <div v-if="clusterScanning" class="cluster-scanning">扫描实例中...</div>
          <div v-else-if="clusterPeers.length === 0" class="cluster-empty">未发现其他 TS2 实例</div>
          <div
            v-for="inst in clusterPeers"
            :key="inst.url"
            class="cluster-instance-card"
            @click="selectClusterInstance(inst.url)"
          >
            <span class="cluster-instance-icon">🖥️</span>
            <div class="cluster-instance-info">
              <div class="cluster-instance-url">{{ inst.url }}</div>
              <div class="cluster-instance-meta">端口 {{ inst.port }} · v{{ inst.version }}</div>
            </div>
            <span class="cluster-instance-arrow">→</span>
          </div>
        </div>

        <!-- 远端文件浏览 -->
        <div v-else class="cluster-browser">
          <div class="cluster-browser-header">
            <button class="btn-back" @click="clusterSelectedUrl = ''; clusterRemoteEntries = []; clusterRemotePath = ''">← 返回实例列表</button>
            <span class="cluster-remote-label">{{ clusterSelectedUrl }}</span>
          </div>

          <!-- 远端搜索 -->
          <div class="cluster-search-bar">
            <input
              v-model="clusterSearchQuery"
              class="search-input"
              placeholder="搜索远端文件..."
              @input="onClusterSearchInput"
            />
            <button v-if="clusterSearchQuery" class="search-clear" @click="clusterSearchQuery = ''; loadClusterDir('')">✕</button>
          </div>

          <!-- 远端面包屑 -->
          <div class="breadcrumb" style="margin-bottom:4px">
            <div class="breadcrumb-links">
              <span class="breadcrumb-item" @click="loadClusterDir('')">根目录</span>
              <template v-for="(seg, idx) in clusterRemotePath.split('/').filter(Boolean)" :key="idx">
                <span class="breadcrumb-sep">/</span>
                <span class="breadcrumb-item" @click="loadClusterDir(clusterRemotePath.split('/').slice(0, idx+1).join('/'))">{{ seg }}</span>
              </template>
            </div>
          </div>

          <!-- 远端文件列表 -->
          <div v-if="clusterRemoteLoading" class="loading-root">加载中...</div>
          <div v-else-if="clusterRemoteEntries.length === 0" class="empty-dir">空目录</div>
          <div v-else class="cluster-entry-list">
            <div v-if="clusterRemotePath" class="entry-row entry-up" @click="loadClusterDir(clusterRemotePath.split('/').slice(0, -1).join('/'))">
              <span class="entry-icon">📁</span><span class="entry-name">..</span>
            </div>
            <div
              v-for="entry in clusterRemoteEntries"
              :key="entry.path || entry.name"
              class="entry-row"
              :class="{ 'cluster-selected': clusterSelectedFiles.has(entry.path) }"
              @click="handleClusterEntryClick(entry)"
            >
              <span class="entry-icon">{{ entry.is_dir ? '📁' : fileIcon(entry.ext) }}</span>
              <span class="entry-name" :class="{ 'is-dir': entry.is_dir }">{{ entry.name }}</span>
              <span v-if="!entry.is_dir" class="entry-check">
                <span v-if="clusterSelectedFiles.has(entry.path)" class="check-on">✓</span>
                <span v-else class="check-off">○</span>
              </span>
            </div>
          </div>

          <!-- 选中文件操作栏 -->
          <div v-if="clusterSelectedFiles.size > 0" class="cluster-action-bar">
            <span>已选 {{ clusterSelectedFiles.size }} 个文件</span>
            <button class="btn-cluster-transfer" @click="doClusterTransfer" :disabled="clusterTransferring">
              {{ clusterTransferring ? '传输中...' : '导入到当前目录' }}
            </button>
            <button class="btn-cluster-clear" @click="clusterSelectedFiles.clear()">清空选择</button>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted, nextTick, defineAsyncComponent } from 'vue'
import { useRouter } from 'vue-router'
const router = useRouter()
import { readDir, getFile, putFile, upload as uploadApi, downloadFile, getServerURL, clusterInstances, clusterRemoteReadDir, clusterRemoteSearch, clusterTransferBatch } from '../api'
import { useWebSocket } from '../composables/useWebSocket'
import { loadAutocompleteConfig, buildHintExtends } from '../autocomplete'
import {
  localReadDir, localReadFile, localWriteFile, localDeleteFile, localMkdir,
  importDirFromServer, exportDirToServer, localFSStats, localFSClear,
  localWriteFileBlob, localReadFileBlob, localSearchTree, isBinaryExt,
  type DirEntry as LocalDirEntry,
} from '../stores/localFS'

// Vditor 加载策略：本地动态导入优先 → CDN 降级
let VditorClass: any = null
let vditorLoadFailed = false
let vditorSource: 'local' | 'cdn' | null = null

const VDITOR_CDN = 'https://unpkg.com/vditor'

function isCapacitor(): boolean {
  return !!(window as any).Capacitor || document.documentElement.getAttribute('data-capacitor') !== null || location.protocol === 'file:'
}

async function loadVditor(): Promise<any> {
  if (VditorClass) return VditorClass
  if (vditorLoadFailed) return null
  if ((window as any).Vditor) { VditorClass = (window as any).Vditor; return VditorClass }

  // 1. 本地动态导入（Vite 打包）
  try {
    const mod = await import('vditor')
    await import('vditor/dist/index.css')
    VditorClass = mod.default
    vditorSource = 'local'
    return VditorClass
  } catch (e) {
    console.warn('Vditor 本地导入失败，尝试 CDN:', e)
  }

  // 2. CDN 降级加载
  try {
    await new Promise<void>((resolve, reject) => {
      const link = document.createElement('link')
      link.rel = 'stylesheet'
      link.href = VDITOR_CDN + '/dist/index.css'
      document.head.appendChild(link)
      const script = document.createElement('script')
      script.src = VDITOR_CDN + '/dist/index.min.js'
      script.onload = () => resolve()
      script.onerror = () => reject(new Error('CDN JS load failed'))
      document.head.appendChild(script)
    })
    VditorClass = (window as any).Vditor
    if (!VditorClass) throw new Error('Vditor not found on window')
    vditorSource = 'cdn'
    return VditorClass
  } catch (e) {
    console.warn('Vditor CDN 加载也失败，使用纯文本编辑:', e)
  }

  vditorLoadFailed = true
  return null
}

function getVditorCdn(): string {
  return vditorSource === 'cdn' ? VDITOR_CDN : import.meta.env.BASE_URL + 'vditor'
}

async function resolveVditorCdn(): Promise<string> {
  return vditorSource === 'cdn' ? VDITOR_CDN : import.meta.env.BASE_URL + 'vditor'
}

interface DirEntry {
  path: string
  name: string
  is_dir: boolean
  ext?: string
  size?: number
  modified?: number
}

const currentPath = ref('')
const entries = ref<DirEntry[]>([])
const loading = ref(true)
const searchQuery = ref('')
const searchResults = ref<DirEntry[]>([])
const searching = ref(false)
let searchTimer: ReturnType<typeof setTimeout> | null = null

// 本地/服务端文件源切换
const fileSource = ref<'server' | 'local'>('server')
const localEntries = ref<DirEntry[]>([])
const localStats = ref({ files: 0, dirs: 0, totalSize: 0 })
const importExportBusy = ref(false)
const importExportMsg = ref('')

// 过滤后的文件列表
const filteredEntries = computed(() => {
  const q = searchQuery.value.trim().toLowerCase()
  // 有搜索关键词时返回搜索结果（服务端和本地都适用）
  if (q) return searchResults.value
  // 本地文件源返回本地条目
  if (fileSource.value === 'local') return localEntries.value
  return entries.value
})

function onSearchInput() {
  if (searchTimer) clearTimeout(searchTimer)
  const q = searchQuery.value.trim()
  if (!q) {
    searchResults.value = []
    searching.value = false
    return
  }
  // 300ms 防抖
  searchTimer = setTimeout(async () => {
    searching.value = true
    try {
      if (fileSource.value === 'local') {
        // 本地模式：递归搜索本地文件树
        const items = await localSearchTree(q, '/')
        searchResults.value = items.map(e => ({
          path: e.path,
          name: e.name,
          is_dir: e.type === 'dir',
          ext: e.type === 'file' ? (e.name.includes('.') ? '.' + e.name.split('.').pop() : '') : undefined,
          size: e.size,
          modified: e.updatedAt,
        }))
      } else {
        // 服务端模式：调用服务端递归搜索
        const { search: searchApi } = await import('../api')
        const res = await searchApi(q)
        const items = res.data?.data ?? res.data ?? []
        searchResults.value = Array.isArray(items) ? items as DirEntry[] : []
      }
    } catch {
      searchResults.value = []
    } finally {
      searching.value = false
    }
  }, 300)
}

function clearSearch() {
  searchQuery.value = ''
  searchResults.value = []
  searching.value = false
}

// WebSocket 消息：服务端文件变更时刷新目录列表
const { wsConnected, onMessage, reconnectWebSocket } = useWebSocket()

onMessage((msg) => {
  if (msg.cmd === 'filechange') {
    const change = msg.data
    if (!change) return
    const changePath = change.path || ''
    const changeType = change.type || ''

    // 如果正在编辑该文件且被外部修改，提示用户
    if (editingFile.value && changePath === editingFile.value && changeType === 'modified') {
      if (!editModified.value) {
        openFile(editingFile.value)
      }
      return
    }

    // 目录变更（created/deleted/renamed/modified）需要刷新目录列表
    if (changeType === 'created' || changeType === 'deleted' || changeType === 'renamed' || changeType === 'modified') {
      const currentDir = currentPath.value
      const parentDir = changePath.includes('/') ? changePath.substring(0, changePath.lastIndexOf('/')) : ''
      if (parentDir === currentDir || changePath.startsWith(currentDir)) {
        navigateTo(currentPath.value)
      }
    }
  } else if (msg.cmd === 'reloadFiletree') {
    navigateTo(currentPath.value)
  }
})

// 前后台切换时重连 WebSocket
document.addEventListener('visibilitychange', () => {
  if (document.visibilityState === 'visible') {
    reconnectWebSocket()
  }
})

// 编辑器状态
const editingFile = ref<string | null>(null)
const originalContent = ref('')
const editModified = ref(false)
const saving = ref(false)
const vditorRef = ref<HTMLDivElement | null>(null)
const textareaRef = ref<HTMLTextAreaElement | null>(null)
const useTextarea = ref(false)
let vditorInstance: any = null

// 动态导入 office 预览组件（代码分割，按需加载）
const VueOfficeDocx = defineAsyncComponent(() => import('@vue-office/docx'))
const VueOfficeExcel = defineAsyncComponent(() => import('@vue-office/excel'))
const VueOfficePptx = defineAsyncComponent(() => import('@vue-office/pptx'))
const VueOfficePdf = defineAsyncComponent(() => import('@vue-office/pdf'))

function getDownloadUrl(path: string): string {
  const base = getServerURL().replace(/\/+$/, '')
  return `${base}/api/file/download/${encodeURIComponent(path)}`
}

// Office 预览状态
const previewFile = ref<string | null>(null)
const previewType = ref<string | null>(null) // 'docx' | 'xlsx' | 'pptx' | 'pdf'
const localPreviewUrl = ref<string>('') // 本地二进制文件的 blob URL

const previewUrl = computed(() => {
  if (!previewFile.value) return ''
  // 本地模式：使用 blob URL
  if (fileSource.value === 'local' && localPreviewUrl.value) return localPreviewUrl.value
  return getDownloadUrl(previewFile.value)
})

// 面包屑
const pathSegments = computed(() => {
  if (!currentPath.value) return []
  return currentPath.value.split('/').filter(Boolean)
})

// 新建文件
const showNewFile = ref(false)
const newFileName = ref('')
const creatingFile = ref(false)
const newFileInputRef = ref<HTMLInputElement | null>(null)

function startNewFile() {
  if (!currentPath.value) {
    alert('请在子目录中创建文件')
    return
  }
  showNewFile.value = true
  newFileName.value = ''
  nextTick(() => {
    newFileInputRef.value?.focus()
  })
}

function cancelNewFile() {
  showNewFile.value = false
  newFileName.value = ''
}

async function createFile() {
  const name = newFileName.value.trim()
  if (!name) return
  const filePath = currentPath.value ? currentPath.value + '/' + name : name
  creatingFile.value = true
  try {
    await putFile(filePath, '')
    showNewFile.value = false
    newFileName.value = ''
    await navigateTo(currentPath.value)
    openFile(filePath)
  } catch {
    alert('创建文件失败')
  } finally {
    creatingFile.value = false
  }
}

onMounted(async () => {
  await navigateTo('')
})

async function navigateTo(path: string) {
  currentPath.value = path
  if (fileSource.value === 'local') {
    await loadLocalEntries(path)
  } else {
    loading.value = true
    try {
      const res = await readDir(path)
      const apiData = res.data?.data ?? res.data
      entries.value = Array.isArray(apiData) ? apiData : []
    } catch {
      entries.value = []
    } finally {
      loading.value = false
    }
  }
}

async function loadLocalEntries(path: string = '/') {
  loading.value = true
  try {
    const localItems = await localReadDir(path)
    localEntries.value = localItems.map(e => ({
      path: e.path,
      name: e.name,
      is_dir: e.type === 'dir',
      ext: e.type === 'file' ? (e.name.includes('.') ? '.' + e.name.split('.').pop() : '') : undefined,
      size: e.size,
      modified: e.updatedAt,
    }))
  } catch {
    localEntries.value = []
  } finally {
    loading.value = false
  }
}

async function refreshLocalStats() {
  try {
    localStats.value = await localFSStats()
  } catch { /* ignore */ }
}

function switchFileSource(source: 'server' | 'local') {
  fileSource.value = source
  currentPath.value = ''
  searchQuery.value = ''
  searchResults.value = []
  if (source === 'local') {
    loadLocalEntries('/')
    refreshLocalStats()
  } else {
    navigateTo('')
  }
}

function goUp() {
  if (!currentPath.value) return
  const parts = currentPath.value.split('/')
  parts.pop()
  navigateTo(parts.join('/'))
}

function handleEntryClick(entry: DirEntry) {
  if (entry.is_dir) {
    const targetPath = entry.path
    clearSearch()
    navigateTo(targetPath)
  } else {
    const ext = (entry.ext || '').toLowerCase()
    const officeType = OFFICE_EXTS[ext]
    if (officeType) {
      openPreview(entry.path, officeType)
    } else if (ext === '.html' || ext === '.htm') {
      // HTML 文件在浏览器新标签页打开预览
      const encodedPath = entry.path.split('/').map(s => encodeURIComponent(s)).join('/')
      const base = getServerURL().replace(/\/+$/, '')
      window.open(base + '/api/file/download/' + encodedPath + '?preview=true', '_blank')
    } else {
      openFile(entry.path)
    }
  }
}

const OFFICE_EXTS: Record<string, string> = { '.docx': 'docx', '.xlsx': 'xlsx', '.xls': 'xlsx', '.pptx': 'pptx', '.pdf': 'pdf' }

function openPreview(path: string, type: string) {
  closeEditor()
  // 释放旧的 blob URL
  if (localPreviewUrl.value) {
    URL.revokeObjectURL(localPreviewUrl.value)
    localPreviewUrl.value = ''
  }
  previewFile.value = path
  previewType.value = type
  // 本地模式：异步读取二进制文件生成 blob URL
  if (fileSource.value === 'local') {
    localReadFileBlob(path).then((blob) => {
      if (blob) {
        localPreviewUrl.value = URL.createObjectURL(blob)
      }
    }).catch(() => { /* ignore */ })
  }
}

function closePreview() {
  // 释放 blob URL
  if (localPreviewUrl.value) {
    URL.revokeObjectURL(localPreviewUrl.value)
    localPreviewUrl.value = ''
  }
  previewFile.value = null
  previewType.value = null
}

function openPdfReader() {
  // 从预览界面跳转到 AI 阅读器（PdfReaderView）
  if (previewFile.value) {
    const path = previewFile.value
    closePreview()
    router.push(`/pdf/${path}`)
  }
}

async function openFile(path: string) {
  try {
    let content = ''
    if (fileSource.value === 'local') {
      const localFile = await localReadFile(path)
      content = localFile?.content ?? ''
    } else {
      const res = await getFile(path)
      const apiData = res.data?.data ?? res.data
      content = apiData?.content ?? ''
    }
    editingFile.value = path
    originalContent.value = content
    editModified.value = false

    await nextTick()

    // 如果 Vditor 实例已存在，复用它（只更新内容）
    if (vditorInstance) {
      try {
        vditorInstance.setValue(content)
        return
      } catch {
        // setValue 失败（实例可能损坏），销毁重建
        try { vditorInstance.destroy() } catch { /* ignore */ }
        vditorInstance = null
      }
    }

    // 尝试加载 Vditor，失败则降级为纯文本编辑
    const Vditor = await loadVditor()
    if (Vditor && vditorRef.value) {
      const isTouch = 'ontouchstart' in window
      const acConfig = loadAutocompleteConfig()
      const currentTheme = document.documentElement.getAttribute('data-theme') || 'dark'
      const vditorCdn = await resolveVditorCdn()
      let vditorReady = false
      try {
        vditorInstance = new Vditor(vditorRef.value, {
          value: content,
          mode: 'ir',
          theme: currentTheme === 'light' ? 'classic' : 'dark',
          placeholder: '开始编辑...',
          cache: { enable: false },
          tab: '\t',
          cdn: vditorCdn,
          hint: {
            delay: 200,
            parse: false,
            extend: buildHintExtends(acConfig),
          },
          input: () => {
            if (vditorInstance) {
              editModified.value = vditorInstance.getValue() !== originalContent.value
            }
          },
          after: () => { vditorReady = true },
          toolbar: isTouch
            ? ['headings', 'bold', 'italic', 'strike', '|', 'quote', 'inline-code', '|', 'list', 'ordered-list', 'check', '|', 'undo', 'redo', '|', 'edit-mode', 'preview']
            : ['headings', 'bold', 'italic', 'strike', '|', 'quote', 'inline-code', 'code', '|', 'list', 'ordered-list', 'check', '|', 'link', 'table', '|', 'undo', 'redo', '|', 'edit-mode', 'preview', 'fullscreen'],
        })
        // 超时检测：子资源加载失败时 vditor 不会触发 after 回调，也不抛异常
        await new Promise<void>((resolve) => setTimeout(resolve, 6000))
        if (!vditorReady) {
          console.warn('Vditor 子资源加载超时（cdn=' + vditorCdn + '），回退纯文本编辑')
          try { vditorInstance.destroy() } catch { /* ignore */ }
          vditorInstance = null
          useTextarea.value = true
          await nextTick()
          if (textareaRef.value) textareaRef.value.value = content
        }
      } catch (initErr) {
        console.warn('Vditor 初始化失败，回退纯文本编辑:', initErr)
        vditorInstance = null
        useTextarea.value = true
        await nextTick()
        if (textareaRef.value) textareaRef.value.value = content
      }
    } else {
      // Vditor 加载失败，回退纯文本
      useTextarea.value = true
      await nextTick()
      if (textareaRef.value) textareaRef.value.value = content
    }
  } catch {
    alert('无法读取文件')
  }
}

function insertMd(before: string, after: string) {
  const ta = textareaRef.value
  if (!ta) return
  const start = ta.selectionStart
  const end = ta.selectionEnd
  const selected = ta.value.substring(start, end)
  const replacement = before + (selected || '文本') + after
  ta.value = ta.value.substring(0, start) + replacement + ta.value.substring(end)
  ta.selectionStart = start + before.length
  ta.selectionEnd = start + before.length + (selected || '文本').length
  ta.focus()
  editModified.value = true
}

async function saveFile() {
  if (!editingFile.value) return
  saving.value = true
  try {
    let content = ''
    if (useTextarea.value && textareaRef.value) {
      content = textareaRef.value.value
    } else if (vditorInstance) {
      content = vditorInstance.getValue()
    }
    if (fileSource.value === 'local') {
      await localWriteFile(editingFile.value, content)
    } else {
      await putFile(editingFile.value, content)
    }
    originalContent.value = content
    editModified.value = false
  } catch {
    alert('保存失败')
  } finally {
    saving.value = false
  }
}

function closeEditor() {
  if (editModified.value) {
    const action = confirm('文件已修改但未保存，是否保存？\n\n确定 = 保存并关闭\n取消 = 不保存直接关闭')
    if (action) {
      saveFile()
    }
  }
  closePreview()
  if (vditorInstance) {
    vditorInstance.destroy()
    vditorInstance = null
  }
  editingFile.value = null
  originalContent.value = ''
  editModified.value = false
  useTextarea.value = false
}

// ─── 导入导出 ──────────────────────────────────────────

// 单文件从服务端导入到本地（参考笔记实现）
async function importSingleFromServer(entry: DirEntry) {
  try {
    const ext = (entry.ext || '').toLowerCase()
    const dir = entry.path.includes('/') ? entry.path.substring(0, entry.path.lastIndexOf('/')) : ''
    // 确保本地目录存在
    if (dir) await localMkdir(dir)
    if (isBinaryExt(ext)) {
      // 二进制文件：用 download API 获取，转 base64 存储
      const url = getDownloadUrl(entry.path)
      const res = await fetch(url)
      if (!res.ok) throw new Error(`下载失败: ${res.status}`)
      const blob = await res.blob()
      await localWriteFileBlob(entry.path, blob)
    } else {
      // 文本文件：用 getFile API 获取
      const res = await getFile(entry.path)
      const content = res.data?.data?.content ?? res.data?.data ?? ''
      if (typeof content === 'string') {
        await localWriteFile(entry.path, content)
      } else {
        throw new Error('文件内容格式异常')
      }
    }
    importExportMsg.value = `已导入：${entry.name}`
    await refreshLocalStats()
    setTimeout(() => { importExportMsg.value = '' }, 2000)
  } catch (e: any) {
    importExportMsg.value = `导入失败：${e.message || e}`
    setTimeout(() => { importExportMsg.value = '' }, 3000)
  }
}

// 单文件从本地导出到服务端（参考笔记实现）
async function exportSingleToServer(entry: DirEntry) {
  try {
    const ext = (entry.ext || '').toLowerCase()
    if (isBinaryExt(ext)) {
      // 二进制文件：读取 base64 转 Blob，用 upload API 上传
      const blob = await localReadFileBlob(entry.path)
      if (!blob) {
        importExportMsg.value = '读取本地文件失败'
        setTimeout(() => { importExportMsg.value = '' }, 3000)
        return
      }
      const formData = new FormData()
      formData.append('files', blob, entry.name)
      const dir = entry.path.includes('/') ? entry.path.substring(0, entry.path.lastIndexOf('/')) : ''
      formData.append('path', dir)
      await uploadApi(formData)
    } else {
      // 文本文件：用 putFile API 上传
      const localFile = await localReadFile(entry.path)
      const content = localFile?.content ?? ''
      await putFile(entry.path, content)
    }
    importExportMsg.value = `已导出：${entry.name}`
    setTimeout(() => { importExportMsg.value = '' }, 2000)
  } catch (e: any) {
    importExportMsg.value = `导出失败：${e.message || e}`
    setTimeout(() => { importExportMsg.value = '' }, 3000)
  }
}

async function doImportFromServer() {
  if (importExportBusy.value) return
  importExportBusy.value = true
  importExportMsg.value = '正在从服务端导入...'
  try {
    const serverDir = currentPath.value || ''
    const localDir = serverDir || 'imported'
    // 确保本地目录存在
    if (localDir !== '/') await localMkdir(localDir)
    const count = await importDirFromServer(
      serverDir, localDir,
      async (path) => {
        const res = await readDir(path)
        const d = res.data?.data ?? res.data
        return Array.isArray(d) ? d : []
      },
      async (path) => {
        const res = await getFile(path)
        const d = res.data?.data ?? res.data
        return d?.content ?? ''
      },
    )
    importExportMsg.value = `导入完成：${count} 个文件`
    await loadLocalEntries(currentPath.value || '/')
    await refreshLocalStats()
  } catch (e: any) {
    importExportMsg.value = `导入失败：${e.message || e}`
  } finally {
    importExportBusy.value = false
    setTimeout(() => { importExportMsg.value = '' }, 3000)
  }
}

async function doExportToServer() {
  if (importExportBusy.value) return
  importExportBusy.value = true
  importExportMsg.value = '正在导出到服务端...'
  try {
    const localDir = currentPath.value || '/'
    const serverDir = currentPath.value || 'exported'
    const count = await exportDirToServer(
      localDir, serverDir,
      async (path, content) => { await putFile(path, content) },
    )
    importExportMsg.value = `导出完成：${count} 个文件`
    // 刷新服务端列表
    if (fileSource.value === 'server') await navigateTo(currentPath.value)
  } catch (e: any) {
    importExportMsg.value = `导出失败：${e.message || e}`
  } finally {
    importExportBusy.value = false
    setTimeout(() => { importExportMsg.value = '' }, 3000)
  }
}

async function doCreateLocalFile() {
  const name = prompt('输入文件名（如 notes/test.md）：')
  if (!name) return
  await localWriteFile(name, '')
  await loadLocalEntries(currentPath.value || '/')
  await refreshLocalStats()
}

async function doCreateLocalDir() {
  const name = prompt('输入目录名（如 notes/物理）：')
  if (!name) return
  await localMkdir(name)
  await loadLocalEntries(currentPath.value || '/')
  await refreshLocalStats()
}

async function doDeleteLocal(entry: DirEntry) {
  if (!confirm(`确定删除 ${entry.name}？`)) return
  if (entry.is_dir) {
    // 递归删除目录下所有文件
    const items = await localReadDir(entry.path)
    for (const item of items) {
      if (item.type === 'file') await localDeleteFile(item.path)
    }
  } else {
    await localDeleteFile(entry.path)
  }
  await loadLocalEntries(currentPath.value || '/')
  await refreshLocalStats()
}

// 上传状态
const uploading = ref(false)
const uploadProgress = ref(0)
const uploadProgressText = ref('')
const dragOver = ref(false)
const fileInputRef = ref<HTMLInputElement | null>(null)
const folderInputRef = ref<HTMLInputElement | null>(null)

function updateUploadProgress(current: number, total: number, name: string) {
  uploadProgress.value = Math.round((current / total) * 100)
  uploadProgressText.value = `(${current}/${total}) ${name}`
}

async function uploadFiles(files: File[]) {
  if (files.length === 0) return
  if (!currentPath.value) {
    alert('禁止在根目录上传，请先进入子目录')
    return
  }
  uploading.value = true
  uploadProgress.value = 0
  uploadProgressText.value = '准备上传...'
  let completed = 0
  for (const file of files) {
    updateUploadProgress(completed, files.length, file.name)
    try {
      const formData = new FormData()
      formData.append('files', file)
      const relPath = (file as any).webkitRelativePath || file.name
      const dirPart = relPath.includes('/') ? relPath.substring(0, relPath.lastIndexOf('/')) : ''
      const targetPath = currentPath.value
        ? (dirPart ? currentPath.value + '/' + dirPart : currentPath.value)
        : dirPart
      formData.append('path', targetPath)
      await uploadApi(formData)
      completed++
    } catch {
      /* continue */
    }
  }
  uploadProgress.value = 100
  uploadProgressText.value = `完成 (${completed}/${files.length})`
  uploading.value = false
  await navigateTo(currentPath.value)
}

async function handleUpload(event: Event) {
  const input = event.target as HTMLInputElement
  const files = input.files
  if (!files || files.length === 0) return
  await uploadFiles(Array.from(files))
  if (fileInputRef.value) fileInputRef.value.value = ''
}

async function handleFolderUpload(event: Event) {
  const input = event.target as HTMLInputElement
  const files = input.files
  if (!files || files.length === 0) return
  await uploadFiles(Array.from(files))
  if (folderInputRef.value) folderInputRef.value.value = ''
}

async function handleDrop(event: DragEvent) {
  dragOver.value = false
  const files = event.dataTransfer?.files
  if (!files || files.length === 0) return
  await uploadFiles(Array.from(files))
}

// 右键菜单
const ctxMenu = ref({ visible: false, x: 0, y: 0, entry: null as DirEntry | null })

function showCtxMenu(entry: DirEntry, event: MouseEvent) {
  ctxMenu.value = { visible: true, x: event.clientX, y: event.clientY, entry }
}

function closeCtxMenu() {
  ctxMenu.value.visible = false
  ctxMenu.value.entry = null
}

function ctxDownload() {
  if (ctxMenu.value.entry) {
    downloadFile(ctxMenu.value.entry.path)
  }
  closeCtxMenu()
}

function ctxCopyPath() {
  if (ctxMenu.value.entry) {
    navigator.clipboard.writeText(ctxMenu.value.entry.path).catch(() => {})
  }
  closeCtxMenu()
}

function ctxOpenInEditor() {
  if (ctxMenu.value.entry) {
    const path = ctxMenu.value.entry.path
    closeCtxMenu()
    router.push(`/editor/${path}`)
  }
}

function onCtxClickAway() {
  if (ctxMenu.value.visible) closeCtxMenu()
}

// ─── 多实例集群导入 ──────────────────────────────────────
const clusterModal = ref(false)
const clusterScanning = ref(false)
const clusterPeers = ref<Array<{ url: string; port: number; version: string }>>([])
const clusterSelectedUrl = ref('')
const clusterRemotePath = ref('')
const clusterRemoteEntries = ref<DirEntry[]>([])
const clusterRemoteLoading = ref(false)
const clusterSearchQuery = ref('')
const clusterSelectedFiles = ref(new Set<string>())
const clusterTransferring = ref(false)
let clusterSearchTimer: ReturnType<typeof setTimeout> | null = null

async function openClusterImport() {
  clusterModal.value = true
  clusterSelectedUrl.value = ''
  clusterRemotePath.value = ''
  clusterRemoteEntries.value = []
  clusterSearchQuery.value = ''
  clusterSelectedFiles.value = new Set()
  clusterScanning.value = true
  try {
    const res = await clusterInstances()
    const data = res.data?.data ?? res.data
    clusterPeers.value = data?.peers ?? []
  } catch {
    clusterPeers.value = []
  } finally {
    clusterScanning.value = false
  }
}

async function selectClusterInstance(url: string) {
  clusterSelectedUrl.value = url
  clusterRemotePath.value = ''
  clusterSearchQuery.value = ''
  clusterSelectedFiles.value = new Set()
  await loadClusterDir('')
}

async function loadClusterDir(path: string) {
  clusterRemotePath.value = path
  clusterRemoteLoading.value = true
  clusterSearchQuery.value = ''
  try {
    const res = await clusterRemoteReadDir(clusterSelectedUrl.value, path)
    const data = res.data?.data ?? res.data
    clusterRemoteEntries.value = Array.isArray(data) ? data : []
  } catch {
    clusterRemoteEntries.value = []
  } finally {
    clusterRemoteLoading.value = false
  }
}

function onClusterSearchInput() {
  if (clusterSearchTimer) clearTimeout(clusterSearchTimer)
  const q = clusterSearchQuery.value.trim()
  if (!q) {
    loadClusterDir(clusterRemotePath.value)
    return
  }
  clusterSearchTimer = setTimeout(async () => {
    clusterRemoteLoading.value = true
    try {
      const res = await clusterRemoteSearch(clusterSelectedUrl.value, q, clusterRemotePath.value)
      const data = res.data?.data ?? res.data
      clusterRemoteEntries.value = Array.isArray(data) ? data : []
    } catch {
      clusterRemoteEntries.value = []
    } finally {
      clusterRemoteLoading.value = false
    }
  }, 300)
}

function handleClusterEntryClick(entry: DirEntry) {
  if (entry.is_dir) {
    loadClusterDir(entry.path)
  } else {
    // 切换选中状态
    const s = new Set(clusterSelectedFiles.value)
    if (s.has(entry.path)) {
      s.delete(entry.path)
    } else {
      s.add(entry.path)
    }
    clusterSelectedFiles.value = s
  }
}

async function doClusterTransfer() {
  if (clusterSelectedFiles.value.size === 0) return
  clusterTransferring.value = true
  const prefix = currentPath.value ? currentPath.value + '/' : ''
  const files = Array.from(clusterSelectedFiles.value).map(rp => ({
    remote_path: rp,
    local_path: prefix + rp.split('/').pop(),
  }))
  try {
    const res = await clusterTransferBatch(clusterSelectedUrl.value, files)
    const data = res.data?.data ?? res.data
    const ok = data?.ok ?? 0
    const fail = data?.fail ?? 0
    clusterSelectedFiles.value = new Set()
    // 刷新本地目录
    await navigateTo(currentPath.value)
    alert(`导入完成：${ok} 个成功${fail > 0 ? `，${fail} 个失败` : ''}`)
  } catch (e: any) {
    alert('导入失败: ' + (e.message || '未知错误'))
  } finally {
    clusterTransferring.value = false
  }
}

// ─── 主题切换时更新 Vditor（无需销毁重建） ────────────────────────────

function onThemeChange(e: Event) {
  const theme = (e as CustomEvent).detail?.theme || 'dark'
  if (vditorInstance) {
    try {
      const vditorTheme = theme === 'light' ? 'classic' : 'dark'
      const contentTheme = theme === 'light' ? 'light' : 'dark'
      const codeTheme = theme === 'light' ? 'github' : 'tokyo-night-dark'
      vditorInstance.setTheme(vditorTheme, contentTheme, codeTheme)
    } catch { /* ignore if setTheme not available */ }
  }
}

onMounted(() => {
  document.addEventListener('click', onCtxClickAway)
  window.addEventListener('ts2-theme-change', onThemeChange)
})

onUnmounted(() => {
  if (vditorInstance) {
    vditorInstance.destroy()
    vditorInstance = null
  }
  document.removeEventListener('click', onCtxClickAway)
  window.removeEventListener('ts2-theme-change', onThemeChange)
})

function fileIcon(ext?: string): string {
  const e = (ext || '').toLowerCase()
  if (e === '.md') return '📝'
  if (e === '.json') return '📋'
  if (e === '.txt' || e === '.rmd') return '📄'
  if (['.py', '.ts', '.js', '.vue', '.r', '.lua'].includes(e)) return '💻'
  if (['.csv', '.xlsx', '.xls'].includes(e)) return '📊'
  if (['.png', '.jpg', '.jpeg', '.svg', '.gif'].includes(e)) return '🖼️'
  if (e === '.pdf') return '📕'
  if (e === '.docx') return '📝'
  if (e === '.pptx') return '📽️'
  return '📄'
}

function formatSize(bytes: number): string {
  if (bytes < 1024) return `${bytes}B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)}KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)}MB`
}
</script>

<style scoped>
.files-body {
  padding: 0 !important;
  display: flex;
  flex-direction: column;
}

/* 文件源切换 */
.source-toggle {
  display: inline-flex;
  border: 1px solid var(--border);
  border-radius: 6px;
  overflow: hidden;
  margin-left: 8px;
}
.source-btn {
  background: transparent;
  border: none;
  color: var(--fg-muted);
  padding: 4px 12px;
  font-size: 12px;
  cursor: pointer;
  transition: all 0.15s;
}
.source-btn.active {
  background: var(--accent);
  color: #fff;
}
.source-btn:hover:not(.active) {
  background: var(--bg-secondary);
}

/* 本地文件操作 */
.import-export-msg {
  font-size: 12px;
  color: var(--accent);
  margin-left: 8px;
}
.local-stats {
  font-size: 11px;
  color: var(--fg-muted);
  margin-left: 8px;
}
.btn-delete-local {
  background: transparent;
  border: none;
  color: var(--fg-muted);
  font-size: 14px;
  cursor: pointer;
  padding: 2px 6px;
  border-radius: 4px;
  opacity: 0;
  transition: opacity 0.15s;
}
.entry-row:hover .btn-delete-local {
  opacity: 1;
}
.btn-delete-local:hover {
  color: #e74c3c;
  background: var(--bg-secondary);
}

/* 单文件导入/导出按钮 */
.btn-import-single,
.btn-export-single {
  background: transparent;
  border: 1px solid var(--border);
  color: var(--accent);
  font-size: 13px;
  cursor: pointer;
  padding: 2px 8px;
  border-radius: 4px;
  opacity: 0;
  transition: opacity 0.15s, background 0.15s;
  margin-left: 4px;
}
.entry-row:hover .btn-import-single,
.entry-row:hover .btn-export-single {
  opacity: 1;
}
.btn-import-single:hover,
.btn-export-single:hover {
  background: var(--accent);
  color: #fff;
}

/* AI 阅读按钮 */
.btn-ai-read {
  background: transparent;
  border: 1px solid var(--accent);
  color: var(--accent);
  padding: 4px 12px;
  border-radius: 6px;
  font-size: 12px;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.15s;
  white-space: nowrap;
}
.btn-ai-read:hover {
  background: var(--accent);
  color: #fff;
}

.header-actions {
  display: flex;
  gap: 8px;
}

.btn-icon {
  background: transparent;
  border: 1px solid var(--border);
  color: var(--fg-muted);
  padding: 4px 8px;
  font-size: 16px;
  border-radius: 6px;
  cursor: pointer;
}

.btn-icon:hover { color: var(--accent); border-color: var(--accent); }
.btn-icon:disabled { opacity: 0.5; cursor: not-allowed; }

.ws-status {
  font-size: 10px;
  color: var(--danger);
  transition: color 0.3s;
}

.ws-status.connected {
  color: #4ade80;
}

/* 新建文件栏 */
.newfile-bar {
  display: flex;
  gap: 6px;
  padding: 8px 16px;
  background: var(--bg-secondary);
  border-bottom: 1px solid var(--border);
  align-items: center;
}

.newfile-input {
  flex: 1;
  padding: 8px 12px;
  border: 1px solid var(--accent);
  border-radius: 6px;
  background: var(--bg);
  color: var(--fg);
  font-size: 14px;
  font-family: monospace;
}

.newfile-input:focus {
  outline: none;
}

.btn-newfile {
  padding: 8px 16px;
  background: var(--accent);
  color: var(--bg);
  border: none;
  border-radius: 6px;
  font-size: 13px;
  font-weight: 500;
  cursor: pointer;
  white-space: nowrap;
}

.btn-newfile:disabled {
  opacity: 0.5;
}

.btn-newfile-cancel {
  background: none;
  border: none;
  color: var(--fg-muted);
  font-size: 13px;
  cursor: pointer;
  padding: 8px 12px;
}

.btn-newfile-cancel:hover {
  color: var(--fg);
}

/* 搜索过滤框 */
.search-bar {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 8px 16px;
  background: var(--bg-secondary);
  border-bottom: 1px solid var(--border);
  flex-shrink: 0;
}

.search-input {
  flex: 1;
  padding: 7px 12px;
  border: 1px solid var(--border);
  border-radius: 6px;
  background: var(--bg);
  color: var(--fg);
  font-size: 14px;
}

.search-input:focus {
  outline: none;
  border-color: var(--accent);
}

.search-input::placeholder {
  color: var(--fg-muted);
}

.search-clear {
  background: transparent;
  border: none;
  color: var(--fg-muted);
  font-size: 14px;
  cursor: pointer;
  padding: 4px 8px;
}

.search-clear:hover {
  color: var(--fg);
}

/* 面包屑 */
.breadcrumb {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  padding: 8px 16px;
  border-bottom: 1px solid var(--border);
  background: var(--bg-secondary);
  flex-shrink: 0;
  overflow-x: auto;
  white-space: nowrap;
}

.breadcrumb-links {
  display: flex;
  align-items: center;
  gap: 2px;
  overflow-x: auto;
  flex: 1;
}

.breadcrumb-item {
  font-size: 13px;
  color: var(--fg-muted);
  cursor: pointer;
  padding: 2px 6px;
  border-radius: 4px;
  transition: color 0.15s, background 0.15s;
}

.breadcrumb-item:hover {
  color: var(--accent);
  background: rgba(122, 162, 247, 0.1);
}

.breadcrumb-item.active {
  color: var(--fg);
  font-weight: 500;
}

.breadcrumb-sep {
  color: var(--fg-muted);
  font-size: 12px;
  opacity: 0.5;
}

.btn-newfile-breadcrumb {
  flex-shrink: 0;
  background: var(--accent);
  color: var(--bg);
  border: none;
  border-radius: 6px;
  padding: 4px 12px;
  font-size: 12px;
  font-weight: 500;
  cursor: pointer;
  white-space: nowrap;
  transition: filter 0.15s;
}

.btn-newfile-breadcrumb:hover {
  filter: brightness(1.1);
}

/* 目录列表 */
.browser-view {
  flex: 1;
  display: flex;
  flex-direction: column;
}

.loading-root,
.empty-dir {
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 40px;
  color: var(--fg-muted);
  font-size: 14px;
}

.entry-list {
  flex: 1;
  overflow-y: auto;
}

.entry-row {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 11px 16px;
  cursor: pointer;
  transition: background 0.15s;
  border-bottom: 1px solid var(--border);
}

.entry-row:hover {
  background: rgba(255, 255, 255, 0.04);
}

.entry-up {
  opacity: 0.7;
}

.entry-icon {
  font-size: 18px;
  flex-shrink: 0;
  width: 22px;
  text-align: center;
}

.entry-name {
  flex: 1;
  font-size: 14px;
  color: var(--fg);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.entry-name.is-dir {
  color: var(--accent);
  font-weight: 500;
}

.entry-path {
  font-size: 11px;
  color: var(--fg-muted);
  flex-shrink: 0;
  max-width: 120px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  margin-right: 8px;
}

.entry-size {
  font-size: 11px;
  color: var(--fg-muted);
  flex-shrink: 0;
}

/* 编辑器 */
.editor-view {
  display: flex;
  flex-direction: column;
  flex: 1;
  height: 100%;
  min-height: 0;
}

.editor-header {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 10px 16px;
  background: var(--bg-secondary);
  border-bottom: 1px solid var(--border);
}

.btn-back {
  background: transparent;
  color: var(--accent);
  padding: 4px 12px;
  font-size: 14px;
  border: 1px solid var(--border);
}

.btn-back:hover {
  background: rgba(255, 255, 255, 0.06);
}

.editor-path {
  font-size: 13px;
  color: var(--fg-muted);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  flex: 1;
}

.edit-modified {
  color: var(--warning);
  font-size: 16px;
}

.vditor-container {
  flex: 1;
  overflow: hidden;
  min-height: 0;
}

.fallback-textarea {
  flex: 1;
  width: 100%;
  min-height: 300px;
  padding: 12px;
  background: var(--bg);
  color: var(--fg);
  border: none;
  font-size: 14px;
  font-family: 'Consolas', 'Monaco', monospace;
  line-height: 1.6;
  resize: none;
  outline: none;
}

.md-toolbar {
  display: flex;
  gap: 4px;
  padding: 6px 10px;
  background: var(--bg-secondary);
  border-bottom: 1px solid var(--border);
  flex-wrap: wrap;
}

.md-toolbar button {
  padding: 4px 8px;
  border: 1px solid var(--border);
  border-radius: 4px;
  background: var(--bg);
  color: var(--fg);
  font-size: 12px;
  cursor: pointer;
  transition: all 0.15s;
}

.md-toolbar button:hover {
  background: var(--accent);
  color: var(--bg);
  border-color: var(--accent);
}

.vditor-container :deep(.vditor) {
  border: none !important;
  border-radius: 0 !important;
  background: var(--bg) !important;
}

.vditor-container :deep(.vditor-toolbar) {
  background: var(--toolbar-bg, var(--bg-secondary)) !important;
  border-bottom: 1px solid var(--border) !important;
}

.vditor-container :deep(.vditor-toolbar__item) {
  color: var(--toolbar-item, var(--fg-muted)) !important;
}

.vditor-container :deep(.vditor-toolbar__item:hover) {
  color: var(--toolbar-item-hover, var(--fg)) !important;
}

.vditor-container :deep(.vditor-toolbar__item--current) {
  color: var(--accent) !important;
}

/* Vditor 编辑器内部 - 强制跟随主题 */
.vditor-container :deep(.vditor-ir) {
  background: var(--editor-bg, var(--bg)) !important;
  color: var(--fg) !important;
}

.vditor-container :deep(.vditor-sv) {
  background: var(--editor-bg, var(--bg)) !important;
  color: var(--fg) !important;
}

.vditor-container :deep(.vditor-wysiwyg) {
  background: var(--editor-bg, var(--bg)) !important;
  color: var(--fg) !important;
}

.vditor-container :deep(.vditor-reset) {
  background: var(--editor-bg, var(--bg)) !important;
  color: var(--fg) !important;
}

.vditor-container :deep(.vditor-content) {
  background: var(--editor-bg, var(--bg)) !important;
}

.vditor-container :deep(.vditor-ir__block),
.vditor-container :deep(.vditor-wysiwyg__block),
.vditor-container :deep(.vditor-sv__block) {
  background: var(--editor-bg, var(--bg)) !important;
  color: var(--fg) !important;
}

/* Vditor 预览模式 */
.vditor-container :deep(.vditor-preview) {
  background: var(--editor-bg, var(--bg)) !important;
  color: var(--fg) !important;
}

.vditor-container :deep(.vditor-preview__content) {
  color: var(--fg) !important;
}

@media (max-width: 768px) {
  .vditor-container :deep(.vditor-toolbar) {
    overflow-x: auto;
    flex-wrap: nowrap;
  }
  .vditor-container :deep(.vditor-toolbar__item) {
    flex-shrink: 0;
  }
  .vditor-container :deep(.vditor-reset) {
    padding: 10px 8px !important;
    font-size: 15px;
  }
  .vditor-container :deep(.vditor-ir),
  .vditor-container :deep(.vditor-sv),
  .vditor-container :deep(.vditor-wysiwyg) {
    min-height: calc(100vh - 120px) !important;
  }
}

.editor-actions {
  display: flex;
  justify-content: flex-end;
  padding: 10px 16px;
  background: var(--bg-secondary);
  border-top: 1px solid var(--border);
}

/* Office 预览容器 */
.office-preview-container {
  flex: 1;
  overflow: auto;
  min-height: 0;
  background: var(--bg);
}

.preview-error {
  display: flex;
  align-items: center;
  justify-content: center;
  height: 200px;
  color: var(--fg-muted);
  font-size: 14px;
}

.btn-save {
  background: var(--accent);
  color: var(--bg);
  font-weight: 600;
  padding: 8px 24px;
}

.btn-save:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

/* 上传 */
.upload-section {
  padding: 16px;
  border-top: 1px solid var(--border);
  background: var(--bg-secondary);
  flex-shrink: 0;
  transition: background 0.2s;
}

.upload-section.drag-over {
  background: rgba(var(--accent-rgb, 59, 130, 246), 0.1);
  border-color: var(--accent);
}

.upload-section.uploading {
  cursor: progress;
}

.upload-row {
  display: flex;
  gap: 8px;
  align-items: center;
}

.btn-upload {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  background: var(--accent);
  color: var(--bg);
  padding: 7px 14px;
  border-radius: 6px;
  font-size: 13px;
  font-weight: 500;
  cursor: pointer;
  white-space: nowrap;
  transition: background 0.15s;
}

.btn-upload:hover {
  filter: brightness(1.1);
}

.btn-upload-folder {
  background: transparent;
  color: var(--accent);
  border: 1px solid var(--accent);
}

.upload-hint {
  font-size: 12px;
  color: var(--fg-muted);
  margin-top: 8px;
  text-align: center;
  padding: 4px;
  border: 1px dashed var(--border);
  border-radius: 6px;
}

.upload-hint-active {
  color: var(--accent);
  border-color: var(--accent);
  background: rgba(var(--accent-rgb, 59, 130, 246), 0.05);
}

.upload-progress-bar {
  margin-top: 8px;
  height: 20px;
  background: var(--border);
  border-radius: 10px;
  overflow: hidden;
  position: relative;
}

.upload-progress-fill {
  height: 100%;
  background: var(--accent);
  border-radius: 10px;
  transition: width 0.3s ease;
}

.upload-progress-text {
  position: absolute;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 11px;
  color: var(--bg);
  font-weight: 600;
  text-shadow: 0 1px 2px rgba(0,0,0,0.3);
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

.ctx-item:active {
  background: rgba(var(--accent-rgb, 59, 130, 246), 0.2);
}

/* 多实例集群导入 */
.btn-cluster-import {
  background: var(--accent, #3b82f6);
  color: #fff;
  border: none;
  cursor: pointer;
  font-size: 12px;
  padding: 6px 12px;
  border-radius: 6px;
}

.cluster-modal-overlay {
  position: fixed;
  inset: 0;
  background: rgba(0,0,0,0.5);
  z-index: 1000;
  display: flex;
  align-items: center;
  justify-content: center;
}

.cluster-modal {
  background: var(--bg, #1e1e2e);
  border-radius: 12px;
  width: 90%;
  max-width: 500px;
  max-height: 80vh;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  box-shadow: 0 8px 32px rgba(0,0,0,0.4);
}

.cluster-modal-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 16px;
  border-bottom: 1px solid var(--border, #333);
}

.cluster-modal-header h3 {
  margin: 0;
  font-size: 16px;
}

.cluster-close {
  background: none;
  border: none;
  color: var(--fg-muted);
  font-size: 18px;
  cursor: pointer;
}

.cluster-instances,
.cluster-browser {
  padding: 16px;
  overflow-y: auto;
  flex: 1;
}

.cluster-scanning,
.cluster-empty {
  text-align: center;
  color: var(--fg-muted);
  padding: 32px 0;
}

.cluster-instance-card {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 12px;
  border-radius: 8px;
  border: 1px solid var(--border, #333);
  margin-bottom: 8px;
  cursor: pointer;
  transition: background 0.15s;
}

.cluster-instance-card:hover {
  background: rgba(var(--accent-rgb, 59, 130, 246), 0.1);
}

.cluster-instance-icon {
  font-size: 24px;
}

.cluster-instance-info {
  flex: 1;
}

.cluster-instance-url {
  font-weight: 600;
  font-size: 14px;
}

.cluster-instance-meta {
  font-size: 11px;
  color: var(--fg-muted);
}

.cluster-instance-arrow {
  color: var(--accent);
  font-size: 18px;
}

.cluster-browser-header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;
}

.cluster-browser-header .btn-back {
  background: none;
  border: none;
  color: var(--accent);
  cursor: pointer;
  font-size: 13px;
  padding: 4px 8px;
}

.cluster-remote-label {
  font-size: 12px;
  color: var(--fg-muted);
  font-family: monospace;
}

.cluster-search-bar {
  display: flex;
  gap: 4px;
  margin-bottom: 8px;
}

.cluster-entry-list {
  max-height: 300px;
  overflow-y: auto;
}

.cluster-selected {
  background: rgba(var(--accent-rgb, 59, 130, 246), 0.12);
}

.entry-check {
  margin-left: auto;
  font-size: 14px;
}

.check-on {
  color: var(--accent);
  font-weight: bold;
}

.check-off {
  color: var(--fg-dim);
}

.cluster-action-bar {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 12px 0 0;
  border-top: 1px solid var(--border, #333);
  margin-top: 12px;
  font-size: 13px;
}

.btn-cluster-transfer {
  background: var(--accent);
  color: #fff;
  border: none;
  border-radius: 6px;
  padding: 6px 16px;
  font-size: 13px;
  cursor: pointer;
}

.btn-cluster-transfer:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.btn-cluster-clear {
  background: none;
  border: 1px solid var(--border);
  color: var(--fg-muted);
  border-radius: 6px;
  padding: 6px 12px;
  font-size: 12px;
  cursor: pointer;
}
</style>

``



================================================
FILE: C:\Users\qu\Desktop\物理科学与技术论题\TS2\mcp\server\web\src\views\GameView.vue
================================================

``vue
<template>
  <div class="game-view">
    <svg class="world-map" :viewBox="`0 0 ${W} ${H}`"
         @mousedown="onPointerDown" @mousemove="onPointerMove" @mouseup="onPointerUp"
         @mouseleave="onPointerUp">
      <defs>
        <radialGradient id="bg-grad" cx="50%" cy="50%" r="60%">
          <stop offset="0%" stop-color="#0f0f1a"/>
          <stop offset="100%" stop-color="#06060e"/>
        </radialGradient>
      </defs>
      <rect width="100%" height="100%" fill="url(#bg-grad)"/>
      <!-- 世界 → 大陆 → 区域 -->
      <!-- 不活跃大陆：只显示区域名和入口光环 -->
      <g v-for="r in inactiveRegions" :key="r.id"
         :transform="`translate(${r.cx},${r.cy})`"
         class="region-glow" @click="travelTo(r.id)">
        <circle :r="r.r" fill="none" :stroke="r.color" stroke-width="1" opacity="0.3"/>
        <circle :r="6" :fill="r.color" opacity="0.6"/>
        <text text-anchor="middle" dy="14" :fill="r.color" font-size="11" font-weight="600"
              opacity="0.7" style="user-select:none;">{{ r.label }}</text>
        <text text-anchor="middle" dy="28" fill="rgba(255,255,255,0.25)" font-size="9"
              style="user-select:none;">{{ r.count }} 概念 · 点击旅行</text>
      </g>
      <!-- 活跃大陆连接线 -->
      <line v-for="(e, i) in edges" :key="'e'+i"
            :x1="e.x1" :y1="e.y1" :x2="e.x2" :y2="e.y2"
            :stroke="e.color" :stroke-width="e.w" :opacity="e.op"/>
      <!-- 活跃大陆概念节点 -->
      <g v-for="n in activeNodes" :key="n.id"
         :transform="`translate(${n.x},${n.y})`"
         :style="n.fossil ? 'opacity:0.2' : ''"
         @mousedown.prevent="onNodeDown(n, $event)">
        <circle :r="n.r" :fill="n.color"
                :stroke="n === selectedNode ? '#fff' : 'rgba(255,255,255,0.3)'"
                :stroke-width="n === selectedNode ? 2.5 : 0.5"
                :style="n.entropy > 0.7 ? 'animation:pulse-node 1.5s ease-in-out infinite;' : ''"/>
        <text text-anchor="middle" :dy="n.r > 10 ? 4 : 0" font-size="8" fill="rgba(255,255,255,0.85)"
              style="pointer-events:none; user-select:none;" v-if="n.r > 7">{{ labelShort(n.label) }}</text>
        <text v-if="n.fossil" text-anchor="middle" dy="0" font-size="13" fill="#f84"
              style="pointer-events:none; user-select:none;">💀</text>
      </g>
      <!-- 玩家标记 -->
      <text v-if="activeRegionId" :x="playerX" :y="playerY" text-anchor="middle" font-size="16"
            fill="#4fc3f7" style="pointer-events:none; user-select:none; filter:drop-shadow(0 0 6px #4fc3f7);">✦</text>
    </svg>

    <!-- 顶栏 -->
    <div class="top-bar">
      <span class="game-title">🎮 知识大陆</span>
      <span class="pill era">{{ store.era || '寒武纪' }}</span>
      <span class="pill">☯ {{ store.globalEntropy.toFixed(2) }}</span>
      <span class="pill">{{ activeRegionLabel }}</span>
      <span class="pill">🧬 {{ activeCount }}</span>
      <span class="pill">⏱ {{ store.tick }}</span>
      <span v-if="unprocessed > 0" class="pill alert">📡 {{ unprocessed }}</span>
    </div>

    <!-- 通知 -->
    <transition name="drop">
      <div v-if="toast" class="toast" @click="toast.action?.()">
        <span class="ti">{{ toast.icon }}</span>
        <div class="tb">
          <div class="tm">{{ toast.msg }}</div>
          <div v-if="toast.detail" class="td">{{ toast.detail }}</div>
          <span v-if="toast.btn" class="tbtn">{{ toast.btn }}→</span>
        </div>
      </div>
    </transition>

    <!-- 详情面板 -->
    <transition name="slide">
      <div v-if="selectedNode" class="detail">
        <div class="dh">
          <span class="dl">{{ selectedNode.label }}</span>
          <button class="dx" @click="selectedNode=null">✕</button>
        </div>
        <div class="ds">
          <span>深度 {{ selectedNode.depth.toFixed(1) }}</span>
          <span>新鲜 {{ (selectedNode.freshness*100).toFixed(0) }}%</span>
          <span :style="selectedNode.entropy > 0.6 ? 'color:#ff8a65;' : ''">熵 {{ selectedNode.entropy.toFixed(2) }}</span>
          <span v-if="selectedNode.fossil" class="fb">💀 化石</span>
        </div>
        <div v-if="nodeSources.length" class="dr">
          <div class="drh">📎 来源</div>
          <div v-for="s in nodeSources" :key="s.source_id || s.file_path" class="sl" @click="goSource(s)">
            <span class="sb" :class="s.source_type">{{ typeTag[s.source_type] || s.source_type }}</span>
            <span class="sx">{{ s.label || s.file_path || s.source_id }}</span>
            <span class="sa">↗</span>
          </div>
        </div>
        <div v-if="!selectedNode.fossil" class="da">
          <button class="ba" @click="doDive(selectedNode.id)">🔍 深潜</button>
          <button class="ba" @click="startCross(selectedNode.id)">🧬 交叉</button>
          <button class="ba" @click="doExpress([selectedNode.id])">✍️ 表达</button>
        </div>
        <div v-if="crossMode" class="ch">
          再点选一个概念完成交叉
          <button class="bc" @click="crossMode=''">取消</button>
        </div>
      </div>
    </transition>

    <!-- 底栏 -->
    <div class="bottom">
      <div class="bm">
        <input v-model="inputText" class="bi" placeholder="记录线下活动…" @keyup.enter="doRecord"/>
        <button class="bb" @click="doRecord" :disabled="!inputText.trim() || recording">📝 记录</button>
        <button class="bb" @click="doObserve" :disabled="observing">📡 {{ observing ? '…' : '导入' }}</button>
      </div>
      <div class="bt">
        <button class="btb" @click="doTick" :disabled="ticking">⏱ 演化</button>
        <button class="btb" @click="centerMap">⟲ 居中</button>
        <button class="btb" @click="doSyncFromCourse" :disabled="syncing">📚 同步</button>
        <span class="bt-hint" v-if="unprocessed > 0">📡 {{ unprocessed }} 条待导入</span>
        <span class="bt-hint region-name">📍 {{ activeRegionLabel }}</span>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, onMounted, onUnmounted } from 'vue'
import { useRouter } from 'vue-router'
import { useEcosystemStore } from '../stores/ecosystem'

const router = useRouter()
const store = useEcosystemStore()

const W = 800, H = 500
const selectedNode = ref<any>(null)
const crossMode = ref('')
const activeRegionId = ref('')
const inputText = ref('')
const recording = ref(false)
const observing = ref(false)
const ticking = ref(false)
const syncing = ref(false)
let simTimer = 0

const toast = ref<{ icon: string; msg: string; detail?: string; btn?: string; action?: () => void } | null>(null)
let toastTimer = 0

const typeTag: Record<string, string> = {
  note: '📝', pdf: '📄', course: '🎓', checkpoint: '📌', project: '📁', code: '💻',
}

// ── 线程调色板 ──
const THREAD_PALETTE: Record<string, string> = {
  A: '#4fc3f7', P: '#ff8a65', CS: '#81c784', DE: '#ce93d8',
  SE: '#ffd54f', D: '#4dd0e1', M: '#e57373', N: '#a1887f',
  C: '#7986cb', S: '#4db6ac', LM: '#f06292', DS: '#aed581',
  BIO: '#ba68c8', UNKNOWN: '#78909c',
}

// ── 概念 → 线程映射 ──
function conceptThread(c: any): string {
  for (const [tid, t] of Object.entries(store.threads)) {
    if ((t as any).concept_ids?.includes(c.id)) return tid.replace('thread_', '')
  }
  return 'UNKNOWN'
}

// ── 区域列表 ──
const regions = computed(() => {
  const allThreads = store.threads ?? {}
  const threadKeys = Object.keys(allThreads).filter(k => k.startsWith('thread_'))
  if (!threadKeys.length) return []
  const conceptIdsByThread: Record<string, string[]> = {}
  for (const c of Object.values(store.concepts)) {
    const tid = conceptThread(c as any)
    if (!conceptIdsByThread[tid]) conceptIdsByThread[tid] = []
    conceptIdsByThread[tid].push((c as any).id)
  }
  const groups: Record<string, number> = {}
  for (const [, t] of Object.entries(allThreads)) {
    const short = (t as any).id?.replace('thread_', '') ?? 'UNKNOWN'
    groups[short] = (t as any).concept_ids?.length ?? conceptIdsByThread[short]?.length ?? 0
  }
  return Object.entries(groups)
    .filter(([_, n]) => n >= 1)
    .map(([tid, n], i, arr) => {
      const angle = (i / arr.length) * Math.PI * 2 - Math.PI / 2
      const dist = Math.min(W, H) * 0.30
      return {
        id: tid,
        label: allThreads[`thread_${tid}`]?.label ?? `${tid}域`,
        count: n,
        cx: W / 2 + Math.cos(angle) * dist,
        cy: H / 2 + Math.sin(angle) * dist,
        r: 30 + Math.min(n, 200) * 0.15,
        color: THREAD_PALETTE[tid] || '#78909c',
        conceptIds: conceptIdsByThread[tid] ?? [],
      }
    })
})

const inactiveRegions = computed(() => regions.value.filter(r => r.id !== activeRegionId.value))
const activeRegion = computed(() => regions.value.find(r => r.id === activeRegionId.value))
const activeRegionLabel = computed(() => activeRegion.value?.label ?? '未选择')
const activeCount = computed(() => activeRegion.value?.count ?? 0)
const conceptCount = computed(() => store.totalConceptCount || Object.keys(store.concepts).length)
const unprocessed = computed(() => (store as any).unprocessedEvents ?? 0)

// ── 活跃节点（力导向） ──
const activeNodes = ref<any[]>([])
let nodeMap: Record<string, any> = {}

function buildActiveGraph() {
  const region = activeRegion.value
  if (!region) { activeNodes.value = []; nodeMap = {}; return }

  // 使用已加载的概念（neighborhood）构建力导向图
  const concepts = Object.values(store.concepts) as any[]
  const N = concepts.length
  if (!N) { activeNodes.value = []; nodeMap = {}; return }

  const palette = ['#4fc3f7', '#26c6da', '#29b6f6', '#42a5f5', '#5c6bc0', '#7e57c2', '#ab47bc']
  const C = Math.min(concepts.length, 7)

  const ns = concepts.map((c: any, i: number) => {
    const angle = (i / N) * Math.PI * 2
    const cv = region.cx + Math.cos(angle) * 60 + (Math.random() - 0.5) * 40
    const cy = region.cy + Math.sin(angle) * 60 + (Math.random() - 0.5) * 40
    const r = 4 + Math.min(c.depth, 8) * 1.8 + (c.parent_ids?.length ? 2 : 0)
    return {
      id: c.id, label: c.label,
      x: cv, y: cy, vx: 0, vy: 0, r,
      depth: c.depth, freshness: c.freshness, entropy: c.entropy,
      fossil: c.is_fossilized, parent_ids: c.parent_ids ?? [],
      related_ids: c.related_ids ?? {},
      color: palette[i % C],
    }
  })
  nodeMap = Object.fromEntries(ns.map((n: any) => [n.id, n]))
  activeNodes.value = ns
  startSim()
}

// ── 力导向 ──
function startSim() {
  cancelAnimationFrame(simTimer)
  const step = () => {
    const ns = activeNodes.value
    if (!ns.length) return
    const reg = activeRegion.value
    let moved = false
    for (const a of ns) {
      // 向区域中心拉力
      if (reg) {
        a.vx += (reg.cx - a.x) * 0.0015
        a.vy += (reg.cy - a.y) * 0.0015
      }
      // 节点间库仑力
      for (const b of ns) {
        if (a.id >= b.id) continue
        const dx = a.x - b.x, dy = a.y - b.y
        const d = Math.sqrt(dx * dx + dy * dy) || 1
        const f = 80 / (d * d + 10)
        a.vx += dx / d * f; a.vy += dy / d * f
        b.vx -= dx / d * f; b.vy -= dy / d * f
      }
      // 连接弹簧力
      for (const [oid, str] of Object.entries(a.related_ids)) {
        const b = nodeMap[oid]
        if (!b) continue
        const dx = b.x - a.x, dy = b.y - a.y
        const k = (str as number) * 0.008
        a.vx += dx * k; a.vy += dy * k
        b.vx -= dx * k; b.vy -= dy * k
      }
      // 父节点吸引力（子靠近父）
      for (const pid of a.parent_ids) {
        const p = nodeMap[pid]
        if (!p) continue
        a.vx += (p.x - a.x) * 0.01
        a.vy += (p.y - a.y) * 0.01
      }
      a.vx *= 0.88; a.vy *= 0.88
      if (Math.abs(a.vx) > 0.05 || Math.abs(a.vy) > 0.05) moved = true
      a.x += a.vx; a.y += a.vy
      if (reg) {
        const bound = reg.r + 40
        a.x = Math.max(reg.cx - bound, Math.min(reg.cx + bound, a.x))
        a.y = Math.max(reg.cy - bound, Math.min(reg.cy + bound, a.y))
      }
    }
    if (moved) simTimer = requestAnimationFrame(step)
  }
  simTimer = requestAnimationFrame(step)
}

const edges = computed(() => {
  const es: any[] = []
  const ns = activeNodes.value
  const seen = new Set<string>()
  for (const e of store.neighborEdges) {
    const a = nodeMap[e.source], b = nodeMap[e.target]
    if (!a || !b) continue
    const key = [e.source, e.target].sort().join(':')
    if (seen.has(key)) continue
    seen.add(key)
    es.push({
      x1: a.x, y1: a.y, x2: b.x, y2: b.y,
      w: e.strength * 1.5 + 0.2, op: e.strength * 0.2 + 0.05,
      color: a.color,
    })
  }
  for (const n of ns) {
    for (const [oid, str] of Object.entries(n.related_ids)) {
      const m = nodeMap[oid]
      if (!m) continue
      const key = [n.id, oid].sort().join(':')
      if (seen.has(key)) continue
      seen.add(key)
      es.push({
        x1: n.x, y1: n.y, x2: m.x, y2: m.y,
        w: (str as number) * 1.5 + 0.2, op: (str as number) * 0.2 + 0.05,
        color: n.color,
      })
    }
  }
  return es
})

const playerX = computed(() => activeNodes.value.length ? activeNodes.value[0]?.x ?? W / 2 : W / 2)
const playerY = computed(() => activeNodes.value.length ? activeNodes.value[0]?.y ?? H / 2 : H / 2)

const nodeSources = computed(() => {
  if (!selectedNode.value) return []
  return (store.concepts[selectedNode.value.id] as any)?.source_refs ?? []
})

function labelShort(label: string) {
  return label.length > 5 ? label.slice(0, 5) + '…' : label
}

function displayLabel(cid: string) {
  return store.concepts[cid]?.label ?? cid.slice(0, 8)
}

// ── 旅行 ──
function travelTo(regionId: string) {
  if (regionId === activeRegionId.value) return
  activeRegionId.value = regionId
  cancelAnimationFrame(simTimer)
  // 到达新大陆时异步加载周围概念
  const tid = `thread_${regionId}`
  const firstConcept = store.threads[tid]?.concept_ids?.[0]
  if (firstConcept) {
    store.fetchNeighborhood(firstConcept)
  }
  showToast('🚀', `已到达 ${regions.value.find(r => r.id === regionId)?.label ?? regionId}`,
    `${activeRegion.value?.count ?? 0} 个概念待探索`)
}

// ── 交互 ──
function onPointerDown() {}
function onPointerUp() {}
function onPointerMove() {}

function onNodeDown(n: any, _ev: MouseEvent) {
  if (crossMode.value) {
    doCross(crossMode.value, n.id)
    crossMode.value = ''
    return
  }
  selectedNode.value = n
  // 玩家跟随
  const idx = activeNodes.value.findIndex(a => a.id === n.id)
  if (idx > 0) {
    const [item] = activeNodes.value.splice(idx, 1)
    activeNodes.value.unshift(item)
  }
}

function centerMap() {
  if (regions.value.length) {
    travelTo(regions.value[0].id)
  }
}

// ── 通知 ──
function showToast(icon: string, msg: string, detail?: string, btn?: string, action?: () => void) {
  clearTimeout(toastTimer)
  toast.value = { icon, msg, detail, btn, action }
  toastTimer = window.setTimeout(() => { toast.value = null }, 5000)
}

// ── 操作 ──
async function doRecord() {
  if (!inputText.value.trim() || recording.value) return
  const text = inputText.value
  inputText.value = ''
  recording.value = true
  try {
    const res = await store.doRecord(text)
    const data = res || {}
    showToast('📝', data.narrative || '已记录')
    buildActiveGraph()
  } catch { showToast('⚠️', '记录失败') }
  finally { recording.value = false }
}

async function doObserve() {
  observing.value = true
  try {
    const res = await store.doObserve()
    showToast('📡', `已导入 ${res?.processed ?? 0} 条TS2活动`)
    buildActiveGraph()
  } catch { showToast('⚠️', '导入失败') }
  finally { observing.value = false }
}

async function doTick() {
  ticking.value = true
  try {
    const res = await store.doTick()
    showToast('⏱', res?.message || '演化完成')
    await store.fetchInspirations()
    if (store.inspirations.length) {
      const top = store.inspirations[0]
      showToast('💡', `灵感: ${top.label}`, top.description)
    }
    buildActiveGraph()
  } catch { showToast('⚠️', '演化失败') }
  finally { ticking.value = false }
}

async function doDive(cid: string) {
  const res = await store.doDive(cid)
  if (res) showToast('🔍', res.narrative || `深潜: ${displayLabel(cid)}`)
  buildActiveGraph()
}

async function doSyncFromCourse() {
  syncing.value = true
  try {
    const res = await store.doSync()
    if (res?.synced) showToast('📚', `已同步 ${res.synced} 个概念`)
    else showToast('💬', '已是最新')
    buildActiveGraph()
  } catch { showToast('⚠️', '同步失败') }
  finally { syncing.value = false }
}

async function doCross(a: string, b: string) {
  const res = await store.doCross(a, b)
  if (res) showToast('🧬', res.narrative || `交叉: ${displayLabel(a)} × ${displayLabel(b)}`)
  buildActiveGraph()
}

function startCross(cid: string) { crossMode.value = cid }

async function doExpress(cids: string[]) {
  const lbl = cids.length === 1 ? displayLabel(cids[0]) : `${cids.length}个概念`
  const res = await store.doExpress(cids)
  if (res) showToast('✍️', res.narrative || `表达: ${lbl}`)
  buildActiveGraph()
}

function goSource(s: any) {
  const fp = s.file_path || ''
  const sid = s.source_id || ''
  switch (s.source_type) {
    case 'pdf': router.push(`/pdf?file=${encodeURIComponent(fp)}`); break
    case 'note': router.push(`/slides?file=${encodeURIComponent(fp)}`); break
    case 'course': router.push(`/courses?highlight=${encodeURIComponent(sid)}`); break
    case 'project': router.push(`/projects?highlight=${encodeURIComponent(sid)}`); break
    case 'checkpoint': router.push(`/agent/checkpoints/${encodeURIComponent(sid)}`); break
    case 'code': router.push(`/files?path=${encodeURIComponent(fp)}`); break
    default: if (fp) router.push(`/files?path=${encodeURIComponent(fp)}`)
  }
}

// ── 生命周期 ──
watch(() => store.concepts, () => {
  if (Object.keys(store.concepts).length) buildActiveGraph()
}, { deep: true })

onMounted(async () => {
  await store.fetchState()
  // 加载玩家当前位置的邻域
  const playerCid = store.player.current_concept_id
  if (playerCid) {
    await store.fetchNeighborhood(playerCid)
  }
  // 确定活跃区域
  if (regions.value.length) {
    const playerTid = store.player.current_thread_id
    const startId = playerTid?.replace('thread_', '')
      ?? (regions.value.find(r => {
        const tid = `thread_${r.id}`
        const cids = store.threads[tid]?.concept_ids ?? []
        return playerCid && cids.includes(playerCid)
      })?.id)
      ?? regions.value[0].id
    activeRegionId.value = startId
    buildActiveGraph()
    showToast('🌱', `知识大陆 · ${conceptCount.value} 个概念`,
      `发现 ${regions.value.length} 个区域，点击其他区域旅行`)
  } else {
    showToast('💬', '知识大陆还是空的', '点 📚 同步从课程加载', '同步', doSyncFromCourse)
  }
})

onUnmounted(() => { cancelAnimationFrame(simTimer); clearTimeout(toastTimer) })
</script>

<style scoped>
.game-view { position: relative; width: 100%; height: 100%; background: #0a0a12; overflow: hidden; }
.world-map { width: 100%; height: 100%; display: block; cursor: grab; }
.world-map:active { cursor: grabbing; }

.top-bar {
  position: absolute; top: 0; left: 0; right: 0; display: flex; align-items: center;
  gap: 6px; padding: 8px 12px;
  background: linear-gradient(180deg, rgba(0,0,0,0.8) 0%, transparent 100%);
  pointer-events: none; z-index: 10;
}
.game-title { font-weight: 700; font-size: 14px; color: #fff; margin-right: 4px; }
.pill { font-size: 10px; color: rgba(255,255,255,0.6); background: rgba(255,255,255,0.08); padding: 2px 7px; border-radius: 4px; white-space: nowrap; }
.pill.era { background: #4fc3f7; color: #000; font-weight: 600; }
.pill.alert { background: #ff5252; color: #fff; animation: pulse 1.5s infinite; }
@keyframes pulse { 0%,100% { opacity: 1; } 50% { opacity: 0.6; } }
@keyframes pulse-node { 0%,100% { opacity: 1; } 50% { opacity: 0.5; } }

.region-glow { cursor: pointer; transition: opacity 0.2s; }
.region-glow:hover { opacity: 1 !important; }
.region-glow:hover circle:first-child { stroke-width: 2; }

.toast {
  position: absolute; top: 42px; left: 12px; right: 12px; z-index: 20;
  display: flex; gap: 8px; align-items: flex-start;
  background: rgba(0,0,0,0.88); backdrop-filter: blur(8px);
  border: 1px solid rgba(255,255,255,0.1); border-radius: 8px;
  padding: 10px 12px; cursor: pointer;
}
.ti { font-size: 18px; line-height: 1.4; }
.tb { flex: 1; min-width: 0; }
.tm { font-size: 13px; color: #fff; }
.td { font-size: 11px; color: rgba(255,255,255,0.5); margin-top: 2px; }
.tbtn { font-size: 11px; color: #4fc3f7; font-weight: 600; margin-top: 4px; display: inline-block; }
.drop-enter-active, .drop-leave-active { transition: all 0.3s ease; }
.drop-enter-from, .drop-leave-to { opacity: 0; transform: translateY(-16px); }

.detail {
  position: absolute; bottom: 76px; left: 12px; right: 12px; z-index: 15;
  background: rgba(16,16,30,0.95); backdrop-filter: blur(12px);
  border: 1px solid rgba(255,255,255,0.1); border-radius: 10px; padding: 14px;
  max-height: 45vh; overflow-y: auto;
}
.dh { display: flex; justify-content: space-between; align-items: center; margin-bottom: 6px; }
.dl { font-weight: 700; font-size: 16px; color: #fff; }
.dx { background: none; border: none; color: rgba(255,255,255,0.3); font-size: 16px; cursor: pointer; }
.ds { display: flex; gap: 8px; font-size: 11px; color: rgba(255,255,255,0.5); margin-bottom: 6px; flex-wrap: wrap; }
.fb { color: #ff8a65; }
.dr { margin-bottom: 6px; }
.drh { font-size: 11px; color: rgba(255,255,255,0.4); margin-bottom: 3px; }
.sl { display: flex; align-items: center; gap: 5px; padding: 3px 0; cursor: pointer; font-size: 12px; border-radius: 4px; }
.sl:hover { background: rgba(255,255,255,0.05); }
.sb { font-size: 10px; padding: 0 4px; }
.sb.pdf { color: #ff5252; } .sb.note { color: #448aff; } .sb.course { color: #69f0ae; }
.sb.project { color: #ff8a65; } .sb.checkpoint { color: #b388ff; } .sb.code { color: #4dd0e1; }
.sx { color: rgba(255,255,255,0.7); flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.sa { color: #4fc3f7; font-size: 13px; }
.da { display: flex; gap: 6px; flex-wrap: wrap; }
.ba {
  background: rgba(255,255,255,0.06); border: 1px solid rgba(255,255,255,0.15);
  border-radius: 6px; padding: 5px 10px; font-size: 11px; cursor: pointer;
  color: #fff; transition: all 0.15s;
}
.ba:hover { background: #4fc3f7; border-color: #4fc3f7; color: #000; }
.ch { font-size: 11px; color: #4fc3f7; margin-top: 6px; display: flex; gap: 8px; align-items: center; }
.bc { background: none; border: 1px solid rgba(255,255,255,0.15); color: rgba(255,255,255,0.5); border-radius: 4px; padding: 2px 8px; font-size: 10px; cursor: pointer; }

.bottom {
  position: absolute; bottom: 0; left: 0; right: 0;
  background: rgba(8,8,16,0.92); backdrop-filter: blur(8px);
  border-top: 1px solid rgba(255,255,255,0.06); padding: 8px 12px; z-index: 10;
}
.bm { display: flex; gap: 6px; }
.bi {
  flex: 1; background: rgba(255,255,255,0.06); border: 1px solid rgba(255,255,255,0.1);
  border-radius: 6px; padding: 7px 10px; color: #fff; font-size: 13px; font-family: inherit;
}
.bi::placeholder { color: rgba(255,255,255,0.25); }
.bi:focus { outline: none; border-color: #4fc3f7; }
.bb {
  background: #4fc3f7; color: #000; border: none; border-radius: 6px;
  padding: 7px 12px; font-size: 12px; cursor: pointer; font-weight: 600; white-space: nowrap;
}
.bb:disabled { opacity: 0.35; }
.bt { display: flex; gap: 6px; align-items: center; margin-top: 6px; flex-wrap: wrap; }
.btb {
  background: rgba(255,255,255,0.04); border: 1px solid rgba(255,255,255,0.08);
  border-radius: 4px; padding: 3px 9px; font-size: 11px; cursor: pointer; color: rgba(255,255,255,0.5);
}
.btb:hover { background: rgba(255,255,255,0.1); }
.btb:disabled { opacity: 0.3; }
.bt-hint { font-size: 10px; color: #ff5252; margin-left: auto; }
.bt-hint.region-name { color: #4fc3f7; margin-left: 0; }

.slide-enter-active, .slide-leave-active { transition: all 0.2s ease; }
.slide-enter-from, .slide-leave-to { opacity: 0; transform: translateY(12px); }
</style>

``



================================================
FILE: C:\Users\qu\Desktop\物理科学与技术论题\TS2\mcp\server\web\src\views\PdfReaderView.vue
================================================

``vue
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

``



================================================
FILE: C:\Users\qu\Desktop\物理科学与技术论题\TS2\mcp\server\web\src\views\ProjectsView.vue
================================================

``vue
<template>
  <div class="view">
    <header class="view-header">
      <h1>项目</h1>
    </header>
    <div class="view-body">
      <div v-if="loading" class="loading">加载中...</div>
      <div v-else-if="projects.length === 0" class="empty">暂无项目</div>
      <div v-else class="project-list">
        <div v-for="proj in projects" :key="proj.path || proj.name" class="project-card" @click="openProject(proj)">
          <div class="project-header">
            <span class="project-icon">🚀</span>
            <div class="project-info">
              <span class="project-title">{{ proj.title || proj.name || '未命名项目' }}</span>
              <span v-if="proj.path" class="project-path">{{ proj.path }}</span>
            </div>
          </div>
          <div v-if="proj.file_count" class="project-meta">{{ proj.file_count }} 个文件</div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { getProjects } from '../api'

const projects = ref<any[]>([])
const loading = ref(true)

onMounted(async () => {
  const bootstrap = (window as any).__TS2_BOOTSTRAP__
  if (bootstrap?.projects) {
    projects.value = Array.isArray(bootstrap.projects) ? bootstrap.projects : []
    delete bootstrap.projects
  }
  try {
    const res = await getProjects()
    const data = res.data?.data ?? res.data
    projects.value = Array.isArray(data) ? data : []
  } catch {
    // keep cached
  } finally {
    loading.value = false
  }
})

function openProject(proj: any) {
  if (proj.path) {
    window.location.hash = `/files`
  }
}
</script>

<style scoped>
.project-list {
  padding: 12px;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.project-card {
  background: var(--card);
  border: 1px solid var(--border);
  border-radius: 10px;
  padding: 14px;
  cursor: pointer;
  transition: border-color 0.15s;
}

.project-card:hover {
  border-color: var(--accent);
}

.project-header {
  display: flex;
  align-items: center;
  gap: 10px;
}

.project-icon {
  font-size: 20px;
}

.project-info {
  flex: 1;
  min-width: 0;
}

.project-title {
  display: block;
  font-size: 15px;
  font-weight: 600;
  color: var(--fg);
}

.project-path {
  display: block;
  font-size: 11px;
  color: var(--fg-muted);
  margin-top: 2px;
}

.project-meta {
  font-size: 12px;
  color: var(--fg-muted);
  margin-top: 6px;
  padding-left: 30px;
}

.loading, .empty {
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 200px;
  color: var(--fg-muted);
  font-size: 14px;
}
</style>

``



================================================
FILE: C:\Users\qu\Desktop\物理科学与技术论题\TS2\mcp\server\web\src\views\ResourcesView.vue
================================================

``vue
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

``



================================================
FILE: C:\Users\qu\Desktop\物理科学与技术论题\TS2\mcp\server\web\src\views\SettingsView.vue
================================================

``vue
<template>
  <div class="view">
    <header class="view-header">
      <h1>设置</h1>
    </header>
    <div class="view-body">
      <!-- 外观设置 (unified with video settings) -->
      <div class="settings-section">
        <h2 class="section-title">🎨 外观</h2>
        <div class="setting-row">
          <label class="setting-label">主题</label>
          <select class="setting-select" :value="themeMode" @change="onThemeChange">
            <option value="dark">深色</option>
            <option value="light">浅色</option>
            <option value="black">纯黑（AMOLED）</option>
            <option value="auto">跟随系统</option>
          </select>
        </div>
      </div>

      <!-- 网络访问控制（仅浏览器端/服务器端显示，参考思源笔记） -->
      <div class="settings-section" v-if="!isNative">
        <h2 class="section-title">网络访问控制</h2>

        <div class="setting-row">
          <div class="toggle-row">
            <div>
              <label class="setting-label">允许局域网访问</label>
              <span class="setting-desc">允许同一局域网内的设备访问服务器</span>
            </div>
            <label class="toggle">
              <input type="checkbox" v-model="netSettings.allow_lan" @change="saveNetSettings" />
              <span class="toggle-slider"></span>
            </label>
          </div>
        </div>

        <div class="setting-row">
          <div class="toggle-row">
            <div>
              <label class="setting-label">允许公用网络访问</label>
              <span class="setting-desc">允许公用网络（如校园网、公共WiFi）的设备访问</span>
            </div>
            <label class="toggle">
              <input type="checkbox" v-model="netSettings.allow_public_network" @change="saveNetSettings" />
              <span class="toggle-slider"></span>
            </label>
          </div>
        </div>

        <div class="setting-row">
          <div class="toggle-row">
            <div>
              <label class="setting-label">允许 USB 连接</label>
              <span class="setting-desc">允许通过 adb reverse 的 USB 连接访问</span>
            </div>
            <label class="toggle">
              <input type="checkbox" v-model="netSettings.allow_usb" @change="saveNetSettings" />
              <span class="toggle-slider"></span>
            </label>
          </div>
        </div>

        <div class="setting-row">
          <label class="setting-label">监听地址</label>
          <span class="setting-value mono">{{ netSettings.effective_host }}:{{ netSettings.port }}</span>
          <span class="setting-hint" v-if="!netSettings.allow_lan && !netSettings.allow_public_network">
            仅本机可访问（127.0.0.1）
          </span>
        </div>

        <div class="btn-group">
          <button class="btn-action" @click="doConfigureFirewall" :disabled="firewallLoading">
            {{ firewallLoading ? '配置中...' : '配置防火墙' }}
          </button>
          <button class="btn-action btn-secondary" @click="doSetNetworkPrivate" :disabled="privateLoading" v-if="netSettings.platform === 'Windows'">
            {{ privateLoading ? '设置中...' : '设为专用网络' }}
          </button>
          <button class="btn-action btn-outline" @click="doCheckNetworkAccess" :disabled="checkLoading">
            {{ checkLoading ? '检测中...' : '检测网络状态' }}
          </button>
        </div>

        <div v-if="firewallMsg" class="msg-box" :class="firewallOk ? 'msg-ok' : 'msg-err'">
          {{ firewallMsg }}
        </div>
        <div v-if="privateMsg" class="msg-box" :class="privateOk ? 'msg-ok' : 'msg-err'">
          {{ privateMsg }}
        </div>

        <!-- 网络检测结果 -->
        <div v-if="networkCheck" class="check-result">
          <div class="check-item">
            <span>本机访问</span>
            <span :class="networkCheck.localhost_accessible ? 'tag-ok' : 'tag-fail'">
              {{ networkCheck.localhost_accessible ? '正常' : '不可用' }}
            </span>
          </div>
          <div class="check-item">
            <span>局域网访问</span>
            <span :class="networkCheck.lan_accessible ? 'tag-ok' : 'tag-fail'">
              {{ networkCheck.lan_accessible ? '正常' : '不可用' }}
            </span>
          </div>
          <div class="check-item">
            <span>防火墙规则</span>
            <span :class="networkCheck.firewall_rule_exists ? 'tag-ok' : 'tag-fail'">
              {{ networkCheck.firewall_rule_exists ? '已配置' : '未配置' }}
            </span>
          </div>
          <div v-for="(iface, idx) in networkCheck.interfaces" :key="idx" class="check-item">
            <span>{{ iface.ip }}</span>
            <span :class="iface.accessible ? 'tag-ok' : 'tag-fail'">
              {{ iface.accessible ? '可达' : '不可达' }}
            </span>
          </div>
          <div v-for="profile in networkCheck.profiles" :key="profile.name" class="check-item">
            <span>{{ profile.name }}</span>
            <span :class="profile.category === 'Private' ? 'tag-ok' : 'tag-warn'">
              {{ profile.category === 'Private' ? '专用网络' : '公用网络' }}
            </span>
          </div>
          <div v-if="networkCheck.recommendations.length > 0" class="recommendations">
            <div v-for="(rec, idx) in networkCheck.recommendations" :key="idx" class="rec-item">
              {{ rec }}
            </div>
          </div>
        </div>
      </div>

      <!-- 公网穿透（frp） -->
      <div class="settings-section">
        <h2 class="section-title">🌐 公网穿透</h2>
        <p class="section-desc" style="font-size:12px;color:#888;margin:-8px 0 8px">
          通过隧道将本服务暴露到公网，适用于与手机不在同一局域网时访问
        </p>

        <!-- 隧道类型 -->
        <div class="setting-row">
          <label class="setting-label">隧道类型</label>
          <div class="tunnel-type-tabs">
            <button
              v-for="t in [{v:'localtunnel',l:'localtunnel (推荐)'},{v:'serveo',l:'serveo.net'},{v:'bore',l:'bore.pub'},{v:'frp',l:'frp (需VPS)'},{v:'cloudflare',l:'Cloudflare'}]"
              :key="t.v"
              :class="['tab-btn', tunnelSettings.tunnel_type === t.v ? 'active' : '']"
              @click="setTunnelType(t.v)"
            >{{ t.l }}</button>
          </div>
          <span class="setting-hint" v-if="tunnelSettings.tunnel_type === 'localtunnel'">
            使用 npx localtunnel，访问 https://xxx.loca.lt（推荐，最稳定）
          </span>
          <span class="setting-hint" v-if="tunnelSettings.tunnel_type === 'serveo'">
            用 SSH 连接到 serveo.net，可能被校园网封锁
          </span>
          <span class="setting-hint" v-if="tunnelSettings.tunnel_type === 'bore'">
            需要下载 bore 可执行文件，无需 VPS
          </span>
          <span class="setting-hint" v-if="tunnelSettings.tunnel_type === 'frp'">
            需要自建 VPS，配置最灵活
          </span>
          <span class="setting-hint" v-if="tunnelSettings.tunnel_type === 'cloudflare'">
            使用 cloudflared，需 Cloudflare 账号，稳定且支持自定义域名
          </span>
        </div>

        <!-- 隧道状态 -->
        <div class="setting-row" v-if="tunnelStatus">
          <span class="setting-label">状态</span>
          <span class="setting-value" :class="tunnelStatus.status === 'running' ? 'tag-ok' : tunnelStatus.status === 'error' ? 'tag-fail' : ''">
            {{ tunnelStatus.status === 'running' ? '已连接' : tunnelStatus.status === 'error' ? '错误' : tunnelStatus.status === 'starting' ? '启动中...' : '未启动' }}
          </span>
        </div>
        <div class="setting-row" v-if="tunnelStatus?.public_url">
          <span class="setting-label">公网地址</span>
          <a :href="tunnelStatus.public_url" target="_blank" class="setting-link mono">
            {{ tunnelStatus.public_url }}
          </a>
        </div>
        <div class="setting-row" v-if="tunnelStatus?.error">
          <span class="setting-label">错误</span>
          <span class="setting-value tag-fail" style="font-size:11px">{{ tunnelStatus.error }}</span>
        </div>

        <div class="btn-group">
          <button class="btn-action" @click="doTunnelStart" :disabled="tunnelLoading || tunnelStatus?.status === 'running'">
            {{ tunnelLoading ? '启动中...' : '启动隧道' }}
          </button>
          <button class="btn-action btn-secondary" @click="doTunnelStop" :disabled="tunnelLoading || tunnelStatus?.status === 'stopped'">
            停止隧道
          </button>
          <button class="btn-action btn-outline" @click="loadTunnelStatus">
            刷新状态
          </button>
        </div>

        <!-- frp 配置（仅 frp 类型显示） -->
        <div class="config-block" v-if="tunnelSettings.tunnel_type === 'frp'">
          <h3 class="config-title">frps 服务器配置</h3>
          <div class="setting-row">
            <label class="setting-label">服务器地址</label>
            <input v-model="tunnelSettings.server_addr" class="setting-input" placeholder="VPS 公网 IP" @change="saveTunnelSettings" />
          </div>
          <div class="setting-row">
            <label class="setting-label">服务器端口</label>
            <input v-model.number="tunnelSettings.server_port" class="setting-input" type="number" placeholder="7000" @change="saveTunnelSettings" />
          </div>
          <div class="setting-row">
            <label class="setting-label">认证令牌</label>
            <input v-model="tunnelSettings.token" class="setting-input" type="password" placeholder="frps token" @change="saveTunnelSettings" />
          </div>
          <div class="setting-row">
            <label class="setting-label">本地端口</label>
            <input v-model.number="tunnelSettings.local_port" class="setting-input" type="number" placeholder="6906" @change="saveTunnelSettings" />
          </div>
          <div class="setting-row">
            <label class="setting-label">远程端口</label>
            <input v-model.number="tunnelSettings.remote_port" class="setting-input" type="number" placeholder="6906" @change="saveTunnelSettings" />
          </div>
          <div class="setting-row">
            <label class="setting-label">frpc 路径</label>
            <input v-model="tunnelSettings.frpc_path" class="setting-input" placeholder="留空自动查找" @change="saveTunnelSettings" />
          </div>
          <div v-if="tunnelSettings.token_preview" class="setting-row">
            <span class="setting-label">令牌预览</span>
            <span class="setting-value mono" style="font-size:11px;color:#888">{{ tunnelSettings.token_preview }}</span>
          </div>
        </div>

        <!-- bore 配置（仅 bore 类型显示） -->
        <div class="config-block" v-if="tunnelSettings.tunnel_type === 'bore'">
          <h3 class="config-title">bore 配置</h3>
          <div class="setting-row">
            <label class="setting-label">本地端口</label>
            <input v-model.number="tunnelSettings.local_port" class="setting-input" type="number" placeholder="6906" @change="saveTunnelSettings" />
          </div>
          <div class="setting-row">
            <label class="setting-label">bore 路径</label>
            <input v-model="tunnelSettings.bore_path" class="setting-input" placeholder="留空自动查找" @change="saveTunnelSettings" />
          </div>
          <div class="setting-row">
            <a href="https://github.com/ekzhang/bore/releases" target="_blank" class="setting-link">
              下载 bore (Windows: bore.exe)
            </a>
          </div>
        </div>

        <!-- serveo 配置（仅 serveo 类型显示） -->
        <div class="config-block" v-if="tunnelSettings.tunnel_type === 'serveo'">
          <h3 class="config-title">serveo 配置</h3>
          <div class="setting-row">
            <label class="setting-label">本地端口</label>
            <input v-model.number="tunnelSettings.local_port" class="setting-input" type="number" placeholder="6906" @change="saveTunnelSettings" />
          </div>
          <div class="setting-row">
            <label class="setting-label">子域名（可选）</label>
            <input v-model="tunnelSettings.subdomain" class="setting-input" placeholder="留空则随机分配" @change="saveTunnelSettings" />
          </div>
        </div>

        <!-- localtunnel 配置（仅 localtunnel 类型显示） -->
        <div class="config-block" v-if="tunnelSettings.tunnel_type === 'localtunnel'">
          <h3 class="config-title">localtunnel 配置</h3>
          <div class="setting-row">
            <label class="setting-label">选择本地实例</label>
            <div class="setting-input-row">
              <select v-model.number="tunnelSettings.local_port" class="setting-select" @change="saveTunnelSettings">
                <option v-for="inst in localInstances" :key="inst.port" :value="inst.port">
                  端口 {{ inst.port }}{{ inst.self ? ' (当前实例)' : '' }}{{ inst.workspace ? ' - ' + (inst.workspace.split(/[/\\]/).pop() || '') : '' }}
                </option>
              </select>
              <button class="btn-refresh" @click="scanLocalInstances" :disabled="scanningInstances" title="刷新实例列表">
                {{ scanningInstances ? '...' : '↻' }}
              </button>
            </div>
          </div>
        </div>

        <!-- Cloudflare 配置（仅 cloudflare 类型显示） -->
        <div class="config-block" v-if="tunnelSettings.tunnel_type === 'cloudflare'">
          <h3 class="config-title">Cloudflare Tunnel 配置</h3>
          <div class="setting-row">
            <label class="setting-label">Tunnel Token</label>
            <input v-model="tunnelSettings.cf_token" class="setting-input" type="password" placeholder="eyJh..." @change="saveTunnelSettings" />
          </div>
          <div class="setting-row">
            <label class="setting-label">域名（可选）</label>
            <input v-model="tunnelSettings.cf_domain" class="setting-input" placeholder="ts2.your-domain.com" @change="saveTunnelSettings" />
          </div>
          <div class="setting-row">
            <label class="setting-label">本地端口</label>
            <div class="setting-input-row">
              <select v-model.number="tunnelSettings.local_port" class="setting-select" @change="saveTunnelSettings">
                <option v-for="inst in localInstances" :key="inst.port" :value="inst.port">
                  端口 {{ inst.port }}{{ inst.self ? ' (当前实例)' : '' }}{{ inst.workspace ? ' - ' + (inst.workspace.split(/[/\\]/).pop() || '') : '' }}
                </option>
              </select>
              <button class="btn-refresh" @click="scanLocalInstances" :disabled="scanningInstances" title="刷新实例列表">
                {{ scanningInstances ? '...' : '↻' }}
              </button>
            </div>
          </div>
          <div class="setting-row">
            <a href="https://developers.cloudflare.com/cloudflare-one/connections/connect-apps/install-and-setup/tunnel-guide/" target="_blank" class="setting-link">
              查看 Cloudflare Tunnel 配置指南
            </a>
          </div>
          <div class="setting-hint" style="margin-top:4px">
            安装 cloudflared: Windows: winget install Cloudflare.cloudflared
          </div>
        </div>

        <div v-if="tunnelMsg" class="msg-box" :class="tunnelMsgType === 'ok' ? 'msg-ok' : 'msg-err'">
          {{ tunnelMsg }}
        </div>
      </div>

      <!-- 数据同步 -->
      <div class="settings-section">
        <h2 class="section-title">🔄 数据同步</h2>
        <p class="section-desc" style="font-size:12px;color:#888;margin:-8px 0 8px">
          将本地任务与书签数据同步到服务器
        </p>

        <div class="setting-row">
          <span class="setting-label">上次同步</span>
          <span class="setting-value">{{ lastSyncTimeText }}</span>
        </div>

        <div class="setting-row">
          <div class="toggle-row">
            <div>
              <label class="setting-label">自动同步</label>
              <span class="setting-desc">每 5 分钟自动同步一次</span>
            </div>
            <label class="toggle">
              <input type="checkbox" v-model="autoSync" @change="toggleAutoSync" />
              <span class="toggle-slider"></span>
            </label>
          </div>
        </div>

        <div class="btn-group">
          <button class="btn-action" @click="doSync" :disabled="syncing">
            {{ syncing ? '同步中...' : '立即同步' }}
          </button>
        </div>

        <div v-if="syncResult" class="sync-result">
          <div class="check-item">
            <span>拉取任务</span>
            <span class="tag-ok">{{ syncResult.pull }} 条</span>
          </div>
          <div class="check-item">
            <span>推送任务</span>
            <span class="tag-ok">{{ syncResult.pushed }} 条</span>
          </div>
          <div class="check-item">
            <span>冲突</span>
            <span :class="syncResult.conflicts > 0 ? 'tag-warn' : 'tag-ok'">{{ syncResult.conflicts }} 条</span>
          </div>
          <div class="check-item">
            <span>拉取书签</span>
            <span class="tag-ok">{{ syncResult.bookmarksPull }} 条</span>
          </div>
          <div class="check-item">
            <span>推送书签</span>
            <span class="tag-ok">{{ syncResult.bookmarksPushed }} 条</span>
          </div>
          <div class="check-item">
            <span>拉取项目</span>
            <span class="tag-ok">{{ syncResult.projectsPull }} 条</span>
          </div>
          <div class="check-item">
            <span>推送项目</span>
            <span class="tag-ok">{{ syncResult.projectsPushed }} 条</span>
          </div>
        </div>

        <div v-if="syncMsg" class="msg-box" :class="syncOk ? 'msg-ok' : 'msg-err'">
          {{ syncMsg }}
        </div>
      </div>

      <!-- 关键路径检测 -->
      <div class="settings-section">
        <h2 class="section-title">📊 关键路径检测</h2>
        <p class="section-desc" style="font-size:12px;color:#888;margin:-8px 0 8px">
          基于任务依赖关系和持续时间，计算项目关键路径（CPM）
        </p>

        <div class="btn-group">
          <button class="btn-action" @click="doCriticalPath" :disabled="cpLoading">
            {{ cpLoading ? '分析中...' : '分析关键路径' }}
          </button>
        </div>

        <div v-if="cpResult" class="sync-result" style="margin-top:12px">
          <div class="check-item">
            <span>项目总工期</span>
            <span class="tag-ok">{{ formatDuration(cpResult.project_duration) }}</span>
          </div>
          <div class="check-item">
            <span>总任务数</span>
            <span class="setting-value">{{ cpResult.total_tasks }}</span>
          </div>
          <div class="check-item">
            <span>关键任务数</span>
            <span :class="cpResult.critical_tasks > 0 ? 'tag-warn' : 'tag-ok'">{{ cpResult.critical_tasks }}</span>
          </div>
        </div>

        <div v-if="cpResult?.critical_path?.length" style="margin-top:8px">
          <div style="font-size:12px;color:var(--fg-muted);margin-bottom:6px">关键路径任务</div>
          <div v-for="task in cpResult.critical_path" :key="task.id" class="cp-task-item">
            <span class="cp-task-title">{{ task.title }}</span>
            <span class="cp-task-duration">{{ formatDuration(task.duration) }}</span>
            <span class="cp-task-float">裕度: {{ task.total_float }}分钟</span>
          </div>
        </div>

        <div v-if="cpMsg" class="msg-box" :class="cpOk ? 'msg-ok' : 'msg-err'">
          {{ cpMsg }}
        </div>
      </div>

      <!-- 自动补全 -->
      <div class="settings-section">
        <h2 class="section-title">✏️ 编辑器自动补全</h2>
        <p class="section-desc" style="font-size:12px;color:#888;margin:-8px 0 8px">
          在 Vditor 编辑器中输入触发字符弹出补全列表（需重新打开文件生效）
        </p>

        <div class="setting-row">
          <div class="toggle-row">
            <div>
              <label class="setting-label">LaTeX 公式补全</label>
              <span class="setting-desc">输入 \ 触发，补全 LaTeX 命令</span>
            </div>
            <label class="toggle">
              <input type="checkbox" v-model="acConfig.latex" @change="saveAcConfig" />
              <span class="toggle-slider"></span>
            </label>
          </div>
        </div>

        <div class="setting-row">
          <div class="toggle-row">
            <div>
              <label class="setting-label">代码片段补全</label>
              <span class="setting-desc">输入 ! 触发，补全表格、代码块等模板</span>
            </div>
            <label class="toggle">
              <input type="checkbox" v-model="acConfig.snippets" @change="saveAcConfig" />
              <span class="toggle-slider"></span>
            </label>
          </div>
        </div>

        <div class="setting-row">
          <div class="toggle-row">
            <div>
              <label class="setting-label">关键词字典补全</label>
              <span class="setting-desc">输入 @ 触发中文，& 触发英文</span>
            </div>
            <label class="toggle">
              <input type="checkbox" v-model="acConfig.dicts" @change="saveAcConfig" />
              <span class="toggle-slider"></span>
            </label>
          </div>
        </div>

        <!-- 字典管理 -->
        <div v-if="acConfig.dicts" class="config-block" style="margin-top:12px">
          <h3 class="config-title">关键词字典</h3>

          <div v-for="(group, gIdx) in acConfig.dictGroups" :key="gIdx" class="dict-group">
            <div class="dict-group-header">
              <label class="toggle" style="transform:scale(0.8)">
                <input type="checkbox" :checked="group.enabled" @change="toggleDictGroup(gIdx)" />
                <span class="toggle-slider"></span>
              </label>
              <span class="dict-group-name" :class="{ disabled: !group.enabled }">{{ group.name }}</span>
              <span class="dict-group-count">{{ group.entries.length }} 条</span>
              <button class="btn-dict-toggle" @click="acEditingDict = acEditingDict === gIdx ? null : gIdx">
                {{ acEditingDict === gIdx ? '收起' : '编辑' }}
              </button>
              <button class="btn-dict-del" @click="removeDict(gIdx)" title="删除字典">✕</button>
            </div>

            <!-- 展开编辑词条 -->
            <div v-if="acEditingDict === gIdx" class="dict-entries">
              <div v-for="(entry, eIdx) in group.entries" :key="eIdx" class="dict-entry-row">
                <span class="dict-entry-key">{{ entry.keyword }}</span>
                <span class="dict-entry-val">{{ entry.value }}</span>
                <span v-if="entry.desc" class="dict-entry-desc">{{ entry.desc }}</span>
                <button class="btn-dict-entry-del" @click="removeDictEntry(gIdx, eIdx)">✕</button>
              </div>
              <div class="dict-add-entry">
                <input v-model="acNewEntryKeyword" class="setting-input dict-input" placeholder="关键词" />
                <input v-model="acNewEntryValue" class="setting-input dict-input" placeholder="补全值" />
                <input v-model="acNewEntryDesc" class="setting-input dict-input dict-input-desc" placeholder="说明(可选)" />
                <button class="btn-action" style="padding:6px 10px;font-size:11px" @click="addDictEntry(gIdx)">添加</button>
              </div>
            </div>
          </div>

          <!-- 添加自定义字典 -->
          <div class="dict-add-group">
            <input v-model="acNewDictName" class="setting-input dict-input" placeholder="新字典名称（如：计算机名词）" @keyup.enter="addCustomDict" />
            <button class="btn-action" style="padding:6px 10px;font-size:11px" @click="addCustomDict">添加字典</button>
          </div>

          <button class="btn-action btn-outline" style="margin-top:8px;font-size:11px;padding:4px 10px" @click="resetDictsToDefault">
            恢复默认字典
          </button>
        </div>
      </div>

      <!-- 服务器连接 -->
      <div class="settings-section">
        <h2 class="section-title">服务器连接</h2>
        <div class="setting-row">
          <span class="setting-label">状态</span>
          <span class="setting-value">
            <span v-if="appMode === 'local'" style="color:var(--fg-muted)">未连接（本地模式）</span>
            <span v-else-if="appMode === 'server_connected'" style="color:#4ade80">已连接</span>
            <span v-else style="color:#ef4444">已断开</span>
          </span>
        </div>
        <div class="setting-row" v-if="appMode !== 'server_connected'">
          <span class="setting-label">服务器地址</span>
          <input v-model="srvUrl" class="setting-input" placeholder="http://192.168.x.x:6906" />
        </div>
        <div class="setting-row" v-if="showAuthFields">
          <span class="setting-label">{{ srvNeedToken ? 'Token' : '' }} {{ srvNeedCode ? '授权码' : '' }}</span>
          <input v-if="srvNeedToken" v-model="srvToken" class="setting-input" type="password" placeholder="API Token" />
          <input v-if="srvNeedCode" v-model="srvCode" class="setting-input" type="password" placeholder="授权码" />
        </div>
        <div class="btn-group">
          <button v-if="appMode !== 'server_connected'" class="btn-action" @click="doConnectServer" :disabled="srvConnecting">
            {{ srvConnecting ? '连接中...' : '连接服务器' }}
          </button>
          <button v-if="appMode === 'server_connected'" class="btn-action btn-danger" @click="doDisconnectServer">
            断开连接
          </button>
          <pre v-if="srvError" class="srv-error-box">{{ srvError }}</pre>
        </div>

        <!-- 地址历史 -->
        <div v-if="addressHistory.length > 0" class="address-list">
          <div class="list-header">
            <span>历史地址</span>
            <button class="btn-clear" @click="clearAllHistory">清空</button>
          </div>
          <div
            v-for="(item, idx) in addressHistory"
            :key="idx"
            class="address-item"
            :class="{ current: item.url === currentURL }"
            @click="switchTo(item.url)"
          >
            <div class="address-info">
              <span class="address-url">{{ item.url }}</span>
              <span class="address-meta">
                {{ formatTime(item.lastUsed) }}
                <span v-if="item.success" class="tag-ok">成功</span>
                <span v-else class="tag-fail">失败</span>
              </span>
            </div>
            <div class="address-actions">
              <span v-if="item.url === currentURL" class="tag-current">当前</span>
              <button class="btn-del" @click.stop="removeHistory(idx)">✕</button>
            </div>
          </div>
        </div>
      </div>

      <div class="settings-section">
        <h2 class="section-title">连接状态</h2>
        <div class="setting-row">
          <span class="setting-label">WebSocket</span>
          <span class="setting-value" :class="{ connected: wsConnected }">
            {{ wsConnected ? '已连接' : '未连接' }}
          </span>
        </div>
        <div class="setting-row">
          <span class="setting-label">同步状态</span>
          <span class="setting-value">{{ syncStatusText }}</span>
        </div>
        <div class="setting-row">
          <span class="setting-label">运行环境</span>
          <span class="setting-value">{{ isNative ? '原生 App' : '浏览器' }}</span>
        </div>
      </div>

      <div class="settings-section">
        <h2 class="section-title">🎬 视频设置</h2>
        <div class="video-settings-tabs">
          <button
            v-for="tab in videoSettingTabs"
            :key="tab.key"
            class="vs-tab"
            :class="{ active: activeVideoTab === tab.key }"
            @click="activeVideoTab = tab.key"
          >{{ tab.label }}</button>
        </div>
        <VideoSettingsSection :active-section="activeVideoTab" />
      </div>

      <div class="settings-section" v-if="serverInfo">
        <h2 class="section-title">服务器信息</h2>
        <div class="setting-row">
          <span class="setting-label">版本</span>
          <span class="setting-value">{{ serverInfo.version }}</span>
        </div>
        <div class="setting-row">
          <span class="setting-label">局域网 IP</span>
          <span class="setting-value">{{ serverInfo.local_ip }}</span>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, onUnmounted, computed } from 'vue'
import { useVideoSettingsStore } from '../stores/videoSettings'
import VideoSettingsSection from '../components/VideoSettingsSection.vue'
import {
  getServerURL, setServerURL, testServerConnection, isNativeApp,
  getNetworkSettings, setNetworkSettings, configureFirewall, setNetworkPrivate, checkNetworkAccess,
  getStats, getProjects, criticalPath,
  tunnelStatus as getTunnelStatusApi, tunnelStart, tunnelStop, tunnelSettingsGet, tunnelSettingsUpdate,
  clusterInstances,
  getAuthInfo, loginAuth, getAuthCode, getApiToken, setCredentials, diagnoseLogin,
} from '../api'
import { useWebSocket } from '../composables/useWebSocket'
import { useAppMode } from '../composables/useAppMode'
import { useTasksStore } from '../stores/tasks'
import { useTimetableStore } from '../stores/timetable'
import { loadAutocompleteConfig, saveAutocompleteConfig, DEFAULT_DICT_GROUPS } from '../autocomplete'
import type { AutocompleteConfig } from '../autocomplete'

const HISTORY_KEY = 'ts2_address_history'
const { appMode, setAppMode } = useAppMode()
const videoSettingsStore = useVideoSettingsStore()
const themeMode = computed(() => videoSettingsStore.settings.themeMode)
function onThemeChange(e: Event) {
  videoSettingsStore.update({ themeMode: (e.target as HTMLSelectElement).value as any })
}

interface HistoryEntry {
  url: string
  lastUsed: number
  success: boolean
}

const serverInfo = ref<any>(null)
const syncStatusText = ref('未知')
const isNative = ref(false)
const addressHistory = ref<HistoryEntry[]>([])
const activeVideoTab = ref('appearance')

// 服务器连接状态
const currentURL = ref(getServerURL())
const srvUrl = ref(getServerURL())
const srvToken = ref('')
const srvCode = ref('')
const srvConnecting = ref(false)
const srvError = ref('')
const srvNeedToken = ref(false)
const srvNeedCode = ref(false)

const showAuthFields = computed(() => {
  return appMode.value !== 'server_connected' && (srvNeedToken.value || srvNeedCode.value)
})
const videoSettingTabs = [
  { key: 'appearance', label: '外观' },
  { key: 'playback', label: '播放' },
  { key: 'content', label: '内容' },
  { key: 'history', label: '历史' },
  { key: 'about', label: '关于' },
]

// 网络设置状态
const netSettings = ref({
  allow_lan: true,
  allow_public_network: true,
  allow_usb: true,
  effective_host: '0.0.0.0',
  port: 6906,
  platform: '',
  firewall_configured: false,
})
const firewallLoading = ref(false)
const firewallMsg = ref('')
const firewallOk = ref(false)
const privateLoading = ref(false)
const privateMsg = ref('')
const privateOk = ref(false)
const checkLoading = ref(false)
const networkCheck = ref<any>(null)

// 隧道状态
const tunnelStatus = ref<any>(null)
const tunnelSettings = ref({
  tunnel_type: 'localtunnel',
  server_addr: '',
  server_port: 7000,
  token: '',
  local_port: 6906,
  remote_port: 6906,
  subdomain: '',
  frpc_path: '',
  bore_path: '',
  cf_token: '',
  cf_domain: '',
  token_preview: '',
})
const tunnelLoading = ref(false)
const tunnelMsg = ref('')
const tunnelMsgType = ref<'ok' | 'err'>('ok')

// 本地实例（用于端口选择）
interface LocalInstance {
  port: number
  url: string
  version: string
  local_ip: string
  self?: boolean
  workspace?: string
}
const localInstances = ref<LocalInstance[]>([])
const scanningInstances = ref(false)

const { wsConnected } = useWebSocket()
const timetableStore = useTimetableStore()

// ─── 数据同步 ────────────────────────────────────────
const tasksStore = useTasksStore()
const syncing = ref(false)
const syncResult = ref<{ pull: number; pushed: number; conflicts: number; bookmarksPull: number; bookmarksPushed: number; projectsPull: number; projectsPushed: number } | null>(null)
const syncMsg = ref('')
const syncOk = ref(false)
const lastSyncTime = ref<number | null>(null)
const autoSync = ref(false)
let autoSyncTimer: ReturnType<typeof setInterval> | null = null

// ─── 自动补全 ────────────────────────────────────────
const acConfig = ref<AutocompleteConfig>(loadAutocompleteConfig())
const acNewDictName = ref('')
const acNewEntryKeyword = ref('')
const acNewEntryValue = ref('')
const acNewEntryDesc = ref('')
const acEditingDict = ref<number | null>(null)  // 正在编辑的字典索引

// ─── 关键路径检测 ────────────────────────────────────────
const cpLoading = ref(false)
const cpResult = ref<any>(null)
const cpMsg = ref('')
const cpOk = ref(false)

function formatDuration(minutes: number): string {
  if (!minutes) return '0分钟'
  if (minutes < 60) return `${minutes}分钟`
  const h = Math.floor(minutes / 60)
  const m = minutes % 60
  if (h < 24) return m > 0 ? `${h}小时${m}分钟` : `${h}小时`
  const d = Math.floor(h / 24)
  const rh = h % 24
  return rh > 0 ? `${d}天${rh}小时` : `${d}天`
}

async function doCriticalPath() {
  cpLoading.value = true
  cpMsg.value = ''
  cpResult.value = null
  try {
    const res = await criticalPath()
    const data = res.data?.data ?? res.data
    if (data) {
      cpResult.value = data
      cpOk.value = true
      cpMsg.value = data.critical_tasks > 0
        ? `检测到 ${data.critical_tasks} 个关键任务，总工期 ${formatDuration(data.project_duration)}`
        : '未检测到关键路径（可能所有任务已完成或无依赖关系）'
    }
  } catch (e: any) {
    cpOk.value = false
    cpMsg.value = e?.message || '关键路径分析失败'
  } finally {
    cpLoading.value = false
  }
}

function saveAcConfig() {
  saveAutocompleteConfig(acConfig.value)
}

function toggleDictGroup(idx: number) {
  acConfig.value.dictGroups[idx].enabled = !acConfig.value.dictGroups[idx].enabled
  saveAcConfig()
}

function addCustomDict() {
  const name = acNewDictName.value.trim()
  if (!name) return
  acConfig.value.dictGroups.push({ name, enabled: true, entries: [] })
  acNewDictName.value = ''
  saveAcConfig()
}

function removeDict(idx: number) {
  acConfig.value.dictGroups.splice(idx, 1)
  saveAcConfig()
}

function addDictEntry(dictIdx: number) {
  const keyword = acNewEntryKeyword.value.trim()
  const value = acNewEntryValue.value.trim()
  if (!keyword || !value) return
  acConfig.value.dictGroups[dictIdx].entries.push({
    keyword,
    value,
    desc: acNewEntryDesc.value.trim() || undefined,
  })
  acNewEntryKeyword.value = ''
  acNewEntryValue.value = ''
  acNewEntryDesc.value = ''
  saveAcConfig()
}

function removeDictEntry(dictIdx: number, entryIdx: number) {
  acConfig.value.dictGroups[dictIdx].entries.splice(entryIdx, 1)
  saveAcConfig()
}

function resetDictsToDefault() {
  acConfig.value.dictGroups = JSON.parse(JSON.stringify(DEFAULT_DICT_GROUPS))
  saveAcConfig()
}

const LAST_SYNC_KEY = 'ts2_last_sync_time'
const AUTO_SYNC_KEY = 'ts2_auto_sync'

const lastSyncTimeText = computed(() => {
  if (!lastSyncTime.value) return '从未同步'
  const d = new Date(lastSyncTime.value)
  const now = new Date()
  const diffMin = Math.floor((now.getTime() - d.getTime()) / 60000)
  if (diffMin < 1) return '刚刚'
  if (diffMin < 60) return `${diffMin}分钟前`
  const diffHr = Math.floor(diffMin / 60)
  if (diffHr < 24) return `${diffHr}小时前`
  return `${d.getMonth() + 1}/${d.getDate()} ${d.getHours()}:${String(d.getMinutes()).padStart(2, '0')}`
})

async function doSync() {
  syncing.value = true
  syncMsg.value = ''
  syncResult.value = null
  try {
    // 获取当前 projects 数据
    let projects: any[] = []
    try {
      const projRes = await getProjects()
      const projData = projRes.data?.data ?? projRes.data
      projects = Array.isArray(projData) ? projData : []
    } catch { /* ignore */ }
    const result = await tasksStore.syncWithServer([], projects)
    syncResult.value = result
    lastSyncTime.value = Date.now()
    localStorage.setItem(LAST_SYNC_KEY, String(lastSyncTime.value))
    syncOk.value = true
    syncMsg.value = '同步完成'
  } catch (e: any) {
    syncOk.value = false
    syncMsg.value = e?.message || '同步失败'
  } finally {
    syncing.value = false
  }
}

function toggleAutoSync() {
  if (autoSync.value) {
    autoSyncTimer = setInterval(() => {
      doSync()
    }, 5 * 60 * 1000)
    localStorage.setItem(AUTO_SYNC_KEY, '1')
  } else {
    if (autoSyncTimer) {
      clearInterval(autoSyncTimer)
      autoSyncTimer = null
    }
    localStorage.removeItem(AUTO_SYNC_KEY)
  }
}

function loadHistory(): HistoryEntry[] {
  try {
    const raw = localStorage.getItem(HISTORY_KEY)
    return raw ? JSON.parse(raw) : []
  } catch { return [] }
}

function saveHistory(list: HistoryEntry[]) {
  localStorage.setItem(HISTORY_KEY, JSON.stringify(list.slice(0, 10)))
}

function addHistory(url: string, success: boolean) {
  const list = loadHistory().filter(h => h.url !== url)
  list.unshift({ url, lastUsed: Date.now(), success })
  saveHistory(list)
  addressHistory.value = list
}

function removeHistory(idx: number) {
  const list = loadHistory()
  list.splice(idx, 1)
  saveHistory(list)
  addressHistory.value = list
}

function clearAllHistory() {
  localStorage.removeItem(HISTORY_KEY)
  addressHistory.value = []
}

function formatTime(ts: number): string {
  const d = new Date(ts)
  const now = new Date()
  const diffMin = Math.floor((now.getTime() - d.getTime()) / 60000)
  if (diffMin < 1) return '刚刚'
  if (diffMin < 60) return `${diffMin}分钟前`
  const diffHr = Math.floor(diffMin / 60)
  if (diffHr < 24) return `${diffHr}小时前`
  return `${d.getMonth() + 1}/${d.getDate()} ${d.getHours()}:${String(d.getMinutes()).padStart(2, '0')}`
}

async function switchTo(url: string) {
  srvUrl.value = url
  await doConnectServer()
}

async function doConnectServer() {
  const url = srvUrl.value?.trim() || ''
  if (!url) { srvError.value = '请输入服务器地址'; return }
  srvConnecting.value = true
  srvError.value = ''
  try {
    const ok = await testServerConnection(url)
    if (!ok) { srvError.value = '无法连接服务器'; return }
    const info = await getAuthInfo(url)
    if (!info.needAuth) {
	setCredentials(srvCode.value.trim() || getAuthCode(), srvToken.value.trim() || getApiToken())
        setServerURL(url)
    	currentURL.value = url
    	addHistory(url, true)
    	setAppMode('server_connected')
    	await Promise.all([tasksStore.switchToServer(), timetableStore.switchToServer()])
    	return
    }
    srvNeedToken.value = info.hasToken
    srvNeedCode.value = info.hasAuthCode
    const code = srvCode.value.trim() || getAuthCode()
    const token = srvToken.value.trim() || getApiToken()
    if ((!info.hasAuthCode || code) && (!info.hasToken || token)) {
      const loginResult = await loginAuth(code, token, url)
      if (loginResult.ok) {
	setCredentials(srvCode.value.trim() || getAuthCode(), srvToken.value.trim() || getApiToken())
        setServerURL(url)
	currentURL.value = url
	addHistory(url, true)
	setAppMode('server_connected')
	await Promise.all([tasksStore.switchToServer(), timetableStore.switchToServer()])
	return
      }
      // 登录失败，构造详细错误信息
      let errorMsg = loginResult.detail || '登录失败'
      // 根据错误类型附加建议
      if (loginResult.errorType === 'network' || loginResult.errorType === 'cors') {
        errorMsg += '\n\n💡 建议：\n- 检查服务器是否在运行\n- 确认IP地址和端口正确\n- 如果是Capacitor环境，请确保服务器与设备在同一网络'
      } else if (loginResult.errorType === 'auth_failed') {
        errorMsg += '\n\n💡 请确认授权码和Token是否正确'
      } else if (loginResult.errorType === 'timeout') {
        errorMsg += '\n\n💡 请检查网络连接，或尝试增加超时时间'
      }
      srvError.value = errorMsg
      // 自动运行诊断附加信息（可选）
      try {
        const diag = await diagnoseLogin(code, token, url)
        srvError.value += '\n\n📋 诊断:\n' + diag.join('\n')
      } catch {}
      return
    }
  } catch (e: any) {
    srvError.value = `连接失败: ${e?.message || e}`
  } finally {
    srvConnecting.value = false
  }
}

// 网络设置操作
async function loadNetSettings() {
  try {
    const res = await getNetworkSettings()
    const data = res.data?.data ?? res.data
    if (data) {
      netSettings.value = {
        allow_lan: data.allow_lan ?? true,
        allow_public_network: data.allow_public_network ?? true,
        allow_usb: data.allow_usb ?? true,
        effective_host: data.host ?? '0.0.0.0',
        port: data.port ?? 6906,
        platform: data.platform ?? '',
        firewall_configured: data.firewall_configured ?? false,
      }
    }
  } catch { /* ignore */ }
}

async function scanLocalInstances() {
  scanningInstances.value = true
  try {
    const res = await clusterInstances()
    const data = res.data?.data ?? res.data
    if (data) {
      // 合并 self 和 peers
      const instances: LocalInstance[] = []
      if (data.self) {
        instances.push(data.self)
      }
      if (data.peers) {
        instances.push(...data.peers)
      }
      localInstances.value = instances.sort((a, b) => a.port - b.port)
      // 如果当前设置的端口不在列表中，添加它
      const currentPort = tunnelSettings.value.local_port
      if (currentPort && !instances.find(i => i.port === currentPort)) {
        localInstances.value.push({
          port: currentPort,
          url: `http://127.0.0.1:${currentPort}`,
          version: 'unknown',
          local_ip: '',
        })
        localInstances.value.sort((a, b) => a.port - b.port)
      }
    }
  } catch {
    localInstances.value = []
  } finally {
    scanningInstances.value = false
  }
}

async function saveNetSettings() {
  try {
    await setNetworkSettings({
      allow_lan: netSettings.value.allow_lan,
      allow_public_network: netSettings.value.allow_public_network,
      allow_usb: netSettings.value.allow_usb,
    })
    // 重新加载以获取更新后的 effective_host
    await loadNetSettings()
  } catch { /* ignore */ }
}

async function doConfigureFirewall() {
  firewallLoading.value = true
  firewallMsg.value = ''
  try {
    const res = await configureFirewall(true)
    const data = res.data?.data ?? res.data
    firewallOk.value = data?.success ?? res.data?.code === 0
    firewallMsg.value = data?.message || data?.msg || (firewallOk.value ? '防火墙配置成功' : '防火墙配置失败')
  } catch (e: any) {
    firewallOk.value = false
    firewallMsg.value = e?.response?.data?.message || '防火墙配置请求失败'
  } finally {
    firewallLoading.value = false
  }
}

async function doSetNetworkPrivate() {
  privateLoading.value = true
  privateMsg.value = ''
  try {
    const res = await setNetworkPrivate()
    const data = res.data?.data ?? res.data
    privateOk.value = data?.success ?? res.data?.code === 0
    privateMsg.value = data?.message || data?.msg || (privateOk.value ? '已设为专用网络' : '设置失败')
  } catch (e: any) {
    privateOk.value = false
    privateMsg.value = e?.response?.data?.message || '设置请求失败'
  } finally {
    privateLoading.value = false
  }
}

async function doCheckNetworkAccess() {
  checkLoading.value = true
  try {
    const res = await checkNetworkAccess()
    const data = res.data?.data ?? res.data
    networkCheck.value = data
  } catch {
    networkCheck.value = null
  } finally {
    checkLoading.value = false
  }
}

// ─── 隧道操作 ────────────────────────────────────────

async function loadTunnelStatus() {
  try {
    const res = await getTunnelStatusApi()
    tunnelStatus.value = res.data?.data ?? res.data
  } catch {
    tunnelStatus.value = null
  }
}

async function loadTunnelSettings() {
  try {
    const res = await tunnelSettingsGet()
    const data = res.data?.data ?? res.data
    if (data) {
      tunnelSettings.value = {
        tunnel_type: data.tunnel_type || 'localtunnel',
        server_addr: data.server_addr || '',
        server_port: data.server_port || 7000,
        token: data.token || '',
        local_port: data.local_port || 6906,
        remote_port: data.remote_port || 6906,
        subdomain: data.subdomain || '',
        frpc_path: data.frpc_path || '',
        bore_path: data.bore_path || '',
        cf_token: data.cf_token || '',
        cf_domain: data.cf_domain || '',
        token_preview: data.token_preview || '',
      }
    }
  } catch { /* ignore */ }
}

async function setTunnelType(type: string) {
  tunnelSettings.value.tunnel_type = type
  await saveTunnelSettings()
}

async function saveTunnelSettings() {
  try {
    const res = await tunnelSettingsUpdate({
      tunnel_type: tunnelSettings.value.tunnel_type,
      server_addr: tunnelSettings.value.server_addr,
      server_port: tunnelSettings.value.server_port,
      token: tunnelSettings.value.token,
      local_port: tunnelSettings.value.local_port,
      remote_port: tunnelSettings.value.remote_port,
      subdomain: tunnelSettings.value.subdomain,
      frpc_path: tunnelSettings.value.frpc_path,
      bore_path: tunnelSettings.value.bore_path,
    })
    const data = res.data?.data ?? res.data
    if (data?.token) {
      tunnelSettings.value.token_preview = data.token_preview || ''
      tunnelSettings.value.token = ''
    }
    tunnelMsg.value = '配置已保存'
    tunnelMsgType.value = 'ok'
  } catch (e: any) {
    tunnelMsg.value = e?.response?.data?.msg || '保存失败'
    tunnelMsgType.value = 'err'
  }
}

async function doTunnelStart() {
  tunnelLoading.value = true
  tunnelMsg.value = ''
  try {
    const res = await tunnelStart()
    const data = res.data?.data ?? res.data
    if (res.data?.code === 0 || data?.success) {
      tunnelMsg.value = data?.message || '隧道启动成功'
      tunnelMsgType.value = 'ok'
    } else {
      tunnelMsg.value = data?.message || '隧道启动失败'
      tunnelMsgType.value = 'err'
    }
    await loadTunnelStatus()
  } catch (e: any) {
    tunnelMsg.value = e?.response?.data?.msg || '启动失败'
    tunnelMsgType.value = 'err'
  } finally {
    tunnelLoading.value = false
  }
}

async function doTunnelStop() {
  tunnelLoading.value = true
  tunnelMsg.value = ''
  try {
    const res = await tunnelStop()
    const data = res.data?.data ?? res.data
    tunnelMsg.value = data?.message || '隧道已停止'
    tunnelMsgType.value = 'ok'
    await loadTunnelStatus()
  } catch (e: any) {
    tunnelMsg.value = e?.response?.data?.msg || '停止失败'
    tunnelMsgType.value = 'err'
  } finally {
    tunnelLoading.value = false
  }
}

onMounted(async () => {
  isNative.value = isNativeApp()
  addressHistory.value = loadHistory()
  // 恢复上次同步时间
  const savedSyncTime = localStorage.getItem(LAST_SYNC_KEY)
  if (savedSyncTime) lastSyncTime.value = Number(savedSyncTime)
  // 恢复自动同步状态
  if (localStorage.getItem(AUTO_SYNC_KEY) === '1') {
    autoSync.value = true
    toggleAutoSync()
  }
  // 浏览器端加载网络设置
  if (!isNative.value) {
    await loadNetSettings()
  }
  // 加载隧道状态、配置和本地实例
  await Promise.all([loadTunnelStatus(), loadTunnelSettings(), scanLocalInstances()])
  try {
    const res = await getStats()
    const data = res.data?.data ?? res.data
    if (data) {
      syncStatusText.value = '在线'
      serverInfo.value = data
    }
  } catch { /* ignore */ }
})

onUnmounted(() => {
  if (autoSyncTimer) {
    clearInterval(autoSyncTimer)
    autoSyncTimer = null
  }
})
</script>

<style scoped>
.settings-section {
  padding: 16px;
  border-bottom: 1px solid var(--border);
}

.section-title {
  font-size: 14px;
  font-weight: 600;
  color: var(--fg-muted);
  margin-bottom: 12px;
  text-transform: uppercase;
  letter-spacing: 0.5px;
}

.setting-row {
  margin-bottom: 12px;
}

.setting-label {
  display: block;
  font-size: 13px;
  color: var(--fg);
  margin-bottom: 4px;
}

.setting-desc {
  display: block;
  font-size: 11px;
  color: var(--fg-muted);
  margin-top: 2px;
}

.setting-hint {
  display: block;
  font-size: 11px;
  color: var(--danger);
  margin-top: 2px;
}

.setting-input-row {
  display: flex;
  gap: 8px;
}

.setting-input {
  flex: 1;
  padding: 8px 12px;
  border: 1px solid var(--border);
  border-radius: 6px;
  background: var(--bg);
  color: var(--fg);
  font-size: 14px;
  font-family: monospace;
}

.setting-input:focus {
  outline: none;
  border-color: var(--accent);
}

.btn-test {
  padding: 8px 16px;
  background: var(--accent);
  color: var(--bg);
  border: none;
  border-radius: 6px;
  font-size: 13px;
  font-weight: 500;
  cursor: pointer;
  white-space: nowrap;
}

.btn-test:disabled {
  opacity: 0.5;
}

.setting-select {
  flex: 1;
  padding: 8px 12px;
  border: 1px solid var(--border);
  border-radius: 6px;
  background: var(--bg);
  color: var(--fg);
  font-size: 14px;
  font-family: monospace;
  cursor: pointer;
}

.setting-select:focus {
  outline: none;
  border-color: var(--accent);
}

.btn-refresh {
  padding: 8px 12px;
  background: var(--bg-secondary);
  color: var(--fg-muted);
  border: 1px solid var(--border);
  border-radius: 6px;
  font-size: 14px;
  cursor: pointer;
  min-width: 36px;
}

.btn-refresh:hover {
  background: var(--bg);
  color: var(--fg);
}

.btn-refresh:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.setting-status {
  font-size: 12px;
  margin-top: 4px;
  display: block;
}

.setting-status.success {
  color: #4ade80;
}

.srv-error-box {
  font-size: 12px;
  color: #ef4444;
  background: rgba(239,68,68,0.08);
  border: 1px solid rgba(239,68,68,0.2);
  border-radius: 6px;
  padding: 8px 12px;
  white-space: pre-wrap;
  word-break: break-all;
  max-height: 300px;
  overflow-y: auto;
  margin-top: 8px;
  line-height: 1.5;
}

.setting-status.error {
  color: var(--danger);
}

.setting-input[type="password"] {
  font-family: monospace;
}

.setting-error {
  color: #ef4444;
  font-size: 12px;
}

.btn-danger {
  background: rgba(239, 68, 68, 0.15);
  color: #ef4444;
  border: 1px solid rgba(239, 68, 68, 0.3);
  padding: 6px 16px;
  border-radius: 6px;
  cursor: pointer;
  font-size: 13px;
}

.setting-value {
  font-size: 13px;
  color: var(--fg-muted);
}

.setting-value.connected {
  color: #4ade80;
}

.setting-value.mono {
  font-family: monospace;
}

/* Toggle 开关 */
.toggle-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.toggle {
  position: relative;
  display: inline-block;
  width: 44px;
  height: 24px;
  flex-shrink: 0;
}

.toggle input {
  opacity: 0;
  width: 0;
  height: 0;
}

.toggle-slider {
  position: absolute;
  cursor: pointer;
  inset: 0;
  background: var(--border);
  border-radius: 24px;
  transition: 0.2s;
}

.toggle-slider::before {
  content: '';
  position: absolute;
  height: 18px;
  width: 18px;
  left: 3px;
  bottom: 3px;
  background: white;
  border-radius: 50%;
  transition: 0.2s;
}

.toggle input:checked + .toggle-slider {
  background: var(--accent);
}

.toggle input:checked + .toggle-slider::before {
  transform: translateX(20px);
}

/* 按钮组 */
.btn-group {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
  margin-top: 8px;
}

.btn-action {
  padding: 8px 14px;
  background: var(--accent);
  color: var(--bg);
  border: none;
  border-radius: 6px;
  font-size: 12px;
  font-weight: 500;
  cursor: pointer;
  white-space: nowrap;
}

.btn-action:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.btn-secondary {
  background: #6366f1;
}

.btn-outline {
  background: transparent;
  color: var(--accent);
  border: 1px solid var(--accent);
}

.btn-outline:hover {
  background: rgba(var(--accent-rgb, 59, 130, 246), 0.1);
}

/* 消息框 */
.msg-box {
  margin-top: 8px;
  padding: 8px 12px;
  border-radius: 6px;
  font-size: 12px;
  line-height: 1.5;
}

.msg-ok {
  background: rgba(74, 222, 128, 0.15);
  color: #4ade80;
}

.msg-err {
  background: rgba(239, 68, 68, 0.15);
  color: #ef4444;
}

/* 网络检测结果 */
.check-result {
  margin-top: 12px;
  background: var(--bg-secondary);
  border-radius: 8px;
  padding: 12px;
}

.check-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 6px 0;
  font-size: 13px;
  border-bottom: 1px solid var(--border);
}

.check-item:last-child {
  border-bottom: none;
}

.tag-ok {
  color: #4ade80;
  font-size: 12px;
}

.tag-fail {
  color: #ef4444;
  font-size: 12px;
}

.tag-warn {
  color: #f59e0b;
  font-size: 12px;
}

.recommendations {
  margin-top: 8px;
  padding-top: 8px;
  border-top: 1px solid var(--border);
}

.rec-item {
  font-size: 12px;
  color: #f59e0b;
  padding: 3px 0;
  padding-left: 12px;
  position: relative;
}

.rec-item::before {
  content: '!';
  position: absolute;
  left: 0;
  font-weight: bold;
}

/* 地址历史列表 */
.address-list {
  margin-top: 12px;
  background: var(--bg-secondary);
  border-radius: 8px;
  overflow: hidden;
}

.list-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 8px 12px;
  font-size: 12px;
  color: var(--fg-muted);
  border-bottom: 1px solid var(--border);
}

.btn-clear {
  background: none;
  border: none;
  color: var(--danger);
  font-size: 12px;
  cursor: pointer;
}

.address-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 10px 12px;
  cursor: pointer;
  transition: background 0.15s;
}

.address-item:hover {
  background: var(--border);
}

.address-item.current {
  background: rgba(var(--accent-rgb, 59, 130, 246), 0.1);
}

.address-info {
  flex: 1;
  min-width: 0;
}

.address-url {
  display: block;
  font-size: 13px;
  font-family: monospace;
  color: var(--fg);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.address-meta {
  display: flex;
  gap: 6px;
  font-size: 11px;
  color: var(--fg-muted);
  margin-top: 2px;
  align-items: center;
}

.address-actions {
  display: flex;
  align-items: center;
  gap: 6px;
}

.tag-current {
  font-size: 10px;
  color: var(--accent);
  background: rgba(var(--accent-rgb, 59, 130, 246), 0.15);
  padding: 2px 6px;
  border-radius: 4px;
}

.btn-del {
  background: none;
  border: none;
  color: var(--fg-muted);
  font-size: 12px;
  cursor: pointer;
  padding: 4px 6px;
  border-radius: 4px;
}

.btn-del:hover {
  background: var(--danger);
  color: white;
}

/* 公网穿透设置 */
.setting-link {
  color: var(--accent);
  text-decoration: none;
  font-size: 13px;
}

.setting-link:hover {
  text-decoration: underline;
}

.config-block {
  margin-top: 12px;
  background: var(--bg-secondary);
  border-radius: 8px;
  padding: 12px;
}

.config-title {
  font-size: 12px;
  font-weight: 600;
  color: var(--fg-muted);
  margin-bottom: 10px;
}

/* 隧道类型标签 */
.tunnel-type-tabs {
  display: flex;
  gap: 6px;
  margin-bottom: 4px;
  flex-wrap: wrap;
}

.tab-btn {
  padding: 4px 12px;
  border: 1px solid var(--border);
  border-radius: 16px;
  background: var(--bg);
  color: var(--fg-muted);
  font-size: 12px;
  cursor: pointer;
  transition: all 0.2s;
}

.tab-btn.active {
  background: var(--accent);
  border-color: var(--accent);
  color: white;
}

.tab-btn:hover:not(.active) {
  border-color: var(--accent);
  color: var(--accent);
}

/* 数据同步结果 */
.sync-result {
  margin-top: 12px;
  background: var(--bg-secondary);
  border-radius: 8px;
  padding: 12px;
}

/* 字典管理 */
.dict-group {
  margin-bottom: 8px;
  border: 1px solid var(--border);
  border-radius: 6px;
  overflow: hidden;
}

.dict-group-header {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 10px;
  background: var(--bg);
}

.dict-group-name {
  flex: 1;
  font-size: 13px;
  font-weight: 500;
}

.dict-group-name.disabled {
  color: var(--fg-muted);
  opacity: 0.6;
}

.dict-group-count {
  font-size: 11px;
  color: var(--fg-muted);
}

.btn-dict-toggle {
  background: none;
  border: 1px solid var(--border);
  color: var(--accent);
  font-size: 11px;
  padding: 2px 8px;
  border-radius: 4px;
  cursor: pointer;
}

.btn-dict-toggle:hover {
  background: rgba(var(--accent-rgb, 59, 130, 246), 0.1);
}

.btn-dict-del {
  background: none;
  border: none;
  color: var(--fg-muted);
  font-size: 12px;
  cursor: pointer;
  padding: 2px 4px;
}

.btn-dict-del:hover {
  color: var(--danger);
}

.dict-entries {
  padding: 8px 10px;
  border-top: 1px solid var(--border);
  background: var(--bg-secondary);
}

.dict-entry-row {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 4px 0;
  font-size: 12px;
  border-bottom: 1px solid var(--border);
}

.dict-entry-row:last-child {
  border-bottom: none;
}

.dict-entry-key {
  color: var(--accent);
  min-width: 60px;
  font-weight: 500;
}

.dict-entry-val {
  flex: 1;
  color: var(--fg);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.dict-entry-desc {
  color: var(--fg-muted);
  font-size: 11px;
}

.btn-dict-entry-del {
  background: none;
  border: none;
  color: var(--fg-muted);
  font-size: 11px;
  cursor: pointer;
  padding: 2px;
}

.btn-dict-entry-del:hover {
  color: var(--danger);
}

.dict-add-entry {
  display: flex;
  gap: 4px;
  margin-top: 8px;
  flex-wrap: wrap;
}

.dict-input {
  font-size: 12px !important;
  padding: 5px 8px !important;
  min-width: 80px;
}

.dict-input-desc {
  max-width: 120px;
}

.dict-add-group {
  display: flex;
  gap: 6px;
  margin-top: 10px;
  padding-top: 10px;
  border-top: 1px solid var(--border);
}

/* 关键路径任务 */
.cp-task-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 10px;
  background: var(--bg-secondary);
  border-radius: 6px;
  margin-bottom: 4px;
  font-size: 12px;
}

.cp-task-title {
  flex: 1;
  color: var(--fg);
  font-weight: 500;
}

.cp-task-duration {
  color: var(--accent);
  font-size: 11px;
}

.cp-task-float {
  color: #f59e0b;
  font-size: 11px;
}

/* 视频设置 tabs */
.video-settings-tabs { display: flex; gap: 4px; margin-bottom: 16px; flex-wrap: wrap; }
.vs-tab { padding: 6px 14px; border: 1px solid var(--border); border-radius: 6px; background: var(--bg-secondary); color: var(--fg); font-size: 13px; cursor: pointer; }
.vs-tab.active { background: var(--accent); border-color: var(--accent); color: #fff; }
</style>





``



================================================
FILE: C:\Users\qu\Desktop\物理科学与技术论题\TS2\mcp\server\web\src\views\SlidesView.vue
================================================

``vue
<template>
  <div class="view slides-view" @keydown="onKeyDown" tabindex="0" ref="viewRef">
    <!-- 顶部栏 -->
    <header class="slides-header">
      <div class="header-left">
        <button class="icon-btn text-btn" @click="showOutline = !showOutline" :title="showOutline ? '关闭大纲' : '打开大纲'">
          <span class="btn-text">☰</span>
        </button>
        <div class="notebook-title-wrap">
          <input
            v-model="notebookTitle"
            class="notebook-title-input"
            placeholder="笔记标题"
            @change="saveNotebook"
          />
        </div>
        <!-- 笔记源切换 -->
        <div class="source-toggle">
          <button class="source-btn" :class="{ active: nbSource === 'server' }" @click="switchNbSource('server')">服务端</button>
          <button class="source-btn" :class="{ active: nbSource === 'local' }" @click="switchNbSource('local')">本地</button>
        </div>
        <!-- 笔记选择器 -->
        <div class="nb-selector">
          <button class="icon-btn text-btn" @click="toggleNbList" title="切换笔记">
            <span class="btn-text">📚</span>
          </button>
          <div class="nb-dropdown" v-if="showNbList">
            <!-- 搜索框 -->
            <div class="nb-dropdown-search" v-if="nbSource === 'server'">
              <input
                type="text"
                v-model="nbSearchQuery"
                @input="onNbSearchInput"
                placeholder="搜索笔记..."
                class="nb-search-input"
              />
              <button v-if="nbSearchQuery" class="nb-search-clear" @click="clearNbSearch">✕</button>
            </div>
            <!-- 搜索结果模式（仅服务端） -->
            <template v-if="nbSource === 'server' && nbSearchQuery.trim()">
              <div class="nb-dropdown-breadcrumb">
                <span class="nb-crumb">🔍 {{ nbSearchResults.length }} 结果</span>
              </div>
              <div class="nb-dropdown-item" v-for="r in nbSearchResults" :key="r.relPath" @click="openNotebookByPath(r.relPath)">
                <span class="nb-dropdown-name">📝 {{ stripMdExt(r.name) }}
                  <span class="nb-search-path" v-if="r.relPath.includes('/')">({{ r.relPath.substring(0, r.relPath.lastIndexOf('/')) }})</span>
                </span>
                <button class="nb-dropdown-del" @click.stop="deleteNotebookByPath(r.relPath)" title="删除">✕</button>
              </div>
            </template>
            <!-- 正常逐层浏览模式 -->
            <template v-else>
              <!-- 路径面包屑 -->
              <div class="nb-dropdown-breadcrumb" v-if="nbSource === 'server' && nbCurrentDir">
                <span class="nb-crumb" @click="nbNavigateTo('')">Notes</span>
                <template v-for="(seg, i) in nbCurrentDir.split('/')" :key="i">
                  <span class="nb-crumb-sep">/</span>
                  <span class="nb-crumb" @click="nbNavigateTo(nbCurrentDir.split('/').slice(0, i + 1).join('/'))">{{ seg }}</span>
                </template>
              </div>
              <!-- 本地面包屑 -->
              <div class="nb-dropdown-breadcrumb" v-else-if="nbSource === 'local' && localNbDir">
                <span class="nb-crumb" @click="nbLocalNavigateTo('')">notebooks</span>
                <template v-for="(seg, i) in localNbDir.split('/')" :key="i">
                  <span class="nb-crumb-sep">/</span>
                  <span class="nb-crumb" @click="nbLocalNavigateTo(localNbDir.split('/').slice(0, i + 1).join('/'))">{{ seg }}</span>
                </template>
              </div>
              <div class="nb-dropdown-breadcrumb" v-else>
                <span class="nb-crumb">{{ nbSource === 'server' ? 'Notes' : 'notebooks' }}</span>
              </div>
              <!-- 服务端：逐层浏览 -->
              <template v-if="nbSource === 'server'">
                <div class="nb-dropdown-item nb-dropdown-folder" v-for="d in nbSubDirs" :key="d.path" @click="nbNavigateTo(d.path)">
                  <span class="nb-dropdown-name">📁 {{ d.name }}</span>
                </div>
                <div class="nb-dropdown-item" v-for="nb in notebookList" :key="nb.name" @click="openNotebook(nb.name)">
                  <span class="nb-dropdown-name">{{ stripMdExt(nb.name) }}</span>
                  <button class="nb-dropdown-import" @click.stop="importSingleFromServer(nb.name)" title="导入到本地">↓</button>
                  <button class="nb-dropdown-del" @click.stop="deleteNotebookFile(nb.name)" title="删除">✕</button>
                </div>
              </template>
              <!-- 本地：完整目录浏览 -->
              <template v-else>
                <div class="nb-dropdown-item nb-dropdown-folder" v-if="localNbDir" @click="nbLocalNavigateTo(localNbDir.split('/').slice(0, -1).join('/'))">
                  <span class="nb-dropdown-name">📁 ..</span>
                </div>
                <div class="nb-dropdown-item nb-dropdown-folder" v-for="d in localNbDirs" :key="d.path" @click="nbLocalNavigateTo(d.relPath)">
                  <span class="nb-dropdown-name">📁 {{ d.name }}</span>
                </div>
                <div class="nb-dropdown-item" v-for="nb in localNbList" :key="nb.path" @click="openLocalNotebook(nb.name)">
                  <span class="nb-dropdown-name">{{ stripMdExt(nb.name) }}</span>
                  <button class="nb-dropdown-export" @click.stop="exportSingleToServer(nb.name)" title="导出到服务端">↑</button>
                  <button class="nb-dropdown-del" @click.stop="deleteLocalNotebook(nb.name)" title="删除">✕</button>
                </div>
              </template>
            </template>
            <div class="nb-dropdown-item nb-dropdown-new" @click="createNewNotebook">
              + 新建笔记
            </div>
          </div>
        </div>
      </div>
      <div class="header-center">
        <div class="page-indicator">
          <button class="page-arrow" @click="prevSlide" :disabled="currentIndex === 0" title="上一页 (←)">
            <span class="arrow-text">‹</span>
          </button>
          <span class="page-num">{{ currentIndex + 1 }}</span>
          <span class="page-sep">/</span>
          <span class="page-total">{{ slides.length }}</span>
          <button class="page-arrow" @click="nextSlide" title="下一页 (→)">
            <span class="arrow-text">›</span>
          </button>
        </div>
      </div>
      <div class="header-right">
        <button class="icon-btn text-btn" @click="addSlide(currentIndex + 1)" title="插入新页">
          <span class="btn-text">+</span>
        </button>
        <div class="header-divider"></div>
        <button v-if="nbSource === 'server'" class="icon-btn text-btn" @click="doSaveToServer" :disabled="savingServer" title="保存到服务器 (Ctrl+S)">
          <span class="btn-text">💾</span>
        </button>
        <button v-else class="icon-btn text-btn" @click="saveToLocalNotebook" title="保存到本地 (Ctrl+S)">
          <span class="btn-text">💾</span>
        </button>
        <button v-if="nbSource === 'server'" class="icon-btn text-btn" @click="doLoadFromServer" :disabled="loadingServer" title="从服务器加载">
          <span class="btn-text">📥</span>
        </button>
        <button class="icon-btn text-btn" @click="exportAsMarkdown" title="导出 Markdown">
          <span class="btn-text">MD</span>
        </button>
        <button class="icon-btn text-btn" @click="exportNotebook" title="导出 JSON">
          <span class="btn-text">⬇️</span>
        </button>
        <button class="icon-btn text-btn" @click="importNotebook" title="导入">
          <span class="btn-text">⬆️</span>
        </button>
        <template v-if="nbSource === 'local'">
          <div class="header-divider"></div>
          <button class="icon-btn text-btn nb-action-btn" @click="doImportFromServer" :disabled="importExportBusy" title="从服务端导入笔记">
            <span class="btn-text">↓</span>
          </button>
          <button class="icon-btn text-btn nb-action-btn" @click="doExportToServer" :disabled="importExportBusy" title="导出笔记到服务端">
            <span class="btn-text">↑</span>
          </button>
          <span v-if="importExportMsg" class="import-export-msg">{{ importExportMsg }}</span>
          <span class="local-stats" v-if="localStats.files > 0">{{ localStats.files }}文件</span>
        </template>
        <span v-if="saveStatus" class="save-badge" :class="saveStatusType">{{ saveStatus }}</span>
      </div>
    </header>

    <div class="slides-body" @click="onBodyClick" @touchstart="onTouchStart" @touchend="onTouchEnd">
      <!-- 大纲侧边栏（始终渲染，用CSS控制显隐） -->
      <aside class="slides-outline" :class="{ 'sidebar-hidden': !showOutline }">
        <div class="outline-header">
          <span class="outline-label">大纲</span>
          <span class="outline-count">{{ slides.length }} 页</span>
        </div>
        <div class="outline-list">
          <div
            v-for="(slide, idx) in slides"
            :key="slide.id"
            class="outline-item"
            :class="{ active: idx === currentIndex }"
            @click="goToSlide(idx)"
          >
            <span class="outline-num">{{ idx + 1 }}</span>
            <span class="outline-title">{{ getSlideTitle(slide, idx) }}</span>
            <button class="outline-del" @click.stop="deleteSlide(idx)" title="删除此页" v-if="slides.length > 1">
              <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><path d="M18 6L6 18M6 6l12 12"/></svg>
            </button>
          </div>
        </div>
        <button class="outline-add" @click="addSlide(slides.length)" title="在末尾添加新页">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><path d="M12 5v14M5 12h14"/></svg>
          添加页面
        </button>
      </aside>

      <!-- 编辑区 -->
      <div class="slides-editor">
        <div class="slide-title-bar">
          <input
            v-model="currentSlide.title"
            class="slide-title-input"
            placeholder="页面标题（可选）"
            @change="saveNotebook"
          />
          <span class="slide-time" v-if="currentSlide.updatedAt">{{ formatTime(currentSlide.updatedAt) }}</span>
        </div>
        <!-- Vditor 编辑器 -->
        <div v-if="!useTextarea" ref="vditorRef" class="vditor-container"></div>
        <!-- textarea 降级编辑器 -->
        <template v-else>
          <div class="md-toolbar">
            <button @click="insertMd('**', '**')" title="粗体">B</button>
            <button @click="insertMd('*', '*')" title="斜体">I</button>
            <button @click="insertMd('## ', '')" title="标题">H</button>
            <button @click="insertMd('- ', '')" title="列表">-</button>
            <button @click="insertMd('1. ', '')" title="有序列表">1.</button>
            <button @click="insertMd('- [ ] ', '')" title="待办">☐</button>
            <button @click="insertMd('`', '`')" title="代码">code</button>
            <button @click="insertMd('[', '](url)')" title="链接">🔗</button>
          </div>
          <textarea
            ref="textareaRef"
            class="fallback-textarea"
            placeholder="开始编辑..."
            @input="onTextareaInput"
          ></textarea>
        </template>
      </div>
    </div>

    <!-- 隐藏的文件输入 -->
    <input type="file" ref="importInput" accept=".json,.md,.markdown,.rmd,.rmarkdown,.mdx,.txt" style="display:none" @change="onImportFile" />

    <!-- 冲突解决对话框 -->
    <div v-if="conflictDialog" class="conflict-overlay" @click.self="conflictDialog = false">
      <div class="conflict-dialog">
        <h3>同步冲突</h3>
        <p>本地版本比服务器版本更新，请选择保留哪个版本：</p>
        <div class="conflict-info">
          <div class="conflict-item">
            <span class="conflict-label">本地</span>
            <span class="conflict-time">{{ formatTime(conflictLocalTime) }}</span>
          </div>
          <div class="conflict-item">
            <span class="conflict-label">服务器</span>
            <span class="conflict-time">{{ formatTime(conflictServerTime) }}</span>
          </div>
        </div>
        <div class="conflict-actions">
          <button class="conflict-btn local-btn" @click="resolveConflict(true)">保留本地</button>
          <button class="conflict-btn server-btn" @click="resolveConflict(false)">使用服务器</button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, onMounted, onUnmounted, nextTick, computed } from 'vue'
import { putFile, getFile, readDir, saveNotebook as apiSaveNotebook, getNotebook as apiGetNotebook } from '../api'
import { loadAutocompleteConfig, buildHintExtends } from '../autocomplete'
import {
  localReadDir, localReadFile, localWriteFile, localDeleteFile, localMkdir,
  importDirFromServer, exportDirToServer, localFSStats,
  type DirEntry as LocalDirEntry,
} from '../stores/localFS'

// ─── 数据模型 ────────────────────────────────────────

interface Slide {
  id: string
  title: string
  markdown: string
  createdAt: number
  updatedAt: number
}

interface Notebook {
  id: string
  title: string
  slides: Slide[]
  createdAt: number
  updatedAt: number
}

const STORAGE_KEY = 'ts2_slides_notebook'
const NB_LOCAL_DIR = 'notebooks'  // 本地笔记存储目录前缀
// 所有 markdown 变体扩展名（小写，用于模式匹配）
  const NB_MD_EXTS = ['.md', '.markdown', '.rmd', '.rmarkdown', '.mdx']
  const NB_MD_EXT_PAT = NB_MD_EXTS.map(e => e.replace('.', '\\.')).join('|')
  // 文件 I/O 用：含常见大小写变体，以兼容大小写文件系统
  const NB_MD_EXTS_IO = [...NB_MD_EXTS, '.Rmd', '.RMD', '.RMARKDOWN', '.Mdx', '.MDX', '.MD', '.MARKDOWN']

// 本地/服务端笔记源切换
const nbSource = ref<'server' | 'local'>('server')
const localNbList = ref<{name: string; path: string; updatedAt: number; isDir: boolean}[]>([])
const localNbDirs = ref<{name: string; relPath: string}[]>([])
const localNbDir = ref('')  // 本地笔记子目录路径
const localStats = ref({ files: 0, dirs: 0, totalSize: 0 })
const importExportBusy = ref(false)
const importExportMsg = ref('')

// Vditor 加载策略：本地动态导入优先 → CDN 降级
let VditorClass: any = null
let _vditorLoadFailed = false
let _vditorSource: 'local' | 'cdn' | null = null
const VDITOR_CDN = 'https://unpkg.com/vditor'

async function resolveVditorCdn(): Promise<string> {
  return _vditorSource === 'cdn' ? VDITOR_CDN : import.meta.env.BASE_URL + 'vditor'
}

function getVditorCdn(): string {
  return _vditorSource === 'cdn' ? VDITOR_CDN : import.meta.env.BASE_URL + 'vditor'
}

async function loadVditor(): Promise<any> {
  if (VditorClass) return VditorClass
  if (_vditorLoadFailed) return null
  if ((window as any).Vditor) { VditorClass = (window as any).Vditor; return VditorClass }

  // 1. 本地动态导入
  try {
    const mod = await import('vditor')
    await import('vditor/dist/index.css')
    VditorClass = mod.default
    _vditorSource = 'local'
    return VditorClass
  } catch (e) {
    console.warn('Vditor 本地导入失败，尝试 CDN:', e)
  }

  // 2. CDN 降级
  try {
    await new Promise<void>((resolve, reject) => {
      const link = document.createElement('link')
      link.rel = 'stylesheet'
      link.href = VDITOR_CDN + '/dist/index.css'
      document.head.appendChild(link)
      const script = document.createElement('script')
      script.src = VDITOR_CDN + '/dist/index.min.js'
      script.onload = () => resolve()
      script.onerror = () => reject(new Error('CDN JS load failed'))
      document.head.appendChild(script)
    })
    VditorClass = (window as any).Vditor
    if (!VditorClass) throw new Error('Vditor not found on window')
    _vditorSource = 'cdn'
    return VditorClass
  } catch (e) {
    console.warn('Vditor CDN 加载失败，使用纯文本编辑:', e)
  }

  _vditorLoadFailed = true
  return null
}

function generateId(): string {
  return Date.now().toString(36) + Math.random().toString(36).substr(2, 6)
}

function createSlide(title = '', markdown = ''): Slide {
  const now = Date.now()
  return { id: generateId(), title, markdown, createdAt: now, updatedAt: now }
}

function loadNotebook(): Notebook {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (raw) {
      const nb = JSON.parse(raw)
      if (nb.slides && nb.slides.length > 0) return nb
    }
  } catch { /* ignore */ }
  return {
    id: generateId(),
    title: '我的笔记',
    slides: [createSlide('欢迎', '# 欢迎\n\n这是第一页笔记。\n\n按 **→** 翻到下一页，按 **←** 返回上一页。\n\n点击 **+ 新页** 插入空白页。')],
    createdAt: Date.now(),
    updatedAt: Date.now(),
  }
}

// ─── 状态 ────────────────────────────────────────

const notebookId = ref('')
const notebookTitle = ref('')
const slides = reactive<Slide[]>([])
const currentIndex = ref(0)
const noteExt = ref('.md')  // 当前打开的服务端笔记原始扩展名

// 替换文件名中的 MD 扩展名（用于显示）
function stripMdExt(name: string): string {
  return name.replace(new RegExp(`\\.(${NB_MD_EXT_PAT})$`, 'i'), '')
}
// 判断是否为 MD 变体文件名（大小写不敏感）
function isMdFile(name: string): boolean {
  const lower = name.toLowerCase()
  return NB_MD_EXTS.some(e => lower.endsWith(e))
}
// 判断本地笔记文件（JSON 或 MD 变体）
function isLocalNbFile(name: string): boolean {
  return name.toLowerCase().endsWith('.json') || isMdFile(name)
}

const showOutline = ref(false)
const vditorRef = ref<HTMLElement | null>(null)
const viewRef = ref<HTMLElement | null>(null)
const importInput = ref<HTMLInputElement | null>(null)
const savingServer = ref(false)
const loadingServer = ref(false)
const saveStatus = ref('')
const saveStatusType = ref<'ok' | 'err'>('ok')
const notebookList = ref<{name: string}[]>([])
const nbCurrentDir = ref('')  // 服务端笔记当前所在子目录（相对 Notes）
const nbSubDirs = ref<{name: string; path: string}[]>([])  // 当前目录下的子文件夹
const nbSearchQuery = ref('')  // 搜索关键词
const nbSearchResults = ref<{name: string; relPath: string}[]>([])  // 搜索结果
const showNbList = ref(false)
const useTextarea = ref(false)
const textareaRef = ref<HTMLTextAreaElement | null>(null)
const conflictDialog = ref(false)
const conflictLocalTime = ref(0)
const conflictServerTime = ref(0)
let pendingServerData: { title: string; slides: Slide[] } | null = null

let vditorInstance: any = null
let isSaving = false
let isSwitching = false

const currentSlide = computed(() => slides[currentIndex.value] || createSlide())

// ─── Vditor 初始化 ──────────────────────────────────────
async function initVditor() {
  useTextarea.value = false
  const V = await loadVditor()
  if (!V || !vditorRef.value) {
    // Vditor 不可用，降级为 textarea
    useTextarea.value = true
    await nextTick()
    if (textareaRef.value && slides[currentIndex.value]) {
      textareaRef.value.value = slides[currentIndex.value].markdown || ''
    }
    return
  }

  const isTouch = 'ontouchstart' in window
  const acConfig = loadAutocompleteConfig()
  const currentTheme = document.documentElement.getAttribute('data-theme') || 'dark'
  const vditorCdn = await resolveVditorCdn()
  let vditorReady = false
  try {
    vditorInstance = new V(vditorRef.value, {
      value: slides[currentIndex.value]?.markdown || '',
      mode: 'ir',
      theme: currentTheme === 'light' ? 'classic' : 'dark',
      placeholder: '开始编辑...',
      cache: { enable: false },
      tab: '\t',
      cdn: vditorCdn,
      hint: {
        delay: 200,
        parse: false,
        extend: buildHintExtends(acConfig),
      },
      input: () => {
        if (vditorInstance && !isSwitching && slides[currentIndex.value]) {
          slides[currentIndex.value].markdown = vditorInstance.getValue()
          slides[currentIndex.value].updatedAt = Date.now()
          debounceSave()
        }
      },
      after: () => { vditorReady = true },
      toolbar: isTouch
        ? ['headings', 'bold', 'italic', 'strike', '|', 'quote', 'inline-code', '|', 'list', 'ordered-list', 'check', '|', 'undo', 'redo', '|', 'edit-mode', 'preview']
        : ['headings', 'bold', 'italic', 'strike', '|', 'quote', 'inline-code', 'code', '|', 'list', 'ordered-list', 'check', '|', 'link', 'table', '|', 'undo', 'redo', '|', 'edit-mode', 'preview', 'fullscreen'],
    })
    // 超时检测：子资源加载失败时 vditor 不会触发 after 回调，也不抛异常
    await new Promise<void>((resolve) => setTimeout(resolve, 6000))
    if (!vditorReady) {
      console.warn('Vditor 子资源加载超时（cdn=' + vditorCdn + '），回退纯文本编辑')
      try { vditorInstance.destroy() } catch { /* ignore */ }
      vditorInstance = null
      useTextarea.value = true
      await nextTick()
      if (textareaRef.value && slides[currentIndex.value]) {
        textareaRef.value.value = slides[currentIndex.value].markdown || ''
      }
    }
  } catch (initErr) {
    console.warn('Vditor 初始化失败，降级为纯文本编辑:', initErr)
    vditorInstance = null
    useTextarea.value = true
    await nextTick()
    if (textareaRef.value && slides[currentIndex.value]) {
      textareaRef.value.value = slides[currentIndex.value].markdown || ''
    }
  }
}

// ─── 本地保存 ────────────────────────────────────────

let saveTimer: ReturnType<typeof setTimeout> | null = null
let autoSaveTimer: ReturnType<typeof setInterval> | null = null
let lastAutoSaveAt = 0  // 上次自动保存时间（毫秒时间戳）
const AUTO_SAVE_INTERVAL = 30000  // 每 30 秒自动保存

// 防抖保存到 localStorage（快速恢复）
function debounceSave() {
  if (saveTimer) clearTimeout(saveTimer)
  saveTimer = setTimeout(() => saveToLocalStorage(), 500)
}

// 保存到 localStorage（快速恢复，始终执行）
function saveToLocalStorage() {
  if (isSaving) return
  isSaving = true
  try {
    const nb: Notebook = {
      id: notebookId.value,
      title: notebookTitle.value,
      slides: slides.map(s => ({ ...s })),
      createdAt: 0,
      updatedAt: Date.now(),
    }
    const existing = localStorage.getItem(STORAGE_KEY)
    if (existing) {
      try { nb.createdAt = JSON.parse(existing).createdAt || Date.now() } catch { nb.createdAt = Date.now() }
    } else {
      nb.createdAt = Date.now()
    }
    localStorage.setItem(STORAGE_KEY, JSON.stringify(nb))
    showSaveStatus('已保存', 'ok')
  } finally {
    isSaving = false
  }
}

// 启动周期性自动保存（每 30 秒）
function startAutoSave() {
  stopAutoSave()
  autoSaveTimer = setInterval(async () => {
    // 如果距上次保存或距上次自动保存超过 30 秒，则自动保存
    if (slides.length === 0) return
    saveCurrentSlide()
    try {
      if (nbSource.value === 'local') {
        await saveToLocalNotebookSilent()
      } else {
        await doSaveToServer()
      }
      lastAutoSaveAt = Date.now()
    } catch { /* silent fail */ }
  }, AUTO_SAVE_INTERVAL)
}

function stopAutoSave() {
  if (autoSaveTimer) {
    clearInterval(autoSaveTimer)
    autoSaveTimer = null
  }
}

// 保存笔记本（统一入口，防抖调用本地存储，周期性调用远端）
function saveNotebook() {
  saveToLocalStorage()
}

// 静默保存到 IndexedDB（无反馈，用于自动保存/退出）
async function saveToLocalNotebookSilent() {
  saveCurrentSlide()
  try {
    const nb: Notebook = {
      id: notebookId.value,
      title: notebookTitle.value,
      slides: slides.map(s => ({ ...s })),
      createdAt: 0,
      updatedAt: Date.now(),
    }
    const existing = localStorage.getItem(STORAGE_KEY)
    if (existing) {
      try { nb.createdAt = JSON.parse(existing).createdAt } catch { /* ignore */ }
    }
    const safeName = (notebookTitle.value || 'note').replace(/[\\/:*?"<>|]/g, '_')
    const dirPrefix = localNbDir.value ? `${NB_LOCAL_DIR}/${localNbDir.value}` : NB_LOCAL_DIR
    await localMkdir(dirPrefix)
    await localWriteFile(`${dirPrefix}/${safeName}.json`, JSON.stringify(nb, null, 2))
    const md = slidesToMarkdown(slides, notebookTitle.value)
    await localWriteFile(`${dirPrefix}/${safeName}.md`, md)
  } catch { /* silent fail */ }
}

// 保存笔记到本地（带用户反馈）
async function saveToLocalNotebook() {
  await saveToLocalNotebookSilent()
  try {
    await loadLocalNbList()
    await refreshLocalStats()
    showSaveStatus('已保存到本地', 'ok')
  } catch {
    showSaveStatus('本地保存失败', 'err')
  }
}

function showSaveStatus(msg: string, type: 'ok' | 'err') {
  saveStatus.value = msg
  saveStatusType.value = type
  setTimeout(() => { saveStatus.value = '' }, 2000)
}

function formatTime(ts: number): string {
  if (!ts) return ''
  const d = new Date(ts)
  const h = d.getHours().toString().padStart(2, '0')
  const m = d.getMinutes().toString().padStart(2, '0')
  return `${h}:${m}`
}

// 将 slides 数组转为 Markdown（参数化版本，供本地导出使用）
function slidesToMarkdown(slides: Slide[], title: string): string {
  const parts: string[] = []
  if (title) parts.push(`# ${title}\n`)
  for (let i = 0; i < slides.length; i++) {
    const s = slides[i]
    if (s.title) parts.push(`## ${s.title}\n`)
    parts.push(s.markdown || '')
    if (i < slides.length - 1) parts.push('\n---\n')
  }
  return parts.join('\n')
}

// ─── 服务器保存/加载（notes 目录 MD 文件）────────────────────────

function notebookToMD(): string {
  const parts: string[] = []
  if (notebookTitle.value) {
    parts.push(`# ${notebookTitle.value}\n`)
  }
  for (let i = 0; i < slides.length; i++) {
    const slide = slides[i]
    if (slide.title) {
      parts.push(`## ${slide.title}\n`)
    }
    parts.push(slide.markdown || '')
    if (i < slides.length - 1) {
      parts.push('\n---\n')
    }
  }
  return parts.join('\n')
}

function mdToSlides(content: string): { title: string; slides: Slide[] } {
  const sections = content.split(/\n---\n/)
  const importedSlides: Slide[] = []
  let nbTitle = ''
  for (let i = 0; i < sections.length; i++) {
    let md = sections[i].trim()
    if (!md) continue
    let title = ''
    const firstLine = md.split('\n')[0]
    if (i === 0 && firstLine.startsWith('# ')) {
      nbTitle = firstLine.replace(/^# +/, '').trim()
      md = md.split('\n').slice(1).join('\n').trim()
      if (!md) continue
    }
    if (firstLine.startsWith('## ')) {
      title = firstLine.replace(/^## +/, '').trim()
      md = md.split('\n').slice(1).join('\n').trim()
    }
    importedSlides.push(createSlide(title, md))
  }
  if (importedSlides.length === 0) {
    importedSlides.push(createSlide('', content))
  }
  return { title: nbTitle, slides: importedSlides }
}

function notesPath(): string {
  const name = (notebookTitle.value || 'note').replace(/[\\/:*?"<>|]/g, '_')
  return `Notes/${name}${noteExt.value}`
}

async function doSaveToServer() {
  saveCurrentSlide()
  savingServer.value = true
  try {
    // 保存 MD 到 notes 目录
    const md = notebookToMD()
    await putFile(notesPath(), md)
    // 同时保存 JSON 元数据
    const meta = {
      id: notebookId.value,
      title: notebookTitle.value,
      slides: slides.map(s => ({ ...s })),
      createdAt: 0,
      updatedAt: Date.now(),
    }
    const existing = localStorage.getItem(STORAGE_KEY)
    if (existing) {
      try { meta.createdAt = JSON.parse(existing).createdAt } catch { /* ignore */ }
    }
    await apiSaveNotebook(notebookId.value, meta)
    showSaveStatus('已保存', 'ok')
  } catch (e: any) {
    showSaveStatus('保存失败', 'err')
  } finally {
    savingServer.value = false
  }
}

async function doLoadFromServer() {
  loadingServer.value = true
  try {
    // 先尝试从 notes 目录读取 MD
    const res = await getFile(notesPath())
    const content = res.data?.data?.content ?? res.data?.data
    if (content && typeof content === 'string' && content.trim()) {
      const parsed = mdToSlides(content)
      // 冲突检测：比较本地和服务器 updatedAt
      const localUpdated = Math.max(...slides.map(s => s.updatedAt || 0), 0)
      const serverUpdated = Math.max(...parsed.slides.map(s => s.updatedAt || 0), 0)
      if (localUpdated > serverUpdated + 5000 && slides.some(s => s.markdown.trim())) {
        // 本地比服务器新超过5秒，可能存在冲突
        pendingServerData = parsed
        conflictLocalTime.value = localUpdated
        conflictServerTime.value = serverUpdated
        conflictDialog.value = true
        loadingServer.value = false
        return
      }
      // 无冲突，直接加载
      applyServerData(parsed)
    } else {
      // 回退到 JSON API
      const nbRes = await apiGetNotebook(notebookId.value)
      const data = nbRes.data?.data ?? nbRes.data
      if (data && data.slides) {
        const serverSlides: Slide[] = (data.slides || []).map((s: any) => ({
          id: s.id || generateId(),
          title: s.title || '',
          markdown: s.markdown || '',
          createdAt: s.createdAt || Date.now(),
          updatedAt: s.updatedAt || Date.now(),
        }))
        // 冲突检测
        const localUpdated = Math.max(...slides.map(s => s.updatedAt || 0), 0)
        const serverUpdated = Math.max(...serverSlides.map(s => s.updatedAt || 0), 0)
        if (localUpdated > serverUpdated + 5000 && slides.some(s => s.markdown.trim())) {
          pendingServerData = { title: data.title || '', slides: serverSlides }
          conflictLocalTime.value = localUpdated
          conflictServerTime.value = serverUpdated
          conflictDialog.value = true
          loadingServer.value = false
          return
        }
        applyServerData({ title: data.title || '', slides: serverSlides })
      } else {
        showSaveStatus('无数据', 'err')
      }
    }
  } catch (e: any) {
    showSaveStatus('加载失败', 'err')
  } finally {
    loadingServer.value = false
  }
}

function applyServerData(data: { title: string; slides: Slide[] }) {
  saveCurrentSlide()
  if (data.title) notebookTitle.value = data.title
  slides.splice(0, slides.length, ...data.slides)
  currentIndex.value = 0
  loadSlide(0)
  saveNotebook()
  showSaveStatus('已加载', 'ok')
}

function resolveConflict(useLocal: boolean) {
  conflictDialog.value = false
  if (useLocal) {
    // 保留本地版本，推送到服务器
    showSaveStatus('保留本地', 'ok')
    doSaveToServer()
  } else if (pendingServerData) {
    // 使用服务器版本
    applyServerData(pendingServerData)
    pendingServerData = null
  }
}

// ─── 翻页 ────────────────────────────────────────

function saveCurrentSlide() {
  if (useTextarea.value && textareaRef.value && slides[currentIndex.value]) {
    slides[currentIndex.value].markdown = textareaRef.value.value
    slides[currentIndex.value].updatedAt = Date.now()
  } else if (vditorInstance && slides[currentIndex.value]) {
    try {
      const val = vditorInstance.getValue()
      if (val !== undefined) {
        slides[currentIndex.value].markdown = val
        slides[currentIndex.value].updatedAt = Date.now()
      }
    } catch { /* ignore */ }
  }
}

function loadSlide(index: number) {
  const md = slides[index]?.markdown || ''
  if (useTextarea.value && textareaRef.value) {
    textareaRef.value.value = md
  } else if (vditorInstance) {
    isSwitching = true
    try {
      vditorInstance.setValue(md)
    } finally {
      setTimeout(() => { isSwitching = false }, 100)
    }
  }
}

function onTextareaInput() {
  if (slides[currentIndex.value]) {
    slides[currentIndex.value].markdown = textareaRef.value?.value || ''
    slides[currentIndex.value].updatedAt = Date.now()
    debounceSave()
  }
}

function insertMd(before: string, after: string) {
  const ta = textareaRef.value
  if (!ta) return
  const start = ta.selectionStart
  const end = ta.selectionEnd
  const selected = ta.value.substring(start, end)
  const replacement = before + (selected || '文本') + after
  ta.value = ta.value.substring(0, start) + replacement + ta.value.substring(end)
  ta.selectionStart = start + before.length
  ta.selectionEnd = start + before.length + (selected || '文本').length
  ta.focus()
  onTextareaInput()
}

function goToSlide(index: number) {
  if (index === currentIndex.value) return
  saveCurrentSlide()
  saveNotebook()
  currentIndex.value = index
  loadSlide(index)
}

function prevSlide() {
  if (currentIndex.value > 0) {
    goToSlide(currentIndex.value - 1)
  }
}

function nextSlide() {
  if (currentIndex.value < slides.length - 1) {
    goToSlide(currentIndex.value + 1)
  } else {
    addSlide(currentIndex.value + 1)
  }
}

function addSlide(insertAt: number) {
  saveCurrentSlide()
  const newSlide = createSlide('', '')
  slides.splice(insertAt, 0, newSlide)
  currentIndex.value = insertAt
  loadSlide(currentIndex.value)
  saveNotebook()
}

function deleteSlide(index: number) {
  if (slides.length <= 1) return
  slides.splice(index, 1)
  if (currentIndex.value >= slides.length) {
    currentIndex.value = slides.length - 1
  } else if (currentIndex.value > index) {
    currentIndex.value--
  } else if (currentIndex.value === index) {
    currentIndex.value = Math.min(index, slides.length - 1)
  }
  loadSlide(currentIndex.value)
  saveNotebook()
}

// ─── 键盘 ────────────────────────────────────────

function onKeyDown(e: KeyboardEvent) {
  const tag = (e.target as HTMLElement)?.tagName?.toLowerCase()
  const isInput = tag === 'input' || tag === 'textarea' || tag === 'select'

  if ((e.ctrlKey || e.metaKey) && e.key === 'ArrowLeft' && !isInput) {
    e.preventDefault()
    prevSlide()
  } else if ((e.ctrlKey || e.metaKey) && e.key === 'ArrowRight' && !isInput) {
    e.preventDefault()
    nextSlide()
  } else if ((e.ctrlKey || e.metaKey) && e.key === 's') {
    e.preventDefault()
    if (nbSource.value === 'local') {
      saveToLocalNotebook()
    } else {
      doSaveToServer()
    }
  }
}

// ─── 辅助 ────────────────────────────────────────

function onBodyClick(e: MouseEvent) {
  const target = e.target as HTMLElement
  // 点击编辑区空白处时关闭大纲和笔记列表
  if (target.closest('.slides-editor')) {
    showOutline.value = false
    showNbList.value = false
  }
}

// ─── 触摸手势：左右滑动切换页面 ────────────────────────────

let touchStartX = 0
let touchStartY = 0
let touchStartTime = 0

function onTouchStart(e: TouchEvent) {
  const touch = e.touches[0]
  touchStartX = touch.clientX
  touchStartY = touch.clientY
  touchStartTime = Date.now()
}

function onTouchEnd(e: TouchEvent) {
  const touch = e.changedTouches[0]
  const dx = touch.clientX - touchStartX
  const dy = touch.clientY - touchStartY
  const dt = Date.now() - touchStartTime
  // 判断为水平快速滑动：水平距离 > 60px，垂直距离 < 水平距离的一半，时间 < 500ms
  if (Math.abs(dx) > 60 && Math.abs(dy) < Math.abs(dx) * 0.5 && dt < 500) {
    if (dx > 0) {
      prevSlide()
    } else {
      nextSlide()
    }
  }
}

function getSlideTitle(slide: Slide, idx: number): string {
  if (slide.title) return slide.title
  const firstLine = slide.markdown?.split('\n')[0] || ''
  const heading = firstLine.replace(/^#+\s*/, '').trim()
  return heading || `第 ${idx + 1} 页`
}

// ─── 导出为 Markdown ────────────────────────────────────────

function exportAsMarkdown() {
  saveCurrentSlide()
  const parts: string[] = []
  if (notebookTitle.value) {
    parts.push(`# ${notebookTitle.value}\n`)
  }
  for (let i = 0; i < slides.length; i++) {
    const slide = slides[i]
    if (slide.title) {
      parts.push(`## ${slide.title}\n`)
    }
    parts.push(slide.markdown || '')
    if (i < slides.length - 1) {
      parts.push('\n---\n')
    }
  }
  const md = parts.join('\n')
  const blob = new Blob([md], { type: 'text/markdown;charset=utf-8' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `${notebookTitle.value || 'note'}.md`
  a.click()
  URL.revokeObjectURL(url)
  showSaveStatus('已导出 MD', 'ok')
}

// ─── 导入/导出 JSON ────────────────────────────────────────

function exportNotebook() {
  saveCurrentSlide()
  saveNotebook()
  const nb: Notebook = {
    id: notebookId.value,
    title: notebookTitle.value,
    slides: slides.map(s => ({ ...s })),
    createdAt: 0,
    updatedAt: Date.now(),
  }
  const existing = localStorage.getItem(STORAGE_KEY)
  if (existing) {
    try { nb.createdAt = JSON.parse(existing).createdAt } catch { /* ignore */ }
  }
  const blob = new Blob([JSON.stringify(nb, null, 2)], { type: 'application/json' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `${notebookTitle.value || 'note'}.json`
  a.click()
  URL.revokeObjectURL(url)
  showSaveStatus('已导出 JSON', 'ok')
}

function importNotebook() {
  importInput.value?.click()
}

function onImportFile(e: Event) {
  const file = (e.target as HTMLInputElement)?.files?.[0]
  if (!file) return
  const reader = new FileReader()
  reader.onload = () => {
    const content = reader.result as string
    const ext = file.name.split('.').pop()?.toLowerCase()

    if (ext === 'md' || ext === 'markdown' || ext === 'rmd' || ext === 'rmarkdown' || ext === 'mdx' || ext === 'txt') {
      importFromMarkdown(content, file.name.replace(/\.\w+$/, ''))
      return
    }

    try {
      const nb = JSON.parse(content)
      if (!nb.slides || !Array.isArray(nb.slides)) {
        alert('无效的笔记文件')
        return
      }
      notebookTitle.value = nb.title || '导入的笔记'
      if (nb.id) notebookId.value = nb.id
      slides.splice(0, slides.length, ...nb.slides.map((s: any) => ({
        id: s.id || generateId(),
        title: s.title || '',
        markdown: s.markdown || '',
        createdAt: s.createdAt || Date.now(),
        updatedAt: s.updatedAt || Date.now(),
      })))
      currentIndex.value = 0
      loadSlide(0)
      saveNotebook()
      showSaveStatus('已导入', 'ok')
    } catch {
      alert('文件解析失败')
    }
  }
  reader.readAsText(file)
  ;(e.target as HTMLInputElement).value = ''
}

function importFromMarkdown(content: string, filename: string) {
  const sections = content.split(/\n---\n/)
  const importedSlides: Slide[] = []

  for (let i = 0; i < sections.length; i++) {
    let md = sections[i].trim()
    if (!md) continue
    let title = ''
    const firstLine = md.split('\n')[0]
    if (firstLine.startsWith('# ')) {
      title = firstLine.replace(/^# +/, '').trim()
      md = md.split('\n').slice(1).join('\n').trim()
    } else if (firstLine.startsWith('## ')) {
      title = firstLine.replace(/^## +/, '').trim()
      md = md.split('\n').slice(1).join('\n').trim()
    }
    importedSlides.push(createSlide(title, md))
  }

  if (importedSlides.length === 0) {
    importedSlides.push(createSlide('', content))
  }

  notebookTitle.value = filename || '导入的笔记'
  slides.splice(0, slides.length, ...importedSlides)
  currentIndex.value = 0
  loadSlide(0)
  saveNotebook()
  showSaveStatus(`已导入 ${importedSlides.length} 页`, 'ok')
}

// ─── 多笔记管理 ────────────────────────────────────────

async function toggleNbList() {
  showNbList.value = !showNbList.value
  if (showNbList.value) {
    await loadNotebookList()
    await nextTick()
    // 检测下拉菜单是否溢出屏幕右侧，若溢出则改为右对齐
    const dd = document.querySelector('.nb-dropdown') as HTMLElement | null
    const btn = document.querySelector('.nb-selector > .icon-btn') as HTMLElement | null
    if (dd && btn) {
      const btnRect = btn.getBoundingClientRect()
      const ddW = dd.offsetWidth
      const vw = window.innerWidth
      if (btnRect.left + ddW > vw - 8) {
        dd.style.left = 'auto'
        dd.style.right = '8px'
      } else {
        dd.style.left = '0'
        dd.style.right = 'auto'
      }
    }
  }
}

// 进入子目录
function nbNavigateTo(dirPath: string) {
  nbCurrentDir.value = dirPath
  loadNotebookList()
}

// 递归搜索整个 Notes 目录树
async function nbSearchTree(dirPath: string, prefix: string, query: string, results: {name: string; relPath: string}[]): Promise<void> {
  try {
    const res = await readDir(dirPath)
    const files = res.data?.data ?? res.data
    if (!Array.isArray(files)) return
    for (const f of files) {
      if (!f.is_dir && isMdFile(f.name)) {
        const relPath = prefix ? `${prefix}/${f.name}` : f.name
        const displayName = stripMdExt(f.name).toLowerCase()
        if (displayName.includes(query)) {
          results.push({ name: f.name, relPath })
        }
      }
    }
    for (const f of files) {
      if (f.is_dir) {
        const subPrefix = prefix ? `${prefix}/${f.name}` : f.name
        await nbSearchTree(`Notes/${subPrefix}`, subPrefix, query, results)
      }
    }
  } catch { /* ignore */ }
}

// 搜索输入处理
let nbSearchTimer: any = null
function onNbSearchInput() {
  if (nbSearchTimer) clearTimeout(nbSearchTimer)
  nbSearchTimer = setTimeout(async () => {
    const q = nbSearchQuery.value.trim().toLowerCase()
    if (!q) {
      nbSearchResults.value = []
      await loadNotebookList()
      return
    }
    nbSearchResults.value = []
    await nbSearchTree('Notes', '', q, nbSearchResults.value)
  }, 300)
}

// 清除搜索
function clearNbSearch() {
  nbSearchQuery.value = ''
  nbSearchResults.value = []
  loadNotebookList()
}

// 通过完整相对路径打开笔记（搜索结果用）
async function openNotebookByPath(relPath: string) {
  showNbList.value = false
  saveCurrentSlide()
  saveToLocalStorage()
  if (nbSource.value === 'local') await saveToLocalNotebookSilent()
  else await doSaveToServer()
  try {
    const res = await getFile(`Notes/${relPath}`)
    const content = res.data?.data?.content ?? res.data?.data
    if (content && typeof content === 'string' && content.trim()) {
      const parsed = mdToSlides(content)
      const fileName = relPath.split('/').pop() || relPath
      notebookTitle.value = parsed.title || stripMdExt(fileName)
      noteExt.value = '.' + (fileName.split('.').pop() || 'md')
      notebookId.value = generateId()
      slides.splice(0, slides.length, ...parsed.slides)
      currentIndex.value = 0
      loadSlide(0)
      saveNotebook()
      startAutoSave()
      showSaveStatus('已打开', 'ok')
    }
  } catch {
    showSaveStatus('打开失败', 'err')
  }
}

// 通过完整相对路径删除笔记（搜索结果用）
async function deleteNotebookByPath(relPath: string) {
  if (!confirm(`确定删除 "${relPath}"？此操作不可恢复。`)) return
  try {
    const { default: axios } = await import('axios')
    const baseURL = localStorage.getItem('ts2_server_url') || ''
    await axios.post(`${baseURL}/api/file/removeFile`, { path: `Notes/${relPath}` })
    showSaveStatus('已删除', 'ok')
    // 刷新搜索结果
    const q = nbSearchQuery.value.trim().toLowerCase()
    if (q) {
      nbSearchResults.value = []
      await nbSearchTree('Notes', '', q, nbSearchResults.value)
    }
  } catch {
    showSaveStatus('删除失败', 'err')
  }
}

async function loadNotebookList() {
  if (nbSource.value === 'local') {
    await loadLocalNbList()
    return
  }
  // 有搜索关键词时走递归搜索，不在此处理（由 onNbSearchInput 处理）
  if (nbSearchQuery.value.trim()) return
  try {
    const dir = nbCurrentDir.value ? `Notes/${nbCurrentDir.value}` : 'Notes'
    const res = await readDir(dir)
    const files = res.data?.data ?? res.data
    if (Array.isArray(files)) {
      // 子文件夹（笔记本）
      nbSubDirs.value = files
        .filter((f: any) => f.is_dir)
        .map((f: any) => ({ name: f.name, path: nbCurrentDir.value ? `${nbCurrentDir.value}/${f.name}` : f.name }))
      // 笔记文件
      notebookList.value = files.filter((f: any) =>
        !f.is_dir && isMdFile(f.name)
      )
    }
  } catch { /* ignore */ }
}

async function loadLocalNbList() {
  try {
    await localMkdir(NB_LOCAL_DIR)
    const subDir = localNbDir.value ? `${NB_LOCAL_DIR}/${localNbDir.value}` : NB_LOCAL_DIR
    const entries = await localReadDir(subDir)
    // 子目录
    localNbDirs.value = entries
      .filter(e => e.type === 'dir')
      .map(e => ({
        name: e.name,
        relPath: localNbDir.value ? `${localNbDir.value}/${e.name}` : e.name,
      }))
    // 笔记文件（去重：同名基只显示一次，优先 .json，否则取第一个 MD 变体）
    const seen = new Map<string, { name: string; path: string; updatedAt: number }>()
    for (const e of entries) {
      if (e.type !== 'file' || !isLocalNbFile(e.name)) continue
      const base = e.name.replace(/\.\w+$/, '')
      const isJson = e.name.endsWith('.json')
      const existing = seen.get(base)
      if (!existing || (isJson && !existing.name.endsWith('.json'))) {
        seen.set(base, { name: e.name, path: e.path, updatedAt: e.updatedAt })
      }
    }
    localNbList.value = Array.from(seen.values())
  } catch { /* ignore */ }
}

function nbLocalNavigateTo(dirPath: string) {
  localNbDir.value = dirPath
  loadLocalNbList()
}

async function refreshLocalStats() {
  try {
    localStats.value = await localFSStats()
  } catch { /* ignore */ }
}

async function switchNbSource(source: 'server' | 'local') {
  // 切换前保存当前笔记到原源
  saveCurrentSlide()
  saveToLocalStorage()
  if (nbSource.value === 'local') await saveToLocalNotebookSilent()
  else await doSaveToServer()
  // 停止自动保存，防止内存中旧源数据泄漏到新源
  stopAutoSave()
  // 重置为空白笔记
  const fresh = { id: generateId(), title: '新笔记', slides: [createSlide('', '')], createdAt: Date.now(), updatedAt: Date.now() }
  notebookId.value = fresh.id
  notebookTitle.value = fresh.title
  slides.splice(0, slides.length, ...fresh.slides)
  currentIndex.value = 0
  noteExt.value = '.md'
  await nextTick()
  loadSlide(0)

  nbSource.value = source
  notebookList.value = []
  nbSubDirs.value = []
  nbCurrentDir.value = ''
  nbSearchQuery.value = ''
  nbSearchResults.value = []
  localNbList.value = []
  localNbDirs.value = []
  localNbDir.value = ''
  if (source === 'local') {
    await loadLocalNbList()
    await refreshLocalStats()
  } else {
    await loadNotebookList()
  }
}

async function openNotebook(fileName: string) {
  showNbList.value = false
  if (nbSource.value === 'local') {
    await openLocalNotebook(fileName)
    return
  }
  // 切换前保存当前笔记
  saveCurrentSlide()
  saveToLocalStorage()
  if (nbSource.value === 'local') await saveToLocalNotebookSilent()
  else await doSaveToServer()

  try {
    const filePath = nbCurrentDir.value ? `Notes/${nbCurrentDir.value}/${fileName}` : `Notes/${fileName}`
    const res = await getFile(filePath)
    const content = res.data?.data?.content ?? res.data?.data
    if (content && typeof content === 'string' && content.trim()) {
      const parsed = mdToSlides(content)
      notebookTitle.value = parsed.title || stripMdExt(fileName)
      noteExt.value = '.' + (fileName.split('.').pop() || 'md')
      notebookId.value = generateId()
      slides.splice(0, slides.length, ...parsed.slides)
      currentIndex.value = 0
      loadSlide(0)
      saveNotebook()
      startAutoSave()
      showSaveStatus('已打开', 'ok')
    }
  } catch {
    showSaveStatus('打开失败', 'err')
  }
}

async function openLocalNotebook(name: string) {
  saveCurrentSlide()
  saveToLocalStorage()
  if (nbSource.value === 'server') await doSaveToServer()

  // 构建文件路径（支持子目录）
  const baseName = name.replace(/\.\w+$/, '')
  const dirPrefix = localNbDir.value ? `${NB_LOCAL_DIR}/${localNbDir.value}` : NB_LOCAL_DIR
  const filePrefix = `${dirPrefix}/${baseName}`

  try {
    // 先尝试 JSON 格式
    const jsonFile = await localReadFile(`${filePrefix}.json`)
    if (jsonFile?.content) {
      const nb = JSON.parse(jsonFile.content)
      if (nb.slides && Array.isArray(nb.slides)) {
        notebookTitle.value = nb.title || baseName
        notebookId.value = nb.id || generateId()
        slides.splice(0, slides.length, ...nb.slides.map((s: any) => ({
          id: s.id || generateId(),
          title: s.title || '',
          markdown: s.markdown || '',
          createdAt: s.createdAt || Date.now(),
          updatedAt: s.updatedAt || Date.now(),
        })))
        currentIndex.value = 0
        loadSlide(0)
        saveNotebook()
        startAutoSave()
        showSaveStatus('已打开本地笔记', 'ok')
        return
      }
    }
    // 回退到 MD 格式（尝试所有变体）
    for (const ext of NB_MD_EXTS_IO) {
      const mdFile = await localReadFile(`${filePrefix}${ext}`)
      if (mdFile?.content) {
        const parsed = mdToSlides(mdFile.content)
        notebookTitle.value = parsed.title || baseName
        notebookId.value = generateId()
        slides.splice(0, slides.length, ...parsed.slides)
        currentIndex.value = 0
        loadSlide(0)
        saveNotebook()
        startAutoSave()
        showSaveStatus('已打开本地笔记', 'ok')
        return
      }
    }
    showSaveStatus('笔记为空', 'err')
  } catch {
    showSaveStatus('打开失败', 'err')
  }
}

async function deleteLocalNotebook(name: string) {
  if (!confirm(`确定删除本地笔记 "${name}"？`)) return
  try {
    const dirPrefix = localNbDir.value ? `${NB_LOCAL_DIR}/${localNbDir.value}` : NB_LOCAL_DIR
    // 尝试删除 JSON 和所有 MD 变体
    try { await localDeleteFile(`${dirPrefix}/${name.replace(/\.\w+$/, '')}.json`) } catch { /* ignore */ }
    for (const ext of NB_MD_EXTS_IO) {
      try { await localDeleteFile(`${dirPrefix}/${name}`) } catch { /* ignore */ }
    }
    showSaveStatus('已删除', 'ok')
    await loadLocalNbList()
    await refreshLocalStats()
  } catch {
    showSaveStatus('删除失败', 'err')
  }
}

async function doImportFromServer() {
  if (importExportBusy.value) return
  importExportBusy.value = true
  importExportMsg.value = '正在从服务端导入...'
  try {
    const serverDir = nbCurrentDir.value ? `Notes/${nbCurrentDir.value}` : 'Notes'
    const localDir = localNbDir.value ? `${NB_LOCAL_DIR}/${localNbDir.value}` : NB_LOCAL_DIR
    await localMkdir(localDir)
    const count = await importDirFromServer(
      serverDir, localDir,
      async (path) => {
        const res = await readDir(path)
        const d = res.data?.data ?? res.data
        return Array.isArray(d) ? d : []
      },
      async (path) => {
        const res = await getFile(path)
        const d = res.data?.data ?? res.data
        return d?.content ?? ''
      },
    )
    importExportMsg.value = `导入完成：${count} 个文件`
    await loadLocalNbList()
    await refreshLocalStats()
  } catch (e: any) {
    importExportMsg.value = `导入失败：${e.message || e}`
  } finally {
    importExportBusy.value = false
    setTimeout(() => { importExportMsg.value = '' }, 3000)
  }
}

async function doExportToServer() {
  if (importExportBusy.value) return
  importExportBusy.value = true
  importExportMsg.value = '正在导出到服务端...'
  try {
    const localDir = localNbDir.value ? `${NB_LOCAL_DIR}/${localNbDir.value}` : NB_LOCAL_DIR
    const serverDir = nbCurrentDir.value ? `Notes/${nbCurrentDir.value}` : 'Notes'
    const count = await exportDirToServer(
      localDir, serverDir,
      async (path, content) => { await putFile(path, content) },
    )
    importExportMsg.value = `导出完成：${count} 个文件`
    if (nbSource.value === 'server') await loadNotebookList()
  } catch (e: any) {
    importExportMsg.value = `导出失败：${e.message || e}`
  } finally {
    importExportBusy.value = false
    setTimeout(() => { importExportMsg.value = '' }, 3000)
  }
}

// 单个笔记从服务端导入到本地
async function importSingleFromServer(fileName: string) {
  try {
    const filePath = nbCurrentDir.value ? `Notes/${nbCurrentDir.value}/${fileName}` : `Notes/${fileName}`
    const res = await getFile(filePath)
    const content = res.data?.data?.content ?? res.data?.data
    if (content && typeof content === 'string') {
      const safeName = stripMdExt(fileName).replace(/[\\/:*?"<>|]/g, '_')
      const originalExt = '.' + (fileName.split('.').pop() || 'md')
      const dirPrefix = localNbDir.value ? `${NB_LOCAL_DIR}/${localNbDir.value}` : NB_LOCAL_DIR
      await localMkdir(dirPrefix)
      // 先解析 MD 为 slides JSON，再存储
      const parsed = mdToSlides(content)
      const nb = {
        id: generateId(),
        title: parsed.title || safeName,
        slides: parsed.slides,
        createdAt: Date.now(),
        updatedAt: Date.now(),
      }
      await localWriteFile(`${dirPrefix}/${safeName}.json`, JSON.stringify(nb, null, 2))
      await localWriteFile(`${dirPrefix}/${safeName}${originalExt}`, content) // 保存原始扩展名
      await loadLocalNbList()
      showSaveStatus('已导入', 'ok')
      setTimeout(() => { showSaveStatus('') }, 2000)
    }
  } catch {
    showSaveStatus('导入失败', 'err')
  }
}

// 单个笔记从本地导出到服务端
async function exportSingleToServer(name: string) {
  try {
    const dirPrefix = localNbDir.value ? `${NB_LOCAL_DIR}/${localNbDir.value}` : NB_LOCAL_DIR
    const baseName = name.replace(/\.\w+$/, '')
    let content = ''
    let foundExt = '.md'
    // 先试 JSON
    const jsonFile = await localReadFile(`${dirPrefix}/${baseName}.json`)
    if (jsonFile?.content) {
      const nb = JSON.parse(jsonFile.content)
      content = slidesToMarkdown(nb.slides, nb.title)
    } else {
      // 再试所有 MD 变体，记录实际扩展名
      for (const ext of NB_MD_EXTS_IO) {
        const mdFile = await localReadFile(`${dirPrefix}/${baseName}${ext}`)
        if (mdFile?.content) {
          content = mdFile.content
          foundExt = ext
          break
        }
      }
    }
    if (content) {
      const serverDir = nbCurrentDir.value ? `Notes/${nbCurrentDir.value}` : 'Notes'
      await putFile(`${serverDir}/${baseName}${foundExt}`, content)
      showSaveStatus('已导出', 'ok')
      setTimeout(() => { showSaveStatus('') }, 2000)
    }
  } catch {
    showSaveStatus('导出失败', 'err')
  }
}

async function deleteNotebookFile(fileName: string) {
  if (!confirm(`确定删除 "${fileName}"？此操作不可恢复。`)) return
  try {
    const { default: axios } = await import('axios')
    const baseURL = localStorage.getItem('ts2_server_url') || ''
    await axios.post(`${baseURL}/api/file/removeFile`, { path: nbCurrentDir.value ? `Notes/${nbCurrentDir.value}/${fileName}` : `Notes/${fileName}` })
    showSaveStatus('已删除', 'ok')
    loadNotebookList()
  } catch {
    showSaveStatus('删除失败', 'err')
  }
}

function createNewNotebook() {
  showNbList.value = false
  const name = prompt('新笔记标题：')
  if (!name || !name.trim()) return
  saveCurrentSlide()
  notebookId.value = generateId()
  notebookTitle.value = name.trim()
  slides.splice(0, slides.length, createSlide('', `# ${name.trim()}\n\n`))
  currentIndex.value = 0
  loadSlide(0)
  saveNotebook()
  if (nbSource.value === 'local') {
    saveToLocalNotebook()
  } else {
    doSaveToServer()
  }
}

// ─── 生命周期 ────────────────────────────────────────

// ─── 主题切换时更新 Vditor（无需销毁重建） ────────────────────────────

function onThemeChange(e: Event) {
  const theme = (e as CustomEvent).detail?.theme || 'dark'
  if (vditorInstance) {
    try {
      const vditorTheme = theme === 'light' ? 'classic' : 'dark'
      const contentTheme = theme === 'light' ? 'light' : 'dark'
      const codeTheme = theme === 'light' ? 'github' : 'tokyo-night-dark'
      vditorInstance.setTheme(vditorTheme, contentTheme, codeTheme)
    } catch { /* ignore if setTheme not available */ }
  }
}

onMounted(async () => {
  const nb = loadNotebook()
  notebookId.value = nb.id || generateId()
  notebookTitle.value = nb.title
  slides.splice(0, slides.length, ...nb.slides)
  currentIndex.value = 0

  await nextTick()
  await initVditor()

  loadNotebookList()
  startAutoSave()
  viewRef.value?.focus()

  window.addEventListener('ts2-theme-change', onThemeChange)
})

onUnmounted(() => {
  saveCurrentSlide()
  saveToLocalStorage()  // 始终保存到 localStorage
  // 退出时同步保存到当前源
  if (nbSource.value === 'local') {
    saveToLocalNotebookSilent()
  } else {
    doSaveToServer()
  }
  stopAutoSave()  // 停止周期性自动保存
  if (vditorInstance) {
    try { vditorInstance.destroy() } catch { /* ignore */ }
    vditorInstance = null
  }
  if (saveTimer) clearTimeout(saveTimer)
  window.removeEventListener('ts2-theme-change', onThemeChange)
})
</script>

<style scoped>
.slides-view {
  display: flex;
  flex-direction: column;
  height: 100vh;
  min-height: 100vh;
  outline: none;
  background: var(--bg);
}

/* ─── 顶部栏 ──────────────────────────────────────── */
.slides-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 12px;
  min-height: 44px;
  border-bottom: 1px solid var(--border);
  background: var(--bg-secondary);
  flex-shrink: 0;
  gap: 8px;
  position: relative;
  z-index: 10;
  flex-wrap: wrap;
}

.header-left {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
  flex-shrink: 1;
  flex-wrap: wrap;
}

.header-center {
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}

.header-right {
  display: flex;
  align-items: center;
  gap: 4px;
}

.header-divider {
  width: 1px;
  height: 18px;
  background: var(--border);
  margin: 0 4px;
}

.icon-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 32px;
  height: 32px;
  border: 1px solid var(--border);
  border-radius: 6px;
  background: var(--bg);
  color: var(--fg);
  cursor: pointer;
  transition: all 0.15s;
}

.icon-btn svg {
  stroke: var(--fg);
}

.icon-btn:hover {
  background: var(--btn-hover-bg, var(--border));
  color: var(--btn-hover-fg, var(--fg));
  border-color: var(--accent);
}

.icon-btn:hover svg {
  stroke: var(--btn-hover-fg, var(--fg));
}

.icon-btn:disabled {
  opacity: 0.35;
  cursor: not-allowed;
  border-color: var(--border);
}

.icon-btn.text-btn {
  font-size: 14px;
  font-weight: bold;
}

.btn-text {
  color: var(--fg);
  font-size: 14px;
  line-height: 1;
}

.icon-btn:hover .btn-text {
  color: var(--btn-hover-fg, var(--fg));
}

.page-arrow .arrow-text {
  color: var(--accent);
  font-size: 20px;
  font-weight: bold;
  line-height: 1;
  text-shadow: 0 0 2px rgba(var(--accent-rgb, 122, 162, 247), 0.5);
}

.page-arrow:disabled .arrow-text {
  color: var(--fg-muted);
  text-shadow: none;
}

.notebook-title-wrap {
  min-width: 0;
}

.notebook-title-input {
  padding: 4px 10px;
  border: 1px solid var(--border);
  border-radius: 6px;
  background: var(--bg);
  color: var(--fg);
  font-size: 14px;
  font-weight: 600;
  width: 180px;
  transition: all 0.15s;
}

.notebook-title-input:hover {
  background: var(--bg-secondary);
  border-color: var(--fg-muted);
}

.notebook-title-input:focus {
  outline: none;
  border-color: var(--accent);
  background: var(--bg);
}

/* 页码指示器 */
.page-indicator {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 4px 8px;
  border-radius: 8px;
  background: var(--bg);
  border: 1px solid var(--border);
}

.page-arrow {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 32px;
  height: 32px;
  border: 1px solid var(--border);
  border-radius: 6px;
  background: var(--bg);
  color: var(--accent);
  cursor: pointer;
  transition: all 0.15s;
}

.page-arrow:hover:not(:disabled) {
  background: var(--btn-hover-bg, var(--border));
  color: var(--btn-hover-fg, var(--fg));
  border-color: var(--accent);
}

.page-arrow:disabled {
  opacity: 0.3;
  cursor: not-allowed;
  border-color: var(--border);
}

.page-num {
  font-weight: 700;
  font-size: 15px;
  color: var(--accent);
  min-width: 20px;
  text-align: center;
}

.page-sep {
  color: var(--fg-muted);
  font-size: 12px;
}

.page-total {
  color: var(--fg-muted);
  font-size: 13px;
  min-width: 16px;
}

.save-badge {
  font-size: 11px;
  padding: 2px 10px;
  border-radius: 10px;
  white-space: nowrap;
  animation: fadeIn 0.2s;
}

.save-badge.ok {
  color: var(--success);
  background: rgba(var(--success-rgb, 74, 222, 128), 0.1);
}

.save-badge.err {
  color: var(--danger);
  background: rgba(var(--danger-rgb), 0.1);
}

@keyframes fadeIn {
  from { opacity: 0; transform: translateY(-4px); }
  to { opacity: 1; transform: translateY(0); }
}

/* ─── 主体 ──────────────────────────────────────── */
.slides-body {
  display: flex;
  flex: 1;
  overflow: hidden;
  min-width: 0;
}

/* ─── 大纲侧边栏 ──────────────────────────────────────── */
.slides-outline {
  width: 220px;
  border-right: 1px solid var(--border);
  background: var(--bg-secondary);
  display: flex;
  flex-direction: column;
  flex-shrink: 0;
  overflow: hidden;
  transition: width 0.2s ease, opacity 0.2s ease;
}

.slides-outline.sidebar-hidden {
  width: 0;
  opacity: 0;
  pointer-events: none;
}

.outline-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 10px 14px;
  border-bottom: 1px solid var(--border);
  flex-shrink: 0;
}

.outline-label {
  font-size: 12px;
  font-weight: 600;
  color: var(--fg-muted);
  text-transform: uppercase;
  letter-spacing: 0.5px;
}

.outline-count {
  font-size: 10px;
  color: var(--fg-muted);
  background: var(--bg);
  padding: 1px 6px;
  border-radius: 8px;
}

.outline-list {
  flex: 1;
  overflow-y: auto;
  padding: 4px;
}

.outline-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 10px;
  cursor: pointer;
  font-size: 12px;
  color: var(--fg-muted);
  border-radius: 6px;
  transition: all 0.15s;
  margin-bottom: 1px;
}

.outline-item:hover {
  background: var(--bg);
  color: var(--fg);
}

.outline-item.active {
  background: var(--outline-active-bg);
  color: var(--accent);
}

.outline-item.active .outline-num {
  color: var(--accent);
  font-weight: 700;
}

.outline-num {
  font-size: 10px;
  color: var(--fg-muted);
  min-width: 18px;
  text-align: center;
  font-variant-numeric: tabular-nums;
}

.outline-title {
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  line-height: 1.4;
}

.outline-del {
  display: flex;
  align-items: center;
  justify-content: center;
  background: none;
  border: none;
  color: var(--fg-muted);
  cursor: pointer;
  padding: 2px;
  border-radius: 4px;
  opacity: 0;
  transition: all 0.15s;
  flex-shrink: 0;
}

.outline-item:hover .outline-del {
  opacity: 0.6;
}

.outline-del:hover {
  opacity: 1 !important;
  color: var(--danger);
  background: rgba(var(--danger-rgb), 0.1);
}

.outline-add {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  padding: 10px;
  border: none;
  border-top: 1px solid var(--border);
  background: transparent;
  color: var(--fg-muted);
  font-size: 12px;
  cursor: pointer;
  transition: all 0.15s;
  flex-shrink: 0;
}

.outline-add:hover {
  color: var(--accent);
  background: var(--bg);
}

/* ─── 编辑区 ──────────────────────────────────────── */
.slides-editor {
  flex: 1;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  min-width: 0;
}

.slide-title-bar {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 16px;
  border-bottom: 1px solid var(--border);
  background: var(--bg-secondary);
  flex-shrink: 0;
}

.slide-title-input {
  flex: 1;
  padding: 4px 8px;
  border: 1px solid transparent;
  border-radius: 4px;
  background: transparent;
  color: var(--fg);
  font-size: 14px;
  font-weight: 500;
  transition: all 0.15s;
}

.slide-title-input:hover {
  background: var(--bg);
}

.slide-title-input:focus {
  outline: none;
  border-color: var(--accent);
  background: var(--bg);
}

.slide-title-input::placeholder {
  color: var(--fg-muted);
  font-weight: 400;
}

.slide-time {
  font-size: 11px;
  color: var(--fg-muted);
  font-variant-numeric: tabular-nums;
  flex-shrink: 0;
}

.vditor-container {
  flex: 1;
  overflow: hidden;
  min-height: 0;
}

.vditor-container :deep(.vditor) {
  border: none !important;
  border-radius: 0 !important;
  height: 100% !important;
  background: var(--bg) !important;
}

.vditor-container :deep(.vditor-toolbar) {
  background: var(--toolbar-bg, var(--bg-secondary)) !important;
  border-bottom: 1px solid var(--border) !important;
}

.vditor-container :deep(.vditor-toolbar__item) {
  color: var(--toolbar-item, var(--fg-muted)) !important;
}

.vditor-container :deep(.vditor-toolbar__item:hover) {
  color: var(--toolbar-item-hover, var(--fg)) !important;
}

.vditor-container :deep(.vditor-toolbar__item--current) {
  color: var(--accent) !important;
}

/* Vditor 编辑器内部 - 强制跟随主题 */
.vditor-container :deep(.vditor-ir) {
  background: var(--editor-bg, var(--bg)) !important;
  color: var(--fg) !important;
}

.vditor-container :deep(.vditor-sv) {
  background: var(--editor-bg, var(--bg)) !important;
  color: var(--fg) !important;
}

.vditor-container :deep(.vditor-wysiwyg) {
  background: var(--editor-bg, var(--bg)) !important;
  color: var(--fg) !important;
}

.vditor-container :deep(.vditor-reset) {
  background: var(--editor-bg, var(--bg)) !important;
  color: var(--fg) !important;
}

.vditor-container :deep(.vditor-content) {
  background: var(--editor-bg, var(--bg)) !important;
}

.vditor-container :deep(.vditor-ir__block),
.vditor-container :deep(.vditor-wysiwyg__block),
.vditor-container :deep(.vditor-sv__block) {
  background: var(--editor-bg, var(--bg)) !important;
  color: var(--fg) !important;
}

/* Vditor 预览模式 */
.vditor-container :deep(.vditor-preview) {
  background: var(--editor-bg, var(--bg)) !important;
  color: var(--fg) !important;
}

.vditor-container :deep(.vditor-preview__content) {
  color: var(--fg) !important;
}

/* Vditor 内容元素强制跟随主题（防止 content-theme CSS 冲突） */
.vditor-container :deep(.vditor-reset) h1,
.vditor-container :deep(.vditor-reset) h2,
.vditor-container :deep(.vditor-reset) h3,
.vditor-container :deep(.vditor-reset) h4,
.vditor-container :deep(.vditor-reset) h5,
.vditor-container :deep(.vditor-reset) h6,
.vditor-container :deep(.vditor-reset) p,
.vditor-container :deep(.vditor-reset) span,
.vditor-container :deep(.vditor-reset) div,
.vditor-container :deep(.vditor-reset) li,
.vditor-container :deep(.vditor-reset) blockquote,
.vditor-container :deep(.vditor-reset) pre,
.vditor-container :deep(.vditor-reset) table,
.vditor-container :deep(.vditor-reset) td,
.vditor-container :deep(.vditor-reset) th,
.vditor-container :deep(.vditor-reset) strong,
.vditor-container :deep(.vditor-reset) em {
  color: var(--fg) !important;
}

.vditor-container :deep(.vditor-reset) a {
  color: var(--accent) !important;
}

.vditor-container :deep(.vditor-reset) code:not(pre code) {
  background: var(--bg-tertiary) !important;
  color: var(--accent) !important;
}

.vditor-container :deep(.vditor-reset) pre {
  background: var(--bg-tertiary) !important;
  border-color: var(--border) !important;
}

.vditor-container :deep(.vditor-reset) blockquote {
  border-left-color: var(--accent) !important;
  background: var(--bg-secondary) !important;
  color: var(--fg) !important;
}

.vditor-container :deep(.vditor-reset) table {
  border-color: var(--border) !important;
}

.vditor-container :deep(.vditor-reset) table td,
.vditor-container :deep(.vditor-reset) table th {
  border-color: var(--border) !important;
}

.vditor-container :deep(.vditor-reset) hr {
  border-color: var(--border) !important;
}

.vditor-container :deep(.vditor-ir),
.vditor-container :deep(.vditor-sv),
.vditor-container :deep(.vditor-wysiwyg) {
  min-height: calc(100vh - 160px) !important;
}

/* textarea 降级编辑器 */
.fallback-textarea {
  flex: 1;
  width: 100%;
  padding: 16px;
  background: var(--bg);
  color: var(--fg);
  border: none;
  font-size: 15px;
  font-family: 'Consolas', 'Monaco', monospace;
  line-height: 1.6;
  resize: none;
  outline: none;
}

.fallback-textarea::placeholder {
  color: var(--fg-muted);
}

.md-toolbar {
  display: flex;
  gap: 4px;
  padding: 6px 10px;
  background: var(--bg-secondary);
  border-bottom: 1px solid var(--border);
  flex-wrap: wrap;
}

.md-toolbar button {
  padding: 4px 10px;
  border: 1px solid var(--border);
  border-radius: 4px;
  background: var(--bg);
  color: var(--fg);
  font-size: 13px;
  font-weight: bold;
  cursor: pointer;
  transition: all 0.15s;
}

.md-toolbar button:hover {
  background: var(--accent);
  color: var(--bg);
  border-color: var(--accent);
}

/* ─── 响应式 ──────────────────────────────────────── */

/* ─── 冲突解决对话框 ─── */
.conflict-overlay {
  position: fixed;
  inset: 0;
  background: rgba(0,0,0,0.5);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 100;
}

.conflict-dialog {
  background: var(--bg-secondary);
  border: 1px solid var(--border);
  border-radius: var(--radius-lg, 12px);
  padding: 24px;
  max-width: 360px;
  width: 90%;
  box-shadow: var(--shadow);
}

.conflict-dialog h3 {
  margin: 0 0 12px;
  font-size: 16px;
  color: var(--fg);
}

.conflict-dialog p {
  margin: 0 0 16px;
  font-size: 13px;
  color: var(--fg-muted);
  line-height: 1.5;
}

.conflict-info {
  display: flex;
  gap: 12px;
  margin-bottom: 20px;
}

.conflict-item {
  flex: 1;
  padding: 10px;
  border-radius: 8px;
  background: var(--bg);
  border: 1px solid var(--border);
  text-align: center;
}

.conflict-label {
  display: block;
  font-size: 12px;
  font-weight: 600;
  color: var(--fg);
  margin-bottom: 4px;
}

.conflict-time {
  font-size: 11px;
  color: var(--fg-muted);
}

.conflict-actions {
  display: flex;
  gap: 10px;
}

.conflict-btn {
  flex: 1;
  padding: 10px;
  border-radius: 8px;
  border: 1px solid var(--border);
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.15s;
}

.local-btn {
  background: var(--accent);
  color: #ffffff;
  border-color: var(--accent);
}

.local-btn:hover {
  opacity: 0.9;
}

.server-btn {
  background: var(--bg);
  color: var(--fg);
}

.server-btn:hover {
  background: var(--bg-tertiary);
}
@media (max-width: 768px) {
  .slides-outline {
    position: absolute;
    left: 0;
    top: 44px;
    bottom: 0;
    z-index: 20;
    box-shadow: 4px 0 12px rgba(0,0,0,0.15);
  }

  .notebook-title-input {
    width: 120px;
  }

  .header-right .icon-btn:nth-child(n+5) {
    display: none;
  }

  .vditor-container :deep(.vditor-toolbar) {
    overflow-x: auto;
    flex-wrap: nowrap;
  }
  .vditor-container :deep(.vditor-toolbar__item) {
    flex-shrink: 0;
  }
  .vditor-container :deep(.vditor-reset) {
    padding: 10px 8px !important;
    font-size: 15px;
  }
  .vditor-container :deep(.vditor-ir),
  .vditor-container :deep(.vditor-sv),
  .vditor-container :deep(.vditor-wysiwyg) {
    min-height: calc(100vh - 120px) !important;
  }
}

/* ─── 笔记选择器 ──────────────────────────────────────── */
.nb-selector {
  position: relative;
}

.nb-dropdown {
  position: absolute;
  top: 100%;
  left: 0;
  margin-top: 4px;
  min-width: 220px;
  max-width: calc(100vw - 24px);
  max-height: min(350px, calc(100vh - 80px));
  overflow-y: auto;
  background: var(--bg-secondary);
  border: 1px solid var(--border);
  border-radius: 8px;
  box-shadow: 0 8px 24px rgba(0,0,0,0.3);
  z-index: 50;
  padding: 4px;
}
@media (max-width: 600px) {
  .nb-dropdown {
    position: fixed;
    top: 52px;
    left: 8px;
    right: 8px;
    width: auto;
    max-width: none;
    max-height: calc(100vh - 80px);
  }
  .nb-dropdown-item .nb-dropdown-name {
    flex: 0 1 auto;
    width: calc(100% - 7ch);
  }
}

.nb-dropdown-breadcrumb {
  display: flex;
  align-items: center;
  gap: 2px;
  padding: 6px 8px;
  font-size: 11px;
  color: var(--fg-muted);
  border-bottom: 1px solid var(--border);
  margin-bottom: 4px;
  flex-wrap: wrap;
}
.nb-crumb {
  cursor: pointer;
  color: var(--accent);
}
.nb-crumb:hover { text-decoration: underline; }
.nb-crumb-sep { opacity: 0.5; }
.nb-dropdown-folder {
  font-weight: 500;
  color: var(--fg) !important;
}
.nb-dropdown-search {
  display: flex;
  align-items: center;
  gap: 4px;
  padding: 4px 6px;
  border-bottom: 1px solid var(--border);
  margin-bottom: 4px;
}
.nb-search-input {
  flex: 1;
  padding: 4px 8px;
  border: 1px solid var(--border);
  border-radius: 6px;
  background: var(--bg);
  color: var(--fg);
  font-size: 11px;
  outline: none;
  box-sizing: border-box;
}
.nb-search-clear {
  background: none;
  border: none;
  color: var(--fg-muted);
  cursor: pointer;
  font-size: 12px;
  padding: 2px 4px;
}
.nb-search-path {
  font-size: 9px;
  opacity: 0.5;
}

.nb-dropdown-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 10px;
  border-radius: 6px;
  cursor: pointer;
  font-size: 12px;
  color: var(--fg-muted);
  transition: all 0.1s;
}

.nb-dropdown-item:hover {
  background: var(--bg);
  color: var(--fg);
}

.nb-dropdown-name {
  flex: 1;
  min-width: 0;
  word-break: break-all;
}

.nb-dropdown-del {
  background: none;
  border: none;
  color: var(--fg-muted);
  font-size: 10px;
  cursor: pointer;
  padding: 2px 4px;
  border-radius: 3px;
  opacity: 0;
  transition: all 0.15s;
}

.nb-dropdown-item:hover .nb-dropdown-del {
  opacity: 0.6;
}

.nb-dropdown-del:hover {
  opacity: 1 !important;
  color: var(--danger);
  background: rgba(var(--danger-rgb), 0.1);
}

.nb-dropdown-import,
.nb-dropdown-export {
  background: none;
  border: none;
  color: var(--accent);
  font-size: 10px;
  cursor: pointer;
  padding: 2px 4px;
  border-radius: 3px;
  opacity: 0;
  transition: all 0.15s;
  margin-right: 2px;
}

.nb-dropdown-item:hover .nb-dropdown-import,
.nb-dropdown-item:hover .nb-dropdown-export {
  opacity: 0.7;
}

.nb-dropdown-import:hover,
.nb-dropdown-export:hover {
  opacity: 1 !important;
  background: rgba(59, 130, 246, 0.12);
}

.nb-dropdown-new {
  color: var(--accent);
  border-top: 1px solid var(--border);
  margin-top: 4px;
  padding-top: 8px;
  font-weight: 500;
}

/* ─── 源切换 ──────────────────────────────────────── */
.source-toggle {
  display: inline-flex;
  border: 1px solid var(--border);
  border-radius: 6px;
  overflow: hidden;
  flex-shrink: 0;
}
.source-btn {
  background: transparent;
  border: none;
  color: var(--fg-muted);
  padding: 3px 10px;
  font-size: 11px;
  cursor: pointer;
  transition: all 0.15s;
}
.source-btn.active {
  background: var(--accent);
  color: #fff;
}
.source-btn:hover:not(.active) {
  background: var(--bg-secondary);
}

/* 本地操作 */
.import-export-msg {
  font-size: 11px;
  color: var(--accent);
  margin-left: 4px;
  white-space: nowrap;
}
.local-stats {
  font-size: 10px;
  color: var(--fg-muted);
  margin-left: 4px;
  white-space: nowrap;
}
.nb-action-btn {
  font-size: 12px !important;
}
</style>

``



================================================
FILE: C:\Users\qu\Desktop\物理科学与技术论题\TS2\mcp\server\web\src\views\StatsView.vue
================================================

``vue
<template>
  <div class="view">
    <header class="view-header">
      <h1>统计</h1>
    </header>
    <div class="view-body stats-body">
      <div v-if="loading" class="loading">加载中...</div>
      <template v-else>
        <!-- 今日概览 -->
        <div class="stats-section">
          <h2 class="section-title">今日概览</h2>
          <div class="stats-grid">
            <div class="stat-card">
              <span class="stat-value">{{ pushData?.today_stats?.overdue_tasks_count ?? '-' }}</span>
              <span class="stat-label">超期任务</span>
            </div>
            <div class="stat-card">
              <span class="stat-value">{{ pushData?.today_stats?.due_tasks_count ?? '-' }}</span>
              <span class="stat-label">近期截止</span>
            </div>
            <div class="stat-card">
              <span class="stat-value">{{ pushData?.today_stats?.due_reviews_count ?? '-' }}</span>
              <span class="stat-label">待复习</span>
            </div>
          </div>
        </div>

        <!-- 课程统计 -->
        <div v-if="courseStats" class="stats-section">
          <h2 class="section-title">课程统计</h2>
          <div class="stats-grid">
            <div class="stat-card">
              <span class="stat-value">{{ courseStats.total_courses ?? '-' }}</span>
              <span class="stat-label">课程数</span>
            </div>
            <div class="stat-card">
              <span class="stat-value">{{ courseStats.total_lessons ?? '-' }}</span>
              <span class="stat-label">总课时</span>
            </div>
            <div class="stat-card">
              <span class="stat-value">{{ courseStats.complete_count ?? '-' }}</span>
              <span class="stat-label">已完成</span>
            </div>
            <div class="stat-card">
              <span class="stat-value">{{ courseStats.total_focus_hours?.toFixed(1) ?? '-' }}</span>
              <span class="stat-label">学时</span>
            </div>
          </div>
        </div>

        <!-- 服务器信息 -->
        <div v-if="serverInfo" class="stats-section">
          <h2 class="section-title">服务器</h2>
          <div class="info-list">
            <div class="info-row">
              <span class="info-label">版本</span>
              <span class="info-value">{{ serverInfo.version }}</span>
            </div>
            <div class="info-row">
              <span class="info-label">IP</span>
              <span class="info-value">{{ serverInfo.local_ip }}:{{ serverInfo.port }}</span>
            </div>
            <div class="info-row">
              <span class="info-label">运行时间</span>
              <span class="info-value">{{ formatUptime(serverInfo.uptime) }}</span>
            </div>
          </div>
        </div>
      </template>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import api from '../api'

const loading = ref(true)
const pushData = ref<any>(null)
const courseStats = ref<any>(null)
const serverInfo = ref<any>(null)

function formatUptime(seconds: number): string {
  const h = Math.floor(seconds / 3600)
  const m = Math.floor((seconds % 3600) / 60)
  if (h > 24) return `${Math.floor(h / 24)}天${h % 24}时`
  if (h > 0) return `${h}时${m}分`
  return `${m}分`
}

onMounted(async () => {
  const bootstrap = (window as any).__TS2_BOOTSTRAP__
  if (bootstrap) {
    pushData.value = bootstrap.push || null
    serverInfo.value = bootstrap.server || null
  }
  try {
    const [pushRes, statsRes] = await Promise.all([
      api.get('/api/push/dashboard'),
      api.get('/api/data/courses/stats'),
    ])
    pushData.value = pushRes.data?.data ?? pushRes.data
    courseStats.value = statsRes.data?.data ?? statsRes.data
  } catch { /* keep cached */ }
  finally {
    loading.value = false
  }
})
</script>

<style scoped>
.stats-body {
  padding: 12px;
}

.stats-section {
  margin-bottom: 20px;
}

.section-title {
  font-size: 13px;
  font-weight: 600;
  color: var(--fg-muted);
  margin-bottom: 10px;
  text-transform: uppercase;
  letter-spacing: 0.5px;
}

.stats-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(100px, 1fr));
  gap: 8px;
}

.stat-card {
  background: var(--card);
  border: 1px solid var(--border);
  border-radius: 10px;
  padding: 14px 12px;
  text-align: center;
}

.stat-value {
  display: block;
  font-size: 24px;
  font-weight: 700;
  color: var(--fg);
}

.stat-label {
  display: block;
  font-size: 11px;
  color: var(--fg-muted);
  margin-top: 4px;
}

.info-list {
  background: var(--card);
  border: 1px solid var(--border);
  border-radius: 10px;
  overflow: hidden;
}

.info-row {
  display: flex;
  justify-content: space-between;
  padding: 10px 14px;
  border-bottom: 1px solid var(--border);
  font-size: 13px;
}

.info-row:last-child {
  border-bottom: none;
}

.info-label {
  color: var(--fg-muted);
}

.info-value {
  color: var(--fg);
  font-family: monospace;
}

.loading {
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 200px;
  color: var(--fg-muted);
  font-size: 14px;
}
</style>

``



================================================
FILE: C:\Users\qu\Desktop\物理科学与技术论题\TS2\mcp\server\web\src\views\SubscriptionsView.vue
================================================

```vue
<template>
  <div class="subscriptions-view">
    <div class="subs-layout">
      <aside class="subs-sidebar">
        <div class="add-bar">
          <input v-model="subscribeUrl" class="add-input" placeholder="输入频道 URL..." @keyup.enter="subscribeChannel" />
          <select v-model="serviceName" class="service-select">
            <option value="YouTube">YouTube</option>
            <option value="BiliBili">BiliBili</option>
          </select>
          <button class="add-btn" @click="subscribeChannel" :disabled="subscribing">{{ subscribing ? '添加中...' : '订阅' }}</button>
        </div>
        <div v-if="subError" class="error-msg">{{ subError }}</div>
        <SubscriptionList :list="subStore.sorted" :active-url="selectedSub?.url" @select="onSubSelect" />
      </aside>
      <main class="subs-main">
        <div v-if="!selectedSub" class="placeholder">选择一个订阅频道查看最新视频</div>
        <div v-else-if="channelLoading" class="loading">加载中...</div>
        <div v-else-if="channelError" class="error-msg">{{ channelError }}</div>
        <template v-else>
          <div class="channel-header">
            <img :src="selectedSub.avatarUrl" :alt="selectedSub.name" class="channel-avatar" loading="lazy" @error="onAvatarError" />
            <div class="channel-info">
              <h2>{{ selectedSub.name }}</h2>
              <p class="channel-meta">{{ formatCount(selectedSub.subscriberCount) }} 订阅者</p>
              <p v-if="selectedSub.description" class="channel-desc">{{ selectedSub.description }}</p>
            </div>
          </div>
          <div class="grid">
            <VideoCard v-for="item in channelItems" :key="item.url" :item="item" @cardClick="onVideoClick" />
          </div>
        </template>
      </main>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import PipePipe from '../plugins/bridge'
import type { ChannelInfoResult, StreamInfoItem } from '../plugins/bridge'
import { useSubscriptionsStore } from '../stores/subscriptions'
import VideoCard from '../components/VideoCard.vue'
import SubscriptionList from '../components/SubscriptionList.vue'

const router = useRouter()
const subStore = useSubscriptionsStore()

const subCount = computed(() => subStore.subscriptions.length)

const subscribeUrl = ref('')
const serviceName = ref('YouTube')
const subscribing = ref(false)
const subError = ref('')

const selectedSub = ref(subStore.subscriptions[0] || undefined)
const channelLoading = ref(false)
const channelError = ref('')
const channelItems = ref<StreamInfoItem[]>([])

function onAvatarError(e: Event) {
  (e.target as HTMLImageElement).style.display = 'none'
}

onMounted(async () => {
  if (subStore.subscriptions.length > 0 && !selectedSub.value) {
    selectedSub.value = subStore.subscriptions[0]
  }
  if (selectedSub.value) {
    await loadChannelInfo(selectedSub.value)
  }
})

async function subscribeChannel() {
  const url = subscribeUrl.value.trim()
  if (!url) return
  subscribing.value = true
  subError.value = ''
  try {
    const resolved = await PipePipe.resolveUrl({ url })
    const info: ChannelInfoResult = await PipePipe.getChannelInfo({ url, serviceId: resolved.serviceId })
    subStore.subscribe({
      serviceId: resolved.serviceId,
      url,
      name: info.name,
      avatarUrl: info.avatarUrl,
      subscriberCount: info.subscriberCount,
      description: info.description,
    })
    const sub = subStore.getByUrl(url)
    if (sub) {
      selectedSub.value = sub
      channelItems.value = info.items
    }
    subscribeUrl.value = ''
  } catch (e: any) {
    subError.value = '订阅失败: ' + (e.message || e)
  } finally {
    subscribing.value = false
  }
}

async function loadChannelInfo(sub: any) {
  channelLoading.value = true
  channelError.value = ''
  channelItems.value = []
  try {
    let sid = sub.serviceId ?? -1
    if (sid < 0) { try { const r = await PipePipe.resolveUrl({ url: sub.url }); sid = r.serviceId } catch {} }
    if (sid < 0) { channelError.value = '无法解析 serviceId: ' + sub.url; channelLoading.value = false; return }
    const info = await PipePipe.getChannelInfo({ url: sub.url, serviceId: sid })
    subStore.updateInfo(sub.url, {
      name: info.name,
      avatarUrl: info.avatarUrl,
      subscriberCount: info.subscriberCount,
      description: info.description,
    })
    channelItems.value = info.items
  } catch (e: any) {
    channelError.value = '加载频道信息失败: ' + (e.message || e)
  } finally {
    channelLoading.value = false
  }
}

async function onSubSelect(sub: any) {
  selectedSub.value = sub
  await loadChannelInfo(sub)
}

function onVideoClick(item: StreamInfoItem) {
  router.push({ name: 'video-player', query: { url: item.url } })
}

function formatCount(n: number): string {
  if (n >= 10000) return (n / 10000).toFixed(1) + '万'
  if (n >= 1000) return (n / 1000).toFixed(1) + 'k'
  return String(n)
}
</script>

<style scoped>
.subscriptions-view { height: 100%; overflow: hidden; }

.subs-layout { display: flex; gap: 16px; height: 100%; }

.subs-sidebar { width: 280px; flex-shrink: 0; display: flex; flex-direction: column; overflow: hidden; border-right: 1px solid var(--border); padding-right: 8px; }

.subs-main { flex: 1; overflow-y: auto; }

.add-bar { display: flex; gap: 6px; margin-bottom: 8px; flex-shrink: 0; }
.add-input { flex: 1; padding: 8px 12px; border: 1px solid var(--border); border-radius: 8px; background: var(--bg-secondary); color: var(--fg); font-size: 13px; min-width: 0; }
.add-input:focus { outline: none; border-color: var(--accent); }
.service-select { padding: 8px 8px; border: 1px solid var(--border); border-radius: 8px; background: var(--bg-secondary); color: var(--fg); font-size: 12px; cursor: pointer; }
.add-btn { padding: 8px 12px; background: var(--accent); color: var(--bg); border: none; border-radius: 8px; font-size: 13px; font-weight: 600; cursor: pointer; white-space: nowrap; }
.add-btn:disabled { opacity: 0.5; }

.error-msg { padding: 6px 10px; margin-bottom: 8px; font-size: 12px; color: #e74c3c; background: #fdf0ef; border-radius: 6px; border: 1px solid #f5c6cb; flex-shrink: 0; }

.channel-header { display: flex; align-items: center; gap: 12px; margin-bottom: 16px; padding-bottom: 12px; border-bottom: 1px solid var(--border); }
.channel-avatar { width: 56px; height: 56px; border-radius: 50%; object-fit: cover; background: var(--border); }
.channel-info h2 { font-size: 18px; font-weight: 700; margin: 0 0 4px; color: var(--fg); }
.channel-meta { font-size: 12px; color: var(--fg-muted); margin: 0 0 4px; }
.channel-desc { font-size: 12px; color: var(--fg-muted); margin: 0; display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; }

.grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(180px, 1fr)); gap: 12px; }

.placeholder { text-align: center; padding: 48px 16px; color: var(--fg-muted); font-size: 14px; }
.loading { text-align: center; padding: 32px; color: var(--fg-muted); }

@media (max-width: 600px) {
  .subs-layout { flex-direction: column; }
  .subs-sidebar { width: 100%; border-right: none; border-bottom: 1px solid var(--border); padding-right: 0; padding-bottom: 8px; max-height: 200px; }
  .grid { grid-template-columns: repeat(2, 1fr); }
}
</style>

```



================================================
FILE: C:\Users\qu\Desktop\物理科学与技术论题\TS2\mcp\server\web\src\views\TasksView.vue
================================================

``vue
<template>
  <div class="view tasks-view">
    <!-- 主内容 -->
    <div class="task-main">
      <header class="view-header">
        <SpaceSelector :counts="spaceCounts" />
        <div class="source-toggle">
          <button class="source-btn" :class="{ active: store.source === 'server' }" @click="switchSource('server')">服务端</button>
          <button class="source-btn" :class="{ active: store.source === 'local' }" @click="switchSource('local')">本地</button>
        </div>
        <button v-if="spacesStore.activeSpace" class="btn-rename" @click="startRename" title="重命名空间">✏️</button>
        <div v-if="store.source === 'server'" class="sync-buttons">
          <button class="btn-icon" @click="doSyncFromServer" title="从服务器拉取">↓</button>
          <button class="btn-icon" @click="doSyncToServer" title="推送到服务器">↑</button>
        </div>
        <div class="header-spacer"></div>
        <div class="header-right">
          <div class="search-box">
            <input v-model="searchQuery" type="text" class="search-input" placeholder="搜索任务..." @input="onSearchInput" />
            <button v-if="searchQuery" class="search-clear" @click="searchQuery = ''">✕</button>
          </div>
          <div class="view-toggle">
            <button class="toggle-btn" :class="{ active: currentView === 'kanban' }" @click="currentView = 'kanban'">看板</button>
            <button class="toggle-btn" :class="{ active: currentView === 'calendar' }" @click="currentView = 'calendar'">日历</button>
          </div>
          <select v-model="priorityFilter" class="filter-select">
            <option value="">全部优先级</option>
            <option value="高">高</option>
            <option value="中">中</option>
            <option value="低">低</option>
          </select>
        </div>
      </header>

      <!-- 统计栏 -->
      <div class="stats-bar">
        <div class="stat-item">
          <span class="stat-value">{{ stats.total }}</span>
          <span class="stat-label">总任务</span>
        </div>
        <div class="stat-item stat-done">
          <span class="stat-value">{{ stats.done }}</span>
          <span class="stat-label">已完成</span>
        </div>
        <div class="stat-item stat-overdue">
          <span class="stat-value">{{ stats.overdue }}</span>
          <span class="stat-label">逾期</span>
        </div>
        <div class="stat-item stat-today">
          <span class="stat-value">{{ stats.todayDue }}</span>
          <span class="stat-label">今日到期</span>
        </div>
        <div class="stat-item stat-time">
          <span class="stat-value">{{ formatMinutes(stats.totalTracked) }}</span>
          <span class="stat-label">追踪时长</span>
        </div>
      </div>

      <div class="view-body kanban-container">
        <div v-if="store.loading" class="loading">加载中...</div>
        <KanbanBoard
          v-else-if="currentView === 'kanban'"
          :tasks="currentTasks"
          :priority-filter="priorityFilter || undefined"
          @add-task="openAddModal"
          @delete-task="confirmDelete"
          @edit-task="openEditModal"
          @status-change="handleStatusChange"
          @start-timer="handleStartTimer"
          @stop-timer="handleStopTimer"
          @toggle-subtask="handleToggleSubtask"
        />
        <CalendarView
          v-else
          :tasks="currentTasks"
          :priority-filter="priorityFilter || undefined"
          @add-task="openAddModal"
          @delete-task="confirmDelete"
          @edit-task="openEditModal"
          @status-change="handleStatusChange"
          @start-timer="handleStartTimer"
          @stop-timer="handleStopTimer"
          @toggle-subtask="handleToggleSubtask"
        />
      </div>

      <!-- 重命名输入 -->
      <Teleport to="body">
        <div v-if="showRename" class="modal-overlay" @click.self="showRename = false">
          <div class="modal modal-sm">
            <h2 class="modal-title">重命名空间</h2>
            <input v-model="renameBuffer" class="rename-input" @keyup.enter="doRename" />
            <div class="modal-actions">
              <button class="btn-cancel" @click="showRename = false">取消</button>
              <button class="btn-submit" @click="doRename">确定</button>
            </div>
          </div>
        </div>
      </Teleport>

      <!-- 添加/编辑任务弹窗 -->
      <Teleport to="body">
        <div v-if="showModal" class="modal-overlay" @click.self="closeModal">
          <div class="modal">
            <h2 class="modal-title">{{ isEditing ? '编辑任务' : '添加任务' }}</h2>
            <form class="modal-form" @submit.prevent="handleSubmit">
              <label class="form-label">
                标题 <span class="required">*</span>
                <input v-model="form.title" type="text" required placeholder="输入任务标题" />
              </label>
              <label class="form-label">
                描述
                <textarea v-model="form.description" rows="3" placeholder="任务描述（可选）"></textarea>
              </label>
              <div class="form-row">
                <label class="form-label">
                  截止日期
                  <input v-model="form.due_date" type="date" />
                </label>
                <label class="form-label">
                  开始时间
                  <input v-model="form.start_time" type="datetime-local" />
                </label>
              </div>
              <div class="form-row">
                <label class="form-label">
                  优先级
                  <select v-model="form.priority">
                    <option value="高">高</option>
                    <option value="中">中</option>
                    <option value="低">低</option>
                  </select>
                </label>
                <label class="form-label">
                  时长（分钟）
                  <input v-model.number="form.duration" type="number" min="1" />
                </label>
              </div>
              <div class="form-row">
                <label class="form-label">
                  循环
                  <select v-model="form.recurrence">
                    <option value="不循环">不循环</option>
                    <option value="每天">每天</option>
                    <option value="每周">每周</option>
                    <option value="每月">每月</option>
                    <option value="工作日">工作日</option>
                  </select>
                </label>
                <label class="form-label">
                  提醒时间
                  <input v-model="form.reminder" type="datetime-local" />
                </label>
              </div>

              <label class="form-label">
                颜色
                <div class="color-swatches">
                  <button
                    v-for="c in colorPresets" :key="c" type="button"
                    class="color-swatch" :class="{ active: form.color === c }"
                    :style="{ background: c }" @click="form.color = form.color === c ? '' : c"
                  ></button>
                </div>
              </label>

              <label class="form-label">
                标签（逗号分隔）
                <input v-model="tagsInput" type="text" placeholder="如：工作,重要" @input="parseTags" />
                <div v-if="form.tags.length" class="tags-preview">
                  <span v-for="tag in form.tags" :key="tag" class="tag-badge">
                    {{ tag }}
                    <button type="button" class="tag-remove" @click="removeTag(tag)">×</button>
                  </span>
                </div>
              </label>

              <label class="form-label">
                子任务
                <div class="subtask-list">
                  <div v-for="(st, idx) in form.subtasks" :key="idx" class="subtask-row">
                    <input type="checkbox" :checked="st.done" @change="form.subtasks[idx].done = !form.subtasks[idx].done" />
                    <input v-model="form.subtasks[idx].title" type="text" class="subtask-input" placeholder="子任务名称" />
                    <button type="button" class="subtask-remove" @click="form.subtasks.splice(idx, 1)">×</button>
                  </div>
                  <div class="subtask-add-row">
                    <input v-model="newSubtaskTitle" type="text" class="subtask-input" placeholder="添加子任务..." @keydown.enter.prevent="addSubtaskInline" />
                    <button type="button" class="subtask-add-btn" @click="addSubtaskInline">＋</button>
                  </div>
                </div>
              </label>

              <div class="modal-actions">
                <button type="button" class="btn-cancel" @click="closeModal">取消</button>
                <button type="submit" class="btn-submit">{{ isEditing ? '保存' : '添加' }}</button>
              </div>
            </form>
          </div>
        </div>
      </Teleport>

      <!-- 删除确认 -->
      <Teleport to="body">
        <div v-if="showDeleteConfirm" class="modal-overlay" @click.self="showDeleteConfirm = false">
          <div class="modal modal-sm">
            <h2 class="modal-title">确认删除</h2>
            <p class="modal-text">确定要删除此任务吗？</p>
            <div class="modal-actions">
              <button class="btn-cancel" @click="showDeleteConfirm = false">取消</button>
              <button class="btn-danger" @click="handleDelete">删除</button>
            </div>
          </div>
        </div>
      </Teleport>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed, onMounted } from 'vue'
import { useTasksStore } from '../stores/tasks'
import { useSpacesStore } from '../stores/spaces'
import type { SubTask } from '../stores/tasks'
import KanbanBoard from '../components/KanbanBoard.vue'
import CalendarView from '../components/CalendarView.vue'
import SpaceSelector from '../components/SpaceSelector.vue'

const store = useTasksStore()
const spacesStore = useSpacesStore()

const priorityFilter = ref('')
const searchQuery = ref('')
const currentView = ref<'kanban' | 'calendar'>('kanban')

let searchTimer: ReturnType<typeof setTimeout> | null = null
function onSearchInput() {
  if (searchTimer) clearTimeout(searchTimer)
}

const colorPresets = ['#ef4444', '#f59e0b', '#22c55e', '#3b82f6', '#8b5cf6', '#ec4899', '#06b6d4', '#6366f1']

const currentTasks = computed(() => {
  if (!spacesStore.activeSpaceId || !store.bySpace) return []
  let list = store.bySpace[spacesStore.activeSpaceId] ?? []
  if (searchQuery.value.trim()) {
    const q = searchQuery.value.trim().toLowerCase()
    list = list.filter(t =>
      t.title.toLowerCase().includes(q) ||
      (t.description || '').toLowerCase().includes(q) ||
      (t.tags || []).some(tag => tag.toLowerCase().includes(q))
    )
  }
  return list
})

const stats = computed(() => {
  if (!spacesStore.activeSpaceId) return { total: 0, done: 0, overdue: 0, todayDue: 0, totalTracked: 0 }
  return store.getStats(spacesStore.activeSpaceId)
})

const spaceCounts = computed(() => {
  const out: Record<string, number> = {}
  if (!store.bySpace) return out
  for (const sp of spacesStore.spaces) {
    out[sp.id] = (store.bySpace[sp.id] ?? []).length
  }
  return out
})

// 空间管理
const showCreateSpace = ref(false)
const newSpaceName = ref('')
const spaceInputRef = ref<HTMLInputElement | null>(null)
const showRename = ref(false)
const renameBuffer = ref('')

function selectSpace(id: string) {
  spacesStore.selectSpace(id)
}

function removeSpace(id: string) {
  spacesStore.removeSpace(id)
}

function doCreateSpace() {
  const name = newSpaceName.value.trim()
  if (!name) return
  spacesStore.addSpace(name)
  newSpaceName.value = ''
  showCreateSpace.value = false
}

function startRename() {
  if (!spacesStore.activeSpace) return
  renameBuffer.value = spacesStore.activeSpace.name
  showRename.value = true
}

function doRename() {
  if (!spacesStore.activeSpaceId || !renameBuffer.value.trim()) return
  spacesStore.renameSpace(spacesStore.activeSpaceId, renameBuffer.value.trim())
  showRename.value = false
}

// 任务 CRUD
const showModal = ref(false)
const isEditing = ref(false)
const editingTaskId = ref<string | null>(null)
const defaultStatus = ref('待办')

const form = reactive({
  title: '', description: '', due_date: '', priority: '中',
  start_time: '', duration: 60, recurrence: '不循环', color: '',
  tags: [] as string[], subtasks: [] as SubTask[], reminder: '',
})
const tagsInput = ref('')
const newSubtaskTitle = ref('')
const showDeleteConfirm = ref(false)
const deletingId = ref<string | null>(null)

onMounted(async () => {
  const bootstrap = (window as any).__TS2_BOOTSTRAP__
  if (bootstrap?.tasks) {
    store.setTasks(Array.isArray(bootstrap.tasks) ? bootstrap.tasks : [])
    delete bootstrap.tasks
  }
  // 默认本地模式，不再自动切换服务端；由 App.vue 后台连接成功后统一切 source
})

function switchSource(val: 'local' | 'server') {
  if (val === 'server') store.switchToServer()
  else store.switchToLocal()
}

async function doSyncFromServer() {
  await store.syncFromServer()
}

async function doSyncToServer() {
  await store.syncToServer()
}

function resetForm() {
  form.title = ''; form.description = ''; form.due_date = ''
  form.priority = '中'; form.start_time = ''; form.duration = 60
  form.recurrence = '不循环'; form.color = ''; form.tags = []
  form.subtasks = []; form.reminder = ''
  tagsInput.value = ''; newSubtaskTitle.value = ''
}

function openAddModal(status: string) {
  if (!spacesStore.activeSpaceId) return
  resetForm()
  isEditing.value = false
  editingTaskId.value = null
  defaultStatus.value = status
  showModal.value = true
}

function openEditModal(task: any) {
  isEditing.value = true
  editingTaskId.value = task.id
  form.title = task.title; form.description = task.description || ''
  form.due_date = task.due_date || ''; form.priority = task.priority || '中'
  form.start_time = task.start_time || ''; form.duration = task.duration || 60
  form.recurrence = task.recurrence || '不循环'; form.color = task.color || ''
  form.tags = task.tags ? [...task.tags] : []
  form.subtasks = task.subtasks ? task.subtasks.map((s: any) => ({ ...s })) : []
  form.reminder = task.reminder || ''
  tagsInput.value = form.tags.join(', ')
  showModal.value = true
}

function closeModal() { showModal.value = false; editingTaskId.value = null }

async function handleSubmit() {
  if (!form.title.trim() || !spacesStore.activeSpaceId) return
  if (isEditing.value && editingTaskId.value) {
    await store.editTask(editingTaskId.value, { ...form })
  } else {
    await store.addTask(spacesStore.activeSpaceId, { ...form, status: defaultStatus.value })
  }
  closeModal()
}

function confirmDelete(id: string) { deletingId.value = id; showDeleteConfirm.value = true }

async function handleDelete() {
  if (deletingId.value) {
    await store.removeTask(deletingId.value)
    deletingId.value = null
    showDeleteConfirm.value = false
  }
}

async function handleStatusChange(id: string, newStatus: string) {
  if (newStatus === '已完成') {
    const all = Object.values(store.bySpace).flat()
    const task = all.find(t => t.id === id)
    if (task && task.recurrence && task.recurrence !== '不循环') {
      store.completeRecurring(id)
      return
    }
  }
  await store.editTask(id, { status: newStatus })
}

function handleStartTimer(id: string) { store.startTimer(id) }
function handleStopTimer(id: string) { store.stopTimer(id) }
async function handleToggleSubtask(taskId: string, subtaskId: string) { await store.toggleSubtask(taskId, subtaskId) }

function parseTags() {
  form.tags = tagsInput.value.split(',').map(t => t.trim()).filter(t => t.length > 0)
}
function removeTag(tag: string) {
  form.tags = form.tags.filter(t => t !== tag)
  tagsInput.value = form.tags.join(', ')
}
function addSubtaskInline() {
  const title = newSubtaskTitle.value.trim()
  if (!title) return
  form.subtasks.push({ id: `sub_${Date.now()}_${Math.random().toString(36).slice(2, 6)}`, title, done: false })
  newSubtaskTitle.value = ''
}
function formatMinutes(min: number): string {
  if (min < 60) return `${min}分钟`
  const h = Math.floor(min / 60)
  const m = min % 60
  return m > 0 ? `${h}h${m}m` : `${h}h`
}
</script>

<style scoped>
.tasks-view {
  display: flex;
  flex: 1;
  min-height: 0;
  overflow: hidden;
}

.space-sidebar {
  width: 180px;
  flex-shrink: 0;
  background: var(--bg-secondary);
  border-right: 1px solid var(--border);
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.space-sidebar-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px;
  border-bottom: 1px solid var(--border);
}

.space-sidebar-header h3 {
  font-size: 13px;
  font-weight: 600;
  color: var(--fg);
}

.btn-space-add {
  width: 24px; height: 24px;
  display: flex; align-items: center; justify-content: center;
  background: rgba(255,255,255,0.06);
  border: 1px solid var(--border);
  border-radius: 4px;
  color: var(--fg-muted);
  font-size: 14px;
  cursor: pointer;
  padding: 0;
}

.btn-space-add:hover { background: rgba(122,162,247,0.15); color: var(--accent); }

.space-list {
  flex: 1;
  overflow-y: auto;
  padding: 4px;
}

.space-item {
  display: flex;
  align-items: center;
  gap: 4px;
  padding: 8px 10px;
  border-radius: 6px;
  cursor: pointer;
  transition: background 0.15s;
  font-size: 13px;
}

.space-item:hover { background: rgba(255,255,255,0.04); }
.space-item.active { background: rgba(122,162,247,0.12); color: var(--accent); }

.space-name { flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.space-count { font-size: 11px; color: var(--fg-muted); }
.space-del-btn {
  background: transparent; border: none; color: var(--fg-muted);
  font-size: 12px; cursor: pointer; padding: 2px 4px; border-radius: 3px;
}
.space-del-btn:hover { background: rgba(239,68,68,0.15); color: #ef4444; }

.space-create-form {
  display: flex;
  gap: 4px;
  padding: 8px;
  border-top: 1px solid var(--border);
  flex-wrap: wrap;
}

.space-create-input {
  flex: 1; min-width: 0;
  background: var(--bg); color: var(--fg);
  border: 1px solid var(--border); border-radius: 4px;
  padding: 4px 8px; font-size: 12px;
}

.btn-space-confirm, .btn-space-cancel {
  background: rgba(122,162,247,0.15); color: var(--accent);
  border: none; border-radius: 4px; padding: 4px 8px; font-size: 11px; cursor: pointer;
}
.btn-space-cancel { background: transparent; color: var(--fg-muted); }

.task-main {
  flex: 1;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.header-left {
  display: flex;
  align-items: center;
  gap: 8px;
}

.view-header {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 8px 16px;
  flex-wrap: nowrap;
  flex-shrink: 0;
  border-bottom: 1px solid var(--border);
  background: var(--bg-secondary);
}

.header-spacer { flex: 1; min-width: 0; }
.header-right { display: flex; align-items: center; gap: 10px; flex-shrink: 0; }

.sync-buttons { display: inline-flex; gap: 2px; flex-shrink: 0; }
.btn-icon { background: transparent; border: 1px solid var(--border); border-radius: 4px; color: var(--fg-muted); padding: 2px 6px; font-size: 12px; cursor: pointer; line-height: 1.4; transition: all 0.15s; }
.btn-icon:hover { background: var(--bg-tertiary); border-color: var(--accent); color: var(--accent); }

.source-toggle { display: inline-flex; border: 1px solid var(--border); border-radius: 6px; overflow: hidden; flex-shrink: 0; }
.source-btn { background: transparent; border: none; color: var(--fg-muted); padding: 3px 10px; font-size: 11px; cursor: pointer; transition: all 0.15s; }
.source-btn.active { background: var(--accent); color: #fff; }
.source-btn:hover:not(.active) { background: var(--bg-secondary); }

.btn-rename {
  background: transparent; border: none; color: var(--fg-muted);
  font-size: 14px; cursor: pointer; padding: 4px;
}

.header-actions { display: flex; align-items: center; gap: 10px; }

.view-toggle { display: flex; border: 1px solid var(--border); border-radius: 6px; overflow: hidden; }
.toggle-btn {
  background: transparent; color: var(--fg-muted); border: none;
  padding: 5px 14px; font-size: 13px; cursor: pointer;
}
.toggle-btn.active { background: var(--accent); color: var(--bg); font-weight: 600; }

.search-box { display: flex; align-items: center; gap: 4px; position: relative; }
.search-input {
  background: var(--bg); color: var(--fg);
  border: 1px solid var(--border); border-radius: 6px;
  padding: 5px 10px; font-size: 13px; outline: none; width: 160px;
  transition: border-color 0.15s;
}
.search-input:focus { border-color: var(--accent); }
.search-clear {
  position: absolute; right: 4px; top: 50%; transform: translateY(-50%);
  background: transparent; border: none; color: var(--fg-muted);
  font-size: 14px; cursor: pointer; padding: 2px;
}

.filter-select {
  background: var(--bg); color: var(--fg);
  border: 1px solid var(--border); border-radius: 6px;
  padding: 4px 8px; font-size: 13px; outline: none;
}

.stats-bar {
  display: flex; gap: 12px; padding: 12px 16px;
  background: var(--bg-secondary); border: 1px solid var(--border);
  border-radius: 10px; margin: 0 12px 8px;
}
.stat-item { display: flex; flex-direction: column; align-items: center; flex: 1; gap: 2px; }
.stat-value { font-size: 20px; font-weight: 700; color: var(--fg); }
.stat-label { font-size: 11px; color: var(--fg-muted); }
.stat-done .stat-value { color: var(--success); }
.stat-overdue .stat-value { color: #ef4444; }
.stat-today .stat-value { color: var(--warning); }
.stat-time .stat-value { color: #3b82f6; }

.kanban-container { padding: 12px; overflow: auto; flex: 1; min-height: 0; display: flex; flex-direction: column; }
.loading { text-align: center; padding: 48px 0; color: var(--fg-muted); font-size: 14px; }

.modal-overlay {
  position: fixed; inset: 0; z-index: 200;
  background: rgba(0,0,0,0.6);
  display: flex; align-items: center; justify-content: center; padding: 16px;
}
.modal {
  background: var(--bg-secondary); border: 1px solid var(--border);
  border-radius: 12px; padding: 24px; width: 100%;
  max-width: 520px; max-height: 90vh; overflow-y: auto;
}
.modal-sm { max-width: 360px; }
.modal-title { font-size: 18px; font-weight: 600; color: var(--fg); margin-bottom: 20px; }
.modal-text { color: var(--fg-muted); font-size: 14px; margin-bottom: 20px; }
.modal-form { display: flex; flex-direction: column; gap: 14px; }
.form-label { display: flex; flex-direction: column; gap: 4px; font-size: 13px; color: var(--fg-muted); }
.required { color: var(--danger); }
.form-row { display: flex; gap: 12px; }
.form-row .form-label { flex: 1; }
.modal-actions { display: flex; justify-content: flex-end; gap: 8px; margin-top: 8px; }

.btn-cancel {
  background: transparent; color: var(--fg-muted);
  border: 1px solid var(--border); padding: 8px 20px; border-radius: 6px; font-size: 14px; cursor: pointer;
}
.btn-submit {
  background: var(--accent); color: var(--bg); border: none;
  padding: 8px 20px; border-radius: 6px; font-size: 14px; font-weight: 600; cursor: pointer;
}
.btn-danger {
  background: var(--danger); color: #fff; border: none;
  padding: 8px 20px; border-radius: 6px; font-size: 14px; font-weight: 600; cursor: pointer;
}

.rename-input {
  width: 100%; padding: 8px 12px; border: 1px solid var(--border);
  border-radius: 6px; background: var(--bg); color: var(--fg);
  font-size: 14px; margin-bottom: 16px;
}

.color-swatches { display: flex; gap: 8px; flex-wrap: wrap; margin-top: 4px; }
.color-swatch {
  width: 28px; height: 28px; border-radius: 50%; border: 2px solid transparent;
  cursor: pointer; transition: border-color 0.15s, transform 0.15s; padding: 0;
}
.color-swatch:hover { transform: scale(1.15); }
.color-swatch.active { border-color: var(--fg); transform: scale(1.15); }
.tags-preview { display: flex; flex-wrap: wrap; gap: 4px; margin-top: 4px; }
.tag-badge {
  display: inline-flex; align-items: center; gap: 2px; padding: 2px 8px;
  border-radius: 10px; font-size: 11px; font-weight: 500;
  background: rgba(59,130,246,0.15); color: #60a5fa; border: 1px solid rgba(59,130,246,0.25);
}
.tag-remove { background: transparent; border: none; color: #60a5fa; font-size: 13px; cursor: pointer; padding: 0 2px; }
.subtask-list { display: flex; flex-direction: column; gap: 6px; margin-top: 4px; }
.subtask-row { display: flex; align-items: center; gap: 6px; }
.subtask-input { flex: 1; background: var(--bg); color: var(--fg); border: 1px solid var(--border); border-radius: 4px; padding: 4px 8px; font-size: 13px; }
.subtask-remove { background: transparent; border: none; color: var(--fg-muted); font-size: 16px; cursor: pointer; }
.subtask-add-row { display: flex; gap: 6px; }
.subtask-add-btn { background: rgba(255,255,255,0.06); border: 1px solid var(--border); color: var(--fg-muted); border-radius: 4px; padding: 4px 10px; font-size: 14px; cursor: pointer; }

@media (max-width: 768px) {
  .space-sidebar { width: 140px; }
  .stats-bar { flex-wrap: wrap; }
  .form-row { flex-direction: column; }
}
</style>

``



================================================
FILE: C:\Users\qu\Desktop\物理科学与技术论题\TS2\mcp\server\web\src\views\TimetableView.vue
================================================

``vue
<template>
  <div class="view timetableView">
    <!-- 主内容 -->
    <div class="tt-main">
      <header class="view-header">
        <SpaceSelector />
        <div class="source-toggle">
          <button class="source-btn" :class="{ active: store.source === 'server' }" @click="switchSource('server')">服务端</button>
          <button class="source-btn" :class="{ active: store.source === 'local' }" @click="switchSource('local')">本地</button>
        </div>
        <!-- 课程表切换 -->
        <div class="tt-selector" v-if="ttList.length > 0">
          <button class="tt-trigger" @click="ttOpen = !ttOpen">
            <span class="tt-trigger-label">{{ activeTT?.name || '选择课程表' }}</span>
            <span class="tt-trigger-arrow">▾</span>
          </button>
          <div v-if="ttOpen" class="tt-dropdown" @click.stop>
            <div
              v-for="tt in ttList"
              :key="tt.timetable_id"
              class="tt-option"
              :class="{ active: tt.timetable_id === activeTTId }"
              @click="switchTT(tt.timetable_id)"
            >
              <span class="tt-opt-name">{{ tt.name }}</span>
              <span v-if="tt.timetable_id === activeTTId" class="tt-opt-check">✓</span>
              <button
                v-if="ttList.length > 1"
                class="tt-opt-del"
                @click.stop="deleteTT(tt.timetable_id)"
                title="删除课程表"
              >✕</button>
            </div>
            <div class="tt-dropdown-divider"></div>
            <div class="tt-option tt-option-new" @click="showCreateTT = true; ttOpen = false">
              <span style="font-weight:600">＋ 新建课程表</span>
            </div>
          </div>
        </div>
        <div v-if="store.source === 'server'" class="sync-buttons">
           <button class="btn-icon" @click="store.syncFromServer()" title="从服务器拉取">↓</button>
           <button class="btn-icon" @click="store.syncToServer()" title="推送到服务器">↑</button>
         </div>
         <button class="btn-action" style="margin-left:auto" @click="showAddSlot = true" :disabled="!activeTT">+ 添加课时</button>
      </header>

      <div v-if="store.loading" class="loading">加载中...</div>
      <div v-else-if="!activeTT" class="empty-state">
        <p>暂无课程表</p>
        <button class="btn-action" @click="showCreateTT = true">创建课程表</button>
      </div>

      <div v-else class="timetable-container">
        <div class="week-info">
          <span class="week-label">{{ activeTT.name }}</span>
          <span v-if="activeTT.semester_start" class="week-dates">
            {{ activeTT.semester_start }} ~ {{ activeTT.semester_end }}
          </span>
          <span class="week-label" style="margin-left:auto">第 {{ weekNumber }} 周</span>
        </div>

        <div class="timetable-scroll">
          <div class="timetable-grid">
            <div class="grid-corner"></div>
            <div v-for="day in 7" :key="day" class="grid-header" :class="{ 'is-today': day === currentDow }">
              <span class="header-day">{{ DAY_NAMES[day] }}</span>
              <span class="header-date">{{ getDateStr(day) }}</span>
            </div>

            <template v-for="(period, pIdx) in PERIODS" :key="pIdx">
              <div class="grid-time" :class="`cat-${period.category}`">
                <span class="time-name">{{ period.name }}</span>
                <span class="time-range">{{ period.start }}</span>
              </div>
              <div
                v-for="day in 7" :key="`${day}-${pIdx}`"
                class="grid-cell"
                :class="{ 'is-today': day === currentDow, 'is-current': isCurrentSlot(day, pIdx), 'is-break': period.category === 'lunch' || period.category === 'evening' }"
                @click="openSlotDetail(day, pIdx)"
              >
                <div v-if="slotMap.get(`${day}_${pIdx}`)" class="slot-chip"
                  :style="{ background: getColor(slotMap.get(`${day}_${pIdx}`)) }"
                >
                  <div class="slot-main" @click.stop="goExecute(slotMap.get(`${day}_${pIdx}`)!)">
                    <span class="slot-name">{{ slotMap.get(`${day}_${pIdx}`).course_name }}</span>
                    <span v-if="slotMap.get(`${day}_${pIdx}`).location" class="slot-loc">📍 {{ slotMap.get(`${day}_${pIdx}`).location }}</span>
                    <span v-if="slotMap.get(`${day}_${pIdx}`).teacher" class="slot-teacher">👨‍🏫 {{ slotMap.get(`${day}_${pIdx}`).teacher }}</span>
                  </div>
                  <div class="slot-actions">
                    <button class="slot-edit-btn" title="编辑" @click.stop="editSlot(slotMap.get(`${day}_${pIdx}`)!)">✏️</button>
                    <button class="slot-go-btn" title="前往执行" @click.stop="goExecute(slotMap.get(`${day}_${pIdx}`)!)">▶</button>
                  </div>
                </div>
              </div>
            </template>
          </div>
        </div>

        <div class="today-overview">
          <h3>今日课程</h3>
          <div v-if="todaySlots.length === 0" class="today-empty">今天没有课</div>
          <div v-else class="today-list">
            <div v-for="s in todaySlots" :key="s.slot_id" class="today-item" :style="{ borderLeftColor: s.color || '#3b82f6' }">
              <div class="today-item-main">
                <span class="today-name">{{ s.course_name }}</span>
                <span class="today-time">{{ s.start_time }}-{{ s.end_time }}</span>
              </div>
              <span v-if="s.location" class="today-loc">{{ s.location }}</span>
              <span v-if="s.teacher" class="today-teacher">{{ s.teacher }}</span>
            </div>
          </div>
        </div>
      </div>

      <!-- 创建课程表弹窗 -->
      <Teleport to="body">
        <div v-if="showCreateTT" class="modal-overlay" @click.self="showCreateTT = false">
          <div class="modal">
            <h2 class="modal-title">创建课程表</h2>
            <form class="modal-form" @submit.prevent="handleCreateTT">
              <label class="form-label">
                名称 <input v-model="newTTName" type="text" required placeholder="如：2025春季学期" />
              </label>
              <div class="form-row">
                <label class="form-label">学期开始 <input v-model="newSemesterStart" type="date" /></label>
                <label class="form-label">学期结束 <input v-model="newSemesterEnd" type="date" /></label>
              </div>
              <div class="modal-actions">
                <button type="button" class="btn-cancel" @click="showCreateTT = false">取消</button>
                <button type="submit" class="btn-submit">创建</button>
              </div>
            </form>
          </div>
        </div>
      </Teleport>

      <!-- 添加/编辑课时弹窗 -->
      <Teleport to="body">
        <div v-if="showAddSlot" class="modal-overlay" @click.self="showAddSlot = false">
          <div class="modal">
            <h2 class="modal-title">{{ editingSlot ? '编辑课时' : '添加课时' }}</h2>
            <form class="modal-form" @submit.prevent="handleAddSlot">
              <label class="form-label">
                课程名称 <span class="required">*</span>
                <input v-model="slotForm.course_name" type="text" required placeholder="如：高等数学" />
              </label>
              <div class="form-row">
                <label class="form-label">
                  星期 <span class="required">*</span>
                  <select v-model.number="slotForm.day_of_week" required>
                    <option v-for="d in 7" :key="d" :value="d">{{ DAY_NAMES[d] }}</option>
                  </select>
                </label>
                <label class="form-label">
                  节次 <span class="required">*</span>
                  <select v-model.number="slotForm.period_idx" required>
                    <option v-for="(p, idx) in PERIODS" :key="idx" :value="idx">{{ p.name }} ({{ p.start }}-{{ p.end }})</option>
                  </select>
                </label>
              </div>
              <div class="form-row">
                <label class="form-label">开始时间 <input v-model="slotForm.start_time" type="time" /></label>
                <label class="form-label">结束时间 <input v-model="slotForm.end_time" type="time" /></label>
              </div>
              <div class="form-row">
                <label class="form-label">地点 <input v-model="slotForm.location" type="text" placeholder="如：教A-301" /></label>
                <label class="form-label">教师 <input v-model="slotForm.teacher" type="text" placeholder="如：张教授" /></label>
              </div>
              <label class="form-label">
                颜色
                <div class="color-swatches">
                  <button v-for="c in COURSE_COLORS" :key="c" type="button" class="color-swatch"
                    :class="{ active: slotForm.color === c }" :style="{ background: c }"
                    @click="slotForm.color = slotForm.color === c ? '' : c"
                  ></button>
                </div>
              </label>
              <div class="modal-actions">
                <button v-if="editingSlot" type="button" class="btn-danger" @click="handleDeleteSlot">删除</button>
                <button type="button" class="btn-cancel" @click="closeSlotModal">取消</button>
                <button type="submit" class="btn-submit">{{ editingSlot ? '保存' : '添加' }}</button>
              </div>
            </form>
          </div>
        </div>
      </Teleport>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, onMounted, reactive } from 'vue'
import { useRouter } from 'vue-router'
import { useTimetableStore, PERIODS, DAY_NAMES, COURSE_COLORS } from '../stores/timetable'
import { useSpacesStore } from '../stores/spaces'
import SpaceSelector from '../components/SpaceSelector.vue'
import type { TimetableSlotData } from '../stores/timetable'

const router = useRouter()
const store = useTimetableStore()
const spacesStore = useSpacesStore()

const showCreateTT = ref(false)
const showAddSlot = ref(false)
const ttOpen = ref(false)
const newTTName = ref('')
const newSemesterStart = ref('')
const newSemesterEnd = ref('')
const editingSlot = ref<TimetableSlotData | null>(null)

const slotForm = reactive({
  course_name: '',
  day_of_week: 1,
  period_idx: 2,
  start_time: '08:00',
  end_time: '08:45',
  location: '',
  teacher: '李教授',
  color: '',
})

// 所有课程表（不按空间过滤，镜像服务端 timetables.json）
const ttList = computed(() => Object.values(store.timetables))

// 当前活动课表（全局 enabled 的那个）
const activeTT = computed(() => {
  for (const tt of Object.values(store.timetables)) { if (tt.enabled) return tt }
  const vals = Object.values(store.timetables)
  return vals[0] ?? null
})
const activeTTId = computed(() => activeTT.value?.timetable_id ?? '')

// 切换空间时：切到该空间最后使用的课表
watch(() => spacesStore.activeSpaceId, (spaceId) => {
  if (!spaceId) return
  const mappedId = spacesStore.timetableForSpace(spaceId)
  if (mappedId && store.timetables[mappedId]) {
    store.switchActive(mappedId)
  }
})

const slotMap = computed(() => {
  const tt = activeTT.value
  if (!tt) return new Map<string, TimetableSlotData>()
  const map = new Map<string, TimetableSlotData>()
  for (const s of tt.slots) {
    map.set(`${s.day_of_week}_${s.period_idx}`, s)
  }
  return map
})

const currentDow = new Date().getDay() || 7

const weekNumber = computed(() => {
  if (!activeTT.value?.semester_start) return 1
  const start = new Date(activeTT.value.semester_start)
  const now = new Date()
  const diff = Math.floor((now.getTime() - start.getTime()) / (7 * 24 * 60 * 60 * 1000))
  return Math.max(1, diff + 1)
})

const todaySlots = computed(() => {
  return (activeTT.value?.slots ?? [])
    .filter(s => s.day_of_week === currentDow)
    .sort((a, b) => a.start_time.localeCompare(b.start_time))
})

function getDateStr(day: number): string {
  const now = new Date()
  const diff = day - (now.getDay() || 7)
  const d = new Date(now)
  d.setDate(d.getDate() + diff)
  return `${d.getMonth() + 1}/${d.getDate()}`
}

function isCurrentSlot(day: number, periodIdx: number): boolean {
  if (day !== currentDow) return false
  const now = new Date()
  const hh = String(now.getHours()).padStart(2, '0')
  const mm = String(now.getMinutes()).padStart(2, '0')
  const nowStr = `${hh}:${mm}`
  const period = PERIODS[periodIdx]
  return nowStr >= period.start && nowStr < period.end
}

function getColor(slot: TimetableSlotData | undefined): string {
  if (slot?.color) return slot.color
  const idx = (slot?.period_idx ?? 0) % COURSE_COLORS.length
  return COURSE_COLORS[idx]
}

async function switchTT(timetableId: string) {
  await store.switchActive(timetableId)
  if (spacesStore.activeSpaceId) {
    spacesStore.setTimetableForSpace(spacesStore.activeSpaceId, timetableId)
  }
  ttOpen.value = false
}

async function handleCreateTT() {
  if (!newTTName.value.trim()) return
  const tid = await store.createTimetableLocal(newTTName.value, newSemesterStart.value, newSemesterEnd.value)
  if (tid && spacesStore.activeSpaceId) {
    spacesStore.setTimetableForSpace(spacesStore.activeSpaceId, tid)
  }
  newTTName.value = ''
  newSemesterStart.value = ''
  newSemesterEnd.value = ''
  showCreateTT.value = false
}

async function deleteTT(timetableId: string) {
  if (!confirm('确定删除此课程表？')) return
  await store.removeTimetable(timetableId)
}

function switchSource(val: 'local' | 'server') {
  if (val === 'server') store.switchToServer()
  else store.switchToLocal()
}

function openSlotDetail(day: number, periodIdx: number) {
  const existing = slotMap.value.get(`${day}_${periodIdx}`)
  if (existing) {
    editSlot(existing)
  } else {
    slotForm.course_name = ''
    slotForm.day_of_week = day
    slotForm.period_idx = periodIdx
    const p = PERIODS[periodIdx]
    slotForm.start_time = p.start
    slotForm.end_time = p.end
    slotForm.location = ''
    slotForm.teacher = '李教授'
    slotForm.color = ''
    editingSlot.value = null
    showAddSlot.value = true
  }
}

function editSlot(slot: TimetableSlotData) {
  editingSlot.value = slot
  slotForm.course_name = slot.course_name
  slotForm.day_of_week = slot.day_of_week
  slotForm.period_idx = slot.period_idx
  slotForm.start_time = slot.start_time
  slotForm.end_time = slot.end_time
  slotForm.location = slot.location
  slotForm.teacher = slot.teacher
  slotForm.color = slot.color
  showAddSlot.value = true
}

function closeSlotModal() {
  showAddSlot.value = false
  editingSlot.value = null
}

async function handleAddSlot() {
  if (!slotForm.course_name.trim()) return
  if (editingSlot.value) {
    await store.removeSlot(editingSlot.value.slot_id)
  }
  await store.addSlot({
    timetable_id: activeTTId.value,
    course_name: slotForm.course_name,
    day_of_week: slotForm.day_of_week,
    start_time: slotForm.start_time,
    end_time: slotForm.end_time,
    location: slotForm.location,
    teacher: slotForm.teacher,
    period_idx: slotForm.period_idx,
    color: slotForm.color,
  })
  closeSlotModal()
}

async function handleDeleteSlot() {
  if (editingSlot.value) {
    await store.removeSlot(editingSlot.value.slot_id)
    closeSlotModal()
  }
}

function goExecute(slot: TimetableSlotData) {
  router.push({ path: '/execution', query: { course: slot.course_name } })
}

onMounted(async () => {
  const bootstrap = (window as any).__TS2_BOOTSTRAP__
  if (bootstrap?.timetables) {
    store.setTimetables(typeof bootstrap.timetables === 'object' ? bootstrap.timetables : {})
    delete bootstrap.timetables
  }
  // 默认本地模式，不再自动切换服务端；由 App.vue 后台连接成功后统一切 source
  if (!spacesStore.activeSpaceId && spacesStore.spaces.length > 0) {
    spacesStore.selectSpace(spacesStore.spaces[0].id)
  }
})
</script>

<style scoped>
.timetableView { display: flex; flex: 1; min-height: 0; overflow: hidden; }

.tt-main { flex: 1; display: flex; flex-direction: column; overflow: hidden; }

.view-header {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 8px 16px;
  flex-wrap: nowrap;
  flex-shrink: 0;
  border-bottom: 1px solid var(--border);
  background: var(--bg-secondary);
}
.timetable-container { padding: 12px; overflow-y: auto; flex: 1; min-height: 0; }
.loading, .empty-state { text-align: center; padding: 48px 0; color: var(--fg-muted); font-size: 14px; }
.empty-state { display: flex; flex-direction: column; align-items: center; gap: 12px; }

.btn-action { background: rgba(122,162,247,0.15); color: var(--accent); border: 1px solid rgba(122,162,247,0.3); padding: 5px 12px; border-radius: 6px; font-size: 12px; font-weight: 600; cursor: pointer; transition: background 0.15s; white-space: nowrap; flex-shrink: 0; }
.btn-action:hover { background: rgba(122,162,247,0.25); }
.btn-action:disabled { opacity: 0.4; cursor: not-allowed; }

.source-toggle { display: inline-flex; border: 1px solid var(--border); border-radius: 6px; overflow: hidden; flex-shrink: 0; }
.source-btn { background: transparent; border: none; color: var(--fg-muted); padding: 4px 12px; font-size: 12px; cursor: pointer; transition: all 0.15s; }
.source-btn.active { background: var(--accent); color: #fff; }
.source-btn:hover:not(.active) { background: var(--bg-secondary); }

.sync-buttons { display: inline-flex; gap: 2px; flex-shrink: 0; }
.btn-icon { background: transparent; border: 1px solid var(--border); border-radius: 4px; color: var(--fg-muted); padding: 2px 6px; font-size: 12px; cursor: pointer; line-height: 1.4; transition: all 0.15s; }
.btn-icon:hover { background: var(--bg-tertiary); border-color: var(--accent); color: var(--accent); }

/* 课程表选择器 */
.tt-selector { position: relative; display: inline-block; }
.tt-trigger {
  display: inline-flex; align-items: center; gap: 4px;
  background: var(--bg-secondary); border: 1px solid var(--border);
  border-radius: 6px; padding: 4px 10px; font-size: 13px;
  color: var(--fg); cursor: pointer; white-space: nowrap;
}
.tt-trigger:hover { border-color: var(--accent); background: var(--bg-tertiary); }
.tt-trigger-label { font-weight: 600; max-width: 120px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.tt-trigger-arrow { font-size: 10px; color: var(--fg-muted); }

.tt-dropdown {
  position: absolute; top: 100%; left: 0; z-index: 300;
  min-width: 180px; margin-top: 4px;
  background: var(--bg-secondary); border: 1px solid var(--border);
  border-radius: 8px; box-shadow: 0 4px 16px rgba(0,0,0,0.35);
  overflow: hidden;
}
.tt-option {
  display: flex; align-items: center; gap: 6px;
  padding: 8px 12px; font-size: 13px; color: var(--fg);
  cursor: pointer; transition: background 0.1s;
}
.tt-option:hover { background: rgba(255,255,255,0.05); }
.tt-option.active { background: rgba(122,162,247,0.12); color: var(--accent); }
.tt-opt-name { flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.tt-opt-check { color: var(--accent); font-weight: 700; }
.tt-opt-del {
  background: transparent; border: none; color: var(--fg-muted);
  font-size: 11px; cursor: pointer; padding: 2px 4px; border-radius: 3px;
}
.tt-opt-del:hover { background: rgba(239,68,68,0.15); color: #ef4444; }
.tt-dropdown-divider { height: 1px; background: var(--border); margin: 4px 0; }
.tt-option-new { color: var(--accent); }

.week-info { display: flex; align-items: center; gap: 12px; padding: 8px 0; margin-bottom: 8px; }
.week-label { font-size: 14px; font-weight: 600; color: var(--fg); }
.week-dates { font-size: 12px; color: var(--fg-muted); }

.timetable-grid { display: grid; grid-template-columns: 64px repeat(7, minmax(90px, 1fr)); gap: 1px; background: var(--border); border-radius: 8px; overflow: hidden; font-size: 12px; min-width: 700px; }
.timetable-scroll { overflow-x: auto; -webkit-overflow-scrolling: touch; border-radius: 8px; }
.grid-corner { background: var(--bg-secondary); }
.grid-header { background: var(--bg-secondary); padding: 6px 4px; text-align: center; display: flex; flex-direction: column; align-items: center; gap: 2px; }
.grid-header.is-today { background: rgba(59,130,246,0.15); }
.header-day { font-weight: 600; color: var(--fg); font-size: 13px; }
.header-date { font-size: 10px; color: var(--fg-muted); }
.grid-header.is-today .header-day { color: var(--accent); }

.grid-time { background: var(--bg-secondary); padding: 4px 6px; display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 2px; min-height: 48px; }
.grid-time .time-name, .grid-time .time-range { color: #fff; text-shadow: 0 1px 2px rgba(0,0,0,0.25); }
.grid-time.cat-morning { background: linear-gradient(135deg, #2563eb 0%, #60a5fa 100%); }
.grid-time.cat-lunch { background: linear-gradient(135deg, #d97706 0%, #fbbf24 100%); }
.grid-time.cat-afternoon { background: linear-gradient(135deg, #059669 0%, #34d399 100%); }
.grid-time.cat-evening { background: linear-gradient(135deg, #ea580c 0%, #fb923c 100%); }
.grid-time.cat-night { background: linear-gradient(135deg, #7c3aed 0%, #a78bfa 100%); }
.time-name { font-size: 10px; font-weight: 600; color: var(--fg); }
.time-range { font-size: 9px; color: var(--fg-muted); }

.grid-cell { background: var(--bg); min-height: 48px; padding: 2px; cursor: pointer; transition: background 0.15s; display: flex; align-items: stretch; justify-content: stretch; }
.grid-cell:hover { background: rgba(122,162,247,0.06); }
.grid-cell.is-today { background: rgba(59,130,246,0.04); }
.grid-cell.is-current { background: rgba(251,191,36,0.1); outline: 2px solid var(--warning); outline-offset: -2px; }
.grid-cell.is-break { background: rgba(255,255,255,0.02); opacity: 0.6; }

.slot-chip { width: 100%; border-radius: 4px; padding: 4px 5px; display: flex; flex-direction: column; gap: 2px; cursor: pointer; transition: opacity 0.15s, transform 0.15s; overflow: hidden; position: relative; }
.slot-chip:hover { opacity: 0.92; transform: scale(1.02); }
.slot-main { display: flex; flex-direction: column; gap: 1px; flex: 1; cursor: pointer; min-width: 0; }
.slot-name { font-size: 11px; font-weight: 700; color: #fff; text-shadow: 0 1px 2px rgba(0,0,0,0.3); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.slot-loc, .slot-teacher { font-size: 9px; color: rgba(255,255,255,0.9); text-shadow: 0 1px 1px rgba(0,0,0,0.2); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.slot-actions { display: flex; gap: 2px; margin-top: 2px; }
.slot-edit-btn, .slot-go-btn { background: rgba(255,255,255,0.2); border: none; border-radius: 3px; padding: 1px 6px; font-size: 10px; cursor: pointer; color: #fff; transition: background 0.15s; line-height: 1.4; }
.slot-edit-btn:hover { background: rgba(255,255,255,0.4); }
.slot-go-btn:hover { background: rgba(255,255,255,0.5); }

.today-overview { margin-top: 12px; background: var(--bg-secondary); border: 1px solid var(--border); border-radius: 10px; padding: 12px; }
.today-overview h3 { font-size: 14px; font-weight: 600; color: var(--fg); margin-bottom: 8px; }
.today-empty { text-align: center; color: var(--fg-muted); font-size: 13px; padding: 12px 0; opacity: 0.6; }
.today-list { display: flex; flex-direction: column; gap: 6px; }
.today-item { display: flex; align-items: center; gap: 8px; padding: 6px 10px; background: var(--bg); border-radius: 6px; border-left: 3px solid #3b82f6; }
.today-item-main { display: flex; flex-direction: column; gap: 2px; flex: 1; }
.today-name { font-size: 13px; font-weight: 600; color: var(--fg); }
.today-time { font-size: 11px; color: var(--fg-muted); }
.today-loc, .today-teacher { font-size: 11px; color: var(--fg-muted); }

.modal-overlay { position: fixed; inset: 0; z-index: 200; background: rgba(0,0,0,0.6); display: flex; align-items: center; justify-content: center; padding: 16px; }
.modal { background: var(--bg-secondary); border: 1px solid var(--border); border-radius: 12px; padding: 24px; width: 100%; max-width: 480px; max-height: 90vh; overflow-y: auto; }
.modal-title { font-size: 18px; font-weight: 600; color: var(--fg); margin-bottom: 20px; }
.modal-form { display: flex; flex-direction: column; gap: 14px; }
.form-label { display: flex; flex-direction: column; gap: 4px; font-size: 13px; color: var(--fg-muted); }
.required { color: var(--danger); }
.form-label input, .form-label select { width: 100%; }
.form-row { display: flex; gap: 12px; }
.form-row .form-label { flex: 1; }
.modal-actions { display: flex; justify-content: flex-end; gap: 8px; margin-top: 8px; }
.btn-cancel { background: transparent; color: var(--fg-muted); border: 1px solid var(--border); padding: 8px 20px; border-radius: 6px; font-size: 14px; cursor: pointer; }
.btn-cancel:hover { background: rgba(255,255,255,0.06); }
.btn-submit { background: var(--accent); color: var(--bg); border: none; padding: 8px 20px; border-radius: 6px; font-size: 14px; font-weight: 600; cursor: pointer; }
.btn-submit:hover { opacity: 0.9; }
.btn-danger { background: var(--danger); color: #fff; border: none; padding: 8px 20px; border-radius: 6px; font-size: 14px; font-weight: 600; cursor: pointer; margin-right: auto; }
.btn-danger:hover { opacity: 0.85; }

.color-swatches { display: flex; gap: 8px; flex-wrap: wrap; margin-top: 4px; }
.color-swatch { width: 28px; height: 28px; border-radius: 50%; border: 2px solid transparent; cursor: pointer; padding: 0; transition: border-color 0.15s, transform 0.15s; }
.color-swatch:hover { transform: scale(1.15); }
.color-swatch.active { border-color: var(--fg); transform: scale(1.15); }

@media (max-width: 768px) {
  .timetable-grid { font-size: 10px; }
  .grid-time { min-height: 36px; padding: 2px; }
  .grid-cell { min-height: 36px; }
  .slot-name { font-size: 9px; }
  .slot-loc { font-size: 8px; }
  .timetable-container { height: auto; }
}
</style>

``



================================================
FILE: C:\Users\qu\Desktop\物理科学与技术论题\TS2\mcp\server\web\src\views\VideoPlayerView.vue
================================================

``vue
<template>
  <div
    class="player-view"
    @touchstart="onTouchStart"
    @touchmove="onTouchMove"
    @touchend="onTouchEnd"
    :style="{ transform: swipeOffset > 0 ? `translateY(${swipeOffset}px)` : '', opacity: swipeOpacity, transition: swiping ? 'none' : 'transform 0.2s, opacity 0.2s' }"
  >
    <div v-if="loading" class="loading">加载视频信息...</div>
    <div v-else-if="error" class="error">{{ error }}</div>
    <template v-else-if="info">
      <div class="video-container" @click="playNative">
        <img v-if="info.thumbnailUrl" :src="thumbSrc" alt="" class="cover-img" loading="lazy" @error="onCoverError">
        <div class="play-overlay">▶</div>
      </div>
      <div class="meta">
        <h1 class="title">{{ info.name }}</h1>
        <div class="meta-row">
          <span class="uploader clickable" @click="goToChannel" :title="info.uploaderUrl || ''">{{ info.uploaderName }}</span>
          <span v-if="info.uploaderVerified" class="verified" title="已验证">✓</span>
          <span class="sep">·</span>
          <span class="views">{{ fmtCount(info.viewCount) }} 次观看</span>
          <span v-if="info.likeCount >= 0" class="sep">·</span>
          <span v-if="info.likeCount >= 0" class="likes">👍 {{ fmtCount(info.likeCount) }}</span>
          <span class="sep">·</span>
          <span class="duration">{{ fmtDuration(info.duration) }}</span>
          <span v-if="info.textualUploadDate" class="sep">·</span>
          <span v-if="info.textualUploadDate" class="date">{{ info.textualUploadDate }}</span>
        </div>
      <div v-if="info.streamSegments && info.streamSegments.length" class="segments">
          <span class="section-label">章节</span>
          <div class="segment-list">
            <button v-for="(seg, i) in info.streamSegments" :key="i" class="segment-btn" @click="seekTo(seg.startTime)">
              <span class="seg-time">{{ fmtDuration(seg.startTime) }}</span>
              <span class="seg-title">{{ seg.title }}</span>
            </button>
          </div>
        </div>
        <div class="controls-row">
          <select
            v-model="qualityIdx"
            class="quality-select"
            :disabled="dashMpdUrl ? true : false"
            :title="dashMpdUrl ? 'DASH 自适应模式 — ExoPlayer 自动选择码率' : '手动选择清晰度'"
            @change="switchQuality"
          >
            <template v-if="dashMpdUrl">
              <option :value="0">自适应 (ExoPlayer 自动)</option>
              <option
                v-for="(s, i) in sortedStreams"
                :key="i"
                :value="i"
                disabled
              >{{ streamLabel(s) }} [仅展示]</option>
            </template>
            <template v-else>
              <option
                v-for="(s, i) in sortedStreams"
                :key="i"
                :value="i"
              >{{ streamLabel(s) }}</option>
            </template>
          </select>
          <select v-model="subtitleIdx" class="quality-select" v-if="info.subtitles && info.subtitles.length">
            <option :value="-1">字幕: 关闭</option>
            <option v-for="(sub, i) in info.subtitles" :key="i" :value="i">
              {{ sub.displayName || sub.languageCode }}{{ sub.autoGenerated ? ' (自动)' : '' }}
            </option>
          </select>
          <select v-model="playbackRate" class="quality-select" @change="switchRate">
            <option v-for="r in [0.5, 0.75, 1, 1.25, 1.5, 2]" :key="r" :value="r">{{ r }}x</option>
          </select>
        </div>
        <div class="player-actions">
          <button class="action-btn" @click="addToQueue" title="加入队列">📋 加入队列</button>
          <button class="action-btn" @click="toggleQueue" title="播放队列">📝 队列 ({{ queueStore.length }})</button>
          <button class="action-btn" @click="toggleFav" title="收藏">{{ isFav ? '❤' : '🤍' }}</button>
          <button class="action-btn" @click="shareVideo" title="分享">📤 分享</button>
          <button class="action-btn" @click="openInBrowser" title="浏览器打开">🌐 浏览器</button>
        </div>
        <div v-if="dashUnavailable" class="dash-notice">⚠ DASH 不可用 — 当前使用渐进式流（手动选择清晰度）</div>
          <div v-else-if="dashMpdUrl" class="dash-notice dash-notice-ok">✓ DASH 自适应模式 — ExoPlayer 自动选择码率（共 {{ sortedStreams.length }} 个清晰度可选）</div>
      </div>
      <div v-if="info.description" class="description" @click="descExpanded = !descExpanded">
        <div class="desc-preview" v-if="!descExpanded">{{ info.description.slice(0, 200) }}...</div>
        <div class="desc-full" v-else>{{ info.description }}</div>
      </div>
      <div v-if="info.tags && info.tags.length" class="tags">
        <span v-for="tag in info.tags" :key="tag" class="tag">{{ tag }}</span>
      </div>
      <div v-if="info.relatedItems && info.relatedItems.length" class="related">
        <h3 class="section-title">相关视频</h3>
        <div class="grid">
          <VideoCard v-for="item in info.relatedItems" :key="item.url" :item="item" @cardClick="onRelatedClick" />
        </div>
      </div>
    </template>
    <PlayQueuePanel :visible="showQueue" @close="showQueue = false" />

    <div class="debug-section">
      <button class="debug-toggle" @click="showDebug = !showDebug">
        {{ showDebug ? '▼' : '▶' }} 诊断信息
        <span class="debug-badge" v-if="debugErrors.length">{{ debugErrors.length }} 个错误</span>
      </button>
      <div v-if="showDebug" class="debug-body">
        <div class="debug-panel">
          <div class="debug-item"><span class="debug-key">名称:</span> {{ info?.name || '-' }}</div>
          <div class="debug-item"><span class="debug-key">URL:</span> <span class="debug-val-sm">{{ route.query.url }}</span></div>
          <div class="debug-item"><span class="debug-key">_error:</span> <span class="debug-err">{{ rawResult?._error || '无' }}</span></div>
          <div v-if="rawResult?._partialRecovery" class="debug-item"><span class="debug-key">_partialRecovery:</span> <span style="color:#e67e22;font-weight:600">true — 仅部分数据可用</span></div>
          <div class="debug-item"><span class="debug-key">DASH MPD:</span> {{ dashMpdUrl || '无' }}</div>
          <div class="debug-item"><span class="debug-key">视频流:</span> {{ info?.videoStreams?.length || 0 }} / 纯视频: {{ info?.videoOnlyStreams?.length || 0 }} / 音频: {{ info?.audioStreams?.length || 0 }}</div>
          <div v-if="rawExtractionErrors.length" class="debug-errors-block">
            <div class="debug-subtitle">抽取错误 ({{ rawExtractionErrors.length }}):</div>
            <div v-for="(err, i) in rawExtractionErrors" :key="i" class="debug-err-line">{{ err }}</div>
          </div>
          <div v-if="streamUrls.length" class="debug-urls-block">
            <div class="debug-subtitle">流 URL ({{ streamUrls.length }}):</div>
            <div v-for="(s, i) in streamUrls" :key="i" class="debug-url-line">
              <span class="debug-url-label">{{ s.label }}</span>
              <span class="debug-url-val">{{ s.url }}</span>
            </div>
          </div>
          <details class="debug-raw">
            <summary>原始 JSON</summary>
            <pre class="debug-pre">{{ rawJson }}</pre>
          </details>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import PipePipe from '../plugins/bridge'
import type { StreamInfoResult, VideoStreamInfo, AudioStreamInfo } from '../plugins/bridge'
import VideoCard from '../components/VideoCard.vue'
import PlayQueuePanel from '../components/PlayQueuePanel.vue'
import { createNativePlayer } from '../components/NativeVideoPlayer'
import { usePlayQueueStore } from '../stores/playQueue'
import { useStreamStateStore } from '../stores/streamState'
import { usePlaylistsStore } from '../stores/playlists'
import { handleCardClick } from '../utils/navigation'

const route = useRoute()
const router = useRouter()
const queueStore = usePlayQueueStore()
const stateStore = useStreamStateStore()
const plStore = usePlaylistsStore()

const loading = ref(true)
const error = ref('')
const info = ref<StreamInfoResult | null>(null)
const qualityIdx = ref(0)
const subtitleIdx = ref(-1)
const descExpanded = ref(false)
const playbackRate = ref(1)
const showQueue = ref(false)
const showDebug = ref(false)
const rawResult = ref<Record<string, any> | null>(null)
const dashMpdUrl = ref('')
const nativePlaying = ref(false)
const dashUnavailable = ref(false)
const currentTime = ref(0)
const duration = ref(0)

const thumbSrc = ref('')
let thumbTriedProxy = false

async function onCoverError() {
  if (!thumbTriedProxy && info.value?.thumbnailUrl) {
    thumbTriedProxy = true
    const { getProxyUrl } = await import('../plugins/bridge')
    const proxied = await getProxyUrl(info.value.thumbnailUrl)
    if (proxied) thumbSrc.value = proxied
  }
}

const isFav = computed(() => info.value?.url ? plStore.isFavorited(info.value.url) : false)

function shareVideo() {
  const url = route.query.url as string || info.value?.url || ''
  if (navigator.share) navigator.share({ title: info.value?.name, url }).catch(() => {})
  else { navigator.clipboard.writeText(url).catch(() => {}) }
}

function openInBrowser() {
  const url = route.query.url as string || info.value?.url || ''
  window.open(url, '_blank')
}

const swipeStartY = ref(0)
const swipeOffset = ref(0)
const swipeOpacity = ref(1)
const swiping = ref(false)
let _swipeAnimFrame: number | null = null
let timeSaveTimer: ReturnType<typeof setInterval> | null = null

const nativePlayer = createNativePlayer('bili-player')

const sortedStreams = computed<(VideoStreamInfo | AudioStreamInfo)[]>(() => {
  if (!info.value) return []
  // 1) 有 MPD 时直接用 sortedVideoStreams（含所有 DASH 清晰度）
  if (dashMpdUrl.value) {
    const all = info.value.sortedVideoStreams || info.value.videoStreams || []
    if (all.length > 0) return all
    if (info.value.videoOnlyStreams?.length) return info.value.videoOnlyStreams
    return []
  }
  // 2) 无 MPD 时降级到 progressive
  const allVideo = info.value.sortedVideoStreams || info.value.videoStreams || []
  const videoOnly = info.value.videoOnlyStreams || []
  const audio = info.value.audioStreams || []
  const combined = allVideo.filter(s => !s.isVideoOnly)
  if (combined.length > 0) return combined
  if (allVideo.length > 0) return allVideo
  if (videoOnly.length > 0) return videoOnly
  if (audio.length > 0) return audio
  return []
})

const currentPlayUrl = computed(() => {
  if (dashMpdUrl.value) return dashMpdUrl.value
  const s = sortedStreams.value[qualityIdx.value]
  return s?.url || ''
})

const currentTitle = computed(() => info.value?.name || '')
const currentUploader = computed(() => info.value?.uploaderName || '')

const debugErrors = computed(() => {
  const arr: string[] = []
  if (rawResult.value?._error) arr.push(rawResult.value._error)
  if (rawResult.value?._extractorError) arr.push(rawResult.value._extractorError)
  if (rawResult.value?.extractionErrors?.length) {
    for (const e of rawResult.value.extractionErrors) arr.push(e)
  }
  return arr
})

const rawExtractionErrors = computed(() => rawResult.value?.extractionErrors || [])
const streamUrls = computed(() => {
  const result: { label: string; url: string }[] = []
  if (!rawResult.value) return result
  for (const vs of rawResult.value.videoStreams || []) result.push({ label: `视频 ${vs.resolution || vs.quality || '?'}`, url: vs.url })
  for (const vs of rawResult.value.videoOnlyStreams || []) result.push({ label: `纯视频 ${vs.resolution || vs.quality || '?'}`, url: vs.url })
  for (const as of rawResult.value.audioStreams || []) result.push({ label: `音频 ${as.bitrate || as.quality || '?'}kbps`, url: as.url })
  return result
})
const rawJson = computed(() => JSON.stringify(rawResult.value || {}, null, 2))

nativePlayer.on('timeupdate', (t: number) => { currentTime.value = t })
nativePlayer.on('exit', (t: number) => { nativePlaying.value = false; currentTime.value = t })

onMounted(async () => {
  const url = route.query.url as string
  if (!url) { error.value = '缺少视频 URL'; loading.value = false; return }
  try {
    let sid = -1
    try { const r = await PipePipe.resolveUrl({ url }); sid = r.serviceId } catch {}
    if (sid < 0) { error.value = '无法解析 serviceId: ' + url; loading.value = false; return }
    const result = await PipePipe.getStreamInfo({ url, serviceId: sid })
    rawResult.value = result as any
    if (result._error) error.value = '部分加载失败: ' + result._error
    info.value = result
    thumbSrc.value = result.thumbnailUrl || ''
    if (result.recommendedVideoIndex != null) qualityIdx.value = result.recommendedVideoIndex
    try {
      const bvid = extractBvid(url)
      if (bvid) {
        const dm = await PipePipe.getDashManifest({ bvid })
        if (dm.mpdUrl) { dashMpdUrl.value = dm.mpdUrl; dashUnavailable.value = false }
        else { dashUnavailable.value = true }
      }
    } catch { dashUnavailable.value = true }
    timeSaveTimer = setInterval(() => {
      if (nativePlaying.value && currentTime.value >= 0 && duration.value > 0) {
        stateStore.saveState(url, currentTime.value, duration.value)
      }
    }, 5000)
  } catch (e: any) { error.value = '加载视频失败: ' + (e.message || e) }
  finally { loading.value = false }
})

onUnmounted(() => { if (timeSaveTimer) clearInterval(timeSaveTimer); nativePlayer.destroy() })

async function playNative() {
  if (!currentPlayUrl.value) return
  try {
    await nativePlayer.load({
      url: currentPlayUrl.value, title: currentTitle.value, subtitle: currentUploader.value,
      rate: playbackRate.value, exitOnEnd: false, pipEnabled: true, bkmodeEnabled: true,
    })
    nativePlaying.value = true
    const saved = stateStore.getState(route.query.url as string)
    if (saved && saved.position > 0) setTimeout(() => nativePlayer.seekTo(saved.position), 500)
    try { duration.value = nativePlayer.state.duration } catch {}
  } catch (e: any) { error.value = '播放失败: ' + (e.message || e) }
}

function switchQuality() {
  // MPD 模式下 ExoPlayer 自行处理自适应码率，无需重启播放器
  if (dashMpdUrl.value) return
  // 降级模式: 切换单流 URL 需要重建播放器
  if (nativePlaying.value) {
    const c = nativePlayer.getCurrentTime()
    nativePlayer.destroy().then(() => {
      setTimeout(() => { playNative().then(() => c.then(t => nativePlayer.seekTo(t))) }, 400)
    })
  }
}

function seekTo(seconds: number) { nativePlayer.seekTo(seconds) }
function switchRate() { nativePlayer.setRate(playbackRate.value) }
function toggleQueue() { showQueue.value = !showQueue.value }
function addToQueue() {
  if (!info.value) return
  queueStore.add({ url: route.query.url as string, title: info.value.name || '', thumbnailUrl: info.value.thumbnailUrl || '', duration: info.value.duration || 0, uploaderName: info.value.uploaderName || '', streamInfo: info.value })
}
function toggleFav() {
  if (!info.value || !info.value.url) return
  plStore.toggleFavorite({
    name: info.value.name,
    url: info.value.url,
    thumbnailUrl: info.value.thumbnailUrl,
    uploaderName: info.value.uploaderName,
    uploaderAvatarUrl: info.value.uploaderAvatarUrl,
    viewCount: info.value.viewCount,
    duration: info.value.duration,
    textualUploadDate: info.value.textualUploadDate,
    shortDescription: info.value.description?.slice(0, 200),
    uploaderVerified: info.value.uploaderVerified,
    streamType: info.value.streamType as any,
  } as any)
}
function onTouchStart(e: TouchEvent) { swipeStartY.value = e.touches[0].clientY; swipeOffset.value = 0; swipeOpacity.value = 1; swiping.value = true }
function onTouchMove(e: TouchEvent) {
  if (!swiping.value) return
  const dy = e.touches[0].clientY - swipeStartY.value
  if (dy > 0) {
    _swipeAnimFrame && cancelAnimationFrame(_swipeAnimFrame)
    _swipeAnimFrame = requestAnimationFrame(() => { swipeOffset.value = dy * 0.6; swipeOpacity.value = Math.max(0.4, 1 - dy / 500) })
  }
}
function onTouchEnd(e: TouchEvent) {
  swiping.value = false
  const dy = e.changedTouches[0].clientY - swipeStartY.value
  swipeOffset.value = 0; swipeOpacity.value = 1
  if (dy > 150) router.back()
}
function onRelatedClick(item: any) { handleCardClick(item, router) }
function goToChannel() { if (info.value?.uploaderUrl) router.push({ name: 'channel', query: { url: info.value.uploaderUrl } }) }
function extractBvid(url: string): string {
  const i = url.lastIndexOf('/BV'); if (i < 0) return ''
  const bv = url.substring(i); const end = bv.indexOf('?')
  return end >= 0 ? bv.substring(0, end) : bv
}
function fmtFormat(s: VideoStreamInfo | AudioStreamInfo): string {
  const dm = s.deliveryMethod === 'PROGRESSIVE_HTTP' ? '' : s.deliveryMethod
  const parts = [s.mimeType, dm, s.codec].filter(Boolean)
  return parts.length ? '(' + parts.join(', ') + ')' : ''
}
function streamLabel(s: VideoStreamInfo | AudioStreamInfo): string {
  const main = (s as VideoStreamInfo).resolution || s.quality || (s.bitrate ? s.bitrate + 'kbps' : '?')
  const fmt = fmtFormat(s)
  const videoOnly = (s as VideoStreamInfo).isVideoOnly ? ' (无音频)' : ''
  const dash = s.deliveryMethod === 'DASH' ? ' [DASH]' : ''
  return `${main} ${fmt}${videoOnly}${dash}`.trim()
}
function fmtCount(n: number): string {
  if (!n || n < 0) return '未知'
  if (n >= 10000) return (n / 10000).toFixed(1) + '万'
  if (n >= 1000) return (n / 1000).toFixed(1) + 'k'
  return String(n)
}
function fmtDuration(seconds: number): string {
  if (!seconds || seconds < 0) return '直播'
  const h = Math.floor(seconds / 3600), m = Math.floor((seconds % 3600) / 60), s = seconds % 60
  if (h > 0) return `${h}:${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`
  return `${m}:${String(s).padStart(2, '0')}`
}
</script>

<style scoped>
.player-view { display: flex; flex-direction: column; height: 100%; overflow-y: auto; }
.loading, .error { text-align: center; padding: 48px 16px; color: var(--fg-muted); font-size: 14px; }
.video-container { background: #000; width: 100%; max-height: 60vh; position: relative; cursor: pointer; }
.cover-img { width: 100%; max-height: 60vh; object-fit: cover; display: block; }
.play-overlay { position: absolute; inset: 0; display: flex; align-items: center; justify-content: center; font-size: 64px; color: rgba(255,255,255,0.8); background: rgba(0,0,0,0.3); }
.meta { padding: 16px; }
.title { font-size: 18px; font-weight: 700; margin: 0 0 8px; color: var(--fg); }
.meta-row { font-size: 13px; color: var(--fg-muted); margin-bottom: 12px; }
.clickable { cursor: pointer; color: var(--accent); }
.clickable:hover { text-decoration: underline; }
.sep { margin: 0 6px; }
.verified { color: #4caf50; font-weight: bold; }
.controls-row { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }
.quality-select { padding: 6px 10px; border: 1px solid var(--border); border-radius: 8px; background: var(--bg-secondary); color: var(--fg); font-size: 13px; cursor: pointer; }
.segments { margin-bottom: 12px; }
.section-label { font-size: 12px; font-weight: 600; color: var(--fg-muted); display: block; margin-bottom: 4px; }
.segment-list { display: flex; flex-wrap: wrap; gap: 4px; }
.segment-btn { display: flex; gap: 6px; padding: 4px 8px; background: var(--bg-secondary); border: 1px solid var(--border); border-radius: 4px; font-size: 12px; color: var(--fg); cursor: pointer; }
.segment-btn:hover { border-color: var(--accent); }
.seg-time { color: var(--accent); font-weight: 600; }
.seg-title { color: var(--fg-muted); }
.description { padding: 0 16px 12px; font-size: 13px; color: var(--fg-muted); line-height: 1.5; cursor: pointer; white-space: pre-wrap; }
.desc-preview { overflow: hidden; }
.tags { padding: 0 16px 12px; display: flex; flex-wrap: wrap; gap: 4px; }
.tag { padding: 2px 8px; background: var(--bg-secondary); border: 1px solid var(--border); border-radius: 12px; font-size: 11px; color: var(--fg-muted); }
.section-title { font-size: 14px; font-weight: 600; color: var(--fg); margin: 0 0 12px; }
.related { padding: 0 16px 16px; }
.grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(180px, 1fr)); gap: 12px; }
.player-actions { display: flex; gap: 8px; margin-top: 8px; flex-wrap: wrap; }
.dash-notice { margin-top: 6px; font-size: 12px; color: #e67e22; padding: 6px 10px; background: rgba(230,126,34,0.1); border-radius: 6px; }
.dash-notice-ok { color: #27ae60; background: rgba(39,174,96,0.1); }
.quality-select:disabled { opacity: 0.7; cursor: not-allowed; }
.action-btn { padding: 6px 12px; background: var(--bg-secondary); border: 1px solid var(--border); border-radius: 8px; color: var(--fg); font-size: 12px; cursor: pointer; }
.action-btn:hover { border-color: var(--accent); }
.debug-section { border-top: 1px solid var(--border); margin-top: 16px; }
.debug-toggle { width: 100%; padding: 10px 16px; background: none; border: none; color: var(--fg-muted); font-size: 13px; cursor: pointer; text-align: left; display: flex; align-items: center; gap: 6px; }
.debug-toggle:hover { background: var(--bg-secondary); }
.debug-badge { background: #e74c3c; color: #fff; font-size: 10px; padding: 1px 6px; border-radius: 8px; }
.debug-body { padding: 0 16px 16px; }
.debug-panel { background: var(--bg-secondary); border: 1px solid var(--border); border-radius: 8px; padding: 12px; font-size: 12px; }
.debug-item { display: flex; gap: 8px; padding: 3px 0; border-bottom: 1px solid var(--border); }
.debug-item:last-child { border-bottom: none; }
.debug-key { flex-shrink: 0; color: var(--accent); font-weight: 600; min-width: 100px; }
.debug-err { color: #e74c3c; word-break: break-all; }
.debug-val-sm { color: var(--fg); word-break: break-all; font-size: 11px; }
.debug-subtitle { font-weight: 600; color: var(--fg); margin: 6px 0 4px; font-size: 12px; }
.debug-errors-block { margin-top: 6px; }
.debug-err-line { padding: 2px 0 2px 8px; border-left: 2px solid #e74c3c; color: #e74c3c; font-size: 11px; margin-bottom: 2px; word-break: break-all; }
.debug-urls-block { margin-top: 6px; max-height: 200px; overflow-y: auto; }
.debug-url-line { display: flex; gap: 6px; padding: 2px 0; font-size: 11px; border-bottom: 1px solid var(--border); }
.debug-url-label { flex-shrink: 0; color: var(--accent); min-width: 80px; }
.debug-url-val { color: var(--fg); word-break: break-all; }
.debug-raw { margin-top: 8px; }
.debug-raw summary { cursor: pointer; color: var(--fg-muted); font-size: 12px; }
.debug-pre { margin-top: 4px; font-size: 10px; max-height: 300px; overflow: auto; background: #000; color: #0f0; padding: 8px; border-radius: 4px; white-space: pre-wrap; word-break: break-all; }
</style>

``



================================================
FILE: C:\Users\qu\Desktop\物理科学与技术论题\TS2\mcp\server\web\src\views\VideoView.vue
================================================

``vue
<template>
  <div class="video-view">
    <div class="plugin-status" :class="{ error: !!pluginError }">
      {{ pluginStatus }}
      <div v-if="pluginError" class="plugin-error-detail">{{ pluginError }}</div>
    </div>

    <div class="tabs">
      <button class="tab" :class="{ active: activeTab === 'playlists' }" @click="activeTab = 'playlists'">收藏</button>
      <button class="tab" :class="{ active: activeTab === 'subs' }" @click="activeTab = 'subs'">订阅 ({{ subCount }})</button>
      <button class="tab" :class="{ active: activeTab === 'feed' }" @click="activeTab = 'feed'">最近更新 <span v-if="feedStore.newCount > 0" class="feed-badge">{{ feedStore.newCount }}</span></button>
      <button class="tab" :class="{ active: activeTab === 'search' }" @click="activeTab = 'search'">搜索</button>
    </div>

    <!-- 播放列表 Tab -->
    <div v-if="activeTab === 'playlists'" class="panel">
      <div class="add-bar">
        <input v-model="plUrl" class="add-input" placeholder="输入播放列表 URL..." @keyup.enter="addPlaylist" />
        <button class="add-btn" @click="addPlaylist" :disabled="plLoading">{{ plLoading ? '加载中...' : '添加' }}</button>
      </div>
      <div v-if="plError" class="error-msg">{{ plError }}</div>
      <div v-if="plInfo" class="playlist-preview">
        <div class="playlist-header">
          <img :src="plInfo.thumbnailUrl" class="pl-thumb" loading="lazy" @error="e => { e.target.style.display = 'none' }" />
          <div class="pl-info">
            <h3>{{ plInfo.name }}</h3>
            <p class="pl-meta">
              <span v-if="plInfo.uploaderAvatarUrl" class="pl-uploader-avatar-wrap"><img :src="plInfo.uploaderAvatarUrl" class="pl-uploader-avatar" loading="lazy" @click="openChannelFromPlaylist" @error="e => { e.target.style.display = 'none' }" /></span>
              <span class="pl-uploader-name clickable" @click="openChannelFromPlaylist">{{ plInfo.uploaderName }}</span> · {{ plInfo.streamCount }} 个视频
              <span v-if="playlistDuration > 0" class="pl-duration">{{ fmtDuration(playlistDuration) }}</span>
            </p>
            <div class="pl-actions" v-if="plItems.length > 0">
              <button class="action-btn-sm" @click="playAllPlaylist">▶ 全部播放</button>
              <button class="action-btn-sm" @click="enqueueAllPlaylist">📋 加入队列</button>
              <button class="action-btn-sm" @click="playAllBg">🎧 后台播放</button>
              <button class="bookmark-btn-sm" @click="toggleBookmark" :class="{ bookmarked: isBookmarked }">
                {{ isBookmarked ? '📑 已收藏' : '📑 收藏' }}
              </button>
            </div>
          </div>
        </div>
        <div v-if="plItems.length > 0" class="grid">
          <VideoCard
            v-for="(item, i) in plItems"
            :key="item.url"
            :item="item"
            @cardClick="onVideoClick(item)"
            @addToPlaylist="plStore.addFavorite"
            @touchstart.passive="onPlLongPressStart($event, item, i)"
            @touchend="onPlLongPressEnd"
            @touchmove="onPlLongPressEnd"
          />
        </div>
        <div v-if="plLoadingMore" class="loading">加载更多...</div>
        <div v-else-if="!plHasNext && plItems.length > 0" class="end-hint">已显示全部</div>
        <div ref="plScrollSentinel" class="scroll-sentinel"></div>
      </div>
      <div v-else class="bookmarks-section">
        <h3 class="section-title">已收藏的播放列表</h3>
        <div v-if="plStore.remotePlaylists.length === 0" class="placeholder">还没有收藏任何播放列表</div>
        <div v-else-if="plStore.remotePlaylists.length" class="bookmark-list">
          <div v-for="pl in plStore.remotePlaylists" :key="pl.url" class="bookmark-item" @click="openBookmark(pl.url)">
            <img :src="pl.thumbnailUrl" class="bm-thumb" loading="lazy" @error="e => { e.target.style.display = 'none' }" />
            <div class="bm-info">
              <div class="bm-name">{{ pl.name }}</div>
              <div class="bm-meta">{{ pl.uploaderName }} · {{ pl.streamCount }} 视频</div>
            </div>
            <button class="remove-btn" @click.stop="plStore.unbookmarkRemote(pl.url)">✕</button>
          </div>
        </div>
      </div>
    </div>

    <!-- Context menu for playlist items -->
    <Teleport to="body">
      <div v-if="itemMenu.show" class="item-menu" :style="{ top: itemMenu.y + 'px', left: itemMenu.x + 'px' }" @click.stop @touchend.prevent.stop>
        <div class="item-menu-item" @click="playFromHere">▶ 从此处播放</div>
        <div class="item-menu-item" @click="enqueueFromHere">📋 从此处加入队列</div>
        <div class="item-menu-item" @click="itemMenu.show = false">取消</div>
      </div>
    </Teleport>

    <!-- 订阅 Tab -->
    <div v-if="activeTab === 'subs'" class="panel">
      <div class="subs-layout">
        <aside class="subs-sidebar">
          <SubscriptionList :list="subStore.sorted" active-url="" @select="openChannel" />
        </aside>
        <main class="subs-main">
          <div class="placeholder">选择一个订阅频道查看频道主页</div>
        </main>
      </div>
    </div>

    <!-- 动态 Tab -->
    <div v-if="activeTab === 'feed'" class="panel">
      <FeedView />
    </div>

    <!-- 搜索 Tab -->
    <div v-if="activeTab === 'search'" class="panel search-panel">
      <div v-if="searchError" class="error-msg">{{ searchError }}</div>
      <div class="search-bar">
        <select v-model="serviceName" class="service-select">
          <option value="YouTube">YouTube</option>
          <option value="BiliBili">BiliBili</option>
          <option value="SoundCloud">SoundCloud</option>
          <option value="Bandcamp">Bandcamp</option>
          <option value="PeerTube">PeerTube</option>
          <option value="NicoNico">NicoNico</option>
          <option value="MediaCCC">MediaCCC</option>
        </select>
        <input v-model="searchQuery" class="search-input" placeholder="搜索视频..." @keyup.enter="doSearch" />
        <button class="search-btn" @click="doSearch" :disabled="searching">{{ searching ? '搜索中...' : '搜索' }}</button>
      </div>
      <div class="filter-bar">
        <select v-model="contentFilter" class="filter-select">
          <option value="videos">视频</option>
          <option value="channels">频道</option>
          <option value="lives">直播</option>
          <option value="animes">番剧</option>
          <option value="movies_and_tv">影视</option>
        </select>
        <select v-model="sortFilter" class="filter-select">
          <option value="sort_overall">综合排序</option>
          <option value="sort_publish_time">最新发布</option>
          <option value="sort_view">最多播放</option>
          <option value="sort_bullet_comments">最多弹幕</option>
          <option value="sort_comments">最多评论</option>
          <option value="sort_bookmark">最多收藏</option>
        </select>
        <select v-model="durationFilter" class="filter-select">
          <option value="all">全部时长</option>
          <option value="short_video">短视频</option>
          <option value="medium_length">中等</option>
          <option value="long_video">长视频</option>
          <option value="extra_long">超长</option>
        </select>
      </div>
      <div v-if="searchItems.length > 0" class="results">
        <div class="grid">
          <VideoCard v-for="item in searchItems" :key="item.url" :item="item" @cardClick="onResultClick" />
        </div>
        <div v-if="loadingMore" class="loading">加载更多...</div>
        <div v-else-if="!hasNextPage && searchItems.length > 0" class="end-hint">已显示全部结果</div>
        <div ref="scrollSentinel" class="scroll-sentinel"></div>
      </div>
      <div v-else-if="!searching && !searchStarted" class="search-idle">
        <div v-if="searchHistory.entries.length" class="history-section">
          <h3 class="section-title">搜索历史</h3>
          <div class="history-list">
            <div v-for="entry in searchHistory.entries.slice(0, 10)" :key="entry.query + entry.timestamp" class="history-item" @click="searchQuery = entry.query; doSearch()">
              <span class="history-query">{{ entry.query }}</span>
              <span class="history-service">{{ entry.service }}</span>
              <button class="history-remove" @click.stop="searchHistory.remove(entry.query)">✕</button>
            </div>
          </div>
          <button v-if="searchHistory.entries.length > 0" class="clear-history-btn" @click="searchHistory.clear()">清空历史</button>
        </div>
        <div v-else class="placeholder">输入关键词搜索视频</div>
      </div>
      <div v-else-if="searching" class="loading">搜索中...</div>
      <div v-else-if="!hasNextPage && searchStarted" class="placeholder">没有找到结果</div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted, watch } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { useSubscriptionsStore, type Subscription } from '../stores/subscriptions'
import { usePlaylistsStore } from '../stores/playlists'
import { usePlayQueueStore } from '../stores/playQueue'
import { useSearchHistoryStore } from '../stores/searchHistory'
import VideoCard from '../components/VideoCard.vue'
import SubscriptionList from '../components/SubscriptionList.vue'
import FeedView from '../components/FeedView.vue'
import PipePipe, { extractNextPage } from '../plugins/bridge'
import type { StreamInfoItem, PlaylistInfoResult, SearchResult, Page } from '../plugins/bridge'
import { useFeedStore } from '../stores/feed'

const router = useRouter()
const route = useRoute()
const subStore = useSubscriptionsStore()
const plStore = usePlaylistsStore()
const queueStore = usePlayQueueStore()
const searchHistory = useSearchHistoryStore()
const feedStore = useFeedStore()

const pluginStatus = ref('')
const pluginError = ref('')
const activeTab = ref<'playlists' | 'favorites' | 'subs' | 'feed' | 'search'>('playlists')
const subCount = computed(() => subStore.subscriptions.length)
const favCount = computed(() => plStore.favoritesItems.length)
const sortedFavs = computed(() => [...plStore.favoritesItems].sort((a: any, b: any) => b.addedAt - a.addedAt))

// ── serviceId 解析 ──
const serviceId = ref(-1)
async function resolveServiceId(url: string) {
  try { const r = await PipePipe.resolveUrl({ url }); serviceId.value = r.serviceId } catch { serviceId.value = -1 }
}

onMounted(async () => {
  try {
    await PipePipe.echo()
    pluginStatus.value = '✓'
  } catch (e: any) {
    pluginStatus.value = '✗'
    pluginError.value = '插件: ' + (e.message || e)
  }
  const playlistUrl = route.query.playlistUrl as string
  if (playlistUrl) { activeTab.value = 'playlists'; loadPlaylist(playlistUrl) }
  if (typeof IntersectionObserver !== 'undefined') {
    observer = new IntersectionObserver((entries) => {
      for (const entry of entries) {
        if (entry.isIntersecting && hasNextPage.value && !loadingMore.value) loadMore()
      }
    }, { rootMargin: '200px' })
  }
})

watch(() => scrollSentinel.value, (el) => {
  if (observer && el) { observer.disconnect(); observer.observe(el) }
})

// ══════ 播放列表面 ══════
const plUrl = ref('')
const plItems = ref<StreamInfoItem[]>([])
const plInfo = ref<PlaylistInfoResult | null>(null)
const plLoading = ref(false)
const plLoadingMore = ref(false)
const plError = ref('')
const plNextPage = ref<Page | null>(null)
const plHasNext = ref(false)
const isBookmarked = ref(false)
const plScrollSentinel = ref<HTMLElement | null>(null)
const itemMenu = ref<{ show: boolean; x: number; y: number; item: StreamInfoItem | null; index: number }>({ show: false, x: 0, y: 0, item: null, index: -1 })
let plObserver: IntersectionObserver | null = null

const playlistDuration = computed(() =>
  plItems.value.reduce((sum, i) => sum + (i.duration || 0), 0))

async function loadPlaylist(url: string) {
  plLoading.value = true; plError.value = ''
  try {
    await resolveServiceId(url)
    const r = await PipePipe.getPlaylistInfo({ url, serviceId: serviceId.value })
    plInfo.value = r
    plItems.value = r.items || []
    plNextPage.value = extractNextPage(r)
    plHasNext.value = !!r._hasNextPage
    isBookmarked.value = plStore.isBookmarked(url)
  } catch (e: any) { plError.value = '加载失败: ' + (e.message || e) }
  finally { plLoading.value = false }
  setupPlSentinel()
}

function addPlaylist() {
  const url = plUrl.value.trim()
  if (!url) return
  loadPlaylist(url)
  plUrl.value = ''
}

async function loadMorePlaylist() {
  if (plLoadingMore.value || !plHasNext.value || !plNextPage.value) return
  plLoadingMore.value = true
  try {
    const r = await PipePipe.getMorePlaylistItems({ url: plInfo.value!.url, serviceId: serviceId.value, page: plNextPage.value })
    const existing = new Set(plItems.value.map(i => i.url))
    for (const item of (r.items || [])) { if (!existing.has(item.url)) plItems.value.push(item) }
    plNextPage.value = extractNextPage(r)
    plHasNext.value = !!r._hasNextPage
  } catch (e: any) { plError.value = '加载更多失败: ' + (e.message || e) }
  finally { plLoadingMore.value = false }
}

function toggleBookmark() {
  const r = plInfo.value
  if (!r) return
  if (isBookmarked.value) { plStore.unbookmarkRemote(r.url); isBookmarked.value = false }
  else { plStore.bookmarkRemote({ url: r.url, name: r.name, thumbnailUrl: r.thumbnailUrl, uploaderName: r.uploaderName, uploaderAvatarUrl: r.uploaderAvatarUrl || '', streamCount: r.streamCount }); isBookmarked.value = true }
}

function setupPlSentinel() {
  plObserver?.disconnect()
  if (typeof IntersectionObserver === 'undefined') return
  plObserver = new IntersectionObserver((entries) => {
    if (entries[0]?.isIntersecting && plHasNext.value && !plLoadingMore.value) loadMorePlaylist()
  }, { rootMargin: '200px' })
  watch(plScrollSentinel, (el) => { if (plObserver && el) { plObserver.disconnect(); plObserver.observe(el) } }, { immediate: true })
}

onUnmounted(() => { plObserver?.disconnect() })

function playAllPlaylist() {
  if (!plItems.value.length) return
  queueStore.replaceWith(plItems.value.map(item => ({ url: item.url, title: item.name, thumbnailUrl: item.thumbnailUrl, duration: item.duration || 0, uploaderName: item.uploaderName || '' })))
  router.push({ name: 'video-player', query: { url: plItems.value[0].url } })
}

function enqueueAllPlaylist() {
  for (const item of plItems.value) queueStore.add({ url: item.url, title: item.name, thumbnailUrl: item.thumbnailUrl, duration: item.duration || 0, uploaderName: item.uploaderName || '' })
}

function playAllBg() {
  if (!plItems.value.length) return
  queueStore.replaceWith(plItems.value.map(item => ({ url: item.url, title: item.name, thumbnailUrl: item.thumbnailUrl, duration: item.duration || 0, uploaderName: item.uploaderName || '' })))
}

function openChannelFromPlaylist() {
  const r = plInfo.value
  if (r?.uploaderUrl) router.push({ name: 'channel', query: { url: r.uploaderUrl } })
}

let _plLongPressTimer: ReturnType<typeof setTimeout> | null = null
function onPlLongPressStart(e: TouchEvent, item: StreamInfoItem, index: number) {
  _plLongPressTimer = setTimeout(() => {
    _plLongPressTimer = null
    const touch = e.touches[0]
    itemMenu.value = { show: true, x: touch.clientX, y: touch.clientY, item, index }
    const close = (ev: Event) => {
      if (!(ev.target as HTMLElement)?.closest?.('.item-menu')) { itemMenu.value.show = false; document.removeEventListener('click', close); document.removeEventListener('touchend', close) }
    }
    setTimeout(() => { document.addEventListener('click', close); document.addEventListener('touchend', close) }, 0)
  }, 500)
}
function onPlLongPressEnd() { if (_plLongPressTimer) { clearTimeout(_plLongPressTimer); _plLongPressTimer = null } }

function playFromHere() {
  if (!itemMenu.value.item || !plItems.value.length) return
  const itemsFrom = plItems.value.slice(itemMenu.value.index)
  queueStore.replaceWith(itemsFrom.map(item => ({ url: item.url, title: item.name, thumbnailUrl: item.thumbnailUrl, duration: item.duration || 0, uploaderName: item.uploaderName || '' })))
  itemMenu.value.show = false
  router.push({ name: 'video-player', query: { url: itemMenu.value.item.url } })
}

function enqueueFromHere() {
  if (!itemMenu.value.item) return
  for (const item of plItems.value.slice(itemMenu.value.index)) queueStore.add({ url: item.url, title: item.name, thumbnailUrl: item.thumbnailUrl, duration: item.duration || 0, uploaderName: item.uploaderName || '' })
  itemMenu.value.show = false
}

function fmtDuration(seconds: number): string {
  if (!seconds || seconds <= 0) return ''
  const h = Math.floor(seconds / 3600)
  const m = Math.floor((seconds % 3600) / 60)
  if (h > 0) return `· ${h}小时${m}分钟`
  return `· ${m}分钟`
}

function openBookmark(url: string) { loadPlaylist(url) }

// ══════ 订阅 tab ══════
function openChannel(sub: Subscription) { router.push({ name: 'channel', query: { url: sub.url } }) }

// ══════ 搜索 tab ══════
const searchServiceId = ref(-1)
const searchQuery = ref('')
const serviceName = ref('BiliBili')
const searching = ref(false)
const searchStarted = ref(false)
const searchItems = ref<StreamInfoItem[]>([])
const searchError = ref('')
const hasNextPage = ref(false)
const nextPage = ref<Page | null>(null)
const loadingMore = ref(false)
const scrollSentinel = ref<HTMLElement | null>(null)
const contentFilter = ref('videos')
const sortFilter = ref('sort_overall')
const durationFilter = ref('all')

// 服务名称 → serviceId 映射
const SERVICE_ID_MAP: Record<string, number> = { YouTube: 0, BiliBili: 5, SoundCloud: 1, Bandcamp: 4, PeerTube: 3, NicoNico: 6, MediaCCC: 2 }

async function doSearch() {
  const q = searchQuery.value.trim()
  if (!q) return
  const sid = SERVICE_ID_MAP[serviceName.value]
  if (sid == null) { searchError.value = '不支持的服务: ' + serviceName.value; return }
  searchServiceId.value = sid
  searching.value = true; searchStarted.value = true
  searchItems.value = []; searchError.value = ''
  hasNextPage.value = false; nextPage.value = null
  searchHistory.add(q, serviceName.value)
  try {
    const res: SearchResult = await PipePipe.search({ query: q, serviceId: searchServiceId.value, contentFilter: contentFilter.value, sortFilter: sortFilter.value, durationFilter: durationFilter.value })
    searchItems.value = res.items || []
    hasNextPage.value = !!res._hasNextPage
    nextPage.value = extractNextPage(res)
  } catch (e: any) { searchItems.value = []; searchError.value = '搜索失败: ' + (e.message || e) }
  finally { searching.value = false }
}

async function loadMore() {
  if (loadingMore.value || !hasNextPage.value || !nextPage.value) return
  loadingMore.value = true
  try {
    const res: SearchResult = await PipePipe.searchMore({ query: searchQuery.value, serviceId: searchServiceId.value, page: nextPage.value, contentFilter: contentFilter.value, sortFilter: sortFilter.value, durationFilter: durationFilter.value })
    const existing = new Set(searchItems.value.map(i => i.url))
    for (const item of (res.items || [])) { if (!existing.has(item.url)) searchItems.value.push(item) }
    hasNextPage.value = !!res._hasNextPage
    nextPage.value = extractNextPage(res)
  } catch (e: any) { searchError.value = '加载更多失败: ' + (e.message || e) }
  finally { loadingMore.value = false }
}

let observer: IntersectionObserver | null = null

function onVideoClick(item: StreamInfoItem) {
  if (item.type === 'channel') router.push({ name: 'channel', query: { url: item.url || item.uploaderUrl } })
  else router.push({ name: 'video-player', query: { url: item.url } })
}

function onResultClick(item: StreamInfoItem) {
  if (item.type === 'channel') router.push({ name: 'channel', query: { url: item.url || item.uploaderUrl } })
  else if (item.type === 'playlist') { activeTab.value = 'playlists'; loadPlaylist(item.url) }
  else router.push({ name: 'video-player', query: { url: item.url } })
}
</script>

<style scoped>
.video-view { display: flex; flex-direction: column; height: 100%; overflow: hidden; }

.plugin-status { padding: 6px 12px; font-size: 12px; color: var(--fg-muted); background: var(--bg-secondary); border-bottom: 1px solid var(--border); }
.plugin-status.error { color: #e74c3c; background: #fdf0ef; }

.tabs { display: flex; border-bottom: 1px solid var(--border); flex-shrink: 0; }
.tab { flex: 1; padding: 12px; background: none; border: none; color: var(--fg-muted); font-size: 14px; font-weight: 600; cursor: pointer; border-bottom: 2px solid transparent; transition: all 0.15s; }
.tab.active { color: var(--accent); border-bottom-color: var(--accent); }

.panel { flex: 1; overflow-y: auto; padding: 12px; }

.plugin-error-detail { font-size: 11px; margin-top: 2px; }

.error-msg { padding: 8px 12px; margin-bottom: 8px; font-size: 13px; color: #e74c3c; background: #fdf0ef; border-radius: 6px; border: 1px solid #f5c6cb; }

/* --- Playlist tab --- */
.add-bar { display: flex; gap: 8px; margin-bottom: 12px; }
.add-input { flex: 1; padding: 8px 12px; border: 1px solid var(--border); border-radius: 8px; background: var(--bg-secondary); color: var(--fg); font-size: 14px; }
.add-input:focus { outline: none; border-color: var(--accent); }
.add-btn { padding: 8px 16px; background: var(--accent); color: var(--bg); border: none; border-radius: 8px; font-size: 14px; font-weight: 600; cursor: pointer; }
.add-btn:disabled { opacity: 0.5; }

.playlist-header { display: flex; gap: 12px; margin-bottom: 16px; padding-bottom: 12px; border-bottom: 1px solid var(--border); }
.pl-thumb { width: 120px; height: 68px; border-radius: 8px; object-fit: cover; background: var(--border); flex-shrink: 0; }
.pl-info h3 { font-size: 16px; font-weight: 700; margin: 0 0 4px; color: var(--fg); }
.pl-meta { font-size: 12px; color: var(--fg-muted); margin: 0 0 8px; }
.pl-duration { color: var(--fg-muted); font-size: 11px; }
.pl-actions { display: flex; gap: 6px; flex-wrap: wrap; }
.action-btn-sm { padding: 4px 10px; font-size: 11px; border-radius: 6px; border: 1px solid var(--border); background: var(--bg-secondary); color: var(--fg); cursor: pointer; white-space: nowrap; }
.action-btn-sm:hover { border-color: var(--accent); color: var(--accent); }
.bookmark-btn-sm { padding: 4px 10px; font-size: 11px; border-radius: 6px; border: 1px solid var(--accent); background: none; color: var(--accent); cursor: pointer; white-space: nowrap; }
.bookmark-btn-sm.bookmarked { background: var(--accent); color: var(--bg); }

/* Context menu for playlist items */
.item-menu { position: fixed; z-index: 9999; background: var(--bg); border: 1px solid var(--border); border-radius: 8px; box-shadow: 0 4px 16px rgba(0,0,0,0.3); padding: 4px 0; min-width: 160px; }
.item-menu-item { padding: 10px 16px; font-size: 13px; color: var(--fg); cursor: pointer; white-space: nowrap; }
.item-menu-item:hover { background: var(--border); }
.item-menu-item:first-child { border-radius: 8px 8px 0 0; }
.item-menu-item:last-child { border-radius: 0 0 8px 8px; border-top: 1px solid var(--border); color: var(--fg-muted); }

.section-title { font-size: 14px; font-weight: 600; color: var(--fg); margin: 0 0 12px; }
.bookmark-list { display: flex; flex-direction: column; gap: 8px; }
.bookmark-item { display: flex; align-items: center; gap: 10px; padding: 8px; border-radius: 8px; border: 1px solid var(--border); cursor: pointer; transition: background 0.15s; }
.bookmark-item:hover { background: var(--bg-secondary); }
.bm-thumb { width: 80px; height: 45px; border-radius: 4px; object-fit: cover; background: var(--border); flex-shrink: 0; }
.bm-info { flex: 1; min-width: 0; }
.bm-name { font-size: 13px; font-weight: 600; color: var(--fg); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.bm-meta { font-size: 11px; color: var(--fg-muted); }
.remove-btn { background: none; border: none; color: var(--fg-muted); font-size: 16px; cursor: pointer; padding: 4px; border-radius: 4px; flex-shrink: 0; }
.remove-btn:hover { background: var(--border); }

/* --- Search tab --- */

.feed-badge { background: var(--accent); color: #fff; font-size: 10px; padding: 1px 5px; border-radius: 8px; margin-left: 4px; }
.search-bar { display: flex; gap: 8px; margin-bottom: 12px; }
.filter-bar { display: flex; gap: 6px; margin-bottom: 12px; flex-wrap: wrap; }
.filter-select { padding: 6px 8px; border: 1px solid var(--border); border-radius: 6px; background: var(--bg-secondary); color: var(--fg); font-size: 12px; cursor: pointer; }
.filter-select:focus { outline: none; border-color: var(--accent); }
.service-select { padding: 8px 10px; border: 1px solid var(--border); border-radius: 8px; background: var(--bg-secondary); color: var(--fg); font-size: 13px; cursor: pointer; }
.search-input { flex: 1; padding: 8px 12px; border: 1px solid var(--border); border-radius: 8px; background: var(--bg-secondary); color: var(--fg); font-size: 14px; }
.search-input:focus { outline: none; border-color: var(--accent); }
.search-btn { padding: 8px 16px; background: var(--accent); color: var(--bg); border: none; border-radius: 8px; font-size: 14px; font-weight: 600; cursor: pointer; }
.search-btn:disabled { opacity: 0.5; }

.suggestion { font-size: 13px; color: var(--fg-muted); margin: 0 0 12px; }
.grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(180px, 1fr)); gap: 12px; }
.placeholder { text-align: center; padding: 48px 16px; color: var(--fg-muted); font-size: 14px; }
.loading { text-align: center; padding: 32px; color: var(--fg-muted); }
.end-hint { text-align: center; padding: 16px; font-size: 12px; color: var(--fg-muted); }
.scroll-sentinel { height: 1px; }

/* --- Subscription tab --- */
.subs-layout { display: flex; gap: 16px; height: 100%; }
.subs-sidebar { width: 220px; flex-shrink: 0; overflow-y: auto; border-right: 1px solid var(--border); padding-right: 8px; }
.subs-main { flex: 1; overflow-y: auto; display: flex; align-items: center; justify-content: center; }

@media (max-width: 600px) {
  .subs-layout { flex-direction: column; }
  .subs-sidebar { width: 100%; border-right: none; border-bottom: 1px solid var(--border); padding-right: 0; padding-bottom: 8px; max-height: 200px; }
}
</style>

``

