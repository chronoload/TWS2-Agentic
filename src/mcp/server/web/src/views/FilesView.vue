<template>
  <div class="view">
    <header class="view-header">
      <h1>文件</h1>
      <div class="header-actions">
        <span class="ws-status" :class="{ connected: wsConnected }" :title="wsConnected ? '已连接' : '未连接'">●</span>
      </div>
    </header>
    <div class="view-body files-body">
      <!-- 文本编辑器（Vditor） -->
      <div v-if="editingFile" class="editor-view">
        <div class="editor-header">
          <button class="btn-back" @click="closeEditor">← 返回</button>
          <span class="editor-path">{{ editingFile }}</span>
          <span v-if="editModified" class="edit-modified">●</span>
        </div>
        <div v-if="!useTextarea" ref="vditorRef" class="vditor-container"></div>
        <template v-else>
          <div class="md-toolbar">
            <button @click="insertMd('**', '**')" title="粗体">B</button>
            <button @click="insertMd('*', '*')" title="斜体">I</button>
            <button @click="insertMd('## ', '')" title="标题">H</button>
            <button @click="insertMd('- ', '')" title="列表">-</button>
            <button @click="insertMd('1. ', '')" title="有序列表">1.</button>
            <button @click="insertMd('- [ ] ', '')" title="待办">☐</button>
            <button @click="insertMd('`', '`')" title="代码">code</button>
            <button @click="insertMd('[', '](url)')" title="链接">🔗</button>
          </div>
          <textarea
            ref="textareaRef"
            class="fallback-textarea"
            @input="editModified = true"
          ></textarea>
        </template>
        <div class="editor-actions">
          <button class="btn-save" @click="saveFile" :disabled="saving || !editModified">
            {{ saving ? '保存中...' : '保存' }}
          </button>
        </div>
      </div>

      <!-- Office 文档预览（docx/excel/pptx/pdf） -->
      <div v-else-if="previewFile" class="editor-view">
        <div class="editor-header">
          <button class="btn-back" @click="closePreview">← 返回</button>
          <span class="editor-path">{{ previewFile }}</span>
          <button v-if="previewType === 'pdf' && fileSource === 'server'" class="btn-ai-read" @click="openPdfReader" title="AI 智能阅读（建立索引、AI问答）">AI 阅读</button>
        </div>
        <div class="office-preview-container">
          <VueOfficeDocx v-if="previewType === 'docx'" :src="previewUrl" style="height:100%;width:100%" />
          <VueOfficeExcel v-else-if="previewType === 'xlsx'" :src="previewUrl" style="height:100%;width:100%" />
          <VueOfficePptx v-else-if="previewType === 'pptx'" :src="previewUrl" style="height:100%;width:100%" />
          <VueOfficePdf v-else-if="previewType === 'pdf'" :src="previewUrl" style="height:100%;width:100%" />
          <div v-else class="preview-error">不支持的文档格式</div>
        </div>
      </div>

      <!-- 文件浏览视图 -->
      <div v-else class="browser-view">

        <!-- 新建文件对话框 -->
        <div v-if="showNewFile" class="newfile-bar">
          <input
            v-model="newFileName"
            class="newfile-input"
            placeholder="文件名（如 note.md）"
            @keyup.enter="createFile"
            ref="newFileInputRef"
          />
          <button class="btn-newfile" @click="createFile" :disabled="creatingFile">创建</button>
          <button class="btn-newfile-cancel" @click="cancelNewFile">取消</button>
        </div>

        <!-- 搜索过滤框 -->
        <div class="search-bar">
          <input
            v-model="searchQuery"
            class="search-input"
            :placeholder="fileSource === 'local' ? '本地搜索...' : '搜索文件...'"
            @input="onSearchInput"
          />
          <button v-if="searchQuery" class="search-clear" @click="clearSearch">✕</button>
          <!-- 文件源切换 -->
          <div class="source-toggle">
            <button
              class="source-btn"
              :class="{ active: fileSource === 'server' }"
              @click="switchFileSource('server')"
            >服务端</button>
            <button
              class="source-btn"
              :class="{ active: fileSource === 'local' }"
              @click="switchFileSource('local')"
            >本地</button>
          </div>
        </div>

        <!-- 面包屑 -->
        <div class="breadcrumb">
          <div class="breadcrumb-links">
            <span class="breadcrumb-item" @click="navigateTo('')">根目录</span>
            <template v-for="(seg, idx) in pathSegments" :key="idx">
              <span class="breadcrumb-sep">/</span>
              <span
                class="breadcrumb-item"
                :class="{ active: idx === pathSegments.length - 1 }"
                @click="navigateTo(pathSegments.slice(0, idx + 1).join('/'))"
              >{{ seg }}</span>
            </template>
          </div>
          <button class="btn-newfile-breadcrumb" @click="startNewFile" :title="currentPath ? '在当前目录新建文件' : '请先进入子目录'" v-if="fileSource === 'server'">+ 新建</button>
          <template v-else>
            <button class="btn-newfile-breadcrumb" @click="doCreateLocalFile">+ 文件</button>
            <button class="btn-newfile-breadcrumb" @click="doCreateLocalDir">+ 目录</button>
            <button class="btn-newfile-breadcrumb" @click="doImportFromServer" :disabled="importExportBusy" title="从服务端导入当前目录">↓ 导入</button>
            <button class="btn-newfile-breadcrumb" @click="doExportToServer" :disabled="importExportBusy" title="导出当前目录到服务端">↑ 导出</button>
            <span v-if="importExportMsg" class="import-export-msg">{{ importExportMsg }}</span>
            <span class="local-stats" v-if="localStats.files > 0">{{ localStats.files }}文件 {{ formatSize(localStats.totalSize) }}</span>
          </template>
        </div>

        <!-- 目录列表 / 搜索结果 -->
        <div v-if="searching" class="loading-root">搜索中...</div>
        <div v-else-if="loading" class="loading-root">加载中...</div>
        <div v-else-if="filteredEntries.length === 0" class="empty-dir">{{ searchQuery ? '没有匹配的文件' : '空目录' }}</div>
        <div v-else class="entry-list">
          <!-- 返回上级（仅在非搜索模式下） -->
          <div v-if="!searchQuery && currentPath" class="entry-row entry-up" @click="goUp">
            <span class="entry-icon">📁</span>
            <span class="entry-name">..</span>
          </div>
          <div
            v-for="entry in filteredEntries"
            :key="entry.path || entry.name"
            class="entry-row"
            @click="handleEntryClick(entry)"
            @contextmenu.prevent="!entry.is_dir && showCtxMenu(entry, $event)"
          >
            <span class="entry-icon">{{ entry.is_dir ? '📁' : fileIcon(entry.ext) }}</span>
            <span class="entry-name" :class="{ 'is-dir': entry.is_dir }">{{ entry.name }}</span>
            <span v-if="searchQuery && !entry.is_dir" class="entry-path" :title="entry.path">{{ entry.path.includes('/') ? entry.path.substring(0, entry.path.lastIndexOf('/')) + '/' : '' }}</span>
            <span v-if="!entry.is_dir && entry.size" class="entry-size">{{ formatSize(entry.size) }}</span>
            <!-- 服务端模式：单文件导入到本地 -->
            <button v-if="fileSource === 'server' && !entry.is_dir" class="btn-import-single" @click.stop="importSingleFromServer(entry)" title="导入到本地">↓</button>
            <!-- 本地模式：单文件导出到服务端 -->
            <button v-if="fileSource === 'local' && !entry.is_dir" class="btn-export-single" @click.stop="exportSingleToServer(entry)" title="导出到服务端">↑</button>
            <button v-if="fileSource === 'local'" class="btn-delete-local" @click.stop="doDeleteLocal(entry)" title="删除">✕</button>
          </div>
        </div>

        <!-- 上传区域（仅服务端模式） -->
        <div
          v-if="fileSource === 'server'"
          class="upload-section"
          @dragenter.prevent="dragOver = true"
          @dragover.prevent="dragOver = true"
          @dragleave.prevent="dragOver = false"
          @drop.prevent="handleDrop"
          :class="{ 'drag-over': dragOver, 'uploading': uploading }"
        >
          <div class="upload-row">
            <label class="btn-upload">
              上传文件
              <input type="file" ref="fileInputRef" multiple @change="handleUpload" style="display:none" />
            </label>
            <label class="btn-upload btn-upload-folder">
              上传文件夹
              <input type="file" ref="folderInputRef" webkitdirectory @change="handleFolderUpload" style="display:none" />
            </label>
            <button class="btn-upload btn-cluster-import" @click="openClusterImport">从其他实例导入</button>
          </div>
          <div v-if="!uploading && !dragOver" class="upload-hint">拖拽文件到此处上传</div>
          <div v-if="dragOver && !uploading" class="upload-hint upload-hint-active">释放以上传文件</div>
          <div v-if="uploading" class="upload-progress-bar">
            <div class="upload-progress-fill" :style="{ width: uploadProgress + '%' }"></div>
            <span class="upload-progress-text">{{ uploadProgressText }}</span>
          </div>
        </div>
      </div>
    </div>

    <!-- 右键菜单 -->
    <div
      v-if="ctxMenu.visible"
      class="context-menu"
      :style="{ left: ctxMenu.x + 'px', top: ctxMenu.y + 'px' }"
      @click.stop
      @contextmenu.prevent
    >
      <div class="ctx-item" @click="ctxDownload">下载</div>
      <div class="ctx-item" @click="ctxCopyPath">复制路径</div>
      <div class="ctx-item" @click="ctxOpenInEditor" v-if="ctxMenu.entry && !ctxMenu.entry.is_dir">在独立编辑器中打开</div>
    </div>

    <!-- 多实例导入弹窗 -->
    <div v-if="clusterModal" class="cluster-modal-overlay" @click.self="clusterModal = false">
      <div class="cluster-modal">
        <div class="cluster-modal-header">
          <h3>从其他实例导入</h3>
          <button class="cluster-close" @click="clusterModal = false">✕</button>
        </div>

        <!-- 实例选择 -->
        <div v-if="!clusterSelectedUrl" class="cluster-instances">
          <div v-if="clusterScanning" class="cluster-scanning">扫描实例中...</div>
          <div v-else-if="clusterPeers.length === 0" class="cluster-empty">未发现其他 TS2 实例</div>
          <div
            v-for="inst in clusterPeers"
            :key="inst.url"
            class="cluster-instance-card"
            @click="selectClusterInstance(inst.url)"
          >
            <span class="cluster-instance-icon">🖥️</span>
            <div class="cluster-instance-info">
              <div class="cluster-instance-url">{{ inst.url }}</div>
              <div class="cluster-instance-meta">端口 {{ inst.port }} · v{{ inst.version }}</div>
            </div>
            <span class="cluster-instance-arrow">→</span>
          </div>
        </div>

        <!-- 远端文件浏览 -->
        <div v-else class="cluster-browser">
          <div class="cluster-browser-header">
            <button class="btn-back" @click="clusterSelectedUrl = ''; clusterRemoteEntries = []; clusterRemotePath = ''">← 返回实例列表</button>
            <span class="cluster-remote-label">{{ clusterSelectedUrl }}</span>
          </div>

          <!-- 远端搜索 -->
          <div class="cluster-search-bar">
            <input
              v-model="clusterSearchQuery"
              class="search-input"
              placeholder="搜索远端文件..."
              @input="onClusterSearchInput"
            />
            <button v-if="clusterSearchQuery" class="search-clear" @click="clusterSearchQuery = ''; loadClusterDir('')">✕</button>
          </div>

          <!-- 远端面包屑 -->
          <div class="breadcrumb" style="margin-bottom:4px">
            <div class="breadcrumb-links">
              <span class="breadcrumb-item" @click="loadClusterDir('')">根目录</span>
              <template v-for="(seg, idx) in clusterRemotePath.split('/').filter(Boolean)" :key="idx">
                <span class="breadcrumb-sep">/</span>
                <span class="breadcrumb-item" @click="loadClusterDir(clusterRemotePath.split('/').slice(0, idx+1).join('/'))">{{ seg }}</span>
              </template>
            </div>
          </div>

          <!-- 远端文件列表 -->
          <div v-if="clusterRemoteLoading" class="loading-root">加载中...</div>
          <div v-else-if="clusterRemoteEntries.length === 0" class="empty-dir">空目录</div>
          <div v-else class="cluster-entry-list">
            <div v-if="clusterRemotePath" class="entry-row entry-up" @click="loadClusterDir(clusterRemotePath.split('/').slice(0, -1).join('/'))">
              <span class="entry-icon">📁</span><span class="entry-name">..</span>
            </div>
            <div
              v-for="entry in clusterRemoteEntries"
              :key="entry.path || entry.name"
              class="entry-row"
              :class="{ 'cluster-selected': clusterSelectedFiles.has(entry.path) }"
              @click="handleClusterEntryClick(entry)"
            >
              <span class="entry-icon">{{ entry.is_dir ? '📁' : fileIcon(entry.ext) }}</span>
              <span class="entry-name" :class="{ 'is-dir': entry.is_dir }">{{ entry.name }}</span>
              <span v-if="!entry.is_dir" class="entry-check">
                <span v-if="clusterSelectedFiles.has(entry.path)" class="check-on">✓</span>
                <span v-else class="check-off">○</span>
              </span>
            </div>
          </div>

          <!-- 选中文件操作栏 -->
          <div v-if="clusterSelectedFiles.size > 0" class="cluster-action-bar">
            <span>已选 {{ clusterSelectedFiles.size }} 个文件</span>
            <button class="btn-cluster-transfer" @click="doClusterTransfer" :disabled="clusterTransferring">
              {{ clusterTransferring ? '传输中...' : '导入到当前目录' }}
            </button>
            <button class="btn-cluster-clear" @click="clusterSelectedFiles.clear()">清空选择</button>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted, nextTick, defineAsyncComponent } from 'vue'
