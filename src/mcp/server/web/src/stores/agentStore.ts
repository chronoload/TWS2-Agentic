import { defineStore } from 'pinia'
import { ref } from 'vue'
import { agentChatStreamFetch, resetAgent } from '../api'

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

const SESSION_ID_KEY = 'ts2_agent_session_id'

function loadSessionId(): string {
  const saved = localStorage.getItem(SESSION_ID_KEY)
  if (saved) return saved
  const id = 'sess_' + Date.now().toString(36) + '_' + Math.random().toString(36).substring(2, 8)
  localStorage.setItem(SESSION_ID_KEY, id)
  return id
}

export const useAgentStore = defineStore('agent', () => {
  const messages = ref<ChatMessage[]>([])
  const loading = ref(false)
  const agentAvailable = ref(false)
  const streamingText = ref('')
  const activeToolCalls = ref<ToolCallInfo[]>([])
  const sessionId = ref(loadSessionId())
  let msgId = 0
  let abortController: AbortController | null = null

  function addMessage(role: 'user' | 'assistant' | 'tool', content: string, toolCalls?: ToolCallInfo[], toolName?: string): number {
    const id = ++msgId
    messages.value.push({ id, role, content, timestamp: Date.now(), toolCalls, toolName })
    return id
  }

  function updateMessage(id: number, content: string): void {
    const msg = messages.value.find(m => m.id === id)
    if (msg) msg.content = content
  }

  async function send(text: string) {
    addMessage('user', text)
    loading.value = true
    streamingText.value = ''
    activeToolCalls.value = []
    let toolCallHappened = false
    const toolMsgIds = new Map<string, number>()

    const context: Record<string, any> = {
      source: 'web-mobile',
      ui_state: {
        current_page: window.location.pathname,
        timestamp: new Date().toISOString(),
        viewport: `${window.innerWidth}x${window.innerHeight}`,
        online: navigator.onLine,
      },
    }

    try {
      const bootstrap = (window as any).__TS2_BOOTSTRAP__
      if (bootstrap) {
        if (bootstrap.courses && Array.isArray(bootstrap.courses)) {
          context.ui_state.available_courses = bootstrap.courses.length
        }
        if (bootstrap.tasks) {
          context.ui_state.available_tasks = Array.isArray(bootstrap.tasks) ? bootstrap.tasks.length : 0
        }
      }
    } catch { /* silent */ }

    abortController = await agentChatStreamFetch(
      text,
      context,
      (token) => { streamingText.value += token },
      (name, args) => {
        if (streamingText.value) {
          addMessage('assistant', streamingText.value)
          streamingText.value = ''
        }
        toolCallHappened = true
        activeToolCalls.value.push({ name, args, status: 'running' })
        toolMsgIds.set(name, addMessage('tool', '⏳ 调用中...', undefined, name))
      },
      (name, result, checkpointHash) => {
        if (checkpointHash) (window as any).__lastCpHash = checkpointHash
        const tool = activeToolCalls.value.find(t => t.name === name && t.status === 'running')
        if (tool) {
          tool.result = result
          tool.status = 'done'
          if (checkpointHash) tool.checkpointHash = checkpointHash
        }
        const msgId = toolMsgIds.get(name)
        if (msgId) {
          const shortResult = result.length > 500 ? result.substring(0, 500) + '...' : result
          updateMessage(msgId, shortResult)
          toolMsgIds.delete(name)
        }
      },
      (reply) => {
        if (streamingText.value) {
          addMessage('assistant', streamingText.value)
        } else if (!toolCallHappened) {
          addMessage('assistant', reply)
        }
        for (const [_, mid] of toolMsgIds) {
          updateMessage(mid, '⚠️ 工具未返回结果')
        }
        streamingText.value = ''
        activeToolCalls.value = []
        loading.value = false
      },
      (err) => {
        addMessage('assistant', `错误: ${err}`)
        streamingText.value = ''
        activeToolCalls.value = []
        loading.value = false
      },
      sessionId.value,
    )
  }

  function cancel() {
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

  function setSessionId(id: string) {
    sessionId.value = id
    localStorage.setItem(SESSION_ID_KEY, id)
  }

  function refreshSessionId() {
    const id = 'sess_' + Date.now().toString(36) + '_' + Math.random().toString(36).substring(2, 8)
    setSessionId(id)
  }

  async function reset() {
    cancel()
    loading.value = false
    streamingText.value = ''
    activeToolCalls.value = []
    try { await resetAgent() } catch { /* ignore */ }
    messages.value = []
    msgId = 0
    refreshSessionId()
    addMessage('assistant', '对话已重置。你好！我是 TS2 学习助手。')
  }

  function setAgentStatus(available: boolean) {
    agentAvailable.value = available
  }

  function setMessagesFromRestore(uiMsgs: any[]) {
    messages.value = []
    msgId = 0
    for (const m of uiMsgs) {
      if (m.role === 'tool') {
        addMessage('tool', m.content || '', undefined, m.tool_name)
      } else if (m.role === 'assistant' && m.tool_calls) {
        const tcs: ToolCallInfo[] = m.tool_calls.map((tc: any) => {
          let args: Record<string, unknown> = {}
          try { args = JSON.parse(tc.function?.arguments || '{}') } catch {}
          return {
            name: tc.function?.name || tc.name || '',
            args,
            status: 'done' as const,
            checkpointHash: tc.checkpoint_hash || undefined,
          }
        })
        addMessage('assistant', m.content || '', tcs)
      } else {
        addMessage(m.role as 'user' | 'assistant', m.content || '')
      }
    }
  }

  function resetMessages() {
    messages.value = []
    msgId = 0
  }

  return {
    messages, loading, agentAvailable, streamingText, activeToolCalls, sessionId,
    addMessage, send, cancel, reset, setSessionId, refreshSessionId,
    setAgentStatus, setMessagesFromRestore, resetMessages,
  }
})
