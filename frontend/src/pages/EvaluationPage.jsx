import { useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";

export default function EvaluationPage() {
  const location = useLocation();
  const navigate = useNavigate();

  const [results, setResults] = useState(
    location.state?.results || []
  );

  const [summary] = useState(
    location.state?.summary || null
  );

  const [editingIndex, setEditingIndex] = useState(null);
  const [editValue, setEditValue] = useState("");

  const [filterText, setFilterText] = useState("");
  const [sortOrder, setSortOrder] = useState("asc");
  const [remarkFilter, setRemarkFilter] = useState("all");

  if (!results.length) {
    return <div className="p-10">No data found</div>;
  }

  // ================= EDIT FUNCTION =================
  const handleEdit = (index, currentValue) => {
    setEditingIndex(index);
    setEditValue(currentValue);
  };

  const handleSaveEdit = (index) => {
    const updated = [...results];

    const correct = updated[index].correct_answer;

    updated[index].detected_answer = editValue;

    // 🔥 Recalculate remark
    if (editValue === correct) {
      updated[index].remark = "Correct";
    } else {
      updated[index].remark = "Wrong";
    }

    // 🔥 Mark as manually corrected
    updated[index].confidence = "Manually corrected";

    setResults(updated);
    setEditingIndex(null);
  };

  // ================= FILTER =================
  let displayed = results.filter((item) =>
    item.question.toString().includes(filterText)
  );

  if (remarkFilter !== "all") {
    displayed = displayed.filter((i) => i.remark === remarkFilter);
  }

  displayed = displayed.sort((a, b) =>
    sortOrder === "asc"
      ? a.question - b.question
      : b.question - a.question
  );

  // ================= DOWNLOAD =================
  const handleDownload = () => {
    const rows = [
      ["Question", "Detected", "Correct", "Remark", "Confidence"],
      ...results.map((r) => [
        r.question,
        r.detected_answer,
        r.correct_answer,
        r.remark,
        r.confidence,
      ]),
    ];

    const csvContent =
      "data:text/csv;charset=utf-8," +
      rows.map((e) => e.join(",")).join("\n");

    const link = document.createElement("a");
    link.href = encodeURI(csvContent);
    link.download = "evaluation_report.csv";
    link.click();
  };

  return (
    <div className="min-h-screen bg-gray-100 p-8">

      <div className="max-w-6xl mx-auto bg-white rounded-2xl shadow-xl p-8">

        {/* HEADER */}
        <div className="flex justify-between items-center mb-6">
          <h1 className="text-2xl font-bold">
            Evaluation Dashboard
          </h1>

          <div className="flex gap-3">
            <button
              onClick={handleDownload}
              className="bg-orange-500 hover:bg-orange-600 text-white px-4 py-2 rounded-lg"
            >
              Download Final Report
            </button>

            <button
              onClick={() => navigate(-1)}
              className="bg-gray-700 text-white px-4 py-2 rounded-lg"
            >
              Back
            </button>
          </div>
        </div>

        {/* FILTERS */}
        <div className="bg-gray-50 p-4 rounded-xl grid md:grid-cols-3 gap-4 mb-6">
          <input
            placeholder="Search Question No"
            value={filterText}
            onChange={(e) => setFilterText(e.target.value)}
            className="border px-3 py-2 rounded"
          />

          <select
            value={sortOrder}
            onChange={(e) => setSortOrder(e.target.value)}
            className="border px-3 py-2 rounded"
          >
            <option value="asc">Ascending</option>
            <option value="desc">Descending</option>
          </select>

          <select
            value={remarkFilter}
            onChange={(e) => setRemarkFilter(e.target.value)}
            className="border px-3 py-2 rounded"
          >
            <option value="all">All</option>
            <option value="Correct">Correct</option>
            <option value="Wrong">Wrong</option>
            <option value="Unable to read">Unable</option>
          </select>
        </div>

        {/* SUMMARY */}
        {summary && (
          <div className="grid grid-cols-3 gap-6 mb-8 text-center">
            <div className="bg-gray-50 p-5 rounded-xl shadow">
              <p>Total Questions</p>
              <p className="text-2xl font-bold">
                {summary.total_questions}
              </p>
            </div>

            <div className="bg-gray-50 p-5 rounded-xl shadow">
              <p>Total Correct</p>
              <p className="text-2xl font-bold text-green-600">
                {summary.total_correct}
              </p>
            </div>

            <div className="bg-gray-50 p-5 rounded-xl shadow">
              <p>Accuracy</p>
              <p className="text-2xl font-bold text-orange-500">
                {summary.accuracy}%
              </p>
            </div>
          </div>
        )}

        {/* QUESTIONS */}
        <div className="grid md:grid-cols-2 gap-6">

          {displayed.map((item, index) => (
            <div
              key={index}
              className="bg-gray-50 p-5 rounded-xl shadow flex gap-4"
            >

              <img
                src={`http://localhost:5000${item.image_url}`}
                className="w-24 h-24 border rounded"
              />

              <div className="flex-1">

                <h2 className="font-semibold mb-2">
                  Question {item.question}
                </h2>

                {/* EDITABLE FIELD */}
                {editingIndex === index ? (
                  <div className="flex gap-2 mb-2">
                    <input
                      value={editValue}
                      onChange={(e) => setEditValue(e.target.value)}
                      className="border px-2 py-1 rounded"
                    />
                    <button
                      onClick={() => handleSaveEdit(index)}
                      className="bg-orange-600 text-white px-2 rounded"
                    >
                      Save
                    </button>
                  </div>
                ) : (
                  <p>
                    <strong>Detected Answer:</strong>{" "}
                    {item.detected_answer}
                    <button
                      onClick={() =>
                        handleEdit(index, item.detected_answer)
                      }
                      className="ml-3 bg-gray-800 text-white px-2 py-1 text-sm rounded"
                    >
                      Edit
                    </button>
                  </p>
                )}

                <p>
                  <strong>Correct Answer:</strong>{" "}
                  {item.correct_answer}
                </p>

                <p>
                  <strong>Remark:</strong>{" "}
                  <span
                    className={
                      item.remark === "Correct"
                        ? "text-green-600"
                        : item.remark === "Wrong"
                        ? "text-red-600"
                        : "text-orange-500"
                    }
                  >
                    {item.remark}
                  </span>
                </p>

                <p>
                  <strong>Confidence:</strong>{" "}
                  {item.confidence}
                </p>

              </div>

            </div>
          ))}

        </div>

        {/* SAVE ALL */}
        <div className="mt-8 flex justify-center">
          <button
            onClick={() => alert("Changes saved")}
            className="bg-orange-500 hover:bg-orange-600 text-white px-8 py-3 rounded-lg font-semibold"
          >
            Save All Changes
          </button>
        </div>

      </div>
    </div>
  );
}