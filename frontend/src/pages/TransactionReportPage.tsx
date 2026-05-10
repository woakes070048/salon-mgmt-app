import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { format, subMonths, startOfMonth, endOfMonth } from 'date-fns'
import { Download } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { getTransactionReport, type TransactionLineItem } from '@/api/reports'

function fmt(s: string | number | null | undefined): string {
  if (s == null) return ''
  const n = typeof s === 'number' ? s : parseFloat(s)
  return Number.isFinite(n) ? n.toFixed(2) : '0.00'
}

function downloadCsv(items: TransactionLineItem[], start: string, end: string) {
  const headers = [
    'Date', 'Receipt', 'Client', 'Provider', 'Type', 'Description',
    'Qty', 'Unit Price', 'Discount', 'Line Total', 'GST', 'PST', 'Sale Total',
  ]
  const rows = items.map(r => [
    r.sale_date,
    r.sale_id,
    r.client_name,
    r.provider_name ?? '',
    r.kind === 'service' ? 'Service' : 'Retail',
    r.description,
    r.quantity,
    fmt(r.unit_price),
    fmt(r.discount),
    fmt(r.line_total),
    r.gst != null ? fmt(r.gst) : '',
    r.pst != null ? fmt(r.pst) : '',
    r.sale_total != null ? fmt(r.sale_total) : '',
  ])
  const csv = [headers, ...rows]
    .map(row => row.map(v => `"${String(v).replace(/"/g, '""')}"`).join(','))
    .join('\n')
  const blob = new Blob([csv], { type: 'text/csv' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `transactions-${start}-${end}.csv`
  a.click()
  URL.revokeObjectURL(url)
}

export default function TransactionReportPage() {
  const now = new Date()
  const [start, setStart] = useState(format(startOfMonth(subMonths(now, 0)), 'yyyy-MM-dd'))
  const [end, setEnd] = useState(format(endOfMonth(subMonths(now, 0)), 'yyyy-MM-dd'))
  const [query, setQuery] = useState({ start, end })

  const { data, isLoading, isError } = useQuery({
    queryKey: ['transaction-report', query.start, query.end],
    queryFn: () => getTransactionReport(query.start, query.end),
    enabled: !!query.start && !!query.end,
  })

  // Group items by sale_id for visual separation
  const sales: TransactionLineItem[][] = []
  let currentSale: TransactionLineItem[] = []
  for (const item of data?.items ?? []) {
    if (currentSale.length && currentSale[0].sale_id !== item.sale_id) {
      sales.push(currentSale)
      currentSale = []
    }
    currentSale.push(item)
  }
  if (currentSale.length) sales.push(currentSale)

  return (
    <div className="h-full overflow-auto bg-muted/30">
      <div className="max-w-7xl mx-auto px-6 py-8 space-y-6">

        <div className="flex items-center justify-between flex-wrap gap-4">
          <h1 className="text-xl font-semibold">Transaction Report</h1>
          <div className="flex items-center gap-3 flex-wrap">
            <div className="flex items-center gap-2 text-sm">
              <label className="text-muted-foreground">From</label>
              <input
                type="date"
                value={start}
                onChange={e => setStart(e.target.value)}
                className="border rounded-md px-2 py-1.5 text-sm bg-white"
              />
              <label className="text-muted-foreground">To</label>
              <input
                type="date"
                value={end}
                onChange={e => setEnd(e.target.value)}
                className="border rounded-md px-2 py-1.5 text-sm bg-white"
              />
            </div>
            <Button onClick={() => setQuery({ start, end })} size="sm">
              Run
            </Button>
            {data && data.items.length > 0 && (
              <Button
                variant="outline"
                size="sm"
                onClick={() => downloadCsv(data.items, query.start, query.end)}
                className="gap-1.5"
              >
                <Download size={14} />
                Export CSV
              </Button>
            )}
          </div>
        </div>

        {isLoading && (
          <div className="text-sm text-muted-foreground py-8 text-center">Loading transactions…</div>
        )}

        {isError && (
          <div className="text-sm text-destructive py-4">Failed to load transactions.</div>
        )}

        {data && (
          <>
            <div className="text-xs text-muted-foreground">
              {data.items.length} line items across {sales.length} sales
              · Grand total: <span className="font-semibold text-foreground">${fmt(data.grand_total)}</span>
            </div>

            <div className="bg-white border rounded-lg overflow-hidden">
              <table className="w-full text-xs">
                <thead className="bg-muted/30 border-b sticky top-0">
                  <tr>
                    <th className="text-left px-3 py-2 font-medium text-muted-foreground">Date</th>
                    <th className="text-left px-3 py-2 font-medium text-muted-foreground">Receipt</th>
                    <th className="text-left px-3 py-2 font-medium text-muted-foreground">Client</th>
                    <th className="text-left px-3 py-2 font-medium text-muted-foreground">Provider</th>
                    <th className="text-left px-3 py-2 font-medium text-muted-foreground">Type</th>
                    <th className="text-left px-3 py-2 font-medium text-muted-foreground">Description</th>
                    <th className="text-right px-3 py-2 font-medium text-muted-foreground">Qty</th>
                    <th className="text-right px-3 py-2 font-medium text-muted-foreground">Unit</th>
                    <th className="text-right px-3 py-2 font-medium text-muted-foreground">Disc</th>
                    <th className="text-right px-3 py-2 font-medium text-muted-foreground">Total</th>
                    <th className="text-right px-3 py-2 font-medium text-muted-foreground">GST</th>
                    <th className="text-right px-3 py-2 font-medium text-muted-foreground">PST</th>
                    <th className="text-right px-3 py-2 font-medium text-muted-foreground">Sale</th>
                  </tr>
                </thead>
                <tbody>
                  {sales.map((saleItems, si) => (
                    saleItems.map((item, ii) => (
                      <tr
                        key={`${item.sale_id}-${ii}`}
                        className={[
                          'border-b',
                          si % 2 === 0 ? 'bg-white' : 'bg-muted/10',
                          item.sale_total != null ? 'border-b-2 border-b-muted/40' : '',
                        ].join(' ')}
                      >
                        <td className="px-3 py-1.5 tabular-nums">{item.sale_date}</td>
                        <td className="px-3 py-1.5 font-mono text-muted-foreground">{item.sale_id}</td>
                        <td className="px-3 py-1.5">{item.client_name}</td>
                        <td className="px-3 py-1.5 text-muted-foreground">{item.provider_name ?? ''}</td>
                        <td className="px-3 py-1.5">
                          <span className={`px-1.5 py-0.5 rounded text-[10px] font-medium ${
                            item.kind === 'service'
                              ? 'bg-blue-50 text-blue-700'
                              : 'bg-amber-50 text-amber-700'
                          }`}>
                            {item.kind === 'service' ? 'Svc' : 'Rtl'}
                          </span>
                        </td>
                        <td className="px-3 py-1.5 max-w-[200px] truncate">{item.description}</td>
                        <td className="px-3 py-1.5 text-right tabular-nums">{item.quantity}</td>
                        <td className="px-3 py-1.5 text-right tabular-nums">${fmt(item.unit_price)}</td>
                        <td className="px-3 py-1.5 text-right tabular-nums text-muted-foreground">
                          {parseFloat(item.discount) > 0 ? `-$${fmt(item.discount)}` : ''}
                        </td>
                        <td className="px-3 py-1.5 text-right tabular-nums font-medium">${fmt(item.line_total)}</td>
                        <td className="px-3 py-1.5 text-right tabular-nums text-muted-foreground">
                          {item.gst != null ? `$${fmt(item.gst)}` : ''}
                        </td>
                        <td className="px-3 py-1.5 text-right tabular-nums text-muted-foreground">
                          {item.pst != null ? `$${fmt(item.pst)}` : ''}
                        </td>
                        <td className="px-3 py-1.5 text-right tabular-nums font-semibold">
                          {item.sale_total != null ? `$${fmt(item.sale_total)}` : ''}
                        </td>
                      </tr>
                    ))
                  ))}
                </tbody>
                <tfoot className="bg-muted/20 border-t-2">
                  <tr>
                    <td colSpan={9} className="px-3 py-2 text-xs font-semibold text-right">Grand Total</td>
                    <td className="px-3 py-2 text-right text-xs font-bold tabular-nums">${fmt(data.grand_total)}</td>
                    <td colSpan={3} />
                  </tr>
                </tfoot>
              </table>
            </div>
          </>
        )}
      </div>
    </div>
  )
}
