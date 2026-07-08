import { BaseRepository } from './repository'
import { iterate } from './database'

export interface StreamEntity {
  id?: number
  url: string
  title: string
  streamType: string
  duration: number
  uploader: string
  uploaderUrl?: string
  thumbnailUrl?: string
  viewCount?: number
  textualUploadDate?: string
  uploadDate?: string
  isPaid?: boolean
}

export class StreamRepository extends BaseRepository<StreamEntity> {
  protected storeName = 'streams'

  async getByUrl(url: string): Promise<StreamEntity | null> {
    return this.findOne(s => s.url === url)
  }

  async deleteByUrl(url: string): Promise<void> {
    const s = await this.getByUrl(url)
    if (s && s.id != null) await this.delete(s.id)
  }

  async upsertAll(streams: StreamEntity[]): Promise<StreamEntity[]> {
    const result: StreamEntity[] = []
    for (const newer of streams) {
      const existing = await this.getByUrl(newer.url)
      if (existing) {
        this.compareAndUpdateStream(existing, newer)
        await this.upsert(existing)
        result.push(existing)
      } else {
        const id = await this.upsert(newer)
        result.push({ ...newer, id: id as number })
      }
    }
    return result
  }

  private compareAndUpdateStream(existing: StreamEntity, newer: StreamEntity): void {
    if (newer.title) existing.title = newer.title
    if (newer.duration > 0 && (existing.duration <= 0 || newer.duration > existing.duration)) existing.duration = newer.duration
    if (newer.uploadDate && newer.streamType !== 'LIVE_STREAM') existing.uploadDate = newer.uploadDate
    if (newer.thumbnailUrl) existing.thumbnailUrl = newer.thumbnailUrl
    if (newer.viewCount != null) existing.viewCount = newer.viewCount
    if (newer.textualUploadDate) existing.textualUploadDate = newer.textualUploadDate
  }

  async deleteOrphans(referencedStreamIds: Set<number>): Promise<number> {
    let deleted = 0
    await iterate(this.storeName, (item, cursor) => {
      const stream = item as StreamEntity
      if (stream.id != null && !referencedStreamIds.has(stream.id)) {
        cursor.delete()
        deleted++
      }
    })
    return deleted
  }
}

export const streamRepo = new StreamRepository()
