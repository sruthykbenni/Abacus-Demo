import { Upload, FileText } from "lucide-react";

export default function StudentTable({ students, navigate }) {
  return (
    <div className="bg-white shadow-xl rounded-2xl overflow-hidden">

      <table className="w-full text-left">

        <thead className="bg-orange-500 text-white">
          <tr>
            <th className="p-4">Student ID</th>
            <th>Name</th>
            <th className="text-center">Upload</th>
            <th className="text-center">Report</th>
          </tr>
        </thead>

        <tbody>
          {students.map((s, i) => (
            <tr
              key={s.id}
              className={`border-t hover:bg-gray-50 transition ${
                i % 2 === 0 ? "bg-gray-50" : ""
              }`}
            >
              <td className="p-4 font-medium">{s.id}</td>
              <td>{s.name}</td>

              <td className="text-center">
                <button
                  onClick={() => navigate(`/upload/${s.id}`)}
                  className="bg-orange-100 hover:bg-orange-200 p-2 rounded-lg"
                >
                  <Upload className="text-orange-600" />
                </button>
              </td>

              <td className="text-center">
                <button
                  onClick={() => navigate(`/report/${s.id}`)}
                  className="bg-gray-200 hover:bg-gray-300 p-2 rounded-lg"
                >
                  <FileText />
                </button>
              </td>

            </tr>
          ))}
        </tbody>

      </table>
    </div>
  );
}