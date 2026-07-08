<template>
  <div class="view slides-view" @keydown="onKeyDown" tabindex="0" ref="viewRef">
    <!-- 顶部栏 -->
    <header class="slides-header">
      <div class="header-left">
        <button class="icon-btn text-btn" @click="showOutline = !showOutline" :title="showOutline ? '关闭大纲' : '打开大纲'">
          <span class="btn-text">☰</span>
        </button>
        <div class="notebook-title-wrap">
          <input
            v-model="notebookTitle"
            class="notebook-title-input"
            placeholder="笔记标题"
            @change="saveNotebook"
          />
        </div>
        <!-- 笔记源切换 -->
        <div class="source-toggle">
          <button class="source-btn" :class="{ active: nbSource === 'server' }" @click="switchNbSource('server')">服务端</button>
          <button class="source-btn" :class="{ active: nbSource === 'local' }" @click="switchNbSource('local')">本地</button>
        </div>
        <!-- 笔记选择器 -->
        <div class="nb-selector">
          <button class="icon-btn text-btn" @click="toggleNbList" title="切换笔记">
            <span class="btn-text">📚</span>
          </button>
          <div class="nb-dropdown" v-if="showNbList">
            <!-- 搜索框 -->
            <div class="nb-dropdown-search" v-if="nbSource === 'server'">
              <input
                type="text"
                v-model="nbSearchQuery"
                @input="onNbSearchInput"
                placeholder="搜索笔记..."
                class="nb-search-input"
              />
              <button v-if="nbSearchQuery" class="nb-search-clear" @click="clearNbSearch">✕</button>
            </div>
            <!-- 搜索结果模式（仅服务端） -->
            <template v-if="nbSource === 'server' && nbSearchQuery.trim()">
              <div class="nb-dropdown-breadcrumb">
                <span class="nb-crumb">🔍 {{ nbSearchResults.length }} 结果</span>
              </div>
              <div class="nb-dropdown-item" v-for="r in nbSearchResults" :key="r.relPath" @click="openNotebookByPath(r.relPath)">
                <span class="nb-dropdown-name">📝 {{ stripMdExt(r.name) }}
                  <span class="nb-search-path" v-if="r.relPath.includes('/')">({{ r.relPath.substring(0, r.relPath.lastIndexOf('/')) }})</span>
                </span>
                <button class="nb-dropdown-del" @click.stop="deleteNotebookByPath(r.relPath)" title="删除">✕</button>
              </div>
            </template>
            <!-- 正常逐层浏览模式 -->
            <template v-else>
              <!-- 路径面包屑 -->
              <div class="nb-dropdown-breadcrumb" v-if="nbSource === 'server' && nbCurrentDir">
                <span class="nb-crumb" @click="nbNavigateTo('')">Notes</span>
                <template v-for="(seg, i) in nbCurrentDir.split('/')" :key="i">
                  <span class="nb-crumb-sep">/</span>
                  <span class="nb-crumb" @click="nbNavigateTo(nbCurrentDir.split('/').slice(0, i + 1).join('/'))">{{ seg }}</span>
                </template>
              </div>
              <!-- 本地面包屑 -->
              <div class="nb-dropdown-breadcrumb" v-else-if="nbSource === 'local' && localNbDir">
                <span class="nb-crumb" @click="nbLocalNavigateTo('')">notebooks</span>
                <template v-for="(seg, i) in localNbDir.split('/')" :key="i">
                  <span class="nb-crumb-sep">/</span>
                  <span class="nb-crumb" @click="nbLocalNavigateTo(localNbDir.split('/').slice(0, i + 1).join('/'))">{{ seg }}</span>
                </template>
              </div>
              <div class="nb-dropdown-breadcrumb" v-else>
                <span class="nb-crumb">{{ nbSource === 'server' ? 'Notes' : 'notebooks' }}</span>
              </div>
              <!-- 服务端：逐层浏览 -->
              <template v-if="nbSource === 'server'">
                <div class="nb-dropdown-item nb-dropdown-folder" v-for="d in nbSubDirs" :key="d.path" @click="nbNavigateTo(d.path)">
                  <span class="nb-dropdown-name">📁 {{ d.name }}</span>
                </div>
                <div class="nb-dropdown-item" v-for="nb in notebookList" :key="nb.name" @click="openNotebook(nb.name)">
                  <span class="nb-dropdown-name">{{ stripMdExt(nb.name) }}</span>
                  <button class="nb-dropdown-import" @click.stop="importSingleFromServer(nb.name)" title="导入到本地">↓</button>
                  <button class="nb-dropdown-del" @click.stop="deleteNotebookFile(nb.name)" title="删除">✕</button>
                </div>
              </template>
              <!-- 本地：完整目录浏览 -->
              <template v-else>
                <div class="nb-dropdown-item nb-dropdown-folder" v-if="localNbDir" @click="nbLocalNavigateTo(localNbDir.split('/').slice(0, -1).join('/'))">
                  <span class="nb-dropdown-name">📁 ..</span>
                </div>
                <div class="nb-dropdown-item nb-dropdown-folder" v-for="d in localNbDirs" :key="d.path" @click="nbLocalNavigateTo(d.relPath)">
                  <span class="nb-dropdown-name">📁 {{ d.name }}</span>
                </div>
                <div class="nb-dropdown-item" v-for="nb in localNbList" :key="nb.path" @click="openLocalNotebook(nb.name)">
                  <span class="nb-dropdown-name">{{ stripMdExt(nb.name) }}</span>
                  <button class="nb-dropdown-export" @click.stop="exportSingleToServer(nb.name)" title="导出到服务端">↑</button>
                  <button class="nb-dropdown-del" @click.stop="deleteLocalNotebook(nb.name)" title="删除">✕</button>
                </div>
              </template>
            </template>
            <div class="nb-dropdown-item nb-dropdown-new" @click="createNewNotebook">
              + 新建笔记
            </div>
          </div>
        </div>
      </div>
      <div class="header-center">
        <div class="page-indicator">
          <button class="page-arrow" @click="prevSlide" :disabled="currentIndex === 0" title="上一页 (←)">
            <span class="arrow-text">‹</span>
          </button>
          <span class="page-num">{{ currentIndex + 1 }}</span>
          <span class="page-sep">/</span>
          <span class="page-total">{{ slides.length }}</span>
          <button class="page-arrow" @click="nextSlide" title="下一页 (→)">
            <span class="arrow-text">›</span>
          </button>
        </div>
      </div>
      <div class="header-right">
        <button class="icon-btn text-btn" @click="addSlide(currentIndex + 1)" title="插入新页">
          <span class="btn-text">+</span>
        </button>
        <div class="header-divider"></div>
        <button v-if="nbSource === 'server'" class="icon-btn text-btn" @click="doSaveToServer" :disabled="savingServer" title="保存到服务器 (Ctrl+S)">
          <span class="btn-text">💾</span>
        </button>
        <button v-else class="icon-btn text-btn" @click="saveToLocalNotebook" title="保存到本地 (Ctrl+S)">
          <span class="btn-text">💾</span>
        </button>
        <button v-if="nbSource === 'server'" class="icon-btn text-btn" @click="doLoadFromServer" :disabled="loadingServer" title="从服务器加载">
          <span class="btn-text">📥</span>
        </button>
        <button class="icon-btn text-btn" @click="exportAsMarkdown" title="导出 Markdown">
          <span class="btn-text">MD</span>
        </button>
        <button class="icon-btn text-btn" @click="exportNotebook" title="导出 JSON">
          <span class="btn-text">⬇️</span>
        </button>
        <button class="icon-btn text-btn" @click="importNotebook" title="导入">
          <span class="btn-text">⬆️</span>
        </button>
        <template v-if="nbSource === 'local'">
          <div class="header-divider"></div>
          <button class="icon-btn text-btn nb-action-btn" @click="doImportFromServer" :disabled="importExportBusy" title="从服务端导入笔记">
            <span class="btn-text">↓</span>
          </button>
          <button class="icon-btn text-btn nb-action-btn" @click="doExportToServer" :disabled="importExportBusy" title="导出笔记到服务端">
            <span class="btn-text">↑</span>
          </button>
          <span v-if="importExportMsg" class="import-export-msg">{{ importExportMsg }}</span>
          <span class="local-stats" v-if="localStats.files > 0">{{ localStats.files }}文件</span>
        </template>
        <span v-if="saveStatus" class="save-badge" :class="saveStatusType">{{ saveStatus }}</span>
      </div>
    </header>

    <div class="slides-body" @click="onBodyClick" @touchstart="onTouchStart" @touchend="onTouchEnd">
      <!-- 大纲侧边栏（始终渲染，用CSS控制显隐） -->
      <aside class="slides-outline" :class="{ 'sidebar-hidden': !showOutline }">
        <div class="outline-header">
          <span class="outline-label">大纲</span>
          <span class="outline-count">{{ slides.length }} 页</span>
        </div>
        <div class="outline-list">
          <div
            v-for="(slide, idx) in slides"
            :key="slide.id"
            class="outline-item"
            :class="{ active: idx === currentIndex }"
            @click="goToSlide(idx)"
          >
            <span class="outline-num">{{ idx + 1 }}</span>
            <span class="outline-title">{{ getSlideTitle(slide, idx) }}</span>
            <button class="outline-del" @click.stop="deleteSlide(idx)" title="删除此页" v-if="slides.length > 1">
              <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><path d="M18 6L6 18M6 6l12 12"/></svg>
            </button>
          </div>
        </div>
        <button class="outline-add" @click="addSlide(slides.length)" title="在末尾添加新页">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><path d="M12 5v14M5 12h14"/></svg>
          添加页面
        </button>
      </aside>

      <!-- 编辑区 -->
      <div class="slides-editor">
        <div class="slide-title-bar">
          <input
            v-model="currentSlide.title"
            class="slide-title-input"
            placeholder="页面标题（可选）"
            @change="saveNotebook"
          />
          <span class="slide-time" v-if="currentSlide.updatedAt">{{ formatTime(currentSlide.updatedAt) }}</span>
        </div>
        <!-- Vditor 编辑器 -->
        <div v-if="!useTextarea" ref="vditorRef" class="vditor-container"></div>
        <!-- textarea 降级编辑器 -->
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
            placeholder="开始编辑..."
            @input="onTextareaInput"
          ></textarea>
        </template>
      </div>
    </div>

    <!-- 隐藏的文件输入 -->
    <input type="file" ref="importInput" accept=".json,.md,.markdown,.rmd,.rmarkdown,.mdx,.txt" style="display:none" @change="onImportFile" />

    <!-- 冲突解决对话框 -->
    <div v-if="conflictDialog" class="conflict-overlay" @click.self="conflictDialog = false">
      <div class="conflict-dialog">
        <h3>同步冲突</h3>
        <p>本地版本比服务器版本更新，请选择保留哪个版本：</p>
        <div class="conflict-info">
          <div class="conflict-item">
            <span class="conflict-label">本地</span>
            <span class="conflict-time">{{ formatTime(conflictLocalTime) }}</span>
          </div>
          <div class="conflict-item">
            <span class="conflict-label">服务器</span>
            <span class="conflict-time">{{ formatTime(conflictServerTime) }}</span>
          </div>
        </div>
        <div class="conflict-actions">
          <button class="conflict-btn local-btn" @click="resolveConflict(true)">保留本地</button>
          <button class="conflict-btn server-btn" @click="resolveConflict(false)">使用服务器</button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, onMounted, onUnmounted, nextTick, computed } from 'vue'
