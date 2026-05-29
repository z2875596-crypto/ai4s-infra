import clsx from "clsx";

const colorMap: Record<string, string> = {
  success: "bg-emerald-100 text-emerald-700 border-emerald-200",
  completed: "bg-emerald-100 text-emerald-700 border-emerald-200",
  running: "bg-blue-100 text-blue-700 border-blue-200",
  active: "bg-blue-100 text-blue-700 border-blue-200",
  pending: "bg-amber-100 text-amber-700 border-amber-200",
  queued: "bg-amber-100 text-amber-700 border-amber-200",
  failed: "bg-red-100 text-red-700 border-red-200",
  error: "bg-red-100 text-red-700 border-red-200",
  cancelled: "bg-slate-100 text-slate-600 border-slate-200",
  warn: "bg-orange-100 text-orange-700 border-orange-200",
  critical: "bg-red-200 text-red-800 border-red-300",
  info: "bg-sky-100 text-sky-700 border-sky-200",
  idle: "bg-slate-100 text-slate-500 border-slate-200",
  offline: "bg-slate-100 text-slate-400 border-slate-200",
  healthy: "bg-emerald-100 text-emerald-700 border-emerald-200",
  degraded: "bg-amber-100 text-amber-700 border-amber-200",
};

export default function StatusBadge({ status }: { status: string }) {
  const key = status.toLowerCase();
  const cls = colorMap[key] || "bg-slate-100 text-slate-600 border-slate-200";
  return (
    <span className={clsx("px-2 py-0.5 rounded-full text-xs font-medium border", cls)}>
      {status}
    </span>
  );
}
