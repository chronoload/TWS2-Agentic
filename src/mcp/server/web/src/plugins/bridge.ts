import { registerPlugin } from '@capacitor/core'
import { UserAction } from '../utils/error'
import { request } from './request'
import { isNativeApp } from '../api'
import { isBilibiliUrl, resolveBilibiliUrl, webGetChannelInfo, webGetChannelTabPage, webGetStreamInfo, webSearch, webSearchMore, webGetComments, webGetMoreComments, webGetMoreChannelItems } from '../extractor/BilibiliWebAdapter'

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

// Bilibili Web 适配器：浏览器直接调用 extractor，不经过后端
const BILIBILI_SID = 5
async function biliFallback<T>(urlOrSid: string | number | undefined, fn: () => Promise<T>): Promise<T | null> {
  const isBili = typeof urlOrSid === 'string'
    ? isBilibiliUrl(urlOrSid) || urlOrSid.includes('/videos')
    : urlOrSid === BILIBILI_SID
  if (isBili) {
    try { return await fn() } catch { return null }
  }
  return null
}

// 封装对标 Android: ErrorInfo + UserAction, DownloaderImpl.execute()
export const api = {
  async resolveUrl(url: string) {
    const bili = await biliFallback(url, async () => resolveBilibiliUrl(url))
    if (bili) return bili
    return nativeOrFallback(
      () => withRetry(() => PipePipe.resolveUrl({ url })),
      () => fallbackFetch<{ serviceId: number; serviceName: string; linkType: string }>('resolveUrl', { url }, UserAction.SOMETHING_ELSE)
    )
  },

  async getStreamInfo(url: string, serviceId: number, _forceLoad?: boolean) {
    const bili = await biliFallback(url, async () => webGetStreamInfo(url))
    if (bili) return bili
    return nativeOrFallback(
      () => withRetry(() => PipePipe.getStreamInfo({ url, serviceId })),
      () => fallbackFetch<any>('streamInfo', { url, serviceId }, UserAction.REQUESTED_STREAM)
    )
  },

  async getChannelInfo(url: string, serviceId?: number, forceLoad?: boolean) {
    const bili = await biliFallback(url, async () => webGetChannelInfo(url, serviceId))
    if (bili) return bili
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
    const bili = await biliFallback(options.tabUrl, async () => webGetChannelTabPage(options))
    if (bili) return bili
    return nativeOrFallback(
      () => withRetry(() => PipePipe.getChannelTabPage(options)),
      () => fallbackFetch<any>('channelTabPage', { tabUrl: options.tabUrl, serviceId: options.serviceId, nextPageUrl: options.nextPageUrl, forceLoad: options.forceLoad }, UserAction.REQUESTED_CHANNEL)
    )
  },

  getPlaylistInfo(url: string, serviceId?: number, forceLoad?: boolean) {
    return nativeOrFallback(
      () => withRetry(() => PipePipe.getPlaylistInfo({ url, serviceId, forceLoad })),
      () => fallbackFetch<any>('playlistInfo', { url, serviceId, forceLoad }, UserAction.REQUESTED_PLAYLIST)
    )
  },

  getMorePlaylistItems(url: string, serviceId?: number, nextPageUrl?: string, page?: Page) {
    return nativeOrFallback(
      () => withRetry(() => PipePipe.getMorePlaylistItems({ url, serviceId, nextPageUrl, page })),
      () => fallbackFetch<any>('morePlaylistItems', { url, serviceId, nextPageUrl }, UserAction.REQUESTED_PLAYLIST)
    )
  },

  getFeedInfo(url: string, serviceId?: number, forceLoad?: boolean) {
    return nativeOrFallback(
      () => withRetry(() => PipePipe.getFeedInfo({ url, serviceId, forceLoad })),
      () => fallbackFetch<any>('feedInfo', { url, serviceId, forceLoad }, UserAction.REQUESTED_FEED)
    )
  },

  async getMoreChannelItems(url: string, serviceId?: number, nextPageUrl?: string, page?: Page) {
    const bili = await biliFallback(url, async () => webGetMoreChannelItems(url, serviceId, nextPageUrl, page))
    if (bili) return bili
    return nativeOrFallback(
      () => withRetry(() => PipePipe.getMoreChannelItems({ url, serviceId, nextPageUrl, page })),
      () => fallbackFetch<any>('moreChannelItems', { url, serviceId, nextPageUrl }, UserAction.REQUESTED_CHANNEL)
    )
  },

  async search(query: string, serviceId: number, contentFilter?: string, sortFilter?: string, durationFilter?: string) {
    const bili = await biliFallback(serviceId, async () => webSearch(query, serviceId))
    if (bili) return bili
    return nativeOrFallback(
      () => withRetry(() => PipePipe.search({ query, serviceId, contentFilter, sortFilter, durationFilter })),
      () => fallbackFetch<any>('search', { query, serviceId, contentFilter, sortFilter, durationFilter }, UserAction.SEARCHED)
    )
  },

  async searchMore(query: string, serviceId: number, page?: Page, contentFilter?: string, sortFilter?: string, durationFilter?: string) {
    const bili = await biliFallback(serviceId, async () => webSearchMore(query, serviceId, page))
    if (bili) return bili
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

  clearCache() {
    if (isNativeApp()) return PipePipe.clearCache({})
    return Promise.resolve()
  },

  async getComments(url: string, serviceId: number, forceLoad?: boolean) {
    const bili = await biliFallback(url, async () => webGetComments(url, serviceId))
    if (bili) return bili
    return nativeOrFallback(
      () => withRetry(() => PipePipe.getComments({ url, serviceId, forceLoad })),
      () => fallbackFetch<any>('comments', { url, serviceId, forceLoad }, UserAction.REQUESTED_COMMENTS)
    )
  },

  async getMoreComments(url: string, serviceId: number, page?: Page) {
    const bili = await biliFallback(url, async () => webGetMoreComments(url, serviceId, page))
    if (bili) return bili
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

// ── 类型（最小必要集） ──

export interface Page {
  url: string
  id?: string
  ids?: string[]
  cookies?: Record<string, string>
  body?: string
}

export interface StreamInfoItem {
  name: string
  url: string
  thumbnailUrl: string
  type?: string
  uploaderName?: string
  uploaderUrl?: string
  uploaderAvatarUrl?: string
  viewCount?: number
  duration?: number
  textualUploadDate?: string
  shortDescription?: string
  uploaderVerified?: boolean
  streamType?: string
  description?: string
  subscriberCount?: number
  streamCount?: number
  verified?: boolean
  playlistType?: string
}

export interface SearchResult {
  query: string
  suggestion: string | null
  items: StreamInfoItem[]
  isCorrectedSearch?: boolean
  _hasNextPage?: boolean
  _nextPageUrl?: string
  _page?: Page
  _error?: string
  extractionErrors?: string[]
}

export interface StreamInfoResult {
  _error?: string
  _partialRecovery?: boolean
  _errorType?: string
  name: string
  url: string
  thumbnailUrl: string
  duration: number
  streamType: string
  ageLimit: number
  startPosition: number
  startAt: number
  description?: string
  descriptionType?: string
  uploaderName: string
  uploaderUrl: string
  uploaderAvatarUrl: string
  uploaderVerified: boolean
  uploaderSubscriberCount: number
  subChannelName: string
  subChannelUrl: string
  textualUploadDate: string
  viewCount: number
  likeCount: number
  dislikeCount: number
  category: string
  licence: string
  host: string
  tags?: string[]
  supportComments: boolean
  supportRelatedItems: boolean
  isRoundPlayStream: boolean
  shortFormContent: boolean
  membersOnly?: boolean
  hlsUrl: string
  videoStreams: VideoStreamInfo[]
  videoOnlyStreams: VideoStreamInfo[]
  audioStreams: AudioStreamInfo[]
  sortedVideoStreams: VideoStreamInfo[]
  sortedAudioStreams: AudioStreamInfo[]
  progressiveStreams: { url: string; resolution: string; quality: string; codec: string; formatId: number }[]
  recommendedVideoIndex?: number
  subtitles?: SubtitlesStreamInfo[]
  relatedItems?: any[]
  streamSegments?: any[]
  extractionErrors?: string[]
}

export interface VideoStreamInfo {
  id: string
  url: string
  isUrl: boolean
  resolution: string
  isVideoOnly: boolean
  codec: string
  bitrate: number
  quality: string
  fps: number
  width: number
  height: number
  deliveryMethod: string
  manifestUrl: string
  initStart: number
  initEnd: number
  indexStart: number
  indexEnd: number
  audioTrackId?: string
  audioTrackName?: string
  audioLocale?: string
  formatId: number
  formatName: string
  mimeType: string
}

export interface AudioStreamInfo {
  id: string
  url: string
  isUrl: boolean
  averageBitrate: number
  bitrate: number
  codec: string
  quality: string
  deliveryMethod: string
  manifestUrl: string
  initStart: number
  initEnd: number
  indexStart: number
  indexEnd: number
  mimeType: string
  audioTrackId?: string
  audioTrackName?: string
  audioLocale?: string
}

export interface SubtitlesStreamInfo {
  url: string
  languageCode: string
  displayName: string
  autoGenerated: boolean
  mimeType?: string
  suffix?: string
}

export interface ChannelInfoResult {
  _error?: string
  _partialRecovery?: boolean
  extractionErrors?: string[]
  serviceId?: number
  name: string
  url: string
  avatarUrl: string
  bannerUrl: string
  subscriberCount: number
  description: string
  verified: boolean
  parentChannelName?: string
  parentChannelUrl?: string
  parentChannelAvatarUrl?: string
  items: StreamInfoItem[]
  tabs?: ChannelTab[]
  _hasNextPage?: boolean
  _nextPageUrl?: string
  _page?: Page
}

export interface ChannelTab {
  name: string
  url: string
  tabId?: string
  _tabId?: string
  _originalUrl?: string
  _token?: string
}

// 兼容旧名
export type ChannelTabInfoResult = ChannelTab

export interface PlaylistInfoResult {
  _error?: string
  extractionErrors?: string[]
  serviceId?: number
  name: string
  url: string
  thumbnailUrl: string
  bannerUrl?: string
  uploaderName: string
  uploaderUrl?: string
  uploaderAvatarUrl?: string
  streamCount: number
  playlistType?: string
  subChannelName?: string
  subChannelUrl?: string
  subChannelAvatarUrl?: string
  items: StreamInfoItem[]
  _hasNextPage?: boolean
  _nextPageUrl?: string
  _page?: Page
}

export interface FeedInfoResult {
  _error?: string
  _partialRecovery?: boolean
  extractionErrors?: string[]
  serviceId?: number
  name?: string
  url?: string
  items: StreamInfoItem[]
  _hasNextPage?: boolean
  _nextPageUrl?: string
  _page?: Page
}

export interface CommentsResult {
  _error?: string
  extractionErrors?: string[]
  items: CommentsInfoItem[]
  _hasNextPage?: boolean
  _nextPageUrl?: string
  _page?: Page
}

export interface CommentsInfoItem {
  commentId: string
  commentText: string
  uploaderName: string
  uploaderAvatarUrl: string
  textualUploadDate: string
  likeCount: number
  replyCount: number
  heartedByUploader: boolean
  pinned: boolean
  streamPosition: number
  uploaderUrl: string
}

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
