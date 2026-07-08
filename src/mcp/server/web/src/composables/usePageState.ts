import { ref, type Ref } from 'vue'

export interface PageState<T> {
  items: Ref<T[]>
  info: Ref<any>
  loading: Ref<boolean>
  loadingMore: Ref<boolean>
  error: Ref<string>
  hasNextPage: Ref<boolean>
  nextPageUrl: Ref<string>
  rawResult: Ref<any>
  reset(): void
  setLoading(): void
  setError(msg: string): void
  setData(data: { items?: T[]; _hasNextPage?: boolean; _nextPageUrl?: string; _error?: string }, append?: boolean): void
}

export function usePageState<T>(): PageState<T> {
  const items = ref<T[]>([]) as Ref<T[]>
  const info = ref<any>(null)
  const loading = ref(false)
  const loadingMore = ref(false)
  const error = ref('')
  const hasNextPage = ref(false)
  const nextPageUrl = ref('')
  const rawResult = ref<any>(null)

  function reset() {
    items.value = []
    info.value = null
    loading.value = false
    loadingMore.value = false
    error.value = ''
    hasNextPage.value = false
    nextPageUrl.value = ''
    rawResult.value = null
  }

  function setLoading() {
    loading.value = true
    error.value = ''
  }

  function setError(msg: string) {
    error.value = msg
    loading.value = false
    loadingMore.value = false
  }

  function setData(data: any, append = false) {
    rawResult.value = data
    if (data.items) {
      if (append) {
        const existing = new Set(items.value.map((i: any) => i.url))
        for (const item of data.items) {
          if (!existing.has(item.url)) {
            items.value.push(item)
            existing.add(item.url)
          }
        }
      } else {
        items.value = data.items
      }
    }
    hasNextPage.value = !!data._hasNextPage
    nextPageUrl.value = data._nextPageUrl || ''
    if (data._error) error.value = data._error
    loading.value = false
    loadingMore.value = false
  }

  return { items, info, loading, loadingMore, error, hasNextPage, nextPageUrl, rawResult, reset, setLoading, setError, setData }
}
