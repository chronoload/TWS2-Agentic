import type { Router } from 'vue-router'

export function handleCardClick(item: any, router: Router): void {
  if (item.type === 'channel') {
    router.push({ name: 'channel', query: { url: item.url || item.uploaderUrl } })
  } else if (item.type === 'playlist') {
    router.push({ name: 'videos', query: { playlistUrl: item.url } })
  } else {
    router.push({ name: 'video-player', query: { url: item.url } })
  }
}