import { useRouter } from 'vue-router'
const router = useRouter()
import { readDir, getFile, putFile, upload as uploadApi, downloadFile, getServerURL, getApiToken, getAuthCode, clusterInstances, clusterRemoteReadDir, clusterRemoteSearch, clusterTransferBatch } from '../api'
import { useWebSocket } from '../composables/useWebSocket'
import { loadAutocompleteConfig, buildHintExtends } from '../autocomplete'
import {
  localReadDir, localReadFile, localWriteFile, localDeleteFile, localMkdir,
  importDirFromServer, exportDirToServer, localFSStats, localFSClear,
  localWriteFileBlob, localReadFileBlob, localSearchTree, isBinaryExt,
  type DirEntry as LocalDirEntry,
} from '../stores/localFS'

// Vditor 加载策略：4层容灾
// 第1层：本地 npm 包（打包进应用）
// 第2层：自建服务器（BASE_URL/vditor）
// 第3层：公共 CDN（unpkg）
// 第4层：回退到 textarea
let VditorClass: any = null
let vditorLoadFailed = false
let vditorSource: 'local' | 'self' | 'cdn' | null = null

const VDITOR_CDN = 'https://unpkg.com/vditor'
const SELF_HOSTED_CDN = import.meta.env.BASE_URL + 'vditor'  // 自建服务器地址

function isCapacitor(): boolean {
  return !!((window as any).Capacitor?.isNative ?? (window as any).Capacitor) 
    || document.documentElement.getAttribute('data-capacitor') !== null 
    || location.protocol === 'file:'
    || /Android.*AppleWebKit.*Version\/\d+\.\d+/.test(navigator.userAgent)
}

const VDITOR_I18N_ZH_CN = {
  'alignCenter': '居中',
  'alignLeft': '居左',
  'alignRight': '居右',
  'alternateText': '替代文本',
  'bold': '粗体',
  'both': '编辑 & 预览',
  'cancelUpload': '取消上传',
  'check': '任务列表',
  'close': '关闭',
  'code': '代码块',
  'code-theme': '代码块主题预览',
  'column': '列',
  'comment': '评论',
  'confirm': '确定',
  'content-theme': '内容主题预览',
  'copied': '已复制',
  'copy': '复制',
  'delete-column': '删除列',
  'delete-row': '删除行',
  'devtools': '开发者工具',
  'down': '下',
  'downloadTip': '该浏览器不支持下载功能',
  'edit': '编辑',
  'edit-mode': '切换编辑模式',
  'emoji': '表情',
  'export': '导出',
  'fileTypeError': '文件类型不允许上传，请压缩后再试',
  'footnoteRef': '脚注标识',
  'fullscreen': '全屏切换',
  'generate': '生成中',
  'headings': '标题',
  'heading1': '一级标题',
  'heading2': '二级标题',
  'heading3': '三级标题',
  'heading4': '四级标题',
  'heading5': '五级标题',
  'heading6': '六级标题',
  'help': '帮助',
  'imageURL': '图片地址',
  'indent': '列表缩进',
  'info': '关于',
  'inline-code': '行内代码',
  'insert-after': '末尾插入行',
  'insert-before': '起始插入行',
  'insertColumnLeft': '在左边插入一列',
  'insertColumnRight': '在右边插入一列',
  'insertRowAbove': '在上方插入一行',
  'insertRowBelow': '在下方插入一行',
  'instantRendering': '即时渲染',
  'italic': '斜体',
  'language': '语言',
  'line': '分隔线',
  'link': '链接',
  'linkRef': '引用标识',
  'list': '无序列表',
  'more': '更多',
  'nameEmpty': '文件名不能为空',
  'ordered-list': '有序列表',
  'outdent': '列表反向缩进',
  'outline': '大纲',
  'over': '超过',
  'performanceTip': '实时预览需 ${x}ms，可点击编辑 & 预览按钮进行关闭',
  'preview': '预览',
  'quote': '引用',
  'record': '开始录音/结束录音',
  'record-tip': '该设备不支持录音功能',
  'recording': '录音中...',
  'redo': '重做',
  'remove': '删除',
  'row': '行',
  'spin': '旋转',
  'splitView': '分屏预览',
  'strike': '删除线',
  'table': '表格',
  'textIsNotEmpty': '文本（不能为空）',
  'title': '标题',
  'tooltipText': '提示文本',
  'undo': '撤销',
  'up': '上',
  'update': '更新',
  'upload': '上传图片或文件',
  'uploadError': '上传错误',
  'uploading': '上传中...',
  'wysiwyg': '所见即所得',
}

