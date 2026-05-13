import { useState, useEffect } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Save } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import {
  getBranding,
  updateBranding,
  type BrandingSettings,
  type ContactDetails,
  type SlotMinutes,
  type TimeFormat,
  SLOT_OPTIONS,
  getOperatingHours,
  updateOperatingHours,
  type OperatingHoursDay,
  getRequestNotifications,
  updateRequestNotifications,
  getPrinterConfig,
  updatePrinterConfig,
  uploadPrinterLogo,
  type PrinterConfig,
} from '@/api/settings'
import { getEmailConfig, saveEmailConfig, testEmailConfig, getPayrollConfig, savePayrollConfig } from '@/api/admin'
import { changePassword } from '@/api/auth'
import {
  listPaymentMethods,
  createPaymentMethod,
  updatePaymentMethod,
  KIND_OPTIONS,
  type PaymentMethod,
  type PaymentMethodKind,
} from '@/api/paymentMethods'
import { listPromotions, createPromotion, updatePromotion, type PromotionKind } from '@/api/promotions'
import { useAuth } from '@/store/auth'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { applyBranding } from '@/lib/branding'

export default function SettingsPage() {
  const { t } = useTranslation()
  const qc = useQueryClient()
  const { user } = useAuth()
  const isAdmin = user?.role === 'tenant_admin' || user?.role === 'super_admin'

  const { data: branding, isLoading } = useQuery({
    queryKey: ['branding'],
    queryFn: getBranding,
  })

  const [salonName, setSalonName] = useState('')
  const [logoUrl, setLogoUrl] = useState('')
  const [brandColor, setBrandColor] = useState('#18181b')
  const [slotMinutes, setSlotMinutes] = useState<SlotMinutes>(10)
  const [timeFormat, setTimeFormat] = useState<TimeFormat>('12h')
  const EMPTY_CONTACT: ContactDetails = {
    address_line1: null, address_line2: null, city: null, region: null,
    postal_code: null, country: null, phone: null, hours_summary: null,
  }
  const [contact, setContact] = useState<ContactDetails>(EMPTY_CONTACT)

  useEffect(() => {
    if (branding) {
      setSalonName(branding.salon_name ?? '')
      setLogoUrl(branding.logo_url ?? '')
      setBrandColor(branding.brand_color ?? '#18181b')
      setSlotMinutes((branding.slot_minutes ?? 10) as SlotMinutes)
      setTimeFormat(branding.time_format ?? '12h')
      setContact({
        address_line1: branding.address_line1,
        address_line2: branding.address_line2,
        city: branding.city,
        region: branding.region,
        postal_code: branding.postal_code,
        country: branding.country,
        phone: branding.phone,
        hours_summary: branding.hours_summary,
      })
    }
  }, [branding])

  function setContactField<K extends keyof ContactDetails>(field: K, value: string) {
    setContact(prev => ({ ...prev, [field]: value || null }))
  }

  const brandingMutation = useMutation({
    mutationFn: () => updateBranding({
      salon_name: salonName.trim() || undefined,
      logo_url: logoUrl || null,
      brand_color: brandColor,
      slot_minutes: slotMinutes,
      time_format: timeFormat,
      ...contact,
    }),
    onSuccess: (updated: BrandingSettings) => {
      qc.setQueryData(['branding'], updated)
      qc.invalidateQueries({ queryKey: ['public-tenant-info'] })
      applyBranding(updated)
    },
  })

  const [tab, setTab] = useState<'branding' | 'scheduling' | 'payment-methods' | 'promotions' | 'email' | 'payroll' | 'printer' | 'account'>('branding')

  if (isLoading) return <div className="p-6 text-sm text-muted-foreground">{t('common.loading')}</div>

  const tabs = [
    { id: 'branding', label: t('settings.tab_branding') },
    { id: 'scheduling', label: t('settings.tab_scheduling') },
    ...(isAdmin ? [{ id: 'payment-methods', label: t('settings.tab_payment_methods') }] : []),
    ...(isAdmin ? [{ id: 'promotions', label: t('settings.tab_promotions') }] : []),
    ...(isAdmin ? [{ id: 'email', label: t('settings.tab_email') }] : []),
    ...(isAdmin ? [{ id: 'payroll', label: t('settings.tab_payroll') }] : []),
    ...(isAdmin ? [{ id: 'printer', label: 'Printer' }] : []),
    { id: 'account', label: t('settings.tab_account') },
  ] as const

  return (
    <div className="h-full overflow-auto bg-muted/30">
      <div className="max-w-2xl mx-auto px-6 py-8 space-y-6">
        <div>
          <h1 className="text-xl font-semibold">{t('settings.page_title')}</h1>
          <p className="text-sm text-muted-foreground mt-1">{t('settings.page_subtitle')}</p>
        </div>

        {/* Tabs */}
        <div className="flex border-b">
          {tabs.map(tabItem => (
            <button
              key={tabItem.id}
              onClick={() => setTab(tabItem.id as typeof tab)}
              className={`px-4 py-2 text-sm border-b-2 -mb-px transition-colors ${
                tab === tabItem.id
                  ? 'border-foreground font-medium'
                  : 'border-transparent text-muted-foreground hover:text-foreground'
              }`}
            >
              {tabItem.label}
            </button>
          ))}
        </div>

        {/* Branding tab */}
        {tab === 'branding' && (
          <section className="border rounded-lg p-5 space-y-5 bg-white">
            <div className="space-y-2">
              <label className="text-sm font-medium">{t('settings.salon_name')}</label>
              <input
                type="text"
                value={salonName}
                onChange={e => setSalonName(e.target.value)}
                placeholder="Salon Lyol"
                className="w-full border border-input rounded-md px-3 py-2 text-sm bg-background"
              />
            </div>
            <div className="space-y-2">
              <label className="text-sm font-medium">{t('settings.logo_url')}</label>
              <input
                type="url"
                value={logoUrl}
                onChange={e => setLogoUrl(e.target.value)}
                placeholder={t('settings.logo_url_placeholder')}
                className="w-full border border-input rounded-md px-3 py-2 text-sm bg-background"
              />
              <p className="text-xs text-muted-foreground">
                {t('settings.logo_help')}
              </p>
              {logoUrl && (
                <div className="flex items-center gap-4 pt-1">
                  <img
                    src={logoUrl}
                    alt="Logo preview"
                    className="h-12 w-auto object-contain border rounded p-1 bg-muted/30"
                    onError={e => (e.currentTarget.style.display = 'none')}
                  />
                  <span className="text-xs text-muted-foreground">{t('settings.preview_button')}</span>
                </div>
              )}
            </div>

            <div className="space-y-2">
              <label className="text-sm font-medium">{t('settings.brand_colour')}</label>
              <div className="flex items-center gap-3">
                <input
                  type="color"
                  value={brandColor}
                  onChange={e => setBrandColor(e.target.value)}
                  className="h-9 w-16 cursor-pointer rounded border border-input p-0.5 bg-background"
                />
                <input
                  type="text"
                  value={brandColor}
                  onChange={e => {
                    const v = e.target.value
                    if (/^#[0-9a-fA-F]{0,6}$/.test(v)) setBrandColor(v)
                  }}
                  className="w-28 border border-input rounded-md px-3 py-2 text-sm bg-background font-mono"
                  maxLength={7}
                />
                <div
                  className="h-9 w-24 rounded border border-input text-xs flex items-center justify-center font-medium"
                  style={{ backgroundColor: brandColor.length === 7 ? brandColor : undefined }}
                >
                  <span style={{ color: colorIsDark(brandColor) ? '#fff' : '#000' }}>Button</span>
                </div>
              </div>
              <p className="text-xs text-muted-foreground">{t('settings.brand_colour_help')}</p>
            </div>

            <div className="space-y-3 border-t pt-5">
              <div>
                <h2 className="text-sm font-medium">{t('settings.contact_section')}</h2>
                <p className="text-xs text-muted-foreground mt-0.5">
                  {t('settings.contact_help')}
                </p>
              </div>

              <div className="space-y-2">
                <label className="text-xs uppercase tracking-wider text-muted-foreground">{t('settings.address_label')}</label>
                <input
                  type="text"
                  value={contact.address_line1 ?? ''}
                  onChange={e => setContactField('address_line1', e.target.value)}
                  placeholder={t('settings.street_placeholder')}
                  className="w-full border border-input rounded-md px-3 py-2 text-sm bg-background"
                />
                <input
                  type="text"
                  value={contact.address_line2 ?? ''}
                  onChange={e => setContactField('address_line2', e.target.value)}
                  placeholder={t('settings.suite_label')}
                  className="w-full border border-input rounded-md px-3 py-2 text-sm bg-background"
                />
                <div className="grid grid-cols-3 gap-2">
                  <input
                    type="text"
                    value={contact.city ?? ''}
                    onChange={e => setContactField('city', e.target.value)}
                    placeholder={t('settings.city_label')}
                    className="border border-input rounded-md px-3 py-2 text-sm bg-background"
                  />
                  <input
                    type="text"
                    value={contact.region ?? ''}
                    onChange={e => setContactField('region', e.target.value)}
                    placeholder={t('settings.province_label')}
                    className="border border-input rounded-md px-3 py-2 text-sm bg-background"
                  />
                  <input
                    type="text"
                    value={contact.postal_code ?? ''}
                    onChange={e => setContactField('postal_code', e.target.value)}
                    placeholder={t('settings.postal_label')}
                    className="border border-input rounded-md px-3 py-2 text-sm bg-background"
                  />
                </div>
                <input
                  type="text"
                  value={contact.country ?? ''}
                  onChange={e => setContactField('country', e.target.value.toUpperCase().slice(0, 2))}
                  placeholder={t('settings.country_label')}
                  maxLength={2}
                  className="w-24 border border-input rounded-md px-3 py-2 text-sm bg-background uppercase"
                />
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div className="space-y-1">
                  <label className="text-xs uppercase tracking-wider text-muted-foreground">{t('settings.phone_label')}</label>
                  <input
                    type="tel"
                    value={contact.phone ?? ''}
                    onChange={e => setContactField('phone', e.target.value)}
                    placeholder="416-555-0100"
                    className="w-full border border-input rounded-md px-3 py-2 text-sm bg-background"
                  />
                </div>
                <div className="space-y-1">
                  <label className="text-xs uppercase tracking-wider text-muted-foreground">{t('settings.hours_summary')}</label>
                  <input
                    type="text"
                    value={contact.hours_summary ?? ''}
                    onChange={e => setContactField('hours_summary', e.target.value)}
                    placeholder={t('settings.hours_format')}
                    className="w-full border border-input rounded-md px-3 py-2 text-sm bg-background"
                  />
                </div>
              </div>
            </div>

            {brandingMutation.isError && (
              <p className="text-xs text-destructive">
                {brandingMutation.error instanceof Error ? brandingMutation.error.message : 'Save failed'}
              </p>
            )}

            <Button onClick={() => brandingMutation.mutate()} disabled={brandingMutation.isPending}>
              <Save size={14} className="mr-1.5" />
              {brandingMutation.isPending ? t('common.saving') : t('common.save')}
            </Button>
          </section>
        )}

        {/* Scheduling tab */}
        {tab === 'scheduling' && (
          <>
            <OperatingHoursSection isAdmin={isAdmin} />
            <section className="border rounded-lg p-5 space-y-5 bg-white">
              <div className="space-y-2">
                <label className="text-sm font-medium">{t('settings.granularity_label')}</label>
                <div className="flex gap-2">
                  {SLOT_OPTIONS.map(opt => (
                    <button
                      key={opt}
                      type="button"
                      onClick={() => setSlotMinutes(opt)}
                      className={`px-3 py-1.5 rounded-md border text-sm transition-colors ${
                        slotMinutes === opt
                          ? 'bg-primary text-primary-foreground border-primary'
                          : 'border-input bg-background hover:bg-muted/50'
                      }`}
                    >
                      {t('settings.granularity_format', { minutes: opt })}
                    </button>
                  ))}
                </div>
                <p className="text-xs text-muted-foreground">
                  {t('settings.granularity_help')}
                </p>
              </div>

              <div className="space-y-2">
                <label className="text-sm font-medium">{t('settings.time_format_label')}</label>
                <div className="flex gap-2">
                  {(['12h', '24h'] as TimeFormat[]).map(opt => (
                    <button
                      key={opt}
                      type="button"
                      onClick={() => setTimeFormat(opt)}
                      className={`px-3 py-1.5 rounded-md border text-sm transition-colors ${
                        timeFormat === opt
                          ? 'bg-primary text-primary-foreground border-primary'
                          : 'border-input bg-background hover:bg-muted/50'
                      }`}
                    >
                      {opt === '12h' ? t('settings.time_format_12') : t('settings.time_format_24')}
                    </button>
                  ))}
                </div>
                <p className="text-xs text-muted-foreground">
                  {t('settings.time_format_help')}
                </p>
              </div>

              {brandingMutation.isError && (
                <p className="text-xs text-destructive">
                  {brandingMutation.error instanceof Error ? brandingMutation.error.message : 'Save failed'}
                </p>
              )}

              <Button onClick={() => brandingMutation.mutate()} disabled={brandingMutation.isPending}>
                <Save size={14} className="mr-1.5" />
                {brandingMutation.isPending ? t('common.saving') : t('common.save')}
              </Button>
            </section>
          </>
        )}

        {/* Payment methods tab — admin only */}
        {tab === 'payment-methods' && isAdmin && <PaymentMethodsSection />}

        {/* Promotions tab — admin only */}
        {tab === 'promotions' && isAdmin && <PromotionsSection />}

        {/* Email tab — admin only */}
        {tab === 'email' && isAdmin && (
          <>
            <EmailSection />
            <RequestNotificationsSection />
            <RemindersSection />
          </>
        )}

        {/* Payroll tab — admin only */}
        {tab === 'payroll' && isAdmin && <PayrollSection />}

        {/* Account tab — all users */}
        {tab === 'printer' && isAdmin && <PrinterSection />}

        {tab === 'account' && <ChangePasswordSection />}
      </div>
    </div>
  )
}

function OperatingHoursSection({ isAdmin }: { isAdmin: boolean }) {
  const { t } = useTranslation()
  const DAY_LABELS = [
    t('settings.day_monday'),
    t('settings.day_tuesday'),
    t('settings.day_wednesday'),
    t('settings.day_thursday'),
    t('settings.day_friday'),
    t('settings.day_saturday'),
    t('settings.day_sunday'),
  ]
  const qc = useQueryClient()
  const { data, isLoading } = useQuery({
    queryKey: ['operating-hours'],
    queryFn: getOperatingHours,
  })

  const [days, setDays] = useState<OperatingHoursDay[]>([])
  const [dirty, setDirty] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (data) {
      setDays(data.map(d => ({ ...d })))
      setDirty(false)
    }
  }, [data])

  function update(dow: number, patch: Partial<OperatingHoursDay>) {
    setDays(prev => prev.map(d => d.day_of_week === dow ? { ...d, ...patch } : d))
    setDirty(true)
    setError(null)
  }

  function toggleOpen(dow: number, open: boolean) {
    if (open) {
      update(dow, { is_open: true, open_time: '09:00', close_time: '18:00' })
    } else {
      update(dow, { is_open: false, open_time: null, close_time: null })
    }
  }

  const mutation = useMutation({
    mutationFn: () => updateOperatingHours(days),
    onSuccess: updated => {
      qc.setQueryData(['operating-hours'], updated)
      setDirty(false)
      setError(null)
    },
    onError: (e: unknown) => setError(e instanceof Error ? e.message : 'Save failed'),
  })

  if (isLoading) return null

  return (
    <section className="border rounded-lg p-5 space-y-4 bg-white">
      <div>
        <h2 className="text-base font-medium">{t('settings.operating_hours')}</h2>
        <p className="text-xs text-muted-foreground mt-0.5">
          {t('settings.operating_hours_help')}
        </p>
      </div>

      <div className="space-y-1.5">
        {days.map(d => (
          <div key={d.day_of_week} className="flex items-center gap-3 text-sm">
            <label className="flex items-center gap-2 w-32 cursor-pointer">
              <input
                type="checkbox"
                checked={d.is_open}
                onChange={e => toggleOpen(d.day_of_week, e.target.checked)}
                disabled={!isAdmin}
                className="accent-primary"
              />
              <span>{DAY_LABELS[d.day_of_week]}</span>
            </label>
            {d.is_open ? (
              <div className="flex items-center gap-1.5">
                <input
                  type="time"
                  value={d.open_time ?? ''}
                  onChange={e => update(d.day_of_week, { open_time: e.target.value })}
                  disabled={!isAdmin}
                  className="border border-input rounded px-2 py-1 text-sm bg-background w-[120px]"
                />
                <span className="text-xs text-muted-foreground">–</span>
                <input
                  type="time"
                  value={d.close_time ?? ''}
                  onChange={e => update(d.day_of_week, { close_time: e.target.value })}
                  disabled={!isAdmin}
                  className="border border-input rounded px-2 py-1 text-sm bg-background w-[120px]"
                />
              </div>
            ) : (
              <span className="text-xs text-muted-foreground">{t('settings.day_closed')}</span>
            )}
          </div>
        ))}
      </div>

      {error && <p className="text-xs text-destructive">{error}</p>}

      {isAdmin && (
        <Button onClick={() => mutation.mutate()} disabled={!dirty || mutation.isPending}>
          <Save size={14} className="mr-1.5" />
          {mutation.isPending ? t('common.saving') : t('common.save')}
        </Button>
      )}
    </section>
  )
}

