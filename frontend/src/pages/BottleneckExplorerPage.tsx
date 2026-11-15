import React, { useEffect, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { AlertCircle, ArrowLeft, RefreshCw, Zap } from 'lucide-react';
import { api } from '../api/client';
import { AnalysisRun, BottleneckRecord } from '../types';
import { BottleneckExplorer } from '../components/BottleneckExplorer';

export const BottleneckExplorerPage: React.FC = () => {
  const { runId } = useParams<{ runId: string }>();
  const [run, setRun] = useState<AnalysisRun | null>(null);
  const [bottlenecks, setBottlenecks] = useState<BottleneckRecord[]>([]);
  const [isLoading, setIsLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  const fetchData = async () => {
    if (!runId) return;
    try {
      setIsLoading(true);
      setError(null);
      const [runData, bData] = await Promise.all([
        api.analysis.getRun(runId),
        api.bottlenecks.list(runId),
      ]);
      setRun(runData);
      setBottlenecks(bData);
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to load bottlenecks');
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    fetchData();
  }, [runId]);

  const isStaticOnly = !run?.workload_spec && (bottlenecks.length > 0 && bottlenecks[0].evidence?.source === 'static-only');

  return (
    <div className="space-y-6">
      {/* Top Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <Link
            to={`/analysis-runs/${runId}`}
            className="p-2 rounded-lg bg-slate-800 text-slate-400 hover:text-white hover:bg-slate-700 transition"
          >
            <ArrowLeft className="w-5 h-5" />
          </Link>
          <div>
            <h1 className="text-2xl font-bold text-white flex items-center gap-2">
              <Zap className="w-6 h-6 text-indigo-400" />
              Bottleneck Explorer
            </h1>
            <p className="text-sm text-slate-400 font-mono">
              Analysis Run: {runId}
            </p>
          </div>
        </div>

        <button
          onClick={fetchData}
          disabled={isLoading}
          className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-slate-800 text-slate-300 hover:text-white hover:bg-slate-700 text-sm font-medium transition"
        >
          <RefreshCw className={`w-4 h-4 ${isLoading ? 'animate-spin' : ''}`} />
          Refresh
        </button>
      </div>

      {error && (
        <div className="p-4 rounded-xl bg-rose-950/40 border border-rose-800/80 text-rose-300 text-sm flex items-center gap-2">
          <AlertCircle className="w-5 h-5 flex-shrink-0" />
          {error}
        </div>
      )}

      {isLoading ? (
        <div className="p-12 text-center text-slate-400">
          <RefreshCw className="w-6 h-6 animate-spin mx-auto mb-2 text-indigo-400" />
          Loading ranked bottlenecks...
        </div>
      ) : (
        <BottleneckExplorer
          bottlenecks={bottlenecks}
          repositoryId={run?.repository_id}
          isStaticOnly={isStaticOnly}
        />
      )}
    </div>
  );
};

