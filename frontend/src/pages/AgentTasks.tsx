import { useEffect, useState, useCallback } from "react";
import { agentAPI } from "@/api/client";
import type { AgentSummary, QueueStats, MemoryEntry, MemoryStats } from "@/types";
import StatCard from "@/components/StatCard";
import StatusBadge from "@/components/StatusBadge";
import { Send, Brain, Search, Plus, Zap, Play, BookOpen } from "lucide-react";
import type { LiteratureResult } from "@/types";

type Tab = "tasks" | "agents" | "tools" | "memory" | "literature";

export default function AgentTasks() {
  const [tab, setTab] = useState<Tab>("tasks");

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-xl font-bold">Agent Tasks</h1>
        <span className="text-xs text-gray-500">Agent Runtime</span>
      </div>

      <div className="flex gap-1 mb-6 border-b border-white/5 pb-0">
        {(["tasks", "agents", "tools", "memory", "literature"] as const).map((t) => (
          <button
            key={t}
            onClick={() => setTab(t)}
            className={`px-4 py-2 text-sm font-medium rounded-t-lg transition-colors ${
              tab === t ? "bg-accent/15 text-accent-light border-b-2 border-accent" : "text-gray-400 hover:text-gray-200"
            }`}
          >
            {t === "tasks" ? "Tasks" : t === "agents" ? "Agents" : t === "tools" ? "Tools" : t === "memory" ? "Memory" : "Literature"}
          </button>
        ))}
      </div>

      {tab === "tasks" && <TasksTab />}
      {tab === "agents" && <AgentsTab />}
      {tab === "tools" && <ToolsTab />}
      {tab === "memory" && <MemoryTab />}
      {tab === "literature" && <LiteratureTab />}
    </div>
  );
}

// ── Tasks Tab ──────────────────────────────────────────────

function TasksTab() {
  const [queue, setQueue] = useState<QueueStats>({ pending: 0, active: 0, dead: 0 });
  const [form, setForm] = useState({ agent_type: "worker", action: "compute", payload: "{}", priority: "normal" });
  const [submitted, setSubmitted] = useState<{ task_id: string; status: string } | null>(null);
  const [error, setError] = useState("");
  const [pollId, setPollId] = useState("");
  const [pollResult, setPollResult] = useState<string>("");

  const loadQueue = useCallback(async () => {
    try { setQueue(await agentAPI.queueStats()); } catch (e: unknown) { setError((e as Error).message); }
  }, []);

  useEffect(() => { loadQueue(); const i = setInterval(loadQueue, 5000); return () => clearInterval(i); }, [loadQueue]);

  const submit = async () => {
    try {
      setError("");
      const res = await agentAPI.submitTask({
        agent_type: form.agent_type,
        action: form.action,
        payload: JSON.parse(form.payload),
        priority: form.priority,
      });
      setSubmitted(res);
      loadQueue();
    } catch (e: unknown) { setError((e as Error).message); }
  };

  const pollTask = async () => {
    try {
      const res = await agentAPI.getTask(pollId);
      setPollResult(JSON.stringify(res, null, 2));
    } catch (e: unknown) { setError((e as Error).message); }
  };

  return (
    <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
      {/* Stats */}
      <div className="lg:col-span-3 grid grid-cols-4 gap-3">
        <StatCard label="Pending" value={queue.pending} accent="amber" />
        <StatCard label="Active" value={queue.active} accent="blue" />
        <StatCard label="Dead" value={queue.dead} accent="red" />
        <StatCard label="Scheduled" value={queue.scheduled ?? 0} accent="purple" />
      </div>

      {/* Submit */}
      <div className="bg-surface-light rounded-xl border border-white/5 p-5">
        <h2 className="text-sm font-semibold mb-3 flex items-center gap-2"><Send className="w-4 h-4 text-accent" /> Submit Task</h2>
        <div className="space-y-2">
          <input className="w-full bg-surface border border-white/10 rounded-lg px-3 py-2 text-sm" placeholder="Agent type" value={form.agent_type} onChange={(e) => setForm({ ...form, agent_type: e.target.value })} />
          <input className="w-full bg-surface border border-white/10 rounded-lg px-3 py-2 text-sm" placeholder="Action" value={form.action} onChange={(e) => setForm({ ...form, action: e.target.value })} />
          <input className="w-full bg-surface border border-white/10 rounded-lg px-3 py-2 text-sm font-mono" placeholder='Payload JSON' value={form.payload} onChange={(e) => setForm({ ...form, payload: e.target.value })} />
          <select className="w-full bg-surface border border-white/10 rounded-lg px-3 py-2 text-sm" value={form.priority} onChange={(e) => setForm({ ...form, priority: e.target.value })}>
            <option value="low">Low</option><option value="normal">Normal</option><option value="high">High</option><option value="critical">Critical</option>
          </select>
          <button onClick={submit} className="w-full bg-accent hover:bg-accent-dark py-2 rounded-lg text-sm font-medium transition-colors">Submit Task</button>
        </div>
        {submitted && (
          <div className="mt-3 p-3 bg-emerald-500/10 rounded-lg text-sm">
            <div className="text-emerald-400 font-mono">{submitted.task_id}</div>
            <div className="text-gray-400 text-xs mt-1">Status: {submitted.status}</div>
          </div>
        )}
      </div>

      {/* Poll */}
      <div className="bg-surface-light rounded-xl border border-white/5 p-5">
        <h2 className="text-sm font-semibold mb-3">Query Task</h2>
        <div className="flex gap-2 mb-2">
          <input className="flex-1 bg-surface border border-white/10 rounded-lg px-3 py-2 text-sm" placeholder="Task ID" value={pollId} onChange={(e) => setPollId(e.target.value)} />
          <button onClick={pollTask} className="bg-accent px-3 py-2 rounded-lg text-sm"><Search className="w-4 h-4" /></button>
        </div>
        {pollResult && <pre className="mt-2 p-3 bg-surface rounded-lg text-xs text-gray-400 overflow-auto max-h-40">{pollResult}</pre>}
      </div>

      {error && <div className="lg:col-span-3 bg-red-500/10 border border-red-500/30 rounded-lg p-3 text-sm text-red-400">{error}</div>}
    </div>
  );
}

