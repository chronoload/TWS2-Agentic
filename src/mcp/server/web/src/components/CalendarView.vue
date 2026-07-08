<template>
  <div class="calendar-view">
    <!-- 月份导航 -->
    <div class="calendar-nav">
      <button class="nav-btn" @click="prevMonth">‹</button>
      <span class="nav-title">{{ year }}年{{ month + 1 }}月</span>
      <button class="nav-btn" @click="nextMonth">›</button>
      <button class="nav-btn today-btn" @click="goToday">今天</button>
    </div>

    <!-- 星期头 -->
    <div class="calendar-scroll">
    <div class="calendar-weekdays">
      <div v-for="d in weekdays" :key="d" class="weekday-cell">{{ d }}</div>
    </div>

    <!-- 日期格子 -->
    <div class="calendar-grid">
      <div
        v-for="(day, idx) in calendarDays"
        :key="idx"
        class="day-cell"
        :class="{
          'other-month': !day.isCurrentMonth,
          'is-today': day.isToday,
          'is-selected': day.dateStr === selectedDate,
          'has-tasks': day.tasks.length > 0,
        }"
        @click="selectDay(day)"
      >
        <div class="day-number">{{ day.day }}</div>
        <div class="day-tasks">
          <div
            v-for="task in day.tasks.slice(0, 3)"
            :key="task.id"
            class="day-task-chip"
            :style="chipStyle(task)"
            @click.stop="emit('editTask', task)"
          >
            <span v-if="task.recurrence && task.recurrence !== '不循环'" class="chip-recurrence">🔄</span>
            <span class="chip-title">{{ task.title }}</span>
          </div>
          <div v-if="day.tasks.length > 3" class="day-more">+{{ day.tasks.length - 3 }}</div>
        </div>
      </div>
    </div>
    </div>

    <!-- 选中日期的任务列表 -->
    <div v-if="selectedDate" class="selected-day-panel">
      <div class="panel-header">
        <h3>{{ selectedDate }} 的任务</h3>
        <button class="btn-add-task" @click="emit('addTask', '待办')">＋ 添加</button>
      </div>
      <div class="panel-tasks">
        <div v-if="selectedDayTasks.length === 0" class="panel-empty">暂无任务</div>
        <KanbanCard
          v-for="task in selectedDayTasks"
          :key="task.id"
          :task="task"
          :timer-running="store.isTimerRunning(task.id)"
          :tracked-minutes="store.getTrackedMinutes(task.id)"
          @delete="emit('deleteTask', $event)"
          @edit="emit('editTask', $event)"
          @start-timer="(id) => emit('startTimer', id)"
          @stop-timer="(id) => emit('stopTimer', id)"
          @toggle-subtask="(tId, sId) => emit('toggleSubtask', tId, sId)"
        />
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import { useTasksStore } from '../stores/tasks'
import type { Task } from '../stores/tasks'
import KanbanCard from './KanbanCard.vue'

interface DayCell {
  date: Date
  dateStr: string
  day: number
  isCurrentMonth: boolean
  isToday: boolean
  tasks: Task[]
}

const props = defineProps<{
  tasks: Task[]
  priorityFilter?: string
}>()

const emit = defineEmits<{
  addTask: [status: string]
  deleteTask: [id: string]
  editTask: [task: Task]
  statusChange: [id: string, newStatus: string]
  startTimer: [id: string]
  stopTimer: [id: string]
  toggleSubtask: [taskId: string, subtaskId: string]
}>()

const store = useTasksStore()

const weekdays = ['一', '二', '三', '四', '五', '六', '日']

const now = new Date()
const year = ref(now.getFullYear())
const month = ref(now.getMonth())
const selectedDate = ref<string | null>(formatDate(now))

function formatDate(d: Date): string {
  const y = d.getFullYear()
  const m = String(d.getMonth() + 1).padStart(2, '0')
  const day = String(d.getDate()).padStart(2, '0')
  return `${y}-${m}-${day}`
}

function prevMonth() {
  if (month.value === 0) {
    month.value = 11
    year.value--
  } else {
    month.value--
  }
  selectedDate.value = null
}

function nextMonth() {
  if (month.value === 11) {
    month.value = 0
    year.value++
  } else {
    month.value++
  }
  selectedDate.value = null
}

function goToday() {
  const today = new Date()
  year.value = today.getFullYear()
  month.value = today.getMonth()
  selectedDate.value = formatDate(today)
}

function selectDay(day: DayCell) {
  selectedDate.value = day.dateStr
}

// 过滤任务
const filteredTasks = computed(() => {
  return props.tasks.filter(t => {
    if (t.status === '已完成') return false
    if (props.priorityFilter && t.priority !== props.priorityFilter) return false
    return true
  })
})

// 构建任务日期映射
const tasksByDate = computed(() => {
  const map = new Map<string, Task[]>()
  for (const t of filteredTasks.value) {
    const dateKey = t.due_date || t.start_time?.split('T')[0]
    if (dateKey) {
      if (!map.has(dateKey)) map.set(dateKey, [])
      map.get(dateKey)!.push(t)
    }
  }
  return map
})

