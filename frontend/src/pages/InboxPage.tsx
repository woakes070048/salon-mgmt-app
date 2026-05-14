import { useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { useDateLocale } from '@/lib/dateLocale'
import { type AppointmentRequest, listAllRequests } from '@/api/appointmentRequests'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import InboxDetailPanel from '@/components/InboxDetailPanel'

const STATUS_VARIANT: Record<
  AppointmentRequest['status'],
  'default' | 'secondary' | 'outline' | 'destructive'
> = {
  new: 'secondary',
  reviewed: 'default',
  converted: 'outline',
  declined: 'destructive',
}

const STATUS_LABELS: Record<AppointmentRequest['status'], string> = {
  new: 'New',
  reviewed: 'Under review',
  converted: 'Confirmed',
  declined: 'Declined',
}

const FILTER_OPTIONS = [
  { value: '', label: 'All' },
  { value: 'new', label: 'New' },
  { value: 'reviewed', label: 'Under review' },
  { value: 'converted', label: 'Confirmed' },
  { value: 'declined', label: 'Declined' },
]

export default function InboxPage() {
  const { bcp47 } = useDateLocale()
  const navigate = useNavigate()
  const qc = useQueryClient()
  const [filter, setFilter] = useState('new')
  const [selected, setSelected] = useState<AppointmentRequest | null>(null)

  const { data: allRequests = [], isLoading } = useQuery({
    queryKey: ['all-requests', filter],
    queryFn: () => listAllRequests(filter || undefined),
  })

  const requests = allRequests.filter(r => r.source === 'email')

  function openConvert(req: AppointmentRequest) {
    const date = req.desired_date.slice(0, 10)
    navigate(`/appointments?request=${req.id}&date=${date}`)
  }

  function handleRefresh() {
    qc.invalidateQueries({ queryKey: ['all-requests'] })
    qc.invalidateQueries({ queryKey: ['requests', 'new'] })
    if (selected) {
      qc.invalidateQueries({ queryKey: ['request-recommendations', selected.id] })
    }
  }

  return (
    <div className="h-full overflow-auto bg-muted/30">
      <main className="max-w-3xl mx-auto px-4 py-6 space-y-4">
        <div>
          <h1 className="text-xl font-semibold">Booking Inbox</h1>
          <p className="text-sm text-muted-foreground mt-0.5">
            Inbound emails — AI-classified and ready for triage.
          </p>
        </div>

        <div className="flex items-center gap-2 flex-wrap">
          {FILTER_OPTIONS.map(opt => (
            <Button
              key={opt.value}
              variant={filter === opt.value ? 'default' : 'outline'}
              size="sm"
              onClick={() => setFilter(opt.value)}
            >
              {opt.label}
            </Button>
          ))}
        </div>

        {isLoading ? (
          <p className="text-muted-foreground text-sm">Loading…</p>
        ) : requests.length === 0 ? (
          <p className="text-muted-foreground text-sm py-8 text-center">No email requests.</p>
        ) : (
          <div className="space-y-3">
            {requests.map(req => (
              <Card
                key={req.id}
                className="cursor-pointer hover:shadow-sm transition-shadow"
                onClick={() => setSelected(req)}
              >
                <CardHeader className="pb-2">
                  <div className="flex items-start justify-between gap-2">
                    <CardTitle className="text-base">
                      {req.first_name} {req.last_name}
                    </CardTitle>
                    <Badge variant={STATUS_VARIANT[req.status]}>
                      {STATUS_LABELS[req.status]}
                    </Badge>
                  </div>
                  <CardDescription className="text-xs">
                    {new Date(req.desired_date + 'T00:00:00').toLocaleDateString(bcp47, {
                      weekday: 'short', month: 'short', day: 'numeric', year: 'numeric',
                    })}
                    {req.desired_time_note && ` · ${req.desired_time_note}`}
                    {' · submitted '}
                    {new Date(req.submitted_at).toLocaleDateString(bcp47, { month: 'short', day: 'numeric' })}
                  </CardDescription>
                </CardHeader>
                <CardContent className="pt-0">
                  <ul className="text-sm space-y-0.5 mb-3">
                    {req.items.map(item => (
                      <li key={item.id} className="text-muted-foreground">
                        • {item.service_name}
                        {item.preferred_provider_name && ` — ${item.preferred_provider_name}`}
                      </li>
                    ))}
                  </ul>
                  {(req.status === 'new' || req.status === 'reviewed') && (
                    <Button
                      size="sm"
                      onClick={e => { e.stopPropagation(); openConvert(req) }}
                    >
                      Convert to appointment
                    </Button>
                  )}
                </CardContent>
              </Card>
            ))}
          </div>
        )}

        {selected && (
          <div className="fixed inset-0 bg-black/40 z-40 flex justify-end" onClick={() => setSelected(null)}>
            <div className="w-full max-w-lg h-full bg-white overflow-auto shadow-xl" onClick={e => e.stopPropagation()}>
              <InboxDetailPanel
                request={selected}
                onClose={() => setSelected(null)}
                onRefresh={handleRefresh}
              />
            </div>
          </div>
        )}
      </main>
    </div>
  )
}
