// 对标 Android DownloaderImpl.java
// - 统一 User-Agent (Mozilla/5.0 ... Firefox/128.0)
// - Cookie 管理 (Youtube restricted mode, Recaptcha)
// - DNS/网络重试 (maxRetries=2, delay=500ms)
// - 429 → ReCaptchaException
// - 自定义超时
// - 统一错误包装为 AppError

import { AppError, UserAction, getErrorMessage } from '../utils/error'

const USER_AGENT = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:128.0) Gecko/20100101 Firefox/128.0'
const MAX_RETRIES = 2
const RETRY_DELAY_MS = 500

interface RequestOptions {
  method?: string
  headers?: Record<string, string>
  body?: BodyInit | null
  signal?: AbortSignal
  timeout?: number
  followRedirects?: boolean
}

// Cookie 存储（对标 DownloaderImpl.mCookies）
const cookieStore: Map<string, string> = new Map()

export function setCookie(key: string, value: string) {
  cookieStore.set(key, value)
}

export function getCookie(key: string): string | undefined {
  return cookieStore.get(key)
}

export function removeCookie(key: string) {
  cookieStore.delete(key)
}

// 获取特定 URL 的 cookies（对标 DownloaderImpl.getCookies()）
function getCookiesForUrl(url: string): string {
  const parts: string[] = []
  if (url.includes('youtube.com')) {
    const ytCookie = getCookie('youtube_restricted_mode_key')
    if (ytCookie) parts.push(ytCookie)
  }
  const recaptchaCookie = getCookie('recaptcha_cookies_key')
  if (recaptchaCookie) parts.push(recaptchaCookie)
  return parts.join('; ')
}

// 睡眠辅助
const sleep = (ms: number) => new Promise(resolve => setTimeout(resolve, ms))

/**
 * 统一网络请求（对标 DownloaderImpl.execute()）
 * - 自动添加 User-Agent
 * - 自动添加 Cookie
 * - DNS/网络失败时自动重试
 * - 429 抛 ReCaptcha 异常
 * - 超时控制
 */
export async function request<T = unknown>(
  url: string,
  userAction: UserAction,
  options: RequestOptions = {}
): Promise<T> {
  let lastError: Error | null = null

  for (let attempt = 0; attempt <= MAX_RETRIES; attempt++) {
    const controller = new AbortController()
    const timeout = options.timeout ?? 30_000
    const timeoutId = setTimeout(() => controller.abort(), timeout)

    try {
      const signal = options.signal
        ? anySignal([options.signal, controller.signal])
        : controller.signal

      const headers: Record<string, string> = {
        'User-Agent': USER_AGENT,
        ...options.headers,
      }

      const cookies = getCookiesForUrl(url)
      if (cookies && !headers['Cookie']) {
        headers['Cookie'] = cookies
      }

      const resp = await fetch(url, {
        method: options.method || 'GET',
        headers,
        body: options.body,
        signal,
        redirect: options.followRedirects !== false ? 'follow' : 'manual',
      })

      if (resp.status === 429) {
        throw new ReCaptchaError('reCaptcha Challenge requested', url)
      }

      if (!resp.ok) {
        const body = await resp.text().catch(() => '')
        throw new HttpError(resp.status, resp.statusText, body, url)
      }

      const text = await resp.text()
      clearTimeout(timeoutId)
      try {
        return JSON.parse(text) as T
      } catch {
        return text as unknown as T
      }
    } catch (err: unknown) {
      clearTimeout(timeoutId)
      lastError = err as Error

      const shouldRetry =
        isDNSError(err) ||
        isNetworkError(err) ||
        (err instanceof HttpError && err.status >= 500) ||
        isAbortError(err)

      if (shouldRetry && attempt < MAX_RETRIES) {
        console.warn(`[request] 重试 ${attempt + 1}/${MAX_RETRIES}: ${url}`)
        await sleep(RETRY_DELAY_MS)
        continue
      }

      const message = getErrorMessage(err, userAction)
      const appError = new AppError(message, {
        userAction,
        request: url,
      }, err)
      throw appError
    }
  }

  throw lastError || new AppError('请求失败：已达最大重试次数', { userAction, request: url })
}

