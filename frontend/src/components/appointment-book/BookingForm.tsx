import { useState, useEffect, useRef } from 'react'
import { useTranslation } from 'react-i18next'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { format } from 'date-fns'
import { useTimeFormat } from '@/lib/timeFormat'
import { searchClients, createClient, type Client } from '@/api/clients'
import { listServices, type Service } from '@/api/services'
import { type Provider } from '@/api/providers'
import { type ProviderWorkStatus } from '@/api/schedules'
import { api } from '@/api/client'
import { useAuth } from '@/store/auth'
import { type Recommendation } from '@/api/scheduling'
import RecommendPanel from '@/components/scheduling/RecommendPanel'
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Button } from '@/components/ui/button'

interface Props {
  open: boolean
  date: string           // YYYY-MM-DD
  initialTime?: string   // HH:MM
  initialProviderId?: string
  providers: Provider[]
  providerHours?: ProviderWorkStatus[]
  slotMinutes?: number
  onClose: () => void
  onSaved: (appt: { id: string; appointment_date: string; clientEmail: string | null }) => void
}

function snapToSlot(time: string, slotMinutes: number): string {
  const [h, m] = time.split(':').map(Number)
  const snapped = Math.round(m / slotMinutes) * slotMinutes
  if (snapped >= 60) return `${String(h + 1).padStart(2, '0')}:00`
  return `${String(h).padStart(2, '0')}:${String(snapped).padStart(2, '0')}`
}

// Advance startTime by a duration and round UP to the nearest slot grid value
// so the new time matches an option in the time <select>. Without rounding,
// e.g. 10:10 + 45min = 10:55, which isn't a 10-min slot — the select would
// silently fall back to its first option.
function advanceToNextSlot(startHHMM: string, durationMins: number, slotMinutes: number): string {
  const [h, m] = startHHMM.split(':').map(Number)
  const endMins = h * 60 + m + durationMins
  const snapped = Math.ceil(endMins / slotMinutes) * slotMinutes
  const sh = Math.min(21, Math.floor(snapped / 60))
  const sm = snapped >= 22 * 60 ? 50 : snapped % 60
  return `${String(sh).padStart(2, '0')}:${String(sm).padStart(2, '0')}`
}

interface ItemDraft {
  service: Service
  provider: Provider
  startTime: string   // HH:MM
  price: number
}

function isItemOutsideHours(startHHMM: string, durationMins: number, hours: ProviderWorkStatus): boolean {
  if (!hours.start_time || !hours.end_time) return false
  const [sh, sm] = startHHMM.split(':').map(Number)
  const startMins = sh * 60 + sm
  const endMins = startMins + durationMins
  const [wsh, wsm] = hours.start_time.split(':').map(Number)
  const [weh, wem] = hours.end_time.split(':').map(Number)
  return startMins < wsh * 60 + wsm || endMins > weh * 60 + wem
}

