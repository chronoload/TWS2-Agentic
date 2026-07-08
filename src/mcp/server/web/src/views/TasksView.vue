<template>
  <div class="view tasks-view">
    <!-- 主内容 -->
    <div class="task-main">
      <header class="view-header">
        <SpaceSelector :counts="spaceCounts" />
        <div class="source-toggle">
          <button class="source-btn" :class="{ active: store.source === 'server' }" @click="switchSource('server')">服务端</button>
          <button class="source-btn" :class="{ active: store.source === 'local' }" @click="switchSource('local')">本地</button>
        </div>
        <button v-if="spacesStore.activeSpace" class="btn-rename" @click="startRename" title="重命名空间">✏️</button>
        <div v-if="store.source === 'server'" class="sync-buttons">
          <button class="btn-icon" @click="doSyncFromServer" title="从服务器拉取">↓</button>
          <button class="btn-icon" @click="doSyncToServer" title="推送到服务器">↑</button>
        </div>
        <div class="header-spacer"></div>
        <div class="header-right">
          <div class="search-box">
            <input v-model="searchQuery" type="text" class="search-input" placeholder="搜索任务..." @input="onSearchInput" />
            <button v-if="searchQuery" class="search-clear" @click="searchQuery = ''">✕</button>
          </div>
          <div class="view-toggle">
            <button class="toggle-btn" :class="{ active: currentView === 'kanban' }" @click="currentView = 'kanban'">看板</button>
            <button class="toggle-btn" :class="{ active: currentView === 'calendar' }" @click="currentView = 'calendar'">日历</button>
          </div>
          <select v-model="priorityFilter" class="filter-select">
            <option value="">全部优先级</option>
            <option value="高">高</option>
            <option value="中">中</option>
            <option value="低">低</option>
          </select>
        </div>
      </header>

      <!-- 统计栏 -->
      <div class="stats-bar">
        <div class="stat-item">
          <span class="stat-value">{{ stats.total }}</span>
          <span class="stat-label">总任务</span>
        </div>
        <div class="stat-item stat-done">
          <span class="stat-value">{{ stats.done }}</span>
          <span class="stat-label">已完成</span>
        </div>
        <div class="stat-item stat-overdue">
          <span class="stat-value">{{ stats.overdue }}</span>
          <span class="stat-label">逾期</span>
        </div>
        <div class="stat-item stat-today">
          <span class="stat-value">{{ stats.todayDue }}</span>
          <span class="stat-label">今日到期</span>
        </div>
        <div class="stat-item stat-time">
          <span class="stat-value">{{ formatMinutes(stats.totalTracked) }}</span>
          <span class="stat-label">追踪时长</span>
        </div>
      </div>

      <div class="view-body kanban-container">
        <div v-if="store.loading" class="loading">加载中...</div>
        <KanbanBoard
          v-else-if="currentView === 'kanban'"
          :tasks="currentTasks"
          :priority-filter="priorityFilter || undefined"
          @add-task="openAddModal"
          @delete-task="confirmDelete"
          @edit-task="openEditModal"
          @status-change="handleStatusChange"
          @start-timer="handleStartTimer"
          @stop-timer="handleStopTimer"
          @toggle-subtask="handleToggleSubtask"
        />
        <CalendarView
          v-else
          :tasks="currentTasks"
          :priority-filter="priorityFilter || undefined"
          @add-task="openAddModal"
          @delete-task="confirmDelete"
          @edit-task="openEditModal"
          @status-change="handleStatusChange"
          @start-timer="handleStartTimer"
          @stop-timer="handleStopTimer"
          @toggle-subtask="handleToggleSubtask"
        />
      </div>

      <!-- 重命名输入 -->
      <Teleport to="body">
        <div v-if="showRename" class="modal-overlay" @click.self="showRename = false">
          <div class="modal modal-sm">
            <h2 class="modal-title">重命名空间</h2>
            <input v-model="renameBuffer" class="rename-input" @keyup.enter="doRename" />
            <div class="modal-actions">
              <button class="btn-cancel" @click="showRename = false">取消</button>
              <button class="btn-submit" @click="doRename">确定</button>
            </div>
          </div>
        </div>
      </Teleport>

      <!-- 添加/编辑任务弹窗 -->
      <Teleport to="body">
        <div v-if="showModal" class="modal-overlay" @click.self="closeModal">
          <div class="modal">
            <h2 class="modal-title">{{ isEditing ? '编辑任务' : '添加任务' }}</h2>
            <form class="modal-form" @submit.prevent="handleSubmit">
              <label class="form-label">
                标题 <span class="required">*</span>
                <input v-model="form.title" type="text" required placeholder="输入任务标题" />
              </label>
              <label class="form-label">
                描述
                <textarea v-model="form.description" rows="3" placeholder="任务描述（可选）"></textarea>
              </label>
              <div class="form-row">
                <label class="form-label">
                  截止日期
                  <input v-model="form.due_date" type="date" />
                </label>
                <label class="form-label">
                  开始时间
                  <input v-model="form.start_time" type="datetime-local" />
                </label>
              </div>
              <div class="form-row">
                <label class="form-label">
                  优先级
                  <select v-model="form.priority">
                    <option value="高">高</option>
                    <option value="中">中</option>
                    <option value="低">低</option>
                  </select>
                </label>
                <label class="form-label">
                  时长（分钟）
                  <input v-model.number="form.duration" type="number" min="1" />
                </label>
              </div>
              <div class="form-row">
                <label class="form-label">
                  循环
                  <select v-model="form.recurrence">
                    <option value="不循环">不循环</option>
                    <option value="每天">每天</option>
                    <option value="每周">每周</option>
                    <option value="每月">每月</option>
                    <option value="工作日">工作日</option>
                  </select>
                </label>
                <label class="form-label">
                  提醒时间
                  <input v-model="form.reminder" type="datetime-local" />
                </label>
              </div>

              <label class="form-label">
                颜色
                <div class="color-swatches">
                  <button
                    v-for="c in colorPresets" :key="c" type="button"
                    class="color-swatch" :class="{ active: form.color === c }"
                    :style="{ background: c }" @click="form.color = form.color === c ? '' : c"
                  ></button>
                </div>
              </label>

              <label class="form-label">
                标签（逗号分隔）
                <input v-model="tagsInput" type="text" placeholder="如：工作,重要" @input="parseTags" />
                <div v-if="form.tags.length" class="tags-preview">
                  <span v-for="tag in form.tags" :key="tag" class="tag-badge">
                    {{ tag }}
                    <button type="button" class="tag-remove" @click="removeTag(tag)">×</button>
                  </span>
                </div>
              </label>

              <label class="form-label">
                子任务
                <div class="subtask-list">
                  <div v-for="(st, idx) in form.subtasks" :key="idx" class="subtask-row">
                    <input type="checkbox" :checked="st.done" @change="form.subtasks[idx].done = !form.subtasks[idx].done" />
                    <input v-model="form.subtasks[idx].title" type="text" class="subtask-input" placeholder="子任务名称" />
                    <button type="button" class="subtask-remove" @click="form.subtasks.splice(idx, 1)">×</button>
                  </div>
                  <div class="subtask-add-row">
                    <input v-model="newSubtaskTitle" type="text" class="subtask-input" placeholder="添加子任务..." @keydown.enter.prevent="addSubtaskInline" />
                    <button type="button" class="subtask-add-btn" @click="addSubtaskInline">＋</button>
                  </div>
                </div>
              </label>

              <div class="modal-actions">
                <button type="button" class="btn-cancel" @click="closeModal">取消</button>
                <button type="submit" class="btn-submit">{{ isEditing ? '保存' : '添加' }}</button>
              </div>
            </form>
          </div>
        </div>
      </Teleport>

      <!-- 删除确认 -->
      <Teleport to="body">
        <div v-if="showDeleteConfirm" class="modal-overlay" @click.self="showDeleteConfirm = false">
          <div class="modal modal-sm">
            <h2 class="modal-title">确认删除</h2>
            <p class="modal-text">确定要删除此任务吗？</p>
            <div class="modal-actions">
              <button class="btn-cancel" @click="showDeleteConfirm = false">取消</button>
              <button class="btn-danger" @click="handleDelete">删除</button>
            </div>
          </div>
        </div>
      </Teleport>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed, onMounted } from 'vue'
