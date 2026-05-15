import { useEffect, useState } from 'react'
import { NavLink, Outlet, useLocation, useNavigate, useSearchParams } from 'react-router-dom'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import { useAuth } from '@/store/auth'
import { useLanguage } from '@/store/language'
import {
  Home, CalendarDays, Users, ClipboardList, Settings, LogOut,
  ShieldCheck, Scissors, Vault, ShoppingBag, DollarSign, UserCog, List,
  ChevronRight, Receipt, Coins, Upload, ScrollText, User, Mail,
  PanelLeftClose, PanelLeftOpen,
} from 'lucide-react'
import { format } from 'date-fns'
import { listAllRequests } from '@/api/appointmentRequests'
import { getBranding } from '@/api/settings'
import { updateLanguagePreference } from '@/api/auth'
import { applyBranding } from '@/lib/branding'
import MiniCalendar from '@/components/MiniCalendar'
import i18n from '@/lib/i18n'

const NAV_LINK = `flex items-center gap-3 px-4 py-2.5 text-sm transition-colors rounded-none`
const ACTIVE   = `bg-muted text-foreground font-medium`
const INACTIVE = `text-muted-foreground hover:text-foreground hover:bg-muted/50`

const ICON_LINK = `flex items-center justify-center py-2.5 transition-colors rounded-none`

function navClass({ isActive }: { isActive: boolean }) {
  return `${NAV_LINK} ${isActive ? ACTIVE : INACTIVE}`
}

function iconNavClass({ isActive }: { isActive: boolean }) {
  return `${ICON_LINK} ${isActive ? ACTIVE : INACTIVE}`
}

function SubNavLink({ to, icon: Icon, label }: { to: string; icon: React.ElementType; label: string }) {
  return (
    <NavLink to={to} className={navClass}>
      <span className="w-4 flex-shrink-0" />
      <Icon size={15} className="flex-shrink-0 text-muted-foreground" />
      <span className="flex-1">{label}</span>
    </NavLink>
  )
}

function SubNavLabel({ label }: { label: string }) {
  return (
    <div className="px-4 pt-3 pb-0.5">
      <span className="text-xs font-medium uppercase tracking-wider text-muted-foreground/50">{label}</span>
    </div>
  )
}

