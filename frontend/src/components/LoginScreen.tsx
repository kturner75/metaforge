import { useMemo, useState, type FormEvent } from 'react'
import type { LoginInput } from '@/hooks/useAuth'

type LoginScreenProps = {
  onLogin: (input: LoginInput) => Promise<boolean>
  isSubmitting: boolean
  error: string | null
}

export function LoginScreen({ onLogin, isSubmitting, error }: LoginScreenProps) {
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [tenantId, setTenantId] = useState('')
  const [showTenant, setShowTenant] = useState(false)

  const canSubmit = useMemo(() => email.trim() && password.trim(), [email, password])

  const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    if (!canSubmit || isSubmitting) return
    await onLogin({
      email: email.trim(),
      password,
      tenantId: showTenant ? tenantId.trim() : undefined,
    })
  }

  return (
    <div className="auth-screen">
      <div className="auth-panel">
        <div className="auth-brand">
          <div className="auth-mark">MF</div>
          <div>
            <h1>MetaForge</h1>
            <p>Metadata-driven framework</p>
          </div>
        </div>

        <form className="auth-form" onSubmit={handleSubmit}>
          <label className="auth-field">
            <span>Email</span>
            <input
              className="field-input"
              type="email"
              autoComplete="username"
              value={email}
              onChange={(event) => setEmail(event.target.value)}
              placeholder="you@company.com"
              required
            />
          </label>

          <label className="auth-field">
            <span>Password</span>
            <input
              className="field-input"
              type="password"
              autoComplete="current-password"
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              placeholder="••••••••"
              required
            />
          </label>

          <button
            type="button"
            className="auth-advanced"
            onClick={() => setShowTenant((prev) => !prev)}
          >
            {showTenant ? 'Hide tenant selection' : 'Use a specific tenant'}
          </button>

          {showTenant && (
            <label className="auth-field">
              <span>Tenant ID</span>
              <input
                className="field-input"
                type="text"
                value={tenantId}
                onChange={(event) => setTenantId(event.target.value)}
                placeholder="tenant-id"
              />
            </label>
          )}

          {error && <div className="auth-error">{error}</div>}

          <button className="primary" type="submit" disabled={!canSubmit || isSubmitting}>
            {isSubmitting ? 'Signing in…' : 'Sign in'}
          </button>
        </form>

        <div className="auth-footer">
          <span>Need access?</span>
          <span>Ask an admin to add you to a tenant.</span>
        </div>
      </div>
    </div>
  )
}
