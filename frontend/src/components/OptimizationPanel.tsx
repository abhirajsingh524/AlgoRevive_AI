import React, { useEffect, useState } from 'react';
import { DiffEditor } from '@monaco-editor/react';
import {
  AlertCircle,
  AlertTriangle,
  CheckCircle2,
  Cpu,
  FileCode2,
  FileDiff,
  Info,
  Loader2,
  Lock,
  Play,
  RotateCcw,
  ShieldCheck,
  Sparkles,
  Zap,
} from 'lucide-react';
import { api } from '../api/client';
import { useJobProgress } from '../hooks/useJobProgress';
import { BottleneckRecord, OptimizationConfig, OptimizationRecord } from '../types';

interface OptimizationPanelProps {
  bottleneck: BottleneckRecord;
  originalSource: string;
  loadingSource: boolean;
}

const TEMPLATE_OPTIONS = [
  { id: 'auto', label: 'Auto (Recommended from Bottleneck Analysis)' },
  { id: 'T1_SET_MEMBERSHIP', label: 'T1: Set Membership (Precompute set for O(1) in-loop lookup)' },
  { id: 'T2_DICT_INDEX_JOIN', label: 'T2: Dict Index Join (Index inner loop with defaultdict)' },
  { id: 'T3_MIN_MAX_HEAP', label: 'T3: Min/Max/Heap (Replace full sort with O(n) extreme selection)' },
  { id: 'T4_JOIN_STRINGS', label: 'T4: String Join (List accumulation & "".join() for loops)' },
  { id: 'T5_LRU_CACHE', label: 'T5: LRU Cache (functools.lru_cache for pure recursion)' },
  { id: 'T6_DEQUE_POPLEFT', label: 'T6: Deque Popleft (collections.deque for fast front pops)' },
];

