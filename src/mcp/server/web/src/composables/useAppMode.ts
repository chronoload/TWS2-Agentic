import { ref, readonly } from 'vue'

export type AppMode = 'local' | 'server_connected' | 'server_disconnected'

const appMode = ref<AppMode>('local')

export function useAppMode() {
  return {
    appMode: readonly(appMode),
    setAppMode(mode: AppMode) {
      appMode.value = mode
    },
    isServerConnected: () => appMode.value === 'server_connected',
  }
}
