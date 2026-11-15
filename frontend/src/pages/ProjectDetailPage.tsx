import React, { useCallback, useEffect, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { AlertCircle, ArrowLeft, ArrowUpRight, CheckCircle2, FileCode2, FolderGit2, HardDriveUpload, Upload } from 'lucide-react';
import { api } from '../api/client';
import { Project, Repository } from '../types';

export const ProjectDetailPage: React.FC = () => {
  const { projectId } = useParams<{ projectId: string }>();
  const [project, setProject] = useState<Project | null>(null);
  const [repositories, setRepositories] = useState<Repository[]>([]);
  const [isLoading, setIsLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  // Upload state
  const [uploadFiles, setUploadFiles] = useState<File[]>([]);
  const [versionLabel, setVersionLabel] = useState<string>('');
  const [isUploading, setIsUploading] = useState<boolean>(false);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const [isDragOver, setIsDragOver] = useState<boolean>(false);

  const fetchProjectData = useCallback(async () => {
    if (!projectId) return;
    try {
      setIsLoading(true);
      setError(null);
      const [projData, repoList] = await Promise.all([
        api.projects.get(projectId),
        api.repositories.list(projectId),
      ]);
      setProject(projData);
      setRepositories(repoList);
    } catch (err: unknown) {
      const axiosErr = err as { response?: { data?: { detail?: string } } };
      setError(axiosErr.response?.data?.detail || 'Failed to load project details');
    } finally {
      setIsLoading(false);
    }
  }, [projectId]);

  useEffect(() => {
    fetchProjectData();
  }, [fetchProjectData]);

  const handleFilesSelect = (files: FileList | null) => {
    if (!files || files.length === 0) return;
    setUploadFiles(Array.from(files));
    setUploadError(null);
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragOver(false);
    if (e.dataTransfer.files && e.dataTransfer.files.length > 0) {
      handleFilesSelect(e.dataTransfer.files);
    }
  };

  const handleUploadSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!projectId || uploadFiles.length === 0) return;

    setIsUploading(true);
    setUploadError(null);

    const formData = new FormData();
    uploadFiles.forEach((file) => {
      formData.append('files', file);
    });
    if (versionLabel.trim()) {
      formData.append('version_label', versionLabel.trim());
    }

    try {
      await api.repositories.upload(projectId, formData);
      setUploadFiles([]);
      setVersionLabel('');
      await fetchProjectData();
    } catch (err: unknown) {
      const axiosErr = err as { response?: { data?: { detail?: string } } };
      setUploadError(axiosErr.response?.data?.detail || 'Upload failed');
    } finally {
      setIsUploading(false);
    }
  };

  if (isLoading) {
    return (
      <div className="flex flex-1 items-center justify-center p-8 text-slate-400">
        <div className="h-6 w-6 animate-spin rounded-full border-2 border-indigo-500 border-t-transparent mr-3"></div>
        <span>Loading repository workspace...</span>
      </div>
    );
  }

  if (error || !project) {
    return (
      <div className="p-8">
        <Link to="/projects" className="inline-flex items-center gap-1.5 text-xs text-indigo-400 hover:text-indigo-300 mb-4">
          <ArrowLeft className="h-3.5 w-3.5" />
          <span>Back to projects</span>
        </Link>
        <div className="rounded-xl border border-red-500/20 bg-red-500/10 p-4 text-red-400">
          <p className="font-semibold">Error</p>
          <p className="text-sm">{error || 'Project not found'}</p>
        </div>
      </div>
    );
  }

  return (
    <div className="p-8 max-w-6xl space-y-8">
      {/* Breadcrumb & Navigation */}
      <div>
        <Link to="/projects" className="inline-flex items-center gap-1.5 text-xs font-medium text-slate-400 hover:text-indigo-400 mb-3 transition-colors">
          <ArrowLeft className="h-3.5 w-3.5" />
          <span>Back to Projects</span>
        </Link>
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-bold tracking-tight text-white">{project.name}</h1>
            <p className="mt-1 text-sm text-slate-400">{project.description || 'No description provided'}</p>
          </div>
          <span className="rounded-full bg-indigo-600/10 border border-indigo-500/20 px-3 py-1 text-xs font-medium text-indigo-400">
            {repositories.length} {repositories.length === 1 ? 'Repository' : 'Repositories'}
          </span>
        </div>
      </div>

      {/* Upload Box */}
      <div className="rounded-2xl border border-slate-800 bg-slate-900/40 p-6 shadow-sm">
        <h2 className="text-base font-semibold text-white flex items-center gap-2">
          <HardDriveUpload className="h-5 w-5 text-indigo-400" />
          <span>Ingest Repository Code</span>
        </h2>
        <p className="mt-1 text-xs text-slate-400">
          Upload a ZIP archive or multiple Python (.py) source files for indexing and algorithmic analysis.
        </p>

        {uploadError && (
          <div className="mt-4 flex items-center gap-2 rounded-lg border border-red-500/30 bg-red-500/10 p-3 text-sm text-red-400">
            <AlertCircle className="h-4 w-4 shrink-0" />
            <span>{uploadError}</span>
          </div>
        )}

        <form onSubmit={handleUploadSubmit} className="mt-5 space-y-4">
          {/* Drag & Drop Zone */}
          <div
            onDragOver={(e) => {
              e.preventDefault();
              setIsDragOver(true);
            }}
            onDragLeave={() => setIsDragOver(false)}
            onDrop={handleDrop}
            className={`flex flex-col items-center justify-center rounded-xl border-2 border-dashed p-8 text-center transition-colors cursor-pointer ${
              isDragOver
                ? 'border-indigo-500 bg-indigo-500/10'
                : 'border-slate-800 bg-slate-950/60 hover:border-slate-700'
            }`}
            onClick={() => document.getElementById('repo-file-input')?.click()}
          >
            <input
              id="repo-file-input"
              type="file"
              multiple
              accept=".zip,.py"
              className="hidden"
              onChange={(e) => handleFilesSelect(e.target.files)}
            />
            <Upload className="h-8 w-8 text-indigo-400 mb-2" />
            <p className="text-sm font-medium text-slate-200">
              {uploadFiles.length > 0 ? (
                <span className="text-indigo-400 font-semibold">
                  {uploadFiles.length} file(s) selected: {uploadFiles.map((f) => f.name).join(', ')}
                </span>
              ) : (
                <>Click or drag & drop a .zip archive or .py files here</>
              )}
            </p>
            <p className="mt-1 text-xs text-slate-500">
              Max size 50 MB, decompressed file limit 2 MB. Ignores .git, __pycache__, and venv automatically.
            </p>
          </div>

          <div className="flex flex-col sm:flex-row items-center gap-4">
            <div className="w-full sm:w-72">
              <input
                type="text"
                value={versionLabel}
                onChange={(e) => setVersionLabel(e.target.value)}
                placeholder="Optional version label (e.g. v1.0.0)"
                className="block w-full rounded-lg border border-slate-800 bg-slate-950 px-3.5 py-2 text-sm text-slate-100 placeholder-slate-600 focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
              />
            </div>
            <button
              type="submit"
              disabled={isUploading || uploadFiles.length === 0}
              className="w-full sm:w-auto inline-flex items-center justify-center gap-2 rounded-lg bg-indigo-600 px-5 py-2 text-sm font-semibold text-white shadow-sm hover:bg-indigo-500 transition-colors disabled:opacity-50"
            >
              {isUploading ? (
                <>
                  <div className="h-4 w-4 animate-spin rounded-full border-2 border-white border-t-transparent" />
                  <span>Uploading & Indexing...</span>
                </>
              ) : (
                <>
                  <Upload className="h-4 w-4" />
                  <span>Ingest Codebase</span>
                </>
              )}
            </button>
          </div>
        </form>
      </div>

      {/* Repositories List */}
      <div className="space-y-4">
        <h2 className="text-base font-semibold text-white">Uploaded Repositories</h2>
        {repositories.length === 0 ? (
          <div className="rounded-xl border border-slate-800 bg-slate-900/20 p-8 text-center text-slate-400">
            <FolderGit2 className="mx-auto h-8 w-8 text-slate-600 mb-2" />
            <p className="text-sm">No repositories uploaded for this project yet.</p>
          </div>
        ) : (
          <div className="grid grid-cols-1 gap-4">
            {repositories.map((repo) => (
              <Link
                key={repo.id}
                to={`/repositories/${repo.id}`}
                className="group flex items-center justify-between rounded-xl border border-slate-800 bg-slate-900/50 p-5 transition-all hover:border-indigo-500/40 hover:bg-slate-900/80 shadow-sm"
              >
                <div className="flex items-center gap-4">
                  <div className="rounded-lg bg-indigo-600/10 p-2.5 text-indigo-400 border border-indigo-500/20">
                    <FileCode2 className="h-5 w-5" />
                  </div>
                  <div>
                    <div className="flex items-center gap-2">
                      <span className="font-semibold text-sm text-slate-200 group-hover:text-indigo-400 transition-colors">
                        {repo.version_label ? `Version: ${repo.version_label}` : `Repository (${repo.id.slice(0, 8)})`}
                      </span>
                      <span className="inline-flex items-center gap-1 rounded-full bg-emerald-500/10 px-2 py-0.5 text-[11px] font-medium text-emerald-400 border border-emerald-500/20">
                        <CheckCircle2 className="h-3 w-3" />
                        <span>{repo.status}</span>
                      </span>
                    </div>
                    <div className="mt-1 flex items-center gap-3 text-xs text-slate-500">
                      <span>Source: {repo.source_type}</span>
                      <span>•</span>
                      <span>{repo.file_count} files</span>
                      <span>•</span>
                      <span>{repo.total_loc} lines of code</span>
                      <span>•</span>
                      <span>Uploaded {new Date(repo.created_at).toLocaleString()}</span>
                    </div>
                  </div>
                </div>

                <div className="flex items-center gap-1 text-xs font-medium text-indigo-400 group-hover:translate-x-1 transition-transform">
                  <span>Browse Files</span>
                  <ArrowUpRight className="h-3.5 w-3.5" />
                </div>
              </Link>
            ))}
          </div>
        )}
      </div>
    </div>
  );
};
