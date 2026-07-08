<template>
  <div class="view">
    <header class="view-header">
      <h1>书签</h1>
    </header>
    <div class="view-body">
      <!-- toolbar -->
      <div v-if="store.bookmarks.length > 0" class="bookmark-toolbar">
        <div class="bookmark-actions">
          <input v-model="searchQuery" class="bookmark-search" placeholder="搜索书签..." autocomplete="off" />
          <button class="add-btn" @click="showAddDialog">➕ 添加</button>
        </div>
        <div class="bookmark-categories">
          <span class="cat-btn" :class="{ active: activeCategory === '' }" @click="activeCategory = ''">全部</span>
          <span v-for="cat in categories" :key="cat" class="cat-btn" :class="{ active: activeCategory === cat }" @click="activeCategory = cat">{{ catLabel(cat) }}</span>
        </div>
      </div>

      <div v-if="store.loading" class="loading">加载中...</div>
      <div v-else-if="store.bookmarks.length === 0" class="empty">暂无书签</div>
      <div v-else-if="filteredBookmarks.length === 0" class="empty">无匹配书签</div>
      <div v-else class="bookmark-list">
        <div v-for="bm in filteredBookmarks" :key="bm.id || bm.url || bm.link" class="bookmark-item" @click="openBookmark(bm)">
          <span class="bookmark-icon">{{ bm.icon || '🔗' }}</span>
          <div class="bookmark-info">
            <span class="bookmark-title">{{ bm.title || bm.name || bm.path || '未命名' }}</span>
            <span v-if="bm.url || bm.link" class="bookmark-path">{{ bm.url || bm.link }}</span>
            <span v-else-if="bm.path" class="bookmark-path">{{ bm.path }}</span>
          </div>
          <span class="bookmark-cat-tag">{{ catLabel(bm.category || bm.group || '') }}</span>
          <button class="bm-remove" @click.stop="removeBookmark(bm)">✕</button>
        </div>
      </div>
    </div>

    <!-- Add Dialog -->
    <div v-if="showDialog" class="dialog-overlay" @click.self="cancelAdd">
      <div class="dialog-box">
        <h3 class="dialog-title">添加书签</h3>
        <div class="form-row">
          <input v-model="form.name" class="form-input" placeholder="名称" ref="nameInput" />
        </div>
        <div class="form-row">
          <div class="url-row">
            <input v-model="form.url" class="form-input" placeholder="URL..." style="flex:1" />
            <button class="paste-btn" @click="pasteUrl" title="从剪贴板粘贴">📋</button>
          </div>
        </div>
        <div class="form-row radio-row">
          <label v-for="cat in allCategories" :key="cat" class="radio-label">
            <input type="radio" v-model="form.category" :value="cat" />
            <span>{{ catLabel(cat) }}</span>
          </label>
        </div>
        <p v-if="addError" class="error-msg">{{ addError }}</p>
        <div class="dialog-actions">
          <button class="dialog-btn cancel" @click="cancelAdd">取消</button>
          <button class="dialog-btn save" @click="saveBookmark">保存</button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, nextTick } from 'vue'
import { useBookmarksStore } from '../stores/bookmarks'

const store = useBookmarksStore()
store.load()

const searchQuery = ref('')
const activeCategory = ref('')
const showDialog = ref(false)
const addError = ref('')
const nameInput = ref<HTMLInputElement | null>(null)
const form = ref({ name: '', url: '', category: 'tool', icon: '' })

const CAT_LABELS: Record<string, string> = {
  preprint: '预印本', search: '学术搜索', journal: '期刊',
  database: '数据库', tool: '工具', other: '其他',
}

const allCategories = ['preprint', 'search', 'journal', 'database', 'tool', 'other']

const categories = computed(() => {
  const set = new Set<string>()
  for (const bm of store.bookmarks) {
    const cat = (bm as any).category || (bm as any).group || ''
    if (cat) set.add(cat)
  }
  return [...set].sort()
})

const filteredBookmarks = computed(() => {
  let list = store.bookmarks
  if (activeCategory.value) {
    list = list.filter((bm: any) => (bm.category || bm.group || '') === activeCategory.value)
  }
  const q = searchQuery.value.trim().toLowerCase()
  if (q) {
    list = list.filter((bm: any) => {
      const title = (bm.title || bm.name || '').toLowerCase()
      const url = (bm.url || bm.link || '').toLowerCase()
      const cat = (bm.category || bm.group || '').toLowerCase()
      return title.includes(q) || url.includes(q) || cat.includes(q)
    })
  }
  return list
})

function catLabel(cat: string): string {
  return CAT_LABELS[cat] || cat
}

function openBookmark(bm: any) {
  const url = bm.url || bm.link
  if (url) {
    window.open(url, '_blank')
  } else if (bm.path) {
    window.location.hash = '/files'
  }
}

async function removeBookmark(bm: any) {
  const id = bm.id || bm.url || bm.link
  if (id) await store.remove(id)
}

function showAddDialog() {
  form.value = { name: '', url: '', category: 'tool', icon: '' }
  addError.value = ''
  showDialog.value = true
  nextTick(() => nameInput.value?.focus())
}

function cancelAdd() {
  showDialog.value = false
  addError.value = ''
}

