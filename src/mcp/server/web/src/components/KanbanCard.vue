<template>
  <div
    class="kanban-card"
    :style="cardStyle"
    :data-task-id="task.id"
    @dragstart="onDragStart"
    @dragend="onDragEnd"
  >
    <div class="card-header">
      <div class="card-header-left">
        <span class="priority-badge" :class="priorityClass">{{ task.priority || '中' }}</span>
        <span v-if="task.recurrence && task.recurrence !== '不循环'" class="recurrence-badge" :title="`循环: ${task.recurrence}`">🔄</span>
        <span v-if="isOverdue" class="overdue-badge">逾期</span>
      </div>
      <div class="card-actions">
        <button
          class="btn-icon timer-btn"
          :class="{ active: timerRunning }"
          :title="timerRunning ? '停止计时' : '开始计时'"
          @click.stop="onTimerClick"
        >
          {{ timerRunning ? '⏸' : '▶' }}
        </button>
        <button class="btn-icon" title="编辑" @click.stop="emit('edit', task)">✏️</button>
        <button class="btn-icon" title="删除" @click.stop="emit('delete', task.id)">🗑️</button>
      </div>
    </div>
    <h3 class="card-title">{{ task.title }}</h3>
    <p v-if="task.description" class="card-desc">{{ task.description }}</p>

    <!-- 标签 -->
    <div v-if="task.tags && task.tags.length" class="card-tags">
      <span v-for="tag in task.tags" :key="tag" class="tag-badge">{{ tag }}</span>
    </div>

    <!-- 子任务列表 -->
    <div v-if="task.subtasks && task.subtasks.length" class="card-subtasks">
      <div class="subtask-progress-row" @click.stop="showSubtasks = !showSubtasks">
        <div class="subtask-progress">
          <div class="subtask-bar" :style="{ width: subtaskPercent + '%' }" />
        </div>
        <span class="subtask-text">{{ subtaskDone }}/{{ task.subtasks.length }}</span>
        <span class="subtask-toggle">{{ showSubtasks ? '▲' : '▼' }}</span>
      </div>
      <div v-if="showSubtasks" class="subtask-items">
        <label v-for="st in task.subtasks" :key="st.id" class="subtask-check">
          <input type="checkbox" :checked="st.done" @change="emit('toggleSubtask', task.id, st.id)" />
          <span :class="{ 'subtask-done': st.done }">{{ st.title }}</span>
        </label>
      </div>
    </div>

    <div class="card-meta">
      <span v-if="task.due_date" class="meta-item" :class="{ overdue: isOverdue }">📅 {{ task.due_date }}</span>
      <span v-if="task.duration" class="meta-item">⏱️ {{ task.duration }}分钟</span>
      <span v-if="trackedMin > 0" class="meta-item tracked" :class="{ overtime: trackedMin > (task.duration || Infinity) }">⏳ {{ formatTracked(trackedMin) }}</span>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import type { Task } from '../stores/tasks'

const props = defineProps<{
  task: Task
  timerRunning?: boolean
  trackedMinutes?: number
}>()

const emit = defineEmits<{
  delete: [id: string]
  edit: [task: Task]
  startTimer: [id: string]
  stopTimer: [id: string]
  toggleSubtask: [taskId: string, subtaskId: string]
}>()

const showSubtasks = ref(false)

const priorityClass = computed(() => {
  const p = props.task.priority
  if (p === '高') return 'priority-high'
  if (p === '中') return 'priority-medium'
  return 'priority-low'
})

const isOverdue = computed(() => {
  if (props.task.status === '已完成' || !props.task.due_date) return false
  return new Date(props.task.due_date) < new Date(new Date().toISOString().split('T')[0])
})

const subtaskDone = computed(() => props.task.subtasks?.filter(s => s.done).length ?? 0)
const subtaskPercent = computed(() => {
  if (!props.task.subtasks?.length) return 0
  return Math.round((subtaskDone.value / props.task.subtasks.length) * 100)
})

const trackedMin = computed(() => props.trackedMinutes ?? 0)

const cardStyle = computed(() => {
  if (props.task.color) {
    return { borderLeft: `3px solid ${props.task.color}` }
  }
  return {}
})

function onTimerClick() {
  if (props.timerRunning) {
    emit('stopTimer', props.task.id)
  } else {
    emit('startTimer', props.task.id)
  }
}

function onDragStart(e: DragEvent) {
  if (e.dataTransfer) {
    e.dataTransfer.setData('text/plain', props.task.id)
    e.dataTransfer.effectAllowed = 'move'
  }
  const el = e.currentTarget as HTMLElement
  if (el) el.classList.add('dragging')
}

