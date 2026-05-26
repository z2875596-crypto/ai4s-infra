import { useEffect, useState, useCallback } from "react";
import { rlhfAPI } from "@/api/client";
import type { FeedbackStats, ConsensusPair, RewardScore, PolicyTrainResult, AnnotatorQuality } from "@/types";
import StatCard from "@/components/StatCard";
import StatusBadge from "@/components/StatusBadge";
import { Brain, ThumbsUp, MessageSquare, Play, BarChart3, Users, CheckCircle } from "lucide-react";

type Tab = "feedback" | "reward" | "policy" | "pipeline";

export default function RLHFTraining() {
  const [tab, setTab] = useState<Tab>("feedback");

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-xl font-bold">RLHF Training</h1>
        <span className="text-xs text-gray-500">RLHF Pipeline</span>
      </div>

      <div className="flex gap-1 mb-6 border-b border-white/5 pb-0">
        {(["feedback", "reward", "policy", "pipeline"] as const).map((t) => (
          <button
            key={t}
            onClick={() => setTab(t)}
            className={`px-4 py-2 text-sm font-medium rounded-t-lg transition-colors ${
              tab === t ? "bg-accent/15 text-accent-light border-b-2 border-accent" : "text-gray-400 hover:text-gray-200"
            }`}
          >
            {t === "feedback" ? "Feedback" : t === "reward" ? "Reward Model" : t === "policy" ? "Policy Training" : "Pipeline"}
          </button>
        ))}
      </div>

      {tab === "feedback" && <FeedbackTab />}
      {tab === "reward" && <RewardTab />}
      {tab === "policy" && <PolicyTab />}
      {tab === "pipeline" && <PipelineTab />}
    </div>
  );
}

// ── Feedback Tab ──────────────────────────────────────────

