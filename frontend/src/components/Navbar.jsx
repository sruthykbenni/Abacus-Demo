import { GraduationCap, LogOut, KeyRound } from "lucide-react";
import { Link, useLocation, useNavigate } from "react-router-dom";

export default function Navbar() {
  const location = useLocation();
  const navigate  = useNavigate();

  const role     = sessionStorage.getItem("role");
  const username = sessionStorage.getItem("username");

  const handleLogout = () => {
    sessionStorage.clear();
    navigate("/login");
  };

  const isHome    = location.pathname === "/";
  const isLogin   = location.pathname === "/login";

  return (
    <div className="bg-white shadow-md px-8 py-4 flex justify-between items-center">

      <div className="flex items-center gap-3">
        <GraduationCap className="text-orange-500" size={28} />
        <h1 className="text-xl font-bold">SIP Evaluation</h1>
      </div>

      <div className="flex items-center gap-4">
        {!isLogin && !isHome && (
          <Link
            to="/"
            className="text-blue-600 hover:text-blue-800 underline text-sm"
          >
            Main Page
          </Link>
        )}

        {/* Answer Key Manager link (admin/teacher only) */}
        {!isLogin && (role === "admin" || role === "teacher") && (
          <Link
            to="/answer-keys"
            className="flex items-center gap-1 text-sm text-orange-600 hover:text-orange-800 font-medium"
          >
            <KeyRound size={15} />
            Answer Keys
          </Link>
        )}

        {username && !isLogin && (
          <span className="text-sm text-gray-500 capitalize">
            {role === "student" ? "👨‍🎓" : role === "teacher" ? "👨‍🏫" : "⚙️"} {username}
          </span>
        )}

        {!isLogin && username && (
          <button
            onClick={handleLogout}
            className="flex items-center gap-1 text-sm text-red-500 hover:text-red-700"
          >
            <LogOut size={15} />
            Logout
          </button>
        )}

        {isLogin && (
          <div className="text-sm text-gray-500">Sign in to continue</div>
        )}
      </div>

    </div>
  );
}
