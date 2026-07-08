import { defineStore } from 'pinia'
import { ref } from 'vue'
import { streamStateRepo } from '../db'

export interface StreamState {
  url: string
  position: number
  duration: number
  updatedAt: number
}

export const useStreamStateStore = defineStore('streamState', () => {
  const states = ref<Record<string, StreamState>>({})

  function load() {
    try {
      const raw = localStorage.getItem('ts2_stream_states')
      if (raw) states.value = JSON.parse(raw)
    } catch { states.value = {} }
  }

  function save() {
    localStorage.setItem('ts2_stream_states', JSON.stringify(states.value))
  }

  async function saveState(url: string, position: number, duration: number) {
    if (!url || position < 0) return
    states.value[url] = { url, position, duration, updatedAt: Date.now() }
    save()
    await streamStateRepo.saveState(url, position, duration)
  }

  function getState(url: string): StreamState | null {
    return states.value[url] || null
  }

  async function getStateAsync(url: string): Promise<StreamState | null> {
    const memo = states.value[url]
    if (memo) return memo
    const db = await streamStateRepo.getByUrl(url)
    if (db) return { url: db.streamUrl, position: db.progressMillis, duration: db.durationSeconds, updatedAt: db.updatedAt }
    return null
  }

  function removeState(url: string) {
    delete states.value[url]
    save()
  }

  function clearStates() {
    states.value = {}
    localStorage.removeItem('ts2_stream_states')
  }

  function isFinished(position: number, duration: number): boolean {
    if (duration <= 0) return false
    const remainingMs = duration * 1000 - position
    return position >= duration * 1000 * 3 / 4 && remainingMs <= 60000
  }

  function shouldSave(position: number, duration: number): boolean {
    if (duration <= 0) return false
    return position >= 5000 || position >= duration * 1000 / 4
  }

  load()

  return { states, saveState, getState, getStateAsync, removeState, clearStates, isFinished, shouldSave }
})
