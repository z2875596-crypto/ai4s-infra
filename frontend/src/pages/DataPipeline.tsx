import { useEffect, useState, useCallback } from "react";
import { dataAPI } from "@/api/client";
import type { CatalogEntry, Snapshot, IngestionReport } from "@/types";
import StatCard from "@/components/StatCard";
import StatusBadge from "@/components/StatusBadge";
import { RefreshCw, Play, Search, Plus, Trash2, GitBranch, Server } from "lucide-react";

type Tab = "ingestion" | "catalog" | "snapshots" | "lineage";

export default function DataPipeline() {
  const [tab, setTab] = useState<Tab>("ingestion");
  const [loading, setLoading] = useState(false);

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-xl font-bold">Data Pipeline</h1>
        <button onClick={() => window.location.reload()} className="flex items-center gap-1.5 text-sm text-gray-400 hover:text-white">
          <RefreshCw className="w-4 h-4" /> Refresh
        </button>
      </div>

      {/* Tab bar */}
      <div className="flex gap-1 mb-6 border-b border-white/5 pb-0">
        {(["ingestion", "catalog", "snapshots", "lineage"] as const).map((t) => (
          <button
            key={t}
            onClick={() => setTab(t)}
            className={`px-4 py-2 text-sm font-medium rounded-t-lg transition-colors ${
              tab === t
                ? "bg-accent/15 text-accent-light border-b-2 border-accent"
                : "text-gray-400 hover:text-gray-200"
            }`}
          >
            {t === "ingestion" ? "Ingestion" : t === "catalog" ? "Catalog" : t === "snapshots" ? "Snapshots" : "Lineage"}
          </button>
        ))}
      </div>

      {tab === "ingestion" && <IngestionTab />}
      {tab === "catalog" && <CatalogTab />}
      {tab === "snapshots" && <SnapshotsTab />}
      {tab === "lineage" && <LineageTab />}
    </div>
  );
}

// ── Ingestion Tab ──────────────────────────────────────────