// ── Agents Tab ─────────────────────────────────────────────

function AgentsTab() {
  const [agents, setAgents] = useState<AgentSummary | null>(null);
  const [form, setForm] = useState({ agent_id: "", capabilities: "", max_capacity: "10" });

  const load = async () => { setAgents(await agentAPI.listAgents()); };
  useEffect(() => { load(); }, []);

  const register = async () => {
    await agentAPI.registerAgent(form.agent_id, form.capabilities.split(",").map((s) => s.trim()), parseInt(form.max_capacity));
    setForm({ agent_id: "", capabilities: "", max_capacity: "10" });
    load();
  };

  return (
    <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
      <div className="bg-surface-light rounded-xl border border-white/5 p-5">
        <h2 className="text-sm font-semibold mb-3 flex items-center gap-2"><Plus className="w-4 h-4 text-accent" /> Register Agent</h2>
        <div className="space-y-2">
          <input className="w-full bg-surface border border-white/10 rounded-lg px-3 py-2 text-sm" placeholder="Agent ID" value={form.agent_id} onChange={(e) => setForm({ ...form, agent_id: e.target.value })} />
          <input className="w-full bg-surface border border-white/10 rounded-lg px-3 py-2 text-sm" placeholder="Capabilities (comma-separated)" value={form.capabilities} onChange={(e) => setForm({ ...form, capabilities: e.target.value })} />
          <input className="w-full bg-surface border border-white/10 rounded-lg px-3 py-2 text-sm" placeholder="Max capacity" type="number" value={form.max_capacity} onChange={(e) => setForm({ ...form, max_capacity: e.target.value })} />
          <button onClick={register} className="w-full bg-accent py-2 rounded-lg text-sm">Register</button>
        </div>
      </div>

      <div className="bg-surface-light rounded-xl border border-white/5 p-5">
        <h2 className="text-sm font-semibold mb-3">Registered Agents</h2>
        {agents && (
          <div className="space-y-1 text-sm mb-3">
            <div className="flex justify-between"><span className="text-gray-400">Total</span><span>{agents.total}</span></div>
            <div className="flex justify-between"><span className="text-gray-400">Online</span><span className="text-emerald-400">{agents.online}</span></div>
            <div className="flex justify-between"><span className="text-gray-400">Busy</span><span className="text-amber-400">{agents.busy}</span></div>
            <div className="flex justify-between"><span className="text-gray-400">Capacity</span><span>{agents.total_load}/{agents.total_capacity}</span></div>
          </div>
        )}
        {agents && Object.entries(agents.capability_matrix).map(([id, caps]) => (
          <div key={id} className="bg-surface rounded-lg p-2 mb-1 text-sm">
            <div className="font-medium">{id}</div>
            <div className="flex flex-wrap gap-1 mt-1">
              {caps.map((c) => <span key={c} className="px-2 py-0.5 bg-accent/10 text-accent-light rounded text-xs">{c}</span>)}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

// ── Tools Tab ──────────────────────────────────────────────

function ToolsTab() {
  const [tools, setTools] = useState<Array<{ function: { name: string; description: string } }>>([]);
  const [execForm, setExecForm] = useState({ tool_name: "", arguments: "{}" });
  const [execResult, setExecResult] = useState("");

  const load = async () => {
    const data = await agentAPI.listTools();
    setTools(data.tools);
  };
  useEffect(() => { load(); }, []);

  const execute = async () => {
    try {
      const res = await agentAPI.executeTool(execForm.tool_name, JSON.parse(execForm.arguments));
      setExecResult(JSON.stringify(res, null, 2));
    } catch (e: unknown) { setExecResult(`Error: ${(e as Error).message}`); }
  };

  return (
    <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
      <div className="bg-surface-light rounded-xl border border-white/5 p-5">
        <h2 className="text-sm font-semibold mb-3 flex items-center gap-2"><Zap className="w-4 h-4 text-amber-400" /> Registered Tools ({tools.length})</h2>
        <div className="space-y-2">
          {tools.map((t) => (
            <div key={t.function.name} className="bg-surface rounded-lg p-3 cursor-pointer hover:bg-surface-lighter" onClick={() => setExecForm({ ...execForm, tool_name: t.function.name })}>
              <div className="text-sm font-medium">{t.function.name}</div>
              <div className="text-xs text-gray-500 mt-1">{t.function.description}</div>
            </div>
          ))}
          {tools.length === 0 && <p className="text-sm text-gray-500">No tools registered.</p>}
        </div>
      </div>

      <div className="bg-surface-light rounded-xl border border-white/5 p-5">
        <h2 className="text-sm font-semibold mb-3">Execute Tool</h2>
        <div className="space-y-2">
          <input className="w-full bg-surface border border-white/10 rounded-lg px-3 py-2 text-sm" placeholder="Tool name" value={execForm.tool_name} onChange={(e) => setExecForm({ ...execForm, tool_name: e.target.value })} />
          <textarea className="w-full bg-surface border border-white/10 rounded-lg px-3 py-2 text-sm font-mono h-24" placeholder='{"key": "value"}' value={execForm.arguments} onChange={(e) => setExecForm({ ...execForm, arguments: e.target.value })} />
          <button onClick={execute} className="w-full bg-accent py-2 rounded-lg text-sm flex items-center justify-center gap-1.5"><Play className="w-4 h-4" /> Execute</button>
        </div>
        {execResult && <pre className="mt-3 p-3 bg-surface rounded-lg text-xs text-gray-400 overflow-auto max-h-48">{execResult}</pre>}
      </div>
    </div>
  );
}

// ── Memory Tab ─────────────────────────────────────────────

function MemoryTab() {
  const [stats, setStats] = useState<MemoryStats>({ total: 0 });
  const [recallQuery, setRecallQuery] = useState("");
  const [memories, setMemories] = useState<MemoryEntry[]>([]);
  const [memForm, setMemForm] = useState({ content: "", tags: "", importance: "0.5" });
  const [asContext, setAsContext] = useState("");

  const loadStats = async () => { setStats(await agentAPI.memoryStats()); };
  useEffect(() => { loadStats(); }, []);

  const remember = async () => {
    await agentAPI.remember(memForm.content, memForm.tags ? memForm.tags.split(",").map((s) => s.trim()) : [], parseFloat(memForm.importance));
    setMemForm({ content: "", tags: "", importance: "0.5" });
    loadStats();
  };

  const recall = async () => {
    const res = await agentAPI.recall(recallQuery, 5, false);
    if (res.memories) setMemories(res.memories);
    if (res.context) setAsContext(res.context);
  };

  return (
    <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
      <div className="bg-surface-light rounded-xl border border-white/5 p-5">
        <h2 className="text-sm font-semibold mb-3 flex items-center gap-2"><Brain className="w-4 h-4 text-purple-400" /> Store Memory</h2>
        <div className="space-y-2">
          <textarea className="w-full bg-surface border border-white/10 rounded-lg px-3 py-2 text-sm h-24" placeholder="Content to remember..." value={memForm.content} onChange={(e) => setMemForm({ ...memForm, content: e.target.value })} />
          <input className="w-full bg-surface border border-white/10 rounded-lg px-3 py-2 text-sm" placeholder="Tags (comma-separated)" value={memForm.tags} onChange={(e) => setMemForm({ ...memForm, tags: e.target.value })} />
          <input className="w-full bg-surface border border-white/10 rounded-lg px-3 py-2 text-sm" placeholder="Importance 0.0-1.0" type="number" step="0.1" min="0" max="1" value={memForm.importance} onChange={(e) => setMemForm({ ...memForm, importance: e.target.value })} />
          <button onClick={remember} className="w-full bg-purple-600 py-2 rounded-lg text-sm">Store</button>
        </div>
      </div>

      <div className="bg-surface-light rounded-xl border border-white/5 p-5">
        <h2 className="text-sm font-semibold mb-3 flex items-center gap-2"><Search className="w-4 h-4 text-sky-400" /> Recall Memory</h2>
        <div className="flex gap-2 mb-3">
          <input className="flex-1 bg-surface border border-white/10 rounded-lg px-3 py-2 text-sm" placeholder="Search query..." value={recallQuery} onChange={(e) => setRecallQuery(e.target.value)} onKeyDown={(e) => e.key === "Enter" && recall()} />
          <button onClick={recall} className="bg-sky-600 px-3 py-2 rounded-lg text-sm">Search</button>
        </div>
        <div className="space-y-2 max-h-64 overflow-auto">
          {memories.map((m) => (
            <div key={m.id} className="bg-surface rounded-lg p-2 text-xs">
              <div className="text-gray-300 line-clamp-3">{m.content}</div>
              <div className="flex gap-2 mt-1 text-gray-500">importance: {m.importance.toFixed(2)} {m.tags.map((t) => <span key={t} className="bg-accent/10 px-1 rounded">{t}</span>)}</div>
            </div>
          ))}
        </div>
      </div>

      <div className="bg-surface-light rounded-xl border border-white/5 p-5">
        <h2 className="text-sm font-semibold mb-3">Memory Stats</h2>
        <div className="grid grid-cols-2 gap-2 text-sm">
          <div className="text-gray-400">Total</div><div className="text-right font-mono">{stats.total}</div>
          <div className="text-gray-400">Avg Importance</div><div className="text-right">{((stats.avg_importance || 0) * 100).toFixed(0)}%</div>
          <div className="text-gray-400">Sources</div><div className="text-right">{(stats.sources || []).join(", ") || "-"}</div>
        </div>
        {asContext && (
          <div className="mt-3 p-3 bg-surface rounded-lg">
            <div className="text-xs text-gray-400 mb-1">Formatted Context:</div>
            <pre className="text-xs text-gray-300 whitespace-pre-wrap max-h-48 overflow-auto">{asContext}</pre>
          </div>
        )}
      </div>
    </div>
  );
}

// ── Literature Tab ─────────────────────────────────────────

function LiteratureTab() {
  const [query, setQuery] = useState("");
  const [limit, setLimit] = useState("10");
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<LiteratureResult | null>(null);
  const [error, setError] = useState("");
  const [expanded, setExpanded] = useState<Set<string>>(new Set());

  const search = async () => {
    if (!query.trim()) return;
    setLoading(true);
    setError("");
    try {
      const res = await agentAPI.literatureSearch(query.trim(), parseInt(limit) || 10);
      setResult(res);
      setExpanded(new Set());
    } catch (e: unknown) {
      setError((e as Error).message);
    } finally {
      setLoading(false);
    }
  };

  const toggleAbstract = (paperId: string) => {
    setExpanded((prev) => {
      const next = new Set(prev);
      if (next.has(paperId)) next.delete(paperId);
      else next.add(paperId);
      return next;
    });
  };

  return (
    <div className="space-y-6">
      {/* Search form */}
      <div className="bg-surface-light rounded-xl border border-white/5 p-5">
        <h2 className="text-sm font-semibold mb-3 flex items-center gap-2">
          <BookOpen className="w-4 h-4 text-accent" /> Chemical Literature Search
        </h2>
        <p className="text-xs text-gray-500 mb-3">
          Search papers from Semantic Scholar. Try keywords like "metal organic framework", "perovskite solar cell", "catalyst design".
        </p>
        <div className="flex gap-2">
          <input
            className="flex-1 bg-surface border border-white/10 rounded-lg px-3 py-2 text-sm"
            placeholder="Search keywords..."
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && search()}
          />
          <select
            className="w-20 bg-surface border border-white/10 rounded-lg px-2 py-2 text-sm"
            value={limit}
            onChange={(e) => setLimit(e.target.value)}
          >
            {[5, 10, 20, 50].map((n) => (
              <option key={n} value={n}>{n}</option>
            ))}
          </select>
          <button
            onClick={search}
            disabled={loading}
            className="flex items-center gap-1.5 bg-accent hover:bg-accent-dark px-4 py-2 rounded-lg text-sm font-medium transition-colors disabled:opacity-50"
          >
            <Search className="w-4 h-4" />
            {loading ? "Searching..." : "Search"}
          </button>
        </div>
        <div className="flex flex-wrap gap-1.5 mt-3">
          {["metal organic framework", "perovskite solar cell", "catalyst design", "drug discovery AI", "green synthesis"].map((kw) => (
            <button
              key={kw}
              type="button"
              onClick={() => setQuery(kw)}
              className="px-2 py-1 text-xs rounded bg-accent/10 text-accent-light hover:bg-accent/20 transition-colors"
            >
              {kw}
            </button>
          ))}
        </div>
      </div>

      {/* Error */}
      {error && (
        <div className="bg-red-500/10 border border-red-500/30 rounded-lg p-3 text-sm text-red-400">{error}</div>
      )}

      {/* Results */}
      {result && (
        <div>
          <div className="flex items-center justify-between mb-3">
            <h3 className="text-sm font-semibold">
              Results for "<span className="text-accent-light">{result.query}</span>"
              <span className="text-gray-500 ml-2">({result.total.toLocaleString()} total, showing {result.count})</span>
            </h3>
          </div>
          <div className="space-y-3">
            {result.papers.map((paper, idx) => (
              <div key={paper.paperId} className="bg-surface-light rounded-xl border border-white/5 p-4 hover:border-white/10 transition-colors">
                <div className="flex items-start justify-between gap-3">
                  <div className="flex-1 min-w-0">
                    <h4 className="text-sm font-semibold leading-snug">
                      <span className="text-gray-500 mr-2">#{idx + 1}</span>
                      {paper.url ? (
                        <a href={paper.url} target="_blank" rel="noopener noreferrer" className="hover:text-accent-light transition-colors">
                          {paper.title}
                        </a>
                      ) : paper.title}
                    </h4>
                    <div className="flex flex-wrap items-center gap-x-3 gap-y-1 mt-1.5 text-xs text-gray-400">
                      {paper.authors.length > 0 && (
                        <span>{paper.authors.slice(0, 3).join(", ")}{paper.authors.length > 3 ? ` et al.` : ""}</span>
                      )}
                      {paper.year && <span className="text-gray-500">{paper.year}</span>}
                      {paper.venue && <span className="text-gray-500">{paper.venue}</span>}
                      {paper.doi && (
                        <a
                          href={`https://doi.org/${paper.doi}`}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="text-accent-light hover:underline"
                        >
                          DOI: {paper.doi}
                        </a>
                      )}
                      <span>Cited: {paper.citationCount}</span>
                    </div>
                  </div>
                  {paper.abstract && (
                    <button
                      onClick={() => toggleAbstract(paper.paperId)}
                      className="shrink-0 text-xs text-accent-light hover:text-accent transition-colors mt-0.5"
                    >
                      {expanded.has(paper.paperId) ? "Hide" : "Abstract"}
                    </button>
                  )}
                </div>
                {expanded.has(paper.paperId) && paper.abstract && (
                  <p className="mt-2 text-xs text-gray-400 leading-relaxed bg-surface rounded-lg p-3">{paper.abstract}</p>
                )}
              </div>
            ))}
          </div>
          {result.papers.length === 0 && (
            <p className="text-sm text-gray-500 text-center py-8">No papers found. Try different keywords.</p>
          )}
        </div>
      )}
    </div>
  );
}