function onDragEnd(e: DragEvent) {
  const el = e.currentTarget as HTMLElement
  if (el) el.classList.remove('dragging')
}

function formatTracked(min: number): string {
  if (min < 60) return `${min}m`
  const h = Math.floor(min / 60)
  const m = min % 60
  return m > 0 ? `${h}h${m}m` : `${h}h`
}
</script>

<style scoped>
.kanban-card {
  background: var(--card);
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 12px;
  cursor: grab;
  transition: transform 0.15s, box-shadow 0.15s, opacity 0.15s;
  user-select: none;
  -webkit-user-select: none;
}

.kanban-card:hover {
  transform: translateY(-2px);
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.3);
}

.kanban-card:active {
  cursor: grabbing;
}

.kanban-card.dragging {
  opacity: 0.4;
  transform: rotate(2deg);
}

.card-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 8px;
}

.card-header-left {
  display: flex;
  align-items: center;
  gap: 4px;
}

.priority-badge {
  display: inline-block;
  padding: 2px 8px;
  border-radius: 10px;
  font-size: 12px;
  font-weight: 600;
  line-height: 1.4;
}

.priority-high {
  background: rgba(247, 118, 142, 0.2);
  color: var(--danger);
}

.priority-medium {
  background: rgba(224, 175, 104, 0.2);
  color: var(--warning);
}

.priority-low {
  background: rgba(158, 206, 106, 0.2);
  color: var(--success);
}

.recurrence-badge {
  font-size: 12px;
  cursor: help;
}

.overdue-badge {
  display: inline-block;
  padding: 1px 6px;
  border-radius: 8px;
  font-size: 10px;
  font-weight: 600;
  background: rgba(239, 68, 68, 0.2);
  color: #ef4444;
}

.card-actions {
  display: flex;
  gap: 2px;
}

.btn-icon {
  background: transparent;
  border: none;
  padding: 4px;
  font-size: 14px;
  line-height: 1;
  cursor: pointer;
  border-radius: 4px;
  color: var(--fg-muted);
  transition: background 0.15s, color 0.15s;
}

.btn-icon:hover {
  background: rgba(255, 255, 255, 0.08);
  color: var(--fg);
}

.timer-btn.active {
  color: #3b82f6;
  animation: timerPulse 1.5s infinite;
}

@keyframes timerPulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.5; }
}

.card-title {
  font-size: 14px;
  font-weight: 600;
  color: var(--fg);
  margin-bottom: 4px;
  word-break: break-word;
}

.card-desc {
  font-size: 12px;
  color: var(--fg-muted);
  margin-bottom: 8px;
  word-break: break-word;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

/* 标签 */
.card-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
  margin-bottom: 8px;
}

.tag-badge {
  display: inline-block;
  padding: 1px 8px;
  border-radius: 10px;
  font-size: 10px;
  font-weight: 500;
  background: rgba(59, 130, 246, 0.15);
  color: #60a5fa;
  border: 1px solid rgba(59, 130, 246, 0.25);
}

/* 子任务 */
.card-subtasks {
  margin-bottom: 8px;
}

.subtask-progress-row {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-bottom: 4px;
  cursor: pointer;
}

.subtask-progress-row:hover {
  opacity: 0.8;
}

.subtask-progress {
  flex: 1;
  height: 4px;
  background: var(--bg-tertiary, rgba(255,255,255,0.1));
  border-radius: 2px;
  overflow: hidden;
}

.subtask-bar {
  height: 100%;
  background: var(--success);
  border-radius: 2px;
  transition: width 0.3s;
}

.subtask-text {
  font-size: 10px;
  color: var(--fg-muted);
  white-space: nowrap;
}

.subtask-toggle {
  font-size: 8px;
  color: var(--fg-muted);
  flex-shrink: 0;
}

.subtask-items {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.subtask-check {
  display: flex;
  align-items: center;
  gap: 4px;
  font-size: 11px;
  color: var(--fg-muted);
  cursor: pointer;
}

.subtask-check input[type="checkbox"] {
  width: 14px;
  height: 14px;
  flex-shrink: 0;
  accent-color: var(--accent);
  margin: 0;
}

.subtask-done {
  text-decoration: line-through;
  opacity: 0.5;
}

/* 元信息 */
.card-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  font-size: 12px;
  color: var(--fg-muted);
}

.meta-item {
  display: inline-flex;
  align-items: center;
  gap: 2px;
}

.meta-item.overdue {
  color: #ef4444;
  font-weight: 600;
}

.meta-item.tracked {
  color: #3b82f6;
}

.meta-item.overtime {
  color: #f59e0b;
}
</style>
