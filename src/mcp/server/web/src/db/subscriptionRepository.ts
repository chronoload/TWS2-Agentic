import { BaseRepository } from './repository'

export interface SubscriptionEntity {
  id?: number
  serviceId: number
  url: string
  name: string
  avatarUrl: string
  subscriberCount: number
  description: string
  notificationMode: number
  groupId?: number
  subscribedAt: number
}

export interface SubscriptionGroupEntity {
  id?: number
  name: string
  sortOrder: number
}

export class SubscriptionRepository extends BaseRepository<SubscriptionEntity> {
  protected storeName = 'subscriptions'

  async getByServiceAndUrl(serviceId: number, url: string): Promise<SubscriptionEntity | null> {
    return this.findOne(s => s.serviceId === serviceId && s.url === url)
  }

  async upsertAll(entities: SubscriptionEntity[]): Promise<SubscriptionEntity[]> {
    const result: SubscriptionEntity[] = []
    for (const entity of entities) {
      const existing = await this.getByServiceAndUrl(entity.serviceId, entity.url)
      if (existing) {
        entity.id = existing.id
        await this.upsert(entity)
        result.push(entity)
      } else {
        const id = await this.upsert(entity)
        result.push({ ...entity, id: id as number })
      }
    }
    return result
  }

  async getByGroup(groupId: number): Promise<SubscriptionEntity[]> {
    return this.find(s => s.groupId === groupId)
  }

  async getUngrouped(): Promise<SubscriptionEntity[]> {
    return this.find(s => s.groupId == null)
  }

  async getByNotifMode(mode: number): Promise<SubscriptionEntity[]> {
    return this.find(s => s.notificationMode === mode)
  }
}

export class SubscriptionGroupRepository extends BaseRepository<SubscriptionGroupEntity> {
  protected storeName = 'subscription_groups'

  async getByName(name: string): Promise<SubscriptionGroupEntity | null> {
    return this.findOne(g => g.name === name)
  }
}

export const subscriptionRepo = new SubscriptionRepository()
export const subscriptionGroupRepo = new SubscriptionGroupRepository()
