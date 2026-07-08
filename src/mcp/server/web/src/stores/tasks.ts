import { defineStore } from 'pinia'
import { ref, watch } from 'vue'
import { getTasks, createTask, updateTask, deleteTask, syncFull } from '../api'
import { isNativeApp } from '../api'
import { useSpacesStore } from './spaces'

let _CapLocalNotifications: any = null
async function _getCapNotif() {
  if (_CapLocalNotifications === null) {
    try {
      const cap = await import('@capacitor/core')
      if (!cap.Capacitor.isNativePlatform()) { _CapLocalNotifications = false; return false }
      const mod = await import('@capacitor/local-notifications')
      _CapLocalNotifications = mod.LocalNotifications
    } catch { _CapLocalNotifications = false }
  }
  return _CapLocalNotifications
}
function _isNativeCap(): boolean {
  return isNativeApp() && !!_CapLocalNotifications
}

export interface SubTask { id: string; title: string; done: boolean }
export interface TimeLog { start: number; end?: number }
export interface Task {
  id: string; _local_id?: string; space_id: string
  title: string; description?: string; status: string; priority?: string
  due_date?: string; start_time?: string; duration?: number
  recurrence?: string; recurrence_rule?: string; tags?: string[]
  subtasks?: SubTask[]; time_logs?: TimeLog[]; reminder?: string
  color?: string; sort_order?: number; created_at?: string; updated_at?: string
}

const LOCAL_KEY = 'ts2_tasks_data'
function _genLocalId(): string { return `loc_${Date.now().toString(36)}_${Math.random().toString(36).slice(2, 10)}` }
function _loadAllLocal(): Record<string, Task[]> {
  try { const raw = localStorage.getItem(LOCAL_KEY); return raw ? JSON.parse(raw) : {} } catch { return {} }
}
function _saveAllLocal(data: Record<string, Task[]>) { localStorage.setItem(LOCAL_KEY, JSON.stringify(data)) }

// 服务端 API 接受的字段 — 只传这些，其余本地字段前端自己维护
const API_TASK_FIELDS = ['title', 'description', 'due_date', 'priority', 'status', 'start_time', 'duration', 'recurrence'] as const
function _apiTask(data: Record<string, unknown>): Record<string, unknown> {
  const out: Record<string, unknown> = {}
  for (const k of API_TASK_FIELDS) { if (k in data) out[k] = data[k] }
  return out
}

