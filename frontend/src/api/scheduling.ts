import { api } from './client'

export type StationType = 'styling' | 'colour' | 'multi_purpose' | 'processing'

export interface RequestedService {
  service_id: string
  preferred_provider_id?: string | null
}

export interface RecommendRequest {
  tenant_id: string
  client_id?: string | null
  appointment_request_id?: string | null
  services: RequestedService[]
  desired_date: string        // YYYY-MM-DD
  earliest_start?: string     // HH:MM
  latest_end?: string         // HH:MM
}

export interface RecommendationItem {
  service_id: string
  service_name: string
  provider_id: string
  provider_name: string
  start_time: string          // HH:MM
  end_time: string            // HH:MM
  duration_minutes: number
  station_type_required: StationType | null
}

export interface Recommendation {
  items: RecommendationItem[]
  total_duration_minutes: number
  score: number
  rationale: string
  requires_consent: boolean
}

export interface RecommendationResponse {
  recommendations: Recommendation[]
  has_more: boolean
}

export function getRecommendations(body: RecommendRequest): Promise<RecommendationResponse> {
  return api.post<RecommendationResponse>('/scheduling/recommend', body)
}

export interface TenantStation {
  id: string
  tenant_id: string
  station_type: StationType
  count: number
  created_at: string
  updated_at: string
}

export function listStations(): Promise<TenantStation[]> {
  return api.get<TenantStation[]>('/scheduling/stations')
}

export function createStation(body: { station_type: StationType; count: number }): Promise<TenantStation> {
  return api.post<TenantStation>('/scheduling/stations', body)
}

export function updateStation(id: string, body: { station_type: StationType; count: number }): Promise<TenantStation> {
  return api.put<TenantStation>(`/scheduling/stations/${id}`, body)
}
