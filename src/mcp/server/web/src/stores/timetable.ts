import { defineStore } from 'pinia'
import { ref, watch } from 'vue'
import {
  getTimetables, createTimetable, setActiveTimetable, deleteTimetable,
  addTimetableSlot, deleteTimetableSlot,
} from '../api'

export const PERIODS = [
  { name: '早读', start: '06:00', end: '07:00', category: 'morning' },
  { name: '早读', start: '07:00', end: '08:00', category: 'morning' },
  { name: '第1节', start: '08:00', end: '08:45', category: 'morning' },
  { name: '第2节', start: '08:55', end: '09:40', category: 'morning' },
  { name: '第3节', start: '10:00', end: '10:45', category: 'morning' },
  { name: '第4节', start: '10:55', end: '11:40', category: 'morning' },
  { name: '午休', start: '11:40', end: '14:00', category: 'lunch' },
  { name: '第5节', start: '14:00', end: '14:45', category: 'afternoon' },
  { name: '第6节', start: '14:55', end: '15:40', category: 'afternoon' },
  { name: '第7节', start: '16:00', end: '16:45', category: 'afternoon' },
  { name: '第8节', start: '16:55', end: '17:40', category: 'afternoon' },
  { name: '傍晚', start: '17:40', end: '19:00', category: 'evening' },
  { name: '第9节', start: '19:00', end: '19:45', category: 'night' },
  { name: '第10节', start: '19:55', end: '20:40', category: 'night' },
  { name: '晚自习', start: '20:50', end: '22:00', category: 'night' },
  { name: '夜间', start: '22:00', end: '23:00', category: 'night' },
]
export const DAY_NAMES: Record<number, string> = { 1: '周一', 2: '周二', 3: '周三', 4: '周四', 5: '周五', 6: '周六', 7: '周日' }
export const COURSE_COLORS = ['#2563eb', '#059669', '#d97706', '#dc2626', '#7c3aed', '#db2777', '#0891b2', '#65a30d', '#ea580c', '#4f46e5']

export interface TimetableSlotData {
  slot_id: string; _local_id?: string; course_id: string; course_name: string
  day_of_week: number; start_time: string; end_time: string; location: string
  teacher: string; period_idx: number; color: string; teacher_model_prompt?: string
}
export interface TimetableData {
  timetable_id: string; _local_id?: string; name: string
  semester_start: string; semester_end: string; slots: TimetableSlotData[]; enabled: boolean
}

const LOCAL_KEY = 'ts2_timetables_data'
function _genLocalId(): string { return `loc_tt_${Date.now().toString(36)}_${Math.random().toString(36).slice(2, 10)}` }
function _genId(prefix: string) { return `${prefix}_${Date.now()}_${Math.random().toString(36).slice(2, 8)}` }
function _loadLocal(): Record<string, TimetableData> { try { const raw = localStorage.getItem(LOCAL_KEY); return raw ? JSON.parse(raw) : {} } catch { return {} } }
function _saveLocal(data: Record<string, TimetableData>) { localStorage.setItem(LOCAL_KEY, JSON.stringify(data)) }
function _autoColor(map: Record<string, TimetableData>): string {
  const used = new Set(Object.values(map).flatMap(tt => tt.slots.map(s => s.color).filter(Boolean)))
  for (const c of COURSE_COLORS) { if (!used.has(c)) return c }
  return COURSE_COLORS[Object.values(map).reduce((n, tt) => n + tt.slots.length, 0) % COURSE_COLORS.length]
}

