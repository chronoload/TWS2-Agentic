const DB_NAME = 'ts2_app'
const DB_VERSION = 1

let _db: IDBDatabase | null = null

async function openDB(): Promise<IDBDatabase> {
  if (_db) return _db
  return new Promise((resolve, reject) => {
    const req = indexedDB.open(DB_NAME, DB_VERSION)
    req.onupgradeneeded = () => {
      const db = req.result
      const stores = ['streams', 'stream_states', 'subscriptions', 'subscription_groups', 'feed', 'feed_last_updated', 'playlists', 'remote_playlists', 'playlist_streams']
      for (const name of stores) {
        if (!db.objectStoreNames.contains(name)) {
          db.createObjectStore(name, { keyPath: 'id', autoIncrement: true })
        }
      }
    }
    req.onsuccess = () => { _db = req.result; resolve(_db) }
    req.onerror = () => reject(req.error)
  })
}

export async function getAll<T>(storeName: string): Promise<T[]> {
  const db = await openDB()
  return new Promise((resolve, reject) => {
    const tx = db.transaction(storeName, 'readonly')
    const store = tx.objectStore(storeName)
    const req = store.getAll()
    req.onsuccess = () => resolve(req.result as T[])
    req.onerror = () => reject(req.error)
  })
}

export async function getByKey<T>(storeName: string, key: IDBValidKey): Promise<T | null> {
  const db = await openDB()
  return new Promise((resolve, reject) => {
    const tx = db.transaction(storeName, 'readonly')
    const store = tx.objectStore(storeName)
    const req = store.get(key)
    req.onsuccess = () => resolve(req.result as T ?? null)
    req.onerror = () => reject(req.error)
  })
}

export async function put<T>(storeName: string, value: T): Promise<IDBValidKey> {
  const db = await openDB()
  return new Promise((resolve, reject) => {
    const tx = db.transaction(storeName, 'readwrite')
    const store = tx.objectStore(storeName)
    const req = store.put(value)
    req.onsuccess = () => resolve(req.result)
    req.onerror = () => reject(req.error)
  })
}

export async function remove(storeName: string, key: IDBValidKey): Promise<void> {
  const db = await openDB()
  return new Promise((resolve, reject) => {
    const tx = db.transaction(storeName, 'readwrite')
    const store = tx.objectStore(storeName)
    store.delete(key)
    tx.oncomplete = () => resolve()
    tx.onerror = () => reject(tx.error)
  })
}

export async function clear(storeName: string): Promise<void> {
  const db = await openDB()
  return new Promise((resolve, reject) => {
    const tx = db.transaction(storeName, 'readwrite')
    const store = tx.objectStore(storeName)
    store.clear()
    tx.oncomplete = () => resolve()
    tx.onerror = () => reject(tx.error)
  })
}

export async function find<T>(storeName: string, predicate: (item: T) => boolean): Promise<T[]> {
  const all = await getAll<T>(storeName)
  return all.filter(predicate)
}

export async function findOne<T>(storeName: string, predicate: (item: T) => boolean): Promise<T | null> {
  const all = await getAll<T>(storeName)
  return all.find(predicate) ?? null
}

export async function count(storeName: string): Promise<number> {
  const db = await openDB()
  return new Promise((resolve, reject) => {
    const tx = db.transaction(storeName, 'readonly')
    const store = tx.objectStore(storeName)
    const req = store.count()
    req.onsuccess = () => resolve(req.result)
    req.onerror = () => reject(req.error)
  })
}

export async function iterate(storeName: string, fn: (item: any, cursor: IDBCursorWithValue) => void): Promise<void> {
  const db = await openDB()
  return new Promise((resolve, reject) => {
    const tx = db.transaction(storeName, 'readwrite')
    const store = tx.objectStore(storeName)
    const req = store.openCursor()
    req.onsuccess = (event: any) => {
      const cursor = event.target.result as IDBCursorWithValue | null
      if (cursor) {
        fn(cursor.value, cursor)
        cursor.continue()
      }
    }
    tx.oncomplete = () => resolve()
    tx.onerror = () => reject(tx.error)
  })
}

export async function batchPut<T>(storeName: string, items: T[]): Promise<void> {
  const db = await openDB()
  return new Promise((resolve, reject) => {
    const tx = db.transaction(storeName, 'readwrite')
    const store = tx.objectStore(storeName)
    for (const item of items) store.put(item)
    tx.oncomplete = () => resolve()
    tx.onerror = () => reject(tx.error)
  })
}
