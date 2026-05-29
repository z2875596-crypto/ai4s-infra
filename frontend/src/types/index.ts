// ── Data Infra ──────────────────────────────────────────

export interface ConnectorInfo {
  name: string;
  type?: string;
}

export interface IngestionReport {
  status: string;
  rows_read: number;
  rows_written: number;
  pass_rate: number;
  duration_sec: number;
  validation_errors: Array<{ row_index: number; column: string; message: string }>;
}

export interface CatalogEntry {
  name: string;
  description: string;
  owner: string;
  columns: Array<{ name: string; dtype: string; description: string }>;
  location: string;
  format: string;
  tags: string[];
  row_count_estimate: number;
  size_bytes_estimate: number;
  quality_score: number;
  created_at: string;
  updated_at: string;
}

export interface Snapshot {
  snapshot_id: string;
  dataset: string;
  created_at: string;
  location: string;
  row_count: number;
  size_bytes: number;
  tags: Record<string, string>;
  parent_snapshot_id: string | null;
}

export interface LineageGraph {
  dataset_id: string;
  upstream: Array<{ source: string; target: string; type: string }>;
  downstream: Array<{ source: string; target: string; type: string }>;
}

// ── Agent Runtime ───────────────────────────────────────

export interface TaskInfo {
  task_id: string;
  status: string;
  result?: unknown;
}

export interface QueueStats {
  pending: number;
  active: number;
  dead: number;
  scheduled?: number;
}

export interface AgentSummary {
  total: number;
  online: number;
  busy: number;
  total_capacity: number;
  total_load: number;
  capability_matrix: Record<string, string[]>;
}

export interface ToolSchema {
  type: string;
  function: { name: string; description: string; parameters: unknown };
}

export interface MemoryEntry {
  id: string;
  content: string;
  importance: number;
  tags: string[];
}

export interface MemoryStats {
  total: number;
  avg_importance?: number;
  sources?: string[];
  tags?: string[];
}

// ── Literature Search ───────────────────────────────────

export interface LiteraturePaper {
  paperId: string;
  title: string;
  authors: string[];
  year: number | null;
  abstract: string;
  doi: string;
  url: string;
  venue: string;
  citationCount: number;
}

export interface LiteratureResult {
  query: string;
  total: number;
  offset: number;
  next: number;
  count: number;
  papers: LiteraturePaper[];
}

// ── HPC Fusion ──────────────────────────────────────────

export interface HPCJob {
  job_id: string;
  name: string;
  state: string;
  partition: string;
  nodes: number;
  gpus_per_node: number;
}

export interface SchedulerStatus {
  policy: string;
  pending: number;
  running: number;
  total_submitted?: number;
  queues: Record<string, number | Record<string, unknown>>;
  preemption_enabled: boolean;
  backfill_enabled: boolean;
}

export interface ClusterSnapshot {
  nodes: number;
  avg_gpu_util: number;
  max_gpu_util: number;
  avg_cpu_util: number;
  avg_mem_util: number;
  unhealthy_nodes: number;
  timestamp: string;
}

export interface NodeDetail {
  node_id: string;
  state: string;
  gpu_free: number;
  gpu_total: number;
  cpu_free: number;
}

export interface Anomaly {
  node: string;
  metric: string;
  severity: string;
  message: string;
}

export interface AlertInfo {
  alert_id: string;
  title: string;
  severity: string;
  message: string;
  acknowledged: boolean;
  resolved: boolean;
  timestamp: string;
}

export interface CapacityHeadroom {
  avg_gpu_utilization_pct: number;
  remaining_capacity_pct: number;
  estimated_free_gpus: number;
  can_fit_small_jobs: boolean;
  can_fit_large_jobs: boolean;
}

// ── RLHF ────────────────────────────────────────────────

export interface FeedbackStats {
  total: number;
  by_status: Record<string, number>;
  by_choice: Record<string, number>;
  annotators: number;
  avg_confidence: number;
}

export interface ConsensusPair {
  prompt: string;
  chosen: string;
  rejected: string;
  _agreement?: number;
  _num_annotators?: number;
}

export interface RewardScore {
  prompt: string;
  score: number;
}

export interface PolicyTrainResult {
  epochs?: number;
  final_loss?: number;
  n_prompts?: number;
  n_pairs?: number;
  training?: Record<string, unknown>;
}

export interface PipelineIterResult {
  n_prompts: number;
  avg_reward?: number;
  training?: Record<string, unknown>;
}

// ── Molecular Prediction ──────────────────────────────

export interface PredictionResult {
  valid: boolean;
  smiles: string;
  canonical_smiles: string;
  molecular_formula: string;
  molecular_weight: number;
  logp: number;
  h_bond_donors: number;
  h_bond_acceptors: number;
  rotatable_bonds: number;
  tpsa: number;
  heavy_atom_count: number;
  ring_count: number;
  aromatic_rings: number;
  error?: string;
}

// ── Experiment Records ──────────────────────────────────

export interface ExperimentRecord {
  id: string;
  name: string;
  date: string;
  molecule: string;
  conditions: string;
  notes: string;
  createdAt: string;
}

export interface AnnotatorQuality {
  [annotatorId: string]: {
    total: number;
    agreed_with_consensus: number;
    accuracy: number;
    avg_confidence: number;
  };
}
