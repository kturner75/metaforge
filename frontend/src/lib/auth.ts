export type AuthTokens = {
  accessToken: string
  refreshToken: string
  expiresAt: number
}

const STORAGE_KEY = 'metaforge.auth'
const AUTH_EVENT = 'metaforge:auth'

function notifyAuthChange() {
  window.dispatchEvent(new CustomEvent(AUTH_EVENT))
}

export function getAuthTokens(): AuthTokens | null {
  if (typeof window === 'undefined') return null
  const raw = window.localStorage.getItem(STORAGE_KEY)
  if (!raw) return null

  try {
    const parsed = JSON.parse(raw) as AuthTokens
    if (!parsed?.accessToken || !parsed?.refreshToken || !parsed?.expiresAt) {
      return null
    }
    return parsed
  } catch {
    return null
  }
}

export function setAuthTokens(tokens: AuthTokens) {
  if (typeof window === 'undefined') return
  window.localStorage.setItem(STORAGE_KEY, JSON.stringify(tokens))
  notifyAuthChange()
}

export function clearAuthTokens() {
  if (typeof window === 'undefined') return
  window.localStorage.removeItem(STORAGE_KEY)
  notifyAuthChange()
}

export function getAccessToken(): string | null {
  return getAuthTokens()?.accessToken ?? null
}

export function getRefreshToken(): string | null {
  return getAuthTokens()?.refreshToken ?? null
}

export function subscribeAuthChange(handler: () => void) {
  window.addEventListener(AUTH_EVENT, handler)
  return () => window.removeEventListener(AUTH_EVENT, handler)
}
