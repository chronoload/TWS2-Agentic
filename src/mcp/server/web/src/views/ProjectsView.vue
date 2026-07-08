<template>
  <div class="view">
    <header class="view-header">
      <h1>项目</h1>
    </header>
    <div class="view-body">
      <div v-if="loading" class="loading">加载中...</div>
      <div v-else-if="projects.length === 0" class="empty">暂无项目</div>
      <div v-else class="project-list">
        <div v-for="proj in projects" :key="proj.path || proj.name" class="project-card" @click="openProject(proj)">
          <div class="project-header">
            <span class="project-icon">🚀</span>
            <div class="project-info">
              <span class="project-title">{{ proj.title || proj.name || '未命名项目' }}</span>
              <span v-if="proj.path" class="project-path">{{ proj.path }}</span>
            </div>
          </div>
          <div v-if="proj.file_count" class="project-meta">{{ proj.file_count }} 个文件</div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { getProjects } from '../api'

const projects = ref<any[]>([])
const loading = ref(true)

onMounted(async () => {
  const bootstrap = (window as any).__TS2_BOOTSTRAP__
  if (bootstrap?.projects) {
    projects.value = Array.isArray(bootstrap.projects) ? bootstrap.projects : []
    delete bootstrap.projects
  }
  try {
    const res = await getProjects()
    const data = res.data?.data ?? res.data
    projects.value = Array.isArray(data) ? data : []
  } catch {
    // keep cached
  } finally {
    loading.value = false
  }
})

function openProject(proj: any) {
  if (proj.path) {
    window.location.hash = `/files`
  }
}
</script>

<style scoped>
.project-list {
  padding: 12px;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.project-card {
  background: var(--card);
  border: 1px solid var(--border);
  border-radius: 10px;
  padding: 14px;
  cursor: pointer;
  transition: border-color 0.15s;
}

.project-card:hover {
  border-color: var(--accent);
}

.project-header {
  display: flex;
  align-items: center;
  gap: 10px;
}

.project-icon {
  font-size: 20px;
}

.project-info {
  flex: 1;
  min-width: 0;
}

.project-title {
  display: block;
  font-size: 15px;
  font-weight: 600;
  color: var(--fg);
}

.project-path {
  display: block;
  font-size: 11px;
  color: var(--fg-muted);
  margin-top: 2px;
}

.project-meta {
  font-size: 12px;
  color: var(--fg-muted);
  margin-top: 6px;
  padding-left: 30px;
}

.loading, .empty {
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 200px;
  color: var(--fg-muted);
  font-size: 14px;
}
</style>
