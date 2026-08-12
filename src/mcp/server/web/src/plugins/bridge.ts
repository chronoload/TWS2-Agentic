import { registerPlugin } from '@capacitor/core'
import { UserAction } from '../utils/error'
import { request } from './request'
import { isNativeApp } from '../api'
import { isBilibiliUrl, resolveBilibiliUrl, webGetChannelInfo, webGetChannelTabPage, webGetStreamInfo, webSearch, webSearchMore, webGetComments, webGetMoreComments, webGetMoreChannelItems, webGetPlaylistInfo, webGetMorePlaylistItems } from '../extractor/BilibiliWebAdapter'
import { isYoutubeUrl, resolveYoutubeUrl, webYoutubeSearch, webYoutubeSearchMore, webYoutubeGetStreamInfo, webYoutubeGetChannelInfo, webYoutubeGetChannelTabPage, webYoutubeGetComments, webYoutubeGetMoreComments, webYoutubeGetFeed, webYoutubeGetPlaylistInfo, webYoutubeGetMorePlaylistItems } from '../extractor/youtube/YoutubeWebAdapter'

interface PipePipePlugin {
  echo(options: {}): Promise<{ ok: boolean; message?: string; initialized?: boolean; proxyPort?: number }>
  resolveUrl(options: { url: string }): Promise<{ serviceId: number; serviceName: string; linkType: string }>
  getStreamInfo(options: { url: string; serviceId?: number; forceLoad?: boolean }): Promise<any>
  getChannelInfo(options: { url: string; serviceId?: number; forceLoad?: boolean }): Promise<any>
  getChannelTabs(options: { url: string; serviceId?: number; forceLoad?: boolean }): Promise<any>
  getChannelTabPage(options: { tabUrl: string; tabId?: string; serviceId?: number; nextPageUrl?: string; forceLoad?: boolean; tabName?: string; page?: Page }): Promise<any>
  getPlaylistInfo(options: { url: string; serviceId?: number; forceLoad?: boolean }): Promise<any>
  getMorePlaylistItems(options: { url: string; serviceId?: number; nextPageUrl?: string; page?: Page }): Promise<any>
  getFeedInfo(options: { url: string; serviceId?: number; forceLoad?: boolean }): Promise<any>
  getMoreChannelItems(options: { url: string; serviceId?: number; nextPageUrl?: string; page?: Page }): Promise<any>
  search(options: { query: string; serviceId: number; contentFilter?: string; sortFilter?: string; durationFilter?: string }): Promise<any>
  searchMore(options: { query: string; serviceId: number; page?: Page; contentFilter?: string; sortFilter?: string; durationFilter?: string }): Promise<any>
  getProxyUrl(options: { url: string }): Promise<{ proxiedUrl?: string; proxyPort?: number }>
  preloadImage(options: { url: string }): Promise<{ localUrl?: string }>
  clearCache(options: {}): Promise<void>
  getComments(options: { url: string; serviceId: number; forceLoad?: boolean }): Promise<any>
  getMoreComments(options: { url: string; serviceId: number; page?: Page }): Promise<any>
  getSuggestions(options: { query: string; serviceId: number }): Promise<{ items: string[] }>
  getRelatedStreams(options: {}): Promise<{ items: any[] }>
}

const _PipePipe = registerPlugin<PipePipePlugin>('PipePipePlugin')

// 对标 PipePipeClient BaseStateFragment.handleError():
// Java 端 resolve({ _error, ... }) 时：若无 _partialRecovery 标志，自动转为 Promise.reject
// 若 _partialRecovery === true, 则视为部分恢复——保留原始响应, 不抛出, 由视图决定如何处置
const PipePipe = new Proxy(_PipePipe, {
  get(target, prop, receiver) {
    const orig = Reflect.get(target, prop, receiver)
    if (typeof orig === 'function') {
      return async (...args: any[]) => {
        const r = await orig(...args)
        if (r && typeof r === 'object' && '_error' in r && r._error) {
          if (r._partialRecovery === true) {
            return r as any
          }
          const err = new Error(r._error)
          ;(err as any).data = r
          throw err
        }
        return r
      }
    }
    return orig
  }
})

