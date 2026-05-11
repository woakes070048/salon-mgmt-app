import { useState, useEffect, useMemo } from 'react'
import { useTranslation } from 'react-i18next'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import type { Appointment } from '@/api/appointments'
import { listAppointments } from '@/api/appointments'
import { createSale, sendReceipt, type Sale } from '@/api/sales'
import { listPaymentMethods } from '@/api/paymentMethods'
import { listPromotions, applyPromotion, type Promotion } from '@/api/promotions'
import { listRetailItems, type RetailItem } from '@/api/retailItems'
import { listProviders } from '@/api/providers'
import { Button } from '@/components/ui/button'
import { Label } from '@/components/ui/label'

interface Props {
  appointment: Appointment
  date: string
  onClose: () => void
  onCompleted: () => void
}

interface ItemDraft {
  kind: 'service' | 'retail'
  appointment_item_id: string | null
  retail_item_id: string | null
  description: string
  providerName: string
  commissionProviderId: string | null  // which provider earns retail commission
  quantity: number
  unitPrice: string
  discount: string        // always dollar amount used for calculations
  discountMode: '$' | '%'
  discountInput: string   // raw user input ($ or % depending on mode)
  isBusinessReimbursed: boolean
  promotionId: string | null
  isGstExempt: boolean
  isPstExempt: boolean
}

interface PaymentDraft {
  payment_method_id: string
  amount: string
  // Cash returned to the client out of the till. (amount - cashback) is
  // what counts toward the bill. Used for both card-tip-via-cashback (the
  // common case at Salon Lyol) and cash change-making — see P2-9.
  cashback: string
}

const GST_RATE = 0.05
const PST_RATE = 0.08

function toMoney(s: string): number {
  const n = parseFloat(s)
  return Number.isFinite(n) ? n : 0
}

function fmt(n: number): string {
  return n.toFixed(2)
}

