import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { listSales } from '@/api/sales'
import SaleSummary from '@/components/appointment-book/SaleSummary'
import { useAuth } from '@/store/auth'

function today() {
  return new Date().toISOString().slice(0, 10)
}

function thirtyDaysAgo() {
  const d = new Date()
  d.setDate(d.getDate() - 30)
  return d.toISOString().slice(0, 10)
}

function fmt(s: string) {
  const n = parseFloat(s)
  return Number.isFinite(n) ? n.toFixed(2) : '0.00'
}

export default function SalesPage() {
  const { user } = useAuth()
  const isAdmin = user?.role === 'tenant_admin' || user?.role === 'super_admin'

  const [dateFrom, setDateFrom] = useState(thirtyDaysAgo())
  const [dateTo, setDateTo]     = useState(today())
  const [search, setSearch]     = useState('')
  const [submitted, setSubmitted] = useState({ dateFrom: thirtyDaysAgo(), dateTo: today(), search: '' })
  const [expandedId, setExpandedId] = useState<string | null>(null)

  const { data: sales = [], isLoading } = useQuery({
    queryKey: ['sales-list', submitted.dateFrom, submitted.dateTo, submitted.search],
    queryFn: () => listSales({
      date_from: submitted.dateFrom,
      date_to: submitted.dateTo,
      client_search: submitted.search || undefined,
    }),
  })

  function handleSearch(e: React.FormEvent) {
    e.preventDefault()
    setSubmitted({ dateFrom, dateTo, search })
    setExpandedId(null)
  }

  if (!isAdmin) {
    return (
      <div className="p-6 max-w-5xl mx-auto">
        <p className="text-sm text-muted-foreground">Access restricted to admins.</p>
      </div>
    )
  }

  return (
    <div className="p-6 max-w-5xl mx-auto space-y-4">
      <h1 className="text-xl font-semibold">Sales</h1>

      <form onSubmit={handleSearch} className="flex flex-wrap gap-2 items-end">
        <div className="space-y-1">
          <label className="text-xs text-muted-foreground">From</label>
          <input type="date" value={dateFrom} onChange={e => setDateFrom(e.target.value)}
            className="border border-input rounded-md px-2 py-1.5 text-sm bg-background" />
        </div>
        <div className="space-y-1">
          <label className="text-xs text-muted-foreground">To</label>
          <input type="date" value={dateTo} onChange={e => setDateTo(e.target.value)}
            className="border border-input rounded-md px-2 py-1.5 text-sm bg-background" />
        </div>
        <div className="space-y-1">
          <label className="text-xs text-muted-foreground">Client</label>
          <input type="text" value={search} onChange={e => setSearch(e.target.value)}
            placeholder="Search by name…"
            className="border border-input rounded-md px-2 py-1.5 text-sm bg-background w-44" />
        </div>
        <button type="submit"
          className="px-3 py-1.5 text-sm bg-foreground text-background rounded-md hover:opacity-90">
          Search
        </button>
      </form>

      {isLoading && <p className="text-sm text-muted-foreground">Loading…</p>}

      {!isLoading && sales.length === 0 && (
        <p className="text-sm text-muted-foreground">No sales found for this range.</p>
      )}

      {sales.length > 0 && (
        <div className="rounded-md border divide-y text-sm">
          {sales.map(sale => {
            const expanded = expandedId === sale.id
            const date = sale.completed_at
              ? new Date(sale.completed_at).toLocaleDateString('en-CA')
              : '—'
            return (
              <div key={sale.id}>
                <button
                  onClick={() => setExpandedId(expanded ? null : sale.id)}
                  className="w-full flex items-center gap-4 px-4 py-2.5 hover:bg-muted/30 text-left"
                >
                  <span className="text-muted-foreground w-24 shrink-0 tabular-nums">{date}</span>
                  <span className="font-medium w-44 shrink-0 truncate">{sale.client_name}</span>
                  <span className="text-muted-foreground flex-1 truncate text-xs">
                    {sale.item_descriptions.join(' · ')}
                  </span>
                  <span className="text-xs text-muted-foreground shrink-0">
                    {sale.payment_labels.join(' / ')}
                  </span>
                  <span className="font-medium w-16 text-right shrink-0">${fmt(sale.total)}</span>
                  <span className="text-muted-foreground text-xs w-4 shrink-0">
                    {expanded ? '▲' : '▼'}
                  </span>
                </button>
                {expanded && (
                  <div className="px-4 pb-3">
                    <SaleSummary saleId={sale.id} isAdmin={isAdmin} />
                  </div>
                )}
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}
