import { useCallback, useEffect, useState } from 'react'
import { fetchJson } from '@/lib/api'
import {
  clearAuthTokens,
  getAuthTokens,
  setAuthTokens,
  subscribeAuthChange,
  type AuthTokens,
} from '@/lib/auth'

export type LoginInput = {
  email: string
  password: string
  tenantId?: string
}

type LoginResponse = {
  access_token: string
  refresh_token: string
  expires_in: number
}

export function useAuth() {
  const [tokens, setTokens] = useState<AuthTokens | null>(() => getAuthTokens())
  const [error, setError] = useState<string | null>(null)
  const [isLoggingIn, setIsLoggingIn] = useState(false)

  useEffect(() => subscribeAuthChange(() => setTokens(getAuthTokens())), [])

  const login = useCallback(async (input: LoginInput) => {
    setIsLoggingIn(true)
    setError(null)

    try {
      const response = await fetchJson<LoginResponse>('/api/auth/login', {
        method: 'POST',
        body: JSON.stringify({
          email: input.email,
          password: input.password,
          tenant_id: input.tenantId || null,
        }),
        skipAuthRefresh: true,
      })

      const nextTokens: AuthTokens = {
        accessToken: response.access_token,
        refreshToken: response.refresh_token,
        expiresAt: Date.now() + response.expires_in * 1000,
      }

      setAuthTokens(nextTokens)
      return true
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Login failed'
      setError(message)
      return false
    } finally {
      setIsLoggingIn(false)
    }
  }, [])

  const logout = useCallback(() => {
    clearAuthTokens()
  }, [])

  return {
    tokens,
    isAuthenticated: !!tokens?.accessToken,
    login,
    logout,
    isLoggingIn,
    error,
  }
}