export const useTimetableStore = defineStore('timetable', () => {
  const timetables = ref<Record<string, TimetableData>>(_loadLocal())
  const loading = ref(false)
  const source = ref<'local' | 'server'>('local')

  watch(timetables, _saveLocal, { deep: true })

  const activeTimetable = (): TimetableData | null => {
    for (const tt of Object.values(timetables.value)) { if (tt.enabled) return tt }
    const vals = Object.values(timetables.value)
    return vals[0] ?? null
  }

  // ─── source 切换 ──────────────────────────

  function switchToLocal() {
    source.value = 'local'
    timetables.value = _loadLocal()
  }

  async function switchToServer(): Promise<boolean> {
    loading.value = true
    try {
      const res = await getTimetables()
      timetables.value = (res.data?.data ?? res.data ?? {}) as Record<string, TimetableData>
      source.value = 'server'
      _saveLocal(timetables.value)
      loading.value = false
      return true
    } catch { loading.value = false; return false }
  }

  function setTimetables(data: Record<string, TimetableData>) {
    timetables.value = { ...data }
  }

  // ─── CRUD：只操作当前活跃的 source ────────

  async function createTimetableLocal(name: string, semesterStart = '', semesterEnd = ''): Promise<string | null> {
    if (source.value === 'server') {
      try {
        const res = await createTimetable(name, semesterStart, semesterEnd)
        const tt = res.data?.data ?? res.data
        if (tt) {
          timetables.value[tt.timetable_id] = tt
          return tt.timetable_id
        }
      } catch { return null }
      return null
    } else {
      const tid = _genId('tt')
      timetables.value[tid] = { timetable_id: tid, _local_id: _genLocalId(), name, semester_start: semesterStart, semester_end: semesterEnd, slots: [], enabled: Object.keys(timetables.value).length === 0 }
      _saveLocal(timetables.value)
      return tid
    }
  }

  async function switchActive(timetableId: string) {
    for (const tt of Object.values(timetables.value)) tt.enabled = (tt.timetable_id === timetableId)
    if (source.value === 'local') {
      _saveLocal(timetables.value)
    } else {
      try { await setActiveTimetable(timetableId) } catch { /* ignore */ }
    }
  }

  async function removeTimetable(timetableId: string) {
    delete timetables.value[timetableId]
    if (source.value === 'local') {
      _saveLocal(timetables.value)
    } else {
      try { await deleteTimetable(timetableId) } catch { /* ignore */ }
    }
  }

  async function addSlot(data: { timetable_id?: string; course_name: string; day_of_week: number; start_time: string; end_time: string; location?: string; teacher?: string; period_idx?: number; color?: string }) {
    const tt = data.timetable_id && timetables.value[data.timetable_id] ? timetables.value[data.timetable_id] : activeTimetable()
    if (!tt) return
    if (source.value === 'server') {
      try {
        const res = await addTimetableSlot({ ...data, timetable_id: tt.timetable_id })
        const slot = res.data?.data ?? res.data
        if (slot) tt.slots.push(slot)
      } catch { /* ignore */ }
    } else {
      const slot: TimetableSlotData = { slot_id: _genId('slot'), _local_id: _genLocalId(), course_id: data.course_name, course_name: data.course_name, day_of_week: data.day_of_week, start_time: data.start_time, end_time: data.end_time, location: data.location || '', teacher: data.teacher || '', period_idx: data.period_idx || 0, color: data.color || _autoColor(timetables.value) }
      tt.slots.push(slot)
      _saveLocal(timetables.value)
    }
  }

  async function removeSlot(slotId: string) {
    for (const tt of Object.values(timetables.value)) {
      const before = tt.slots.length
      tt.slots = tt.slots.filter(s => s.slot_id !== slotId)
      if (tt.slots.length < before) {
        if (source.value === 'local') _saveLocal(timetables.value)
        else { try { await deleteTimetableSlot(slotId, tt.timetable_id) } catch { /* ignore */ } }
        return
      }
    }
  }

  async function initAutoConnect() {
    loading.value = true
    try {
      const res = await getTimetables()
      timetables.value = (res.data?.data ?? res.data ?? {}) as Record<string, TimetableData>
      source.value = 'server'
      _saveLocal(timetables.value)
    } catch {
      source.value = 'local'
      timetables.value = _loadLocal()
    }
    loading.value = false
  }

  // ─── 显式同步 ──────────────────────────

  async function syncFromServer() {
    loading.value = true
    try {
      const res = await getTimetables()
      const serverData: Record<string, TimetableData> = res.data?.data ?? res.data ?? {}
      const local = _loadLocal()
      const merged: Record<string, TimetableData> = {}
      for (const [tid, stt] of Object.entries(serverData)) {
        const ltt = local[tid]
        if (ltt) {
          merged[tid] = { ...stt, _local_id: ltt._local_id || _genLocalId() }
          const localSlotById = new Map(ltt.slots.filter(s => s._local_id).map(s => [s.slot_id, s]))
          for (const s of merged[tid].slots) { const ls = localSlotById.get(s.slot_id); if (ls?._local_id) s._local_id = ls._local_id; if (!s._local_id) s._local_id = _genLocalId() }
        } else { if (!stt._local_id) stt._local_id = _genLocalId(); merged[tid] = stt }
      }
      for (const [tid, ltt] of Object.entries(local)) { if (!merged[tid]) merged[tid] = ltt }
      _saveLocal(merged)
      if (source.value === 'local') timetables.value = merged
    } catch { /* silent */ }
    loading.value = false
  }

  async function syncToServer() {
    const local = _loadLocal()
    for (const tt of Object.values(local)) {
      try { await createTimetable(tt.name, tt.semester_start, tt.semester_end) } catch { try { await setActiveTimetable(tt.timetable_id) } catch { /* ignore */ } }
      for (const s of tt.slots) {
        try { await addTimetableSlot({ timetable_id: tt.timetable_id, course_name: s.course_name, day_of_week: s.day_of_week, start_time: s.start_time, end_time: s.end_time, location: s.location, teacher: s.teacher, period_idx: s.period_idx, color: s.color }) } catch { /* ignore */ }
      }
    }
  }

  return {
    timetables, loading, source,
    activeTimetable,
    switchToLocal, switchToServer, setTimetables, initAutoConnect,
    createTimetableLocal, switchActive, removeTimetable, addSlot, removeSlot,
    syncFromServer, syncToServer,
  }
})
