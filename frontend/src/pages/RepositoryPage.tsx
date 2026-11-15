import React, { useEffect, useRef, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import Editor, { OnMount } from '@monaco-editor/react';
import {
  AlertCircle,
  ArrowLeft,
  Check,
  CheckCircle2,
  Code2,
  Copy,
  FolderGit2,
  Hash,
  Layers,
  Network,
  Play,
  RefreshCw,
} from 'lucide-react';
import { api } from '../api/client';
import {
  AnalysisRun,
  CallGraphData,
  FileContent,
  FileRecord,
  FunctionRecord,
  Repository,
} from '../types';
import { FileTree } from '../components/FileTree';
import { FunctionsTable } from '../components/FunctionsTable';
import { CallGraphView } from '../components/CallGraphView';

type ActiveTab = 'files' | 'functions' | 'callgraph';

interface HighlightRange {
  fileId: string;
  lineno: number;
  endLineno: number;
}

export const RepositoryPage: React.FC = () => {
  const { repositoryId } = useParams<{ repositoryId: string }>();
  const [repository, setRepository] = useState<Repository | null>(null);
  const [files, setFiles] = useState<FileRecord[]>([]);
  const [selectedFileId, setSelectedFileId] = useState<string | null>(null);
  const [fileContent, setFileContent] = useState<FileContent | null>(null);
  const [activeTab, setActiveTab] = useState<ActiveTab>('files');

  // Analysis state
  const [functions, setFunctions] = useState<FunctionRecord[]>([]);
  const [callGraph, setCallGraph] = useState<CallGraphData | null>(null);
  const [activeRun, setActiveRun] = useState<AnalysisRun | null>(null);
  const [isAnalyzing, setIsAnalyzing] = useState<boolean>(false);
  const [analysisError, setAnalysisError] = useState<string | null>(null);

  // Loading & error
  const [isLoading, setIsLoading] = useState<boolean>(true);
  const [isFileLoading, setIsFileLoading] = useState<boolean>(false);
  const [isDataLoading, setIsDataLoading] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);
  const [copied, setCopied] = useState<boolean>(false);

  // Monaco editor references and highlighting
  const editorRef = useRef<any>(null);
  const monacoRef = useRef<any>(null);
  const decorationsRef = useRef<string[]>([]);
  const [pendingHighlight, setPendingHighlight] = useState<HighlightRange | null>(null);

  // 1. Initial load
  useEffect(() => {
    if (!repositoryId) return;

    const fetchData = async () => {
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

        // Try to fetch existing analysis artifacts
        await reloadAnalysisData(repositoryId);
      } catch (err: unknown) {
        const axiosErr = err as { response?: { data?: { detail?: string } } };
        setError(axiosErr.response?.data?.detail || 'Failed to load repository');
      } finally {
        setIsLoading(false);
      }
    };

    fetchData();
  }, [repositoryId]);

  const reloadAnalysisData = async (repoId: string) => {
    try {
      setIsDataLoading(true);
      const [funcList, graphData] = await Promise.allSettled([
        api.repositories.listFunctions(repoId),
        api.repositories.getCallGraph(repoId),
      ]);

      if (funcList.status === 'fulfilled') {
        setFunctions(funcList.value);
      }
      if (graphData.status === 'fulfilled') {
        setCallGraph(graphData.value);
      }
    } finally {
      setIsDataLoading(false);
    }
  };

  // 2. Load file content on file selection
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

  // 3. Apply line highlight in Monaco once file content is loaded
  useEffect(() => {
    if (!pendingHighlight || !editorRef.current || !monacoRef.current || isFileLoading) return;
    if (selectedFileId !== pendingHighlight.fileId) return;

    try {
      const editor = editorRef.current;
      const monaco = monacoRef.current;

      editor.revealLineInCenter(pendingHighlight.lineno);

      const newDecorations = [
        {
          range: new monaco.Range(
            pendingHighlight.lineno,
            1,
            pendingHighlight.endLineno,
            1
          ),
          options: {
            isWholeLine: true,
            className: 'bg-indigo-500/20 border-l-2 border-indigo-400',
            inlineClassName: 'bg-indigo-500/10',
          },
        },
      ];

      decorationsRef.current = editor.deltaDecorations(decorationsRef.current, newDecorations);
    } catch (e) {
      console.warn('Failed to apply Monaco decorations:', e);
    }
  }, [pendingHighlight, selectedFileId, fileContent, isFileLoading]);

  // 4. Polling analysis run
  useEffect(() => {
    if (!activeRun || activeRun.status === 'completed' || activeRun.status === 'failed') {
      return;
    }

    const interval = setInterval(async () => {
      try {
        const updated = await api.analysis.getRun(activeRun.id);
        setActiveRun(updated);

        if (updated.status === 'completed') {
          setIsAnalyzing(false);
          clearInterval(interval);
          if (repositoryId) {
            await reloadAnalysisData(repositoryId);
          }
        } else if (updated.status === 'failed') {
          setIsAnalyzing(false);
          setAnalysisError(updated.error || 'Analysis failed');
          clearInterval(interval);
        }
      } catch (err) {
        console.error('Error polling analysis run:', err);
      }
    }, 1500);

    return () => clearInterval(interval);
  }, [activeRun, repositoryId]);

  const handleRunAnalysis = async () => {
    if (!repositoryId || isAnalyzing) return;
    try {
      setIsAnalyzing(true);
      setAnalysisError(null);
      const run = await api.analysis.createRun(repositoryId);
      setActiveRun(run);
    } catch (err: unknown) {
      const axiosErr = err as { response?: { data?: { detail?: string } } };
      setAnalysisError(axiosErr.response?.data?.detail || 'Failed to initiate analysis');
      setIsAnalyzing(false);
    }
  };

  const handleSelectFunction = (fn: FunctionRecord) => {
    setPendingHighlight({
      fileId: fn.file_id,
      lineno: fn.lineno,
      endLineno: fn.end_lineno,
    });
    setSelectedFileId(fn.file_id);
    setActiveTab('files');
  };

  const handleSelectGraphNode = (nodeId: string) => {
    const fn = functions.find((f) => f.id === nodeId);
    if (fn) {
      handleSelectFunction(fn);
    }
  };

  const handleEditorMount: OnMount = (editor, monaco) => {
    editorRef.current = editor;
    monacoRef.current = monaco;
  };

  const handleCopyCode = () => {
    if (!fileContent) return;
    navigator.clipboard.writeText(fileContent.content);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  if (isLoading) {
    return (
      <div className="flex flex-1 items-center justify-center p-8 text-slate-400">
        <div className="h-6 w-6 animate-spin rounded-full border-2 border-indigo-500 border-t-transparent mr-3" />
        <span>Loading repository...</span>
      </div>
    );
  }

  if (error || !repository) {
    return (
      <div className="p-8">
        <Link
          to="/projects"
          className="inline-flex items-center gap-1.5 text-xs text-indigo-400 hover:text-indigo-300 mb-4"
        >
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
    <div className="flex flex-col h-full overflow-hidden bg-slate-950">
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
              {repository.version_label
                ? `Version: ${repository.version_label}`
                : `Repository (${repository.id.slice(0, 8)})`}
            </span>
          </div>
          <span className="text-xs text-slate-500">•</span>
          <span className="text-xs text-slate-400">{repository.file_count} files</span>
          <span className="text-xs text-slate-500">•</span>
          <span className="text-xs text-slate-400">{repository.total_loc} LOC</span>
        </div>

        {/* Actions / Run Analysis */}
        <div className="flex items-center gap-3">
          <button
            onClick={handleRunAnalysis}
            disabled={isAnalyzing}
            className={`flex items-center gap-2 px-3 py-1.5 rounded-lg text-xs font-medium transition-all ${
              isAnalyzing
                ? 'bg-indigo-600/50 text-indigo-200 cursor-not-allowed'
                : 'bg-indigo-600 hover:bg-indigo-500 text-white shadow-lg shadow-indigo-600/20'
            }`}
          >
            {isAnalyzing ? (
              <>
                <RefreshCw className="h-3.5 w-3.5 animate-spin" />
                <span>
                  Analyzing ({activeRun?.stage || 'running'}{' '}
                  {activeRun?.progress !== undefined ? `${activeRun.progress}%` : ''})...
                </span>
              </>
            ) : (
              <>
                <Play className="h-3.5 w-3.5 fill-white" />
                <span>Run Analysis</span>
              </>
            )}
          </button>
        </div>
      </div>

      {/* Analysis Status Banner */}
      {activeRun && activeRun.status === 'running' && (
        <div className="bg-indigo-950/40 border-b border-indigo-500/20 px-6 py-2 flex items-center justify-between text-xs text-indigo-300 shrink-0">
          <div className="flex items-center gap-2">
            <RefreshCw className="h-3.5 w-3.5 animate-spin text-indigo-400" />
            <span>
              Analysis in progress: Stage <strong>{activeRun.stage}</strong> ({activeRun.progress}%)
            </span>
          </div>
          <div className="w-48 bg-slate-800 rounded-full h-1.5 overflow-hidden">
            <div
              className="bg-indigo-500 h-full transition-all duration-300"
              style={{ width: `${activeRun.progress}%` }}
            />
          </div>
        </div>
      )}

      {activeRun && activeRun.status === 'completed' && !isAnalyzing && (
        <div className="bg-emerald-950/30 border-b border-emerald-500/20 px-6 py-1.5 flex items-center gap-2 text-xs text-emerald-400 shrink-0">
          <CheckCircle2 className="h-3.5 w-3.5 text-emerald-400" />
          <span>Static analysis completed: {functions.length} functions extracted.</span>
        </div>
      )}

      {analysisError && (
        <div className="bg-rose-950/30 border-b border-rose-500/20 px-6 py-2 flex items-center gap-2 text-xs text-rose-400 shrink-0">
          <AlertCircle className="h-3.5 w-3.5 text-rose-400" />
          <span>Analysis failed: {analysisError}</span>
        </div>
      )}

      {/* Navigation Tabs Header */}
      <div className="border-b border-slate-800 bg-slate-900/40 px-6 flex items-center justify-between shrink-0">
        <div className="flex items-center gap-1">
          <button
            onClick={() => setActiveTab('files')}
            className={`flex items-center gap-2 px-4 py-2.5 text-xs font-medium border-b-2 transition-colors ${
              activeTab === 'files'
                ? 'border-indigo-500 text-indigo-400 bg-indigo-500/5'
                : 'border-transparent text-slate-400 hover:text-slate-200'
            }`}
          >
            <FolderGit2 className="h-3.5 w-3.5" />
            <span>Files</span>
          </button>

          <button
            onClick={() => setActiveTab('functions')}
            className={`flex items-center gap-2 px-4 py-2.5 text-xs font-medium border-b-2 transition-colors ${
              activeTab === 'functions'
                ? 'border-indigo-500 text-indigo-400 bg-indigo-500/5'
                : 'border-transparent text-slate-400 hover:text-slate-200'
            }`}
          >
            <Code2 className="h-3.5 w-3.5" />
            <span>Functions</span>
            {functions.length > 0 && (
              <span className="px-1.5 py-0.2 rounded-full text-[10px] bg-slate-800 text-slate-300">
                {functions.length}
              </span>
            )}
          </button>

          <button
            onClick={() => setActiveTab('callgraph')}
            className={`flex items-center gap-2 px-4 py-2.5 text-xs font-medium border-b-2 transition-colors ${
              activeTab === 'callgraph'
                ? 'border-indigo-500 text-indigo-400 bg-indigo-500/5'
                : 'border-transparent text-slate-400 hover:text-slate-200'
            }`}
          >
            <Network className="h-3.5 w-3.5" />
            <span>Call Graph</span>
            {callGraph && (
              <span className="px-1.5 py-0.2 rounded-full text-[10px] bg-slate-800 text-slate-300">
                {callGraph.node_count} nodes
              </span>
            )}
          </button>
        </div>

        {activeTab === 'files' && selectedFile && (
          <div className="flex items-center gap-3 text-xs text-slate-400 py-1">
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

      {/* Main Tab Content */}
      <div className="flex-1 overflow-hidden flex flex-col">
        {activeTab === 'files' && (
          <div className="flex flex-1 overflow-hidden">
            {/* Left: File Tree */}
            <FileTree
              files={files}
              selectedFileId={selectedFileId}
              onSelectFile={(id) => {
                setSelectedFileId(id);
                setPendingHighlight(null);
                decorationsRef.current = [];
              }}
            />

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
                        <div className="h-6 w-6 animate-spin rounded-full border-2 border-indigo-500 border-t-transparent mr-2" />
                        <span>Loading file content...</span>
                      </div>
                    ) : (
                      <Editor
                        height="100%"
                        language={selectedFile.language === 'python' ? 'python' : 'text'}
                        theme="vs-dark"
                        value={fileContent?.content || ''}
                        onMount={handleEditorMount}
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
        )}

        {activeTab === 'functions' && (
          <FunctionsTable
            functions={functions}
            onSelectFunction={handleSelectFunction}
            isLoading={isDataLoading}
          />
        )}

        {activeTab === 'callgraph' && (
          <CallGraphView
            data={callGraph}
            onSelectNode={handleSelectGraphNode}
            isLoading={isDataLoading}
          />
        )}
      </div>
    </div>
  );
};
