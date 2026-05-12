import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { toast } from 'sonner'
import {
  type AppointmentRequest,
  type StoredRec,
  getRequestRecommendations,
  draftReply,
  sendReply,
  reviewRequest,
} from '@/api/appointmentRequests'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'

function formatTime12h(minutes: number): string {
  const h = Math.floor(minutes / 60)
  const m = minutes % 60
  const period = h < 12 ? 'am' : 'pm'
  const h12 = h % 12 || 12
  return m === 0 ? `${h12}${period}` : `${h12}:${String(m).padStart(2, '0')}${period}`
}

function parseConfidence(specialNote: string | null): number | null {
  if (!specialNote) return null
  const match = specialNote.match(/confidence:\s*(\d+)%/)
  return match ? parseInt(match[1], 10) : null
}

const SOURCE_LABEL: Record<AppointmentRequest['source'], string> = {
  email: 'Email',
  online_form: 'Online form',
  phone: 'Phone',
  walk_in: 'Walk-in',
  staff_entered: 'Staff entered',
}

interface Props {
  request: AppointmentRequest
  onClose: () => void
  onRefresh: () => void
}

export default function InboxDetailPanel({ request, onClose, onRefresh }: Props) {
  const navigate = useNavigate()
  const qc = useQueryClient()

  const [selectedRecIdx, setSelectedRecIdx] = useState<number | null>(null)
  const [draft, setDraft] = useState<{ subject: string; body: string } | null>(null)
  const [editSubject, setEditSubject] = useState('')
  const [editBody, setEditBody] = useState('')
  const [staffNotes, setStaffNotes] = useState(request.staff_notes ?? '')
  const [error, setError] = useState<string | null>(null)

  const isEmail = request.source === 'email'
  const confidence = parseConfidence(request.special_note)

  const { data: recsData, isLoading: recsLoading } = useQuery({
    queryKey: ['request-recommendations', request.id],
    queryFn: () => getRequestRecommendations(request.id),
    enabled: isEmail,
  })

  const recs: StoredRec[] = recsData?.recommendations ?? []

  const { mutateAsync: doDraft, isPending: drafting } = useMutation({
    mutationFn: () => draftReply(request.id, selectedRecIdx!),
    onSuccess: (data) => {
      setDraft(data)
      setEditSubject(data.subject)
      setEditBody(data.body)
      setError(null)
    },
    onError: (err) => setError(err instanceof Error ? err.message : 'Failed to draft reply'),
  })

  const { mutateAsync: doSend, isPending: sending } = useMutation({
    mutationFn: () =>
      sendReply(request.id, {
        subject: editSubject,
        body: editBody,
        chosen_recommendation_index: selectedRecIdx ?? undefined,
      }),
    onSuccess: () => {
      toast.success('Reply sent')
      setDraft(null)
      onRefresh()
    },
    onError: (err) => setError(err instanceof Error ? err.message : 'Failed to send reply'),
  })

  const { mutateAsync: doDecline, isPending: declining } = useMutation({
    mutationFn: () =>
      reviewRequest(request.id, {
        status: 'declined',
        staff_notes: staffNotes || undefined,
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['all-requests'] })
      qc.invalidateQueries({ queryKey: ['requests', 'new'] })
      onClose()
    },
    onError: (err) => setError(err instanceof Error ? err.message : 'Failed to decline'),
  })

  const { mutateAsync: doSaveNotes, isPending: savingNotes } = useMutation({
    mutationFn: () =>
      reviewRequest(request.id, {
        status: request.status,
        staff_notes: staffNotes || undefined,
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['all-requests'] })
      toast.success('Notes saved')
    },
    onError: (err) => setError(err instanceof Error ? err.message : 'Failed to save notes'),
  })

  function openConvert() {
    const date = request.desired_date.slice(0, 10)
    navigate(`/appointments?request=${request.id}&date=${date}`)
    onClose()
  }

  function selectRec(idx: number) {
    setSelectedRecIdx(idx)
    setDraft(null)
    setError(null)
  }

  const notesChanged = staffNotes !== (request.staff_notes ?? '')
  const canAct = request.status !== 'converted'

  return (
    <>
      {/* Backdrop */}
      <div
        className="fixed inset-0 z-30 bg-black/20"
        onClick={onClose}
      />

      {/* Panel */}
      <div className="fixed inset-y-0 right-0 z-40 w-[500px] bg-white shadow-2xl flex flex-col border-l">
        {/* Header */}
        <div className="flex items-start justify-between px-5 py-4 border-b flex-shrink-0">
          <div className="min-w-0 flex-1 space-y-1">
            <div className="flex items-center gap-2 flex-wrap">
              <h2 className="text-base font-semibold">
                {request.first_name} {request.last_name}
              </h2>
              <Badge variant={isEmail ? 'secondary' : 'outline'} className="text-xs">
                {SOURCE_LABEL[request.source]}
              </Badge>
              {confidence !== null && (
                <span
                  className={`text-xs px-1.5 py-0.5 rounded font-medium ${
                    confidence >= 80
                      ? 'bg-green-100 text-green-800'
                      : confidence >= 50
                        ? 'bg-amber-100 text-amber-800'
                        : 'bg-red-100 text-red-800'
                  }`}
                >
                  {confidence}% confidence
                </span>
              )}
            </div>
            <p className="text-xs text-muted-foreground">
              {new Date(request.desired_date + 'T00:00:00').toLocaleDateString('en-CA', {
                weekday: 'short',
                month: 'short',
                day: 'numeric',
                year: 'numeric',
              })}
              {request.desired_time_note && ` · ${request.desired_time_note}`}
              {' · '}
              {request.email}
            </p>
          </div>
          <button
            onClick={onClose}
            className="text-muted-foreground hover:text-foreground text-xl leading-none ml-3 flex-shrink-0"
          >
            ×
          </button>
        </div>

        {/* Body */}
        <div className="flex-1 overflow-y-auto p-5 space-y-5">
          {/* Requested services */}
          <div>
            <p className="text-xs font-medium text-muted-foreground uppercase tracking-wide mb-1.5">
              Requested
            </p>
            <ul className="space-y-0.5">
              {request.items.map((item) => (
                <li key={item.id} className="text-sm">
                  <span className="font-medium">{item.service_name}</span>
                  {item.preferred_provider_name && (
                    <span className="text-muted-foreground"> · {item.preferred_provider_name}</span>
                  )}
                </li>
              ))}
            </ul>
            {request.special_note && (() => {
              const note = request.special_note.replace(/\[Parsed from email.*?\]/g, '').trim()
              return note ? (
                <p className="mt-1.5 text-sm italic text-muted-foreground">"{note}"</p>
              ) : null
            })()}
          </div>

          {/* Original email */}
          {isEmail && request.inbound_raw_body && (
            <div>
              <p className="text-xs font-medium text-muted-foreground uppercase tracking-wide mb-1.5">
                Original email
              </p>
              <div className="rounded-md bg-muted/40 border px-3 py-3 text-xs text-muted-foreground whitespace-pre-wrap font-mono leading-relaxed max-h-48 overflow-y-auto">
                {request.inbound_raw_body}
              </div>
            </div>
          )}

          {/* Stored recommendations */}
          {isEmail && (
            <div>
              <p className="text-xs font-medium text-muted-foreground uppercase tracking-wide mb-1.5">
                Suggested slots
              </p>

              {recsLoading ? (
                <p className="text-sm text-muted-foreground">Loading…</p>
              ) : recs.length === 0 ? (
                <p className="text-sm text-muted-foreground">
                  No slots were suggested at intake. Use Convert to schedule manually.
                </p>
              ) : (
                <div className="space-y-2">
                  {recs.map((rec, idx) => (
                    <div
                      key={idx}
                      onClick={() => selectRec(idx)}
                      className={[
                        'rounded-lg border p-3 cursor-pointer transition-colors',
                        selectedRecIdx === idx
                          ? 'border-primary bg-primary/5'
                          : 'border-border hover:border-primary/40 hover:bg-muted/30',
                      ].join(' ')}
                    >
                      <ul className="space-y-0.5">
                        {rec.items.map((item, iIdx) => (
                          <li key={iIdx} className="text-sm">
                            <span className="font-medium">{item.provider_name}</span>
                            <span className="text-muted-foreground"> · {item.service_name}</span>
                            <span className="text-muted-foreground">
                              {' '}
                              {formatTime12h(item.start_minutes)}–{formatTime12h(item.end_minutes)}
                            </span>
                          </li>
                        ))}
                      </ul>
                      <div className="mt-1 flex items-center gap-2 flex-wrap">
                        <span className="text-xs text-muted-foreground">{rec.rationale}</span>
                        {rec.requires_consent && (
                          <span className="text-[10px] px-1.5 py-0.5 rounded bg-amber-100 text-amber-800 border border-amber-200">
                            Requires approval
                          </span>
                        )}
                      </div>
                    </div>
                  ))}
                </div>
              )}

              {/* Draft reply trigger */}
              {recs.length > 0 && selectedRecIdx !== null && !draft && (
                <div className="mt-3">
                  <Button
                    size="sm"
                    variant="outline"
                    onClick={() => doDraft()}
                    disabled={drafting}
                  >
                    {drafting ? 'Drafting…' : 'Draft reply'}
                  </Button>
                </div>
              )}

              {/* Editable draft */}
              {draft && (
                <div className="mt-3 space-y-3">
                  <p className="text-xs font-medium text-muted-foreground uppercase tracking-wide">
                    Draft reply
                  </p>
                  <div className="space-y-1">
                    <label className="text-xs text-muted-foreground">Subject</label>
                    <input
                      value={editSubject}
                      onChange={(e) => setEditSubject(e.target.value)}
                      className="w-full border border-input rounded-md px-3 py-1.5 text-sm bg-background"
                    />
                  </div>
                  <div className="space-y-1">
                    <label className="text-xs text-muted-foreground">Body</label>
                    <textarea
                      value={editBody}
                      onChange={(e) => setEditBody(e.target.value)}
                      rows={8}
                      className="w-full border border-input rounded-md px-3 py-2 text-sm bg-background resize-y"
                    />
                  </div>
                  <div className="flex gap-2">
                    <Button
                      size="sm"
                      onClick={() => doSend()}
                      disabled={sending || !editSubject.trim() || !editBody.trim()}
                    >
                      {sending ? 'Sending…' : 'Send reply'}
                    </Button>
                    <Button size="sm" variant="outline" onClick={() => setDraft(null)}>
                      Discard
                    </Button>
                  </div>
                </div>
              )}
            </div>
          )}

          {/* Staff notes */}
          <div className="space-y-1.5">
            <p className="text-xs font-medium text-muted-foreground uppercase tracking-wide">
              Staff notes
            </p>
            <textarea
              value={staffNotes}
              onChange={(e) => setStaffNotes(e.target.value)}
              rows={3}
              placeholder="Internal notes…"
              className="w-full border border-input rounded-md px-3 py-2 text-sm bg-background resize-none"
            />
            {notesChanged && (
              <Button
                size="sm"
                variant="outline"
                onClick={() => doSaveNotes()}
                disabled={savingNotes}
              >
                {savingNotes ? 'Saving…' : 'Save notes'}
              </Button>
            )}
          </div>

          {error && <p className="text-sm text-destructive">{error}</p>}
        </div>

        {/* Footer */}
        <div className="border-t px-5 py-4 flex gap-2 flex-shrink-0">
          {canAct && request.status !== 'declined' && (
            <Button variant="outline" onClick={() => doDecline()} disabled={declining}>
              {declining ? 'Declining…' : 'Decline'}
            </Button>
          )}
          <Button onClick={openConvert} className="flex-1" disabled={request.status === 'converted'}>
            {request.status === 'converted' ? 'Already converted' : 'Convert to appointment'}
          </Button>
        </div>
      </div>
    </>
  )
}
