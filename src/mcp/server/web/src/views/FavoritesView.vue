<template>
  <div class="lpl-view">
    <div class="lpl-header">
      <h3 class="section-title">我的合集</h3>
      <button class="create-btn" @click="showCreateDialog = true">＋ 新建合集</button>
    </div>
    <div v-if="store.localPlaylists.length === 0 && store.remotePlaylists.length === 0 && store.favoritesItems.length === 0" class="placeholder">还没有任何合集或收藏的视频</div>

    <!-- 收藏视频 -->
    <div v-if="store.favoritesItems.length" class="remote-section">
      <h4 class="subsection-title">收藏视频 ({{ store.favoritesItems.length }})</h4>
      <div class="grid">
        <VideoCard v-for="item in store.favoritesItems" :key="item.url" :item="item" @cardClick="onVideoClick(item)" />
      </div>
    </div>

    <!-- 远程播放列表 -->
    <div v-if="store.remotePlaylists.length" class="remote-section">
      <h4 class="subsection-title">收藏的播放列表</h4>
      <div class="remote-list">
        <div v-for="pl in store.remotePlaylists" :key="pl.url" class="remote-item" @click="router.push({ name: 'video-player', query: { url: pl.url } })">
          <img :src="proxyImageUrl(pl.thumbnailUrl)" class="remote-thumb" loading="lazy" @error="hideThumb" />
          <div class="remote-info">
            <div class="remote-name">{{ pl.name }}</div>
            <div class="remote-meta">{{ pl.uploaderName }} · {{ pl.streamCount }} 视频</div>
          </div>
          <button class="remove-btn" @click.stop="store.unbookmarkRemote(pl.url)">✕</button>
        </div>
      </div>
    </div>
    <div v-for="pl in store.localPlaylists" :key="pl.id" class="lpl-card">
      <div class="lpl-title-row">
        <span class="lpl-name" @click="toggleExpand(pl.id)">{{ pl.name }}</span>
        <span class="lpl-count">{{ pl.items.length }} 个视频</span>
        <div class="lpl-actions">
          <button class="lpl-btn rename-btn" @click="startRename(pl)">✏️</button>
          <button class="lpl-btn" @click="playAll(pl)">▶ 全部播放</button>
          <button class="lpl-btn danger" @click="deletePlaylist(pl)">🗑</button>
        </div>
      </div>
      <template v-if="expanded[pl.id]">
        <div v-if="pl.items.length === 0" class="sub-placeholder">合集为空</div>
        <div v-else class="grid">
          <VideoCard v-for="item in pl.items" :key="item.url" :item="item" @cardClick="onVideoClick(item)" @addToPlaylist="e => store.addToLocalPlaylist(pl.id, e)" />
        </div>
      </template>
    </div>

    <!-- Create dialog -->
    <div v-if="showCreateDialog" class="dialog-overlay" @click.self="showCreateDialog = false">
      <div class="dialog-box">
        <h3 class="dialog-title">新建合集</h3>
        <input v-model="newName" class="form-input" placeholder="合集名称" ref="nameInput" @keyup.enter="createPlaylist" />
        <div class="dialog-actions">
          <button class="dialog-btn cancel" @click="showCreateDialog = false">取消</button>
          <button class="dialog-btn save" @click="createPlaylist" :disabled="!newName.trim()">创建</button>
        </div>
      </div>
    </div>

    <!-- Rename dialog -->
    <div v-if="renameTarget" class="dialog-overlay" @click.self="renameTarget = null">
      <div class="dialog-box">
        <h3 class="dialog-title">重命名合集</h3>
        <input v-model="renameName" class="form-input" placeholder="合集名称" @keyup.enter="doRename" />
        <div class="dialog-actions">
          <button class="dialog-btn cancel" @click="renameTarget = null">取消</button>
          <button class="dialog-btn save" @click="doRename">保存</button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, nextTick } from 'vue'
import { useRouter } from 'vue-router'
import { proxyImageUrl } from '../extractor/BilibiliImageProxy'
import { usePlaylistsStore } from '../stores/playlists'
import { usePlayQueueStore } from '../stores/playQueue'
import type { StreamInfoItem } from '../plugins/bridge'
import VideoCard from '../components/VideoCard.vue'

const router = useRouter()
const store = usePlaylistsStore()
const queueStore = usePlayQueueStore()

const expanded = ref<Record<string, boolean>>({})
const showCreateDialog = ref(false)
const newName = ref('')
const nameInput = ref<HTMLInputElement | null>(null)
const renameTarget = ref<{ id: string; name: string } | null>(null)
const renameName = ref('')

function hideThumb(e: Event) {
  const el = e.target as HTMLElement
  el.style.display = 'none'
}

function toggleExpand(id: string) { expanded.value[id] = !expanded.value[id] }

