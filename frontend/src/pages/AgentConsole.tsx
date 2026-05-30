import { useState, useRef, useEffect, useCallback, useMemo } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import {
  Send, Brain, Wrench, Eye, FileText, AlertCircle, Loader2,
  History, Trash2, ChevronDown, ChevronRight,
  Zap, BookOpen, CheckCircle2,
} from "lucide-react";
import type { AgentEvent, AgentSession, AgentStep } from "@/types";
import { agentResearchAPI } from "@/api/client";

/* ── Status helpers ────────────────────────────────────── */

const TOOL_LABELS: Record<string, string> = {
  search_literature: "正在搜索文献…",
  search_pubchem: "正在查询 PubChem 化合物…",
  predict_properties: "正在预测分子性质…",
  calculate_molar_mass: "正在计算摩尔质量…",
  lookup_element: "正在查询元素信息…",
};

function getStatusText(events: AgentEvent[], running: boolean): { text: string; step: number } {
  if (!running) return { text: "研究完成", step: 0 };
  // Find the latest action event
  for (let i = events.length - 1; i >= 0; i--) {
    if (events[i].type === "action" && events[i].tool_name) {
      const label = TOOL_LABELS[events[i].tool_name!] || `正在执行: ${events[i].tool_name}`;
      return { text: `${label}（步骤 ${events[i].step_index}）`, step: events[i].step_index };
    }
  }
  // If there are thought events but no action yet
  const lastThought = [...events].reverse().find(e => e.type === "thought");
  if (lastThought) return { text: `正在思考…（步骤 ${lastThought.step_index}）`, step: lastThought.step_index };
  return { text: "正在分析问题…", step: 0 };
}

const EXAMPLE_QUERIES = [
  "分析布洛芬的 ADMET 性质",
  "研究钙钛矿太阳能电池最新进展",
  "寻找 COX-2 抑制剂候选分子",
];

/* ── Step card colors ──────────────────────────────────── */

const STEP_COLORS: Record<string, { icon: React.ComponentType<{ className?: string }>; label: string; border: string; bg: string; dot: string }> = {
  thought:     { icon: Brain,       label: "思考",   border: "border-l-blue-500",   bg: "bg-blue-50/60",   dot: "bg-blue-500" },
  action:      { icon: Wrench,      label: "工具调用", border: "border-l-purple-500", bg: "bg-purple-50/60", dot: "bg-purple-500" },
  observation: { icon: Eye,         label: "观察结果", border: "border-l-emerald-500", bg: "bg-emerald-50/60", dot: "bg-emerald-500" },
  answer:      { icon: FileText,    label: "最终报告", border: "border-l-amber-500",  bg: "bg-amber-50/60",  dot: "bg-amber-500" },
  error:       { icon: AlertCircle, label: "错误",   border: "border-l-red-500",    bg: "bg-red-50/60",    dot: "bg-red-500" },
};

/* ── Step Card (colored left border + collapse) ────────── */

