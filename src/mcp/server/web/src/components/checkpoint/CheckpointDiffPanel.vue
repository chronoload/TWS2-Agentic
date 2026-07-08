<template>
  <div class="diff-panel">
    <div v-if="loading" class="diff-state">加载差异中...</div>
    <div v-else-if="!diffData || diffData.length === 0" class="diff-state diff-empty">无差异</div>
    <div v-else>
      <div v-if="summary" class="diff-summary-bar">
        <span class="diff-add">+{{ summary.additions }}</span>
        <span class="diff-del">-{{ summary.deletions }}</span>
        <span class="diff-files">{{ summary.files_changed }} 个文件</span>
      </div>
      <div v-for="d in diffData" :key="d.path" class="diff-file-entry">
        <div class="diff-file-header" @click="toggleFile(d.path)">
          <span :class="'diff-badge diff-' + d.status">{{ statusLabel(d.status) }}</span>
          <span class="diff-file-path">{{ d.path }}</span>
          <span class="diff-file-stats">+{{ d.additions || 0 }} -{{ d.deletions || 0 }}</span>
          <span class="diff-toggle">{{ expandedFiles.has(d.path) ? '▼' : '▶' }}</span>
        </div>
        <div v-if="expandedFiles.has(d.path)" class="diff-file-body">
          <pre v-if="d.diff" class="diff-code">{{ d.diff }}</pre>
          <div v-else class="diff-state diff-empty">（无文本差异）</div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import type { CheckpointDiff, CheckpointSummary } from '../../stores/checkpointStore'

defineProps<{
  diffData: CheckpointDiff[]
  summary: CheckpointSummary | null
  loading: boolean
}>()

const expandedFiles = ref(new Set<string>())

function toggleFile(path: string) {
  if (expandedFiles.value.has(path)) {
    expandedFiles.value.delete(path)
  } else {
    expandedFiles.value.add(path)
  }
}

function statusLabel(s: string): string {
  return s === 'A' ? '新增' : s === 'D' ? '删除' : '修改'
}
</script>

<style scoped>
.diff-panel {
  margin-top: 6px;
  border-radius: 6px;
  background: var(--bg-secondary);
  max-height: 500px;
  overflow-y: auto;
}
.diff-state {
  font-size: 11px;
  color: var(--fg-muted);
  padding: 8px;
  text-align: center;
}
.diff-summary-bar {
  display: flex;
  gap: 8px;
  padding: 6px 8px;
  font-size: 11px;
  border-bottom: 1px solid var(--border);
}
.diff-add { color: #4ade80; font-weight: 600; }
.diff-del { color: #ef4444; font-weight: 600; }
.diff-files { color: var(--fg-muted); }
.diff-file-entry {
  border-bottom: 1px solid var(--border);
}
.diff-file-entry:last-child { border-bottom: none; }
.diff-file-header {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 5px 8px;
  cursor: pointer;
  font-size: 11px;
}
.diff-file-header:hover {
  background: rgba(255,255,255,0.03);
}
.diff-badge {
  font-size: 9px;
  font-weight: 700;
  padding: 1px 4px;
  border-radius: 3px;
}
.diff-badge.M { background: rgba(250,204,21,0.2); color: #facc15; }
.diff-badge.A { background: rgba(74,222,128,0.2); color: #4ade80; }
.diff-badge.D { background: rgba(239,68,68,0.2); color: #ef4444; }
.diff-file-path {
  flex: 1;
  font-family: monospace;
  color: var(--fg);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.diff-file-stats {
  color: var(--fg-muted);
  font-size: 10px;
}
.diff-toggle {
  font-size: 9px;
  color: var(--fg-muted);
}
.diff-file-body {
  border-top: 1px solid var(--border);
}
.diff-code {
  font-size: 10px;
  font-family: monospace;
  white-space: pre;
  overflow-x: auto;
  margin: 0;
  padding: 6px;
  background: rgba(0,0,0,0.1);
  max-height: 300px;
  overflow-y: auto;
  color: var(--fg-muted);
}
</style>
