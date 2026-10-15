import { createContext, useContext } from 'react'
import type { Role, User } from '../types'

export type Status = 'loading' | 'authed' | 'anon'
export interface AuthState { status: Status; user: User | null; role: Role | null; adminSession: boolean; reload: () => Promise<void>; signOut: () => Promise<void> }

export const AuthCtx = createContext<AuthState | null>(null)

export function useAuth(): AuthState {
  const v = useContext(AuthCtx)
  if (!v) throw new Error('useAuth must be used inside <AuthProvider>')
  return v
}

export const ROLE_RANK: Record<Role, number> = { viewer: 1, analyst: 2, admin: 3 }
export const atLeast = (role: Role | null, min: Role): boolean => !!role && ROLE_RANK[role] >= ROLE_RANK[min]
