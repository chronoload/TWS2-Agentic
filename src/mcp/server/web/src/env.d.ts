/// <reference types="vite/client" />

declare module '*.vue' {
  import type { DefineComponent } from 'vue'
  const component: DefineComponent<object, object, unknown>
  export default component
}

interface Window {
  __TS2_BOOTSTRAP__?: {
    tasks?: any[]
    courses?: any
    bookmarks?: any[]
    projects?: any[]
    agent?: { available: boolean; tools?: number; model?: string }
    push?: any
    push_dashboard?: any
    server?: { version: string; local_ip: string; port: number; uptime: number }
  }
  __TS2_OFFLINE__?: any
}
