import { defineStore } from 'pinia'
import { ref } from 'vue'
import {
  swarmGetAgents, swarmGetTasks, swarmEnableCluster,
  swarmDisableCluster, swarmCancelAgent, swarmPollTask,
} from '../api'

export interface SwarmAgent {
  name: string
  role: string
  status: string
  is_busy: boolean
  system_prompt?: string
  model?: string
  max_turns: number
  allowed_tools?: string[]
  denied_tools?: string[]
  running_tasks?: Array<{ task_id: string }>
}

export interface SwarmTask {
  task_id: string
  agent_name: string
  status: string
  content?: string
  error?: string
  completed: boolean
}

export const useSwarmStore = defineStore('swarm', () => {
  const agents = ref<SwarmAgent[]>([])
  const tasks = ref<SwarmTask[]>([])
  const swarmEnabled = ref(false)
  const available = ref(false)
  const loading = ref(false)
  const panelOpen = ref(false)
  const detailText = ref('')

  const pollTimers = new Map<string, ReturnType<typeof setInterval>>()

  async function refresh() {
    loading.value = true
    try {
      const res = await swarmGetAgents()
      const data = res.data?.data
      if (!data?.available) {
        available.value = false
        agents.value = []
        return
      }
      available.value = true
      agents.value = data.agents || []
      swarmEnabled.value = data.swarm_enabled || false
    } catch {
      available.value = false
      agents.value = []
    }
    loading.value = false
  }

  async function refreshTasks() {
    try {
      const res = await swarmGetTasks()
      const data = res.data?.data
      tasks.value = data?.tasks || []

      // 自动轮询未完成任务
      for (const t of tasks.value) {
        if (!t.completed && !pollTimers.has(t.task_id)) {
          pollTimers.set(t.task_id, setInterval(() => poll(t.task_id), 5000))
        }
      }
      // 清除已完成任务的定时器
      for (const [tid, timer] of pollTimers) {
        if (!tasks.value.find(t => t.task_id === tid && !t.completed)) {
          clearInterval(timer)
          pollTimers.delete(tid)
        }
      }
    } catch { /* silent */ }
  }

  async function enableCluster(reason: string) {
    try {
      const res = await swarmEnableCluster(reason)
      if (res.data?.code === 0) {
        swarmEnabled.value = true
        refresh()
      }
    } catch { /* silent */ }
  }

  async function disableCluster() {
    try {
      const res = await swarmDisableCluster()
      if (res.data?.code === 0) {
        swarmEnabled.value = false
        refresh()
      }
    } catch { /* silent */ }
  }

  async function cancelAgent(agentName: string) {
    try {
      await swarmCancelAgent(agentName)
      refresh()
    } catch { /* silent */ }
  }

  async function poll(taskId: string): Promise<boolean> {
    try {
      const res = await swarmPollTask(taskId)
      const d = res.data?.data
      if (d?.completed) {
        const timer = pollTimers.get(taskId)
        if (timer) {
          clearInterval(timer)
          pollTimers.delete(taskId)
        }
        refresh()
        refreshTasks()
        return true
      }
    } catch { /* silent */ }
    return false
  }

  function cleanup() {
    for (const [, timer] of pollTimers) {
      clearInterval(timer)
    }
    pollTimers.clear()
  }

  return {
    agents, tasks, swarmEnabled, available, loading, panelOpen, detailText,
    refresh, refreshTasks, enableCluster, disableCluster, cancelAgent, poll, cleanup,
  }
})
