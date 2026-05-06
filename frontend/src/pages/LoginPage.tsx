import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { login } from '@/api/auth'
import { useAuth } from '@/store/auth'
import { Button } from '@/components/ui/button'

export default function LoginPage() {
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)
  const { setUser } = useAuth()
  const navigate = useNavigate()
  const { t } = useTranslation()

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
              <img src="/salon-lyol-logo.png" alt="Salon Lyol" className="h-48 w-auto" />
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
