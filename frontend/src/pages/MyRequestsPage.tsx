import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { PlusCircle, LogOut } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { useDateLocale } from '@/lib/dateLocale'
import { useAuth } from '@/store/auth'
import {
  type AppointmentRequest,
  type AppointmentRequestIn,
  createRequest,
  listMyRequests,
} from '@/api/appointmentRequests'
import { listServices, type Service } from '@/api/services'
import { listProviders, type Provider } from '@/api/providers'
import { getPublicAcknowledgements, type PublicAcknowledgement } from '@/api/acknowledgements'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'

const STATUS_VARIANT: Record<
  AppointmentRequest['status'],
  'default' | 'secondary' | 'outline' | 'destructive'
> = {
  new: 'secondary',
  reviewed: 'default',
  converted: 'default',
  declined: 'destructive',
}

// ── Request form ─────────────────────────────────────────────────────────────

interface ServiceItem {
  service_name: string
  preferred_provider_name: string
}

function AcknowledgementBlock({
  ack,
  checked,
  onChange,
}: {
  ack: PublicAcknowledgement
  checked: boolean
  onChange: (v: boolean) => void
}) {
  const { t } = useTranslation()
  // body_text supports a `{link}` placeholder. Split on it so we can render
  // a real anchor in place of the placeholder.
  const parts = ack.body_text.split(/\{link\}/i)
  const linkNode = ack.link_url ? (
    <a
      href={ack.link_url}
      target="_blank"
      rel="noopener noreferrer"
      className="text-primary underline"
    >
      {ack.link_text || ack.link_url}
    </a>
  ) : null

  return (
    <div className="rounded-md border p-4 space-y-3">
      <div className="flex items-start gap-2">
        <p className="text-sm font-semibold flex-1">{ack.title}</p>
        {ack.is_required && <span className="text-destructive text-sm">*</span>}
      </div>
      <p className="text-sm text-foreground leading-relaxed">
        {parts.map((part, i) => (
          <span key={i}>
            {part}
            {i < parts.length - 1 && linkNode}
          </span>
        ))}
      </p>
      <label className="flex items-center gap-2 cursor-pointer text-sm">
        <input
          type="radio"
          checked={checked}
          onChange={() => onChange(true)}
          onClick={e => {
            // Allow toggling off by clicking again
            if (checked) { onChange(false); (e.target as HTMLInputElement).checked = false }
          }}
        />
        <span>{t('requests.acknowledge_and_agree')}</span>
      </label>
    </div>
  )
}

