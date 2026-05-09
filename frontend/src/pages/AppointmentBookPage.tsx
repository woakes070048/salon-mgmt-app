import { useState, useEffect, useRef, useCallback } from 'react'
import { useTranslation } from 'react-i18next'
import { useDateLocale } from '@/lib/dateLocale'
import { useQuery } from '@tanstack/react-query'
import { useSearchParams, useNavigate, useLocation } from 'react-router-dom'
import { format, addDays, subDays, parseISO, getISODay } from 'date-fns'
import { listAppointments, type Appointment, type AppointmentItem } from '@/api/appointments'
import { listProviders, type Provider } from '@/api/providers'
import { getSchedule } from '@/api/schedules'
import { getRequest } from '@/api/appointmentRequests'
import { type Recommendation } from '@/api/scheduling'
import { getBranding, getOperatingHours, type SlotMinutes } from '@/api/settings'
import { listTimeBlocks, type TimeBlock } from '@/api/timeBlocks'
import TimeGrid from '@/components/appointment-book/TimeGrid'
import AppointmentDetail from '@/components/appointment-book/AppointmentDetail'
import BookingForm from '@/components/appointment-book/BookingForm'
import TimeBlockEditDialog from '@/components/appointment-book/TimeBlockEditDialog'
import ClientCard from '@/components/ClientCard'
import ConvertRequestPanel from '@/components/ConvertRequestPanel'
import ConfirmationDialog from '@/components/appointment-book/ConfirmationDialog'
import { Button } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/skeleton'
import { Eye, EyeOff, Keyboard, UserPlus, X } from 'lucide-react'
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover'

// ── Grid geometry (must match TimeGrid constants) ─────────────────────────────
const SLOT_HEIGHT = 20
const START_HOUR  = 8
const END_HOUR    = 21

type TSI = { providerId: string; slotTopPx: number }

function tsiToTime(tsi: TSI, slotMinutes: number): string {
  const totalMins = START_HOUR * 60 + (tsi.slotTopPx / SLOT_HEIGHT) * slotMinutes
  const h = Math.floor(totalMins / 60)
  const m = totalMins % 60
  return `${String(h).padStart(2, '0')}:${String(m).padStart(2, '0')}`
}

// ── Shortcuts panel ───────────────────────────────────────────────────────────
interface ShortcutDef {
  label: string
  keys: string[]
  action: () => void
  disabled?: boolean
}

function Kbd({ k }: { k: string }) {
  return (
    <kbd className="inline-flex items-center justify-center min-w-[1.5rem] h-6 px-1.5 text-xs font-mono bg-muted border rounded">
      {k}
    </kbd>
  )
}

function ShortcutsPanel({ shortcuts, onClose }: { shortcuts: ShortcutDef[]; onClose: () => void }) {
  const { t } = useTranslation()
  return (
    <>
      <div className="fixed inset-0 z-40" onClick={onClose} />
      <div className="fixed bottom-16 right-6 z-50 bg-white border rounded-xl shadow-xl p-3 w-64">
        <p className="text-xs font-semibold text-muted-foreground px-1 pb-2 uppercase tracking-wide">
          {t('appt.shortcuts_title')}
        </p>
        <div className="space-y-0.5">
          {shortcuts.map(({ label, keys, action, disabled }) => (
            <button
              key={label}
              disabled={disabled}
              onClick={() => { action(); onClose() }}
              className="flex items-center justify-between w-full px-2 py-1.5 text-sm rounded-md hover:bg-muted/60 disabled:opacity-40 disabled:cursor-not-allowed"
            >
              <span>{label}</span>
              <span className="flex gap-1">
                {keys.map(k => <Kbd key={k} k={k} />)}
              </span>
            </button>
          ))}
        </div>
      </div>
    </>
  )
}

