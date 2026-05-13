import { api } from './client'

export interface Client {
  id: string
  first_name: string
  last_name: string
  pronouns: string | null
  cell_phone: string | null
  email: string | null
  special_instructions: string | null
  no_show_count: number
  late_cancellation_count: number
  is_vip: boolean
  language_preference: string
  preferred_provider_id: string | null
  preferred_provider_name: string | null
}

export function searchClients(q: string): Promise<Client[]> {
  return api.get<Client[]>(`/clients?q=${encodeURIComponent(q)}&limit=20`)
}

export function getClient(id: string): Promise<Client> {
  return api.get<Client>(`/clients/${id}`)
}

export function createClient(data: {
  first_name: string
  last_name: string
  cell_phone?: string
  email?: string
  language_preference?: string
}): Promise<Client> {
  return api.post<Client>('/clients', data)
}

export function updateClient(clientId: string, data: {
  first_name?: string
  last_name?: string
  email?: string | null
  cell_phone?: string | null
  language_preference?: string
  preferred_provider_id?: string | null
  clear_preferred_provider?: boolean
}): Promise<Client> {
  return api.patch<Client>(`/clients/${clientId}`, data)
}

export function updateClientNotes(clientId: string, notes: string | null): Promise<Client> {
  return api.patch<Client>(`/clients/${clientId}/notes`, { special_instructions: notes })
}

export interface VisitItem {
  service_name: string
  provider_name: string
  start_time: string
  price: number
}

export interface Visit {
  appointment_id: string
  date: string
  status: string
  items: VisitItem[]
}

export function getClientHistory(clientId: string): Promise<Visit[]> {
  return api.get<Visit[]>(`/clients/${clientId}/history`)
}

export interface ColourNote {
  id: string
  note_date: string   // YYYY-MM-DD
  note_text: string
  created_at: string
}

export function listColourNotes(clientId: string): Promise<ColourNote[]> {
  return api.get<ColourNote[]>(`/clients/${clientId}/colour-notes`)
}

export function createColourNote(clientId: string, note_date: string, note_text: string): Promise<ColourNote> {
  return api.post<ColourNote>(`/clients/${clientId}/colour-notes`, { note_date, note_text })
}

export function deleteClient(clientId: string): Promise<void> {
  return api.delete<void>(`/clients/${clientId}`)
}

export function checkDuplicateClients(email: string, phone: string): Promise<Client[]> {
  const params = new URLSearchParams()
  if (email) params.set('email', email)
  if (phone) params.set('phone', phone)
  return api.get<Client[]>(`/clients/check-duplicates?${params}`)
}
