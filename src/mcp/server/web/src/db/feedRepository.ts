import { BaseRepository } from './repository'
import { iterate } from './database'
import { streamRepo } from './streamRepository'

export interface FeedEntity {
  id?: number
  streamUrl: string
  subscriptionUrl: string
  channelName: string
  channelUrl: string
  addedAt: number
}

const FEED_WEEKS = 13
const FEED_OLDEST_ALLOWED_MS = FEED_WEEKS * 7 * 24 * 60 * 60 * 1000

export class FeedRepository extends BaseRepository<FeedEntity> {
  protected storeName = 'feed'

  async getBySubscription(subscriptionUrl: string): Promise<FeedEntity[]> {
    return this.find(f => f.subscriptionUrl === subscriptionUrl)
  }

  async getByStreamUrl(url: string): Promise<FeedEntity | null> {
    return this.findOne(f => f.streamUrl === url)
  }

  async upsertAll(
    subscriptionUrl: string,
    channelName: string,
    channelUrl: string,
    items: Array<{ url: string; title: string; streamType: string; duration: number; uploader: string; thumbnailUrl?: string; viewCount?: number; textualUploadDate?: string }>
  ): Promise<void> {
    const now = Date.now()
    const oldestAllowed = now - FEED_OLDEST_ALLOWED_MS

    const toInsert = items.filter(item => {
      if (item.streamType === 'LIVE_STREAM') return true
      return now >= oldestAllowed
    })

    for (const item of toInsert) {
      const existing = await this.getByStreamUrl(item.url)
      if (!existing) {
        await this.upsert({
          streamUrl: item.url,
          subscriptionUrl,
          channelName,
          channelUrl,
          addedAt: now,
        })
      }
    }

    await streamRepo.upsertAll(
      toInsert.map(item => ({
        url: item.url,
        title: item.title,
        streamType: item.streamType,
        duration: item.duration,
        uploader: item.uploader,
        thumbnailUrl: item.thumbnailUrl,
        viewCount: item.viewCount,
        textualUploadDate: item.textualUploadDate,
      }))
    )
  }

  async pruneStale(): Promise<number> {
    const cutoff = Date.now() - FEED_OLDEST_ALLOWED_MS
    let deleted = 0
    await iterate(this.storeName, (item, cursor) => {
      const feed = item as FeedEntity
      if (feed.addedAt < cutoff) {
        cursor.delete()
        deleted++
      }
    })
    return deleted
  }

  async getUnplayedStreams(playedUrls: Set<string>): Promise<FeedEntity[]> {
    const all = await this.getAll()
    return all.filter(f => !playedUrls.has(f.streamUrl))
  }

  static isPruneDue(lastPrune: number): boolean {
    return Date.now() - lastPrune > 24 * 60 * 60 * 1000
  }
}

export const feedRepo = new FeedRepository()
