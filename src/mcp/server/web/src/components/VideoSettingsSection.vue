<template>
  <div class="video-settings">
    <div v-if="activeSection === 'appearance'" class="settings-panel">
      <h3 class="panel-title">外观</h3>
      <div class="setting-row">
        <label class="setting-label">主题</label>
        <select v-model="localTheme" class="setting-select" @change="onThemeChange">
          <option value="dark">深色</option>
          <option value="light">浅色</option>
          <option value="black">纯黑（AMOLED）</option>
          <option value="auto">跟随系统</option>
        </select>
      </div>
    </div>

    <div v-if="activeSection === 'playback'" class="settings-panel">
      <h3 class="panel-title">播放</h3>
      <div class="setting-row">
        <label class="setting-label">自动播放</label>
        <label class="toggle">
          <input type="checkbox" :checked="settings.autoplay" @change="store.update({ autoplay: !settings.autoplay })" />
          <span class="toggle-slider"></span>
        </label>
      </div>
      <div class="setting-row">
        <label class="setting-label">默认倍速</label>
        <select class="setting-select" :value="settings.defaultPlaybackRate" @change="onRateChange">
          <option v-for="r in settings.playbackRatePresets" :key="r" :value="r">{{ r }}x</option>
        </select>
      </div>
      <div class="setting-row">
        <label class="setting-label">默认字幕</label>
        <label class="toggle">
          <input type="checkbox" :checked="settings.subtitleEnabled" @change="store.update({ subtitleEnabled: !settings.subtitleEnabled })" />
          <span class="toggle-slider"></span>
        </label>
      </div>
      <div class="setting-row">
        <label class="setting-label">默认画质</label>
        <select class="setting-select" :value="settings.defaultQuality" @change="onQualityChange">
          <option value="highest">最高画质</option>
          <option value="lowest">最低画质</option>
        </select>
      </div>
    </div>

    <div v-if="activeSection === 'content'" class="settings-panel">
      <h3 class="panel-title">内容</h3>
      <div class="setting-row">
        <label class="setting-label">代理</label>
        <label class="toggle">
          <input type="checkbox" :checked="settings.proxyEnabled" @change="store.update({ proxyEnabled: !settings.proxyEnabled })" />
          <span class="toggle-slider"></span>
        </label>
      </div>
      <div class="setting-row">
        <label class="setting-label">代理主机</label>
        <input class="setting-input" :value="settings.proxyHost" @change="e => store.update({ proxyHost: (e.target as HTMLInputElement).value })" />
      </div>
    </div>

    <div v-if="activeSection === 'history'" class="settings-panel">
      <h3 class="panel-title">历史</h3>
      <div class="setting-row">
        <button class="danger-btn" @click="clearStreamStates">清除播放状态</button>
      </div>
      <div class="setting-row">
        <button class="danger-btn" @click="clearFeed">清除订阅动态缓存</button>
      </div>
      <div class="setting-row">
        <button class="danger-btn" @click="clearAll">清除全部视频数据</button>
      </div>
    </div>

    <div v-if="activeSection === 'about'" class="settings-panel">
      <h3 class="panel-title">关于</h3>
      <div class="about-line">
        <span>PipePipe 移植版</span>
        <span class="about-version">Phase E-G</span>
      </div>
      <div class="about-line">
        <span>基于 PipePipeExtractor</span>
      </div>
      <div class="about-line">
        <span>支持 BiliBili / YouTube / NicoNico</span>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, watch } from 'vue'
import { useVideoSettingsStore } from '../stores/videoSettings'
import { useStreamStateStore } from '../stores/streamState'
import { useFeedStore } from '../stores/feed'

defineProps<{ activeSection: string }>()

const store = useVideoSettingsStore()
const stateStore = useStreamStateStore()
const feedStore = useFeedStore()
const { settings } = store
const localTheme = ref(settings.themeMode)

watch(() => settings.themeMode, v => localTheme.value = v)

function onThemeChange() {
  store.update({ themeMode: localTheme.value as any })
}

function onRateChange(e: Event) {
  store.update({ defaultPlaybackRate: parseFloat((e.target as HTMLSelectElement).value) })
}

function onQualityChange(e: Event) {
  store.update({ defaultQuality: (e.target as HTMLSelectElement).value })
}

function clearStreamStates() {
  stateStore.clearStates()
}

function clearFeed() {
  feedStore.clear()
}

function clearAll() {
  stateStore.clearStates()
  feedStore.clear()
}
</script>

<style scoped>
.video-settings { padding: 0; }
.panel-title { font-size: 14px; font-weight: 600; color: var(--fg); margin: 0 0 16px; }
.setting-row { display: flex; align-items: center; justify-content: space-between; padding: 10px 0; border-bottom: 1px solid var(--border); gap: 12px; }
.setting-row:last-child { border-bottom: none; }
.setting-label { font-size: 13px; color: var(--fg); }
.setting-select { padding: 6px 10px; border: 1px solid var(--border); border-radius: 6px; background: var(--bg-secondary); color: var(--fg); font-size: 13px; }
.setting-input { padding: 6px 10px; border: 1px solid var(--border); border-radius: 6px; background: var(--bg-secondary); color: var(--fg); font-size: 13px; width: 150px; }
.toggle { position: relative; display: inline-block; width: 40px; height: 22px; flex-shrink: 0; }
.toggle input { opacity: 0; width: 0; height: 0; }
.toggle-slider { position: absolute; cursor: pointer; inset: 0; background: var(--border); border-radius: 22px; transition: 0.2s; }
.toggle-slider::before { content: ''; position: absolute; height: 16px; width: 16px; left: 3px; bottom: 3px; background: #fff; border-radius: 50%; transition: 0.2s; }
.toggle input:checked + .toggle-slider { background: var(--accent); }
.toggle input:checked + .toggle-slider::before { transform: translateX(18px); }
.danger-btn { padding: 8px 16px; background: rgba(231, 76, 60, 0.1); border: 1px solid #e74c3c; border-radius: 6px; color: #e74c3c; font-size: 13px; cursor: pointer; }
.danger-btn:hover { background: rgba(231, 76, 60, 0.2); }
.about-line { display: flex; justify-content: space-between; align-items: center; padding: 8px 0; font-size: 13px; color: var(--fg); border-bottom: 1px solid var(--border); }
.about-line:last-child { border-bottom: none; }
.about-version { font-size: 11px; color: var(--fg-muted); }
</style>
