<template>
  <div class="eco-thread-panel">
    <div class="panel-header">
      <span class="panel-title">🧵 研究线程</span>
      <button class="btn-sm" @click="store.fetchState()" :title="'刷新'">↻</button>
    </div>
    <div v-if="threadList.length === 0" class="empty-state">暂无线程</div>
    <div v-for="thread in threadList" :key="thread.id" class="thread-card"
         :class="{ archived: thread.is_archived }">
      <div class="thread-header" @click="toggleExpand(thread.id)">
        <span class="thread-label">{{ thread.label }}</span>
        <span class="thread-meta">
          C{{ thread.clarity.toFixed(1) }} E{{ thread.entropy.toFixed(2) }}
        </span>
      </div>
      <div v-if="expanded[thread.id]" class="thread-body">
        <div v-if="thread.description" class="thread-desc">{{ thread.description }}</div>
        <div class="concept-list">
          <div v-for="cid in thread.concept_ids" :key="cid"
               class="concept-mini"
               :class="{ fossilized: getConcept(cid)?.is_fossilized }"
               @click="selectConcept(cid)">
            <span class="c-label">{{ getConcept(cid)?.label ?? cid.slice(0, 8) }}</span>
            <span class="c-stats">d{{ getConcept(cid)?.depth.toFixed(1) }} f{{ getConcept(cid)?.freshness.toFixed(1) }}</span>
          </div>
        </div>
        <div class="thread-actions">
          <button class="btn-sm" @click="runExpress(thread.concept_ids)">📝 表达</button>
        </div>
      </div>
    </div>
    <div v-if="store.error" class="error-bar">{{ store.error }}</div>
  </div>
</template>

<script setup lang="ts">
import { computed, reactive } from 'vue'
import { useEcosystemStore } from '../stores/ecosystem'

const store = useEcosystemStore()
const expanded = reactive<Record<string, boolean>>({})

const threadList = computed(() =>
  Object.values(store.threads).sort((a, b) => b.momentum - a.momentum)
)

function toggleExpand(id: string) { expanded[id] = !expanded[id] }

function getConcept(id: string) { return store.concepts[id] }

function selectConcept(_id: string) {
  // Could emit or navigate to concept detail
}

async function runExpress(conceptIds: string[]) {
  await store.doExpress(conceptIds)
}
</script>

<style scoped>
.eco-thread-panel { background: var(--bg-secondary); border-radius: 8px; padding: 12px; }
.panel-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; }
.panel-title { font-weight: 600; font-size: 14px; }
.btn-sm { background: none; border: 1px solid var(--border); border-radius: 4px; color: var(--fg); padding: 2px 8px; font-size: 12px; cursor: pointer; }
.btn-sm:hover { background: var(--bg); }
.empty-state { color: var(--fg-muted); font-size: 13px; text-align: center; padding: 20px 0; }
.thread-card { background: var(--bg); border-radius: 6px; margin-bottom: 6px; overflow: hidden; }
.thread-card.archived { opacity: 0.5; }
.thread-header { display: flex; justify-content: space-between; padding: 8px 10px; cursor: pointer; font-size: 13px; }
.thread-header:hover { background: var(--bg-secondary); }
.thread-label { font-weight: 500; }
.thread-meta { color: var(--fg-muted); font-size: 11px; }
.thread-body { padding: 0 10px 8px; }
.thread-desc { font-size: 11px; color: var(--fg-muted); margin-bottom: 6px; }
.concept-list { display: flex; flex-wrap: wrap; gap: 4px; margin-bottom: 6px; }
.concept-mini {
  display: flex; gap: 4px; align-items: center;
  background: var(--bg-secondary); padding: 2px 6px; border-radius: 4px;
  font-size: 11px; cursor: pointer;
}
.concept-mini.fossilized { opacity: 0.4; text-decoration: line-through; }
.c-label { font-weight: 500; }
.c-stats { color: var(--fg-muted); font-size: 10px; }
.thread-actions { display: flex; gap: 4px; }
.error-bar { margin-top: 6px; padding: 4px 8px; background: var(--danger); color: #fff; border-radius: 4px; font-size: 12px; }
</style>
