import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { GraduationCap, LogIn } from "lucide-react";

export default function LoginPage() {
  const navigate  = useNavigate();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error,    setError]    = useState("");
  const [loading,  setLoading]  = useState(false);

  const handleLogin = async () => {
    setError("");
    if (!username.trim() || !password) {
      setError("Please enter username and password");
      return;
    }

    setLoading(true);
    try {
      const res  = await fetch("http://127.0.0.1:5000/login", {
        method:  "POST",
        headers: { "Content-Type": "application/json" },
        body:    JSON.stringify({ username: username.trim(), password }),
      });
      const data = await res.json();

      if (!res.ok || data.error) {
        setError(data.error || "Login failed");
        return;
      }

      // Store auth in sessionStorage
      sessionStorage.setItem("user_id",    data.user_id);
      sessionStorage.setItem("username",   data.username);
      sessionStorage.setItem("role",       data.role);
      if (data.student_id) {
        sessionStorage.setItem("student_id", data.student_id);
      }

      // Route by role
      if (data.role === "student") {
        navigate(`/upload/${data.student_id}`);
      } else {
        // teacher or admin → session page
        navigate("/");
      }
    } catch (err) {
      setError("Cannot connect to server");
    } finally {
      setLoading(false);
    }
  };

  const handleKeyDown = (e) => {
    if (e.key === "Enter") handleLogin();
  };

  return (
    <div className="min-h-screen bg-gray-100 flex items-center justify-center">
      <div className="bg-white shadow-2xl rounded-2xl p-10 w-[420px]">

        {/* Logo */}
        <div className="flex flex-col items-center mb-8">
          <div className="bg-orange-100 p-4 rounded-full mb-4">
            <GraduationCap className="text-orange-500" size={40} />
          </div>
          <h1 className="text-2xl font-bold text-gray-800">SIP Evaluation</h1>
          <p className="text-sm text-gray-500 mt-1">Sign in to continue</p>
        </div>

        {/* Error */}
        {error && (
          <div className="bg-red-50 border border-red-200 text-red-600 text-sm px-4 py-2 rounded-lg mb-4">
            {error}
          </div>
        )}

        {/* Fields */}
        <div className="space-y-4">
          <div>
            <label className="block text-sm font-semibold text-gray-700 mb-1">
              Username
            </label>
            <input
              type="text"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder="Enter username"
              className="w-full border-2 border-gray-300 rounded-xl px-4 py-2 focus:outline-none focus:border-orange-400 text-sm"
            />
          </div>

          <div>
            <label className="block text-sm font-semibold text-gray-700 mb-1">
              Password
            </label>
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder="Enter password"
              className="w-full border-2 border-gray-300 rounded-xl px-4 py-2 focus:outline-none focus:border-orange-400 text-sm"
            />
          </div>
        </div>

        <button
          onClick={handleLogin}
          disabled={loading}
          className={`mt-6 w-full py-3 rounded-xl font-semibold flex items-center justify-center gap-2 ${
            loading
              ? "bg-orange-300 cursor-not-allowed text-white"
              : "bg-orange-500 hover:bg-orange-600 text-white"
          }`}
        >
          {loading ? (
            "Signing in..."
          ) : (
            <>
              <LogIn size={18} />
              Sign In
            </>
          )}
        </button>

        {/* Role hint */}
        <div className="mt-6 bg-gray-50 rounded-xl p-4 text-xs text-gray-500 space-y-1">
          <p className="font-semibold text-gray-600 mb-2">Demo credentials</p>
          <p>👨‍🏫 Teacher: <span className="font-mono">teacher1 / teacher123</span></p>
          <p>👨‍🎓 Student: <span className="font-mono">rahul / student123</span></p>
          <p>⚙️ Admin: <span className="font-mono">admin / admin123</span></p>
        </div>

      </div>
    </div>
  );
}
