import { lazy, Suspense } from 'react'
import { Navigate, Route, Routes } from 'react-router'
import { AppShell } from '../components/layout/AppShell'
import { Skeleton } from '../components/ui'
import { useAuth } from '../hooks/auth-context'
import { can } from '../lib/permissions'

// Split per route: the charts bundle is the largest thing here and only the
// dashboard needs it.
const DashboardPage = lazy(() => import('../pages/DashboardPage'))
const ShipmentsPage = lazy(() => import('../pages/ShipmentsPage'))
const SuppliersPage = lazy(() => import('../pages/SuppliersPage'))
const DocumentsPage = lazy(() => import('../pages/DocumentsPage'))
const AskPage = lazy(() => import('../pages/AskPage'))
const AlertsPage = lazy(() => import('../pages/AlertsPage'))
const SettingsPage = lazy(() => import('../pages/SettingsPage'))
const LoginPage = lazy(() => import('../pages/LoginPage'))
const SignupPage = lazy(() => import('../pages/SignupPage'))

function Loading() {
  return (
    <div className="flex flex-col gap-4 p-4">
      <Skeleton className="h-8 w-48" />
      <Skeleton className="h-48 w-full" />
    </div>
  )
}

export function AppRoutes() {
  const { state, user } = useAuth()

  // A splash while the refresh cookie is being exchanged. Without it the login
  // page flashes for a moment on every reload of an authenticated session.
  if (state === 'checking') return <Loading />

  if (state === 'anonymous') {
    return (
      <Suspense fallback={<Loading />}>
        <Routes>
          <Route path="/login" element={<LoginPage />} />
          <Route path="/signup" element={<SignupPage />} />
          <Route path="*" element={<Navigate to="/login" replace />} />
        </Routes>
      </Suspense>
    )
  }

  return (
    <Suspense fallback={<Loading />}>
      <Routes>
        <Route element={<AppShell />}>
          <Route index element={<DashboardPage />} />
          <Route path="shipments" element={<ShipmentsPage />} />
          <Route path="suppliers" element={<SuppliersPage />} />
          <Route path="documents" element={<DocumentsPage />} />
          <Route path="ask" element={<AskPage />} />
          <Route path="alerts" element={<AlertsPage />} />
          <Route
            path="settings"
            element={can(user?.role, 'user:write') ? <SettingsPage /> : <Navigate to="/" replace />}
          />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Route>
      </Routes>
    </Suspense>
  )
}