export default PipePipe

// ── 高级 API 封装（对标 Android UserAction + 重试） ──
// 对标 DownloaderImpl.execute() 的 maxRetries=2, delay=500ms
const MAX_RETRIES = 2
const RETRY_DELAY = 500
const sleep = (ms: number) => new Promise(r => setTimeout(r, ms))

function isRetryableError(err: unknown): boolean {
  const m = (err as any)?.message?.toLowerCase() || ''
  return m.includes('network') || m.includes('timeout') || m.includes('econnrefused') ||
    m.includes('dns') || m.includes('fetch failed') || m.includes('retry')
}

async function withRetry<T>(fn: () => Promise<T>): Promise<T> {
  let lastErr: unknown
  for (let i = 0; i <= MAX_RETRIES; i++) {
    try {
      return await fn()
    } catch (err) {
      lastErr = err
      if (isRetryableError(err) && i < MAX_RETRIES) {
        await sleep(RETRY_DELAY)
        continue
      }
      throw err
    }
  }
  throw lastErr
}

// 浏览器回退：通过后端代理 API 调用 extractor（当不在 Capacitor 原生环境时）
const EXTRACTOR_API_BASE = '/api/extractor'

async function fallbackFetch<T>(endpoint: string, params: Record<string, string | number | boolean | undefined>, userAction: UserAction): Promise<T> {
  const query = Object.entries(params)
    .filter(([_, v]) => v != null)
    .map(([k, v]) => `${encodeURIComponent(k)}=${encodeURIComponent(String(v))}`)
    .join('&')
  return request<T>(`${EXTRACTOR_API_BASE}/${endpoint}?${query}`, userAction)
}

// 尝试原生插件，失败时回退到浏览器 fetch
async function nativeOrFallback<T>(nativeFn: () => Promise<T>, fallbackFn: () => Promise<T>): Promise<T> {
  if (isNativeApp()) return nativeFn()
  try {
    return await nativeFn()
  } catch {
    return fallbackFn()
  }
}

// Web 适配器：浏览器直接调用 extractor，不经过后端
const BILIBILI_SID = 5
const YOUTUBE_SID = 0

function detectService(urlOrSid: string | number | undefined): 'bilibili' | 'youtube' | null {
  if (typeof urlOrSid === 'string') {
    if (isBilibiliUrl(urlOrSid) || urlOrSid.includes('/videos')) return 'bilibili'
    if (isYoutubeUrl(urlOrSid)) return 'youtube'
    return null
  }
  if (urlOrSid === BILIBILI_SID) return 'bilibili'
  if (urlOrSid === YOUTUBE_SID) return 'youtube'
  return null
}

async function webFallback<T>(urlOrSid: string | number | undefined, fn: (service: 'bilibili' | 'youtube') => Promise<T>): Promise<T | null> {
  const service = detectService(urlOrSid)
  if (!service) return null
  try { return await fn(service) } catch { return null }
}