// 生成日历格子
const calendarDays = computed<DayCell[]>(() => {
  const days: DayCell[] = []
  const firstDay = new Date(year.value, month.value, 1)
  const lastDay = new Date(year.value, month.value + 1, 0)

  let startDow = firstDay.getDay() - 1
  if (startDow < 0) startDow = 6

  const todayStr = formatDate(new Date())

  // 上月填充
  const prevLastDay = new Date(year.value, month.value, 0).getDate()
  for (let i = startDow - 1; i >= 0; i--) {
    const d = prevLastDay - i
    const date = new Date(year.value, month.value - 1, d)
    const dateStr = formatDate(date)
    days.push({
      date,
      dateStr,
      day: d,
      isCurrentMonth: false,
      isToday: dateStr === todayStr,
      tasks: tasksByDate.value.get(dateStr) || [],
    })
  }

  // 本月
  for (let d = 1; d <= lastDay.getDate(); d++) {
    const date = new Date(year.value, month.value, d)
    const dateStr = formatDate(date)
    days.push({
      date,
      dateStr,
      day: d,
      isCurrentMonth: true,
      isToday: dateStr === todayStr,
      tasks: tasksByDate.value.get(dateStr) || [],
    })
  }

  // 下月填充
  const remaining = 42 - days.length
  for (let d = 1; d <= remaining; d++) {
    const date = new Date(year.value, month.value + 1, d)
    const dateStr = formatDate(date)
    days.push({
      date,
      dateStr,
      day: d,
      isCurrentMonth: false,
      isToday: dateStr === todayStr,
      tasks: tasksByDate.value.get(dateStr) || [],
    })
  }

  return days
})

// 选中日期的任务
const selectedDayTasks = computed(() => {
  if (!selectedDate.value) return []
  return filteredTasks.value.filter(t => {
    const dateKey = t.due_date || t.start_time?.split('T')[0]
    return dateKey === selectedDate.value
  })
})

function chipStyle(task: Task) {
  const bg = task.color || 'rgba(59,130,246,0.2)'
  return { background: bg, color: '#fff' }
}
</script>

<style scoped>
.calendar-view {
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 12px;
  height: calc(100vh - 160px);
  overflow-y: auto;
}

.calendar-nav {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 4px 0;
}

.nav-btn {
  background: rgba(255, 255, 255, 0.06);
  border: 1px solid var(--border);
  color: var(--fg);
  border-radius: 6px;
  padding: 4px 10px;
  font-size: 16px;
  cursor: pointer;
  transition: background 0.15s;
}

.nav-btn:hover {
  background: rgba(122, 162, 247, 0.15);
}

.nav-title {
  font-size: 16px;
  font-weight: 600;
  color: var(--fg);
  min-width: 120px;
  text-align: center;
}

.today-btn {
  font-size: 12px;
  padding: 4px 12px;
  margin-left: auto;
}

.calendar-weekdays {
  display: grid;
  grid-template-columns: repeat(7, minmax(100px, 1fr));
  gap: 1px;
  min-width: 700px;
}

.weekday-cell {
  text-align: center;
  font-size: 12px;
  font-weight: 600;
  color: var(--fg-muted);
  padding: 6px 0;
  background: var(--bg-secondary);
  border-radius: 4px 4px 0 0;
}

.calendar-scroll {
  overflow-x: auto;
  -webkit-overflow-scrolling: touch;
  border-radius: 8px;
}

.calendar-grid {
  display: grid;
  grid-template-columns: repeat(7, minmax(100px, 1fr));
  gap: 1px;
  background: var(--border);
  border-radius: 8px;
  overflow: hidden;
  min-width: 700px;
}

.day-cell {
  background: var(--bg);
  min-height: 80px;
  padding: 4px;
  cursor: pointer;
  transition: background 0.15s;
  display: flex;
  flex-direction: column;
  min-width: 0;
}

.day-cell:hover {
  background: rgba(122, 162, 247, 0.06);
}

.day-cell.other-month {
  opacity: 0.35;
}

.day-cell.is-today .day-number {
  background: var(--accent);
  color: var(--bg);
  border-radius: 50%;
  width: 22px;
  height: 22px;
  display: flex;
  align-items: center;
  justify-content: center;
}

.day-cell.is-selected {
  background: rgba(122, 162, 247, 0.1);
  outline: 2px solid var(--accent);
  outline-offset: -2px;
}

.day-number {
  font-size: 12px;
  font-weight: 600;
  color: var(--fg);
  margin-bottom: 2px;
}

.day-tasks {
  display: flex;
  flex-direction: column;
  gap: 2px;
  flex: 1;
  overflow: hidden;
  min-width: 0;
}

.day-task-chip {
  display: flex;
  align-items: center;
  gap: 2px;
  padding: 1px 6px;
  border-radius: 3px;
  font-size: 10px;
  line-height: 1.5;
  white-space: nowrap;
  overflow: hidden;
  cursor: pointer;
  transition: opacity 0.15s;
}

.day-task-chip:hover {
  opacity: 0.85;
}

.chip-recurrence {
  font-size: 9px;
  flex-shrink: 0;
}

.chip-title {
  overflow: hidden;
  text-overflow: ellipsis;
}

.day-more {
  font-size: 10px;
  color: var(--fg-muted);
  padding-left: 4px;
}

.selected-day-panel {
  background: var(--bg-secondary);
  border: 1px solid var(--border);
  border-radius: 10px;
  padding: 12px;
  margin-top: 4px;
}

.panel-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 10px;
}

.panel-header h3 {
  font-size: 14px;
  font-weight: 600;
  color: var(--fg);
}

.btn-add-task {
  background: var(--accent);
  color: var(--bg);
  border: none;
  padding: 4px 12px;
  border-radius: 6px;
  font-size: 12px;
  font-weight: 600;
  cursor: pointer;
}

.btn-add-task:hover { opacity: 0.9; }

.panel-tasks {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.panel-empty {
  text-align: center;
  color: var(--fg-muted);
  font-size: 13px;
  padding: 16px 0;
  opacity: 0.6;
}

@media (max-width: 768px) {
  .day-cell { min-height: 60px; }
  .day-task-chip { font-size: 9px; }
  .calendar-view { height: auto; }
}
</style>
