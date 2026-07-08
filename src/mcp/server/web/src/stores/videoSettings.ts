import { defineStore } from 'pinia'
import { ref } from 'vue'

const STORAGE_KEY = 'ts2_video_settings'

export type ThemeMode = 'light' | 'dark' | 'black' | 'auto'

export interface VideoSettings {
  defaultQuality: string
  autoplay: boolean
  playbackRatePresets: number[]
  defaultPlaybackRate: number
  subtitleEnabled: boolean
  subtitleLanguage: string
  proxyEnabled: boolean
  proxyHost: string
  proxyPort: number
  themeMode: ThemeMode
}

const defaults: VideoSettings = {
  defaultQuality: 'highest',
  autoplay: true,
  playbackRatePresets: [0.5, 0.75, 1, 1.25, 1.5, 2],
  defaultPlaybackRate: 1,
  subtitleEnabled: false,
  subtitleLanguage: 'zh',
  proxyEnabled: true,
  proxyHost: '127.0.0.1',
  proxyPort: 0,
  themeMode: 'dark'
}

export const useVideoSettingsStore = defineStore('videoSettings', () => {
  const settings = ref<VideoSettings>({ ...defaults })

  function load() {
    try {
      const raw = localStorage.getItem(STORAGE_KEY)
      if (raw) settings.value = { ...defaults, ...JSON.parse(raw) }
    } catch { settings.value = { ...defaults } }
  }

  function save() {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(settings.value))
  }

  function update(partial: Partial<VideoSettings>) {
    settings.value = { ...settings.value, ...partial }
    save()
    applyTheme()
  }

  function reset() {
    settings.value = { ...defaults }
    save()
    applyTheme()
  }

  function applyTheme() {
    const root = document.documentElement
    const mode = settings.value.themeMode

    let effective: 'light' | 'dark'
    if (mode === 'auto') {
      effective = window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light'
    } else if (mode === 'black') {
      effective = 'dark'
    } else {
      effective = mode
    }

    root.setAttribute('data-theme', effective)
    root.classList.toggle('theme-black', mode === 'black')
    localStorage.setItem('ts2_theme', effective)
    window.dispatchEvent(new CustomEvent('ts2-theme-change', { detail: { theme: effective } }))
  }

  load()
  applyTheme()

  // Watch system theme changes when in auto mode
  if (settings.value.themeMode === 'auto') {
    const mq = window.matchMedia('(prefers-color-scheme: dark)')
    mq.addEventListener('change', applyTheme)
  }

  return { settings, load, save, update, reset, applyTheme }
})
