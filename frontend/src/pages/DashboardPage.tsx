import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { format, getISODay } from 'date-fns'
import { useTranslation } from 'react-i18next'
import { useTimeFormat } from '@/lib/timeFormat'
import { useDateLocale } from '@/lib/dateLocale'
import { useNavigate } from 'react-router-dom'
import { type Appointment, listAppointments } from '@/api/appointments'
import { type AppointmentRequest, listAllRequests } from '@/api/appointmentRequests'
import { listTimeEntries, checkIn, checkOut, type TimeEntry } from '@/api/time_entries'
import { getOperatingHours } from '@/api/settings'
import { useAuth } from '@/store/auth'
import { Button } from '@/components/ui/button'
import { CalendarDays, ClipboardList, ArrowRight, Clock, LogIn, LogOut, Plus } from 'lucide-react'
import ManualTimeEntryDialog from '@/components/ManualTimeEntryDialog'

const APPT_STATUS_DOT: Record<Appointment['status'], string> = {
  confirmed:   'bg-blue-400',
  in_progress: 'bg-green-500',
  completed:   'bg-muted-foreground',
  cancelled:   'bg-destructive',
  no_show:     'bg-destructive',
}

// ── Today's schedule ──────────────────────────────────────────────────────────

function TodaySchedule({ appointments }: { appointments: Appointment[] }) {
  const navigate = useNavigate()
  const { formatTime: ft } = useTimeFormat()
  const { t } = useTranslation()

  const active = appointments.filter(a => a.status !== 'cancelled' && a.status !== 'no_show')

  // Flatten to individual items sorted by start time
  const items = active
    .flatMap(appt =>
      appt.items
        .filter(i => i.status !== 'cancelled')
        .map(item => ({ appt, item }))
    )
    .sort((a, b) => new Date(a.item.start_time).getTime() - new Date(b.item.start_time).getTime())

  if (items.length === 0) {
    return <p className="text-sm text-muted-foreground py-4 text-center">{t('dashboard.no_appointments')}</p>
  }

  return (
    <ul className="divide-y">
      {items.map(({ appt, item }) => {
        const start = new Date(item.start_time)
        const duration = item.duration_override_minutes ?? item.duration_minutes
        const end = new Date(start.getTime() + duration * 60000)
        return (
          <li key={item.id}>
            <button
              onClick={() => navigate('/appointments')}
              className="w-full text-left px-4 py-3 hover:bg-muted/40 transition-colors flex items-center gap-3"
            >
              <div className="w-20 flex-shrink-0 text-right">
                <span className="text-sm font-medium tabular-nums">{ft(start)}</span>
              </div>
              <div
                className={`w-1.5 h-1.5 rounded-full flex-shrink-0 ${APPT_STATUS_DOT[appt.status]}`}
              />
              <div className="flex-1 min-w-0">
                <p className="text-sm font-medium truncate">
                  {appt.client.first_name} {appt.client.last_name}
                </p>
                <p className="text-xs text-muted-foreground truncate">
                  {item.service.name} · {item.provider.display_name}
                  {' · '}{ft(start)}–{ft(end)}
                </p>
              </div>
              <ArrowRight size={14} className="text-muted-foreground flex-shrink-0" />
            </button>
          </li>
        )
      })}
    </ul>
  )
}

// ── Staff clock widget ────────────────────────────────────────────────────────

interface StaffClockWidgetProps {
  providers: { id: string; display_name: string }[]
  entries: TimeEntry[]
  today: string
}

function StaffClockWidget({ providers, entries, today }: StaffClockWidgetProps) {
  const qc = useQueryClient()
  const { t } = useTranslation()

  const checkInMut = useMutation({
    mutationFn: (provider_id: string) => checkIn(provider_id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['time-entries', today] }),
  })

  const checkOutMut = useMutation({
    mutationFn: (entry_id: string) => checkOut(entry_id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['time-entries', today] }),
  })

  if (providers.length === 0) {
    return <p className="text-sm text-muted-foreground py-4 text-center">{t('dashboard.no_providers_scheduled')}</p>
  }

  return (
    <ul className="divide-y">
      {providers.map(p => {
        const entry = entries.find(e => e.provider_id === p.id && e.check_out_at === null)
        const checkedOut = entries.find(e => e.provider_id === p.id && e.check_out_at !== null)
        const active = entry ?? checkedOut

        return (
          <li key={p.id} className="flex items-center justify-between px-4 py-3">
            <div>
              <p className="text-sm font-medium">{p.display_name}</p>
              {active && (
                <p className="text-xs text-muted-foreground">
                  In {new Date(active.check_in_at).toLocaleTimeString('en-CA', { hour: 'numeric', minute: '2-digit' })}
                  {active.check_out_at && ` · Out ${new Date(active.check_out_at).toLocaleTimeString('en-CA', { hour: 'numeric', minute: '2-digit' })} · ${active.hours}h`}
                </p>
              )}
            </div>
            {!entry && !checkedOut && (
              <Button
                size="sm"
                variant="outline"
                className="text-xs h-7"
                onClick={() => checkInMut.mutate(p.id)}
                disabled={checkInMut.isPending}
              >
                <LogIn size={12} className="mr-1" /> {t('dashboard.clock_in')}
              </Button>
            )}
            {entry && (
              <Button
                size="sm"
                variant="outline"
                className="text-xs h-7 text-emerald-600 border-emerald-200 hover:bg-emerald-50"
                onClick={() => checkOutMut.mutate(entry.id)}
                disabled={checkOutMut.isPending}
              >
                <LogOut size={12} className="mr-1" /> {t('dashboard.clock_out')}
              </Button>
            )}
            {!entry && checkedOut && (
              <span className="text-xs text-muted-foreground">{t('dashboard.status_done')}</span>
            )}
          </li>
        )
      })}
    </ul>
  )
}

