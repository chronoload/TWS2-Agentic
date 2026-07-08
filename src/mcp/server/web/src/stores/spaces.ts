import { defineStore } from 'pinia'
import { ref, computed, watch } from 'vue'

export interface Space {
  id: string
  _local_id: string
  name: string
  created_at: number
  updated_at: number
}

const LOCAL_SPACES_KEY = 'ts2_spaces'
const LOCAL_IDS_KEY = 'ts2_space_local_ids'
const TIMETABLE_MAP_KEY = 'ts2_space_timetable_map'

function _genId(): string {
  return `sp_${Date.now().toString(36)}_${Math.random().toString(36).slice(2, 10)}`
}
function _genLocalId(): string {
  return `loc_sp_${Date.now().toString(36)}_${Math.random().toString(36).slice(2, 10)}`
}
function _loadSpaces(): Space[] {
  try { const raw = localStorage.getItem(LOCAL_SPACES_KEY); return raw ? JSON.parse(raw) : [] } catch { return [] }
}
function _saveSpaces(spaces: Space[]) { localStorage.setItem(LOCAL_SPACES_KEY, JSON.stringify(spaces)) }
function _loadLocalIds(): Set<string> {
  try { const raw = localStorage.getItem(LOCAL_IDS_KEY); return new Set(raw ? JSON.parse(raw) : []) } catch { return new Set() }
}
function _saveLocalIds(set: Set<string>) { localStorage.setItem(LOCAL_IDS_KEY, JSON.stringify([...set])) }
function _loadTimetableMap(): Record<string, string> {
  try { const raw = localStorage.getItem(TIMETABLE_MAP_KEY); return raw ? JSON.parse(raw) : {} } catch { return {} }
}
function _saveTimetableMap(m: Record<string, string>) { localStorage.setItem(TIMETABLE_MAP_KEY, JSON.stringify(m)) }

export const useSpacesStore = defineStore('spaces', () => {
  const spaces = ref<Space[]>(_loadSpaces())
  const activeSpaceId = ref<string | null>(null)
  const showManager = ref(false)
  const spaceTimetableMap = ref<Record<string, string>>(_loadTimetableMap())

  const activeSpace = computed<Space | null>(() => {
    if (!activeSpaceId.value) return null
    return spaces.value.find(s => s.id === activeSpaceId.value) ?? null
  })

  const defaultSpace = computed<Space>(() => {
    let d = spaces.value.find(s => s.name === '默认空间')
    if (!d && spaces.value.length > 0) d = spaces.value[0]
    if (!d) {
      d = { id: _genId(), _local_id: _genLocalId(), name: '默认空间', created_at: Date.now(), updated_at: Date.now() }
      spaces.value.push(d)
      _saveSpaces(spaces.value)
    }
    return d
  })

  if (!activeSpaceId.value && !localStorage.getItem('ts2_selected_space')) {
    activeSpaceId.value = defaultSpace.value.id
  } else {
    const saved = localStorage.getItem('ts2_selected_space')
    if (saved && spaces.value.some(s => s.id === saved)) {
      activeSpaceId.value = saved
    }
  }

  watch(spaces, _saveSpaces, { deep: true })
  watch(activeSpaceId, (id) => { if (id) localStorage.setItem('ts2_selected_space', id) })
  watch(spaceTimetableMap, _saveTimetableMap, { deep: true })

  function selectSpace(id: string) { activeSpaceId.value = id }
  function addSpace(name: string): Space {
    const newSpace: Space = { id: _genId(), _local_id: _genLocalId(), name, created_at: Date.now(), updated_at: Date.now() }
    spaces.value.push(newSpace)
    const localIds = _loadLocalIds()
    localIds.add(newSpace._local_id)
    _saveLocalIds(localIds)
    activeSpaceId.value = newSpace.id
    return newSpace
  }
  function removeSpace(id: string) {
    const space = spaces.value.find(s => s.id === id)
    if (!space) return
    spaces.value = spaces.value.filter(s => s.id !== id)
    const localIds = _loadLocalIds()
    localIds.delete(space._local_id)
    _saveLocalIds(localIds)
    delete spaceTimetableMap.value[id]
    if (activeSpaceId.value === id) {
      activeSpaceId.value = spaces.value.length > 0 ? spaces.value[0].id : null
    }
  }
  function renameSpace(id: string, name: string) {
    const space = spaces.value.find(s => s.id === id)
    if (space) { space.name = name; space.updated_at = Date.now() }
  }

  // 空间 ↔ 课程表映射（纯本地，不上传服务端）
  function setTimetableForSpace(spaceId: string, timetableId: string) {
    spaceTimetableMap.value[spaceId] = timetableId
  }
  function timetableForSpace(spaceId: string): string | undefined {
    return spaceTimetableMap.value[spaceId]
  }

  return {
    spaces, activeSpaceId, activeSpace, defaultSpace, showManager, spaceTimetableMap,
    selectSpace, addSpace, removeSpace, renameSpace, toggleManager: () => { showManager.value = !showManager.value },
    setTimetableForSpace, timetableForSpace,
  }
})
