import { BaseRepository } from './repository'

export interface LocalPlaylistEntity {
  id?: number
  playlistId: string
  name: string
  createdAt: number
  streamUrls: string[]
}

export interface RemotePlaylistEntity {
  id?: number
  url: string
  name: string
  serviceId: number
  thumbnailUrl: string
  uploaderName: string
  uploaderAvatarUrl: string
  streamCount: number
}

export class LocalPlaylistRepository extends BaseRepository<LocalPlaylistEntity> {
  protected storeName = 'playlists'

  async getByPlaylistId(playlistId: string): Promise<LocalPlaylistEntity | null> {
    return this.findOne(p => p.playlistId === playlistId)
  }

  async addStream(playlistId: string, streamUrl: string): Promise<void> {
    const pl = await this.getByPlaylistId(playlistId)
    if (!pl) return
    if (!pl.streamUrls.includes(streamUrl)) {
      pl.streamUrls.push(streamUrl)
      await this.upsert(pl)
    }
  }

  async removeStream(playlistId: string, streamUrl: string): Promise<void> {
    const pl = await this.getByPlaylistId(playlistId)
    if (!pl) return
    pl.streamUrls = pl.streamUrls.filter(u => u !== streamUrl)
    await this.upsert(pl)
  }

  async containsStream(playlistId: string, streamUrl: string): Promise<boolean> {
    const pl = await this.getByPlaylistId(playlistId)
    return pl ? pl.streamUrls.includes(streamUrl) : false
  }
}

export class RemotePlaylistRepository extends BaseRepository<RemotePlaylistEntity> {
  protected storeName = 'remote_playlists'

  async getByUrl(url: string): Promise<RemotePlaylistEntity | null> {
    return this.findOne(p => p.url === url)
  }

  async upsertByUrl(entity: RemotePlaylistEntity): Promise<void> {
    const existing = await this.getByUrl(entity.url)
    if (existing) {
      entity.id = existing.id
      await this.upsert(entity)
    } else {
      await this.upsert(entity)
    }
  }

  async isIdenticalTo(entity: RemotePlaylistEntity): Promise<boolean> {
    const existing = await this.getByUrl(entity.url)
    if (!existing) return false
    return existing.name === entity.name
      && existing.thumbnailUrl === entity.thumbnailUrl
      && existing.uploaderName === entity.uploaderName
      && existing.streamCount === entity.streamCount
  }
}

export const localPlaylistRepo = new LocalPlaylistRepository()
export const remotePlaylistRepo = new RemotePlaylistRepository()
