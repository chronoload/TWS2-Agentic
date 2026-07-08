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
