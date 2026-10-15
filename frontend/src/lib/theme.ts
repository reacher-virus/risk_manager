import { useCallback, useEffect, useState } from 'react'

export type Theme = 'dark' | 'light'
const KEY = 'risk_theme'

const read = (): Theme => {
  try { return localStorage.getItem(KEY) === 'light' ? 'light' : 'dark' } catch { return 'dark' }
}

/** Light/dark preference, persisted. (The sign-in screens are always dark by design: they use `.force-dark`.) */
export function useTheme(): [Theme, () => void, (t: Theme) => void] {
  const [theme, setTheme] = useState<Theme>(read)
  useEffect(() => {
    document.documentElement.dataset.theme = theme
    try { localStorage.setItem(KEY, theme) } catch { /* private mode: keep it for this visit only */ }
  }, [theme])
  const toggle = useCallback(() => setTheme((t) => (t === 'dark' ? 'light' : 'dark')), [])
  return [theme, toggle, setTheme]
}
