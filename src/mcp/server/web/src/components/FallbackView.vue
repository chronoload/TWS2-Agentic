<template>
  <div class="fallback-view">
    <p>该文档格式暂不支持预览</p>
    <p class="hint">请在桌面端查看</p>
  </div>
</template>

<script setup lang="ts">
</script>

<style scoped>
.fallback-view {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  min-height: 200px;
  color: var(--fg-muted);
  font-size: 14px;
}

.hint {
  font-size: 12px;
  margin-top: 4px;
  opacity: 0.7;
}
</style>