function PaymentMethodsSection() {
  const { t } = useTranslation()
  const qc = useQueryClient()
  const { data: methods = [], isLoading } = useQuery({
    queryKey: ['payment-methods'],
    queryFn: () => listPaymentMethods(false),
  })

  const [showNew, setShowNew] = useState(false)

  if (isLoading) return <p className="text-sm text-muted-foreground">{t('common.loading')}</p>

  return (
    <section className="border rounded-lg p-5 space-y-4 bg-white">
      <div>
        <h2 className="text-base font-medium">{t('settings.payment_methods_section')}</h2>
        <p className="text-xs text-muted-foreground mt-0.5">
          {t('settings.payment_methods_help')}
        </p>
      </div>

      <div className="space-y-2">
        {methods.length === 0 && (
          <p className="text-sm text-muted-foreground italic">{t('settings.no_payment_methods')}</p>
        )}
        {methods.map(m => (
          <PaymentMethodRow key={m.id} method={m} onSaved={() => qc.invalidateQueries({ queryKey: ['payment-methods'] })} />
        ))}
      </div>

      {showNew ? (
        <NewPaymentMethodForm
          onCancel={() => setShowNew(false)}
          onSaved={() => { setShowNew(false); qc.invalidateQueries({ queryKey: ['payment-methods'] }) }}
        />
      ) : (
        <Button variant="outline" size="sm" onClick={() => setShowNew(true)}>
          {t('settings.add_method')}
        </Button>
      )}
    </section>
  )
}

