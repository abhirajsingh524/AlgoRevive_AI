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
