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

// Certificate injected at build time — allows QZ Tray to auto-trust this site.
const QZ_CERTIFICATE = `-----BEGIN CERTIFICATE-----
MIIECzCCAvOgAwIBAgIGAZ4hWtQUMA0GCSqGSIb3DQEBCwUAMIGiMQswCQYDVQQG
EwJVUzELMAkGA1UECAwCTlkxEjAQBgNVBAcMCUNhbmFzdG90YTEbMBkGA1UECgwS
UVogSW5kdXN0cmllcywgTExDMRswGQYDVQQLDBJRWiBJbmR1c3RyaWVzLCBMTEMx
HDAaBgkqhkiG9w0BCQEWDXN1cHBvcnRAcXouaW8xGjAYBgNVBAMMEVFaIFRyYXkg
RGVtbyBDZXJ0MB4XDTI2MDUxMjEyNDEwMVoXDTQ2MDUxMjEyNDEwMVowgaIxCzAJ
BgNVBAYTAlVTMQswCQYDVQQIDAJOWTESMBAGA1UEBwwJQ2FuYXN0b3RhMRswGQYD
VQQKDBJRWiBJbmR1c3RyaWVzLCBMTEMxGzAZBgNVBAsMElFaIEluZHVzdHJpZXMs
IExMQzEcMBoGCSqGSIb3DQEJARYNc3VwcG9ydEBxei5pbzEaMBgGA1UEAwwRUVog
VHJheSBEZW1vIENlcnQwggEiMA0GCSqGSIb3DQEBAQUAA4IBDwAwggEKAoIBAQC3
DM7h2yJcgeTuLvi3rwya7fjVCO+8jJBg1DSVsCF8LVz+ISp5xcCzKbG5mC/6b1HE
ya/ls1SgFVTrx36/FxX4Op9bExlWdA+vlJDTx55l1kQQZYb6Rv+HaZU28XLBCTn/
WCMNEpZHqBRAymBouumZkzTPvnwb+/HGhcWbjitOAWkABl6vUPSkvZQHYlO34TEx
tUoKJX3t2FB4JvbITyJYRkE59ZRHrE9zFIiUufe7A3tJ82RBkE+jILhNG0uaDsXJ
CKKAnhBu47+6CheLJukIGlcxXczvKQfn6A2ZfeTDxpH47oFfnyNytkQWrJQ396up
jbWT9nJV2w4s/al3PDB9AgMBAAGjRTBDMBIGA1UdEwEB/wQIMAYBAf8CAQEwDgYD
VR0PAQH/BAQDAgEGMB0GA1UdDgQWBBRdyJuaytjPjg6Bf7DyhBboiw4JHzANBgkq
hkiG9w0BAQsFAAOCAQEAfTg1oRbzm27J8avTmd4H70Jp/ku6XcGzuSBrbG0ErG/o
KohZ6x7mUX+IlWyquC4uRqrevl0rKkOH2t40VhPiEwr2ouEDfMiwb7hQwTHFR/XT
JFbCf4FeP67Euu6mI1zHghsbBs/3z6YhcVMZGOdf2ht9gbTPr2mROC7D2F8XqmWN
MhP/n0IeoagMk+NU/j0cSTyWRBuuITw1jdJnXl4n16qGN5xFzg62YNA60f8QAjxN
asvxQWZ9OhkM+xO8dwIDFHmT7xgMh+elWELLPIDzH0ASt4znpmVyXoSkXvfkUfvO
X/RyGE0H4Wa4CWeIpKk3oSwA9DbyMzs8IhQ+WQEUXA==
-----END CERTIFICATE-----`

// Private key injected from VITE_QZ_PRIVATE_KEY build arg (GitHub secret — never in repo).
const QZ_PRIVATE_KEY: string = import.meta.env.VITE_QZ_PRIVATE_KEY ?? ''

async function signData(toSign: string): Promise<string> {
  const pemContents = QZ_PRIVATE_KEY
    .replace('-----BEGIN PRIVATE KEY-----', '')
    .replace('-----END PRIVATE KEY-----', '')
    .replace(/\s/g, '')
  const binaryDer = atob(pemContents)
  const binaryArray = new Uint8Array(binaryDer.length)
  for (let i = 0; i < binaryDer.length; i++) binaryArray[i] = binaryDer.charCodeAt(i)

  const cryptoKey = await crypto.subtle.importKey(
    'pkcs8',
    binaryArray.buffer,
    { name: 'RSASSA-PKCS1-v1_5', hash: 'SHA-512' },
    false,
    ['sign'],
  )
  const signature = await crypto.subtle.sign(
    'RSASSA-PKCS1-v1_5',
    cryptoKey,
    new TextEncoder().encode(toSign),
  )
  const bytes = new Uint8Array(signature)
  let binary = ''
  for (let i = 0; i < bytes.byteLength; i++) binary += String.fromCharCode(bytes[i])
  return btoa(binary)
}

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

  // Set up certificate and signing so QZ Tray trusts this site without prompting.
  window.qz.security.setCertificatePromise((_resolve: (v: string) => void) => {
    _resolve(QZ_CERTIFICATE)
  })
  window.qz.security.setSignatureAlgorithm('SHA512')
  window.qz.security.setSignaturePromise((toSign: string) => {
    return (resolve: (v: string) => void, reject: (e: unknown) => void) => {
      signData(toSign).then(resolve).catch(reject)
    }
  })

  if (!window.qz.websocket.isActive()) {
    try {
      await window.qz.websocket.connect({ host: 'localhost', usingSecure: true })
    } catch {
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