async function loadVditor(): Promise<any> {
  if (VditorClass) return VditorClass
  if (vditorLoadFailed) return null
  if ((window as any).Vditor) { VditorClass = (window as any).Vditor; return VditorClass }

  // 第1层：本地动态导入（Vite 打包）
  try {
    const mod = await import('vditor')
    await import('vditor/dist/index.css')
    VditorClass = mod.default
    vditorSource = 'local'
    return VditorClass
  } catch (e) {
    console.warn('第1层失败（本地导入），尝试第2层（自建服务器）:', e)
  }

  // 第2层：自建服务器加载
  try {
    await new Promise<void>((resolve, reject) => {
      const script = document.createElement('script')
      script.src = `${SELF_HOSTED_CDN}/dist/index.min.js`
      script.onload = () => resolve()
      script.onerror = () => reject(new Error('自建服务器 JS load failed'))
      document.head.appendChild(script)
      // 顺便加载 CSS
      const link = document.createElement('link')
      link.rel = 'stylesheet'
      link.href = `${SELF_HOSTED_CDN}/dist/index.css`
      document.head.appendChild(link)
    })
    VditorClass = (window as any).Vditor
    if (!VditorClass) throw new Error('Vditor not found on window')
    vditorSource = 'self'
    console.log('✅ Vditor 从自建服务器加载成功')
    return VditorClass
  } catch (e) {
    console.warn('第2层失败（自建服务器），尝试第3层（CDN）:', e)
  }

  // 第3层：公共 CDN 降级加载
  try {
    await new Promise<void>((resolve, reject) => {
      const link = document.createElement('link')
      link.rel = 'stylesheet'
      link.href = VDITOR_CDN + '/dist/index.css'
      document.head.appendChild(link)
      const script = document.createElement('script')
      script.src = VDITOR_CDN + '/dist/index.min.js'
      script.onload = () => resolve()
      script.onerror = () => reject(new Error('CDN JS load failed'))
      document.head.appendChild(script)
    })
    VditorClass = (window as any).Vditor
    if (!VditorClass) throw new Error('Vditor not found on window')
    vditorSource = 'cdn'
    console.log('✅ Vditor 从 CDN 加载成功')
    return VditorClass
  } catch (e) {
    console.warn('第3层失败（CDN），使用纯文本编辑:', e)
  }

  // 第4层：全部失败 -> 回退 textarea
  vditorLoadFailed = true
  console.warn('❌ Vditor 加载全部失败，回退到纯文本编辑')
  return null
}

function getVditorCdn(): string {
  return vditorSource === 'cdn' ? VDITOR_CDN : import.meta.env.BASE_URL + 'vditor'
}

async function resolveVditorCdn(): Promise<string> {
  // Capacitor: '/vditor' 映射到应用资源根目录
  if (isCapacitor()) return '/vditor'
  if (vditorSource === 'cdn') return VDITOR_CDN
  if (vditorSource === 'self') return SELF_HOSTED_CDN
  return import.meta.env.BASE_URL + 'vditor'
}

interface DirEntry {
  path: string
  name: string
  is_dir: boolean
  ext?: string
  size?: number
  modified?: number
}

const currentPath = ref('')
const entries = ref<DirEntry[]>([])
const loading = ref(true)
const searchQuery = ref('')
const searchResults = ref<DirEntry[]>([])
const searching = ref(false)
let searchTimer: ReturnType<typeof setTimeout> | null = null

// 本地/服务端文件源切换
const fileSource = ref<'server' | 'local'>('server')
const localEntries = ref<DirEntry[]>([])
const localStats = ref({ files: 0, dirs: 0, totalSize: 0 })
const importExportBusy = ref(false)
const importExportMsg = ref('')

// 过滤后的文件列表
const filteredEntries = computed(() => {
  const q = searchQuery.value.trim().toLowerCase()
  // 有搜索关键词时返回搜索结果（服务端和本地都适用）
  if (q) return searchResults.value
  // 本地文件源返回本地条目
  if (fileSource.value === 'local') return localEntries.value
  return entries.value
})

function onSearchInput() {
  if (searchTimer) clearTimeout(searchTimer)
  const q = searchQuery.value.trim()
  if (!q) {
    searchResults.value = []
    searching.value = false
    return
  }
  // 300ms 防抖
  searchTimer = setTimeout(async () => {
    searching.value = true
    try {
      if (fileSource.value === 'local') {
        // 本地模式：递归搜索本地文件树
        const items = await localSearchTree(q, '/')
        searchResults.value = items.map(e => ({
          path: e.path,
          name: e.name,
          is_dir: e.type === 'dir',
          ext: e.type === 'file' ? (e.name.includes('.') ? '.' + e.name.split('.').pop() : '') : undefined,
          size: e.size,
          modified: e.updatedAt,
        }))
      } else {
        // 服务端模式：调用服务端递归搜索
        const { search: searchApi } = await import('../api')
        const res = await searchApi(q)
        const items = res.data?.data ?? res.data ?? []
        searchResults.value = Array.isArray(items) ? items as DirEntry[] : []
      }
    } catch {
      searchResults.value = []
    } finally {
      searching.value = false
    }
  }, 300)
}

function clearSearch() {
  searchQuery.value = ''
  searchResults.value = []
  searching.value = false
}

// WebSocket 消息：服务端文件变更时刷新目录列表
const { wsConnected, onMessage, reconnectWebSocket } = useWebSocket()

onMessage((msg) => {
  if (msg.cmd === 'filechange') {
    const change = msg.data
    if (!change) return
    const changePath = change.path || ''
    const changeType = change.type || ''

    // 如果正在编辑该文件且被外部修改，提示用户
    if (editingFile.value && changePath === editingFile.value && changeType === 'modified') {
      if (!editModified.value) {
        openFile(editingFile.value)
      }
      return
    }

    // 目录变更（created/deleted/renamed/modified）需要刷新目录列表
    if (changeType === 'created' || changeType === 'deleted' || changeType === 'renamed' || changeType === 'modified') {
      const currentDir = currentPath.value
      const parentDir = changePath.includes('/') ? changePath.substring(0, changePath.lastIndexOf('/')) : ''
      if (parentDir === currentDir || changePath.startsWith(currentDir)) {
        navigateTo(currentPath.value)
      }
    }
  } else if (msg.cmd === 'reloadFiletree') {
    navigateTo(currentPath.value)
  }
})

// 前后台切换时重连 WebSocket
document.addEventListener('visibilitychange', () => {
  if (document.visibilityState === 'visible') {
    reconnectWebSocket()
  }
})

// 编辑器状态
const editingFile = ref<string | null>(null)
const originalContent = ref('')
const editModified = ref(false)
const saving = ref(false)
const vditorRef = ref<HTMLDivElement | null>(null)
const textareaRef = ref<HTMLTextAreaElement | null>(null)
const useTextarea = ref(false)
let vditorInstance: any = null

// 动态导入 office 预览组件（代码分割，按需加载）
const VueOfficeDocx = defineAsyncComponent(() => import('@vue-office/docx'))
const VueOfficeExcel = defineAsyncComponent(() => import('@vue-office/excel'))
const VueOfficePptx = defineAsyncComponent(() => import('@vue-office/pptx'))
const VueOfficePdf = defineAsyncComponent(() => import('@vue-office/pdf'))

function getDownloadUrl(path: string): string {
  const base = getServerURL().replace(/\/+$/, '')
  return `${base}/api/file/download/${encodeURIComponent(path)}`
}

