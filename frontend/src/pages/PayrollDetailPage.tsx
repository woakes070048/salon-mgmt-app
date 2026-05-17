import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { format, subMonths } from 'date-fns'
import { Download, Printer } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { listProviders } from '@/api/providers'
import { getPayrollDetail } from '@/api/reports'

function fmt(s: string | number | null | undefined): string {
  if (s == null) return '0.00'
  const n = typeof s === 'number' ? s : parseFloat(s)
  return Number.isFinite(n) ? n.toFixed(2) : '0.00'
}

function SummaryRow({ label, value, indent, bold, negative }: {
  label: string; value: string; indent?: boolean; bold?: boolean; negative?: boolean
}) {
  return (
    <div className={`flex justify-between py-1.5 text-sm border-b last:border-0 ${bold ? 'font-semibold' : ''}`}>
      <span className={`${indent ? 'pl-6' : ''} ${bold ? '' : 'text-muted-foreground'}`}>{label}</span>
      <span className="tabular-nums">{negative ? '−' : ''}${value}</span>
    </div>
  )
}

export default function PayrollDetailPage() {
  const now = new Date()
  const prev = subMonths(now, 1)
  const [providerId, setProviderId] = useState('')
  const [start, setStart] = useState(format(new Date(prev.getFullYear(), prev.getMonth(), 16), 'yyyy-MM-dd'))
  const [end, setEnd] = useState(format(new Date(now.getFullYear(), now.getMonth(), 15), 'yyyy-MM-dd'))
  const [query, setQuery] = useState<{ providerId: string; start: string; end: string } | null>(null)

  const { data: providers = [] } = useQuery({ queryKey: ['providers'], queryFn: listProviders })
  const activeProviders = providers.filter(p => p.has_appointments)

  const { data, isLoading, isError } = useQuery({
    queryKey: ['payroll-detail', query?.providerId, query?.start, query?.end],
    queryFn: () => getPayrollDetail(query!.providerId, query!.start, query!.end),
    enabled: !!query,
  })

  function downloadCsv() {
    if (!data) return
    const lines = [
      ['Payroll Detail Report'],
      [`Provider: ${data.provider_name}`],
      [`Period: ${data.period_start} to ${data.period_end}`],
      [],
      ['SERVICE TRANSACTIONS'],
      ['Date', 'Client', 'Service', 'Category', 'Gross', 'Product Fee', 'Net'],
      ...data.service_rows.map(r => [
        r.date, r.client_name, r.service_name, r.category ?? '',
        fmt(r.gross_amount), fmt(r.product_fee), fmt(r.net_amount),
      ]),
      [],
      ['RETAIL TRANSACTIONS'],
      ['Date', 'Client', 'Description', 'Amount'],
      ...data.retail_rows.map(r => [r.date, r.client_name, r.description, fmt(r.amount)]),
      [],
      ['SUMMARY'],
      ['Styling gross', fmt(data.styling_gross)],
      ['Styling product fees', fmt(data.styling_fees)],
      ['Colour gross', fmt(data.colour_gross)],
      ['Colour product fees', fmt(data.colour_fees)],
      ['Net service revenue', fmt(data.net_service_revenue)],
      [`Commission (${fmt(data.commission_rate_pct)}%)`, fmt(data.commission_on_services)],
      ['Retail revenue', fmt(data.retail_gross)],
      [`Retail commission (${fmt(data.retail_commission_pct)}%)`, fmt(data.retail_commission)],
      ['Gross before vacation', fmt(data.gross_before_vacation)],
      [`Vacation pay (${fmt(data.vacation_pct)}%)`, fmt(data.vacation_pay)],
      ['GROSS PAY', fmt(data.gross_pay)],
    ]
    const csv = lines.map(row =>
      row.map(v => `"${String(v).replace(/"/g, '""')}"`).join(',')
    ).join('\n')
    const blob = new Blob([csv], { type: 'text/csv' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `payroll-detail-${data.provider_name}-${query!.start}-${query!.end}.csv`
    a.click()
    URL.revokeObjectURL(url)
  }

  return (
    <div className="h-full overflow-auto bg-muted/30">
      <div className="max-w-5xl mx-auto px-6 py-8 space-y-6">

        <div className="flex items-center justify-between flex-wrap gap-4">
          <h1 className="text-xl font-semibold">Payroll Detail</h1>
          {data && (
            <div className="flex gap-2 print:hidden">
              <Button variant="outline" size="sm" onClick={downloadCsv} className="gap-1.5">
                <Download size={14} />Export CSV
              </Button>
              <Button variant="outline" size="sm" onClick={() => {
                const prev = document.title
                document.title = `${data.provider_name} Payroll Detail ${query!.start} to ${query!.end}`
                window.addEventListener('afterprint', () => { document.title = prev }, { once: true })
                window.print()
              }} className="gap-1.5" title="Print / Save PDF">
                <Printer size={14} />Print
              </Button>
            </div>
          )}
        </div>

        {/* Controls */}
        <div className="bg-white border rounded-lg p-4 flex flex-wrap gap-4 items-end print:hidden">
          <div className="space-y-1">
            <label className="text-xs text-muted-foreground uppercase tracking-wide">Provider</label>
            <select
              value={providerId}
              onChange={e => setProviderId(e.target.value)}
              className="border rounded-md px-2 py-1.5 text-sm bg-white min-w-[160px]"
            >
              <option value="">Select provider…</option>
              {activeProviders.map(p => (
                <option key={p.id} value={p.id}>{p.display_name}</option>
              ))}
            </select>
          </div>
          <div className="space-y-1">
            <label className="text-xs text-muted-foreground uppercase tracking-wide">Period start</label>
            <input type="date" value={start} onChange={e => setStart(e.target.value)}
              className="border rounded-md px-2 py-1.5 text-sm bg-white" />
          </div>
          <div className="space-y-1">
            <label className="text-xs text-muted-foreground uppercase tracking-wide">Period end</label>
            <input type="date" value={end} onChange={e => setEnd(e.target.value)}
              className="border rounded-md px-2 py-1.5 text-sm bg-white" />
          </div>
          <Button
            onClick={() => providerId && setQuery({ providerId, start, end })}
            disabled={!providerId}
          >
            Calculate
          </Button>
        </div>

        {isLoading && <p className="text-sm text-muted-foreground">Loading…</p>}
        {isError && <p className="text-sm text-destructive">Failed to load.</p>}

        {data && (
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">

            {/* Left: transactions */}
            <div className="lg:col-span-2 space-y-4">

              {/* Service transactions */}
              <div className="bg-white border rounded-lg overflow-hidden">
                <div className="px-4 py-3 border-b bg-muted/30 flex justify-between items-center">
                  <h2 className="text-sm font-medium">Service Transactions</h2>
                  <span className="text-xs text-muted-foreground">{data.service_rows.length} items</span>
                </div>
                <table className="w-full text-xs">
                  <thead className="bg-muted/10 border-b">
                    <tr>
                      <th className="text-left px-3 py-2 font-medium text-muted-foreground">Date</th>
                      <th className="text-left px-3 py-2 font-medium text-muted-foreground">Client</th>
                      <th className="text-left px-3 py-2 font-medium text-muted-foreground">Service</th>
                      <th className="text-left px-3 py-2 font-medium text-muted-foreground">Cat</th>
                      <th className="text-right px-3 py-2 font-medium text-muted-foreground">Gross</th>
                      <th className="text-right px-3 py-2 font-medium text-muted-foreground">Prod Fee</th>
                      <th className="text-right px-3 py-2 font-medium text-muted-foreground">Net</th>
                    </tr>
                  </thead>
                  <tbody>
                    {data.service_rows.map((r, i) => (
                      <tr key={i} className={`border-b last:border-0 ${r.is_colour ? 'bg-purple-50/30' : ''}`}>
                        <td className="px-3 py-1.5 tabular-nums">{r.date}</td>
                        <td className="px-3 py-1.5">{r.client_name}</td>
                        <td className="px-3 py-1.5 max-w-[160px] truncate">{r.service_name}</td>
                        <td className="px-3 py-1.5">
                          <span className={`px-1.5 py-0.5 rounded text-[10px] font-medium ${
                            r.is_colour ? 'bg-purple-100 text-purple-700' : 'bg-blue-50 text-blue-700'
                          }`}>
                            {r.is_colour ? 'Clr' : 'Sty'}
                          </span>
                        </td>
                        <td className="px-3 py-1.5 text-right tabular-nums">${fmt(r.gross_amount)}</td>
                        <td className="px-3 py-1.5 text-right tabular-nums text-muted-foreground">
                          {parseFloat(r.product_fee) > 0 ? `-$${fmt(r.product_fee)}` : ''}
                        </td>
                        <td className="px-3 py-1.5 text-right tabular-nums font-medium">${fmt(r.net_amount)}</td>
                      </tr>
                    ))}
                  </tbody>
                  <tfoot className="bg-muted/20 border-t">
                    <tr>
                      <td colSpan={4} className="px-3 py-2 text-xs font-semibold text-right text-muted-foreground">
                        Net service revenue
                      </td>
                      <td className="px-3 py-2 text-right text-xs tabular-nums">
                        ${fmt(parseFloat(data.styling_gross) + parseFloat(data.colour_gross))}
                      </td>
                      <td className="px-3 py-2 text-right text-xs tabular-nums text-muted-foreground">
                        -${fmt(parseFloat(data.styling_fees) + parseFloat(data.colour_fees))}
                      </td>
                      <td className="px-3 py-2 text-right text-xs font-bold tabular-nums">
                        ${fmt(data.net_service_revenue)}
                      </td>
                    </tr>
                  </tfoot>
                </table>
              </div>

              {/* Retail transactions */}
              {data.retail_rows.length > 0 && (
                <div className="bg-white border rounded-lg overflow-hidden">
                  <div className="px-4 py-3 border-b bg-muted/30 flex justify-between items-center">
                    <h2 className="text-sm font-medium">Retail Sales in Provider's Appointments</h2>
                    <span className="text-xs text-muted-foreground">{data.retail_rows.length} items</span>
                  </div>
                  <table className="w-full text-xs">
                    <thead className="bg-muted/10 border-b">
                      <tr>
                        <th className="text-left px-3 py-2 font-medium text-muted-foreground">Date</th>
                        <th className="text-left px-3 py-2 font-medium text-muted-foreground">Client</th>
                        <th className="text-left px-3 py-2 font-medium text-muted-foreground">Item</th>
                        <th className="text-right px-3 py-2 font-medium text-muted-foreground">Amount</th>
                      </tr>
                    </thead>
                    <tbody>
                      {data.retail_rows.map((r, i) => (
                        <tr key={i} className="border-b last:border-0">
                          <td className="px-3 py-1.5 tabular-nums">{r.date}</td>
                          <td className="px-3 py-1.5">{r.client_name}</td>
                          <td className="px-3 py-1.5">{r.description}</td>
                          <td className="px-3 py-1.5 text-right tabular-nums">${fmt(r.amount)}</td>
                        </tr>
                      ))}
                    </tbody>
                    <tfoot className="bg-muted/20 border-t">
                      <tr>
                        <td colSpan={3} className="px-3 py-2 text-xs font-semibold text-right">Total retail</td>
                        <td className="px-3 py-2 text-right text-xs font-bold">${fmt(data.retail_gross)}</td>
                      </tr>
                    </tfoot>
                  </table>
                </div>
              )}
            </div>

            {/* Right: commission summary */}
            <div className="space-y-4">
              <div className="bg-white border rounded-lg p-4">
                <h2 className="text-sm font-medium mb-3">Commission Summary</h2>
                <div className="space-y-0 text-sm">
                  <SummaryRow label="Styling gross" value={fmt(data.styling_gross)} indent />
                  <SummaryRow label="Less styling product fees" value={fmt(data.styling_fees)} indent negative />
                  <SummaryRow label="Colour gross" value={fmt(data.colour_gross)} indent />
                  <SummaryRow label="Less colour product fees" value={fmt(data.colour_fees)} indent negative />
                  <SummaryRow label="Net service revenue" value={fmt(data.net_service_revenue)} bold />
                  <SummaryRow
                    label={`Commission (${fmt(data.commission_rate_pct)}%)`}
                    value={fmt(data.commission_on_services)}
                    indent
                  />
                  {parseFloat(data.retail_gross) > 0 && <>
                    <SummaryRow label="Retail revenue" value={fmt(data.retail_gross)} indent />
                    <SummaryRow
                      label={`Retail commission (${fmt(data.retail_commission_pct)}%)`}
                      value={fmt(data.retail_commission)}
                      indent
                    />
                  </>}
                  <SummaryRow label="Gross before vacation" value={fmt(data.gross_before_vacation)} bold />
                  <SummaryRow
                    label={`Vacation pay (${fmt(data.vacation_pct)}%)`}
                    value={fmt(data.vacation_pay)}
                    indent
                  />
                  <SummaryRow label="Gross pay" value={fmt(data.gross_pay)} bold />
                </div>
              </div>

              <div className="bg-muted/30 rounded-lg p-4 text-xs text-muted-foreground space-y-1">
                <p><span className="font-medium">Pay basis:</span> {data.pay_basis}</p>
                <p><span className="font-medium">Period:</span> {data.period_start} → {data.period_end}</p>
                <p className="pt-1">Styling items shown in blue · Colour items in purple</p>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
