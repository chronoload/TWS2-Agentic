import { BaseRepository } from './repository'

export interface StreamStateEntity {
  id?: number
  streamUrl: string
  progressMillis: number
  durationSeconds: number
  updatedAt: number
}

const SAVE_THRESHOLD_MS = 5000
const FINISHED_END_MS = 60000

export class StreamStateRepository extends BaseRepository<StreamStateEntity> {
  protected storeName = 'stream_states'

  async getByUrl(url: string): Promise<StreamStateEntity | null> {
    return this.findOne(s => s.streamUrl === url)
  }

  async saveState(url: string, progressMs: number, durationSec: number): Promise<void> {
    if (!url || progressMs < 0) return
    const existing = await this.getByUrl(url)
    if (existing) {
      existing.progressMillis = progressMs
      existing.durationSeconds = durationSec
      existing.updatedAt = Date.now()
      await this.upsert(existing)
    } else {
      await this.upsert({
        streamUrl: url,
        progressMillis: progressMs,
        durationSeconds: durationSec,
        updatedAt: Date.now(),
      })
    }
  }

  async deleteByUrl(url: string): Promise<void> {
    const s = await this.getByUrl(url)
    if (s && s.id != null) await this.delete(s.id)
  }

  isFinished(state: StreamStateEntity): boolean {
    const durationMs = state.durationSeconds * 1000
    const remainingMs = durationMs - state.progressMillis
    return state.progressMillis >= durationMs * 3 / 4 && remainingMs <= FINISHED_END_MS
  }

  shouldSaveState(progressMs: number, durationSec: number): boolean {
    if (durationSec <= 0) return false
    const durationMs = durationSec * 1000
    return progressMs >= SAVE_THRESHOLD_MS || progressMs >= durationMs / 4
  }
}

export const streamStateRepo = new StreamStateRepository()
