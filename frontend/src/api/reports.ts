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

export interface TransactionLineItem {
  sale_id: string
  sale_date: string
  client_name: string
  provider_name: string | null
  kind: string
  description: string
  quantity: number
  unit_price: string
  discount: string
  line_total: string
  gst: string | null
  pst: string | null
  sale_total: string | null
}

export interface TransactionReport {
  period_start: string
  period_end: string
  items: TransactionLineItem[]
  grand_total: string
}

export function getTransactionReport(start: string, end: string): Promise<TransactionReport> {
  return api.get<TransactionReport>(`/reports/transactions?start=${start}&end=${end}`)
}

export interface PayrollServiceRow {
  date: string; client_name: string; service_name: string
  category: string | null; is_colour: boolean
  gross_amount: string; product_fee: string; net_amount: string
}
export interface PayrollRetailRow {
  date: string; client_name: string; description: string; amount: string
}
export interface PayrollDetailReport {
  provider_id: string; provider_name: string
  period_start: string; period_end: string
  pay_type: string | null; pay_basis: string
  service_rows: PayrollServiceRow[]
  styling_gross: string; styling_fees: string
  colour_gross: string; colour_fees: string
  net_service_revenue: string
  commission_rate_pct: string; commission_on_services: string
  retail_rows: PayrollRetailRow[]
  retail_gross: string; retail_commission_pct: string; retail_commission: string
  vacation_pct: string; gross_before_vacation: string
  vacation_pay: string; gross_pay: string
}
export function getPayrollDetail(
  providerId: string, start: string, end: string
): Promise<PayrollDetailReport> {
  return api.get<PayrollDetailReport>(
    `/reports/payroll-detail?provider_id=${providerId}&start=${start}&end=${end}`
  )
}

export interface ServicePerformanceServiceRow {
  service_name: string
  total_sales: string
  product_fee: string
  net_sales: string
  sales_count: number
  average_price: string
  pct_of_sales: string
  pct_of_count: string
}
export interface ServicePerformanceReport {
  provider_id: string; provider_name: string
  period_start: string; period_end: string
  service_rows: ServicePerformanceServiceRow[]
  total_service_sales: string
  total_service_fees: string
  total_net_service_sales: string
  total_service_count: number; average_service_price: string
  total_retail_sales: string; total_retail_count: number; average_retail_price: string
  total_sales: string
  pct_service_of_total: string; pct_retail_of_total: string; pct_retail_of_service: string
  receipt_count: number; clients_serviced: number
  avg_per_receipt: string; items_per_receipt: string
}
export function getServicePerformance(
  providerId: string, start: string, end: string
): Promise<ServicePerformanceReport> {
  return api.get<ServicePerformanceReport>(
    `/reports/service-performance?provider_id=${providerId}&start=${start}&end=${end}`
  )
}
