import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useEffect, useState, type ReactNode } from 'react'
import { auth } from '../api'
import { setAccessToken, getAccessToken } from '../lib/auth-store'
import { setSessionLostHandler } from '../lib/api-client'
import { qk } from '../lib/query-keys'
import { AuthContext, type AuthValue } from './auth-context'

export function AuthProvider({ children }: { children: ReactNode }) {
  const client = useQueryClient()
  const [state, setState] = useState<AuthValue['state']>('checking')

  useEffect(() => {
    setSessionLostHandler(() => {
      setAccessToken(null)
      client.clear()
      setState('anonymous')
    })
  }, [client])

  useEffect(() => {
    // The access token lives in memory, so a reload has none. The refresh
    // cookie survives, and this is what turns it back into a session.
    let cancelled = false
    auth
      .refresh()
      .then((token) => {
        if (cancelled) return
        setAccessToken(token.access_token)
        setState('authenticated')
      })
      .catch(() => {
        if (!cancelled) setState('anonymous')
      })
    return () => {
      cancelled = true
    }
  }, [])

  const me = useQuery({
    queryKey: qk.me,
    queryFn: auth.me,
    enabled: state === 'authenticated' && getAccessToken() !== null,
    retry: false,
  })

  const loginMutation = useMutation({
    mutationFn: auth.login,
    onSuccess: (token) => {
      setAccessToken(token.access_token)
      setState('authenticated')
    },
  })

  const signupMutation = useMutation({
    mutationFn: auth.signup,
    onSuccess: (token) => {
      setAccessToken(token.access_token)
      setState('authenticated')
    },
  })

  const value: AuthValue = {
    state,
    user: me.data,
    login: async (body) => {
      await loginMutation.mutateAsync(body)
    },
    signup: async (body) => {
      await signupMutation.mutateAsync(body)
    },
    logout: async () => {
      try {
        await auth.logout()
      } finally {
        setAccessToken(null)
        // Otherwise the next account to sign in on this browser sees the
        // previous one's cached lists before the refetch lands.
        client.clear()
        setState('anonymous')
      }
    },
  }

  return <AuthContext value={value}>{children}</AuthContext>
}
