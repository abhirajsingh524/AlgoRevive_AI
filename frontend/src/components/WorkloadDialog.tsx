import React, { useEffect, useState } from 'react';
import Editor from '@monaco-editor/react';
import { AlertCircle, CheckCircle2, FileCode, Play, Sparkles, X } from 'lucide-react';
import { api } from '../api/client';
import { FileRecord } from '../types';

interface WorkloadDialogProps {
  isOpen: boolean;
  onClose: () => void;
  onSubmit: (workloadSpec: Record<string, any>) => void;
  repositoryId: string;
  files: FileRecord[];
  isSubmitting?: boolean;
}

const SAMPLE_SPEC = {
  sizes: [10, 50, 100],
  entrypoints: [
    {
      function: "demo.operations:slow_membership",
      args: [
        { kind: "records", size_factor: 1.0, fixed: null, options: {} },
        { kind: "int_list", size_factor: 0.5, fixed: null, options: {} }
      ]
    },
    {
      function: "demo.operations:nested_match",
      args: [
        { kind: "two_record_lists", size_factor: 1.0, fixed: null, options: {} }
      ]
    },
    {
      function: "demo.operations:fib",
      args: [
        { kind: "int", size_factor: 0.2, fixed: null, options: { max: 24 } }
      ]
    },
    {
      function: "demo.operations:efficient_total",
      args: [
        { kind: "int_list", size_factor: 1.0, fixed: null, options: {} }
      ]
    }
  ],
  operation_mix: { lookup: 0.9, insert: 0.05, delete: 0.05 },
  memory_constraint: "low",
  latency_target_ms: null,
  seed: 42
};

