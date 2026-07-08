// 对标 Android ErrorInfo + UserAction + ErrorUtil
// 见 ptm.md: ErrorInfo.kt, UserAction.java, ErrorUtil.kt

export const UserAction = {
  USER_REPORT: 'user report',
  UI_ERROR: 'ui error',
  SUBSCRIPTION_CHANGE: 'subscription change',
  SUBSCRIPTION_UPDATE: 'subscription update',
  SUBSCRIPTION_GET: 'get subscription',
  SUBSCRIPTION_IMPORT_EXPORT: 'subscription import or export',
  LOAD_IMAGE: 'load image',
  SOMETHING_ELSE: 'something else',
  SEARCHED: 'searched',
  GET_SUGGESTIONS: 'get suggestions',
  REQUESTED_STREAM: 'requested stream',
  REQUESTED_CHANNEL: 'requested channel',
  REQUESTED_PLAYLIST: 'requested playlist',
  REQUESTED_KIOSK: 'requested kiosk',
  REQUESTED_COMMENTS: 'requested comments',
  REQUESTED_FEED: 'requested feed',
  REQUESTED_BOOKMARK: 'bookmark',
  DELETE_FROM_HISTORY: 'delete from history',
  PLAY_STREAM: 'play stream',
  DOWNLOAD_OPEN_DIALOG: 'download open dialog',
  DOWNLOAD_POSTPROCESSING: 'download post-processing',
  DOWNLOAD_FAILED: 'download failed',
  NEW_STREAMS_NOTIFICATIONS: 'new streams notifications',
  PREFERENCES_MIGRATION: 'migration of preferences',
  SHARE_TO_NEWPIPE: 'share to newpipe',
  CHECK_FOR_NEW_APP_VERSION: 'check for new app version',
} as const

export type UserAction = (typeof UserAction)[keyof typeof UserAction]

interface ErrorInfoOptions {
  userAction: UserAction
  request?: string
  serviceName?: string
  context?: Record<string, unknown>
}

export class AppError extends Error {
  readonly userAction: UserAction
  readonly request: string
  readonly serviceName: string
  readonly context: Record<string, unknown>
  readonly timestamp: string
  readonly originalError?: unknown

  constructor(message: string, options: ErrorInfoOptions, originalError?: unknown) {
    super(message)
    this.name = 'AppError'
    this.userAction = options.userAction
    this.request = options.request || ''
    this.serviceName = options.serviceName || 'none'
    this.context = options.context || {}
    this.timestamp = new Date().toISOString()
    this.originalError = originalError
  }

  toJSON(): Record<string, unknown> {
    return {
      name: this.name,
      message: this.message,
      userAction: this.userAction,
      request: this.request,
      serviceName: this.serviceName,
      context: this.context,
      timestamp: this.timestamp,
      stack: this.stack,
    }
  }
}

// Android getMessageStringId() 的亲缘逻辑 —— 根据异常类型推断用户可读消息
export function getErrorMessage(throwable: unknown, userAction: UserAction): string {
  if (throwable instanceof AppError) return throwable.message

  const msg = (throwable as any)?.message || String(throwable || '')

  if (msg.includes('429') || msg.toLowerCase().includes('reCaptcha'.toLowerCase()) || msg.toLowerCase().includes('captcha')) {
    return '请求被拦截，可能需要验证 reCaptcha'
  }
  if (msg.toLowerCase().includes('network') || msg.toLowerCase().includes('econnrefused') || msg.toLowerCase().includes('timeout') || msg.toLowerCase().includes('dns')) {
    return '网络错误，请检查网络连接'
  }
  if (msg.toLowerCase().includes('content not available') || msg.includes('404')) {
    return '内容不可用或已被删除'
  }
  if (msg.toLowerCase().includes('account terminated')) {
    return '账号已被封禁'
  }
  if (msg.toLowerCase().includes('need login') || msg.toLowerCase().includes('login')) {
    return '需要登录才能访问此内容'
  }
  if (msg.toLowerCase().includes('age restricted') || msg.toLowerCase().includes('age')) {
    return '年龄受限内容'
  }
  if (msg.toLowerCase().includes('geo') || msg.toLowerCase().includes('geographic')) {
    return '此内容在您所在地区不可用'
  }
  if (msg.toLowerCase().includes('paid') || msg.toLowerCase().includes('premium')) {
    return '此内容需要付费'
  }
  if (msg.toLowerCase().includes('private')) {
    return '此内容为私密内容'
  }
  if (msg.toLowerCase().includes('live not start') || msg.toLowerCase().includes('live')) {
    return '直播尚未开始'
  }
  if (msg.toLowerCase().includes('not supported') || msg.toLowerCase().includes('unsupported')) {
    return '内容格式不受支持'
  }

  switch (userAction) {
    case UserAction.REQUESTED_STREAM:
      return '无法加载视频信息'
    case UserAction.REQUESTED_CHANNEL:
      return '无法加载频道信息'
    case UserAction.REQUESTED_PLAYLIST:
      return '无法加载播放列表'
    case UserAction.REQUESTED_COMMENTS:
      return '无法加载评论'
    case UserAction.REQUESTED_FEED:
      return '无法加载订阅源'
    case UserAction.SEARCHED:
      return '搜索失败'
    case UserAction.SUBSCRIPTION_CHANGE:
      return '订阅操作失败'
    case UserAction.SUBSCRIPTION_UPDATE:
      return '订阅更新失败'
    case UserAction.LOAD_IMAGE:
      return '无法加载图片'
    case UserAction.DOWNLOAD_OPEN_DIALOG:
      return '无法打开下载菜单'
    case UserAction.PLAY_STREAM:
      return '播放失败'
    case UserAction.DOWNLOAD_FAILED:
      return '下载失败'
    default:
      return msg || '发生未知错误'
  }
}

