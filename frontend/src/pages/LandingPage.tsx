import { Link } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import { getPublicTenantInfo, type PublicTenantInfo } from '@/api/settings'

function formatAddress(t: PublicTenantInfo | undefined): string | null {
  if (!t) return null
  const street = [t.address_line1, t.address_line2].filter(Boolean).join(', ')
  const city = [t.city, t.region].filter(Boolean).join(', ')
  const parts = [street, city].filter(Boolean)
  return parts.length ? parts.join(' · ') : null
}

export default function LandingPage() {
  const { t } = useTranslation()
  const { data: tenant } = useQuery({
    queryKey: ['public-tenant-info'],
    queryFn: getPublicTenantInfo,
  })

  const address = formatAddress(tenant)
  const phone = tenant?.phone

  return (
    <div className="min-h-screen relative flex flex-col text-white">
      {/* Hero background */}
      <div
        className="absolute inset-0 bg-cover bg-center pointer-events-none"
        style={{ backgroundImage: 'url(/images/1Z2A5708.webp)' }}
        aria-hidden
      />
      {/* Soft gradient overlay for legibility */}
      <div
        className="absolute inset-0 bg-gradient-to-b from-black/30 via-black/40 to-black/70 pointer-events-none"
        aria-hidden
      />

      {/* Top brand bar */}
      <header className="relative z-20 px-6 sm:px-10 py-6 flex items-center justify-between">
        <Link
          to="/login"
          className="text-xs tracking-widest uppercase font-medium text-white border border-white/50 rounded-sm px-5 py-2 hover:bg-white hover:text-neutral-900 transition-colors"
        >
          {t('landing.sign_in')}
        </Link>
        <img
          src="/salon-lyol-logo.png"
          alt="Salon Lyol"
          className="h-48 w-auto drop-shadow-md"
        />
      </header>

      {/* Main content */}
      <main className="relative z-10 flex-1 flex flex-col items-center justify-center px-6 text-center -mt-20">
        <p
          className="text-xs sm:text-sm tracking-[0.4em] uppercase text-white/70 mb-6"
        >
          {[tenant?.city, tenant?.region].filter(Boolean).join(' · ') || 'Toronto · Ontario'}
        </p>
        <h1
          className="text-5xl sm:text-7xl font-light leading-tight max-w-3xl"
          style={{ fontFamily: 'var(--font-display)' }}
        >
          Every day can be a<br />
          <em className="font-normal">good hair day.</em>
        </h1>
        <p className="mt-6 text-base sm:text-lg text-white/80 font-light max-w-md">
          {t('landing.subtitle')}
        </p>

        <div className="mt-10 flex flex-col sm:flex-row gap-3 w-full max-w-md">
          <Link
            to="/register"
            className="flex-1 inline-flex items-center justify-center rounded-sm bg-white text-neutral-900 text-sm tracking-widest uppercase font-medium px-8 py-4 hover:bg-white/90 transition-colors"
          >
            {t('landing.request_appointment')}
          </Link>
          <Link
            to="/login"
            className="sm:hidden flex-1 inline-flex items-center justify-center rounded-sm border border-white/40 text-sm tracking-widest uppercase font-medium px-8 py-4 hover:bg-white/10 transition-colors"
          >
            {t('landing.sign_in')}
          </Link>
        </div>
      </main>

      {/* Footer */}
      <footer className="relative z-10 px-6 sm:px-10 py-6 flex flex-col sm:flex-row items-center justify-between gap-2 text-xs text-white/60">
        <p className="tracking-wider">
          {address ?? tenant?.name ?? 'Salon Lyol · Toronto, ON'}
        </p>
        <div className="flex gap-4 items-center">
          {phone && <span className="tracking-wider">{phone}</span>}
          <a
            href="https://salonlyol.ca"
            className="tracking-wider hover:text-white transition-colors"
          >
            salonlyol.ca
          </a>
        </div>
      </footer>
    </div>
  )
}