function IngestionTab() {
  const [sources, setSources] = useState<string[]>([]);
  const [form, setForm] = useState({ name: "", type: "local", config: "{}" });
  const [ingestForm, setIngestForm] = useState({
    source_name: "", table: "", target_path: "/data/output", batch_size: 10000,
  });
  const [lastReport, setLastReport] = useState<IngestionReport | null>(null);
  const [error, setError] = useState("");

  const loadSources = useCallback(async () => {
    try {
      const data = await dataAPI.listConnectors();
      setSources(data.sources);
    } catch (e: unknown) { setError((e as Error).message); }
  }, []);

  useEffect(() => { loadSources(); }, [loadSources]);

  const addConnector = async () => {
    try {
      setError("");
      await dataAPI.registerConnector(form.name, form.type, JSON.parse(form.config));
      setForm({ name: "", type: "local", config: "{}" });
      loadSources();
    } catch (e: unknown) { setError((e as Error).message); }
  };

  const removeConnector = async (name: string) => {
    await dataAPI.removeConnector(name);
    loadSources();
  };

  const runIngestion = async () => {
    try {
      setError("");
      const report = await dataAPI.runIngestion(ingestForm);
      setLastReport(report);
    } catch (e: unknown) { setError((e as Error).message); }
  };

  return (
    <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
      {/* Connectors */}
      <div className="bg-surface-light rounded-xl border border-white/5 p-5">
        <h2 className="text-sm font-semibold mb-4 flex items-center gap-2">
          <Server className="w-4 h-4 text-accent" /> Connectors
        </h2>
        <div className="space-y-2 mb-4">
          {sources.map((s) => (
            <div key={s} className="flex items-center justify-between bg-surface px-3 py-2 rounded-lg">
              <span className="text-sm">{s}</span>
              <button onClick={() => removeConnector(s)} className="text-gray-500 hover:text-red-400">
                <Trash2 className="w-3.5 h-3.5" />
              </button>
            </div>
          ))}
          {sources.length === 0 && <p className="text-sm text-gray-500">No connectors registered.</p>}
        </div>
        <div className="space-y-2">
          <input className="w-full bg-surface border border-white/10 rounded-lg px-3 py-2 text-sm" placeholder="Name" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} />
          <select className="w-full bg-surface border border-white/10 rounded-lg px-3 py-2 text-sm" value={form.type} onChange={(e) => setForm({ ...form, type: e.target.value })}>
            <option value="local">local</option>
            <option value="s3">s3</option>
            <option value="postgresql">postgresql</option>
            <option value="rest">rest</option>
          </select>
          <input className="w-full bg-surface border border-white/10 rounded-lg px-3 py-2 text-sm font-mono" placeholder='Config JSON e.g. {"root_path":"/data"}' value={form.config} onChange={(e) => setForm({ ...form, config: e.target.value })} />
          <button onClick={addConnector} className="flex items-center gap-1.5 bg-accent hover:bg-accent-dark px-4 py-2 rounded-lg text-sm font-medium transition-colors">
            <Plus className="w-4 h-4" /> Add Connector
          </button>
        </div>
      </div>

      {/* Run Ingestion */}
      <div className="bg-surface-light rounded-xl border border-white/5 p-5">
        <h2 className="text-sm font-semibold mb-4 flex items-center gap-2">
          <Play className="w-4 h-4 text-emerald-400" /> Run Ingestion
        </h2>
        <div className="space-y-2 mb-4">
          <select className="w-full bg-surface border border-white/10 rounded-lg px-3 py-2 text-sm" value={ingestForm.source_name} onChange={(e) => setIngestForm({ ...ingestForm, source_name: e.target.value })}>
            <option value="">Select source...</option>
            {sources.map((s) => <option key={s} value={s}>{s}</option>)}
          </select>
          <input className="w-full bg-surface border border-white/10 rounded-lg px-3 py-2 text-sm" placeholder="Table name" value={ingestForm.table} onChange={(e) => setIngestForm({ ...ingestForm, table: e.target.value })} />
          <input className="w-full bg-surface border border-white/10 rounded-lg px-3 py-2 text-sm" placeholder="Target path" value={ingestForm.target_path} onChange={(e) => setIngestForm({ ...ingestForm, target_path: e.target.value })} />
        </div>
        <button onClick={runIngestion} className="flex items-center gap-1.5 bg-emerald-600 hover:bg-emerald-700 px-4 py-2 rounded-lg text-sm font-medium transition-colors">
          <Play className="w-4 h-4" /> Run Ingestion
        </button>

        {lastReport && (
          <div className="mt-4 grid grid-cols-3 gap-2">
            <StatCard label="Rows Read" value={lastReport.rows_read.toLocaleString()} accent="blue" />
            <StatCard label="Rows Written" value={lastReport.rows_written.toLocaleString()} accent="green" />
            <StatCard label="Pass Rate" value={`${(lastReport.pass_rate * 100).toFixed(1)}%`} accent={lastReport.pass_rate > 0.95 ? "green" : "amber"} />
          </div>
        )}
      </div>

      {error && <div className="lg:col-span-2 bg-red-500/10 border border-red-500/30 rounded-lg p-3 text-sm text-red-400">{error}</div>}
    </div>
  );
}

// ── Catalog Tab ────────────────────────────────────────────

