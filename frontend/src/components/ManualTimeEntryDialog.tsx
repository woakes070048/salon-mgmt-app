import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useTranslation } from 'react-i18next'
import { listProviders } from '@/api/providers'
import { adminCreateEntry } from '@/api/time_entries'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import {
  Dialog, DialogContent, DialogHeader, DialogTitle,
} from '@/components/ui/dialog'
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from '@/components/ui/select'

interface Props {
  open: boolean
  onClose: () => void
  defaultDate?: string   // YYYY-MM-DD
}

export default function ManualTimeEntryDialog({ open, onClose, defaultDate }: Props) {
  const { t } = useTranslation()
  const qc = useQueryClient()

  const today = new Date().toISOString().slice(0, 10)
  const [providerId, setProviderId] = useState('')
  const [date, setDate] = useState(defaultDate ?? today)
  const [checkIn, setCheckIn] = useState('')
  const [checkOut, setCheckOut] = useState('')
  const [notes, setNotes] = useState('')
  const [error, setError] = useState<string | null>(null)

  const { data: providers = [] } = useQuery({
    queryKey: ['providers'],
    queryFn: listProviders,
  })

  const mut = useMutation({
    mutationFn: () => {
      const checkInDt = `${date}T${checkIn}:00`
      const checkOutDt = checkOut ? `${date}T${checkOut}:00` : null
      return adminCreateEntry(providerId, checkInDt, checkOutDt, notes.trim() || null)
    },
    onSuccess: (entry) => {
      qc.invalidateQueries({ queryKey: ['time-entries', entry.date] })
      qc.invalidateQueries({ queryKey: ['time-entries', today] })
      handleClose()
    },
    onError: (err: Error) => {
      setError(err.message || 'Failed to save entry')
    },
  })

  function handleClose() {
    setProviderId('')
    setDate(defaultDate ?? today)
    setCheckIn('')
    setCheckOut('')
    setNotes('')
    setError(null)
    onClose()
  }

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    setError(null)
    if (!providerId) { setError('Select a staff member'); return }
    if (!checkIn) { setError('Enter a check-in time'); return }
    if (checkOut && checkOut <= checkIn) { setError('Check-out must be after check-in'); return }
    mut.mutate()
  }

  return (
    <Dialog open={open} onOpenChange={v => { if (!v) handleClose() }}>
      <DialogContent className="max-w-sm">
        <DialogHeader>
          <DialogTitle>{t('dashboard.add_time_entry')}</DialogTitle>
        </DialogHeader>

        <form onSubmit={handleSubmit} className="space-y-4 pt-1">
          <div className="space-y-1.5">
            <Label>{t('dashboard.staff_member')}</Label>
            <Select value={providerId} onValueChange={setProviderId}>
              <SelectTrigger>
                <SelectValue placeholder={t('dashboard.select_staff')} />
              </SelectTrigger>
              <SelectContent>
                {providers.map(p => (
                  <SelectItem key={p.id} value={p.id}>{p.display_name}</SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          <div className="space-y-1.5">
            <Label>{t('common.date')}</Label>
            <Input
              type="date"
              value={date}
              max={today}
              onChange={e => setDate(e.target.value)}
              required
            />
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1.5">
              <Label>{t('dashboard.check_in_time')}</Label>
              <Input
                type="time"
                value={checkIn}
                onChange={e => setCheckIn(e.target.value)}
                required
              />
            </div>
            <div className="space-y-1.5">
              <Label>{t('dashboard.check_out_time')} <span className="text-muted-foreground text-xs">({t('common.optional')})</span></Label>
              <Input
                type="time"
                value={checkOut}
                onChange={e => setCheckOut(e.target.value)}
              />
            </div>
          </div>

          <div className="space-y-1.5">
            <Label>{t('common.notes')} <span className="text-muted-foreground text-xs">({t('common.optional')})</span></Label>
            <Input
              value={notes}
              onChange={e => setNotes(e.target.value)}
              placeholder={t('dashboard.time_entry_notes_placeholder')}
            />
          </div>

          {error && <p className="text-sm text-destructive">{error}</p>}

          <div className="flex justify-end gap-2 pt-1">
            <Button type="button" variant="outline" onClick={handleClose}>
              {t('common.cancel')}
            </Button>
            <Button type="submit" disabled={mut.isPending}>
              {mut.isPending ? t('common.saving') : t('common.save')}
            </Button>
          </div>
        </form>
      </DialogContent>
    </Dialog>
  )
}
