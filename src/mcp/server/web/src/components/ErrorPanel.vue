<template>
  <div class="error-panel" v-if="visible">
    <div class="ep-icon">⚠</div>
    <div class="ep-content">
      <div class="ep-title">{{ title }}</div>
      <div class="ep-message">{{ message }}</div>
    </div>
    <div class="ep-actions">
      <button v-if="retryable" class="ep-btn ep-retry" @click="$emit('retry')">重试</button>
      <button class="ep-btn ep-report" @click="report">报告</button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { injectErrorStyles, showErrorDialog, AppError, UserAction } from '../utils/error'

defineProps<{
  visible: boolean
  title?: string
  message?: string
  retryable?: boolean
  error?: AppError | null
}>()

const emit = defineEmits<{
  retry: []
}>()

injectErrorStyles()

function report() {
  const err = new AppError(message || title || '未知错误', {
    userAction: UserAction.UI_ERROR,
    request: window.location.href,
  })
  showErrorDialog(err)
}
</script>

<style scoped>
.error-panel {
  display: flex;
  align-items: flex-start;
  gap: 12px;
  padding: 16px;
  margin: 16px;
  background: rgba(231, 76, 60, 0.08);
  border: 1px solid rgba(231, 76, 60, 0.3);
  border-radius: 10px;
}

.ep-icon {
  font-size: 24px;
  flex-shrink: 0;
  line-height: 1;
}

.ep-content {
  flex: 1;
  min-width: 0;
}

.ep-title {
  font-size: 14px;
  font-weight: 600;
  color: #e74c3c;
  margin-bottom: 4px;
}

.ep-message {
  font-size: 13px;
  color: var(--fg-muted);
  word-break: break-word;
}

.ep-actions {
  display: flex;
  gap: 6px;
  flex-shrink: 0;
  align-items: center;
}

.ep-btn {
  padding: 6px 12px;
  border-radius: 6px;
  font-size: 12px;
  font-weight: 600;
  cursor: pointer;
  border: 1px solid var(--border);
  transition: all 0.15s;
}

.ep-retry {
  background: var(--accent);
  color: #fff;
  border-color: var(--accent);
}

.ep-retry:hover {
  opacity: 0.9;
}

.ep-report {
  background: var(--bg-secondary);
  color: var(--fg);
}

.ep-report:hover {
  background: var(--bg);
}
</style>
