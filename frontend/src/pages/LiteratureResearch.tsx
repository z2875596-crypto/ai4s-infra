import { useState, useEffect, useMemo } from "react";
import { agentAPI } from "@/api/client";
import type { LiteratureResult } from "@/types";
import { Search, BookOpen, FileText, ChevronDown, ChevronUp, Download, ExternalLink, Clock, X, TrendingUp, Flame, Newspaper } from "lucide-react";

// ── Search history ──
const HISTORY_KEY = "lit_search_history";

function loadHistory(): string[] {
  try { const raw = localStorage.getItem(HISTORY_KEY); return raw ? JSON.parse(raw) : []; }
  catch { return []; }
}

function saveHistoryToStore(term: string) {
  const history = loadHistory().filter((h) => h !== term);
  history.unshift(term);
  localStorage.setItem(HISTORY_KEY, JSON.stringify(history.slice(0, 20)));
}

function clearHistoryFromStore() {
  localStorage.removeItem(HISTORY_KEY);
}

// ── Search stats ──
const STATS_KEY = "lit_search_stats";
interface SearchStats { totalSearches: number; keywordCounts: Record<string, number>; weeklySearches: Record<string, number>; }

function loadStats(): SearchStats {
  try { const raw = localStorage.getItem(STATS_KEY); return raw ? JSON.parse(raw) : { totalSearches: 0, keywordCounts: {}, weeklySearches: {} }; }
  catch { return { totalSearches: 0, keywordCounts: {}, weeklySearches: {} }; }
}

function recordSearchStat(term: string) {
  const weekKey = getWeekKey();
  const stats = loadStats();
  stats.totalSearches++;
  stats.keywordCounts[term] = (stats.keywordCounts[term] || 0) + 1;
  stats.weeklySearches[weekKey] = (stats.weeklySearches[weekKey] || 0) + 1;
  localStorage.setItem(STATS_KEY, JSON.stringify(stats));
}

function getWeekKey(): string {
  const now = new Date();
  const startOfYear = new Date(now.getFullYear(), 0, 1);
  const week = Math.ceil(((now.getTime() - startOfYear.getTime()) / 86400000 + startOfYear.getDay() + 1) / 7);
  return `${now.getFullYear()}-W${week}`;
}

// ── BibTeX ──
function generateBibTeX(paper: {
  paperId: string; title: string; authors: string[];
  year: number | null; venue: string; doi: string;
}): string {
  const firstAuthor = paper.authors[0]?.split(" ").pop() ?? "unknown";
  const key = `${firstAuthor}${paper.year ?? "0000"}`;
  const lines = [
    `@article{${key},`,
    `  title = {${paper.title}},`,
    `  author = {${paper.authors.join(" and ")}},`,
  ];
  if (paper.year) lines.push(`  year = {${paper.year}},`);
  if (paper.venue) lines.push(`  journal = {${paper.venue}},`);
  if (paper.doi) lines.push(`  doi = {${paper.doi}},`);
  lines.push("}");
  return lines.join("\n");
}