// ── 诊断 Toast（不依赖 nav/panel，Android WebView 可靠） ──
export function debugToast(_message: string, _duration: number = 3000) {
  // no-op — disabled per user request
}

// ── 重试助手 ──
export interface RetryOptions {
  maxRetries?: number
  baseDelay?: number
  onRetry?: (attempt: number, error: unknown) => void
}

export async function withRetry<T>(
  fn: () => Promise<T>,
  options: RetryOptions = {},
): Promise<T> {
  const maxRetries = options.maxRetries ?? 3
  const baseDelay = options.baseDelay ?? 1000
  let lastErr: unknown
  for (let i = 0; i <= maxRetries; i++) {
    try {
      return await fn()
    } catch (err) {
      lastErr = err
      if (i < maxRetries) {
        options.onRetry?.(i + 1, err)
        await new Promise(r => setTimeout(r, baseDelay * Math.pow(2, i)))
      }
    }
  }
  throw lastErr
}

// ── 三阶错误报告（对标 ErrorUtil.kt） ──
export type ErrorLevel = 'snackbar' | 'notification' | 'critical'

// 轻量级 snackbar：用于 UI 可恢复场景
export function showErrorSnackbar(
  message: string,
  options?: { action?: string; onAction?: () => void; duration?: number }
) {
  const div = document.createElement('div')
  div.className = 'error-snackbar'
  div.textContent = message

  if (options?.action) {
    const btn = document.createElement('button')
    btn.className = 'error-snackbar-action'
    btn.textContent = options.action
    btn.addEventListener('click', () => {
      dismissSnackbar(div)
      options.onAction?.()
    })
    div.appendChild(btn)
  }

  const closeBtn = document.createElement('button')
  closeBtn.className = 'error-snackbar-close'
  closeBtn.textContent = '✕'
  closeBtn.addEventListener('click', () => dismissSnackbar(div))
  div.appendChild(closeBtn)

  document.body.appendChild(div)
  requestAnimationFrame(() => div.classList.add('visible'))

  const duration = options?.duration ?? 5000
  if (duration > 0) {
    setTimeout(() => dismissSnackbar(div), duration)
  }
}

function dismissSnackbar(el: HTMLElement) {
  el.classList.remove('visible')
  el.addEventListener('transitionend', () => el.remove(), { once: true })
  setTimeout(() => el.remove(), 300)
}

// 中等：通知式（后台场景）
export function showErrorNotification(title: string, message: string) {
  const div = document.createElement('div')
  div.className = 'error-notification'
  div.innerHTML = `<strong>${title}</strong><p>${message}</p>`
  document.body.appendChild(div)
  requestAnimationFrame(() => div.classList.add('visible'))
  setTimeout(() => {
    div.classList.remove('visible')
    div.addEventListener('transitionend', () => div.remove(), { once: true })
  }, 6000)
}

// 严重：错误报告页面（对标 ErrorActivity）
export function showErrorDialog(error: AppError) {
  const overlay = document.createElement('div')
  overlay.className = 'error-dialog-overlay'
  overlay.innerHTML = `
    <div class="error-dialog">
      <h3>发生错误</h3>
      <p class="error-msg">${escapeHtml(error.message)}</p>
      <div class="error-meta">
        <span>操作: ${error.userAction}</span>
        <span>请求: ${escapeHtml(error.request)}</span>
        <span>服务: ${error.serviceName}</span>
        <span>时间: ${error.timestamp}</span>
      </div>
      <pre class="error-stack">${escapeHtml(error.stack || '')}</pre>
      <div class="error-dialog-actions">
        <button class="err-btn err-copy" data-copy>复制报告</button>
        <button class="err-btn err-github" data-github>报告到 GitHub</button>
        <button class="err-btn err-close" data-close>关闭</button>
      </div>
    </div>
  `
  document.body.appendChild(overlay)

  overlay.querySelector('[data-close]')?.addEventListener('click', () => {
    overlay.remove()
  })

  overlay.querySelector('[data-copy]')?.addEventListener('click', () => {
    const report = buildMarkdownReport(error)
    navigator.clipboard.writeText(report).catch(() => {})
    const btn = overlay.querySelector('[data-copy]')
    if (btn) btn.textContent = '已复制!'
  })

  overlay.querySelector('[data-github]')?.addEventListener('click', () => {
    const report = buildMarkdownReport(error)
    const githubUrl = 'https://github.com/InfinityLoop1308/PipePipe/issues/new?body=' + encodeURIComponent(report)
    window.open(githubUrl, '_blank')
  })

  overlay.addEventListener('click', (e) => {
    if (e.target === overlay) overlay.remove()
  })
}

