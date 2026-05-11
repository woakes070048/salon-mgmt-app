import { useState, useRef } from 'react'
import { useTranslation } from 'react-i18next'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { getSaleByAppointment, editSalePayments, patchSaleItem, type SaleItem } from '@/api/sales'
import { listPaymentMethods } from '@/api/paymentMethods'
import { Button } from '@/components/ui/button'

interface Props {
  appointmentId: string
}

function ItemEditRow({ item, onSave, saving }: {
  item: SaleItem
  onSave: (body: { discount_amount?: string; is_business_reimbursed?: boolean }) => void
  saving: boolean
}) {
  const discountRef = useRef<HTMLInputElement>(null)
  const [br, setBr] = useState(item.is_business_reimbursed)
  return (
    <div className="mt-1 pl-2 border-l-2 border-muted space-y-1.5 pb-1">
      <div className="flex items-center gap-2">
        <span className="text-muted-foreground w-16 shrink-0">Discount $</span>
        <input ref={discountRef} type="number" step="0.01" min="0"
          defaultValue={parseFloat(item.discount_amount).toFixed(2)}
          className="border rounded px-1.5 py-0.5 text-xs w-20 bg-white" />
      </div>
      <label className="flex items-center gap-2 cursor-pointer">
        <input type="checkbox" checked={br} onChange={e => setBr(e.target.checked)}
          className="h-3 w-3 rounded accent-foreground" />
        <span className="text-muted-foreground">Business reimbursed</span>
      </label>
      <button
        disabled={saving}
        onClick={() => onSave({
          discount_amount: parseFloat(discountRef.current?.value || '0').toFixed(2),
          is_business_reimbursed: br,
        })}
        className="text-[10px] bg-foreground text-background px-2 py-0.5 rounded hover:opacity-90 disabled:opacity-50"
      >
        {saving ? 'Saving…' : 'Save'}
      </button>
    </div>
  )
}

function fmt(s: string): string {
  const n = parseFloat(s)
  return Number.isFinite(n) ? n.toFixed(2) : '0.00'
}

interface PaymentRow {
  payment_method_id: string
  amount: string
  cashback_amount: string
}

function EditPaymentsDialog({
  saleId,
  saleTotal,
  initialPayments,
  onDone,
}: {
  saleId: string
  saleTotal: string
  initialPayments: PaymentRow[]
  onDone: () => void
}) {
  const { t } = useTranslation()
  const qc = useQueryClient()
  const { data: methods = [] } = useQuery({
    queryKey: ['payment-methods', 'active'],
    queryFn: () => listPaymentMethods(true),
  })

  const [rows, setRows] = useState<PaymentRow[]>(initialPayments.map(p => ({ ...p })))
  const [error, setError] = useState<string | null>(null)

  const mutation = useMutation({
    mutationFn: () => editSalePayments(saleId, rows),
    onSuccess: (updated) => {
      updated.appointment_ids.forEach(id => qc.setQueryData(['sale', 'by-appointment', id], updated))
      onDone()
    },
    onError: (e: Error) => setError(e.message),
  })

  function updateRow(idx: number, patch: Partial<PaymentRow>) {
    setRows(rs => rs.map((r, i) => i === idx ? { ...r, ...patch } : r))
  }

  function addRow() {
    const firstMethod = methods[0]
    if (!firstMethod) return
    setRows(rs => [...rs, { payment_method_id: firstMethod.id, amount: '0.00', cashback_amount: '0.00' }])
  }

  function removeRow(idx: number) {
    setRows(rs => rs.filter((_, i) => i !== idx))
  }

  const total = parseFloat(saleTotal)
  const applied = rows.reduce((sum, r) => {
    const amt = parseFloat(r.amount) || 0
    const cb = parseFloat(r.cashback_amount) || 0
    return sum + (amt - cb)
  }, 0)
  const remaining = Math.round((total - applied) * 100) / 100
  const balanced = Math.abs(remaining) < 0.005

  return (
    <div className="mt-2 border rounded-md bg-white p-3 space-y-3">
      <p className="text-xs font-medium">{t('checkout.edit_payments_title')}</p>

      <div className="space-y-2">
        {rows.map((row, idx) => (
          <div key={idx} className="flex items-center gap-1.5">
            <select
              value={row.payment_method_id}
              onChange={e => updateRow(idx, { payment_method_id: e.target.value })}
              className="flex-1 border border-input rounded px-2 py-1 text-xs bg-background"
            >
              {methods.map(m => (
                <option key={m.id} value={m.id}>{m.label}</option>
              ))}
            </select>
            <input
              type="number"
              step="0.01"
              min="0"
              value={row.amount}
              onChange={e => updateRow(idx, { amount: e.target.value })}
              className="w-20 border border-input rounded px-2 py-1 text-xs text-right bg-background"
              placeholder="Amount"
            />
            {parseFloat(row.cashback_amount) > 0 && (
              <input
                type="number"
                step="0.01"
                min="0"
                value={row.cashback_amount}
                onChange={e => updateRow(idx, { cashback_amount: e.target.value })}
                className="w-20 border border-input rounded px-2 py-1 text-xs text-right bg-background"
                placeholder="Cashback"
              />
            )}
            {rows.length > 1 && (
              <button
                onClick={() => removeRow(idx)}
                className="text-muted-foreground hover:text-destructive text-xs px-1"
              >✕</button>
            )}
          </div>
        ))}
      </div>

      <button
        onClick={addRow}
        className="text-xs text-muted-foreground hover:text-foreground underline"
      >
        {t('checkout.add_payment_line')}
      </button>

      <div className={`text-xs flex justify-between font-medium ${balanced ? 'text-green-600' : 'text-destructive'}`}>
        <span>{balanced ? t('checkout.balanced') : remaining > 0 ? t('checkout.short_by', { amount: Math.abs(remaining).toFixed(2) }) : t('checkout.over_by', { amount: Math.abs(remaining).toFixed(2) })}</span>
        <span>Total: ${fmt(saleTotal)}</span>
      </div>

      {error && <p className="text-xs text-destructive">{error}</p>}

      <div className="flex gap-2">
        <Button
          size="sm"
          disabled={!balanced || mutation.isPending}
          onClick={() => { setError(null); mutation.mutate() }}
        >
          {mutation.isPending ? t('common.saving') : t('common.save')}
        </Button>
        <Button size="sm" variant="outline" onClick={onDone}>{t('common.cancel')}</Button>
      </div>
    </div>
  )
}

