import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { format, addMonths, subMonths, endOfMonth } from 'date-fns'
import { ChevronLeft, ChevronRight } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { useDateLocale } from '@/lib/dateLocale'
import { getMonthlyReport } from '@/api/reports'
import { getPayrollReport } from '@/api/providers'
import { Button } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/skeleton'

function fmt(s: string | number): string {
  const n = typeof s === 'number' ? s : parseFloat(s)
  return Number.isFinite(n) ? n.toFixed(2) : '0.00'
}

function SummaryCard({ label, value, sub }: { label: string; value: string; sub?: string }) {
  return (
    <div className="bg-white border rounded-lg px-4 py-3 space-y-0.5">
      <p className="text-xs text-muted-foreground">{label}</p>
      <p className="text-xl font-semibold tabular-nums">${value}</p>
      {sub && <p className="text-xs text-muted-foreground">{sub}</p>}
    </div>
  )
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="bg-white border rounded-lg overflow-hidden">
      <div className="px-4 py-3 border-b bg-muted/30">
        <h2 className="text-sm font-medium">{title}</h2>
      </div>
      {children}
    </div>
  )
}

function Row({
  label, value, indent, bold, negative, sub,
}: {
  label: string; value: string; indent?: boolean; bold?: boolean; negative?: boolean; sub?: string
}) {
  return (
    <div className={`flex justify-between items-baseline px-4 py-2 border-b last:border-0 text-sm ${bold ? 'font-semibold' : ''}`}>
      <span className={`${bold ? '' : 'text-muted-foreground'} ${indent ? 'pl-4' : ''}`}>
        {label}
        {sub && <span className="ml-2 text-xs font-normal text-muted-foreground">{sub}</span>}
      </span>
      <span className="tabular-nums">{negative ? '−' : ''}${value}</span>
    </div>
  )
}

