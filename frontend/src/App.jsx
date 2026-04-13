import { Routes, Route } from "react-router-dom";
import SessionPage from "./pages/SessionPage";
import UploadPage from "./pages/UploadPage";
import ReportPage from "./pages/ReportPage";
import EvaluationPage from "./pages/EvaluationPage";

export default function App() {
  return (
    <Routes>
      <Route path="/" element={<SessionPage />} />
      <Route path="/upload/:studentId" element={<UploadPage />} />
      <Route path="/report/:studentId" element={<ReportPage />} />
      <Route path="/evaluation/:submissionId" element={<EvaluationPage />} />
    </Routes>
  );
}