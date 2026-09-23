import { createContext, use } from 'react'
import type { User } from '../types'

export interface AuthValue {
  state: 'checking' | 'authenticated' | 'anonymous'
  user: User | undefined
  login: (body: { tenant_slug: string; email: string; password: string }) => Promise<void>
  signup: (body: {
    company_name: string
    tenant_slug: string
    email: string
    password: string
    full_name: string
  }) => Promise<void>
  logout: () => Promise<void>
}

export const AuthContext = createContext<AuthValue | null>(null)

export function useAuth(): AuthValue {
  const value = use(AuthContext)
  if (!value) throw new Error('useAuth must be used inside AuthProvider')
  return value
}