function RequestForm({
  open,
  onClose,
  onSubmit,
}: {
  open: boolean
  onClose: () => void
  onSubmit: (data: AppointmentRequestIn) => Promise<void>
}) {
  const { t } = useTranslation()
  const { data: services = [] } = useQuery({ queryKey: ['services'], queryFn: listServices })
  const { data: providers = [] } = useQuery({ queryKey: ['providers'], queryFn: listProviders })
  const { data: acknowledgements = [] } = useQuery({
    queryKey: ['public-acknowledgements'],
    queryFn: getPublicAcknowledgements,
  })

  const [desiredDate, setDesiredDate] = useState('')
  const [timeNote, setTimeNote] = useState('')
  const [specialNote, setSpecialNote] = useState('')
  const [items, setItems] = useState<ServiceItem[]>([{ service_name: '', preferred_provider_name: '' }])
  const [agreed, setAgreed] = useState<Record<string, boolean>>({})
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)

  function reset() {
    setDesiredDate('')
    setTimeNote('')
    setSpecialNote('')
    setItems([{ service_name: '', preferred_provider_name: '' }])
    setAgreed({})
    setError(null)
  }

  function handleClose() {
    reset()
    onClose()
  }

  function addItem() {
    setItems(prev => [...prev, { service_name: '', preferred_provider_name: '' }])
  }

  function removeItem(idx: number) {
    setItems(prev => prev.filter((_, i) => i !== idx))
  }

  function updateItem(idx: number, field: keyof ServiceItem, value: string) {
    setItems(prev => prev.map((item, i) => (i === idx ? { ...item, [field]: value } : item)))
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    setError(null)

    if (!desiredDate) { setError('Please select a desired date'); return }
    if (items.some(i => !i.service_name)) { setError('Please select a service for each item'); return }

    const missingAcks = acknowledgements.filter(a => a.is_required && !agreed[a.id])
    if (missingAcks.length > 0) {
      setError(t('requests.acknowledgements_required'))
      return
    }

    setSubmitting(true)
    try {
      await onSubmit({
        desired_date: desiredDate,
        desired_time_note: timeNote || undefined,
        special_note: specialNote || undefined,
        items: items.map((item, idx) => ({ ...item, sequence: idx + 1 })),
        acknowledgements_agreed: Object.keys(agreed).length > 0 ? agreed : undefined,
      })
      reset()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Submission failed')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <Dialog open={open} onOpenChange={v => { if (!v) handleClose() }}>
      <DialogContent className="max-w-lg max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>{t('requests.request_form_title')}</DialogTitle>
          <DialogDescription>
            {t('requests.request_form_intro')}
          </DialogDescription>
        </DialogHeader>

        <form onSubmit={handleSubmit} className="space-y-5 py-2">
          <div className="space-y-1.5">
            <Label htmlFor="desired_date">{t('requests.preferred_date')}</Label>
            <Input
              id="desired_date"
              type="date"
              value={desiredDate}
              onChange={e => setDesiredDate(e.target.value)}
              min={new Date().toISOString().split('T')[0]}
              required
            />
          </div>

          <div className="space-y-1.5">
            <Label htmlFor="time_note">{t('requests.preferred_time')}</Label>
            <Input
              id="time_note"
              placeholder={t('requests.preferred_time_placeholder')}
              value={timeNote}
              onChange={e => setTimeNote(e.target.value)}
            />
          </div>

          <div className="space-y-2">
            <Label>{t('requests.services_requested')}</Label>
            {items.map((item, idx) => (
              <div key={idx} className="border rounded-md p-3 space-y-3">
                <div className="flex items-center justify-between">
                  <span className="text-sm font-medium text-muted-foreground">{t('requests.service_number', { number: idx + 1 })}</span>
                  {items.length > 1 && (
                    <button
                      type="button"
                      onClick={() => removeItem(idx)}
                      className="text-xs text-destructive hover:underline"
                    >
                      {t('common.remove')}
                    </button>
                  )}
                </div>

                <div className="space-y-1.5">
                  <Label htmlFor={`service-${idx}`}>{t('appt.service_label')}</Label>
                  <Select
                    value={item.service_name}
                    onValueChange={v => updateItem(idx, 'service_name', v ?? '')}
                  >
                    <SelectTrigger id={`service-${idx}`}>
                      <SelectValue placeholder={t('appt.select_service')} />
                    </SelectTrigger>
                    <SelectContent>
                      {services.map((s: Service) => (
                        <SelectItem key={s.id} value={s.name}>{s.name}</SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>

                <div className="space-y-1.5">
                  <Label htmlFor={`provider-${idx}`}>{t('requests.preferred_provider')}</Label>
                  <Select
                    value={item.preferred_provider_name}
                    onValueChange={v => updateItem(idx, 'preferred_provider_name', v ?? '')}
                  >
                    <SelectTrigger id={`provider-${idx}`}>
                      <SelectValue placeholder="Select preference…" />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="No preference">{t('requests.no_preference')}</SelectItem>
                      {providers.map((p: Provider) => (
                        <SelectItem key={p.id} value={p.display_name}>{p.display_name}</SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
              </div>
            ))}

            <Button type="button" variant="outline" size="sm" onClick={addItem} className="w-full">
              {t('requests.add_service')}
            </Button>
          </div>

          <div className="space-y-1.5">
            <Label htmlFor="special_note">{t('requests.special_notes')}</Label>
            <textarea
              id="special_note"
              className="w-full rounded-md border border-input bg-transparent px-3 py-2 text-sm shadow-xs placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring disabled:opacity-50 min-h-[80px] resize-none"
              placeholder={t('requests.special_notes_placeholder')}
              value={specialNote}
              onChange={e => setSpecialNote(e.target.value)}
            />
          </div>

          {/* Acknowledgements (tenant policies) */}
          {acknowledgements.map(ack => (
            <AcknowledgementBlock
              key={ack.id}
              ack={ack}
              checked={!!agreed[ack.id]}
              onChange={v => setAgreed(prev => ({ ...prev, [ack.id]: v }))}
            />
          ))}

          {error && <p className="text-sm text-destructive">{error}</p>}

          <DialogFooter>
            <Button type="button" variant="outline" onClick={handleClose} disabled={submitting}>
              {t('common.cancel')}
            </Button>
            <Button type="submit" disabled={submitting}>
              {submitting ? t('common.sending') : t('requests.submit_request')}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}

// ── Main page ─────────────────────────────────────────────────────────────────

export default function MyRequestsPage() {
  const { t } = useTranslation()
  const { bcp47 } = useDateLocale()
  const { user, logout } = useAuth()
  const qc = useQueryClient()
  const [formOpen, setFormOpen] = useState(false)

  const STATUS_LABELS: Record<AppointmentRequest['status'], string> = {
    new: 'Pending review',
    reviewed: t('requests.filter_under_review'),
    converted: t('requests.filter_confirmed'),
    declined: t('requests.filter_declined'),
  }

  const { data: requests = [], isLoading } = useQuery({
    queryKey: ['my-requests'],
    queryFn: listMyRequests,
  })

  const { mutateAsync: submitRequest } = useMutation({
    mutationFn: createRequest,
    onSuccess: () => qc.invalidateQueries({ queryKey: ['my-requests'] }),
  })

  async function handleSubmit(data: AppointmentRequestIn) {
    await submitRequest(data)
    setFormOpen(false)
  }

  return (
    <div className="min-h-screen bg-muted/30">
      <header className="border-b bg-background px-6 py-4 flex items-center justify-between">
        <img src="/salon-lyol-logo.png" className="h-32 w-auto" alt="Salon Lyol" />
        <div className="flex items-center gap-4">
          <div className="text-right">
            {user?.display_name && (
              <p className="text-sm font-medium">{user.display_name}</p>
            )}
            <p className="text-xs text-muted-foreground">{user?.email}</p>
          </div>
          <Button variant="ghost" size="sm" onClick={logout}>
            <LogOut className="h-4 w-4 mr-1.5" />
            {t('nav.sign_out')}
          </Button>
        </div>
      </header>

      <main className="max-w-2xl mx-auto px-4 py-8 space-y-6">
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-semibold">{t('requests.my_requests_title')}</h1>
            <p className="text-muted-foreground text-sm mt-1">
              {t('requests.my_requests_subtitle')}
            </p>
          </div>
          <Button onClick={() => setFormOpen(true)}>
            <PlusCircle className="h-4 w-4 mr-1.5" />
            {t('requests.new_request')}
          </Button>
        </div>

        {isLoading ? (
          <p className="text-muted-foreground text-sm">{t('common.loading')}</p>
        ) : requests.length === 0 ? (
          <Card>
            <CardContent className="py-12 text-center text-muted-foreground">
              <p className="mb-4">{t('requests.no_requests_yet')}</p>
              <Button onClick={() => setFormOpen(true)}>{t('requests.first_request_cta')}</Button>
            </CardContent>
          </Card>
        ) : (
          <div className="space-y-3">
            {requests.map(req => (
              <Card key={req.id}>
                <CardHeader className="pb-2">
                  <div className="flex items-start justify-between gap-2">
                    <CardTitle className="text-base">
                      {new Date(req.desired_date + 'T00:00:00').toLocaleDateString(bcp47, {
                        weekday: 'long',
                        year: 'numeric',
                        month: 'long',
                        day: 'numeric',
                      })}
                      {req.desired_time_note && (
                        <span className="font-normal text-muted-foreground ml-2 text-sm">
                          · {req.desired_time_note}
                        </span>
                      )}
                    </CardTitle>
                    <Badge variant={STATUS_VARIANT[req.status]}>
                      {STATUS_LABELS[req.status]}
                    </Badge>
                  </div>
                  <CardDescription className="text-xs">
                    Submitted {new Date(req.submitted_at).toLocaleDateString(bcp47, { month: 'short', day: 'numeric', year: 'numeric' })}
                  </CardDescription>
                </CardHeader>
                <CardContent className="pt-0 space-y-2">
                  <ul className="text-sm space-y-1">
                    {req.items.map(item => (
                      <li key={item.id} className="flex gap-1">
                        <span className="text-muted-foreground">•</span>
                        <span>{item.service_name}</span>
                        <span className="text-muted-foreground">with {item.preferred_provider_name}</span>
                      </li>
                    ))}
                  </ul>
                  {req.special_note && (
                    <p className="text-xs text-muted-foreground italic">"{req.special_note}"</p>
                  )}
                  {req.staff_notes && req.status === 'declined' && (
                    <p className="text-xs text-muted-foreground border-l-2 pl-2">
                      {req.staff_notes}
                    </p>
                  )}
                </CardContent>
              </Card>
            ))}
          </div>
        )}
      </main>

      <RequestForm
        open={formOpen}
        onClose={() => setFormOpen(false)}
        onSubmit={handleSubmit}
      />
    </div>
  )
}
