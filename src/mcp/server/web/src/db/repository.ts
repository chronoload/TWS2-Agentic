import { getAll, getByKey, put, remove, clear, find, findOne, count } from './database'

export interface Repository<T extends { id?: IDBValidKey }> {
  getAll(): Promise<T[]>
  getById(id: IDBValidKey): Promise<T | null>
  upsert(entity: T): Promise<IDBValidKey>
  delete(id: IDBValidKey): Promise<void>
  clearAll(): Promise<void>
  count(): Promise<number>
}

export abstract class BaseRepository<T extends { id?: IDBValidKey }> implements Repository<T> {
  protected abstract storeName: string

  async getAll(): Promise<T[]> {
    return getAll<T>(this.storeName)
  }

  async getById(id: IDBValidKey): Promise<T | null> {
    return getByKey<T>(this.storeName, id)
  }

  async upsert(entity: T): Promise<IDBValidKey> {
    return put(this.storeName, entity)
  }

  async delete(id: IDBValidKey): Promise<void> {
    return remove(this.storeName, id)
  }

  async clearAll(): Promise<void> {
    return clear(this.storeName)
  }

  async count(): Promise<number> {
    return count(this.storeName)
  }

  protected async find(predicate: (item: T) => boolean): Promise<T[]> {
    return find(this.storeName, predicate)
  }

  protected async findOne(predicate: (item: T) => boolean): Promise<T | null> {
    return findOne(this.storeName, predicate)
  }
}