function PaymentMethodRow({ method, onSaved }: { method: PaymentMethod; onSaved: () => void }) {
  const { t } = useTranslation()
  const [label, setLabel] = useState(method.label)
  const [code, setCode] = useState(method.code)
  const [kind, setKind] = useState<PaymentMethodKind>(method.kind)
  const [isActive, setIsActive] = useState(method.is_active)
  const [error, setError] = useState<string | null>(null)

  const dirty =
    label !== method.label ||
    code !== method.code ||
    kind !== method.kind ||
    isActive !== method.is_active

  const mutation = useMutation({
    mutationFn: () => updatePaymentMethod(method.id, {
      label,
      code,
      kind,
      is_active: isActive,
    }),
    onSuccess: () => { setError(null); onSaved() },
    onError: (e: unknown) => setError(e instanceof Error ? e.message : 'Save failed'),
  })

  return (
    <div className={`border rounded-md px-3 py-2.5 grid grid-cols-12 gap-2 items-center ${!isActive ? 'opacity-60' : ''}`}>
      <input
        value={label}
        onChange={e => setLabel(e.target.value)}
        className="col-span-4 border border-input rounded px-2 py-1 text-sm bg-background"
        placeholder={t('settings.col_label')}
      />
      <input
        value={code}
        onChange={e => setCode(e.target.value.toLowerCase().replace(/[^a-z0-9_]/g, ''))}
        className="col-span-2 border border-input rounded px-2 py-1 text-sm bg-background font-mono"
        placeholder={t('settings.col_code')}
      />
      <select
        value={kind}
        onChange={e => setKind(e.target.value as PaymentMethodKind)}
        className="col-span-2 border border-input rounded px-2 py-1 text-sm bg-background"
      >
        {KIND_OPTIONS.map(opt => (
          <option key={opt.value} value={opt.value}>{opt.label}</option>
        ))}
      </select>
      <label className="col-span-2 flex items-center gap-1.5 text-xs text-muted-foreground">
        <input
          type="checkbox"
          checked={isActive}
          onChange={e => setIsActive(e.target.checked)}
          className="h-3.5 w-3.5"
        />
        {t('settings.col_active')}
      </label>
      <Button
        size="sm"
        variant="outline"
        className="col-span-2"
        disabled={!dirty || mutation.isPending}
        onClick={() => mutation.mutate()}
      >
        {mutation.isPending ? t('common.saving') : t('common.save')}
      </Button>
      {error && <p className="col-span-12 text-xs text-destructive">{error}</p>}
    </div>
  )
}