function StepCard({
  type, content, toolName, idx, defaultExpanded,
}: {
  type: string;
  content: string;
  toolName?: string | null;
  idx: number;
  defaultExpanded: boolean;
}) {
  const [collapsed, setCollapsed] = useState(!defaultExpanded);
  const colors = STEP_COLORS[type] || STEP_COLORS.thought;
  const Icon = colors.icon;

  return (
    <div className={`rounded-r-lg border-l-4 ${colors.border} bg-white border border-slate-200 border-l-4 shadow-sm overflow-hidden`}>
      {/* Header — click to toggle */}
      <button
        onClick={() => setCollapsed(!collapsed)}
        className="w-full flex items-center gap-2 px-3 py-2 hover:bg-slate-50 transition-colors text-left"
      >
        <span className={`w-1.5 h-1.5 rounded-full ${colors.dot} shrink-0`} />
        <Icon className="w-3.5 h-3.5 text-slate-500 shrink-0" />
        <span className="text-xs font-semibold text-slate-600">
          {colors.label} #{idx}
        </span>
        {toolName && (
          <span className="text-[10px] bg-slate-100 border border-slate-200 rounded px-1.5 py-0.5 text-slate-500 font-mono shrink-0">
            {toolName}
          </span>
        )}
        <span className="flex-1" />
        {collapsed
          ? <ChevronRight className="w-3.5 h-3.5 text-slate-400 shrink-0" />
          : <ChevronDown className="w-3.5 h-3.5 text-slate-400 shrink-0" />
        }
      </button>

      {/* Body */}
      {!collapsed && (
        <div className={`px-3 pb-3 pt-1 ${colors.bg}`}>
          {type === "answer" ? (
            <div className="prose prose-sm max-w-none text-slate-700 prose-headings:text-slate-800 prose-a:text-brand-600 prose-code:text-rose-600 prose-code:bg-slate-100 prose-code:px-1 prose-code:py-0.5 prose-code:rounded prose-code:text-xs prose-pre:bg-slate-800 prose-pre:text-emerald-300 prose-table:border-collapse">
              <ReactMarkdown remarkPlugins={[remarkGfm]}>
                {content}
              </ReactMarkdown>
            </div>
          ) : type === "observation" && toolName === "search_literature" ? (
            <div className="text-xs text-slate-600 leading-relaxed">
              <ReactMarkdown
                remarkPlugins={[remarkGfm]}
                components={{
                  a: ({ href, children }) => (
                    <a
                      href={href}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="text-blue-500 no-underline hover:underline"
                    >
                      {children}
                    </a>
                  ),
                }}
              >
                {content}
              </ReactMarkdown>
            </div>
          ) : (
            <div className="text-xs text-slate-600 whitespace-pre-wrap leading-relaxed">{content}</div>
          )}
        </div>
      )}
    </div>
  );
}

/* ── Session History Sidebar ───────────────────────────── */

