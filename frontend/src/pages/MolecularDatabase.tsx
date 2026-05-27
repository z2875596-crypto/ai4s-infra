import { useState, useEffect } from "react";
import { dataAPI } from "@/api/client";
import type { PredictionResult } from "@/types";
import { Search, Clock, X, FlaskConical, ChevronRight, Star } from "lucide-react";

const POPULAR_MOLECULES = [
  { nameCN: "阿司匹林", nameEN: "Aspirin", key: "aspirin", desc: "最经典的解热镇痛药" },
  { nameCN: "青霉素G", nameEN: "Penicillin G", key: "penicillin", desc: "第一个抗生素" },
  { nameCN: "三磷酸腺苷", nameEN: "ATP", key: "atp", desc: "细胞的能量货币" },
  { nameCN: "咖啡因", nameEN: "Caffeine", key: "caffeine", desc: "最广泛使用的精神活性物质" },
  { nameCN: "维生素C", nameEN: "Vitamin C", key: "vitamin c", desc: "必需营养素与抗氧化剂" },
  { nameCN: "胆固醇", nameEN: "Cholesterol", key: "cholesterol", desc: "细胞膜的重要组成" },
  { nameCN: "多巴胺", nameEN: "Dopamine", key: "dopamine", desc: "重要的神经递质" },
  { nameCN: "血清素", nameEN: "Serotonin", key: "serotonin", desc: "调节情绪与睡眠" },
];