// ── 辅助类型 ──

export class ReCaptchaError extends Error {
  readonly url: string
  constructor(message: string, url: string) {
    super(message)
    this.name = 'ReCaptchaError'
    this.url = url
  }
}

export class HttpError extends Error {
  readonly status: number
  readonly statusText: string
  readonly body: string
  readonly url: string
  constructor(status: number, statusText: string, body: string, url: string) {
    super(`HTTP ${status} ${statusText}`)
    this.name = 'HttpError'
    this.status = status
    this.statusText = statusText
    this.body = body
    this.url = url
  }
}

function isDNSError(err: unknown): boolean {
  const m = (err as any)?.message?.toLowerCase() || ''
  return m.includes('dns') || m.includes('enotfound') || m.includes('eai_again')
}

function isNetworkError(err: unknown): boolean {
  const m = (err as any)?.message?.toLowerCase() || ''
  return m.includes('econnrefused') || m.includes('enetunreach') ||
    m.includes('network') || m.includes('fetch failed') ||
    m.includes('name resolution')
}

function isAbortError(err: unknown): boolean {
  return (err instanceof DOMException && err.name === 'AbortError') ||
    (err as any)?.name === 'AbortError' ||
    (err as any)?.message?.includes('aborted')
}

// 合并多个 AbortSignal，自动清理已 abort 的 listener
function anySignal(signals: AbortSignal[]): AbortSignal {
  const controller = new AbortController()
  const listeners: Array<[AbortSignal, () => void]> = []
  for (const signal of signals) {
    if (signal.aborted) {
      controller.abort(signal.reason)
      return controller.signal
    }
    const handler = () => { controller.abort(signal.reason); cleanup() }
    signal.addEventListener('abort', handler, { once: true })
    listeners.push([signal, handler])
  }
  function cleanup() {
    for (const [sig, fn] of listeners) sig.removeEventListener('abort', fn)
  }
  if (controller.signal.aborted) cleanup()
  else controller.signal.addEventListener('abort', cleanup, { once: true })
  return controller.signal
}

/**
 * 创建带超时的 fetch，对标 OkHttpClient.newCall().execute()
 */
export async function fetchWithTimeout(url: string, timeoutMs = 30_000, options: RequestInit = {}): Promise<Response> {
  const controller = new AbortController()
  const id = setTimeout(() => controller.abort(), timeoutMs)
  try {
    const resp = await fetch(url, { ...options, signal: anySignal([controller.signal, ...(options.signal ? [options.signal] : [])]) })
    return resp
  } finally {
    clearTimeout(id)
  }
}

/**
 * 便捷方法：直接返回 JSON 解析结果（对标 DownloaderImpl.execute() + JSON response）
 */
export async function requestJSON<T = unknown>(
  url: string,
  userAction: UserAction,
  options: RequestOptions = {}
): Promise<T> {
  return request<T>(url, userAction, { ...options, headers: { ...options.headers, Accept: 'application/json' } })
}

/**
 * 便捷方法：直接返回纯文本
 */
export async function requestText(
  url: string,
  userAction: UserAction,
  options: RequestOptions = {}
): Promise<string> {
  return request<string>(url, userAction, options)
}

/**
 * 获取 Content-Length（对标 DownloaderImpl.getContentLength()）
 */
export async function getContentLength(url: string): Promise<number> {
  const resp = await fetchWithTimeout(url, 15_000, { method: 'HEAD' })
  if (!resp.ok) throw new HttpError(resp.status, resp.statusText, '', url)
  const len = resp.headers.get('Content-Length')
  if (!len) throw new Error('Invalid content length')
  return parseInt(len, 10)
}
