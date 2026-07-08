import { defineStore } from 'pinia'
import { ref } from 'vue'
import { getAgentCheckpoints, getAgentCheckpointDiff, restoreAgentCheckpoint } from '../api'
import { useAgentStore } from './agentStore'

export interface CheckpointDiff {
  path: string
  status: string
  additions?: number
  deletions?: number
  diff?: string
}

export interface CheckpointSummary {
  additions: number
  deletions: number
  files_changed: number
}

export const useCheckpointStore = defineStore('checkpoint', () => {
  const showPanel = ref(false)
  const list = ref<any[]>([])
  const activeDiff = ref('')
  const diffData = ref<CheckpointDiff[]>([])
  const diffSummary = ref<CheckpointSummary | null>(null)
  const diffLoading = ref(false)
  const version = ref(0)
  const hasNew = ref(false)
  const showRestoreModal = ref(false)
  const restoreTarget = ref('')

  async function fetchList() {
    const agent = useAgentStore()
    try {
      const res = await getAgentCheckpoints(agent.sessionId)
      const data = res.data?.data
      list.value = data?.checkpoints ?? []
      if (data?.version) version.value = data.version
    } catch { list.value = [] }
  }

  async function showDiff(hash: string) {
    if (activeDiff.value === hash) {
      activeDiff.value = ''
      return
    }
    activeDiff.value = hash
    diffLoading.value = true
    diffData.value = []
    diffSummary.value = null
    try {
      const res = await getAgentCheckpointDiff(hash)
      diffData.value = res.data?.data?.diff ?? []
      diffSummary.value = res.data?.data?.summary ?? null
    } catch { diffData.value = [] }
    diffLoading.value = false
  }

  function openRestoreModal(hash: string) {
    restoreTarget.value = hash
    showRestoreModal.value = true
  }

  async function doRestore(restoreType: string) {
    showRestoreModal.value = false
    const hash = restoreTarget.value
    if (!hash) return
    try {
      const res = await restoreAgentCheckpoint(hash, restoreType)
      if (res.data?.data?.restored) {
        showPanel.value = false
        activeDiff.value = ''
        diffData.value = []
        const agent = useAgentStore()
        agent.setMessagesFromRestore(res.data?.data?.ui_messages ?? [])
        ;(window as any).__lastCpHash = hash
        alert('已恢复检查点')
      } else {
        alert('恢复失败: ' + (res.data?.data?.error || '未知错误'))
      }
    } catch (e: any) {
      alert('恢复失败: ' + (e.message || '网络错误'))
    }
  }

  function onCheckpointCreated(newVersion: number) {
    if (newVersion > version.value) {
      version.value = newVersion
      if (showPanel.value) {
        fetchList()
      } else {
        hasNew.value = true
      }
    }
  }

  return {
    showPanel, list, activeDiff, diffData, diffSummary, diffLoading,
    version, hasNew, showRestoreModal, restoreTarget,
    fetchList, showDiff, openRestoreModal, doRestore, onCheckpointCreated,
  }
})
