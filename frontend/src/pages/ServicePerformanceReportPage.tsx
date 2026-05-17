import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { format, subMonths } from 'date-fns'
import { Download, Printer } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { listProviders } from '@/api/providers'
import { getServicePerformance } from '@/api/reports'

function fmt(s: string | number | null | undefined): string {
  if (s == null) return '0.00'
  const n = typeof s === 'number' ? s : parseFloat(s)
  return Number.isFinite(n) ? n.toFixed(2) : '0.00'
}

function fmtPct(s: string | number | null | undefined): string {
  if (s == null) return '0.0'
  const n = typeof s === 'number' ? s : parseFloat(s)
  return Number.isFinite(n) ? n.toFixed(1) : '0.0'
}

function SummaryRow({ label, value, indent, bold }: {
  label: string; value: string; indent?: boolean; bold?: boolean
}) {
  return (
    <div className={`flex justify-between py-1.5 text-sm border-b last:border-0 ${bold ? 'font-semibold' : ''}`}>
      <span className={`${indent ? 'pl-6' : ''} ${bold ? '' : 'text-muted-foreground'}`}>{label}</span>
      <span className="tabular-nums">{value}</span>
    </div>
  )
}

export default function ServicePerformanceReportPage() {
  const now = new Date()
  const prev = subMonths(now, 1)
  const [providerId, setProviderId] = useState('')
  const [start, setStart] = useState(format(new Date(prev.getFullYear(), prev.getMonth(), 16), 'yyyy-MM-dd'))
  const [end, setEnd] = useState(format(new Date(now.getFullYear(), now.getMonth(), 15), 'yyyy-MM-dd'))
  const [query, setQuery] = useState<{ providerId: string; start: string; end: string } | null>(null)

  const { data: providers = [] } = useQuery({ queryKey: ['providers'], queryFn: listProviders })
  const activeProviders = providers.filter(p => p.has_appointments)

  const { data, isLoading, isError } = useQuery({
    queryKey: ['service-performance', query?.providerId, query?.start, query?.end],
    queryFn: () => getServicePerformance(query!.providerId, query!.start, query!.end),
    enabled: !!query,
  })

  function downloadCsv() {
    if (!data) return
    const lines = [
      ['Service Performance Report'],
      [`Provider: ${data.provider_name}`],
      [`Period: ${data.period_start} to ${data.period_end}`],
      [],
      ['SERVICES'],
      ['Service', 'Total Sales', 'Product Fee', 'Net Sales', '# Sales', 'Avg Price', '% of Sales', '% of Count'],
      ...data.service_rows.map(r => [
        r.service_name, fmt(r.total_sales), fmt(r.product_fee), fmt(r.net_sales),
        String(r.sales_count),
        fmt(r.average_price), fmtPct(r.pct_of_sales), fmtPct(r.pct_of_count),
      ]),
      [],
      ['TOTALS'],
      ['Total service sales (gross)', fmt(data.total_service_sales), String(data.total_service_count)],
      ['Total product fees', fmt(data.total_service_fees)],
      ['Total net service sales', fmt(data.total_net_service_sales)],
      ['Total retail sales', fmt(data.total_retail_sales), String(data.total_retail_count)],
      ['Total sales', fmt(data.total_sales)],
      [],
      ['RATIOS'],
      ['% Service of total', fmtPct(data.pct_service_of_total)],
      ['% Retail of total', fmtPct(data.pct_retail_of_total)],
      ['% Retail of service', fmtPct(data.pct_retail_of_service)],
      [],
      ['RECEIPTS'],
      ['# Receipts', String(data.receipt_count)],
      ['# Clients serviced', String(data.clients_serviced)],
      ['Avg per receipt', fmt(data.avg_per_receipt)],
      ['Items per receipt', fmt(data.items_per_receipt)],
    ]
    const csv = lines.map(row =>
      row.map(v => `"${String(v).replace(/"/g, '""')}"`).join(',')
    ).join('\n')
    const blob = new Blob([csv], { type: 'text/csv' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `service-performance-${data.provider_name}-${query!.start}-${query!.end}.csv`
    a.click()
    URL.revokeObjectURL(url)
  }

  const empty = !!data && data.service_rows.length === 0 && data.total_retail_count === 0

  return (
    <div className="h-full overflow-auto bg-muted/30">
      <div className="max-w-5xl mx-auto px-6 py-8 space-y-6">

        <div className="flex items-center justify-between flex-wrap gap-4">
          <h1 className="text-xl font-semibold">Service Performance</h1>
          {data && !empty && (
            <div className="flex gap-2 print:hidden">
              <Button variant="outline" size="sm" onClick={downloadCsv} className="gap-1.5">
                <Download size={14} />Export CSV
              </Button>
              <Button variant="outline" size="sm" onClick={() => {
                const prevTitle = document.title
                document.title = `${data.provider_name} Service Performance ${query!.start} to ${query!.end}`
                window.addEventListener('afterprint', () => { document.title = prevTitle }, { once: true })
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
            Run report
          </Button>
        </div>

        {isLoading && <p className="text-sm text-muted-foreground">Loading…</p>}
        {isError && <p className="text-sm text-destructive">Failed to load.</p>}

        {data && (
          <>
            {/* Print-only header */}
            <div className="hidden print:block text-center space-y-1 mb-4">
              <p className="text-base font-semibold">Service Performance Report for {data.provider_name}</p>
              <p className="text-sm text-muted-foreground">
                {data.period_start} to {data.period_end}
              </p>
            </div>

            {empty ? (
              <div className="bg-white border rounded-lg p-10 text-center text-sm text-muted-foreground">
                No sales for {data.provider_name} in this period.
              </div>
            ) : (
              <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">

                {/* Left: service breakdown */}
                <div className="lg:col-span-2 space-y-4">
                  <div className="bg-white border rounded-lg overflow-hidden">
                    <div className="px-4 py-3 border-b bg-muted/30 flex justify-between items-center">
                      <h2 className="text-sm font-medium">Services</h2>
                      <span className="text-xs text-muted-foreground">{data.service_rows.length} services</span>
                    </div>
                    <table className="w-full text-xs">
                      <thead className="bg-muted/10 border-b">
                        <tr>
                          <th className="text-left px-3 py-2 font-medium text-muted-foreground">Service</th>
                          <th className="text-right px-3 py-2 font-medium text-muted-foreground">Total Sales</th>
                          <th className="text-right px-3 py-2 font-medium text-muted-foreground">Product Fee</th>
                          <th className="text-right px-3 py-2 font-medium text-muted-foreground">Net Sales</th>
                          <th className="text-right px-3 py-2 font-medium text-muted-foreground"># Sales</th>
                          <th className="text-right px-3 py-2 font-medium text-muted-foreground">Avg Price</th>
                          <th className="text-right px-3 py-2 font-medium text-muted-foreground">% Sales</th>
                          <th className="text-right px-3 py-2 font-medium text-muted-foreground">% Count</th>
                        </tr>
                      </thead>
                      <tbody>
                        {data.service_rows.map((r, i) => {
                          const unmapped = r.service_name.startsWith('(Unmapped)')
                          return (
                            <tr key={i} className={`border-b last:border-0 ${unmapped ? 'bg-amber-50' : ''}`}>
                              <td className="px-3 py-1.5" title={unmapped ? 'No matching Service in catalog — sale_item not linked' : undefined}>{r.service_name}</td>
                              <td className="px-3 py-1.5 text-right tabular-nums">${fmt(r.total_sales)}</td>
                              <td className="px-3 py-1.5 text-right tabular-nums text-muted-foreground">${fmt(r.product_fee)}</td>
                              <td className="px-3 py-1.5 text-right tabular-nums font-medium">${fmt(r.net_sales)}</td>
                              <td className="px-3 py-1.5 text-right tabular-nums">{r.sales_count}</td>
                              <td className="px-3 py-1.5 text-right tabular-nums text-muted-foreground">${fmt(r.average_price)}</td>
                              <td className="px-3 py-1.5 text-right tabular-nums text-muted-foreground">{fmtPct(r.pct_of_sales)}%</td>
                              <td className="px-3 py-1.5 text-right tabular-nums text-muted-foreground">{fmtPct(r.pct_of_count)}%</td>
                            </tr>
                          )
                        })}
                      </tbody>
                      <tfoot className="bg-muted/20 border-t">
                        <tr>
                          <td className="px-3 py-2 text-xs font-semibold">Total service</td>
                          <td className="px-3 py-2 text-right text-xs font-bold tabular-nums">${fmt(data.total_service_sales)}</td>
                          <td className="px-3 py-2 text-right text-xs font-bold tabular-nums">${fmt(data.total_service_fees)}</td>
                          <td className="px-3 py-2 text-right text-xs font-bold tabular-nums">${fmt(data.total_net_service_sales)}</td>
                          <td className="px-3 py-2 text-right text-xs font-bold tabular-nums">{data.total_service_count}</td>
                          <td className="px-3 py-2 text-right text-xs tabular-nums text-muted-foreground">${fmt(data.average_service_price)}</td>
                          <td colSpan={2}></td>
                        </tr>
                      </tfoot>
                    </table>
                  </div>

                  {/* Retail row */}
                  <div className="bg-white border rounded-lg p-4">
                    <h2 className="text-sm font-medium mb-2">Retail</h2>
                    <div className="grid grid-cols-3 gap-4 text-sm">
                      <div>
                        <p className="text-xs text-muted-foreground">Total retail sales</p>
                        <p className="text-base font-semibold tabular-nums">${fmt(data.total_retail_sales)}</p>
                      </div>
                      <div>
                        <p className="text-xs text-muted-foreground"># Sales</p>
                        <p className="text-base font-semibold tabular-nums">{data.total_retail_count}</p>
                      </div>
                      <div>
                        <p className="text-xs text-muted-foreground">Avg price</p>
                        <p className="text-base font-semibold tabular-nums">${fmt(data.average_retail_price)}</p>
                      </div>
                    </div>
                  </div>
                </div>

                {/* Right: ratios + receipts */}
                <div className="space-y-4">
                  <div className="bg-white border rounded-lg p-4">
                    <h2 className="text-sm font-medium mb-3">Totals</h2>
                    <div className="space-y-0 text-sm">
                      <SummaryRow label="Total service (gross)" value={`$${fmt(data.total_service_sales)}`} />
                      <SummaryRow label="− Product fees" value={`$${fmt(data.total_service_fees)}`} indent />
                      <SummaryRow label="Total service (net)" value={`$${fmt(data.total_net_service_sales)}`} bold />
                      <SummaryRow label="Total retail" value={`$${fmt(data.total_retail_sales)}`} />
                      <SummaryRow label="Total sales (gross)" value={`$${fmt(data.total_sales)}`} bold />
                    </div>
                  </div>

                  <div className="bg-white border rounded-lg p-4">
                    <h2 className="text-sm font-medium mb-3">Ratios</h2>
                    <div className="space-y-0 text-sm">
                      <SummaryRow label="% Service of total" value={`${fmtPct(data.pct_service_of_total)}%`} />
                      <SummaryRow label="% Retail of total" value={`${fmtPct(data.pct_retail_of_total)}%`} />
                      <SummaryRow label="% Retail of service" value={`${fmtPct(data.pct_retail_of_service)}%`} />
                    </div>
                  </div>

                  <div className="bg-white border rounded-lg p-4">
                    <h2 className="text-sm font-medium mb-3">Receipt analysis</h2>
                    <div className="space-y-0 text-sm">
                      <SummaryRow label="# Receipts" value={String(data.receipt_count)} />
                      <SummaryRow label="# Clients serviced" value={String(data.clients_serviced)} />
                      <SummaryRow label="Avg / receipt" value={`$${fmt(data.avg_per_receipt)}`} />
                      <SummaryRow label="Items / receipt" value={fmt(data.items_per_receipt)} />
                    </div>
                  </div>

                  <div className="bg-muted/30 rounded-lg p-4 text-xs text-muted-foreground space-y-1">
                    <p><span className="font-medium">Provider:</span> {data.provider_name}</p>
                    <p><span className="font-medium">Period:</span> {data.period_start} → {data.period_end}</p>
                  </div>
                </div>
              </div>
            )}
          </>
        )}
      </div>
    </div>
  )
}
