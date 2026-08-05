import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom';
import type { ReactNode } from 'react';

import { AuthPage } from '@/components/AuthPage';
import { Layout } from '@/components/Layout';
import { useAuth } from '@/hooks/AuthContext';
import { ScenarioProvider } from '@/hooks/ScenarioContext';
import { CurrentPage } from '@/pages/CurrentPage';
import { HardeningPage } from '@/pages/HardeningPage';
import { OperatorPage } from '@/pages/OperatorPage';
import { RegistryPage } from '@/pages/RegistryPage';
import { SimulationPage } from '@/pages/SimulationPage';

function AuthGuard({ children, requireAuth }: { children: ReactNode; requireAuth: boolean }) {
  const { isAuthenticated, loading } = useAuth();

  if (loading) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-slate-100">
        <div className="text-sm text-slate-500">Wczytywanie…</div>
      </div>
    );
  }

  if (requireAuth && !isAuthenticated) return <Navigate to="/auth" replace />;
  if (!requireAuth && isAuthenticated) return <Navigate to="/" replace />;

  return <>{children}</>;
}

/** Pięć ekranów scenariusza pod wspólnym układem i wspólnym zegarem sceny. */
function Shell({ children }: { children: ReactNode }) {
  return (
    <AuthGuard requireAuth={true}>
      <ScenarioProvider>
        <Layout>{children}</Layout>
      </ScenarioProvider>
    </AuthGuard>
  );
}

function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route
          path="/auth"
          element={
            <AuthGuard requireAuth={false}>
              <AuthPage />
            </AuthGuard>
          }
        />
        <Route
          path="/"
          element={
            <Shell>
              <SimulationPage />
            </Shell>
          }
        />
        <Route
          path="/obraz"
          element={
            <Shell>
              <CurrentPage />
            </Shell>
          }
        />
        <Route
          path="/meldunek"
          element={
            <Shell>
              <OperatorPage />
            </Shell>
          }
        />
        <Route
          path="/rejestr"
          element={
            <Shell>
              <RegistryPage />
            </Shell>
          }
        />
        <Route
          path="/wzmocnienia"
          element={
            <Shell>
              <HardeningPage />
            </Shell>
          }
        />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </BrowserRouter>
  );
}

export default App;
