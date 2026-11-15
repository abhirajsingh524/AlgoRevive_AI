import React, { useEffect, useState } from 'react';
import Editor from '@monaco-editor/react';
import {
  Code2,
  Database,
  GitFork,
  HelpCircle,
  X,
} from 'lucide-react';
import { api } from '../api/client';
import { BottleneckRecord } from '../types';
import { MiniCallGraph } from './MiniCallGraph';
import { WhyFlaggedTree } from './WhyFlaggedTree';

interface BottleneckDetailDrawerProps {
  bottleneck: BottleneckRecord;
  repositoryId?: string;
  onClose: () => void;
}

export const BottleneckDetailDrawer: React.FC<BottleneckDetailDrawerProps> = ({
  bottleneck,
  repositoryId,
  onClose,
}) => {
  const [activeTab, setActiveTab] = useState<'why' | 'code' | 'workload' | 'callers'>('why');
  const [fileContent, setFileContent] = useState<string>('');
  const [loadingCode, setLoadingCode] = useState<boolean>(false);

  const fn = bottleneck.function;
  const evidence = bottleneck.evidence || {};
  const workload = evidence.workload;
  const affectedCallers = evidence.affected_functions || [];
  const whyFlaggedNode = evidence.why_flagged;

  useEffect(() => {
    if (activeTab === 'code' && fn && repositoryId && !fileContent) {
      const fetchCode = async () => {
        try {
          setLoadingCode(true);
          const data = await api.repositories.getFileContent(repositoryId, fn.file_id);
          setFileContent(data.content);
        } catch (err) {
          console.error('Failed to load function source code:', err);
        } finally {
          setLoadingCode(false);
        }
      };
      fetchCode();
    }
  }, [activeTab, fn, repositoryId, fileContent]);

  const getSeverityBadge = (severity: string) => {
    switch (severity.toUpperCase()) {
      case 'CRITICAL':
        return (
          <span className="px-2.5 py-0.5 rounded-full text-xs font-bold uppercase tracking-wider bg-rose-950 text-rose-300 border border-rose-800">
            Critical
          </span>
        );
      case 'HIGH':
        return (
          <span className="px-2.5 py-0.5 rounded-full text-xs font-bold uppercase tracking-wider bg-amber-950 text-amber-300 border border-amber-800">
            High
          </span>
        );
      case 'MEDIUM':
        return (
          <span className="px-2.5 py-0.5 rounded-full text-xs font-bold uppercase tracking-wider bg-yellow-950 text-yellow-300 border border-yellow-800">
            Medium
          </span>
        );
      default:
        return (
          <span className="px-2.5 py-0.5 rounded-full text-xs font-bold uppercase tracking-wider bg-emerald-950 text-emerald-300 border border-emerald-800">
            Low
          </span>
        );
    }
  };

  return (
    <div className="fixed inset-y-0 right-0 z-50 w-full max-w-2xl bg-slate-900 border-l border-slate-800 shadow-2xl flex flex-col animate-in slide-in-from-right duration-200">
      {/* Header */}
      <div className="p-5 border-b border-slate-800 flex items-start justify-between bg-slate-950/60">
        <div>
          <div className="flex items-center gap-2 mb-1">
            {getSeverityBadge(bottleneck.severity)}
            <span className="text-xs font-mono text-slate-400">
              Impact: <strong className="text-white">{bottleneck.impact_score.toFixed(3)}</strong>
            </span>
            {evidence.source === 'static-only' && (
              <span className="px-2 py-0.5 rounded text-[10px] font-semibold bg-slate-800 text-slate-300 border border-slate-700">
                Static-Only
              </span>
            )}
          </div>
          <h2 className="text-lg font-mono font-bold text-white truncate max-w-lg">
            {fn?.name || 'Function Bottleneck'}
          </h2>
          <div className="text-xs text-slate-400 font-mono truncate max-w-lg">
            {fn?.qualified_name}
          </div>
        </div>
        <button
          onClick={onClose}
          className="p-1.5 rounded-lg text-slate-400 hover:text-white hover:bg-slate-800 transition"
        >
          <X className="w-5 h-5" />
        </button>
      </div>

      {/* Tabs */}
      <div className="flex border-b border-slate-800 px-5 bg-slate-950/40">
        <button
          onClick={() => setActiveTab('why')}
          className={`flex items-center gap-1.5 py-3 px-3 border-b-2 text-sm font-medium transition ${
            activeTab === 'why'
              ? 'border-indigo-500 text-indigo-400'
              : 'border-transparent text-slate-400 hover:text-slate-200'
          }`}
        >
          <HelpCircle className="w-4 h-4" />
          Why Flagged?
        </button>
        <button
          onClick={() => setActiveTab('code')}
          className={`flex items-center gap-1.5 py-3 px-3 border-b-2 text-sm font-medium transition ${
            activeTab === 'code'
              ? 'border-indigo-500 text-indigo-400'
              : 'border-transparent text-slate-400 hover:text-slate-200'
          }`}
        >
          <Code2 className="w-4 h-4" />
          Code Highlight
        </button>
        <button
          onClick={() => setActiveTab('workload')}
          className={`flex items-center gap-1.5 py-3 px-3 border-b-2 text-sm font-medium transition ${
            activeTab === 'workload'
              ? 'border-indigo-500 text-indigo-400'
              : 'border-transparent text-slate-400 hover:text-slate-200'
          }`}
        >
          <Database className="w-4 h-4" />
          Workload Profile
        </button>
        <button
          onClick={() => setActiveTab('callers')}
          className={`flex items-center gap-1.5 py-3 px-3 border-b-2 text-sm font-medium transition ${
            activeTab === 'callers'
              ? 'border-indigo-500 text-indigo-400'
              : 'border-transparent text-slate-400 hover:text-slate-200'
          }`}
        >
          <GitFork className="w-4 h-4" />
          Call Graph ({affectedCallers.length})
        </button>
      </div>

      {/* Content */}
      <div className="flex-1 overflow-y-auto p-5 space-y-4">
        {/* Tab 1: Why Flagged? */}
        {activeTab === 'why' && (
          <div className="space-y-4">
            <div className="text-xs text-slate-400">
              Structured diagnostic tree derived strictly from stored static complexity and runtime profiling evidence.
            </div>
            {whyFlaggedNode ? (
              <WhyFlaggedTree node={whyFlaggedNode} isRoot />
            ) : (
              <div className="p-4 rounded-lg bg-slate-950 border border-slate-800 text-sm text-slate-400">
                No explanation tree generated.
              </div>
            )}
          </div>
        )}

        {/* Tab 2: Code Highlight */}
        {activeTab === 'code' && (
          <div className="space-y-3 h-full flex flex-col">
            <div className="flex items-center justify-between text-xs text-slate-400 font-mono">
              <span>Lines {fn?.lineno} - {fn?.end_lineno}</span>
              <span>Complexity: {fn?.complexity_class || 'N/A'}</span>
            </div>
            <div className="flex-1 min-h-[420px] rounded-lg border border-slate-800 overflow-hidden">
              {loadingCode ? (
                <div className="h-full flex items-center justify-center text-slate-400 text-sm">
                  Loading source code...
                </div>
              ) : (
                <Editor
                  height="420px"
                  language="python"
                  theme="vs-dark"
                  value={fileContent}
                  options={{
                    readOnly: true,
                    minimap: { enabled: false },
                    scrollBeyondLastLine: false,
                    fontSize: 12,
                    lineNumbers: 'on',
                  }}
                  onMount={(editor) => {
                    if (fn?.lineno) {
                      editor.revealLineInCenter(fn.lineno);
                      editor.setSelection({
                        startLineNumber: fn.lineno,
                        startColumn: 1,
                        endLineNumber: fn.end_lineno || fn.lineno,
                        endColumn: 100,
                      });
                    }
                  }}
                />
              )}
            </div>
          </div>
        )}

        {/* Tab 3: Workload Profile */}
        {activeTab === 'workload' && (
          <div className="space-y-4">
            <div className="text-xs text-slate-400">
              Workload characteristics driving the execution profile and downstream ML feature representation.
            </div>
            {workload ? (
              <div className="grid grid-cols-2 gap-3">
                <div className="p-3 rounded-lg bg-slate-950 border border-slate-800">
                  <div className="text-xs text-slate-400">Input Size (Largest N)</div>
                  <div className="text-lg font-mono font-bold text-white mt-0.5">
                    {workload.input_size.toLocaleString()}
                  </div>
                </div>
                <div className="p-3 rounded-lg bg-slate-950 border border-slate-800">
                  <div className="text-xs text-slate-400">Lookup Frequency</div>
                  <div className="text-lg font-mono font-bold text-amber-400 mt-0.5">
                    {workload.lookup_frequency}
                  </div>
                </div>
                <div className="p-3 rounded-lg bg-slate-950 border border-slate-800">
                  <div className="text-xs text-slate-400">Insert / Delete Ratio</div>
                  <div className="text-sm font-mono text-slate-200 mt-0.5">
                    Insert: {workload.insert_ratio} | Delete: {workload.delete_ratio}
                  </div>
                </div>
                <div className="p-3 rounded-lg bg-slate-950 border border-slate-800">
                  <div className="text-xs text-slate-400">Read / Write Ratio</div>
                  <div className="text-lg font-mono font-bold text-indigo-400 mt-0.5">
                    {workload.read_write_ratio}:1
                  </div>
                </div>
                <div className="p-3 rounded-lg bg-slate-950 border border-slate-800">
                  <div className="text-xs text-slate-400">Data Distribution</div>
                  <div className="text-sm font-mono text-slate-200 mt-0.5 capitalize">
                    {workload.data_distribution}
                  </div>
                </div>
                <div className="p-3 rounded-lg bg-slate-950 border border-slate-800">
                  <div className="text-xs text-slate-400">Memory Constraint</div>
                  <div className="text-sm font-mono text-slate-200 mt-0.5">
                    {workload.memory_constraint}
                  </div>
                </div>
                <div className="p-3 rounded-lg bg-slate-950 border border-slate-800 col-span-2">
                  <div className="text-xs text-slate-400">Latency Requirement</div>
                  <div className="text-sm font-mono text-slate-200 mt-0.5">
                    {workload.latency_requirement}
                  </div>
                </div>
              </div>
            ) : (
              <div className="p-4 rounded-lg bg-slate-950 border border-slate-800 text-sm text-slate-400">
                No workload profile available (static-only execution).
              </div>
            )}
          </div>
        )}

        {/* Tab 4: Affected Callers */}
        {activeTab === 'callers' && (
          <div className="space-y-4">
            <div className="text-xs text-slate-400">
              Transitive caller functions discovered in call graph. Functions labeled with green are tested directly by the workload spec.
            </div>
            <MiniCallGraph
              bottleneckName={fn?.name || 'target'}
              affectedFunctions={affectedCallers}
            />
            {affectedCallers.length > 0 && (
              <div className="space-y-2 pt-2">
                <div className="text-xs font-semibold uppercase tracking-wider text-slate-400">
                  Callers Table
                </div>
                <div className="rounded-lg border border-slate-800 overflow-hidden">
                  <table className="w-full text-left text-xs">
                    <thead className="bg-slate-950 text-slate-400 border-b border-slate-800">
                      <tr>
                        <th className="py-2 px-3">Depth</th>
                        <th className="py-2 px-3">Caller Function</th>
                        <th className="py-2 px-3">File Path</th>
                        <th className="py-2 px-3">Workload Coverage</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-slate-800">
                      {affectedCallers.map((c, i) => (
                        <tr key={i} className="hover:bg-slate-800/40">
                          <td className="py-2 px-3 font-mono text-slate-400">{c.depth}</td>
                          <td className="py-2 px-3 font-mono font-semibold text-slate-200">{c.name}</td>
                          <td className="py-2 px-3 text-slate-400 truncate max-w-xs">{c.file_path}</td>
                          <td className="py-2 px-3">
                            {c.covered_by_workload ? (
                              <span className="px-2 py-0.5 rounded bg-emerald-950 text-emerald-400 border border-emerald-800 text-[10px] font-semibold">
                                Covered
                              </span>
                            ) : (
                              <span className="px-2 py-0.5 rounded bg-slate-800 text-slate-400 border border-slate-700 text-[10px]">
                                Indirect
                              </span>
                            )}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
};
