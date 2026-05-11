import { api } from './client'

export interface SaleItem {
  id: string
  kind: string
  description: string
  provider_id: string
  sequence: number
  quantity: number
  unit_price: string
  discount_amount: string
  line_total: string
  is_business_reimbursed: boolean
}

export interface SalePayment {
  id: string
  payment_method_id: string
  payment_method_code: string
  payment_method_label: string
  amount: string
  cashback_amount: string
}

export interface Sale {
  id: string
  appointment_ids: string[]
  client_id: string
  subtotal: string
  discount_total: string
  gst_amount: string
  pst_amount: string
  total: string
  status: 'pending' | 'completed'
  completed_at: string | null
  notes: string | null
  is_editable: boolean
  items: SaleItem[]
  payments: SalePayment[]
}

export interface SaleItemIn {
  appointment_item_id?: string | null
  retail_item_id?: string | null
  commission_provider_id?: string | null
  quantity?: number
  unit_price: string
  discount_amount: string
  promotion_id?: string | null
  is_business_reimbursed?: boolean
  is_gst_exempt?: boolean
  is_pst_exempt?: boolean
}

export function patchSaleItem(
  saleId: string,
  itemId: string,
  body: { discount_amount?: string; is_business_reimbursed?: boolean }
): Promise<Sale> {
  return api.patch<Sale>(`/sales/${saleId}/items/${itemId}`, body)
}

export interface SalePaymentIn {
  payment_method_id: string
  amount: string
  cashback_amount: string
}

export interface SaleIn {
  appointment_ids: string[]
  notes?: string | null
  items: SaleItemIn[]
  payments: SalePaymentIn[]
}

export function createSale(body: SaleIn): Promise<Sale> {
  return api.post<Sale>('/sales', body)
}

export function sendReceipt(saleId: string, to: string): Promise<void> {
  return api.post<void>(`/sales/${saleId}/send-receipt`, { to })
}

export function getSaleByAppointment(appointmentId: string): Promise<Sale> {
  return api.get<Sale>(`/sales/by-appointment/${appointmentId}`)
}

export function getSaleById(saleId: string): Promise<Sale> {
  return api.get<Sale>(`/sales/${saleId}`)
}

export interface SaleListItem {
  id: string
  client_id: string
  client_name: string
  completed_at: string | null
  total: string
  item_descriptions: string[]
  payment_labels: string[]
}

export function listSales(params: {
  date_from?: string
  date_to?: string
  client_search?: string
}): Promise<SaleListItem[]> {
  const q = new URLSearchParams()
  if (params.date_from) q.set('date_from', params.date_from)
  if (params.date_to) q.set('date_to', params.date_to)
  if (params.client_search) q.set('client_search', params.client_search)
  return api.get<SaleListItem[]>(`/sales?${q.toString()}`)
}

export function editSalePayments(
  saleId: string,
  payments: { payment_method_id: string; amount: string; cashback_amount: string }[],
): Promise<Sale> {
  return api.patch<Sale>(`/sales/${saleId}/payments`, { payments })
}