function NewPaymentMethodForm({ onCancel, onSaved }: { onCancel: () => void; onSaved: () => void }) {
  const { t } = useTranslation()
  const [label, setLabel] = useState('')
  const [code, setCode] = useState('')
  const [kind, setKind] = useState<PaymentMethodKind>('card')
  const [error, setError] = useState<string | null>(null)

  const mutation = useMutation({
    mutationFn: () => createPaymentMethod({ label, code, kind }),
    onSuccess: () => { setError(null); onSaved() },
    onError: (e: unknown) => setError(e instanceof Error ? e.message : 'Failed to add'),
  })

  function submit() {
    if (!label.trim()) { setError('Label required'); return }
    if (!code.trim()) { setError('Code required'); return }
    setError(null)
    mutation.mutate()
  }

  return (
    <div className="border border-dashed rounded-md px-3 py-3 space-y-2 bg-muted/20">
      <p className="text-xs font-medium text-muted-foreground">{t('settings.new_method_title')}</p>
      <div className="grid grid-cols-12 gap-2 items-center">
        <input
          value={label}
          onChange={e => {
            setLabel(e.target.value)
            if (!code) setCode(e.target.value.toLowerCase().replace(/[^a-z0-9]/g, '_'))
          }}
          placeholder={t('settings.method_label_placeholder')}
          className="col-span-4 border border-input rounded px-2 py-1 text-sm bg-background"
        />
        <input
          value={code}
          onChange={e => setCode(e.target.value.toLowerCase().replace(/[^a-z0-9_]/g, ''))}
          placeholder={t('settings.col_code')}
          className="col-span-3 border border-input rounded px-2 py-1 text-sm bg-background font-mono"
        />
        <select
          value={kind}
          onChange={e => setKind(e.target.value as PaymentMethodKind)}
          className="col-span-3 border border-input rounded px-2 py-1 text-sm bg-background"
        >
          {KIND_OPTIONS.map(opt => (
            <option key={opt.value} value={opt.value}>{opt.label}</option>
          ))}
        </select>
        <Button size="sm" className="col-span-1" onClick={submit} disabled={mutation.isPending}>
          {mutation.isPending ? '…' : t('common.add')}
        </Button>
        <Button size="sm" variant="ghost" className="col-span-1" onClick={onCancel}>
          {t('common.cancel')}
        </Button>
      </div>
      {error && <p className="text-xs text-destructive">{error}</p>}
    </div>
  )
}

function PromotionsSection() {
  const { t } = useTranslation()
  const qc = useQueryClient()
  const [adding, setAdding] = useState(false)
  const [newCode, setNewCode] = useState('')
  const [newLabel, setNewLabel] = useState('')
  const [newKind, setNewKind] = useState<PromotionKind>('percent')
  const [newValue, setNewValue] = useState('')
  const [formError, setFormError] = useState<string | null>(null)

  const { data: promos = [], isLoading } = useQuery({
    queryKey: ['promotions'],
    queryFn: () => listPromotions(false),
  })

  const createMutation = useMutation({
    mutationFn: () => createPromotion({
      code: newCode.trim(), label: newLabel.trim(),
      kind: newKind, value: newValue,
    }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['promotions'] })
      setAdding(false)
      setNewCode(''); setNewLabel(''); setNewValue(''); setFormError(null)
    },
    onError: (e: Error) => setFormError(e.message),
  })

  const toggleMutation = useMutation({
    mutationFn: ({ id, is_active }: { id: string; is_active: boolean }) =>
      updatePromotion(id, { is_active }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['promotions'] }),
  })

  function handleAdd(e: React.FormEvent) {
    e.preventDefault()
    setFormError(null)
    if (!newCode.trim() || !newLabel.trim() || !newValue) {
      setFormError('All fields required')
      return
    }
    createMutation.mutate()
  }

  return (
    <section className="border rounded-lg bg-white overflow-hidden">
      <div className="px-5 py-3 border-b bg-muted/30 flex items-center justify-between">
        <h2 className="text-sm font-medium">{t('settings.promotions_section')}</h2>
        {!adding && (
          <Button size="sm" variant="outline" onClick={() => setAdding(true)}>{t('settings.add_promotion')}</Button>
        )}
      </div>
      <div className="p-5 space-y-4">
        {isLoading ? (
          <p className="text-sm text-muted-foreground">{t('common.loading')}</p>
        ) : promos.length === 0 && !adding ? (
          <p className="text-sm text-muted-foreground">{t('settings.no_promotions')}</p>
        ) : (
          <ul className="space-y-2">
            {promos.map(p => (
              <li key={p.id} className={`flex items-center justify-between rounded-md border px-3 py-2 text-sm ${!p.is_active ? 'opacity-50' : ''}`}>
                <div>
                  <span className="font-medium">{p.label}</span>
                  <span className="text-xs text-muted-foreground ml-2">
                    {p.kind === 'percent' ? `${p.value}% off` : `$${p.value} off`} · code: {p.code}
                  </span>
                </div>
                <button
                  onClick={() => toggleMutation.mutate({ id: p.id, is_active: !p.is_active })}
                  className="text-xs text-muted-foreground hover:text-foreground"
                >
                  {p.is_active ? t('settings.deactivate') : t('settings.activate')}
                </button>
              </li>
            ))}
          </ul>
        )}

        {adding && (
          <form onSubmit={handleAdd} className="space-y-3 border rounded-md p-3 bg-muted/20">
            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-1">
                <Label className="text-xs">{t('settings.promotion_label')}</Label>
                <Input value={newLabel} onChange={e => setNewLabel(e.target.value)} placeholder={t('settings.promotion_label_placeholder')} />
              </div>
              <div className="space-y-1">
                <Label className="text-xs">{t('common.code')}</Label>
                <Input value={newCode} onChange={e => setNewCode(e.target.value)} placeholder={t('settings.promotion_code_placeholder')} />
              </div>
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-1">
                <Label className="text-xs">{t('settings.promotion_type')}</Label>
                <select
                  value={newKind}
                  onChange={e => setNewKind(e.target.value as PromotionKind)}
                  className="w-full border border-input rounded-md px-2 py-1.5 text-sm bg-background"
                >
                  <option value="percent">{t('settings.type_percent')}</option>
                  <option value="amount">{t('settings.type_fixed')}</option>
                </select>
              </div>
              <div className="space-y-1">
                <Label className="text-xs">{t('settings.promotion_value')}</Label>
                <Input
                  type="text"
                  inputMode="decimal"
                  value={newValue}
                  onChange={e => setNewValue(e.target.value)}
                  placeholder={newKind === 'percent' ? '10' : '5.00'}
                />
              </div>
            </div>
            {formError && <p className="text-xs text-destructive">{formError}</p>}
            <div className="flex gap-2">
              <Button type="submit" size="sm" disabled={createMutation.isPending}>
                {createMutation.isPending ? t('common.saving') : t('common.save')}
              </Button>
              <Button type="button" size="sm" variant="outline" onClick={() => { setAdding(false); setFormError(null) }}>
                {t('common.cancel')}
              </Button>
            </div>
          </form>
        )}
      </div>
    </section>
  )
}

