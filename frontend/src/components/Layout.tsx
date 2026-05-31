import { NavLink, Outlet } from "react-router-dom";
import { FlaskConical, BookOpen, Beaker, Calculator, Brain } from "lucide-react";
import Logo from "./Logo";

const nav = [
  { to: "/agent", label: "AI 研究助手", icon: Brain },
  { to: "/database", label: "分子数据库", icon: FlaskConical },
  { to: "/literature", label: "文献调研", icon: BookOpen },
  { to: "/prediction", label: "性质预测", icon: Beaker },
  { to: "/experiments", label: "化学计算工具箱", icon: Calculator },
];

export default function Layout() {
  return (
    <div className="flex h-screen bg-slate-50">
      {/* Sidebar */}
      <aside className="w-56 bg-white border-r border-slate-200 flex flex-col shrink-0">
        <div className="p-4 border-b border-slate-100 flex items-center gap-2.5">
          <Logo size="small" />
          <div className="flex items-baseline gap-1.5">
            <span className="font-bold text-sm" style={{ color: "#6366F1" }}>鸢见</span>
            <span className="text-[10px]" style={{ color: "#6366F1" }}>AI4S</span>
          </div>
        </div>
        <nav className="flex-1 p-3 space-y-1">
          {nav.map(({ to, label, icon: Icon }) => (
            <NavLink
              key={to}
              to={to}
              className={({ isActive }) =>
                `flex items-center gap-2.5 px-3 py-2.5 rounded-lg text-sm font-medium transition-colors ${
                  isActive
                    ? "bg-brand-50 text-brand-700"
                    : "text-slate-500 hover:text-slate-700 hover:bg-slate-50"
                }`
              }
            >
              <Icon className="w-4 h-4" />
              {label}
            </NavLink>
          ))}
        </nav>
        <div className="p-3 border-t border-slate-100 text-xs text-slate-400 flex items-center gap-1.5">
          <span className="w-1.5 h-1.5 rounded-full bg-emerald-500" />
          API: localhost:8000
        </div>
      </aside>

      {/* Main */}
      <main className="flex-1 overflow-auto">
        <div className="p-6 max-w-7xl mx-auto">
          <Outlet />
        </div>
      </main>
    </div>
  );
}
