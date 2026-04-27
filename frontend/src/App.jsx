import { Routes, Route, Navigate } from "react-router-dom";
import LoginPage     from "./pages/LoginPage";
import SessionPage   from "./pages/SessionPage";
import UploadPage    from "./pages/UploadPage";
import ReportPage    from "./pages/ReportPage";
import EvaluationPage from "./pages/EvaluationPage";
import AnswerKeyPage from "./pages/AnswerKeyPage";

// Simple auth guard
function RequireAuth({ children, allowedRoles }) {
  const role = sessionStorage.getItem("role");
  if (!role) return <Navigate to="/login" replace />;
  if (allowedRoles && !allowedRoles.includes(role)) {
    // Redirect student to their upload page, others to main
    if (role === "student") {
      const sid = sessionStorage.getItem("student_id");
      return <Navigate to={`/upload/${sid}`} replace />;
    }
    return <Navigate to="/" replace />;
  }
  return children;
}

export default function App() {
  return (
    <Routes>
      {/* Public */}
      <Route path="/login" element={<LoginPage />} />

      {/* Default redirect */}
      <Route path="/" element={
        <RequireAuth allowedRoles={["teacher", "admin"]}>
          <SessionPage />
        </RequireAuth>
      } />

      {/* Student */}
      <Route path="/upload/:studentId" element={
        <RequireAuth>
          <UploadPage />
        </RequireAuth>
      } />

      {/* Teacher / Admin */}
      <Route path="/report/:studentId" element={
        <RequireAuth allowedRoles={["teacher", "admin"]}>
          <ReportPage />
        </RequireAuth>
      } />

      <Route path="/evaluation/:submissionId" element={
        <RequireAuth>
          <EvaluationPage />
        </RequireAuth>
      } />

      {/* Admin / Teacher: Answer Key Manager */}
      <Route path="/answer-keys" element={
        <RequireAuth allowedRoles={["teacher", "admin"]}>
          <AnswerKeyPage />
        </RequireAuth>
      } />

      {/* Catch-all → login */}
      <Route path="*" element={<Navigate to="/login" replace />} />
    </Routes>
  );
}