function EmailSection() {
  const { t } = useTranslation()
  const qc = useQueryClient()

  const { data: cfg, isLoading } = useQuery({
    queryKey: ['email-config'],
    queryFn: getEmailConfig,
  })

  const [sendMode, setSendMode] = useState<'smtp' | 'resend_api'>('resend_api')
  // Resend API fields
  const [resendApiKey, setResendApiKey] = useState('')
  // SMTP fields
  const [host, setHost] = useState('')
  const [port, setPort] = useState('587')
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [useTls, setUseTls] = useState(true)
  // Shared
  const [fromAddress, setFromAddress] = useState('')
  const [accountingFromAddress, setAccountingFromAddress] = useState('')
  const [testTo, setTestTo] = useState('')
  const [saveMsg, setSaveMsg] = useState<string | null>(null)
  const [testMsg, setTestMsg] = useState<string | null>(null)

  useEffect(() => {
    if (cfg?.is_configured) {
      setSendMode(cfg.send_mode)
      setHost(cfg.smtp_host)
      setPort(String(cfg.smtp_port))
      setUsername(cfg.smtp_username)
      setUseTls(cfg.smtp_use_tls)
      setFromAddress(cfg.from_address)
      setAccountingFromAddress(cfg.accounting_from_address ?? '')
    }
  }, [cfg])

  const saveMutation = useMutation({
    mutationFn: () => saveEmailConfig(
      sendMode === 'resend_api'
        ? {
            send_mode: 'resend_api',
            resend_api_key: resendApiKey || undefined,
            from_address: fromAddress.trim(),
            accounting_from_address: accountingFromAddress.trim() || null,
          }
        : {
            send_mode: 'smtp',
            smtp_host: host.trim(),
            smtp_port: parseInt(port, 10),
            smtp_username: username.trim(),
            smtp_password: password || undefined,
            smtp_use_tls: useTls,
            from_address: fromAddress.trim(),
            accounting_from_address: accountingFromAddress.trim() || null,
          }
    ),
    onSuccess: updated => {
      qc.setQueryData(['email-config'], updated)
      setResendApiKey('')
      setPassword('')
      setSaveMsg(t('settings.status_saved'))
      setTimeout(() => setSaveMsg(null), 3000)
    },
    onError: (err: unknown) => setSaveMsg((err as Error).message),
  })

  const testMutation = useMutation({
    mutationFn: () => testEmailConfig(testTo),
    onSuccess: () => {
      setTestMsg(t('settings.test_sent', { email: testTo }))
      setTimeout(() => setTestMsg(null), 5000)
    },
    onError: (err: unknown) => setTestMsg((err as Error).message),
  })

  if (isLoading) return null

  return (
    <section className="border rounded-lg p-5 space-y-5 bg-white">
      <div>
        <h2 className="text-base font-medium">{t('settings.email_section')}</h2>
        <p className="text-xs text-muted-foreground mt-0.5">
          {t('settings.email_help')}
        </p>
      </div>

      {cfg?.is_configured && (
        <div className="text-xs bg-green-50 border border-green-200 text-green-800 rounded-md px-3 py-2">
          {t('settings.email_configured', { email: cfg.from_address })}
        </div>
      )}

      {/* Mode toggle */}
      <div className="flex gap-1 p-1 bg-muted rounded-md w-fit">
        {(['resend_api', 'smtp'] as const).map(mode => (
          <button
            key={mode}
            onClick={() => setSendMode(mode)}
            className={`px-3 py-1.5 text-sm rounded transition-colors ${
              sendMode === mode
                ? 'bg-white shadow-sm font-medium'
                : 'text-muted-foreground hover:text-foreground'
            }`}
          >
            {mode === 'resend_api' ? t('settings.option_resend') : t('settings.option_smtp')}
          </button>
        ))}
      </div>

      {sendMode === 'resend_api' ? (
        <div className="space-y-4">
          <div className="space-y-1.5">
            <Label htmlFor="resend-api-key">
              {t('settings.api_key_label')}
              {cfg?.resend_api_key_set && (
                <span className="ml-2 text-xs font-normal text-muted-foreground">(leave blank to keep current)</span>
              )}
            </Label>
            <Input
              id="resend-api-key"
              type="password"
              value={resendApiKey}
              onChange={e => setResendApiKey(e.target.value)}
              placeholder={cfg?.resend_api_key_set ? '••••••••' : t('settings.api_key_placeholder')}
              autoComplete="new-password"
            />
            <p className="text-xs text-muted-foreground">
              {t('settings.api_key_help')}
            </p>
          </div>
        </div>
      ) : (
        <div className="space-y-4">
          <div className="grid grid-cols-2 gap-4">
            <div className="space-y-1.5 col-span-2 sm:col-span-1">
              <Label htmlFor="smtp-host">{t('settings.smtp_host')}</Label>
              <Input
                id="smtp-host"
                value={host}
                onChange={e => setHost(e.target.value)}
                placeholder={t('settings.smtp_host_placeholder')}
              />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="smtp-port">{t('settings.port_label')}</Label>
              <Input
                id="smtp-port"
                type="number"
                value={port}
                onChange={e => setPort(e.target.value)}
                placeholder="587"
              />
            </div>
          </div>

          <div className="space-y-1.5">
            <Label htmlFor="smtp-username">{t('settings.username_label')}</Label>
            <Input
              id="smtp-username"
              value={username}
              onChange={e => setUsername(e.target.value)}
              placeholder={t('settings.username_placeholder')}
              autoComplete="off"
            />
          </div>

          <div className="space-y-1.5">
            <Label htmlFor="smtp-password">
              {t('settings.password_label')}
              {cfg?.smtp_password_set && (
                <span className="ml-2 text-xs font-normal text-muted-foreground">(leave blank to keep current)</span>
              )}
            </Label>
            <Input
              id="smtp-password"
              type="password"
              value={password}
              onChange={e => setPassword(e.target.value)}
              placeholder={cfg?.smtp_password_set ? '••••••••' : t('common.required')}
              autoComplete="new-password"
            />
            <p className="text-xs text-muted-foreground">
              {t('settings.password_help')}
            </p>
          </div>

          <div className="flex items-center gap-2">
            <input
              id="use-tls"
              type="checkbox"
              checked={useTls}
              onChange={e => setUseTls(e.target.checked)}
              className="h-4 w-4 rounded border-gray-300"
            />
            <Label htmlFor="use-tls" className="font-normal cursor-pointer">
              {t('settings.starttls_label')}
            </Label>
          </div>
        </div>
      )}

      <div className="space-y-1.5">
        <Label htmlFor="from-address">{t('settings.client_from_label')}</Label>
        <Input
          id="from-address"
          value={fromAddress}
          onChange={e => setFromAddress(e.target.value)}
          placeholder={t('settings.client_from_placeholder')}
        />
        <p className="text-xs text-muted-foreground">
          {t('settings.client_from_help')}
        </p>
      </div>

      <div className="space-y-1.5">
        <Label htmlFor="accounting-from-address">{t('settings.accounting_from_label')}</Label>
        <Input
          id="accounting-from-address"
          value={accountingFromAddress}
          onChange={e => setAccountingFromAddress(e.target.value)}
          placeholder={t('settings.accounting_from_placeholder')}
        />
        <p className="text-xs text-muted-foreground">
          {t('settings.accounting_from_help')}
        </p>
      </div>

      <div className="flex items-center gap-3 flex-wrap">
        <Button
          onClick={() => { setSaveMsg(null); saveMutation.mutate() }}
          disabled={saveMutation.isPending}
        >
          <Save size={14} className="mr-1.5" />
          {saveMutation.isPending ? t('common.saving') : t('common.save')}
        </Button>
        {saveMsg && (
          <span className={`text-sm ${saveMsg === t('settings.status_saved') ? 'text-green-600' : 'text-destructive'}`}>
            {saveMsg}
          </span>
        )}
      </div>

      {cfg?.is_configured && (
        <div className="border-t pt-4 space-y-3">
          <h3 className="text-sm font-medium">{t('settings.test_email_button')}</h3>
          <div className="flex gap-2 items-center flex-wrap">
            <Input
              className="max-w-xs"
              type="email"
              value={testTo}
              onChange={e => setTestTo(e.target.value)}
              placeholder="recipient@example.com"
            />
            <Button
              variant="outline"
              onClick={() => { setTestMsg(null); testMutation.mutate() }}
              disabled={testMutation.isPending || !testTo}
            >
              {testMutation.isPending ? t('common.sending') : t('settings.send_test')}
            </Button>
          </div>
          {testMsg && (
            <p className={`text-sm ${testMsg.startsWith('Test email sent') ? 'text-green-600' : 'text-destructive'}`}>
              {testMsg}
            </p>
          )}
        </div>
      )}
    </section>
  )
}