function CatalogTab() {
  const [datasets, setDatasets] = useState<CatalogEntry[]>([]);
  const [keyword, setKeyword] = useState("");
  const [tag, setTag] = useState("");
  const [selected, setSelected] = useState<CatalogEntry | null>(null);
  const [summary, setSummary] = useState<Record<string, unknown>>({});

  const search = useCallback(async () => {
    const params: Record<string, string> = {};
    if (keyword) params.keyword = keyword;
    if (tag) params.tag = tag;
    const data = await dataAPI.searchCatalog(params);
    setDatasets(data.datasets);
  }, [keyword, tag]);

  useEffect(() => {
    search();
    dataAPI.catalogSummary().then(setSummary);
  }, [search]);

  return (
    <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
      <div className="lg:col-span-2 bg-surface-light rounded-xl border border-white/5 p-5">
        <div className="flex gap-2 mb-4">
          <input className="flex-1 bg-surface border border-white/10 rounded-lg px-3 py-2 text-sm" placeholder="Keyword search..." value={keyword} onChange={(e) => setKeyword(e.target.value)} onKeyDown={(e) => e.key === "Enter" && search()} />
          <input className="w-40 bg-surface border border-white/10 rounded-lg px-3 py-2 text-sm" placeholder="Tag filter" value={tag} onChange={(e) => setTag(e.target.value)} />
          <button onClick={search} className="flex items-center gap-1 bg-accent px-3 py-2 rounded-lg text-sm"><Search className="w-4 h-4" /></button>
        </div>
        <div className="space-y-2">
          {datasets.map((d) => (
            <div key={d.name} onClick={() => setSelected(d)} className="bg-surface rounded-lg p-3 cursor-pointer hover:bg-surface-lighter transition-colors">
              <div className="flex items-center justify-between">
                <span className="text-sm font-medium">{d.name}</span>
                <StatusBadge status={d.quality_score > 0.9 ? "healthy" : "degraded"} />
              </div>
              <div className="text-xs text-gray-500 mt-1">{d.owner} &middot; {d.format} &middot; {d.row_count_estimate.toLocaleString()} rows</div>
            </div>
          ))}
        </div>
      </div>

      {/* Details + Summary */}
      <div className="space-y-4">
        <div className="bg-surface-light rounded-xl border border-white/5 p-4">
          <h3 className="text-sm font-semibold mb-2">Summary</h3>
          <div className="grid grid-cols-2 gap-2 text-sm">
            <div className="text-gray-400">Datasets</div><div className="text-right">{String(summary.total_datasets || 0)}</div>
            <div className="text-gray-400">Est. Rows</div><div className="text-right">{Number(summary.total_estimated_rows || 0).toLocaleString()}</div>
            <div className="text-gray-400">Owners</div><div className="text-right">{String((summary.owners as string[])?.length || 0)}</div>
          </div>
        </div>

        {selected && (
          <div className="bg-surface-light rounded-xl border border-white/5 p-4">
            <h3 className="text-sm font-semibold mb-2">{selected.name}</h3>
            <div className="text-xs text-gray-400 space-y-1">
              <p>{selected.description || "No description"}</p>
              <p>Owner: {selected.owner}</p>
              <p>Format: {selected.format}</p>
              <p>Location: {selected.location}</p>
              <div className="flex flex-wrap gap-1 mt-2">
                {selected.tags.map((t) => <span key={t} className="px-2 py-0.5 bg-accent/10 text-accent-light rounded-full text-xs">{t}</span>)}
              </div>
              <div className="mt-2 pt-2 border-t border-white/5">
                <p className="font-medium mb-1">Columns ({selected.columns.length})</p>
                {selected.columns.map((c) => (
                  <div key={c.name} className="flex justify-between"><span>{c.name}</span><span className="text-gray-500">{c.dtype}</span></div>
                ))}
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

// ── Snapshots Tab ──────────────────────────────────────────

function SnapshotsTab() {
  const [snapshots, setSnapshots] = useState<Snapshot[]>([]);
  const [dataset, setDataset] = useState("");
  const [form, setForm] = useState({ dataset: "", source_path: "", tag_key: "", tag_val: "" });

  const load = async () => {
    const data = await dataAPI.listSnapshots(dataset || undefined);
    setSnapshots(data.snapshots);
  };

  useEffect(() => { load(); }, []);

  const create = async () => {
    const tags = form.tag_key && form.tag_val ? { [form.tag_key]: form.tag_val } : undefined;
    await dataAPI.createSnapshot(form.dataset, form.source_path, tags);
    setForm({ dataset: "", source_path: "", tag_key: "", tag_val: "" });
    load();
  };

  return (
    <div>
      <div className="bg-surface-light rounded-xl border border-white/5 p-5 mb-4">
        <div className="flex gap-2">
          <input className="flex-1 bg-surface border border-white/10 rounded-lg px-3 py-2 text-sm" placeholder="Dataset" value={form.dataset} onChange={(e) => setForm({ ...form, dataset: e.target.value })} />
          <input className="flex-1 bg-surface border border-white/10 rounded-lg px-3 py-2 text-sm" placeholder="Source path" value={form.source_path} onChange={(e) => setForm({ ...form, source_path: e.target.value })} />
          <input className="w-32 bg-surface border border-white/10 rounded-lg px-3 py-2 text-sm" placeholder="Tag key" value={form.tag_key} onChange={(e) => setForm({ ...form, tag_key: e.target.value })} />
          <input className="w-40 bg-surface border border-white/10 rounded-lg px-3 py-2 text-sm" placeholder="Tag value" value={form.tag_val} onChange={(e) => setForm({ ...form, tag_val: e.target.value })} />
          <button onClick={create} className="bg-accent px-4 py-2 rounded-lg text-sm whitespace-nowrap">Create</button>
        </div>
      </div>
      <div className="bg-surface-light rounded-xl border border-white/5 overflow-hidden">
        <table className="w-full text-sm">
          <thead><tr className="border-b border-white/5 text-gray-400 text-left"><th className="p-3">ID</th><th className="p-3">Dataset</th><th className="p-3">Rows</th><th className="p-3">Size</th><th className="p-3">Created</th></tr></thead>
          <tbody>
            {snapshots.map((s) => (
              <tr key={s.snapshot_id} className="border-b border-white/5 hover:bg-white/5">
                <td className="p-3 font-mono text-xs">{s.snapshot_id}</td>
                <td className="p-3">{s.dataset}</td>
                <td className="p-3">{s.row_count.toLocaleString()}</td>
                <td className="p-3">{(s.size_bytes / 1e6).toFixed(1)} MB</td>
                <td className="p-3 text-gray-500">{new Date(s.created_at).toLocaleString()}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

// ── Lineage Tab ────────────────────────────────────────────

function LineageTab() {
  const [datasetId, setDatasetId] = useState("");
  const [graph, setGraph] = useState<{ upstream: Array<{ source: string; target: string; type: string }>; downstream: Array<{ source: string; target: string; type: string }> } | null>(null);
  const [mermaid, setMermaid] = useState("");

  const load = async () => {
    if (!datasetId) return;
    const data = await dataAPI.getLineage(datasetId);
    setGraph(data);
    try {
      const m = await (await fetch(`/api/v1/data/lineage/${datasetId}/mermaid`)).json();
      setMermaid(m.mermaid || "");
    } catch { /* mermaid endpoint optional */ }
  };

  return (
    <div>
      <div className="flex gap-2 mb-4">
        <input className="flex-1 bg-surface-light border border-white/10 rounded-lg px-3 py-2 text-sm" placeholder="Dataset ID e.g. my_source/mytable" value={datasetId} onChange={(e) => setDatasetId(e.target.value)} onKeyDown={(e) => e.key === "Enter" && load()} />
        <button onClick={load} className="flex items-center gap-1.5 bg-accent px-4 py-2 rounded-lg text-sm"><GitBranch className="w-4 h-4" /> Trace</button>
      </div>

      {graph && (
        <div className="grid grid-cols-2 gap-4">
          <div className="bg-surface-light rounded-xl border border-white/5 p-4">
            <h3 className="text-sm font-semibold mb-3">Upstream ({graph.upstream.length})</h3>
            {graph.upstream.map((e, i) => (
              <div key={i} className="flex items-center gap-2 text-sm py-1">
                <span className="text-gray-500">{e.source}</span> <span className="text-accent">→</span> <span>{e.target}</span>
                <StatusBadge status={e.type} />
              </div>
            ))}
          </div>
          <div className="bg-surface-light rounded-xl border border-white/5 p-4">
            <h3 className="text-sm font-semibold mb-3">Downstream ({graph.downstream.length})</h3>
            {graph.downstream.map((e, i) => (
              <div key={i} className="flex items-center gap-2 text-sm py-1">
                <span>{e.source}</span> <span className="text-accent">→</span> <span className="text-gray-500">{e.target}</span>
                <StatusBadge status={e.type} />
              </div>
            ))}
          </div>
        </div>
      )}

      {mermaid && (
        <div className="mt-4 bg-surface-light rounded-xl border border-white/5 p-4">
          <h3 className="text-sm font-semibold mb-2">Mermaid Graph</h3>
          <pre className="text-xs text-gray-400 font-mono whitespace-pre-wrap">{mermaid}</pre>
        </div>
      )}
    </div>
  );
}
