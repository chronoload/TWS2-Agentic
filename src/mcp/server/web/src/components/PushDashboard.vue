<template>
  <div class="push-dashboard" v-if="hasItems">
    <div class="push-header" @click="collapsed = !collapsed">
      <span class="push-title">📌 待办提醒</span>
      <span class="push-badge">{{ totalCount }}</span>
      <span class="push-toggle">{{ collapsed ? '▸' : '▾' }}</span>
    </div>
    <div v-if="!collapsed" class="push-body">
      <!-- 超期任务 -->
      <div v-if="data.overdue_tasks?.length" class="push-section urgent">
        <div class="push-section-title">⚠️ 超期 ({{ data.overdue_tasks.length }})</div>
        <div v-for="t in data.overdue_tasks.slice(0, 3)" :key="t.id" class="push-item" @click="$router.push('/tasks')">
          <span class="push-item-title">{{ t.title }}</span>
          <span class="push-item-meta">超期{{ t.overdue_days }}天</span>
        </div>
      </div>
      <!-- 近期截止 -->
      <div v-if="data.due_tasks?.length" class="push-section warning">
        <div class="push-section-title">📅 近期截止 ({{ data.due_tasks.length }})</div>
        <div v-for="t in data.due_tasks.slice(0, 3)" :key="t.id" class="push-item" @click="$router.push('/tasks')">
          <span class="push-item-title">{{ t.title }}</span>
          <span class="push-item-meta">{{ t.due_date }}</span>
        </div>
      </div>
      <!-- 待复习 -->
      <div v-if="data.due_reviews?.length" class="push-section info">
        <div class="push-section-title">🔄 待复习 ({{ data.due_reviews.length }})</div>
        <div v-for="r in data.due_reviews.slice(0, 3)" :key="r.course_id + r.lesson_number" class="push-item" @click="$router.push('/courses')">
          <span class="push-item-title">{{ r.lesson_title }}</span>
          <span class="push-item-meta">{{ r.course_title }}</span>
        </div>
      </div>
      <!-- 最近资源 -->
      <div v-if="data.recent_resources?.length" class="push-section">
        <div class="push-section-title">📎 最近资源</div>
        <div v-for="r in data.recent_resources.slice(0, 3)" :key="(r._course_id || '') + (r.label || '')" class="push-item" @click="$router.push('/courses')">
          <span class="push-item-title">{{ r.label || r.type || '资源' }}</span>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { getPushDashboard } from '../api'
import { useWebSocket } from '../composables/useWebSocket'

const data = ref<any>({})
const collapsed = ref(false)

const hasItems = computed(() => {
  return (data.value.overdue_tasks?.length || 0) +
         (data.value.due_tasks?.length || 0) +
         (data.value.due_reviews?.length || 0) > 0
})

const totalCount = computed(() => {
  return (data.value.overdue_tasks?.length || 0) +
         (data.value.due_tasks?.length || 0) +
         (data.value.due_reviews?.length || 0)
})

async function loadPush() {
  // 优先从 bootstrap 缓存
  const bootstrap = (window as any).__TS2_BOOTSTRAP__
  if (bootstrap?.push) {
    data.value = bootstrap.push
    delete bootstrap.push
  }
  // 从 API 加载（仅在 baseURL 已设置时）
  try {
    const res = await getPushDashboard()
    data.value = res.data?.data ?? res.data ?? {}
  } catch { /* keep cached */ }
}

// WebSocket 推送更新
const { onMessage } = useWebSocket()
onMessage((msg) => {
  if (msg.cmd === 'pushDashboard' && msg.data) {
    data.value = msg.data
  }
})

onMounted(() => {
  // 延迟加载，等连接就绪
  setTimeout(loadPush, 500)
})
</script>

<style scoped>
.push-dashboard {
  background: var(--bg-secondary);
  border-bottom: 1px solid var(--border);
  flex-shrink: 0;
}

.push-header {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 8px 12px;
  cursor: pointer;
  user-select: none;
}

.push-title {
  font-size: 12px;
  font-weight: 600;
  color: var(--fg-muted);
}

.push-badge {
  background: var(--accent);
  color: var(--bg);
  font-size: 10px;
  font-weight: 700;
  padding: 1px 6px;
  border-radius: 10px;
  min-width: 16px;
  text-align: center;
}

.push-toggle {
  font-size: 10px;
  color: var(--fg-muted);
  margin-left: auto;
}

.push-body {
  padding: 0 12px 8px;
}

.push-section {
  margin-bottom: 6px;
}

.push-section:last-child {
  margin-bottom: 0;
}

.push-section-title {
  font-size: 11px;
  font-weight: 600;
  color: var(--fg-muted);
  margin-bottom: 2px;
}

.urgent .push-section-title { color: #ef4444; }
.warning .push-section-title { color: #f59e0b; }
.info .push-section-title { color: var(--accent); }

.push-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 3px 6px;
  border-radius: 4px;
  cursor: pointer;
  font-size: 12px;
}

.push-item:hover {
  background: var(--border);
}

.push-item-title {
  color: var(--fg);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  flex: 1;
}

.push-item-meta {
  font-size: 10px;
  color: var(--fg-muted);
  white-space: nowrap;
  margin-left: 6px;
}
</style>
