import {
  clearAuthTokens,
  getAuthTokens,
  getRefreshToken,
  setAuthTokens,
  type AuthTokens,
} from './auth'

export interface ValidationErrorItem {
  message: string
  code: string
  field: string | null
  severity: 'error' | 'warning'
}

export interface ValidationErrorBody {
  valid: false
  errors: ValidationErrorItem[]
  warnings: ValidationErrorItem[]
}

export class ApiError extends Error {
  status: number
  validation?: ValidationErrorBody

  constructor(message: string, status: number, validation?: ValidationErrorBody) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.validation = validation
  }
}

type FetchOptions = RequestInit & {
  skipAuthRefresh?: boolean
}

let refreshInFlight: Promise<AuthTokens> | null = null

async function parseErrorMessage(response: Response) {
  const fallback = response.statusText || 'Request failed'
  try {
    const data = await response.json()
    return data?.message || data?.detail || fallback
  } catch {
    return fallback
  }
}

async function safeJson<T>(response: Response): Promise<T> {
  const text = await response.text()
  if (!text) return {} as T
  return JSON.parse(text) as T
}

async function refreshAccessToken(): Promise<AuthTokens> {
  if (refreshInFlight) return refreshInFlight

  const refreshToken = getRefreshToken()
  if (!refreshToken) {
    throw new ApiError('No refresh token available', 401)
  }

  refreshInFlight = (async () => {
    const response = await fetch('/api/auth/refresh', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ refresh_token: refreshToken }),
    })

    if (!response.ok) {
      const message = await parseErrorMessage(response)
      throw new ApiError(message, response.status)
    }

    const data = await safeJson<{
      access_token: string
      refresh_token: string
      expires_in: number
    }>(response)

    const nextTokens: AuthTokens = {
      accessToken: data.access_token,
      refreshToken: data.refresh_token || refreshToken,
      expiresAt: Date.now() + data.expires_in * 1000,
    }

    setAuthTokens(nextTokens)
    return nextTokens
  })()

  try {
    return await refreshInFlight
  } finally {
    refreshInFlight = null
  }
}

export async function fetchJson<T>(url: string, options: FetchOptions = {}): Promise<T> {
  const { skipAuthRefresh, ...fetchOptions } = options
  const tokens = getAuthTokens()
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    ...(fetchOptions.headers as Record<string, string> || {}),
  }

  if (tokens?.accessToken) {
    headers.Authorization = `Bearer ${tokens.accessToken}`
  }

  const response = await fetch(url, { ...fetchOptions, headers })

  if (response.ok) {
    return safeJson<T>(response)
  }

  if (!skipAuthRefresh && (response.status === 401 || response.status === 403)) {
    try {
      const refreshed = await refreshAccessToken()
      const retryResponse = await fetch(url, {
        ...fetchOptions,
        headers: {
          ...headers,
          Authorization: `Bearer ${refreshed.accessToken}`,
        },
      })

      if (retryResponse.ok) {
        return safeJson<T>(retryResponse)
      }

      const retryMessage = await parseErrorMessage(retryResponse)
      throw new ApiError(retryMessage, retryResponse.status)
    } catch (error) {
      clearAuthTokens()
      throw error
    }
  }

  // Preserve structured validation errors from 422 responses
  if (response.status === 422) {
    try {
      const body = await response.json()
      if (body && Array.isArray(body.errors)) {
        const messages = body.errors.map((e: ValidationErrorItem) => e.message)
        throw new ApiError(
          messages.join('; ') || 'Validation failed',
          422,
          body as ValidationErrorBody,
        )
      }
    } catch (err) {
      if (err instanceof ApiError) throw err
    }
  }

  const message = await parseErrorMessage(response)
  throw new ApiError(message, response.status)
}