// ── Page ─────────────────────────────────────────────────────────────────────
export default function AppointmentBookPage() {
  const { t } = useTranslation()
  const { locale } = useDateLocale()
  const [searchParams, setSearchParams] = useSearchParams()
  const navigate = useNavigate()
  const location = useLocation()
  // Capture recommendation from navigation state immediately — before setSearchParams
  // replaces the history entry and drops the state.
  const [pendingRec] = useState<Recommendation | undefined>(
    () => (location.state as { recommendation?: Recommendation } | null)?.recommendation
  )
  const requestId = searchParams.get('request')
  const highlightApptId = searchParams.get('appointment')

  const [date, setDate] = useState(() => searchParams.get('date') ?? format(new Date(), 'yyyy-MM-dd'))
  const [selected, setSelected] = useState<{ item: AppointmentItem; appt: Appointment } | null>(null)
  const [booking, setBooking] = useState<{ time?: string; providerId?: string } | null>(null)
  const [editingBlock, setEditingBlock] = useState<TimeBlock | null>(null)
  const [creatingBlock, setCreatingBlock] = useState<{ time: string; providerId: string } | null>(null)
  const [selectedClientId, setSelectedClientId] = useState<string | null>(null)
  const [pendingConfirmation, setPendingConfirmation] = useState<{
    id: string; appointment_date: string; clientEmail: string | null
  } | null>(null)
  const [showCancelled, setShowCancelled] = useState(() =>
    localStorage.getItem('showCancelled') === 'true'
  )
  const [tsi, setTsi] = useState<TSI | null>(null)
  const [showShortcuts, setShowShortcuts] = useState(false)

  const { data: branding } = useQuery({ queryKey: ['branding'], queryFn: getBranding })
  const slotMinutes: SlotMinutes = (branding?.slot_minutes ?? 10) as SlotMinutes

  const { data: convertRequest } = useQuery({
    queryKey: ['request', requestId],
    queryFn: () => getRequest(requestId!),
    enabled: !!requestId,
  })

  useEffect(() => {
    const urlDate = searchParams.get('date')
    if (urlDate && urlDate !== date) setDate(urlDate)
  }, [searchParams.get('date')])

  // Keep URL in sync. Preserve 'request' param so the convert panel stays mounted.
  useEffect(() => {
    const params: Record<string, string> = { date }
    if (requestId) params.request = requestId
    setSearchParams(params, { replace: true })
  }, [date])

  useEffect(() => {
    if (convertRequest) setDate(convertRequest.desired_date)
  }, [convertRequest?.id])

  const { data: providers = [], isLoading: providersLoading } = useQuery<Provider[]>({
    queryKey: ['providers'],
    queryFn: listProviders,
  })

  const { data: appointments = [], isLoading: apptLoading } = useQuery<Appointment[]>({
    queryKey: ['appointments', date],
    queryFn: () => listAppointments(date),
  })

  useEffect(() => {
    if (!highlightApptId || appointments.length === 0) return
    const appt = appointments.find(a => a.id === highlightApptId)
    if (appt && appt.items.length > 0) {
      setSelected({ item: appt.items[0], appt })
      navigate('/appointments', { replace: true })
    }
  }, [highlightApptId, appointments])

  const { data: schedules = [] } = useQuery({
    queryKey: ['schedules', date],
    queryFn: () => getSchedule(date),
  })

  const { data: timeBlocks = [] } = useQuery<TimeBlock[]>({
    queryKey: ['time-blocks', date],
    queryFn: () => listTimeBlocks(date),
  })

  const [pinnedProviderIds, setPinnedProviderIds] = useState<Set<string>>(new Set())

  // Reset pins when the date changes
  useEffect(() => { setPinnedProviderIds(new Set()) }, [date])

  const { data: operatingHours = [] } = useQuery({
    queryKey: ['operating-hours'],
    queryFn: getOperatingHours,
    staleTime: 5 * 60 * 1000,
  })

  // day_of_week: 0=Mon…6=Sun; date-fns getISODay: 1=Mon…7=Sun → subtract 1
  const dayIndex = getISODay(parseISO(date + 'T12:00:00')) - 1
  const salonOpen = operatingHours.length === 0
    || (operatingHours.find(d => d.day_of_week === dayIndex)?.is_open ?? true)

  const activeProviders = providers.filter(p => p.has_appointments)
  const workingProviderIds = new Set(schedules.filter(s => s.is_working).map(s => s.provider_id))
  const providersWithAppts = new Set(appointments.flatMap(a => a.items.map(i => i.provider.id)))

  // Providers that auto-show: must be scheduled (or have appointments) AND salon must be open
  // AND provider must be a real bookable person (makes_appointments=true).
  // Providers with makes_appointments=false (e.g. HOUSE) always stay in the pin pool.
  const autoVisible = (!salonOpen || schedules.length === 0)
    ? []
    : activeProviders.filter(p =>
        p.makes_appointments &&
        (workingProviderIds.has(p.id) || providersWithAppts.has(p.id))
      )

  const visibleProviders = [
    ...autoVisible,
    ...activeProviders.filter(p => pinnedProviderIds.has(p.id) && !autoVisible.some(v => v.id === p.id)),
  ]
  const unscheduledProviders = activeProviders.filter(
    p => !autoVisible.some(v => v.id === p.id) && !pinnedProviderIds.has(p.id)
  )

  // Inject synthetic zero-window schedule for pinned providers so the whole
  // column shades amber and the drag warning fires for any appointment.
  const augmentedSchedules = [
    ...schedules,
    ...[...pinnedProviderIds]
      .filter(id => !workingProviderIds.has(id))
      .map(id => ({ provider_id: id, date, is_working: true, start_time: '08:00', end_time: '08:00' })),
  ]
  const displayDate = parseISO(date + 'T12:00:00')

  const prev  = useCallback(() => setDate(format(subDays(displayDate, 1), 'yyyy-MM-dd')), [displayDate])
  const next  = useCallback(() => setDate(format(addDays(displayDate, 1), 'yyyy-MM-dd')), [displayDate])
  const goToday = useCallback(() => setDate(format(new Date(), 'yyyy-MM-dd')), [])

  function toggleCancelled() {
    setShowCancelled(v => { localStorage.setItem('showCancelled', String(!v)); return !v })
  }

  const displayedAppointments = showCancelled
    ? appointments
    : appointments.filter(a => a.status !== 'cancelled' && a.status !== 'no_show')

  // ── TSI helpers ─────────────────────────────────────────────────────────────
  const totalSlots = ((END_HOUR - START_HOUR) * 60) / slotMinutes
  const maxSlotTop = (totalSlots - 1) * SLOT_HEIGHT

  function newApptAtTsi() {
    if (!tsi) return
    setBooking({ time: tsiToTime(tsi, slotMinutes), providerId: tsi.providerId })
  }
  function newBlockAtTsi() {
    if (!tsi) return
    setCreatingBlock({ time: tsiToTime(tsi, slotMinutes), providerId: tsi.providerId })
  }

  // ── Keyboard shortcuts ──────────────────────────────────────────────────────
  const tsiRef = useRef(tsi)
  useEffect(() => { tsiRef.current = tsi }, [tsi])

  useEffect(() => {
    function onKeyDown(e: KeyboardEvent) {
      const target = e.target as HTMLElement
      const isTyping = target.tagName === 'INPUT' || target.tagName === 'TEXTAREA' || target.isContentEditable

      // ? always toggles panel (unless typing)
      if (e.key === '?' && !isTyping) {
        setShowShortcuts(v => !v)
        return
      }
      // Escape closes panel
      if (e.key === 'Escape') {
        setShowShortcuts(false)
        return
      }

      if (isTyping) return

      // Suppress grid shortcuts when any panel/dialog is open
      const panelOpen = booking !== null || selected !== null || editingBlock !== null
        || creatingBlock !== null || selectedClientId !== null || pendingConfirmation !== null
        || !!convertRequest

      switch (e.key) {
        case 'ArrowLeft':
          e.preventDefault()
          if (!panelOpen) prev()
          break
        case 'ArrowRight':
          e.preventDefault()
          if (!panelOpen) next()
          break
        case 'h': case 'H':
          if (!panelOpen) goToday()
          break
        case 't': case 'T':
          if (!panelOpen) navigate('/till')
          break
        case 'c': case 'C':
          if (!panelOpen) navigate('/clients')
          break
        case 'n': case 'N':
          if (!panelOpen && tsiRef.current) {
            setBooking({ time: tsiToTime(tsiRef.current, slotMinutes), providerId: tsiRef.current.providerId })
          }
          break
        case 'b': case 'B':
          if (!panelOpen && tsiRef.current) {
            setCreatingBlock({ time: tsiToTime(tsiRef.current, slotMinutes), providerId: tsiRef.current.providerId })
          }
          break
        case 'ArrowUp':
          e.preventDefault()
          if (!panelOpen) setTsi(t => t ? { ...t, slotTopPx: Math.max(0, t.slotTopPx - SLOT_HEIGHT) } : t)
          break
        case 'ArrowDown':
          e.preventDefault()
          if (!panelOpen) setTsi(t => t ? { ...t, slotTopPx: Math.min(maxSlotTop, t.slotTopPx + SLOT_HEIGHT) } : t)
          break
      }
    }

    window.addEventListener('keydown', onKeyDown)
    return () => window.removeEventListener('keydown', onKeyDown)
  }, [booking, selected, editingBlock, creatingBlock, selectedClientId, pendingConfirmation,
      convertRequest, prev, next, goToday, slotMinutes, maxSlotTop])

  // ── Shortcut definitions (also used by panel buttons) ──────────────────────
  const anyPanelOpen = booking !== null || selected !== null || editingBlock !== null
    || creatingBlock !== null || selectedClientId !== null || pendingConfirmation !== null
    || !!convertRequest

  const shortcuts: ShortcutDef[] = [
    { label: t('appt.shortcut_prev_day'),   keys: ['←'], action: prev,          disabled: anyPanelOpen },
    { label: t('appt.shortcut_next_day'),   keys: ['→'], action: next,          disabled: anyPanelOpen },
    { label: t('appt.shortcut_today'),      keys: ['H'], action: goToday,       disabled: anyPanelOpen },
    { label: t('nav.till'),                 keys: ['T'], action: () => navigate('/till'),    disabled: anyPanelOpen },
    { label: t('nav.clients'),              keys: ['C'], action: () => navigate('/clients'), disabled: anyPanelOpen },
    { label: t('appt.shortcut_new_appt'),   keys: ['N'], action: newApptAtTsi,  disabled: anyPanelOpen || !tsi },
    { label: t('appt.shortcut_new_block'),  keys: ['B'], action: newBlockAtTsi, disabled: anyPanelOpen || !tsi },
    { label: t('appt.shortcut_move_up'),    keys: ['↑'], action: () => setTsi(t => t ? { ...t, slotTopPx: Math.max(0, t.slotTopPx - SLOT_HEIGHT) } : t), disabled: anyPanelOpen || !tsi },
    { label: t('appt.shortcut_move_down'),  keys: ['↓'], action: () => setTsi(t => t ? { ...t, slotTopPx: Math.min(maxSlotTop, t.slotTopPx + SLOT_HEIGHT) } : t), disabled: anyPanelOpen || !tsi },
    { label: t('appt.shortcut_show'),       keys: ['?'], action: () => setShowShortcuts(v => !v) },
  ]

  const isLoading = providersLoading || apptLoading

  return (
    <div className="flex flex-col h-full bg-muted/30">
      <header className="flex items-center justify-between px-4 py-2 bg-white border-b gap-4 flex-shrink-0">
        <div className="flex items-center gap-2">
          <Button variant="outline" size="sm" onClick={prev}>‹</Button>
          <Button variant="outline" size="sm" onClick={goToday}>{t('appt.today')}</Button>
          <span className="text-sm font-medium w-40 text-center">
            {format(displayDate, 'EEEE, MMM d, yyyy', { locale })}
          </span>
          <Button variant="outline" size="sm" onClick={next}>›</Button>
        </div>

        <div className="flex items-center gap-2">
          {/* Pinned (unscheduled) provider badges */}
          {[...pinnedProviderIds].map(id => {
            const p = activeProviders.find(x => x.id === id)
            if (!p) return null
            return (
              <span key={id} className="inline-flex items-center gap-1 text-xs bg-amber-100 text-amber-800 border border-amber-200 rounded px-2 py-1">
                {p.display_name}
                <button onClick={() => setPinnedProviderIds(prev => { const s = new Set(prev); s.delete(id); return s })} className="hover:text-amber-900">
                  <X size={10} />
                </button>
              </span>
            )
          })}

          {/* Add unscheduled staff */}
          {unscheduledProviders.length > 0 && (
            <Popover>
              <PopoverTrigger asChild>
                <Button variant="outline" size="sm" className="text-muted-foreground gap-1.5">
                  <UserPlus size={14} />
                  {t('appt.add_staff')}
                </Button>
              </PopoverTrigger>
              <PopoverContent align="end" className="w-52 p-2">
                <p className="text-xs font-medium text-muted-foreground px-2 pb-2">{t('appt.not_scheduled')}</p>
                {unscheduledProviders.map(p => (
                  <button
                    key={p.id}
                    onClick={() => setPinnedProviderIds(prev => new Set([...prev, p.id]))}
                    disabled={pinnedProviderIds.has(p.id)}
                    className="w-full text-left text-sm px-2 py-1.5 rounded hover:bg-muted disabled:opacity-40 disabled:cursor-not-allowed"
                  >
                    {p.display_name}
                  </button>
                ))}
              </PopoverContent>
            </Popover>
          )}

          <Button
            variant="outline"
            size="sm"
            onClick={toggleCancelled}
            className={showCancelled ? '' : 'text-muted-foreground'}
            title={showCancelled ? t('appt.hide_cancelled') : t('appt.show_cancelled')}
          >
            {showCancelled ? <Eye size={14} /> : <EyeOff size={14} />}
            <span className="ml-1.5">Cancelled</span>
          </Button>
          <Button size="sm" onClick={() => setBooking({})}>{t('appt.new_button')}</Button>
        </div>
      </header>

      <main className="flex-1 overflow-hidden p-4">
        {isLoading ? (
          <div className="space-y-2">
            <Skeleton className="h-10 w-full" />
            <Skeleton className="h-96 w-full" />
          </div>
        ) : (
          <TimeGrid
            providers={visibleProviders}
            appointments={displayedAppointments}
            timeBlocks={timeBlocks}
            date={date}
            slotMinutes={slotMinutes}
            providerHours={augmentedSchedules}
            pinnedProviderIds={pinnedProviderIds}
            tsi={tsi}
            onTsiChange={(t) => { setTsi(t); if (t) (document.activeElement as HTMLElement)?.blur() }}
            onItemClick={(item, appt) => setSelected({ item, appt })}
            onNewAppointment={(time, providerId) => setBooking({ time, providerId })}
            onNewBlock={(time, providerId) => setCreatingBlock({ time, providerId })}
            onBlockClick={setEditingBlock}
            onClientClick={setSelectedClientId}
          />
        )}
      </main>

      {/* Floating shortcuts toggle */}
      <Button
        variant="outline"
        size="icon"
        onClick={(e) => { setShowShortcuts(v => !v); (e.currentTarget as HTMLElement).blur() }}
        className="fixed bottom-6 right-6 z-40 h-9 w-9 rounded-full shadow-md"
        title="Keyboard shortcuts (?)"
      >
        <Keyboard size={16} />
      </Button>

      {showShortcuts && (
        <ShortcutsPanel shortcuts={shortcuts} onClose={() => setShowShortcuts(false)} />
      )}

      <AppointmentDetail
        item={selected?.item ?? null}
        appointment={selected ? (appointments.find(a => a.id === selected.appt.id) ?? selected.appt) : null}
        date={date}
        onClose={() => setSelected(null)}
      />

      <BookingForm
        open={booking !== null}
        date={date}
        initialTime={booking?.time}
        initialProviderId={booking?.providerId}
        providers={visibleProviders}
        providerHours={schedules}
        slotMinutes={slotMinutes}
        onClose={() => setBooking(null)}
        onSaved={(appt) => { setBooking(null); setPendingConfirmation(appt) }}
      />

      <TimeBlockEditDialog
        block={editingBlock}
        creating={creatingBlock}
        date={date}
        providers={visibleProviders}
        onClose={() => { setEditingBlock(null); setCreatingBlock(null) }}
      />

      <ClientCard
        clientId={selectedClientId}
        onClose={() => setSelectedClientId(null)}
      />

      {convertRequest && (
        <ConvertRequestPanel
          request={convertRequest}
          date={date}
          onDateChange={setDate}
          initialRecommendation={pendingRec}
          onClose={() => navigate('/appointments')}
          onConverted={apptDate => {
            setDate(apptDate)
            navigate('/appointments')
          }}
        />
      )}

      {pendingConfirmation && (
        <ConfirmationDialog
          appointmentId={pendingConfirmation.id}
          appointmentDate={pendingConfirmation.appointment_date}
          open={true}
          recipientEmail={pendingConfirmation.clientEmail}
          onClose={() => setPendingConfirmation(null)}
        />
      )}
    </div>
  )
}
