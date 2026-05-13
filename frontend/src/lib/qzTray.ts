// QZ Tray bridge — connects browser to the local Epson TM-T88V via QZ Tray WebSocket.
// QZ Tray must be installed and running on the salon PC.
// Download: https://qz.io/download/

declare global {
  interface Window {
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    qz: any
  }
}

const QZ_CDN = 'https://cdn.jsdelivr.net/npm/qz-tray@2.2.4/qz-tray.min.js'
const CHAR_WIDTH = 42  // chars across 80mm thermal roll at default font

function loadScript(): Promise<void> {
  return new Promise((resolve, reject) => {
    if (window.qz) { resolve(); return }
    const s = document.createElement('script')
    s.src = QZ_CDN
    s.onload = () => resolve()
    s.onerror = () => reject(new Error('Failed to load QZ Tray script. Is QZ Tray installed?'))
    document.head.appendChild(s)
  })
}

async function ensureConnected(): Promise<void> {
  await loadScript()
  if (!window.qz.websocket.isActive()) {
    try {
      await window.qz.websocket.connect({ host: 'localhost', usingSecure: true })
    } catch {
      // Fall back to non-secure (older QZ Tray installs)
      await window.qz.websocket.connect({ host: 'localhost', usingSecure: false })
    }
  }
}

function pad(left: string, right: string, width: number = CHAR_WIDTH): string {
  const spaces = width - left.length - right.length
  return left + ' '.repeat(Math.max(1, spaces)) + right
}

function divider(char: string = '-'): string {
  return char.repeat(CHAR_WIDTH)
}

export interface ReceiptData {
  sale_id: string
  completed_at: string
  salon_name: string
  address: string | null
  phone: string | null
  booking_email: string | null
  website: string | null
  receipt_logo_url: string | null
  client_first_name: string | null
  next_appointment: string | null
  items: { description: string; quantity: number; line_total: string }[]
  subtotal: string
  gst_amount: string
  pst_amount: string
  total: string
  payments: { label: string; amount: string; is_cash: boolean }[]
  printer_name: string
  cash_drawer_enabled: boolean
  auto_print_on_cash: boolean
  has_cash_payment: boolean
}

// ESC/POS constants
const ESC = '\x1b'
const GS = '\x1d'
const INIT = ESC + '@'
const CENTER = ESC + 'a\x01'
const LEFT = ESC + 'a\x00'
const BOLD_ON = ESC + 'E\x01'
const BOLD_OFF = ESC + 'E\x00'
const DOUBLE_SIZE = ESC + '!\x30'
const NORMAL_SIZE = ESC + '!\x00'
const CUT = GS + 'V\x41\x05'
const DRAWER = ESC + 'p\x00\x19\xFF'

function raw(data: string) {
  return { type: 'raw', format: 'plain', data }
}

function image(url: string) {
  return { type: 'raw', format: 'image', data: url, options: { language: 'ESCPOS', dotDensity: 'double' } }
}

function buildCommands(d: ReceiptData): object[] {
  const cmds: object[] = []

  cmds.push(raw(INIT))

  // Logo (if configured)
  if (d.receipt_logo_url) {
    cmds.push(raw(CENTER))
    cmds.push(image(d.receipt_logo_url))
    cmds.push(raw('\n'))
  }

  // Header
  cmds.push(raw(CENTER + BOLD_ON + DOUBLE_SIZE))
  cmds.push(raw(d.salon_name + '\n'))
  cmds.push(raw(BOLD_OFF + NORMAL_SIZE))
  if (d.address) cmds.push(raw(d.address + '\n'))
  if (d.phone) cmds.push(raw(d.phone + '\n'))
  cmds.push(raw('\n'))

  // Date / time
  cmds.push(raw(LEFT))
  cmds.push(raw(d.completed_at + '\n'))
  cmds.push(raw(divider() + '\n'))

  // Line items
  for (const item of d.items) {
    const desc = item.quantity > 1 ? `${item.description} x${item.quantity}` : item.description
    cmds.push(raw(pad(desc, `$${parseFloat(item.line_total).toFixed(2)}`) + '\n'))
  }
  cmds.push(raw(divider() + '\n'))

  // Totals
  cmds.push(raw(pad('Subtotal', `$${parseFloat(d.subtotal).toFixed(2)}`) + '\n'))
  cmds.push(raw(pad('GST (5%)', `$${parseFloat(d.gst_amount).toFixed(2)}`) + '\n'))
  cmds.push(raw(pad('PST (8%)', `$${parseFloat(d.pst_amount).toFixed(2)}`) + '\n'))
  cmds.push(raw(divider('=') + '\n'))
  cmds.push(raw(BOLD_ON))
  cmds.push(raw(pad('TOTAL', `$${parseFloat(d.total).toFixed(2)}`) + '\n'))
  cmds.push(raw(BOLD_OFF))

  // Payments
  cmds.push(raw('\n'))
  for (const p of d.payments) {
    cmds.push(raw(pad(p.label, `$${parseFloat(p.amount).toFixed(2)}`) + '\n'))
  }

  // Client footer — only if there's a next appointment to show
  if (d.client_first_name && d.next_appointment) {
    cmds.push(raw('\n'))
    cmds.push(raw(`Hi ${d.client_first_name},\n`))
    cmds.push(raw(`Your next appointment:\n${d.next_appointment}\n`))
  }

  // Salon contact footer
  cmds.push(raw('\n'))
  cmds.push(raw(CENTER))
  cmds.push(raw(d.salon_name + '\n'))
  if (d.address) cmds.push(raw(d.address + '\n'))
  if (d.phone) cmds.push(raw(d.phone + '\n'))
  if (d.booking_email) cmds.push(raw(d.booking_email + '\n'))
  if (d.website) cmds.push(raw(d.website + '\n'))
  cmds.push(raw(LEFT))

  // Feed and cut
  cmds.push(raw('\n\n\n'))
  cmds.push(raw(CUT))

  return cmds
}

export async function printReceipt(data: ReceiptData): Promise<void> {
  await ensureConnected()
  const config = window.qz.configs.create(data.printer_name)
  const cmds = buildCommands(data)
  await window.qz.print(config, cmds)

  if (data.cash_drawer_enabled && data.has_cash_payment) {
    await window.qz.print(config, [raw(DRAWER)])
  }
}

export async function openCashDrawer(printerName: string): Promise<void> {
  await ensureConnected()
  const config = window.qz.configs.create(printerName)
  await window.qz.print(config, [raw(INIT + DRAWER)])
}
