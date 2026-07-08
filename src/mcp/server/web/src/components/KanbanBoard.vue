<template>
  <div class="kanban-board" @touchstart="onTouchStart" @touchmove.prevent="onTouchMove" @touchend="onTouchEnd">
    <div
      v-for="col in columns"
      :key="col.status"
      class="kanban-column"
      :class="{ 'drag-over': dragOverCol === col.status }"
      :data-status="col.status"
      @dragover.prevent="onDragOver($event, col.status)"
      @dragleave="onDragLeave"
      @drop="onDrop($event, col.status)"
    >
      <div class="column-header">
        <h2 class="column-title">
          <span class="column-dot" :style="{ background: col.color }"></span>
          {{ col.label }}
          <span class="column-count">{{ filteredTasks(col.status).length }}</span>
        </h2>
        <button class="btn-add" @click="emit('addTask', col.status)">＋</button>
      </div>
      <div class="column-body">
        <KanbanCard
          v-for="task in filteredTasks(col.status)"
          :key="task.id"
          :task="task"
          :timer-running="store.isTimerRunning(task.id)"
          :tracked-minutes="store.getTrackedMinutes(task.id)"
          draggable="true"
          @delete="emit('deleteTask', $event)"
          @edit="emit('editTask', $event)"
          @start-timer="(id) => emit('startTimer', id)"
          @stop-timer="(id) => emit('stopTimer', id)"
          @toggle-subtask="(tId, sId) => emit('toggleSubtask', tId, sId)"
        />
        <div v-if="filteredTasks(col.status).length === 0" class="column-empty">
          暂无任务
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { useTasksStore } from '../stores/tasks'
import type { Task } from '../stores/tasks'
import KanbanCard from './KanbanCard.vue'

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

const columns = [
  { status: '待办', label: '待办', color: 'var(--accent)' },
  { status: '进行中', label: '进行中', color: 'var(--warning)' },
  { status: '已完成', label: '已完成', color: 'var(--success)' },
]

const dragOverCol = ref<string | null>(null)
let dragLeaveTimer: ReturnType<typeof setTimeout> | null = null

function filteredTasks(status: string) {
  const priorityOrder: Record<string, number> = { '高': 0, '中': 1, '低': 2 }
  return props.tasks
    .filter((t) => t.status === status && (!props.priorityFilter || t.priority === props.priorityFilter))
    .sort((a, b) => {
      // 逾期排最前
      const aOverdue = a.due_date && a.status !== '已完成' && new Date(a.due_date) < new Date(new Date().toISOString().split('T')[0]) ? 0 : 1
      const bOverdue = b.due_date && b.status !== '已完成' && new Date(b.due_date) < new Date(new Date().toISOString().split('T')[0]) ? 0 : 1
      if (aOverdue !== bOverdue) return aOverdue - bOverdue
      // 按优先级排序
      const pa = priorityOrder[a.priority || '中'] ?? 1
      const pb = priorityOrder[b.priority || '中'] ?? 1
      if (pa !== pb) return pa - pb
      // 按截止日期排序
      if (a.due_date && b.due_date) return a.due_date.localeCompare(b.due_date)
      if (a.due_date) return -1
      if (b.due_date) return 1
      return 0
    })
}

function onDragOver(e: DragEvent, status: string) {
  if (e.dataTransfer) {
    e.dataTransfer.dropEffect = 'move'
  }
  // 清除延迟重置，保持高亮
  if (dragLeaveTimer) {
    clearTimeout(dragLeaveTimer)
    dragLeaveTimer = null
  }
  dragOverCol.value = status
}

function onDragLeave() {
  // 延迟重置，避免在子元素间移动时闪烁
  if (dragLeaveTimer) clearTimeout(dragLeaveTimer)
  dragLeaveTimer = setTimeout(() => {
    dragOverCol.value = null
  }, 50)
}

function onDrop(e: DragEvent, newStatus: string) {
  dragOverCol.value = null
  if (dragLeaveTimer) {
    clearTimeout(dragLeaveTimer)
    dragLeaveTimer = null
  }
  const taskId = e.dataTransfer?.getData('text/plain')
  if (taskId) {
    emit('statusChange', taskId, newStatus)
  }
}

// ─── Touch / 移动端拖动（长按300ms触发） ─────────────────

const touchDragTaskId = ref<string | null>(null)
let touchDragGhost: HTMLElement | null = null
let longPressTimer: ReturnType<typeof setTimeout> | null = null
let touchStartPos: { x: number; y: number } | null = null
const LONG_PRESS_MS = 300
const MOVE_THRESHOLD = 10

function _startDrag(card: HTMLElement, taskId: string, touch: Touch) {
  touchDragTaskId.value = taskId
  card.classList.add('dragging')
  const ghost = card.cloneNode(true) as HTMLElement
  ghost.classList.add('drag-ghost')
  ghost.style.position = 'fixed'
  ghost.style.width = card.offsetWidth + 'px'
  ghost.style.pointerEvents = 'none'
  ghost.style.zIndex = '1000'
  ghost.style.opacity = '0.8'
  ghost.style.transform = 'rotate(3deg)'
  ghost.style.left = touch.clientX - card.offsetWidth / 2 + 'px'
  ghost.style.top = touch.clientY - 40 + 'px'
  document.body.appendChild(ghost)
  touchDragGhost = ghost
}

