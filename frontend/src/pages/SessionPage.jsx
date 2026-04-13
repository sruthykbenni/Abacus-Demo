import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import Navbar from "../components/Navbar";
import StudentTable from "../components/StudentTable";

export default function SessionPage() {
  const navigate = useNavigate();
  const [students, setStudents] = useState([]);

  useEffect(() => {
    // Replace with API later
    setStudents([
      { id: 101, name: "Rahul" },
      { id: 102, name: "Anjali" },
      { id: 103, name: "Kiran" }
    ]);
  }, []);

  return (
    <div className="min-h-screen bg-gray-100">

      <Navbar />

      <div className="p-10">

        <h2 className="text-3xl font-bold mb-6">
          Session SIP 01
        </h2>

        <StudentTable students={students} navigate={navigate} />

      </div>
    </div>
  );
}