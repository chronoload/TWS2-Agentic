<template>
  <div class="toast-container">
    <transition-group name="toast">
      <div
        v-for="t in toasts"
        :key="t.id"
        class="toast"
        :class="'toast-' + t.type"
        @click="dismiss(t.id)"
      >
        <span class="toast-icon">{{ iconMap[t.type] }}</span>
        <span class="toast-msg">{{ t.message }}</span>
      </div>
    </transition-group>
  </div>
</template>

<script setup lang="ts">
import { useToast } from '../composables/useToast'

const { toasts, dismiss } = useToast()

const iconMap: Record<string, string> = {
  success: '✓',
  error: '✕',
  warning: '⚠',
  info: 'ℹ',
}
</script>

<style scoped>
.toast-container {
  position: fixed;
  bottom: 68px;
  left: 50%;
  transform: translateX(-50%);
  z-index: 9999;
  display: flex;
  flex-direction: column;
  gap: 8px;
  pointer-events: none;
  max-width: 90vw;
}

.toast {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 16px;
  border-radius: 8px;
  font-size: 13px;
  line-height: 1.4;
  color: #fff;
  cursor: pointer;
  pointer-events: auto;
  box-shadow: 0 4px 12px rgba(0,0,0,0.25);
  white-space: pre-wrap;
  word-break: break-word;
  backdrop-filter: blur(8px);
}

.toast-success { background: rgba(34,197,94,0.92); }
.toast-error   { background: rgba(239,68,68,0.92); }
.toast-warning { background: rgba(234,179,8,0.92); color: #1a1a1a; }
.toast-info    { background: rgba(59,130,246,0.92); }

.toast-icon { font-size: 15px; flex-shrink: 0; }
.toast-msg  { flex: 1; }

.toast-enter-active,
.toast-leave-active {
  transition: all 0.3s ease;
}
.toast-enter-from {
  opacity: 0;
  transform: translateY(16px);
}
.toast-leave-to {
  opacity: 0;
  transform: translateY(-8px);
}
</style>
