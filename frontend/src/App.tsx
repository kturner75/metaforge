import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import { LoginScreen } from '@/components'
import { AppLayout } from '@/components/AppLayout'
import { EntityCrudScreen } from '@/components/EntityCrudScreen'
import { useAuthMe } from '@/hooks/useApi'
import { useAuth } from '@/hooks/useAuth'
import { useNavigation } from '@/hooks/useNavigation'
import './App.css'

const queryClient = new QueryClient()

function AuthenticatedRoutes() {
  const auth = useAuth()
  const { data: me } = useAuthMe(auth.isAuthenticated)
  const { data: nav } = useNavigation()

  if (!auth.isAuthenticated) {
    return (
      <LoginScreen
        onLogin={auth.login}
        isSubmitting={auth.isLoggingIn}
        error={auth.error}
      />
    )
  }

  const userLabel = me?.name || me?.email ? `Signed in as ${me?.name || me?.email}` : 'Signed in'
  const defaultSlug = nav?.defaultScreen ?? 'contacts'

  const handleLogout = () => {
    auth.logout()
    queryClient.clear()
  }

  return (
    <Routes>
      <Route element={<AppLayout userLabel={userLabel} onLogout={handleLogout} />}>
        <Route index element={<Navigate to={`/${defaultSlug}`} replace />} />
        <Route path=":slug" element={<EntityCrudScreen />} />
        <Route path=":slug/new" element={<EntityCrudScreen />} />
        <Route path=":slug/:id" element={<EntityCrudScreen />} />
        <Route path=":slug/:id/edit" element={<EntityCrudScreen />} />
      </Route>
    </Routes>
  )
}

function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <Routes>
          <Route path="/*" element={<AuthenticatedRoutes />} />
        </Routes>
      </BrowserRouter>
    </QueryClientProvider>
  )
}

export default App