function escapeHtml(s: string): string {
  return s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;')
}

function buildMarkdownReport(error: AppError): string {
  const lines: string[] = []
  lines.push('## 错误报告')
  lines.push('')
  lines.push(`- **时间**: ${error.timestamp}`)
  lines.push(`- **操作**: ${error.userAction}`)
  lines.push(`- **请求**: ${error.request}`)
  lines.push(`- **服务**: ${error.serviceName}`)
  lines.push(`- **消息**: ${error.message}`)
  lines.push('')
  lines.push('### 堆栈')
  lines.push('```')
  lines.push(error.stack || '无堆栈信息')
  lines.push('```')
  return lines.join('\n')
}

// ── 全局样式注入 ──
let stylesInjected = false
export function injectErrorStyles() {
  if (stylesInjected) return
  stylesInjected = true
  const css = `
.error-snackbar {
  position: fixed; bottom: 24px; left: 50%; transform: translateX(-50%) translateY(100px);
  background: #e74c3c; color: #fff; padding: 12px 20px; border-radius: 10px;
  font-size: 14px; z-index: 10000; display: flex; align-items: center; gap: 12px;
  box-shadow: 0 4px 16px rgba(0,0,0,0.3); opacity: 0; transition: all 0.3s ease;
  max-width: 90vw;
}
.error-snackbar.visible { opacity: 1; transform: translateX(-50%) translateY(0); }
.error-snackbar-action {
  background: rgba(255,255,255,0.2); border: 1px solid rgba(255,255,255,0.4);
  color: #fff; padding: 4px 12px; border-radius: 6px; cursor: pointer; font-size: 13px; font-weight: 600;
}
.error-snackbar-action:hover { background: rgba(255,255,255,0.3); }
.error-snackbar-close {
  background: none; border: none; color: rgba(255,255,255,0.7); cursor: pointer; font-size: 16px; padding: 0 4px;
}
.error-notification {
  position: fixed; top: 16px; right: 16px; background: var(--bg, #fff); color: var(--fg, #333);
  border: 1px solid var(--border, #ddd); border-left: 4px solid #e74c3c; border-radius: 8px;
  padding: 12px 16px; font-size: 13px; z-index: 10000; max-width: 360px;
  box-shadow: 0 4px 16px rgba(0,0,0,0.15); opacity: 0; transform: translateX(100%); transition: all 0.3s ease;
}
.error-notification.visible { opacity: 1; transform: translateX(0); }
.error-notification strong { display: block; margin-bottom: 4px; }
.error-notification p { margin: 0; color: var(--fg-muted, #666); }
.error-dialog-overlay {
  position: fixed; inset: 0; z-index: 11000; display: flex; align-items: center; justify-content: center;
  background: rgba(0,0,0,0.5);
}
.error-dialog {
  background: var(--bg, #fff); color: var(--fg, #333); border: 1px solid var(--border, #ddd);
  border-radius: 12px; width: min(560px, 90vw); max-height: 80vh; display: flex; flex-direction: column;
  padding: 24px; box-shadow: 0 8px 32px rgba(0,0,0,0.3);
}
.error-dialog h3 { margin: 0 0 12px; font-size: 18px; color: #e74c3c; }
.error-msg { font-size: 14px; color: var(--fg-muted, #666); margin: 0 0 12px; }
.error-meta { display: flex; flex-direction: column; gap: 4px; font-size: 12px; color: var(--fg-muted, #888); margin-bottom: 12px; }
.error-stack {
  flex: 1; overflow: auto; background: #1e1e1e; color: #ddd; font-size: 11px; padding: 12px;
  border-radius: 6px; white-space: pre-wrap; word-break: break-all; max-height: 300px;
  margin: 0 0 16px;
}
.error-dialog-actions { display: flex; gap: 8px; justify-content: flex-end; }
.err-btn {
  padding: 8px 16px; border-radius: 8px; font-size: 13px; cursor: pointer; font-weight: 600;
  border: 1px solid var(--border, #ddd); transition: all 0.15s;
}
.err-copy { background: var(--bg-secondary, #f5f5f5); color: var(--fg); }
.err-copy:hover { background: var(--bg, #eee); }
.err-github { background: #24292e; color: #fff; border-color: #24292e; }
.err-github:hover { opacity: 0.9; }
.err-close { background: var(--bg-secondary, #f5f5f5); color: var(--fg); }
.err-close:hover { background: var(--bg, #eee); }
`
  const style = document.createElement('style')
  style.textContent = css
  document.head?.appendChild(style) || document.documentElement.appendChild(style)
}