// 封装对标 Android: ErrorInfo + UserAction, DownloaderImpl.execute()
export const api = {
  async resolveUrl(url: string) {
    const web = await webFallback(url, async (svc) => {
      if (svc === 'bilibili') return resolveBilibiliUrl(url)
      const yt = resolveYoutubeUrl(url)
      return yt || { serviceId: 0, serviceName: 'YouTube', linkType: 'stream' }
    })
    if (web) return web
    return nativeOrFallback(
      () => withRetry(() => PipePipe.resolveUrl({ url })),
      () => fallbackFetch<{ serviceId: number; serviceName: string; linkType: string }>('resolveUrl', { url }, UserAction.SOMETHING_ELSE)
    )
  },

  async getStreamInfo(url: string, serviceId: number, _forceLoad?: boolean) {
    const web = await webFallback(serviceId, async (svc) => {
      if (svc === 'bilibili') return webGetStreamInfo(url)
      return webYoutubeGetStreamInfo(url)
    })
    if (web) return web
    return nativeOrFallback(
      () => withRetry(() => PipePipe.getStreamInfo({ url, serviceId })),
      () => fallbackFetch<any>('streamInfo', { url, serviceId }, UserAction.REQUESTED_STREAM)
    )
  },

  async getChannelInfo(url: string, serviceId?: number, forceLoad?: boolean) {
    const web = await webFallback(serviceId, async (svc) => {
      if (svc === 'bilibili') return webGetChannelInfo(url, serviceId)
      return webYoutubeGetChannelInfo(url)
    })
    if (web) return web
    return nativeOrFallback(
      () => withRetry(() => PipePipe.getChannelInfo({ url, serviceId, forceLoad })),
      () => fallbackFetch<any>('channelInfo', { url, serviceId, forceLoad }, UserAction.REQUESTED_CHANNEL)
    )
  },

  getChannelTabs(url: string, serviceId?: number, forceLoad?: boolean) {
    return nativeOrFallback(
      () => withRetry(() => PipePipe.getChannelTabs({ url, serviceId, forceLoad })),
      () => fallbackFetch<any>('channelTabs', { url, serviceId, forceLoad }, UserAction.REQUESTED_CHANNEL)
    )
  },

  async getChannelTabPage(options: { tabUrl: string; tabId?: string; serviceId?: number; nextPageUrl?: string; forceLoad?: boolean; tabName?: string; page?: Page }) {
    const web = await webFallback(options.serviceId, async (svc) => {
      if (svc === 'bilibili') return webGetChannelTabPage(options)
      return webYoutubeGetChannelTabPage(options.tabUrl)
    })
    if (web) return web
    return nativeOrFallback(
      () => withRetry(() => PipePipe.getChannelTabPage(options)),
      () => fallbackFetch<any>('channelTabPage', { tabUrl: options.tabUrl, serviceId: options.serviceId, nextPageUrl: options.nextPageUrl, forceLoad: options.forceLoad }, UserAction.REQUESTED_CHANNEL)
    )
  },

  async getPlaylistInfo(url: string, serviceId?: number, _forceLoad?: boolean) {
    const web = await webFallback(serviceId, async (svc) => {
      if (svc === 'bilibili') return webGetPlaylistInfo(url)
      return webYoutubeGetPlaylistInfo(url)
    })
    if (web) return web
    return nativeOrFallback(
      () => withRetry(() => PipePipe.getPlaylistInfo({ url, serviceId })),
      () => fallbackFetch<any>('playlistInfo', { url, serviceId }, UserAction.REQUESTED_PLAYLIST)
    )
  },

  async getMorePlaylistItems(url: string, serviceId?: number, _nextPageUrl?: string, page?: Page) {
    const web = await webFallback(serviceId, async (svc) => {
      if (svc === 'bilibili') return webGetMorePlaylistItems(url, page)
      return webYoutubeGetMorePlaylistItems(url, page)
    })
    if (web) return web
    return nativeOrFallback(
      () => withRetry(() => PipePipe.getMorePlaylistItems({ url, serviceId, nextPageUrl: _nextPageUrl, page })),
      () => fallbackFetch<any>('morePlaylistItems', { url, serviceId, nextPageUrl: _nextPageUrl }, UserAction.REQUESTED_PLAYLIST)
    )
  },

  async getFeedInfo(url: string, serviceId?: number, forceLoad?: boolean) {
    const web = await webFallback(serviceId, async (svc) => {
      if (svc === 'youtube') return webYoutubeGetFeed()
      return null
    })
    if (web) return web
    return nativeOrFallback(
      () => withRetry(() => PipePipe.getFeedInfo({ url, serviceId, forceLoad })),
      () => fallbackFetch<any>('feedInfo', { url, serviceId, forceLoad }, UserAction.REQUESTED_FEED)
    )
  },

  async getMoreChannelItems(url: string, serviceId?: number, nextPageUrl?: string, page?: Page) {
    const web = await webFallback(serviceId, async (svc) => {
      if (svc === 'bilibili') return webGetMoreChannelItems(url, serviceId, nextPageUrl, page)
      return null
    })
    if (web) return web
    return nativeOrFallback(
      () => withRetry(() => PipePipe.getMoreChannelItems({ url, serviceId, nextPageUrl, page })),
      () => fallbackFetch<any>('moreChannelItems', { url, serviceId, nextPageUrl }, UserAction.REQUESTED_CHANNEL)
    )
  },

  async search(query: string, serviceId: number, contentFilter?: string, sortFilter?: string, durationFilter?: string) {
    const web = await webFallback(serviceId, async (svc) => {
      if (svc === 'bilibili') return webSearch(query, serviceId)
      return webYoutubeSearch(query)
    })
    if (web) return web
    return nativeOrFallback(
      () => withRetry(() => PipePipe.search({ query, serviceId, contentFilter, sortFilter, durationFilter })),
      () => fallbackFetch<any>('search', { query, serviceId, contentFilter, sortFilter, durationFilter }, UserAction.SEARCHED)
    )
  },

  async searchMore(query: string, serviceId: number, page?: Page, contentFilter?: string, sortFilter?: string, durationFilter?: string) {
    const web = await webFallback(serviceId, async (svc) => {
      if (svc === 'bilibili') return webSearchMore(query, serviceId, page)
      return webYoutubeSearchMore(query, page)
    })
    if (web) return web
    return nativeOrFallback(
      () => withRetry(() => PipePipe.searchMore({ query, serviceId, page, contentFilter, sortFilter, durationFilter })),
      () => fallbackFetch<any>('searchMore', { query, serviceId, contentFilter, sortFilter, durationFilter }, UserAction.SEARCHED)
    )
  },

  getProxyUrl(url: string) {
    return nativeOrFallback(
      () => withRetry(() => PipePipe.getProxyUrl({ url })),
      () => Promise.resolve({ proxiedUrl: url, proxyPort: -1 })
    )
  },

  preloadImage(url: string) {
    return nativeOrFallback(
      () => withRetry(() => PipePipe.preloadImage({ url })),
      () => Promise.resolve({ localUrl: url })
    )
  },

  async echo() {
    return PipePipe.echo({})
  },

  clearCache() {
    if (isNativeApp()) return PipePipe.clearCache({})
    return Promise.resolve()
  },

  async getComments(url: string, serviceId: number, forceLoad?: boolean) {
    const web = await webFallback(serviceId, async (svc) => {
      if (svc === 'bilibili') return webGetComments(url, serviceId)
      return webYoutubeGetComments(url)
    })
    if (web) return web
    return nativeOrFallback(
      () => withRetry(() => PipePipe.getComments({ url, serviceId, forceLoad })),
      () => fallbackFetch<any>('comments', { url, serviceId, forceLoad }, UserAction.REQUESTED_COMMENTS)
    )
  },

  async getMoreComments(url: string, serviceId: number, page?: Page) {
    const web = await webFallback(serviceId, async (svc) => {
      if (svc === 'bilibili') return webGetMoreComments(url, serviceId, page)
      return webYoutubeGetMoreComments(url, page)
    })
    if (web) return web
    return nativeOrFallback(
      () => withRetry(() => PipePipe.getMoreComments({ url, serviceId, page })),
      () => fallbackFetch<any>('moreComments', { url, serviceId }, UserAction.REQUESTED_COMMENTS)
    )
  },

  getSuggestions(query: string, serviceId: number) {
    return nativeOrFallback(
      () => withRetry(() => PipePipe.getSuggestions({ query, serviceId })),
      () => fallbackFetch<{ items: string[] }>('suggestions', { query, serviceId }, UserAction.GET_SUGGESTIONS)
    )
  },
}

// Types moved to src/types/extraction.ts
import type { Page } from '../types/extraction'

// ── 工具函数 ──

export async function getProxyUrl(url: string): Promise<string | null> {
  try {
    const r = await PipePipe.getProxyUrl({ url })
    return r.proxiedUrl || null
  } catch {
    return null
  }
}

export async function requestViaFetch(url: string, options?: { method?: string; headers?: Record<string, string>; body?: any }): Promise<Response> {
  return fetch(url, { method: options?.method ?? 'GET', headers: options?.headers, body: options?.body })
}

export function extractNextPage(result: { _page?: Page; _nextPageUrl?: string; _hasNextPage?: boolean }): Page | null {
  if (!result._hasNextPage) return null
  if (result._page && result._page.url) return result._page
  if (result._nextPageUrl) return { url: result._nextPageUrl }
  return null
}