function colorIsDark(hex: string): boolean {
  if (hex.length !== 7) return true
  const r = parseInt(hex.slice(1, 3), 16)
  const g = parseInt(hex.slice(3, 5), 16)
  const b = parseInt(hex.slice(5, 7), 16)
  return (0.299 * r + 0.587 * g + 0.114 * b) / 255 < 0.5
}

const LEAD_HOUR_OPTIONS = [2, 4, 12, 24, 48, 72]

function RemindersSection() {
  const { t } = useTranslation()
  const qc = useQueryClient()
  const { data, isLoading } = useQuery({
    queryKey: ['request-notifications'],
    queryFn: getRequestNotifications,
  })

  const [enabled, setEnabled] = useState(false)
  const [leadHours, setLeadHours] = useState(24)
  const [sendTime, setSendTime] = useState('09:00')
  const [dirty, setDirty] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [savedMsg, setSavedMsg] = useState<string | null>(null)

  useEffect(() => {
    if (data) {
      setEnabled(data.reminder_enabled)
      setLeadHours(data.reminder_lead_hours)
      setSendTime(data.reminder_send_time ?? '09:00')
      setDirty(false)
    }
  }, [data])

  const mutation = useMutation({
    mutationFn: () => updateRequestNotifications({ reminder_enabled: enabled, reminder_lead_hours: leadHours, reminder_send_time: sendTime }),
    onSuccess: updated => {
      qc.setQueryData(['request-notifications'], updated)
      setDirty(false)
      setError(null)
      setSavedMsg(t('settings.status_saved'))
      setTimeout(() => setSavedMsg(null), 3000)
    },
    onError: (e: unknown) => setError(e instanceof Error ? e.message : 'Save failed'),
  })

  if (isLoading) return null

  return (
    <section className="border rounded-lg p-5 space-y-4 bg-white">
      <div>
        <h2 className="text-base font-medium">{t('settings.reminders_section')}</h2>
        <p className="text-xs text-muted-foreground mt-0.5">
          {t('settings.reminders_help')}
        </p>
      </div>

      <label className="flex items-center gap-2 cursor-pointer">
        <input
          type="checkbox"
          checked={enabled}
          onChange={e => { setEnabled(e.target.checked); setDirty(true) }}
          className="h-4 w-4"
        />
        <span className="text-sm">{t('settings.reminders_checkbox')}</span>
      </label>

      {enabled && (
        <div className="space-y-3">
          <div className="space-y-1.5">
            <Label>{t('settings.send_reminder')}</Label>
            <select
              value={leadHours}
              onChange={e => { setLeadHours(Number(e.target.value)); setDirty(true) }}
              className="border border-input rounded-md px-2 py-1.5 text-sm bg-background"
            >
              {LEAD_HOUR_OPTIONS.map(h => (
                <option key={h} value={h}>
                  {h < 24 ? `${h} hours` : `${h / 24} day${h / 24 > 1 ? 's' : ''}`} before
                </option>
              ))}
            </select>
          </div>
          {leadHours >= 24 && (
            <div className="space-y-1.5">
              <Label>{t('settings.reminder_send_time')}</Label>
              <input
                type="time"
                value={sendTime}
                onChange={e => { setSendTime(e.target.value); setDirty(true) }}
                className="border border-input rounded-md px-2 py-1.5 text-sm bg-background"
              />
            </div>
          )}
          <p className="text-xs text-muted-foreground">
            {t('settings.reminders_note')}
          </p>
        </div>
      )}

      {error && <p className="text-xs text-destructive">{error}</p>}

      <div className="flex items-center gap-3">
        <Button onClick={() => mutation.mutate()} disabled={!dirty || mutation.isPending}>
          <Save size={14} className="mr-1.5" />
          {mutation.isPending ? t('common.saving') : t('common.save')}
        </Button>
        {savedMsg && <span className="text-sm text-green-600">{savedMsg}</span>}
      </div>
    </section>
  )
}

