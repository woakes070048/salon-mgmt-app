import { useRef, useState } from 'react'
import { AlertCircle, CheckCircle2, FileText, Trash2, Upload } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { Button } from '@/components/ui/button'
import { importLegacyData, previewZeroApptClients, deleteZeroApptClients, upsertHistoricalPayments, diagnoseSalesSummary, backfillSaleItemLinks, backfillSaleItemServiceIds, type ImportResult, type ZeroApptPreview, type DiagnoseSalesSummary, type BackfillSaleItemLinksResult, type BackfillSaleItemServiceIdsResult } from '@/api/admin'

const FILES = [
  { key: 'clients_csv',          labelKey: 'import.client_details',          hint: 'Client Details.txt',            required: true  },
  { key: 'all_bookings_csv',     labelKey: 'import.future_past_bookings',     hint: 'Future and Past Bookings.txt',  required: true  },
  { key: 'receipts_csv',         labelKey: 'import.receipt_transactions',     hint: 'Receipt Transactions.txt',      required: true  },
  { key: 'current_bookings_csv', labelKey: 'import.all_bookings',             hint: 'All Bookings.txt',              required: false },
  { key: 'on_account_csv',       labelKey: 'import.on_account',               hint: 'On Account Summary.txt',        required: false },
] as const

type FileKey = typeof FILES[number]['key']

const RESULT_KEY_MAP: Record<string, string> = {
  clients:          'import.result_clients',
  receipts:         'import.result_receipts',
  past_unreceipted: 'import.result_past_bookings',
  future_bookings:  'import.result_future_bookings',
  current_bookings: 'import.result_current_bookings',
  on_account:       'import.result_account_balances',
}

function ZeroApptCleanup() {
  const [preview, setPreview] = useState<ZeroApptPreview | null>(null)
  const [loading, setLoading] = useState(false)
  const [deleting, setDeleting] = useState(false)
  const [deleted, setDeleted] = useState<number | null>(null)
  const [error, setError] = useState<string | null>(null)

  async function handlePreview() {
    setLoading(true)
    setError(null)
    setDeleted(null)
    try {
      setPreview(await previewZeroApptClients())
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load preview')
    } finally {
      setLoading(false)
    }
  }

  async function handleDelete() {
    setDeleting(true)
    setError(null)
    try {
      const result = await deleteZeroApptClients()
      setDeleted(result.deleted)
      setPreview(null)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Delete failed')
    } finally {
      setDeleting(false)
    }
  }

  return (
    <div className="border rounded-lg p-5 bg-white space-y-4">
      <div>
        <h2 className="text-base font-medium">Remove clients with no appointments</h2>
        <p className="text-xs text-muted-foreground mt-0.5">
          Hard-deletes all active clients who have never had an appointment. Useful after a data import to clear out incomplete records.
        </p>
      </div>

      {deleted !== null && (
        <div className="flex items-center gap-2 text-sm text-green-700">
          <CheckCircle2 size={15} />
          {deleted === 0 ? 'No clients to remove.' : `${deleted} client${deleted !== 1 ? 's' : ''} removed.`}
        </div>
      )}

      {!preview && deleted === null && (
        <Button variant="outline" size="sm" onClick={handlePreview} disabled={loading}>
          {loading ? 'Scanning…' : 'Preview'}
        </Button>
      )}

      {preview && (
        <div className="space-y-3">
          {preview.count === 0 ? (
            <p className="text-sm text-muted-foreground">No clients with zero appointments found.</p>
          ) : (
            <>
              <p className="text-sm font-medium text-destructive">
                {preview.count} client{preview.count !== 1 ? 's' : ''} would be permanently deleted.
              </p>
              {preview.sample.length > 0 && (
                <ul className="text-xs text-muted-foreground space-y-0.5 pl-3 border-l-2">
                  {preview.sample.map(c => (
                    <li key={c.id}>
                      {c.last_name}, {c.first_name}
                      {c.email && <span className="ml-1.5 opacity-70">{c.email}</span>}
                    </li>
                  ))}
                  {preview.count > preview.sample.length && (
                    <li className="opacity-50">…and {preview.count - preview.sample.length} more</li>
                  )}
                </ul>
              )}
              <div className="flex gap-2">
                <Button
                  size="sm"
                  variant="destructive"
                  onClick={handleDelete}
                  disabled={deleting}
                  className="gap-1.5"
                >
                  <Trash2 size={13} />
                  {deleting ? 'Deleting…' : `Delete ${preview.count} client${preview.count !== 1 ? 's' : ''}`}
                </Button>
                <Button size="sm" variant="outline" onClick={() => setPreview(null)} disabled={deleting}>
                  Cancel
                </Button>
              </div>
            </>
          )}
        </div>
      )}

      {error && (
        <div className="flex items-center gap-2 text-sm text-destructive">
          <AlertCircle size={14} />
          {error}
        </div>
      )}
    </div>
  )
}

