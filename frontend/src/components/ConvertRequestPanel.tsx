import { useState, useEffect, useRef } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import { searchClients, createClient, checkDuplicateClients, type Client } from '@/api/clients'
import { listServices } from '@/api/services'
import { listProviders } from '@/api/providers'
import { listAppointments, type AppointmentItem } from '@/api/appointments'
import { type AppointmentRequest, convertRequest } from '@/api/appointmentRequests'
import { Button } from '@/components/ui/button'
import { Label } from '@/components/ui/label'
import { useAuth } from '@/store/auth'
import { type Recommendation } from '@/api/scheduling'
import RecommendPanel from '@/components/scheduling/RecommendPanel'

interface ItemFormState {
  requestItemId: string
  serviceId: string
  providerId: string
  startTime: string
  durationMinutes: number
  price: string
  notes: string
}

interface Props {
  request: AppointmentRequest
  date: string
  onDateChange: (date: string) => void
  onClose: () => void
  onConverted: (appointmentDate: string) => void
}

export default function ConvertRequestPanel({ request, date, onDateChange, onClose, onConverted }: Props) {
  const { t } = useTranslation()
  const qc = useQueryClient()
  const { user } = useAuth()

  const [clientMode, setClientMode] = useState<'new' | 'existing'>('new')
  const [newFirst, setNewFirst] = useState('')
  const [newLast, setNewLast] = useState('')
  const [newPhone, setNewPhone] = useState('')
  const [newEmail, setNewEmail] = useState('')
  const [newLangPref, setNewLangPref] = useState('en')
  const [clientQuery, setClientQuery] = useState('')
  const [selectedClient, setSelectedClient] = useState<Client | null>(null)
  const [debouncedQuery, setDebouncedQuery] = useState('')
  const searchTimer = useRef<ReturnType<typeof setTimeout> | null>(null)

  const [apptNotes, setApptNotes] = useState('')
  const [items, setItems] = useState<ItemFormState[]>([])
  const [error, setError] = useState<string | null>(null)
  const [clashWarning, setClashWarning] = useState<string[] | null>(null)
  const [duplicates, setDuplicates] = useState<Client[]>([])
  const [bypassDuplicateCheck, setBypassDuplicateCheck] = useState(false)

  const { data: services = [] } = useQuery({ queryKey: ['services'], queryFn: listServices })
  const { data: providers = [] } = useQuery({ queryKey: ['providers'], queryFn: listProviders })
  const { data: clientResults = [] } = useQuery({
    queryKey: ['clients', debouncedQuery],
    queryFn: () => searchClients(debouncedQuery),
    enabled: debouncedQuery.length >= 1,
  })

  useEffect(() => {
    if (request.client_id) {
      setClientMode('existing')
      setSelectedClient({
        id: request.client_id,
        first_name: request.first_name,
        last_name: request.last_name,
        email: request.email,
        cell_phone: request.phone ?? null,
        special_instructions: null,
        pronouns: null,
        no_show_count: 0,
        late_cancellation_count: 0,
        is_vip: false,
        language_preference: 'en',
      })
    } else {
      setClientMode('new')
      setSelectedClient(null)
    }
    setNewFirst(request.first_name)
    setNewLast(request.last_name)
    setNewEmail(request.email)
    setNewPhone(request.phone ?? '')
    setClientQuery('')
    setApptNotes('')
    setError(null)
    setDuplicates([])
    setBypassDuplicateCheck(false)
    setItems(request.items.map((ri, idx) => {
      const offsetMinutes = idx * 60
      const h = Math.floor(offsetMinutes / 60) + 9
      const m = offsetMinutes % 60
      return {
        requestItemId: ri.id,
        serviceId: '',
        providerId: '',
        startTime: `${String(h).padStart(2, '0')}:${String(m).padStart(2, '0')}`,
        durationMinutes: 60,
        price: '',
        notes: '',
      }
    }))
  }, [request.id])

  useEffect(() => {
    if (searchTimer.current) clearTimeout(searchTimer.current)
    searchTimer.current = setTimeout(() => setDebouncedQuery(clientQuery), 250)
  }, [clientQuery])

  // Auto-match request service/provider names to catalog IDs so recommendations
  // appear without staff having to manually pick from dropdowns first.
  useEffect(() => {
    if (services.length === 0) return
    setItems(prev => {
      let changed = false
      const next = prev.map((item, idx) => {
        if (item.serviceId) return item  // respect manual selection
        const reqName = (request.items[idx]?.service_name ?? '').toLowerCase()
        const reqProv = (request.items[idx]?.preferred_provider_name ?? '').toLowerCase()

        const matchSvc = services.find(s => s.name.toLowerCase() === reqName)
          ?? services.find(s => s.name.toLowerCase().includes(reqName) || reqName.includes(s.name.toLowerCase()))
        if (!matchSvc) return item

        const matchProv = reqProv
          ? (providers.find(p => p.display_name.toLowerCase() === reqProv)
              ?? providers.find(p => p.display_name.toLowerCase().includes(reqProv)))
          : undefined

        changed = true
        return {
          ...item,
          serviceId: matchSvc.id,
          durationMinutes: matchSvc.duration_minutes ?? item.durationMinutes,
          price: matchSvc.default_price != null ? String(matchSvc.default_price) : item.price,
          providerId: matchProv ? matchProv.id : item.providerId,
        }
      })

      if (!changed) return prev

      // Cascade start times from matched durations
      for (let i = 0; i < next.length - 1; i++) {
        const [h, m] = next[i].startTime.split(':').map(Number)
        const endMins = h * 60 + m + next[i].durationMinutes
        next[i + 1] = {
          ...next[i + 1],
          startTime: `${String(Math.floor(endMins / 60)).padStart(2, '0')}:${String(endMins % 60).padStart(2, '0')}`,
        }
      }

      return next
    })
  }, [services, providers, request.id])

  function updateItem(idx: number, patch: Partial<ItemFormState>) {
    setItems(prev => {
      const next = prev.map((it, i) => i === idx ? { ...it, ...patch } : it)
      if ('startTime' in patch || 'durationMinutes' in patch) {
        for (let i = idx; i < next.length - 1; i++) {
          const [h, m] = next[i].startTime.split(':').map(Number)
          const endMins = h * 60 + m + next[i].durationMinutes
          const nh = Math.floor(endMins / 60)
          const nm = endMins % 60
          next[i + 1] = { ...next[i + 1], startTime: `${String(nh).padStart(2, '0')}:${String(nm).padStart(2, '0')}` }
        }
      }
      return next
    })
  }

  function handleServiceChange(idx: number, serviceId: string) {
    const svc = services.find(s => s.id === serviceId)
    const newDuration = svc?.duration_minutes ?? 60
    setItems(prev => {
      const next = prev.map((it, i) => i === idx ? {
        ...it,
        serviceId,
        durationMinutes: newDuration,
        price: svc?.default_price != null ? String(svc.default_price) : it.price,
      } : it)
      for (let i = idx + 1; i < next.length; i++) {
        const prev_item = next[i - 1]
        const [ph, pm] = prev_item.startTime.split(':').map(Number)
        const nextStart = ph * 60 + pm + prev_item.durationMinutes
        const nh = Math.floor(nextStart / 60)
        const nm = nextStart % 60
        next[i] = { ...next[i], startTime: `${String(nh).padStart(2, '0')}:${String(nm).padStart(2, '0')}` }
      }
      return next
    })
  }

  const activeProviders = providers.filter(p => p.has_appointments)
  const serviceCategories = Array.from(new Set(services.map(s => s.category_name)))

  const { mutateAsync, isPending } = useMutation({
    mutationFn: async () => {
      let clientId: string | undefined
      if (clientMode === 'existing') {
        if (!selectedClient) throw new Error('Select an existing client')
        clientId = selectedClient.id
      } else {
        if (!newFirst.trim() || !newLast.trim()) throw new Error('First and last name required')
        const created = await createClient({
          first_name: newFirst.trim(),
          last_name: newLast.trim(),
          cell_phone: newPhone.trim() || undefined,
          email: newEmail.trim() || undefined,
          language_preference: newLangPref,
        })
        clientId = created.id
      }
      for (const item of items) {
        if (!item.serviceId) throw new Error('Select a service for each item')
        if (!item.providerId) throw new Error('Select a provider for each item')
      }
      return convertRequest(request.id, {
        client_id: clientId,
        appointment_date: date,
        notes: apptNotes.trim() || undefined,
        items: items.map((it, idx) => ({
          request_item_id: it.requestItemId,
          service_id: it.serviceId,
          provider_id: it.providerId,
          sequence: idx + 1,
          start_time: `${date}T${it.startTime}:00`,
          duration_minutes: it.durationMinutes,
          price: parseFloat(it.price) || 0,
          notes: it.notes.trim() || undefined,
        })),
      })
    },
    onSuccess: result => {
      if (result) {
        qc.invalidateQueries({ queryKey: ['all-requests'] })
        qc.invalidateQueries({ queryKey: ['requests', 'new'] })
        qc.invalidateQueries({ queryKey: ['appointments', result.appointment_date] })
        onConverted(result.appointment_date)
      }
    },
  })

  function detectClashes(existingItems: AppointmentItem[]): string[] {
    const seen = new Set<string>()
    for (const item of items) {
      if (!item.providerId) continue
      const [nh, nm] = item.startTime.split(':').map(Number)
      const newStart = nh * 60 + nm
      const newEnd = newStart + item.durationMinutes
      for (const ex of existingItems) {
        if (ex.provider.id !== item.providerId) continue
        const timePart = ex.start_time.split('T')[1] ?? ex.start_time
        const [eh, em] = timePart.split(':').map(Number)
        const exStart = eh * 60 + em
        const exEnd = exStart + (ex.duration_override_minutes ?? ex.duration_minutes)
        if (newStart < exEnd && newEnd > exStart) {
          const provider = activeProviders.find(p => p.id === item.providerId)
          seen.add(`${provider?.display_name ?? 'Provider'} at ${item.startTime}`)
        }
      }
    }
    return Array.from(seen)
  }

  function applyRecommendation(rec: Recommendation) {
    setItems(prev =>
      rec.items.map((ri, idx) => {
        const existing = prev[idx]
        const svc = services.find(s => s.id === ri.service_id)
        return {
          requestItemId: existing?.requestItemId ?? '',
          serviceId: ri.service_id,
          providerId: ri.provider_id,
          startTime: ri.start_time,
          durationMinutes: ri.duration_minutes,
          price: svc?.default_price != null ? String(svc.default_price) : existing?.price ?? '',
          notes: existing?.notes ?? '',
        }
      })
    )
  }

  async function handleSubmit(force = false) {
    setError(null)
    setClashWarning(null)
    try {
      if (clientMode === 'new' && !bypassDuplicateCheck) {
        const matches = await checkDuplicateClients(newEmail.trim(), newPhone.trim())
        if (matches.length > 0) {
          const exactMatch = matches.find(m =>
            m.first_name.trim().toLowerCase() === newFirst.trim().toLowerCase() &&
            m.last_name.trim().toLowerCase() === newLast.trim().toLowerCase()
          )
          if (exactMatch) {
            setError('A client with this exact name and contact information already exists.')
            return
          }
          setDuplicates(matches)
          return
        }
      }
      if (!force && date) {
        const existing = await listAppointments(date)
        const existingItems = existing.flatMap(a => a.items)
        const clashes = detectClashes(existingItems)
        if (clashes.length > 0) {
          setClashWarning(clashes)
          return
        }
      }
      await mutateAsync()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Conversion failed')
    }
  }

  const clientReady = clientMode === 'new'
    ? newFirst.trim().length > 0 && newLast.trim().length > 0
    : selectedClient !== null
  const isValid = clientReady && date.length > 0 && items.length > 0 && items.every(it => it.serviceId && it.providerId)

  return (
    <div className="fixed inset-y-0 right-0 z-40 w-[420px] bg-white shadow-2xl flex flex-col border-l">
      {/* Header */}
      <div className="flex items-center justify-between px-5 py-4 border-b flex-shrink-0">
        <div>
          <h2 className="text-base font-semibold">{t('convert.title')}</h2>
          <p className="text-xs text-muted-foreground mt-0.5">
            {request.first_name} {request.last_name} · requested{' '}
            {new Date(request.desired_date + 'T00:00:00').toLocaleDateString('en-CA', {
              weekday: 'short', month: 'short', day: 'numeric',
            })}
            {request.desired_time_note && ` · ${request.desired_time_note}`}
          </p>
        </div>
        <button onClick={onClose} className="text-muted-foreground hover:text-foreground text-xl leading-none ml-3">×</button>
      </div>

      {/* Body */}
      <div className="flex-1 overflow-y-auto p-5 space-y-5">

        {/* Special note */}
        {request.special_note && (
          <div className="rounded-md bg-muted px-3 py-2 text-sm text-muted-foreground italic">
            "{request.special_note}"
          </div>
        )}

        {/* Booking recommendations — pre-populated from request */}
        {user && date && items.some(it => it.serviceId) && (
          <RecommendPanel
            tenantId={user.tenant_id}
            services={items.map(it => ({
              serviceId: it.serviceId,
              preferredProviderId: it.providerId || undefined,
            })).filter(s => s.serviceId)}
            desiredDate={date}
            onSelect={applyRecommendation}
          />
        )}

        {/* Client */}
        <div className="space-y-2">
          <Label>Client</Label>
          <div className="flex gap-2">
            <Button size="sm" variant={clientMode === 'new' ? 'default' : 'outline'} onClick={() => setClientMode('new')}>
              {t('convert.tab_create_new')}
            </Button>
            <Button size="sm" variant={clientMode === 'existing' ? 'default' : 'outline'} onClick={() => setClientMode('existing')}>
              {t('convert.tab_link_existing')}
            </Button>
          </div>

          {clientMode === 'new' && (
            <div className="grid grid-cols-2 gap-2 pt-1">
              <input placeholder={t('auth.first_name') + ' *'} value={newFirst} onChange={e => setNewFirst(e.target.value)}
                className="border border-input rounded-md px-3 py-1.5 text-sm bg-background" />
              <input placeholder={t('auth.last_name') + ' *'} value={newLast} onChange={e => setNewLast(e.target.value)}
                className="border border-input rounded-md px-3 py-1.5 text-sm bg-background" />
              <input placeholder={t('auth.cell_phone')} value={newPhone} onChange={e => setNewPhone(e.target.value)}
                className="border border-input rounded-md px-3 py-1.5 text-sm bg-background" />
              <input placeholder={t('common.email')} value={newEmail} onChange={e => setNewEmail(e.target.value)}
                className="border border-input rounded-md px-3 py-1.5 text-sm bg-background" />
              <select
                value={newLangPref}
                onChange={e => setNewLangPref(e.target.value)}
                className="col-span-2 border border-input rounded-md px-3 py-1.5 text-sm bg-background"
              >
                <option value="en">{t('translations.lang_en')}</option>
                <option value="fr">{t('translations.lang_fr')}</option>
              </select>
            </div>
          )}

          {clientMode === 'existing' && (
            <div className="space-y-1 pt-1">
              {selectedClient ? (
                <div className="flex items-center justify-between rounded-md border px-3 py-2 bg-muted/40">
                  <div className="text-sm">
                    <span className="font-medium">{selectedClient.first_name} {selectedClient.last_name}</span>
                    {selectedClient.cell_phone && <span className="text-muted-foreground ml-2">{selectedClient.cell_phone}</span>}
                    {selectedClient.email && <span className="text-muted-foreground ml-2">{selectedClient.email}</span>}
                  </div>
                  <button onClick={() => setSelectedClient(null)} className="text-xs text-muted-foreground hover:text-foreground ml-3 shrink-0">{t('appt.change_client')}</button>
                </div>
              ) : (
                <>
                  <input placeholder={t('convert.search_placeholder')} value={clientQuery} onChange={e => setClientQuery(e.target.value)}
                    className="w-full border border-input rounded-md px-3 py-1.5 text-sm bg-background" />
                  {debouncedQuery.length >= 1 && (
                    <ul className="border rounded-md divide-y max-h-36 overflow-auto">
                      {clientResults.length === 0 ? (
                        <li className="px-3 py-2 text-sm text-muted-foreground">{t('convert.no_clients')}</li>
                      ) : clientResults.map(c => (
                        <li key={c.id}>
                          <button className="w-full text-left px-3 py-2 text-sm hover:bg-muted/40"
                            onClick={() => { setSelectedClient(c); setClientQuery('') }}>
                            <span className="font-medium">{c.first_name} {c.last_name}</span>
                            {c.cell_phone && <span className="text-muted-foreground ml-2">{c.cell_phone}</span>}
                            {c.email && <span className="text-muted-foreground ml-2">{c.email}</span>}
                          </button>
                        </li>
                      ))}
                    </ul>
                  )}
                </>
              )}
            </div>
          )}
        </div>

        {/* Date — drives the appointment book */}
        <div className="space-y-1.5">
          <Label>{t('convert.appt_date')}</Label>
          <input
            type="date"
            value={date}
            onChange={e => onDateChange(e.target.value)}
            className="border border-input rounded-md px-3 py-1.5 text-sm bg-background"
          />
          <p className="text-xs text-muted-foreground">{t('convert.book_updates')}</p>
        </div>

        {/* Service items */}
        <div className="space-y-3">
          <Label>{t('convert.services_label')}</Label>
          {items.map((item, idx) => {
            const reqItem = request.items[idx]
            return (
              <div key={item.requestItemId} className="rounded-md border p-3 space-y-2">
                <p className="text-xs text-muted-foreground">
                  {t('convert.requested_service', { service: reqItem.service_name, provider: reqItem.preferred_provider_name })}
                </p>
                <div className="grid grid-cols-2 gap-2">
                  <div>
                    <label className="text-xs text-muted-foreground">Service</label>
                    <select value={item.serviceId} onChange={e => handleServiceChange(idx, e.target.value)}
                      className="w-full border border-input rounded-md px-2 py-1.5 text-sm bg-background mt-0.5">
                      <option value="">{t('convert.select_service')}</option>
                      {serviceCategories.map(cat => (
                        <optgroup key={cat} label={cat}>
                          {services.filter(s => s.category_name === cat).map(s => (
                            <option key={s.id} value={s.id}>{s.name} ({s.duration_minutes}m)</option>
                          ))}
                        </optgroup>
                      ))}
                    </select>
                  </div>
                  <div>
                    <label className="text-xs text-muted-foreground">Provider</label>
                    <select value={item.providerId} onChange={e => updateItem(idx, { providerId: e.target.value })}
                      className="w-full border border-input rounded-md px-2 py-1.5 text-sm bg-background mt-0.5">
                      <option value="">{t('convert.select_service')}</option>
                      {activeProviders.map(p => (
                        <option key={p.id} value={p.id}>{p.display_name}</option>
                      ))}
                    </select>
                  </div>
                  <div>
                    <label className="text-xs text-muted-foreground">Start time</label>
                    <input type="time" value={item.startTime} onChange={e => updateItem(idx, { startTime: e.target.value })}
                      className="w-full border border-input rounded-md px-2 py-1.5 text-sm bg-background mt-0.5" />
                  </div>
                  <div>
                    <label className="text-xs text-muted-foreground">{t('convert.duration_label')}</label>
                    <input type="number" min="5" step="5" value={item.durationMinutes}
                      onChange={e => updateItem(idx, { durationMinutes: parseInt(e.target.value) || 60 })}
                      className="w-full border border-input rounded-md px-2 py-1.5 text-sm bg-background mt-0.5" />
                  </div>
                  <div>
                    <label className="text-xs text-muted-foreground">Price ($)</label>
                    <input type="number" min="0" step="0.01" value={item.price} placeholder="0.00"
                      onChange={e => updateItem(idx, { price: e.target.value })}
                      className="w-full border border-input rounded-md px-2 py-1.5 text-sm bg-background mt-0.5" />
                  </div>
                  <div>
                    <label className="text-xs text-muted-foreground">{t('common.notes')}</label>
                    <input type="text" value={item.notes} placeholder={t('convert.notes_placeholder')}
                      onChange={e => updateItem(idx, { notes: e.target.value })}
                      className="w-full border border-input rounded-md px-2 py-1.5 text-sm bg-background mt-0.5" />
                  </div>
                </div>
              </div>
            )
          })}
        </div>

        {/* Appointment notes */}
        <div className="space-y-1.5">
          <Label htmlFor="appt-notes">{t('convert.appt_notes')}</Label>
          <textarea id="appt-notes" value={apptNotes} onChange={e => setApptNotes(e.target.value)}
            rows={2} placeholder={t('convert.notes_placeholder')}
            className="w-full border border-input rounded-md px-3 py-2 text-sm bg-background resize-none" />
        </div>

        {duplicates.length > 0 && (
          <div className="rounded-md border border-amber-300 bg-amber-50 px-3 py-2 text-sm text-amber-800 space-y-1">
            <p className="font-medium">{t('convert.possible_duplicate')}</p>
            {duplicates.map(d => (
              <p key={d.id} className="text-xs font-medium">
                {d.first_name} {d.last_name}{d.cell_phone && ` · ${d.cell_phone}`}{d.email && ` · ${d.email}`}
              </p>
            ))}
            <p className="text-xs mt-1">{t('convert.duplicate_confirm')}</p>
          </div>
        )}

        {clashWarning && (
          <div className="rounded-md border border-amber-300 bg-amber-50 px-3 py-2 text-sm text-amber-800">
            <p className="font-medium mb-1">{t('convert.scheduling_conflict')}</p>
            {clashWarning.map((c, i) => <p key={i} className="text-xs">{t('convert.conflict_detail', { provider: c.split(' at ')[0], time: c.split(' at ')[1] })}</p>)}
            <p className="text-xs mt-1">{t('convert.book_anyway')}</p>
          </div>
        )}

        {error && <p className="text-sm text-destructive">{error}</p>}
      </div>

      {/* Footer */}
      <div className="border-t px-5 py-4 flex gap-2 flex-shrink-0">
        <Button variant="outline" onClick={onClose} disabled={isPending}>{t('common.cancel')}</Button>
        {duplicates.length > 0 ? (
          <>
            <Button variant="outline" onClick={() => setDuplicates([])} disabled={isPending}>{t('common.back')}</Button>
            <Button onClick={() => { setBypassDuplicateCheck(true); setDuplicates([]); handleSubmit() }} disabled={isPending}>
              {t('convert.create_anyway')}
            </Button>
          </>
        ) : clashWarning ? (
          <>
            <Button variant="outline" onClick={() => setClashWarning(null)} disabled={isPending}>{t('common.back')}</Button>
            <Button onClick={() => handleSubmit(true)} disabled={isPending}>
              {isPending ? t('convert.creating') : t('convert.book_anyway')}
            </Button>
          </>
        ) : (
          <Button onClick={() => handleSubmit()} disabled={!isValid || isPending} className="flex-1">
            {isPending ? t('convert.creating') : t('appt.confirm_appointment')}
          </Button>
        )}
      </div>
    </div>
  )
}