function RequestNotificationsSection() {
  const { t } = useTranslation()
  const qc = useQueryClient()
  const { data, isLoading } = useQuery({
    queryKey: ['request-notifications'],
    queryFn: getRequestNotifications,
  })

  const [enabled, setEnabled] = useState(true)
  const [recipientsText, setRecipientsText] = useState('')
  const [dirty, setDirty] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [savedMsg, setSavedMsg] = useState<string | null>(null)

  useEffect(() => {
    if (data) {
      setEnabled(data.enabled)
      setRecipientsText(data.recipients.join('\n'))
      setDirty(false)
    }
  }, [data])

  const mutation = useMutation({
    mutationFn: () => {
      const recipients = recipientsText
        .split(/[\n,]/)
        .map(r => r.trim())
        .filter(Boolean)
      return updateRequestNotifications({ enabled, recipients })
    },
    onSuccess: updated => {
      qc.setQueryData(['request-notifications'], updated)
      setRecipientsText(updated.recipients.join('\n'))
      setDirty(false)
      setError(null)
      setSavedMsg(t('settings.status_saved'))
      setTimeout(() => setSavedMsg(null), 3000)
    },
    onError: (e: unknown) => setError(e instanceof Error ? e.message : 'Save failed'),
  })

  if (isLoading) return null

  return (
    <section className="border rounded-lg p-5 space-y-4 bg-white">
      <div>
        <h2 className="text-base font-medium">{t('settings.notifications_section')}</h2>
        <p className="text-xs text-muted-foreground mt-0.5">
          {t('settings.notifications_help')}
        </p>
      </div>

      <label className="flex items-center gap-2 cursor-pointer">
        <input
          type="checkbox"
          checked={enabled}
          onChange={e => { setEnabled(e.target.checked); setDirty(true) }}
          className="h-4 w-4"
        />
        <span className="text-sm">{t('settings.notifications_checkbox')}</span>
      </label>

      <div className="space-y-1.5">
        <Label htmlFor="recipients">{t('settings.recipients_label')}</Label>
        <textarea
          id="recipients"
          value={recipientsText}
          onChange={e => { setRecipientsText(e.target.value); setDirty(true) }}
          rows={3}
          placeholder={t('settings.recipients_placeholder')}
          className="w-full border border-input rounded-md px-3 py-2 text-sm bg-background resize-none font-mono"
        />
        <p className="text-xs text-muted-foreground">
          {t('settings.recipients_help')}
        </p>
      </div>

      {error && <p className="text-xs text-destructive">{error}</p>}

      <div className="flex items-center gap-3">
        <Button onClick={() => mutation.mutate()} disabled={!dirty || mutation.isPending}>
          <Save size={14} className="mr-1.5" />
          {mutation.isPending ? t('common.saving') : t('common.save')}
        </Button>
        {savedMsg && <span className="text-sm text-green-600">{savedMsg}</span>}
      </div>
    </section>
  )
}

// ── Payroll Section ───────────────────────────────────────────────────────────

function PayrollSection() {
  const { t } = useTranslation()
  const qc = useQueryClient()
  const { data, isLoading } = useQuery({
    queryKey: ['payroll-config'],
    queryFn: getPayrollConfig,
  })

  const [form, setForm] = useState({
    provider_name: '',
    provider_email: '',
    client_id: '',
    signature: '',
    footer: '',
  })
  const [pSaved, setPSaved] = useState(false)

  useEffect(() => {
    if (data) {
      setForm({
        provider_name: data.provider_name ?? '',
        provider_email: data.provider_email ?? '',
        client_id: data.client_id ?? '',
        signature: data.signature ?? '',
        footer: data.footer ?? '',
      })
    }
  }, [data])

  const mutation = useMutation({
    mutationFn: () => savePayrollConfig({
      provider_name: form.provider_name || null,
      provider_email: form.provider_email || null,
      client_id: form.client_id || null,
      signature: form.signature || null,
      footer: form.footer || null,
    }),
    onSuccess: updated => {
      qc.setQueryData(['payroll-config'], updated)
      setPSaved(true)
      setTimeout(() => setPSaved(false), 3000)
    },
  })

  function setField(field: string, value: string) {
    setForm(f => ({ ...f, [field]: value }))
  }

  if (isLoading) return null

  return (
    <section className="border rounded-lg p-5 space-y-5 bg-white">
      <div>
        <h2 className="text-sm font-semibold">{t('settings.payroll_provider_section')}</h2>
        <p className="text-xs text-muted-foreground mt-1">
          {t('settings.payroll_provider_help')}
        </p>
      </div>

      <div className="grid grid-cols-2 gap-4">
        <div className="space-y-1.5">
          <Label>{t('settings.provider_name_label')}</Label>
          <Input value={form.provider_name} onChange={e => setField('provider_name', e.target.value)} placeholder={t('settings.provider_name_placeholder')} />
        </div>
        <div className="space-y-1.5">
          <Label>{t('settings.provider_email_label')}</Label>
          <Input type="email" value={form.provider_email} onChange={e => setField('provider_email', e.target.value)} placeholder={t('settings.provider_email_placeholder')} />
        </div>
        <div className="space-y-1.5">
          <Label>{t('settings.client_id_label')}</Label>
          <Input value={form.client_id} onChange={e => setField('client_id', e.target.value)} placeholder={t('settings.client_id_placeholder')} />
        </div>
        <div className="space-y-1.5">
          <Label>{t('settings.signature_name_label')}</Label>
          <Input value={form.signature} onChange={e => setField('signature', e.target.value)} placeholder={t('settings.signature_name_placeholder')} />
        </div>
      </div>

      <div className="space-y-1.5">
        <Label>{t('settings.footer_label')}</Label>
        <textarea
          value={form.footer}
          onChange={e => setField('footer', e.target.value)}
          rows={4}
          placeholder={'Salon Lyol\n1452 Yonge Street, Toronto, ON M4T 1Y5\n(416) 922-0611\ninfo@salonlyol.ca'}
          className="w-full border border-input rounded-md px-3 py-2 text-sm bg-background resize-none font-mono"
        />
      </div>

      <div className="flex items-center gap-3">
        <Button onClick={() => mutation.mutate()} disabled={mutation.isPending}>
          <Save size={14} className="mr-1.5" />
          {mutation.isPending ? t('common.saving') : t('common.save')}
        </Button>
        {pSaved && <span className="text-sm text-green-600">{t('settings.status_saved')}</span>}
      </div>
    </section>
  )
}