import { useTasksStore } from '../stores/tasks'
import { useSpacesStore } from '../stores/spaces'
import type { SubTask } from '../stores/tasks'
import KanbanBoard from '../components/KanbanBoard.vue'
import CalendarView from '../components/CalendarView.vue'
import SpaceSelector from '../components/SpaceSelector.vue'

const store = useTasksStore()
const spacesStore = useSpacesStore()

const priorityFilter = ref('')
const searchQuery = ref('')
const currentView = ref<'kanban' | 'calendar'>('kanban')

let searchTimer: ReturnType<typeof setTimeout> | null = null
function onSearchInput() {
  if (searchTimer) clearTimeout(searchTimer)
}

const colorPresets = ['#ef4444', '#f59e0b', '#22c55e', '#3b82f6', '#8b5cf6', '#ec4899', '#06b6d4', '#6366f1']

const currentTasks = computed(() => {
  if (!spacesStore.activeSpaceId || !store.bySpace) return []
  let list = store.bySpace[spacesStore.activeSpaceId] ?? []
  if (searchQuery.value.trim()) {
    const q = searchQuery.value.trim().toLowerCase()
    list = list.filter(t =>
      t.title.toLowerCase().includes(q) ||
      (t.description || '').toLowerCase().includes(q) ||
      (t.tags || []).some(tag => tag.toLowerCase().includes(q))
    )
  }
  return list
})

