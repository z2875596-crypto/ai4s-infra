import clsx from "clsx";

const colorMap: Record<string, string> = {
  success: "bg-emerald-500/20 text-emerald-400 border-emerald-500/30",
  completed: "bg-emerald-500/20 text-emerald-400 border-emerald-500/30",
  running: "bg-blue-500/20 text-blue-400 border-blue-500/30",
  active: "bg-blue-500/20 text-blue-400 border-blue-500/30",
  pending: "bg-amber-500/20 text-amber-400 border-amber-500/30",
  queued: "bg-amber-500/20 text-amber-400 border-amber-500/30",
  failed: "bg-red-500/20 text-red-400 border-red-500/30",
  error: "bg-red-500/20 text-red-400 border-red-500/30",
  cancelled: "bg-gray-500/20 text-gray-400 border-gray-500/30",
  warn: "bg-orange-500/20 text-orange-400 border-orange-500/30",
  critical: "bg-red-600/30 text-red-300 border-red-500/50",
  info: "bg-sky-500/20 text-sky-400 border-sky-500/30",
  idle: "bg-gray-500/20 text-gray-400 border-gray-500/30",
  offline: "bg-gray-700/30 text-gray-500 border-gray-600/30",
  healthy: "bg-emerald-500/20 text-emerald-400 border-emerald-500/30",
  degraded: "bg-amber-500/20 text-amber-400 border-amber-500/30",
};

export default function StatusBadge({ status }: { status: string }) {
  const key = status.toLowerCase();
  const cls = colorMap[key] || "bg-gray-500/20 text-gray-400 border-gray-500/30";
  return (
    <span className={clsx("px-2 py-0.5 rounded-full text-xs font-medium border", cls)}>
      {status}
    </span>
  );
}