async function createPlaylist() {
  const name = newName.value.trim()
  if (!name) return
  store.createLocalPlaylist(name)
  newName.value = ''
  showCreateDialog.value = false
}

function startRename(pl: { id: string; name: string }) {
  renameTarget.value = pl
  renameName.value = pl.name
}

function doRename() {
  if (renameTarget.value && renameName.value.trim()) {
    store.renameLocalPlaylist(renameTarget.value.id, renameName.value.trim())
  }
  renameTarget.value = null
}

function deletePlaylist(pl: { id: string; name: string }) {
  if (confirm(`删除合集"${pl.name}"？`)) store.deleteLocalPlaylist(pl.id)
}

function playAll(pl: { id: string; items: StreamInfoItem[] }) {
  if (!pl.items.length) return
  queueStore.replaceWith(pl.items.map(item => ({ url: item.url, title: item.name, thumbnailUrl: item.thumbnailUrl, duration: item.duration || 0, uploaderName: item.uploaderName || '' })))
  router.push({ name: 'video-player', query: { url: pl.items[0].url } })
}

function onVideoClick(item: StreamInfoItem) {
  if (item.type === 'channel') router.push({ name: 'channel', query: { url: item.url || item.uploaderUrl } })
  else router.push({ name: 'video-player', query: { url: item.url } })
}
</script>

<style scoped>
.lpl-view { padding: 4px 12px; }
.lpl-header { display: flex; justify-content: space-between; align-items: center; padding: 8px 0; }
.create-btn { padding: 6px 14px; background: var(--accent); color: var(--bg); border: none; border-radius: 6px; font-size: 13px; font-weight: 600; cursor: pointer; }

.remote-section { margin-bottom: 12px; }
.subsection-title { font-size: 13px; font-weight: 600; color: var(--fg-muted); margin: 0 0 6px; }
.remote-list { display: flex; flex-direction: column; gap: 6px; }
.remote-item { display: flex; align-items: center; gap: 10px; padding: 8px; border-radius: 8px; border: 1px solid var(--border); cursor: pointer; }
.remote-item:hover { background: var(--bg-secondary); }
.remote-thumb { width: 40px; height: 40px; border-radius: 4px; object-fit: cover; flex-shrink: 0; background: var(--border); }
.remote-info { flex: 1; min-width: 0; }
.remote-name { font-size: 13px; color: var(--fg); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.remote-meta { font-size: 11px; color: var(--fg-muted); }
.remove-btn { width: 20px; height: 20px; border: none; background: none; color: var(--fg-muted); font-size: 12px; cursor: pointer; border-radius: 4px; flex-shrink: 0; }
.remote-item:hover .remove-btn { display: flex; align-items: center; justify-content: center; }
.remove-btn:hover { background: var(--border); color: #e74c3c; }

.lpl-card { border: 1px solid var(--border); border-radius: 8px; margin-bottom: 10px; overflow: hidden; }
.lpl-title-row { display: flex; align-items: center; gap: 8px; padding: 10px 12px; background: var(--bg-secondary); }
.lpl-name { font-size: 14px; font-weight: 600; color: var(--fg); cursor: pointer; flex: 1; }
.lpl-count { font-size: 11px; color: var(--fg-muted); white-space: nowrap; }
.lpl-actions { display: flex; gap: 4px; }
.lpl-btn { padding: 3px 8px; font-size: 11px; border: 1px solid var(--border); border-radius: 4px; background: var(--bg); color: var(--fg); cursor: pointer; }
.lpl-btn.danger { color: #e74c3c; }
.sub-placeholder { text-align: center; padding: 24px; color: var(--fg-muted); font-size: 13px; }
.grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(180px, 1fr)); gap: 12px; padding: 12px; }
.placeholder { text-align: center; padding: 48px; color: var(--fg-muted); font-size: 14px; }
.dialog-overlay { position: fixed; inset: 0; background: rgba(0,0,0,0.4); z-index: 1000; display: flex; align-items: center; justify-content: center; }
.dialog-box { background: var(--bg); border-radius: 12px; padding: 20px; width: 320px; }
.dialog-title { font-size: 16px; font-weight: 700; margin: 0 0 12px; color: var(--fg); }
.form-input { width: 100%; padding: 8px 12px; border: 1px solid var(--border); border-radius: 8px; background: var(--bg-secondary); color: var(--fg); font-size: 13px; box-sizing: border-box; }
.dialog-actions { display: flex; gap: 8px; justify-content: flex-end; margin-top: 16px; }
.dialog-btn { padding: 8px 20px; border-radius: 8px; font-size: 14px; font-weight: 600; cursor: pointer; border: none; }
.dialog-btn.cancel { background: var(--bg-secondary); color: var(--fg); }
.dialog-btn.save { background: var(--accent); color: var(--bg); }
</style>
