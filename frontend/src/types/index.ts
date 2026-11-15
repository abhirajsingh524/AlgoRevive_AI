export interface User {
  id: string;
  email: string;
  full_name: string | null;
  is_active: boolean;
  role: string;
  created_at: string;
}

export interface AuthResponse {
  access_token: string;
  token_type: string;
  user: User;
}

export interface Project {
  id: string;
  owner_id: string;
  name: string;
  description: string | null;
  created_at: string;
  updated_at: string;
}

export interface Repository {
  id: string;
  project_id: string;
  version_label: string | null;
  source_type: string;
  storage_key: string;
  status: string;
  file_count: number;
  total_loc: number;
  created_at: string;
  updated_at: string;
}

export interface FileRecord {
  id: string;
  repository_id: string;
  path: string;
  language: string;
  loc: number;
  sha256: string;
  storage_key: string;
  created_at: string;
  updated_at: string;
}

export interface FileContent {
  id: string;
  path: string;
  language: string;
  content: string;
}

export interface DetectedPatternItem {
  pattern_id: string;
  line_number: number;
  matched_snippet: string;
}

export interface FunctionRecord {
  id: string;
  file_id: string;
  repository_id: string;
  qualified_name: string;
  name: string;
  lineno: number;
  end_lineno: number;
  params: any;
  complexity_class: string | null;
  complexity_rank: number;
  loop_depth: number;
  has_recursion: boolean;
  patterns: DetectedPatternItem[] | null;
  severity: 'LOW' | 'MEDIUM' | 'HIGH' | 'CRITICAL' | string;
  metrics: Record<string, any> | null;
  created_at: string;
  updated_at: string;
}

export interface AnalysisRun {
  id: string;
  repository_id: string;
  requested_by: string | null;
  status: 'queued' | 'running' | 'completed' | 'failed' | string;
  stage: string;
  progress: number;
  config: Record<string, any> | null;
  workload_spec?: any;
  workload_hash?: string | null;
  environment?: any;
  error: string | null;
  started_at: string | null;
  finished_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface CallGraphNode {
  id: string;
  name: string;
  qualified_name: string;
  file_id: string;
  file_path: string;
  lineno: number;
  end_lineno: number;
  severity: string;
  complexity_class: string;
  complexity_rank: number;
  fan_in: number;
  fan_out: number;
  callers: string[];
  callees: string[];
}

export interface CallGraphEdge {
  source: string;
  target: string;
  call_count: number;
}

export interface CallGraphData {
  repository_id: string;
  node_count: number;
  edge_count: number;
  nodes: CallGraphNode[];
  edges: CallGraphEdge[];
}

export interface FunctionProfile {
  file: string;
  function: string;
  lineno: number;
  calls: number;
  total_time: number;
  cumulative_time: number;
}

export interface MeasurementResult {
  n: number;
  runtime_s: number;
  cpu_time_s: number;
  peak_memory_kb: number;
  top_functions: FunctionProfile[];
}

export interface EntrypointProfile {
  function: string;
  status: string;
  growth_exponent: number;
  sizes: number[];
  measurements: MeasurementResult[];
  error?: string;
  warning?: string;
  traceback?: string;
}

export interface ProfileResult {
  status: string;
  entrypoints: Record<string, EntrypointProfile>;
  summary: {
    total_entrypoints: number;
    successful_entrypoints: number;
    failed_entrypoints: number;
  };
  extra?: Record<string, any>;
}

export interface WorkloadProfileData {
  input_size: number;
  lookup_frequency: 'LOW' | 'MEDIUM' | 'HIGH' | 'VERY_HIGH';
  insert_ratio: number;
  delete_ratio: number;
  read_write_ratio: number;
  data_distribution: 'uniform' | 'sorted' | 'skewed';
  memory_constraint: 'LOW' | 'MEDIUM' | 'HIGH';
  latency_requirement: 'LOW' | 'MEDIUM' | 'HIGH' | 'VERY_HIGH';
}

export interface WhyFlaggedNodeData {
  reason: string;
  metric: string;
  value: any;
  weight: number | null;
  children?: WhyFlaggedNodeData[];
}

export interface AffectedFunctionData {
  function_id: string;
  name: string;
  qualified_name: string;
  file_path: string;
  depth: number;
  covered_by_workload: boolean;
}

export interface BottleneckEvidence {
  source?: string;
  static_norm?: number;
  runtime_pct?: number;
  call_freq_norm?: number;
  mem_norm?: number;
  max_calls?: number;
  max_peak_mem_kb?: number;
  runtime_score?: number;
  static_score?: number;
  impact_score?: number;
  severity?: string;
  workload?: WorkloadProfileData;
  features?: Record<string, any>;
  features_array?: number[];
  affected_functions?: AffectedFunctionData[];
  why_flagged?: WhyFlaggedNodeData;
  [key: string]: any;
}

export interface BottleneckRecord {
  id: string;
  analysis_run_id: string;
  function_id: string;
  static_score: number;
  runtime_score: number;
  call_count: number;
  runtime_pct: number;
  memory_peak_kb: number;
  impact_score: number;
  severity: 'LOW' | 'MEDIUM' | 'HIGH' | 'CRITICAL' | string;
  evidence: BottleneckEvidence | null;
  created_at: string;
  updated_at: string;
  function?: FunctionRecord;
}