export default function SaleSummary({ appointmentId }: Props) {
  const { t } = useTranslation()
  const { data: sale, isLoading, error } = useQuery({
    queryKey: ['sale', 'by-appointment', appointmentId],
    queryFn: () => getSaleByAppointment(appointmentId),
    retry: false,
  })
  const [editing, setEditing] = useState(false)
  const [editingItem, setEditingItem] = useState<string | null>(null)
  const qc = useQueryClient()

  const patchItemMutation = useMutation({
    mutationFn: ({ itemId, body }: { itemId: string; body: { discount_amount?: string; is_business_reimbursed?: boolean } }) =>
      patchSaleItem(sale?.id ?? '', itemId, body),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['sale-by-appointment', appointmentId] })
      setEditingItem(null)
    },
  })

  if (isLoading) {
    return <p className="text-xs text-muted-foreground text-center pt-2">{t('common.loading')}</p>
  }

  if (error || !sale) return null

  const discount = parseFloat(sale.discount_total)
  const showDiscount = Number.isFinite(discount) && discount > 0

  return (
    <div className="rounded-md border bg-muted/30 px-3 py-2 mt-2 space-y-1 text-xs">
      {/* Line items — editable if sale is today */}
      {sale.items.length > 0 && (
        <div className="space-y-1 pb-1.5 border-b">
          {sale.items.map((item: SaleItem) => {
            const hasDiscount = parseFloat(item.discount_amount) > 0
            const isEditing = editingItem === item.id
            return (
              <div key={item.id}>
                <div className="flex justify-between items-baseline">
                  <span className="text-muted-foreground truncate max-w-[160px]">{item.description}</span>
                  <div className="flex items-center gap-1.5 shrink-0">
                    {item.is_business_reimbursed && (
                      <span className="text-[9px] bg-amber-100 text-amber-700 px-1 rounded">BR</span>
                    )}
                    {hasDiscount && <span className="text-muted-foreground">−${fmt(item.discount_amount)}</span>}
                    <span>${fmt(item.line_total)}</span>
                    {sale.is_editable && (
                      <button onClick={() => setEditingItem(isEditing ? null : item.id)}
                        className="text-[10px] text-muted-foreground hover:text-foreground underline ml-1">
                        {isEditing ? 'cancel' : 'edit'}
                      </button>
                    )}
                  </div>
                </div>
                {isEditing && (
                  <ItemEditRow item={item} onSave={(body) => patchItemMutation.mutate({ itemId: item.id, body })}
                    saving={patchItemMutation.isPending} />
                )}
              </div>
            )
          })}
        </div>
      )}
      <div className="flex justify-between">
        <span className="text-muted-foreground">{t('checkout.sale_subtotal')}</span>
        <span>${fmt(sale.subtotal)}</span>
      </div>
      {showDiscount && (
        <div className="flex justify-between text-muted-foreground">
          <span>{t('checkout.sale_discount')}</span>
          <span>−${fmt(sale.discount_total)}</span>
        </div>
      )}
      <div className="flex justify-between text-muted-foreground">
        <span>{t('checkout.sale_gst')}</span>
        <span>${fmt(sale.gst_amount)}</span>
      </div>
      <div className="flex justify-between text-muted-foreground">
        <span>{t('checkout.sale_pst')}</span>
        <span>${fmt(sale.pst_amount)}</span>
      </div>
      <div className="flex justify-between font-semibold border-t pt-1 mt-1">
        <span>{t('checkout.sale_total')}</span>
        <span>${fmt(sale.total)}</span>
      </div>

      {sale.payments.length > 0 && (
        <div className="pt-1.5 mt-1.5 border-t space-y-0.5">
          {sale.payments.map(p => {
            const cb = parseFloat(p.cashback_amount)
            return (
              <div key={p.id} className="flex justify-between text-muted-foreground">
                <span>{p.payment_method_label}</span>
                <span>
                  ${fmt(p.amount)}
                  {Number.isFinite(cb) && cb > 0 && (
                    <span className="ml-1 text-[10px]">(−${fmt(p.cashback_amount)} cashback)</span>
                  )}
                </span>
              </div>
            )
          })}
          {sale.is_editable && !editing && (
            <button
              onClick={() => setEditing(true)}
              className="text-[10px] text-muted-foreground hover:text-foreground underline pt-0.5"
            >
              {t('checkout.edit_payments')}
            </button>
          )}
        </div>
      )}

      {editing && (
        <EditPaymentsDialog
          saleId={sale.id}
          saleTotal={sale.total}
          initialPayments={sale.payments.map(p => ({
            payment_method_id: p.payment_method_id,
            amount: p.amount,
            cashback_amount: p.cashback_amount,
          }))}
          onDone={() => setEditing(false)}
        />
      )}
    </div>
  )
}
