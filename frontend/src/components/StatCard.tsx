import clsx from "clsx";

interface Props {
  label: string;
  value: string | number;
  sub?: string;
  accent?: "default" | "green" | "amber" | "red" | "blue" | "purple";
}

const accentMap = {
  default: "border-accent/40 bg-accent/5",
  green: "border-emerald-500/40 bg-emerald-500/5",
  amber: "border-amber-500/40 bg-amber-500/5",
  red: "border-red-500/40 bg-red-500/5",
  blue: "border-blue-500/40 bg-blue-500/5",
  purple: "border-purple-500/40 bg-purple-500/5",
};

export default function StatCard({ label, value, sub, accent = "default" }: Props) {
  return (
    <div className={clsx("rounded-xl border p-4", accentMap[accent])}>
      <div className="text-xs text-gray-400 uppercase tracking-wide">{label}</div>
      <div className="text-2xl font-bold mt-1">{value}</div>
      {sub && <div className="text-xs text-gray-500 mt-0.5">{sub}</div>}
    </div>
  );
}
