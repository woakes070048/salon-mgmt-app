import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { format, parseISO, isToday } from 'date-fns'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import { Printer } from 'lucide-react'
import { getClient, getClientHistory, updateClient, updateClientNotes, listColourNotes, createColourNote, getClientBrief } from '@/api/clients'
import { updateAppointmentStatus } from '@/api/appointments'
import { printClientBrief } from '@/lib/qzTray'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Separator } from '@/components/ui/separator'

type Tab = 'profile' | 'appointments' | 'colour' | 'notes'

interface Props {
  clientId: string | null
  onClose: () => void
}

const VISIT_STATUS_LABEL: Record<string, string> = {
  confirmed: 'Upcoming',
  in_progress: 'In progress',
  completed: 'Completed',
  cancelled: 'Cancelled',
  no_show: 'No show',
}

const VISIT_STATUS_COLOR: Record<string, string> = {
  confirmed: 'text-blue-600',
  in_progress: 'text-green-600',
  completed: 'text-muted-foreground',
  cancelled: 'text-destructive',
  no_show: 'text-orange-600',
}

export default function ClientCard({ clientId, onClose }: Props) {
  const { t } = useTranslation()
  const qc = useQueryClient()
  const [tab, setTab] = useState<Tab>('profile')
  const [notesValue, setNotesValue] = useState<string | null>(null)
  const [editing, setEditing] = useState(false)
  const [editFirst, setEditFirst] = useState('')
  const [editLast, setEditLast] = useState('')
  const [editEmail, setEditEmail] = useState('')
  const [editPhone, setEditPhone] = useState('')
  const [editLangPref, setEditLangPref] = useState('en')
  const [editError, setEditError] = useState<string | null>(null)
  const [newNoteText, setNewNoteText] = useState('')
  const [newNoteDate, setNewNoteDate] = useState(format(new Date(), 'yyyy-MM-dd'))
  const [printing, setPrinting] = useState(false)

  async function handlePrintBrief() {
    if (!clientId) return
    setPrinting(true)
    try {
      const brief = await getClientBrief(clientId)
      await printClientBrief(brief)
    } finally {
      setPrinting(false)
    }
  }

  const { data: client, isLoading: clientLoading } = useQuery({
    queryKey: ['client', clientId],
    queryFn: () => getClient(clientId!),
    enabled: !!clientId,
  })

  const { data: visits = [], isLoading: historyLoading } = useQuery({
    queryKey: ['client-history', clientId],
    queryFn: () => getClientHistory(clientId!),
    enabled: !!clientId && tab === 'appointments',
  })

  const notesMutation = useMutation({
    mutationFn: (notes: string | null) => updateClientNotes(clientId!, notes),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['client', clientId] })
      qc.invalidateQueries({ queryKey: ['appointments'] })
      setNotesValue(null)
    },
  })

  const updateMutation = useMutation({
    mutationFn: () => updateClient(clientId!, {
      first_name: editFirst.trim(),
      last_name: editLast.trim(),
      email: editEmail.trim() || null,
      cell_phone: editPhone.trim() || null,
      language_preference: editLangPref,
    }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['client', clientId] })
      qc.invalidateQueries({ queryKey: ['clients'] })
      setEditing(false)
      setEditError(null)
    },
    onError: (err: unknown) => setEditError((err as Error).message ?? 'Save failed'),
  })

  function startEdit() {
    if (!client) return
    setEditFirst(client.first_name)
    setEditLast(client.last_name)
    setEditEmail(client.email ?? '')
    setEditPhone(client.cell_phone ?? '')
    setEditLangPref(client.language_preference ?? 'en')
    setEditError(null)
    setEditing(true)
  }

  const { data: colourNotes = [], isLoading: colourLoading } = useQuery({
    queryKey: ['client-colour-notes', clientId],
    queryFn: () => listColourNotes(clientId!),
    enabled: !!clientId && tab === 'colour',
  })

  const addColourNote = useMutation({
    mutationFn: () => createColourNote(clientId!, newNoteDate, newNoteText),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['client-colour-notes', clientId] })
      setNewNoteText('')
      setNewNoteDate(format(new Date(), 'yyyy-MM-dd'))
    },
  })

  const cancelAppt = useMutation({
    mutationFn: ({ id }: { id: string; date: string }) => updateAppointmentStatus(id, 'cancelled'),
    onSuccess: (_, { date }) => {
      qc.invalidateQueries({ queryKey: ['client-history', clientId] })
      qc.invalidateQueries({ queryKey: ['appointments', date] })
    },
  })

  const todayStr = format(new Date(), 'yyyy-MM-dd')
  const upcoming = visits.filter(v => v.date >= todayStr).reverse()
  const past = visits.filter(v => v.date < todayStr)

  const currentNotes = notesValue !== null ? notesValue : (client?.special_instructions ?? '')

  if (!clientId) return null

  return (
    <div className="fixed inset-0 z-50 flex justify-end">
      <div className="absolute inset-0 bg-black/20" onClick={onClose} />

      <div className="relative w-[440px] bg-white h-full flex flex-col shadow-2xl">
        {/* Header */}
        <div className="flex items-start justify-between px-5 pt-5 pb-3 border-b flex-shrink-0">
          {clientLoading ? (
            <div className="h-6 w-40 bg-muted animate-pulse rounded" />
          ) : client ? (
            <div>
              <div className="flex items-center gap-2">
                <h2 className="text-lg font-semibold">
                  {client.first_name} {client.last_name}
                </h2>
                {client.is_vip && (
                  <Badge variant="default" className="text-xs">VIP</Badge>
                )}
                {client.language_preference && client.language_preference !== 'en' && (
                  <Badge variant="outline" className="text-xs uppercase">
                    {client.language_preference}
                  </Badge>
                )}
              </div>
              {client.pronouns && (
                <p className="text-xs text-muted-foreground mt-0.5">{client.pronouns}</p>
              )}
            </div>
          ) : (
            <span className="text-muted-foreground text-sm">Client not found</span>
          )}
          <div className="flex items-center gap-2 ml-4">
            <button
              onClick={handlePrintBrief}
              disabled={printing || !client}
              className="text-muted-foreground hover:text-foreground disabled:opacity-40 transition-colors"
              title="Print client brief"
            >
              <Printer size={16} />
            </button>
            <button
              onClick={onClose}
              className="text-muted-foreground hover:text-foreground text-xl leading-none mt-0.5"
            >
              ×
            </button>
          </div>
        </div>

        {/* Tabs */}
        <div className="flex border-b flex-shrink-0 px-5">
          {(['profile', 'appointments', 'colour', 'notes'] as Tab[]).map(tabId => (
            <button
              key={tabId}
              onClick={() => setTab(tabId)}
              className={`px-3 py-2 text-sm capitalize border-b-2 -mb-px transition-colors ${
                tab === tabId
                  ? 'border-foreground font-medium'
                  : 'border-transparent text-muted-foreground hover:text-foreground'
              }`}
            >
              {tabId === 'profile' ? t('clients.tab_profile') : tabId === 'appointments' ? t('clients.tab_appointments') : tabId === 'colour' ? t('clients.tab_colour') : t('clients.tab_notes')}
            </button>
          ))}
        </div>

        {/* Content */}
        <div className="flex-1 overflow-y-auto">

          {/* ── Profile tab ── */}
          {tab === 'profile' && (
            <div className="p-5 space-y-4">
              {clientLoading ? (
                <div className="space-y-2">
                  {[1, 2, 3].map(i => (
                    <div key={i} className="h-4 bg-muted animate-pulse rounded" />
                  ))}
                </div>
              ) : client ? (
                <>
                  {editing ? (
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
                      <div className="space-y-1">
                        <Label className="text-xs">{t('common.email')}</Label>
                        <Input type="email" value={editEmail} onChange={e => setEditEmail(e.target.value)} placeholder={t('common.optional')} />
                      </div>
                      <div className="space-y-1">
                        <Label className="text-xs">{t('common.phone')}</Label>
                        <Input type="tel" value={editPhone} onChange={e => setEditPhone(e.target.value)} placeholder={t('common.optional')} />
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
                      {editError && <p className="text-xs text-destructive">{editError}</p>}
                      <div className="flex gap-2">
                        <Button
                          size="sm"
                          className="flex-1"
                          disabled={updateMutation.isPending || !editFirst.trim() || !editLast.trim()}
                          onClick={() => updateMutation.mutate()}
                        >
                          {updateMutation.isPending ? t('common.saving') : t('common.save')}
                        </Button>
                        <Button size="sm" variant="outline" onClick={() => setEditing(false)}>
                          {t('common.cancel')}
                        </Button>
                      </div>
                    </div>
                  ) : (
                    <>
                      <div className="space-y-2">
                        {client.email && (
                          <div className="flex items-center gap-3 text-sm">
                            <span className="text-muted-foreground w-16 shrink-0">{t('common.email')}</span>
                            <a href={`mailto:${client.email}`} className="hover:underline truncate">
                              {client.email}
                            </a>
                          </div>
                        )}
                        {client.cell_phone && (
                          <div className="flex items-center gap-3 text-sm">
                            <span className="text-muted-foreground w-16 shrink-0">{t('common.phone')}</span>
                            <a href={`tel:${client.cell_phone}`} className="hover:underline">
                              {client.cell_phone}
                            </a>
                          </div>
                        )}
                        {!client.email && !client.cell_phone && (
                          <p className="text-sm text-muted-foreground">{t('clients.no_contact')}</p>
                        )}
                      </div>
                      <Button size="sm" variant="outline" onClick={startEdit}>
                        {t('clients.edit_profile')}
                      </Button>
                    </>
                  )}

                  {(client.no_show_count > 0 || client.late_cancellation_count > 0) && !editing && (
                    <>
                      <Separator />
                      <div className="space-y-1.5">
                        {client.no_show_count > 0 && (
                          <div className="flex items-center gap-3 text-sm">
                            <span className="text-muted-foreground w-32 shrink-0">{t('clients.no_shows_label')}</span>
                            <span className="font-medium text-orange-600">{client.no_show_count}</span>
                          </div>
                        )}
                        {client.late_cancellation_count > 0 && (
                          <div className="flex items-center gap-3 text-sm">
                            <span className="text-muted-foreground w-32 shrink-0">{t('clients.late_cancellations')}</span>
                            <span className="font-medium text-orange-600">{client.late_cancellation_count}</span>
                          </div>
                        )}
                      </div>
                    </>
                  )}

                  {client.special_instructions && !editing && (
                    <>
                      <Separator />
                      <div className="rounded-md bg-amber-50 border border-amber-200 px-3 py-2 text-sm text-amber-800">
                        {client.special_instructions}
                      </div>
                    </>
                  )}
                </>
              ) : null}
            </div>
          )}

          {/* ── Appointments tab ── */}
          {tab === 'appointments' && (
            <div className="p-5 space-y-5">
              {historyLoading ? (
                <p className="text-sm text-muted-foreground text-center py-8">{t('common.loading')}</p>
              ) : (
                <>
                  {upcoming.length > 0 && (
                    <div className="space-y-2">
                      <h3 className="text-xs font-medium text-muted-foreground uppercase tracking-wide">
                        {t('clients.upcoming')}
                      </h3>
                      {upcoming.map(visit => (
                        <VisitRow key={visit.appointment_id} visit={visit} onCancel={(id, date) => cancelAppt.mutate({ id, date })} onClose={onClose} />
                      ))}
                    </div>
                  )}

                  {upcoming.length > 0 && past.length > 0 && <Separator />}

                  {past.length > 0 && (
                    <div className="space-y-2">
                      <h3 className="text-xs font-medium text-muted-foreground uppercase tracking-wide">
                        {t('clients.history')}
                      </h3>
                      {past.map(visit => (
                        <VisitRow key={visit.appointment_id} visit={visit} onClose={onClose} />
                      ))}
                    </div>
                  )}

                  {upcoming.length === 0 && past.length === 0 && (
                    <p className="text-sm text-muted-foreground text-center py-8">{t('clients.no_appointments')}</p>
                  )}
                </>
              )}
            </div>
          )}

          {/* ── Colour tab ── */}
          {tab === 'colour' && (
            <div className="p-5 space-y-4">
              {/* Add new note */}
              <div className="rounded-md border p-3 space-y-2 bg-muted/20">
                <p className="text-xs font-medium text-muted-foreground">{t('clients.new_formula')}</p>
                <div className="flex gap-2">
                  <input
                    type="date"
                    value={newNoteDate}
                    onChange={e => setNewNoteDate(e.target.value)}
                    className="border border-input rounded-md px-2 py-1.5 text-sm bg-background"
                  />
                </div>
                <textarea
                  rows={4}
                  value={newNoteText}
                  onChange={e => setNewNoteText(e.target.value)}
                  placeholder={t('clients.formula_placeholder')}
                  className="w-full border border-input rounded-md px-3 py-2 text-sm bg-background resize-none"
                />
                {addColourNote.isError && (
                  <p className="text-xs text-destructive">Save failed</p>
                )}
                <Button
                  size="sm"
                  className="w-full"
                  disabled={!newNoteText.trim() || addColourNote.isPending}
                  onClick={() => addColourNote.mutate()}
                >
                  {addColourNote.isPending ? t('common.saving') : t('clients.save_formula')}
                </Button>
              </div>

              {/* Existing notes */}
              {colourLoading ? (
                <p className="text-sm text-muted-foreground text-center py-4">{t('common.loading')}</p>
              ) : colourNotes.length === 0 ? (
                <p className="text-sm text-muted-foreground text-center py-4">{t('clients.no_colour_notes')}</p>
              ) : (
                <div className="space-y-3">
                  {colourNotes.map(note => (
                    <div key={note.id} className="border rounded-md px-3 py-2 space-y-1">
                      <p className="text-xs text-muted-foreground">
                        {format(parseISO(note.note_date + 'T12:00:00'), 'MMM d, yyyy')}
                      </p>
                      <p className="text-sm whitespace-pre-wrap">{note.note_text}</p>
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}

          {/* ── Notes tab ── */}
          {tab === 'notes' && (
            <div className="p-5 space-y-3">
              <p className="text-xs text-muted-foreground">
                {t('clients.notes_tooltip')}
              </p>
              {clientLoading ? (
                <div className="h-24 bg-muted animate-pulse rounded" />
              ) : (
                <>
                  <textarea
                    rows={6}
                    value={currentNotes}
                    onChange={e => setNotesValue(e.target.value)}
                    placeholder={t('clients.notes_placeholder')}
                    className="w-full border border-input rounded-md px-3 py-2 text-sm bg-background resize-none"
                  />
                  {notesMutation.isError && (
                    <p className="text-xs text-destructive">Save failed</p>
                  )}
                  <Button
                    className="w-full"
                    disabled={notesMutation.isPending || currentNotes === (client?.special_instructions ?? '')}
                    onClick={() => notesMutation.mutate(currentNotes || null)}
                  >
                    {notesMutation.isPending ? t('common.saving') : t('clients.save_notes')}
                  </Button>
                </>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

function VisitRow({ visit, onCancel, onClose }: {
  visit: { appointment_id: string; date: string; status: string; items: { service_name: string; provider_name: string; price: number }[] }
  onCancel?: (id: string, date: string) => void
  onClose?: () => void
}) {
  const navigate = useNavigate()
  const [confirmCancel, setConfirmCancel] = useState(false)
  const dateObj = parseISO(visit.date + 'T12:00:00')
  const total = visit.items.reduce((sum, i) => sum + i.price, 0)
  const isNavigable = visit.status !== 'cancelled' && visit.status !== 'no_show'

  function handleNavigate() {
    if (!isNavigable) return
    onClose?.()
    navigate(`/appointments?date=${visit.date}&appointment=${visit.appointment_id}`)
  }

  return (
    <div
      className={`border rounded-md px-3 py-2 space-y-1 ${isNavigable ? 'cursor-pointer hover:bg-muted/30 transition-colors' : ''}`}
      onClick={handleNavigate}
    >
      <div className="flex items-center justify-between gap-2">
        <span className="text-sm font-medium">
          {isToday(dateObj) ? 'Today' : format(dateObj, 'MMM d, yyyy')}
        </span>
        <div className="flex items-center gap-2">
          <span className="text-xs text-muted-foreground">${total.toFixed(2)}</span>
          <span className={`text-xs ${VISIT_STATUS_COLOR[visit.status] ?? ''}`}>
            {VISIT_STATUS_LABEL[visit.status] ?? visit.status}
          </span>
          {onCancel && visit.status === 'confirmed' && (
            confirmCancel ? (
              <span className="flex items-center gap-1" onClick={e => e.stopPropagation()}>
                <span className="text-xs text-muted-foreground">Sure?</span>
                <button onClick={() => { onCancel(visit.appointment_id, visit.date); setConfirmCancel(false) }}
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
      {visit.items.map((item, i) => (
        <p key={i} className="text-xs text-muted-foreground">
          {item.service_name} · {item.provider_name}
        </p>
      ))}
    </div>
  )
}