// Office 预览状态
const previewFile = ref<string | null>(null)
const previewType = ref<string | null>(null) // 'docx' | 'xlsx' | 'pptx' | 'pdf'
const localPreviewUrl = ref<string>('') // 本地二进制文件的 blob URL
const serverPreviewUrl = ref<string>('') // 服务端文件的 blob URL（经鉴权 fetch 后生成）

const previewUrl = computed(() => {
  if (!previewFile.value) return ''
  if (fileSource.value === 'local' && localPreviewUrl.value) return localPreviewUrl.value
  if (serverPreviewUrl.value) return serverPreviewUrl.value
  return getDownloadUrl(previewFile.value)
})

// 面包屑
const pathSegments = computed(() => {
  if (!currentPath.value) return []
  return currentPath.value.split('/').filter(Boolean)
})

// 新建文件
const showNewFile = ref(false)
const newFileName = ref('')
const creatingFile = ref(false)
const newFileInputRef = ref<HTMLInputElement | null>(null)

function startNewFile() {
  if (!currentPath.value) {
    alert('请在子目录中创建文件')
    return
  }
  showNewFile.value = true
  newFileName.value = ''
  nextTick(() => {
    newFileInputRef.value?.focus()
  })
}

function cancelNewFile() {
  showNewFile.value = false
  newFileName.value = ''
}

async function createFile() {
  const name = newFileName.value.trim()
  if (!name) return
  const filePath = currentPath.value ? currentPath.value + '/' + name : name
  creatingFile.value = true
  try {
    await putFile(filePath, '')
    showNewFile.value = false
    newFileName.value = ''
    await navigateTo(currentPath.value)
    openFile(filePath)
  } catch {
    alert('创建文件失败')
  } finally {
    creatingFile.value = false
  }
}

onMounted(async () => {
  await navigateTo('')
})

async function navigateTo(path: string) {
  currentPath.value = path
  if (fileSource.value === 'local') {
    await loadLocalEntries(path)
  } else {
    loading.value = true
    try {
      const res = await readDir(path)
      const apiData = res.data?.data ?? res.data
      entries.value = Array.isArray(apiData) ? apiData : []
    } catch {
      entries.value = []
    } finally {
      loading.value = false
    }
  }
}

async function loadLocalEntries(path: string = '/') {
  loading.value = true
  try {
    const localItems = await localReadDir(path)
    localEntries.value = localItems.map(e => ({
      path: e.path,
      name: e.name,
      is_dir: e.type === 'dir',
      ext: e.type === 'file' ? (e.name.includes('.') ? '.' + e.name.split('.').pop() : '') : undefined,
      size: e.size,
      modified: e.updatedAt,
    }))
  } catch {
    localEntries.value = []
  } finally {
    loading.value = false
  }
}

async function refreshLocalStats() {
  try {
    localStats.value = await localFSStats()
  } catch { /* ignore */ }
}

function switchFileSource(source: 'server' | 'local') {
  fileSource.value = source
  currentPath.value = ''
  searchQuery.value = ''
  searchResults.value = []
  if (source === 'local') {
    loadLocalEntries('/')
    refreshLocalStats()
  } else {
    navigateTo('')
  }
}

function goUp() {
  if (!currentPath.value) return
  const parts = currentPath.value.split('/')
  parts.pop()
  navigateTo(parts.join('/'))
}

function handleEntryClick(entry: DirEntry) {
  if (entry.is_dir) {
    const targetPath = entry.path
    clearSearch()
    navigateTo(targetPath)
  } else {
    const ext = (entry.ext || '').toLowerCase()
    const officeType = OFFICE_EXTS[ext]
    if (officeType) {
      openPreview(entry.path, officeType)
    } else if (ext === '.html' || ext === '.htm') {
      // HTML 文件在浏览器新标签页打开预览
      const encodedPath = entry.path.split('/').map(s => encodeURIComponent(s)).join('/')
      const base = getServerURL().replace(/\/+$/, '')
      window.open(base + '/api/file/download/' + encodedPath + '?preview=true', '_blank')
    } else {
      openFile(entry.path)
    }
  }
}

const OFFICE_EXTS: Record<string, string> = { '.docx': 'docx', '.xlsx': 'xlsx', '.xls': 'xlsx', '.pptx': 'pptx', '.pdf': 'pdf' }

function openPreview(path: string, type: string) {
  closeEditor()
  if (localPreviewUrl.value) {
    URL.revokeObjectURL(localPreviewUrl.value)
    localPreviewUrl.value = ''
  }
  if (serverPreviewUrl.value) {
    URL.revokeObjectURL(serverPreviewUrl.value)
    serverPreviewUrl.value = ''
  }
  previewFile.value = path
  previewType.value = type
  if (fileSource.value === 'local') {
    localReadFileBlob(path).then((blob) => {
      if (blob) localPreviewUrl.value = URL.createObjectURL(blob)
    }).catch(() => {})
  } else {
    const url = getDownloadUrl(path)
    const headers: Record<string, string> = {}
    const token = getApiToken()
    const code = getAuthCode()
    if (token) headers['Authorization'] = `Token ${token}`
    if (code) headers['X-Auth-Code'] = code
    fetch(url, { headers }).then(r => {
      if (!r.ok) throw new Error(`预览加载失败: ${r.status}`)
      return r.blob()
    }).then(blob => {
      serverPreviewUrl.value = URL.createObjectURL(blob)
    }).catch(e => console.error('预览获取文件失败:', e))
  }
}

function closePreview() {
  if (localPreviewUrl.value) {
    URL.revokeObjectURL(localPreviewUrl.value)
    localPreviewUrl.value = ''
  }
  if (serverPreviewUrl.value) {
    URL.revokeObjectURL(serverPreviewUrl.value)
    serverPreviewUrl.value = ''
  }
  previewFile.value = null
  previewType.value = null
}

function openPdfReader() {
  // 从预览界面跳转到 AI 阅读器（PdfReaderView）
  if (previewFile.value) {
    const path = previewFile.value
    closePreview()
    router.push(`/pdf/${path}`)
  }
}

async function openFile(path: string) {
  try {
    let content = ''
    if (fileSource.value === 'local') {
      const localFile = await localReadFile(path)
      content = localFile?.content ?? ''
    } else {
      const res = await getFile(path)
      const apiData = res.data?.data ?? res.data
      content = apiData?.content ?? ''
    }
    editingFile.value = path
    originalContent.value = content
    editModified.value = false

    await nextTick()

    // 如果 Vditor 实例已存在，复用它（只更新内容）
    if (vditorInstance) {
      try {
        vditorInstance.setValue(content)
        return
      } catch {
        // setValue 失败（实例可能损坏），销毁重建
        try { vditorInstance.destroy() } catch { /* ignore */ }
        vditorInstance = null
      }
    }

    // 尝试加载 Vditor，失败则降级为纯文本编辑
    const Vditor = await loadVditor()
    if (Vditor && vditorRef.value) {
      const isTouch = 'ontouchstart' in window
      const acConfig = loadAutocompleteConfig()
      const currentTheme = document.documentElement.getAttribute('data-theme') || 'dark'
      const vditorCdn = await resolveVditorCdn()
      let vditorReady = false
      try {
        vditorInstance = new Vditor(vditorRef.value, {
          value: content,
          mode: 'ir',
          i18n: VDITOR_I18N_ZH_CN,
          theme: currentTheme === 'light' ? 'classic' : 'dark',
          placeholder: '开始编辑...',
          cache: { enable: false },
          tab: '\t',
          cdn: vditorCdn,
          _lutePath: vditorCdn + '/dist/js/lute/lute.min.js',
          hint: {
            delay: 200,
            parse: false,
            extend: buildHintExtends(acConfig),
          },
          input: () => {
            if (vditorInstance) {
              editModified.value = vditorInstance.getValue() !== originalContent.value
            }
          },
          after: () => { vditorReady = true },
          toolbar: isTouch
            ? ['headings', 'bold', 'italic', 'strike', '|', 'quote', 'inline-code', '|', 'list', 'ordered-list', 'check', '|', 'undo', 'redo', '|', 'edit-mode', 'preview']
            : ['headings', 'bold', 'italic', 'strike', '|', 'quote', 'inline-code', 'code', '|', 'list', 'ordered-list', 'check', '|', 'link', 'table', '|', 'undo', 'redo', '|', 'edit-mode', 'preview', 'fullscreen'],
        })
        // 超时检测：子资源加载失败时 vditor 不会触发 after 回调，也不抛异常
        await new Promise<void>((resolve) => setTimeout(resolve, 6000))
        if (!vditorReady) {
          console.warn('Vditor 子资源加载超时（cdn=' + vditorCdn + '），回退纯文本编辑')
          try { vditorInstance.destroy() } catch { /* ignore */ }
          vditorInstance = null
          useTextarea.value = true
          await nextTick()
          if (textareaRef.value) textareaRef.value.value = content
        }
      } catch (initErr) {
        console.warn('Vditor 初始化失败，回退纯文本编辑:', initErr)
        vditorInstance = null
        useTextarea.value = true
        await nextTick()
        if (textareaRef.value) textareaRef.value.value = content
      }
    } else {
      // Vditor 加载失败，回退纯文本
      useTextarea.value = true
      await nextTick()
      if (textareaRef.value) textareaRef.value.value = content
    }
  } catch {
    alert('无法读取文件')
  }
}

