import { format, parseISO } from 'date-fns'
import { useTranslation } from 'react-i18next'
import { useTimeFormat } from '@/lib/timeFormat'
import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { X, ExternalLink } from 'lucide-react'
import type { Appointment, AppointmentItem } from '@/api/appointments'
import { updateAppointmentStatus, addAppointmentItem, removeAppointmentItem } from '@/api/appointments'
import { getClientHistory, updateClientNotes } from '@/api/clients'
import { listServices } from '@/api/services'
import { listProviders } from '@/api/providers'
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Separator } from '@/components/ui/separator'
import CheckoutPanel from '@/components/appointment-book/CheckoutPanel'
import SaleSummary from '@/components/appointment-book/SaleSummary'
import ConfirmationDialog from '@/components/appointment-book/ConfirmationDialog'
import { useAuth } from '@/store/auth'

const STATUS_VARIANT: Record<string, 'default' | 'secondary' | 'destructive' | 'outline'> = {
  pending: 'secondary',
  in_progress: 'default',
  completed: 'outline',
  cancelled: 'destructive',
}

const VISIT_STATUS_COLOR: Record<string, string> = {
  confirmed: 'text-blue-600',
  in_progress: 'text-green-600',
  completed: 'text-muted-foreground',
  cancelled: 'text-destructive',
}

type Tab = 'appointment' | 'history' | 'notes'

interface Props {
  item: AppointmentItem | null
  appointment: Appointment | null
  date: string
  onClose: () => void
}

interface AddItemForm {
  serviceId: string
  providerId: string
  startTime: string
  durationMinutes: number
  price: string
}

