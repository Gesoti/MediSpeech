import { Link, useLocation, useNavigate } from "react-router-dom";
import { Stethoscope, FolderOpen, FileText, LogOut } from "lucide-react";
import type { ReactNode } from "react";
import { useAuth } from "@/context/AuthContext";

interface LayoutProps {
  children: ReactNode;
}

const navItems = [
  { to: "/", label: "Cases", icon: FolderOpen },
  { to: "/reports", label: "Reports", icon: FileText },
];

export function Layout({ children }: LayoutProps) {
  const { pathname } = useLocation();
  const { logout } = useAuth();
  const navigate = useNavigate();

  const handleLogout = () => {
    logout();
    navigate("/login", { replace: true });
  };

  return (
    <div className="min-h-screen flex flex-col">
      <header className="bg-white border-b border-slate-200 shadow-sm">
        <div className="max-w-6xl mx-auto px-4 h-14 flex items-center gap-6">
          <Link to="/" className="flex items-center gap-2 font-semibold text-primary-700">
            <Stethoscope size={20} />
            <span>MediSpeech</span>
          </Link>
          <nav className="flex gap-1 flex-1">
            {navItems.map(({ to, label, icon: Icon }) => (
              <Link
                key={to}
                to={to}
                className={`flex items-center gap-1.5 px-3 py-1.5 rounded-md text-sm font-medium transition-colors ${
                  (to === "/" ? pathname === "/" : pathname.startsWith(to))
                    ? "bg-primary-50 text-primary-700"
                    : "text-slate-600 hover:bg-slate-100"
                }`}
              >
                <Icon size={15} />
                {label}
              </Link>
            ))}
          </nav>
          <button
            onClick={handleLogout}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-md text-sm font-medium text-slate-500 hover:bg-slate-100 hover:text-slate-700 transition-colors"
          >
            <LogOut size={15} />
            Sign out
          </button>
        </div>
      </header>
      <main className="flex-1 max-w-6xl mx-auto w-full px-4 py-6">{children}</main>
    </div>
  );
}
