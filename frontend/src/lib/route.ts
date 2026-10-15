import { useSyncExternalStore } from 'react'

export interface Route { path: string; params: URLSearchParams }

/** "#/reset?token=abc" -> { path: "/reset", params: {token: "abc"} }. Hash routing keeps secrets (reset tokens) out of server logs and Referer headers. */
export function parseHash(hash: string): Route {
  const raw = hash.replace(/^#/, '') || '/'
  const [path, query = ''] = raw.split('?')
  return { path: path.startsWith('/') ? path : `/${path}`, params: new URLSearchParams(query) }
}

export function navigate(path: string, replace = false): void {
  const target = `#${path}`
  if (replace) window.history.replaceState(null, '', target)
  else window.location.hash = path
  window.dispatchEvent(new HashChangeEvent('hashchange'))
}

const subscribe = (cb: () => void) => { window.addEventListener('hashchange', cb); return () => window.removeEventListener('hashchange', cb) }
const snapshot = () => window.location.hash

export function useRoute(): Route {
  return parseHash(useSyncExternalStore(subscribe, snapshot))
}
