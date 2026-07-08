<template>
  <div class="swarm-panel">
    <div class="swarm-header" @click="togglePanel">
      <div class="swarm-header-left">
        <span class="swarm-icon">🐝</span>
        <span class="swarm-title">Swarm</span>
        <span class="swarm-mode-badge" :class="{ active: swarm.swarmEnabled }">
          {{ swarm.swarmEnabled ? '集群模式' : '单次模式' }}
        </span>
      </div>
      <div class="swarm-header-right">
        <button class="swarm-btn-sm" @click.stop="onRefresh">刷新</button>
        <span class="swarm-toggle">{{ open ? '▼' : '▶' }}</span>
      </div>
    </div>

    <div v-if="open" class="swarm-body">
      <!-- 集群模式控制 -->
      <div class="swarm-cluster-bar">
        <span class="swarm-cluster-label">集群模式(&gt;4并行)</span>
        <div class="swarm-cluster-btns">
          <button v-if="!swarm.swarmEnabled" class="swarm-enable-btn" @click="onEnableCluster">启用</button>
          <button v-else class="swarm-disable-btn" @click="onDisableCluster">禁用</button>
        </div>
      </div>

      <!-- 子 Agent 列表 -->
      <div class="swarm-agent-list">
        <div v-if="swarm.loading" class="swarm-empty">加载中...</div>
        <div v-else-if="!swarm.available" class="swarm-empty">Swarm 系统未初始化</div>
        <div v-else-if="swarm.agents.length === 0" class="swarm-empty">无已注册子 Agent</div>
        <div v-for="a in swarm.agents" :key="a.name" class="swarm-agent-card">
          <div class="swarm-agent-top">
            <div class="swarm-agent-info">
              <span class="swarm-agent-dot" :style="{ background: statusColor(a.status) }" :class="{ pulse: a.is_busy }" />
              <span class="swarm-agent-name">{{ a.name }}</span>
              <span class="swarm-agent-role">{{ a.role }}</span>
            </div>
            <div class="swarm-agent-actions">
              <button v-if="a.is_busy" class="swarm-cancel-btn" @click="onCancelAgent(a.name)">取消</button>
              <button class="swarm-detail-btn" @click="onShowDetail(a.name)">详情</button>
            </div>
          </div>
          <div class="swarm-agent-meta">
            <div v-if="a.system_prompt" class="swarm-agent-prompt">{{ a.system_prompt }}</div>
            <div>状态: <span :style="{ color: statusColor(a.status) }">{{ statusLabel(a.status) }}</span> | 最大轮次: {{ a.max_turns }}<template v-if="a.model"> | 模型: {{ a.model }}</template></div>
            <div v-if="a.running_tasks && a.running_tasks.length">后台任务: {{ a.running_tasks.map(t => t.task_id.slice(0, 8)).join(', ') }}</div>
          </div>
        </div>
      </div>

      <!-- 后台任务 -->
      <div class="swarm-tasks-section">
        <div class="swarm-tasks-header">
          <span class="swarm-tasks-label">后台任务</span>
          <button class="swarm-btn-xs" @click="onRefreshTasks">刷新</button>
        </div>
        <div class="swarm-task-list">
          <div v-if="swarm.tasks.length === 0" class="swarm-empty-sm">暂无后台任务</div>
          <div v-for="t in swarm.tasks" :key="t.task_id" class="swarm-task-card">
            <div class="swarm-task-top">
              <div class="swarm-task-info">
                <span class="swarm-task-dot" :style="{ background: taskStatusColor(t.status) }" :class="{ pulse: !t.completed }" />
                <span class="swarm-task-agent">{{ t.agent_name || '未知' }}</span>
                <span class="swarm-task-id">{{ t.task_id.slice(0, 8) }}</span>
              </div>
              <span class="swarm-task-status" :style="{ color: taskStatusColor(t.status) }">{{ t.status }}</span>
            </div>
            <div v-if="t.content" class="swarm-task-content">{{ t.content.slice(0, 80) }}</div>
            <div v-if="t.error" class="swarm-task-error">{{ t.error.slice(0, 60) }}</div>
            <button v-if="!t.completed" class="swarm-btn-xs" @click="onPollTask(t.task_id)">轮询结果</button>
          </div>
        </div>
      </div>

      <!-- 详情展示 -->
      <div v-if="swarm.detailText" class="swarm-detail-box">
        <pre class="swarm-detail-pre">{{ swarm.detailText }}</pre>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, onUnmounted } from 'vue'