export const WorkloadDialog: React.FC<WorkloadDialogProps> = ({
  isOpen,
  onClose,
  onSubmit,
  repositoryId,
  files,
  isSubmitting = false,
}) => {
  const [specText, setSpecText] = useState<string>(JSON.stringify(SAMPLE_SPEC, null, 2));
  const [validationError, setValidationError] = useState<string | null>(null);
  const [detectedSpecFile, setDetectedSpecFile] = useState<string | null>(null);
  const [isLoadingFile, setIsLoadingFile] = useState<boolean>(false);

  // Auto-detect repo-root spec on mount or open
  useEffect(() => {
    if (!isOpen) return;

    const autoDetect = async () => {
      const match = files.find((f) => {
        const clean = f.path.replace(/^[./\\]+/, '');
        return clean === 'algorevive.workload.json' || clean === 'workload.json';
      });

      if (match) {
        setDetectedSpecFile(match.path);
        try {
          setIsLoadingFile(true);
          const content = await api.repositories.getFileContent(repositoryId, match.id);
          if (content?.content) {
            // Test parse
            JSON.parse(content.content);
            setSpecText(content.content);
            setValidationError(null);
          }
        } catch (e) {
          console.warn('Could not load auto-detected workload spec:', e);
        } finally {
          setIsLoadingFile(false);
        }
      } else {
        setDetectedSpecFile(null);
      }
    };

    autoDetect();
  }, [isOpen, repositoryId, files]);

  if (!isOpen) return null;

  const validateSpec = (text: string): Record<string, any> | null => {
    try {
      const parsed = JSON.parse(text);
      if (!parsed || typeof parsed !== 'object') {
        setValidationError('Workload spec must be a valid JSON object');
        return null;
      }
      if (!Array.isArray(parsed.sizes) || parsed.sizes.length === 0 || parsed.sizes.length > 8) {
        setValidationError('Field "sizes" must be an array of 1 to 8 integers');
        return null;
      }
      for (const s of parsed.sizes) {
        if (typeof s !== 'number' || s <= 0 || s > 2000000) {
          setValidationError(`Invalid size: ${s}. Must be positive integer <= 2,000,000`);
          return null;
        }
      }
      if (!Array.isArray(parsed.entrypoints) || parsed.entrypoints.length === 0 || parsed.entrypoints.length > 10) {
        setValidationError('Field "entrypoints" must be an array of 1 to 10 entrypoints');
        return null;
      }
      for (const ep of parsed.entrypoints) {
        if (!ep.function || !ep.function.includes(':')) {
          setValidationError(`Invalid entrypoint: "${ep.function}". Must be formatted as "module:function"`);
          return null;
        }
      }
      setValidationError(null);
      return parsed;
    } catch (e: any) {
      setValidationError(`Invalid JSON syntax: ${e.message}`);
      return null;
    }
  };

  const handleEditorChange = (value: string | undefined) => {
    const text = value || '';
    setSpecText(text);
    validateSpec(text);
  };

  const handleLoadSample = () => {
    const sample = JSON.stringify(SAMPLE_SPEC, null, 2);
    setSpecText(sample);
    setValidationError(null);
  };

  const handleSubmit = () => {
    const valid = validateSpec(specText);
    if (!valid) return;
    onSubmit(valid);
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm p-4">
      <div className="bg-slate-900 border border-slate-700 rounded-xl shadow-2xl w-full max-w-4xl flex flex-col max-h-[90vh] overflow-hidden">
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-slate-800 bg-slate-950/60">
          <div className="flex items-center space-x-3">
            <div className="p-2 bg-indigo-500/10 text-indigo-400 rounded-lg border border-indigo-500/20">
              <FileCode className="w-5 h-5" />
            </div>
            <div>
              <h3 className="text-lg font-semibold text-white">Run Analysis & Workload Spec</h3>
              <p className="text-xs text-slate-400">
                Configure runtime profiling workload and entrypoint benchmarks
              </p>
            </div>
          </div>
          <button
            onClick={onClose}
            className="text-slate-400 hover:text-white p-1 rounded-lg hover:bg-slate-800 transition"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Toolbar */}
        <div className="flex items-center justify-between px-6 py-2.5 bg-slate-800/40 border-b border-slate-800 text-xs">
          <div className="flex items-center space-x-2">
            {detectedSpecFile ? (
              <span className="flex items-center text-emerald-400 bg-emerald-500/10 px-2.5 py-1 rounded border border-emerald-500/20">
                <CheckCircle2 className="w-3.5 h-3.5 mr-1.5" />
                Auto-detected: <code className="ml-1 font-mono">{detectedSpecFile}</code>
              </span>
            ) : (
              <span className="text-slate-400">No repo-root spec found (using default)</span>
            )}
            {isLoadingFile && <span className="text-indigo-400 animate-pulse">Loading file...</span>}
          </div>
          <button
            type="button"
            onClick={handleLoadSample}
            className="flex items-center text-indigo-400 hover:text-indigo-300 bg-indigo-500/10 hover:bg-indigo-500/20 px-2.5 py-1 rounded border border-indigo-500/20 transition"
          >
            <Sparkles className="w-3.5 h-3.5 mr-1.5" />
            Load Sample Template
          </button>
        </div>

        {/* Monaco Editor */}
        <div className="flex-1 min-h-[350px] relative bg-slate-950">
          <Editor
            height="100%"
            defaultLanguage="json"
            theme="vs-dark"
            value={specText}
            onChange={handleEditorChange}
            options={{
              minimap: { enabled: false },
              fontSize: 13,
              scrollBeyondLastLine: false,
              wordWrap: 'on',
              formatOnPaste: true,
              automaticLayout: true,
            }}
          />
        </div>

        {/* Validation error display */}
        {validationError && (
          <div className="px-6 py-2 bg-rose-500/10 border-t border-rose-500/20 text-rose-400 text-xs flex items-center">
            <AlertCircle className="w-4 h-4 mr-2 flex-shrink-0" />
            <span>{validationError}</span>
          </div>
        )}

        {/* Footer */}
        <div className="flex items-center justify-between px-6 py-4 border-t border-slate-800 bg-slate-950/60">
          <button
            type="button"
            onClick={onClose}
            className="px-4 py-2 text-sm text-slate-300 hover:text-white hover:bg-slate-800 rounded-lg transition"
          >
            Cancel
          </button>
          <button
            type="button"
            onClick={handleSubmit}
            disabled={isSubmitting || !!validationError}
            className="flex items-center px-5 py-2 text-sm font-medium text-white bg-indigo-600 hover:bg-indigo-500 disabled:opacity-50 disabled:cursor-not-allowed rounded-lg shadow-lg shadow-indigo-600/30 transition"
          >
            <Play className="w-4 h-4 mr-2 fill-current" />
            {isSubmitting ? 'Starting Run...' : 'Launch Analysis Pipeline'}
          </button>
        </div>
      </div>
    </div>
  );
};
