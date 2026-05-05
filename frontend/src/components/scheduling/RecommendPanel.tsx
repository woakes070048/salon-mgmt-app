import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { getRecommendations, type Recommendation, type RequestedService } from '@/api/scheduling'
import { Button } from '@/components/ui/button'

interface Props {
  tenantId: string
  clientId?: string
  services: { serviceId: string; preferredProviderId?: string }[]
  desiredDate: string     // ISO date YYYY-MM-DD
  earliestStart?: string  // HH:MM
  latestEnd?: string      // HH:MM
  onSelect: (rec: Recommendation) => void
}

function minutesToHhmm(minutes: number): string {
  const h = Math.floor(minutes / 60)
  const m = minutes % 60
  return `${String(h).padStart(2, '0')}:${String(m).padStart(2, '0')}`
}

function formatHhmm(hhmm: string): string {
  const [hStr, mStr] = hhmm.split(':')
  const h = parseInt(hStr, 10)
  const m = parseInt(mStr, 10)
  const period = h < 12 ? 'am' : 'pm'
  const h12 = h % 12 || 12
  return m === 0 ? `${h12}${period}` : `${h12}:${String(m).padStart(2, '0')}${period}`
}

export default function RecommendPanel({
  tenantId,
  clientId,
  services,
  desiredDate,
  earliestStart,
  latestEnd,
  onSelect,
}: Props) {
  const [selectedIdx, setSelectedIdx] = useState<number | null>(null)

  const requestedServices: RequestedService[] = services.map((s) => ({
    service_id: s.serviceId,
    preferred_provider_id: s.preferredProviderId ?? null,
  }))

  const enabled =
    tenantId.length > 0 &&
    desiredDate.length === 10 &&
    requestedServices.length > 0

  const { data, isLoading, isError, error } = useQuery({
    queryKey: ['scheduling-recommend', tenantId, desiredDate, JSON.stringify(requestedServices), earliestStart, latestEnd],
    queryFn: () =>
      getRecommendations({
        tenant_id: tenantId,
        client_id: clientId ?? null,
        services: requestedServices,
        desired_date: desiredDate,
        earliest_start: earliestStart,
        latest_end: latestEnd,
      }),
    enabled,
    staleTime: 30_000,
  })

  if (!enabled) return null

  if (isLoading) {
    return (
      <div className="rounded-lg border bg-muted/30 p-4">
        <p className="text-sm text-muted-foreground">Finding available slots…</p>
      </div>
    )
  }

  if (isError) {
    return (
      <div className="rounded-lg border border-destructive/30 bg-destructive/5 p-4">
        <p className="text-sm text-destructive">
          Could not load recommendations:{' '}
          {error instanceof Error ? error.message : 'Unknown error'}
        </p>
      </div>
    )
  }

  const recommendations = data?.recommendations ?? []

  if (recommendations.length === 0) {
    return (
      <div className="rounded-lg border bg-muted/30 p-4">
        <p className="text-sm text-muted-foreground">
          No available slots found for the selected date and services.
        </p>
      </div>
    )
  }

  return (
    <div className="space-y-2">
      <p className="text-xs font-medium text-muted-foreground uppercase tracking-wide">
        Suggested slots
      </p>

      <div className="space-y-2">
        {recommendations.map((rec, idx) => (
          <div
            key={idx}
            className={[
              'rounded-lg border p-3 transition-colors cursor-pointer',
              selectedIdx === idx
                ? 'border-primary bg-primary/5'
                : 'border-border hover:border-primary/50 hover:bg-muted/30',
            ].join(' ')}
            onClick={() => setSelectedIdx(idx)}
          >
            <div className="flex items-start justify-between gap-3">
              <div className="flex-1 min-w-0">
                {/* Per-service assignments */}
                <ul className="space-y-0.5">
                  {rec.items.map((item, iIdx) => (
                    <li key={iIdx} className="text-sm">
                      <span className="font-medium">{item.provider_name}</span>
                      <span className="text-muted-foreground"> · {item.service_name}</span>
                      <span className="text-muted-foreground">
                        {' '}
                        {formatHhmm(item.start_time)}–{formatHhmm(item.end_time)}
                      </span>
                    </li>
                  ))}
                </ul>

                {/* Rationale + badges */}
                <div className="mt-1.5 flex flex-wrap items-center gap-1.5">
                  <span className="text-xs text-muted-foreground">{rec.rationale}</span>
                  {rec.requires_consent && (
                    <span className="inline-flex items-center rounded px-1.5 py-0.5 text-[10px] font-medium bg-amber-100 text-amber-800 border border-amber-200">
                      Requires approval
                    </span>
                  )}
                  <span className="text-[10px] text-muted-foreground/60">
                    {rec.total_duration_minutes} min total
                  </span>
                </div>
              </div>

              <Button
                size="sm"
                variant={selectedIdx === idx ? 'default' : 'outline'}
                className="shrink-0"
                onClick={(e) => {
                  e.stopPropagation()
                  setSelectedIdx(idx)
                  onSelect(rec)
                }}
              >
                Use this
              </Button>
            </div>
          </div>
        ))}
      </div>

      {/* "Show more options" stub — not yet implemented */}
      <div className="flex justify-center pt-1">
        <Button
          variant="ghost"
          size="sm"
          disabled
          className="text-xs text-muted-foreground"
        >
          Show more options
        </Button>
      </div>
    </div>
  )
}
