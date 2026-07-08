import { ref } from 'vue'

export type ToastType = 'success' | 'error' | 'warning' | 'info'

export interface Toast {
  id: number
  message: string
  type: ToastType
  duration: number
}

const toasts = ref<Toast[]>([])
let nextId = 0

export function useToast() {
  function show(message: string, type: ToastType = 'info', duration: number = 3000) {
    const id = ++nextId
    toasts.value.push({ id, message, type, duration })
    if (duration > 0) {
      setTimeout(() => dismiss(id), duration)
    }
  }

  function success(message: string, duration?: number) {
    show(message, 'success', duration)
  }

  function error(message: string, duration?: number) {
    show(message, 'error', duration ?? 4000)
  }

  function warning(message: string, duration?: number) {
    show(message, 'warning', duration)
  }

  function info(message: string, duration?: number) {
    show(message, 'info', duration)
  }

  function dismiss(id: number) {
    const idx = toasts.value.findIndex(t => t.id === id)
    if (idx !== -1) toasts.value.splice(idx, 1)
  }

  return { toasts, show, success, error, warning, info, dismiss }
}