function insertMd(before: string, after: string) {
  const ta = textareaRef.value
  if (!ta) return
  const start = ta.selectionStart
  const end = ta.selectionEnd
  const selected = ta.value.substring(start, end)
  const replacement = before + (selected || '文本') + after
  ta.value = ta.value.substring(0, start) + replacement + ta.value.substring(end)
  ta.selectionStart = start + before.length
  ta.selectionEnd = start + before.length + (selected || '文本').length
  ta.focus()
  editModified.value = true
}

async function saveFile() {
  if (!editingFile.value) return
  saving.value = true
  try {
    let content = ''
    if (useTextarea.value && textareaRef.value) {
      content = textareaRef.value.value
    } else if (vditorInstance) {
      content = vditorInstance.getValue()
    }
    if (fileSource.value === 'local') {
      await localWriteFile(editingFile.value, content)
    } else {
      await putFile(editingFile.value, content)
    }
    originalContent.value = content
    editModified.value = false
  } catch {
    alert('保存失败')
  } finally {
    saving.value = false
  }
}

function closeEditor() {
  if (editModified.value) {
    const action = confirm('文件已修改但未保存，是否保存？\n\n确定 = 保存并关闭\n取消 = 不保存直接关闭')
    if (action) {
      saveFile()
    }
  }
  closePreview()
  if (vditorInstance) {
    vditorInstance.destroy()
    vditorInstance = null
  }
  editingFile.value = null
  originalContent.value = ''
  editModified.value = false
  useTextarea.value = false
}

// ─── 导入导出 ──────────────────────────────────────────

// 单文件从服务端导入到本地（参考笔记实现）
async function importSingleFromServer(entry: DirEntry) {
  try {
    const ext = (entry.ext || '').toLowerCase()
    const dir = entry.path.includes('/') ? entry.path.substring(0, entry.path.lastIndexOf('/')) : ''
    // 确保本地目录存在
    if (dir) await localMkdir(dir)
    if (isBinaryExt(ext)) {
      const url = getDownloadUrl(entry.path)
      const headers: Record<string, string> = {}
      const token = getApiToken()
      const code = getAuthCode()
      if (token) headers['Authorization'] = `Token ${token}`
      if (code) headers['X-Auth-Code'] = code
      const res = await fetch(url, { headers })
      if (!res.ok) throw new Error(`下载失败: ${res.status}`)
      const blob = await res.blob()
      await localWriteFileBlob(entry.path, blob)
    } else {
      // 文本文件：用 getFile API 获取
      const res = await getFile(entry.path)
      const content = res.data?.data?.content ?? res.data?.data ?? ''
      if (typeof content === 'string') {
        await localWriteFile(entry.path, content)
      } else {
        throw new Error('文件内容格式异常')
      }
    }
    importExportMsg.value = `已导入：${entry.name}`
    await refreshLocalStats()
    setTimeout(() => { importExportMsg.value = '' }, 2000)
  } catch (e: any) {
    importExportMsg.value = `导入失败：${e.message || e}`
    setTimeout(() => { importExportMsg.value = '' }, 3000)
  }
}

// 单文件从本地导出到服务端（参考笔记实现）
async function exportSingleToServer(entry: DirEntry) {
  try {
    const ext = (entry.ext || '').toLowerCase()
    if (isBinaryExt(ext)) {
      // 二进制文件：读取 base64 转 Blob，用 upload API 上传
      const blob = await localReadFileBlob(entry.path)
      if (!blob) {
        importExportMsg.value = '读取本地文件失败'
        setTimeout(() => { importExportMsg.value = '' }, 3000)
        return
      }
      const formData = new FormData()
      formData.append('files', blob, entry.name)
      const dir = entry.path.includes('/') ? entry.path.substring(0, entry.path.lastIndexOf('/')) : ''
      formData.append('path', dir)
      await uploadApi(formData)
    } else {
      // 文本文件：用 putFile API 上传
      const localFile = await localReadFile(entry.path)
      const content = localFile?.content ?? ''
      await putFile(entry.path, content)
    }
    importExportMsg.value = `已导出：${entry.name}`
    setTimeout(() => { importExportMsg.value = '' }, 2000)
  } catch (e: any) {
    importExportMsg.value = `导出失败：${e.message || e}`
    setTimeout(() => { importExportMsg.value = '' }, 3000)
  }
}

async function doImportFromServer() {
  if (importExportBusy.value) return
  importExportBusy.value = true
  importExportMsg.value = '正在从服务端导入...'
  try {
    const serverDir = currentPath.value || ''
    const localDir = serverDir || 'imported'
    // 确保本地目录存在
    if (localDir !== '/') await localMkdir(localDir)
    const count = await importDirFromServer(
      serverDir, localDir,
      async (path) => {
        const res = await readDir(path)
        const d = res.data?.data ?? res.data
        return Array.isArray(d) ? d : []
      },
      async (path) => {
        const res = await getFile(path)
        const d = res.data?.data ?? res.data
        return d?.content ?? ''
      },
    )
    importExportMsg.value = `导入完成：${count} 个文件`
    await loadLocalEntries(currentPath.value || '/')
    await refreshLocalStats()
  } catch (e: any) {
    importExportMsg.value = `导入失败：${e.message || e}`
  } finally {
    importExportBusy.value = false
    setTimeout(() => { importExportMsg.value = '' }, 3000)
  }
}

async function doExportToServer() {
  if (importExportBusy.value) return
  importExportBusy.value = true
  importExportMsg.value = '正在导出到服务端...'
  try {
    const localDir = currentPath.value || '/'
    const serverDir = currentPath.value || 'exported'
    const count = await exportDirToServer(
      localDir, serverDir,
      async (path, content) => { await putFile(path, content) },
    )
    importExportMsg.value = `导出完成：${count} 个文件`
    // 刷新服务端列表
    if (fileSource.value === 'server') await navigateTo(currentPath.value)
  } catch (e: any) {
    importExportMsg.value = `导出失败：${e.message || e}`
  } finally {
    importExportBusy.value = false
    setTimeout(() => { importExportMsg.value = '' }, 3000)
  }
}

async function doCreateLocalFile() {
  const name = prompt('输入文件名（如 notes/test.md）：')
  if (!name) return
  await localWriteFile(name, '')
  await loadLocalEntries(currentPath.value || '/')
  await refreshLocalStats()
}

async function doCreateLocalDir() {
  const name = prompt('输入目录名（如 notes/物理）：')
  if (!name) return
  await localMkdir(name)
  await loadLocalEntries(currentPath.value || '/')
  await refreshLocalStats()
}

async function doDeleteLocal(entry: DirEntry) {
  if (!confirm(`确定删除 ${entry.name}？`)) return
  if (entry.is_dir) {
    // 递归删除目录下所有文件
    const items = await localReadDir(entry.path)
    for (const item of items) {
      if (item.type === 'file') await localDeleteFile(item.path)
    }
  } else {
    await localDeleteFile(entry.path)
  }
  await loadLocalEntries(currentPath.value || '/')
  await refreshLocalStats()
}

// 上传状态
const uploading = ref(false)
const uploadProgress = ref(0)
const uploadProgressText = ref('')
const dragOver = ref(false)
const fileInputRef = ref<HTMLInputElement | null>(null)
const folderInputRef = ref<HTMLInputElement | null>(null)

function updateUploadProgress(current: number, total: number, name: string) {
  uploadProgress.value = Math.round((current / total) * 100)
  uploadProgressText.value = `(${current}/${total}) ${name}`
}

