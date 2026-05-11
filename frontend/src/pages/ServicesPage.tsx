import { useState, useEffect, useRef } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { ChevronDown, ChevronRight, Plus } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import {
  listServicesFull,
  getService,
  createService,
  updateService,
  deactivateService,
  type ServiceDetail,
  type ServiceIn,
  type ServicePatch,
  type PricingType,
} from '@/api/services'
import {
  listServiceCategories,
  getServiceCategory,
  createServiceCategory,
  updateServiceCategory,
  type ServiceCategory,
} from '@/api/serviceCategories'
import {
  listProviderServicePrices,
  createProviderServicePrice,
  updateProviderServicePrice,
  deleteProviderServicePrice,
  type ProviderServicePrice,
} from '@/api/providerServicePrices'
import { listProviders, type Provider } from '@/api/providers'
import { Button } from '@/components/ui/button'
import { Label } from '@/components/ui/label'
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog'

export default function ServicesPage() {
  const { t } = useTranslation()
  const qc = useQueryClient()
  const { data: services = [], isLoading: servicesLoading } = useQuery({
    queryKey: ['services-full'],
    queryFn: listServicesFull,
  })
  const { data: categories = [] } = useQuery({
    queryKey: ['service-categories'],
    queryFn: listServiceCategories,
  })

  const [editingId, setEditingId] = useState<string | null>(null)
  const [creating, setCreating] = useState(false)
  const [showCategories, setShowCategories] = useState(false)
  const [collapsed, setCollapsed] = useState<Record<string, boolean>>({})

  const grouped = groupByCategory(services, categories)

  const refresh = () => {
    qc.invalidateQueries({ queryKey: ['services-full'] })
    qc.invalidateQueries({ queryKey: ['services'] })
    qc.invalidateQueries({ queryKey: ['service-categories'] })
  }

  // After a save: if we just created a new service, flip the dialog into edit
  // mode for that service so the Providers tab unlocks. Otherwise close.
  const handleSaved = (svc: ServiceDetail | null) => {
    refresh()
    if (svc && creating) {
      qc.setQueryData<ServiceDetail[]>(['services-full'], old => {
        if (!old) return [svc]
        return old.some(s => s.id === svc.id)
          ? old.map(s => s.id === svc.id ? svc : s)
          : [...old, svc]
      })
      setCreating(false)
      setEditingId(svc.id)
    } else {
      setEditingId(null)
      setCreating(false)
    }
  }

  return (
    <div className="h-full overflow-auto bg-muted/30">
      <div className="max-w-4xl mx-auto px-6 py-8 space-y-6">
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-xl font-semibold">{t('services.page_title')}</h1>
            <p className="text-sm text-muted-foreground mt-1">
              {t('services.page_description')}
            </p>
          </div>
          <Button size="sm" onClick={() => setCreating(true)} disabled={categories.length === 0}>
            <Plus size={14} className="mr-1.5" /> {t('services.new_service')}
          </Button>
        </div>

        {/* Categories — collapsed by default */}
        <section className="border rounded-lg bg-white">
          <button
            onClick={() => setShowCategories(s => !s)}
            className="w-full flex items-center justify-between px-5 py-3 text-sm font-medium hover:bg-muted/30"
          >
            <span className="flex items-center gap-2">
              {showCategories ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
              {t('services.categories_section', { count: categories.length })}
            </span>
          </button>
          {showCategories && <CategoryManager categories={categories} onChanged={refresh} />}
        </section>

        {/* Services list */}
        {servicesLoading ? (
          <p className="text-sm text-muted-foreground">{t('common.loading')}</p>
        ) : services.length === 0 ? (
          <div className="border rounded-lg p-8 bg-white text-center">
            <p className="text-sm text-muted-foreground">
              {categories.length === 0
                ? t('services.create_category_first')
                : t('services.no_services')}
            </p>
          </div>
        ) : (
          <div className="space-y-3">
            {grouped.map(({ category, services: rows }) => {
              const isCollapsed = collapsed[category.id]
              return (
                <section key={category.id} className="border rounded-lg bg-white overflow-hidden">
                  <button
                    onClick={() => setCollapsed(c => ({ ...c, [category.id]: !c[category.id] }))}
                    className="w-full flex items-center justify-between px-5 py-3 text-sm font-medium hover:bg-muted/30 border-b"
                  >
                    <span className="flex items-center gap-2">
                      {isCollapsed ? <ChevronRight size={14} /> : <ChevronDown size={14} />}
                      {category.name}
                      <span className="text-xs text-muted-foreground font-normal">({rows.length})</span>
                    </span>
                  </button>
                  {!isCollapsed && (
                    <div className="divide-y">
                      {rows.length === 0 && (
                        <p className="px-5 py-3 text-sm text-muted-foreground italic">{t('services.no_services_in_category')}</p>
                      )}
                      {rows.map(svc => (
                        <button
                          key={svc.id}
                          onClick={() => setEditingId(svc.id)}
                          className={`w-full text-left px-5 py-3 hover:bg-muted/30 grid grid-cols-12 gap-3 items-center ${!svc.is_active ? 'opacity-60' : ''}`}
                        >
                          <span className="col-span-6 text-sm font-medium">{svc.name}</span>
                          <span className="col-span-2 text-sm text-muted-foreground">
                            {svc.default_price ? `$${parseFloat(svc.default_price).toFixed(2)}` : '—'}
                          </span>
                          <span className="col-span-2 text-sm text-muted-foreground">{svc.duration_minutes} min</span>
                          <span className={`col-span-2 text-xs ${svc.is_active ? 'text-green-600' : 'text-muted-foreground'}`}>
                            {svc.is_active ? t('services.status_active') : t('services.status_inactive')}
                          </span>
                        </button>
                      ))}
                    </div>
                  )}
                </section>
              )
            })}
          </div>
        )}

        {(editingId || creating) && (
          <ServiceEditDialog
            serviceId={editingId}
            categories={categories}
            onClose={() => { setEditingId(null); setCreating(false) }}
            onSaved={handleSaved}
          />
        )}
      </div>
    </div>
  )
}

function groupByCategory(services: ServiceDetail[], categories: ServiceCategory[]) {
  const byCat = new Map<string, ServiceDetail[]>()
  for (const c of categories) byCat.set(c.id, [])
  for (const s of services) {
    if (!byCat.has(s.category_id)) byCat.set(s.category_id, [])
    byCat.get(s.category_id)!.push(s)
  }
  return categories.map(c => ({ category: c, services: byCat.get(c.id) ?? [] }))
}

// ── Category manager ─────────────────────────────────────────────────────────

function CategoryManager({ categories, onChanged }: { categories: ServiceCategory[]; onChanged: () => void }) {
  const { t } = useTranslation()
  const [newName, setNewName] = useState('')
  const [error, setError] = useState<string | null>(null)

  const createMut = useMutation({
    mutationFn: () => createServiceCategory({ name: newName.trim() }),
    onSuccess: () => { setNewName(''); setError(null); onChanged() },
    onError: (e: unknown) => setError(e instanceof Error ? e.message : 'Failed'),
  })

  return (
    <div className="px-5 py-4 space-y-3 border-t">
      {categories.map(c => (
        <CategoryRow key={c.id} category={c} onSaved={onChanged} />
      ))}
      <div className="flex gap-2 items-center pt-2 border-t border-dashed">
        <input
          value={newName}
          onChange={e => setNewName(e.target.value)}
          placeholder={t('services.new_category_name')}
          className="flex-1 border border-input rounded-md px-2 py-1.5 text-sm bg-background"
        />
        <Button size="sm" onClick={() => createMut.mutate()} disabled={!newName.trim() || createMut.isPending}>
          {createMut.isPending ? '…' : t('common.add')}
        </Button>
      </div>
      {error && <p className="text-xs text-destructive">{error}</p>}
    </div>
  )
}

function CategoryRow({ category, onSaved }: { category: ServiceCategory; onSaved: () => void }) {
  const { t } = useTranslation()
  const qc = useQueryClient()
  const [name, setName] = useState(category.name)
  const [isActive, setIsActive] = useState(category.is_active)
  const [showTranslations, setShowTranslations] = useState(false)

  const supportedLanguages =
    qc.getQueryData<{ supported_languages: string[] }>(['branding'])?.supported_languages ?? ['en', 'fr']
  const nonEnglishLanguages = supportedLanguages.filter(l => l !== 'en')

  type TranslationRow = { name: string }
  const [translationNames, setTranslationNames] = useState<Record<string, TranslationRow>>({})

  const { data: catDetail } = useQuery({
    queryKey: ['category-translations', category.id],
    queryFn: () => getServiceCategory(category.id),
    enabled: showTranslations,
  })

  useEffect(() => {
    if (!catDetail) return
    const initial: Record<string, TranslationRow> = {}
    for (const lang of nonEnglishLanguages) {
      const entry = catDetail.translations?.[lang] ?? {}
      initial[lang] = { name: (entry as { name?: string }).name ?? '' }
    }
    setTranslationNames(initial)
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [catDetail])

  const dirty =
    name !== category.name ||
    isActive !== category.is_active ||
    (showTranslations && Object.keys(translationNames).length > 0)

  const mut = useMutation({
    mutationFn: () => updateServiceCategory(category.id, {
      name,
      is_active: isActive,
      ...(showTranslations && Object.keys(translationNames).length > 0
        ? { translations: translationNames }
        : {}),
    }),
    onSuccess: () => onSaved(),
  })

  return (
    <div className={`space-y-2 ${!isActive ? 'opacity-60' : ''}`}>
      <div className="flex gap-2 items-center">
        <input
          value={name}
          onChange={e => setName(e.target.value)}
          className="flex-1 border border-input rounded-md px-2 py-1 text-sm bg-background"
        />
        <label className="flex items-center gap-1.5 text-xs text-muted-foreground">
          <input
            type="checkbox"
            checked={isActive}
            onChange={e => setIsActive(e.target.checked)}
            className="h-3.5 w-3.5"
          />
          {t('common.active')}
        </label>
        {nonEnglishLanguages.length > 0 && (
          <button
            type="button"
            onClick={() => setShowTranslations(s => !s)}
            className="text-xs text-muted-foreground hover:text-foreground flex items-center gap-0.5"
          >
            {t('translations.tab')}
            {showTranslations ? <ChevronDown size={12} /> : <ChevronRight size={12} />}
          </button>
        )}
        <Button size="sm" variant="outline" disabled={!dirty || mut.isPending} onClick={() => mut.mutate()}>
          {mut.isPending ? '…' : t('common.save')}
        </Button>
      </div>
      {showTranslations && nonEnglishLanguages.length > 0 && (
        <div className="pl-2 space-y-1.5 border-l-2 border-muted ml-1">
          {nonEnglishLanguages.map(lang => (
            <div key={lang} className="flex items-center gap-2">
              <span className="text-xs text-muted-foreground w-20 shrink-0">
                {t('translations.lang_' + lang)}
              </span>
              <input
                value={translationNames[lang]?.name ?? ''}
                onChange={e =>
                  setTranslationNames(prev => ({ ...prev, [lang]: { name: e.target.value } }))
                }
                placeholder={name}
                className="flex-1 border border-input rounded-md px-2 py-1 text-sm bg-background"
              />
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

// ── Service edit dialog ──────────────────────────────────────────────────────

interface EditDialogProps {
  serviceId: string | null  // null → create mode
  categories: ServiceCategory[]
  onClose: () => void
  onSaved: (svc: ServiceDetail | null) => void
}

function ServiceEditDialog({ serviceId, categories, onClose, onSaved }: EditDialogProps) {
  const { t } = useTranslation()
  const isCreate = serviceId === null
  // The list endpoint already returns full ServiceDetail, so we read from the
  // react-query cache rather than re-fetching by id.
  const qc = useQueryClient()
  const cached = qc.getQueryData<ServiceDetail[]>(['services-full'])
  const initial = !isCreate ? cached?.find(s => s.id === serviceId) ?? null : null

  const [tab, setTab] = useState<'details' | 'providers' | 'translations'>('details')
  // When the dialog transitions from create-mode to edit-mode of the just-created
  // service, automatically jump to the Providers tab — that's where the user
  // typically wants to go next.
  const startedCreating = useRef(serviceId === null)
  useEffect(() => {
    if (startedCreating.current && serviceId !== null) {
      setTab('providers')
      startedCreating.current = false
    }
  }, [serviceId])

  const tabLabel = (key: 'details' | 'providers' | 'translations') => {
    if (key === 'details') return t('services.tab_details')
    if (key === 'providers') return t('services.tab_providers')
    return t('translations.tab')
  }

  return (
    <Dialog open onOpenChange={(o) => { if (!o) onClose() }}>
      <DialogContent className="max-w-2xl max-h-[85vh] overflow-hidden flex flex-col">
        <DialogHeader>
          <DialogTitle>{isCreate ? t('services.new_service_title') : initial?.name ?? 'Service'}</DialogTitle>
        </DialogHeader>

        <div className="flex border-b -mx-6 px-6">
          {(['details', 'providers', 'translations'] as const).map(tabKey => (
            <button
              key={tabKey}
              onClick={() => setTab(tabKey)}
              disabled={(tabKey === 'providers' || tabKey === 'translations') && isCreate}
              className={`px-4 py-2 text-sm border-b-2 -mb-px capitalize transition-colors disabled:opacity-50 disabled:cursor-not-allowed ${
                tab === tabKey ? 'border-foreground font-medium' : 'border-transparent text-muted-foreground hover:text-foreground'
              }`}
            >
              {tabLabel(tabKey)}
            </button>
          ))}
        </div>

        <div className="flex-1 overflow-auto -mx-6 px-6">
          {tab === 'details' && (
            <DetailsForm
              initial={initial}
              categories={categories}
              isCreate={isCreate}
              onSaved={onSaved}
              onClose={onClose}
            />
          )}
          {tab === 'providers' && !isCreate && initial && (
            <ProvidersMatrix service={initial} />
          )}
          {tab === 'translations' && !isCreate && serviceId && (
            <TranslationsForm serviceId={serviceId} />
          )}
        </div>
      </DialogContent>
    </Dialog>
  )
}

// ── Details tab ──────────────────────────────────────────────────────────────

function DetailsForm({
  initial,
  categories,
  isCreate,
  onSaved,
  onClose,
}: {
  initial: ServiceDetail | null
  categories: ServiceCategory[]
  isCreate: boolean
  onSaved: (svc: ServiceDetail | null) => void
  onClose: () => void
}) {
  const { t } = useTranslation()
  const [form, setForm] = useState({
    name: initial?.name ?? '',
    service_code: initial?.service_code ?? '',
    description: initial?.description ?? '',
    category_id: initial?.category_id ?? categories[0]?.id ?? '',
    pricing_type: (initial?.pricing_type ?? 'fixed') as PricingType,
    default_price: initial?.default_price ?? '',
    default_cost: initial?.default_cost ?? '',
    is_cost_percent: initial?.is_cost_percent ?? false,
    duration_minutes: String(initial?.duration_minutes ?? 60),
    processing_offset_minutes: String(initial?.processing_offset_minutes ?? 0),
    processing_duration_minutes: String(initial?.processing_duration_minutes ?? 0),
    requires_prior_consultation: initial?.requires_prior_consultation ?? false,
    is_active: initial?.is_active ?? true,
    suggestions: initial?.suggestions ?? '',
  })
  const [error, setError] = useState<string | null>(null)

  function set<K extends keyof typeof form>(key: K, value: typeof form[K]) {
    setForm(f => ({ ...f, [key]: value }))
  }

  const saveMut = useMutation({
    mutationFn: () => {
      const body: ServiceIn | ServicePatch = {
        category_id: form.category_id,
        service_code: form.service_code.trim() || undefined,
        name: form.name.trim(),
        description: form.description.trim() || null,
        pricing_type: form.pricing_type,
        default_price: form.default_price ? parseFloat(form.default_price) : null,
        default_cost: form.default_cost ? parseFloat(form.default_cost) : null,
        is_cost_percent: form.is_cost_percent,
        duration_minutes: parseInt(form.duration_minutes, 10),
        processing_offset_minutes: parseInt(form.processing_offset_minutes, 10) || 0,
        processing_duration_minutes: parseInt(form.processing_duration_minutes, 10) || 0,
        requires_prior_consultation: form.requires_prior_consultation,
        suggestions: form.suggestions.trim() || null,
        is_active: form.is_active,
      }
      return isCreate
        ? createService(body as ServiceIn)
        : updateService(initial!.id, body as ServicePatch)
    },
    onSuccess: (svc) => { setError(null); onSaved(svc) },
    onError: (e: unknown) => setError(e instanceof Error ? e.message : 'Save failed'),
  })

  const deactivateMut = useMutation({
    mutationFn: () => deactivateService(initial!.id),
    onSuccess: () => onSaved(null),
  })

  function submit() {
    if (!form.name.trim()) { setError('Name required'); return }
    if (!form.category_id) { setError('Category required'); return }
    if (!form.duration_minutes || parseInt(form.duration_minutes, 10) < 5) {
      setError('Duration must be at least 5 minutes'); return
    }
    saveMut.mutate()
  }

  return (
    <div className="py-4 space-y-4">
      <div className="grid grid-cols-2 gap-3">
        <div className="col-span-2">
          <Label>{t('common.name')}</Label>
          <input
            value={form.name}
            onChange={e => set('name', e.target.value)}
            className="w-full mt-1 border border-input rounded-md px-2 py-1.5 text-sm bg-background"
            placeholder="e.g. Type 1 Haircut"
          />
        </div>
        <div>
          <Label>{t('services.category_label')}</Label>
          <select
            value={form.category_id}
            onChange={e => set('category_id', e.target.value)}
            className="w-full mt-1 border border-input rounded-md px-2 py-1.5 text-sm bg-background"
          >
            <option value="">{t('services.select_placeholder')}</option>
            {categories.map(c => (
              <option key={c.id} value={c.id}>{c.name}</option>
            ))}
          </select>
        </div>
        <div>
          <Label>{t('services.code_label')}</Label>
          <input
            value={form.service_code}
            onChange={e => set('service_code', e.target.value.toLowerCase().replace(/[^a-z0-9_]/g, ''))}
            className="w-full mt-1 border border-input rounded-md px-2 py-1.5 text-sm bg-background font-mono"
            placeholder={t('services.code_default')}
          />
        </div>
        <div className="col-span-2">
          <Label>{t('services.description_label')}</Label>
          <textarea
            rows={2}
            value={form.description}
            onChange={e => set('description', e.target.value)}
            className="w-full mt-1 border border-input rounded-md px-2 py-1.5 text-sm bg-background resize-none"
          />
        </div>
        <div>
          <Label>{t('services.default_price')}</Label>
          <input
            type="text" inputMode="decimal"
            value={form.default_price}
            onChange={e => set('default_price', e.target.value)}
            className="w-full mt-1 border border-input rounded-md px-2 py-1.5 text-sm bg-background"
            placeholder="0.00"
          />
        </div>
        <div>
          <Label>Product fee</Label>
          <div className="flex gap-2 mt-1">
            <input
              type="text" inputMode="decimal"
              value={form.default_cost}
              onChange={e => set('default_cost', e.target.value)}
              className="flex-1 border border-input rounded-md px-2 py-1.5 text-sm bg-background"
              placeholder={form.is_cost_percent ? 'e.g. 10 for 10%' : '0.00'}
            />
            <div className="flex rounded-md border border-input overflow-hidden text-xs">
              {(['$', '%'] as const).map(mode => (
                <button
                  key={mode}
                  type="button"
                  onClick={() => set('is_cost_percent', mode === '%')}
                  className={`px-2.5 py-1.5 font-medium transition-colors ${
                    (mode === '%') === form.is_cost_percent
                      ? 'bg-foreground text-background'
                      : 'bg-muted text-muted-foreground hover:bg-muted/70'
                  }`}
                >{mode}</button>
              ))}
            </div>
          </div>
          <p className="text-xs text-muted-foreground mt-1">
            {form.is_cost_percent ? 'Percentage of gross charged to provider' : 'Flat amount per service application'}
          </p>
        </div>
        <div>
          <Label>{t('services.duration_label')}</Label>
          <input
            type="number" min={5}
            value={form.duration_minutes}
            onChange={e => set('duration_minutes', e.target.value)}
            className="w-full mt-1 border border-input rounded-md px-2 py-1.5 text-sm bg-background"
          />
        </div>
        <div>
          <Label>{t('services.pricing_type')}</Label>
          <select
            value={form.pricing_type}
            onChange={e => set('pricing_type', e.target.value as PricingType)}
            className="w-full mt-1 border border-input rounded-md px-2 py-1.5 text-sm bg-background"
          >
            <option value="fixed">{t('services.pricing_fixed')}</option>
            <option value="hourly">{t('services.pricing_hourly')}</option>
          </select>
        </div>
        <div>
          <Label>{t('services.processing_offset')}</Label>
          <input
            type="number" min={0}
            value={form.processing_offset_minutes}
            onChange={e => set('processing_offset_minutes', e.target.value)}
            className="w-full mt-1 border border-input rounded-md px-2 py-1.5 text-sm bg-background"
          />
        </div>
        <div>
          <Label>{t('services.processing_duration')}</Label>
          <input
            type="number" min={0}
            value={form.processing_duration_minutes}
            onChange={e => set('processing_duration_minutes', e.target.value)}
            className="w-full mt-1 border border-input rounded-md px-2 py-1.5 text-sm bg-background"
          />
        </div>
      </div>

      <div className="grid grid-cols-2 gap-x-3 gap-y-1.5 pt-2 border-t">
        <Toggle label={t('services.active_checkbox')} value={form.is_active} onChange={v => set('is_active', v)} />
        <Toggle label={t('services.consultation_checkbox')} value={form.requires_prior_consultation} onChange={v => set('requires_prior_consultation', v)} />
      </div>

      {error && <p className="text-sm text-destructive">{error}</p>}

      <div className="flex gap-2 pt-2 border-t">
        <Button onClick={submit} disabled={saveMut.isPending} className="flex-1">
          {saveMut.isPending ? t('common.saving') : isCreate ? t('services.create_service') : t('services.save_changes')}
        </Button>
        {!isCreate && initial?.is_active && (
          <Button
            variant="outline"
            onClick={() => deactivateMut.mutate()}
            disabled={deactivateMut.isPending}
          >
            {t('services.deactivate')}
          </Button>
        )}
        <Button variant="ghost" onClick={onClose}>{t('common.cancel')}</Button>
      </div>
    </div>
  )
}

function Toggle({ label, value, onChange }: { label: string; value: boolean; onChange: (v: boolean) => void }) {
  return (
    <label className="flex items-center gap-2 text-sm">
      <input
        type="checkbox"
        checked={value}
        onChange={e => onChange(e.target.checked)}
        className="h-3.5 w-3.5"
      />
      {label}
    </label>
  )
}

// ── Translations tab ─────────────────────────────────────────────────────────

function TranslationsForm({ serviceId }: { serviceId: string }) {
  const { t } = useTranslation()
  const qc = useQueryClient()

  const supportedLanguages =
    qc.getQueryData<{ supported_languages: string[] }>(['branding'])?.supported_languages ?? ['en', 'fr']

  const { data: svc, isLoading } = useQuery({
    queryKey: ['service-translations', serviceId],
    queryFn: () => getService(serviceId),
  })

  type TranslationRow = { name: string; description: string }
  const [local, setLocal] = useState<Record<string, TranslationRow>>({})
  const [saved, setSaved] = useState(false)

  useEffect(() => {
    if (!svc) return
    const initial: Record<string, TranslationRow> = {}
    for (const lang of supportedLanguages) {
      const entry = svc.translations?.[lang] ?? {}
      initial[lang] = {
        name: (entry as { name?: string }).name ?? '',
        description: (entry as { description?: string }).description ?? '',
      }
    }
    setLocal(initial)
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [svc])

  const saveMut = useMutation({
    mutationFn: () => updateService(serviceId, { translations: local }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['services-full'] })
      setSaved(true)
      setTimeout(() => setSaved(false), 2000)
    },
  })

  function setField(lang: string, field: 'name' | 'description', value: string) {
    setLocal(prev => ({ ...prev, [lang]: { ...prev[lang], [field]: value } }))
  }

  if (isLoading) return <p className="py-4 text-sm text-muted-foreground">{t('common.loading')}</p>

  return (
    <div className="py-4 space-y-4">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b text-xs text-muted-foreground">
            <th className="text-left pb-2 pr-3 w-24">{t('translations.col_language')}</th>
            <th className="text-left pb-2 pr-3">{t('translations.col_name')}</th>
            <th className="text-left pb-2">{t('translations.col_description')}</th>
          </tr>
        </thead>
        <tbody className="divide-y">
          {supportedLanguages.map(lang => (
            <tr key={lang}>
              <td className="py-2 pr-3 text-muted-foreground text-xs align-middle whitespace-nowrap">
                {t('translations.lang_' + lang)}
              </td>
              <td className="py-2 pr-3">
                <input
                  value={local[lang]?.name ?? ''}
                  onChange={e => setField(lang, 'name', e.target.value)}
                  className="w-full border border-input rounded-md px-2 py-1 text-sm bg-background"
                />
              </td>
              <td className="py-2">
                <input
                  value={local[lang]?.description ?? ''}
                  onChange={e => setField(lang, 'description', e.target.value)}
                  className="w-full border border-input rounded-md px-2 py-1 text-sm bg-background"
                />
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      <div className="flex items-center gap-3 pt-2 border-t">
        <Button onClick={() => saveMut.mutate()} disabled={saveMut.isPending}>
          {saveMut.isPending ? t('common.saving') : t('translations.save_all')}
        </Button>
        {saved && <span className="text-xs text-green-600">{t('translations.saved')}</span>}
      </div>
    </div>
  )
}

// ── Providers tab ────────────────────────────────────────────────────────────

function ProvidersMatrix({ service }: { service: ServiceDetail }) {
  const { t } = useTranslation()
  const qc = useQueryClient()
  const { data: providers = [] } = useQuery({
    queryKey: ['providers'],
    queryFn: listProviders,
  })
  const { data: psps = [] } = useQuery({
    queryKey: ['psps', service.id],
    queryFn: () => listProviderServicePrices({ service_id: service.id }),
  })

  const refresh = () => qc.invalidateQueries({ queryKey: ['psps', service.id] })

  return (
    <div className="py-4 space-y-2">
      <p className="text-xs text-muted-foreground">
        {t('services.providers_subtitle')}
        (${service.default_price ? parseFloat(service.default_price).toFixed(2) : '—'} / {service.duration_minutes} min).
      </p>
      {providers.map(p => {
        const existing = psps.find(x => x.provider_id === p.id) ?? null
        return (
          <ProviderMatrixRow
            key={p.id}
            provider={p}
            service={service}
            existing={existing}
            onChanged={refresh}
          />
        )
      })}
      {providers.length === 0 && (
        <p className="text-sm text-muted-foreground italic">{t('services.no_providers')}</p>
      )}
    </div>
  )
}

function ProviderMatrixRow({
  provider, service, existing, onChanged,
}: {
  provider: Provider
  service: ServiceDetail
  existing: ProviderServicePrice | null
  onChanged: () => void
}) {
  const { t } = useTranslation()
  const [enabled, setEnabled] = useState(!!existing)
  const [price, setPrice] = useState(existing?.price ?? service.default_price ?? '')
  // Empty string = use service default. Number string = override.
  const [duration, setDuration] = useState(
    existing?.duration_minutes != null ? String(existing.duration_minutes) : ''
  )
  const [procOffset, setProcOffset] = useState(
    existing?.processing_offset_minutes != null ? String(existing.processing_offset_minutes) : ''
  )
  const [procDuration, setProcDuration] = useState(
    existing?.processing_duration_minutes != null ? String(existing.processing_duration_minutes) : ''
  )
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    setEnabled(!!existing)
    setPrice(existing?.price ?? service.default_price ?? '')
    setDuration(existing?.duration_minutes != null ? String(existing.duration_minutes) : '')
    setProcOffset(existing?.processing_offset_minutes != null ? String(existing.processing_offset_minutes) : '')
    setProcDuration(existing?.processing_duration_minutes != null ? String(existing.processing_duration_minutes) : '')
  }, [existing, service])

  const intOrNull = (s: string) => s.trim() ? parseInt(s, 10) : null

  const createMut = useMutation({
    mutationFn: () => createProviderServicePrice({
      provider_id: provider.id,
      service_id: service.id,
      price: parseFloat(price || service.default_price || '0'),
      duration_minutes: intOrNull(duration),
      processing_offset_minutes: intOrNull(procOffset),
      processing_duration_minutes: intOrNull(procDuration),
    }),
    onSuccess: () => { setError(null); onChanged() },
    onError: (e: unknown) => { setEnabled(false); setError(e instanceof Error ? e.message : 'Failed') },
  })

  const updateMut = useMutation({
    mutationFn: () => updateProviderServicePrice(existing!.id, {
      price: parseFloat(price),
      duration_minutes: intOrNull(duration),
      processing_offset_minutes: intOrNull(procOffset),
      processing_duration_minutes: intOrNull(procDuration),
    }),
    onSuccess: () => { setError(null); onChanged() },
    onError: (e: unknown) => setError(e instanceof Error ? e.message : 'Failed'),
  })

  const deleteMut = useMutation({
    mutationFn: () => deleteProviderServicePrice(existing!.id),
    onSuccess: () => onChanged(),
  })

  function toggle(checked: boolean) {
    setEnabled(checked)
    if (checked && !existing) createMut.mutate()
    else if (!checked && existing) deleteMut.mutate()
  }

  const parsedPrice = parseFloat(price)
  const priceValid = !isNaN(parsedPrice) && parsedPrice >= 0

  const dirty = existing && priceValid && (
    parsedPrice !== parseFloat(existing.price) ||
    intOrNull(duration) !== existing.duration_minutes ||
    intOrNull(procOffset) !== existing.processing_offset_minutes ||
    intOrNull(procDuration) !== existing.processing_duration_minutes
  )

  return (
    <div className="flex gap-3 items-center border rounded-md px-3 py-2 flex-wrap">
      <label className="flex items-center gap-2 flex-1 min-w-[140px] text-sm cursor-pointer">
        <input
          type="checkbox"
          checked={enabled}
          onChange={e => toggle(e.target.checked)}
          className="h-4 w-4"
        />
        {provider.display_name}
      </label>
      {enabled && (
        <>
          <Field label="$" title={t('services.price_override')}>
            <input
              type="text" inputMode="decimal"
              value={price}
              onChange={e => { setPrice(e.target.value); setError(null) }}
              className={`w-20 border rounded px-2 py-1 text-sm bg-background ${!priceValid && price !== '' ? 'border-destructive' : 'border-input'}`}
            />
          </Field>
          <Field label="min" title={t('services.duration_override')} trailing>
            <input
              type="number" min={5}
              value={duration}
              onChange={e => setDuration(e.target.value)}
              placeholder={String(service.duration_minutes)}
              className="w-16 border border-input rounded px-2 py-1 text-sm bg-background"
            />
          </Field>
          <Field label="proc offset" title="Processing offset override — minutes after the start when processing begins (blank = use service default)" trailing>
            <input
              type="number" min={0}
              value={procOffset}
              onChange={e => setProcOffset(e.target.value)}
              placeholder={String(service.processing_offset_minutes)}
              className="w-16 border border-input rounded px-2 py-1 text-sm bg-background"
            />
          </Field>
          <Field label="proc min" title="Processing duration override — gap during which the provider is free (blank = use service default)" trailing>
            <input
              type="number" min={0}
              value={procDuration}
              onChange={e => setProcDuration(e.target.value)}
              placeholder={String(service.processing_duration_minutes)}
              className="w-16 border border-input rounded px-2 py-1 text-sm bg-background"
            />
          </Field>
          {dirty && (
            <Button size="sm" variant="outline" onClick={() => updateMut.mutate()} disabled={updateMut.isPending}>
              {updateMut.isPending ? '…' : t('common.save')}
            </Button>
          )}
        </>
      )}
      {error && <p className="w-full text-xs text-destructive">{error}</p>}
    </div>
  )
}

function Field({
  label, title, trailing = false, children,
}: {
  label: string
  title?: string
  trailing?: boolean
  children: React.ReactNode
}) {
  return (
    <div className="flex items-center gap-1.5" title={title}>
      {!trailing && <span className="text-xs text-muted-foreground">{label}</span>}
      {children}
      {trailing && <span className="text-xs text-muted-foreground">{label}</span>}
    </div>
  )
}
