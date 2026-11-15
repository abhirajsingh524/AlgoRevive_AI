import axios from 'axios';
import {
  AnalysisRun,
  AuthResponse,
  CallGraphData,
  FileContent,
  FileRecord,
  FunctionRecord,
  Project,
  Repository,
  User,
} from '../types';

const API_BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000';

export const apiClient = axios.create({
  baseURL: `${API_BASE_URL}/api/v1`,
});

apiClient.interceptors.request.use((config) => {
  const token = localStorage.getItem('algorevive_token');
  if (token && config.headers) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

apiClient.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401) {
      localStorage.removeItem('algorevive_token');
      localStorage.removeItem('algorevive_user');
      if (
        window.location.pathname !== '/login' &&
        window.location.pathname !== '/register'
      ) {
        window.location.href = '/login';
      }
    }
    return Promise.reject(error);
  }
);

export const api = {
  auth: {
    register: async (data: { email: string; password: string; full_name?: string }): Promise<User> => {
      const res = await apiClient.post<User>('/auth/register', data);
      return res.data;
    },
    login: async (data: { email: string; password: string }): Promise<AuthResponse> => {
      const res = await apiClient.post<AuthResponse>('/auth/login', data);
      return res.data;
    },
    me: async (): Promise<User> => {
      const res = await apiClient.get<User>('/auth/me');
      return res.data;
    },
  },
  projects: {
    list: async (): Promise<Project[]> => {
      const res = await apiClient.get<Project[]>('/projects');
      return res.data;
    },
    get: async (id: string): Promise<Project> => {
      const res = await apiClient.get<Project>(`/projects/${id}`);
      return res.data;
    },
    create: async (data: { name: string; description?: string }): Promise<Project> => {
      const res = await apiClient.post<Project>('/projects', data);
      return res.data;
    },
    delete: async (id: string): Promise<void> => {
      await apiClient.delete(`/projects/${id}`);
    },
  },
  repositories: {
    list: async (projectId: string): Promise<Repository[]> => {
      const res = await apiClient.get<Repository[]>(`/projects/${projectId}/repositories`);
      return res.data;
    },
    get: async (id: string): Promise<Repository> => {
      const res = await apiClient.get<Repository>(`/repositories/${id}`);
      return res.data;
    },
    upload: async (projectId: string, formData: FormData): Promise<Repository> => {
      const res = await apiClient.post<Repository>(
        `/projects/${projectId}/repositories`,
        formData,
        {
          headers: {
            'Content-Type': 'multipart/form-data',
          },
        }
      );
      return res.data;
    },
    listFiles: async (repoId: string): Promise<FileRecord[]> => {
      const res = await apiClient.get<FileRecord[]>(`/repositories/${repoId}/files`);
      return res.data;
    },
    getFileContent: async (repoId: string, fileId: string): Promise<FileContent> => {
      const res = await apiClient.get<FileContent>(`/repositories/${repoId}/files/${fileId}/content`);
      return res.data;
    },
    listFunctions: async (
      repoId: string,
      params?: { file_id?: string; severity?: string; min_rank?: number; pattern?: string }
    ): Promise<FunctionRecord[]> => {
      const res = await apiClient.get<FunctionRecord[]>(`/repositories/${repoId}/functions`, {
        params,
      });
      return res.data;
    },
    getCallGraph: async (repoId: string): Promise<CallGraphData> => {
      const res = await apiClient.get<CallGraphData>(`/repositories/${repoId}/call-graph`);
      return res.data;
    },
  },
  analysis: {
    createRun: async (
      repoId: string,
      payload?: { config?: Record<string, any>; workload_spec?: Record<string, any> }
    ): Promise<AnalysisRun> => {
      const res = await apiClient.post<AnalysisRun>(`/repositories/${repoId}/analysis-runs`, {
        config: payload?.config || {},
        workload_spec: payload?.workload_spec,
      });
      return res.data;
    },
    listRuns: async (repoId: string): Promise<AnalysisRun[]> => {
      const res = await apiClient.get<AnalysisRun[]>(`/repositories/${repoId}/analysis-runs`);
      return res.data;
    },
    getRun: async (runId: string): Promise<AnalysisRun> => {
      const res = await apiClient.get<AnalysisRun>(`/analysis-runs/${runId}`);
      return res.data;
    },
    getProfile: async (runId: string): Promise<any> => {
      const res = await apiClient.get(`/analysis-runs/${runId}/profile`);
      return res.data;
    },
  },
};