function onTouchStart(e: TouchEvent) {
  const target = e.target as HTMLElement
  const card = target.closest('[data-task-id]') as HTMLElement | null
  if (!card || target.closest('button, input, label, select, textarea')) return
  const taskId = card.dataset.taskId
  if (!taskId) return
  const touch = e.touches[0]
  touchStartPos = { x: touch.clientX, y: touch.clientY }
  // 设置长按定时器
  longPressTimer = setTimeout(() => {
    _startDrag(card, taskId, touch)
    longPressTimer = null
  }, LONG_PRESS_MS)
}

function onTouchMove(e: TouchEvent) {
  if (touchDragTaskId.value && touchDragGhost) {
    // 拖动中
    const touch = e.touches[0]
    touchDragGhost.style.left = touch.clientX - touchDragGhost.offsetWidth / 2 + 'px'
    touchDragGhost.style.top = touch.clientY - 40 + 'px'
    const el = document.elementFromPoint(touch.clientX, touch.clientY)
    if (el) {
      const column = el.closest('[data-status]') as HTMLElement | null
      dragOverCol.value = column ? (column.dataset.status ?? null) : null
    }
  } else if (longPressTimer && touchStartPos) {
    // 长按检测中：如果手指移动超过阈值，取消长按（判定为滚动）
    const touch = e.touches[0]
    const dx = Math.abs(touch.clientX - touchStartPos.x)
    const dy = Math.abs(touch.clientY - touchStartPos.y)
    if (dx > MOVE_THRESHOLD || dy > MOVE_THRESHOLD) {
      clearTimeout(longPressTimer)
      longPressTimer = null
    }
  }
}

function onTouchEnd(e: TouchEvent) {
  // 取消长按定时器
  if (longPressTimer) {
    clearTimeout(longPressTimer)
    longPressTimer = null
  }
  // 清理 ghost
  if (touchDragGhost) {
    touchDragGhost.remove()
    touchDragGhost = null
  }
  document.querySelectorAll('.kanban-card.dragging').forEach(el => el.classList.remove('dragging'))
  const taskId = touchDragTaskId.value
  touchDragTaskId.value = null
  touchStartPos = null
  if (!taskId) {
    dragOverCol.value = null
    return
  }
  const touch = e.changedTouches[0]
  const el = document.elementFromPoint(touch.clientX, touch.clientY)
  if (el) {
    const column = el.closest('[data-status]') as HTMLElement | null
    if (column && column.dataset.status) {
      emit('statusChange', taskId, column.dataset.status)
    }
  }
  dragOverCol.value = null
}
</script>

<style scoped>
.kanban-board {
  display: flex;
  gap: 12px;
  flex: 1;
  min-height: 0;
  overflow-x: auto;
  padding-bottom: 8px;
}

.kanban-column {
  flex: 1;
  min-width: 260px;
  display: flex;
  flex-direction: column;
  background: var(--bg);
  border: 2px solid var(--border);
  border-radius: 10px;
  transition: border-color 0.2s, background 0.2s;
  overflow: hidden;
}

.kanban-column.drag-over {
  border-color: var(--accent);
  background: rgba(122, 162, 247, 0.04);
}

.column-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 14px;
  border-bottom: 1px solid var(--border);
  background: var(--bg-secondary);
  flex-shrink: 0;
}

.column-title {
  font-size: 14px;
  font-weight: 600;
  color: var(--fg);
  display: flex;
  align-items: center;
  gap: 6px;
}

.column-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  flex-shrink: 0;
}

.column-count {
  font-size: 12px;
  font-weight: 400;
  color: var(--fg-muted);
  background: rgba(255, 255, 255, 0.06);
  padding: 1px 6px;
  border-radius: 8px;
}

.btn-add {
  width: 28px;
  height: 28px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: rgba(255, 255, 255, 0.06);
  border: 1px solid var(--border);
  border-radius: 6px;
  color: var(--fg-muted);
  font-size: 16px;
  cursor: pointer;
  padding: 0;
  transition: background 0.15s, color 0.15s;
}

.btn-add:hover {
  background: rgba(122, 162, 247, 0.15);
  color: var(--accent);
}

.column-body {
  flex: 1;
  overflow-y: auto;
  padding: 10px;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.column-empty {
  text-align: center;
  color: var(--fg-muted);
  font-size: 13px;
  padding: 24px 0;
  opacity: 0.6;
}

@media (max-width: 768px) {
  .kanban-board {
    flex-direction: column;
    height: auto;
    flex: none;
  }

  .kanban-column {
    min-width: unset;
    max-height: 50vh;
  }
}
</style>
