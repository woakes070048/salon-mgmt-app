import { api } from './client'

export interface Acknowledgement {
  id: string
  title: string
  body_text: string
  link_url: string | null
  link_text: string | null
  is_required: boolean
  display_order: number
  is_active: boolean
}

export interface PublicAcknowledgement {
  id: string
  title: string
  body_text: string
  link_url: string | null
  link_text: string | null
  is_required: boolean
}

export interface AcknowledgementCreate {
  title: string
  body_text: string
  link_url?: string | null
  link_text?: string | null
  is_required?: boolean
  display_order?: number
  is_active?: boolean
}

export type AcknowledgementPatch = Partial<AcknowledgementCreate>

// Public — used by the booking form (no auth required)
export function getPublicAcknowledgements(): Promise<PublicAcknowledgement[]> {
  return api.get<PublicAcknowledgement[]>('/public/acknowledgements')
}

// Admin — settings UI
export function listAcknowledgements(): Promise<Acknowledgement[]> {
  return api.get<Acknowledgement[]>('/settings/acknowledgements')
}

export function createAcknowledgement(body: AcknowledgementCreate): Promise<Acknowledgement> {
  return api.post<Acknowledgement>('/settings/acknowledgements', body)
}

export function updateAcknowledgement(id: string, body: AcknowledgementPatch): Promise<Acknowledgement> {
  return api.patch<Acknowledgement>(`/settings/acknowledgements/${id}`, body)
}

export function deleteAcknowledgement(id: string): Promise<void> {
  return api.delete<void>(`/settings/acknowledgements/${id}`)
}
