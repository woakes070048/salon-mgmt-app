import { api } from './client'

export interface TimeEntry {
  id: string
  provider_id: string
  provider_name: string
  date: string
  check_in_at: string
  check_out_at: string | null
  hours: number | null
  notes: string | null
}

export function listTimeEntries(date?: string): Promise<TimeEntry[]> {
  const q = date ? `?date=${date}` : ''
  return api.get(`/time-entries${q}`)
}

export function checkIn(provider_id: string): Promise<TimeEntry> {
  return api.post('/time-entries', { provider_id })
}

export function checkOut(entry_id: string): Promise<TimeEntry> {
  return api.post(`/time-entries/${entry_id}/check-out`, {})
}

export function adminCreateEntry(
  provider_id: string,
  check_in_at: string,
  check_out_at: string | null,
  notes: string | null,
): Promise<TimeEntry> {
  return api.post('/time-entries', { provider_id, check_in_at, check_out_at, notes })
}

export function deleteEntry(entry_id: string): Promise<void> {
  return api.delete(`/time-entries/${entry_id}`)
}
