import { Routes, Route, Navigate } from "react-router-dom";
import { AuthProvider, useAuth } from "@/context/AuthContext";
import { Layout } from "@/components/Layout";
import { LoginPage } from "@/pages/LoginPage";
import { CasesPage } from "@/pages/CasesPage";
import { CaseDetailPage } from "@/pages/CaseDetailPage";
import { ReportsPage } from "@/pages/ReportsPage";

function ProtectedRoutes() {
  const { token } = useAuth();
  if (!token) return <Navigate to="/login" replace />;
  return (
    <Layout>
      <Routes>
        <Route path="/" element={<CasesPage />} />
        <Route path="/cases/:id" element={<CaseDetailPage />} />
        <Route path="/reports" element={<ReportsPage />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </Layout>
  );
}

export default function App() {
  return (
    <AuthProvider>
      <Routes>
        <Route path="/login" element={<AuthRedirect />} />
        <Route path="/*" element={<ProtectedRoutes />} />
      </Routes>
    </AuthProvider>
  );
}

function AuthRedirect() {
  const { token } = useAuth();
  return token ? <Navigate to="/" replace /> : <LoginPage />;
}