async function uploadFiles(files: File[]) {
  if (files.length === 0) return
  if (!currentPath.value) {
    alert('禁止在根目录上传，请先进入子目录')
    return
  }
  uploading.value = true
  uploadProgress.value = 0
  uploadProgressText.value = '准备上传...'
  let completed = 0
  for (const file of files) {
    updateUploadProgress(completed, files.length, file.name)
    try {
      const formData = new FormData()
      formData.append('files', file)
      const relPath = (file as any).webkitRelativePath || file.name
      const dirPart = relPath.includes('/') ? relPath.substring(0, relPath.lastIndexOf('/')) : ''
      const targetPath = currentPath.value
        ? (dirPart ? currentPath.value + '/' + dirPart : currentPath.value)
        : dirPart
      formData.append('path', targetPath)
      await uploadApi(formData)
      completed++
    } catch {
      /* continue */
    }
  }
  uploadProgress.value = 100
  uploadProgressText.value = `完成 (${completed}/${files.length})`
  uploading.value = false
  await navigateTo(currentPath.value)
}

async function handleUpload(event: Event) {
  const input = event.target as HTMLInputElement
  const files = input.files
  if (!files || files.length === 0) return
  await uploadFiles(Array.from(files))
  if (fileInputRef.value) fileInputRef.value.value = ''
}

async function handleFolderUpload(event: Event) {
  const input = event.target as HTMLInputElement
  const files = input.files
  if (!files || files.length === 0) return
  await uploadFiles(Array.from(files))
  if (folderInputRef.value) folderInputRef.value.value = ''
}

async function handleDrop(event: DragEvent) {
  dragOver.value = false
  const files = event.dataTransfer?.files
  if (!files || files.length === 0) return
  await uploadFiles(Array.from(files))
}

// 右键菜单
const ctxMenu = ref({ visible: false, x: 0, y: 0, entry: null as DirEntry | null })

function showCtxMenu(entry: DirEntry, event: MouseEvent) {
  ctxMenu.value = { visible: true, x: event.clientX, y: event.clientY, entry }
}

function closeCtxMenu() {
  ctxMenu.value.visible = false
  ctxMenu.value.entry = null
}

function ctxDownload() {
  if (ctxMenu.value.entry) {
    downloadFile(ctxMenu.value.entry.path)
  }
  closeCtxMenu()
}

function ctxCopyPath() {
  if (ctxMenu.value.entry) {
    navigator.clipboard.writeText(ctxMenu.value.entry.path).catch(() => {})
  }
  closeCtxMenu()
}

function ctxOpenInEditor() {
  if (ctxMenu.value.entry) {
    const path = ctxMenu.value.entry.path
    closeCtxMenu()
    router.push(`/editor/${path}`)
  }
}

function onCtxClickAway() {
  if (ctxMenu.value.visible) closeCtxMenu()
}

// ─── 多实例集群导入 ──────────────────────────────────────
const clusterModal = ref(false)
const clusterScanning = ref(false)
const clusterPeers = ref<Array<{ url: string; port: number; version: string }>>([])
const clusterSelectedUrl = ref('')
const clusterRemotePath = ref('')
const clusterRemoteEntries = ref<DirEntry[]>([])
const clusterRemoteLoading = ref(false)
const clusterSearchQuery = ref('')
const clusterSelectedFiles = ref(new Set<string>())
const clusterTransferring = ref(false)
let clusterSearchTimer: ReturnType<typeof setTimeout> | null = null

async function openClusterImport() {
  clusterModal.value = true
  clusterSelectedUrl.value = ''
  clusterRemotePath.value = ''
  clusterRemoteEntries.value = []
  clusterSearchQuery.value = ''
  clusterSelectedFiles.value = new Set()
  clusterScanning.value = true
  try {
    const res = await clusterInstances()
    const data = res.data?.data ?? res.data
    clusterPeers.value = data?.peers ?? []
  } catch {
    clusterPeers.value = []
  } finally {
    clusterScanning.value = false
  }
}

async function selectClusterInstance(url: string) {
  clusterSelectedUrl.value = url
  clusterRemotePath.value = ''
  clusterSearchQuery.value = ''
  clusterSelectedFiles.value = new Set()
  await loadClusterDir('')
}

async function loadClusterDir(path: string) {
  clusterRemotePath.value = path
  clusterRemoteLoading.value = true
  clusterSearchQuery.value = ''
  try {
    const res = await clusterRemoteReadDir(clusterSelectedUrl.value, path)
    const data = res.data?.data ?? res.data
    clusterRemoteEntries.value = Array.isArray(data) ? data : []
  } catch {
    clusterRemoteEntries.value = []
  } finally {
    clusterRemoteLoading.value = false
  }
}

function onClusterSearchInput() {
  if (clusterSearchTimer) clearTimeout(clusterSearchTimer)
  const q = clusterSearchQuery.value.trim()
  if (!q) {
    loadClusterDir(clusterRemotePath.value)
    return
  }
  clusterSearchTimer = setTimeout(async () => {
    clusterRemoteLoading.value = true
    try {
      const res = await clusterRemoteSearch(clusterSelectedUrl.value, q, clusterRemotePath.value)
      const data = res.data?.data ?? res.data
      clusterRemoteEntries.value = Array.isArray(data) ? data : []
    } catch {
      clusterRemoteEntries.value = []
    } finally {
      clusterRemoteLoading.value = false
    }
  }, 300)
}

function handleClusterEntryClick(entry: DirEntry) {
  if (entry.is_dir) {
    loadClusterDir(entry.path)
  } else {
    // 切换选中状态
    const s = new Set(clusterSelectedFiles.value)
    if (s.has(entry.path)) {
      s.delete(entry.path)
    } else {
      s.add(entry.path)
    }
    clusterSelectedFiles.value = s
  }
}

async function doClusterTransfer() {
  if (clusterSelectedFiles.value.size === 0) return
  clusterTransferring.value = true
  const prefix = currentPath.value ? currentPath.value + '/' : ''
  const files = Array.from(clusterSelectedFiles.value).map(rp => ({
    remote_path: rp,
    local_path: prefix + rp.split('/').pop(),
  }))
  try {
    const res = await clusterTransferBatch(clusterSelectedUrl.value, files)
    const data = res.data?.data ?? res.data
    const ok = data?.ok ?? 0
    const fail = data?.fail ?? 0
    clusterSelectedFiles.value = new Set()
    // 刷新本地目录
    await navigateTo(currentPath.value)
    alert(`导入完成：${ok} 个成功${fail > 0 ? `，${fail} 个失败` : ''}`)
  } catch (e: any) {
    alert('导入失败: ' + (e.message || '未知错误'))
  } finally {
    clusterTransferring.value = false
  }
}

// ─── 主题切换时更新 Vditor（无需销毁重建） ────────────────────────────

function onThemeChange(e: Event) {
  const theme = (e as CustomEvent).detail?.theme || 'dark'
  if (vditorInstance) {
    try {
      const vditorTheme = theme === 'light' ? 'classic' : 'dark'
      const contentTheme = theme === 'light' ? 'light' : 'dark'
      const codeTheme = theme === 'light' ? 'github' : 'tokyo-night-dark'
      vditorInstance.setTheme(vditorTheme, contentTheme, codeTheme)
    } catch { /* ignore if setTheme not available */ }
  }
}

onMounted(() => {
  document.addEventListener('click', onCtxClickAway)
  window.addEventListener('ts2-theme-change', onThemeChange)
})

onUnmounted(() => {
  if (vditorInstance) {
    vditorInstance.destroy()
    vditorInstance = null
  }
  document.removeEventListener('click', onCtxClickAway)
  window.removeEventListener('ts2-theme-change', onThemeChange)
})

function fileIcon(ext?: string): string {
  const e = (ext || '').toLowerCase()
  if (e === '.md') return '📝'
  if (e === '.json') return '📋'
  if (e === '.txt' || e === '.rmd') return '📄'
  if (['.py', '.ts', '.js', '.vue', '.r', '.lua'].includes(e)) return '💻'
  if (['.csv', '.xlsx', '.xls'].includes(e)) return '📊'
  if (['.png', '.jpg', '.jpeg', '.svg', '.gif'].includes(e)) return '🖼️'
  if (e === '.pdf') return '📕'
  if (e === '.docx') return '📝'
  if (e === '.pptx') return '📽️'
  return '📄'
}

function formatSize(bytes: number): string {
  if (bytes < 1024) return `${bytes}B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)}KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)}MB`
}
</script>

<style scoped>
.files-body {
  padding: 0 !important;
  display: flex;
  flex-direction: column;
}

/* 文件源切换 */
.source-toggle {
  display: inline-flex;
  border: 1px solid var(--border);
  border-radius: 6px;
  overflow: hidden;
  margin-left: 8px;
}
.source-btn {
  background: transparent;
  border: none;
  color: var(--fg-muted);
  padding: 4px 12px;
  font-size: 12px;
  cursor: pointer;
  transition: all 0.15s;
}
.source-btn.active {
  background: var(--accent);
  color: #fff;
}
.source-btn:hover:not(.active) {
  background: var(--bg-secondary);
}