import { useSwarmStore } from '../../stores/swarmStore'
import { swarmGetAgentDetail } from '../../api'

const swarm = useSwarmStore()
const open = ref(false)
let refreshTimer: ReturnType<typeof setInterval> | null = null

function togglePanel() {
  open.value = !open.value
  if (open.value && !swarm.available) {
    swarm.refresh()
    swarm.refreshTasks()
  }
}

function onRefresh() {
  swarm.refresh()
  swarm.refreshTasks()
}

function onRefreshTasks() {
  swarm.refreshTasks()
}

async function onEnableCluster() {
  const reason = prompt('请输入启用 Swarm 集群模式的原因（如：大规模并行研究任务）：')
  if (!reason || !reason.trim()) return
  swarm.enableCluster(reason.trim())
}

function onDisableCluster() {
  if (!confirm('确认禁用 Swarm 集群模式？正在运行的大规模并行任务将被取消。')) return
  swarm.disableCluster()
}

function onCancelAgent(agentName: string) {
  swarm.cancelAgent(agentName)
}

async function onShowDetail(agentName: string) {
  try {
    const res = await swarmGetAgentDetail(agentName)
    const a = res.data?.data
    if (!a) return

    let text = `=== ${a.name} (${a.role}) ===\n`
    text += `状态: ${a.status} | 忙碌: ${a.is_busy}\n`
    text += `模型: ${a.model || '继承主Agent'} | 最大轮次: ${a.max_turns}\n`
    if (a.allowed_tools) text += `允许工具: ${a.allowed_tools.join(', ')}\n`
    if (a.denied_tools) text += `禁止工具: ${a.denied_tools.join(', ')}\n`
    text += `\n--- System Prompt ---\n${a.system_prompt || '(无)'}`

    if (a.last_result) {
      const lr = a.last_result
      text += `\n\n--- 最近结果 ---\n`
      text += `耗时: ${lr.duration_ms}ms | 工具调用: ${lr.tool_calls_count}\n`
      text += `tokens: ${lr.prompt_tokens}+${lr.completion_tokens}\n`
      if (lr.error) text += `错误: ${lr.error}\n`
      if (lr.content) text += `\n${lr.content}`
    }
    swarm.detailText = text
  } catch { /* silent */ }
}

async function onPollTask(taskId: string) {
  const done = await swarm.poll(taskId)
  if (done) swarm.refreshTasks()
}

const statusColors: Record<string, string> = {
  idle: '#6b7280', pending: '#f59e0b', running: '#3b82f6',
  completed: '#10b981', failed: '#ef4444', cancelled: '#9ca3af',
}
const statusLabels: Record<string, string> = {
  idle: '空闲', pending: '等待', running: '运行中',
  completed: '已完成', failed: '失败', cancelled: '已取消',
}
function statusColor(s: string) { return statusColors[s] || '#6b7280' }
function statusLabel(s: string) { return statusLabels[s] || s }
function taskStatusColor(s: string) { return statusColors[s] || '#6b7280' }

onMounted(() => {
  // 定时刷新（面板打开时）
  refreshTimer = setInterval(() => {
    if (open.value) {
      swarm.refresh()
      swarm.refreshTasks()
    }
  }, 30000)
})

onUnmounted(() => {
  if (refreshTimer) clearInterval(refreshTimer)
  swarm.cleanup()
})
</script>

<style scoped>
.swarm-panel {
  border-top: 1px solid var(--border);
  max-height: 50%;
  overflow-y: auto;
  flex-shrink: 0;
}

.swarm-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 4px 10px;
  background: var(--bg-secondary);
  cursor: pointer;
  user-select: none;
}

.swarm-header-left {
  display: flex;
  align-items: center;
  gap: 6px;
}

.swarm-icon { font-size: 11px; }
.swarm-title { font-size: 11px; font-weight: 600; color: var(--fg); }

.swarm-mode-badge {
  font-size: 9px;
  padding: 1px 6px;
  border-radius: 4px;
  background: var(--bg-tertiary);
  color: var(--fg-muted);
}
.swarm-mode-badge.active {
  background: #10b981;
  color: #fff;
}

.swarm-header-right {
  display: flex;
  gap: 4px;
  align-items: center;
}

.swarm-toggle {
  font-size: 10px;
  color: var(--fg-muted);
}

