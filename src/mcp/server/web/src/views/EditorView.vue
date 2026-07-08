<template>
  <div class="view editor-view-root">
    <div class="editor-header">
      <button class="btn-back" @click="goBack">← 返回</button>
      <span class="editor-path">{{ filePath }}</span>
      <span v-if="dirty" class="edit-modified">●</span>
      <div class="header-spacer"></div>
      <button class="btn-save" @click="saveFile" :disabled="saving || !dirty">
        {{ saving ? '保存中...' : '保存' }}
      </button>
    </div>
    <div v-if="loading" class="loading-editor">加载中...</div>
    <div v-else-if="error" class="error-editor">{{ error }}</div>
    <template v-else>
      <div v-if="!useTextarea" ref="vditorRef" class="vditor-container"></div>
      <textarea
        v-else
        ref="textareaRef"
        class="fallback-textarea"
        @input="dirty = true"
      ></textarea>
    </template>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, onUnmounted, nextTick } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { getFile, putFile } from '../api'
import { loadAutocompleteConfig, buildHintExtends } from '../autocomplete'

const route = useRoute()
const router = useRouter()

const filePath = ref('')
const loading = ref(true)
const error = ref('')
const saving = ref(false)
const dirty = ref(false)
const vditorRef = ref<HTMLDivElement | null>(null)
const textareaRef = ref<HTMLTextAreaElement | null>(null)
const useTextarea = ref(false)

// Vditor 加载策略：4层容灾
// 第1层：本地 npm 包（打包进应用）
// 第2层：自建服务器（BASE_URL/vditor）
// 第3层：公共 CDN（unpkg）
// 第4层：回退到 textarea
let VditorClass: any = null
let vditorLoadFailed = false
let vditorSource: 'local' | 'self' | 'cdn' | null = null
let vditorInstance: any = null
let originalContent = ''

const VDITOR_CDN = 'https://unpkg.com/vditor'
const SELF_HOSTED_CDN = import.meta.env.BASE_URL + 'vditor'

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

async function resolveVditorCdn(): Promise<string> {
  // Capacitor: '/vditor' 映射到应用资源根目录
  if (isCapacitor()) return '/vditor'
  if (vditorSource === 'cdn') return VDITOR_CDN
  if (vditorSource === 'self') return SELF_HOSTED_CDN
  return import.meta.env.BASE_URL + 'vditor'
}

onMounted(async () => {
  const path = (route.params.path as string[])?.join('/') || ''
  if (!path) {
    error.value = '未指定文件路径'
    loading.value = false
    return
  }
  filePath.value = path

  try {
    const res = await getFile(path)
    const apiData = res.data?.data ?? res.data
    const content = apiData?.content ?? ''
    originalContent = content

    await nextTick()

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
              dirty.value = vditorInstance.getValue() !== originalContent
            }
          },
          after: () => { vditorReady = true },
          toolbar: isTouch
            ? ['headings', 'bold', 'italic', 'strike', '|', 'quote', 'inline-code', '|', 'list', 'ordered-list', 'check', '|', 'undo', 'redo', '|', 'edit-mode', 'preview']
            : ['headings', 'bold', 'italic', 'strike', '|', 'quote', 'inline-code', 'code', '|', 'list', 'ordered-list', 'check', '|', 'link', 'table', '|', 'undo', 'redo', '|', 'edit-mode', 'preview', 'fullscreen'],
        })
        await new Promise<void>((resolve) => setTimeout(resolve, 6000))
        if (!vditorReady) {
          console.warn('Vditor 子资源加载超时，回退纯文本编辑')
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
      useTextarea.value = true
      await nextTick()
      if (textareaRef.value) textareaRef.value.value = content
    }
  } catch {
    error.value = '无法读取文件'
  } finally {
    loading.value = false
  }
})

onUnmounted(() => {
  if (vditorInstance) {
    try { vditorInstance.destroy() } catch { /* ignore */ }
    vditorInstance = null
  }
})

async function saveFile() {
  if (!filePath.value) return
  saving.value = true
  try {
    let content = ''
    if (useTextarea.value && textareaRef.value) {
      content = textareaRef.value.value
    } else if (vditorInstance) {
      content = vditorInstance.getValue()
    }
    await putFile(filePath.value, content)
    originalContent = content
    dirty.value = false
  } catch {
    alert('保存失败')
  } finally {
    saving.value = false
  }
}

function goBack() {
  if (dirty.value) {
    const action = confirm('文件已修改但未保存，是否保存？\n\n确定 = 保存并关闭\n取消 = 不保存直接关闭')
    if (action) {
      saveFile()
    }
  }
  if (vditorInstance) {
    try { vditorInstance.destroy() } catch { /* ignore */ }
    vditorInstance = null
  }
  if (window.history.length > 1) {
    router.back()
  } else {
    router.push('/files')
  }
}
</script>

<style scoped>
.editor-view-root {
  display: flex;
  flex-direction: column;
  height: 100%;
  overflow: hidden;
}

.editor-header {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 12px;
  background: var(--bg-secondary);
  border-bottom: 1px solid var(--border);
  flex-shrink: 0;
}

.editor-path {
  font-size: 12px;
  color: var(--fg-muted);
  font-family: monospace;
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.header-spacer {
  flex: 1;
}

.edit-modified {
  color: var(--accent);
  font-size: 16px;
}

.btn-back {
  background: none;
  border: 1px solid var(--border);
  color: var(--fg);
  font-size: 12px;
  padding: 4px 10px;
  border-radius: 6px;
  cursor: pointer;
  white-space: nowrap;
}

.btn-back:hover {
  background: var(--bg-tertiary);
}

.btn-save {
  padding: 6px 16px;
  background: var(--accent);
  color: var(--bg);
  border: none;
  border-radius: 6px;
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
  white-space: nowrap;
}

.btn-save:disabled {
  opacity: 0.5;
}

.vditor-container {
  flex: 1;
  min-height: 0;
}

.fallback-textarea {
  flex: 1;
  min-height: 0;
  width: 100%;
  padding: 12px;
  background: var(--bg);
  color: var(--fg);
  border: none;
  font-family: monospace;
  font-size: 13px;
  line-height: 1.6;
  resize: none;
  outline: none;
}

.loading-editor,
.error-editor {
  display: flex;
  align-items: center;
  justify-content: center;
  flex: 1;
  color: var(--fg-muted);
  font-size: 14px;
}
</style>
