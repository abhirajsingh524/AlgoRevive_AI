import React, { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { ArrowUpRight, FolderGit2, FolderKanban, Plus, Sparkles } from 'lucide-react';
import { api } from '../api/client';
import { Project } from '../types';

export const DashboardPage: React.FC = () => {
  const [projects, setProjects] = useState<Project[]>([]);
  const [totalRepos, setTotalRepos] = useState<number>(0);
  const [isLoading, setIsLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const fetchDashboardData = async () => {
      try {
        setIsLoading(true);
        const projectList = await api.projects.list();
        setProjects(projectList);

        // Fetch repositories count across projects
        let repoCount = 0;
        await Promise.all(
          projectList.map(async (p) => {
            try {
              const repos = await api.repositories.list(p.id);
              repoCount += repos.length;
            } catch {
              // ignore individual repo list errors
            }
          })
        );
        setTotalRepos(repoCount);
      } catch (err: unknown) {
        const axiosErr = err as { response?: { data?: { detail?: string } } };
        setError(axiosErr.response?.data?.detail || 'Failed to load dashboard data');
      } finally {
        setIsLoading(false);
      }
    };

    fetchDashboardData();
  }, []);

  if (isLoading) {
    return (
      <div className="flex flex-1 items-center justify-center p-8 text-slate-400">
        <div className="h-6 w-6 animate-spin rounded-full border-2 border-indigo-500 border-t-transparent mr-3"></div>
        <span>Loading dashboard metrics...</span>
      </div>
    );
  }

  if (error) {
    return (
      <div className="p-8">
        <div className="rounded-xl border border-red-500/20 bg-red-500/10 p-4 text-red-400">
          <p className="font-semibold">Error</p>
          <p className="text-sm">{error}</p>
        </div>
      </div>
    );
  }

  return (
    <div className="p-8 space-y-8 max-w-6xl">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-white">System Dashboard</h1>
          <p className="mt-1 text-sm text-slate-400">
            Algorithmic codebase overview & repository intelligence
          </p>
        </div>
        <Link
          to="/projects"
          className="inline-flex items-center gap-2 rounded-lg bg-indigo-600 px-4 py-2 text-sm font-semibold text-white shadow-sm hover:bg-indigo-500 transition-colors"
        >
          <Plus className="h-4 w-4" />
          <span>New Project</span>
        </Link>
      </div>

      {/* Stats Cards */}
      <div className="grid grid-cols-1 gap-5 sm:grid-cols-2 lg:grid-cols-3">
        <div className="rounded-xl border border-slate-800 bg-slate-900/50 p-6 shadow-sm">
          <div className="flex items-center justify-between">
            <span className="text-xs font-semibold uppercase tracking-wider text-slate-400">Total Projects</span>
            <div className="rounded-lg bg-indigo-600/10 p-2 text-indigo-400 border border-indigo-500/20">
              <FolderKanban className="h-5 w-5" />
            </div>
          </div>
          <p className="mt-4 text-3xl font-bold tracking-tight text-white">{projects.length}</p>
          <Link
            to="/projects"
            className="mt-3 inline-flex items-center gap-1 text-xs font-medium text-indigo-400 hover:text-indigo-300"
          >
            <span>View all projects</span>
            <ArrowUpRight className="h-3 w-3" />
          </Link>
        </div>

        <div className="rounded-xl border border-slate-800 bg-slate-900/50 p-6 shadow-sm">
          <div className="flex items-center justify-between">
            <span className="text-xs font-semibold uppercase tracking-wider text-slate-400">Indexed Repositories</span>
            <div className="rounded-lg bg-emerald-600/10 p-2 text-emerald-400 border border-emerald-500/20">
              <FolderGit2 className="h-5 w-5" />
            </div>
          </div>
          <p className="mt-4 text-3xl font-bold tracking-tight text-white">{totalRepos}</p>
          <p className="mt-3 text-xs text-slate-500">Across active user projects</p>
        </div>

        <div className="rounded-xl border border-slate-800 bg-slate-900/50 p-6 shadow-sm">
          <div className="flex items-center justify-between">
            <span className="text-xs font-semibold uppercase tracking-wider text-slate-400">Engine Status</span>
            <div className="rounded-lg bg-amber-600/10 p-2 text-amber-400 border border-amber-500/20">
              <Sparkles className="h-5 w-5" />
            </div>
          </div>
          <p className="mt-4 text-lg font-bold tracking-tight text-emerald-400">Phase 1 Foundation Ready</p>
          <p className="mt-3 text-xs text-slate-500">FastAPI, SQLAlchemy, Storage, Monaco</p>
        </div>
      </div>

      {/* Recent Projects Section */}
      <div className="rounded-xl border border-slate-800 bg-slate-900/30 p-6">
        <h2 className="text-base font-semibold text-white">Recent Projects</h2>
        {projects.length === 0 ? (
          <div className="py-12 text-center">
            <FolderKanban className="mx-auto h-8 w-8 text-slate-600" />
            <p className="mt-2 text-sm font-medium text-slate-400">No projects created yet</p>
            <p className="mt-1 text-xs text-slate-500">Get started by creating your first code repository project.</p>
            <Link
              to="/projects"
              className="mt-4 inline-flex items-center gap-1.5 rounded-lg bg-indigo-600 px-3 py-1.5 text-xs font-semibold text-white hover:bg-indigo-500 transition-colors"
            >
              <Plus className="h-3.5 w-3.5" />
              <span>Create Project</span>
            </Link>
          </div>
        ) : (
          <div className="mt-4 divide-y divide-slate-800/80">
            {projects.slice(0, 5).map((project) => (
              <div key={project.id} className="py-3 flex items-center justify-between hover:bg-slate-800/20 px-2 rounded-lg transition-colors">
                <div>
                  <Link to={`/projects/${project.id}`} className="text-sm font-medium text-slate-200 hover:text-indigo-400">
                    {project.name}
                  </Link>
                  <p className="text-xs text-slate-500">{project.description || 'No description provided'}</p>
                </div>
                <Link
                  to={`/projects/${project.id}`}
                  className="text-xs font-medium text-indigo-400 hover:text-indigo-300 flex items-center gap-1"
                >
                  <span>Open</span>
                  <ArrowUpRight className="h-3 w-3" />
                </Link>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
};