export default function DataImportPage() {
  const { t } = useTranslation()
  const [files, setFiles] = useState<Partial<Record<FileKey, File>>>({})
  const [loading, setLoading] = useState(false)
  const [result, setResult] = useState<ImportResult | null>(null)
  const [error, setError] = useState<string | null>(null)
  const inputRefs = useRef<Partial<Record<FileKey, HTMLInputElement | null>>>({})

  const canRun = FILES.filter(f => f.required).every(f => files[f.key])

  function handleFile(key: FileKey, file: File | null) {
    setFiles(prev => {
      const next = { ...prev }
      if (file) next[key] = file
      else delete next[key]
      return next
    })
    setResult(null)
  }

  async function handleRun() {
    setLoading(true)
    setResult(null)
    setError(null)
    try {
      const fd = new FormData()
      for (const [key, file] of Object.entries(files)) {
        if (file) fd.append(key, file)
      }
      setResult(await importLegacyData(fd))
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Unknown error')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="h-full overflow-auto p-6">
      <div className="max-w-xl mx-auto">
        <h1 className="text-xl font-semibold mb-1">{t('import.page_title')}</h1>
        <p className="text-sm text-muted-foreground mb-6">
          {t('import.page_subtitle')}
        </p>

        <div className="space-y-2 mb-6">
          {FILES.map(({ key, labelKey, hint, required }) => {
            const file = files[key]
            return (
              <div key={key} className="flex items-center gap-3 p-3 border rounded-lg bg-white">
                <FileText size={16} className="text-muted-foreground flex-shrink-0" />
                <div className="flex-1 min-w-0">
                  <div className="flex items-baseline gap-1.5">
                    <span className="text-sm font-medium">{t(labelKey)}</span>
                    {!required && (
                      <span className="text-xs text-muted-foreground">{t('import.optional_marker')}</span>
                    )}
                  </div>
                  <p className="text-xs text-muted-foreground truncate">
                    {file ? file.name : hint}
                  </p>
                </div>
                {file && <CheckCircle2 size={15} className="text-green-500 flex-shrink-0" />}
                <input
                  ref={el => { inputRefs.current[key] = el }}
                  type="file"
                  accept=".txt,.csv"
                  className="hidden"
                  onChange={e => handleFile(key, e.target.files?.[0] ?? null)}
                />
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => inputRefs.current[key]?.click()}
                >
                  {file ? t('import.change_button') : t('import.browse_button')}
                </Button>
              </div>
            )
          })}
        </div>

        <Button
          onClick={handleRun}
          disabled={!canRun || loading}
          className="w-full gap-2"
        >
          <Upload size={15} />
          {loading ? t('import.importing') : t('import.run_import')}
        </Button>

        {error && (
          <div className="mt-4 flex items-start gap-2 text-destructive text-sm">
            <AlertCircle size={15} className="flex-shrink-0 mt-0.5" />
            <span>{error}</span>
          </div>
        )}

        {result && <ImportResults result={result} />}

        <div className="mt-8 pt-6 border-t">
          <ZeroApptCleanup />
        </div>

        <div className="mt-8 pt-6 border-t">
          <HistoricalPayments />
        </div>

        <div className="mt-8 pt-6 border-t">
          <DiagnoseSales />
        </div>
      </div>
    </div>
  )
}

