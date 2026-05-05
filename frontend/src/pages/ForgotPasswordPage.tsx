import { useState } from 'react'
import { Link } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { requestReset } from '@/api/auth'
import { Button } from '@/components/ui/button'

export default function ForgotPasswordPage() {
  const { t } = useTranslation()
  const [email, setEmail] = useState('')
  const [loading, setLoading] = useState(false)
  const [done, setDone] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const fieldClass =
    'w-full border-0 border-b border-input bg-transparent px-0 py-2 text-sm focus:outline-none focus:border-foreground transition-colors'
  const labelClass = 'text-xs uppercase tracking-wider text-muted-foreground'

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    setError(null)
    setLoading(true)
    try {
      await requestReset(email)
      setDone(true)
    } catch (err: unknown) {
      setError((err as Error).message ?? 'Something went wrong')
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
        <div className="relative z-10 h-full flex flex-col justify-between p-10 text-white">
          <Link to="/" className="inline-block">
            <img src="/salon-lyol-logo.png" alt="Salon Lyol" className="h-9 w-auto" />
          </Link>
          <div className="space-y-4 max-w-sm">
            <p className="text-xs tracking-[0.4em] uppercase text-white/70">Salon Lyol · Toronto</p>
            <p
              className="text-3xl xl:text-4xl font-light leading-tight"
              style={{ fontFamily: 'var(--font-display)' }}
            >
              Every day can be a <em className="font-normal">good hair day.</em>
            </p>
          </div>
        </div>
      </div>

      {/* Right: form */}
      <div className="flex items-center justify-center px-6 py-12 bg-[#faf9f7]">
        <div className="w-full max-w-sm space-y-8">
          <div className="flex justify-center lg:hidden">
            <img src="/salon-lyol-logo.png" alt="Salon Lyol" className="h-12 w-auto" />
          </div>

          {done ? (
            <div className="text-center space-y-4">
              <p className="text-xs tracking-[0.3em] uppercase text-muted-foreground">
                {t('auth.forgot_sent_eyebrow')}
              </p>
              <h1 className="text-3xl font-light" style={{ fontFamily: 'var(--font-display)' }}>
                {t('auth.forgot_sent_heading')}
              </h1>
              <p className="text-sm text-muted-foreground">{t('auth.forgot_sent_message')}</p>
              <Button
                variant="outline"
                onClick={() => window.location.href = '/login'}
                className="h-12 rounded-sm tracking-widest uppercase text-xs"
              >
                {t('auth.back_to_sign_in')}
              </Button>
            </div>
          ) : (
            <>
              <div className="space-y-2 text-center lg:text-left">
                <p className="text-xs tracking-[0.3em] uppercase text-muted-foreground">
                  {t('auth.forgot_eyebrow')}
                </p>
                <h1 className="text-3xl font-light" style={{ fontFamily: 'var(--font-display)' }}>
                  {t('auth.forgot_heading')}
                </h1>
                <p className="text-sm text-muted-foreground">{t('auth.forgot_subheading')}</p>
              </div>

              <form onSubmit={handleSubmit} className="flex flex-col gap-4">
                <div className="space-y-1">
                  <label htmlFor="email" className={labelClass}>{t('auth.email_label')}</label>
                  <input
                    id="email"
                    type="email"
                    value={email}
                    onChange={e => setEmail(e.target.value)}
                    required
                    className={fieldClass}
                  />
                </div>
                {error && <p className="text-sm text-destructive">{error}</p>}
                <Button
                  type="submit"
                  disabled={loading}
                  className="mt-2 h-12 rounded-sm tracking-widest uppercase text-xs"
                >
                  {loading ? t('auth.forgot_sending') : t('auth.forgot_submit')}
                </Button>
                <p className="text-center text-sm text-muted-foreground">
                  <Link to="/login" className="text-foreground underline-offset-4 hover:underline">
                    {t('auth.back_to_sign_in')}
                  </Link>
                </p>
              </form>
            </>
          )}
        </div>
      </div>
    </div>
  )
}
