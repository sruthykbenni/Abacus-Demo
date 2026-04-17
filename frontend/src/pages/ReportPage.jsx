import { useParams, useNavigate } from "react-router-dom";
import { Edit, User } from "lucide-react";
import { useState, useEffect } from "react";
import Navbar from "../components/Navbar";

export default function ReportPage() {
  const { studentId } = useParams();
  const navigate = useNavigate();

  const [showProfile, setShowProfile] = useState(false);

  // ✅ Load student profile from DB
  const [student, setStudent] = useState({
    name: "",
    contact: "",
    level: "",
    center: "",
  });

  // ✅ Load submissions from DB
  const [exams, setExams] = useState([]);

  useEffect(() => {
    // Fetch student profile
    fetch(`http://127.0.0.1:5000/students/${studentId}`)
      .then((r) => r.json())
      .then((data) => {
        if (!data.error) setStudent(data);
      })
      .catch((err) => console.error("Failed to load student:", err));

    // Fetch all submissions for this student
    fetch(`http://127.0.0.1:5000/students/${studentId}/submissions`)
      .then((r) => r.json())
      .then((data) => {
        if (Array.isArray(data)) setExams(data);
      })
      .catch((err) => console.error("Failed to load submissions:", err));
  }, [studentId]);

  return (
    <div className="min-h-screen bg-gray-100">

      <Navbar />

      <div className="p-10">

        {/* HEADER */}
        <div className="flex items-center gap-3 mb-6">
          <h2 className="text-2xl font-bold">
            {student.name || `Student ${studentId}`}'s Reports
          </h2>

          {/* PROFILE ICON */}
          <button
            onClick={() => setShowProfile(true)}
            className="bg-orange-100 p-2 rounded-lg hover:bg-orange-200"
          >
            <User className="text-orange-600" size={18} />
          </button>
        </div>

        {/* TABLE */}
        <div className="bg-white shadow-xl rounded-2xl overflow-hidden">

          <table className="w-full border-collapse">

            <thead className="bg-orange-500 text-white">
              <tr>
                <th className="p-4 border-r">Exam ID</th>
                <th className="border-r">Date</th>
                <th className="border-r">Submission</th>
                <th className="border-r">Total</th>
                <th className="border-r">Mark</th>
                <th className="border-r">Accuracy</th>
                <th>Edit</th>
              </tr>
            </thead>

            <tbody>
              {exams.length === 0 ? (
                <tr>
                  <td colSpan={7} className="p-6 text-center text-gray-400">
                    No submissions found
                  </td>
                </tr>
              ) : (
                exams.map((e, i) => (
                  <tr
                    key={i}
                    className="border-t text-center hover:bg-gray-50"
                  >
                    <td className="p-4 border-r">{e.exam_id}</td>
                    <td className="border-r">{e.date}</td>
                    <td className="border-r">{e.submission_id}</td>
                    <td className="border-r">{e.total_questions}</td>
                    <td className="border-r">{e.total_correct}</td>
                    <td className="border-r">{e.accuracy}%</td>

                    <td>
                      <button
                        onClick={() =>
                          navigate(`/evaluation/${e.submission_id}`)
                        }
                        className="bg-orange-100 p-2 rounded"
                      >
                        <Edit className="text-orange-600" />
                      </button>
                    </td>
                  </tr>
                ))
              )}
            </tbody>

          </table>
        </div>

      </div>

      {/* PROFILE MODAL */}
      {showProfile && (
        <div className="fixed inset-0 bg-black bg-opacity-40 flex justify-center items-center">

          <div className="bg-white rounded-xl p-6 w-[400px] shadow-xl">

            <h3 className="text-xl font-bold mb-4">
              Student Profile
            </h3>

            <div className="space-y-2 text-sm">
              <p><strong>Name:</strong> {student.name}</p>
              <p><strong>Contact:</strong> {student.contact}</p>
              <p><strong>Level:</strong> {student.level}</p>
              <p><strong>Center:</strong> {student.center}</p>
            </div>

            <button
              onClick={() => setShowProfile(false)}
              className="mt-5 w-full bg-orange-500 text-white py-2 rounded"
            >
              Close
            </button>

          </div>
        </div>
      )}
    </div>
  );
}