function DiagnoseSales() {
  const [start, setStart] = useState('2026-05-07')
  const [end, setEnd] = useState('2026-05-13')
  const [data, setData] = useState<DiagnoseSalesSummary | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [backfilling, setBackfilling] = useState(false)
  const [backfillResult, setBackfillResult] = useState<BackfillSaleItemLinksResult | null>(null)
  const [svcBackfilling, setSvcBackfilling] = useState(false)
  const [svcBackfillResult, setSvcBackfillResult] = useState<BackfillSaleItemServiceIdsResult | null>(null)

  async function run() {
    setLoading(true); setError(null); setData(null)
    try {
      setData(await diagnoseSalesSummary(start, end))
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed')
    } finally {
      setLoading(false)
    }
  }

  async function runBackfill() {
    if (!confirm('Link orphaned service sale_items to appointment_items across the whole tenant? This rewrites sale_items.appointment_item_id for matched rows.')) return
    setBackfilling(true); setError(null); setBackfillResult(null)
    try {
      const r = await backfillSaleItemLinks()
      setBackfillResult(r)
      // Refresh the current diagnose view so the user sees the effect.
      if (data) setData(await diagnoseSalesSummary(start, end))
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Backfill failed')
    } finally {
      setBackfilling(false)
    }
  }

  async function runSvcBackfill() {
    if (!confirm('Re-resolve sale_items.service_id from description for items where it is NULL. Use this after adding a missing service to the catalog so historical reports pick it up.')) return
    setSvcBackfilling(true); setError(null); setSvcBackfillResult(null)
    try {
      setSvcBackfillResult(await backfillSaleItemServiceIds())
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Service-id backfill failed')
    } finally {
      setSvcBackfilling(false)
    }
  }

  return (
    <div>
      <h2 className="text-sm font-semibold mb-1">Diagnose missing sales</h2>
      <p className="text-xs text-muted-foreground mb-3">
        Shows what sale_items are actually in the DB for a date range, grouped by provider.
        Use this to figure out why a provider's payroll report is missing transactions.
      </p>
      <div className="flex items-end gap-2 mb-3">
        <div>
          <label className="text-xs text-muted-foreground">Start</label>
          <input type="date" value={start} onChange={e => setStart(e.target.value)}
            className="block border rounded px-2 py-1 text-sm" />
        </div>
        <div>
          <label className="text-xs text-muted-foreground">End</label>
          <input type="date" value={end} onChange={e => setEnd(e.target.value)}
            className="block border rounded px-2 py-1 text-sm" />
        </div>
        <Button onClick={run} disabled={loading} size="sm">
          {loading ? 'Running…' : 'Diagnose'}
        </Button>
        <Button onClick={runBackfill} disabled={backfilling} size="sm" variant="outline">
          {backfilling ? 'Linking…' : 'Backfill appt links'}
        </Button>
        <Button onClick={runSvcBackfill} disabled={svcBackfilling} size="sm" variant="outline">
          {svcBackfilling ? 'Linking…' : 'Backfill service IDs'}
        </Button>
      </div>

      {error && <p className="text-sm text-destructive">{error}</p>}

      {backfillResult && (
        <p className="text-sm mb-3">
          Backfill (appt links): found {backfillResult.orphans_found}, linked {backfillResult.linked}, unmatched {backfillResult.unmatched}.
        </p>
      )}

      {svcBackfillResult && (
        <div className="text-sm mb-3 space-y-1">
          <p>
            Backfill (service IDs): found {svcBackfillResult.orphans_found}, linked {svcBackfillResult.linked}.
          </p>
          {svcBackfillResult.unmapped_descriptions.length > 0 && (
            <details className="text-xs">
              <summary className="cursor-pointer text-amber-700">
                {svcBackfillResult.unmapped_descriptions.length} unknown description(s) — not in RECEIPT_SERVICE_MAP
              </summary>
              <ul className="ml-4 mt-1 list-disc">
                {svcBackfillResult.unmapped_descriptions.map((d, i) => (
                  <li key={i}><code>{d.description}</code> ({d.count})</li>
                ))}
              </ul>
            </details>
          )}
          {svcBackfillResult.missing_service_codes.length > 0 && (
            <details className="text-xs">
              <summary className="cursor-pointer text-amber-700">
                {svcBackfillResult.missing_service_codes.length} service code(s) missing from catalog — add the service then re-run
              </summary>
              <ul className="ml-4 mt-1 list-disc">
                {svcBackfillResult.missing_service_codes.map((c, i) => (
                  <li key={i}><code>{c.service_code}</code> ({c.count})</li>
                ))}
              </ul>
            </details>
          )}
        </div>
      )}

      {data && (
        <div className="space-y-4">
          {data.items.length === 0 ? (
            <p className="text-sm text-destructive font-medium">
              No sale_items in DB for {data.range.start} → {data.range.end}.
              The data was never imported.
            </p>
          ) : (
            <div className="border rounded-lg overflow-hidden bg-white">
              <table className="w-full text-xs">
                <thead className="bg-muted/30 border-b">
                  <tr>
                    <th className="text-left px-2 py-1.5">Day</th>
                    <th className="text-left px-2 py-1.5">Provider</th>
                    <th className="text-left px-2 py-1.5">Kind</th>
                    <th className="text-right px-2 py-1.5">Items</th>
                    <th className="text-center px-2 py-1.5">Appt link missing?</th>
                  </tr>
                </thead>
                <tbody>
                  {data.items.map((r, i) => (
                    <tr key={i} className={`border-b last:border-0 ${r.appt_item_id_is_null ? 'bg-amber-50' : ''}`}>
                      <td className="px-2 py-1 tabular-nums">{r.day}</td>
                      <td className="px-2 py-1">{r.provider}</td>
                      <td className="px-2 py-1 text-muted-foreground">{r.kind}</td>
                      <td className="px-2 py-1 text-right tabular-nums">{r.items}</td>
                      <td className="px-2 py-1 text-center">{r.appt_item_id_is_null ? '⚠️ YES' : ''}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}

          <details className="text-xs">
            <summary className="cursor-pointer text-muted-foreground">All current providers ({data.providers.length})</summary>
            <ul className="mt-2 space-y-0.5">
              {data.providers.map(p => (
                <li key={p.id} className="font-mono">{p.display_name}</li>
              ))}
            </ul>
          </details>
        </div>
      )}
    </div>
  )
}

function ImportResults({ result }: { result: ImportResult }) {
  const { t } = useTranslation()
  const entries = Object.entries(result).filter(([k]) => k !== 'error')

  return (
    <div className="mt-6">
      <h2 className="text-sm font-semibold mb-3">{t('import.results_section')}</h2>

      {result.error && (
        <div className="mb-3 text-sm text-destructive bg-destructive/10 rounded-lg p-3">
          <pre className="whitespace-pre-wrap font-mono text-xs">{result.error}</pre>
        </div>
      )}

      <div className="space-y-2">
        {entries.map(([key, data]) => (
          <div key={key} className="border rounded-lg p-3 bg-white">
            <div className="text-sm font-medium mb-1.5">
              {RESULT_KEY_MAP[key] ? t(RESULT_KEY_MAP[key]) : key}
            </div>
            <div className="flex flex-wrap gap-x-4 gap-y-1">
              {Object.entries(data as Record<string, unknown>).map(([k, v]) => (
                Array.isArray(v) ? (
                  v.length > 0 && (
                    <span key={k} className="text-xs text-muted-foreground w-full">
                      {k.replace(/_/g, ' ')}:{' '}
                      <span className="text-foreground font-medium">{v.join(', ')}</span>
                    </span>
                  )
                ) : (
                  <span key={k} className="text-xs text-muted-foreground">
                    {k.replace(/_/g, ' ')}:{' '}
                    <span className="text-foreground font-medium">{String(v)}</span>
                  </span>
                )
              ))}
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}

const MONTHS = [
  'January','February','March','April','May','June',
  'July','August','September','October','November','December',
]

const DEFAULT_LABELS = ['VISA','MASTERCARD','AMEX','DEBIT','CASH','E-TRANSFER']

function HistoricalPayments() {
  const now = new Date()
  const [year, setYear] = useState(now.getFullYear())
  const [month, setMonth] = useState(now.getMonth() + 1)
  const [rows, setRows] = useState<{ label: string; amount: string }[]>(
    DEFAULT_LABELS.map(l => ({ label: l, amount: '' }))
  )
  const [saving, setSaving] = useState(false)
  const [saved, setSaved] = useState(false)
  const [error, setError] = useState<string | null>(null)

  function updateRow(idx: number, field: 'label' | 'amount', val: string) {
    setRows(prev => prev.map((r, i) => i === idx ? { ...r, [field]: val } : r))
    setSaved(false)
  }

  function addRow() {
    setRows(prev => [...prev, { label: '', amount: '' }])
  }

  function removeRow(idx: number) {
    setRows(prev => prev.filter((_, i) => i !== idx))
  }

  async function handleSave() {
    setSaving(true)
    setError(null)
    setSaved(false)
    try {
      const validRows = rows
        .filter(r => r.label.trim() && r.amount.trim())
        .map(r => ({ label: r.label.trim().toUpperCase(), amount: parseFloat(r.amount) }))
        .filter(r => Number.isFinite(r.amount))
      if (!validRows.length) throw new Error('No valid rows to save')
      await upsertHistoricalPayments({ year, month, rows: validRows, source: 'milano' })
      setSaved(true)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Save failed')
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="space-y-4">
      <div>
        <h2 className="text-sm font-semibold">Historical Payment Breakdown</h2>
        <p className="text-xs text-muted-foreground mt-0.5">
          Enter monthly payment type totals from Milano Daily Sales Reports. These populate
          the Payment Reconciliation section of the sales report for historical months.
        </p>
      </div>

      <div className="flex gap-3">
        <select
          value={year}
          onChange={e => { setYear(Number(e.target.value)); setSaved(false) }}
          className="border rounded-md px-2 py-1.5 text-sm bg-white"
        >
          {[2025, 2026, 2027].map(y => <option key={y} value={y}>{y}</option>)}
        </select>
        <select
          value={month}
          onChange={e => { setMonth(Number(e.target.value)); setSaved(false) }}
          className="border rounded-md px-2 py-1.5 text-sm bg-white"
        >
          {MONTHS.map((m, i) => <option key={i + 1} value={i + 1}>{m}</option>)}
        </select>
      </div>

      <div className="space-y-2">
        {rows.map((row, idx) => (
          <div key={idx} className="flex gap-2 items-center">
            <input
              value={row.label}
              onChange={e => updateRow(idx, 'label', e.target.value)}
              placeholder="Payment type"
              className="border rounded-md px-2 py-1.5 text-sm w-36 bg-white"
            />
            <span className="text-muted-foreground text-sm">$</span>
            <input
              value={row.amount}
              onChange={e => updateRow(idx, 'amount', e.target.value)}
              placeholder="0.00"
              type="number"
              step="0.01"
              className="border rounded-md px-2 py-1.5 text-sm w-32 bg-white tabular-nums"
            />
            <button
              onClick={() => removeRow(idx)}
              className="text-muted-foreground hover:text-destructive text-xs px-1"
            >
              ×
            </button>
          </div>
        ))}
        <button
          onClick={addRow}
          className="text-xs text-muted-foreground hover:text-foreground underline-offset-2 hover:underline"
        >
          + Add row
        </button>
      </div>

      <div className="flex items-center gap-3">
        <Button size="sm" onClick={handleSave} disabled={saving}>
          {saving ? 'Saving…' : `Save ${MONTHS[month - 1]} ${year}`}
        </Button>
        {saved && <span className="text-xs text-green-600">Saved — refresh the sales report to see it.</span>}
        {error && <span className="text-xs text-destructive">{error}</span>}
      </div>
    </div>
  )
}
