import { Routes, Route, Navigate } from 'react-router-dom'
import { AuthProvider, useAuth } from './auth/AuthContext'
import Layout from './components/Layout'
import LandingPage from './pages/LandingPage'
import PublicOfferPage from './pages/PublicOfferPage'
import Case1Page from './pages/Case1Page'
import Case2Page from './pages/Case2Page'
import Case3Page from './pages/Case3Page'
import CurrencyPage from './pages/CurrencyPage'
import BankPage from './pages/BankPage'
import UsersPage from './pages/UsersPage'
import SettingsPage from './pages/SettingsPage'
import AccessPage from './pages/AccessPage'
import ChangelogPage from './pages/ChangelogPage'

function ProtectedRoute({ children, service, staffOnly }: { children: React.ReactNode; service?: string; staffOnly?: boolean }) {
  const { isAuthenticated, loading, services, user } = useAuth()

  if (loading) {
    return <div className="loading">Загрузка...</div>
  }

  if (!isAuthenticated) {
    return <Navigate to="/" replace />
  }

  // UX-only guard; the backend (require_service) is the real gate.
  if (service && !services.some((s) => s.code === service)) {
    return <Navigate to="/" replace />
  }

  // UX-only guard; the backend (require_staff) is the real gate.
  if (staffOnly && user?.role === 'client') {
    return <Navigate to="/" replace />
  }

  return <>{children}</>
}

function App() {
  return (
    <AuthProvider>
      <Routes>
        <Route path="/offer" element={<PublicOfferPage />} />
        <Route path="/" element={<Layout />}>
          <Route index element={<LandingPage />} />
          <Route path="case1" element={<ProtectedRoute service="case1"><div className="container"><Case1Page /></div></ProtectedRoute>} />
          <Route path="case2" element={<ProtectedRoute service="case2"><div className="container"><Case2Page /></div></ProtectedRoute>} />
          <Route path="case3" element={<ProtectedRoute service="case3"><div className="container"><Case3Page /></div></ProtectedRoute>} />
          <Route path="case_currency" element={<ProtectedRoute service="case_currency"><div className="container"><CurrencyPage /></div></ProtectedRoute>} />
          <Route path="case_bank" element={<ProtectedRoute service="case_bank"><div className="container"><BankPage /></div></ProtectedRoute>} />
          <Route path="changelog" element={<ProtectedRoute staffOnly><div className="container"><ChangelogPage /></div></ProtectedRoute>} />
          <Route path="users" element={<ProtectedRoute><UsersPage /></ProtectedRoute>} />
          <Route path="access" element={<ProtectedRoute><AccessPage /></ProtectedRoute>} />
          <Route path="settings" element={<ProtectedRoute><div className="container"><SettingsPage /></div></ProtectedRoute>} />
        </Route>
      </Routes>
    </AuthProvider>
  )
}

export default App
