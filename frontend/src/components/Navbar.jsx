import { GraduationCap } from "lucide-react";

export default function Navbar() {
  return (
    <div className="bg-white shadow-md px-8 py-4 flex justify-between items-center">

      <div className="flex items-center gap-3">
        <GraduationCap className="text-orange-500" size={28} />
        <h1 className="text-xl font-bold">SIP Evaluation</h1>
      </div>

      <div className="text-sm text-gray-500">
        Admin Panel
      </div>

    </div>
  );
}