// ── Pending requests ──────────────────────────────────────────────────────────

function PendingRequests({ requests }: { requests: AppointmentRequest[] }) {
  const navigate = useNavigate()
  const { t } = useTranslation()
  const { bcp47 } = useDateLocale()

  if (requests.length === 0) {
    return <p className="text-sm text-muted-foreground py-4 text-center">{t('dashboard.no_pending_requests')}</p>
  }

  return (
    <ul className="divide-y">
      {requests.map(req => (
        <li key={req.id}>
          <button
            onClick={() => navigate('/requests')}
            className="w-full text-left px-4 py-3 hover:bg-muted/40 transition-colors flex items-center gap-3"
          >
            <div className="flex-1 min-w-0">
              <p className="text-sm font-medium truncate">
                {req.first_name} {req.last_name}
              </p>
              <p className="text-xs text-muted-foreground truncate">
                {new Date(req.desired_date + 'T00:00:00').toLocaleDateString(bcp47, {
                  weekday: 'short', month: 'short', day: 'numeric',
                })}
                {req.desired_time_note && ` · ${req.desired_time_note}`}
                {' · '}{req.items.map(i => i.service_name).join(', ')}
              </p>
            </div>
            <ArrowRight size={14} className="text-muted-foreground flex-shrink-0" />
          </button>
        </li>
      ))}
    </ul>
  )
}

// ── Page ──────────────────────────────────────────────────────────────────────