import { putFile, getFile, readDir, saveNotebook as apiSaveNotebook, getNotebook as apiGetNotebook } from '../api'
import { loadAutocompleteConfig, buildHintExtends } from '../autocomplete'
import {
  localReadDir, localReadFile, localWriteFile, localDeleteFile, localMkdir,
  importDirFromServer, exportDirToServer, localFSStats,
  type DirEntry as LocalDirEntry,
} from '../stores/localFS'

// ─── 数据模型 ────────────────────────────────────────

interface Slide {
  id: string
  title: string
  markdown: string
  createdAt: number
  updatedAt: number
}

interface Notebook {
  id: string
  title: string
  slides: Slide[]
  createdAt: number
  updatedAt: number
}

const STORAGE_KEY = 'ts2_slides_notebook'
const NB_LOCAL_DIR = 'notebooks'  // 本地笔记存储目录前缀
// 所有 markdown 变体扩展名（小写，用于模式匹配）
  const NB_MD_EXTS = ['.md', '.markdown', '.rmd', '.rmarkdown', '.mdx']
  const NB_MD_EXT_PAT = NB_MD_EXTS.map(e => e.replace('.', '\\.')).join('|')
  // 文件 I/O 用：含常见大小写变体，以兼容大小写文件系统
  const NB_MD_EXTS_IO = [...NB_MD_EXTS, '.Rmd', '.RMD', '.RMARKDOWN', '.Mdx', '.MDX', '.MD', '.MARKDOWN']

// 本地/服务端笔记源切换
const nbSource = ref<'server' | 'local'>('server')
const localNbList = ref<{name: string; path: string; updatedAt: number; isDir: boolean}[]>([])
const localNbDirs = ref<{name: string; relPath: string}[]>([])
const localNbDir = ref('')  // 本地笔记子目录路径
const localStats = ref({ files: 0, dirs: 0, totalSize: 0 })
const importExportBusy = ref(false)
const importExportMsg = ref('')

// Vditor 加载策略：4层容灾
// 第1层：本地 npm 包（打包进应用）
// 第2层：自建服务器（BASE_URL/vditor）
// 第3层：公共 CDN（unpkg）
// 第4层：回退到 textarea
let VditorClass: any = null
let _vditorLoadFailed = false
let _vditorSource: 'local' | 'self' | 'cdn' | null = null

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

async function resolveVditorCdn(): Promise<string> {
  // Capacitor: '/vditor' 映射到应用资源根目录
  if (isCapacitor()) return '/vditor'
  if (_vditorSource === 'cdn') return VDITOR_CDN
  if (_vditorSource === 'self') return SELF_HOSTED_CDN
  return import.meta.env.BASE_URL + 'vditor'
}

function getVditorCdn(): string {
  if (isCapacitor()) return '/vditor'
  if (_vditorSource === 'cdn') return VDITOR_CDN
  if (_vditorSource === 'self') return SELF_HOSTED_CDN
  return import.meta.env.BASE_URL + 'vditor'
}

async function loadVditor(): Promise<any> {
  if (VditorClass) return VditorClass
  if (_vditorLoadFailed) return null
  if ((window as any).Vditor) { VditorClass = (window as any).Vditor; return VditorClass }

  // 第1层：本地动态导入（Vite 打包）
  try {
    const mod = await import('vditor')
    await import('vditor/dist/index.css')
    VditorClass = mod.default
    _vditorSource = 'local'
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
    _vditorSource = 'self'
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
    _vditorSource = 'cdn'
    console.log('✅ Vditor 从 CDN 加载成功')
    return VditorClass
  } catch (e) {
    console.warn('第3层失败（CDN），使用纯文本编辑:', e)
  }

  // 第4层：全部失败 -> 回退 textarea
  _vditorLoadFailed = true
  console.warn('❌ Vditor 加载全部失败，回退到纯文本编辑')
  return null
}

function generateId(): string {
  return Date.now().toString(36) + Math.random().toString(36).substr(2, 6)
}

function createSlide(title = '', markdown = ''): Slide {
  const now = Date.now()
  return { id: generateId(), title, markdown, createdAt: now, updatedAt: now }
}

function loadNotebook(): Notebook {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (raw) {
      const nb = JSON.parse(raw)
      if (nb.slides && nb.slides.length > 0) return nb
    }
  } catch { /* ignore */ }
  return {
    id: generateId(),
    title: '我的笔记',
    slides: [createSlide('欢迎', '# 欢迎\n\n这是第一页笔记。\n\n按 **→** 翻到下一页，按 **←** 返回上一页。\n\n点击 **+ 新页** 插入空白页。')],
    createdAt: Date.now(),
    updatedAt: Date.now(),
  }
}

// ─── 状态 ────────────────────────────────────────

const notebookId = ref('')
const notebookTitle = ref('')
const slides = reactive<Slide[]>([])
const currentIndex = ref(0)
const noteExt = ref('.md')  // 当前打开的服务端笔记原始扩展名

// 替换文件名中的 MD 扩展名（用于显示）
function stripMdExt(name: string): string {
  return name.replace(new RegExp(`\\.(${NB_MD_EXT_PAT})$`, 'i'), '')
}
// 判断是否为 MD 变体文件名（大小写不敏感）
function isMdFile(name: string): boolean {
  const lower = name.toLowerCase()
  return NB_MD_EXTS.some(e => lower.endsWith(e))
}
// 判断本地笔记文件（JSON 或 MD 变体）
function isLocalNbFile(name: string): boolean {
  return name.toLowerCase().endsWith('.json') || isMdFile(name)
}

const showOutline = ref(false)
const vditorRef = ref<HTMLElement | null>(null)
const viewRef = ref<HTMLElement | null>(null)
const importInput = ref<HTMLInputElement | null>(null)
const savingServer = ref(false)
const loadingServer = ref(false)
const saveStatus = ref('')
const saveStatusType = ref<'ok' | 'err'>('ok')
const notebookList = ref<{name: string}[]>([])
const nbCurrentDir = ref('')  // 服务端笔记当前所在子目录（相对 Notes）
const nbSubDirs = ref<{name: string; path: string}[]>([])  // 当前目录下的子文件夹
const nbSearchQuery = ref('')  // 搜索关键词
const nbSearchResults = ref<{name: string; relPath: string}[]>([])  // 搜索结果
const showNbList = ref(false)
const useTextarea = ref(false)
const textareaRef = ref<HTMLTextAreaElement | null>(null)
const conflictDialog = ref(false)
const conflictLocalTime = ref(0)
const conflictServerTime = ref(0)
let pendingServerData: { title: string; slides: Slide[] } | null = null

let vditorInstance: any = null
let isSaving = false
let isSwitching = false

const currentSlide = computed(() => slides[currentIndex.value] || createSlide())

