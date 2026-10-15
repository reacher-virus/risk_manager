import { createContext, useContext } from 'react'

export type ToastKind = 'success' | 'error' | 'info'
export interface ToastApi { success: (m: string) => void; error: (m: string) => void; info: (m: string) => void }

export const ToastCtx = createContext<ToastApi | null>(null)

const noop: ToastApi = { success: () => {}, error: () => {}, info: () => {} }
/** Safe to call anywhere: outside a provider (e.g. an isolated test) it quietly does nothing. */
export function useToast(): ToastApi {
  return useContext(ToastCtx) ?? noop
}
