<template>
  <div class="exec-timer">
    <div class="exec-timer__display" :class="{ 'exec-timer__display--warning': isWarning, 'exec-timer__display--done': isDone }">
      {{ formattedTime }}
    </div>
    <div class="exec-timer__controls">
      <button v-if="!isRunning && !isDone" class="exec-timer__btn exec-timer__btn--start" @click="start">
        {{ hasStarted ? '继续' : '开始' }}
      </button>
      <button v-if="isRunning" class="exec-timer__btn exec-timer__btn--pause" @click="pause">
        暂停
      </button>
      <button v-if="hasStarted" class="exec-timer__btn exec-timer__btn--stop" @click="stop">
        停止
      </button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, onUnmounted } from 'vue'

const props = withDefaults(defineProps<{
  duration?: number
  autoStart?: boolean
}>(), {
  duration: 0,
  autoStart: false,
})

// 安全地获取持续时间，确保是有效数字
const safeDuration = computed(() => {
  let val = props.duration
  // 多重安全检查
  if (val === null || val === undefined || val === '') {
    return 0
  }
  const num = Number(val)
  return Number.isFinite(num) && num >= 0 ? num : 0
})

const emit = defineEmits<{
  started: []
  paused: []
  stopped: []
  completed: []
}>()

const totalSeconds = computed(() => safeDuration.value * 60)
const remaining = ref(0)  // 初始化为 0，在 watch 中设置
const isRunning = ref(false)
const hasStarted = ref(false)
let intervalId: ReturnType<typeof setInterval> | null = null

// 确保 remaining 始终是有效数字
const safeRemaining = computed(() => {
  const val = remaining.value
  if (val === null || val === undefined) return 0
  const num = Number(val)
  return Number.isFinite(num) ? num : 0
})

const isDone = computed(() => safeRemaining.value <= 0)
const isWarning = computed(() => totalSeconds.value > 0 && safeRemaining.value <= 60 && safeRemaining.value > 0)

const formattedTime = computed(() => {
  const mins = Math.floor(Math.abs(safeRemaining.value) / 60)
  const secs = Math.abs(safeRemaining.value) % 60
  return `${String(mins).padStart(2, '0')}:${String(secs).padStart(2, '0')}`
})

function start() {
  if (isDone.value) return
  isRunning.value = true
  hasStarted.value = true
  emit('started')
  intervalId = setInterval(() => {
    if (totalSeconds.value > 0) {
      remaining.value = Math.max(0, safeRemaining.value - 1)
      if (safeRemaining.value <= 0) {
        remaining.value = 0
        clearInterval(intervalId!)
        intervalId = null
        isRunning.value = false
        emit('completed')
      }
    } else {
      remaining.value = safeRemaining.value + 1
    }
  }, 1000)
}

function pause() {
  isRunning.value = false
  if (intervalId) {
    clearInterval(intervalId)
    intervalId = null
  }
  emit('paused')
}

function stop() {
  isRunning.value = false
  if (intervalId) {
    clearInterval(intervalId)
    intervalId = null
  }
  hasStarted.value = false
  remaining.value = totalSeconds.value
  emit('stopped')
}

// 监听 safeDuration 变化并初始化
watch(safeDuration, (newVal) => {
  if (!hasStarted.value) {
    remaining.value = newVal * 60
  }
}, { immediate: true })

watch(() => props.autoStart, (val) => {
  if (val && !hasStarted.value) {
    start()
  }
})

onUnmounted(() => {
  if (intervalId) clearInterval(intervalId)
})
</script>

<style scoped>
.exec-timer {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 16px;
  padding: 20px;
}

.exec-timer__display {
  font-size: 48px;
  font-weight: 700;
  font-variant-numeric: tabular-nums;
  color: var(--fg);
  letter-spacing: 2px;
}

.exec-timer__display--warning {
  color: var(--warning);
}

.exec-timer__display--done {
  color: var(--success);
}

.exec-timer__controls {
  display: flex;
  gap: 10px;
}

.exec-timer__btn {
  min-width: 72px;
  font-size: 14px;
  font-weight: 500;
}

.exec-timer__btn--start {
  background: var(--success);
  color: var(--bg);
}

.exec-timer__btn--start:hover {
  background: #b5e88c;
}

.exec-timer__btn--pause {
  background: var(--warning);
  color: var(--bg);
}

.exec-timer__btn--pause:hover {
  background: #f0c674;
}

.exec-timer__btn--stop {
  background: var(--danger);
  color: var(--bg);
}

.exec-timer__btn--stop:hover {
  background: #f9a4b4;
}
</style>
