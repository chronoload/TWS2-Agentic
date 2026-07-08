<template>
  <div class="subagent-panel">
    <div class="subagent-header" @click="expanded = !expanded">
      <span class="subagent-icon">{{ roleIcon }}</span>
      <span class="subagent-name">{{ data.agent_name || 'sub_agent' }}</span>
      <span class="subagent-toggle">{{ expanded ? '▼ 收起' : '▶ 展开' }}</span>
      <span class="subagent-status" :class="data.status || 'completed'">{{ statusText }}</span>
    </div>
    <div class="subagent-meta">
      <span>轮次: {{ data.tool_calls_count || 0 }}</span>
      <span>tokens: {{ data.prompt_tokens || 0 }}+{{ data.completion_tokens || 0 }}</span>
      <span>耗时: {{ data.duration_ms || 0 }}ms</span>
    </div>
    <div v-if="expanded" class="subagent-body">
      <div class="subagent-content" v-html="renderSimpleMarkdown(data.content || '')" />
    </div>
    <div v-if="expanded && data.reasoning_content" class="subagent-reasoning">
      <div class="subagent-reasoning-label">💭 推理过程</div>
      <pre class="subagent-reasoning-text">{{ data.reasoning_content.substring(0, 1000) }}</pre>
    </div>
    <div v-if="data.error" class="subagent-error">❌ {{ data.error }}</div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'

interface SubAgentData {
  __sub_agent__: boolean
  agent_name?: string
  role?: string
  status?: string
  content?: string
  reasoning_content?: string
  error?: string
  tool_calls_count?: number
  prompt_tokens?: number
  completion_tokens?: number
  duration_ms?: number
}

const props = defineProps<{
  data: SubAgentData
}>()

const expanded = ref(false)

const roleIcons: Record<string, string> = { coder: '💻', task: '📋', research: '🔍', review: '🔎' }
const roleIcon = computed(() => roleIcons[props.data.role || ''] || '🐝')

const statusTexts: Record<string, string> = { completed: '完成', failed: '失败', cancelled: '已取消' }
const statusText = computed(() => statusTexts[props.data.status || ''] || props.data.status || '完成')

function renderSimpleMarkdown(text: string): string {
  let html = text
  html = html.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
  html = html.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
  html = html.replace(/`([^`]+)`/g, '<code>$1</code>')
  html = html.replace(/^- (.+)$/gm, '<li>$1</li>')
  html = html.replace(/(<li>.*<\/li>\n?)+/g, (match) => `<ul>${match}</ul>`)
  html = html.replace(/\n/g, '<br>')
  return html
}
</script>

<style scoped>
.subagent-panel {
  border: 1px solid var(--border);
  border-radius: 8px;
  margin: 6px 0;
  overflow: hidden;
}

.subagent-header {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 6px 10px;
  cursor: pointer;
  user-select: none;
  background: var(--bg-secondary);
  transition: background 0.15s;
}
.subagent-header:hover {
  background: var(--bg-hover);
}

.subagent-icon { font-size: 14px; }

.subagent-name {
  font-weight: 600;
  color: var(--accent);
  font-size: 12px;
}

.subagent-toggle {
  font-size: 10px;
  color: var(--fg-muted);
  margin-left: 4px;
}

.subagent-status {
  font-size: 10px;
  padding: 1px 6px;
  border-radius: 4px;
  margin-left: auto;
}
.subagent-status.completed { background: rgba(80,200,120,0.15); color: var(--green); }
.subagent-status.failed { background: rgba(240,80,80,0.15); color: #f05050; }
.subagent-status.cancelled { background: rgba(180,180,180,0.15); color: var(--fg-muted); }

.subagent-meta {
  display: flex;
  gap: 8px;
  padding: 4px 10px;
  font-size: 10px;
  color: var(--fg-muted);
  border-bottom: 1px solid var(--border);
}

.subagent-body {
  padding: 8px 10px;
  font-size: 12px;
  line-height: 1.5;
  color: var(--fg);
}

.subagent-content :deep(ul) {
  padding-left: 20px;
  margin: 4px 0;
}

.subagent-content :deep(code) {
  background: rgba(255, 255, 255, 0.1);
  padding: 1px 5px;
  border-radius: 4px;
  font-size: 11px;
}

.subagent-reasoning {
  border-top: 1px solid var(--border);
  padding: 6px 10px;
}

.subagent-reasoning-label {
  color: #e8a840;
  font-weight: 600;
  font-size: 10px;
  margin-bottom: 2px;
}

.subagent-reasoning-text {
  font-size: 10px;
  color: var(--fg-muted);
  white-space: pre-wrap;
  word-break: break-all;
  margin: 0;
  max-height: 150px;
  overflow-y: auto;
}

.subagent-error {
  color: #f05050;
  padding: 6px 10px;
  font-size: 11px;
}
</style>
