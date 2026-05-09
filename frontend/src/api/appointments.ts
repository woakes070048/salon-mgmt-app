import { api } from './client'

export interface ServiceSummary {
  id: string
  service_code: string
  name: string
  duration_minutes: number
  processing_offset_minutes: number
  processing_duration_minutes: number
}

export interface ProviderSummary {
  id: string
  display_name: string
  provider_type: 'stylist' | 'colourist' | 'dualist'
  makes_appointments: boolean
}

export interface ClientSummary {
  id: string
  first_name: string
  last_name: string
  cell_phone: string | null
  email: string | null
  special_instructions: string | null
}

export interface AppointmentItem {
  id: string
  service: ServiceSummary
  provider: ProviderSummary
  second_provider: ProviderSummary | null
  sequence: number
  start_time: string
  duration_minutes: number
  duration_override_minutes: number | null
  price: number
  status: 'pending' | 'in_progress' | 'completed' | 'cancelled'
  notes: string | null
}

export type ConfirmationStatus = 'not_sent' | 'draft' | 'sent' | 'skipped'

export interface Appointment {
  id: string
  appointment_date: string
  status: 'confirmed' | 'in_progress' | 'completed' | 'cancelled' | 'no_show'
  source: string
  notes: string | null
  client: ClientSummary
  items: AppointmentItem[]
  confirmation_status: ConfirmationStatus
  confirmation_sent_at: string | null
}

export interface Confirmation {
  status: ConfirmationStatus
  subject: string
  body: string
  sent_at: string | null
  is_default: boolean
}

export function getConfirmation(appointmentId: string): Promise<Confirmation> {
  return api.get<Confirmation>(`/appointments/${appointmentId}/confirmation`)
}

export function saveConfirmationDraft(
  appointmentId: string,
  subject: string,
  body: string,
): Promise<Confirmation> {
  return api.put<Confirmation>(`/appointments/${appointmentId}/confirmation`, { subject, body })
}

export function sendConfirmation(
  appointmentId: string,
  override?: { subject: string; body: string },
): Promise<Confirmation> {
  return api.post<Confirmation>(`/appointments/${appointmentId}/confirmation/send`, override ?? {})
}

export function skipConfirmation(appointmentId: string): Promise<Confirmation> {
  return api.post<Confirmation>(`/appointments/${appointmentId}/confirmation/skip`, {})
}

export function listAppointments(date: string): Promise<Appointment[]> {
  return api.get<Appointment[]>(`/appointments?date=${date}`)
}

export function getAppointment(id: string): Promise<Appointment> {
  return api.get<Appointment>(`/appointments/${id}`)
}

export function updateAppointmentStatus(
  id: string,
  status: Appointment['status'],
): Promise<Appointment> {
  return api.patch<Appointment>(`/appointments/${id}/status`, { status })
}

export function patchAppointmentItem(
  appointmentId: string,
  itemId: string,
  patch: { start_time?: string; provider_id?: string; duration_override_minutes?: number },
): Promise<Appointment> {
  return api.patch<Appointment>(`/appointments/${appointmentId}/items/${itemId}`, patch)
}

export function addAppointmentItem(
  appointmentId: string,
  item: {
    service_id: string
    provider_id: string
    start_time: string
    duration_minutes: number
    price: number
    sequence: number
    notes?: string
  },
): Promise<Appointment> {
  return api.post<Appointment>(`/appointments/${appointmentId}/items`, item)
}

export function removeAppointmentItem(
  appointmentId: string,
  itemId: string,
): Promise<Appointment> {
  return api.delete<Appointment>(`/appointments/${appointmentId}/items/${itemId}`)
}