const KNOWN_MOLECULES: Record<string, {
  nameCN: string; nameEN: string; formula: string; mw: number;
  smiles: string; cas?: string;
}> = {
  "aspirin": { nameCN: "阿司匹林", nameEN: "Aspirin", formula: "C9H8O4", mw: 180.16, smiles: "CC(=O)Oc1ccccc1C(=O)O", cas: "50-78-2" },
  "caffeine": { nameCN: "咖啡因", nameEN: "Caffeine", formula: "C8H10N4O2", mw: 194.19, smiles: "CN1C=NC2=C1C(=O)N(C(=O)N2C)C", cas: "58-08-2" },
  "ibuprofen": { nameCN: "布洛芬", nameEN: "Ibuprofen", formula: "C13H18O2", mw: 206.28, smiles: "CC(C)CC1=CC=C(C=C1)C(C)C(=O)O", cas: "15687-27-1" },
  "paracetamol": { nameCN: "对乙酰氨基酚", nameEN: "Paracetamol", formula: "C8H9NO2", mw: 151.16, smiles: "CC(=O)NC1=CC=C(C=C1)O", cas: "103-90-2" },
  "glucose": { nameCN: "葡萄糖", nameEN: "Glucose", formula: "C6H12O6", mw: 180.16, smiles: "C(C1C(C(C(C(O1)O)O)O)O)O", cas: "50-99-7" },
  "ethanol": { nameCN: "乙醇", nameEN: "Ethanol", formula: "C2H6O", mw: 46.07, smiles: "CCO", cas: "64-17-5" },
  "methanol": { nameCN: "甲醇", nameEN: "Methanol", formula: "CH4O", mw: 32.04, smiles: "CO", cas: "67-56-1" },
  "acetone": { nameCN: "丙酮", nameEN: "Acetone", formula: "C3H6O", mw: 58.08, smiles: "CC(=O)C", cas: "67-64-1" },
  "benzene": { nameCN: "苯", nameEN: "Benzene", formula: "C6H6", mw: 78.11, smiles: "c1ccccc1", cas: "71-43-2" },
  "toluene": { nameCN: "甲苯", nameEN: "Toluene", formula: "C7H8", mw: 92.14, smiles: "Cc1ccccc1", cas: "108-88-3" },
  "water": { nameCN: "水", nameEN: "Water", formula: "H2O", mw: 18.02, smiles: "O", cas: "7732-18-5" },
  "morphine": { nameCN: "吗啡", nameEN: "Morphine", formula: "C17H19NO3", mw: 285.34, smiles: "CN1CCC23C4C1CC5=C2C(=C(C=C5)O)OC3C(C=C4)O", cas: "57-27-2" },
  "penicillin": { nameCN: "青霉素G", nameEN: "Penicillin G", formula: "C16H18N2O4S", mw: 334.39, smiles: "CC1(C(N2C(S1)C(C2=O)NC(=O)CC3=CC=CC=C3)C(=O)O)C", cas: "61-33-6" },
  "dopamine": { nameCN: "多巴胺", nameEN: "Dopamine", formula: "C8H11NO2", mw: 153.18, smiles: "C1=CC(=C(C=C1CCN)O)O", cas: "51-61-6" },
  "serotonin": { nameCN: "血清素", nameEN: "Serotonin", formula: "C10H12N2O", mw: 176.22, smiles: "C1=CC2=C(C=C1O)C(=CN2)CCN", cas: "50-67-9" },
  "testosterone": { nameCN: "睾酮", nameEN: "Testosterone", formula: "C19H28O2", mw: 288.42, smiles: "CC12CCC3C(C1CCC2O)CCC4=CC(=O)CCC34C", cas: "58-22-0" },
  "cholesterol": { nameCN: "胆固醇", nameEN: "Cholesterol", formula: "C27H46O", mw: 386.65, smiles: "CC(C)CCCC(C)C1CCC2C1(CCC3C2CC=C4C3(CCC(C4)O)C)C", cas: "57-88-5" },
  "atp": { nameCN: "三磷酸腺苷", nameEN: "ATP", formula: "C10H16N5O13P3", mw: 507.18, smiles: "C1=NC2=C(C(=N1)N)N=CN2C3C(C(C(O3)COP(=O)(O)OP(=O)(O)OP(=O)(O)O)O)O", cas: "56-65-5" },
  "vitamin c": { nameCN: "维生素C", nameEN: "Vitamin C", formula: "C6H8O6", mw: 176.12, smiles: "C(C(C1C(=C(C(=O)O1)O)O)O)O", cas: "50-81-7" },
  "vitamin d3": { nameCN: "维生素D3", nameEN: "Vitamin D3", formula: "C27H44O", mw: 384.64, smiles: "CC(C)CCCC(C)C1CCC2C1(CCCC2=CC=C3CC(CCC3=C)O)C", cas: "67-97-0" },
  "咖啡因": { nameCN: "咖啡因", nameEN: "Caffeine", formula: "C8H10N4O2", mw: 194.19, smiles: "CN1C=NC2=C1C(=O)N(C(=O)N2C)C", cas: "58-08-2" },
  "阿司匹林": { nameCN: "阿司匹林", nameEN: "Aspirin", formula: "C9H8O4", mw: 180.16, smiles: "CC(=O)Oc1ccccc1C(=O)O", cas: "50-78-2" },
  "布洛芬": { nameCN: "布洛芬", nameEN: "Ibuprofen", formula: "C13H18O2", mw: 206.28, smiles: "CC(C)CC1=CC=C(C=C1)C(C)C(=O)O", cas: "15687-27-1" },
  "葡萄糖": { nameCN: "葡萄糖", nameEN: "Glucose", formula: "C6H12O6", mw: 180.16, smiles: "C(C1C(C(C(C(O1)O)O)O)O)O", cas: "50-99-7" },
  "乙醇": { nameCN: "乙醇", nameEN: "Ethanol", formula: "C2H6O", mw: 46.07, smiles: "CCO", cas: "64-17-5" },
  "甲醇": { nameCN: "甲醇", nameEN: "Methanol", formula: "CH4O", mw: 32.04, smiles: "CO", cas: "67-56-1" },
  "苯": { nameCN: "苯", nameEN: "Benzene", formula: "C6H6", mw: 78.11, smiles: "c1ccccc1", cas: "71-43-2" },
  "丙酮": { nameCN: "丙酮", nameEN: "Acetone", formula: "C3H6O", mw: 58.08, smiles: "CC(=O)C", cas: "67-64-1" },
  "甲苯": { nameCN: "甲苯", nameEN: "Toluene", formula: "C7H8", mw: 92.14, smiles: "Cc1ccccc1", cas: "108-88-3" },
};

