<template>
  <div class="tool-call-card" :class="{ 'is-done': tool.status === 'done', 'is-running': tool.status === 'running' }">
    <div class="tool-call-header" @click="expanded = !expanded">
      <span class="tool-status-icon">{{ tool.status === 'running' ? '⏳' : '✅' }}</span>
      <span class="tool-name">{{ tool.name }}</span>
      <span class="tool-expand-icon">{{ expanded ? '▼' : '▶' }}</span>
    </div>
    <div v-if="expanded" class="tool-call-body">
      <div v-if="hasArgs" class="tool-section">
        <div class="tool-section-label">参数</div>
        <pre class="tool-args">{{ formatArgs }}</pre>
      </div>
      <div v-if="tool.result" class="tool-section">
        <div class="tool-section-label">结果</div>
        <pre class="tool-result">{{ tool.result.substring(0, 1000) }}{{ tool.result.length > 1000 ? '...' : '' }}</pre>
      </div>
      <div v-if="tool.checkpointHash" class="tool-section tool-meta">
        <span class="tool-checkpoint-badge" @click="$emit('viewCheckpointDiff', tool.checkpointHash!)">📊 {{ tool.checkpointHash.substring(0, 8) }}</span>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import type { ToolCallInfo } from '../../stores/agentStore'

const props = defineProps<{
  tool: ToolCallInfo
}>()

defineEmits<{
  viewCheckpointDiff: [hash: string]
}>()

const expanded = ref(true)
const hasArgs = computed(() => props.tool.args && Object.keys(props.tool.args).length > 0)
const formatArgs = computed(() => JSON.stringify(props.tool.args, null, 2))
</script>

<style scoped>
.tool-call-card {
  border: 1px solid var(--border);
  border-radius: 8px;
  margin: 6px 0;
  overflow: hidden;
  transition: border-color 0.2s;
}
.tool-call-card.is-running {
  border-color: rgba(250, 204, 21, 0.4);
}
.tool-call-card.is-done {
  border-color: rgba(74, 222, 128, 0.3);
}
.tool-call-header {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 6px 10px;
  cursor: pointer;
  user-select: none;
  font-size: 13px;
}
.tool-status-icon { font-size: 14px; }
.tool-name {
  flex: 1;
  font-family: monospace;
  font-weight: 600;
  color: var(--accent);
}
.tool-expand-icon {
  font-size: 10px;
  color: var(--fg-muted);
}
.tool-call-body {
  border-top: 1px solid var(--border);
  padding: 8px 10px;
}
.tool-section {
  margin-bottom: 6px;
}
.tool-section:last-child { margin-bottom: 0; }
.tool-section-label {
  font-size: 11px;
  color: var(--fg-muted);
  margin-bottom: 3px;
}
.tool-args, .tool-result {
  font-size: 11px;
  font-family: monospace;
  white-space: pre-wrap;
  word-break: break-all;
  margin: 0;
  padding: 4px 6px;
  background: rgba(0,0,0,0.08);
  border-radius: 4px;
  max-height: 150px;
  overflow-y: auto;
}
.tool-meta {
  display: flex;
  gap: 4px;
}
.tool-checkpoint-badge {
  font-size: 10px;
  cursor: pointer;
  padding: 2px 6px;
  border-radius: 4px;
  background: rgba(122,162,247,0.12);
  color: var(--accent);
}
.tool-checkpoint-badge:hover {
  background: rgba(122,162,247,0.25);
}
</style>
