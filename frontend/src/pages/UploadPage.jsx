import { useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import Navbar from "../components/Navbar";

export default function UploadPage() {
  const { studentId } = useParams();
  const navigate = useNavigate();

  const [answerSheet, setAnswerSheet] = useState(null);
  const [answerKey, setAnswerKey] = useState(null);
  // ✅ NEW: Question Paper Code field
  const [examId, setExamId] = useState("");
  const [loading, setLoading] = useState(false);

  const handleDrop = (e, type) => {
    e.preventDefault();
    const file = e.dataTransfer.files[0];

    if (type === "sheet") setAnswerSheet(file);
    else setAnswerKey(file);
  };

  const handleSubmit = async () => {
    if (!answerSheet) {
      alert("Please upload answer sheet");
      return;
    }

    if (!examId.trim()) {
      alert("Please enter the Question Paper Code");
      return;
    }

    try {
      setLoading(true);

      const formData = new FormData();
      formData.append("answer_sheet", answerSheet);

      if (answerKey) {
        formData.append("answer_key", answerKey);
      }

      // ✅ Send student_id and exam_id to backend
      formData.append("student_id", studentId);
      formData.append("exam_id", examId.trim());

      const res = await fetch("http://127.0.0.1:5000/process", {
        method: "POST",
        body: formData,
      });

      const data = await res.json();

      if (data.error) {
        alert(data.error);
        return;
      }

      // ✅ Use real submission_id from DB if available, else fall back to "temp"
      const submissionId = data.submission_id ?? "temp";

      navigate(`/evaluation/${submissionId}`, {
        state: {
          results: data.results,
          summary: {
            total_questions: data.total_questions,
            total_correct: data.total_correct,
            accuracy: data.accuracy,
          },
        },
      });

    } catch (err) {
      console.error(err);
      alert("Processing failed");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-gray-100">

      <Navbar />

      <div className="flex justify-center items-center h-[80vh]">

        <div className="bg-white shadow-2xl rounded-2xl p-10 w-[750px]">

          <h2 className="text-2xl font-bold mb-8 text-center">
            Upload Answer Sheet
          </h2>

          {/* ✅ NEW: Question Paper Code input */}
          <div className="mb-6">
            <label className="block font-semibold mb-2 text-gray-700">
              Question Paper Code
            </label>
            <input
              type="text"
              value={examId}
              onChange={(e) => setExamId(e.target.value)}
              placeholder="e.g. 417, L5_839"
              className="w-full border-2 border-gray-300 rounded-xl px-4 py-2 focus:outline-none focus:border-orange-400"
            />
          </div>

          <div className="grid md:grid-cols-2 gap-6 mb-8">

            {/* ANSWER SHEET */}
            <div
              onDragOver={(e) => e.preventDefault()}
              onDrop={(e) => handleDrop(e, "sheet")}
              className="border-2 border-dashed border-gray-300 p-6 rounded-xl text-center hover:border-orange-400"
            >
              <p className="font-semibold mb-4">
                Upload Answer Sheet
              </p>

              <label className="cursor-pointer bg-orange-500 hover:bg-orange-600 text-white px-5 py-2 rounded-lg">
                Choose File
                <input
                  type="file"
                  onChange={(e) =>
                    setAnswerSheet(e.target.files[0])
                  }
                  className="hidden"
                />
              </label>

              <p className="text-xs text-gray-400 mt-3">
                or drag & drop
              </p>

              {answerSheet && (
                <div className="mt-3 text-sm">
                  📄 {answerSheet.name}
                </div>
              )}
            </div>

            {/* ANSWER KEY */}
            <div
              onDragOver={(e) => e.preventDefault()}
              onDrop={(e) => handleDrop(e, "key")}
              className="border-2 border-dashed border-gray-300 p-6 rounded-xl text-center hover:border-orange-400"
            >
              <p className="font-semibold mb-4">
                Upload Answer Key (PDF)
              </p>

              <label className="cursor-pointer bg-orange-500 hover:bg-orange-600 text-white px-5 py-2 rounded-lg">
                Choose File
                <input
                  type="file"
                  onChange={(e) =>
                    setAnswerKey(e.target.files[0])
                  }
                  className="hidden"
                />
              </label>

              <p className="text-xs text-gray-400 mt-3">
                or drag & drop
              </p>

              {answerKey && (
                <div className="mt-3 text-sm">
                  📄 {answerKey.name}
                </div>
              )}
            </div>

          </div>

          {/* BUTTON */}
          <button
            onClick={handleSubmit}
            disabled={loading}
            className={`w-full py-3 rounded-lg font-semibold ${
              loading
                ? "bg-orange-300 cursor-not-allowed"
                : "bg-orange-500 hover:bg-orange-600 text-white"
            }`}
          >
            {loading ? "Processing..." : "Run Evaluation"}
          </button>

        </div>

      </div>
    </div>
  );
}