function isSMILES(s: string): boolean {
  return /[=#()\[\]@+\-/\\]/.test(s) && !/\s/.test(s) && s.length > 2;
}

function lookupMolecule(input: string) {
  const key = input.trim().toLowerCase();
  if (KNOWN_MOLECULES[key]) return KNOWN_MOLECULES[key];
  for (const mol of Object.values(KNOWN_MOLECULES)) {
    if (mol.nameCN === input.trim()) return mol;
    if (mol.nameEN.toLowerCase() === key) return mol;
    if (mol.formula.toLowerCase() === key) return mol;
    if (mol.cas === input.trim()) return mol;
  }
  return null;
}

const HISTORY_KEY = "molecule_search_history";

function loadHistory(): string[] {
  try {
    const raw = localStorage.getItem(HISTORY_KEY);
    return raw ? JSON.parse(raw) : [];
  } catch { return []; }
}

function saveHistory(term: string) {
  const history = loadHistory().filter((h) => h !== term);
  history.unshift(term);
  localStorage.setItem(HISTORY_KEY, JSON.stringify(history.slice(0, 20)));
}

export default function MolecularDatabase() {
  const [query, setQuery] = useState("");
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<{
    nameCN: string; nameEN: string; formula: string; mw: number;
    smiles: string; canonicalSmiles: string; inchi: string; cas?: string;
    logp?: number; hbd?: number; hba?: number; tpsa?: number;
  } | null>(null);
  const [error, setError] = useState("");
  const [history, setHistory] = useState<string[]>(loadHistory);

  const clearHistory = () => {
    localStorage.removeItem(HISTORY_KEY);
    setHistory([]);
  };

  const search = async (input?: string) => {
    const term = (input ?? query).trim();
    if (!term) return;
    setLoading(true);
    setError("");
    setResult(null);

    try {
      let smiles = "";
      const known = lookupMolecule(term);

      if (known) {
        smiles = known.smiles;
      } else if (isSMILES(term)) {
        smiles = term;
      } else {
        setError("未找到该分子，请尝试输入 SMILES 表达式、英文名或 CAS 号");
        setLoading(false);
        return;
      }

      saveHistory(term);
      setHistory(loadHistory());

      const pred = await dataAPI.predictMolecule(smiles);

      if (!pred.valid) {
        setError(pred.error || "无效的分子结构");
        setLoading(false);
        return;
      }

      setResult({
        nameCN: known?.nameCN ?? "",
        nameEN: known?.nameEN ?? "",
        formula: pred.molecular_formula,
        mw: pred.molecular_weight,
        smiles,
        canonicalSmiles: pred.canonical_smiles,
        inchi: "",
        cas: known?.cas,
        logp: pred.logp,
        hbd: pred.h_bond_donors,
        hba: pred.h_bond_acceptors,
        tpsa: pred.tpsa,
      });
    } catch (e: unknown) {
      setError((e as Error).message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div>
      <div className="mb-6">
        <h1 className="text-xl font-bold text-slate-800">分子数据库</h1>
        <p className="text-sm text-slate-500 mt-1">查询分子基本信息，支持名称、CAS 号或 SMILES 搜索</p>
      </div>

      {/* Search box */}
      <div className="bg-white rounded-xl border border-slate-200 shadow-sm p-6 mb-6">
        <div className="flex gap-3">
          <div className="flex-1 relative">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-5 h-5 text-slate-400" />
            <input
              className="w-full bg-slate-50 border border-slate-200 rounded-lg pl-10 pr-4 py-3 text-sm focus:outline-none focus:ring-2 focus:ring-brand-500 focus:border-transparent"
              placeholder="输入分子名称、CAS 号或 SMILES 搜索..."
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && search()}
            />
          </div>
          <button
            onClick={() => search()}
            disabled={loading}
            className="bg-brand-700 hover:bg-brand-800 text-white px-6 py-3 rounded-lg text-sm font-medium transition-colors disabled:opacity-50 flex items-center gap-2"
          >
            <Search className="w-4 h-4" />
            {loading ? "搜索中..." : "搜索"}
          </button>
        </div>
        <p className="text-xs text-slate-400 mt-2">
          试试：aspirin、咖啡因、C6H12O6、50-78-2、CC(=O)Oc1ccccc1C(=O)O
        </p>
      </div>

      {/* Popular molecules */}
      <div className="bg-white rounded-xl border border-slate-200 shadow-sm p-5 mb-6">
        <h3 className="text-sm font-semibold text-slate-700 flex items-center gap-2 mb-3">
          <Star className="w-4 h-4 text-amber-500" />
          热门分子推荐
        </h3>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
          {POPULAR_MOLECULES.map((mol) => (
            <button
              key={mol.key}
              onClick={() => {
                const known = lookupMolecule(mol.key);
                if (known) {
                  setQuery(known.nameEN || known.nameCN);
                  search(known.nameEN || known.nameCN);
                }
              }}
              className="text-left p-3 rounded-lg bg-slate-50 hover:bg-brand-50 border border-slate-100 hover:border-brand-200 transition-colors group"
            >
              <div className="text-xs font-medium text-slate-700 group-hover:text-brand-700 truncate">
                {mol.nameCN}
              </div>
              <div className="text-[10px] text-slate-400 mt-0.5 truncate">
                {mol.nameEN}
              </div>
              <div className="text-[10px] text-slate-300 mt-0.5 truncate">
                {mol.desc}
              </div>
            </button>
          ))}
        </div>
      </div>

      {/* Error */}
      {error && (
        <div className="bg-red-50 border border-red-200 rounded-lg p-4 text-sm text-red-700 mb-6">{error}</div>
      )}

      {/* Result */}
      {result && (
        <div className="bg-white rounded-xl border border-slate-200 shadow-sm p-6 mb-6">
          <h2 className="text-lg font-bold text-slate-800 mb-4 flex items-center gap-2">
            <FlaskConical className="w-5 h-5 text-brand-700" />
            {result.nameCN && result.nameEN
              ? `${result.nameCN}（${result.nameEN}）`
              : result.nameEN || result.nameCN || result.canonicalSmiles}
          </h2>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            {result.nameCN && result.nameEN && (
              <Property label="分子名称" value={`${result.nameCN}（${result.nameEN}）`} />
            )}
            {result.cas && <Property label="CAS 号" value={result.cas} mono />}
            <Property label="Molecular Formula" value={result.formula} mono />
            <Property label="Molecular Weight" value={`${result.mw.toFixed(2)} g/mol`} mono />
            <Property label="SMILES" value={result.canonicalSmiles} mono />
            {result.logp !== undefined && <Property label="LogP" value={result.logp.toFixed(2)} mono />}
            {result.hbd !== undefined && <Property label="H-Bond Donors" value={String(result.hbd)} mono />}
            {result.hba !== undefined && <Property label="H-Bond Acceptors" value={String(result.hba)} mono />}
            {result.tpsa !== undefined && <Property label="TPSA" value={`${result.tpsa.toFixed(2)} Å²`} mono />}
          </div>
        </div>
      )}

      {/* Search history */}
      <div className="bg-white rounded-xl border border-slate-200 shadow-sm p-5">
        <div className="flex items-center justify-between mb-3">
          <h3 className="text-sm font-semibold text-slate-700 flex items-center gap-2">
            <Clock className="w-4 h-4 text-slate-400" />
            最近搜索
          </h3>
          {history.length > 0 && (
            <button
              onClick={clearHistory}
              className="text-xs text-slate-400 hover:text-red-500 flex items-center gap-1 transition-colors"
            >
              <X className="w-3 h-3" /> 清空记录
            </button>
          )}
        </div>
        {history.length === 0 ? (
          <p className="text-sm text-slate-400 text-center py-4">暂无搜索记录，开始搜索分子吧</p>
        ) : (
          <div className="flex flex-wrap gap-2">
            {history.map((term, idx) => (
              <button
                key={idx}
                onClick={() => { setQuery(term); search(term); }}
                className="flex items-center gap-1.5 px-3 py-1.5 bg-slate-50 hover:bg-brand-50 text-slate-600 hover:text-brand-700 rounded-full text-sm border border-slate-200 hover:border-brand-200 transition-colors"
              >
                <Clock className="w-3 h-3" />
                {term}
                <ChevronRight className="w-3 h-3" />
              </button>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

function Property({ label, value, mono }: { label: string; value: string; mono?: boolean }) {
  return (
    <div className="bg-slate-50 rounded-lg px-4 py-3 flex justify-between items-center">
      <span className="text-sm text-slate-500">{label}</span>
      <span className={`text-sm font-medium text-slate-800 ${mono ? "font-mono" : ""}`}>{value}</span>
    </div>
  );
}