function FeedbackTab() {
  const [stats, setStats] = useState<FeedbackStats | null>(null);
  const [consensus, setConsensus] = useState<ConsensusPair[]>([]);
  const [quality, setQuality] = useState<AnnotatorQuality>({});
  const [form, setForm] = useState({
    prompts: "What is AI?\nExplain gravity.",
    responses_a: "AI is artificial intelligence.\nGravity is a fundamental force.",
    responses_b: "AI is a field of CS.\nGravity is the curvature of spacetime.",
  });
  const [annotateForm, setAnnotateForm] = useState({ item_id: "", annotator_id: "annotator-1", choice: "A" });

  const load = useCallback(async () => {
    try {
      const [s, c, q] = await Promise.all([
        rlhfAPI.feedbackStats(), rlhfAPI.getConsensus(), rlhfAPI.annotatorQuality(),
      ]);
      setStats(s); setConsensus(c.pairs); setQuality(q);
    } catch { /* backend offline */ }
  }, []);

  useEffect(() => { load(); }, [load]);

  const addItems = async () => {
    await rlhfAPI.addFeedback(
      form.prompts.split("\n").filter(Boolean),
      form.responses_a.split("\n").filter(Boolean),
      form.responses_b.split("\n").filter(Boolean),
    );
    load();
  };

  const assignAnnotate = async () => {
    // Assign
    const assignRes = await (await fetch("/api/v1/rlhf/feedback/assign", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ annotator_id: annotateForm.annotator_id, n: 3 }),
    })).json();
    // Annotate all assigned
    const items: Array<{ item_id: string }> = assignRes.items || [];
    for (const item of items) {
      await rlhfAPI.annotate(item.item_id, annotateForm.annotator_id, annotateForm.choice);
    }
    load();
  };

  return (
    <div className="space-y-6">
      {/* Stats */}
      {stats && (
        <div className="grid grid-cols-2 lg:grid-cols-6 gap-3">
          <StatCard label="Total Items" value={stats.total} accent="default" />
          <StatCard label="Pending" value={stats.by_status?.pending || 0} accent="amber" />
          <StatCard label="Annotated" value={stats.by_status?.annotated || 0} accent="blue" />
          <StatCard label="Consensus" value={stats.by_status?.consensus || 0} accent="green" />
          <StatCard label="Annotators" value={stats.annotators} accent="purple" />
          <StatCard label="Avg Confidence" value={`${((stats.avg_confidence || 0) * 100).toFixed(0)}%`} accent="default" />
        </div>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Add items */}
        <div className="bg-surface-light rounded-xl border border-white/5 p-5">
          <h2 className="text-sm font-semibold mb-3 flex items-center gap-2"><MessageSquare className="w-4 h-4 text-accent" /> Add Feedback Items</h2>
          <div className="space-y-2">
            <div>
              <label className="text-xs text-gray-400">Prompts (one per line)</label>
              <textarea className="w-full bg-surface border border-white/10 rounded-lg px-3 py-2 text-sm h-20 mt-1" value={form.prompts} onChange={(e) => setForm({ ...form, prompts: e.target.value })} />
            </div>
            <div className="grid grid-cols-2 gap-2">
              <div>
                <label className="text-xs text-gray-400">Response A</label>
                <textarea className="w-full bg-surface border border-white/10 rounded-lg px-3 py-2 text-sm h-20 mt-1" value={form.responses_a} onChange={(e) => setForm({ ...form, responses_a: e.target.value })} />
              </div>
              <div>
                <label className="text-xs text-gray-400">Response B</label>
                <textarea className="w-full bg-surface border border-white/10 rounded-lg px-3 py-2 text-sm h-20 mt-1" value={form.responses_b} onChange={(e) => setForm({ ...form, responses_b: e.target.value })} />
              </div>
            </div>
            <button onClick={addItems} className="w-full bg-accent py-2 rounded-lg text-sm">Add Items</button>
          </div>
        </div>

        {/* Annotate */}
        <div className="bg-surface-light rounded-xl border border-white/5 p-5">
          <h2 className="text-sm font-semibold mb-3 flex items-center gap-2"><ThumbsUp className="w-4 h-4 text-emerald-400" /> Annotate</h2>
          <div className="space-y-2">
            <input className="w-full bg-surface border border-white/10 rounded-lg px-3 py-2 text-sm" placeholder="Annotator ID" value={annotateForm.annotator_id} onChange={(e) => setAnnotateForm({ ...annotateForm, annotator_id: e.target.value })} />
            <select className="w-full bg-surface border border-white/10 rounded-lg px-3 py-2 text-sm" value={annotateForm.choice} onChange={(e) => setAnnotateForm({ ...annotateForm, choice: e.target.value })}>
              <option value="A">Prefer A</option><option value="B">Prefer B</option><option value="tie">Tie</option><option value="both_bad">Both Bad</option><option value="both_good">Both Good</option>
            </select>
            <button onClick={assignAnnotate} className="w-full bg-emerald-600 py-2 rounded-lg text-sm">Auto-Assign & Annotate</button>
          </div>
        </div>
      </div>

      {/* Consensus pairs */}
      {consensus.length > 0 && (
        <div className="bg-surface-light rounded-xl border border-white/5 p-5">
          <h2 className="text-sm font-semibold mb-3">Consensus Pairs ({consensus.length})</h2>
          <div className="space-y-2 max-h-80 overflow-auto">
            {consensus.map((p, i) => (
              <div key={i} className="bg-surface rounded-lg p-3 text-sm">
                <div className="text-gray-400 text-xs mb-1">Prompt: {p.prompt.slice(0, 120)}</div>
                <div className="grid grid-cols-2 gap-2">
                  <div className="bg-emerald-500/10 rounded p-2 text-xs"><span className="text-emerald-400 font-medium">Chosen:</span> {p.chosen.slice(0, 150)}</div>
                  <div className="bg-red-500/10 rounded p-2 text-xs"><span className="text-red-400 font-medium">Rejected:</span> {p.rejected.slice(0, 150)}</div>
                </div>
                {p._agreement && <div className="text-xs text-gray-500 mt-1">Agreement: {(p._agreement * 100).toFixed(0)}% &middot; {p._num_annotators} annotators</div>}
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Annotator Quality */}
      {Object.keys(quality).length > 0 && (
        <div className="bg-surface-light rounded-xl border border-white/5 p-5">
          <h2 className="text-sm font-semibold mb-3 flex items-center gap-2"><Users className="w-4 h-4 text-sky-400" /> Annotator Quality</h2>
          <div className="space-y-2">
            {Object.entries(quality).map(([id, q]) => (
              <div key={id} className="flex items-center justify-between bg-surface rounded-lg p-3 text-sm">
                <span className="font-medium">{id}</span>
                <div className="flex gap-4 text-xs text-gray-400">
                  <span>Total: {q.total}</span>
                  <span>Agreed: {q.agreed_with_consensus}</span>
                  <span className="text-emerald-400">Accuracy: {(q.accuracy * 100).toFixed(0)}%</span>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

// ── Reward Tab ─────────────────────────────────────────────

function RewardTab() {
  const [form, setForm] = useState({ prompts: "", responses: "" });
  const [scores, setScores] = useState<RewardScore[]>([]);

  const score = async () => {
    const res = await rlhfAPI.scoreReward(
      form.prompts.split("\n").filter(Boolean),
      form.responses.split("\n").filter(Boolean),
    );
    setScores(res.scores);
  };

  const avgScore = scores.length > 0 ? scores.reduce((a, s) => a + s.score, 0) / scores.length : 0;

  return (
    <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
      <div className="bg-surface-light rounded-xl border border-white/5 p-5">
        <h2 className="text-sm font-semibold mb-3 flex items-center gap-2"><Brain className="w-4 h-4 text-purple-400" /> Score with Reward Model</h2>
        <div className="space-y-2">
          <div>
            <label className="text-xs text-gray-400">Prompts (one per line)</label>
            <textarea className="w-full bg-surface border border-white/10 rounded-lg px-3 py-2 text-sm h-24 mt-1" placeholder="What is 2+2?\nExplain machine learning." value={form.prompts} onChange={(e) => setForm({ ...form, prompts: e.target.value })} />
          </div>
          <div>
            <label className="text-xs text-gray-400">Responses (one per line, matching prompts)</label>
            <textarea className="w-full bg-surface border border-white/10 rounded-lg px-3 py-2 text-sm h-24 mt-1" placeholder="4\nMachine learning is..." value={form.responses} onChange={(e) => setForm({ ...form, responses: e.target.value })} />
          </div>
          <button onClick={score} className="w-full bg-purple-600 py-2 rounded-lg text-sm">Score</button>
        </div>
      </div>

      <div className="bg-surface-light rounded-xl border border-white/5 p-5">
        <h2 className="text-sm font-semibold mb-3">Reward Scores</h2>
        {scores.length > 0 && (
          <>
            <div className="text-3xl font-bold mb-4">{avgScore.toFixed(3)} <span className="text-sm text-gray-400 font-normal">avg reward</span></div>
            <div className="space-y-2 max-h-80 overflow-auto">
              {scores.map((s, i) => (
                <div key={i} className="bg-surface rounded-lg p-3 flex items-center justify-between text-sm">
                  <span className="text-gray-300 truncate max-w-md">{s.prompt}</span>
                  <span className={`font-mono font-bold ${s.score >= 0 ? "text-emerald-400" : "text-red-400"}`}>{s.score.toFixed(3)}</span>
                </div>
              ))}
            </div>
          </>
        )}
        {scores.length === 0 && <p className="text-gray-500 text-sm">Run scoring to see results.</p>}
      </div>
    </div>
  );
}

// ── Policy Tab ─────────────────────────────────────────────

function PolicyTab() {
  const [algo, setAlgo] = useState<"dpo" | "ppo">("dpo");
  const [pairsText, setPairsText] = useState(
    '[\n  {"prompt": "What is AI?", "chosen": "AI is artificial intelligence.", "rejected": "AI is magic."},\n  {"prompt": "Explain gravity.", "chosen": "Gravity curves spacetime.", "rejected": "Things fall down."}\n]'
  );
  const [result, setResult] = useState<PolicyTrainResult | null>(null);
  const [error, setError] = useState("");

  const train = async () => {
    try {
      setError("");
      const pairs = JSON.parse(pairsText);
      const res = await rlhfAPI.trainPolicy(algo, pairs);
      setResult(res);
    } catch (e: unknown) { setError((e as Error).message); }
  };

  return (
    <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
      <div className="bg-surface-light rounded-xl border border-white/5 p-5">
        <h2 className="text-sm font-semibold mb-3 flex items-center gap-2"><Play className="w-4 h-4 text-emerald-400" /> Policy Training</h2>
        <div className="space-y-2">
          <div className="flex gap-2">
            <button onClick={() => setAlgo("dpo")} className={`flex-1 py-2 rounded-lg text-sm font-medium transition-colors ${algo === "dpo" ? "bg-accent" : "bg-surface border border-white/10"}`}>DPO</button>
            <button onClick={() => setAlgo("ppo")} className={`flex-1 py-2 rounded-lg text-sm font-medium transition-colors ${algo === "ppo" ? "bg-accent" : "bg-surface border border-white/10"}`}>PPO</button>
          </div>
          <div>
            <label className="text-xs text-gray-400">Preference Pairs (JSON)</label>
            <textarea className="w-full bg-surface border border-white/10 rounded-lg px-3 py-2 text-sm font-mono h-40 mt-1" value={pairsText} onChange={(e) => setPairsText(e.target.value)} />
          </div>
          <button onClick={train} className="w-full bg-emerald-600 py-2 rounded-lg text-sm font-medium">Train Policy ({algo.toUpperCase()})</button>
        </div>
        {error && <div className="mt-3 p-3 bg-red-500/10 border border-red-500/30 rounded-lg text-sm text-red-400">{error}</div>}
      </div>

      <div className="bg-surface-light rounded-xl border border-white/5 p-5">
        <h2 className="text-sm font-semibold mb-3">Training Result</h2>
        {result ? (
          <div className="space-y-3 text-sm">
            {result.n_prompts !== undefined && <StatCard label="Prompts" value={result.n_prompts} accent="blue" />}
            {result.n_pairs !== undefined && <StatCard label="Pairs" value={result.n_pairs} accent="blue" />}
            {result.final_loss !== undefined && <StatCard label="Final Loss" value={result.final_loss.toFixed(4)} accent="amber" />}
            {result.epochs && <div className="text-gray-400">Epochs: {result.epochs}</div>}
            {result.training && (
              <div className="bg-surface rounded-lg p-3">
                <div className="text-xs text-gray-400 mb-1">Training Details</div>
                <pre className="text-xs text-gray-300 whitespace-pre-wrap">{JSON.stringify(result.training, null, 2)}</pre>
              </div>
            )}
          </div>
        ) : (
          <p className="text-gray-500 text-sm">Run training to see results.</p>
        )}
      </div>
    </div>
  );
}

// ── Pipeline Tab ───────────────────────────────────────────

function PipelineTab() {
  const [prompts, setPrompts] = useState("What is AI?\nExplain gravity.\nHow does a neural network work?");
  const [result, setResult] = useState<PipelineIterResult | null>(null);
  const [evalResult, setEvalResult] = useState<Record<string, unknown> | null>(null);
  const [loading, setLoading] = useState(false);

  const iterate = async () => {
    setLoading(true);
    try {
      const res = await rlhfAPI.pipelineIterate(prompts.split("\n").filter(Boolean));
      setResult(res);
    } catch { /* no backend */ }
    setLoading(false);
  };

  const evaluate = async () => {
    try {
      const promptList = prompts.split("\n").filter(Boolean);
      const res = await rlhfAPI.pipelineEvaluate(promptList, promptList.map(() => "dummy response"));
      setEvalResult(res);
    } catch { /* no backend */ }
  };

  return (
    <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
      <div className="bg-surface-light rounded-xl border border-white/5 p-5">
        <h2 className="text-sm font-semibold mb-3 flex items-center gap-2"><BarChart3 className="w-4 h-4 text-accent" /> Pipeline Iteration</h2>
        <div className="space-y-2">
          <div>
            <label className="text-xs text-gray-400">Prompts (one per line)</label>
            <textarea className="w-full bg-surface border border-white/10 rounded-lg px-3 py-2 text-sm h-32 mt-1" value={prompts} onChange={(e) => setPrompts(e.target.value)} />
          </div>
          <div className="flex gap-2">
            <button onClick={iterate} disabled={loading} className="flex-1 bg-accent py-2 rounded-lg text-sm font-medium disabled:opacity-50 flex items-center justify-center gap-1.5">
              <Play className="w-4 h-4" /> {loading ? "Running..." : "Run Iteration"}
            </button>
            <button onClick={evaluate} className="bg-surface-lighter border border-white/10 px-4 py-2 rounded-lg text-sm">Evaluate</button>
          </div>
        </div>
      </div>

      <div className="bg-surface-light rounded-xl border border-white/5 p-5">
        <h2 className="text-sm font-semibold mb-3">Results</h2>
        {result && (
          <div className="space-y-3">
            <div className="grid grid-cols-2 gap-3">
              <StatCard label="Prompts" value={result.n_prompts} accent="blue" />
              {result.avg_reward !== undefined && <StatCard label="Avg Reward" value={result.avg_reward.toFixed(3)} accent="green" />}
            </div>
            {result.training && (
              <div className="bg-surface rounded-lg p-3">
                <pre className="text-xs text-gray-300 whitespace-pre-wrap">{JSON.stringify(result.training, null, 2)}</pre>
              </div>
            )}
          </div>
        )}
        {evalResult && (
          <div className="mt-4 bg-surface rounded-lg p-3">
            <div className="text-xs text-gray-400 mb-1">Evaluation</div>
            <pre className="text-xs text-gray-300 whitespace-pre-wrap">{JSON.stringify(evalResult, null, 2)}</pre>
          </div>
        )}
        {!result && !evalResult && <p className="text-gray-500 text-sm">Run an iteration to see results.</p>}
      </div>
    </div>
  );
}
