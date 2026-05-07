import { api } from './client'

export interface ProviderRow {
  provider_name: string
  total: string
  sale_count: number
}

export interface PaymentMethodRow {
  label: string
  gross: string
  cashback: string
  net: string
}

export interface DayRow {
  date: string
  sale_count: number
  total: string
}

export interface MonthlyReport {
  year: number
  month: number
  sale_count: number
  subtotal: string
  discount_total: string
  gst_amount: string
  pst_amount: string
  total: string
  service_gross: string
  service_discount: string
  service_total: string
  retail_gross: string
  retail_discount: string
  retail_total: string
  retail_returns: string
  gift_card_total: string
  on_account_sales: string
  on_account_payments: string
  petty_cash_total: string
  by_provider: ProviderRow[]
  by_payment_method: PaymentMethodRow[]
  by_day: DayRow[]
}

export function getMonthlyReport(year: number, month: number): Promise<MonthlyReport> {
  return api.get<MonthlyReport>(`/reports/monthly?year=${year}&month=${month}`)
}

export interface PettyCashEntryRow {
  date: string
  description: string
  amount: string
}

export interface PettyCashReport {
  year: number
  month: number
  entries: PettyCashEntryRow[]
  total: string
}

export function getPettyCashReport(year: number, month: number): Promise<PettyCashReport> {
  return api.get<PettyCashReport>(`/reports/petty-cash?year=${year}&month=${month}`)
}