function SessionList({
  sessions, onSelect, onRefresh, loading, onNew,
}: {
  sessions: AgentSession[];
  onSelect: (s: AgentSession) => void;
  onRefresh: () => void;
  loading: boolean;
  onNew: () => void;
}) {
  return (
    <div className="bg-white w-60 shrink-0 border-r border-slate-200 hidden md:flex md:flex-col">
      <div className="p-3 border-b border-slate-100">
        <button
          onClick={onNew}
          className="w-full px-3 py-1.5 border border-blue-500 text-blue-600 rounded-lg text-xs font-medium hover:bg-blue-50 transition-colors flex items-center justify-center gap-1.5"
        >
          + 新建研究
        </button>
      </div>
      <div className="flex items-center justify-between px-3 py-2 border-b border-slate-100">
        <span className="text-xs font-semibold text-slate-500">历史会话</span>
        <button onClick={onRefresh} className="text-slate-400 hover:text-slate-600" title="刷新">
          <History className="w-3.5 h-3.5" />
        </button>
      </div>
      {loading ? (
        <div className="p-4 flex justify-center"><Loader2 className="w-4 h-4 animate-spin text-slate-300" /></div>
      ) : sessions.length === 0 ? (
        <p className="p-4 text-xs text-slate-400 text-center">暂无历史会话</p>
      ) : (
        <div className="flex-1 overflow-auto p-2 space-y-1">
          {sessions.map((s) => (
            <button
              key={s.session_id}
              onClick={() => onSelect(s)}
              className="w-full text-left p-2 rounded-lg hover:bg-blue-50 transition-colors"
            >
              <div className="text-xs font-medium text-slate-700 truncate">{s.title}</div>
              <div className="text-[10px] text-slate-400 mt-0.5">
                {s.steps.length} 步 · {new Date(s.created_at * 1000).toLocaleDateString("zh-CN")}
              </div>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

/* ── Custom table for alternating rows ─────────────────── */

function ReportTable({ children }: { children: React.ReactNode }) {
  return (
    <div className="my-5 overflow-x-auto rounded-lg border border-slate-300 shadow-sm">
      <table className="min-w-full border-collapse text-xs sm:text-sm">
        {children}
      </table>
    </div>
  );
}

function ReportTH({ children }: { children: React.ReactNode }) {
  return (
    <th className="border border-slate-300 bg-slate-100 px-3 sm:px-4 py-2 sm:py-2.5 text-left text-xs sm:text-sm font-semibold text-slate-700 whitespace-nowrap">
      {children}
    </th>
  );
}

function ReportTD({ children }: { children: React.ReactNode }) {
  return (
    <td className="border border-slate-200 px-3 sm:px-4 py-2 sm:py-2.5 text-xs sm:text-sm text-slate-600">
      {children}
    </td>
  );
}

function ReportTR({ children, index }: { children: React.ReactNode; index: number }) {
  return (
    <tr className={index % 2 === 0 ? "bg-white" : "bg-slate-50"}>
      {children}
    </tr>
  );
}

/* ── Research Report Section ───────────────────────────── */

function ResearchReport({ content }: { content: string }) {
  let trIndex = 0;

  return (
    <div className="bg-white border border-amber-200 rounded-xl shadow-sm overflow-hidden mt-6">
      {/* Report header */}
      <div className="bg-amber-50 border-b border-amber-200 px-4 sm:px-6 py-3 flex items-center gap-2">
        <BookOpen className="w-4 h-4 text-amber-600" />
        <span className="text-sm font-semibold text-amber-800">研究报告</span>
        <span className="flex-1" />
        <CheckCircle2 className="w-4 h-4 text-emerald-500" />
        <span className="text-xs text-emerald-600 font-medium">生成完成</span>
      </div>
      {/* Report body — responsive padding & spacing */}
      <div className="px-4 sm:px-6 md:px-8 py-5 sm:py-7">
        <div className="prose prose-sm sm:prose-base max-w-none text-slate-700
          prose-headings:text-slate-800
          prose-h2:text-lg sm:prose-h2:text-xl prose-h2:font-bold
            prose-h2:mt-10 prose-h2:mb-6 prose-h2:pt-8
            prose-h2:border-t prose-h2:border-slate-200
            prose-h2:pb-2 prose-h2:border-b prose-h2:border-slate-200
          prose-h3:text-base sm:prose-h3:text-lg prose-h3:font-semibold
            prose-h3:mt-8 prose-h3:mb-3
          prose-a:text-brand-600 prose-a:underline
          prose-code:text-rose-600 prose-code:bg-slate-100
            prose-code:px-1.5 prose-code:py-0.5 prose-code:rounded
            prose-code:text-xs prose-code:before:content-none prose-code:after:content-none
          prose-pre:bg-slate-800 prose-pre:text-emerald-300
            prose-pre:rounded-lg prose-pre:p-4 prose-pre:text-xs sm:prose-pre:text-sm
            prose-pre:overflow-x-auto
          prose-p:text-sm sm:prose-p:text-base prose-p:leading-relaxed prose-p:mb-4
          prose-li:text-sm sm:prose-li:text-base prose-li:leading-relaxed prose-li:mb-1
          prose-strong:font-semibold prose-strong:text-slate-800
          prose-em:text-slate-600
        ">
          <ReactMarkdown
            remarkPlugins={[remarkGfm]}
            components={{
              table: ({ children }) => <ReportTable>{children}</ReportTable>,
              thead: ({ children }) => <thead className="bg-slate-100">{children}</thead>,
              tbody: ({ children }) => <tbody>{children}</tbody>,
              th: ({ children }) => <ReportTH>{children}</ReportTH>,
              td: ({ children }) => <ReportTD>{children}</ReportTD>,
              tr: ({ children }) => {
                const idx = trIndex++;
                return <ReportTR index={idx}>{children}</ReportTR>;
              },
            }}
          >
            {content}
          </ReactMarkdown>
        </div>
      </div>
    </div>
  );
}

/* ── Main Console ──────────────────────────────────────── */

export default function AgentConsole() {
  const [query, setQuery] = useState("");
  const [running, setRunning] = useState(false);
  const [events, setEvents] = useState<AgentEvent[]>([]);
  const [error, setError] = useState("");
  const [sessions, setSessions] = useState<AgentSession[]>([]);
  const [sessionsLoading, setSessionsLoading] = useState(false);
  const [currentSessionId, setCurrentSessionId] = useState<string | null>(null);
  const abortRef = useRef<AbortController | null>(null);
  const scrollRef = useRef<HTMLDivElement>(null);

  const reportRef = useRef<HTMLDivElement>(null);

  // Derived state (declared before useEffects below that reference them)
  const lastAnswer = useMemo(() => [...events].reverse().find((e) => e.type === "answer"), [events]);
  const hasFinished = !running && !!lastAnswer;

  // Auto-scroll to bottom when new events arrive during run
  useEffect(() => {
    if (scrollRef.current && running) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [events, running]);

  // Auto-scroll to report when agent finishes
  useEffect(() => {
    if (hasFinished && reportRef.current) {
      setTimeout(() => {
        reportRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
      }, 400);
    }
  }, [hasFinished]);

  // Load sessions on mount
  const loadSessions = useCallback(async () => {
    setSessionsLoading(true);
    try {
      const data = await agentResearchAPI.listSessions(20);
      setSessions(data.sessions);
    } catch {
      // silently fail
    } finally {
      setSessionsLoading(false);
    }
  }, []);

  useEffect(() => {
    loadSessions();
  }, [loadSessions]);

  // View a past session
  const viewSession = useCallback(async (session: AgentSession) => {
    setEvents([]);
    setError("");
    setCurrentSessionId(session.session_id);
    setEvents(
      session.steps.map((s: AgentStep, i: number) => ({
        type: s.step_type,
        content: s.content,
        tool_name: s.tool_name,
        step_index: i + 1,
      }))
    );
  }, []);

  // Run the agent
  const handleSubmit = async () => {
    const q = query.trim();
    if (!q || running) return;

    setRunning(true);
    setEvents([]);
    setError("");
    setCurrentSessionId(null);

    abortRef.current = new AbortController();

    try {
      const response = await agentResearchAPI.run(q);
      if (!response.ok) {
        const text = await response.text();
        throw new Error(`API 错误 (${response.status}): ${text}`);
      }

      const reader = response.body?.getReader();
      if (!reader) throw new Error("浏览器不支持流式响应");

      const decoder = new TextDecoder();
      let buffer = "";

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n");
        buffer = lines.pop() || "";

        for (const line of lines) {
          const trimmed = line.trim();
          if (!trimmed.startsWith("data: ")) continue;

          try {
            const event: AgentEvent = JSON.parse(trimmed.slice(6));
            setEvents((prev) => [...prev, event]);
          } catch {
            // skip malformed lines
          }
        }
      }
    } catch (err: any) {
      if (err.name === "AbortError") return;
      setError(err.message || "Agent 运行失败");
      setEvents((prev) => [
        ...prev,
        { type: "error", content: err.message || "运行失败", tool_name: null, step_index: 0 },
      ]);
    } finally {
      setRunning(false);
      abortRef.current = null;
      loadSessions();
    }
  };

  const handleStop = () => {
    abortRef.current?.abort();
    setRunning(false);
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSubmit();
    }
  };

  const handleNewSession = () => {
    setEvents([]);
    setError("");
    setCurrentSessionId(null);
    setQuery("");
  };

  const handleExampleClick = (text: string) => setQuery(text);

  // Derived state
  const statusInfo = useMemo(() => getStatusText(events, running), [events, running]);

  return (
    <div>
      {/* Header */}
      <div className="flex items-center justify-between mb-4">
        <div>
          <h1 className="text-xl font-bold text-slate-800">AI 研究助手</h1>
          <p className="text-sm text-slate-500 mt-1">基于 ReAct 模式的多步推理研究 Agent</p>
        </div>
      </div>

      {/* ── Status indicator bar ── */}
      <div className="mb-4 bg-white border border-slate-200 rounded-lg px-4 py-2.5 flex items-center gap-3 shadow-sm">
        {running ? (
          <Loader2 className="w-4 h-4 text-brand-600 animate-spin shrink-0" />
        ) : hasFinished ? (
          <CheckCircle2 className="w-4 h-4 text-emerald-500 shrink-0" />
        ) : (
          <Zap className="w-4 h-4 text-slate-400 shrink-0" />
        )}
        <span className={`text-sm font-medium ${running ? "text-brand-700" : hasFinished ? "text-emerald-700" : "text-slate-500"}`}>
          {statusInfo.text}
        </span>
        {hasFinished && (
          <button
            onClick={() => reportRef.current?.scrollIntoView({ behavior: "smooth", block: "start" })}
            className="ml-2 px-2.5 py-1 bg-amber-100 text-amber-700 rounded-full text-xs font-medium hover:bg-amber-200 transition-colors flex items-center gap-1"
          >
            <BookOpen className="w-3 h-3" />
            查看报告
          </button>
        )}
        {/* Progress steps */}
        <div className="flex-1" />
        <div className="flex items-center gap-1.5">
          {(["search_literature", "search_pubchem", "predict_properties", "calculate_molar_mass", "lookup_element"] as const).map((tool) => {
            const toolUsed = events.some(e => e.type === "action" && e.tool_name === tool);
            return (
              <span
                key={tool}
                className={`w-2 h-2 rounded-full ${
                  toolUsed ? "bg-emerald-400" : "bg-slate-200"
                }`}
                title={TOOL_LABELS[tool]?.replace("正在", "").replace("…", "")}
              />
            );
          })}
        </div>
      </div>

      {/* ── Main area with sidebar ── */}
      <div className="flex flex-col md:flex-row gap-0 rounded-xl border border-slate-200 shadow-sm overflow-hidden bg-white" style={{ minHeight: 600 }}>
        {/* Session sidebar — left */}
        <SessionList
          sessions={sessions}
          onSelect={viewSession}
          onRefresh={loadSessions}
          loading={sessionsLoading}
          onNew={handleNewSession}
        />
        {/* Center — display + input */}
        <div className="flex-1 flex flex-col min-w-0">
          {/* Input */}
          <div className="p-3 border-b border-slate-100 bg-white">
            <div className="flex gap-2 items-start">
              <div className="flex-1 relative">
                <textarea
                  className="w-full bg-white border border-slate-200 rounded-lg px-3 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-blue-500 resize-none"
                  rows={1}
                  placeholder="输入研究问题，如：请查找阿司匹林的分子性质、预测其ADMET参数，并搜索相关最新研究文献..."
                  value={query}
                  onChange={(e) => setQuery(e.target.value)}
                  onKeyDown={handleKeyDown}
                  disabled={running}
                />
              </div>
              <div className="flex gap-1.5 shrink-0">
                {running ? (
                  <button
                    onClick={handleStop}
                    className="px-3 py-1.5 bg-red-500 text-white rounded-lg hover:bg-red-600 transition-colors text-xs font-medium flex items-center gap-1 min-w-[72px] justify-center"
                  >
                    <Trash2 className="w-3 h-3" />
                    停止
                  </button>
                ) : (
                  <button
                    onClick={handleSubmit}
                    disabled={!query.trim()}
                    className="px-3 py-1.5 bg-brand-700 text-white rounded-lg hover:bg-brand-800 disabled:opacity-50 disabled:cursor-not-allowed transition-colors text-xs font-medium flex items-center gap-1 min-w-[72px] justify-center"
                  >
                    <Send className="w-3 h-3" />
                    提交
                  </button>
                )}
              </div>
            </div>
            <p className="text-[10px] text-slate-400 mt-1.5">
              Agent 将自动调用文献搜索、PubChem 查询、性质预测、摩尔质量计算、元素查询等工具进行多步推理
            </p>
          </div>

          {/* Scrollable display */}
          <div ref={scrollRef} className="flex-1 overflow-auto p-4 space-y-2.5">
            {/* Empty state */}
            {events.length === 0 && !running && !error && (
              <div className="flex flex-col items-center justify-center h-full gap-6 py-16">
                <div className="flex flex-col items-center gap-2 text-slate-300">
                  <Brain className="w-8 h-8" />
                  <p className="text-sm">选择示例课题或输入自定义研究问题</p>
                </div>
                <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 max-w-2xl">
                  {EXAMPLE_QUERIES.map((q) => (
                    <button
                      key={q}
                      onClick={() => handleExampleClick(q)}
                      className="bg-white border border-slate-200 rounded-lg px-4 py-3 text-xs text-slate-600 hover:border-blue-400 hover:text-blue-600 transition-colors text-left leading-relaxed"
                    >
                      {q}
                    </button>
                  ))}
                </div>
              </div>
            )}

            {/* Step cards */}
            {events
              .filter(e => e.type !== "answer") // answers rendered in final report
              .map((evt, i, arr) => {
                const isLatest = running && i === arr.length - 1;
                return (
                  <StepCard
                    key={i}
                    type={evt.type}
                    content={evt.content}
                    toolName={evt.tool_name}
                    idx={evt.step_index}
                    defaultExpanded={evt.type === "error" || isLatest}
                  />
                );
              })}

            {/* Running indicator */}
            {running && (
              <div className="flex items-center gap-2 text-xs text-brand-600 py-2 px-1">
                <Loader2 className="w-3.5 h-3.5 animate-spin" />
                {statusInfo.text}
              </div>
            )}

            {/* Inline error (when there are also events shown) */}
            {error && !running && events.length > 0 && (
              <div className="bg-red-50 border-l-4 border-l-red-500 rounded-r-lg p-3 text-red-700 text-xs">
                <AlertCircle className="w-3.5 h-3.5 inline mr-1.5" />
                {error}
              </div>
            )}

            {/* Full error state */}
            {error && !running && events.length === 0 && (
              <div className="bg-red-50 border border-red-200 rounded-lg p-4 text-red-700 text-sm">
                <AlertCircle className="w-4 h-4 inline mr-1.5" />
                {error}
              </div>
            )}

            {/* ── Final research report ── */}
            {lastAnswer && !running && (
              <div ref={reportRef}>
                <ResearchReport content={lastAnswer.content} />
              </div>
            )}
          </div>
        </div>

      </div>

      {/* Hints */}
      <details className="mt-4 text-xs text-slate-400 bg-white rounded-lg border border-slate-100 p-3">
        <summary className="cursor-pointer font-medium text-slate-500">使用说明与示例问题</summary>
        <div className="mt-2 space-y-1.5">
          <p><strong className="text-slate-600">工作原理：</strong>Agent 将你的问题分解为多个步骤，通过 Thought（思考）→ Action（调用工具）→ Observation（观察结果）的循环，逐步收集信息，最终生成综合研究报告。</p>
          <p className="mt-2"><strong className="text-slate-600">示例问题：</strong></p>
          <ul className="list-disc ml-4 space-y-0.5">
            <li>请查找阿司匹林的分子性质，预测其ADMET参数，并搜索相关最新研究</li>
            <li>计算 H2SO4 和 Ca(OH)2 的摩尔质量，并比较它们的化学性质</li>
            <li>查找铁(Fe)和钯(Pd)的元素性质，并分析它们在催化反应中的应用</li>
            <li>搜索关于"MOF材料用于CO2捕获"的最新研究文献</li>
          </ul>
          <p className="mt-2"><strong className="text-slate-600">环境要求：</strong>需要设置 <code className="bg-slate-100 px-1 rounded">DEEPSEEK_API_KEY</code> 环境变量以启用 LLM 推理。</p>
        </div>
      </details>
    </div>
  );
}
