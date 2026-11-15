import React, { useEffect, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import Editor from '@monaco-editor/react';
import { ArrowLeft, Check, Copy, FileCode, FolderGit2, Hash, Layers } from 'lucide-react';
import { api } from '../api/client';
import { FileContent, FileRecord, Repository } from '../types';

export const RepositoryPage: React.FC = () => {
  const { repositoryId } = useParams<{ repositoryId: string }>();
  const [repository, setRepository] = useState<Repository | null>(null);
  const [files, setFiles] = useState<FileRecord[]>([]);
  const [selectedFileId, setSelectedFileId] = useState<string | null>(null);
  const [fileContent, setFileContent] = useState<FileContent | null>(null);
  const [isLoading, setIsLoading] = useState<boolean>(true);
  const [isFileLoading, setIsFileLoading] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);
  const [copied, setCopied] = useState<boolean>(false);

  useEffect(() => {
    if (!repositoryId) return;

    const fetchRepoAndFiles = async () => {
      try {
        setIsLoading(true);
        setError(null);
        const [repoData, fileList] = await Promise.all([
          api.repositories.get(repositoryId),
          api.repositories.listFiles(repositoryId),
        ]);
        setRepository(repoData);
        setFiles(fileList);
        if (fileList.length > 0) {
          setSelectedFileId(fileList[0].id);
        }
      } catch (err: unknown) {
        const axiosErr = err as { response?: { data?: { detail?: string } } };
        setError(axiosErr.response?.data?.detail || 'Failed to load repository files');
      } finally {
        setIsLoading(false);
      }
    };

    fetchRepoAndFiles();
  }, [repositoryId]);

  useEffect(() => {
    if (!repositoryId || !selectedFileId) return;

    const fetchContent = async () => {
      try {
        setIsFileLoading(true);
        const contentData = await api.repositories.getFileContent(repositoryId, selectedFileId);
        setFileContent(contentData);
      } catch (err: unknown) {
        console.error('Failed to load file content', err);
      } finally {
        setIsFileLoading(false);
      }
    };

    fetchContent();
  }, [repositoryId, selectedFileId]);

  const handleCopyCode = () => {
    if (!fileContent) return;
    navigator.clipboard.writeText(fileContent.content);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  if (isLoading) {
    return (
      <div className="flex flex-1 items-center justify-center p-8 text-slate-400">
        <div className="h-6 w-6 animate-spin rounded-full border-2 border-indigo-500 border-t-transparent mr-3"></div>
        <span>Loading repository files...</span>
      </div>
    );
  }

  if (error || !repository) {
    return (
      <div className="p-8">
        <Link to="/projects" className="inline-flex items-center gap-1.5 text-xs text-indigo-400 hover:text-indigo-300 mb-4">
          <ArrowLeft className="h-3.5 w-3.5" />
          <span>Back to Projects</span>
        </Link>
        <div className="rounded-xl border border-red-500/20 bg-red-500/10 p-4 text-red-400">
          <p className="font-semibold">Error</p>
          <p className="text-sm">{error || 'Repository not found'}</p>
        </div>
      </div>
    );
  }

  const selectedFile = files.find((f) => f.id === selectedFileId);

  return (
    <div className="flex flex-col h-full overflow-hidden">
      {/* Top Header */}
      <div className="h-14 border-b border-slate-800 bg-slate-900/60 px-6 flex items-center justify-between shrink-0">
        <div className="flex items-center gap-3">
          <Link
            to={`/projects/${repository.project_id}`}
            className="p-1.5 text-slate-400 hover:text-slate-200 hover:bg-slate-800 rounded-md transition-colors"
            title="Back to Project"
          >
            <ArrowLeft className="h-4 w-4" />
          </Link>
          <div className="flex items-center gap-2">
            <FolderGit2 className="h-4 w-4 text-indigo-400" />
            <span className="font-semibold text-sm text-slate-200">
              {repository.version_label ? `Version: ${repository.version_label}` : `Repository (${repository.id.slice(0, 8)})`}
            </span>
          </div>
          <span className="text-xs text-slate-500">•</span>
          <span className="text-xs text-slate-400">{repository.file_count} files</span>
          <span className="text-xs text-slate-500">•</span>
          <span className="text-xs text-slate-400">{repository.total_loc} LOC</span>
        </div>

        {selectedFile && (
          <div className="flex items-center gap-3 text-xs text-slate-400">
            <span className="flex items-center gap-1">
              <Layers className="h-3.5 w-3.5 text-slate-500" />
              <span>{selectedFile.language}</span>
            </span>
            <span className="flex items-center gap-1">
              <Hash className="h-3.5 w-3.5 text-slate-500" />
              <span>{selectedFile.loc} lines</span>
            </span>
            <button
              onClick={handleCopyCode}
              className="flex items-center gap-1 px-2.5 py-1 rounded bg-slate-800 text-slate-300 hover:bg-slate-700 hover:text-white transition-colors"
            >
              {copied ? <Check className="h-3 w-3 text-emerald-400" /> : <Copy className="h-3 w-3" />}
              <span>{copied ? 'Copied' : 'Copy'}</span>
            </button>
          </div>
        )}
      </div>

      {/* Main File Browser Split */}
      <div className="flex flex-1 overflow-hidden">
        {/* Left: File Tree */}
        <div className="w-80 border-r border-slate-800 bg-slate-900/30 flex flex-col shrink-0">
          <div className="px-4 py-3 border-b border-slate-800/80 text-xs font-semibold uppercase tracking-wider text-slate-400">
            Files ({files.length})
          </div>
          <div className="flex-1 overflow-y-auto p-2 space-y-1">
            {files.map((file) => {
              const isSelected = file.id === selectedFileId;
              return (
                <button
                  key={file.id}
                  onClick={() => setSelectedFileId(file.id)}
                  className={`w-full flex items-center justify-between px-3 py-2 rounded-lg text-left text-xs transition-colors ${
                    isSelected
                      ? 'bg-indigo-600/20 text-indigo-300 font-medium border border-indigo-500/30'
                      : 'text-slate-400 hover:bg-slate-800/50 hover:text-slate-200'
                  }`}
                >
                  <div className="flex items-center gap-2 overflow-hidden pr-2">
                    <FileCode className={`h-3.5 w-3.5 shrink-0 ${isSelected ? 'text-indigo-400' : 'text-slate-500'}`} />
                    <span className="truncate">{file.path}</span>
                  </div>
                  <span className="text-[10px] text-slate-500 shrink-0">{file.loc} L</span>
                </button>
              );
            })}
          </div>
        </div>

        {/* Right: Monaco Editor Viewer */}
        <div className="flex-1 flex flex-col bg-slate-950 overflow-hidden">
          {selectedFile ? (
            <>
              <div className="h-9 px-4 border-b border-slate-800/80 bg-slate-900/20 flex items-center justify-between text-xs text-slate-400 shrink-0">
                <span className="font-mono text-slate-300">{selectedFile.path}</span>
                <span className="text-[11px] text-slate-500 font-mono truncate max-w-xs">
                  SHA: {selectedFile.sha256.slice(0, 16)}...
                </span>
              </div>
              <div className="flex-1 relative overflow-hidden">
                {isFileLoading ? (
                  <div className="absolute inset-0 flex items-center justify-center bg-slate-950 text-slate-400">
                    <div className="h-6 w-6 animate-spin rounded-full border-2 border-indigo-500 border-t-transparent mr-2"></div>
                    <span>Loading file content...</span>
                  </div>
                ) : (
                  <Editor
                    height="100%"
                    language={selectedFile.language === 'python' ? 'python' : 'text'}
                    theme="vs-dark"
                    value={fileContent?.content || ''}
                    options={{
                      readOnly: true,
                      minimap: { enabled: true },
                      fontSize: 13,
                      lineNumbers: 'on',
                      scrollBeyondLastLine: false,
                      automaticLayout: true,
                      wordWrap: 'on',
                    }}
                  />
                )}
              </div>
            </>
          ) : (
            <div className="flex-1 flex items-center justify-center text-slate-500 text-sm">
              Select a file from the list to view its code
            </div>
          )}
        </div>
      </div>
    </div>
  );
};
