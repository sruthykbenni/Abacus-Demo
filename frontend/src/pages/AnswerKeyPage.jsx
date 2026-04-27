import { useState, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { Upload, Trash2, Eye, KeyRound } from "lucide-react";
import Navbar from "../components/Navbar";

export default function AnswerKeyPage() {
  const navigate   = useNavigate();
  const [keys,     setKeys]     = useState([]);
  const [examId,   setExamId]   = useState("");
  const [keyFile,  setKeyFile]  = useState(null);
  const [loading,  setLoading]  = useState(false);
  const [message,  setMessage]  = useState(null);
  const [preview,  setPreview]  = useState(null);

  const userId = sessionStorage.getItem("user_id");
  const role   = sessionStorage.getItem("role");

  // Redirect if not admin/teacher
  useEffect(() => {
    if (!role || role === "student") {
      navigate("/login");
    }
  }, [role, navigate]);

  // Load existing keys
  const loadKeys = () => {
    fetch("http://127.0.0.1:5000/answer-keys")
      .then((r) => r.json())
      .then((data) => { if (Array.isArray(data)) setKeys(data); })
      .catch(() => {});
  };

  useEffect(() => { loadKeys(); }, []);

  const handleUpload = async () => {
    if (!examId.trim()) { setMessage({ type: "error", text: "Exam ID is required" }); return; }
    if (!keyFile)        { setMessage({ type: "error", text: "Please select an answer key PDF" }); return; }

    setLoading(true);
    setMessage(null);
    try {
      const fd = new FormData();
      fd.append("exam_id",     examId.trim());
      fd.append("answer_key",  keyFile);
      fd.append("uploaded_by", userId);

      const res  = await fetch("http://127.0.0.1:5000/answer-keys", { method: "POST", body: fd });
      const data = await res.json();

      if (!res.ok || data.error) {
        setMessage({ type: "error", text: data.error || "Upload failed" });
      } else {
        setMessage({
          type: "success",
          text: `✅ Answer key for "${data.exam_id}" stored (${data.question_count} questions)`,
        });
        setExamId("");
        setKeyFile(null);
        loadKeys();
      }
    } catch (err) {
      setMessage({ type: "error", text: "Server error" });
    } finally {
      setLoading(false);
    }
  };

  const handleDelete = async (eid) => {
    if (!confirm(`Delete answer key for exam "${eid}"?`)) return;
    try {
      await fetch(`http://127.0.0.1:5000/answer-keys/${eid}`, { method: "DELETE" });
      loadKeys();
    } catch {}
  };

  const handlePreview = async (eid) => {
    try {
      const res  = await fetch(`http://127.0.0.1:5000/answer-keys/${eid}`);
      const data = await res.json();
      setPreview({ exam_id: eid, key_data: data.key_data });
    } catch {}
  };

  return (
    <div className="min-h-screen bg-gray-100">
      <Navbar />

      <div className="p-10 max-w-4xl mx-auto">

        <div className="flex items-center gap-3 mb-8">
          <KeyRound className="text-orange-500" size={28} />
          <h2 className="text-3xl font-bold">Answer Key Manager</h2>
        </div>

        {/* Upload Card */}
        <div className="bg-white shadow-xl rounded-2xl p-8 mb-8">
          <h3 className="text-lg font-bold mb-5 text-gray-700">Upload New Answer Key</h3>

          {message && (
            <div className={`text-sm px-4 py-2 rounded-lg mb-4 ${
              message.type === "error"
                ? "bg-red-50 border border-red-200 text-red-600"
                : "bg-green-50 border border-green-200 text-green-700"
            }`}>
              {message.text}
            </div>
          )}

          <div className="grid md:grid-cols-2 gap-5 mb-5">
            <div>
              <label className="block font-semibold text-sm text-gray-700 mb-1">
                Exam ID / Question Paper Code
              </label>
              <input
                type="text"
                value={examId}
                onChange={(e) => setExamId(e.target.value)}
                placeholder="e.g. 417, L5_839, EXAM_2025_01"
                className="w-full border-2 border-gray-300 rounded-xl px-4 py-2 focus:outline-none focus:border-orange-400 text-sm"
              />
            </div>

            <div>
              <label className="block font-semibold text-sm text-gray-700 mb-1">
                Answer Key PDF
              </label>
              <label className="flex items-center gap-2 cursor-pointer border-2 border-dashed border-gray-300 rounded-xl px-4 py-2 hover:border-orange-400">
                <Upload size={16} className="text-orange-400" />
                <span className="text-sm text-gray-500 truncate">
                  {keyFile ? keyFile.name : "Choose PDF file"}
                </span>
                <input
                  type="file"
                  accept=".pdf"
                  className="hidden"
                  onChange={(e) => setKeyFile(e.target.files[0])}
                />
              </label>
            </div>
          </div>

          <button
            onClick={handleUpload}
            disabled={loading}
            className={`px-6 py-2 rounded-xl font-semibold text-sm flex items-center gap-2 ${
              loading
                ? "bg-orange-300 cursor-not-allowed text-white"
                : "bg-orange-500 hover:bg-orange-600 text-white"
            }`}
          >
            <Upload size={16} />
            {loading ? "Extracting & Storing..." : "Upload & Store Key"}
          </button>
        </div>

        {/* Keys Table */}
        <div className="bg-white shadow-xl rounded-2xl overflow-hidden">
          <div className="bg-orange-500 px-6 py-3">
            <h3 className="text-white font-bold">Stored Answer Keys</h3>
          </div>

          {keys.length === 0 ? (
            <div className="p-8 text-center text-gray-400">
              No answer keys stored yet
            </div>
          ) : (
            <table className="w-full border-collapse text-sm">
              <thead className="bg-gray-50 text-gray-600">
                <tr>
                  <th className="p-4 text-left border-b">Exam ID</th>
                  <th className="p-4 text-left border-b">Questions</th>
                  <th className="p-4 text-left border-b">Uploaded By</th>
                  <th className="p-4 text-left border-b">Date</th>
                  <th className="p-4 text-center border-b">Actions</th>
                </tr>
              </thead>
              <tbody>
                {keys.map((k, i) => (
                  <tr key={i} className="border-b hover:bg-gray-50">
                    <td className="p-4 font-mono font-semibold text-orange-600">{k.exam_id}</td>
                    <td className="p-4">{k.question_count || "—"}</td>
                    <td className="p-4 text-gray-500">{k.uploaded_by || "—"}</td>
                    <td className="p-4 text-gray-400">
                      {k.created_at ? new Date(k.created_at).toLocaleDateString() : "—"}
                    </td>
                    <td className="p-4 text-center flex justify-center gap-2">
                      <button
                        onClick={() => handlePreview(k.exam_id)}
                        className="bg-blue-100 hover:bg-blue-200 p-2 rounded-lg"
                        title="Preview key"
                      >
                        <Eye size={16} className="text-blue-600" />
                      </button>
                      <button
                        onClick={() => handleDelete(k.exam_id)}
                        className="bg-red-100 hover:bg-red-200 p-2 rounded-lg"
                        title="Delete"
                      >
                        <Trash2 size={16} className="text-red-600" />
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      </div>

      {/* Preview Modal */}
      {preview && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex justify-center items-center z-50">
          <div className="bg-white rounded-2xl p-6 w-[480px] max-h-[80vh] overflow-y-auto shadow-2xl">
            <h3 className="text-lg font-bold mb-4">
              Answer Key: <span className="text-orange-500">{preview.exam_id}</span>
            </h3>
            <table className="w-full text-sm border-collapse">
              <thead className="bg-gray-100">
                <tr>
                  <th className="p-2 text-left border">Q #</th>
                  <th className="p-2 text-left border">Answer</th>
                </tr>
              </thead>
              <tbody>
                {Object.entries(preview.key_data)
                  .sort(([a], [b]) => parseInt(a) - parseInt(b))
                  .map(([q, a]) => (
                    <tr key={q} className="border-b hover:bg-gray-50">
                      <td className="p-2 border font-semibold text-gray-600">{q}</td>
                      <td className="p-2 border font-mono">{a}</td>
                    </tr>
                  ))}
              </tbody>
            </table>
            <button
              onClick={() => setPreview(null)}
              className="mt-4 w-full bg-orange-500 text-white py-2 rounded-xl font-semibold"
            >
              Close
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
