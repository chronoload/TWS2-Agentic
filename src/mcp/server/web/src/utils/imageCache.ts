const MAX_ENTRIES = 100
const cache = new Map<string, string>()
const pending = new Map<string, Promise<string | null>>()
let totalEvicted = 0

function makeKey(url: string): string {
  return url.split('?')[0]
}

function evictLRU() {
  const oldest = cache.keys().next()
  if (!oldest.done && oldest.value) {
    cache.delete(oldest.value)
    totalEvicted++
  }
}

export async function preloadImageCached(url: string): Promise<string | null> {
  if (!url) return null
  const key = makeKey(url)

  const hit = cache.get(key)
  if (hit) {
    cache.delete(key)
    cache.set(key, hit)
    return hit
  }

  const p = pending.get(key)
  if (p) return p

  const promise = loadImage(url)
  pending.set(key, promise)
  const result = await promise
  pending.delete(key)

  if (result) {
    if (cache.size >= MAX_ENTRIES) evictLRU()
    cache.set(key, result)
  }
  return result
}

async function loadImage(url: string): Promise<string | null> {
  return new Promise((resolve) => {
    const img = new Image()
    img.crossOrigin = 'anonymous'
    img.onload = () => {
      const canvas = document.createElement('canvas')
      canvas.width = img.width
      canvas.height = img.height
      const ctx = canvas.getContext('2d')
      if (!ctx) { resolve(null); return }
      ctx.drawImage(img, 0, 0)
      resolve(canvas.toDataURL('image/jpeg', 0.7))
    }
    img.onerror = () => resolve(null)
    img.src = url
  })
}

export function getImageCacheStats() {
  return { size: cache.size, max: MAX_ENTRIES, evicted: totalEvicted }
}

export function clearImageCache() {
  cache.clear()
  pending.clear()
}
