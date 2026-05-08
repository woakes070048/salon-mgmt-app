import { useState, useEffect, useRef } from 'react'
import { useMutation, useQuery } from '@tanstack/react-query'
import { format, addDays } from 'date-fns'
import { Send, Printer, ClipboardCopy, RefreshCw } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { getPayrollReport, sendPayrollEmail, type ProviderPayrollLine } from '@/api/providers'
import { getPayrollConfig } from '@/api/admin'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'

// ── Date helpers ──────────────────────────────────────────────────────────────

function defaultPeriod() {
  const now = new Date()
  // period_end = 15th of current month; period_start = 16th of previous month
  const periodEnd = new Date(now.getFullYear(), now.getMonth(), 15)
  const periodStart = new Date(now.getFullYear(), now.getMonth() - 1, 16)
  return {
    start: format(periodStart, 'yyyy-MM-dd'),
    end: format(periodEnd, 'yyyy-MM-dd'),
  }
}

function defaultPaymentDate(periodEnd: string) {
  return format(addDays(new Date(periodEnd + 'T12:00:00'), 5), 'yyyy-MM-dd')
}

function longDate(iso: string) {
  return format(new Date(iso + 'T12:00:00'), 'MMMM do yyyy')
}

function fmtCad(n: number) {
  return n.toLocaleString('en-CA', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

// ── Pay line generation ───────────────────────────────────────────────────────

interface EditableLine {
  provider_id: string
  first_name: string
  last_name: string
  is_owner: boolean
  pay_basis: string
  scheduled_hours: number
  hourly_minimum: number | null
  service_commission: number
  retail_commission: number
  vacation_pct: number
  gross_pay: number
}

function generatePayLine(line: EditableLine): string {
  const name = `${line.first_name} ${line.last_name}`

  if (line.is_owner) {
    if (line.pay_basis === 'salary') {
      return `${name}\nSalary = $${fmtCad(line.gross_pay)} (No Stat holidays and no Vacation pay)`
    }
    return `${name}\nService Commission = $${fmtCad(line.service_commission)} (No Stat holidays and no Vacation pay)`
  }

  if (line.pay_basis === 'n/a') return ''

  let base = ''
  if (line.pay_basis === 'salary') {
    base = `Salary $${fmtCad(line.gross_pay)}`
  } else if (line.pay_basis === 'hourly' && line.hourly_minimum) {
    const total = Math.round(line.scheduled_hours * line.hourly_minimum * 100) / 100
    base = `${Math.round(line.scheduled_hours)} hours @$${fmtCad(line.hourly_minimum)} = $${fmtCad(total)}`
  } else {
    base = `Service Commission $${fmtCad(line.service_commission)}`
  }

  const retail = line.retail_commission > 0 ? ` + Retail Commission $${fmtCad(line.retail_commission)}` : ''
  const vac = line.vacation_pct > 0 ? ` + ${line.vacation_pct}% vacation pay` : ''

  return `${name}\n${base}${retail}${vac}`
}

function buildEmailBody(opts: {
  paymentDate: string
  periodStart: string
  periodEnd: string
  notes: string
  owners: EditableLine[]
  staff: EditableLine[]
  signature: string
  footer: string
}): string {
  const { paymentDate, periodStart, periodEnd, notes, owners, staff, signature, footer } = opts
  const pmtFormatted = format(new Date(paymentDate + 'T12:00:00'), 'MMMM do yyyy')

  const lines: string[] = []
  lines.push('Team1,')
  lines.push('')
  lines.push(
    `This is the ${pmtFormatted} payroll for the pay period from ${longDate(periodStart)} to ${longDate(periodEnd)}.`
  )
  if (notes.trim()) {
    lines.push(notes.trim())
  }

  if (owners.length) {
    lines.push('')
    lines.push('@Owner')
    owners.forEach(o => lines.push(generatePayLine(o)))
  }

  if (staff.length) {
    lines.push('')
    lines.push('@STAFF')
    let firstStaffWritten = false
    staff.forEach(s => {
      const line = generatePayLine(s)
      if (!line) return
      if (firstStaffWritten) lines.push('')
      lines.push(line)
      firstStaffWritten = true
    })
  }

  lines.push('')
  lines.push(`Thank you,\n${signature}`)

  if (footer.trim()) {
    lines.push('')
    lines.push('--')
    lines.push(footer.trim())
  }

  return lines.join('\n')
}

// ── Review table ──────────────────────────────────────────────────────────────

function ReviewTable({
  editable,
  onChange,
}: {
  editable: EditableLine[]
  onChange: (id: string, patch: Partial<EditableLine>) => void
}) {
  const { t } = useTranslation()
  return (
    <div className="overflow-auto border rounded-lg">
      <table className="w-full text-sm">
        <thead className="bg-muted/30 border-b">
          <tr>
            <th className="text-left px-4 py-2 font-medium text-xs text-muted-foreground">{t('reports.col_name')}</th>
            <th className="text-left px-4 py-2 font-medium text-xs text-muted-foreground">{t('reports.col_basis')}</th>
            <th className="text-right px-4 py-2 font-medium text-xs text-muted-foreground">{t('reports.col_hours')}</th>
            <th className="text-right px-4 py-2 font-medium text-xs text-muted-foreground">{t('reports.col_svc_commission')}</th>
            <th className="text-right px-4 py-2 font-medium text-xs text-muted-foreground">{t('reports.col_retail_commission')}</th>
            <th className="text-right px-4 py-2 font-medium text-xs text-muted-foreground">{t('reports.col_vac')}</th>
            <th className="text-right px-4 py-2 font-medium text-xs text-muted-foreground">{t('reports.col_gross_pay')}</th>
          </tr>
        </thead>
        <tbody>
          {editable.map((el) => {
            const gross = el.is_owner
              ? el.service_commission
              : el.pay_basis === 'hourly' && el.hourly_minimum
              ? el.scheduled_hours * el.hourly_minimum + el.retail_commission
              : el.service_commission + el.retail_commission

            return (
              <tr key={el.provider_id} className="border-b last:border-0 hover:bg-muted/20">
                <td className="px-4 py-2">
                  <span className="font-medium">{el.first_name} {el.last_name}</span>
                  {el.is_owner && (
                    <span className="ml-2 text-[10px] bg-amber-100 text-amber-700 px-1.5 py-0.5 rounded">{t('reports.col_owner')}</span>
                  )}
                </td>
                <td className="px-4 py-2 text-muted-foreground capitalize text-xs">{el.pay_basis}</td>
                <td className="px-4 py-2 text-right">
                  <Input
                    type="number"
                    step="0.5"
                    value={el.scheduled_hours}
                    onChange={e => onChange(el.provider_id, { scheduled_hours: parseFloat(e.target.value) || 0 })}
                    className="w-20 h-7 text-xs text-right ml-auto"
                  />
                </td>
                <td className="px-4 py-2 text-right">
                  <Input
                    type="number"
                    step="0.01"
                    value={el.service_commission}
                    onChange={e => onChange(el.provider_id, { service_commission: parseFloat(e.target.value) || 0 })}
                    className="w-28 h-7 text-xs text-right ml-auto"
                  />
                </td>
                <td className="px-4 py-2 text-right">
                  <Input
                    type="number"
                    step="0.01"
                    value={el.retail_commission}
                    onChange={e => onChange(el.provider_id, { retail_commission: parseFloat(e.target.value) || 0 })}
                    className="w-24 h-7 text-xs text-right ml-auto"
                  />
                </td>
                <td className="px-4 py-2 text-right">
                  {el.is_owner ? (
                    <span className="text-xs text-muted-foreground">—</span>
                  ) : (
                    <Input
                      type="number"
                      step="1"
                      value={el.vacation_pct}
                      onChange={e => onChange(el.provider_id, { vacation_pct: parseFloat(e.target.value) || 0 })}
                      className="w-16 h-7 text-xs text-right ml-auto"
                    />
                  )}
                </td>
                <td className="px-4 py-2 text-right font-medium">
                  ${fmtCad(gross)}
                </td>
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}

// ── Main page ─────────────────────────────────────────────────────────────────

export default function PayrollReportPage() {
  const { t } = useTranslation()
  const defaults = defaultPeriod()
  const [periodStart, setPeriodStart] = useState(defaults.start)
  const [periodEnd, setPeriodEnd] = useState(defaults.end)
  const [paymentDate, setPaymentDate] = useState(() => defaultPaymentDate(defaults.end))
  const [notes, setNotes] = useState('')
  const [clientId, setClientId] = useState('')
  const [toEmail, setToEmail] = useState('')
  const [signature, setSignature] = useState('')
  const [footer, setFooter] = useState('')
  const [settingsLoaded, setSettingsLoaded] = useState(false)

  const { data: payrollCfg } = useQuery({ queryKey: ['payroll-config'], queryFn: getPayrollConfig })

  useEffect(() => {
    if (!settingsLoaded && payrollCfg) {
      if (payrollCfg.provider_email) setToEmail(payrollCfg.provider_email)
      if (payrollCfg.client_id) setClientId(payrollCfg.client_id)
      if (payrollCfg.signature) setSignature(payrollCfg.signature)
      if (payrollCfg.footer) setFooter(payrollCfg.footer)
      setSettingsLoaded(true)
    }
  }, [payrollCfg, settingsLoaded])
  const [editableLines, setEditableLines] = useState<EditableLine[]>([])
  const [emailText, setEmailText] = useState('')
  const [copied, setCopied] = useState(false)
  const emailRef = useRef<HTMLTextAreaElement>(null)

  const { data, isLoading, refetch } = useQuery({
    queryKey: ['payroll-report', periodStart, periodEnd],
    queryFn: () => getPayrollReport(periodStart, periodEnd),
    enabled: false,
  })

  function toEditable(l: ProviderPayrollLine): EditableLine {
    return {
      provider_id: l.provider_id,
      first_name: l.first_name,
      last_name: l.last_name,
      is_owner: l.is_owner,
      pay_basis: l.pay_basis,
      scheduled_hours: l.scheduled_hours,
      hourly_minimum: l.hourly_minimum,
      // For salary employees, surface gross_pay as the editable commission field
      service_commission: l.pay_basis === 'salary' ? l.gross_pay : l.service_commission,
      retail_commission: l.retail_commission,
      vacation_pct: l.vacation_pct,
      gross_pay: l.gross_pay,
    }
  }

  useEffect(() => {
    if (data) {
      const els = [...data.lines].sort((a, b) => {
        if (a.is_owner !== b.is_owner) return a.is_owner ? -1 : 1
        return a.booking_order - b.booking_order
      }).map(toEditable)
      setEditableLines(els)
    }
  }, [data])

  useEffect(() => {
    if (editableLines.length === 0) return
    const owners = editableLines.filter(l => l.is_owner)
    const staff = editableLines.filter(l => !l.is_owner)
    setEmailText(buildEmailBody({ paymentDate, periodStart, periodEnd, notes, owners, staff, signature, footer }))
  }, [editableLines, paymentDate, periodStart, periodEnd, notes, signature, footer])

  function updateLine(id: string, patch: Partial<EditableLine>) {
    setEditableLines(prev => prev.map(l => l.provider_id === id ? { ...l, ...patch } : l))
  }

  function handleCalculate() {
    refetch()
  }

  const subject = `${clientId} : ${format(new Date(paymentDate + 'T12:00:00'), 'MMMM do yyyy')} Payroll`

  const sendMutation = useMutation({
    mutationFn: () => sendPayrollEmail({ to_email: toEmail, subject, body_text: emailText }),
  })

  function handleCopy() {
    navigator.clipboard.writeText(emailText).then(() => {
      setCopied(true)
      setTimeout(() => setCopied(false), 2000)
    })
  }

  function handlePrint(target: 'review' | 'email') {
    document.body.dataset.printTarget = target
    window.print()
    delete document.body.dataset.printTarget
  }

  const owners = editableLines.filter(l => l.is_owner)
  const staff = editableLines.filter(l => !l.is_owner)

  return (
    <div className="min-h-screen bg-muted/30">
      <header className="bg-white border-b px-6 py-3 flex items-center gap-4">
        <h1 className="font-semibold text-base">{t('reports.payroll_title')}</h1>
        <span className="text-sm text-muted-foreground">Paytrak</span>
      </header>

      <div className="p-6 space-y-6 max-w-[1200px]">

        {/* ── Top: Period + Review ── */}
        <div className="space-y-5">
          {/* Period controls */}
          <div data-panel="period" className="bg-white border rounded-lg p-4 space-y-4">
            <h2 className="text-sm font-semibold">{t('reports.pay_period')}</h2>
            <div className="grid grid-cols-2 gap-4">
              <div className="space-y-1">
                <Label className="text-xs text-muted-foreground">{t('reports.period_start')}</Label>
                <Input type="date" value={periodStart} onChange={e => setPeriodStart(e.target.value)} />
              </div>
              <div className="space-y-1">
                <Label className="text-xs text-muted-foreground">{t('reports.period_end')}</Label>
                <Input type="date" value={periodEnd} onChange={e => {
                  setPeriodEnd(e.target.value)
                  setPaymentDate(defaultPaymentDate(e.target.value))
                }} />
              </div>
              <div className="space-y-1">
                <Label className="text-xs text-muted-foreground">{t('reports.payment_date')}</Label>
                <Input type="date" value={paymentDate} onChange={e => setPaymentDate(e.target.value)} />
              </div>
              <div className="flex items-end">
                <Button onClick={handleCalculate} disabled={isLoading} className="w-full gap-2">
                  <RefreshCw size={14} className={isLoading ? 'animate-spin' : ''} />
                  {isLoading ? t('reports.calculating') : t('reports.calculate')}
                </Button>
              </div>
            </div>
            <div className="space-y-1">
              <Label className="text-xs text-muted-foreground">{t('reports.stat_holiday')}</Label>
              <Input
                value={notes}
                onChange={e => setNotes(e.target.value)}
                placeholder={t('reports.stat_holiday_placeholder')}
              />
            </div>
          </div>

          {/* Review table */}
          {editableLines.length > 0 && (
            <div data-panel="review" className="bg-white border rounded-lg p-4 space-y-3">
              <div className="flex items-center justify-between">
                <h2 className="text-sm font-semibold">{t('reports.review_section')}</h2>
                <div className="flex items-center gap-3">
                  <span className="text-xs text-muted-foreground">{t('reports.review_subtitle')}</span>
                  <Button variant="ghost" size="sm" className="h-7 gap-1.5 text-xs" onClick={() => handlePrint('review')}>
                    <Printer size={12} />
                    {t('reports.print_pdf')}
                  </Button>
                </div>
              </div>

              {owners.length > 0 && (
                <div className="space-y-1.5">
                  <p className="text-xs font-medium text-muted-foreground uppercase tracking-wide">{t('reports.col_owner')}</p>
                  <ReviewTable editable={owners} onChange={updateLine} />
                </div>
              )}
              {staff.length > 0 && (
                <div className="space-y-1.5">
                  <p className="text-xs font-medium text-muted-foreground uppercase tracking-wide">{t('reports.col_staff')}</p>
                  <ReviewTable editable={staff} onChange={updateLine} />
                </div>
              )}
            </div>
          )}
        </div>

        {/* ── Bottom: Email composer ── */}
        <div>
          <div data-panel="email" className="bg-white border rounded-lg p-4 space-y-4">
            <h2 className="text-sm font-semibold">{t('reports.email_section')}</h2>

            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-1">
                <Label className="text-xs text-muted-foreground">{t('reports.to_label')}</Label>
                <Input value={toEmail} onChange={e => setToEmail(e.target.value)} />
              </div>
              <div className="space-y-1">
                <Label className="text-xs text-muted-foreground">{t('reports.paytrak_id')}</Label>
                <Input value={clientId} onChange={e => setClientId(e.target.value)} />
              </div>
            </div>

            <div className="space-y-1">
              <Label className="text-xs text-muted-foreground">{t('reports.subject_label')}</Label>
              <Input value={subject} readOnly className="bg-muted/30 text-muted-foreground" />
            </div>

            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-1">
                <Label className="text-xs text-muted-foreground">{t('reports.signature_label')}</Label>
                <Input value={signature} onChange={e => setSignature(e.target.value)} />
              </div>
            </div>

            <div className="space-y-1">
              <Label className="text-xs text-muted-foreground">{t('reports.footer_label')}</Label>
              <textarea
                value={footer}
                onChange={e => setFooter(e.target.value)}
                rows={4}
                className="w-full border border-input rounded-md px-3 py-2 text-xs bg-background resize-y font-mono"
              />
            </div>

            <div className="space-y-1">
              <div className="flex items-center justify-between">
                <Label className="text-xs text-muted-foreground">{t('reports.email_body')}</Label>
                <button onClick={handleCopy} className="text-xs text-muted-foreground hover:text-foreground flex items-center gap-1">
                  <ClipboardCopy size={12} />
                  {copied ? t('common.copied') : t('common.copy')}
                </button>
              </div>
              <textarea
                ref={emailRef}
                value={emailText}
                onChange={e => setEmailText(e.target.value)}
                rows={30}
                className="w-full border border-input rounded-md px-3 py-2 text-sm bg-background resize-y font-mono"
              />
            </div>

            <div className="flex gap-3 pt-1">
              <Button
                onClick={() => sendMutation.mutate()}
                disabled={!emailText || sendMutation.isPending || editableLines.length === 0}
                className="gap-2"
              >
                <Send size={14} />
                {sendMutation.isPending ? t('common.sending') : t('reports.send_paytrak')}
              </Button>
              <Button variant="ghost" onClick={() => handlePrint('email')} className="gap-2">
                <Printer size={14} />
                {t('reports.print_pdf')}
              </Button>
            </div>

            {sendMutation.isSuccess && (
              <p className="text-sm text-emerald-600">Email sent to {toEmail}</p>
            )}
            {sendMutation.isError && (
              <p className="text-sm text-destructive">
                Failed to send: {(sendMutation.error as Error)?.message}
              </p>
            )}
          </div>
        </div>
      </div>

      {/* Print styles */}
      <style>{`
        @media print {
          body { background: white !important; }
          header { display: none !important; }
          button { display: none !important; }
          textarea {
            border: none !important;
            height: auto !important;
            min-height: 0 !important;
            overflow: visible !important;
            white-space: pre-wrap !important;
            font-size: 12px !important;
            resize: none !important;
          }

          /* Print review: hide email panel */
          body[data-print-target="review"] [data-panel="email"] { display: none !important; }

          /* Print email: hide review and period panels */
          body[data-print-target="email"] [data-panel="review"] { display: none !important; }
          body[data-print-target="email"] [data-panel="period"] { display: none !important; }

          /* Ensure table doesn't clip when printing */
          body[data-print-target="review"] table { width: 100% !important; }
          body[data-print-target="review"] input { border: none !important; background: transparent !important; }
        }
      `}</style>
    </div>
  )
}