const stats = computed(() => {
  if (!spacesStore.activeSpaceId) return { total: 0, done: 0, overdue: 0, todayDue: 0, totalTracked: 0 }
  return store.getStats(spacesStore.activeSpaceId)
})

const spaceCounts = computed(() => {
  const out: Record<string, number> = {}
  if (!store.bySpace) return out
  for (const sp of spacesStore.spaces) {
    out[sp.id] = (store.bySpace[sp.id] ?? []).length
  }
  return out
})

// 空间管理
const showCreateSpace = ref(false)
const newSpaceName = ref('')
const spaceInputRef = ref<HTMLInputElement | null>(null)
const showRename = ref(false)
const renameBuffer = ref('')

function selectSpace(id: string) {
  spacesStore.selectSpace(id)
}

function removeSpace(id: string) {
  spacesStore.removeSpace(id)
}

function doCreateSpace() {
  const name = newSpaceName.value.trim()
  if (!name) return
  spacesStore.addSpace(name)
  newSpaceName.value = ''
  showCreateSpace.value = false
}

function startRename() {
  if (!spacesStore.activeSpace) return
  renameBuffer.value = spacesStore.activeSpace.name
  showRename.value = true
}

function doRename() {
  if (!spacesStore.activeSpaceId || !renameBuffer.value.trim()) return
  spacesStore.renameSpace(spacesStore.activeSpaceId, renameBuffer.value.trim())
  showRename.value = false
}

// 任务 CRUD
const showModal = ref(false)
const isEditing = ref(false)
const editingTaskId = ref<string | null>(null)
const defaultStatus = ref('待办')

const form = reactive({
  title: '', description: '', due_date: '', priority: '中',
  start_time: '', duration: 60, recurrence: '不循环', color: '',
  tags: [] as string[], subtasks: [] as SubTask[], reminder: '',
})
const tagsInput = ref('')
const newSubtaskTitle = ref('')
const showDeleteConfirm = ref(false)
const deletingId = ref<string | null>(null)

onMounted(async () => {
  const bootstrap = (window as any).__TS2_BOOTSTRAP__
  if (bootstrap?.tasks) {
    store.setTasks(Array.isArray(bootstrap.tasks) ? bootstrap.tasks : [])
    delete bootstrap.tasks
  }
  // 默认本地模式，不再自动切换服务端；由 App.vue 后台连接成功后统一切 source
})

function switchSource(val: 'local' | 'server') {
  if (val === 'server') store.switchToServer()
  else store.switchToLocal()
}

async function doSyncFromServer() {
  await store.syncFromServer()
}

async function doSyncToServer() {
  await store.syncToServer()
}

function resetForm() {
  form.title = ''; form.description = ''; form.due_date = ''
  form.priority = '中'; form.start_time = ''; form.duration = 60
  form.recurrence = '不循环'; form.color = ''; form.tags = []
  form.subtasks = []; form.reminder = ''
  tagsInput.value = ''; newSubtaskTitle.value = ''
}

