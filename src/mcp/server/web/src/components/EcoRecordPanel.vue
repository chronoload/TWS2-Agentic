<template>
  <div class="eco-record-panel">
    <div class="panel-header">
      <span class="panel-title">📝 记录</span>
    </div>
    <div class="input-area">
      <textarea
        v-model="text"
        class="eco-input"
        placeholder="输入你今天做的学术活动..."
        rows="3"
        @keydown.enter.ctrl="submit"
      ></textarea>
      <div class="input-actions">
        <span class="hint">Ctrl+Enter 提交</span>
        <button class="btn-submit" @click="submit" :disabled="!text.trim() || submitting">
          {{ submitting ? '…' : '记录' }}
        </button>
      </div>
    </div>
    <div v-if="result" class="result-area">
      <div v-if="result.new_concept_ids?.length" class="result-section">
        <span class="result-label">新概念:</span>
        <span class="concept-tag" v-for="cid in result.new_concept_ids" :key="cid">
          {{ (store.concepts[cid as string]?.label ?? (cid as string).slice(0, 8)) }}
        </span>
      </div>
      <div v-if="result.depth_changes && Object.keys(result.depth_changes).length" class="result-section">
        <span class="result-label">加固:</span>
        <span class="reinforce-item" v-for="(delta, cid) in result.depth_changes" :key="cid">
          {{ store.concepts[cid as string]?.label ?? (cid as string).slice(0, 6) }}+{{ delta.toFixed(2) }}
        </span>
      </div>
      <div v-if="result.narrative" class="result-narrative">{{ result.narrative }}</div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { useEcosystemStore } from '../stores/ecosystem'

const store = useEcosystemStore()
const text = ref('')
const submitting = ref(false)
const result = ref<any>(null)

async function submit() {
  if (!text.value.trim() || submitting.value) return
  submitting.value = true
  result.value = null
  try {
    const res = await store.doRecord(text.value)
    result.value = res
    if (res?.narrative) text.value = ''
  } finally {
    submitting.value = false
  }
}
</script>

<style scoped>
.eco-record-panel { background: var(--bg-secondary); border-radius: 8px; padding: 12px; }
.panel-header { margin-bottom: 8px; }
.panel-title { font-weight: 600; font-size: 14px; }
.eco-input {
  width: 100%; box-sizing: border-box; resize: vertical;
  background: var(--bg); border: 1px solid var(--border); border-radius: 6px;
  padding: 8px 10px; color: var(--fg); font-size: 13px; font-family: inherit;
}
.eco-input:focus { outline: none; border-color: var(--accent); }
.input-actions { display: flex; justify-content: space-between; align-items: center; margin-top: 6px; }
.hint { font-size: 11px; color: var(--fg-muted); }
.btn-submit {
  background: var(--accent); color: #fff; border: none; border-radius: 4px;
  padding: 4px 14px; font-size: 13px; cursor: pointer;
}
.btn-submit:disabled { opacity: 0.5; cursor: default; }
.result-area { margin-top: 10px; padding: 8px; background: var(--bg); border-radius: 6px; font-size: 12px; }
.result-section { margin-bottom: 4px; display: flex; flex-wrap: wrap; gap: 4px; align-items: center; }
.result-label { color: var(--fg-muted); font-size: 11px; }
.concept-tag { background: var(--accent); color: #fff; padding: 1px 6px; border-radius: 3px; font-size: 11px; }
.reinforce-item { background: var(--bg-secondary); padding: 1px 6px; border-radius: 3px; font-size: 11px; }
.result-narrative { margin-top: 4px; color: var(--fg-muted); font-style: italic; }
</style>