export default function ReportsPage() {
  const { t } = useTranslation()
  const { locale } = useDateLocale()
  const now = new Date()
  const [cursor, setCursor] = useState(new Date(now.getFullYear(), now.getMonth(), 1))

  const year = cursor.getFullYear()
  const month = cursor.getMonth() + 1
  const monthStart = format(cursor, 'yyyy-MM-dd')
  const monthEnd = format(endOfMonth(cursor), 'yyyy-MM-dd')

  const { data: report, isLoading } = useQuery({
    queryKey: ['monthly-report', year, month],
    queryFn: () => getMonthlyReport(year, month),
  })

  const { data: payroll } = useQuery({
    queryKey: ['payroll-report-for-sales', year, month],
    queryFn: () => getPayrollReport(monthStart, monthEnd),
    enabled: !!report && report.sale_count > 0,
  })

  const payrollTotal = payroll?.lines.reduce((sum, l) => sum + l.gross_pay, 0) ?? 0
  const netSales = report ? parseFloat(report.subtotal) : 0
  const payrollPct = payrollTotal > 0 && netSales > 0 ? (payrollTotal / netSales) * 100 : null

  const isCurrentMonth = year === now.getFullYear() && month === now.getMonth() + 1

  return (
    <div className="h-full overflow-auto bg-muted/30">
      <div className="max-w-2xl mx-auto px-6 py-8 space-y-6">

        {/* Header + month nav */}
        <div className="flex items-center justify-between">
          <h1 className="text-xl font-semibold">{t('reports.sales_title')}</h1>
          <div className="flex items-center gap-2">
            <Button variant="outline" size="icon" onClick={() => setCursor(subMonths(cursor, 1))}>
              <ChevronLeft size={16} />
            </Button>
            <span className="text-sm font-medium w-32 text-center">
              {format(cursor, 'MMMM yyyy', { locale })}
            </span>
            <Button variant="outline" size="icon" onClick={() => setCursor(addMonths(cursor, 1))} disabled={isCurrentMonth}>
              <ChevronRight size={16} />
            </Button>
          </div>
        </div>

        {isLoading ? (
          <div className="space-y-3">
            <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
              {Array.from({ length: 4 }).map((_, i) => <Skeleton key={i} className="h-20 rounded-lg" />)}
            </div>
            <Skeleton className="h-12 rounded-lg" />
            <Skeleton className="h-48 rounded-lg" />
            <Skeleton className="h-40 rounded-lg" />
          </div>
        ) : !report ? null : report.sale_count === 0 ? (
          <p className="text-sm text-muted-foreground text-center py-16">No completed sales in {format(cursor, 'MMMM yyyy', { locale })}.</p>
        ) : (
          <>
            {/* Summary cards */}
            <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
              <SummaryCard label={t('reports.revenue_card')} value={fmt(report.total)} />
              <div className="bg-white border rounded-lg px-4 py-3 space-y-0.5">
                <p className="text-xs text-muted-foreground">{t('reports.sales_card')}</p>
                <p className="text-xl font-semibold tabular-nums">{report.sale_count}</p>
              </div>
              <SummaryCard label={t('reports.tax_card')} value={fmt(String(parseFloat(report.gst_amount) + parseFloat(report.pst_amount)))} sub={t('reports.tax_subtitle')} />
              <SummaryCard label={t('reports.avg_sale_card')} value={fmt(String(parseFloat(report.total) / report.sale_count))} />
            </div>

            {/* Payroll % of net sales — primary KPI */}
            {payrollPct !== null && (
              <div className={`flex items-center justify-between rounded-lg border px-5 py-4 ${
                payrollPct > 60 ? 'bg-red-50 border-red-200' :
                payrollPct > 50 ? 'bg-amber-50 border-amber-200' :
                'bg-green-50 border-green-200'
              }`}>
                <div>
                  <p className="text-xs text-muted-foreground">Payroll % of net sales</p>
                  <p className="text-2xl font-semibold tabular-nums mt-0.5">{payrollPct.toFixed(1)}%</p>
                </div>
                <div className="text-right text-sm text-muted-foreground">
                  <p>Payroll ${fmt(payrollTotal)}</p>
                  <p>Net sales ${fmt(netSales)}</p>
                </div>
              </div>
            )}

            {/* Revenue */}
            <Section title={t('reports.revenue_section')}>
              {/* Service stream */}
              <Row label="Service sales" value={fmt(report.service_gross)} />
              <Row label="Less discounts" value={fmt(report.service_discount)} indent negative />
              <Row label="Less returns" value="0.00" indent negative />
              <Row label="Total service sales" value={fmt(report.service_total)} />

              {/* Retail stream */}
              <Row label="Retail sales" value={fmt(report.retail_gross)} />
              <Row label="Less discounts" value={fmt(report.retail_discount)} indent negative />
              <Row label="Less returns" value={fmt(report.retail_returns)} indent negative />
              <Row label="Total retail sales" value={fmt(report.retail_total)} />

              {/* Totals */}
              <Row label="Total sales before taxes" value={fmt(report.subtotal)} bold />
              <Row label="GST (5%)" value={fmt(report.gst_amount)} indent />
              <Row label="PST (8%)" value={fmt(report.pst_amount)} indent />
              <Row
                label="Total taxes collected"
                value={fmt(parseFloat(report.gst_amount) + parseFloat(report.pst_amount))}
                indent
              />

              {/* Below-the-line adjustments — match Milano structure */}
              <Row label="Gift cards" value={fmt(report.gift_card_total)} />
              <Row label="Less on account sales" value={fmt(report.on_account_sales)} negative />
              <Row label="Plus on account payments" value={fmt(report.on_account_payments)} />

              <Row label="Grand total" value={fmt(report.total)} bold />
            </Section>

            {/* By provider */}
            {report.by_provider.length > 0 && (
              <Section title={t('reports.by_provider')}>
                {report.by_provider.map(r => (
                  <Row
                    key={r.provider_name}
                    label={r.provider_name}
                    value={fmt(r.total)}
                    sub={`${r.sale_count} ${r.sale_count === 1 ? 'sale' : 'sales'}`}
                  />
                ))}
              </Section>
            )}

            {/* Payment reconciliation */}
            {report.by_payment_method.length > 0 && (
              <Section title={t('reports.payment_section')}>
                {report.by_payment_method.map(r => {
                  const net = parseFloat(r.net)
                  const hasCashback = parseFloat(r.cashback) > 0
                  const isCash = r.label.toLowerCase().includes('cash')
                  return (
                    <div key={r.label} className="flex justify-between items-baseline px-4 py-2 border-b text-sm">
                      <span className="text-muted-foreground">{r.label}</span>
                      <span className={`tabular-nums text-right ${isCash && net < 0 ? 'text-destructive' : ''}`}>
                        {net < 0 ? '−' : ''}${fmt(Math.abs(net))}
                        {hasCashback && (
                          <span className="ml-2 text-xs text-muted-foreground">
                            −${fmt(r.cashback)} cashback
                          </span>
                        )}
                      </span>
                    </div>
                  )
                })}
                {(() => {
                  const paymentSubtotal = report.by_payment_method.reduce(
                    (sum, r) => sum + parseFloat(r.net), 0
                  )
                  const petty = parseFloat(report.petty_cash_total)
                  const grandTotal = parseFloat(report.total)
                  return (
                    <>
                      <Row label="Sub total" value={fmt(paymentSubtotal)} bold />
                      {petty > 0 && (
                        <Row label="Plus petty cash" value={fmt(petty)} />
                      )}
                      <Row label={t('reports.grand_total')} value={fmt(petty > 0 ? paymentSubtotal + petty : grandTotal)} bold />
                    </>
                  )
                })()}
              </Section>
            )}

            {/* Daily breakdown */}
            <Section title={t('reports.daily_section')}>
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b text-xs text-muted-foreground">
                      <th className="px-4 py-2 text-left font-medium">{t('reports.col_date')}</th>
                      <th className="px-4 py-2 text-right font-medium">{t('reports.col_sales')}</th>
                      <th className="px-4 py-2 text-right font-medium">{t('reports.col_revenue')}</th>
                    </tr>
                  </thead>
                  <tbody>
                    {report.by_day.map(r => (
                      <tr key={r.date} className="border-b last:border-0 hover:bg-muted/20">
                        <td className="px-4 py-2">
                          {format(new Date(r.date + 'T12:00:00'), 'EEE, MMM d')}
                        </td>
                        <td className="px-4 py-2 text-right text-muted-foreground">{r.sale_count}</td>
                        <td className="px-4 py-2 text-right tabular-nums">${fmt(r.total)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </Section>
          </>
        )}
      </div>
    </div>
  )
}