export default function AppointmentDetail({ item, appointment, date, onClose }: Props) {
  const { t } = useTranslation()
  const qc = useQueryClient()
  const navigate = useNavigate()
  const { formatTime: ft } = useTimeFormat()
  const { user } = useAuth()
  const isAdmin = user?.role === 'tenant_admin' || user?.role === 'super_admin'
  const [tab, setTab] = useState<Tab>('appointment')
  const [notesValue, setNotesValue] = useState<string | null>(null)
  const [showAddForm, setShowAddForm] = useState(false)
  const [addForm, setAddForm] = useState<AddItemForm>({
    serviceId: '',
    providerId: '',
    startTime: '09:00',
    durationMinutes: 60,
    price: '',
  })
  const [addError, setAddError] = useState<string | null>(null)
  const [removeError, setRemoveError] = useState<string | null>(null)
  const [pendingRemoveId, setPendingRemoveId] = useState<string | null>(null)
  const [confirmCancel, setConfirmCancel] = useState(false)
  const [checkoutOpen, setCheckoutOpen] = useState(false)
  const [confirmationOpen, setConfirmationOpen] = useState(false)

  const clientId = appointment?.client.id ?? null

  const { data: history = [], isLoading: historyLoading } = useQuery({
    queryKey: ['client-history', clientId],
    queryFn: () => getClientHistory(clientId!),
    enabled: !!clientId && tab === 'history',
  })

  const { data: services = [] } = useQuery({
    queryKey: ['services'],
    queryFn: listServices,
    enabled: showAddForm,
  })

  const { data: providers = [] } = useQuery({
    queryKey: ['providers'],
    queryFn: listProviders,
    enabled: showAddForm,
  })

  const statusMutation = useMutation({
    mutationFn: (newStatus: Appointment['status']) =>
      updateAppointmentStatus(appointment!.id, newStatus),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['appointments', date] })
      onClose()
    },
  })

  const notesMutation = useMutation({
    mutationFn: (notes: string | null) => updateClientNotes(clientId!, notes),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['appointments', date] })
      setNotesValue(null)
    },
  })

  const removeMutation = useMutation({
    mutationFn: (itemId: string) => removeAppointmentItem(appointment!.id, itemId),
    onSuccess: (updated) => {
      setRemoveError(null)
      qc.setQueryData(['appointments', date], (old: Appointment[] | undefined) =>
        old?.map(a => a.id === updated.id ? updated : a)
      )
    },
    onError: (e) => setRemoveError(e instanceof Error ? e.message : 'Failed to remove service'),
  })

  const addMutation = useMutation({
    mutationFn: () => {
      if (!appointment) throw new Error('No appointment')
      const apptDate = appointment.appointment_date.split('T')[0]
      return addAppointmentItem(appointment.id, {
        service_id: addForm.serviceId,
        provider_id: addForm.providerId,
        start_time: `${apptDate}T${addForm.startTime}:00`,
        duration_minutes: addForm.durationMinutes,
        price: parseFloat(addForm.price),
        sequence: (appointment.items.length ?? 0) + 1,
      })
    },
    onSuccess: (updated) => {
      qc.setQueryData(['appointments', date], (old: Appointment[] | undefined) =>
        old?.map(a => a.id === updated.id ? updated : a)
      )
      setShowAddForm(false)
      setAddForm({ serviceId: '', providerId: '', startTime: '09:00', durationMinutes: 60, price: '' })
      setAddError(null)
    },
    onError: (e) => setAddError(e instanceof Error ? e.message : 'Failed to add service'),
  })

  function handleOpenChange(isOpen: boolean) {
    if (!isOpen) { setTab('appointment'); setNotesValue(null); setShowAddForm(false); onClose() }
  }

  function handleServiceChange(serviceId: string) {
    const svc = services.find(s => s.id === serviceId)
    setAddForm(f => ({
      ...f,
      serviceId,
      durationMinutes: svc?.duration_minutes ?? 60,
      price: svc?.default_price != null ? String(svc.default_price) : f.price,
    }))
  }

  function handleAddSubmit() {
    if (!addForm.serviceId) { setAddError('Select a service'); return }
    if (!addForm.providerId) { setAddError('Select a provider'); return }
    if (!addForm.price || isNaN(parseFloat(addForm.price))) { setAddError('Enter a price'); return }
    setAddError(null)
    addMutation.mutate()
  }

  function defaultNextStartTime(): string {
    const items = appointment?.items ?? []
    if (items.length === 0) return '09:00'
    const sorted = [...items].sort(
      (a, b) => new Date(a.start_time).getTime() - new Date(b.start_time).getTime()
    )
    const last = sorted[sorted.length - 1]
    const dur = last.duration_override_minutes ?? last.duration_minutes
    const end = new Date(new Date(last.start_time).getTime() + dur * 60000)
    return `${String(end.getHours()).padStart(2, '0')}:${String(end.getMinutes()).padStart(2, '0')}`
  }

  function openAddForm() {
    setAddForm(f => ({ ...f, startTime: defaultNextStartTime() }))
    setShowAddForm(true)
  }

  if (!item || !appointment) return null

  const apptStatus = appointment.status
  const client = appointment.client
  const canEdit = apptStatus === 'confirmed'
  const currentNotes = notesValue !== null ? notesValue : (client.special_instructions ?? '')

  // Sort items by start time
  const sortedItems = [...appointment.items].sort(
    (a, b) => new Date(a.start_time).getTime() - new Date(b.start_time).getTime()
  )

  return (
    <>
    {!checkoutOpen && (
    <Dialog open onOpenChange={handleOpenChange}>
      <DialogContent className="max-w-md max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            {client.first_name} {client.last_name}
            <button
              onClick={() => { onClose(); navigate(`/clients?id=${client.id}`) }}
              className="text-muted-foreground hover:text-foreground transition-colors"
              title={t('appt.open_client_profile')}
            >
              <ExternalLink size={14} />
            </button>
          </DialogTitle>
        </DialogHeader>

        <p className="text-sm text-muted-foreground -mt-2">
          {format(parseISO(appointment.appointment_date.split('T')[0] + 'T12:00:00'), 'EEEE, MMMM d, yyyy')}
          {client.cell_phone && <> · {client.cell_phone}</>}
        </p>

        {/* Tabs */}
        <div className="flex gap-1 border-b">
          {(['appointment', 'history', 'notes'] as Tab[]).map((tabKey) => (
            <button
              key={tabKey}
              onClick={() => setTab(tabKey)}
              className={`px-3 py-1.5 text-sm capitalize border-b-2 -mb-px transition-colors ${
                tab === tabKey
                  ? 'border-foreground font-medium'
                  : 'border-transparent text-muted-foreground hover:text-foreground'
              }`}
            >
              {tabKey === 'notes' ? t('appt.tab_client_notes') : tabKey === 'history' ? t('appt.tab_appointments') : t('appt.tab_appointment')}
            </button>
          ))}
        </div>

        {/* ── Appointment tab ── */}
        {tab === 'appointment' && (
          <div className="space-y-4">
            {client.special_instructions && (
              <div className="rounded-md bg-amber-50 border border-amber-200 px-3 py-2 text-sm text-amber-800">
                {client.special_instructions}
              </div>
            )}

            {/* All items */}
            <div className="space-y-2">
              {sortedItems.map(apptItem => {
                const startTime = new Date(apptItem.start_time)
                const effectiveDuration = apptItem.duration_override_minutes ?? apptItem.duration_minutes
                const endTime = new Date(startTime.getTime() + effectiveDuration * 60000)
                const isClicked = apptItem.id === item.id
                return (
                  <div
                    key={apptItem.id}
                    className={`rounded-md border px-3 py-2 ${isClicked ? 'border-foreground/30 bg-muted/30' : ''}`}
                  >
                    <div className="flex items-start justify-between gap-2">
                      <div>
                        <p className="font-medium text-sm">{apptItem.service.name}</p>
                        <p className="text-xs text-muted-foreground">
                          {ft(startTime)} – {ft(endTime)} · {effectiveDuration} min
                        </p>
                        <p className="text-xs text-muted-foreground">
                          with {apptItem.provider.display_name}
                          {apptItem.second_provider ? ` & ${apptItem.second_provider.display_name}` : ''}
                        </p>
                      </div>
                      <div className="flex flex-col items-end gap-1">
                        <div className="flex items-center gap-1">
                          {canEdit && sortedItems.length > 1 && (
                            <button
                              onClick={() => setPendingRemoveId(apptItem.id)}
                              disabled={removeMutation.isPending || statusMutation.isPending}
                              className="text-muted-foreground hover:text-destructive transition-colors"
                              title={t('appt.remove_service')}
                            >
                              <X className="h-3.5 w-3.5" />
                            </button>
                          )}
                          <Badge variant={STATUS_VARIANT[apptItem.status]}>
                            {apptItem.status.replace('_', ' ')}
                          </Badge>
                        </div>
                        <span className="text-sm font-medium">${apptItem.price.toFixed(2)}</span>
                      </div>
                    </div>
                    {apptItem.notes && (
                      <p className="text-xs text-muted-foreground italic mt-1">{apptItem.notes}</p>
                    )}
                  </div>
                )
              })}
            </div>

            {pendingRemoveId && (() => {
              const target = sortedItems.find(i => i.id === pendingRemoveId)
              return (
                <div className="rounded-md border border-amber-300 bg-amber-50 px-3 py-2.5 space-y-2 text-sm text-amber-900">
                  <p className="font-medium">Remove {target?.service.name}?</p>
                  <p className="text-xs">This appointment has {sortedItems.length} services. Do you want to remove just this service, or cancel all services?</p>
                  <div className="flex gap-2">
                    <Button
                      size="sm"
                      variant="outline"
                      className="flex-1 border-amber-400 bg-white"
                      disabled={removeMutation.isPending || statusMutation.isPending}
                      onClick={() => { removeMutation.mutate(pendingRemoveId); setPendingRemoveId(null) }}
                    >
                      {t('appt.this_service_only')}
                    </Button>
                    <Button
                      size="sm"
                      variant="destructive"
                      className="flex-1"
                      disabled={removeMutation.isPending || statusMutation.isPending}
                      onClick={() => { statusMutation.mutate('cancelled'); setPendingRemoveId(null) }}
                    >
                      {t('appt.cancel_all_services')}
                    </Button>
                    <Button
                      size="sm"
                      variant="ghost"
                      disabled={removeMutation.isPending || statusMutation.isPending}
                      onClick={() => setPendingRemoveId(null)}
                    >
                      {t('common.back')}
                    </Button>
                  </div>
                </div>
              )
            })()}

            {removeError && (
              <p className="text-xs text-destructive">{removeError}</p>
            )}

            {/* Add service form */}
            {canEdit && (
              showAddForm ? (
                <div className="rounded-md border p-3 space-y-2 bg-muted/20">
                  <p className="text-xs font-medium text-muted-foreground">
                    Add service · {format(parseISO(appointment.appointment_date), 'EEEE, MMM d')}
                  </p>
                  <select
                    value={addForm.serviceId}
                    onChange={e => handleServiceChange(e.target.value)}
                    className="w-full border border-input rounded-md px-2 py-1.5 text-sm bg-background"
                  >
                    <option value="">{t('appt.select_service')}</option>
                    {services.map(s => (
                      <option key={s.id} value={s.id}>{s.name}</option>
                    ))}
                  </select>
                  <select
                    value={addForm.providerId}
                    onChange={e => setAddForm(f => ({ ...f, providerId: e.target.value }))}
                    className="w-full border border-input rounded-md px-2 py-1.5 text-sm bg-background"
                  >
                    <option value="">{t('appt.select_provider')}</option>
                    {providers.map(p => (
                      <option key={p.id} value={p.id}>{p.display_name}</option>
                    ))}
                  </select>
                  <div className="flex gap-2">
                    <div className="flex-1">
                      <p className="text-xs text-muted-foreground mb-1">{t('appt.start_time')}</p>
                      <input
                        type="time"
                        value={addForm.startTime}
                        onChange={e => setAddForm(f => ({ ...f, startTime: e.target.value }))}
                        className="w-full border border-input rounded-md px-2 py-1.5 text-sm bg-background"
                      />
                    </div>
                    <div className="flex-1">
                      <p className="text-xs text-muted-foreground mb-1">{t('appt.price_label')}</p>
                      <input
                        type="number"
                        min="0"
                        step="0.01"
                        value={addForm.price}
                        onChange={e => setAddForm(f => ({ ...f, price: e.target.value }))}
                        placeholder="0.00"
                        className="w-full border border-input rounded-md px-2 py-1.5 text-sm bg-background"
                      />
                    </div>
                  </div>
                  {addError && <p className="text-xs text-destructive">{addError}</p>}
                  <div className="flex gap-2">
                    <Button size="sm" className="flex-1" onClick={handleAddSubmit} disabled={addMutation.isPending}>
                      {addMutation.isPending ? t('common.saving') : t('appt.add_service')}
                    </Button>
                    <Button size="sm" variant="outline" onClick={() => { setShowAddForm(false); setAddError(null) }}>
                      {t('common.cancel')}
                    </Button>
                  </div>
                </div>
              ) : (
                <Button variant="outline" size="sm" className="w-full" onClick={openAddForm}>
                  {t('appt.add_service')}
                </Button>
              )
            )}

            {appointment.notes && (
              <>
                <Separator />
                <p className="text-xs text-muted-foreground">{appointment.notes}</p>
              </>
            )}

            {statusMutation.isError && (
              <p className="text-xs text-destructive">
                {statusMutation.error instanceof Error ? statusMutation.error.message : 'Update failed'}
              </p>
            )}

            {apptStatus !== 'cancelled' && (
              <ConfirmationStatusRow
                status={appointment.confirmation_status}
                sentAt={appointment.confirmation_sent_at}
                hasEmail={!!client.email}
                onOpen={() => setConfirmationOpen(true)}
              />
            )}

            {apptStatus === 'confirmed' && (
              <div className="flex gap-2 pt-1 flex-wrap">
                <Button
                  className="flex-1 bg-green-600 hover:bg-green-700 text-white"
                  disabled={statusMutation.isPending}
                  onClick={() => statusMutation.mutate('in_progress')}
                >
                  {t('appt.client_arrived')}
                </Button>
                {confirmCancel ? (
                  <span className="flex items-center gap-1">
                    <span className="text-xs text-muted-foreground">{t('common.sure')}</span>
                    <Button size="sm" variant="destructive" disabled={statusMutation.isPending}
                      onClick={() => { statusMutation.mutate('cancelled'); setConfirmCancel(false) }}>{t('common.yes')}</Button>
                    <Button size="sm" variant="outline" onClick={() => setConfirmCancel(false)}>{t('common.no')}</Button>
                  </span>
                ) : (
                  <Button variant="destructive" disabled={statusMutation.isPending}
                    onClick={() => setConfirmCancel(true)}>{t('common.cancel')}</Button>
                )}
              </div>
            )}

            {apptStatus === 'in_progress' && (
              <div className="flex gap-2 pt-1 flex-wrap">
                <Button
                  className="flex-1"
                  disabled={statusMutation.isPending}
                  onClick={() => setCheckoutOpen(true)}
                >
                  {t('appt.check_out')}
                </Button>
                <Button
                  variant="outline"
                  disabled={statusMutation.isPending}
                  onClick={() => statusMutation.mutate('confirmed')}
                >
                  {t('appt.not_arrived')}
                </Button>
                {confirmCancel ? (
                  <span className="flex items-center gap-1">
                    <span className="text-xs text-muted-foreground">{t('common.sure')}</span>
                    <Button size="sm" variant="destructive" disabled={statusMutation.isPending}
                      onClick={() => { statusMutation.mutate('cancelled'); setConfirmCancel(false) }}>{t('common.yes')}</Button>
                    <Button size="sm" variant="outline" onClick={() => setConfirmCancel(false)}>{t('common.no')}</Button>
                  </span>
                ) : (
                  <Button variant="destructive" disabled={statusMutation.isPending}
                    onClick={() => setConfirmCancel(true)}>{t('common.cancel')}</Button>
                )}
              </div>
            )}

            {apptStatus === 'completed' && (
              <div className="pt-1">
                <div className="flex gap-2 justify-center">
                  <p className="text-xs text-muted-foreground">{t('appt.status_checked_out')}</p>
                  <button
                    className="text-xs text-muted-foreground hover:text-foreground underline"
                    disabled={statusMutation.isPending}
                    onClick={() => statusMutation.mutate('in_progress')}
                  >
                    {t('appt.undo')}
                  </button>
                </div>
                <SaleSummary appointmentId={appointment.id} isAdmin={isAdmin} />
              </div>
            )}
            {apptStatus === 'cancelled' && (
              <p className="text-xs text-destructive text-center pt-1">{t('appt.status_cancelled')}</p>
            )}
          </div>
        )}

        {/* ── History tab ── */}
        {tab === 'history' && (
          <div className="space-y-2 max-h-80 overflow-auto">
            {historyLoading ? (
              <p className="text-sm text-muted-foreground py-4 text-center">{t('common.loading')}</p>
            ) : history.length === 0 ? (
              <p className="text-sm text-muted-foreground py-4 text-center">{t('appt.no_previous_visits')}</p>
            ) : (
              history.map((visit) => {
                const isNavigable = visit.status !== 'cancelled' && visit.status !== 'no_show'
                return (
                  <div
                    key={visit.appointment_id}
                    className={`border rounded-md px-3 py-2 space-y-1 ${isNavigable ? 'cursor-pointer hover:bg-muted/30 transition-colors' : ''}`}
                    onClick={() => {
                      if (!isNavigable) return
                      onClose()
                      navigate(`/appointments?date=${visit.date}&appointment=${visit.appointment_id}`)
                    }}
                  >
                    <div className="flex items-center justify-between">
                      <span className="text-sm font-medium">
                        {format(parseISO(visit.date), 'MMM d, yyyy')}
                      </span>
                      <span className={`text-xs capitalize ${VISIT_STATUS_COLOR[visit.status] ?? ''}`}>
                        {visit.status.replace('_', ' ')}
                      </span>
                    </div>
                    {visit.items.map((vi, i) => (
                      <p key={i} className="text-xs text-muted-foreground">
                        {vi.service_name} · {vi.provider_name}
                        <span className="ml-1 text-foreground">${vi.price.toFixed(2)}</span>
                      </p>
                    ))}
                  </div>
                )
              })
            )}
          </div>
        )}

        {/* ── Notes tab ── */}
        {tab === 'notes' && (
          <div className="space-y-3">
            <p className="text-xs text-muted-foreground">
              Standing notes shown whenever this client has an appointment.
            </p>
            <textarea
              rows={5}
              value={currentNotes}
              onChange={(e) => setNotesValue(e.target.value)}
              placeholder={t('appt.notes_placeholder')}
              className="w-full border border-input rounded-md px-3 py-2 text-sm bg-background resize-none"
            />
            {notesMutation.isError && (
              <p className="text-xs text-destructive">Save failed</p>
            )}
            <Button
              className="w-full"
              disabled={notesMutation.isPending || currentNotes === (client.special_instructions ?? '')}
              onClick={() => notesMutation.mutate(currentNotes || null)}
            >
              {notesMutation.isPending ? t('common.saving') : t('appt.save_notes')}
            </Button>
          </div>
        )}
      </DialogContent>
    </Dialog>
    )}

    {checkoutOpen && appointment && (
      <CheckoutPanel
        appointment={appointment}
        date={date}
        onClose={() => { setCheckoutOpen(false); onClose() }}
        onCompleted={() => { setCheckoutOpen(false); onClose() }}
      />
    )}

    {appointment && (
      <ConfirmationDialog
        appointmentId={appointment.id}
        appointmentDate={appointment.appointment_date}
        open={confirmationOpen}
        recipientEmail={client.email ?? null}
        onClose={() => setConfirmationOpen(false)}
      />
    )}
    </>
  )
}

