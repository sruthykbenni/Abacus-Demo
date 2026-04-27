import { useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { CheckCircle } from "lucide-react";
import Navbar from "../components/Navbar";

export default function UploadPage() {
  const { studentId } = useParams();
  const navigate      = useNavigate();

  const [answerSheet, setAnswerSheet] = useState(null);
  const [examId,      setExamId]      = useState("");
  const [loading,     setLoading]     = useState(false);
  const [success,     setSuccess]     = useState(false);
  const [submissionId, setSubmissionId] = useState(null);
  const [keyMissing,  setKeyMissing]  = useState(false);

  const handleDrop = (e) => {
    e.preventDefault();
    const file = e.dataTransfer.files[0];
    if (file) setAnswerSheet(file);
  };

  const handleSubmit = async () => {
    if (!answerSheet) {
      alert("Please upload answer sheet");
      return;
    }
    if (!examId.trim()) {
      alert("Please enter the Question Paper Code (Exam ID)");
      return;
    }

    try {
      setLoading(true);
      setKeyMissing(false);

      const formData = new FormData();
      formData.append("answer_sheet", answerSheet);
      formData.append("student_id",   studentId);
      formData.append("exam_id",      examId.trim());

      const res  = await fetch("http://127.0.0.1:5000/process", {
        method: "POST",
        body:   formData,
      });
      const data = await res.json();

      if (data.error) {
        alert(data.error);
        return;
      }

      if (!data.answer_key_found) {
        setKeyMissing(true);
      }

      const sid = data.submission_id ?? "temp";
      setSubmissionId(sid);
      setSuccess(true);

      // Store results for evaluation page
      sessionStorage.setItem(
        `submission_${sid}`,
        JSON.stringify({
          results: data.results,
          summary: {
            total_questions: data.total_questions,
            total_correct:   data.total_correct,
            accuracy:        data.accuracy,
          },
        })
      );
    } catch (err) {
      console.error(err);
      alert("Processing failed");
    } finally {
      setLoading(false);
    }
  };

  // ── SUCCESS VIEW ──
  if (success) {
    return (
      <div className="min-h-screen bg-gray-100">
        <Navbar />
        <div className="flex justify-center items-center h-[80vh]">
          <div className="bg-white shadow-2xl rounded-2xl p-12 w-[480px] text-center">
            <CheckCircle className="text-green-500 mx-auto mb-4" size={72} />
            <h2 className="text-2xl font-bold text-gray-800 mb-2">
              Assessment Submitted
            </h2>
            <p className="text-gray-500 mb-1">
              Exam ID: <span className="font-semibold text-orange-500">{examId}</span>
            </p>
            {submissionId && submissionId !== "temp" && (
              <p className="text-gray-400 text-sm mb-4">
                Submission #{submissionId}
              </p>
            )}
            {keyMissing && (
              <div className="bg-yellow-50 border border-yellow-200 text-yellow-700 text-sm px-4 py-2 rounded-lg mb-4">
                ⚠️ No answer key found for this exam ID. Results show detected answers only.
              </div>
            )}
            <div className="flex gap-3 mt-6">
              <button
                onClick={() =>
                  navigate(`/evaluation/${submissionId}`, {
                    state: JSON.parse(
                      sessionStorage.getItem(`submission_${submissionId}`) || "{}"
                    ),
                  })
                }
                className="flex-1 bg-orange-500 hover:bg-orange-600 text-white py-2 rounded-xl font-semibold"
              >
                View Results
              </button>
              <button
                onClick={() => {
                  setSuccess(false);
                  setAnswerSheet(null);
                  setExamId("");
                  setSubmissionId(null);
                }}
                className="flex-1 bg-gray-100 hover:bg-gray-200 text-gray-700 py-2 rounded-xl font-semibold"
              >
                New Submission
              </button>
            </div>
          </div>
        </div>
      </div>
    );
  }

  // ── UPLOAD VIEW ──
  return (
    <div className="min-h-screen bg-gray-100">
      <Navbar />

      <div className="flex justify-center items-center h-[80vh]">
        <div className="bg-white shadow-2xl rounded-2xl p-10 w-[520px]">

          <h2 className="text-2xl font-bold mb-8 text-center">
            Upload Answer Sheet
          </h2>

          {/* Exam ID */}
          <div className="mb-6">
            <label className="block font-semibold mb-2 text-gray-700">
              Question Paper Code (Exam ID)
            </label>
            <input
              type="text"
              value={examId}
              onChange={(e) => setExamId(e.target.value)}
              placeholder="e.g. 417, L5_839"
              className="w-full border-2 border-gray-300 rounded-xl px-4 py-2 focus:outline-none focus:border-orange-400"
            />
            <p className="text-xs text-gray-400 mt-1">
              Must match an exam ID registered by your teacher/admin
            </p>
          </div>

          {/* Answer Sheet Upload */}
          <div
            onDragOver={(e) => e.preventDefault()}
            onDrop={handleDrop}
            className="border-2 border-dashed border-gray-300 p-8 rounded-xl text-center hover:border-orange-400 mb-8"
          >
            <p className="font-semibold mb-4">Upload Answer Sheet</p>

            <label className="cursor-pointer bg-orange-500 hover:bg-orange-600 text-white px-5 py-2 rounded-lg">
              Choose File
              <input
                type="file"
                onChange={(e) => setAnswerSheet(e.target.files[0])}
                className="hidden"
                accept=".png,.jpg,.jpeg"
              />
            </label>

            <p className="text-xs text-gray-400 mt-3">or drag & drop (PNG / JPG)</p>

            {answerSheet && (
              <div className="mt-3 text-sm text-gray-700">
                📄 {answerSheet.name}
              </div>
            )}
          </div>

          {/* Submit */}
          <button
            onClick={handleSubmit}
            disabled={loading}
            className={`w-full py-3 rounded-xl font-semibold ${
              loading
                ? "bg-orange-300 cursor-not-allowed text-white"
                : "bg-orange-500 hover:bg-orange-600 text-white"
            }`}
          >
            {loading ? "Processing..." : "Submit Assessment"}
          </button>

        </div>
      </div>
    </div>
  );
}