export default function AppShell() {
  const { t } = useTranslation()
  const { user, logout } = useAuth()
  const isAdmin = user?.role === 'tenant_admin' || user?.role === 'super_admin'
  const location = useLocation()
  const navigate = useNavigate()
  const [searchParams] = useSearchParams()
  const { sessionLanguage, setSessionLanguage } = useLanguage()
  const qc = useQueryClient()

  const [sidebarOpen, setSidebarOpen] = useState(() =>
    localStorage.getItem('sidebarOpen') !== 'false'
  )

  const toggleSidebar = () => setSidebarOpen(v => {
    localStorage.setItem('sidebarOpen', String(!v))
    return !v
  })

  const isAdminRoute = (
    location.pathname.startsWith('/services') ||
    location.pathname.startsWith('/staff') ||
    location.pathname.startsWith('/retail') ||
    location.pathname.startsWith('/till') ||
    location.pathname.startsWith('/reports') ||
    location.pathname.startsWith('/users') ||
    location.pathname.startsWith('/login-log') ||
    location.pathname.startsWith('/settings') ||
    location.pathname.startsWith('/import')
  )

  const [adminOpen, setAdminOpen] = useState(false)

  const { data: pendingRequests = [] } = useQuery({
    queryKey: ['requests', 'new'],
    queryFn: () => listAllRequests('new'),
    refetchInterval: 60_000,
  })
  const pendingCount = pendingRequests.filter(r => r.source !== 'email').length
  const inboxCount = pendingRequests.filter(r => r.source === 'email').length

  const { data: branding } = useQuery({
    queryKey: ['branding'],
    queryFn: getBranding,
    staleTime: Infinity,
  })

  useEffect(() => {
    if (branding) applyBranding(branding)
  }, [branding])

  // Sync i18n to stored user preference on mount / user change
  useEffect(() => {
    const lang = user?.language_preference ?? 'en'
    if (!sessionLanguage) i18n.changeLanguage(lang)
  }, [user?.language_preference])

  // Invalidate all queries when session language changes so they refetch in the new language
  useEffect(() => {
    qc.invalidateQueries()
  }, [sessionLanguage])

  const supportedLanguages = branding?.supported_languages ?? ['en', 'fr']
  const effectiveLang = sessionLanguage ?? user?.language_preference ?? 'en'

  function toggleLanguage(lang: string) {
    i18n.changeLanguage(lang)
    setSessionLanguage(lang)
    updateLanguagePreference(lang).catch(() => {})
  }

  const TOP_NAV = [
    { to: '/dashboard',    icon: Home,          label: t('nav.home'),             badge: 0 },
    { to: '/appointments', icon: CalendarDays,  label: t('nav.appointment_book'), badge: 0 },
    { to: '/clients',      icon: Users,         label: t('nav.clients'),          badge: 0 },
    { to: '/requests',     icon: ClipboardList, label: t('nav.requests'),         badge: pendingCount },
    { to: '/inbox',        icon: Mail,          label: 'Inbox',                   badge: inboxCount },
  ]

  // Mini calendar date — read from URL if on appointment book, else today
  const isOnAppointments = location.pathname.startsWith('/appointments')
  const calendarDate = isOnAppointments
    ? (searchParams.get('date') ?? format(new Date(), 'yyyy-MM-dd'))
    : format(new Date(), 'yyyy-MM-dd')

  return (
    <div className="flex h-screen bg-muted/30">
      <nav className={`${sidebarOpen ? 'w-56' : 'w-12'} flex-shrink-0 bg-white border-r flex flex-col transition-[width] duration-200 print:hidden`}>

        {/* Logo / header */}
        {sidebarOpen ? (
          <div className="flex flex-col items-center py-5 border-b gap-2">
            <img
              src={branding?.logo_url ?? '/salon-lyol-icon.png'}
              alt={branding?.salon_name ?? 'Salon Lyol'}
              className="h-10 w-auto object-contain"
              onError={e => { e.currentTarget.src = '/salon-lyol-icon.png' }}
            />
            <span className="text-xs font-medium tracking-widest uppercase text-muted-foreground">
              {branding?.salon_name ?? 'Salon Lyol'}
            </span>
          </div>
        ) : (
          <div className="flex justify-center py-3 border-b">
            <img
              src={branding?.logo_url ?? '/salon-lyol-icon.png'}
              alt=""
              className="h-6 w-auto object-contain"
              onError={e => { e.currentTarget.src = '/salon-lyol-icon.png' }}
            />
          </div>
        )}

        {/* Nav items */}
        <div className="flex-1 py-2 overflow-auto">
          {sidebarOpen ? (
            <>
              {/* Expanded nav */}
              {TOP_NAV.map(({ to, icon: Icon, label, badge }) => (
                <NavLink key={to} to={to} className={navClass}>
                  <Icon size={16} className="flex-shrink-0" />
                  <span className="flex-1">{label}</span>
                  {badge > 0 && (
                    <span className="ml-auto bg-amber-500 text-white text-xs font-medium rounded-full px-1.5 py-0.5 min-w-[1.25rem] text-center leading-none">
                      {badge}
                    </span>
                  )}
                </NavLink>
              ))}

              {/* Admin group */}
              {isAdmin && (
                <>
                  <button
                    onClick={() => setAdminOpen(o => !o)}
                    className={`${NAV_LINK} w-full ${isAdminRoute ? ACTIVE : INACTIVE}`}
                  >
                    <ShieldCheck size={16} className="flex-shrink-0" />
                    <span className="flex-1 text-left">Admin</span>
                    <ChevronRight
                      size={14}
                      className={`flex-shrink-0 transition-transform duration-150 ${adminOpen ? 'rotate-90' : ''}`}
                    />
                  </button>
                  {adminOpen && (
                    <>
                      <SubNavLabel label={t('nav.catalog')} />
                      <SubNavLink to="/services" icon={Scissors}    label={t('nav.services')} />
                      <SubNavLink to="/retail"   icon={ShoppingBag} label={t('nav.retail')}   />

                      <SubNavLabel label={t('nav.users_group')} />
                      <SubNavLink to="/users"     icon={User}       label={t('nav.admins')}     />
                      <SubNavLink to="/staff"     icon={UserCog}    label={t('nav.staff')}      />
                      <SubNavLink to="/login-log" icon={ScrollText} label={t('nav.login_log')}  />

                      <SubNavLabel label={t('nav.finance')} />
                      <SubNavLink to="/till"               icon={Vault}      label={t('nav.till')}       />
                      <SubNavLink to="/sales"              icon={Receipt}    label="Sales"               />
                      <SubNavLink to="/reports/sales"      icon={Receipt}    label="Daily Report"        />
                      <SubNavLink to="/reports/transactions"  icon={List}       label="Transactions"            />
                      <SubNavLink to="/reports/payroll"        icon={DollarSign} label={t('nav.payroll')}        />
                      <SubNavLink to="/reports/payroll-detail" icon={List}       label="Payroll Detail"          />
                      <SubNavLink to="/reports/petty-cash"    icon={Coins}      label={t('nav.petty_cash')}     />

                      <SubNavLabel label={t('nav.settings')} />
                      <SubNavLink to="/settings" icon={Settings} label={t('nav.settings')} />
                      <SubNavLink to="/import"   icon={Upload}   label={t('nav.import')}   />
                    </>
                  )}
                </>
              )}

              {/* Settings for non-admins */}
              {!isAdmin && (
                <NavLink to="/settings" className={navClass}>
                  <Settings size={16} className="flex-shrink-0" />
                  <span className="flex-1">{t('nav.settings')}</span>
                </NavLink>
              )}
            </>
          ) : (
            <>
              {/* Collapsed — icon-only top nav */}
              {TOP_NAV.map(({ to, icon: Icon, label, badge }) => (
                <NavLink key={to} to={to} className={iconNavClass} title={label}>
                  <div className="relative">
                    <Icon size={18} />
                    {badge > 0 && (
                      <span className="absolute -top-1 -right-1 bg-amber-500 text-white text-[9px] font-bold rounded-full w-3.5 h-3.5 flex items-center justify-center leading-none">
                        {badge}
                      </span>
                    )}
                  </div>
                </NavLink>
              ))}

              {/* Admin icon — click to expand sidebar */}
              {isAdmin && (
                <button
                  onClick={toggleSidebar}
                  title="Admin"
                  className={`${ICON_LINK} w-full ${isAdminRoute ? ACTIVE : INACTIVE}`}
                >
                  <ShieldCheck size={18} />
                </button>
              )}

              {/* Settings icon */}
              {isAdmin ? (
                <button
                  onClick={toggleSidebar}
                  title="Settings"
                  className={`${ICON_LINK} w-full ${location.pathname.startsWith('/settings') ? ACTIVE : INACTIVE}`}
                >
                  <Settings size={18} />
                </button>
              ) : (
                <NavLink to="/settings" className={iconNavClass} title="Settings">
                  <Settings size={18} />
                </NavLink>
              )}
            </>
          )}
        </div>

        {/* Mini calendar — expanded sidebar only */}
        {sidebarOpen && (
          <div className="border-t">
            <MiniCalendar
              selectedDate={calendarDate}
              onDateChange={d => {
                // Preserve the ?request= param so the convert panel stays
                // mounted as the user clicks through dates.
                const params = new URLSearchParams(searchParams)
                params.set('date', d)
                navigate(`/appointments?${params.toString()}`)
              }}
            />
          </div>
        )}

        {/* Current user identity */}
        {sidebarOpen && user && (
          <div className="border-t px-3 py-2.5">
            {user.display_name && (
              <p className="text-xs font-medium text-foreground truncate">{user.display_name}</p>
            )}
            <p className="text-xs text-muted-foreground truncate">{user.email}</p>
          </div>
        )}

        {/* Footer — toggle + language + sign out */}
        <div className="border-t p-2 flex items-center justify-between gap-1">
          <button
            onClick={toggleSidebar}
            className="p-1.5 rounded text-muted-foreground hover:text-foreground hover:bg-muted/50 transition-colors"
            title={sidebarOpen ? t('nav.collapse_sidebar') : t('nav.expand_sidebar')}
          >
            {sidebarOpen ? <PanelLeftClose size={15} /> : <PanelLeftOpen size={15} />}
          </button>

          {/* Language toggle */}
          {sidebarOpen ? (
            <div className="flex items-center gap-0.5">
              {supportedLanguages.map((lang, i) => (
                <span key={lang} className="flex items-center gap-0.5">
                  {i > 0 && <span className="text-muted-foreground/40 text-xs">·</span>}
                  <button
                    onClick={() => toggleLanguage(lang)}
                    className={`px-1.5 py-0.5 rounded text-xs transition-colors ${
                      effectiveLang === lang
                        ? 'font-semibold text-foreground'
                        : 'text-muted-foreground hover:text-foreground'
                    }`}
                    title={`Switch to ${lang.toUpperCase()}`}
                  >
                    {lang.toUpperCase()}
                  </button>
                </span>
              ))}
            </div>
          ) : (
            <button
              onClick={() => {
                const next = supportedLanguages[(supportedLanguages.indexOf(effectiveLang) + 1) % supportedLanguages.length]
                toggleLanguage(next)
              }}
              className="p-1 rounded text-xs font-semibold text-muted-foreground hover:text-foreground hover:bg-muted/50 transition-colors"
              title={`Language: ${effectiveLang.toUpperCase()}`}
            >
              {effectiveLang.toUpperCase()}
            </button>
          )}

          {sidebarOpen ? (
            <button
              onClick={logout}
              className="flex items-center gap-2 px-2 py-1.5 text-sm text-muted-foreground hover:text-foreground rounded-md hover:bg-muted/50 transition-colors"
            >
              <LogOut size={15} />
              {t('nav.sign_out')}
            </button>
          ) : (
            <button
              onClick={logout}
              className="p-1.5 rounded text-muted-foreground hover:text-foreground hover:bg-muted/50 transition-colors"
              title={t('nav.sign_out')}
            >
              <LogOut size={15} />
            </button>
          )}
        </div>
      </nav>

      <div className="flex-1 min-w-0 overflow-hidden">
        <Outlet />
      </div>
    </div>
  )
}