interface ConfirmationStatusRowProps {
  status: 'not_sent' | 'draft' | 'sent' | 'skipped'
  sentAt: string | null
  hasEmail: boolean
  onOpen: () => void
}

function ConfirmationStatusRow({ status, sentAt, hasEmail, onOpen }: ConfirmationStatusRowProps) {
  const { t } = useTranslation()
  let label: string
  let buttonLabel: string
  let tone: string

  switch (status) {
    case 'sent':
      label = `${t('appt.confirmation_sent')}${sentAt ? ` ${new Date(sentAt).toLocaleDateString()}` : ''}`
      buttonLabel = t('appt.view_confirmation')
      tone = 'text-green-700'
      break
    case 'draft':
      label = t('appt.confirmation_draft_saved')
      buttonLabel = t('appt.open_draft')
      tone = 'text-amber-700'
      break
    case 'skipped':
      label = t('appt.confirmation_skipped')
      buttonLabel = t('appt.send_anyway')
      tone = 'text-muted-foreground'
      break
    default:
      label = hasEmail ? t('appt.no_confirmation_sent') : t('appt.no_confirmation_no_email')
      buttonLabel = t('appt.send_confirmation')
      tone = 'text-muted-foreground'
  }

  return (
    <div className="flex items-center justify-between gap-2 rounded-md bg-muted/40 px-3 py-2">
      <span className={`text-xs ${tone}`}>{label}</span>
      <button
        onClick={onOpen}
        className="text-xs font-medium text-foreground hover:underline underline-offset-4"
      >
        {buttonLabel}
      </button>
    </div>
  )
}