export const useTasksStore = defineStore('tasks', () => {
  const bySpace = ref<Record<string, Task[]>>(_loadAllLocal())
  const loading = ref(false)
  const source = ref<'local' | 'server'>('local')
  const timerTick = ref(Date.now())
  let timerInterval: ReturnType<typeof setInterval> | null = null

  watch(bySpace, _saveAllLocal, { deep: true })

  const _runningTimers = _loadRunningTimers()
  // 恢复页面刷新前的运行中计时器
  restoreRunningTimers()

  function tasksFor(spaceId: string): Task[] { return bySpace.value[spaceId] ?? [] }
  function _saveForSpace(spaceId: string, t: Task[]) { bySpace.value = { ...bySpace.value, [spaceId]: t } }
  function setTasks(tasks: Task[]) {
    const byS: Record<string, Task[]> = {}
    for (const t of tasks) { const sid = t.space_id || 'default'; if (!byS[sid]) byS[sid] = []; byS[sid].push(t) }
    bySpace.value = { ...bySpace.value, ...byS }
  }

  // ─── source 切换 ──────────────────────────

  function switchToLocal() {
    source.value = 'local'
    bySpace.value = _loadAllLocal()
  }

  async function switchToServer(): Promise<boolean> {
    loading.value = true
    try {
      const res = await getTasks()
      const serverTasks: Task[] = res.data?.data ?? res.data ?? []
      const ss = useSpacesStore()
      const byS: Record<string, Task[]> = {}
      for (const t of serverTasks) {
        const sid = t.space_id || ss.defaultSpace.id
        if (!byS[sid]) byS[sid] = []
        if (!t._local_id) t._local_id = _genLocalId()
        byS[sid].push(t)
      }
      source.value = 'server'
      bySpace.value = byS
      _saveAllLocal(byS)
      loading.value = false
      return true
    } catch { loading.value = false; return false }
  }

  // ─── CRUD：只操作当前活跃的 source ────────

  async function addTask(spaceId: string, data: Record<string, unknown>) {
    if (source.value === 'server') {
      try {
        const res = await createTask(_apiTask(data))
        const serverTask = res.data?.data ?? res.data
        if (serverTask) {
          const merged = { ...serverTask, space_id: spaceId, _local_id: _genLocalId(), subtasks: data.subtasks || [], time_logs: data.time_logs || [], tags: data.tags || [], color: data.color || '', reminder: data.reminder || '', sort_order: data.sort_order || 0 } as Task
          const list = [...(bySpace.value[spaceId] ?? []), merged]
          _saveForSpace(spaceId, list)
          return merged
        }
      } catch { return null }
      return null
    } else {
      const now = new Date().toISOString()
      const newTask: Task = {
        id: `local_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`,
        _local_id: _genLocalId(), space_id: spaceId,
        title: data.title as string, description: data.description as string || '',
        status: data.status as string || '待办', priority: data.priority as string || '中',
        due_date: data.due_date as string || '', start_time: data.start_time as string || '',
        duration: data.duration as number || 60, recurrence: data.recurrence as string || '不循环',
        tags: data.tags as string[] || [], subtasks: data.subtasks as SubTask[] || [],
        time_logs: [], reminder: data.reminder as string || '', color: data.color as string || '',
        sort_order: data.sort_order as number || 0, created_at: now, updated_at: now,
      }
      const current = [...(bySpace.value[spaceId] ?? []), newTask]
      _saveForSpace(spaceId, current)
      return newTask
    }
  }

  async function editTask(id: string, data: Record<string, unknown>) {
    for (const [sid, list] of Object.entries(bySpace.value)) {
      const idx = list.findIndex(t => t.id === id)
      if (idx === -1) continue
      const old = list[idx]
      list[idx] = { ...old, ...data, updated_at: new Date().toISOString() }
      _saveForSpace(sid, list)
      if (source.value === 'server') {
        try { await updateTask(id, _apiTask(data)) } catch { /* ignore */ }
      }
      if (data.reminder !== undefined && data.reminder !== old.reminder) {
        if (old.reminder) cancelNativeReminder(id)
        scheduleNativeReminders()
      }
      return
    }
  }

  async function removeTask(id: string) {
    for (const [sid, list] of Object.entries(bySpace.value)) {
      if (!list.find(t => t.id === id)) continue
      _saveForSpace(sid, list.filter(t => t.id !== id))
      cancelNativeReminder(id)
      if (source.value === 'server') {
        try { await deleteTask(id) } catch { /* ignore */ }
      }
      return
    }
  }

  async function toggleSubtask(taskId: string, subtaskId: string) {
    for (const [sid, list] of Object.entries(bySpace.value)) {
      const task = list.find(t => t.id === taskId)
      if (!task?.subtasks) continue
      const sub = task.subtasks.find(s => s.id === subtaskId)
      if (!sub) return
      sub.done = !sub.done; task.updated_at = new Date().toISOString()
      if (task.subtasks.every(s => s.done)) task.status = '已完成'
      _saveForSpace(sid, list)
      if (source.value === 'server') {
        try { await updateTask(taskId, { status: task.status } as any) } catch { /* ignore */ }
      }
      return
    }
  }

  function addSubtask(taskId: string, title: string) {
    for (const list of Object.values(bySpace.value)) { const task = list.find(t => t.id === taskId); if (!task) continue; if (!task.subtasks) task.subtasks = []; task.subtasks.push({ id: `sub_${Date.now()}`, title, done: false }); task.updated_at = new Date().toISOString() }
  }
  function removeSubtask(taskId: string, subtaskId: string) {
    for (const list of Object.values(bySpace.value)) { const task = list.find(t => t.id === taskId); if (!task?.subtasks) continue; task.subtasks = task.subtasks.filter(s => s.id !== subtaskId); task.updated_at = new Date().toISOString() }
  }

  // ─── 计时 ────────────────────────────────

  const RUNNING_TIMER_KEY = 'ts2_running_timer'

  function _loadRunningTimers(): Set<string> {
    try { const raw = localStorage.getItem(RUNNING_TIMER_KEY); return new Set(raw ? JSON.parse(raw) : []) } catch { return new Set() }
  }
  function _saveRunningTimers(set: Set<string>) { localStorage.setItem(RUNNING_TIMER_KEY, JSON.stringify([...set])) }

  function startTimer(taskId: string) {
    // 停止其他运行中的计时器
    for (const runningId of _runningTimers) {
      if (runningId !== taskId) stopTimer(runningId)
    }
    for (const list of Object.values(bySpace.value)) {
      const task = list.find(t => t.id === taskId)
      if (!task) continue
      if (!task.time_logs) task.time_logs = []
      const running = task.time_logs.find(l => !l.end)
      if (running) running.end = Date.now()
      task.time_logs.push({ start: Date.now() })
      task.status = '进行中'
      task.updated_at = new Date().toISOString()
      _runningTimers.add(taskId)
      _saveRunningTimers(_runningTimers)
      ensureTimerTick()
      return
    }
  }
  function stopTimer(taskId: string) {
    for (const list of Object.values(bySpace.value)) {
      const task = list.find(t => t.id === taskId)
      if (!task?.time_logs) continue
      const running = task.time_logs.find(l => !l.end)
      if (running) {
        running.end = Date.now()
        task.updated_at = new Date().toISOString()
      }
    }
    _runningTimers.delete(taskId)
    _saveRunningTimers(_runningTimers)
    if (_runningTimers.size === 0) {
      if (timerInterval) { clearInterval(timerInterval); timerInterval = null }
    }
  }
  function ensureTimerTick() {
    if (timerInterval) return
    timerInterval = setInterval(() => { timerTick.value = Date.now() }, 1000)
  }
  // 页面加载时恢复所有运行中的计时器
  function restoreRunningTimers() {
    if (_runningTimers.size > 0) ensureTimerTick()
  }

  // ─── 提醒 ────────────────────────────────

  const REMINDER_FIRED_KEY = 'ts2_reminders_fired'
  function loadFiredReminders(): Set<string> { try { const raw = localStorage.getItem(REMINDER_FIRED_KEY); return new Set(raw ? JSON.parse(raw) : []) } catch { return new Set() } }
  function saveFiredReminders(set: Set<string>) { localStorage.setItem(REMINDER_FIRED_KEY, JSON.stringify([...set])) }
  let _notifIdCounter = 1000
  function _taskNotifId(taskId: string): number { let hash = 0; for (let i = 0; i < taskId.length; i++) { hash = ((hash << 5) - hash) + taskId.charCodeAt(i); hash |= 0 }; return Math.abs(hash) % 10000 + 1000 }

  async function scheduleNativeReminders() {
    const notif = await _getCapNotif(); if (!notif) return
    try { const pending = await notif.getPending(); for (const n of pending.notifications) await notif.cancel({ notifications: [{ id: n.id }] }) } catch { /* ignore */ }
    const fired = loadFiredReminders()
    for (const list of Object.values(bySpace.value)) { for (const task of list) { if (!task.reminder || task.status === '已完成') continue; const reminderTs = new Date(task.reminder).getTime(); if (isNaN(reminderTs) || reminderTs <= Date.now()) continue; const key = `${task.id}_${task.reminder}`; if (fired.has(key)) continue; try { await notif.schedule({ notifications: [{ title: '⏰ 任务提醒', body: task.title, id: _taskNotifId(task.id), schedule: { at: new Date(task.reminder) }, sound: 'default' }] }) } catch { /* skip */ } } }
    try { await notif.requestPermissions() } catch { /* ignore */ }
  }
  async function cancelNativeReminder(taskId: string) { const notif = await _getCapNotif(); if (!notif) return; try { await notif.cancel({ notifications: [{ id: _taskNotifId(taskId) }] }) } catch { /* ignore */ } }

  function checkReminders() {
    const fired = loadFiredReminders(); const now = Date.now(); let changed = false
    for (const list of Object.values(bySpace.value)) { for (const task of list) { if (!task.reminder || task.status === '已完成') continue; const reminderTs = new Date(task.reminder).getTime(); if (isNaN(reminderTs)) continue; const key = `${task.id}_${task.reminder}`; if (fired.has(key)) continue; if (reminderTs <= now && now - reminderTs < 120000) { fired.add(key); changed = true; if (_isNativeCap()) _getCapNotif().then(notif => { if (notif) notif.schedule({ notifications: [{ title: '⏰ 任务提醒', body: task.title, id: _notifIdCounter++, sound: 'default' }] }).catch(() => {}) }); if (typeof Notification !== 'undefined' && Notification.permission === 'granted') new Notification('任务提醒', { body: task.title, icon: '/favicon.svg' }); window.dispatchEvent(new CustomEvent('ts2-reminder', { detail: { id: task.id, title: task.title, reminder: task.reminder } })) } } }
    if (changed) saveFiredReminders(fired)
  }
  async function requestNotifyPermission() { if (_isNativeCap()) { const notif = await _getCapNotif(); if (notif) { try { await notif.requestPermissions() } catch { /* ignore */ } } } else if (typeof Notification !== 'undefined' && Notification.permission === 'default') Notification.requestPermission() }

  function getTrackedMinutes(taskId: string): number { void timerTick.value; for (const list of Object.values(bySpace.value)) { const task = list.find(t => t.id === taskId); if (!task?.time_logs) continue; return task.time_logs.reduce((sum, l) => { const end = l.end || Date.now(); return sum + Math.round((end - l.start) / 60000) }, 0) }; return 0 }
  function isTimerRunning(taskId: string): boolean { void timerTick.value; return Object.values(bySpace.value).some(list => list.some(t => t.id === taskId && t.time_logs?.some(l => !l.end))) }

  function completeRecurring(taskId: string) {
    for (const [spaceId, list] of Object.entries(bySpace.value)) {
      const task = list.find(t => t.id === taskId)
      if (!task || task.recurrence === '不循环') return
      task.status = '已完成'
      task.updated_at = new Date().toISOString()
      const nextDate = getNextRecurrenceDate(task.due_date || '', task.recurrence || '不循环', task.recurrence_rule)
      if (nextDate) {
        const newTaskData = {
          title: task.title!,
          description: task.description,
          status: '待办',
          priority: task.priority,
          due_date: nextDate,
          start_time: '',
          duration: task.duration,
          recurrence: task.recurrence,
          recurrence_rule: task.recurrence_rule,
          tags: task.tags ? [...task.tags] : [],
          subtasks: task.subtasks?.map(s => ({ ...s, done: false })) || [],
          color: task.color,
        }
        addTask(spaceId, newTaskData)
      }
    }
  }
  function getNextRecurrenceDate(currentDate: string, recurrence: string, _rule?: string): string | null { if (!currentDate || recurrence === '不循环') return null; const d = new Date(currentDate); switch (recurrence) { case '每天': d.setDate(d.getDate() + 1); break; case '每周': d.setDate(d.getDate() + 7); break; case '每月': d.setMonth(d.getMonth() + 1); break; case '工作日': { d.setDate(d.getDate() + 1); while (d.getDay() === 0 || d.getDay() === 6) d.setDate(d.getDate() + 1); break } default: return null }; return d.toISOString().split('T')[0] }

  function getStats(spaceId: string) { const list = bySpace.value[spaceId] ?? []; const total = list.length; const done = list.filter(t => t.status === '已完成').length; const overdue = list.filter(t => { if (t.status === '已完成' || !t.due_date) return false; return new Date(t.due_date) < new Date(new Date().toISOString().split('T')[0]) }).length; const todayDue = list.filter(t => { if (t.status === '已完成' || !t.due_date) return false; return t.due_date === new Date().toISOString().split('T')[0] }).length; return { total, done, overdue, todayDue, totalTracked: list.reduce((sum, t) => sum + getTrackedMinutes(t.id), 0) } }

  // 显式同步 ──────────────────────────

  async function syncFromServer() {
    loading.value = true
    try {
      const res = await getTasks()
      const serverTasks: Task[] = res.data?.data ?? res.data ?? []
      const ss = useSpacesStore()
      const local = _loadAllLocal()
      const merged: Record<string, Task[]> = {}
      for (const space of ss.spaces) {
        const filtered = serverTasks.filter(t => t.space_id === space.id)
        if (!filtered.length) continue
        const localList = local[space.id] ?? []
        const localById = new Map(localList.map(t => [t._local_id || t.id, t]))
        const seen = new Set<string>()
        merged[space.id] = []
        for (const st of filtered) {
          const key = st._local_id || st.id; const lm = localById.get(key)
          if (lm) { merged[space.id].push({ ...st, _local_id: lm._local_id, subtasks: lm.subtasks || st.subtasks, time_logs: lm.time_logs || st.time_logs, tags: lm.tags || st.tags }) } else { if (!st._local_id) st._local_id = _genLocalId(); merged[space.id].push(st) }
          seen.add(key)
        }
        for (const lt of localList) { if (!seen.has(lt._local_id || lt.id)) merged[space.id].push(lt) }
      }
      const orphans = serverTasks.filter(t => !t.space_id); const defId = ss.defaultSpace.id
      if (orphans.length > 0) { const localList = local[defId] ?? []; const seen = new Set(localList.map(t => t._local_id || t.id)); merged[defId] = [...localList]; for (const st of orphans) { if (!st._local_id) st._local_id = _genLocalId(); if (!seen.has(st._local_id)) { st.space_id = defId; merged[defId].push(st) } } }
      _saveAllLocal(merged)
      if (source.value === 'local') bySpace.value = merged
    } catch { /* silent */ }
    loading.value = false
  }

  async function syncToServer() {
    let pushed = 0
    const allTasks = _loadAllLocal()
    for (const [, list] of Object.entries(allTasks)) {
      for (const task of list) {
        try { await createTask(_apiTask(task as any)); pushed++ }
        catch { try { await updateTask(task.id, _apiTask(task as any)); pushed++ } catch { /* skip */ } }
      }
    }
    return { pushed }
  }

  async function syncWithServer(bookmarks: any[] = [], projects: any[] = []) {
    const allTasks = Object.values(bySpace.value).flat()
    const res = await syncFull(allTasks, bookmarks, projects)
    const data = res.data?.data ?? res.data
    if (data?.tasks?.server_data) {
      const serverTasks: Task[] = data.tasks.server_data
      const byS: Record<string, Task[]> = {}
      for (const t of serverTasks) { const sid = t.space_id || 'default'; if (!byS[sid]) byS[sid] = []; const lm = Object.values(bySpace.value).flat().find(lt => lt._local_id && lt._local_id === t._local_id); byS[sid].push(lm ? { ...t, _local_id: lm._local_id } : t) }
      for (const [sid, localList] of Object.entries(bySpace.value)) { if (!byS[sid]) byS[sid] = []; const serverKeys = new Set(byS[sid].map(t => t._local_id || t.id)); for (const lt of localList) { if (!serverKeys.has(lt._local_id || lt.id)) byS[sid].push(lt) } }
      bySpace.value = byS
    }
    return { pull: data?.tasks?.pull?.length ?? 0, pushed: data?.tasks?.pushed ?? 0, conflicts: data?.tasks?.conflicts?.length ?? 0, bookmarksPull: data?.bookmarks?.pull?.length ?? 0, bookmarksPushed: data?.bookmarks?.pushed ?? 0, projectsPull: data?.projects?.pull?.length ?? 0, projectsPushed: data?.projects?.pushed ?? 0 }
  }

  return {
    bySpace, loading, source, timerTick,
    tasksFor, setTasks, switchToServer, switchToLocal,
    addTask, editTask, removeTask, toggleSubtask, addSubtask, removeSubtask,
    startTimer, stopTimer, getTrackedMinutes, isTimerRunning, restoreRunningTimers,
    completeRecurring, getNextRecurrenceDate, getStats,
    checkReminders, requestNotifyPermission, scheduleNativeReminders, cancelNativeReminder,
    syncFromServer, syncToServer, syncWithServer,
  }
})