export default function DashboardPage() {
  const navigate = useNavigate()
  const { t } = useTranslation()
  const { locale } = useDateLocale()
  const { user } = useAuth()
  const isAdmin = user?.role === 'tenant_admin' || user?.role === 'super_admin'
  const today = format(new Date(), 'yyyy-MM-dd')
  const [addingEntry, setAddingEntry] = useState(false)

  const { data: appointments = [] } = useQuery({
    queryKey: ['appointments', today],
    queryFn: () => listAppointments(today),
    refetchInterval: 60_000,
  })

  const { data: pendingRequests = [] } = useQuery({
    queryKey: ['requests', 'new'],
    queryFn: () => listAllRequests('new'),
    refetchInterval: 60_000,
  })

  const { data: timeEntries = [] } = useQuery({
    queryKey: ['time-entries', today],
    queryFn: () => listTimeEntries(today),
    refetchInterval: 60_000,
  })

  const { data: operatingHours = [] } = useQuery({
    queryKey: ['operating-hours'],
    queryFn: getOperatingHours,
  })

  // getISODay: 1=Mon…7=Sun → subtract 1 → 0=Mon…6=Sun (matches backend)
  const todayDow = getISODay(new Date()) - 1
  const todayHours = operatingHours.find(h => h.day_of_week === todayDow)
  const salonClosedToday = todayHours !== undefined && !todayHours.is_open

  const myProviderId = user?.provider_id ?? null

  // Each user sees only their own appointments. Admins without a linked provider see all.
  const activeAppts = appointments.filter(a => {
    if (a.status === 'cancelled' || a.status === 'no_show') return false
    if (myProviderId) return a.items.some(i => i.provider.id === myProviderId)
    return true
  })
  const serviceCount = activeAppts.reduce(
    (n, a) => n + a.items.filter(i => i.status !== 'cancelled' && (!myProviderId || i.provider.id === myProviderId)).length, 0
  )

  const scheduledProviders = myProviderId
    ? activeAppts.flatMap(a => a.items
        .filter(i => i.provider.id === myProviderId)
        .map(i => i.provider)
      ).filter((p, idx, arr) => arr.findIndex(x => x.id === p.id) === idx)
    : Array.from(
        new Map(
          activeAppts.flatMap(a => a.items.map(i => [i.provider.id, i.provider] as [string, { id: string; display_name: string }]))
        ).values()
      ).sort((a, b) => a.display_name.localeCompare(b.display_name))

  return (
    <div className="h-full overflow-auto bg-muted/30">
      <div className="max-w-4xl mx-auto px-6 py-8 space-y-6">

        {/* Header */}
        <div>
          <h1 className="text-2xl font-semibold">
            {(() => { const h = new Date().getHours(); return h < 12 ? t('dashboard.good_morning') : h < 17 ? t('dashboard.good_afternoon') : t('dashboard.good_evening') })()}
          </h1>
          <p className="text-muted-foreground mt-0.5">
            {format(new Date(), 'EEEE, MMMM d, yyyy', { locale })}
          </p>
        </div>

        {salonClosedToday && (
          <div className="rounded-lg border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-800">
            {t('dashboard.salon_closed')}
          </div>
        )}

        {/* Stat cards */}
        <div className="grid grid-cols-3 gap-4">
          <button
            onClick={() => navigate('/appointments')}
            className="border rounded-lg p-5 bg-white text-left hover:border-foreground/30 transition-colors"
          >
            <div className="flex items-center gap-2 text-muted-foreground text-sm mb-3">
              <CalendarDays size={14} />
              {t('dashboard.services_today')}
            </div>
            <p className="text-3xl font-semibold">{serviceCount}</p>
            <p className="text-xs text-muted-foreground mt-1">
              {t('dashboard.across_visits', { count: activeAppts.length })}
            </p>
          </button>

          <button
            onClick={() => navigate('/requests')}
            className={`border rounded-lg p-5 text-left hover:border-foreground/30 transition-colors
              ${pendingRequests.length > 0 ? 'bg-amber-50 border-amber-300' : 'bg-white'}`}
          >
            <div className="flex items-center gap-2 text-muted-foreground text-sm mb-3">
              <ClipboardList size={14} />
              {t('dashboard.pending_requests')}
            </div>
            <p className="text-3xl font-semibold">{pendingRequests.length}</p>
            <p className="text-xs text-muted-foreground mt-1">{t('dashboard.awaiting_review')}</p>
          </button>

          <button
            onClick={() => navigate('/appointments')}
            className="border rounded-lg p-5 bg-white text-left hover:border-foreground/30 transition-colors"
          >
            <div className="flex items-center gap-2 text-muted-foreground text-sm mb-3">
              <CalendarDays size={14} />
              {t('dashboard.providers_working')}
            </div>
            <p className="text-3xl font-semibold">{providerSet.size}</p>
            <p className="text-xs text-muted-foreground mt-1">{t('dashboard.scheduled_today')}</p>
          </button>
        </div>

        {/* Schedule + requests */}
        <div className="grid grid-cols-5 gap-4">

          {/* Today's schedule (wider) */}
          <div className="col-span-3 bg-white border rounded-lg overflow-hidden">
            <div className="flex items-center justify-between px-4 py-3 border-b">
              <h2 className="text-sm font-medium">{t('dashboard.todays_schedule')}</h2>
              <button
                onClick={() => navigate('/appointments')}
                className="text-xs text-muted-foreground hover:text-foreground flex items-center gap-1"
              >
                {t('dashboard.open_book')} <ArrowRight size={12} />
              </button>
            </div>
            <TodaySchedule appointments={appointments} />
          </div>

          {/* Pending requests */}
          <div className="col-span-2 bg-white border rounded-lg overflow-hidden">
            <div className="flex items-center justify-between px-4 py-3 border-b">
              <h2 className="text-sm font-medium">{t('dashboard.section_pending_requests')}</h2>
              {pendingRequests.length > 0 && (
                <button
                  onClick={() => navigate('/requests')}
                  className="text-xs text-muted-foreground hover:text-foreground flex items-center gap-1"
                >
                  {t('dashboard.review_all')} <ArrowRight size={12} />
                </button>
              )}
            </div>
            <PendingRequests requests={pendingRequests} />
          </div>

        </div>

        {pendingRequests.length > 0 && (
          <div className="flex gap-3">
            <Button variant="outline" onClick={() => navigate('/requests')}>
              {t('dashboard.review_requests', { count: pendingRequests.length })}
            </Button>
          </div>
        )}

        {/* Staff clock-in */}
        <div className="bg-white border rounded-lg overflow-hidden">
          <div className="flex items-center justify-between px-4 py-3 border-b">
            <div className="flex items-center gap-2">
              <Clock size={14} className="text-muted-foreground" />
              <h2 className="text-sm font-medium">{t('dashboard.staff_attendance')}</h2>
            </div>
            {isAdmin && (
              <Button
                size="sm"
                variant="ghost"
                className="h-7 text-xs text-muted-foreground"
                onClick={() => setAddingEntry(true)}
              >
                <Plus size={12} className="mr-1" />
                {t('dashboard.add_time_entry')}
              </Button>
            )}
          </div>
          <StaffClockWidget providers={scheduledProviders} entries={timeEntries} today={today} />
        </div>

        <ManualTimeEntryDialog
          open={addingEntry}
          onClose={() => setAddingEntry(false)}
          defaultDate={today}
        />

      </div>
    </div>
  )
}
