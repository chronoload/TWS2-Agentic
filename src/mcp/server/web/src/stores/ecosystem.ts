import { ref } from 'vue'
import { defineStore } from 'pinia'
import * as api from '../api'

export interface ConceptData {
  id: string
  label: string
  aliases: string[]
  depth: number
  freshness: number
  connectivity: number
  entropy: number
  is_fossilized: boolean
  parent_ids: string[]
  child_ids: string[]
  related_ids: Record<string, number>
}

export interface ThreadData {
  id: string
  label: string
  description: string
  concept_ids: string[]
  clarity: number
  entropy: number
  momentum: number
  is_archived: boolean
}

export interface ArtifactData {
  id: string
  artifact_type: string
  title: string
  file_path: string | null
  concept_ids: string[]
  word_count: number
}

export interface InspirationData {
  action_type: string
  label: string
  description: string
  priority: number
}

export const useEcosystemStore = defineStore('ecosystem', () => {
  const concepts = ref<Record<string, ConceptData>>({})
  const threads = ref<Record<string, ThreadData>>({})
  const artifacts = ref<Record<string, ArtifactData>>({})
  const inspirations = ref<InspirationData[]>([])
  const neighborEdges = ref<{ source: string; target: string; strength: number }[]>([])
  const totalConceptCount = ref(0)
  const tick = ref(0)
  const globalEntropy = ref(0)
  const era = ref('')
  const player = ref({ total_actions: 0, total_concepts_encountered: 0, current_concept_id: '', current_thread_id: '' })
  const centerConceptId = ref('')
  const loading = ref(false)
  const error = ref('')

  async function fetchState() {
    loading.value = true
    error.value = ''
    try {
      const res = await api.ecoState()
      const d = res.data?.data ?? res.data
      tick.value = d.tick ?? 0
      globalEntropy.value = d.global_entropy ?? 0
      era.value = d.era ?? ''
      threads.value = d.threads ?? {}
      player.value = d.player ?? player.value
    } catch (e: any) {
      error.value = e.message || 'Failed to load ecosystem state'
    } finally {
      loading.value = false
    }
  }

  async function fetchNeighborhood(conceptId?: string) {
    loading.value = true
    error.value = ''
    try {
      const res = await api.ecoNeighborhood(conceptId)
      const d = res.data?.data ?? res.data
      concepts.value = d.concepts ?? {}
      neighborEdges.value = d.edges ?? []
      totalConceptCount.value = d.total_concepts ?? 0
      centerConceptId.value = d.center_id ?? conceptId ?? ''
      // merge thread metadata from neighborhood response
      if (d.threads) {
        for (const [tid, t] of Object.entries(d.threads)) {
          (threads.value as any)[tid] = t
        }
      }
    } catch (e: any) {
      error.value = e.message || 'Failed to load neighborhood'
    } finally {
      loading.value = false
    }
  }

  function _refetch() {
    if (centerConceptId.value) return fetchNeighborhood(centerConceptId.value)
  }

  async function doRecord(text: string) {
    error.value = ''
    try {
      const res = await api.ecoRecord(text)
      const d = res.data?.data ?? res.data
      await _refetch()
      return d
    } catch (e: any) {
      error.value = e.message || 'Record failed'
      return null
    }
  }

  async function doDive(conceptId: string) {
    error.value = ''
    try {
      const res = await api.ecoDive(conceptId)
      await _refetch()
      return res.data?.data ?? res.data
    } catch (e: any) {
      error.value = e.message || 'Dive failed'
      return null
    }
  }

  async function doCross(conceptIdA: string, conceptIdB: string) {
    error.value = ''
    try {
      const res = await api.ecoCross(conceptIdA, conceptIdB)
      await _refetch()
      return res.data?.data ?? res.data
    } catch (e: any) {
      error.value = e.message || 'Cross failed'
      return null
    }
  }

  async function doExpress(conceptIds: string[]) {
    error.value = ''
    try {
      const res = await api.ecoExpress(conceptIds)
      await _refetch()
      return res.data?.data ?? res.data
    } catch (e: any) {
      error.value = e.message || 'Express failed'
      return null
    }
  }

  async function doTick() {
    error.value = ''
    try {
      const res = await api.ecoTick()
      const d = res.data?.data ?? res.data
      tick.value = d.tick ?? tick.value
      await _refetch()
      return d
    } catch (e: any) {
      error.value = e.message || 'Tick failed'
      return null
    }
  }

  async function fetchInspirations() {
    try {
      const res = await api.ecoInspirations()
      inspirations.value = res.data?.data ?? []
    } catch {
      // silent
    }
  }

  async function doObserve() {
    error.value = ''
    try {
      const res = await api.ecoObserve()
      const d = res.data?.data ?? res.data
      await _refetch()
      return d
    } catch (e: any) {
      error.value = e.message || 'Observe failed'
      return null
    }
  }

  async function doSpeciationScan() {
    error.value = ''
    try {
      const res = await api.ecoSpeciationScan()
      const d = res.data?.data ?? res.data
      await _refetch()
      return d?.events ?? []
    } catch (e: any) {
      error.value = e.message || 'Speciation scan failed'
      return []
    }
  }

  async function doSync() {
    error.value = ''
    try {
      const res = await api.ecoSync()
      const d = res.data?.data ?? res.data
      await _refetch()
      return d
    } catch (e: any) {
      error.value = e.message || 'Sync failed'
      return null
    }
  }

  return {
    concepts, threads, artifacts, inspirations,
    neighborEdges, totalConceptCount, centerConceptId,
    player,
    tick, globalEntropy, era, loading, error,
    fetchState, fetchNeighborhood,
    doRecord, doDive, doCross, doExpress, doObserve,
    doTick, fetchInspirations, doSpeciationScan, doSync,
  }
})
