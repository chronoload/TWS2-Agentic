<template>
  <div class="ecosystem-view">
    <div class="left-col">
      <EcoRecordPanel />
      <EcoThreadPanel style="margin-top: 12px;" />
    </div>
    <div class="right-col">
      <EcoWorldMap />
    </div>
  </div>
</template>

<script setup lang="ts">
import EcoRecordPanel from '../components/EcoRecordPanel.vue'
import EcoThreadPanel from '../components/EcoThreadPanel.vue'
import EcoWorldMap from '../components/EcoWorldMap.vue'
</script>

<style scoped>
.ecosystem-view {
  display: grid; grid-template-columns: 340px 1fr; gap: 12px;
  padding: 12px; height: 100%; box-sizing: border-box; overflow: auto;
}
.left-col { display: flex; flex-direction: column; }
.right-col { min-width: 0; }
</style>
