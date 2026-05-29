import clsx from "clsx";

interface Props {
  label: string;
  value: string | number;
  sub?: string;
  accent?: "default" | "green" | "amber" | "red" | "blue" | "purple";
}

const accentMap = {
  default: "border-slate-200 bg-white",
  green: "border-emerald-200 bg-emerald-50",
  amber: "border-amber-200 bg-amber-50",
  red: "border-red-200 bg-red-50",
  blue: "border-blue-200 bg-blue-50",
  purple: "border-purple-200 bg-purple-50",
};

export default function StatCard({ label, value, sub, accent = "default" }: Props) {
  return (
    <div className={clsx("rounded-xl border p-4", accentMap[accent])}>
      <div className="text-xs text-slate-500 uppercase tracking-wide">{label}</div>
      <div className="text-2xl font-bold mt-1 text-slate-800">{value}</div>
      {sub && <div className="text-xs text-slate-400 mt-0.5">{sub}</div>}
    </div>
  );
}
