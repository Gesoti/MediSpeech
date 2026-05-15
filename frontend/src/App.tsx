import { Routes, Route, Navigate } from "react-router-dom";
import { Layout } from "@/components/Layout";
import { CasesPage } from "@/pages/CasesPage";
import { CaseDetailPage } from "@/pages/CaseDetailPage";
import { ReportsPage } from "@/pages/ReportsPage";

export default function App() {
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
