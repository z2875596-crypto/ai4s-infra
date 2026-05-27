import { useState, useEffect } from "react";
import { dataAPI } from "@/api/client";
import type { PredictionResult } from "@/types";
import { Beaker, HelpCircle, Clock, X, ChevronRight } from "lucide-react";

// ── Prediction history ──
interface HistoryEntry {
  query: string;
  formula: string;
  mw: number;
  logp: number;
  time: string;
}

const PRED_HISTORY_KEY = "prediction_history";

function loadPredHistory(): HistoryEntry[] {
  try { const raw = localStorage.getItem(PRED_HISTORY_KEY); return raw ? JSON.parse(raw) : []; }
  catch { return []; }
}

function savePredHistory(entry: HistoryEntry) {
  const history = loadPredHistory().filter((h) => h.query !== entry.query);
  history.unshift(entry);
  localStorage.setItem(PRED_HISTORY_KEY, JSON.stringify(history.slice(0, 10)));
}

function clearPredHistory() {
  localStorage.removeItem(PRED_HISTORY_KEY);
}

const QUICK_MOLECULES = [
  { label: "Aspirin（阿司匹林）", smiles: "CC(=O)Oc1ccccc1C(=O)O" },
  { label: "Caffeine（咖啡因）", smiles: "CN1C=NC2=C1C(=O)N(C(=O)N2C)C" },
  { label: "Ibuprofen（布洛芬）", smiles: "CC(C)CC1=CC=C(C=C1)C(C)C(=O)O" },
  { label: "Glucose（葡萄糖）", smiles: "C(C1C(C(C(C(O1)O)O)O)O)O" },
  { label: "Ethanol（乙醇）", smiles: "CCO" },
];

const NAME_TO_SMILES: Record<string, string> = {
  "aspirin": "CC(=O)Oc1ccccc1C(=O)O",
  "caffeine": "CN1C=NC2=C1C(=O)N(C(=O)N2C)C",
  "ibuprofen": "CC(C)CC1=CC=C(C=C1)C(C)C(=O)O",
  "paracetamol": "CC(=O)NC1=CC=C(C=C1)O",
  "glucose": "C(C1C(C(C(C(O1)O)O)O)O)O",
  "ethanol": "CCO",
  "阿司匹林": "CC(=O)Oc1ccccc1C(=O)O",
  "咖啡因": "CN1C=NC2=C1C(=O)N(C(=O)N2C)C",
  "布洛芬": "CC(C)CC1=CC=C(C=C1)C(C)C(=O)O",
  "葡萄糖": "C(C1C(C(C(C(O1)O)O)O)O)O",
  "乙醇": "CCO",
};

function logpExplanation(logp: number): string {
  if (logp < 0) return "亲水性强，易溶于水";
  if (logp < 1) return "亲水性较好";
  if (logp < 3) return "亲水亲脂适中";
  if (logp < 5) return "亲脂性较强，易溶于有机溶剂";
  return "亲脂性强，难溶于水";
}

function tpsaExplanation(tpsa: number): string {
  if (tpsa < 60) return "极性较低，容易穿透细胞膜";
  if (tpsa < 140) return "极性适中，通常具有良好的口服生物利用度";
  return "极性较高，口服吸收可能受限";
}

