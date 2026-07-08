/**
 * Vue 端本地文件系统 — 基于 IndexedDB，独立于 server，离线可用
 * 支持文件夹树、文件读写、与 server 导入导出
 */

const FS_DB_NAME = 'ts2_local_fs'
const FS_DB_VERSION = 1
const FS_FILES_STORE = 'files'
const FS_DIRS_STORE = 'dirs'

// ─── 数据结构 ──────────────────────────────────────────

export interface LocalFile {
  path: string          // 唯一路径，如 "notes/物理/力学.md"
  name: string          // 文件名
  content: string       // 文件内容
  dir: string           // 所属目录
  updatedAt: number     // 最后修改时间
  createdAt: number     // 创建时间
  size: number          // 内容字节数
}

export interface LocalDir {
  path: string          // 唯一路径，如 "notes/物理"
  name: string          // 目录名
  parent: string        // 父目录路径
  updatedAt: number
  createdAt: number
}

export interface DirEntry {
  name: string
  type: 'file' | 'dir'
  path: string
  updatedAt: number
  size?: number
}

// ─── IndexedDB 操作 ──────────────────────────────────────

function openFSDB(): Promise<IDBDatabase> {
  return new Promise((resolve, reject) => {
    const req = indexedDB.open(FS_DB_NAME, FS_DB_VERSION)
    req.onupgradeneeded = () => {
      const db = req.result
      if (!db.objectStoreNames.contains(FS_FILES_STORE)) {
        const store = db.createObjectStore(FS_FILES_STORE, { keyPath: 'path' })
        store.createIndex('dir', 'dir', { unique: false })
      }
      if (!db.objectStoreNames.contains(FS_DIRS_STORE)) {
        const store = db.createObjectStore(FS_DIRS_STORE, { keyPath: 'path' })
        store.createIndex('parent', 'parent', { unique: false })
      }
    }
    req.onsuccess = () => resolve(req.result)
    req.onerror = () => reject(req.error)
  })
}

// ─── 文件操作 ──────────────────────────────────────────

export async function localReadFile(path: string): Promise<LocalFile | null> {
  try {
    const db = await openFSDB()
    return new Promise((resolve, reject) => {
      const tx = db.transaction(FS_FILES_STORE, 'readonly')
      const req = tx.objectStore(FS_FILES_STORE).get(path)
      req.onsuccess = () => resolve(req.result ?? null)
      req.onerror = () => reject(req.error)
      tx.oncomplete = () => db.close()
    })
  } catch {
    return null
  }
}

export async function localWriteFile(path: string, content: string): Promise<void> {
  const now = Date.now()
  const name = path.split('/').pop() || path
  const dir = path.substring(0, path.lastIndexOf('/')) || '/'
  const file: LocalFile = {
    path,
    name,
    content,
    dir,
    updatedAt: now,
    createdAt: now,
    size: new Blob([content]).size,
  }
  // 如果文件已存在，保留 createdAt
  try {
    const existing = await localReadFile(path)
    if (existing) file.createdAt = existing.createdAt
  } catch { /* ignore */ }

  const db = await openFSDB()
  return new Promise((resolve, reject) => {
    const tx = db.transaction(FS_FILES_STORE, 'readwrite')
    tx.objectStore(FS_FILES_STORE).put(file)
    tx.oncomplete = () => { db.close(); resolve() }
    tx.onerror = () => reject(tx.error)
  })
}

export async function localDeleteFile(path: string): Promise<void> {
  const db = await openFSDB()
  return new Promise((resolve, reject) => {
    const tx = db.transaction(FS_FILES_STORE, 'readwrite')
    tx.objectStore(FS_FILES_STORE).delete(path)
    tx.oncomplete = () => { db.close(); resolve() }
    tx.onerror = () => reject(tx.error)
  })
}

// ─── 目录操作 ──────────────────────────────────────────

export async function localMkdir(path: string): Promise<void> {
  const now = Date.now()
  const name = path.split('/').pop() || path
  const parent = path.substring(0, path.lastIndexOf('/')) || '/'
  const dir: LocalDir = {
    path,
    name,
    parent,
    updatedAt: now,
    createdAt: now,
  }
  const db = await openFSDB()
  return new Promise((resolve, reject) => {
    const tx = db.transaction(FS_DIRS_STORE, 'readwrite')
    tx.objectStore(FS_DIRS_STORE).put(dir)
    tx.oncomplete = () => { db.close(); resolve() }
    tx.onerror = () => reject(tx.error)
  })
}

