<template>
  <div class="view">
    <header class="view-header">
      <h1>统计</h1>
    </header>
    <div class="view-body stats-body">
      <div v-if="loading" class="loading">加载中...</div>
      <template v-else>
        <!-- 今日概览 -->
        <div class="stats-section">
          <h2 class="section-title">今日概览</h2>
          <div class="stats-grid">
            <div class="stat-card">
              <span class="stat-value">{{ pushData?.today_stats?.overdue_tasks_count ?? '-' }}</span>
              <span class="stat-label">超期任务</span>
            </div>
            <div class="stat-card">
              <span class="stat-value">{{ pushData?.today_stats?.due_tasks_count ?? '-' }}</span>
              <span class="stat-label">近期截止</span>
            </div>
            <div class="stat-card">
              <span class="stat-value">{{ pushData?.today_stats?.due_reviews_count ?? '-' }}</span>
              <span class="stat-label">待复习</span>
            </div>
          </div>
        </div>

        <!-- 课程统计 -->
        <div v-if="courseStats" class="stats-section">
          <h2 class="section-title">课程统计</h2>
          <div class="stats-grid">
            <div class="stat-card">
              <span class="stat-value">{{ courseStats.total_courses ?? '-' }}</span>
              <span class="stat-label">课程数</span>
            </div>
            <div class="stat-card">
              <span class="stat-value">{{ courseStats.total_lessons ?? '-' }}</span>
              <span class="stat-label">总课时</span>
            </div>
            <div class="stat-card">
              <span class="stat-value">{{ courseStats.complete_count ?? '-' }}</span>
              <span class="stat-label">已完成</span>
            </div>
            <div class="stat-card">
              <span class="stat-value">{{ courseStats.total_focus_hours?.toFixed(1) ?? '-' }}</span>
              <span class="stat-label">学时</span>
            </div>
          </div>
        </div>

        <!-- 服务器信息 -->
        <div v-if="serverInfo" class="stats-section">
          <h2 class="section-title">服务器</h2>
          <div class="info-list">
            <div class="info-row">
              <span class="info-label">版本</span>
              <span class="info-value">{{ serverInfo.version }}</span>
            </div>
            <div class="info-row">
              <span class="info-label">IP</span>
              <span class="info-value">{{ serverInfo.local_ip }}:{{ serverInfo.port }}</span>
            </div>
            <div class="info-row">
              <span class="info-label">运行时间</span>
              <span class="info-value">{{ formatUptime(serverInfo.uptime) }}</span>
            </div>
          </div>
        </div>
      </template>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import api from '../api'

const loading = ref(true)
const pushData = ref<any>(null)
const courseStats = ref<any>(null)
const serverInfo = ref<any>(null)

function formatUptime(seconds: number): string {
  const h = Math.floor(seconds / 3600)
  const m = Math.floor((seconds % 3600) / 60)
  if (h > 24) return `${Math.floor(h / 24)}天${h % 24}时`
  if (h > 0) return `${h}时${m}分`
  return `${m}分`
}

onMounted(async () => {
  const bootstrap = (window as any).__TS2_BOOTSTRAP__
  if (bootstrap) {
    pushData.value = bootstrap.push || null
    serverInfo.value = bootstrap.server || null
  }
  try {
    const [pushRes, statsRes] = await Promise.all([
      api.get('/api/push/dashboard'),
      api.get('/api/data/courses/stats'),
    ])
    pushData.value = pushRes.data?.data ?? pushRes.data
    courseStats.value = statsRes.data?.data ?? statsRes.data
  } catch { /* keep cached */ }
  finally {
    loading.value = false
  }
})
</script>

<style scoped>
.stats-body {
  padding: 12px;
}

.stats-section {
  margin-bottom: 20px;
}

.section-title {
  font-size: 13px;
  font-weight: 600;
  color: var(--fg-muted);
  margin-bottom: 10px;
  text-transform: uppercase;
  letter-spacing: 0.5px;
}

.stats-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(100px, 1fr));
  gap: 8px;
}

.stat-card {
  background: var(--card);
  border: 1px solid var(--border);
  border-radius: 10px;
  padding: 14px 12px;
  text-align: center;
}

.stat-value {
  display: block;
  font-size: 24px;
  font-weight: 700;
  color: var(--fg);
}

.stat-label {
  display: block;
  font-size: 11px;
  color: var(--fg-muted);
  margin-top: 4px;
}

.info-list {
  background: var(--card);
  border: 1px solid var(--border);
  border-radius: 10px;
  overflow: hidden;
}

.info-row {
  display: flex;
  justify-content: space-between;
  padding: 10px 14px;
  border-bottom: 1px solid var(--border);
  font-size: 13px;
}

.info-row:last-child {
  border-bottom: none;
}

.info-label {
  color: var(--fg-muted);
}

.info-value {
  color: var(--fg);
  font-family: monospace;
}

.loading {
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 200px;
  color: var(--fg-muted);
  font-size: 14px;
}
</style>
