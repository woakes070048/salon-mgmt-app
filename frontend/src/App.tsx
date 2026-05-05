import { Navigate, Route, Routes } from 'react-router-dom'
import { useAuth } from '@/store/auth'
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
  )
}
