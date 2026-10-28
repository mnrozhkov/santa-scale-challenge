export type AccessRole = 'guest' | 'operator'

const STORAGE_KEY = 'santa-operator'

export function captureOperatorFromUrl(): void {
  const url = new URL(window.location.href)
  const op = url.searchParams.get('op')
  if (!op) return
  sessionStorage.setItem(STORAGE_KEY, op)
  url.searchParams.delete('op')
  const qs = url.searchParams.toString()
  window.history.replaceState(null, '', `${url.pathname}${qs ? `?${qs}` : ''}${url.hash}`)
}

export function operatorHeaders(): Record<string, string> {
  const tok = sessionStorage.getItem(STORAGE_KEY)
  return tok ? { 'X-Santa-Operator': tok } : {}
}

export function kioskOrigin(): string {
  return window.location.origin
}

export async function fetchAccess(): Promise<AccessRole> {
  const resp = await fetch('/api/access', { headers: operatorHeaders() })
  if (!resp.ok) return 'guest'
  const data = (await resp.json()) as { role?: unknown }
  return data.role === 'operator' ? 'operator' : 'guest'
}