function downloadBibTeX(paper: {
  paperId: string; title: string; authors: string[];
  year: number | null; venue: string; doi: string;
}) {
  const bib = generateBibTeX(paper);
  const blob = new Blob([bib], { type: "text/plain" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `${paper.paperId}.bib`;
  a.click();
  URL.revokeObjectURL(url);
}

// ── Hot topics ──
const HOT_TOPICS = [
  { keyword: "Perovskite Solar Cells", label: "钙钛矿太阳能电池", emoji: "☀️" },
  { keyword: "Metal-Organic Frameworks", label: "金属有机框架 (MOF)", emoji: "🧱" },
  { keyword: "AI Drug Discovery", label: "AI 辅助药物发现", emoji: "💊" },
  { keyword: "Green Chemistry", label: "绿色化学", emoji: "🌿" },
  { keyword: "2D Materials graphene", label: "二维材料（石墨烯等）", emoji: "📐" },
  { keyword: "CRISPR Chemistry", label: "基因编辑化学", emoji: "🧬" },
];

// ── News (Semantic Scholar API) ──
interface NewsPaper { title: string; authors: string; year: number; venue: string; url: string; citations: number; }

const DEMO_NEWS: NewsPaper[] = [
  { title: "Machine Learning-Guided Protein Engineering: Recent Advances", authors: "Yang et al.", year: 2026, venue: "Nature Chemistry", url: "https://www.nature.com/nchem/", citations: 234 },
  { title: "Electrochemical CO2 Reduction on Single-Atom Catalysts", authors: "Wang et al.", year: 2026, venue: "JACS", url: "https://pubs.acs.org/jacs", citations: 189 },
  { title: "Self-Healing Polymers via Dynamic Covalent Networks", authors: "Chen et al.", year: 2026, venue: "Science", url: "https://www.science.org/", citations: 312 },
  { title: "Quantum Computing for Molecular Energy Calculations", authors: "Kim et al.", year: 2026, venue: "Nature", url: "https://www.nature.com/", citations: 156 },
  { title: "Biodegradable Microplastics: Design and Degradation", authors: "Liu et al.", year: 2026, venue: "Angewandte Chemie", url: "https://onlinelibrary.wiley.com/journal/15213757", citations: 201 },
];

export default function LiteratureResearch() {
  const [query, setQuery] = useState("");
  const [limit, setLimit] = useState("10");
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<LiteratureResult | null>(null);
  const [error, setError] = useState("");
  const [expanded, setExpanded] = useState<Set<string>>(new Set());
  const [expandedDetails, setExpandedDetails] = useState<Set<string>>(new Set());
  const [history, setHistory] = useState<string[]>(loadHistory);
  const [news, setNews] = useState<NewsPaper[]>(DEMO_NEWS);
  const [newsLoading, setNewsLoading] = useState(false);

  const [stats, setStats] = useState<SearchStats>(loadStats);

  // Fetch news from Semantic Scholar on mount
  useEffect(() => {
    setNewsLoading(true);
    fetch(
      "https://api.semanticscholar.org/graph/v1/paper/search?query=chemistry&limit=5&fields=title,authors,year,venue,url,citationCount&sort=citationCount:desc"
    )
      .then((r) => r.json())
      .then((d) => {
        if (d.data?.length) {
          setNews(
            d.data.map((p: { title: string; authors: { name: string }[]; year: number | null; venue: string; url: string; citationCount: number }) => ({
              title: p.title,
              authors: p.authors?.slice(0, 2).map((a: { name: string }) => a.name).join(", ") ?? "Unknown",
              year: p.year ?? new Date().getFullYear(),
              venue: p.venue ?? "预印本",
              url: p.url ?? "#",
              citations: p.citationCount ?? 0,
            }))
          );
        }
      })
      .catch(() => { /* fallback to demo news */ })
      .finally(() => setNewsLoading(false));
  }, []);

  const search = async (searchTerm?: string) => {
    const term = (searchTerm ?? query).trim();
    if (!term) return;
    setQuery(term);
    setLoading(true);
    setError("");
    saveHistoryToStore(term);
    setHistory(loadHistory());
    recordSearchStat(term);
    setStats(loadStats());
    try {
      const res = await agentAPI.literatureSearch(term, parseInt(limit) || 10);
      setResult(res);
      setExpanded(new Set());
      setExpandedDetails(new Set());
    } catch (e: unknown) {
      setError((e as Error).message);
    } finally {
      setLoading(false);
    }
  };

  const clearHistory = () => { clearHistoryFromStore(); setHistory([]); };

  const removeHistoryItem = (item: string) => {
    const updated = history.filter((h) => h !== item);
    localStorage.setItem(HISTORY_KEY, JSON.stringify(updated));
    setHistory(updated);
  };

  const toggleAbstract = (id: string) => {
    setExpanded((prev) => {
      const next = new Set(prev);
      next.has(id) ? next.delete(id) : next.add(id);
      return next;
    });
  };

  const toggleDetails = (id: string) => {
    setExpandedDetails((prev) => {
      const next = new Set(prev);
      next.has(id) ? next.delete(id) : next.add(id);
      return next;
    });
  };

  const topKeywords = useMemo(() => {
    return Object.entries(stats.keywordCounts)
      .sort(([, a], [, b]) => b - a)
      .slice(0, 5);
  }, [stats]);

  return (
    <div>
      <div className="mb-6">
        <h1 className="text-xl font-bold text-slate-800">文献调研</h1>
        <p className="text-sm text-slate-500 mt-1">搜索化学领域学术论文，浏览前沿热点与最新动态</p>
      </div>

      {/* Search Bar */}
      <div className="bg-white rounded-xl border border-slate-200 shadow-sm p-5 mb-5">
        <div className="flex gap-3">
          <div className="flex-1 relative">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-5 h-5 text-slate-400" />
            <input
              className="w-full bg-slate-50 border border-slate-200 rounded-lg pl-10 pr-4 py-3 text-sm focus:outline-none focus:ring-2 focus:ring-brand-500 focus:border-transparent"
              placeholder="输入研究关键词，如：perovskite、MOF、有机合成..."
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && search()}
            />
          </div>
          <select
            className="w-20 bg-slate-50 border border-slate-200 rounded-lg px-2 py-3 text-sm text-slate-600 focus:outline-none focus:ring-2 focus:ring-brand-500"
            value={limit}
            onChange={(e) => setLimit(e.target.value)}
          >
            {[5, 10, 20, 50].map((n) => (
              <option key={n} value={n}>{n}</option>
            ))}
          </select>
          <button
            onClick={() => search()}
            disabled={loading}
            className="bg-brand-700 hover:bg-brand-800 text-white px-6 py-3 rounded-lg text-sm font-medium transition-colors disabled:opacity-50 flex items-center gap-2"
          >
            <Search className="w-4 h-4" />
            {loading ? "搜索中..." : "搜索"}
          </button>
        </div>

        {/* Search history */}
        {history.length > 0 && (
          <div className="mt-3 pt-3 border-t border-slate-100">
            <div className="flex items-center justify-between mb-2">
              <span className="text-xs text-slate-400 flex items-center gap-1"><Clock className="w-3 h-3" /> 最近搜索</span>
              <button onClick={clearHistory} className="text-xs text-slate-400 hover:text-red-500 transition-colors">清空全部</button>
            </div>
            <div className="flex flex-wrap gap-1.5">
              {history.slice(0, 8).map((term) => (
                <span key={term} className="inline-flex items-center gap-1 px-2.5 py-1 bg-slate-50 rounded-full text-xs text-slate-600 border border-slate-200 group">
                  <button onClick={() => search(term)} className="hover:text-brand-700 transition-colors">{term}</button>
                  <button onClick={() => removeHistoryItem(term)} className="text-slate-300 hover:text-red-400 transition-colors"><X className="w-3 h-3" /></button>
                </span>
              ))}
            </div>
          </div>
        )}
      </div>

      {/* Main content area */}
      <div className="grid grid-cols-1 lg:grid-cols-[280px_1fr_300px] gap-5">
        {/* Left sidebar: Hot topics */}
        <div className="space-y-5">
          <div className="bg-white rounded-xl border border-slate-200 shadow-sm p-4">
            <h3 className="text-sm font-semibold text-slate-700 flex items-center gap-2 mb-3">
              <Flame className="w-4 h-4 text-orange-500" />
              🔥 化学热点研究方向
            </h3>
            <div className="space-y-1.5">
              {HOT_TOPICS.map((topic) => (
                <button
                  key={topic.keyword}
                  onClick={() => search(topic.keyword)}
                  className="w-full text-left px-3 py-2 rounded-lg hover:bg-brand-50 transition-colors group border border-transparent hover:border-brand-100"
                >
                  <div className="flex items-center gap-2">
                    <span className="text-sm">{topic.emoji}</span>
                    <div className="flex-1 min-w-0">
                      <div className="text-xs font-medium text-slate-700 group-hover:text-brand-700 truncate">
                        {topic.label}
                      </div>
                      <div className="text-[10px] text-slate-400 truncate">{topic.keyword}</div>
                    </div>
                  </div>
                </button>
              ))}
            </div>
          </div>

          {/* Search stats */}
          {stats.totalSearches > 0 && (
            <div className="bg-white rounded-xl border border-slate-200 shadow-sm p-4">
              <h3 className="text-sm font-semibold text-slate-700 flex items-center gap-2 mb-3">
                <TrendingUp className="w-4 h-4 text-brand-500" />
                搜索统计
              </h3>
              <div className="space-y-2">
                <div className="flex justify-between text-xs">
                  <span className="text-slate-500">总搜索次数</span>
                  <span className="font-mono font-semibold text-slate-700">{stats.totalSearches}</span>
                </div>
                {topKeywords.length > 0 && (
                  <div>
                    <div className="text-xs text-slate-500 mb-1.5">最常搜索</div>
                    <div className="space-y-1">
                      {topKeywords.map(([kw, count], i) => (
                        <div key={kw} className="flex items-center gap-2 text-xs">
                          <span className="text-slate-400 w-4 text-right">{i + 1}.</span>
                          <button onClick={() => search(kw)} className="flex-1 text-left text-slate-600 hover:text-brand-700 truncate transition-colors">
                            {kw}
                          </button>
                          <span className="text-slate-400 font-mono">{count}次</span>
                        </div>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            </div>
          )}
        </div>

        {/* Center: Results / Empty state */}
        <div className="min-w-0">
          {error && (
            <div className="bg-red-50 border border-red-200 rounded-lg p-4 text-sm text-red-700 mb-4">{error}</div>
          )}

          {result ? (
            <div>
              <div className="flex items-center justify-between mb-4">
                <h3 className="text-sm font-semibold text-slate-700">
                  搜索：<span className="text-brand-700">"{result.query}"</span>
                  <span className="text-slate-400 ml-2 font-normal">（共 {result.total.toLocaleString()} 篇，显示 {result.count} 篇）</span>
                </h3>
              </div>
              <div className="space-y-3">
                {result.papers.map((paper, idx) => (
                  <div key={paper.paperId} className="bg-white rounded-xl border border-slate-200 shadow-sm hover:shadow-md hover:border-brand-200 transition-all">
                    <div className="p-5">
                      <div className="flex items-start gap-4">
                        <div className="flex-1 min-w-0">
                          <h4 className="text-sm font-semibold text-slate-800 leading-snug">
                            <span className="text-slate-300 mr-2 font-mono text-xs">#{idx + 1}</span>
                            {paper.url ? (
                              <a href={paper.url} target="_blank" rel="noopener noreferrer" className="hover:text-brand-600 transition-colors">
                                {paper.title}
                              </a>
                            ) : (paper.title)}
                          </h4>
                          <div className="flex flex-wrap items-center gap-x-3 gap-y-1 mt-2 text-xs text-slate-500">
                            {paper.authors.length > 0 && (
                              <span>
                                <span className="text-slate-400">作者：</span>
                                {paper.authors.slice(0, 3).join(", ")}{paper.authors.length > 3 && ` 等 ${paper.authors.length} 人`}
                              </span>
                            )}
                          </div>
                          <div className="flex flex-wrap items-center gap-x-4 gap-y-1 mt-1 text-xs text-slate-400">
                            {paper.venue && <span>期刊：{paper.venue}</span>}
                            {paper.year && <span>年份：{paper.year}</span>}
                            <span>引用：{paper.citationCount} 次</span>
                          </div>
                        </div>
                      </div>
                      <div className="flex gap-2 mt-3">
                        {paper.abstract && (
                          <button onClick={() => toggleAbstract(paper.paperId)} className="flex items-center gap-1 px-3 py-1.5 text-xs rounded-lg bg-slate-50 hover:bg-brand-50 text-slate-600 hover:text-brand-700 border border-slate-200 hover:border-brand-200 transition-colors">
                            <FileText className="w-3.5 h-3.5" />
                            {expanded.has(paper.paperId) ? "收起摘要" : "查看摘要"}
                            {expanded.has(paper.paperId) ? <ChevronUp className="w-3.5 h-3.5" /> : <ChevronDown className="w-3.5 h-3.5" />}
                          </button>
                        )}
                        <button onClick={() => toggleDetails(paper.paperId)} className="flex items-center gap-1 px-3 py-1.5 text-xs rounded-lg bg-slate-50 hover:bg-brand-50 text-slate-600 hover:text-brand-700 border border-slate-200 hover:border-brand-200 transition-colors">
                          <BookOpen className="w-3.5 h-3.5" />
                          {expandedDetails.has(paper.paperId) ? "收起详情" : "查看详情"}
                        </button>
                        <button onClick={() => downloadBibTeX(paper)} className="flex items-center gap-1 px-3 py-1.5 text-xs rounded-lg bg-brand-50 hover:bg-brand-100 text-brand-700 border border-brand-200 transition-colors">
                          <Download className="w-3.5 h-3.5" /> 导出 BibTeX
                        </button>
                        {paper.url && (
                          <a href={paper.url} target="_blank" rel="noopener noreferrer" className="flex items-center gap-1 px-3 py-1.5 text-xs rounded-lg bg-slate-50 hover:bg-slate-100 text-slate-500 border border-slate-200 transition-colors">
                            <ExternalLink className="w-3.5 h-3.5" /> 原文
                          </a>
                        )}
                      </div>
                      {expanded.has(paper.paperId) && paper.abstract && (
                        <div className="mt-3 bg-slate-50 rounded-lg p-4 text-sm text-slate-600 leading-relaxed border border-slate-100">
                          {paper.abstract}
                        </div>
                      )}
                      {expandedDetails.has(paper.paperId) && (
                        <div className="mt-3 bg-slate-50 rounded-lg p-4 border border-slate-100">
                          <PaperDetail paper={paper} bib={generateBibTeX(paper)} />
                        </div>
                      )}
                    </div>
                  </div>
                ))}
              </div>
              {result.papers.length === 0 && (
                <div className="bg-white rounded-xl border border-slate-200 shadow-sm p-12 text-center">
                  <BookOpen className="w-12 h-12 text-slate-300 mx-auto mb-3" />
                  <p className="text-slate-500">未找到相关论文</p>
                </div>
              )}
            </div>
          ) : (
            <div className="bg-white rounded-xl border border-slate-200 shadow-sm p-12 text-center">
              <BookOpen className="w-16 h-16 text-slate-200 mx-auto mb-4" />
              <p className="text-slate-500 font-medium">输入关键词开始文献搜索</p>
              <p className="text-sm text-slate-400 mt-1">支持中英文关键词，左侧有热点研究方向供你探索</p>
            </div>
          )}
        </div>

        {/* Right sidebar: News */}
        <div>
          <div className="bg-white rounded-xl border border-slate-200 shadow-sm p-4 sticky top-4">
            <h3 className="text-sm font-semibold text-slate-700 flex items-center gap-2 mb-3">
              <Newspaper className="w-4 h-4 text-blue-500" />
              化学前沿动态
            </h3>
            {newsLoading ? (
              <div className="space-y-3">
                {[1, 2, 3].map((i) => (
                  <div key={i} className="animate-pulse">
                    <div className="h-4 bg-slate-100 rounded w-3/4 mb-1.5" />
                    <div className="h-3 bg-slate-50 rounded w-1/2" />
                  </div>
                ))}
              </div>
            ) : (
              <div className="space-y-3">
                {news.slice(0, 5).map((paper, idx) => (
                  <a
                    key={idx}
                    href={paper.url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="block p-2.5 rounded-lg hover:bg-brand-50 transition-colors group border border-transparent hover:border-brand-100"
                  >
                    <div className="text-xs font-medium text-slate-700 group-hover:text-brand-700 leading-snug line-clamp-2">
                      {paper.title}
                    </div>
                    <div className="flex items-center gap-x-2 mt-1.5 text-[10px] text-slate-400">
                      <span>{paper.authors}</span>
                      <span>{paper.year}</span>
                      <span className="text-orange-500 font-medium">{paper.citations} 引用</span>
                    </div>
                  </a>
                ))}
              </div>
            )}
            <div className="mt-3 pt-2 border-t border-slate-100 text-[10px] text-slate-400 text-center">
              {newsLoading ? "正在获取数据..." : "数据来源：Semantic Scholar"}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

function PaperDetail({ paper, bib }: { paper: { paperId: string; title: string; authors: string[]; year: number | null; venue: string; doi: string; citationCount: number }; bib: string }) {
  return (
    <>
      <div className="grid grid-cols-1 md:grid-cols-2 gap-2 text-sm">
        <div className="flex justify-between py-1"><span className="text-slate-400">Title</span><span className="text-slate-700 text-right">{paper.title}</span></div>
        <div className="flex justify-between py-1"><span className="text-slate-400">Authors</span><span className="text-slate-700 text-right">{paper.authors.join("; ")}</span></div>
        <div className="flex justify-between py-1"><span className="text-slate-400">Journal</span><span className="text-slate-700 text-right">{paper.venue || "-"}</span></div>
        <div className="flex justify-between py-1"><span className="text-slate-400">Year</span><span className="text-slate-700 text-right">{paper.year ?? "-"}</span></div>
        <div className="flex justify-between py-1"><span className="text-slate-400">DOI</span><span className="text-slate-700 text-right font-mono text-xs">{paper.doi || "-"}</span></div>
        <div className="flex justify-between py-1"><span className="text-slate-400">Citations</span><span className="text-slate-700 text-right">{paper.citationCount}</span></div>
      </div>
      <div className="mt-3 pt-3 border-t border-slate-200">
        <div className="text-xs text-slate-400 mb-1">BibTeX</div>
        <pre className="text-xs text-slate-600 font-mono bg-white rounded p-2 border border-slate-200 overflow-x-auto">{bib}</pre>
      </div>
    </>
  );
}
