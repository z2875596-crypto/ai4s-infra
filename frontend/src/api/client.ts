const BASE = "/api/v1";

async function request<T>(url: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${url}`, {
    headers: { "Content-Type": "application/json", ...options?.headers },
    ...options,
  });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`${res.status}: ${text}`);
  }
  return res.json();
}

function get<T>(url: string) { return request<T>(url); }

function post<T>(url: string, body?: unknown) {
  return request<T>(url, { method: "POST", body: body ? JSON.stringify(body) : undefined });
}

function del<T>(url: string) {
  return request<T>(url, { method: "DELETE" });
}

// ── Data Infra ──────────────────────────────────────────

export const dataAPI = {
  listConnectors: () => get<{ sources: string[] }>("/data/connectors"),
  registerConnector: (name: string, sourceType: string, config: Record<string, unknown>) =>
    post("/data/connectors", { name, source_type: sourceType, config }),
  removeConnector: (name: string) => del(`/data/connectors/${name}`),

  runIngestion: (body: {
    source_name: string; table: string; target_path: string;
    batch_size?: number; target_format?: string;
  }) => post<import("@/types").IngestionReport>("/data/ingest", body),

  registerSchema: (table: string, columns: Record<string, string>, required?: string[]) =>
    post("/data/schemas", { table, columns, required }),

  searchCatalog: (params: Record<string, string>) => {
    const qs = new URLSearchParams(params).toString();
    return get<{ count: number; datasets: import("@/types").CatalogEntry[] }>(`/data/catalog?${qs}`);
  },
  getDataset: (name: string) => get<import("@/types").CatalogEntry>(`/data/catalog/${encodeURIComponent(name)}`),
  catalogSummary: () => get<Record<string, unknown>>("/data/catalog/summary"),

  createSnapshot: (dataset: string, sourcePath: string, tags?: Record<string, string>) =>
    post<import("@/types").Snapshot>("/data/snapshots", { dataset, source_path: sourcePath, tags }),
  listSnapshots: (dataset?: string) =>
    get<{ count: number; snapshots: import("@/types").Snapshot[] }>(`/data/snapshots${dataset ? `?dataset=${dataset}` : ""}`),

  getLineage: (id: string) => get<import("@/types").LineageGraph>(`/data/lineage/${id}`),

  predictMolecule: (smiles: string) =>
    post<import("@/types").PredictionResult>("/data/predict", { smiles }),
};

// ── Agent Runtime ───────────────────────────────────────

export const agentAPI = {
  submitTask: (body: { agent_type: string; action: string; payload?: Record<string, unknown>; priority?: string }) =>
    post<{ task_id: string; status: string }>("/agent/tasks", body),
  getTask: (id: string) => get<import("@/types").TaskInfo>(`/agent/tasks/${id}`),
  queueStats: () => get<import("@/types").QueueStats>("/agent/queue/stats"),

  registerAgent: (agentId: string, capabilities: string[], maxCapacity?: number) =>
    post("/agent/agents", { agent_id: agentId, capabilities, max_capacity: maxCapacity || 10 }),
  listAgents: () => get<import("@/types").AgentSummary>("/agent/agents"),

  listTools: () => get<{ tools: import("@/types").ToolSchema[] }>("/agent/tools"),
  executeTool: (toolName: string, args: Record<string, unknown>) =>
    post("/agent/tools/execute", { tool_name: toolName, arguments: args }),

  remember: (content: string, tags?: string[], importance?: number) =>
    post<{ memory_id: string }>("/agent/memory", { content, tags, importance }),
  recall: (query: string, topK?: number, asContext?: boolean) =>
    post<{ count?: number; memories?: import("@/types").MemoryEntry[]; context?: string }>(
      "/agent/memory/recall", { query, top_k: topK || 5, as_context: asContext || false }
    ),
  memoryStats: () => get<import("@/types").MemoryStats>("/agent/memory/stats"),

  orchestratorStatus: () => get<Record<string, unknown>>("/agent/status"),

  literatureSearch: (query: string, limit?: number, yearFrom?: string, yearTo?: string) =>
    post<import("@/types").LiteratureResult>("/agent/literature/search", {
      query, limit: limit || 10, year_from: yearFrom, year_to: yearTo,
    }),
};

// ── HPC Fusion ──────────────────────────────────────────

export const hpcAPI = {
  submitJob: (body: Record<string, unknown>) =>
    post<{ job_id?: string; status: string }>("/hpc/jobs", body),
  listJobs: (connector?: string) =>
    get<{ count: number; jobs: import("@/types").HPCJob[] }>(`/hpc/jobs?connector=${connector || "slurm"}`),
  cancelJob: (id: string) => del(`/hpc/jobs/${id}`),

  schedulerStatus: () => get<import("@/types").SchedulerStatus>("/hpc/scheduler/status"),
  runScheduleCycle: () => post<{ scheduled: number }>("/hpc/scheduler/cycle"),
  pendingJobs: () => get<{ pending: Array<{ spec: Record<string, unknown>; priority: number }> }>("/hpc/scheduler/pending"),

  listNodes: (connector?: string) =>
    get<{ count: number; nodes: import("@/types").NodeDetail[] }>(`/hpc/nodes?connector=${connector || "slurm"}`),
  clusterMetrics: () => get<import("@/types").ClusterSnapshot>("/hpc/metrics/cluster"),
  capacityHeadroom: () => get<import("@/types").CapacityHeadroom>("/hpc/metrics/headroom"),

  detectAnomalies: () => get<{ count: number; anomalies: import("@/types").Anomaly[] }>("/hpc/analysis/anomalies"),
  clusterHealth: () => get<{ status: string; utilization: Record<string, number>; anomalies: number }>("/hpc/analysis/health"),

  sendAlert: (title: string, message: string, severity: string) =>
    post<import("@/types").AlertInfo>("/hpc/alerts", { title, message, severity }),
  activeAlerts: () => get<{ alerts: import("@/types").AlertInfo[] }>("/hpc/alerts/active"),
  alertHistory: () => get<{ alerts: import("@/types").AlertInfo[] }>("/hpc/alerts/history?limit=50"),
  resolveAlert: (id: string) => post(`/hpc/alerts/${id}/resolve`),
};

// ── Agent Research ──────────────────────────────────────

export const agentResearchAPI = {
  run: (query: string, sessionId?: string, maxSteps?: number) => {
    const base = "/api/agent";
    return fetch(`${base}/run`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        query,
        session_id: sessionId || null,
        max_steps: maxSteps || 10,
      }),
    });
  },

  listSessions: async (limit?: number) => {
    const resp = await fetch(`/api/agent/sessions?limit=${limit || 20}`);
    if (!resp.ok) throw new Error(`${resp.status}: ${await resp.text()}`);
    return resp.json() as Promise<{ count: number; sessions: import("@/types").AgentSession[] }>;
  },

  getSession: async (id: string) => {
    const resp = await fetch(`/api/agent/sessions/${id}`);
    if (!resp.ok) throw new Error(`${resp.status}: ${await resp.text()}`);
    return resp.json() as Promise<import("@/types").AgentSession>;
  },

  deleteSession: async (id: string) => {
    const resp = await fetch(`/api/agent/sessions/${id}`, { method: "DELETE" });
    if (!resp.ok) throw new Error(`${resp.status}: ${await resp.text()}`);
    return resp.json() as Promise<{ status: string; deleted: boolean }>;
  },

  deleteAllSessions: async () => {
    const resp = await fetch(`/api/agent/sessions`, { method: "DELETE" });
    if (!resp.ok) throw new Error(`${resp.status}: ${await resp.text()}`);
    return resp.json() as Promise<{ status: string; deleted_count: number }>;
  },
};

// ── RLHF ────────────────────────────────────────────────

export const rlhfAPI = {
  feedbackStats: () => get<import("@/types").FeedbackStats>("/rlhf/feedback/stats"),
  addFeedback: (prompts: string[], responsesA: string[], responsesB: string[]) =>
    post<{ count: number; item_ids: string[] }>("/rlhf/feedback/items", {
      prompts, responses_a: responsesA, responses_b: responsesB,
    }),
  assignFeedback: (annotatorId: string, n: number) =>
    post("/rlhf/feedback/assign", { annotator_id: annotatorId, n }),
  annotate: (itemId: string, annotatorId: string, choice: string) =>
    post("/rlhf/feedback/annotate", { item_id: itemId, annotator_id: annotatorId, choice }),

  getConsensus: () => get<{ count: number; pairs: import("@/types").ConsensusPair[] }>("/rlhf/feedback/consensus"),
  annotatorQuality: () => get<import("@/types").AnnotatorQuality>("/rlhf/feedback/annotator-quality"),

  scoreReward: (prompts: string[], responses: string[]) =>
    post<{ scores: import("@/types").RewardScore[] }>("/rlhf/reward/score", { prompts, responses }),

  trainPolicy: (algorithm: string, trainingData: Array<{ prompt: string; chosen: string; rejected: string }>) =>
    post<import("@/types").PolicyTrainResult>("/rlhf/policy/train", { algorithm, training_data: trainingData }),

  pipelineIterate: (prompts: string[]) =>
    post<import("@/types").PipelineIterResult>("/rlhf/pipeline/iterate", { prompts }),
  pipelineEvaluate: (prompts: string[], responses: string[]) =>
    post("/rlhf/pipeline/evaluate", { prompts, responses }),
  pipelineFeedbackStats: () => get<Record<string, unknown>>("/rlhf/pipeline/feedback-stats"),
};
