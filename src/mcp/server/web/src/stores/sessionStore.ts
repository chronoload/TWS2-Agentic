import { defineStore } from 'pinia'
import { ref } from 'vue'
import { getAgentSessions, createAgentSession, switchAgentSession, deleteAgentSession } from '../api'
import { useAgentStore } from './agentStore'

export interface SessionInfo {
  id: string
  summary?: string
  preview?: string
  timestamp?: number
  message_count?: number
}

export const useSessionStore = defineStore('session', () => {
  const sessions = ref<SessionInfo[]>([])
  const showList = ref(false)
  const loading = ref(false)

  async function fetchList() {
    loading.value = true
    try {
      const res = await getAgentSessions()
      sessions.value = res.data?.data ?? res.data ?? []
    } catch { /* silent */ }
    finally { loading.value = false }
  }

  async function createNew() {
    const agent = useAgentStore()
    agent.cancel()
    agent.refreshSessionId()
    try {
      const res = await createAgentSession()
      const data = res.data?.data ?? res.data
      if (data?.created) {
        agent.resetMessages()
        agent.addMessage('assistant', '新会话已创建。你好！我是 TS2 学习助手。')
      } else {
        await agent.reset()
      }
    } catch {
      try { await agent.reset() } catch { /* ignore */ }
    }
  }

  async function loadSession(sessionId: string) {
    const agent = useAgentStore()
    try {
      const res = await switchAgentSession(sessionId)
      const data = res.data?.data ?? res.data
      if (data?.switched) {
        showList.value = false
        agent.resetMessages()
        const restoredMessages = data.messages || []
        if (restoredMessages.length > 0) {
          for (const msg of restoredMessages) {
            if (msg.role === 'tool') {
              agent.addMessage('tool', msg.content || '', undefined, msg.tool_name || '')
            } else if (msg.role === 'assistant') {
              const toolCalls = msg.tool_calls?.map((tc: any) => {
                const tcDict = typeof tc === 'object' ? tc : {}
                const func = tcDict.function || {}
                let args = {}
                try {
                  args = typeof func.arguments === 'string' ? JSON.parse(func.arguments) : (func.arguments || {})
                } catch { /* ignore */ }
                return { name: func.name || '', args, status: 'done' as const }
              })
              agent.addMessage('assistant', msg.content || '', toolCalls?.length ? toolCalls : undefined)
            } else if (msg.role === 'user') {
              agent.addMessage('user', msg.content || '')
            }
          }
        } else {
          agent.addMessage('assistant', '已载入历史会话。')
        }
      } else {
        alert(data?.error || '载入会话失败')
      }
    } catch {
      alert('载入会话失败')
    }
  }

  async function removeSession(sessionId: string) {
    try {
      await deleteAgentSession(sessionId)
      sessions.value = sessions.value.filter(s => s.id !== sessionId)
    } catch { /* silent */ }
  }

  return { sessions, showList, loading, fetchList, createNew, loadSession, removeSession }
})
