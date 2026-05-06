import { api } from './client'

export interface RequestItem {
  id: string
  sequence: number
  service_name: string
  preferred_provider_name: string
  service_id: string | null
}

export interface AppointmentRequest {
  id: string
  status: 'new' | 'reviewed' | 'converted' | 'declined'
  desired_date: string
  desired_time_note: string | null
  special_note: string | null
  submitted_at: string
  staff_notes: string | null
  first_name: string
  last_name: string
  email: string
  phone: string | null
  client_id: string | null
  items: RequestItem[]
}

export interface RequestItemIn {
  service_name: string
  preferred_provider_name: string
  sequence: number
}

export interface AppointmentRequestIn {
  desired_date: string
  desired_time_note?: string
  special_note?: string
  items: RequestItemIn[]
}

export function createRequest(body: AppointmentRequestIn): Promise<AppointmentRequest> {
  return api.post<AppointmentRequest>('/appointment-requests', body)
}

export function listMyRequests(): Promise<AppointmentRequest[]> {
  return api.get<AppointmentRequest[]>('/appointment-requests')
}

export function getRequest(id: string): Promise<AppointmentRequest> {
  return api.get<AppointmentRequest>(`/appointment-requests/${id}`)
}

export function listAllRequests(status?: string): Promise<AppointmentRequest[]> {
  const qs = status ? `?status=${status}` : ''
  return api.get<AppointmentRequest[]>(`/appointment-requests${qs}`)
}

export function reviewRequest(
  id: string,
  body: { status: AppointmentRequest['status']; staff_notes?: string },
): Promise<AppointmentRequest> {
  return api.patch<AppointmentRequest>(`/appointment-requests/${id}`, body)
}

export interface ConvertItemIn {
  request_item_id: string
  service_id: string
  provider_id: string
  second_provider_id?: string
  sequence: number
  start_time: string
  duration_minutes: number
  price: number
  notes?: string
}

export interface ConvertRequestIn {
  client_id?: string
  appointment_date: string
  notes?: string
  items: ConvertItemIn[]
}

export interface ConvertOut {
  appointment_id: string
  appointment_date: string
}

export function convertRequest(id: string, body: ConvertRequestIn): Promise<ConvertOut> {
  return api.post<ConvertOut>(`/appointment-requests/${id}/convert`, body)
}
