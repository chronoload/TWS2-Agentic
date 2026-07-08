<template>
  <nav class="app-menu">
    <div class="menu-header">
      <span class="menu-logo">TS2</span>
      <span class="menu-subtitle">视频</span>
    </div>
    <div class="menu-sections">
      <div class="menu-group">
        <router-link to="/videos/search" class="menu-item" active-class="active">
          <span class="menu-icon">🔍</span>
          <span class="menu-label">搜索</span>
        </router-link>
        <router-link to="/videos/subs" class="menu-item" active-class="active">
          <span class="menu-icon">📺</span>
          <span class="menu-label">订阅</span>
          <span v-if="subCount > 0" class="menu-badge">{{ subCount }}</span>
        </router-link>
        <router-link to="/videos/bookmarks" class="menu-item" active-class="active">
          <span class="menu-icon">📑</span>
          <span class="menu-label">播放列表</span>
        </router-link>
        <router-link to="/videos" class="menu-item" active-class="active">
          <span class="menu-icon">🎬</span>
          <span class="menu-label">旧版</span>
        </router-link>
      </div>
    </div>
  </nav>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useSubscriptionsStore } from '../stores/subscriptions'

const subStore = useSubscriptionsStore()
const subCount = computed(() => subStore.subscriptions.length)
</script>

<style scoped>
.app-menu {
  width: 200px;
  background: var(--bg-secondary);
  border-right: 1px solid var(--border);
  display: flex;
  flex-direction: column;
  flex-shrink: 0;
  height: 100%;
  overflow-y: auto;
}
.menu-header {
  padding: 16px;
  border-bottom: 1px solid var(--border);
}
.menu-logo {
  font-size: 18px;
  font-weight: 700;
  color: var(--accent);
}
.menu-subtitle {
  font-size: 11px;
  color: var(--fg-muted);
  margin-left: 8px;
}
.menu-sections {
  padding: 8px;
  flex: 1;
}
.menu-group {
  display: flex;
  flex-direction: column;
  gap: 2px;
}
.menu-item {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px 12px;
  border-radius: 8px;
  text-decoration: none;
  color: var(--fg);
  font-size: 14px;
  transition: background 0.15s;
}
.menu-item:hover {
  background: var(--border);
}
.menu-item.active {
  background: var(--accent);
  color: var(--bg);
  font-weight: 600;
}
.menu-icon {
  font-size: 16px;
  flex-shrink: 0;
  width: 20px;
  text-align: center;
}
.menu-label {
  flex: 1;
}
.menu-badge {
  font-size: 11px;
  font-weight: 600;
  color: var(--accent);
  background: var(--bg);
  padding: 1px 6px;
  border-radius: 8px;
  min-width: 18px;
  text-align: center;
}
</style>