export async function localRmdir(path: string): Promise<void> {
  const db = await openFSDB()
  return new Promise((resolve, reject) => {
    const tx = db.transaction(FS_DIRS_STORE, 'readwrite')
    tx.objectStore(FS_DIRS_STORE).delete(path)
    tx.oncomplete = () => { db.close(); resolve() }
    tx.onerror = () => reject(tx.error)
  })
}

export async function localReadDir(dirPath: string = '/'): Promise<DirEntry[]> {
  const entries: DirEntry[] = []
  const db = await openFSDB()

  // 获取子目录
  const dirs = await new Promise<LocalDir[]>((resolve, reject) => {
    const tx = db.transaction(FS_DIRS_STORE, 'readonly')
    const idx = tx.objectStore(FS_DIRS_STORE).index('parent')
    const req = idx.getAll(dirPath)
    req.onsuccess = () => resolve(req.result ?? [])
    req.onerror = () => reject(req.error)
  })

  for (const d of dirs) {
    entries.push({
      name: d.name,
      type: 'dir',
      path: d.path,
      updatedAt: d.updatedAt,
    })
  }

  // 获取文件
  const files = await new Promise<LocalFile[]>((resolve, reject) => {
    const tx = db.transaction(FS_FILES_STORE, 'readonly')
    const idx = tx.objectStore(FS_FILES_STORE).index('dir')
    const req = idx.getAll(dirPath)
    req.onsuccess = () => resolve(req.result ?? [])
    req.onerror = () => reject(req.error)
  })

  for (const f of files) {
    entries.push({
      name: f.name,
      type: 'file',
      path: f.path,
      updatedAt: f.updatedAt,
      size: f.size,
    })
  }

  db.close()
  return entries.sort((a, b) => {
    // 目录在前，文件在后；同类型按名称排序
    if (a.type !== b.type) return a.type === 'dir' ? -1 : 1
    return a.name.localeCompare(b.name)
  })
}

// ─── 导入导出 ──────────────────────────────────────────

/** 从 server 导入文件到本地 */
export async function importFromServer(
  serverPath: string,
  localPath: string,
  getContent: (path: string) => Promise<string>,
): Promise<boolean> {
  try {
    const content = await getContent(serverPath)
    await localWriteFile(localPath, content)
    return true
  } catch {
    return false
  }
}

/** 从 server 导入整个目录 */
export async function importDirFromServer(
  serverDir: string,
  localDir: string,
  listDir: (path: string) => Promise<any[]>,
  getFile: (path: string) => Promise<string>,
): Promise<number> {
  let count = 0
  try {
    const entries = await listDir(serverDir)
    for (const entry of entries) {
      const serverEntryPath = serverDir ? `${serverDir}/${entry.name}` : entry.name
      const localEntryPath = localDir ? `${localDir}/${entry.name}` : entry.name
      if (entry.type === 'dir' || entry.is_dir) {
        await localMkdir(localEntryPath)
        count += await importDirFromServer(serverEntryPath, localEntryPath, listDir, getFile)
      } else {
        const ok = await importFromServer(serverEntryPath, localEntryPath, getFile)
        if (ok) count++
      }
    }
  } catch { /* ignore */ }
  return count
}

/** 导出本地文件到 server */
export async function exportToServer(
  localPath: string,
  serverPath: string,
  putContent: (path: string, content: string) => Promise<void>,
): Promise<boolean> {
  try {
    const file = await localReadFile(localPath)
    if (!file) return false
    await putContent(serverPath, file.content)
    return true
  } catch {
    return false
  }
}

/** 导出整个本地目录到 server */
export async function exportDirToServer(
  localDir: string,
  serverDir: string,
  putFile: (path: string, content: string) => Promise<void>,
): Promise<number> {
  let count = 0
  const entries = await localReadDir(localDir)
  for (const entry of entries) {
    const serverEntryPath = serverDir ? `${serverDir}/${entry.name}` : entry.name
    const localEntryPath = localDir ? `${localDir}/${entry.name}` : entry.name
    if (entry.type === 'dir') {
      count += await exportDirToServer(localEntryPath, serverEntryPath, putFile)
    } else {
      const ok = await exportToServer(localEntryPath, serverEntryPath, putFile)
      if (ok) count++
    }
  }
  return count
}

