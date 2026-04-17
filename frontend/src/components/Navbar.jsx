import { GraduationCap } from "lucide-react";
import { Link, useLocation } from "react-router-dom";

export default function Navbar() {
  const location = useLocation();

  return (
    <div className="bg-white shadow-md px-8 py-4 flex justify-between items-center">

      <div className="flex items-center gap-3">
        <GraduationCap className="text-orange-500" size={28} />
        <h1 className="text-xl font-bold">SIP Evaluation</h1>
      </div>

      <div className="flex items-center gap-4">
        {location.pathname !== "/" && (
          <Link
            to="/"
            className="text-blue-600 hover:text-blue-800 underline text-sm"
          >
            Return to Main Page
          </Link>
        )}
        <div className="text-sm text-gray-500">
          Admin Panel
        </div>
      </div>

    </div>
  );
}