import { api } from './client'

export type PricingType = 'fixed' | 'hourly'

export interface Service {
  id: string
  service_code: string
  name: string
  category_name: string
  duration_minutes: number
  default_price: number | null
  pricing_type: string
}

export interface ServiceTranslationEntry {
  name?: string | null
  description?: string | null
  suggestions?: string | null
}

export interface ServiceDetail {
  id: string
  category_id: string
  category_name: string
  service_code: string
  name: string
  description: string | null
  pricing_type: PricingType
  default_price: string | null
  default_cost: string | null
  is_cost_percent: boolean
  duration_minutes: number
  processing_offset_minutes: number
  processing_duration_minutes: number
  requires_prior_consultation: boolean
  suggestions: string | null
  is_active: boolean
  display_order: number
  translations?: Record<string, ServiceTranslationEntry>
}

export interface ServiceIn {
  category_id: string
  service_code?: string | null
  name: string
  description?: string | null
  pricing_type?: PricingType
  default_price?: number | null
  default_cost?: number | null
  is_cost_percent?: boolean
  duration_minutes?: number
  processing_offset_minutes?: number
  processing_duration_minutes?: number
  requires_prior_consultation?: boolean
  suggestions?: string | null
  is_active?: boolean
  display_order?: number
  translations?: Record<string, ServiceTranslationEntry>
}

export type ServicePatch = Partial<ServiceIn>

export function listServices(): Promise<Service[]> {
  return api.get<Service[]>('/services')
}

export function listServicesFull(): Promise<ServiceDetail[]> {
  return api.get<ServiceDetail[]>('/services/all')
}

export function getService(id: string): Promise<ServiceDetail> {
  return api.get<ServiceDetail>(`/services/${id}`)
}

export function createService(body: ServiceIn): Promise<ServiceDetail> {
  return api.post<ServiceDetail>('/services', body)
}

export function updateService(id: string, body: ServicePatch): Promise<ServiceDetail> {
  return api.patch<ServiceDetail>(`/services/${id}`, body)
}

export function deactivateService(id: string): Promise<void> {
  return api.delete<void>(`/services/${id}`)
}

export interface ServiceFeeHistoryRow {
  effective_from: string
  product_fee: string | null
  is_cost_percent: boolean
  changed_by_user_id: string | null
}

export function getServiceFeeHistory(id: string): Promise<ServiceFeeHistoryRow[]> {
  return api.get<ServiceFeeHistoryRow[]>(`/services/${id}/fee-history`)
}
