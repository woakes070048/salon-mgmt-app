import { api } from './client'

export interface AdminUser {
  id: string
  email: string
  role: 'super_admin' | 'tenant_admin' | 'staff' | 'guest'
  is_active: boolean
  client_name: string | null
  first_name: string | null
  last_name: string | null
  language_preference: string
}

export function listUsers(): Promise<AdminUser[]> {
  return api.get<AdminUser[]>('/admin/users')
}

export function createUser(data: {
  email: string
  role: string
  send_welcome: boolean
  first_name?: string | null
  last_name?: string | null
}): Promise<AdminUser> {
  return api.post<AdminUser>('/admin/users', data)
}

export function updateUser(
  id: string,
  data: { role?: string; is_active?: boolean; first_name?: string | null; last_name?: string | null; language_preference?: string },
): Promise<AdminUser> {
  return api.patch<AdminUser>(`/admin/users/${id}`, data)
}

export function deleteUser(id: string): Promise<void> {
  return api.delete<void>(`/admin/users/${id}`)
}

export function sendWelcomeEmail(id: string): Promise<void> {
  return api.post<void>(`/admin/users/${id}/send-welcome`, {})
}

export function sendResetLink(id: string): Promise<void> {
  return api.post<void>(`/admin/users/${id}/send-reset`, {})
}

// ── Email config ──────────────────────────────────────────────────────────────

export interface EmailConfig {
  is_configured: boolean
  send_mode: 'smtp' | 'resend_api'
  resend_api_key_set: boolean
  smtp_host: string
  smtp_port: number
  smtp_username: string
  smtp_password_set: boolean
  smtp_use_tls: boolean
  from_address: string
  accounting_from_address: string | null
}

export interface PayrollConfig {
  provider_name: string | null
  provider_email: string | null
  client_id: string | null
  signature: string | null
  footer: string | null
}

export function getEmailConfig(): Promise<EmailConfig> {
  return api.get<EmailConfig>('/admin/email-config')
}

export function saveEmailConfig(data: {
  send_mode: 'smtp' | 'resend_api'
  resend_api_key?: string
  smtp_host?: string
  smtp_port?: number
  smtp_username?: string
  smtp_password?: string
  smtp_use_tls?: boolean
  from_address: string
  accounting_from_address?: string | null
}): Promise<EmailConfig> {
  return api.put<EmailConfig>('/admin/email-config', data)
}

export function getPayrollConfig(): Promise<PayrollConfig> {
  return api.get<PayrollConfig>('/admin/payroll-config')
}

export function savePayrollConfig(data: PayrollConfig): Promise<PayrollConfig> {
  return api.put<PayrollConfig>('/admin/payroll-config', data)
}

export function testEmailConfig(to: string): Promise<void> {
  return api.post<void>('/admin/email-config/test', { to })
}

// ── Login log ────────────────────────────────────────────────────────────────

export interface LoginLogEntry {
  id: string
  email: string
  role: string
  logged_in_at: string
}

export function getLoginLogs(limit = 500): Promise<LoginLogEntry[]> {
  return api.get<LoginLogEntry[]>(`/admin/login-logs?limit=${limit}`)
}

// ── Zero-appointment client cleanup ──────────────────────────────────────────

export interface ZeroApptClientSample {
  id: string
  first_name: string
  last_name: string
  email: string | null
  cell_phone: string | null
}

export interface ZeroApptPreview {
  count: number
  sample: ZeroApptClientSample[]
}

export function previewZeroApptClients(): Promise<ZeroApptPreview> {
  return api.get<ZeroApptPreview>('/admin/cleanup/zero-appointment-clients')
}

export function deleteZeroApptClients(): Promise<{ deleted: number }> {
  return api.delete<{ deleted: number }>('/admin/cleanup/zero-appointment-clients')
}

// ── Historical payment summary ────────────────────────────────────────────────

export interface HistoricalPaymentRow {
  label: string
  amount: number
}

export interface HistoricalPaymentIn {
  year: number
  month: number
  rows: HistoricalPaymentRow[]
  source?: string
}

export interface HistoricalPaymentOut {
  year: number
  month: number
  label: string
  amount: number
  source: string
}

export function upsertHistoricalPayments(body: HistoricalPaymentIn): Promise<{ saved: number }> {
  return api.put<{ saved: number }>('/admin/historical-payments', body)
}

export function getHistoricalPayments(): Promise<HistoricalPaymentOut[]> {
  return api.get<HistoricalPaymentOut[]>('/admin/historical-payments')
}

// ── Legacy data import ────────────────────────────────────────────────────────

export interface ImportResult {
  clients?: { created: number; updated: number; skipped: number }
  receipts?: { created: number; updated: number; skipped_existing: number; skipped_no_client: number; skipped_walk_in: number; errors: number }
  past_unreceipted?: { created: number; skipped_existing: number; skipped_no_client: number; skipped_no_service: number }
  future_bookings?: { created: number; skipped_existing: number; skipped_no_client: number; skipped_no_service: number; skipped_no_provider: number; unmapped_service_codes: string[] }
  current_bookings?: { created: number; skipped_existing: number; skipped_no_client: number; skipped_no_service: number; skipped_no_provider: number; unmapped_service_codes: string[] }
  on_account?: { updated: number; skipped: number }
  error?: string
}

export async function importLegacyData(formData: FormData): Promise<ImportResult> {
  const BASE_URL = (import.meta as unknown as { env: Record<string, string> }).env.VITE_API_URL ?? 'http://localhost:8000'
  const token = localStorage.getItem('access_token')
  const res = await fetch(`${BASE_URL}/admin/import-legacy`, {
    method: 'POST',
    headers: token ? { Authorization: `Bearer ${token}` } : {},
    body: formData,
  })
  if (res.status === 401) throw new Error('Unauthorized')
  if (!res.ok) {
    const body = await res.json().catch(() => ({}))
    throw new Error((body as { detail?: string }).detail ?? `HTTP ${res.status}`)
  }
  return res.json()
}