/* 本地文件操作 */
.import-export-msg {
  font-size: 12px;
  color: var(--accent);
  margin-left: 8px;
}
.local-stats {
  font-size: 11px;
  color: var(--fg-muted);
  margin-left: 8px;
}
.btn-delete-local {
  background: transparent;
  border: none;
  color: var(--fg-muted);
  font-size: 14px;
  cursor: pointer;
  padding: 2px 6px;
  border-radius: 4px;
  opacity: 0;
  transition: opacity 0.15s;
}
.entry-row:hover .btn-delete-local {
  opacity: 1;
}
.btn-delete-local:hover {
  color: #e74c3c;
  background: var(--bg-secondary);
}

/* 单文件导入/导出按钮 */
.btn-import-single,
.btn-export-single {
  background: transparent;
  border: 1px solid var(--border);
  color: var(--accent);
  font-size: 13px;
  cursor: pointer;
  padding: 2px 8px;
  border-radius: 4px;
  opacity: 0;
  transition: opacity 0.15s, background 0.15s;
  margin-left: 4px;
}
.entry-row:hover .btn-import-single,
.entry-row:hover .btn-export-single {
  opacity: 1;
}
.btn-import-single:hover,
.btn-export-single:hover {
  background: var(--accent);
  color: #fff;
}

/* AI 阅读按钮 */
.btn-ai-read {
  background: transparent;
  border: 1px solid var(--accent);
  color: var(--accent);
  padding: 4px 12px;
  border-radius: 6px;
  font-size: 12px;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.15s;
  white-space: nowrap;
}
.btn-ai-read:hover {
  background: var(--accent);
  color: #fff;
}

.header-actions {
  display: flex;
  gap: 8px;
}

.btn-icon {
  background: transparent;
  border: 1px solid var(--border);
  color: var(--fg-muted);
  padding: 4px 8px;
  font-size: 16px;
  border-radius: 6px;
  cursor: pointer;
}

.btn-icon:hover { color: var(--accent); border-color: var(--accent); }
.btn-icon:disabled { opacity: 0.5; cursor: not-allowed; }

.ws-status {
  font-size: 10px;
  color: var(--danger);
  transition: color 0.3s;
}

.ws-status.connected {
  color: #4ade80;
}

/* 新建文件栏 */
.newfile-bar {
  display: flex;
  gap: 6px;
  padding: 8px 16px;
  background: var(--bg-secondary);
  border-bottom: 1px solid var(--border);
  align-items: center;
}

.newfile-input {
  flex: 1;
  padding: 8px 12px;
  border: 1px solid var(--accent);
  border-radius: 6px;
  background: var(--bg);
  color: var(--fg);
  font-size: 14px;
  font-family: monospace;
}

.newfile-input:focus {
  outline: none;
}

.btn-newfile {
  padding: 8px 16px;
  background: var(--accent);
  color: var(--bg);
  border: none;
  border-radius: 6px;
  font-size: 13px;
  font-weight: 500;
  cursor: pointer;
  white-space: nowrap;
}

.btn-newfile:disabled {
  opacity: 0.5;
}

.btn-newfile-cancel {
  background: none;
  border: none;
  color: var(--fg-muted);
  font-size: 13px;
  cursor: pointer;
  padding: 8px 12px;
}

.btn-newfile-cancel:hover {
  color: var(--fg);
}

/* 搜索过滤框 */
.search-bar {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 8px 16px;
  background: var(--bg-secondary);
  border-bottom: 1px solid var(--border);
  flex-shrink: 0;
}

.search-input {
  flex: 1;
  padding: 7px 12px;
  border: 1px solid var(--border);
  border-radius: 6px;
  background: var(--bg);
  color: var(--fg);
  font-size: 14px;
}

.search-input:focus {
  outline: none;
  border-color: var(--accent);
}

.search-input::placeholder {
  color: var(--fg-muted);
}

.search-clear {
  background: transparent;
  border: none;
  color: var(--fg-muted);
  font-size: 14px;
  cursor: pointer;
  padding: 4px 8px;
}

.search-clear:hover {
  color: var(--fg);
}

/* 面包屑 */
.breadcrumb {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  padding: 8px 16px;
  border-bottom: 1px solid var(--border);
  background: var(--bg-secondary);
  flex-shrink: 0;
  overflow-x: auto;
  white-space: nowrap;
}

.breadcrumb-links {
  display: flex;
  align-items: center;
  gap: 2px;
  overflow-x: auto;
  flex: 1;
}

.breadcrumb-item {
  font-size: 13px;
  color: var(--fg-muted);
  cursor: pointer;
  padding: 2px 6px;
  border-radius: 4px;
  transition: color 0.15s, background 0.15s;
}

.breadcrumb-item:hover {
  color: var(--accent);
  background: rgba(122, 162, 247, 0.1);
}

.breadcrumb-item.active {
  color: var(--fg);
  font-weight: 500;
}

.breadcrumb-sep {
  color: var(--fg-muted);
  font-size: 12px;
  opacity: 0.5;
}

.btn-newfile-breadcrumb {
  flex-shrink: 0;
  background: var(--accent);
  color: var(--bg);
  border: none;
  border-radius: 6px;
  padding: 4px 12px;
  font-size: 12px;
  font-weight: 500;
  cursor: pointer;
  white-space: nowrap;
  transition: filter 0.15s;
}

.btn-newfile-breadcrumb:hover {
  filter: brightness(1.1);
}

/* 目录列表 */
.browser-view {
  flex: 1;
  display: flex;
  flex-direction: column;
}

.loading-root,
.empty-dir {
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 40px;
  color: var(--fg-muted);
  font-size: 14px;
}

.entry-list {
  flex: 1;
  overflow-y: auto;
}

.entry-row {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 11px 16px;
  cursor: pointer;
  transition: background 0.15s;
  border-bottom: 1px solid var(--border);
}

.entry-row:hover {
  background: rgba(255, 255, 255, 0.04);
}

.entry-up {
  opacity: 0.7;
}

.entry-icon {
  font-size: 18px;
  flex-shrink: 0;
  width: 22px;
  text-align: center;
}

