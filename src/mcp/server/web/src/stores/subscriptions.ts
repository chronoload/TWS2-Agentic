import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { subscriptionRepo, subscriptionGroupRepo } from '../db'
import type { SubscriptionEntity } from '../db'

export interface Subscription {
  serviceId: number
  url: string
  name: string
  avatarUrl: string
  subscriberCount: number
  description: string
  subscribedAt: number
  notifEnabled?: boolean
  groupId?: number
}

export interface SubscriptionGroup {
  id: number
  name: string
  sortOrder: number
}

const STORAGE_KEY = 'ts2_subscriptions'
const GROUP_KEY = 'ts2_subscription_groups'

function loadAll(): Subscription[] {
  try {
    return JSON.parse(localStorage.getItem(STORAGE_KEY) || '[]')
  } catch {
    return []
  }
}

function saveAll(list: Subscription[]) {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(list))
}

function loadGroups(): SubscriptionGroup[] {
  try {
    return JSON.parse(localStorage.getItem(GROUP_KEY) || '[]')
  } catch {
    return []
  }
}

function saveGroups(list: SubscriptionGroup[]) {
  localStorage.setItem(GROUP_KEY, JSON.stringify(list))
}

export const useSubscriptionsStore = defineStore('subscriptions', () => {
  const subscriptions = ref<Subscription[]>(loadAll())
  const groups = ref<SubscriptionGroup[]>(loadGroups())
  const notifOnly = ref(false)

  function persist() {
    saveAll(subscriptions.value)
    syncToDB()
  }

  function persistGroups() {
    saveGroups(groups.value)
    syncGroupsToDB()
  }

  async function syncToDB() {
    const entities: SubscriptionEntity[] = subscriptions.value.map(s => ({
      serviceId: s.serviceId,
      url: s.url,
      name: s.name,
      avatarUrl: s.avatarUrl,
      subscriberCount: s.subscriberCount,
      description: s.description,
      notificationMode: s.notifEnabled ? 1 : 0,
      groupId: s.groupId,
      subscribedAt: s.subscribedAt,
    }))
    for (const e of entities) await subscriptionRepo.upsert(e)
  }

  async function syncGroupsToDB() {
    for (const g of groups.value) {
      await subscriptionGroupRepo.upsert({ name: g.name, sortOrder: g.sortOrder })
    }
  }

  async function loadFromDB() {
    const dbSubs = await subscriptionRepo.getAll()
    if (dbSubs.length > 0 && subscriptions.value.length === 0) {
      subscriptions.value = dbSubs.map(s => ({
        serviceId: s.serviceId,
        url: s.url,
        name: s.name,
        avatarUrl: s.avatarUrl,
        subscriberCount: s.subscriberCount,
        description: s.description,
        subscribedAt: s.subscribedAt,
        notifEnabled: s.notificationMode === 1,
        groupId: s.groupId,
      }))
    }
  }

  function subscribe(sub: Omit<Subscription, 'subscribedAt'>) {
    const exists = subscriptions.value.find(s => s.url === sub.url)
    if (exists) return
    subscriptions.value.push({
      ...sub,
      subscribedAt: Date.now(),
      notifEnabled: sub.notifEnabled ?? false,
      groupId: sub.groupId,
    })
    persist()
  }

  function unsubscribe(url: string) {
    subscriptions.value = subscriptions.value.filter(s => s.url !== url)
    persist()
  }

  function isSubscribed(url: string): boolean {
    return subscriptions.value.some(s => s.url === url)
  }

  function getByUrl(url: string): Subscription | undefined {
    return subscriptions.value.find(s => s.url === url)
  }

  function updateInfo(url: string, data: Partial<Subscription>) {
    const sub = subscriptions.value.find(s => s.url === url)
    if (sub) {
      Object.assign(sub, data)
      persist()
    }
  }

  function getNotif(url: string): boolean {
    const sub = subscriptions.value.find(s => s.url === url)
    return sub?.notifEnabled ?? false
  }

  function setNotif(url: string, enabled: boolean) {
    const sub = subscriptions.value.find(s => s.url === url)
    if (sub) {
      sub.notifEnabled = enabled
      persist()
    }
  }

  // --- Group management ---
  function createGroup(name: string): SubscriptionGroup {
    const maxOrder = groups.value.reduce((max, g) => Math.max(max, g.sortOrder), -1)
    const id = Date.now()
    const group: SubscriptionGroup = { id, name, sortOrder: maxOrder + 1 }
    groups.value.push(group)
    persistGroups()
    return group
  }

  function deleteGroup(groupId: number) {
    groups.value = groups.value.filter(g => g.id !== groupId)
    for (const sub of subscriptions.value) {
      if (sub.groupId === groupId) sub.groupId = undefined
    }
    persistGroups()
    persist()
  }

  function renameGroup(groupId: number, name: string) {
    const g = groups.value.find(g => g.id === groupId)
    if (g) { g.name = name; persistGroups() }
  }

  function assignGroup(url: string, groupId?: number) {
    const sub = subscriptions.value.find(s => s.url === url)
    if (sub) { sub.groupId = groupId; persist() }
  }

  function getGroupSubscriptions(groupId?: number): Subscription[] {
    if (groupId === undefined || groupId === -1) {
      // -1 or undefined means "ungrouped"
      return subscriptions.value.filter(s => s.groupId === undefined)
    }
    return subscriptions.value.filter(s => s.groupId === groupId)
  }

  // --- Service ID helpers ---
  function guessServiceId(url: string, existingServiceId?: number): number {
    if (existingServiceId != null) return existingServiceId
    const lower = url.toLowerCase()
    // BiliBili
    if (lower.includes('bilibili.com') || lower.includes('b23.tv') || lower.includes('bili2233.cn')) return 5
    // YouTube
    if (lower.includes('youtube.com') || lower.includes('youtu.be')) return 0
    // NicoNico
    if (lower.includes('nicovideo.jp')) return 1
    // SoundCloud
    if (lower.includes('soundcloud.com')) return 2
    // media.ccc.de
    if (lower.includes('media.ccc.de')) return 3
    // PeerTube
    if (lower.includes('peertube')) return 4
    // Bandcamp
    if (lower.includes('bandcamp.com')) return 6
    // default to YouTube
    return 0
  }

  // --- Import/Export (inspired by PipePipeClient SubscriptionsExportService) ---
  function exportJSON(): string {
    return JSON.stringify({
      version: 1,
      exportedAt: Date.now(),
      subscriptions: subscriptions.value.map(s => ({
        url: s.url, name: s.name, avatarUrl: s.avatarUrl,
        subscriberCount: s.subscriberCount, description: s.description,
        serviceId: s.serviceId, notifEnabled: s.notifEnabled,
      })),
    }, null, 2)
  }

  function importJSON(json: string): { imported: number; errors: string[] } {
    const errors: string[] = []
    let imported = 0
    try {
      const data = JSON.parse(json)
      if (!data.subscriptions || !Array.isArray(data.subscriptions)) {
        return { imported: 0, errors: ['无效的导入文件格式'] }
      }
      for (const s of data.subscriptions) {
        if (!s.url || !s.name) {
          errors.push(`跳过: ${s.name || '未知'} (缺少url或name)`)
          continue
        }
        if (subscriptions.value.some(ex => ex.url === s.url)) continue
        subscriptions.value.push({
          url: s.url, name: s.name, avatarUrl: s.avatarUrl || '',
          subscriberCount: s.subscriberCount || 0, description: s.description || '',
          serviceId: guessServiceId(s.url, s.serviceId), subscribedAt: Date.now(),
          notifEnabled: s.notifEnabled ?? false,
        })
        imported++
      }
      persist()
    } catch (e: any) {
      return { imported: 0, errors: ['JSON解析失败: ' + e.message] }
    }
    return { imported, errors }
  }

  if (subscriptions.value.length === 0) loadFromDB()

  const sorted = computed(() =>
    [...subscriptions.value].sort((a, b) => b.subscribedAt - a.subscribedAt)
  )

  const sortedGroups = computed(() =>
    [...groups.value].sort((a, b) => a.sortOrder - b.sortOrder)
  )

  const notifSubscriptions = computed(() =>
    subscriptions.value.filter(s => s.notifEnabled)
  )

  return {
    subscriptions, groups, notifOnly,
    sorted, sortedGroups, notifSubscriptions,
    subscribe, unsubscribe, isSubscribed, getByUrl, updateInfo,
    getNotif, setNotif,
    createGroup, deleteGroup, renameGroup, assignGroup, getGroupSubscriptions,
    exportJSON, importJSON, guessServiceId,
  }
})
