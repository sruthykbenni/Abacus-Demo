import { Edit } from "lucide-react";

export default function ExamTable({ exams, navigate }) {
  return (
    <div className="bg-white shadow-xl rounded-2xl overflow-hidden">

      <table className="w-full">

        <thead className="bg-orange-500 text-white">
          <tr>
            <th className="p-4">Exam ID</th>
            <th>Date</th>
            <th>Submission</th>
            <th>Total</th>
            <th>Mark</th>
            <th>Accuracy</th>
            <th>Edit</th>
          </tr>
        </thead>

        <tbody>
          {exams.map((e, i) => (
            <tr key={i} className="border-t hover:bg-gray-50">

              <td className="p-4">{e.examId}</td>
              <td>{e.date}</td>
              <td>{e.submissionId}</td>
              <td>{e.total}</td>
              <td>{e.mark}</td>
              <td>{e.accuracy}%</td>

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
  );
}