import { useState, useRef, useEffect } from 'react'
import { useSearchParams, useNavigate } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import { useDateLocale } from '@/lib/dateLocale'
import {
  type Visit,
  type ColourNote,
  searchClients,
  getClient,
  getClientHistory,
  listColourNotes,
  createColourNote,
  updateClient,
  updateClientNotes,
  deleteClient,
} from '@/api/clients'
import { updateAppointmentStatus } from '@/api/appointments'
import { listProviders } from '@/api/providers'
import { useTimeFormat } from '@/lib/timeFormat'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Star, ChevronRight } from 'lucide-react'

// ── Client list ───────────────────────────────────────────────────────────────

function ClientList({
  selectedId,
  onSelect,
}: {
  selectedId: string | null
  onSelect: (id: string) => void
}) {
  const { t } = useTranslation()
  const [query, setQuery] = useState('')
  const [debouncedQ, setDebouncedQ] = useState('')
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null)

  useEffect(() => {
    if (timer.current) clearTimeout(timer.current)
    timer.current = setTimeout(() => setDebouncedQ(query), 200)
  }, [query])

  const { data: clients = [], isLoading } = useQuery({
    queryKey: ['clients', debouncedQ],
    queryFn: () => searchClients(debouncedQ),
  })

  const navigate = useNavigate()

  return (
    <div className="flex flex-col h-full border-r bg-white">
      <div className="p-3 border-b space-y-2">
        <input
          type="search"
          placeholder={t('clients.search_placeholder')}
          value={query}
          onChange={e => setQuery(e.target.value)}
          className="w-full border border-input rounded-md px-3 py-1.5 text-sm bg-background"
        />
        <button
          onClick={() => navigate('/clients/cleanup')}
          className="w-full text-xs text-muted-foreground hover:text-foreground text-left px-1 transition-colors"
        >
          {t('clients.manage_duplicates')}
        </button>
      </div>

      <div className="flex-1 overflow-auto">
        {isLoading ? (
          <p className="p-4 text-sm text-muted-foreground">{t('common.loading')}</p>
        ) : clients.length === 0 ? (
          <p className="p-4 text-sm text-muted-foreground">
            {debouncedQ ? t('clients.no_clients_found') : t('clients.no_clients_yet')}
          </p>
        ) : (
          <ul>
            {clients.map(c => (
              <li key={c.id}>
                <button
                  onClick={() => onSelect(c.id)}
                  className={`w-full text-left px-4 py-3 flex items-center gap-2 hover:bg-muted/40 transition-colors border-b border-muted/60
                    ${selectedId === c.id ? 'bg-muted/60' : ''}`}
                >
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-1.5">
                      <span className="text-sm font-medium truncate">
                        {c.last_name}, {c.first_name}
                      </span>
                      {c.is_vip && <Star size={11} className="text-amber-500 fill-amber-500 flex-shrink-0" />}
                    </div>
                    <p className="text-xs text-muted-foreground truncate">
                      {[c.cell_phone, c.email].filter(Boolean).join(' · ') || t('clients.no_contact')}
                    </p>
                  </div>
                  {(c.no_show_count > 0 || c.late_cancellation_count > 0) && (
                    <span className="text-xs text-destructive flex-shrink-0">
                      {c.no_show_count > 0 && `${c.no_show_count} NS`}
                      {c.no_show_count > 0 && c.late_cancellation_count > 0 && ' · '}
                      {c.late_cancellation_count > 0 && `${c.late_cancellation_count} LC`}
                    </span>
                  )}
                  <ChevronRight size={14} className="text-muted-foreground flex-shrink-0" />
                </button>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  )
}

// ── Colour notes ──────────────────────────────────────────────────────────────

function ColourNotes({ clientId }: { clientId: string }) {
  const { t } = useTranslation()
  const { bcp47 } = useDateLocale()
  const qc = useQueryClient()
  const [newDate, setNewDate] = useState(() => new Date().toISOString().slice(0, 10))
  const [newText, setNewText] = useState('')
  const [adding, setAdding] = useState(false)

  const { data: notes = [] } = useQuery({
    queryKey: ['colour-notes', clientId],
    queryFn: () => listColourNotes(clientId),
  })

  const { mutate, isPending } = useMutation({
    mutationFn: () => createColourNote(clientId, newDate, newText.trim()),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['colour-notes', clientId] })
      setNewText('')
      setAdding(false)
    },
  })

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-medium">Colour notes</h3>
        {!adding && (
          <Button size="sm" variant="outline" onClick={() => setAdding(true)}>
            Add note
          </Button>
        )}
      </div>

      {adding && (
        <div className="rounded-md border p-3 space-y-2">
          <input
            type="date"
            value={newDate}
            onChange={e => setNewDate(e.target.value)}
            className="border border-input rounded-md px-2 py-1 text-sm bg-background"
          />
          <textarea
            value={newText}
            onChange={e => setNewText(e.target.value)}
            placeholder="Formula, developer, timing…"
            rows={3}
            className="w-full border border-input rounded-md px-3 py-2 text-sm bg-background resize-none"
          />
          <div className="flex gap-2">
            <Button
              size="sm"
              onClick={() => mutate()}
              disabled={!newText.trim() || isPending}
            >
              {isPending ? t('common.saving') : t('common.save')}
            </Button>
            <Button size="sm" variant="outline" onClick={() => setAdding(false)} disabled={isPending}>
              {t('common.cancel')}
            </Button>
          </div>
        </div>
      )}

      {notes.length === 0 && !adding ? (
        <p className="text-sm text-muted-foreground">No colour notes yet.</p>
      ) : (
        <ul className="space-y-2">
          {notes.map((n: ColourNote) => (
            <li key={n.id} className="rounded-md border p-3 text-sm space-y-1">
              <p className="text-xs text-muted-foreground font-medium">
                {new Date(n.note_date + 'T00:00:00').toLocaleDateString(bcp47, {
                  year: 'numeric', month: 'short', day: 'numeric',
                })}
              </p>
              <p className="whitespace-pre-wrap">{n.note_text}</p>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}

// ── Visit history ─────────────────────────────────────────────────────────────

const VISIT_STATUS_LABEL: Record<string, string> = {
  confirmed: 'Confirmed',
  completed: 'Completed',
  cancelled: 'Cancelled',
  no_show: 'No-show',
  in_progress: 'In progress',
}

function VisitRow({ visit, onCancel }: { visit: Visit; onCancel?: (id: string) => void }) {
  const [confirmCancel, setConfirmCancel] = useState(false)
  const { formatTime: ft } = useTimeFormat()
  const { bcp47 } = useDateLocale()
  const navigate = useNavigate()
  const todayStr = new Date().toISOString().slice(0, 10)
  const isUpcoming = visit.date >= todayStr
  const isNavigable = visit.status !== 'cancelled' && visit.status !== 'no_show'

  return (
    <li
      className={`rounded-md border p-3 text-sm space-y-1 ${isNavigable ? 'cursor-pointer hover:bg-muted/30 transition-colors' : ''}`}
      onClick={() => { if (isNavigable) navigate(`/appointments?date=${visit.date}&appointment=${visit.appointment_id}`) }}
    >
      <div className="flex items-center justify-between gap-2">
        <span className="font-medium">
          {new Date(visit.date + 'T00:00:00').toLocaleDateString(bcp47, {
            weekday: 'short', year: 'numeric', month: 'short', day: 'numeric',
          })}
        </span>
        <div className="flex items-center gap-2">
          <span className="text-xs text-muted-foreground">
            {VISIT_STATUS_LABEL[visit.status] ?? visit.status}
          </span>
          {isUpcoming && visit.status === 'confirmed' && onCancel && (
            confirmCancel ? (
              <span className="flex items-center gap-1" onClick={e => e.stopPropagation()}>
                <span className="text-xs text-muted-foreground">Sure?</span>
                <button onClick={() => { onCancel(visit.appointment_id); setConfirmCancel(false) }}
                  className="text-xs text-destructive hover:underline">Yes</button>
                <button onClick={() => setConfirmCancel(false)}
                  className="text-xs text-muted-foreground hover:underline">No</button>
              </span>
            ) : (
              <button onClick={e => { e.stopPropagation(); setConfirmCancel(true) }}
                className="text-xs text-destructive hover:underline">Cancel</button>
            )
          )}
        </div>
      </div>
      <ul className="space-y-0.5">
        {visit.items.map((item, i) => (
          <li key={i} className="text-muted-foreground text-xs">
            <span className="tabular-nums text-foreground">
              {ft(item.start_time)}
            </span>
            {' · '}{item.service_name} — {item.provider_name}
            {' · '}${item.price.toFixed(2)}
          </li>
        ))}
      </ul>
      {visit.items.length > 0 && (
        <p className="text-xs font-medium pt-0.5">
          Total: ${visit.items.reduce((sum, i) => sum + i.price, 0).toFixed(2)}
        </p>
      )}
    </li>
  )
}

function VisitHistory({ clientId }: { clientId: string }) {
  const { t } = useTranslation()
  const qc = useQueryClient()
  const todayStr = new Date().toISOString().slice(0, 10)

  const { data: visits = [], isLoading } = useQuery({
    queryKey: ['client-history', clientId],
    queryFn: () => getClientHistory(clientId),
  })

  const { mutate: cancelAppt } = useMutation({
    mutationFn: (appointmentId: string) => updateAppointmentStatus(appointmentId, 'cancelled'),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['client-history', clientId] })
      qc.invalidateQueries({ queryKey: ['appointments'] })
    },
  })

  if (isLoading) return <p className="text-sm text-muted-foreground">{t('common.loading')}</p>
  if (visits.length === 0) return <p className="text-sm text-muted-foreground">No visits yet.</p>

  const upcoming = visits.filter(v => v.date >= todayStr).reverse()
  const past = visits.filter(v => v.date < todayStr)

  return (
    <div className="space-y-5">
      {upcoming.length > 0 && (
        <div className="space-y-2">
          <h3 className="text-xs font-medium text-muted-foreground uppercase tracking-wide">{t('clients.upcoming')}</h3>
          <ul className="space-y-2">
            {upcoming.map(v => <VisitRow key={v.appointment_id} visit={v} onCancel={id => cancelAppt(id)} />)}
          </ul>
        </div>
      )}
      {past.length > 0 && (
        <div className="space-y-2">
          <h3 className="text-xs font-medium text-muted-foreground uppercase tracking-wide">{t('clients.history')}</h3>
          <ul className="space-y-2">
            {past.map(v => <VisitRow key={v.appointment_id} visit={v} />)}
          </ul>
        </div>
      )}
    </div>
  )
}

// ── Client detail panel ───────────────────────────────────────────────────────

type Tab = 'history' | 'colour' | 'notes'

function ClientDetail({ clientId, onDeleted }: { clientId: string; onDeleted: () => void }) {
  const { t } = useTranslation()
  const qc = useQueryClient()
  const [tab, setTab] = useState<Tab>('history')
  const [editingNotes, setEditingNotes] = useState(false)
  const [notesText, setNotesText] = useState('')
  const [confirmDelete, setConfirmDelete] = useState(false)
  const [deleteError, setDeleteError] = useState<string | null>(null)
  const [editingProfile, setEditingProfile] = useState(false)
  const [editFirst, setEditFirst] = useState('')
  const [editLast, setEditLast] = useState('')
  const [editEmail, setEditEmail] = useState('')
  const [editPhone, setEditPhone] = useState('')
  const [editLangPref, setEditLangPref] = useState('en')
  const [editPreferredProvider, setEditPreferredProvider] = useState<string>('')
  const [editError, setEditError] = useState<string | null>(null)

  const { data: providers = [] } = useQuery({
    queryKey: ['providers'],
    queryFn: listProviders,
    staleTime: Infinity,
  })

  const { data: client, isLoading } = useQuery({
    queryKey: ['client', clientId],
    queryFn: () => getClient(clientId),
  })

  useEffect(() => {
    if (client) setNotesText(client.special_instructions ?? '')
  }, [client?.id])

  const { mutate: saveNotes, isPending: savingNotes } = useMutation({
    mutationFn: () => updateClientNotes(clientId, notesText.trim() || null),
    onSuccess: updated => {
      qc.setQueryData(['client', clientId], updated)
      setEditingNotes(false)
    },
  })

  const { mutate: saveProfile, isPending: savingProfile } = useMutation({
    mutationFn: () => updateClient(clientId, {
      first_name: editFirst.trim(),
      last_name: editLast.trim(),
      email: editEmail.trim() || null,
      cell_phone: editPhone.trim() || null,
      language_preference: editLangPref,
      ...(editPreferredProvider
        ? { preferred_provider_id: editPreferredProvider }
        : { clear_preferred_provider: true }),
    }),
    onSuccess: updated => {
      qc.setQueryData(['client', clientId], updated)
      qc.invalidateQueries({ queryKey: ['clients'] })
      setEditingProfile(false)
      setEditError(null)
    },
    onError: (e: Error) => setEditError(e.message || 'Save failed'),
  })

  function startEditProfile() {
    if (!client) return
    setEditFirst(client.first_name)
    setEditLast(client.last_name)
    setEditEmail(client.email ?? '')
    setEditPhone(client.cell_phone ?? '')
    setEditLangPref(client.language_preference ?? 'en')
    setEditPreferredProvider(client.preferred_provider_id ?? '')
    setEditError(null)
    setEditingProfile(true)
  }

  const { mutate: doDelete, isPending: deleting } = useMutation({
    mutationFn: () => deleteClient(clientId),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['clients'] })
      onDeleted()
    },
    onError: (e: Error) => {
      setDeleteError(e.message || 'Could not delete client')
      setConfirmDelete(false)
    },
  })

  if (isLoading || !client) {
    return <div className="p-6 text-sm text-muted-foreground">{t('common.loading')}</div>
  }

  const TABS: { id: Tab; label: string }[] = [
    { id: 'history', label: t('clients.tab_appointments') },
    { id: 'colour', label: t('clients.tab_colour_notes') },
    { id: 'notes', label: t('clients.tab_special_instructions') },
  ]

  return (
    <div className="flex flex-col h-full overflow-hidden">
      {/* Header */}
      <div className="px-6 pt-5 pb-4 border-b bg-white flex-shrink-0">
        {editingProfile ? (
          <div className="space-y-3">
            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-1">
                <Label className="text-xs">{t('auth.first_name')}</Label>
                <Input value={editFirst} onChange={e => setEditFirst(e.target.value)} />
              </div>
              <div className="space-y-1">
                <Label className="text-xs">{t('auth.last_name')}</Label>
                <Input value={editLast} onChange={e => setEditLast(e.target.value)} />
              </div>
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-1">
                <Label className="text-xs">{t('common.email')}</Label>
                <Input type="email" value={editEmail} onChange={e => setEditEmail(e.target.value)} placeholder={t('common.optional')} />
              </div>
              <div className="space-y-1">
                <Label className="text-xs">{t('common.phone')}</Label>
                <Input type="tel" value={editPhone} onChange={e => setEditPhone(e.target.value)} placeholder={t('common.optional')} />
              </div>
            </div>
            <div className="space-y-1">
              <Label className="text-xs">{t('clients.language_preference')}</Label>
              <select
                value={editLangPref}
                onChange={e => setEditLangPref(e.target.value)}
                className="w-full border border-input rounded-md px-3 py-2 text-sm bg-background"
              >
                <option value="en">{t('translations.lang_en')}</option>
                <option value="fr">{t('translations.lang_fr')}</option>
              </select>
            </div>
            <div className="space-y-1">
              <Label className="text-xs">Preferred provider</Label>
              <select
                value={editPreferredProvider}
                onChange={e => setEditPreferredProvider(e.target.value)}
                className="w-full border border-input rounded-md px-3 py-2 text-sm bg-background"
              >
                <option value="">— None —</option>
                {providers.map(p => (
                  <option key={p.id} value={p.id}>{p.display_name}</option>
                ))}
              </select>
            </div>
            {editError && <p className="text-xs text-destructive">{editError}</p>}
            <div className="flex gap-2">
              <Button size="sm" onClick={() => saveProfile()} disabled={savingProfile || !editFirst.trim() || !editLast.trim()}>
                {savingProfile ? t('common.saving') : t('common.save')}
              </Button>
              <Button size="sm" variant="outline" onClick={() => setEditingProfile(false)} disabled={savingProfile}>
                {t('common.cancel')}
              </Button>
            </div>
          </div>
        ) : (
          <div className="flex items-start justify-between gap-3">
            <div>
              <div className="flex items-center gap-2">
                <h2 className="text-lg font-semibold">
                  {client.first_name} {client.last_name}
                </h2>
                {client.is_vip && (
                  <Badge variant="outline" className="text-amber-600 border-amber-400 text-xs">VIP</Badge>
                )}
                {client.language_preference && client.language_preference !== 'en' && (
                  <Badge variant="outline" className="text-xs uppercase">{client.language_preference}</Badge>
                )}
                {client.pronouns && (
                  <span className="text-xs text-muted-foreground">{client.pronouns}</span>
                )}
              </div>
              <div className="mt-1 flex flex-wrap gap-x-4 gap-y-0.5 text-sm text-muted-foreground">
                {client.cell_phone && <span>{client.cell_phone}</span>}
                {client.email && <span>{client.email}</span>}
                {!client.cell_phone && !client.email && <span>{t('clients.no_contact')}</span>}
              </div>
              {client.preferred_provider_name && (
                <div className="mt-1 text-xs text-muted-foreground">
                  Prefers <span className="font-medium text-foreground">{client.preferred_provider_name}</span>
                </div>
              )}
            </div>
            <div className="flex items-start gap-4 flex-shrink-0">
              <div className="flex gap-3 text-xs text-right">
                {client.no_show_count > 0 && (
                  <div className="text-destructive">
                    <div className="font-semibold text-base leading-none">{client.no_show_count}</div>
                    <div>no-shows</div>
                  </div>
                )}
                {client.late_cancellation_count > 0 && (
                  <div className="text-amber-600">
                    <div className="font-semibold text-base leading-none">{client.late_cancellation_count}</div>
                    <div>late cancel</div>
                  </div>
                )}
              </div>
              <Button size="sm" variant="ghost" className="text-muted-foreground" onClick={startEditProfile}>
                {t('common.edit')}
              </Button>
              {confirmDelete ? (
                <div className="flex items-center gap-2">
                  <span className="text-xs text-destructive">Delete this client?</span>
                  <Button size="sm" variant="destructive" onClick={() => doDelete()} disabled={deleting}>
                    {deleting ? 'Deleting…' : 'Confirm'}
                  </Button>
                  <Button size="sm" variant="outline" onClick={() => { setConfirmDelete(false); setDeleteError(null) }} disabled={deleting}>
                    {t('common.cancel')}
                  </Button>
                </div>
              ) : (
                <Button size="sm" variant="ghost" className="text-muted-foreground hover:text-destructive" onClick={() => { setDeleteError(null); setConfirmDelete(true) }}>
                  {t('common.delete')}
                </Button>
              )}
            </div>
          </div>
        )}
        {deleteError && (
          <p className="mt-2 text-xs text-destructive">{deleteError}</p>
        )}
      </div>

      {/* Tabs */}
      <div className="flex border-b bg-white flex-shrink-0 px-6">
        {TABS.map(t => (
          <button
            key={t.id}
            onClick={() => setTab(t.id)}
            className={`py-2.5 px-1 mr-5 text-sm border-b-2 transition-colors
              ${tab === t.id
                ? 'border-primary text-foreground font-medium'
                : 'border-transparent text-muted-foreground hover:text-foreground'
              }`}
          >
            {t.label}
          </button>
        ))}
      </div>

      {/* Tab content */}
      <div className="flex-1 overflow-auto p-6">
        {tab === 'history' && <VisitHistory clientId={clientId} />}
        {tab === 'colour' && <ColourNotes clientId={clientId} />}
        {tab === 'notes' && (
          <div className="space-y-3 max-w-lg">
            <h3 className="text-sm font-medium">Special instructions</h3>
            {editingNotes ? (
              <>
                <textarea
                  value={notesText}
                  onChange={e => setNotesText(e.target.value)}
                  rows={5}
                  placeholder="Allergies, preferences, access needs…"
                  className="w-full border border-input rounded-md px-3 py-2 text-sm bg-background resize-none"
                />
                <div className="flex gap-2">
                  <Button size="sm" onClick={() => saveNotes()} disabled={savingNotes}>
                    {savingNotes ? t('common.saving') : t('common.save')}
                  </Button>
                  <Button size="sm" variant="outline" onClick={() => {
                    setNotesText(client.special_instructions ?? '')
                    setEditingNotes(false)
                  }} disabled={savingNotes}>
                    {t('common.cancel')}
                  </Button>
                </div>
              </>
            ) : (
              <div
                onClick={() => setEditingNotes(true)}
                className="min-h-[80px] rounded-md border border-dashed px-3 py-2 text-sm cursor-pointer hover:bg-muted/30 transition-colors"
              >
                {client.special_instructions ? (
                  <p className="whitespace-pre-wrap">{client.special_instructions}</p>
                ) : (
                  <p className="text-muted-foreground">Click to add instructions…</p>
                )}
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  )
}

// ── Page ──────────────────────────────────────────────────────────────────────

export default function ClientsPage() {
  const { t } = useTranslation()
  const [searchParams] = useSearchParams()
  const [selectedId, setSelectedId] = useState<string | null>(searchParams.get('id'))

  return (
    <div className="flex h-full overflow-hidden bg-muted/30">
      <div className="w-72 flex-shrink-0 h-full">
        <ClientList selectedId={selectedId} onSelect={setSelectedId} />
      </div>

      <div className="flex-1 min-w-0 h-full overflow-hidden bg-white">
        {selectedId ? (
          <ClientDetail key={selectedId} clientId={selectedId} onDeleted={() => setSelectedId(null)} />
        ) : (
          <div className="flex items-center justify-center h-full text-sm text-muted-foreground">
            {t('clients.select_client')}
          </div>
        )}
      </div>
    </div>
  )
}