export default function BookingForm({
  open, date, initialTime, initialProviderId, providers, providerHours = [], slotMinutes = 10, onClose, onSaved,
}: Props) {
  const { t } = useTranslation()
  const qc = useQueryClient()
  const { user } = useAuth()

  // ── Step: 'client' | 'items' | 'confirm'
  const { formatTime: ft } = useTimeFormat()
  const [step, setStep] = useState<'client' | 'items' | 'confirm'>('client')

  // ── Client search
  const [clientQuery, setClientQuery] = useState('')
  const [selectedClient, setSelectedClient] = useState<Client | null>(null)
  const [showNewClient, setShowNewClient] = useState(false)
  const [newFirst, setNewFirst] = useState('')
  const [newLast, setNewLast] = useState('')
  const [newPhone, setNewPhone] = useState('')
  const [newEmail, setNewEmail] = useState('')
  const [newLang, setNewLang] = useState('en')
  const [creatingClient, setCreatingClient] = useState(false)
  const searchRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const [debouncedQuery, setDebouncedQuery] = useState('')

  useEffect(() => {
    if (searchRef.current) clearTimeout(searchRef.current)
    searchRef.current = setTimeout(() => setDebouncedQuery(clientQuery), 250)
  }, [clientQuery])

  const { data: clientResults = [] } = useQuery({
    queryKey: ['clients', debouncedQuery],
    queryFn: () => searchClients(debouncedQuery),
    enabled: debouncedQuery.length >= 1,
  })

  // ── Services
  const { data: services = [] } = useQuery({
    queryKey: ['services'],
    queryFn: listServices,
  })

  // ── Items draft
  const [items, setItems] = useState<ItemDraft[]>([])
  const [serviceId, setServiceId] = useState('')
  const [providerId, setProviderId] = useState(initialProviderId ?? providers[0]?.id ?? '')
  const [startTime, setStartTime] = useState(initialTime ?? '09:00')
  const [price, setPrice] = useState('')
  const [notes, setNotes] = useState('')

  // Reset when re-opened
  useEffect(() => {
    if (open) {
      setStep('client')
      setClientQuery('')
      setSelectedClient(null)
      setShowNewClient(false)
      setNewFirst(''); setNewLast(''); setNewPhone(''); setNewEmail(''); setNewLang('en')
      setItems([])
      setServiceId('')
      setProviderId(initialProviderId ?? providers[0]?.id ?? '')
      setStartTime(snapToSlot(initialTime ?? '09:00', slotMinutes))
      setPrice('')
      setNotes('')
    }
  }, [open, initialProviderId, initialTime])

  const selectedService = services.find((s) => s.id === serviceId)
  const selectedProvider = providers.find((p) => p.id === providerId)

  function addItem() {
    if (!selectedService || !selectedProvider) return
    setItems((prev) => [
      ...prev,
      {
        service: selectedService,
        provider: selectedProvider,
        startTime,
        price: price ? parseFloat(price) : (selectedService.default_price ?? 0),
      },
    ])
    // Advance start time for next item — snap to slot grid so the value matches a select option.
    setStartTime(advanceToNextSlot(startTime, selectedService.duration_minutes, slotMinutes))
    setServiceId('')
    setPrice('')
  }

  function removeItem(idx: number) {
    setItems((prev) => prev.filter((_, i) => i !== idx))
  }

  function applyRecommendation(rec: Recommendation) {
    const newItems: ItemDraft[] = []
    for (const ri of rec.items) {
      const svc = services.find((s) => s.id === ri.service_id)
      const prov = providers.find((p) => p.id === ri.provider_id)
      if (!svc || !prov) continue
      newItems.push({
        service: svc,
        provider: prov,
        startTime: ri.start_time,
        price: svc.default_price ?? 0,
      })
    }
    if (newItems.length > 0) {
      setItems(newItems)
    }
  }

  // ── Save
  const mutation = useMutation({
    mutationFn: () =>
      api.post<{ id: string; appointment_date: string; client: { email: string | null } }>('/appointments', {
        client_id: selectedClient!.id,
        appointment_date: date,
        source: 'staff_entered',
        notes: notes || null,
        items: items.map((item, idx) => {
          const [h, m] = item.startTime.split(':').map(Number)
          const localISO = `${date}T${String(h).padStart(2, '0')}:${String(m).padStart(2, '0')}:00`
          return {
            service_id: item.service.id,
            provider_id: item.provider.id,
            sequence: idx + 1,
            start_time: localISO,
            duration_minutes: item.service.duration_minutes,
            price: item.price,
          }
        }),
      }),
    onSuccess: (appt) => {
      qc.invalidateQueries({ queryKey: ['appointments', date] })
      onSaved({ id: appt.id, appointment_date: appt.appointment_date, clientEmail: appt.client.email })
    },
  })

  const canSave = selectedClient && items.length > 0 && !mutation.isPending

  return (
    <Dialog open={open} onOpenChange={(isOpen: boolean) => !isOpen && onClose()}>
      <DialogContent className="max-w-lg">
        <DialogHeader>
          <DialogTitle>{t('appt.new_appt_title', { date: format(new Date(date + 'T12:00:00'), 'MMM d, yyyy') })}</DialogTitle>
        </DialogHeader>

        {/* ── Step 1: Client ───────────────────────── */}
        {step === 'client' && (
          <div className="space-y-3">
            <input
              autoFocus
              autoComplete="off"
              placeholder={t('appt.search_client')}
              value={clientQuery}
              onChange={(e) => setClientQuery(e.target.value)}
              className="w-full border border-input rounded-md px-3 py-2 text-sm bg-background"
            />

            {selectedClient ? (
              <div className="flex items-center justify-between rounded-md border px-3 py-2 bg-muted/40">
                <span className="text-sm font-medium">
                  {selectedClient.first_name} {selectedClient.last_name}
                  {selectedClient.cell_phone && (
                    <span className="text-muted-foreground font-normal ml-2">{selectedClient.cell_phone}</span>
                  )}
                </span>
                <button onClick={() => setSelectedClient(null)} className="text-xs text-muted-foreground hover:text-foreground">{t('appt.change_client')}</button>
              </div>
            ) : showNewClient ? (
              <div className="border rounded-md p-3 space-y-2 bg-muted/20">
                <p className="text-xs font-medium text-muted-foreground">{t('appt.new_client')}</p>
                <div className="grid grid-cols-2 gap-2">
                  <input placeholder={t('auth.first_name') + ' *'} value={newFirst} onChange={(e) => setNewFirst(e.target.value)}
                    className="border border-input rounded-md px-2 py-1.5 text-sm bg-background" />
                  <input placeholder={t('auth.last_name') + ' *'} value={newLast} onChange={(e) => setNewLast(e.target.value)}
                    className="border border-input rounded-md px-2 py-1.5 text-sm bg-background" />
                  <input placeholder={t('auth.cell_phone')} value={newPhone} onChange={(e) => setNewPhone(e.target.value)}
                    className="border border-input rounded-md px-2 py-1.5 text-sm bg-background" />
                  <input placeholder={t('common.email')} value={newEmail} onChange={(e) => setNewEmail(e.target.value)}
                    className="border border-input rounded-md px-2 py-1.5 text-sm bg-background" />
                  <select value={newLang} onChange={e => setNewLang(e.target.value)}
                    className="col-span-2 border border-input rounded-md px-2 py-1.5 text-sm bg-background">
                    <option value="en">{t('translations.lang_en')}</option>
                    <option value="fr">{t('translations.lang_fr')}</option>
                  </select>
                </div>
                <div className="flex gap-2">
                  <Button size="sm" variant="secondary" onClick={() => setShowNewClient(false)} className="flex-1">{t('common.cancel')}</Button>
                  <Button
                    size="sm"
                    className="flex-1"
                    disabled={!newFirst.trim() || !newLast.trim() || creatingClient}
                    onClick={async () => {
                      setCreatingClient(true)
                      try {
                        const client = await createClient({
                          first_name: newFirst.trim(),
                          last_name: newLast.trim(),
                          cell_phone: newPhone.trim() || undefined,
                          email: newEmail.trim() || undefined,
                          language_preference: newLang,
                        })
                        setSelectedClient(client)
                        setShowNewClient(false)
                      } finally {
                        setCreatingClient(false)
                      }
                    }}
                  >
                    {creatingClient ? t('common.saving') : t('appt.new_client')}
                  </Button>
                </div>
              </div>
            ) : (
              debouncedQuery.length >= 1 && (
                <ul className="border rounded-md divide-y max-h-52 overflow-auto">
                  {clientResults.map((c) => (
                    <li key={c.id}>
                      <button
                        className="w-full text-left px-3 py-2 text-sm hover:bg-muted/40"
                        onClick={() => { setSelectedClient(c); setClientQuery('') }}
                      >
                        <span className="font-medium">{c.first_name} {c.last_name}</span>
                        {c.cell_phone && <span className="text-muted-foreground ml-2">{c.cell_phone}</span>}
                      </button>
                    </li>
                  ))}
                </ul>
              )
            )}

            <div className="flex justify-end gap-2">
              {!selectedClient && !showNewClient && (
                <Button variant="outline" onClick={() => { setShowNewClient(true); setNewFirst(clientQuery); setClientQuery('') }}>
                  {t('appt.new_client_button')}
                </Button>
              )}
              <Button disabled={!selectedClient} onClick={() => setStep('items')}>
                {t('common.next')} →
              </Button>
            </div>
          </div>
        )}

        {/* ── Step 2: Services ─────────────────────── */}
        {step === 'items' && (
          <div className="space-y-4">
            <p className="text-sm font-medium">
              {selectedClient!.first_name} {selectedClient!.last_name}
            </p>

            {/* Booking recommendations */}
            {user && (
              <RecommendPanel
                tenantId={user.tenant_id}
                clientId={selectedClient?.id}
                services={items.map((it) => ({
                  serviceId: it.service.id,
                  preferredProviderId: it.provider.id,
                }))}
                desiredDate={date}
                onSelect={applyRecommendation}
              />
            )}

            {/* Added items */}
            {items.length > 0 && (
              <ul className="space-y-1">
                {items.map((item, idx) => (
                  <li key={idx} className="flex items-center justify-between text-sm border rounded-md px-3 py-1.5">
                    <span>
                      <span className="font-medium">{ft(item.startTime)}</span>
                      <span className="mx-1 text-muted-foreground">·</span>
                      {item.service.name}
                      <span className="mx-1 text-muted-foreground">·</span>
                      {item.provider.display_name}
                    </span>
                    <span className="flex items-center gap-2">
                      <span className="text-muted-foreground">${item.price.toFixed(2)}</span>
                      <button onClick={() => removeItem(idx)} className="text-destructive text-xs">✕</button>
                    </span>
                  </li>
                ))}
              </ul>
            )}

            {/* Add item form */}
            <div className="rounded-md border p-3 space-y-2 bg-muted/20">
              <div className="grid grid-cols-2 gap-2">
                <div>
                  <label className="text-xs text-muted-foreground">{t('appt.service_label')}</label>
                  <select
                    value={serviceId}
                    onChange={(e) => {
                      setServiceId(e.target.value)
                      const svc = services.find((s) => s.id === e.target.value)
                      if (svc?.default_price) setPrice(String(svc.default_price))
                    }}
                    className="w-full border border-input rounded-md px-2 py-1.5 text-sm bg-background mt-0.5"
                  >
                    <option value="">{t('convert.select_provider')}</option>
                    {['Styling', 'Colouring', 'Extensions'].map((cat) => (
                      <optgroup key={cat} label={cat}>
                        {services.filter((s) => s.category_name === cat).map((s) => (
                          <option key={s.id} value={s.id}>{s.name} ({s.duration_minutes}m)</option>
                        ))}
                      </optgroup>
                    ))}
                  </select>
                </div>
                <div>
                  <label className="text-xs text-muted-foreground">{t('appt.provider_label')}</label>
                  <select
                    value={providerId}
                    onChange={(e) => setProviderId(e.target.value)}
                    className="w-full border border-input rounded-md px-2 py-1.5 text-sm bg-background mt-0.5"
                  >
                    <option value="">{t('convert.select_provider')}</option>
                    {providers.filter((p) => p.has_appointments).map((p) => (
                      <option key={p.id} value={p.id}>{p.display_name}</option>
                    ))}
                  </select>
                </div>
                <div>
                  <label className="text-xs text-muted-foreground">{t('appt.start_time')}</label>
                  <select
                    value={startTime}
                    onChange={(e) => setStartTime(e.target.value)}
                    className="w-full border border-input rounded-md px-2 py-1.5 text-sm bg-background mt-0.5"
                  >
                    {Array.from({ length: (22 * 60) / slotMinutes - (8 * 60) / slotMinutes }, (_, i) => {
                      const totalMins = 8 * 60 + i * slotMinutes
                      const h = Math.floor(totalMins / 60)
                      const m = totalMins % 60
                      const val = `${String(h).padStart(2, '0')}:${String(m).padStart(2, '0')}`
                      return <option key={val} value={val}>{ft(val)}</option>
                    })}
                  </select>
                </div>
                <div>
                  <label className="text-xs text-muted-foreground">{t('appt.price_label')}</label>
                  <input
                    type="text"
                    inputMode="decimal"
                    value={price}
                    onChange={(e) => setPrice(e.target.value)}
                    placeholder={selectedService?.default_price?.toFixed(2) ?? '0.00'}
                    className="w-full border border-input rounded-md px-2 py-1.5 text-sm bg-background mt-0.5"
                  />
                </div>
              </div>
              <Button
                size="sm"
                variant="secondary"
                disabled={!serviceId || !providerId}
                onClick={addItem}
                className="w-full"
              >
                {t('appt.add_service')}
              </Button>
            </div>

            <div>
              <label className="text-xs text-muted-foreground">{t('common.notes')}</label>
              <textarea
                value={notes}
                onChange={(e) => setNotes(e.target.value)}
                rows={2}
                placeholder={t('appt.notes_optional')}
                className="w-full border border-input rounded-md px-3 py-2 text-sm bg-background mt-0.5 resize-none"
              />
            </div>

            <div className="flex justify-between">
              <Button variant="ghost" onClick={() => setStep('client')}>← {t('common.back')}</Button>
              <Button
                disabled={items.length === 0 && (!serviceId || !providerId)}
                onClick={() => {
                  // Auto-add a complete in-progress entry so users don't lose it by clicking Review.
                  if (serviceId && providerId) addItem()
                  setStep('confirm')
                }}
              >
                {t('common.next')} →
              </Button>
            </div>
          </div>
        )}

        {/* ── Step 3: Confirm ──────────────────────── */}
        {step === 'confirm' && (
          <div className="space-y-4">
            <div className="rounded-md border p-3 space-y-1">
              <p className="font-medium text-sm">
                {selectedClient!.first_name} {selectedClient!.last_name}
              </p>
              {items.map((item, idx) => (
                <p key={idx} className="text-sm text-muted-foreground">
                  {ft(item.startTime)} · {item.service.name} · {item.provider.display_name} · <span className="text-foreground">${item.price.toFixed(2)}</span>
                </p>
              ))}
              {notes && <p className="text-xs text-muted-foreground italic mt-1">{notes}</p>}
            </div>

            {(() => {
              const conflicts = items.filter((item) => {
                const ph = providerHours.find((h) => h.provider_id === item.provider.id)
                return ph ? isItemOutsideHours(item.startTime, item.service.duration_minutes, ph) : false
              })
              return conflicts.length > 0 ? (
                <div className="rounded-md border border-amber-300 bg-amber-50 px-3 py-2 text-sm text-amber-800">
                  <p className="font-medium mb-0.5">{t('appt.outside_hours')}</p>
                  {conflicts.map((item, i) => (
                    <p key={i} className="text-xs">
                      {item.provider.display_name} · {item.startTime} · {item.service.name}
                    </p>
                  ))}
                </div>
              ) : null
            })()}

            {mutation.isError && (
              <p className="text-sm text-destructive">
                {mutation.error instanceof Error ? mutation.error.message : t('appt.save_failed')}
              </p>
            )}

            <div className="flex justify-between">
              <Button variant="ghost" onClick={() => setStep('items')}>← {t('common.back')}</Button>
              <Button disabled={!canSave} onClick={() => mutation.mutate()}>
                {mutation.isPending ? t('common.saving') : t('appt.confirm_appointment')}
              </Button>
            </div>
          </div>
        )}
      </DialogContent>
    </Dialog>
  )
}