function openAddModal(status: string) {
  if (!spacesStore.activeSpaceId) return
  resetForm()
  isEditing.value = false
  editingTaskId.value = null
  defaultStatus.value = status
  showModal.value = true
}

function openEditModal(task: any) {
  isEditing.value = true
  editingTaskId.value = task.id
  form.title = task.title; form.description = task.description || ''
  form.due_date = task.due_date || ''; form.priority = task.priority || '中'
  form.start_time = task.start_time || ''; form.duration = task.duration || 60
  form.recurrence = task.recurrence || '不循环'; form.color = task.color || ''
  form.tags = task.tags ? [...task.tags] : []
  form.subtasks = task.subtasks ? task.subtasks.map((s: any) => ({ ...s })) : []
  form.reminder = task.reminder || ''
  tagsInput.value = form.tags.join(', ')
  showModal.value = true
}

function closeModal() { showModal.value = false; editingTaskId.value = null }

async function handleSubmit() {
  if (!form.title.trim() || !spacesStore.activeSpaceId) return
  if (isEditing.value && editingTaskId.value) {
    await store.editTask(editingTaskId.value, { ...form })
  } else {
    await store.addTask(spacesStore.activeSpaceId, { ...form, status: defaultStatus.value })
  }
  closeModal()
}

function confirmDelete(id: string) { deletingId.value = id; showDeleteConfirm.value = true }

async function handleDelete() {
  if (deletingId.value) {
    await store.removeTask(deletingId.value)
    deletingId.value = null
    showDeleteConfirm.value = false
  }
}

async function handleStatusChange(id: string, newStatus: string) {
  if (newStatus === '已完成') {
    const all = Object.values(store.bySpace).flat()
    const task = all.find(t => t.id === id)
    if (task && task.recurrence && task.recurrence !== '不循环') {
      store.completeRecurring(id)
      return
    }
  }
  await store.editTask(id, { status: newStatus })
}

function handleStartTimer(id: string) { store.startTimer(id) }
function handleStopTimer(id: string) { store.stopTimer(id) }
async function handleToggleSubtask(taskId: string, subtaskId: string) { await store.toggleSubtask(taskId, subtaskId) }

function parseTags() {
  form.tags = tagsInput.value.split(',').map(t => t.trim()).filter(t => t.length > 0)
}
function removeTag(tag: string) {
  form.tags = form.tags.filter(t => t !== tag)
  tagsInput.value = form.tags.join(', ')
}
function addSubtaskInline() {
  const title = newSubtaskTitle.value.trim()
  if (!title) return
  form.subtasks.push({ id: `sub_${Date.now()}_${Math.random().toString(36).slice(2, 6)}`, title, done: false })
  newSubtaskTitle.value = ''
}
function formatMinutes(min: number): string {
  if (min < 60) return `${min}分钟`
  const h = Math.floor(min / 60)
  const m = min % 60
  return m > 0 ? `${h}h${m}m` : `${h}h`
}
</script>

<style scoped>
.tasks-view {
  display: flex;
  flex: 1;
  min-height: 0;
  overflow: hidden;
}

.space-sidebar {
  width: 180px;
  flex-shrink: 0;
  background: var(--bg-secondary);
  border-right: 1px solid var(--border);
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.space-sidebar-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px;
  border-bottom: 1px solid var(--border);
}

.space-sidebar-header h3 {
  font-size: 13px;
  font-weight: 600;
  color: var(--fg);
}

.btn-space-add {
  width: 24px; height: 24px;
  display: flex; align-items: center; justify-content: center;
  background: rgba(255,255,255,0.06);
  border: 1px solid var(--border);
  border-radius: 4px;
  color: var(--fg-muted);
  font-size: 14px;
  cursor: pointer;
  padding: 0;
}

.btn-space-add:hover { background: rgba(122,162,247,0.15); color: var(--accent); }

.space-list {
  flex: 1;
  overflow-y: auto;
  padding: 4px;
}

