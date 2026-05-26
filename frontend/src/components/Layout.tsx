import { NavLink, Outlet } from "react-router-dom";
import {
  Database, Bot, Cpu, Brain, Activity, Server,
} from "lucide-react";

const nav = [
  { to: "/data", label: "Data Pipeline", icon: Database },
  { to: "/agents", label: "Agent Tasks", icon: Bot },
  { to: "/hpc", label: "HPC Resources", icon: Cpu },
  { to: "/rlhf", label: "RLHF Training", icon: Brain },
];

export default function Layout() {
  return (
    <div className="flex h-screen bg-surface">
      {/* Sidebar */}
      <aside className="w-56 bg-surface-light border-r border-white/5 flex flex-col shrink-0">
        <div className="p-4 border-b border-white/5 flex items-center gap-2">
          <Server className="w-5 h-5 text-accent" />
          <span className="font-bold text-sm">AI4S Infra</span>
        </div>
        <nav className="flex-1 p-2 space-y-0.5">
          {nav.map(({ to, label, icon: Icon }) => (
            <NavLink
              key={to}
              to={to}
              className={({ isActive }) =>
                `flex items-center gap-2.5 px-3 py-2 rounded-lg text-sm transition-colors ${
                  isActive
                    ? "bg-accent/15 text-accent-light font-medium"
                    : "text-gray-400 hover:text-gray-200 hover:bg-white/5"
                }`
              }
            >
              <Icon className="w-4 h-4" />
              {label}
            </NavLink>
          ))}
        </nav>
        <div className="p-3 border-t border-white/5 text-xs text-gray-500 flex items-center gap-1.5">
          <Activity className="w-3 h-3 text-emerald-400" />
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
