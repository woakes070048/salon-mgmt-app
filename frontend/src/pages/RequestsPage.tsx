import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { useDateLocale } from '@/lib/dateLocale'
import {
  type AppointmentRequest,
  listAllRequests,
  reviewRequest,
} from '@/api/appointmentRequests'
import { useAuth } from '@/store/auth'
import { type Recommendation } from '@/api/scheduling'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Label } from '@/components/ui/label'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import RecommendPanel from '@/components/scheduling/RecommendPanel'

const STATUS_VARIANT: Record<
  AppointmentRequest['status'],
  'default' | 'secondary' | 'outline' | 'destructive'
> = {
  new: 'secondary',
  reviewed: 'default',
  converted: 'outline',
  declined: 'destructive',
}

// ── Review dialog ─────────────────────────────────────────────────────────────

function ReviewDialog({
  request,
  onClose,
  onSave,
  onConvert,
}: {
  request: AppointmentRequest | null
  onClose: () => void
  onSave: (id: string, status: AppointmentRequest['status'], notes: string) => Promise<void>
  onConvert: (rec?: Recommendation) => void
}) {
  const { t } = useTranslation()
  const { bcp47 } = useDateLocale()
  const { user } = useAuth()
  const [newStatus, setNewStatus] = useState<AppointmentRequest['status']>('reviewed')
  const [notes, setNotes] = useState('')
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const recommendServices = request?.items
    .filter(i => i.service_id)
    .map(i => ({ serviceId: i.service_id! })) ?? []

  const today = new Date().toISOString().slice(0, 10)
  const nowDate = new Date()
  const earliestStart = request?.desired_date === today
    ? `${String(nowDate.getHours()).padStart(2, '0')}:${String(nowDate.getMinutes()).padStart(2, '0')}`
    : undefined

  async function handleSave() {
    if (!request) return
    setSaving(true)
    setError(null)
    try {
      await onSave(request.id, newStatus, notes)
      onClose()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Save failed')
    } finally {
      setSaving(false)
    }
  }

  return (
    <Dialog open={!!request} onOpenChange={v => { if (!v) onClose() }}>
      <DialogContent className="max-w-xl">
        <DialogHeader>
          <DialogTitle>{t('requests.review_title')}</DialogTitle>
        </DialogHeader>

        {request && (
          <div className="space-y-4 py-2">
            <div className="rounded-md bg-muted px-4 py-3 space-y-1 text-sm">
              <p className="font-medium">{request.first_name} {request.last_name}</p>
              <p className="text-muted-foreground">{request.email}</p>
              <p className="mt-1">
                {new Date(request.desired_date + 'T00:00:00').toLocaleDateString(bcp47, {
                  weekday: 'long', year: 'numeric', month: 'long', day: 'numeric',
                })}
                {request.desired_time_note && ` · ${request.desired_time_note}`}
              </p>
              <ul className="mt-1 space-y-0.5">
                {request.items.map(item => (
                  <li key={item.id} className="text-muted-foreground">
                    • {item.service_name} — {item.preferred_provider_name}
                  </li>
                ))}
              </ul>
              {request.special_note && (
                <p className="mt-1 italic text-muted-foreground">"{request.special_note}"</p>
              )}
            </div>

            {user && recommendServices.length > 0 && (
              <RecommendPanel
                tenantId={user.tenant_id}
                services={recommendServices}
                desiredDate={request.desired_date}
                earliestStart={earliestStart}
                onSelect={(rec) => { onClose(); onConvert(rec) }}
              />
            )}

            <div className="space-y-1.5">
              <Label>{t('requests.update_status')}</Label>
              <Select
                value={newStatus}
                onValueChange={v => v && setNewStatus(v as AppointmentRequest['status'])}
              >
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="reviewed">{t('requests.status_under_review')}</SelectItem>
                  <SelectItem value="declined">{t('requests.status_declined')}</SelectItem>
                </SelectContent>
              </Select>
            </div>

            <div className="space-y-1.5">
              <Label htmlFor="staff-notes">
                {t('requests.staff_notes')}
              </Label>
              <textarea
                id="staff-notes"
                className="w-full rounded-md border border-input bg-transparent px-3 py-2 text-sm shadow-xs placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring min-h-[80px] resize-none"
                placeholder={t('requests.notes_placeholder')}
                value={notes}
                onChange={e => setNotes(e.target.value)}
              />
            </div>

            {error && <p className="text-sm text-destructive">{error}</p>}
          </div>
        )}

        <DialogFooter className="flex-wrap gap-2">
          <Button variant="outline" onClick={onClose} disabled={saving}>{t('common.cancel')}</Button>
          <Button variant="outline" onClick={() => { onClose(); onConvert() }} disabled={saving}>
            {t('requests.action_convert')}
          </Button>
          <Button onClick={handleSave} disabled={saving}>
            {saving ? t('common.saving') : t('common.save')}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

// ── Main page ─────────────────────────────────────────────────────────────────

export default function RequestsPage() {
  const { t } = useTranslation()
  const { bcp47 } = useDateLocale()
  const navigate = useNavigate()
  const qc = useQueryClient()
  const [filter, setFilter] = useState('')
  const [reviewing, setReviewing] = useState<AppointmentRequest | null>(null)

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

  function openConvert(req: AppointmentRequest, rec?: Recommendation) {
    const date = req.desired_date.slice(0, 10)
    navigate(`/appointments?request=${req.id}&date=${date}`, { state: rec ? { recommendation: rec } : undefined })
  }

  const { data: requests = [], isLoading } = useQuery({
    queryKey: ['all-requests', filter],
    queryFn: () => listAllRequests(filter || undefined),
  })

  const { mutateAsync: doReview } = useMutation({
    mutationFn: ({ id, status, notes }: { id: string; status: AppointmentRequest['status']; notes: string }) =>
      reviewRequest(id, { status, staff_notes: notes || undefined }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['all-requests'] })
      qc.invalidateQueries({ queryKey: ['requests', 'new'] })
    },
  })

  async function handleSave(id: string, status: AppointmentRequest['status'], notes: string) {
    await doReview({ id, status, notes })
  }

  return (
    <div className="h-full overflow-auto bg-muted/30">
      <main className="max-w-3xl mx-auto px-4 py-6 space-y-4">
        <h1 className="text-xl font-semibold">{t('requests.page_title')}</h1>
        <div className="flex items-center gap-2">
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
              <Card key={req.id}>
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
                    {' · '}submitted {new Date(req.submitted_at).toLocaleDateString(bcp47, { month: 'short', day: 'numeric' })}
                  </CardDescription>
                </CardHeader>
                <CardContent className="pt-0">
                  <ul className="text-sm space-y-0.5 mb-3">
                    {req.items.map(item => (
                      <li key={item.id} className="text-muted-foreground">
                        • {item.service_name} — {item.preferred_provider_name}
                      </li>
                    ))}
                  </ul>
                  <div className="flex gap-2">
                    {(req.status === 'new' || req.status === 'reviewed') && (
                      <>
                        <Button
                          size="sm"
                          onClick={() => openConvert(req)}
                        >
                          {t('requests.action_convert')}
                        </Button>
                        <Button
                          size="sm"
                          variant="outline"
                          onClick={() => setReviewing(req)}
                        >
                          {t('requests.action_review')}
                        </Button>
                      </>
                    )}
                  </div>
                </CardContent>
              </Card>
            ))}
          </div>
        )}
      </main>

      <ReviewDialog
        request={reviewing}
        onClose={() => setReviewing(null)}
        onSave={handleSave}
        onConvert={(rec) => { if (reviewing) openConvert(reviewing, rec); setReviewing(null) }}
      />
    </div>
  )
}
