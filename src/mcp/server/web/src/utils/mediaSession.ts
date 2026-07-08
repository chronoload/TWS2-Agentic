const noop = () => {}

export interface MediaSessionHandlers {
  play?: () => void
  pause?: () => void
  seekforward?: () => void
  seekbackward?: () => void
  seekto?: (details: { seekTime: number; fastSeek?: boolean }) => void
  next?: () => void
  previous?: () => void
  stop?: () => void
}

export function setMediaSession(
  metadata: { title: string; artist: string; artwork: { src: string; sizes: string; type: string }[] },
  handlers: MediaSessionHandlers = {}
) {
  if (!('mediaSession' in navigator)) return
  const ms = navigator.mediaSession
  ms.metadata = new MediaMetadata(metadata)
  ms.setActionHandler('play', handlers.play ?? noop)
  ms.setActionHandler('pause', handlers.pause ?? noop)
  ms.setActionHandler('seekforward', handlers.seekforward ?? noop)
  ms.setActionHandler('seekbackward', handlers.seekbackward ?? noop)
  if (handlers.seekto) {
    ms.setActionHandler('seekto', handlers.seekto as any)
  }
  ms.setActionHandler('nexttrack', handlers.next ?? noop)
  ms.setActionHandler('previoustrack', handlers.previous ?? noop)
  ms.setActionHandler('stop', handlers.stop ?? noop)
}

export function updateMediaSessionPosition(
  position: number,
  duration: number,
  playbackRate: number = 1
) {
  if (!('mediaSession' in navigator)) return
  navigator.mediaSession.setPositionState({ position, duration, playbackRate })
}

export function clearMediaSession() {
  if (!('mediaSession' in navigator)) return
  const ms = navigator.mediaSession
  ms.metadata = null
  ms.setActionHandler('play', null)
  ms.setActionHandler('pause', null)
  ms.setActionHandler('seekforward', null)
  ms.setActionHandler('seekbackward', null)
  ms.setActionHandler('seekto', null)
  ms.setActionHandler('nexttrack', null)
  ms.setActionHandler('previoustrack', null)
  ms.setActionHandler('stop', null)
}