function PrinterSection() {
  const qc = useQueryClient()
  const { data: cfg, isLoading } = useQuery({
    queryKey: ['printer-config'],
    queryFn: getPrinterConfig,
  })

  const [printerName, setPrinterName] = useState('')
  const [printerHost, setPrinterHost] = useState('')
  const [printerPort, setPrinterPort] = useState(9100)
  const [paperWidth, setPaperWidth] = useState<58 | 80>(80)
  const [autoprint, setAutoprint] = useState(false)
  const [cashDrawer, setCashDrawer] = useState(false)
  const [saved, setSaved] = useState(false)
  const [logoUploading, setLogoUploading] = useState(false)
  const [logoError, setLogoError] = useState<string | null>(null)

  useEffect(() => {
    if (cfg) {
      setPrinterName(cfg.printer_name)
      setPrinterHost(cfg.printer_host ?? '')
      setPrinterPort(cfg.printer_port)
      setPaperWidth(cfg.paper_width as 58 | 80)
      setAutoprint(cfg.auto_print_on_cash)
      setCashDrawer(cfg.cash_drawer_enabled)
    }
  }, [cfg])

  const saveMutation = useMutation({
    mutationFn: () => updatePrinterConfig({
      printer_name: printerName.trim() || undefined,
      printer_host: printerHost.trim() || undefined,
      printer_port: printerPort,
      paper_width: paperWidth,
      auto_print_on_cash: autoprint,
      cash_drawer_enabled: cashDrawer,
    }),
    onSuccess: (updated: PrinterConfig) => {
      qc.setQueryData(['printer-config'], updated)
      setSaved(true)
      setTimeout(() => setSaved(false), 2000)
    },
  })

  async function handleLogoUpload(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0]
    if (!file) return
    setLogoUploading(true)
    setLogoError(null)
    try {
      const updated = await uploadPrinterLogo(file)
      qc.setQueryData(['printer-config'], updated)
    } catch (err) {
      setLogoError(err instanceof Error ? err.message : 'Upload failed')
    } finally {
      setLogoUploading(false)
      e.target.value = ''
    }
  }

  if (isLoading) return <div className="p-6 text-sm text-muted-foreground">Loading…</div>

  return (
    <section className="border rounded-lg p-5 space-y-5 bg-white">
      <div>
        <h2 className="text-sm font-semibold">Receipt Printer</h2>
        <p className="text-xs text-muted-foreground mt-0.5">
          Epson TM-T88V via QZ Tray. QZ Tray must be installed and running on the salon PC.
        </p>
      </div>

      <div className="space-y-2">
        <Label htmlFor="prt-name">Printer name</Label>
        <Input id="prt-name" value={printerName} onChange={e => setPrinterName(e.target.value)}
          placeholder="EPSON TM-T88V Receipt" />
        <p className="text-xs text-muted-foreground">Must match the printer name in QZ Tray exactly.</p>
      </div>

      <div className="grid grid-cols-2 gap-4">
        <div className="space-y-2">
          <Label htmlFor="prt-host">Printer IP address</Label>
          <Input id="prt-host" value={printerHost} onChange={e => setPrinterHost(e.target.value)}
            placeholder="192.168.1.x" />
        </div>
        <div className="space-y-2">
          <Label htmlFor="prt-port">Port</Label>
          <Input id="prt-port" type="number" value={printerPort}
            onChange={e => setPrinterPort(parseInt(e.target.value) || 9100)} />
        </div>
      </div>

      <div className="space-y-2">
        <Label>Paper width</Label>
        <div className="flex gap-3">
          {([80, 58] as const).map(w => (
            <label key={w} className="flex items-center gap-1.5 cursor-pointer text-sm">
              <input type="radio" name="paper-width" checked={paperWidth === w}
                onChange={() => setPaperWidth(w)} />
              {w}mm
            </label>
          ))}
        </div>
      </div>

      <div className="space-y-2">
        <label className="flex items-center gap-2 cursor-pointer text-sm">
          <input type="checkbox" checked={cashDrawer} onChange={e => setCashDrawer(e.target.checked)}
            className="h-4 w-4 rounded" />
          Cash drawer connected
        </label>
        <label className="flex items-center gap-2 cursor-pointer text-sm">
          <input type="checkbox" checked={autoprint} onChange={e => setAutoprint(e.target.checked)}
            className="h-4 w-4 rounded" disabled={!cashDrawer} />
          Auto-print + open drawer on cash checkout
        </label>
      </div>

      <div className="space-y-2">
        <Label>Receipt logo</Label>
        {cfg?.receipt_logo_url && (
          <img src={cfg.receipt_logo_url} alt="Receipt logo" className="h-12 object-contain border rounded p-1 bg-white" />
        )}
        <div className="flex items-center gap-3">
          <label className="cursor-pointer text-xs border rounded px-3 py-1.5 hover:bg-muted">
            {logoUploading ? 'Uploading…' : cfg?.receipt_logo_url ? 'Replace logo' : 'Upload logo'}
            <input type="file" accept="image/*" className="hidden" onChange={handleLogoUpload} disabled={logoUploading} />
          </label>
          {logoError && <p className="text-xs text-destructive">{logoError}</p>}
        </div>
        <p className="text-xs text-muted-foreground">PNG or JPEG, black on white, max ~500×150px for best results.</p>
      </div>

      <div className="flex items-center gap-3">
        <Button onClick={() => saveMutation.mutate()} disabled={saveMutation.isPending}>
          <Save className="h-3.5 w-3.5 mr-1.5" />
          {saveMutation.isPending ? 'Saving…' : 'Save printer settings'}
        </Button>
        {saved && <span className="text-sm text-green-600">Saved</span>}
        {saveMutation.isError && (
          <span className="text-sm text-destructive">
            {saveMutation.error instanceof Error ? saveMutation.error.message : 'Save failed'}
          </span>
        )}
      </div>
    </section>
  )
}

function ChangePasswordSection() {
  const { t } = useTranslation()
  const [current, setCurrent] = useState('')
  const [next, setNext] = useState('')
  const [confirm, setConfirm] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [saved, setSaved] = useState(false)

  const mutation = useMutation({
    mutationFn: () => changePassword(current, next),
    onSuccess: () => {
      setSaved(true)
      setCurrent('')
      setNext('')
      setConfirm('')
      setError(null)
      setTimeout(() => setSaved(false), 3000)
    },
    onError: (err: Error) => {
      setError(err.message || 'Something went wrong')
    },
  })

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    setError(null)
    setSaved(false)
    if (next !== confirm) {
      setError('New passwords do not match')
      return
    }
    if (next.length < 8) {
      setError('New password must be at least 8 characters')
      return
    }
    mutation.mutate()
  }

  return (
    <section className="border rounded-lg p-5 space-y-4 bg-white">
      <h2 className="text-base font-medium">{t('settings.change_password_section')}</h2>
      <form onSubmit={handleSubmit} className="space-y-4 max-w-sm">
        <div className="space-y-1.5">
          <Label htmlFor="cp-current">{t('settings.current_password_label')}</Label>
          <Input
            id="cp-current"
            type="password"
            value={current}
            onChange={e => setCurrent(e.target.value)}
            autoComplete="current-password"
            required
          />
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="cp-new">{t('settings.new_password_label')}</Label>
          <Input
            id="cp-new"
            type="password"
            value={next}
            onChange={e => setNext(e.target.value)}
            autoComplete="new-password"
            required
          />
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="cp-confirm">{t('settings.confirm_password_label')}</Label>
          <Input
            id="cp-confirm"
            type="password"
            value={confirm}
            onChange={e => setConfirm(e.target.value)}
            autoComplete="new-password"
            required
          />
        </div>
        {error && <p className="text-sm text-destructive">{error}</p>}
        <div className="flex items-center gap-3">
          <Button type="submit" disabled={mutation.isPending}>
            {mutation.isPending ? t('common.saving') : t('settings.change_password_button')}
          </Button>
          {saved && <span className="text-sm text-green-600">{t('settings.status_saved')}</span>}
        </div>
      </form>
    </section>
  )
}