.space-item {
  display: flex;
  align-items: center;
  gap: 4px;
  padding: 8px 10px;
  border-radius: 6px;
  cursor: pointer;
  transition: background 0.15s;
  font-size: 13px;
}

.space-item:hover { background: rgba(255,255,255,0.04); }
.space-item.active { background: rgba(122,162,247,0.12); color: var(--accent); }

.space-name { flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.space-count { font-size: 11px; color: var(--fg-muted); }
.space-del-btn {
  background: transparent; border: none; color: var(--fg-muted);
  font-size: 12px; cursor: pointer; padding: 2px 4px; border-radius: 3px;
}
.space-del-btn:hover { background: rgba(239,68,68,0.15); color: #ef4444; }

.space-create-form {
  display: flex;
  gap: 4px;
  padding: 8px;
  border-top: 1px solid var(--border);
  flex-wrap: wrap;
}

.space-create-input {
  flex: 1; min-width: 0;
  background: var(--bg); color: var(--fg);
  border: 1px solid var(--border); border-radius: 4px;
  padding: 4px 8px; font-size: 12px;
}

.btn-space-confirm, .btn-space-cancel {
  background: rgba(122,162,247,0.15); color: var(--accent);
  border: none; border-radius: 4px; padding: 4px 8px; font-size: 11px; cursor: pointer;
}
.btn-space-cancel { background: transparent; color: var(--fg-muted); }

.task-main {
  flex: 1;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.header-left {
  display: flex;
  align-items: center;
  gap: 8px;
}

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

.header-spacer { flex: 1; min-width: 0; }
.header-right { display: flex; align-items: center; gap: 10px; flex-shrink: 0; }

.sync-buttons { display: inline-flex; gap: 2px; flex-shrink: 0; }
.btn-icon { background: transparent; border: 1px solid var(--border); border-radius: 4px; color: var(--fg-muted); padding: 2px 6px; font-size: 12px; cursor: pointer; line-height: 1.4; transition: all 0.15s; }
.btn-icon:hover { background: var(--bg-tertiary); border-color: var(--accent); color: var(--accent); }

.source-toggle { display: inline-flex; border: 1px solid var(--border); border-radius: 6px; overflow: hidden; flex-shrink: 0; }
.source-btn { background: transparent; border: none; color: var(--fg-muted); padding: 3px 10px; font-size: 11px; cursor: pointer; transition: all 0.15s; }
.source-btn.active { background: var(--accent); color: #fff; }
.source-btn:hover:not(.active) { background: var(--bg-secondary); }

.btn-rename {
  background: transparent; border: none; color: var(--fg-muted);
  font-size: 14px; cursor: pointer; padding: 4px;
}

.header-actions { display: flex; align-items: center; gap: 10px; }

.view-toggle { display: flex; border: 1px solid var(--border); border-radius: 6px; overflow: hidden; }
.toggle-btn {
  background: transparent; color: var(--fg-muted); border: none;
  padding: 5px 14px; font-size: 13px; cursor: pointer;
}
.toggle-btn.active { background: var(--accent); color: var(--bg); font-weight: 600; }

.search-box { display: flex; align-items: center; gap: 4px; position: relative; }
.search-input {
  background: var(--bg); color: var(--fg);
  border: 1px solid var(--border); border-radius: 6px;
  padding: 5px 10px; font-size: 13px; outline: none; width: 160px;
  transition: border-color 0.15s;
}
.search-input:focus { border-color: var(--accent); }
.search-clear {
  position: absolute; right: 4px; top: 50%; transform: translateY(-50%);
  background: transparent; border: none; color: var(--fg-muted);
  font-size: 14px; cursor: pointer; padding: 2px;
}

.filter-select {
  background: var(--bg); color: var(--fg);
  border: 1px solid var(--border); border-radius: 6px;
  padding: 4px 8px; font-size: 13px; outline: none;
}

.stats-bar {
  display: flex; gap: 12px; padding: 12px 16px;
  background: var(--bg-secondary); border: 1px solid var(--border);
  border-radius: 10px; margin: 0 12px 8px;
}
.stat-item { display: flex; flex-direction: column; align-items: center; flex: 1; gap: 2px; }
.stat-value { font-size: 20px; font-weight: 700; color: var(--fg); }
.stat-label { font-size: 11px; color: var(--fg-muted); }
.stat-done .stat-value { color: var(--success); }
.stat-overdue .stat-value { color: #ef4444; }
.stat-today .stat-value { color: var(--warning); }
.stat-time .stat-value { color: #3b82f6; }

.kanban-container { padding: 12px; overflow: auto; flex: 1; min-height: 0; display: flex; flex-direction: column; }
.loading { text-align: center; padding: 48px 0; color: var(--fg-muted); font-size: 14px; }

.modal-overlay {
  position: fixed; inset: 0; z-index: 200;
  background: rgba(0,0,0,0.6);
  display: flex; align-items: center; justify-content: center; padding: 16px;
}
.modal {
  background: var(--bg-secondary); border: 1px solid var(--border);
  border-radius: 12px; padding: 24px; width: 100%;
  max-width: 520px; max-height: 90vh; overflow-y: auto;
}
.modal-sm { max-width: 360px; }
.modal-title { font-size: 18px; font-weight: 600; color: var(--fg); margin-bottom: 20px; }
.modal-text { color: var(--fg-muted); font-size: 14px; margin-bottom: 20px; }
.modal-form { display: flex; flex-direction: column; gap: 14px; }
.form-label { display: flex; flex-direction: column; gap: 4px; font-size: 13px; color: var(--fg-muted); }
.required { color: var(--danger); }
.form-row { display: flex; gap: 12px; }
.form-row .form-label { flex: 1; }
.modal-actions { display: flex; justify-content: flex-end; gap: 8px; margin-top: 8px; }

.btn-cancel {
  background: transparent; color: var(--fg-muted);
  border: 1px solid var(--border); padding: 8px 20px; border-radius: 6px; font-size: 14px; cursor: pointer;
}
.btn-submit {
  background: var(--accent); color: var(--bg); border: none;
  padding: 8px 20px; border-radius: 6px; font-size: 14px; font-weight: 600; cursor: pointer;
}
.btn-danger {
  background: var(--danger); color: #fff; border: none;
  padding: 8px 20px; border-radius: 6px; font-size: 14px; font-weight: 600; cursor: pointer;
}

.rename-input {
  width: 100%; padding: 8px 12px; border: 1px solid var(--border);
  border-radius: 6px; background: var(--bg); color: var(--fg);
  font-size: 14px; margin-bottom: 16px;
}

.color-swatches { display: flex; gap: 8px; flex-wrap: wrap; margin-top: 4px; }
.color-swatch {
  width: 28px; height: 28px; border-radius: 50%; border: 2px solid transparent;
  cursor: pointer; transition: border-color 0.15s, transform 0.15s; padding: 0;
}
.color-swatch:hover { transform: scale(1.15); }
.color-swatch.active { border-color: var(--fg); transform: scale(1.15); }
.tags-preview { display: flex; flex-wrap: wrap; gap: 4px; margin-top: 4px; }
.tag-badge {
  display: inline-flex; align-items: center; gap: 2px; padding: 2px 8px;
  border-radius: 10px; font-size: 11px; font-weight: 500;
  background: rgba(59,130,246,0.15); color: #60a5fa; border: 1px solid rgba(59,130,246,0.25);
}
.tag-remove { background: transparent; border: none; color: #60a5fa; font-size: 13px; cursor: pointer; padding: 0 2px; }
.subtask-list { display: flex; flex-direction: column; gap: 6px; margin-top: 4px; }
.subtask-row { display: flex; align-items: center; gap: 6px; }
.subtask-input { flex: 1; background: var(--bg); color: var(--fg); border: 1px solid var(--border); border-radius: 4px; padding: 4px 8px; font-size: 13px; }
.subtask-remove { background: transparent; border: none; color: var(--fg-muted); font-size: 16px; cursor: pointer; }
.subtask-add-row { display: flex; gap: 6px; }
.subtask-add-btn { background: rgba(255,255,255,0.06); border: 1px solid var(--border); color: var(--fg-muted); border-radius: 4px; padding: 4px 10px; font-size: 14px; cursor: pointer; }

@media (max-width: 768px) {
  .space-sidebar { width: 140px; }
  .stats-bar { flex-wrap: wrap; }
  .form-row { flex-direction: column; }
}
</style>