export default function PropertyPrediction() {
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<PredictionResult | null>(null);
  const [error, setError] = useState("");
  const [history, setHistory] = useState<HistoryEntry[]>(loadPredHistory);

  const predict = async (smilesOrName?: string) => {
    const raw = (smilesOrName ?? input).trim();
    if (!raw) return;

    let smiles = raw;
    if (!/[=#()\[\]]/.test(raw)) {
      const mapped = NAME_TO_SMILES[raw.toLowerCase()];
      if (mapped) smiles = mapped;
    }

    setLoading(true);
    setError("");
    setResult(null);
    try {
      const res = await dataAPI.predictMolecule(smiles);
      if (!res.valid) {
        setError(res.error || "无效的分子结构，请检查 SMILES 表达式");
      } else {
        setResult(res);
        savePredHistory({
          query: raw,
          formula: res.molecular_formula,
          mw: res.molecular_weight,
          logp: res.logp,
          time: new Date().toLocaleString("zh-CN"),
        });
        setHistory(loadPredHistory());
      }
    } catch (e: unknown) {
      setError((e as Error).message);
    } finally {
      setLoading(false);
    }
  };

  const clearHistory = () => { clearPredHistory(); setHistory([]); };

  return (
    <div>
      <div className="mb-6">
        <h1 className="text-xl font-bold text-slate-800">性质预测</h1>
        <p className="text-sm text-slate-500 mt-1">输入分子名称或 SMILES，预测分子理化性质与类药性</p>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Input panel */}
        <div className="bg-white rounded-xl border border-slate-200 shadow-sm p-6">
          <h2 className="text-sm font-semibold text-slate-700 mb-3 flex items-center gap-2">
            <Beaker className="w-4 h-4 text-brand-700" /> 输入分子
          </h2>
          <p className="text-xs text-slate-500 mb-4">
            输入分子名称（如 aspirin、咖啡因）或直接输入 SMILES 表达式，点击预测查看各项理化性质。
          </p>
          <div className="space-y-3">
            <input
              className="w-full bg-slate-50 border border-slate-200 rounded-lg px-4 py-3 text-sm focus:outline-none focus:ring-2 focus:ring-brand-500 focus:border-transparent font-mono"
              placeholder="输入分子名称或 SMILES，如：CC(=O)Oc1ccccc1C(=O)O"
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && predict()}
            />
            <button
              onClick={() => predict()}
              disabled={loading}
              className="w-full bg-brand-700 hover:bg-brand-800 text-white py-3 rounded-lg text-sm font-medium transition-colors disabled:opacity-50 flex items-center justify-center gap-2"
            >
              <Beaker className="w-4 h-4" />
              {loading ? "预测中..." : "开始预测"}
            </button>
          </div>
          <div className="mt-4">
            <p className="text-xs text-slate-400 mb-2">快捷选择：</p>
            <div className="flex flex-wrap gap-1.5">
              {QUICK_MOLECULES.map(({ label, smiles }) => (
                <button
                  key={smiles}
                  type="button"
                  onClick={() => { setInput(smiles); setResult(null); setError(""); }}
                  className={`px-3 py-1.5 text-xs rounded-full transition-colors border ${
                    input === smiles
                      ? "bg-brand-700 text-white border-brand-700"
                      : "bg-slate-50 text-slate-600 hover:bg-brand-50 hover:text-brand-700 border-slate-200 hover:border-brand-200"
                  }`}
                >
                  {label}
                </button>
              ))}
            </div>
          </div>
        </div>

        {/* Results panel */}
        <div className="bg-white rounded-xl border border-slate-200 shadow-sm p-6">
          <h2 className="text-sm font-semibold text-slate-700 mb-3">预测结果</h2>

          {error && (
            <div className="bg-red-50 border border-red-200 rounded-lg p-4 text-sm text-red-700 mb-4">{error}</div>
          )}

          {result && result.valid && (
            <div>
              <div className="bg-slate-50 rounded-lg p-3 mb-4 border border-slate-100">
                <div className="text-xs text-slate-400 mb-1">SMILES</div>
                <div className="text-sm font-mono text-brand-700 break-all">{result.canonical_smiles}</div>
              </div>

              <div className="space-y-1.5">
                <ResultRow label="Molecular Weight" value={`${result.molecular_weight.toFixed(2)} g/mol`} help="分子量，即分子的相对质量，单位为 g/mol" />
                <ResultRow label="Molecular Formula" value={result.molecular_formula} help="分子式，表示分子中各类原子的数量" />
                <ResultRow
                  label="LogP"
                  value={result.logp.toFixed(2)}
                  help={`脂水分配系数的对数值。${logpExplanation(result.logp)}`}
                  extra={logpExplanation(result.logp)}
                />
                <ResultRow label="H-Bond Donors" value={String(result.h_bond_donors)} help="氢键供体数量，指分子中可提供氢原子的基团数量" />
                <ResultRow label="H-Bond Acceptors" value={String(result.h_bond_acceptors)} help="氢键受体数量，指分子中可接受氢原子的基团数量" />
                <ResultRow label="Rotatable Bonds" value={String(result.rotatable_bonds)} help="可旋转键数量，反映分子的柔性程度" />
                <ResultRow
                  label="TPSA"
                  value={`${result.tpsa.toFixed(2)} Å²`}
                  help={`拓扑极性表面积。${tpsaExplanation(result.tpsa)}`}
                  extra={tpsaExplanation(result.tpsa)}
                />
                <ResultRow label="Heavy Atoms" value={String(result.heavy_atom_count)} help="重原子（非氢原子）数量" />
                <ResultRow label="Ring Count" value={`${result.ring_count}（芳香环: ${result.aromatic_rings}）`} help="环的数量，包括脂肪环和芳香环" />
              </div>

              {/* Lipinski Rule of Five */}
              <LipinskiRule
                mw={result.molecular_weight}
                logp={result.logp}
                hbd={result.h_bond_donors}
                hba={result.h_bond_acceptors}
              />
            </div>
          )}

          {!result && !error && (
            <div className="flex flex-col items-center justify-center py-12 text-center">
              <Beaker className="w-12 h-12 text-slate-200 mb-3" />
              <p className="text-sm text-slate-500">在左侧输入分子名称或 SMILES</p>
              <p className="text-xs text-slate-400 mt-1">点击"开始预测"查看结果</p>
            </div>
          )}

          {/* Prediction history */}
          {history.length > 0 && (
            <div className="mt-4 pt-4 border-t border-slate-100">
              <div className="flex items-center justify-between mb-2">
                <h3 className="text-xs font-semibold text-slate-500 flex items-center gap-1.5">
                  <Clock className="w-3.5 h-3.5" /> 预测历史
                </h3>
                <button onClick={clearHistory} className="text-xs text-slate-400 hover:text-red-500 transition-colors flex items-center gap-1">
                  <X className="w-3 h-3" /> 清空
                </button>
              </div>
              <div className="space-y-1">
                {history.slice(0, 8).map((entry, i) => (
                  <button
                    key={i}
                    onClick={() => { setInput(entry.query); predict(entry.query); }}
                    className="w-full flex items-center gap-2 px-3 py-2 rounded-lg hover:bg-brand-50 transition-colors group border border-transparent hover:border-brand-100"
                  >
                    <span className="text-xs font-mono text-slate-600 group-hover:text-brand-700 truncate flex-1 text-left">
                      {entry.query}
                    </span>
                    <span className="text-[10px] text-slate-400 font-mono">{entry.formula}</span>
                    <span className="text-[10px] text-slate-400">{entry.mw.toFixed(1)} g/mol</span>
                    <span className="text-[10px] text-slate-300">{entry.time.split(" ")[0]}</span>
                    <ChevronRight className="w-3 h-3 text-slate-300 group-hover:text-brand-500" />
                  </button>
                ))}
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

function ResultRow({ label, value, help, extra }: { label: string; value: string; help: string; extra?: string }) {
  return (
    <div className="bg-slate-50 rounded-lg px-4 py-3">
      <div className="flex justify-between items-center">
        <div className="flex items-center gap-1.5">
          <span className="text-sm text-slate-600">{label}</span>
          <span className="group relative">
            <HelpCircle className="w-3.5 h-3.5 text-slate-300 hover:text-slate-500 cursor-help" />
            <span className="absolute bottom-full left-1/2 -translate-x-1/2 mb-1.5 hidden group-hover:block bg-slate-800 text-white text-xs rounded-lg px-3 py-1.5 w-48 text-center leading-relaxed z-10 shadow-lg">
              {help}
            </span>
          </span>
        </div>
        <div className="text-right">
          <span className="text-sm font-medium text-slate-800 font-mono">{value}</span>
          {extra && <p className="text-xs text-slate-400 mt-0.5">{extra}</p>}
        </div>
      </div>
    </div>
  );
}

function LipinskiRule({ mw, logp, hbd, hba }: { mw: number; logp: number; hbd: number; hba: number }) {
  const rules = [
    { label: "MW ≤ 500", pass: mw <= 500, value: `${mw.toFixed(2)} g/mol` },
    { label: "LogP ≤ 5", pass: logp <= 5, value: logp.toFixed(2) },
    { label: "H-Bond Donors ≤ 5", pass: hbd <= 5, value: String(hbd) },
    { label: "H-Bond Acceptors ≤ 10", pass: hba <= 10, value: String(hba) },
  ];

  const violations = rules.filter((r) => !r.pass).length;

  return (
    <div className="mt-4 bg-brand-50 rounded-lg p-4 border border-brand-100">
      <div className="flex items-center gap-2 mb-3">
        <span className="text-sm font-semibold text-brand-800">Lipinski Rule of Five（类药五规则）</span>
        <span className="group relative">
          <HelpCircle className="w-3.5 h-3.5 text-brand-400 hover:text-brand-600 cursor-help" />
          <span className="absolute bottom-full left-1/2 -translate-x-1/2 mb-1.5 hidden group-hover:block bg-slate-800 text-white text-xs rounded-lg px-3 py-1.5 w-60 text-center leading-relaxed z-10 shadow-lg">
            用于评估化合物是否具有口服药物潜力的经验法则。违反 0-1 条规则通常表示较好的类药性。
          </span>
        </span>
      </div>
      <div className="grid grid-cols-2 gap-2">
        {rules.map((rule) => (
          <div
            key={rule.label}
            className={`flex items-center justify-between px-3 py-2 rounded-lg text-sm ${
              rule.pass ? "bg-emerald-50 text-emerald-700" : "bg-red-50 text-red-700"
            }`}
          >
            <span>{rule.label}</span>
            <span className="font-mono text-xs">{rule.value}</span>
          </div>
        ))}
      </div>
      <div className={`mt-3 text-center text-sm font-medium ${violations <= 1 ? "text-emerald-700" : "text-red-600"}`}>
        {violations === 0
          ? "完全符合 Lipinski 五规则，具有良好的口服药物开发潜力"
          : violations === 1
          ? "违反 1 条规则，仍可能具有较好的口服生物利用度"
          : `违反 ${violations} 条规则，口服生物利用度可能受限`}
      </div>
    </div>
  );
}
