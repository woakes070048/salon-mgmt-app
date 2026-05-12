import { useState } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { login } from '@/api/auth'
import { useAuth } from '@/store/auth'
import { Button } from '@/components/ui/button'

const API_URL = import.meta.env.VITE_API_URL ?? 'http://localhost:8000'
const SSO_ENABLED = import.meta.env.VITE_SSO_ENABLED === 'true'

const SSO_ERROR_MESSAGES: Record<string, string> = {
  state_mismatch: 'Sign-in session expired. Please try again.',
  token_exchange: 'Could not complete sign-in. Please try again.',
  userinfo: 'Could not retrieve your profile. Please try again.',
  no_email: 'Your account has no email address. Please sign in with email instead.',
  no_tenant: 'Service unavailable. Please try again later.',
  auth_failed: 'Authentication failed. Please try again.',
}

export default function LoginPage() {
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)
  const { setUser } = useAuth()
  const navigate = useNavigate()
  const { t } = useTranslation()
  const [searchParams] = useSearchParams()
  const ssoError = searchParams.get('error')

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    setError('')
    setLoading(true)
    try {
      const user = await login(email, password)
      setUser(user)
      navigate(user.role === 'guest' ? '/my-requests' : '/dashboard')
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Login failed')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="min-h-screen grid lg:grid-cols-[1.1fr_1fr]">
      {/* Left: portrait hero panel */}
      <div className="relative hidden lg:block">
        <div
          className="absolute inset-0 bg-cover bg-center"
          style={{ backgroundImage: 'url(/images/Erin.Salon.Final-5.jpg)' }}
          aria-hidden
        />
        <div className="absolute inset-0 bg-gradient-to-b from-black/20 via-black/30 to-black/60" aria-hidden />
        <div className="relative z-10 h-full flex flex-col justify-end p-10 text-white">
          <div className="space-y-4 max-w-sm">
            <p className="text-xs tracking-[0.4em] uppercase text-white/70">
              Salon Lyol · Toronto
            </p>
            <p
              className="text-3xl xl:text-4xl font-light leading-tight"
              style={{ fontFamily: 'var(--font-display)' }}
            >
              Every day can be a <em className="font-normal">good hair day.</em>
            </p>
          </div>
        </div>
      </div>

      {/* Right: sign-in form */}
      <div className="flex items-center justify-center px-6 py-12 bg-[#faf9f7]">
        <div className="w-full max-w-sm space-y-8">
          <div className="flex justify-center">
            <Link to="/">
              <img src="/salon-lyol-logo.png" alt="Salon Lyol" className="h-24 w-auto" />
            </Link>
          </div>

          <div className="space-y-2 text-center lg:text-left">
            <p className="text-xs tracking-[0.3em] uppercase text-muted-foreground">
              {t('auth.welcome_back')}
            </p>
            <h1
              className="text-3xl font-light"
              style={{ fontFamily: 'var(--font-display)' }}
            >
              {t('auth.sign_in_heading')}
            </h1>
          </div>

          {ssoError && (
            <p className="text-sm text-destructive text-center">
              {SSO_ERROR_MESSAGES[ssoError] ?? 'Sign-in failed. Please try again.'}
            </p>
          )}

          {SSO_ENABLED && (
            <div className="flex flex-col gap-3">
              <a
                href={`${API_URL}/auth/oauth/start?provider=google`}
                className="flex items-center justify-center gap-3 h-11 rounded-sm border border-input bg-white text-sm font-medium hover:bg-muted/50 transition-colors"
              >
                <svg width="18" height="18" viewBox="0 0 18 18" aria-hidden>
                  <path fill="#4285F4" d="M17.64 9.2c0-.637-.057-1.251-.164-1.84H9v3.481h4.844a4.14 4.14 0 0 1-1.796 2.716v2.259h2.908c1.702-1.567 2.684-3.875 2.684-6.615Z"/>
                  <path fill="#34A853" d="M9 18c2.43 0 4.467-.806 5.956-2.18l-2.908-2.259c-.806.54-1.837.86-3.048.86-2.344 0-4.328-1.584-5.036-3.711H.957v2.332A8.997 8.997 0 0 0 9 18Z"/>
                  <path fill="#FBBC05" d="M3.964 10.71A5.41 5.41 0 0 1 3.682 9c0-.593.102-1.17.282-1.71V4.958H.957A8.996 8.996 0 0 0 0 9c0 1.452.348 2.827.957 4.042l3.007-2.332Z"/>
                  <path fill="#EA4335" d="M9 3.58c1.321 0 2.508.454 3.44 1.345l2.582-2.58C13.463.891 11.426 0 9 0A8.997 8.997 0 0 0 .957 4.958L3.964 6.29C4.672 4.163 6.656 3.58 9 3.58Z"/>
                </svg>
                Continue with Google
              </a>
              <a
                href={`${API_URL}/auth/oauth/start?provider=apple`}
                className="flex items-center justify-center gap-3 h-11 rounded-sm border border-input bg-black text-white text-sm font-medium hover:bg-black/90 transition-colors"
              >
                <svg width="16" height="18" viewBox="0 0 814 1000" aria-hidden fill="currentColor">
                  <path d="M788.1 340.9c-5.8 4.5-108.2 62.2-108.2 190.5 0 148.4 130.3 200.9 134.2 202.2-.6 3.2-20.7 71.9-68.7 141.9-42.8 61.6-87.5 123.1-155.5 123.1s-85.5-39.5-164-39.5c-76.5 0-103.7 40.8-165.9 40.8s-105-42.5-155.5-127.4C46.7 790.7 0 663 0 541.8c0-207.8 135.4-317.9 268.5-317.9 70.7 0 129.5 46.4 173.1 46.4 42.8 0 109.9-49 188.6-49 30.1 0 108.2 2.6 168.9 80.7zm-244.7-111.9c31.1-36.9 53.1-88.1 53.1-139.3 0-7.1-.6-14.3-1.9-20.1-50.6 1.9-110.8 33.7-147.1 75.8-28.5 32.4-55.1 83.6-55.1 135.5 0 7.8 1.3 15.6 1.9 18.1 3.2.6 8.4 1.3 13.6 1.3 45.4 0 102.5-30.4 135.5-71.3z"/>
                </svg>
                Continue with Apple
              </a>
              <div className="flex items-center gap-3 py-1">
                <div className="flex-1 border-t border-input" />
                <span className="text-xs text-muted-foreground uppercase tracking-wider">or</span>
                <div className="flex-1 border-t border-input" />
              </div>
            </div>
          )}

          <form onSubmit={handleSubmit} className="flex flex-col gap-4">
            <div className="space-y-1.5">
              <label htmlFor="email" className="text-xs uppercase tracking-wider text-muted-foreground">
                {t('auth.email_label')}
              </label>
              <input
                id="email"
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                required
                className="w-full border-0 border-b border-input bg-transparent px-0 py-2 text-sm focus:outline-none focus:border-foreground transition-colors"
              />
            </div>
            <div className="space-y-1.5">
              <label htmlFor="password" className="text-xs uppercase tracking-wider text-muted-foreground">
                {t('auth.password_label')}
              </label>
              <input
                id="password"
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                required
                className="w-full border-0 border-b border-input bg-transparent px-0 py-2 text-sm focus:outline-none focus:border-foreground transition-colors"
              />
            </div>
            {error && <p className="text-sm text-destructive">{error}</p>}
            <Button
              type="submit"
              disabled={loading}
              className="mt-2 h-12 rounded-sm tracking-widest uppercase text-xs"
            >
              {loading ? t('auth.signing_in') : t('auth.sign_in')}
            </Button>
            <p className="text-center text-sm text-muted-foreground pt-2">
              {t('auth.new_client_prompt')}{' '}
              <Link to="/register" className="text-foreground underline-offset-4 hover:underline">
                {t('auth.create_account_link')}
              </Link>
            </p>
            <p className="text-center text-sm text-muted-foreground">
              <Link to="/forgot-password" className="text-foreground underline-offset-4 hover:underline">
                {t('auth.forgot_password')}
              </Link>
            </p>
          </form>
        </div>
      </div>
    </div>
  )
}
