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
