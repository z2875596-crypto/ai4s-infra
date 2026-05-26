import { useEffect, useState, useCallback } from "react";
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
  LineChart, Line, AreaChart, Area,
} from "recharts";
import { hpcAPI } from "@/api/client";
import type { ClusterSnapshot, SchedulerStatus, HPCJob, NodeDetail, Anomaly, AlertInfo, CapacityHeadroom } from "@/types";
import StatCard from "@/components/StatCard";
import StatusBadge from "@/components/StatusBadge";
import { RefreshCw, AlertTriangle, Bell, Server, Cpu, HardDrive, Activity } from "lucide-react";

type Tab = "overview" | "jobs" | "nodes" | "alerts";

export default function HPCResources() {
  const [tab, setTab] = useState<Tab>("overview");

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-xl font-bold">HPC Resources</h1>
        <span className="text-xs text-gray-500">HPC Fusion</span>
      </div>

      <div className="flex gap-1 mb-6 border-b border-white/5 pb-0">
        {(["overview", "jobs", "nodes", "alerts"] as const).map((t) => (
          <button
            key={t}
            onClick={() => setTab(t)}
            className={`px-4 py-2 text-sm font-medium rounded-t-lg transition-colors ${
              tab === t ? "bg-accent/15 text-accent-light border-b-2 border-accent" : "text-gray-400 hover:text-gray-200"
            }`}
          >
            {t === "overview" ? "Overview" : t === "jobs" ? "Jobs" : t === "nodes" ? "Nodes" : "Alerts"}
          </button>
        ))}
      </div>

      {tab === "overview" && <OverviewTab />}
      {tab === "jobs" && <JobsTab />}
      {tab === "nodes" && <NodesTab />}
      {tab === "alerts" && <AlertsTab />}
    </div>
  );
}

// ── Overview Tab ──────────────────────────────────────────