.entry-name {
  flex: 1;
  font-size: 14px;
  color: var(--fg);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.entry-name.is-dir {
  color: var(--accent);
  font-weight: 500;
}

.entry-path {
  font-size: 11px;
  color: var(--fg-muted);
  flex-shrink: 0;
  max-width: 120px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  margin-right: 8px;
}

.entry-size {
  font-size: 11px;
  color: var(--fg-muted);
  flex-shrink: 0;
}

/* 编辑器 */
.editor-view {
  display: flex;
  flex-direction: column;
  flex: 1;
  height: 100%;
  min-height: 0;
}

.editor-header {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 10px 16px;
  background: var(--bg-secondary);
  border-bottom: 1px solid var(--border);
}

.btn-back {
  background: transparent;
  color: var(--accent);
  padding: 4px 12px;
  font-size: 14px;
  border: 1px solid var(--border);
}

.btn-back:hover {
  background: rgba(255, 255, 255, 0.06);
}

.editor-path {
  font-size: 13px;
  color: var(--fg-muted);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  flex: 1;
}

.edit-modified {
  color: var(--warning);
  font-size: 16px;
}

.vditor-container {
  flex: 1;
  overflow: hidden;
  min-height: 0;
}

.fallback-textarea {
  flex: 1;
  width: 100%;
  min-height: 300px;
  padding: 12px;
  background: var(--bg);
  color: var(--fg);
  border: none;
  font-size: 14px;
  font-family: 'Consolas', 'Monaco', monospace;
  line-height: 1.6;
  resize: none;
  outline: none;
}

.md-toolbar {
  display: flex;
  gap: 4px;
  padding: 6px 10px;
  background: var(--bg-secondary);
  border-bottom: 1px solid var(--border);
  flex-wrap: wrap;
}

.md-toolbar button {
  padding: 4px 8px;
  border: 1px solid var(--border);
  border-radius: 4px;
  background: var(--bg);
  color: var(--fg);
  font-size: 12px;
  cursor: pointer;
  transition: all 0.15s;
}

.md-toolbar button:hover {
  background: var(--accent);
  color: var(--bg);
  border-color: var(--accent);
}

.vditor-container :deep(.vditor) {
  border: none !important;
  border-radius: 0 !important;
  background: var(--bg) !important;
}

.vditor-container :deep(.vditor-toolbar) {
  background: var(--toolbar-bg, var(--bg-secondary)) !important;
  border-bottom: 1px solid var(--border) !important;
}

.vditor-container :deep(.vditor-toolbar__item) {
  color: var(--toolbar-item, var(--fg-muted)) !important;
}

.vditor-container :deep(.vditor-toolbar__item:hover) {
  color: var(--toolbar-item-hover, var(--fg)) !important;
}

.vditor-container :deep(.vditor-toolbar__item--current) {
  color: var(--accent) !important;
}

/* Vditor 编辑器内部 - 强制跟随主题 */
.vditor-container :deep(.vditor-ir) {
  background: var(--editor-bg, var(--bg)) !important;
  color: var(--fg) !important;
}

.vditor-container :deep(.vditor-sv) {
  background: var(--editor-bg, var(--bg)) !important;
  color: var(--fg) !important;
}

.vditor-container :deep(.vditor-wysiwyg) {
  background: var(--editor-bg, var(--bg)) !important;
  color: var(--fg) !important;
}

.vditor-container :deep(.vditor-reset) {
  background: var(--editor-bg, var(--bg)) !important;
  color: var(--fg) !important;
}

.vditor-container :deep(.vditor-content) {
  background: var(--editor-bg, var(--bg)) !important;
}

.vditor-container :deep(.vditor-ir__block),
.vditor-container :deep(.vditor-wysiwyg__block),
.vditor-container :deep(.vditor-sv__block) {
  background: var(--editor-bg, var(--bg)) !important;
  color: var(--fg) !important;
}

/* Vditor 预览模式 */
.vditor-container :deep(.vditor-preview) {
  background: var(--editor-bg, var(--bg)) !important;
  color: var(--fg) !important;
}

.vditor-container :deep(.vditor-preview__content) {
  color: var(--fg) !important;
}

@media (max-width: 768px) {
  .vditor-container :deep(.vditor-toolbar) {
    overflow-x: auto;
    flex-wrap: nowrap;
  }
  .vditor-container :deep(.vditor-toolbar__item) {
    flex-shrink: 0;
  }
  .vditor-container :deep(.vditor-reset) {
    padding: 10px 8px !important;
    font-size: 15px;
  }
  .vditor-container :deep(.vditor-ir),
  .vditor-container :deep(.vditor-sv),
  .vditor-container :deep(.vditor-wysiwyg) {
    min-height: calc(100vh - 120px) !important;
  }
}

.editor-actions {
  display: flex;
  justify-content: flex-end;
  padding: 10px 16px;
  background: var(--bg-secondary);
  border-top: 1px solid var(--border);
}

/* Office 预览容器 */
.office-preview-container {
  flex: 1;
  overflow: auto;
  min-height: 0;
  background: var(--bg);
}

.preview-error {
  display: flex;
  align-items: center;
  justify-content: center;
  height: 200px;
  color: var(--fg-muted);
  font-size: 14px;
}

.btn-save {
  background: var(--accent);
  color: var(--bg);
  font-weight: 600;
  padding: 8px 24px;
}

.btn-save:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

/* 上传 */
.upload-section {
  padding: 16px;
  border-top: 1px solid var(--border);
  background: var(--bg-secondary);
  flex-shrink: 0;
  transition: background 0.2s;
}

.upload-section.drag-over {
  background: rgba(var(--accent-rgb, 59, 130, 246), 0.1);
  border-color: var(--accent);
}

.upload-section.uploading {
  cursor: progress;
}

.upload-row {
  display: flex;
  gap: 8px;
  align-items: center;
}

.btn-upload {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  background: var(--accent);
  color: var(--bg);
  padding: 7px 14px;
  border-radius: 6px;
  font-size: 13px;
  font-weight: 500;
  cursor: pointer;
  white-space: nowrap;
  transition: background 0.15s;
}

.btn-upload:hover {
  filter: brightness(1.1);
}

.btn-upload-folder {
  background: transparent;
  color: var(--accent);
  border: 1px solid var(--accent);
}

.upload-hint {
  font-size: 12px;
  color: var(--fg-muted);
  margin-top: 8px;
  text-align: center;
  padding: 4px;
  border: 1px dashed var(--border);
  border-radius: 6px;
}

.upload-hint-active {
  color: var(--accent);
  border-color: var(--accent);
  background: rgba(var(--accent-rgb, 59, 130, 246), 0.05);
}

.upload-progress-bar {
  margin-top: 8px;
  height: 20px;
  background: var(--border);
  border-radius: 10px;
  overflow: hidden;
  position: relative;
}

.upload-progress-fill {
  height: 100%;
  background: var(--accent);
  border-radius: 10px;
  transition: width 0.3s ease;
}

.upload-progress-text {
  position: absolute;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 11px;
  color: var(--bg);
  font-weight: 600;
  text-shadow: 0 1px 2px rgba(0,0,0,0.3);
}

/* 右键上下文菜单 */
.context-menu {
  position: fixed;
  z-index: 1000;
  min-width: 140px;
  background: var(--bg-secondary);
  border: 1px solid var(--border);
  border-radius: 8px;
  box-shadow: 0 4px 16px rgba(0,0,0,0.3);
  padding: 4px 0;
  overflow: hidden;
}

.ctx-item {
  padding: 10px 16px;
  font-size: 13px;
  color: var(--fg);
  cursor: pointer;
  transition: background 0.1s;
  user-select: none;
}

.ctx-item:hover {
  background: rgba(var(--accent-rgb, 59, 130, 246), 0.12);
  color: var(--accent);
}

.ctx-item:active {
  background: rgba(var(--accent-rgb, 59, 130, 246), 0.2);
}

/* 多实例集群导入 */
.btn-cluster-import {
  background: var(--accent, #3b82f6);
  color: #fff;
  border: none;
  cursor: pointer;
  font-size: 12px;
  padding: 6px 12px;
  border-radius: 6px;
}

.cluster-modal-overlay {
  position: fixed;
  inset: 0;
  background: rgba(0,0,0,0.5);
  z-index: 1000;
  display: flex;
  align-items: center;
  justify-content: center;
}

.cluster-modal {
  background: var(--bg, #1e1e2e);
  border-radius: 12px;
  width: 90%;
  max-width: 500px;
  max-height: 80vh;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  box-shadow: 0 8px 32px rgba(0,0,0,0.4);
}

.cluster-modal-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 16px;
  border-bottom: 1px solid var(--border, #333);
}

.cluster-modal-header h3 {
  margin: 0;
  font-size: 16px;
}

.cluster-close {
  background: none;
  border: none;
  color: var(--fg-muted);
  font-size: 18px;
  cursor: pointer;
}

.cluster-instances,
.cluster-browser {
  padding: 16px;
  overflow-y: auto;
  flex: 1;
}

.cluster-scanning,
.cluster-empty {
  text-align: center;
  color: var(--fg-muted);
  padding: 32px 0;
}

.cluster-instance-card {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 12px;
  border-radius: 8px;
  border: 1px solid var(--border, #333);
  margin-bottom: 8px;
  cursor: pointer;
  transition: background 0.15s;
}

.cluster-instance-card:hover {
  background: rgba(var(--accent-rgb, 59, 130, 246), 0.1);
}

.cluster-instance-icon {
  font-size: 24px;
}

.cluster-instance-info {
  flex: 1;
}

.cluster-instance-url {
  font-weight: 600;
  font-size: 14px;
}

.cluster-instance-meta {
  font-size: 11px;
  color: var(--fg-muted);
}

.cluster-instance-arrow {
  color: var(--accent);
  font-size: 18px;
}

.cluster-browser-header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;
}

.cluster-browser-header .btn-back {
  background: none;
  border: none;
  color: var(--accent);
  cursor: pointer;
  font-size: 13px;
  padding: 4px 8px;
}

.cluster-remote-label {
  font-size: 12px;
  color: var(--fg-muted);
  font-family: monospace;
}

.cluster-search-bar {
  display: flex;
  gap: 4px;
  margin-bottom: 8px;
}

.cluster-entry-list {
  max-height: 300px;
  overflow-y: auto;
}

.cluster-selected {
  background: rgba(var(--accent-rgb, 59, 130, 246), 0.12);
}

.entry-check {
  margin-left: auto;
  font-size: 14px;
}

.check-on {
  color: var(--accent);
  font-weight: bold;
}

.check-off {
  color: var(--fg-dim);
}

.cluster-action-bar {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 12px 0 0;
  border-top: 1px solid var(--border, #333);
  margin-top: 12px;
  font-size: 13px;
}

.btn-cluster-transfer {
  background: var(--accent);
  color: #fff;
  border: none;
  border-radius: 6px;
  padding: 6px 16px;
  font-size: 13px;
  cursor: pointer;
}

.btn-cluster-transfer:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.btn-cluster-clear {
  background: none;
  border: 1px solid var(--border);
  color: var(--fg-muted);
  border-radius: 6px;
  padding: 6px 12px;
  font-size: 12px;
  cursor: pointer;
}
</style>

