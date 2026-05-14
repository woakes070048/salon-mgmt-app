import { useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { useDateLocale } from '@/lib/dateLocale'
import {
  type AppointmentRequest,
  listAllRequests,
} from '@/api/appointmentRequests'
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

export default function RequestsPage() {
  const { t } = useTranslation()
  const { bcp47 } = useDateLocale()
  const navigate = useNavigate()
  const qc = useQueryClient()
  const [filter, setFilter] = useState('new')
  const [selected, setSelected] = useState<AppointmentRequest | null>(null)

  const STATUS_LABELS: Record<AppointmentRequest['status'], string> = {
    new: t('requests.filter_new'),
    reviewed: t('requests.filter_under_review'),
    converted: t('requests.filter_confirmed'),
    declined: t('requests.filter_declined'),
  }

  const FILTER_OPTIONS = [
    { value: '', label: t('requests.filter_all') },
    { value: 'new', label: t('requests.filter_new') },
    { value: 'reviewed', label: t('requests.filter_under_review') },
    { value: 'converted', label: t('requests.filter_confirmed') },
    { value: 'declined', label: t('requests.filter_declined') },
  ]

  function openConvert(req: AppointmentRequest) {
    const date = req.desired_date.slice(0, 10)
    navigate(`/appointments?request=${req.id}&date=${date}`)
  }

  const { data: requests = [], isLoading } = useQuery({
    queryKey: ['all-requests', filter],
    queryFn: () => listAllRequests(filter || undefined),
  })

  function handleRefresh() {
    qc.invalidateQueries({ queryKey: ['all-requests'] })
    qc.invalidateQueries({ queryKey: ['requests', 'new'] })
    // Sync panel to refreshed data
    if (selected) {
      qc.invalidateQueries({ queryKey: ['request-recommendations', selected.id] })
    }
  }

  return (
    <div className="h-full overflow-auto bg-muted/30">
      <main className="max-w-3xl mx-auto px-4 py-6 space-y-4">
        <h1 className="text-xl font-semibold">{t('requests.page_title')}</h1>
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
          <p className="text-muted-foreground text-sm">{t('common.loading')}</p>
        ) : requests.length === 0 ? (
          <p className="text-muted-foreground text-sm py-8 text-center">{t('requests.no_requests')}</p>
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
                    <div className="flex items-center gap-1.5 flex-shrink-0">
                      {req.source === 'email' && (
                        <Badge variant="outline" className="text-xs">Email</Badge>
                      )}
                      <Badge variant={STATUS_VARIANT[req.status]}>
                        {STATUS_LABELS[req.status]}
                      </Badge>
                    </div>
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
                    <div className="flex gap-2">
                      <Button
                        size="sm"
                        onClick={(e) => { e.stopPropagation(); openConvert(req) }}
                      >
                        {t('requests.action_convert')}
                      </Button>
                    </div>
                  )}
                </CardContent>
              </Card>
            ))}
          </div>
        )}
      </main>

      {selected && (
        <InboxDetailPanel
          request={selected}
          onClose={() => setSelected(null)}
          onRefresh={handleRefresh}
        />
      )}
    </div>
  )
}