.swarm-btn-sm {
  background: var(--bg-tertiary);
  color: var(--fg);
  border: 1px solid var(--border);
  border-radius: 4px;
  padding: 1px 8px;
  font-size: 10px;
  cursor: pointer;
}

.swarm-body {
  padding: 6px 8px;
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.swarm-cluster-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 4px 6px;
  background: var(--bg-tertiary);
  border-radius: 4px;
}

.swarm-cluster-label {
  font-size: 10px;
  color: var(--fg-muted);
}

.swarm-enable-btn {
  background: #f59e0b;
  color: #000;
  border: none;
  border-radius: 3px;
  padding: 1px 8px;
  font-size: 9px;
  cursor: pointer;
}

.swarm-disable-btn {
  background: var(--bg-tertiary);
  color: var(--fg-muted);
  border: 1px solid var(--border);
  border-radius: 3px;
  padding: 1px 8px;
  font-size: 9px;
  cursor: pointer;
}

.swarm-agent-list {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.swarm-empty {
  color: var(--fg-muted);
  font-size: 11px;
  text-align: center;
  padding: 20px;
}

.swarm-agent-card {
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 8px 10px;
  background: var(--bg-secondary);
}

.swarm-agent-top {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.swarm-agent-info {
  display: flex;
  align-items: center;
  gap: 6px;
}

.swarm-agent-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  flex-shrink: 0;
}
.swarm-agent-dot.pulse {
  animation: swarmPulse 1.5s infinite;
}

@keyframes swarmPulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.4; }
}

.swarm-agent-name {
  font-size: 12px;
  font-weight: 600;
  color: var(--fg);
}

.swarm-agent-role {
  font-size: 10px;
  color: var(--fg-muted);
  background: var(--bg-tertiary);
  padding: 1px 6px;
  border-radius: 4px;
}

.swarm-agent-actions {
  display: flex;
  gap: 4px;
}

.swarm-cancel-btn {
  background: #ef4444;
  color: #fff;
  border: none;
  border-radius: 4px;
  padding: 2px 8px;
  font-size: 10px;
  cursor: pointer;
}

.swarm-detail-btn {
  background: var(--bg-tertiary);
  color: var(--fg);
  border: 1px solid var(--border);
  border-radius: 4px;
  padding: 2px 8px;
  font-size: 10px;
  cursor: pointer;
}

.swarm-agent-meta {
  margin-top: 4px;
  font-size: 10px;
  color: var(--fg-muted);
}

.swarm-agent-prompt {
  margin-bottom: 2px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.swarm-tasks-section {
  border-top: 1px solid var(--border);
  padding-top: 6px;
}

.swarm-tasks-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 4px;
}

.swarm-tasks-label {
  font-size: 10px;
  font-weight: 600;
  color: var(--fg-muted);
}

.swarm-btn-xs {
  background: transparent;
  color: var(--fg-muted);
  border: none;
  font-size: 9px;
  cursor: pointer;
  padding: 1px 4px;
}

.swarm-task-list {
  display: flex;
  flex-direction: column;
  gap: 3px;
}

.swarm-empty-sm {
  color: var(--fg-muted);
  font-size: 10px;
  text-align: center;
  padding: 6px;
}

.swarm-task-card {
  border: 1px solid var(--border);
  border-radius: 6px;
  padding: 6px 8px;
  background: var(--bg-secondary);
  font-size: 10px;
}

.swarm-task-top {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.swarm-task-info {
  display: flex;
  align-items: center;
  gap: 4px;
}

.swarm-task-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  flex-shrink: 0;
}
.swarm-task-dot.pulse {
  animation: swarmPulse 1.5s infinite;
}

.swarm-task-agent { color: var(--fg); }
.swarm-task-id { color: var(--fg-muted); }
.swarm-task-status { font-size: 10px; }

.swarm-task-content {
  margin-top: 3px;
  color: var(--fg-muted);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.swarm-task-error {
  margin-top: 2px;
  color: #ef4444;
}

.swarm-detail-box {
  border-top: 1px solid var(--border);
  margin-top: 6px;
  padding-top: 6px;
}

.swarm-detail-pre {
  font-size: 10px;
  font-family: monospace;
  color: var(--fg-muted);
  white-space: pre-wrap;
  word-break: break-all;
  max-height: 200px;
  overflow-y: auto;
  margin: 0;
}
</style>