async function pasteUrl() {
  try {
    const text = await navigator.clipboard.readText()
    if (text && (text.startsWith('http://') || text.startsWith('https://'))) {
      form.value.url = text
      if (!form.value.name) {
        try { form.value.name = new URL(text).hostname } catch {}
      }
    }
  } catch {}
}

async function saveBookmark() {
  addError.value = ''
  if (!form.value.name.trim()) { addError.value = '请输入名称'; return }
  if (!form.value.url.trim()) { addError.value = '请输入 URL'; return }
  let url = form.value.url.trim()
  if (!url.startsWith('http://') && !url.startsWith('https://')) url = 'https://' + url
  const ok = await store.add({
    name: form.value.name.trim(),
    url,
    category: form.value.category,
  })
  if (!ok) { addError.value = '添加失败'; return }
  showDialog.value = false
  addError.value = ''
}
</script>

<style scoped>
.bookmark-toolbar {
  padding: 8px 12px;
  border-bottom: 1px solid var(--border);
  background: var(--bg-secondary);
  position: sticky;
  top: 0;
  z-index: 1;
}
.bookmark-actions {
  display: flex;
  gap: 6px;
}
.bookmark-search {
  flex: 1;
  padding: 8px 12px;
  border: 1px solid var(--border);
  border-radius: 6px;
  background: var(--bg);
  color: var(--fg);
  font-size: 13px;
  outline: none;
  box-sizing: border-box;
}
.bookmark-search:focus { border-color: var(--accent); }
.bookmark-search::placeholder { color: var(--fg-muted); }

.add-btn {
  padding: 8px 12px;
  background: var(--accent);
  color: var(--bg);
  border: none;
  border-radius: 6px;
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
  white-space: nowrap;
  flex-shrink: 0;
}

.bookmark-categories {
  display: flex;
  gap: 6px;
  margin-top: 8px;
  overflow-x: auto;
  flex-wrap: nowrap;
  -webkit-overflow-scrolling: touch;
}
.cat-btn {
  flex-shrink: 0;
  padding: 3px 10px;
  border: 1px solid var(--border);
  border-radius: 12px;
  font-size: 12px;
  color: var(--fg-muted);
  cursor: pointer;
  transition: all 0.15s;
  user-select: none;
}
.cat-btn:hover { border-color: var(--accent); color: var(--fg); }
.cat-btn.active { background: var(--accent); color: var(--bg); border-color: var(--accent); }

.bookmark-list {
  padding: 4px 12px;
}
.bookmark-item {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px 12px;
  border-bottom: 1px solid var(--border);
  cursor: pointer;
  transition: background 0.15s;
  position: relative;
}
.bookmark-item:hover { background: rgba(255, 255, 255, 0.04); }

.bookmark-icon { font-size: 18px; flex-shrink: 0; }
.bookmark-info { flex: 1; min-width: 0; }
.bookmark-title {
  display: block;
  font-size: 14px;
  color: var(--fg);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.bookmark-path {
  display: block;
  font-size: 11px;
  color: var(--fg-muted);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  margin-top: 2px;
}
.bookmark-cat-tag {
  flex-shrink: 0;
  font-size: 10px;
  padding: 2px 6px;
  border-radius: 8px;
  background: rgba(122, 162, 247, 0.1);
  color: var(--accent);
  white-space: nowrap;
}

.bm-remove {
  width: 20px;
  height: 20px;
  border: none;
  background: none;
  color: var(--fg-muted);
  font-size: 12px;
  cursor: pointer;
  border-radius: 4px;
  flex-shrink: 0;
  display: none;
}
.bookmark-item:hover .bm-remove { display: flex; align-items: center; justify-content: center; }
.bm-remove:hover { background: var(--border); color: #e74c3c; }

.loading, .empty {
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 200px;
  color: var(--fg-muted);
  font-size: 14px;
}

.dialog-overlay { position: fixed; inset: 0; background: rgba(0,0,0,0.4); z-index: 1000; display: flex; align-items: center; justify-content: center; }
.dialog-box { background: var(--bg); border-radius: 12px; padding: 20px; width: 360px; max-width: 90vw; max-height: 80vh; overflow-y: auto; }
.dialog-title { font-size: 16px; font-weight: 700; margin: 0 0 16px; color: var(--fg); }
.form-row { margin-bottom: 12px; }
.form-input { width: 100%; padding: 8px 12px; border: 1px solid var(--border); border-radius: 8px; background: var(--bg-secondary); color: var(--fg); font-size: 13px; box-sizing: border-box; }
.form-input:focus { outline: none; border-color: var(--accent); }
.url-row { display: flex; gap: 4px; }
.paste-btn { padding: 8px; background: none; border: 1px solid var(--border); border-radius: 8px; cursor: pointer; font-size: 14px; }
.radio-row { display: flex; flex-wrap: wrap; gap: 8px; }
.radio-label { display: flex; align-items: center; gap: 4px; font-size: 13px; color: var(--fg); cursor: pointer; }
.error-msg { font-size: 12px; color: #e74c3c; margin: 4px 0; }
.dialog-actions { display: flex; gap: 8px; justify-content: flex-end; margin-top: 16px; }
.dialog-btn { padding: 8px 20px; border-radius: 8px; font-size: 14px; font-weight: 600; cursor: pointer; border: none; }
.dialog-btn.cancel { background: var(--bg-secondary); color: var(--fg); }
.dialog-btn.save { background: var(--accent); color: var(--bg); }
</style>