export const OptimizationPanel: React.FC<OptimizationPanelProps> = ({
  bottleneck,
  originalSource,
  loadingSource,
}) => {
  const [optimizations, setOptimizations] = useState<OptimizationRecord[]>([]);
  const [selectedOpt, setSelectedOpt] = useState<OptimizationRecord | null>(null);
  const [loadingOpts, setLoadingOpts] = useState<boolean>(false);
  const [generating, setGenerating] = useState<boolean>(false);
  const [activeJobId, setActiveJobId] = useState<string | null>(null);

  const [mode, setMode] = useState<'template' | 'llm'>('template');
  const [templateId, setTemplateId] = useState<string>('auto');
  const [viewPatchDiff, setViewPatchDiff] = useState<boolean>(false);

  const [config, setConfig] = useState<OptimizationConfig>({
    llm_provider: 'none',
    llm_enabled: false,
    llm_model: null,
    templates: [],
  });

  const fn = bottleneck.function;
  const rec = bottleneck.recommendation || bottleneck.evidence?.recommendation;

  // 1. Fetch LLM & generator config
  useEffect(() => {
    let isMounted = true;
    const fetchConfig = async () => {
      try {
        const cfg = await api.optimizations.getConfig();
        if (isMounted) {
          setConfig(cfg);
        }
      } catch (err) {
        console.warn('Could not fetch optimization config:', err);
      }
    };
    fetchConfig();
    return () => {
      isMounted = false;
    };
  }, []);

  // 2. Fetch existing optimizations for this bottleneck
  const loadOptimizations = async () => {
    try {
      setLoadingOpts(true);
      const data = await api.optimizations.list(bottleneck.id);
      setOptimizations(data);
      if (data.length > 0) {
        setSelectedOpt(data[0]);
      } else {
        setSelectedOpt(null);
      }
    } catch (err) {
      console.error('Failed to load optimizations:', err);
    } finally {
      setLoadingOpts(false);
    }
  };

  useEffect(() => {
    loadOptimizations();
  }, [bottleneck.id]);

  // 3. WebSocket Job Progress
  const { progressState, isConnected } = useJobProgress(activeJobId, async (finalStatus) => {
    console.log(`Optimization generation finished with status: ${finalStatus}`);
    setGenerating(false);
    setActiveJobId(null);
    await loadOptimizations();
  });

  // 4. Trigger Candidate Generation
  const handleGenerate = async () => {
    if (mode === 'llm' && !config.llm_enabled) return;

    try {
      setGenerating(true);
      const payload: { mode: 'template' | 'llm'; template_id?: string } = {
        mode,
        ...(mode === 'template' && templateId !== 'auto' ? { template_id: templateId } : {}),
      };

      const opt = await api.optimizations.create(bottleneck.id, payload);
      setActiveJobId(opt.id);

      // If backend finished synchronously, update immediately
      if (opt.status === 'generated' || opt.status === 'failed') {
        setSelectedOpt(opt);
        setGenerating(false);
        setActiveJobId(null);
        await loadOptimizations();
      }
    } catch (err: any) {
      console.error('Candidate generation failed:', err);
      setGenerating(false);
      setActiveJobId(null);
      await loadOptimizations();
    }
  };

  const decisionReason = selectedOpt?.decision_reason;
  const rationale = decisionReason?.rationale;
  const safetyNotes = decisionReason?.safety_notes;
  const changedLines = decisionReason?.changed_lines;

  return (
    <div className="space-y-6">
      {/* Configuration & Trigger Card */}
      <div className="p-4 rounded-xl bg-slate-950 border border-slate-800 space-y-4">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Zap className="w-4 h-4 text-amber-400" />
            <h3 className="text-sm font-semibold text-white">Generate Candidate Optimization</h3>
          </div>
          {isConnected && generating && (
            <span className="flex items-center gap-1.5 text-xs text-emerald-400 font-mono">
              <span className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse" />
              Live WebSocket
            </span>
          )}
        </div>

        {/* Mode Selector */}
        <div className="space-y-2">
          <label className="text-xs font-medium text-slate-300">Generation Engine</label>
          <div className="grid grid-cols-2 gap-3">
            {/* Template Mode */}
            <button
              type="button"
              onClick={() => setMode('template')}
              disabled={generating}
              className={`p-3 rounded-lg border text-left transition flex flex-col justify-between ${
                mode === 'template'
                  ? 'border-indigo-500 bg-indigo-950/30 text-white shadow-sm'
                  : 'border-slate-800 bg-slate-900/60 text-slate-400 hover:border-slate-700'
              }`}
            >
              <div className="flex items-center justify-between w-full">
                <span className="text-sm font-semibold text-white flex items-center gap-1.5">
                  <ShieldCheck className="w-4 h-4 text-indigo-400" />
                  Deterministic Template
                </span>
                <span className="text-[10px] px-1.5 py-0.5 rounded font-mono font-bold bg-indigo-900/60 text-indigo-300 border border-indigo-700">
                  Mode A
                </span>
              </div>
              <p className="text-xs text-slate-400 mt-1">
                Guaranteed semantic preservation via LibCST AST transformations. Zero hallucinations.
              </p>
            </button>

            {/* LLM Mode */}
            <div className="relative">
              <button
                type="button"
                onClick={() => {
                  if (config.llm_enabled) setMode('llm');
                }}
                disabled={generating || !config.llm_enabled}
                className={`w-full p-3 rounded-lg border text-left transition flex flex-col justify-between h-full ${
                  !config.llm_enabled
                    ? 'border-slate-800/80 bg-slate-950/40 text-slate-500 cursor-not-allowed opacity-75'
                    : mode === 'llm'
                    ? 'border-purple-500 bg-purple-950/30 text-white shadow-sm'
                    : 'border-slate-800 bg-slate-900/60 text-slate-400 hover:border-slate-700'
                }`}
              >
                <div className="flex items-center justify-between w-full">
                  <span className="text-sm font-semibold flex items-center gap-1.5 text-slate-300">
                    <Sparkles className="w-4 h-4 text-purple-400" />
                    LLM Synthesis
                  </span>
                  <span className="text-[10px] px-1.5 py-0.5 rounded font-mono font-bold bg-purple-900/60 text-purple-300 border border-purple-700">
                    Mode B
                  </span>
                </div>
                <p className="text-xs text-slate-400 mt-1">
                  Guided LLM code generation with sandbox AST validation and import allowlisting.
                </p>
              </button>

              {/* Disabled Tooltip / Explanation */}
              {!config.llm_enabled && (
                <div className="mt-1.5 flex items-center gap-1 text-[11px] text-amber-400 font-mono">
                  <Lock className="w-3 h-3 flex-shrink-0" />
                  <span>
                    LLM disabled (<code>LLM_PROVIDER=none</code>). Configure OpenAI, Ollama, or vLLM in settings to enable.
                  </span>
                </div>
              )}
            </div>
          </div>
        </div>

        {/* Template Selector (When Template mode is active) */}
        {mode === 'template' && (
          <div className="space-y-1.5">
            <label className="text-xs font-medium text-slate-300">Target Template</label>
            <select
              value={templateId}
              onChange={(e) => setTemplateId(e.target.value)}
              disabled={generating}
              className="w-full bg-slate-900 border border-slate-800 rounded-lg px-3 py-2 text-xs text-slate-200 focus:outline-none focus:border-indigo-500 font-mono"
            >
              {TEMPLATE_OPTIONS.map((opt) => (
                <option key={opt.id} value={opt.id}>
                  {opt.label}
                </option>
              ))}
            </select>
            {rec?.recommended_algorithm && (
              <div className="text-[11px] text-slate-400">
                Recommended by analysis:{' '}
                <span className="font-mono text-indigo-400 font-semibold">{rec.recommended_algorithm}</span>
              </div>
            )}
          </div>
        )}

        {/* Generate Button & Progress */}
        <div className="pt-2 flex flex-col gap-3">
          <div className="flex items-center gap-3">
            <button
              type="button"
              onClick={handleGenerate}
              disabled={generating || (mode === 'llm' && !config.llm_enabled)}
              className="flex items-center gap-2 px-4 py-2.5 rounded-lg text-xs font-semibold text-white bg-indigo-600 hover:bg-indigo-500 disabled:opacity-50 disabled:cursor-not-allowed transition shadow-md shadow-indigo-900/30"
            >
              {generating ? (
                <>
                  <Loader2 className="w-4 h-4 animate-spin" />
                  Synthesizing Candidate...
                </>
              ) : (
                <>
                  <Play className="w-4 h-4 fill-current" />
                  Generate Candidate
                </>
              )}
            </button>

            {optimizations.length > 0 && (
              <div className="flex items-center gap-2 ml-auto text-xs text-slate-400">
                <span>Runs ({optimizations.length}):</span>
                <select
                  value={selectedOpt?.id || ''}
                  onChange={(e) => {
                    const found = optimizations.find((o) => o.id === e.target.value);
                    if (found) setSelectedOpt(found);
                  }}
                  className="bg-slate-900 border border-slate-800 rounded px-2 py-1 text-xs text-slate-200 font-mono"
                >
                  {optimizations.map((o, idx) => (
                    <option key={o.id} value={o.id}>
                      #{optimizations.length - idx} ({o.mode.toUpperCase()}: {o.status})
                    </option>
                  ))}
                </select>
                <button
                  type="button"
                  onClick={loadOptimizations}
                  title="Refresh runs"
                  className="p-1 rounded hover:bg-slate-800 text-slate-400 hover:text-white transition"
                >
                  <RotateCcw className="w-3.5 h-3.5" />
                </button>
              </div>
            )}
          </div>

          {/* Live Progress Bar */}
          {generating && (
            <div className="p-3 rounded-lg bg-slate-900/90 border border-indigo-900/50 space-y-2">
              <div className="flex items-center justify-between text-xs font-mono">
                <span className="text-indigo-300 font-semibold flex items-center gap-1.5">
                  <Loader2 className="w-3.5 h-3.5 animate-spin text-indigo-400" />
                  {progressState?.stage ? `Stage: ${progressState.stage}` : 'Initializing pipeline...'}
                </span>
                <span className="text-white font-bold">{progressState?.progress ?? 20}%</span>
              </div>
              <div className="w-full h-1.5 bg-slate-800 rounded-full overflow-hidden">
                <div
                  className="h-full bg-gradient-to-r from-indigo-500 to-purple-500 transition-all duration-300"
                  style={{ width: `${progressState?.progress ?? 20}%` }}
                />
              </div>
              <div className="text-[11px] text-slate-400 font-mono truncate">
                {progressState?.message || 'Processing candidate synthesis...'}
              </div>
            </div>
          )}
        </div>
      </div>

      {/* Loading State */}
      {loadingOpts && !selectedOpt && (
        <div className="p-8 text-center text-slate-400 text-sm">
          <Loader2 className="w-5 h-5 animate-spin mx-auto mb-2 text-indigo-400" />
          Loading candidate history...
        </div>
      )}

      {/* Case 1: No Candidate Generated Yet */}
      {!loadingOpts && optimizations.length === 0 && !generating && (
        <div className="p-8 rounded-xl border border-dashed border-slate-800 text-center space-y-3 bg-slate-950/40">
          <FileCode2 className="w-8 h-8 text-slate-600 mx-auto" />
          <h4 className="text-sm font-semibold text-white">No Candidate Generated Yet</h4>
          <p className="text-xs text-slate-400 max-w-md mx-auto">
            Choose Deterministic Template (Mode A) or LLM Synthesis (Mode B) above and click{' '}
            <strong className="text-slate-200">Generate Candidate</strong> to produce a safe, minimal AST diff for{' '}
            <code className="text-indigo-300">{fn?.name}</code>.
          </p>
        </div>
      )}

      {/* Case 2: Candidate Generation Failed / No Safe Candidate Available */}
      {selectedOpt && selectedOpt.status === 'failed' && (
        <div className="p-5 rounded-xl border border-rose-900/60 bg-rose-950/20 space-y-3">
          <div className="flex items-start gap-3">
            <AlertCircle className="w-5 h-5 text-rose-400 flex-shrink-0 mt-0.5" />
            <div>
              <h4 className="text-sm font-semibold text-rose-200">No Safe Candidate Available</h4>
              <p className="text-xs text-rose-300/90 mt-1 font-mono leading-relaxed">
                {selectedOpt.error || 'The optimizer rejected candidate generation because safety preconditions were not met.'}
              </p>
            </div>
          </div>
          <div className="p-3 rounded-lg bg-slate-950/60 border border-slate-800 text-xs text-slate-400 space-y-1">
            <div className="font-semibold text-slate-300 flex items-center gap-1.5">
              <Info className="w-3.5 h-3.5 text-indigo-400" />
              Safety Guarantee
            </div>
            <div>
              Deterministic templates strictly require all AST preconditions to hold before modifying code. When
              conditions fail (e.g. elements mutated, or function is already optimal), generation safely aborts without
              altering target behavior.
            </div>
          </div>
        </div>
      )}

      {/* Case 3: Candidate Generated Successfully */}
      {selectedOpt && selectedOpt.status === 'generated' && (
        <div className="space-y-4">
          {/* Status Header Badge */}
          <div className="flex items-center justify-between p-3 rounded-lg bg-emerald-950/30 border border-emerald-900/60">
            <div className="flex items-center gap-2">
              <CheckCircle2 className="w-4 h-4 text-emerald-400" />
              <span className="text-xs font-semibold text-emerald-200">Candidate Generated Successfully</span>
              <span className="text-[10px] px-2 py-0.5 rounded font-mono bg-emerald-900/60 text-emerald-300 border border-emerald-700 uppercase">
                {selectedOpt.mode} {selectedOpt.template_id ? `(${selectedOpt.template_id})` : ''}
              </span>
            </div>
            {changedLines && changedLines.length > 0 && (
              <span className="text-xs font-mono text-slate-400">
                Changed Lines: <strong className="text-emerald-400">{changedLines.join(', ')}</strong>
              </span>
            )}
          </div>

          {/* Rationale & Safety Notes Cards */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            {/* Rationale */}
            <div className="p-3.5 rounded-lg bg-slate-950 border border-slate-800 space-y-1.5">
              <div className="flex items-center gap-1.5 text-xs font-semibold text-indigo-300">
                <Cpu className="w-3.5 h-3.5 text-indigo-400" />
                Optimization Rationale
              </div>
              <p className="text-xs text-slate-300 leading-relaxed font-sans">
                {rationale || 'Candidate replaces identified algorithmic bottleneck with optimal complexity structure.'}
              </p>
            </div>

            {/* Safety Notes */}
            <div className="p-3.5 rounded-lg bg-slate-950 border border-slate-800 space-y-1.5">
              <div className="flex items-center gap-1.5 text-xs font-semibold text-amber-300">
                <AlertTriangle className="w-3.5 h-3.5 text-amber-400" />
                Safety Notes & Invariants
              </div>
              <p className="text-xs text-slate-300 leading-relaxed font-sans">
                {safetyNotes || 'Candidate conforms to shared AST guards: unchanged signature and target-only scope.'}
              </p>
            </div>
          </div>

          {/* Monaco Diff Viewer & Patch Toggle */}
          <div className="rounded-xl border border-slate-800 overflow-hidden bg-slate-950">
            <div className="px-4 py-2.5 border-b border-slate-800 flex items-center justify-between bg-slate-900/80">
              <div className="flex items-center gap-2 text-xs font-mono text-slate-300">
                <FileDiff className="w-4 h-4 text-indigo-400" />
                <span>Original vs Candidate Implementation</span>
              </div>
              <div className="flex items-center gap-2">
                <button
                  type="button"
                  onClick={() => setViewPatchDiff(!viewPatchDiff)}
                  className="px-2.5 py-1 rounded text-[11px] font-mono border border-slate-700 bg-slate-800 text-slate-300 hover:text-white hover:bg-slate-700 transition"
                >
                  {viewPatchDiff ? 'View Side-by-Side' : 'View Unified Patch'}
                </button>
              </div>
            </div>

            {loadingSource ? (
              <div className="h-[420px] flex items-center justify-center text-slate-400 text-sm">
                <Loader2 className="w-5 h-5 animate-spin mr-2 text-indigo-400" />
                Loading original file source...
              </div>
            ) : viewPatchDiff ? (
              <div className="p-4 bg-slate-950 font-mono text-xs text-slate-300 overflow-x-auto max-h-[450px]">
                <pre className="whitespace-pre">{selectedOpt.patch || 'No unified diff patch available'}</pre>
              </div>
            ) : (
              <DiffEditor
                height="450px"
                language="python"
                theme="vs-dark"
                original={originalSource}
                modified={selectedOpt.candidate_code || ''}
                options={{
                  readOnly: true,
                  minimap: { enabled: false },
                  scrollBeyondLastLine: false,
                  fontSize: 12,
                  lineNumbers: 'on',
                  renderSideBySide: true,
                }}
              />
            )}
          </div>
        </div>
      )}
    </div>
  );
};
