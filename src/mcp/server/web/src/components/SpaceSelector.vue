<template>
  <div class="space-selector" ref="containerRef">
    <button class="space-trigger" @click="open = !open">
      <span class="space-trigger-label">{{ activeName }}</span>
      <span class="space-trigger-arrow">▾</span>
    </button>

    <div v-if="open" class="space-dropdown" @click.stop>
      <div
        v-for="sp in spacesStore.spaces"
        :key="sp.id"
        class="space-option"
        :class="{ active: sp.id === spacesStore.activeSpaceId }"
        @click="select(sp.id)"
      >
        <span class="space-opt-name">{{ sp.name }}</span>
        <span v-if="counts?.[sp.id] !== undefined" class="space-opt-count">{{ counts[sp.id] }}</span>
        <span v-if="sp.id === spacesStore.activeSpaceId" class="space-opt-check">✓</span>
        <button
          v-if="spacesStore.spaces.length > 1"
          class="space-opt-del"
          @click.stop="remove(sp.id)"
          title="删除空间"
        >✕</button>
      </div>
      <div class="space-dropdown-divider"></div>
      <div class="space-option space-option-new" @click="startCreate">
        <span style="font-weight:600">＋ 新建空间</span>
      </div>
      <div v-if="showInput" class="space-dropdown-input">
        <input
          v-model="newName"
          class="space-input"
          placeholder="空间名称"
          @keyup.enter="doCreate"
          ref="inputRef"
        />
        <button class="space-input-ok" @click="doCreate">确定</button>
        <button class="space-input-cancel" @click="showInput = false">取消</button>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted, nextTick } from 'vue'
import { useSpacesStore } from '../stores/spaces'

const props = defineProps<{
  counts?: Record<string, number>
}>()

const spacesStore = useSpacesStore()

const open = ref(false)
const showInput = ref(false)
const newName = ref('')
const inputRef = ref<HTMLInputElement | null>(null)
const containerRef = ref<HTMLElement | null>(null)

const activeName = computed(() => spacesStore.activeSpace?.name || '空间')

function select(id: string) {
  spacesStore.selectSpace(id)
  open.value = false
}

function remove(id: string) {
  spacesStore.removeSpace(id)
}

function startCreate() {
  showInput.value = true
  newName.value = ''
  nextTick(() => inputRef.value?.focus())
}

function doCreate() {
  const n = newName.value.trim()
  if (!n) return
  spacesStore.addSpace(n)
  showInput.value = false
  newName.value = ''
}

function onClickOutside(e: MouseEvent) {
  if (containerRef.value && !containerRef.value.contains(e.target as Node)) {
    open.value = false
    showInput.value = false
  }
}

onMounted(() => document.addEventListener('click', onClickOutside))
onUnmounted(() => document.removeEventListener('click', onClickOutside))
</script>

<style scoped>
.space-selector {
  position: relative;
  display: inline-block;
}
.space-trigger {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  background: var(--bg-secondary);
  border: 1px solid var(--border);
  border-radius: 6px;
  padding: 4px 10px;
  font-size: 13px;
  color: var(--fg);
  cursor: pointer;
  white-space: nowrap;
}
.space-trigger:hover {
  border-color: var(--accent);
  background: var(--bg-tertiary);
}
.space-trigger-label {
  font-weight: 600;
  max-width: 120px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.space-trigger-arrow {
  font-size: 10px;
  color: var(--fg-muted);
}
.space-dropdown {
  position: absolute;
  top: 100%;
  left: 0;
  z-index: 300;
  min-width: 180px;
  margin-top: 4px;
  background: var(--bg-secondary);
  border: 1px solid var(--border);
  border-radius: 8px;
  box-shadow: 0 4px 16px rgba(0,0,0,0.35);
  overflow: hidden;
}
.space-option {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 8px 12px;
  font-size: 13px;
  color: var(--fg);
  cursor: pointer;
  transition: background 0.1s;
}
.space-option:hover { background: rgba(255,255,255,0.05); }
.space-option.active {
  background: rgba(122,162,247,0.12);
  color: var(--accent);
}
.space-opt-name { flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.space-opt-count {
  font-size: 11px;
  color: var(--fg-muted);
  background: rgba(255,255,255,0.06);
  padding: 0 6px;
  border-radius: 8px;
}
.space-opt-check { color: var(--accent); font-weight: 700; }
.space-opt-del {
  background: transparent; border: none; color: var(--fg-muted);
  font-size: 11px; cursor: pointer; padding: 2px 4px; border-radius: 3px;
}
.space-opt-del:hover { background: rgba(239,68,68,0.15); color: #ef4444; }
.space-dropdown-divider { height: 1px; background: var(--border); margin: 4px 0; }
.space-option-new { color: var(--accent); }
.space-dropdown-input {
  display: flex;
  gap: 4px;
  padding: 6px 10px 10px;
}
.space-input {
  flex: 1;
  background: var(--bg);
  color: var(--fg);
  border: 1px solid var(--border);
  border-radius: 4px;
  padding: 4px 8px;
  font-size: 12px;
  min-width: 0;
}
.space-input-ok, .space-input-cancel {
  background: var(--accent);
  color: var(--bg);
  border: none;
  border-radius: 4px;
  padding: 4px 8px;
  font-size: 11px;
  cursor: pointer;
}
.space-input-cancel { background: transparent; color: var(--fg-muted); }
</style>
