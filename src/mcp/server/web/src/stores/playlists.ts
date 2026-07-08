import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import type { StreamInfoItem } from '../plugins/bridge'
import { localPlaylistRepo, remotePlaylistRepo } from '../db'

// ─── Types ────────────────────────────────────────────────────────────

export interface LocalPlaylist {
  id: string
  name: string
  createdAt: number
  items: StreamInfoItem[]
}

export interface RemotePlaylist {
  url: string
  name: string
  thumbnailUrl: string
  uploaderName: string
  uploaderAvatarUrl: string
  streamCount: number
}

// "Favorites" is the default local playlist; all video toggle actions
// add/remove from it. It exists automatically when first used.

// ─── Keys ─────────────────────────────────────────────────────────────

const LOCAL_KEY = 'ts2_local_playlists'
const REMOTE_KEY = 'ts2_remote_playlists'
const FAVORITES_PLAYLIST_ID = '_favorites'
const FAVORITES_PLAYLIST_NAME = '收藏'

// ─── Persistence ──────────────────────────────────────────────────────

function loadLocal(): LocalPlaylist[] {
  try {
    return JSON.parse(localStorage.getItem(LOCAL_KEY) || '[]')
  } catch { return [] }
}

function saveLocal(list: LocalPlaylist[]) {
  localStorage.setItem(LOCAL_KEY, JSON.stringify(list))
}

function loadRemote(): RemotePlaylist[] {
  try {
    return JSON.parse(localStorage.getItem(REMOTE_KEY) || '[]')
  } catch { return [] }
}

function saveRemote(list: RemotePlaylist[]) {
  localStorage.setItem(REMOTE_KEY, JSON.stringify(list))
}

// ─── Store ────────────────────────────────────────────────────────────

export const usePlaylistsStore = defineStore('playlists', () => {
  const locals = ref<LocalPlaylist[]>(loadLocal())
  const remotes = ref<RemotePlaylist[]>(loadRemote())

  // The "Favorites" playlist is always the first one.
  function ensureFavorites() {
    const existing = locals.value.find(p => p.id === FAVORITES_PLAYLIST_ID)
    if (existing) return existing
    const pl: LocalPlaylist = {
      id: FAVORITES_PLAYLIST_ID,
      name: FAVORITES_PLAYLIST_NAME,
      createdAt: Date.now(),
      items: [],
    }
    locals.value.unshift(pl)
    _persist()
    return pl
  }

  // Persist both
  function _persist() {
    saveLocal(locals.value)
    saveRemote(remotes.value)
    syncToDB()
  }

  async function syncToDB() {
    for (const pl of locals.value) await localPlaylistRepo.upsert({
      playlistId: pl.id,
      name: pl.name,
      createdAt: pl.createdAt,
      streamUrls: pl.items.map(i => i.url),
    })
    for (const rp of remotes.value) await remotePlaylistRepo.upsertByUrl({
      url: rp.url,
      name: rp.name,
      serviceId: 0,
      thumbnailUrl: rp.thumbnailUrl,
      uploaderName: rp.uploaderName,
      uploaderAvatarUrl: rp.uploaderAvatarUrl,
      streamCount: rp.streamCount,
    })
  }

  // ════════════════════════════════════════════════════════════════════
  // Favorites — single-video toggle (PipePipeClient uses default playlist)
  // ════════════════════════════════════════════════════════════════════

  function isFavorited(url: string): boolean {
    const fav = locals.value.find(p => p.id === FAVORITES_PLAYLIST_ID)
    return fav ? fav.items.some(i => i.url === url) : false
  }

  function toggleFavorite(item: StreamInfoItem) {
    const fav = ensureFavorites()
    const idx = fav.items.findIndex(i => i.url === item.url)
    if (idx >= 0) {
      fav.items.splice(idx, 1)
    } else {
      fav.items.unshift(item)
    }
    _persist()
  }

  function addFavorite(item: StreamInfoItem) {
    const fav = ensureFavorites()
    if (!fav.items.some(i => i.url === item.url)) {
      fav.items.unshift(item)
      _persist()
    }
  }

  function removeFavorite(url: string) {
    const fav = locals.value.find(p => p.id === FAVORITES_PLAYLIST_ID)
    if (fav) {
      fav.items = fav.items.filter(i => i.url !== url)
      _persist()
    }
  }

  const favoritesItems = computed(() => {
    const fav = locals.value.find(p => p.id === FAVORITES_PLAYLIST_ID)
    return fav ? [...fav.items] : []
  })

  // ════════════════════════════════════════════════════════════════════
  // Local Playlists — user-created, CRUD (PipePipeClient LocalPlaylistManager)
  // ════════════════════════════════════════════════════════════════════

  function createLocalPlaylist(name: string): string | null {
    const id = 'pl_' + Date.now() + '_' + Math.random().toString(36).slice(2, 6)
    locals.value.push({ id, name, createdAt: Date.now(), items: [] })
    _persist()
    return id
  }

  function renameLocalPlaylist(id: string, name: string) {
    const pl = locals.value.find(p => p.id === id)
    if (pl) { pl.name = name; _persist() }
  }

  function deleteLocalPlaylist(id: string) {
    // Cannot delete the Favorites playlist
    if (id === FAVORITES_PLAYLIST_ID) return
    locals.value = locals.value.filter(p => p.id !== id)
    _persist()
  }

  function addToLocalPlaylist(playlistId: string, item: StreamInfoItem) {
    const pl = locals.value.find(p => p.id === playlistId)
    if (!pl) return
    if (pl.items.some(i => i.url === item.url)) return
    pl.items.push(item)
    _persist()
  }

  function removeFromLocalPlaylist(playlistId: string, itemUrl: string) {
    const pl = locals.value.find(p => p.id === playlistId)
    if (!pl) return
    pl.items = pl.items.filter(i => i.url !== itemUrl)
    _persist()
  }

  function playlistContaining(itemUrl: string): LocalPlaylist[] {
    return locals.value.filter(p => p.items.some(i => i.url === itemUrl))
  }

  const localPlaylists = computed(() =>
    locals.value.filter(p => p.id !== FAVORITES_PLAYLIST_ID)
  )

  // ════════════════════════════════════════════════════════════════════
  // Remote Playlists — bookmarked from web (PipePipeClient RemotePlaylistManager)
  // ════════════════════════════════════════════════════════════════════

  function bookmarkRemote(pl: RemotePlaylist) {
    if (remotes.value.some(r => r.url === pl.url)) return
    remotes.value.push(pl)
    _persist()
  }

  function unbookmarkRemote(url: string) {
    remotes.value = remotes.value.filter(r => r.url !== url)
    _persist()
  }

  function isBookmarked(url: string): boolean {
    return remotes.value.some(r => r.url === url)
  }

  const remotePlaylists = computed(() => [...remotes.value])

  // ════════════════════════════════════════════════════════════════════
  // Summary
  // ════════════════════════════════════════════════════════════════════

  const totalCount = computed(() =>
    locals.value.reduce((s, p) => s + p.items.length, 0)
  )

  return {
    // Favorites
    isFavorited, toggleFavorite, addFavorite, removeFavorite, favoritesItems,
    // Local playlists
    localPlaylists, createLocalPlaylist, renameLocalPlaylist,
    deleteLocalPlaylist, addToLocalPlaylist, removeFromLocalPlaylist,
    playlistContaining,
    // Remote playlists
    remotePlaylists, bookmarkRemote, unbookmarkRemote, isBookmarked,
    // Summary
    totalCount, locals, remotes,
  }
})
