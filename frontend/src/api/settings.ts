import { api } from './client'

export const SLOT_OPTIONS = [5, 10, 15, 20, 30] as const
export type SlotMinutes = typeof SLOT_OPTIONS[number]

export type TimeFormat = '12h' | '24h'

export interface ContactDetails {
  address_line1: string | null
  address_line2: string | null
  city: string | null
  region: string | null
  postal_code: string | null
  country: string | null
  phone: string | null
  hours_summary: string | null
  website: string | null
}

export interface BrandingSettings extends ContactDetails {
  salon_name: string
  logo_url: string | null
  brand_color: string | null
  slot_minutes: SlotMinutes
  time_format: TimeFormat
  default_language: string
  supported_languages: string[]
}

export function getBranding(): Promise<BrandingSettings> {
  return api.get<BrandingSettings>('/settings/branding')
}

type BrandingPatchable = Partial<Pick<BrandingSettings,
  'salon_name' | 'logo_url' | 'brand_color' | 'slot_minutes' | 'time_format'
> & ContactDetails>

export function updateBranding(patch: BrandingPatchable): Promise<BrandingSettings> {
  return api.patch<BrandingSettings>('/settings/branding', patch)
}

export interface PublicTenantInfo extends ContactDetails {
  name: string
  logo_url: string | null
  brand_color: string | null
}

export function getPublicTenantInfo(): Promise<PublicTenantInfo> {
  return api.get<PublicTenantInfo>('/public/tenant-info')
}

export interface OperatingHoursDay {
  day_of_week: number  // 0=Mon … 6=Sun
  is_open: boolean
  open_time: string | null  // "HH:MM"
  close_time: string | null
}

export function getOperatingHours(): Promise<OperatingHoursDay[]> {
  return api.get<OperatingHoursDay[]>('/settings/operating-hours')
}

export function updateOperatingHours(days: OperatingHoursDay[]): Promise<OperatingHoursDay[]> {
  return api.put<OperatingHoursDay[]>('/settings/operating-hours', { days })
}

export interface RequestNotifications {
  enabled: boolean
  recipients: string[]
  reminder_enabled: boolean
  reminder_lead_hours: number
  reminder_send_time: string
}

export function getRequestNotifications(): Promise<RequestNotifications> {
  return api.get<RequestNotifications>('/settings/notifications')
}

export function updateRequestNotifications(
  patch: { enabled?: boolean; recipients?: string[]; reminder_enabled?: boolean; reminder_lead_hours?: number; reminder_send_time?: string },
): Promise<RequestNotifications> {
  return api.patch<RequestNotifications>('/settings/notifications', patch)
}

export interface PrinterConfig {
  printer_name: string
  printer_host: string | null
  printer_port: number
  paper_width: number
  auto_print_on_cash: boolean
  cash_drawer_enabled: boolean
  receipt_logo_url: string | null
}

export function getPrinterConfig(): Promise<PrinterConfig> {
  return api.get<PrinterConfig>('/settings/printer')
}

export function updatePrinterConfig(patch: Partial<Omit<PrinterConfig, 'receipt_logo_url'>>): Promise<PrinterConfig> {
  return api.patch<PrinterConfig>('/settings/printer', patch)
}

export function uploadPrinterLogo(file: File): Promise<PrinterConfig> {
  const fd = new FormData()
  fd.append('file', file)
  return api.postForm<PrinterConfig>('/settings/printer/logo', fd)
}