function OverviewTab() {
  const [scheduler, setScheduler] = useState<SchedulerStatus | null>(null);
  const [cluster, setCluster] = useState<ClusterSnapshot | null>(null);
  const [headroom, setHeadroom] = useState<CapacityHeadroom | null>(null);
  const [anomalies, setAnomalies] = useState<Anomaly[]>([]);
  const [health, setHealth] = useState<{ status: string; utilization: Record<string, number>; anomalies: number } | null>(null);

  const load = useCallback(async () => {
    try {
      const [sch, cl, hr, an, h] = await Promise.all([
        hpcAPI.schedulerStatus(), hpcAPI.clusterMetrics(),
        hpcAPI.capacityHeadroom(), hpcAPI.detectAnomalies(), hpcAPI.clusterHealth(),
      ]);
      setScheduler(sch); setCluster(cl); setHeadroom(hr); setAnomalies(an.anomalies); setHealth(h);
    } catch { /* backend may not be running */ }
  }, []);

  useEffect(() => { load(); const i = setInterval(load, 10000); return () => clearInterval(i); }, [load]);

  const chartData = cluster ? [
    { name: "GPU", value: cluster.avg_gpu_util, max: cluster.max_gpu_util },
    { name: "CPU", value: cluster.avg_cpu_util, max: cluster.avg_cpu_util },
    { name: "Memory", value: cluster.avg_mem_util, max: cluster.avg_mem_util },
  ] : [];

  return (
    <div className="space-y-6">
      {/* Stats row */}
      <div className="grid grid-cols-2 lg:grid-cols-5 gap-3">
        <StatCard label="Cluster Status" value={health?.status || "unknown"} accent={health?.status === "healthy" ? "green" : "amber"} />
        <StatCard label="Nodes" value={cluster?.nodes || 0} accent="blue" />
        <StatCard label="GPU Util Avg" value={`${cluster?.avg_gpu_util.toFixed(1) || 0}%`} accent={cluster && cluster.avg_gpu_util > 80 ? "amber" : "green"} />
        <StatCard label="Jobs Running" value={scheduler?.running || 0} accent="blue" />
        <StatCard label="Jobs Pending" value={scheduler?.pending || 0} accent={scheduler && scheduler.pending > 10 ? "amber" : "default"} />
      </div>

      {/* Charts */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <div className="bg-surface-light rounded-xl border border-white/5 p-5">
          <h2 className="text-sm font-semibold mb-4">Utilization</h2>
          <ResponsiveContainer width="100%" height={220}>
            <BarChart data={chartData}>
              <CartesianGrid strokeDasharray="3 3" stroke="#334155" />
              <XAxis dataKey="name" stroke="#94a3b8" fontSize={12} />
              <YAxis stroke="#94a3b8" fontSize={12} domain={[0, 100]} />
              <Tooltip contentStyle={{ background: "#1e293b", border: "1px solid #334155", borderRadius: 8, fontSize: 12 }} />
              <Bar dataKey="value" fill="#6366f1" radius={[4, 4, 0, 0]} name="Average" />
              <Bar dataKey="max" fill="#818cf8" radius={[4, 4, 0, 0]} name="Max" opacity={0.6} />
            </BarChart>
          </ResponsiveContainer>
        </div>

        <div className="bg-surface-light rounded-xl border border-white/5 p-5">
          <h2 className="text-sm font-semibold mb-4">Capacity Headroom</h2>
          {headroom && (
            <div className="space-y-4">
              <div>
                <div className="flex justify-between text-sm mb-1"><span className="text-gray-400">GPU Used</span><span>{headroom.avg_gpu_utilization_pct.toFixed(1)}%</span></div>
                <div className="w-full bg-surface rounded-full h-2"><div className="bg-accent h-2 rounded-full" style={{ width: `${headroom.avg_gpu_utilization_pct}%` }} /></div>
              </div>
              <div className="grid grid-cols-2 gap-3 text-sm">
                <div className="bg-surface rounded-lg p-3">
                  <div className="text-gray-400">Free GPUs</div>
                  <div className="text-xl font-bold">{headroom.estimated_free_gpus}</div>
                </div>
                <div className="bg-surface rounded-lg p-3">
                  <div className="text-gray-400">Remaining</div>
                  <div className="text-xl font-bold">{headroom.remaining_capacity_pct.toFixed(0)}%</div>
                </div>
              </div>
            </div>
          )}
        </div>
      </div>

      {/* Anomalies */}
      {anomalies.length > 0 && (
        <div className="bg-surface-light rounded-xl border border-red-500/20 p-5">
          <h2 className="text-sm font-semibold mb-3 flex items-center gap-2 text-red-400"><AlertTriangle className="w-4 h-4" /> Anomalies ({anomalies.length})</h2>
          <div className="space-y-2">
            {anomalies.map((a, i) => (
              <div key={i} className="flex items-center justify-between bg-surface rounded-lg p-3 text-sm">
                <div><span className="font-mono text-gray-400">{a.node}</span> &mdash; {a.metric}</div>
                <div className="flex items-center gap-2">
                  <span className="text-xs text-gray-500">{a.message}</span>
                  <StatusBadge status={a.severity} />
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Scheduler info */}
      {scheduler && (
        <div className="bg-surface-light rounded-xl border border-white/5 p-5">
          <h2 className="text-sm font-semibold mb-3">Scheduler</h2>
          <div className="grid grid-cols-4 gap-4 text-sm">
            <div><span className="text-gray-400">Policy:</span> <span className="font-medium">{scheduler.policy}</span></div>
            <div><span className="text-gray-400">Preemption:</span> <StatusBadge status={scheduler.preemption_enabled ? "active" : "offline"} /></div>
            <div><span className="text-gray-400">Backfill:</span> <StatusBadge status={scheduler.backfill_enabled ? "active" : "offline"} /></div>
            <div><span className="text-gray-400">Total Submitted:</span> <span className="font-medium">{scheduler.total_submitted || 0}</span></div>
          </div>
        </div>
      )}
    </div>
  );
}

// ── Jobs Tab ────────────────────────────────────────────────

function JobsTab() {
  const [jobs, setJobs] = useState<HPCJob[]>([]);
  const [form, setForm] = useState({
    name: "ai4s-job", connector: "slurm", nodes: "1", gpus: "1",
    cpus: "4", memory_mb: "32000", partition: "gpu", time_minutes: "60",
    script: "#!/bin/bash\nhostname", priority: "5", user: "unknown", project: "default",
  });
  const [result, setResult] = useState("");

  const loadJobs = async () => {
    try { setJobs((await hpcAPI.listJobs("slurm")).jobs); } catch { /* offline */ }
  };
  useEffect(() => { loadJobs(); const i = setInterval(loadJobs, 8000); return () => clearInterval(i); }, []);

  const submit = async () => {
    try {
      const res = await hpcAPI.submitJob({
        ...form, nodes: parseInt(form.nodes), gpus: parseInt(form.gpus),
        cpus: parseInt(form.cpus), memory_mb: parseInt(form.memory_mb),
        time_minutes: parseInt(form.time_minutes), priority: parseInt(form.priority),
      });
      setResult(JSON.stringify(res, null, 2));
      loadJobs();
    } catch (e: unknown) { setResult(`Error: ${(e as Error).message}`); }
  };

  const cancel = async (id: string) => { await hpcAPI.cancelJob(id); loadJobs(); };

  return (
    <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
      <div className="bg-surface-light rounded-xl border border-white/5 p-5">
        <h2 className="text-sm font-semibold mb-3">Submit Job</h2>
        <div className="space-y-2">
          <div className="grid grid-cols-2 gap-2">
            <input className="bg-surface border border-white/10 rounded-lg px-3 py-2 text-sm" placeholder="Name" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} />
            <select className="bg-surface border border-white/10 rounded-lg px-3 py-2 text-sm" value={form.connector} onChange={(e) => setForm({ ...form, connector: e.target.value })}>
              <option value="slurm">Slurm</option><option value="k8s">Kubernetes</option>
            </select>
          </div>
          <div className="grid grid-cols-3 gap-2">
            <input className="bg-surface border border-white/10 rounded-lg px-3 py-2 text-sm" placeholder="Nodes" type="number" value={form.nodes} onChange={(e) => setForm({ ...form, nodes: e.target.value })} />
            <input className="bg-surface border border-white/10 rounded-lg px-3 py-2 text-sm" placeholder="GPUs" type="number" value={form.gpus} onChange={(e) => setForm({ ...form, gpus: e.target.value })} />
            <input className="bg-surface border border-white/10 rounded-lg px-3 py-2 text-sm" placeholder="CPUs" type="number" value={form.cpus} onChange={(e) => setForm({ ...form, cpus: e.target.value })} />
          </div>
          <div className="grid grid-cols-2 gap-2">
            <input className="bg-surface border border-white/10 rounded-lg px-3 py-2 text-sm" placeholder="Memory MB" type="number" value={form.memory_mb} onChange={(e) => setForm({ ...form, memory_mb: e.target.value })} />
            <input className="bg-surface border border-white/10 rounded-lg px-3 py-2 text-sm" placeholder="Partition" value={form.partition} onChange={(e) => setForm({ ...form, partition: e.target.value })} />
          </div>
          <textarea className="w-full bg-surface border border-white/10 rounded-lg px-3 py-2 text-sm font-mono h-20" placeholder="Script" value={form.script} onChange={(e) => setForm({ ...form, script: e.target.value })} />
          <button onClick={submit} className="w-full bg-accent py-2 rounded-lg text-sm font-medium">Submit Job</button>
        </div>
        {result && <pre className="mt-3 p-3 bg-surface rounded-lg text-xs text-gray-400 overflow-auto max-h-32">{result}</pre>}
      </div>

      <div className="lg:col-span-2 bg-surface-light rounded-xl border border-white/5 overflow-hidden">
        <table className="w-full text-sm">
          <thead><tr className="border-b border-white/5 text-gray-400 text-left"><th className="p-3">Job ID</th><th className="p-3">Name</th><th className="p-3">State</th><th className="p-3">Partition</th><th className="p-3">Nodes</th><th className="p-3">GPUs</th><th className="p-3"></th></tr></thead>
          <tbody>
            {jobs.map((j) => (
              <tr key={j.job_id} className="border-b border-white/5 hover:bg-white/5">
                <td className="p-3 font-mono text-xs">{j.job_id}</td>
                <td className="p-3">{j.name}</td>
                <td className="p-3"><StatusBadge status={j.state} /></td>
                <td className="p-3 text-gray-400">{j.partition}</td>
                <td className="p-3">{j.nodes}</td>
                <td className="p-3">{j.gpus_per_node}</td>
                <td className="p-3">
                  {j.state === "running" && (
                    <button onClick={() => cancel(j.job_id)} className="text-xs text-red-400 hover:text-red-300">Cancel</button>
                  )}
                </td>
              </tr>
            ))}
            {jobs.length === 0 && <tr><td colSpan={7} className="p-6 text-center text-gray-500">No jobs found.</td></tr>}
          </tbody>
        </table>
      </div>
    </div>
  );
}

// ── Nodes Tab ───────────────────────────────────────────────

function NodesTab() {
  const [nodes, setNodes] = useState<NodeDetail[]>([]);
  const [connector, setConnector] = useState("slurm");

  const load = async () => {
    try { setNodes((await hpcAPI.listNodes(connector)).nodes); } catch { setNodes([]); }
  };
  useEffect(() => { load(); }, [connector]);

  const nodeChartData = nodes.map((n) => ({
    name: n.node_id,
    gpu_used: n.gpu_total - n.gpu_free,
    gpu_free: n.gpu_free,
  }));

  return (
    <div className="space-y-6">
      <div className="flex gap-2 items-center">
        <select className="bg-surface-light border border-white/10 rounded-lg px-3 py-2 text-sm" value={connector} onChange={(e) => setConnector(e.target.value)}>
          <option value="slurm">Slurm</option><option value="k8s">Kubernetes</option>
        </select>
        <span className="text-sm text-gray-400">{nodes.length} nodes</span>
      </div>

      {nodeChartData.length > 0 && (
        <div className="bg-surface-light rounded-xl border border-white/5 p-5">
          <h2 className="text-sm font-semibold mb-4">GPU Allocation by Node</h2>
          <ResponsiveContainer width="100%" height={Math.max(200, nodes.length * 36)}>
            <BarChart data={nodeChartData} layout="vertical">
              <CartesianGrid strokeDasharray="3 3" stroke="#334155" />
              <XAxis type="number" stroke="#94a3b8" fontSize={12} />
              <YAxis type="category" dataKey="name" stroke="#94a3b8" fontSize={11} width={100} />
              <Tooltip contentStyle={{ background: "#1e293b", border: "1px solid #334155", borderRadius: 8, fontSize: 12 }} />
              <Bar dataKey="gpu_used" fill="#6366f1" stackId="a" radius={[0, 0, 0, 0]} name="GPU Used" />
              <Bar dataKey="gpu_free" fill="#334155" stackId="a" radius={[0, 4, 4, 0]} name="GPU Free" />
            </BarChart>
          </ResponsiveContainer>
        </div>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-3">
        {nodes.map((n) => (
          <div key={n.node_id} className="bg-surface-light rounded-xl border border-white/5 p-4">
            <div className="flex items-center justify-between mb-2">
              <span className="font-mono text-sm">{n.node_id}</span>
              <StatusBadge status={n.state} />
            </div>
            <div className="space-y-1 text-xs text-gray-400">
              <div className="flex justify-between"><span>GPUs</span><span className="text-gray-200">{n.gpu_total - n.gpu_free}/{n.gpu_total}</span></div>
              <div className="w-full bg-surface rounded-full h-1.5 mt-1">
                <div className="bg-accent h-1.5 rounded-full" style={{ width: `${n.gpu_total ? ((n.gpu_total - n.gpu_free) / n.gpu_total) * 100 : 0}%` }} />
              </div>
              <div className="flex justify-between mt-1"><span>CPUs Free</span><span>{n.cpu_free}</span></div>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

// ── Alerts Tab ──────────────────────────────────────────────

function AlertsTab() {
  const [alerts, setAlerts] = useState<AlertInfo[]>([]);
  const [form, setForm] = useState({ title: "", message: "", severity: "warn" });
  const [submitted, setSubmitted] = useState(false);

  const load = async () => {
    try { setAlerts((await hpcAPI.activeAlerts()).alerts); } catch { /* no backend */ }
  };
  useEffect(() => { load(); }, []);

  const send = async () => {
    await hpcAPI.sendAlert(form.title, form.message, form.severity);
    setForm({ title: "", message: "", severity: "warn" });
    setSubmitted(true);
    load();
    setTimeout(() => setSubmitted(false), 3000);
  };

  const resolve = async (id: string) => { await hpcAPI.resolveAlert(id); load(); };

  return (
    <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
      <div className="bg-surface-light rounded-xl border border-white/5 p-5">
        <h2 className="text-sm font-semibold mb-3 flex items-center gap-2"><Bell className="w-4 h-4 text-amber-400" /> Send Alert</h2>
        <div className="space-y-2">
          <input className="w-full bg-surface border border-white/10 rounded-lg px-3 py-2 text-sm" placeholder="Title" value={form.title} onChange={(e) => setForm({ ...form, title: e.target.value })} />
          <textarea className="w-full bg-surface border border-white/10 rounded-lg px-3 py-2 text-sm h-20" placeholder="Message" value={form.message} onChange={(e) => setForm({ ...form, message: e.target.value })} />
          <select className="w-full bg-surface border border-white/10 rounded-lg px-3 py-2 text-sm" value={form.severity} onChange={(e) => setForm({ ...form, severity: e.target.value })}>
            <option value="info">Info</option><option value="warn">Warning</option><option value="critical">Critical</option>
          </select>
          <button onClick={send} className="w-full bg-amber-600 py-2 rounded-lg text-sm">Send Alert</button>
        </div>
        {submitted && <div className="mt-3 text-sm text-emerald-400">Alert sent!</div>}
      </div>

      <div className="lg:col-span-2 bg-surface-light rounded-xl border border-white/5 p-5">
        <h2 className="text-sm font-semibold mb-3">Active Alerts ({alerts.length})</h2>
        <div className="space-y-2">
          {alerts.map((a) => (
            <div key={a.alert_id} className="flex items-center justify-between bg-surface rounded-lg p-3 text-sm">
              <div className="flex items-center gap-3">
                <StatusBadge status={a.severity} />
                <div>
                  <div className="font-medium">{a.title}</div>
                  <div className="text-xs text-gray-500">{a.message}</div>
                </div>
              </div>
              <button onClick={() => resolve(a.alert_id)} className="text-xs text-emerald-400 hover:text-emerald-300 px-2 py-1 rounded border border-emerald-500/30">Resolve</button>
            </div>
          ))}
          {alerts.length === 0 && <p className="text-gray-500 text-sm">No active alerts.</p>}
        </div>
      </div>
    </div>
  );
}
