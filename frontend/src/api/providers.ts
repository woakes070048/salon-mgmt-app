import { api } from './client'

export interface Provider {
  id: string
  display_name: string
  provider_type: 'stylist' | 'colourist' | 'dualist'
  booking_order: number
  has_appointments: boolean
  makes_appointments: boolean
}

export interface ProviderDetail {
  id: string
  user_id: string | null

  first_name: string
  last_name: string
  display_name: string
  provider_code: string | null
  provider_type: 'stylist' | 'colourist' | 'dualist'
  job_title: string | null
  is_owner: boolean
  is_active: boolean

  sex: string | null
  address_line: string | null
  city: string | null
  province: string | null
  postal_code: string | null
  personal_email: string | null
  home_phone: string | null
  cell_phone: string | null
  other_phone: string | null
  birthday: string | null
  notes: string | null
  provider_photo_url: string | null

  hire_date: string | null
  first_day_worked: string | null
  certification: string | null
  sin_set: boolean

  pay_type: 'hourly' | 'salary' | 'commission' | null
  pay_amount: number | null
  hourly_minimum: number | null
  vacation_pct: number | null
  retail_commission_pct: number | null
  commission_tiers: CommissionTier[] | null

  bank_institution_no: string | null
  bank_transit_no: string | null
  bank_account_masked: string | null

  cpp_exempt: boolean | null
  ei_exempt: boolean | null
  ei_rate_type: 'normal' | 'reduced' | null
  province_of_taxation: string | null
  wcb_csst_exempt: boolean | null
  td1_federal_credit: number | null
  td1_provincial_credit: number | null

  can_be_cashier: boolean
  makes_appointments: boolean
  has_appointments: boolean
  booking_order: number
  online_booking_visibility: 'not_available' | 'available_to_my_clients' | 'available_to_all'
}

export interface CommissionTier {
  monthly_threshold: number
  rate_pct: number
}

export interface ProviderCreatePayload {
  first_name: string
  last_name: string
  display_name: string
  provider_type: string
  job_title?: string | null
  provider_code?: string | null
  is_owner?: boolean
  booking_order?: number
  has_appointments?: boolean
  makes_appointments?: boolean
  can_be_cashier?: boolean
  online_booking_visibility?: string
  sex?: string | null
  personal_email?: string | null
  cell_phone?: string | null
  home_phone?: string | null
  other_phone?: string | null
  address_line?: string | null
  city?: string | null
  province?: string | null
  postal_code?: string | null
  birthday?: string | null
  notes?: string | null
  hire_date?: string | null
  first_day_worked?: string | null
  certification?: string | null
  pay_type?: string | null
  pay_amount?: number | null
  hourly_minimum?: number | null
  vacation_pct?: number | null
  retail_commission_pct?: number | null
  commission_tiers?: CommissionTier[] | null
  bank_institution_no?: string | null
  bank_transit_no?: string | null
  bank_account_no?: string | null
  cpp_exempt?: boolean | null
  ei_exempt?: boolean | null
  ei_rate_type?: string | null
  province_of_taxation?: string | null
  wcb_csst_exempt?: boolean | null
  td1_federal_credit?: number | null
  td1_provincial_credit?: number | null
  user_id?: string | null
  sin?: string | null
  provider_photo_url?: string | null
  is_active?: boolean
}

export type ProviderUpdatePayload = Partial<ProviderCreatePayload>

export function listProviders(): Promise<Provider[]> {
  return api.get<Provider[]>('/providers')
}

export function listAllProviders(): Promise<ProviderDetail[]> {
  return api.get<ProviderDetail[]>('/providers/all')
}

export function getProvider(id: string): Promise<ProviderDetail> {
  return api.get<ProviderDetail>(`/providers/${id}`)
}

export function createProvider(payload: ProviderCreatePayload): Promise<ProviderDetail> {
  return api.post<ProviderDetail>('/providers', payload)
}

export function updateProvider(id: string, payload: ProviderUpdatePayload): Promise<ProviderDetail> {
  return api.patch<ProviderDetail>(`/providers/${id}`, payload)
}

export function deactivateProvider(id: string): Promise<void> {
  return api.delete(`/providers/${id}`)
}

export interface CommissionTierOut {
  monthly_threshold: number
  rate_pct: number
}

export interface PayrollOut {
  provider_id: string
  display_name: string
  year: number
  month: number
  pay_type: string | null
  scheduled_hours: number
  actual_hours: number
  hours_source: 'actual' | 'scheduled'
  payroll_hours: number
  styling_revenue: number
  styling_item_count: number
  colour_revenue: number
  colour_item_count: number
  other_service_revenue: number
  gross_service_revenue: number
  styling_product_fee: number
  colour_product_fee: number
  total_product_fees: number
  net_service_revenue: number
  commission_tier_applied: CommissionTierOut | null
  commission_on_services: number
  retail_revenue: number
  retail_commission: number
  total_commission_pay: number
  hourly_minimum: number | null
  hourly_floor_amount: number
  pay_basis: 'commission' | 'hourly' | 'salary' | 'n/a'
  gross_before_vacation: number
  vacation_pct: number
  vacation_pay: number
  gross_pay: number
}

export function getProviderPayroll(id: string, year: number, month: number): Promise<PayrollOut> {
  return api.get<PayrollOut>(`/providers/${id}/payroll?year=${year}&month=${month}`)
}

export interface ProviderPayrollLine {
  provider_id: string
  first_name: string
  last_name: string
  display_name: string
  is_owner: boolean
  booking_order: number
  pay_type: string | null
  pay_basis: 'commission' | 'hourly' | 'salary' | 'n/a'
  scheduled_hours: number
  actual_hours: number
  payroll_hours: number
  hours_source: 'actual' | 'scheduled' | 'override'
  hourly_minimum: number | null
  hourly_floor_amount: number
  service_commission: number
  retail_revenue: number
  retail_commission: number
  vacation_pct: number
  gross_before_vacation: number
  vacation_pay: number
  gross_pay: number
}

export interface PayrollReportOut {
  period_start: string
  period_end: string
  lines: ProviderPayrollLine[]
}

export function getPayrollReport(period_start: string, period_end: string): Promise<PayrollReportOut> {
  return api.get<PayrollReportOut>(`/providers/payroll-report?period_start=${period_start}&period_end=${period_end}`)
}

export function savePayrollHours(payload: {
  period_start: string
  period_end: string
  overrides: {
    provider_id: string
    hours: number
    service_commission: number | null
    retail_commission: number | null
    vacation_pct: number | null
  }[]
}): Promise<void> {
  return api.post('/providers/payroll-hours', payload)
}

export function sendPayrollEmail(payload: {
  to_email: string
  subject: string
  body_text: string
}): Promise<void> {
  return api.post('/providers/payroll-report/send-email', payload)
}
