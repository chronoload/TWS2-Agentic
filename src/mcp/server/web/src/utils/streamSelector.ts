import type { VideoStreamInfo, AudioStreamInfo } from '../plugins/bridge'

export type QualityPreference = 'highest' | 'lowest' | number

export function parseHeight(quality: string): number {
  const m = quality.match(/(\d+)/)
  return m ? parseInt(m[1], 10) : 0
}

export function getDefaultVideoIndex(
  streams: VideoStreamInfo[],
  preferred: QualityPreference = 'highest',
): number {
  if (!streams.length) return -1
  const sorted = streams
    .map((s, i) => ({ ...s, _idx: i }))
    .sort((a, b) => {
      const ha = a.height || parseHeight(a.quality)
      const hb = b.height || parseHeight(b.quality)
      return hb - ha
    })
  if (preferred === 'lowest') return sorted[sorted.length - 1]._idx
  const prefH = typeof preferred === 'number' ? preferred : 99999
  let best = sorted[0]._idx
  for (const s of sorted) {
    const h = s.height || parseHeight(s.quality)
    if (h <= prefH) { best = s._idx; break }
  }
  return best
}

export function getDefaultAudioIndex(
  streams: AudioStreamInfo[],
  preferred: QualityPreference = 'highest',
): number {
  if (!streams.length) return -1
  const sorted = streams
    .map((s, i) => ({ ...s, _idx: i }))
    .sort((a, b) => b.bitrate - a.bitrate)
  if (preferred === 'lowest') return sorted[sorted.length - 1]._idx
  if (preferred === 'highest') return sorted[0]._idx
  const prefB = typeof preferred === 'number' ? preferred : 999999
  let best = sorted[0]._idx
  for (const s of sorted) {
    if (s.bitrate <= prefB) { best = s._idx; break }
  }
  return best
}

export function getStreamLabel(s: VideoStreamInfo | AudioStreamInfo): string {
  const main = (s as VideoStreamInfo).resolution || s.quality || (s.bitrate ? s.bitrate + 'kbps' : '?')
  const fmt = s.mimeType && s.codec ? `(${s.mimeType}, ${s.codec})` : s.mimeType ? `(${s.mimeType})` : ''
  const videoOnly = (s as VideoStreamInfo).isVideoOnly ? ' [无音频]' : ''
  const dash = s.deliveryMethod === 'DASH' ? ' [DASH]' : ''
  return `${main} ${fmt}${videoOnly}${dash}`.trim()
}
