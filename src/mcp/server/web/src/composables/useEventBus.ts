import { ref } from 'vue'

type EventCallback = (payload: any) => void

interface EventMap {
  checkpoint_created: { version: number; hash: string }
  agent_status: { available: boolean }
  session_switched: { session_id: string }
}

type HandlerStore = { [K in keyof EventMap]?: EventCallback }

const bus = ref<{ handlers: HandlerStore }>({
  handlers: {},
})

export function useEventBus() {
  function on<K extends keyof EventMap>(event: K, cb: (payload: EventMap[K]) => void) {
    bus.value.handlers[event] = cb as EventCallback
  }

  function off<K extends keyof EventMap>(event: K) {
    delete bus.value.handlers[event]
  }

  function emit<K extends keyof EventMap>(event: K, payload: EventMap[K]) {
    const handler = bus.value.handlers[event]
    if (handler) handler(payload)
  }

  return { on, off, emit }
}
