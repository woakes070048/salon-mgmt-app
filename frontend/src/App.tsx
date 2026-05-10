import { Component, type ReactNode } from 'react'
import { Navigate, Route, Routes } from 'react-router-dom'
import { useAuth } from '@/store/auth'

class ErrorBoundary extends Component<{ children: ReactNode }, { error: Error | null }> {
  state = { error: null }
  static getDerivedStateFromError(error: Error) { return { error } }
  render() {
    if (this.state.error) {
      return (
        <div className="min-h-screen flex items-center justify-center bg-muted/30 p-8">
          <div className="bg-white border border-destructive/30 rounded-lg p-6 max-w-lg w-full space-y-3">
            <p className="font-semibold text-destructive">Something went wrong</p>
            <pre className="text-xs text-muted-foreground whitespace-pre-wrap font-mono bg-muted p-3 rounded">
              {(this.state.error as Error).message}
              {'\n\n'}
              {(this.state.error as Error).stack?.slice(0, 600)}
            </pre>
            <button className="text-sm underline" onClick={() => window.location.reload()}>Reload</button>
          </div>
        </div>
      )
    }
    return this.props.children
  }
}
import AppShell from '@/components/AppShell'
import LandingPage from '@/pages/LandingPage'
import LoginPage from '@/pages/LoginPage'
import RegisterPage from '@/pages/RegisterPage'
import ResetPasswordPage from '@/pages/ResetPasswordPage'
import ForgotPasswordPage from '@/pages/ForgotPasswordPage'
import DashboardPage from '@/pages/DashboardPage'
import AppointmentBookPage from '@/pages/AppointmentBookPage'
import StaffManagementPage from '@/pages/StaffManagementPage'
import PayrollReportPage from '@/pages/PayrollReportPage'
import PettyCashReportPage from '@/pages/PettyCashReportPage'
import MyRequestsPage from '@/pages/MyRequestsPage'
import RequestsPage from '@/pages/RequestsPage'
import SettingsPage from '@/pages/SettingsPage'
import ClientsPage from '@/pages/ClientsPage'
import ClientCleanupPage from '@/pages/ClientCleanupPage'
import ServicesPage from '@/pages/ServicesPage'
import UsersPage from '@/pages/UsersPage'
import TillPage from '@/pages/TillPage'
import RetailPage from '@/pages/RetailPage'
import ReportsPage from '@/pages/ReportsPage'
import TransactionReportPage from '@/pages/TransactionReportPage'
import DataImportPage from '@/pages/DataImportPage'
import LoginLogsPage from '@/pages/LoginLogsPage'

function StaffShell() {
  const { user, loading } = useAuth()
  if (loading) return <div className="min-h-screen bg-muted/30" />
  if (!user) return <Navigate to="/login" replace />
  if (user.role === 'guest') return <Navigate to="/my-requests" replace />
  return <AppShell />
}

function RequireGuest({ children }: { children: React.ReactNode }) {
  const { user, loading } = useAuth()
  if (loading) return <div className="min-h-screen bg-muted/30" />
  if (!user) return <Navigate to="/login" replace />
  if (user.role !== 'guest') return <Navigate to="/" replace />
  return <>{children}</>
}


export default function App() {
  return (
    <ErrorBoundary>
    <Routes>
      {/* Public routes */}
      <Route path="/" element={<LandingPage />} />
      <Route path="/login" element={<LoginPage />} />
      <Route path="/register" element={<RegisterPage />} />
      <Route path="/reset-password" element={<ResetPasswordPage />} />
      <Route path="/forgot-password" element={<ForgotPasswordPage />} />

      <Route
        path="/my-requests"
        element={
          <RequireGuest>
            <MyRequestsPage />
          </RequireGuest>
        }
      />

      {/* Staff shell — all staff routes nested here */}
      <Route element={<StaffShell />}>
        <Route path="/dashboard" element={<DashboardPage />} />
        <Route path="/appointments" element={<AppointmentBookPage />} />
        <Route path="/requests" element={<RequestsPage />} />
        <Route path="/staff" element={<StaffManagementPage />} />
        <Route path="/clients" element={<ClientsPage />} />
        <Route path="/clients/cleanup" element={<ClientCleanupPage />} />
        <Route path="/services" element={<ServicesPage />} />
        <Route path="/reports" element={<Navigate to="/reports/sales" replace />} />
        <Route path="/reports/sales" element={<ReportsPage />} />
        <Route path="/reports/transactions" element={<TransactionReportPage />} />
        <Route path="/reports/payroll" element={<PayrollReportPage />} />
        <Route path="/reports/petty-cash" element={<PettyCashReportPage />} />
        <Route path="/payroll" element={<Navigate to="/reports/payroll" replace />} />
        <Route path="/retail" element={<RetailPage />} />
        <Route path="/till" element={<TillPage />} />
        <Route path="/settings" element={<SettingsPage />} />
        <Route path="/users" element={<UsersPage />} />
        <Route path="/import" element={<DataImportPage />} />
        <Route path="/login-log" element={<LoginLogsPage />} />
      </Route>

      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
    </ErrorBoundary>
  )
}
