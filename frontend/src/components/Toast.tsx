import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from 'react'
import { AlertCircle, CheckCircle2, Info, X } from 'lucide-react'
import { ToastCtx, type ToastApi, type ToastKind } from './toast-context'

interface Toast { id: number; kind: ToastKind; message: string }

const ICON = { success: CheckCircle2, error: AlertCircle, info: Info } as const

/** App-wide success / error / info messages. Errors are announced assertively to screen readers, the rest politely. */
export function ToastProvider({ children }: { children: ReactNode }) {
  const [items, setItems] = useState<Toast[]>([])
  const next = useRef(1)
  const timers = useRef(new Map<number, ReturnType<typeof setTimeout>>())

  const dismiss = useCallback((id: number) => {
    clearTimeout(timers.current.get(id)); timers.current.delete(id)
    setItems((xs) => xs.filter((x) => x.id !== id))
  }, [])
  const push = useCallback((kind: ToastKind, message: string) => {
    const id = next.current++
    setItems((xs) => [...xs.slice(-3), { id, kind, message }])                       // at most 4 on screen
    timers.current.set(id, setTimeout(() => dismiss(id), kind === 'error' ? 8000 : 4500))
  }, [dismiss])
  useEffect(() => { const t = timers.current; return () => t.forEach(clearTimeout) }, [])

  const api = useMemo<ToastApi>(() => ({ success: (m) => push('success', m), error: (m) => push('error', m), info: (m) => push('info', m) }), [push])
  return (
    <ToastCtx.Provider value={api}>
      {children}
      <div className="toasts" aria-label="Notifications">
        {items.map((t) => {
          const Icon = ICON[t.kind]
          return (
            <div key={t.id} className={`toast toast--${t.kind}`} role={t.kind === 'error' ? 'alert' : 'status'}>
              <Icon size={18} aria-hidden="true" />
              <span className="toast__msg">{t.message}</span>
              <button className="toast__close" onClick={() => dismiss(t.id)} aria-label="Dismiss notification"><X size={16} aria-hidden="true" /></button>
            </div>
          )
        })}
      </div>
    </ToastCtx.Provider>
  )
}