// ─── Vditor 初始化 ──────────────────────────────────────
async function initVditor() {
  useTextarea.value = false
  const V = await loadVditor()
  if (!V || !vditorRef.value) {
    // Vditor 不可用，降级为 textarea
    useTextarea.value = true
    await nextTick()
    if (textareaRef.value && slides[currentIndex.value]) {
      textareaRef.value.value = slides[currentIndex.value].markdown || ''
    }
    return
  }

  const isTouch = 'ontouchstart' in window
  const acConfig = loadAutocompleteConfig()
  const currentTheme = document.documentElement.getAttribute('data-theme') || 'dark'
  const vditorCdn = await resolveVditorCdn()
  let vditorReady = false
  try {
    vditorInstance = new V(vditorRef.value, {
      value: slides[currentIndex.value]?.markdown || '',
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
        if (vditorInstance && !isSwitching && slides[currentIndex.value]) {
          slides[currentIndex.value].markdown = vditorInstance.getValue()
          slides[currentIndex.value].updatedAt = Date.now()
          debounceSave()
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
      if (textareaRef.value && slides[currentIndex.value]) {
        textareaRef.value.value = slides[currentIndex.value].markdown || ''
      }
    }
  } catch (initErr) {
    console.warn('Vditor 初始化失败，降级为纯文本编辑:', initErr)
    vditorInstance = null
    useTextarea.value = true
    await nextTick()
    if (textareaRef.value && slides[currentIndex.value]) {
      textareaRef.value.value = slides[currentIndex.value].markdown || ''
    }
  }
}

// ─── 本地保存 ────────────────────────────────────────

let saveTimer: ReturnType<typeof setTimeout> | null = null
let autoSaveTimer: ReturnType<typeof setInterval> | null = null
let lastAutoSaveAt = 0  // 上次自动保存时间（毫秒时间戳）
const AUTO_SAVE_INTERVAL = 30000  // 每 30 秒自动保存

// 防抖保存到 localStorage（快速恢复）
function debounceSave() {
  if (saveTimer) clearTimeout(saveTimer)
  saveTimer = setTimeout(() => saveToLocalStorage(), 500)
}

// 保存到 localStorage（快速恢复，始终执行）
function saveToLocalStorage() {
  if (isSaving) return
  isSaving = true
  try {
    const nb: Notebook = {
      id: notebookId.value,
      title: notebookTitle.value,
      slides: slides.map(s => ({ ...s })),
      createdAt: 0,
      updatedAt: Date.now(),
    }
    const existing = localStorage.getItem(STORAGE_KEY)
    if (existing) {
      try { nb.createdAt = JSON.parse(existing).createdAt || Date.now() } catch { nb.createdAt = Date.now() }
    } else {
      nb.createdAt = Date.now()
    }
    localStorage.setItem(STORAGE_KEY, JSON.stringify(nb))
    showSaveStatus('已保存', 'ok')
  } finally {
    isSaving = false
  }
}

// 启动周期性自动保存（每 30 秒）
function startAutoSave() {
  stopAutoSave()
  autoSaveTimer = setInterval(async () => {
    // 如果距上次保存或距上次自动保存超过 30 秒，则自动保存
    if (slides.length === 0) return
    saveCurrentSlide()
    try {
      if (nbSource.value === 'local') {
        await saveToLocalNotebookSilent()
      } else {
        await doSaveToServer()
      }
      lastAutoSaveAt = Date.now()
    } catch { /* silent fail */ }
  }, AUTO_SAVE_INTERVAL)
}

function stopAutoSave() {
  if (autoSaveTimer) {
    clearInterval(autoSaveTimer)
    autoSaveTimer = null
  }
}

// 保存笔记本（统一入口，防抖调用本地存储，周期性调用远端）
function saveNotebook() {
  saveToLocalStorage()
}

// 静默保存到 IndexedDB（无反馈，用于自动保存/退出）
async function saveToLocalNotebookSilent() {
  saveCurrentSlide()
  try {
    const nb: Notebook = {
      id: notebookId.value,
      title: notebookTitle.value,
      slides: slides.map(s => ({ ...s })),
      createdAt: 0,
      updatedAt: Date.now(),
    }
    const existing = localStorage.getItem(STORAGE_KEY)
    if (existing) {
      try { nb.createdAt = JSON.parse(existing).createdAt } catch { /* ignore */ }
    }
    const safeName = (notebookTitle.value || 'note').replace(/[\\/:*?"<>|]/g, '_')
    const dirPrefix = localNbDir.value ? `${NB_LOCAL_DIR}/${localNbDir.value}` : NB_LOCAL_DIR
    await localMkdir(dirPrefix)
    await localWriteFile(`${dirPrefix}/${safeName}.json`, JSON.stringify(nb, null, 2))
    const md = slidesToMarkdown(slides, notebookTitle.value)
    await localWriteFile(`${dirPrefix}/${safeName}.md`, md)
  } catch { /* silent fail */ }
}

// 保存笔记到本地（带用户反馈）
async function saveToLocalNotebook() {
  await saveToLocalNotebookSilent()
  try {
    await loadLocalNbList()
    await refreshLocalStats()
    showSaveStatus('已保存到本地', 'ok')
  } catch {
    showSaveStatus('本地保存失败', 'err')
  }
}

function showSaveStatus(msg: string, type: 'ok' | 'err') {
  saveStatus.value = msg
  saveStatusType.value = type
  setTimeout(() => { saveStatus.value = '' }, 2000)
}

function formatTime(ts: number): string {
  if (!ts) return ''
  const d = new Date(ts)
  const h = d.getHours().toString().padStart(2, '0')
  const m = d.getMinutes().toString().padStart(2, '0')
  return `${h}:${m}`
}

// 将 slides 数组转为 Markdown（参数化版本，供本地导出使用）
function slidesToMarkdown(slides: Slide[], title: string): string {
  const parts: string[] = []
  if (title) parts.push(`# ${title}\n`)
  for (let i = 0; i < slides.length; i++) {
    const s = slides[i]
    if (s.title) parts.push(`## ${s.title}\n`)
    parts.push(s.markdown || '')
    if (i < slides.length - 1) parts.push('\n---\n')
  }
  return parts.join('\n')
}

// ─── 服务器保存/加载（notes 目录 MD 文件）────────────────────────

function notebookToMD(): string {
  const parts: string[] = []
  if (notebookTitle.value) {
    parts.push(`# ${notebookTitle.value}\n`)
  }
  for (let i = 0; i < slides.length; i++) {
    const slide = slides[i]
    if (slide.title) {
      parts.push(`## ${slide.title}\n`)
    }
    parts.push(slide.markdown || '')
    if (i < slides.length - 1) {
      parts.push('\n---\n')
    }
  }
  return parts.join('\n')
}

function mdToSlides(content: string): { title: string; slides: Slide[] } {
  const sections = content.split(/\n---\n/)
  const importedSlides: Slide[] = []
  let nbTitle = ''
  for (let i = 0; i < sections.length; i++) {
    let md = sections[i].trim()
    if (!md) continue
    let title = ''
    const firstLine = md.split('\n')[0]
    if (i === 0 && firstLine.startsWith('# ')) {
      nbTitle = firstLine.replace(/^# +/, '').trim()
      md = md.split('\n').slice(1).join('\n').trim()
      if (!md) continue
    }
    if (firstLine.startsWith('## ')) {
      title = firstLine.replace(/^## +/, '').trim()
      md = md.split('\n').slice(1).join('\n').trim()
    }
    importedSlides.push(createSlide(title, md))
  }
  if (importedSlides.length === 0) {
    importedSlides.push(createSlide('', content))
  }
  return { title: nbTitle, slides: importedSlides }
}

function notesPath(): string {
  const name = (notebookTitle.value || 'note').replace(/[\\/:*?"<>|]/g, '_')
  return `Notes/${name}${noteExt.value}`
}

async function doSaveToServer() {
  saveCurrentSlide()
  savingServer.value = true
  try {
    // 保存 MD 到 notes 目录
    const md = notebookToMD()
    await putFile(notesPath(), md)
    // 同时保存 JSON 元数据
    const meta = {
      id: notebookId.value,
      title: notebookTitle.value,
      slides: slides.map(s => ({ ...s })),
      createdAt: 0,
      updatedAt: Date.now(),
    }
    const existing = localStorage.getItem(STORAGE_KEY)
    if (existing) {
      try { meta.createdAt = JSON.parse(existing).createdAt } catch { /* ignore */ }
    }
    await apiSaveNotebook(notebookId.value, meta)
    showSaveStatus('已保存', 'ok')
  } catch (e: any) {
    showSaveStatus('保存失败', 'err')
  } finally {
    savingServer.value = false
  }
}

async function doLoadFromServer() {
  loadingServer.value = true
  try {
    // 先尝试从 notes 目录读取 MD
    const res = await getFile(notesPath())
    const content = res.data?.data?.content ?? res.data?.data
    if (content && typeof content === 'string' && content.trim()) {
      const parsed = mdToSlides(content)
      // 冲突检测：比较本地和服务器 updatedAt
      const localUpdated = Math.max(...slides.map(s => s.updatedAt || 0), 0)
      const serverUpdated = Math.max(...parsed.slides.map(s => s.updatedAt || 0), 0)
      if (localUpdated > serverUpdated + 5000 && slides.some(s => s.markdown.trim())) {
        // 本地比服务器新超过5秒，可能存在冲突
        pendingServerData = parsed
        conflictLocalTime.value = localUpdated
        conflictServerTime.value = serverUpdated
        conflictDialog.value = true
        loadingServer.value = false
        return
      }
      // 无冲突，直接加载
      applyServerData(parsed)
    } else {
      // 回退到 JSON API
      const nbRes = await apiGetNotebook(notebookId.value)
      const data = nbRes.data?.data ?? nbRes.data
      if (data && data.slides) {
        const serverSlides: Slide[] = (data.slides || []).map((s: any) => ({
          id: s.id || generateId(),
          title: s.title || '',
          markdown: s.markdown || '',
          createdAt: s.createdAt || Date.now(),
          updatedAt: s.updatedAt || Date.now(),
        }))
        // 冲突检测
        const localUpdated = Math.max(...slides.map(s => s.updatedAt || 0), 0)
        const serverUpdated = Math.max(...serverSlides.map(s => s.updatedAt || 0), 0)
        if (localUpdated > serverUpdated + 5000 && slides.some(s => s.markdown.trim())) {
          pendingServerData = { title: data.title || '', slides: serverSlides }
          conflictLocalTime.value = localUpdated
          conflictServerTime.value = serverUpdated
          conflictDialog.value = true
          loadingServer.value = false
          return
        }
        applyServerData({ title: data.title || '', slides: serverSlides })
      } else {
        showSaveStatus('无数据', 'err')
      }
    }
  } catch (e: any) {
    showSaveStatus('加载失败', 'err')
  } finally {
    loadingServer.value = false
  }
}

function applyServerData(data: { title: string; slides: Slide[] }) {
  saveCurrentSlide()
  if (data.title) notebookTitle.value = data.title
  slides.splice(0, slides.length, ...data.slides)
  currentIndex.value = 0
  loadSlide(0)
  saveNotebook()
  showSaveStatus('已加载', 'ok')
}

function resolveConflict(useLocal: boolean) {
  conflictDialog.value = false
  if (useLocal) {
    // 保留本地版本，推送到服务器
    showSaveStatus('保留本地', 'ok')
    doSaveToServer()
  } else if (pendingServerData) {
    // 使用服务器版本
    applyServerData(pendingServerData)
    pendingServerData = null
  }
}

// ─── 翻页 ────────────────────────────────────────

function saveCurrentSlide() {
  if (useTextarea.value && textareaRef.value && slides[currentIndex.value]) {
    slides[currentIndex.value].markdown = textareaRef.value.value
    slides[currentIndex.value].updatedAt = Date.now()
  } else if (vditorInstance && slides[currentIndex.value]) {
    try {
      const val = vditorInstance.getValue()
      if (val !== undefined) {
        slides[currentIndex.value].markdown = val
        slides[currentIndex.value].updatedAt = Date.now()
      }
    } catch { /* ignore */ }
  }
}

function loadSlide(index: number) {
  const md = slides[index]?.markdown || ''
  if (useTextarea.value && textareaRef.value) {
    textareaRef.value.value = md
  } else if (vditorInstance) {
    isSwitching = true
    try {
      vditorInstance.setValue(md)
    } finally {
      setTimeout(() => { isSwitching = false }, 100)
    }
  }
}

function onTextareaInput() {
  if (slides[currentIndex.value]) {
    slides[currentIndex.value].markdown = textareaRef.value?.value || ''
    slides[currentIndex.value].updatedAt = Date.now()
    debounceSave()
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
  onTextareaInput()
}

function goToSlide(index: number) {
  if (index === currentIndex.value) return
  saveCurrentSlide()
  saveNotebook()
  currentIndex.value = index
  loadSlide(index)
}

function prevSlide() {
  if (currentIndex.value > 0) {
    goToSlide(currentIndex.value - 1)
  }
}

function nextSlide() {
  if (currentIndex.value < slides.length - 1) {
    goToSlide(currentIndex.value + 1)
  } else {
    addSlide(currentIndex.value + 1)
  }
}

function addSlide(insertAt: number) {
  saveCurrentSlide()
  const newSlide = createSlide('', '')
  slides.splice(insertAt, 0, newSlide)
  currentIndex.value = insertAt
  loadSlide(currentIndex.value)
  saveNotebook()
}

function deleteSlide(index: number) {
  if (slides.length <= 1) return
  slides.splice(index, 1)
  if (currentIndex.value >= slides.length) {
    currentIndex.value = slides.length - 1
  } else if (currentIndex.value > index) {
    currentIndex.value--
  } else if (currentIndex.value === index) {
    currentIndex.value = Math.min(index, slides.length - 1)
  }
  loadSlide(currentIndex.value)
  saveNotebook()
}

// ─── 键盘 ────────────────────────────────────────

function onKeyDown(e: KeyboardEvent) {
  const tag = (e.target as HTMLElement)?.tagName?.toLowerCase()
  const isInput = tag === 'input' || tag === 'textarea' || tag === 'select'

  if ((e.ctrlKey || e.metaKey) && e.key === 'ArrowLeft' && !isInput) {
    e.preventDefault()
    prevSlide()
  } else if ((e.ctrlKey || e.metaKey) && e.key === 'ArrowRight' && !isInput) {
    e.preventDefault()
    nextSlide()
  } else if ((e.ctrlKey || e.metaKey) && e.key === 's') {
    e.preventDefault()
    if (nbSource.value === 'local') {
      saveToLocalNotebook()
    } else {
      doSaveToServer()
    }
  }
}

// ─── 辅助 ────────────────────────────────────────

function onBodyClick(e: MouseEvent) {
  const target = e.target as HTMLElement
  // 点击编辑区空白处时关闭大纲和笔记列表
  if (target.closest('.slides-editor')) {
    showOutline.value = false
    showNbList.value = false
  }
}

// ─── 触摸手势：左右滑动切换页面 ────────────────────────────

let touchStartX = 0
let touchStartY = 0
let touchStartTime = 0

function onTouchStart(e: TouchEvent) {
  const touch = e.touches[0]
  touchStartX = touch.clientX
  touchStartY = touch.clientY
  touchStartTime = Date.now()
}

function onTouchEnd(e: TouchEvent) {
  const touch = e.changedTouches[0]
  const dx = touch.clientX - touchStartX
  const dy = touch.clientY - touchStartY
  const dt = Date.now() - touchStartTime
  // 判断为水平快速滑动：水平距离 > 60px，垂直距离 < 水平距离的一半，时间 < 500ms
  if (Math.abs(dx) > 60 && Math.abs(dy) < Math.abs(dx) * 0.5 && dt < 500) {
    if (dx > 0) {
      prevSlide()
    } else {
      nextSlide()
    }
  }
}

function getSlideTitle(slide: Slide, idx: number): string {
  if (slide.title) return slide.title
  const firstLine = slide.markdown?.split('\n')[0] || ''
  const heading = firstLine.replace(/^#+\s*/, '').trim()
  return heading || `第 ${idx + 1} 页`
}

// ─── 导出为 Markdown ────────────────────────────────────────

function exportAsMarkdown() {
  saveCurrentSlide()
  const parts: string[] = []
  if (notebookTitle.value) {
    parts.push(`# ${notebookTitle.value}\n`)
  }
  for (let i = 0; i < slides.length; i++) {
    const slide = slides[i]
    if (slide.title) {
      parts.push(`## ${slide.title}\n`)
    }
    parts.push(slide.markdown || '')
    if (i < slides.length - 1) {
      parts.push('\n---\n')
    }
  }
  const md = parts.join('\n')
  const blob = new Blob([md], { type: 'text/markdown;charset=utf-8' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `${notebookTitle.value || 'note'}.md`
  a.click()
  URL.revokeObjectURL(url)
  showSaveStatus('已导出 MD', 'ok')
}

// ─── 导入/导出 JSON ────────────────────────────────────────

function exportNotebook() {
  saveCurrentSlide()
  saveNotebook()
  const nb: Notebook = {
    id: notebookId.value,
    title: notebookTitle.value,
    slides: slides.map(s => ({ ...s })),
    createdAt: 0,
    updatedAt: Date.now(),
  }
  const existing = localStorage.getItem(STORAGE_KEY)
  if (existing) {
    try { nb.createdAt = JSON.parse(existing).createdAt } catch { /* ignore */ }
  }
  const blob = new Blob([JSON.stringify(nb, null, 2)], { type: 'application/json' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `${notebookTitle.value || 'note'}.json`
  a.click()
  URL.revokeObjectURL(url)
  showSaveStatus('已导出 JSON', 'ok')
}

function importNotebook() {
  importInput.value?.click()
}

function onImportFile(e: Event) {
  const file = (e.target as HTMLInputElement)?.files?.[0]
  if (!file) return
  const reader = new FileReader()
  reader.onload = () => {
    const content = reader.result as string
    const ext = file.name.split('.').pop()?.toLowerCase()

    if (ext === 'md' || ext === 'markdown' || ext === 'rmd' || ext === 'rmarkdown' || ext === 'mdx' || ext === 'txt') {
      importFromMarkdown(content, file.name.replace(/\.\w+$/, ''))
      return
    }

    try {
      const nb = JSON.parse(content)
      if (!nb.slides || !Array.isArray(nb.slides)) {
        alert('无效的笔记文件')
        return
      }
      notebookTitle.value = nb.title || '导入的笔记'
      if (nb.id) notebookId.value = nb.id
      slides.splice(0, slides.length, ...nb.slides.map((s: any) => ({
        id: s.id || generateId(),
        title: s.title || '',
        markdown: s.markdown || '',
        createdAt: s.createdAt || Date.now(),
        updatedAt: s.updatedAt || Date.now(),
      })))
      currentIndex.value = 0
      loadSlide(0)
      saveNotebook()
      showSaveStatus('已导入', 'ok')
    } catch {
      alert('文件解析失败')
    }
  }
  reader.readAsText(file)
  ;(e.target as HTMLInputElement).value = ''
}

function importFromMarkdown(content: string, filename: string) {
  const sections = content.split(/\n---\n/)
  const importedSlides: Slide[] = []

  for (let i = 0; i < sections.length; i++) {
    let md = sections[i].trim()
    if (!md) continue
    let title = ''
    const firstLine = md.split('\n')[0]
    if (firstLine.startsWith('# ')) {
      title = firstLine.replace(/^# +/, '').trim()
      md = md.split('\n').slice(1).join('\n').trim()
    } else if (firstLine.startsWith('## ')) {
      title = firstLine.replace(/^## +/, '').trim()
      md = md.split('\n').slice(1).join('\n').trim()
    }
    importedSlides.push(createSlide(title, md))
  }

  if (importedSlides.length === 0) {
    importedSlides.push(createSlide('', content))
  }

  notebookTitle.value = filename || '导入的笔记'
  slides.splice(0, slides.length, ...importedSlides)
  currentIndex.value = 0
  loadSlide(0)
  saveNotebook()
  showSaveStatus(`已导入 ${importedSlides.length} 页`, 'ok')
}

// ─── 多笔记管理 ────────────────────────────────────────

async function toggleNbList() {
  showNbList.value = !showNbList.value
  if (showNbList.value) {
    await loadNotebookList()
    await nextTick()
    // 检测下拉菜单是否溢出屏幕右侧，若溢出则改为右对齐
    const dd = document.querySelector('.nb-dropdown') as HTMLElement | null
    const btn = document.querySelector('.nb-selector > .icon-btn') as HTMLElement | null
    if (dd && btn) {
      const btnRect = btn.getBoundingClientRect()
      const ddW = dd.offsetWidth
      const vw = window.innerWidth
      if (btnRect.left + ddW > vw - 8) {
        dd.style.left = 'auto'
        dd.style.right = '8px'
      } else {
        dd.style.left = '0'
        dd.style.right = 'auto'
      }
    }
  }
}

// 进入子目录
function nbNavigateTo(dirPath: string) {
  nbCurrentDir.value = dirPath
  loadNotebookList()
}

// 递归搜索整个 Notes 目录树
async function nbSearchTree(dirPath: string, prefix: string, query: string, results: {name: string; relPath: string}[]): Promise<void> {
  try {
    const res = await readDir(dirPath)
    const files = res.data?.data ?? res.data
    if (!Array.isArray(files)) return
    for (const f of files) {
      if (!f.is_dir && isMdFile(f.name)) {
        const relPath = prefix ? `${prefix}/${f.name}` : f.name
        const displayName = stripMdExt(f.name).toLowerCase()
        if (displayName.includes(query)) {
          results.push({ name: f.name, relPath })
        }
      }
    }
    for (const f of files) {
      if (f.is_dir) {
        const subPrefix = prefix ? `${prefix}/${f.name}` : f.name
        await nbSearchTree(`Notes/${subPrefix}`, subPrefix, query, results)
      }
    }
  } catch { /* ignore */ }
}

// 搜索输入处理
let nbSearchTimer: any = null
function onNbSearchInput() {
  if (nbSearchTimer) clearTimeout(nbSearchTimer)
  nbSearchTimer = setTimeout(async () => {
    const q = nbSearchQuery.value.trim().toLowerCase()
    if (!q) {
      nbSearchResults.value = []
      await loadNotebookList()
      return
    }
    nbSearchResults.value = []
    await nbSearchTree('Notes', '', q, nbSearchResults.value)
  }, 300)
}

// 清除搜索
function clearNbSearch() {
  nbSearchQuery.value = ''
  nbSearchResults.value = []
  loadNotebookList()
}

// 通过完整相对路径打开笔记（搜索结果用）
async function openNotebookByPath(relPath: string) {
  showNbList.value = false
  saveCurrentSlide()
  saveToLocalStorage()
  if (nbSource.value === 'local') await saveToLocalNotebookSilent()
  else await doSaveToServer()
  try {
    const res = await getFile(`Notes/${relPath}`)
    const content = res.data?.data?.content ?? res.data?.data
    if (content && typeof content === 'string' && content.trim()) {
      const parsed = mdToSlides(content)
      const fileName = relPath.split('/').pop() || relPath
      notebookTitle.value = parsed.title || stripMdExt(fileName)
      noteExt.value = '.' + (fileName.split('.').pop() || 'md')
      notebookId.value = generateId()
      slides.splice(0, slides.length, ...parsed.slides)
      currentIndex.value = 0
      loadSlide(0)
      saveNotebook()
      startAutoSave()
      showSaveStatus('已打开', 'ok')
    }
  } catch {
    showSaveStatus('打开失败', 'err')
  }
}

// 通过完整相对路径删除笔记（搜索结果用）
async function deleteNotebookByPath(relPath: string) {
  if (!confirm(`确定删除 "${relPath}"？此操作不可恢复。`)) return
  try {
    const { default: axios } = await import('axios')
    const baseURL = localStorage.getItem('ts2_server_url') || ''
    await axios.post(`${baseURL}/api/file/removeFile`, { path: `Notes/${relPath}` })
    showSaveStatus('已删除', 'ok')
    // 刷新搜索结果
    const q = nbSearchQuery.value.trim().toLowerCase()
    if (q) {
      nbSearchResults.value = []
      await nbSearchTree('Notes', '', q, nbSearchResults.value)
    }
  } catch {
    showSaveStatus('删除失败', 'err')
  }
}

async function loadNotebookList() {
  if (nbSource.value === 'local') {
    await loadLocalNbList()
    return
  }
  // 有搜索关键词时走递归搜索，不在此处理（由 onNbSearchInput 处理）
  if (nbSearchQuery.value.trim()) return
  try {
    const dir = nbCurrentDir.value ? `Notes/${nbCurrentDir.value}` : 'Notes'
    const res = await readDir(dir)
    const files = res.data?.data ?? res.data
    if (Array.isArray(files)) {
      // 子文件夹（笔记本）
      nbSubDirs.value = files
        .filter((f: any) => f.is_dir)
        .map((f: any) => ({ name: f.name, path: nbCurrentDir.value ? `${nbCurrentDir.value}/${f.name}` : f.name }))
      // 笔记文件
      notebookList.value = files.filter((f: any) =>
        !f.is_dir && isMdFile(f.name)
      )
    }
  } catch { /* ignore */ }
}

async function loadLocalNbList() {
  try {
    await localMkdir(NB_LOCAL_DIR)
    const subDir = localNbDir.value ? `${NB_LOCAL_DIR}/${localNbDir.value}` : NB_LOCAL_DIR
    const entries = await localReadDir(subDir)
    // 子目录
    localNbDirs.value = entries
      .filter(e => e.type === 'dir')
      .map(e => ({
        name: e.name,
        relPath: localNbDir.value ? `${localNbDir.value}/${e.name}` : e.name,
      }))
    // 笔记文件（去重：同名基只显示一次，优先 .json，否则取第一个 MD 变体）
    const seen = new Map<string, { name: string; path: string; updatedAt: number }>()
    for (const e of entries) {
      if (e.type !== 'file' || !isLocalNbFile(e.name)) continue
      const base = e.name.replace(/\.\w+$/, '')
      const isJson = e.name.endsWith('.json')
      const existing = seen.get(base)
      if (!existing || (isJson && !existing.name.endsWith('.json'))) {
        seen.set(base, { name: e.name, path: e.path, updatedAt: e.updatedAt })
      }
    }
    localNbList.value = Array.from(seen.values())
  } catch { /* ignore */ }
}

function nbLocalNavigateTo(dirPath: string) {
  localNbDir.value = dirPath
  loadLocalNbList()
}

async function refreshLocalStats() {
  try {
    localStats.value = await localFSStats()
  } catch { /* ignore */ }
}

async function switchNbSource(source: 'server' | 'local') {
  // 切换前保存当前笔记到原源
  saveCurrentSlide()
  saveToLocalStorage()
  if (nbSource.value === 'local') await saveToLocalNotebookSilent()
  else await doSaveToServer()
  // 停止自动保存，防止内存中旧源数据泄漏到新源
  stopAutoSave()
  // 重置为空白笔记
  const fresh = { id: generateId(), title: '新笔记', slides: [createSlide('', '')], createdAt: Date.now(), updatedAt: Date.now() }
  notebookId.value = fresh.id
  notebookTitle.value = fresh.title
  slides.splice(0, slides.length, ...fresh.slides)
  currentIndex.value = 0
  noteExt.value = '.md'
  await nextTick()
  loadSlide(0)

  nbSource.value = source
  notebookList.value = []
  nbSubDirs.value = []
  nbCurrentDir.value = ''
  nbSearchQuery.value = ''
  nbSearchResults.value = []
  localNbList.value = []
  localNbDirs.value = []
  localNbDir.value = ''
  if (source === 'local') {
    await loadLocalNbList()
    await refreshLocalStats()
  } else {
    await loadNotebookList()
  }
}

async function openNotebook(fileName: string) {
  showNbList.value = false
  if (nbSource.value === 'local') {
    await openLocalNotebook(fileName)
    return
  }
  // 切换前保存当前笔记
  saveCurrentSlide()
  saveToLocalStorage()
  if (nbSource.value === 'local') await saveToLocalNotebookSilent()
  else await doSaveToServer()

  try {
    const filePath = nbCurrentDir.value ? `Notes/${nbCurrentDir.value}/${fileName}` : `Notes/${fileName}`
    const res = await getFile(filePath)
    const content = res.data?.data?.content ?? res.data?.data
    if (content && typeof content === 'string' && content.trim()) {
      const parsed = mdToSlides(content)
      notebookTitle.value = parsed.title || stripMdExt(fileName)
      noteExt.value = '.' + (fileName.split('.').pop() || 'md')
      notebookId.value = generateId()
      slides.splice(0, slides.length, ...parsed.slides)
      currentIndex.value = 0
      loadSlide(0)
      saveNotebook()
      startAutoSave()
      showSaveStatus('已打开', 'ok')
    }
  } catch {
    showSaveStatus('打开失败', 'err')
  }
}

async function openLocalNotebook(name: string) {
  saveCurrentSlide()
  saveToLocalStorage()
  if (nbSource.value === 'server') await doSaveToServer()

  // 构建文件路径（支持子目录）
  const baseName = name.replace(/\.\w+$/, '')
  const dirPrefix = localNbDir.value ? `${NB_LOCAL_DIR}/${localNbDir.value}` : NB_LOCAL_DIR
  const filePrefix = `${dirPrefix}/${baseName}`

  try {
    // 先尝试 JSON 格式
    const jsonFile = await localReadFile(`${filePrefix}.json`)
    if (jsonFile?.content) {
      const nb = JSON.parse(jsonFile.content)
      if (nb.slides && Array.isArray(nb.slides)) {
        notebookTitle.value = nb.title || baseName
        notebookId.value = nb.id || generateId()
        slides.splice(0, slides.length, ...nb.slides.map((s: any) => ({
          id: s.id || generateId(),
          title: s.title || '',
          markdown: s.markdown || '',
          createdAt: s.createdAt || Date.now(),
          updatedAt: s.updatedAt || Date.now(),
        })))
        currentIndex.value = 0
        loadSlide(0)
        saveNotebook()
        startAutoSave()
        showSaveStatus('已打开本地笔记', 'ok')
        return
      }
    }
    // 回退到 MD 格式（尝试所有变体）
    for (const ext of NB_MD_EXTS_IO) {
      const mdFile = await localReadFile(`${filePrefix}${ext}`)
      if (mdFile?.content) {
        const parsed = mdToSlides(mdFile.content)
        notebookTitle.value = parsed.title || baseName
        notebookId.value = generateId()
        slides.splice(0, slides.length, ...parsed.slides)
        currentIndex.value = 0
        loadSlide(0)
        saveNotebook()
        startAutoSave()
        showSaveStatus('已打开本地笔记', 'ok')
        return
      }
    }
    showSaveStatus('笔记为空', 'err')
  } catch {
    showSaveStatus('打开失败', 'err')
  }
}

async function deleteLocalNotebook(name: string) {
  if (!confirm(`确定删除本地笔记 "${name}"？`)) return
  try {
    const dirPrefix = localNbDir.value ? `${NB_LOCAL_DIR}/${localNbDir.value}` : NB_LOCAL_DIR
    // 尝试删除 JSON 和所有 MD 变体
    try { await localDeleteFile(`${dirPrefix}/${name.replace(/\.\w+$/, '')}.json`) } catch { /* ignore */ }
    for (const ext of NB_MD_EXTS_IO) {
      try { await localDeleteFile(`${dirPrefix}/${name}`) } catch { /* ignore */ }
    }
    showSaveStatus('已删除', 'ok')
    await loadLocalNbList()
    await refreshLocalStats()
  } catch {
    showSaveStatus('删除失败', 'err')
  }
}

async function doImportFromServer() {
  if (importExportBusy.value) return
  importExportBusy.value = true
  importExportMsg.value = '正在从服务端导入...'
  try {
    const serverDir = nbCurrentDir.value ? `Notes/${nbCurrentDir.value}` : 'Notes'
    const localDir = localNbDir.value ? `${NB_LOCAL_DIR}/${localNbDir.value}` : NB_LOCAL_DIR
    await localMkdir(localDir)
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
    await loadLocalNbList()
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
    const localDir = localNbDir.value ? `${NB_LOCAL_DIR}/${localNbDir.value}` : NB_LOCAL_DIR
    const serverDir = nbCurrentDir.value ? `Notes/${nbCurrentDir.value}` : 'Notes'
    const count = await exportDirToServer(
      localDir, serverDir,
      async (path, content) => { await putFile(path, content) },
    )
    importExportMsg.value = `导出完成：${count} 个文件`
    if (nbSource.value === 'server') await loadNotebookList()
  } catch (e: any) {
    importExportMsg.value = `导出失败：${e.message || e}`
  } finally {
    importExportBusy.value = false
    setTimeout(() => { importExportMsg.value = '' }, 3000)
  }
}

// 单个笔记从服务端导入到本地
async function importSingleFromServer(fileName: string) {
  try {
    const filePath = nbCurrentDir.value ? `Notes/${nbCurrentDir.value}/${fileName}` : `Notes/${fileName}`
    const res = await getFile(filePath)
    const content = res.data?.data?.content ?? res.data?.data
    if (content && typeof content === 'string') {
      const safeName = stripMdExt(fileName).replace(/[\\/:*?"<>|]/g, '_')
      const originalExt = '.' + (fileName.split('.').pop() || 'md')
      const dirPrefix = localNbDir.value ? `${NB_LOCAL_DIR}/${localNbDir.value}` : NB_LOCAL_DIR
      await localMkdir(dirPrefix)
      // 先解析 MD 为 slides JSON，再存储
      const parsed = mdToSlides(content)
      const nb = {
        id: generateId(),
        title: parsed.title || safeName,
        slides: parsed.slides,
        createdAt: Date.now(),
        updatedAt: Date.now(),
      }
      await localWriteFile(`${dirPrefix}/${safeName}.json`, JSON.stringify(nb, null, 2))
      await localWriteFile(`${dirPrefix}/${safeName}${originalExt}`, content) // 保存原始扩展名
      await loadLocalNbList()
      showSaveStatus('已导入', 'ok')
      setTimeout(() => { showSaveStatus('') }, 2000)
    }
  } catch {
    showSaveStatus('导入失败', 'err')
  }
}

// 单个笔记从本地导出到服务端
async function exportSingleToServer(name: string) {
  try {
    const dirPrefix = localNbDir.value ? `${NB_LOCAL_DIR}/${localNbDir.value}` : NB_LOCAL_DIR
    const baseName = name.replace(/\.\w+$/, '')
    let content = ''
    let foundExt = '.md'
    // 先试 JSON
    const jsonFile = await localReadFile(`${dirPrefix}/${baseName}.json`)
    if (jsonFile?.content) {
      const nb = JSON.parse(jsonFile.content)
      content = slidesToMarkdown(nb.slides, nb.title)
    } else {
      // 再试所有 MD 变体，记录实际扩展名
      for (const ext of NB_MD_EXTS_IO) {
        const mdFile = await localReadFile(`${dirPrefix}/${baseName}${ext}`)
        if (mdFile?.content) {
          content = mdFile.content
          foundExt = ext
          break
        }
      }
    }
    if (content) {
      const serverDir = nbCurrentDir.value ? `Notes/${nbCurrentDir.value}` : 'Notes'
      await putFile(`${serverDir}/${baseName}${foundExt}`, content)
      showSaveStatus('已导出', 'ok')
      setTimeout(() => { showSaveStatus('') }, 2000)
    }
  } catch {
    showSaveStatus('导出失败', 'err')
  }
}

async function deleteNotebookFile(fileName: string) {
  if (!confirm(`确定删除 "${fileName}"？此操作不可恢复。`)) return
  try {
    const { default: axios } = await import('axios')
    const baseURL = localStorage.getItem('ts2_server_url') || ''
    await axios.post(`${baseURL}/api/file/removeFile`, { path: nbCurrentDir.value ? `Notes/${nbCurrentDir.value}/${fileName}` : `Notes/${fileName}` })
    showSaveStatus('已删除', 'ok')
    loadNotebookList()
  } catch {
    showSaveStatus('删除失败', 'err')
  }
}

function createNewNotebook() {
  showNbList.value = false
  const name = prompt('新笔记标题：')
  if (!name || !name.trim()) return
  saveCurrentSlide()
  notebookId.value = generateId()
  notebookTitle.value = name.trim()
  slides.splice(0, slides.length, createSlide('', `# ${name.trim()}\n\n`))
  currentIndex.value = 0
  loadSlide(0)
  saveNotebook()
  if (nbSource.value === 'local') {
    saveToLocalNotebook()
  } else {
    doSaveToServer()
  }
}

// ─── 生命周期 ────────────────────────────────────────

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

onMounted(async () => {
  const nb = loadNotebook()
  notebookId.value = nb.id || generateId()
  notebookTitle.value = nb.title
  slides.splice(0, slides.length, ...nb.slides)
  currentIndex.value = 0

  await nextTick()
  await initVditor()

  loadNotebookList()
  startAutoSave()
  viewRef.value?.focus()

  window.addEventListener('ts2-theme-change', onThemeChange)
})

onUnmounted(() => {
  saveCurrentSlide()
  saveToLocalStorage()  // 始终保存到 localStorage
  // 退出时同步保存到当前源
  if (nbSource.value === 'local') {
    saveToLocalNotebookSilent()
  } else {
    doSaveToServer()
  }
  stopAutoSave()  // 停止周期性自动保存
  if (vditorInstance) {
    try { vditorInstance.destroy() } catch { /* ignore */ }
    vditorInstance = null
  }
  if (saveTimer) clearTimeout(saveTimer)
  window.removeEventListener('ts2-theme-change', onThemeChange)
})
</script>

<style scoped>
.slides-view {
  display: flex;
  flex-direction: column;
  height: 100vh;
  min-height: 100vh;
  outline: none;
  background: var(--bg);
}

/* ─── 顶部栏 ──────────────────────────────────────── */
.slides-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 12px;
  min-height: 44px;
  border-bottom: 1px solid var(--border);
  background: var(--bg-secondary);
  flex-shrink: 0;
  gap: 8px;
  position: relative;
  z-index: 10;
  flex-wrap: wrap;
}

.header-left {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
  flex-shrink: 1;
  flex-wrap: wrap;
}

.header-center {
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}

.header-right {
  display: flex;
  align-items: center;
  gap: 4px;
}

.header-divider {
  width: 1px;
  height: 18px;
  background: var(--border);
  margin: 0 4px;
}

.icon-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 32px;
  height: 32px;
  border: 1px solid var(--border);
  border-radius: 6px;
  background: var(--bg);
  color: var(--fg);
  cursor: pointer;
  transition: all 0.15s;
}

.icon-btn svg {
  stroke: var(--fg);
}

.icon-btn:hover {
  background: var(--btn-hover-bg, var(--border));
  color: var(--btn-hover-fg, var(--fg));
  border-color: var(--accent);
}

.icon-btn:hover svg {
  stroke: var(--btn-hover-fg, var(--fg));
}

.icon-btn:disabled {
  opacity: 0.35;
  cursor: not-allowed;
  border-color: var(--border);
}

.icon-btn.text-btn {
  font-size: 14px;
  font-weight: bold;
}

.btn-text {
  color: var(--fg);
  font-size: 14px;
  line-height: 1;
}

.icon-btn:hover .btn-text {
  color: var(--btn-hover-fg, var(--fg));
}

.page-arrow .arrow-text {
  color: var(--accent);
  font-size: 20px;
  font-weight: bold;
  line-height: 1;
  text-shadow: 0 0 2px rgba(var(--accent-rgb, 122, 162, 247), 0.5);
}

.page-arrow:disabled .arrow-text {
  color: var(--fg-muted);
  text-shadow: none;
}

.notebook-title-wrap {
  min-width: 0;
}

.notebook-title-input {
  padding: 4px 10px;
  border: 1px solid var(--border);
  border-radius: 6px;
  background: var(--bg);
  color: var(--fg);
  font-size: 14px;
  font-weight: 600;
  width: 180px;
  transition: all 0.15s;
}

.notebook-title-input:hover {
  background: var(--bg-secondary);
  border-color: var(--fg-muted);
}

.notebook-title-input:focus {
  outline: none;
  border-color: var(--accent);
  background: var(--bg);
}

/* 页码指示器 */
.page-indicator {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 4px 8px;
  border-radius: 8px;
  background: var(--bg);
  border: 1px solid var(--border);
}

.page-arrow {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 32px;
  height: 32px;
  border: 1px solid var(--border);
  border-radius: 6px;
  background: var(--bg);
  color: var(--accent);
  cursor: pointer;
  transition: all 0.15s;
}

.page-arrow:hover:not(:disabled) {
  background: var(--btn-hover-bg, var(--border));
  color: var(--btn-hover-fg, var(--fg));
  border-color: var(--accent);
}

.page-arrow:disabled {
  opacity: 0.3;
  cursor: not-allowed;
  border-color: var(--border);
}

.page-num {
  font-weight: 700;
  font-size: 15px;
  color: var(--accent);
  min-width: 20px;
  text-align: center;
}

.page-sep {
  color: var(--fg-muted);
  font-size: 12px;
}

.page-total {
  color: var(--fg-muted);
  font-size: 13px;
  min-width: 16px;
}

.save-badge {
  font-size: 11px;
  padding: 2px 10px;
  border-radius: 10px;
  white-space: nowrap;
  animation: fadeIn 0.2s;
}

.save-badge.ok {
  color: var(--success);
  background: rgba(var(--success-rgb, 74, 222, 128), 0.1);
}

.save-badge.err {
  color: var(--danger);
  background: rgba(var(--danger-rgb), 0.1);
}

@keyframes fadeIn {
  from { opacity: 0; transform: translateY(-4px); }
  to { opacity: 1; transform: translateY(0); }
}

/* ─── 主体 ──────────────────────────────────────── */
.slides-body {
  display: flex;
  flex: 1;
  overflow: hidden;
  min-width: 0;
}

/* ─── 大纲侧边栏 ──────────────────────────────────────── */
.slides-outline {
  width: 220px;
  border-right: 1px solid var(--border);
  background: var(--bg-secondary);
  display: flex;
  flex-direction: column;
  flex-shrink: 0;
  overflow: hidden;
  transition: width 0.2s ease, opacity 0.2s ease;
}

.slides-outline.sidebar-hidden {
  width: 0;
  opacity: 0;
  pointer-events: none;
}

.outline-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 10px 14px;
  border-bottom: 1px solid var(--border);
  flex-shrink: 0;
}

.outline-label {
  font-size: 12px;
  font-weight: 600;
  color: var(--fg-muted);
  text-transform: uppercase;
  letter-spacing: 0.5px;
}

.outline-count {
  font-size: 10px;
  color: var(--fg-muted);
  background: var(--bg);
  padding: 1px 6px;
  border-radius: 8px;
}

.outline-list {
  flex: 1;
  overflow-y: auto;
  padding: 4px;
}

.outline-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 10px;
  cursor: pointer;
  font-size: 12px;
  color: var(--fg-muted);
  border-radius: 6px;
  transition: all 0.15s;
  margin-bottom: 1px;
}

.outline-item:hover {
  background: var(--bg);
  color: var(--fg);
}

.outline-item.active {
  background: var(--outline-active-bg);
  color: var(--accent);
}

.outline-item.active .outline-num {
  color: var(--accent);
  font-weight: 700;
}

.outline-num {
  font-size: 10px;
  color: var(--fg-muted);
  min-width: 18px;
  text-align: center;
  font-variant-numeric: tabular-nums;
}

.outline-title {
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  line-height: 1.4;
}

.outline-del {
  display: flex;
  align-items: center;
  justify-content: center;
  background: none;
  border: none;
  color: var(--fg-muted);
  cursor: pointer;
  padding: 2px;
  border-radius: 4px;
  opacity: 0;
  transition: all 0.15s;
  flex-shrink: 0;
}

.outline-item:hover .outline-del {
  opacity: 0.6;
}

.outline-del:hover {
  opacity: 1 !important;
  color: var(--danger);
  background: rgba(var(--danger-rgb), 0.1);
}

.outline-add {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  padding: 10px;
  border: none;
  border-top: 1px solid var(--border);
  background: transparent;
  color: var(--fg-muted);
  font-size: 12px;
  cursor: pointer;
  transition: all 0.15s;
  flex-shrink: 0;
}

.outline-add:hover {
  color: var(--accent);
  background: var(--bg);
}

/* ─── 编辑区 ──────────────────────────────────────── */
.slides-editor {
  flex: 1;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  min-width: 0;
}

.slide-title-bar {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 16px;
  border-bottom: 1px solid var(--border);
  background: var(--bg-secondary);
  flex-shrink: 0;
}

.slide-title-input {
  flex: 1;
  padding: 4px 8px;
  border: 1px solid transparent;
  border-radius: 4px;
  background: transparent;
  color: var(--fg);
  font-size: 14px;
  font-weight: 500;
  transition: all 0.15s;
}

.slide-title-input:hover {
  background: var(--bg);
}

.slide-title-input:focus {
  outline: none;
  border-color: var(--accent);
  background: var(--bg);
}

.slide-title-input::placeholder {
  color: var(--fg-muted);
  font-weight: 400;
}

.slide-time {
  font-size: 11px;
  color: var(--fg-muted);
  font-variant-numeric: tabular-nums;
  flex-shrink: 0;
}

.vditor-container {
  flex: 1;
  overflow: hidden;
  min-height: 0;
}

.vditor-container :deep(.vditor) {
  border: none !important;
  border-radius: 0 !important;
  height: 100% !important;
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

/* Vditor 内容元素强制跟随主题（防止 content-theme CSS 冲突） */
.vditor-container :deep(.vditor-reset) h1,
.vditor-container :deep(.vditor-reset) h2,
.vditor-container :deep(.vditor-reset) h3,
.vditor-container :deep(.vditor-reset) h4,
.vditor-container :deep(.vditor-reset) h5,
.vditor-container :deep(.vditor-reset) h6,
.vditor-container :deep(.vditor-reset) p,
.vditor-container :deep(.vditor-reset) span,
.vditor-container :deep(.vditor-reset) div,
.vditor-container :deep(.vditor-reset) li,
.vditor-container :deep(.vditor-reset) blockquote,
.vditor-container :deep(.vditor-reset) pre,
.vditor-container :deep(.vditor-reset) table,
.vditor-container :deep(.vditor-reset) td,
.vditor-container :deep(.vditor-reset) th,
.vditor-container :deep(.vditor-reset) strong,
.vditor-container :deep(.vditor-reset) em {
  color: var(--fg) !important;
}

.vditor-container :deep(.vditor-reset) a {
  color: var(--accent) !important;
}

.vditor-container :deep(.vditor-reset) code:not(pre code) {
  background: var(--bg-tertiary) !important;
  color: var(--accent) !important;
}

.vditor-container :deep(.vditor-reset) pre {
  background: var(--bg-tertiary) !important;
  border-color: var(--border) !important;
}

.vditor-container :deep(.vditor-reset) blockquote {
  border-left-color: var(--accent) !important;
  background: var(--bg-secondary) !important;
  color: var(--fg) !important;
}

.vditor-container :deep(.vditor-reset) table {
  border-color: var(--border) !important;
}

.vditor-container :deep(.vditor-reset) table td,
.vditor-container :deep(.vditor-reset) table th {
  border-color: var(--border) !important;
}

.vditor-container :deep(.vditor-reset) hr {
  border-color: var(--border) !important;
}

.vditor-container :deep(.vditor-ir),
.vditor-container :deep(.vditor-sv),
.vditor-container :deep(.vditor-wysiwyg) {
  min-height: calc(100vh - 160px) !important;
}

/* textarea 降级编辑器 */
.fallback-textarea {
  flex: 1;
  width: 100%;
  padding: 16px;
  background: var(--bg);
  color: var(--fg);
  border: none;
  font-size: 15px;
  font-family: 'Consolas', 'Monaco', monospace;
  line-height: 1.6;
  resize: none;
  outline: none;
}

.fallback-textarea::placeholder {
  color: var(--fg-muted);
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
  padding: 4px 10px;
  border: 1px solid var(--border);
  border-radius: 4px;
  background: var(--bg);
  color: var(--fg);
  font-size: 13px;
  font-weight: bold;
  cursor: pointer;
  transition: all 0.15s;
}

.md-toolbar button:hover {
  background: var(--accent);
  color: var(--bg);
  border-color: var(--accent);
}

/* ─── 响应式 ──────────────────────────────────────── */

/* ─── 冲突解决对话框 ─── */
.conflict-overlay {
  position: fixed;
  inset: 0;
  background: rgba(0,0,0,0.5);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 100;
}

.conflict-dialog {
  background: var(--bg-secondary);
  border: 1px solid var(--border);
  border-radius: var(--radius-lg, 12px);
  padding: 24px;
  max-width: 360px;
  width: 90%;
  box-shadow: var(--shadow);
}

.conflict-dialog h3 {
  margin: 0 0 12px;
  font-size: 16px;
  color: var(--fg);
}

.conflict-dialog p {
  margin: 0 0 16px;
  font-size: 13px;
  color: var(--fg-muted);
  line-height: 1.5;
}

.conflict-info {
  display: flex;
  gap: 12px;
  margin-bottom: 20px;
}

.conflict-item {
  flex: 1;
  padding: 10px;
  border-radius: 8px;
  background: var(--bg);
  border: 1px solid var(--border);
  text-align: center;
}

.conflict-label {
  display: block;
  font-size: 12px;
  font-weight: 600;
  color: var(--fg);
  margin-bottom: 4px;
}

.conflict-time {
  font-size: 11px;
  color: var(--fg-muted);
}

.conflict-actions {
  display: flex;
  gap: 10px;
}

.conflict-btn {
  flex: 1;
  padding: 10px;
  border-radius: 8px;
  border: 1px solid var(--border);
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.15s;
}

.local-btn {
  background: var(--accent);
  color: #ffffff;
  border-color: var(--accent);
}

.local-btn:hover {
  opacity: 0.9;
}

.server-btn {
  background: var(--bg);
  color: var(--fg);
}

.server-btn:hover {
  background: var(--bg-tertiary);
}
@media (max-width: 768px) {
  .slides-outline {
    position: absolute;
    left: 0;
    top: 44px;
    bottom: 0;
    z-index: 20;
    box-shadow: 4px 0 12px rgba(0,0,0,0.15);
  }

  .notebook-title-input {
    width: 120px;
  }

  .header-right .icon-btn:nth-child(n+5) {
    display: none;
  }

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

/* ─── 笔记选择器 ──────────────────────────────────────── */
.nb-selector {
  position: relative;
}

.nb-dropdown {
  position: absolute;
  top: 100%;
  left: 0;
  margin-top: 4px;
  min-width: 220px;
  max-width: calc(100vw - 24px);
  max-height: min(350px, calc(100vh - 80px));
  overflow-y: auto;
  background: var(--bg-secondary);
  border: 1px solid var(--border);
  border-radius: 8px;
  box-shadow: 0 8px 24px rgba(0,0,0,0.3);
  z-index: 50;
  padding: 4px;
}
@media (max-width: 600px) {
  .nb-dropdown {
    position: fixed;
    top: 52px;
    left: 8px;
    right: 8px;
    width: auto;
    max-width: none;
    max-height: calc(100vh - 80px);
  }
  .nb-dropdown-item .nb-dropdown-name {
    flex: 0 1 auto;
    width: calc(100% - 7ch);
  }
}

.nb-dropdown-breadcrumb {
  display: flex;
  align-items: center;
  gap: 2px;
  padding: 6px 8px;
  font-size: 11px;
  color: var(--fg-muted);
  border-bottom: 1px solid var(--border);
  margin-bottom: 4px;
  flex-wrap: wrap;
}
.nb-crumb {
  cursor: pointer;
  color: var(--accent);
}
.nb-crumb:hover { text-decoration: underline; }
.nb-crumb-sep { opacity: 0.5; }
.nb-dropdown-folder {
  font-weight: 500;
  color: var(--fg) !important;
}
.nb-dropdown-search {
  display: flex;
  align-items: center;
  gap: 4px;
  padding: 4px 6px;
  border-bottom: 1px solid var(--border);
  margin-bottom: 4px;
}
.nb-search-input {
  flex: 1;
  padding: 4px 8px;
  border: 1px solid var(--border);
  border-radius: 6px;
  background: var(--bg);
  color: var(--fg);
  font-size: 11px;
  outline: none;
  box-sizing: border-box;
}
.nb-search-clear {
  background: none;
  border: none;
  color: var(--fg-muted);
  cursor: pointer;
  font-size: 12px;
  padding: 2px 4px;
}
.nb-search-path {
  font-size: 9px;
  opacity: 0.5;
}

.nb-dropdown-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 10px;
  border-radius: 6px;
  cursor: pointer;
  font-size: 12px;
  color: var(--fg-muted);
  transition: all 0.1s;
}

.nb-dropdown-item:hover {
  background: var(--bg);
  color: var(--fg);
}

.nb-dropdown-name {
  flex: 1;
  min-width: 0;
  word-break: break-all;
}

.nb-dropdown-del {
  background: none;
  border: none;
  color: var(--fg-muted);
  font-size: 10px;
  cursor: pointer;
  padding: 2px 4px;
  border-radius: 3px;
  opacity: 0;
  transition: all 0.15s;
}

.nb-dropdown-item:hover .nb-dropdown-del {
  opacity: 0.6;
}

.nb-dropdown-del:hover {
  opacity: 1 !important;
  color: var(--danger);
  background: rgba(var(--danger-rgb), 0.1);
}

.nb-dropdown-import,
.nb-dropdown-export {
  background: none;
  border: none;
  color: var(--accent);
  font-size: 10px;
  cursor: pointer;
  padding: 2px 4px;
  border-radius: 3px;
  opacity: 0;
  transition: all 0.15s;
  margin-right: 2px;
}

.nb-dropdown-item:hover .nb-dropdown-import,
.nb-dropdown-item:hover .nb-dropdown-export {
  opacity: 0.7;
}

.nb-dropdown-import:hover,
.nb-dropdown-export:hover {
  opacity: 1 !important;
  background: rgba(59, 130, 246, 0.12);
}

.nb-dropdown-new {
  color: var(--accent);
  border-top: 1px solid var(--border);
  margin-top: 4px;
  padding-top: 8px;
  font-weight: 500;
}

/* ─── 源切换 ──────────────────────────────────────── */
.source-toggle {
  display: inline-flex;
  border: 1px solid var(--border);
  border-radius: 6px;
  overflow: hidden;
  flex-shrink: 0;
}
.source-btn {
  background: transparent;
  border: none;
  color: var(--fg-muted);
  padding: 3px 10px;
  font-size: 11px;
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

/* 本地操作 */
.import-export-msg {
  font-size: 11px;
  color: var(--accent);
  margin-left: 4px;
  white-space: nowrap;
}
.local-stats {
  font-size: 10px;
  color: var(--fg-muted);
  margin-left: 4px;
  white-space: nowrap;
}
.nb-action-btn {
  font-size: 12px !important;
}
</style>

