<template>
  <div v-if="errors.length" class="extraction-errors">
    <button class="ee-toggle" @click="expanded = !expanded">
      <span class="ee-icon">⚠</span>
      数据解析异常（{{ errors.length }} 项）
      <span class="ee-arrow">{{ expanded ? '▼' : '▶' }}</span>
    </button>
    <div v-if="expanded" class="ee-body">
      <div v-for="(err, i) in errors" :key="i" class="ee-item">{{ err }}</div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'

defineProps<{ errors: string[] }>()

const expanded = ref(false)
</script>

<style scoped>
.extraction-errors {
  margin: 8px 16px;
  font-size: 12px;
}
.ee-toggle {
  width: 100%;
  padding: 8px 12px;
  background: rgba(230, 126, 34, 0.08);
  border: 1px solid rgba(230, 126, 34, 0.2);
  border-radius: 6px;
  color: #e67e22;
  cursor: pointer;
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
}
.ee-toggle:hover {
  background: rgba(230, 126, 34, 0.14);
}
.ee-icon {
  font-size: 14px;
}
.ee-arrow {
  margin-left: auto;
}
.ee-body {
  margin-top: 4px;
  background: var(--bg-secondary);
  border: 1px solid var(--border);
  border-radius: 6px;
  padding: 8px 12px;
  max-height: 200px;
  overflow-y: auto;
}
.ee-item {
  padding: 3px 0;
  color: #e67e22;
  font-size: 11px;
  word-break: break-all;
  border-bottom: 1px solid var(--border);
}
.ee-item:last-child {
  border-bottom: none;
}
</style>