/** 获取本地文件系统统计 */
export async function localFSStats(): Promise<{ files: number; dirs: number; totalSize: number }> {
  const db = await openFSDB()
  const files = await new Promise<LocalFile[]>((resolve, reject) => {
    const tx = db.transaction(FS_FILES_STORE, 'readonly')
    const req = tx.objectStore(FS_FILES_STORE).getAll()
    req.onsuccess = () => resolve(req.result ?? [])
    req.onerror = () => reject(req.error)
  })
  const dirs = await new Promise<LocalDir[]>((resolve, reject) => {
    const tx = db.transaction(FS_DIRS_STORE, 'readonly')
    const req = tx.objectStore(FS_DIRS_STORE).getAll()
    req.onsuccess = () => resolve(req.result ?? [])
    req.onerror = () => reject(req.error)
  })
  db.close()
  return {
    files: files.length,
    dirs: dirs.length,
    totalSize: files.reduce((sum, f) => sum + (f.size || 0), 0),
  }
}

/** 清空本地文件系统 */
export async function localFSClear(): Promise<void> {
  const db = await openFSDB()
  return new Promise((resolve, reject) => {
    const tx = db.transaction([FS_FILES_STORE, FS_DIRS_STORE], 'readwrite')
    tx.objectStore(FS_FILES_STORE).clear()
    tx.objectStore(FS_DIRS_STORE).clear()
    tx.oncomplete = () => { db.close(); resolve() }
    tx.onerror = () => reject(tx.error)
  })
}

// ─── 二进制文件支持（base64 存储） ──────────────────────

/** 判断是否是二进制文件扩展名 */
const BINARY_EXTS = new Set([
  '.pdf', '.docx', '.xlsx', '.xls', '.pptx',
  '.png', '.jpg', '.jpeg', '.gif', '.svg', '.webp', '.bmp',
  '.zip', '.rar', '.7z', '.tar', '.gz',
])

export function isBinaryExt(ext: string): boolean {
  return BINARY_EXTS.has(ext.toLowerCase())
}

/** 将 Blob 转为 base64 字符串（去掉 data:...;base64, 前缀） */
function blobToBase64(blob: Blob): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader()
    reader.onloadend = () => {
      const result = reader.result as string
      const base64 = result.includes(',') ? result.split(',')[1] : result
      resolve(base64)
    }
    reader.onerror = () => reject(reader.error)
    reader.readAsDataURL(blob)
  })
}

/** 将 base64 字符串转为 Blob */
function base64ToBlob(base64: string, mimeType: string = 'application/octet-stream'): Blob {
  try {
    const bytes = atob(base64)
    const arr = new Uint8Array(bytes.length)
    for (let i = 0; i < bytes.length; i++) {
      arr[i] = bytes.charCodeAt(i)
    }
    return new Blob([arr], { type: mimeType })
  } catch {
    return new Blob([], { type: mimeType })
  }
}

/** 写入二进制文件（以 base64 字符串形式存储） */
export async function localWriteFileBlob(path: string, blob: Blob): Promise<void> {
  const base64 = await blobToBase64(blob)
  await localWriteFile(path, base64)
}

/** 读取二进制文件，返回 Blob */
export async function localReadFileBlob(path: string): Promise<Blob | null> {
  const file = await localReadFile(path)
  if (!file) return null
  return base64ToBlob(file.content)
}

// ─── 递归搜索 ──────────────────────────────────────────

/** 递归搜索本地文件树，返回匹配的文件和目录 */
export async function localSearchTree(query: string, dirPath: string = '/'): Promise<DirEntry[]> {
  const results: DirEntry[] = []
  const q = query.toLowerCase()

  async function search(dPath: string) {
    let entries: DirEntry[] = []
    try {
      entries = await localReadDir(dPath)
    } catch { return }
    for (const entry of entries) {
      if (entry.type === 'dir') {
        // 目录名匹配也加入结果
        if (entry.name.toLowerCase().includes(q)) {
          results.push(entry)
        }
        await search(entry.path)
      } else {
        if (entry.name.toLowerCase().includes(q) || entry.path.toLowerCase().includes(q)) {
          results.push(entry)
        }
      }
    }
  }

  await search(dirPath)
  return results
}
