import { useParams, useNavigate } from "react-router-dom";
import { Edit, User } from "lucide-react";
import { useState } from "react";
import Navbar from "../components/Navbar";

export default function ReportPage() {
  const { studentId } = useParams();
  const navigate = useNavigate();

  const [showProfile, setShowProfile] = useState(false);

  // 🔌 Replace with API later
  const student = {
    name: "Rahul",
    contact: "9876543210",
    level: "Advanced Level 1",
    center: "Kochi Center"
  };

  const exams = [
    {
      examId: "EX101",
      date: "2026-04-05",
      submissionId: "SUB1",
      total: 60,
      mark: 55,
      accuracy: 91
    }
  ];

  return (
    <div className="min-h-screen bg-gray-100">

      <Navbar />

      <div className="p-10">

        {/* HEADER */}
        <div className="flex items-center gap-3 mb-6">
          <h2 className="text-2xl font-bold">
            Student {studentId} Reports
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
              {exams.map((e, i) => (
                <tr
                  key={i}
                  className="border-t text-center hover:bg-gray-50"
                >
                  <td className="p-4 border-r">{e.examId}</td>
                  <td className="border-r">{e.date}</td>
                  <td className="border-r">{e.submissionId}</td>
                  <td className="border-r">{e.total}</td>
                  <td className="border-r">{e.mark}</td>
                  <td className="border-r">{e.accuracy}%</td>

                  <td>
                    <button
                      onClick={() =>
                        navigate(`/evaluation/${e.submissionId}`)
                      }
                      className="bg-orange-100 p-2 rounded"
                    >
                      <Edit className="text-orange-600" />
                    </button>
                  </td>
                </tr>
              ))}
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