import Hls from 'hls.js'

export interface NativePlayerState {
  playerId: string
  initialized: boolean
  playing: boolean
  duration: number
}

export type PlayerEventCallback = (t: number) => void
export type PlayerErrorCallback = (err: PlayerError) => void

export interface PlayerError {
  type: 'native' | 'html5' | 'hls' | 'network'
  code?: number | string
  message: string
  url?: string
  detail?: string
}

interface PlayerHandle {
  load: (opts: {
    url: string
    title?: string
    subtitle?: string
    subtitleUrl?: string
    subtitleLanguage?: string
    rate?: number
    exitOnEnd?: boolean
    pipEnabled?: boolean
    bkmodeEnabled?: boolean
    headers?: Record<string, string>
    width?: number
    height?: number
  }) => Promise<void>
  seekTo: (seconds: number) => Promise<void>
  play: () => Promise<void>
  pause: () => Promise<void>
  setRate: (rate: number) => Promise<void>
  getCurrentTime: () => Promise<number>
  on: (ev: 'timeupdate' | 'exit', cb: PlayerEventCallback) => void
  onError?: (cb: PlayerErrorCallback) => void
  destroy: () => Promise<void>
  state: NativePlayerState
}

function createNativePlayerFallback(playerId: string, containerSelector?: string): PlayerHandle {
  let state: NativePlayerState = { playerId, initialized: false, playing: false, duration: 0 }
  let onTimeUpdate: PlayerEventCallback | null = null
  let onExit: PlayerEventCallback | null = null
  let onErrorCb: PlayerErrorCallback | null = null

  let videoEl: HTMLVideoElement | null = null
  let hls: Hls | null = null
  let animFrame: number | null = null

  function emitError(err: PlayerError) {
    onErrorCb?.(err)
  }

  function trackTime() {
    if (!videoEl) return
    onTimeUpdate?.(videoEl.currentTime)
    animFrame = requestAnimationFrame(trackTime)
  }

  async function load(options: {
    url: string
    title?: string
    subtitle?: string
    subtitleUrl?: string
    subtitleLanguage?: string
    rate?: number
    exitOnEnd?: boolean
    pipEnabled?: boolean
    bkmodeEnabled?: boolean
    headers?: Record<string, string>
    width?: number
    height?: number
  }) {
    videoEl = document.createElement('video')
    videoEl.id = playerId
    videoEl.controls = true
    videoEl.crossOrigin = 'anonymous'
    videoEl.setAttribute('playsinline', '')
    const container = containerSelector ? document.querySelector(containerSelector) as HTMLElement : null
    if (container) {
      videoEl.style.cssText = 'width:100%;height:100%;background:#000;object-fit:contain;display:block'
      container.appendChild(videoEl)
    } else {
      videoEl.style.cssText = 'position:fixed;top:0;left:0;width:100%;height:100%;background:#000;object-fit:contain;z-index:9999'
      document.body.appendChild(videoEl)
    }

    if (options.rate) videoEl.playbackRate = options.rate

    const src = options.url
    if (src.includes('.m3u8') && Hls.isSupported()) {
      hls = new Hls()
      hls.on(Hls.Events.ERROR, (_event, data) => {
        if (data.fatal) {
          emitError({
            type: 'hls',
            code: data.type,
            message: `HLS ${data.type === Hls.ErrorTypes.NETWORK_ERROR ? 'network' : 'media'} error: ${data.details}`,
            url: src,
            detail: JSON.stringify(data),
          })
        }
      })
      hls.loadSource(src)
      hls.attachMedia(videoEl)
      hls.on(Hls.Events.MANIFEST_PARSED, () => {
        videoEl?.play().catch((e) => emitError({ type: 'network', message: 'play() rejected: ' + e.message, url: src }))
      })
    } else {
      videoEl.src = src
    }

    videoEl.onloadedmetadata = () => {
      if (videoEl) state.duration = videoEl.duration
    }
    videoEl.onplay = () => { state.playing = true; animFrame = requestAnimationFrame(trackTime) }
    videoEl.onpause = () => { state.playing = false; if (animFrame) cancelAnimationFrame(animFrame) }
    videoEl.onended = () => {
      state.playing = false
      if (videoEl) onExit?.(videoEl.currentTime)
    }
    videoEl.onerror = () => {
      const me = videoEl?.error
      const code = me?.code
      const msgs: Record<number, string> = {
        1: '视频加载被中止',
        2: '网络错误 — 无法加载视频',
        3: '视频解码失败 — 格式可能不受支持',
        4: '视频格式不支持或没有视频源',
      }
      emitError({
        type: 'html5',
        code: code ?? -1,
        message: me ? (msgs[code ?? -1] || `未知视频错误 (code=${code})`) : '视频元素初始化错误，可能是 URL 无法访问或格式不兼容',
        url: src,
        detail: me ? `code=${me.code} message=${me.message}` : 'videoEl.error 为 null',
      })
    }

    state.initialized = true
    try { await videoEl.play() } catch (e: any) {
      emitError({ type: 'network', message: 'play() rejected: ' + e.message, url: src })
    }
  }

  async function seekTo(seconds: number) {
    if (videoEl) videoEl.currentTime = seconds
  }

  async function play() {
    try { await videoEl?.play(); state.playing = true } catch {}
  }

  async function pause() {
    videoEl?.pause(); state.playing = false
  }

  async function setRate(rate: number) {
    if (videoEl) videoEl.playbackRate = rate
  }

  async function getCurrentTime(): Promise<number> {
    return videoEl?.currentTime ?? 0
  }

  function on(ev: 'timeupdate' | 'exit', cb: PlayerEventCallback) {
    if (ev === 'timeupdate') onTimeUpdate = cb
    else if (ev === 'exit') onExit = cb
  }

  async function destroy() {
    if (animFrame) cancelAnimationFrame(animFrame)
    if (hls) { hls.destroy(); hls = null }
    if (videoEl) {
      onExit?.(videoEl.currentTime)
      videoEl.pause()
      videoEl.remove()
      videoEl = null
    }
    state.initialized = false
    state.playing = false
  }

  function onError(cb: PlayerErrorCallback) { onErrorCb = cb }
  return { load, seekTo, play, pause, setRate, getCurrentTime, on, onError, destroy, state }
}

export function createNativePlayer(playerId: string, containerSelector?: string): PlayerHandle {
  return createNativePlayerFallback(playerId, containerSelector)
}
