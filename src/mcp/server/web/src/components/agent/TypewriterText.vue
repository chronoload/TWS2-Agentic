<template>
  <span class="typewriter-container">
    <template v-if="mode === 'instant'">
      {{ displayed }}
    </template>
    <template v-else>
      <span v-for="(char, i) in displayedArray" :key="i" :class="{ 'typewriter-char': true, 'typing': i === displayedArray.length - 1 && cursor }">{{ char }}</span>
      <span v-if="cursor && !done" class="typewriter-cursor">▌</span>
    </template>
  </span>
</template>

<script setup lang="ts">
import { ref, watch, computed, onUnmounted } from 'vue'

const props = withDefaults(defineProps<{
  text: string
  mode?: 'instant' | 'fast' | 'normal' | 'slow'
  cursor?: boolean
}>(), {
  mode: 'instant',
  cursor: true,
})

const emit = defineEmits<{
  done: []
}>()

const SPEED: Record<string, number> = { instant: 0, fast: 8, normal: 25, slow: 50 }

const displayed = ref('')
let timer: ReturnType<typeof setInterval> | null = null
let fullText = ''
let idx = 0
let isInCodeBlock = false

const isTypewriter = computed(() => props.mode !== 'instant')
const displayedArray = computed(() => displayed.value.split(''))

const done = computed(() => displayed.value.length >= (fullText.length || 0))

function tick() {
  if (idx >= fullText.length) {
    if (timer) clearInterval(timer)
    timer = null
    emit('done')
    return
  }
  const remaining = fullText.slice(idx)
  if (remaining.startsWith('```')) {
    isInCodeBlock = !isInCodeBlock
  }
  const chunkSize = isInCodeBlock ? 20 : 1
  const end = Math.min(idx + chunkSize, fullText.length)
  displayed.value = fullText.slice(0, end)
  idx = end
}

function start() {
  stop()
  fullText = props.text
  idx = 0
  displayed.value = ''
  if (props.mode === 'instant') {
    displayed.value = fullText
    emit('done')
    return
  }
  timer = setInterval(tick, SPEED[props.mode] || 25)
}

function stop() {
  if (timer) { clearInterval(timer); timer = null }
}

watch(() => props.text, (val) => {
  if (!val) { displayed.value = ''; return }
  if (isTypewriter.value && val.length > (fullText.length || 0)) {
    fullText = val
  } else {
    start()
  }
}, { immediate: true })

onUnmounted(stop)
</script>

<style scoped>
.typewriter-container {
  white-space: pre-wrap;
  word-break: break-word;
}
.typewriter-char {
  transition: none;
}
.typewriter-cursor {
  animation: blink 1s step-end infinite;
  color: var(--accent);
}
@keyframes blink {
  50% { opacity: 0; }
}
</style>