export default function CheckoutPanel({ appointment, date, onClose, onCompleted }: Props) {
  const { t } = useTranslation()
  const qc = useQueryClient()

  const { data: methods = [], isLoading: methodsLoading } = useQuery({
    queryKey: ['payment-methods', 'active'],
    queryFn: () => listPaymentMethods(true),
  })

  const { data: promotions = [] } = useQuery({
    queryKey: ['promotions', 'active'],
    queryFn: () => listPromotions(true),
  })

  const { data: retailCatalog = [] } = useQuery({
    queryKey: ['retail-items', 'active'],
    queryFn: () => listRetailItems(true),
  })

  const { data: providers = [] } = useQuery({
    queryKey: ['providers'],
    queryFn: listProviders,
  })
  const activeProviders = providers.filter(p => p.has_appointments)

  const [items, setItems] = useState<ItemDraft[]>(() =>
    appointment.items.map(it => ({
      kind: 'service' as const,
      appointment_item_id: it.id,
      retail_item_id: null,
      description: it.service.name,
      providerName: it.provider.display_name,
      commissionProviderId: null,
      isBusinessReimbursed: false,
      quantity: 1,
      unitPrice: it.price.toFixed(2),
      discount: '0.00',
      discountMode: '$' as const,
      discountInput: '0.00',
      promotionId: null,
      isGstExempt: false,
      isPstExempt: false,
    }))
  )
  const [extraAppointments, setExtraAppointments] = useState<Appointment[]>([])
  const [notes, setNotes] = useState('')
  const [payments, setPayments] = useState<PaymentDraft[]>([])
  const [error, setError] = useState<string | null>(null)
  const [completedSale, setCompletedSale] = useState<Sale | null>(null)

  // Same-day in-progress appointments (for group checkout picker)
  const { data: sameDayAppts = [] } = useQuery({
    queryKey: ['appointments', date],
    queryFn: () => listAppointments(date),
  })
  const addableAppointments = sameDayAppts.filter(
    a => a.status === 'in_progress'
      && a.id !== appointment.id
      && !extraAppointments.find(e => e.id === a.id)
  )

  function addAppointment(appt: Appointment) {
    setExtraAppointments(prev => [...prev, appt])
    setItems(prev => [
      ...prev,
      ...appt.items.map(it => ({
        kind: 'service' as const,
        appointment_item_id: it.id,
        retail_item_id: null,
        description: it.service.name,
        providerName: it.provider.display_name,
      commissionProviderId: null,
      isBusinessReimbursed: false,
        quantity: 1,
        unitPrice: it.price.toFixed(2),
        discount: '0.00',
        discountMode: '$' as const,
        discountInput: '0.00',
        promotionId: null,
        isGstExempt: false,
        isPstExempt: false,
      })),
    ])
  }

  function removeExtraAppointment(apptId: string) {
    setExtraAppointments(prev => prev.filter(a => a.id !== apptId))
    setItems(prev => prev.filter(it => {
      const extra = extraAppointments.find(a => a.id === apptId)
      if (!extra) return true
      const extraItemIds = new Set(extra.items.map(i => i.id))
      return !extraItemIds.has(it.appointment_item_id ?? '')
    }))
  }

  // Initialise payment row once methods are loaded (default: first method, $0, no cashback).
  useEffect(() => {
    if (methods.length > 0 && payments.length === 0) {
      setPayments([{ payment_method_id: methods[0].id, amount: '0.00', cashback: '0.00' }])
    }
  }, [methods, payments.length])

  // Compute totals. Tip is intentionally not part of the sale — see P2-9.
  // Bill is covered when sum(amount - cashback) across payments equals total.
  const totals = useMemo(() => {
    const subtotal = items.reduce(
      (sum, i) => sum + Math.max(0, (toMoney(i.unitPrice) - toMoney(i.discount)) * i.quantity),
      0,
    )
    const discountTotal = items.reduce((sum, i) => sum + toMoney(i.discount) * i.quantity, 0)
    const gstTaxable = items.reduce(
      (sum, i) => !i.isGstExempt ? sum + Math.max(0, (toMoney(i.unitPrice) - toMoney(i.discount)) * i.quantity) : sum, 0
    )
    const pstTaxable = items.reduce(
      (sum, i) => !i.isPstExempt ? sum + Math.max(0, (toMoney(i.unitPrice) - toMoney(i.discount)) * i.quantity) : sum, 0
    )
    const gst = Math.round(gstTaxable * GST_RATE * 100) / 100
    const pst = Math.round(pstTaxable * PST_RATE * 100) / 100
    const total = Math.round((subtotal + gst + pst) * 100) / 100
    const applied = payments.reduce(
      (sum, p) => sum + toMoney(p.amount) - toMoney(p.cashback),
      0,
    )
    const remaining = Math.round((total - applied) * 100) / 100
    return { subtotal, discountTotal, gst, pst, total, remaining }
  }, [items, payments])

  // When the total changes (and there's only one payment row at default), update it
  useEffect(() => {
    if (payments.length === 1 && payments[0].amount === '0.00') {
      setPayments([{ ...payments[0], amount: fmt(totals.total) }])
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [totals.total])

  function updateItem(idx: number, patch: Partial<ItemDraft>) {
    setItems(prev => prev.map((it, i) => i === idx ? { ...it, ...patch } : it))
  }

  function addRetailItem(ri: RetailItem) {
    setItems(prev => [...prev, {
      kind: 'retail' as const,
      appointment_item_id: null,
      retail_item_id: ri.id,
      description: ri.name,
      providerName: '',
      commissionProviderId: null,
      isBusinessReimbursed: false,
      quantity: 1,
      unitPrice: parseFloat(ri.default_price).toFixed(2),
      discount: '0.00',
      discountMode: '$' as const,
      discountInput: '0.00',
      promotionId: null,
      isGstExempt: ri.is_gst_exempt,
      isPstExempt: ri.is_pst_exempt,
    }])
  }

  function removeItem(idx: number) {
    setItems(prev => prev.filter((_, i) => i !== idx))
  }

  function applyPromotionToItem(idx: number, promo: Promotion | null) {
    setItems(prev => prev.map((it, i) => {
      if (i !== idx) return it
      if (!promo) return { ...it, promotionId: null, discount: '0.00', discountMode: '$' as const, discountInput: '0.00' }
      const discountAmt = applyPromotion(promo, toMoney(it.unitPrice))
      return { ...it, promotionId: promo.id, discount: fmt(discountAmt), discountMode: '$' as const, discountInput: fmt(discountAmt) }
    }))
  }

  function updatePayment(idx: number, patch: Partial<PaymentDraft>) {
    setPayments(prev => prev.map((p, i) => {
      if (i !== idx) return p
      const updated = { ...p, ...patch }
      // When amount changes (and the user isn't simultaneously editing cashback),
      // auto-set cashback to the overage above what this row needs to contribute
      // to the bill. Common case: bill $73.45, user types amount $83.45 → cashback
      // auto-fills to $10.00. The user can still override cashback manually after.
      if (patch.amount !== undefined && patch.cashback === undefined) {
        const otherApplied = prev.reduce(
          (sum, op, j) => j === i ? sum : sum + toMoney(op.amount) - toMoney(op.cashback),
          0,
        )
        const needed = Math.max(0, Math.round((totals.total - otherApplied) * 100) / 100)
        const newAmount = toMoney(updated.amount)
        const newCashback = Math.max(0, Math.round((newAmount - needed) * 100) / 100)
        updated.cashback = fmt(newCashback)
      }
      return updated
    }))
  }

  function addPaymentRow() {
    if (methods.length === 0) return
    setPayments(prev => [
      ...prev,
      { payment_method_id: methods[0].id, amount: fmt(Math.max(0, totals.remaining)), cashback: '0.00' },
    ])
  }

  function removePaymentRow(idx: number) {
    setPayments(prev => prev.filter((_, i) => i !== idx))
  }

  const mutation = useMutation({
    mutationFn: () => createSale({
      appointment_ids: [appointment.id, ...extraAppointments.map(a => a.id)],
      notes: notes.trim() || null,
      items: items.map(i => ({
        appointment_item_id: i.appointment_item_id ?? null,
        retail_item_id: i.retail_item_id ?? null,
        commission_provider_id: i.kind === 'retail' ? (i.commissionProviderId ?? null) : null,
        quantity: i.quantity,
        unit_price: fmt(toMoney(i.unitPrice)),
        discount_amount: fmt(toMoney(i.discount)),
        is_business_reimbursed: i.isBusinessReimbursed,
        promotion_id: i.promotionId ?? null,
        is_gst_exempt: i.isGstExempt,
        is_pst_exempt: i.isPstExempt,
      })),
      payments: payments.map(p => ({
        payment_method_id: p.payment_method_id,
        amount: fmt(toMoney(p.amount)),
        cashback_amount: fmt(toMoney(p.cashback)),
      })),
    }),
    onSuccess: (sale) => {
      qc.invalidateQueries({ queryKey: ['appointments'] })
      setCompletedSale(sale)
    },
    onError: (err: unknown) => setError((err as Error).message ?? 'Checkout failed'),
  })

  function handleSubmit() {
    setError(null)
    if (totals.remaining !== 0) {
      setError(`Bill not balanced. Remaining: $${fmt(totals.remaining)}`)
      return
    }
    for (const p of payments) {
      const cb = toMoney(p.cashback)
      if (cb < 0) { setError('Cashback cannot be negative'); return }
      if (cb > toMoney(p.amount)) { setError('Cashback cannot exceed payment amount'); return }
    }
    mutation.mutate()
  }

  if (completedSale) {
    return (
      <ReceiptPanel
        sale={completedSale}
        clientEmail={appointment.client.email ?? null}
        clientName={`${appointment.client.first_name} ${appointment.client.last_name}`}
        methods={methods}
        onDone={onCompleted}
      />
    )
  }

  return (
    <div className="fixed inset-y-0 right-0 z-50 w-[440px] bg-white shadow-2xl flex flex-col border-l">
      {/* Header */}
      <div className="flex items-center justify-between px-5 py-4 border-b flex-shrink-0">
        <div>
          <h2 className="text-base font-semibold">{t('checkout.title')}</h2>
          <p className="text-xs text-muted-foreground mt-0.5">
            {appointment.client.first_name} {appointment.client.last_name}
          </p>
        </div>
        <button onClick={onClose} className="text-muted-foreground hover:text-foreground text-xl leading-none ml-3">×</button>
      </div>

      {/* Body */}
      <div className="flex-1 overflow-y-auto p-5 space-y-5">

        {/* Group checkout — extra appointments */}
        {(extraAppointments.length > 0 || addableAppointments.length > 0) && (
          <div className="space-y-1.5">
            <Label className="text-xs text-muted-foreground uppercase tracking-wide">{t('checkout.tab_appointments')}</Label>
            <div className="rounded-md border divide-y text-sm">
              <div className="px-3 py-2 flex justify-between items-center bg-muted/20">
                <span>{appointment.client.first_name} {appointment.client.last_name}</span>
                <span className="text-xs text-muted-foreground">{t('checkout.role_primary')}</span>
              </div>
              {extraAppointments.map(a => (
                <div key={a.id} className="px-3 py-2 flex justify-between items-center">
                  <span>{a.client.first_name} {a.client.last_name}</span>
                  <button
                    onClick={() => removeExtraAppointment(a.id)}
                    className="text-xs text-muted-foreground hover:text-destructive"
                  >{t('checkout.remove')}</button>
                </div>
              ))}
            </div>
            {addableAppointments.length > 0 && (
              <select
                className="text-xs border border-input rounded-md px-2 py-1 bg-background w-full"
                value=""
                onChange={e => {
                  const a = addableAppointments.find(x => x.id === e.target.value)
                  if (a) addAppointment(a)
                }}
              >
                <option value="">{t('checkout.add_appointment')}</option>
                {addableAppointments.map(a => (
                  <option key={a.id} value={a.id}>
                    {a.client.first_name} {a.client.last_name} — {a.items.map(i => i.service.name).join(', ')}
                  </option>
                ))}
              </select>
            )}
          </div>
        )}

        {/* Items */}
        <div className="space-y-2">
          <div className="flex items-center justify-between">
            <Label>{t('checkout.items_section')}</Label>
            {retailCatalog.length > 0 && (
              <select
                className="text-xs border border-input rounded-md px-2 py-1 bg-background"
                value=""
                onChange={e => {
                  const ri = retailCatalog.find(r => r.id === e.target.value)
                  if (ri) addRetailItem(ri)
                }}
              >
                <option value="">{t('checkout.add_retail')}</option>
                {retailCatalog.map(r => (
                  <option key={r.id} value={r.id}>{r.name} (${parseFloat(r.default_price).toFixed(2)})</option>
                ))}
              </select>
            )}
          </div>
          {items.map((it, idx) => {
            const lineTotal = Math.max(0, (toMoney(it.unitPrice) - toMoney(it.discount)) * it.quantity)
            const overDiscount = toMoney(it.discount) > toMoney(it.unitPrice)
            return (
              <div key={idx} className="rounded-md border p-3 space-y-2">
                <div className="flex items-start justify-between gap-2">
                  <div>
                    <p className="text-sm font-medium">{it.description}</p>
                    <p className="text-xs text-muted-foreground">
                      {it.kind === 'retail' ? 'Retail' : it.providerName}
                      {(it.isGstExempt || it.isPstExempt) && (
                        <span className="ml-1 text-amber-600">
                          ({[it.isGstExempt && 'GST', it.isPstExempt && 'PST'].filter(Boolean).join('+')} exempt)
                        </span>
                      )}
                    </p>
                  </div>
                  {it.kind === 'retail' && (
                    <button onClick={() => removeItem(idx)} className="text-muted-foreground hover:text-destructive text-lg leading-none">×</button>
                  )}
                </div>
                {it.kind === 'retail' && (
                  <div>
                    <label className="text-xs text-muted-foreground">Commission to</label>
                    <select
                      value={it.commissionProviderId ?? ''}
                      onChange={e => updateItem(idx, { commissionProviderId: e.target.value || null })}
                      className="w-full border border-input rounded-md px-2 py-1.5 text-sm bg-background mt-0.5"
                    >
                      <option value="">— no commission —</option>
                      {activeProviders.map(p => (
                        <option key={p.id} value={p.id}>{p.display_name}</option>
                      ))}
                    </select>
                  </div>
                )}
                {promotions.length > 0 && (
                  <div>
                    <label className="text-xs text-muted-foreground">{t('checkout.promotion_label')}</label>
                    <select
                      value={it.promotionId ?? ''}
                      onChange={e => {
                        const promo = promotions.find(p => p.id === e.target.value) ?? null
                        applyPromotionToItem(idx, promo)
                      }}
                      className="w-full border border-input rounded-md px-2 py-1.5 text-sm bg-background mt-0.5"
                    >
                      <option value="">{t('checkout.none_option')}</option>
                      {promotions.map(p => (
                        <option key={p.id} value={p.id}>
                          {p.label} ({p.kind === 'percent' ? `${p.value}%` : `$${p.value}`} off)
                        </option>
                      ))}
                    </select>
                  </div>
                )}
                <div className={`grid gap-2 ${it.kind === 'retail' ? 'grid-cols-4' : 'grid-cols-3'}`}>
                  {it.kind === 'retail' && (
                    <div>
                      <label className="text-xs text-muted-foreground">{t('checkout.qty')}</label>
                      <input
                        type="number"
                        min={1}
                        value={it.quantity}
                        onChange={e => updateItem(idx, { quantity: Math.max(1, parseInt(e.target.value) || 1) })}
                        className="w-full border border-input rounded-md px-2 py-1.5 text-sm bg-background mt-0.5"
                      />
                    </div>
                  )}
                  <div>
                    <label className="text-xs text-muted-foreground">{t('checkout.price_col')}</label>
                    <input
                      type="text"
                      inputMode="decimal"
                      value={it.unitPrice}
                      onChange={e => updateItem(idx, { unitPrice: e.target.value, promotionId: null })}
                      className="w-full border border-input rounded-md px-2 py-1.5 text-sm bg-background mt-0.5"
                    />
                  </div>
                  <div>
                    <label className="text-xs text-muted-foreground">{t('checkout.discount_col')}</label>
                    <div className={`flex mt-0.5 rounded-md border overflow-hidden ${overDiscount ? 'border-destructive' : 'border-input'}`}>
                      <input
                        type="text"
                        inputMode="decimal"
                        value={it.discountInput}
                        onChange={e => {
                          const raw = e.target.value
                          const num = parseFloat(raw) || 0
                          const dollar = it.discountMode === '%'
                            ? fmt(toMoney(it.unitPrice) * Math.min(num, 100) / 100)
                            : raw
                          updateItem(idx, { discountInput: raw, discount: dollar, promotionId: null })
                        }}
                        className="flex-1 min-w-0 px-2 py-1.5 text-sm bg-background outline-none"
                      />
                      {(['$', '%'] as const).map(mode => (
                        <button
                          key={mode}
                          type="button"
                          onClick={() => {
                            const price = toMoney(it.unitPrice)
                            const existingDollar = toMoney(it.discount)
                            const newInput = mode === '%' && price > 0
                              ? fmt((existingDollar / price) * 100)
                              : fmt(existingDollar)
                            updateItem(idx, { discountMode: mode, discountInput: newInput, promotionId: null })
                          }}
                          className={`px-2 text-xs font-medium border-l border-input transition-colors ${
                            it.discountMode === mode
                              ? 'bg-foreground text-background'
                              : 'bg-muted text-muted-foreground hover:bg-muted/70'
                          }`}
                        >{mode}</button>
                      ))}
                    </div>
                  </div>
                  <div>
                    <label className="text-xs text-muted-foreground">{t('checkout.line_col')}</label>
                    <div className="px-2 py-1.5 text-sm mt-0.5 font-medium">${fmt(lineTotal)}</div>
                  </div>
                </div>
                {/* Business Reimbursed toggle — only shown when there is a discount */}
                {toMoney(it.discount) > 0 && (
                  <label className="flex items-center gap-2 cursor-pointer select-none pt-1">
                    <input
                      type="checkbox"
                      checked={it.isBusinessReimbursed}
                      onChange={e => updateItem(idx, { isBusinessReimbursed: e.target.checked })}
                      className="h-3.5 w-3.5 rounded border-input accent-foreground"
                    />
                    <span className="text-xs text-muted-foreground">
                      Business reimbursed — provider commissioned &amp; product fee on full amount
                    </span>
                  </label>
                )}
              </div>
            )
          })}
        </div>

        {/* Totals */}
        <div className="rounded-md bg-muted/40 p-3 space-y-1 text-sm">
          <div className="flex justify-between"><span>{t('checkout.subtotal')}</span><span>${fmt(totals.subtotal)}</span></div>
          {totals.discountTotal > 0 && (
            <div className="flex justify-between text-muted-foreground">
              <span>{t('checkout.discount')}</span><span>−${fmt(totals.discountTotal)}</span>
            </div>
          )}
          <div className="flex justify-between"><span>{t('checkout.gst')}</span><span>${fmt(totals.gst)}</span></div>
          <div className="flex justify-between"><span>{t('checkout.pst')}</span><span>${fmt(totals.pst)}</span></div>
          <div className="flex justify-between font-semibold border-t pt-1 mt-1">
            <span>{t('checkout.total')}</span><span>${fmt(totals.total)}</span>
          </div>
        </div>

        {/* Payments */}
        <div className="space-y-2">
          <div className="flex items-center justify-between">
            <Label>{t('checkout.payment_section')}</Label>
            <button
              type="button"
              onClick={addPaymentRow}
              className="text-xs text-muted-foreground hover:text-foreground"
            >
              {t('checkout.split_payment')}
            </button>
          </div>
          {methodsLoading && payments.length === 0 && (
            <p className="text-xs text-muted-foreground">{t('checkout.loading_methods')}</p>
          )}
          {!methodsLoading && methods.length === 0 && (
            <p className="text-xs text-destructive">
              {t('checkout.no_payment_methods')}
            </p>
          )}
          {payments.map((p, idx) => {
            const amountNum = toMoney(p.amount)
            const cashbackNum = toMoney(p.cashback)
            const applied = Math.round((amountNum - cashbackNum) * 100) / 100
            const cashbackInvalid = cashbackNum < 0 || cashbackNum > amountNum
            return (
              <div key={idx} className="space-y-1.5">
                <div className="flex gap-2 items-center">
                  <select
                    value={p.payment_method_id}
                    onChange={e => updatePayment(idx, { payment_method_id: e.target.value })}
                    className="border border-input rounded-md px-2 py-1.5 text-sm bg-background flex-1"
                  >
                    {methods.map(m => (
                      <option key={m.id} value={m.id}>{m.label}</option>
                    ))}
                  </select>
                  <input
                    type="text"
                    inputMode="decimal"
                    value={p.amount}
                    onChange={e => updatePayment(idx, { amount: e.target.value })}
                    title="Total paid via this method (charged to card or handed over in cash)"
                    className="w-24 border border-input rounded-md px-2 py-1.5 text-sm bg-background"
                  />
                  {payments.length > 1 && (
                    <button
                      type="button"
                      onClick={() => removePaymentRow(idx)}
                      className="text-muted-foreground hover:text-destructive text-lg leading-none px-1"
                    >
                      ×
                    </button>
                  )}
                </div>
                <div className="flex gap-2 items-center pl-2 border-l-2 border-muted-foreground/20">
                  <label className="text-xs text-muted-foreground w-20">{t('checkout.cashback_label')}</label>
                  <input
                    type="text"
                    inputMode="decimal"
                    value={p.cashback}
                    onChange={e => updatePayment(idx, { cashback: e.target.value })}
                    title="Cash returned to client out of the till (often handed to the staff member as a tip)"
                    className={`w-24 border rounded-md px-2 py-1 text-xs bg-background ${
                      cashbackInvalid ? 'border-destructive' : 'border-input'
                    }`}
                  />
                  <span className="text-xs text-muted-foreground">
                    {t('checkout.applies_to')}{' '}
                    <span className="text-foreground font-medium">${fmt(applied)}</span>
                  </span>
                </div>
              </div>
            )
          })}
          <p className={`text-xs ${totals.remaining === 0 ? 'text-green-600' : 'text-destructive'}`}>
            {totals.remaining === 0
              ? t('checkout.bill_balanced')
              : totals.remaining > 0
                ? t('checkout.bill_short', { amount: fmt(totals.remaining) })
                : t('checkout.bill_over', { amount: fmt(-totals.remaining) })}
          </p>
        </div>

        {/* Notes */}
        <div className="space-y-1.5">
          <Label htmlFor="notes">{t('checkout.notes_section')}</Label>
          <textarea
            id="notes"
            value={notes}
            onChange={e => setNotes(e.target.value)}
            rows={2}
            placeholder={t('checkout.notes_placeholder')}
            className="w-full border border-input rounded-md px-3 py-2 text-sm bg-background resize-none"
          />
        </div>

        {error && <p className="text-sm text-destructive">{error}</p>}
      </div>

      {/* Footer */}
      <div className="border-t px-5 py-4 flex gap-2 flex-shrink-0">
        <Button variant="outline" onClick={onClose} disabled={mutation.isPending}>{t('common.cancel')}</Button>
        <Button
          onClick={handleSubmit}
          disabled={mutation.isPending || totals.remaining !== 0 || payments.length === 0}
          className="flex-1"
        >
          {mutation.isPending ? t('checkout.processing') : t('checkout.complete_checkout', { total: fmt(totals.total) })}
        </Button>
      </div>
    </div>
  )
}

// ── Receipt panel ─────────────────────────────────────────────────────────────

import type { PaymentMethod } from '@/api/paymentMethods'

function ReceiptPanel({
  sale, clientEmail, clientName, methods, onDone,
}: {
  sale: Sale
  clientEmail: string | null
  clientName: string
  methods: PaymentMethod[]
  onDone: () => void
}) {
  const { t } = useTranslation()
  const methodsById = Object.fromEntries(methods.map(m => [m.id, m]))
  const [emailTo, setEmailTo] = useState(clientEmail ?? '')
  const [emailSent, setEmailSent] = useState(false)
  const [emailError, setEmailError] = useState<string | null>(null)

  const emailMutation = useMutation({
    mutationFn: () => sendReceipt(sale.id, emailTo.trim()),
    onSuccess: () => { setEmailSent(true); setEmailError(null) },
    onError: (e: Error) => setEmailError(e.message ?? 'Failed to send'),
  })

  function handlePrint() {
    const w = window.open('', '_blank', 'width=400,height=600')
    if (!w) return
    const itemRows = sale.items.map(it =>
      `<tr><td>${it.description}</td><td style="text-align:right">$${parseFloat(it.line_total).toFixed(2)}</td></tr>`
    ).join('')
    const payRows = sale.payments.map(p => {
      const label = methodsById[p.payment_method_id]?.label ?? p.payment_method_label ?? '—'
      return `<tr><td>${label}</td><td style="text-align:right">$${parseFloat(p.amount).toFixed(2)}</td></tr>`
    }).join('')
    w.document.write(`
      <html><head><title>Receipt</title>
      <style>body{font-family:sans-serif;font-size:13px;padding:16px}
      table{width:100%;border-collapse:collapse}td{padding:3px 0}
      hr{border:none;border-top:1px solid #ccc;margin:8px 0}
      .total{font-weight:bold}</style></head>
      <body>
        <h3 style="margin:0 0 4px">${clientName}</h3>
        <p style="margin:0 0 12px;color:#555">${sale.completed_at ? new Date(sale.completed_at).toLocaleDateString() : ''}</p>
        <table>${itemRows}</table>
        <hr/>
        <table>
          <tr><td>Subtotal</td><td style="text-align:right">$${parseFloat(sale.subtotal).toFixed(2)}</td></tr>
          <tr><td>GST (5%)</td><td style="text-align:right">$${parseFloat(sale.gst_amount).toFixed(2)}</td></tr>
          <tr><td>PST (8%)</td><td style="text-align:right">$${parseFloat(sale.pst_amount).toFixed(2)}</td></tr>
          <tr class="total"><td>Total</td><td style="text-align:right">$${parseFloat(sale.total).toFixed(2)}</td></tr>
        </table>
        <hr/>
        <table>${payRows}</table>
      </body></html>`)
    w.document.close()
    w.print()
  }

  return (
    <div className="fixed inset-y-0 right-0 z-50 w-[440px] bg-white shadow-2xl flex flex-col border-l">
      <div className="flex items-center justify-between px-5 py-4 border-b flex-shrink-0">
        <div>
          <h2 className="text-base font-semibold">{t('checkout.receipt_title')}</h2>
          <p className="text-xs text-muted-foreground mt-0.5">{clientName} · ${parseFloat(sale.total).toFixed(2)}</p>
        </div>
      </div>

      <div className="flex-1 overflow-y-auto p-5 space-y-5">
        {/* Summary */}
        <div className="rounded-md bg-muted/30 p-3 space-y-1 text-sm">
          {sale.items.map(it => (
            <div key={it.id} className="flex justify-between">
              <span className="text-muted-foreground">{it.description}</span>
              <span>${parseFloat(it.line_total).toFixed(2)}</span>
            </div>
          ))}
          <div className="flex justify-between border-t pt-1 mt-1 text-muted-foreground text-xs">
            <span>GST + PST</span>
            <span>${(parseFloat(sale.gst_amount) + parseFloat(sale.pst_amount)).toFixed(2)}</span>
          </div>
          <div className="flex justify-between font-semibold">
            <span>Total</span>
            <span>${parseFloat(sale.total).toFixed(2)}</span>
          </div>
          <div className="border-t pt-1 mt-1 space-y-0.5">
            {sale.payments.map(p => (
              <div key={p.id} className="flex justify-between text-xs text-muted-foreground">
                <span>{methodsById[p.payment_method_id]?.label ?? p.payment_method_label}</span>
                <span>${parseFloat(p.amount).toFixed(2)}</span>
              </div>
            ))}
          </div>
        </div>

        {/* Print */}
        <Button variant="outline" className="w-full" onClick={handlePrint}>
          {t('checkout.print_receipt')}
        </Button>

        {/* Email */}
        <div className="space-y-2">
          <Label>{t('checkout.email_receipt')}</Label>
          <div className="flex gap-2">
            <input
              type="email"
              value={emailTo}
              onChange={e => setEmailTo(e.target.value)}
              placeholder={t('checkout.email_placeholder')}
              className="flex-1 border border-input rounded-md px-3 py-1.5 text-sm bg-background"
            />
            <Button
              variant="outline"
              onClick={() => emailMutation.mutate()}
              disabled={!emailTo.trim() || emailMutation.isPending || emailSent}
            >
              {emailMutation.isPending ? t('common.sending') : emailSent ? t('common.sent') + ' ✓' : t('common.send')}
            </Button>
          </div>
          {emailError && <p className="text-xs text-destructive">{emailError}</p>}
        </div>
      </div>

      <div className="border-t px-5 py-4 flex-shrink-0">
        <Button className="w-full" onClick={onDone}>{t('common.done')}</Button>
      </div>
    </div>
  )
}
