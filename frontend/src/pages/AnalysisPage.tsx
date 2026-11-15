import React, { useEffect, useRef, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import {
  AlertCircle,
  ArrowLeft,
  Activity,
  CheckCircle2,
  Clock,
  RefreshCw,
  Terminal,
  TrendingUp,
  Zap,
} from 'lucide-react';
import {
  Bar,
  BarChart,
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import { api } from '../api/client';
import {
  AnalysisRun,
  BottleneckRecord,
  FunctionRecord,
  ProfileResult,
} from '../types';
import { BottleneckExplorer } from '../components/BottleneckExplorer';

const PIPELINE_STAGES = [
  'queued',
  'static',
  'structure',
  'profile',
  'bottleneck',
  'workload',
  'recommend',
  'completed',
];

interface LogEntry {
  timestamp: string;
  stage: string;
  progress: number;
  message: string;
  status: string;
}

const COLORS = ['#6366f1', '#10b981', '#f59e0b', '#ec4899', '#8b5cf6', '#06b6d4', '#f97316'];

export const AnalysisPage: React.FC = () => {
  const { repositoryId, runId } = useParams<{ repositoryId: string; runId: string }>();

  const [run, setRun] = useState<AnalysisRun | null>(null);
  const [profile, setProfile] = useState<ProfileResult | null>(null);
  const [bottlenecks, setBottlenecks] = useState<BottleneckRecord[]>([]);
  const [functions, setFunctions] = useState<FunctionRecord[]>([]);
  const [logs, setLogs] = useState<LogEntry[]>([]);
  const [wsConnected, setWsConnected] = useState<boolean>(false);
  const [isLoading, setIsLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  const socketRef = useRef<WebSocket | null>(null);
  const logEndRef = useRef<HTMLDivElement | null>(null);

  // Auto-scroll logs
  useEffect(() => {
    logEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [logs]);

  // 1. Initial run fetch
  useEffect(() => {
    if (!runId) return;

    const fetchInitial = async () => {
      try {
        setIsLoading(true);
        const data = await api.analysis.getRun(runId);
        setRun(data);
        if (data.status === 'completed') {
          await loadCompletedData(data.repository_id || repositoryId, runId);
        }
      } catch (err: any) {
        setError(err.response?.data?.detail || 'Failed to load analysis run');
      } finally {
        setIsLoading(false);
      }
    };

    fetchInitial();
  }, [runId]);

  const loadCompletedData = async (repoId?: string, targetRunId?: string) => {
    const rId = targetRunId || runId;
    if (!rId) return;
    try {
      const prof = await api.analysis.getProfile(rId);
      setProfile(prof);
    } catch (e) {
      console.warn('Could not load profile result:', e);
    }

    try {
      const bList = await api.bottlenecks.list(rId);
      setBottlenecks(bList);
    } catch (e) {
      console.warn('Could not load bottlenecks:', e);
    }

    const effectiveRepoId = repoId || repositoryId;
    if (effectiveRepoId) {
      try {
        const funcs = await api.repositories.listFunctions(effectiveRepoId);
        setFunctions(funcs);
      } catch (e) {
        console.warn('Could not load functions:', e);
      }
    }
  };

  // 2. WebSocket connection with polling fallback
  useEffect(() => {
    if (!runId) return;
    if (run?.status === 'completed' || run?.status === 'failed') return;

    let pollingInterval: NodeJS.Timeout | null = null;
    let isSubscribed = true;

    const startPollingFallback = () => {
      if (pollingInterval) return;
      console.log('Starting polling fallback for analysis progress...');
      pollingInterval = setInterval(async () => {
        try {
          const updated = await api.analysis.getRun(runId);
          if (!isSubscribed) return;
          setRun(updated);

          setLogs((prev) => [
            ...prev,
            {
              timestamp: new Date().toLocaleTimeString(),
              stage: updated.stage,
              progress: updated.progress,
              message: updated.error || `Polling: Stage ${updated.stage} (${updated.progress}%)`,
              status: updated.status,
            },
          ]);

          if (updated.status === 'completed') {
            if (pollingInterval) clearInterval(pollingInterval);
            await loadCompletedData(updated.repository_id || repositoryId, updated.id);
          } else if (updated.status === 'failed') {
            if (pollingInterval) clearInterval(pollingInterval);
          }
        } catch (pollErr) {
          console.warn('Polling error:', pollErr);
        }
      }, 2000);
    };

    const token = localStorage.getItem('algorevive_token');
    const apiBase = import.meta.env.VITE_API_URL || 'http://localhost:8000';
    const wsProto = apiBase.startsWith('https') ? 'wss:' : 'ws:';
    const host = apiBase.replace(/^https?:\/\//, '');
    const wsUrl = `${wsProto}//${host}/api/v1/ws/jobs/${runId}?token=${token || ''}`;

    try {
      const ws = new WebSocket(wsUrl);
      socketRef.current = ws;

      ws.onopen = () => {
        if (!isSubscribed) return;
        setWsConnected(true);
        console.log('Connected to job progress WebSocket');
      };

      ws.onmessage = async (event) => {
        if (!isSubscribed) return;
        try {
          const data = JSON.parse(event.data);
          if (data.type === 'heartbeat') return;

          setLogs((prev) => [
            ...prev,
            {
              timestamp: new Date().toLocaleTimeString(),
              stage: data.stage || 'running',
              progress: data.progress ?? 0,
              message: data.message || `Stage ${data.stage} at ${data.progress}%`,
              status: data.status || 'running',
            },
          ]);

          setRun((prev) =>
            prev
              ? {
                  ...prev,
                  stage: data.stage || prev.stage,
                  progress: data.progress ?? prev.progress,
                  status: data.status || prev.status,
                }
              : null
          );

          if (data.status === 'completed') {
            ws.close();
            await loadCompletedData(repositoryId, runId);
          }
        } catch (jsonErr) {
          console.warn('Failed to parse WebSocket frame:', jsonErr);
        }
      };

      ws.onerror = () => {
        setWsConnected(false);
        startPollingFallback();
      };

      ws.onclose = () => {
        setWsConnected(false);
        if (run?.status !== 'completed' && run?.status !== 'failed') {
          startPollingFallback();
        }
      };
    } catch (wsErr) {
      console.warn('WebSocket init failed, switching to polling:', wsErr);
      setWsConnected(false);
      startPollingFallback();
    }

    return () => {
      isSubscribed = false;
      if (socketRef.current) {
        socketRef.current.close();
      }
      if (pollingInterval) {
        clearInterval(pollingInterval);
      }
    };
  }, [runId, run?.status]);

  // Build chart datasets
  const entrypointsList = profile ? Object.values(profile.entrypoints) : [];

  // 1. Runtime vs n chart data
  const sizesSet = new Set<number>();
  entrypointsList.forEach((ep) => {
    (ep.measurements || []).forEach((m) => sizesSet.add(m.n));
  });
  const sortedSizes = Array.from(sizesSet).sort((a, b) => a - b);

  const runtimeChartData = sortedSizes.map((n) => {
    const item: Record<string, any> = { n };
    entrypointsList.forEach((ep) => {
      const m = (ep.measurements || []).find((meas) => meas.n === n);
      if (m) {
        item[ep.function] = m.runtime_s;
      }
    });
    return item;
  });

  // 2. Top functions by cumulative time
  const funcAggMap: Record<string, { function: string; cumulative_time: number }> = {};
  entrypointsList.forEach((ep) => {
    (ep.measurements || []).forEach((m) => {
      (m.top_functions || []).forEach((tf) => {
        const key = tf.function;
        if (!funcAggMap[key]) {
          funcAggMap[key] = { function: key, cumulative_time: 0 };
        }
        funcAggMap[key].cumulative_time = Math.max(
          funcAggMap[key].cumulative_time,
          tf.cumulative_time
        );
      });
    });
  });
  const topFuncChartData = Object.values(funcAggMap)
    .sort((a, b) => b.cumulative_time - a.cumulative_time)
    .slice(0, 10);

  // Helper map for static complexity lookup
  const staticMap: Record<string, FunctionRecord> = {};
  functions.forEach((f) => {
    staticMap[f.name] = f;
    staticMap[f.qualified_name] = f;
  });

  const getStageIndex = (stage: string) => {
    const idx = PIPELINE_STAGES.indexOf(stage);
    return idx >= 0 ? idx : 0;
  };

  const currentStageIndex = run ? getStageIndex(run.stage) : 0;

  if (isLoading && !run) {
    return (
      <div className="flex items-center justify-center min-h-[50vh] text-slate-400">
        <RefreshCw className="w-6 h-6 animate-spin mr-3 text-indigo-400" />
        <span>Loading analysis run...</span>
      </div>
    );
  }

  return (
    <div className="p-8 max-w-7xl mx-auto space-y-8">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center space-x-4">
          <Link
            to={repositoryId ? `/repositories/${repositoryId}` : '/projects'}
            className="p-2 bg-slate-800 hover:bg-slate-700 text-slate-300 rounded-lg transition"
          >
            <ArrowLeft className="w-5 h-5" />
          </Link>
          <div>
            <div className="flex items-center space-x-3">
              <h1 className="text-2xl font-bold text-white tracking-tight">Analysis Execution</h1>
              {run && (
                <span
                  className={`px-2.5 py-0.5 rounded-full text-xs font-medium uppercase ${
                    run.status === 'completed'
                      ? 'bg-emerald-500/10 text-emerald-400 border border-emerald-500/20'
                      : run.status === 'failed'
                      ? 'bg-rose-500/10 text-rose-400 border border-rose-500/20'
                      : 'bg-indigo-500/10 text-indigo-400 border border-indigo-500/20 animate-pulse'
                  }`}
                >
                  {run.status}
                </span>
              )}
            </div>
            <p className="text-sm text-slate-400 mt-1">
              Job ID: <code className="font-mono text-xs">{runId}</code>
            </p>
          </div>
        </div>

        <div className="flex items-center space-x-3 text-xs">
          <div className="flex items-center px-3 py-1.5 rounded-lg bg-slate-900 border border-slate-800">
            <span
              className={`w-2 h-2 rounded-full mr-2 ${
                wsConnected ? 'bg-emerald-400 animate-pulse' : 'bg-amber-400'
              }`}
            />
            <span className="text-slate-300">
              {wsConnected ? 'WebSocket Live' : 'Polling Fallback (2s)'}
            </span>
          </div>
        </div>
      </div>

      {error && (
        <div className="p-4 bg-rose-500/10 border border-rose-500/20 rounded-xl text-rose-400 text-sm flex items-center">
          <AlertCircle className="w-5 h-5 mr-3 flex-shrink-0" />
          {error}
        </div>
      )}

      {/* Stage Stepper */}
      <div className="bg-slate-900/60 border border-slate-800 rounded-xl p-6 backdrop-blur-sm shadow-xl space-y-6">
        <div className="flex items-center justify-between">
          <h2 className="text-sm font-semibold uppercase tracking-wider text-slate-300">
            Pipeline Progress
          </h2>
          <span className="text-sm font-mono text-indigo-400">{run?.progress ?? 0}%</span>
        </div>

        {/* Progress Bar */}
        <div className="w-full bg-slate-800 rounded-full h-2 overflow-hidden">
          <div
            className="bg-indigo-500 h-2 rounded-full transition-all duration-500"
            style={{ width: `${run?.progress ?? 0}%` }}
          />
        </div>

        {/* Stepper pills */}
        <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-8 gap-3">
          {PIPELINE_STAGES.map((st, idx) => {
            const isCompleted = run?.status === 'completed' || idx < currentStageIndex;
            const isCurrent = idx === currentStageIndex && run?.status !== 'completed';
            return (
              <div
                key={st}
                className={`p-3 rounded-lg border text-center transition flex flex-col items-center justify-center space-y-1 ${
                  isCompleted
                    ? 'bg-emerald-500/10 border-emerald-500/30 text-emerald-400'
                    : isCurrent
                    ? 'bg-indigo-500/10 border-indigo-500/40 text-indigo-300 ring-1 ring-indigo-500/50'
                    : 'bg-slate-950/40 border-slate-800 text-slate-500'
                }`}
              >
                {isCompleted ? (
                  <CheckCircle2 className="w-4 h-4 text-emerald-400" />
                ) : (
                  <span className="text-xs font-mono font-medium">{idx + 1}</span>
                )}
                <span className="text-xs font-medium capitalize">{st}</span>
              </div>
            );
          })}
        </div>
      </div>

      {/* Live Log Stream */}
      <div className="bg-slate-950 border border-slate-800 rounded-xl overflow-hidden shadow-2xl">
        <div className="flex items-center justify-between px-4 py-3 bg-slate-900 border-b border-slate-800">
          <div className="flex items-center space-x-2 text-slate-300 text-xs font-semibold">
            <Terminal className="w-4 h-4 text-indigo-400" />
            <span>Real-time Execution Log</span>
          </div>
          <span className="text-xs font-mono text-slate-400">{logs.length} messages</span>
        </div>
        <div className="p-4 h-48 overflow-y-auto font-mono text-xs space-y-1.5 text-slate-300 scrollbar-thin">
          {logs.length === 0 ? (
            <div className="text-slate-500 italic">Connecting to progress stream...</div>
          ) : (
            logs.map((log, i) => (
              <div key={i} className="flex items-start space-x-3">
                <span className="text-slate-500 flex-shrink-0">[{log.timestamp}]</span>
                <span className="text-indigo-400 flex-shrink-0 uppercase">[{log.stage}]</span>
                <span
                  className={
                    log.status === 'failed'
                      ? 'text-rose-400'
                      : log.status === 'completed'
                      ? 'text-emerald-400 font-medium'
                      : 'text-slate-300'
                  }
                >
                  {log.message}
                </span>
              </div>
            ))
          )}
          <div ref={logEndRef} />
        </div>
      </div>

      {/* Profile Section (Shown upon completion) */}
      {profile && (
        <div className="space-y-8 animate-fadeIn">
          <div className="flex items-center justify-between border-b border-slate-800 pb-4">
            <div>
              <h2 className="text-xl font-bold text-white flex items-center">
                <Activity className="w-5 h-5 mr-2 text-indigo-400" />
                Runtime Profile Results
              </h2>
              <p className="text-sm text-slate-400">
                Empirical evidence collected inside isolated sandbox execution
              </p>
            </div>
            <div className="flex items-center space-x-4 text-xs font-mono">
              <span className="text-emerald-400 bg-emerald-500/10 px-3 py-1 rounded border border-emerald-500/20">
                {profile.summary.successful_entrypoints} / {profile.summary.total_entrypoints} Entrypoints Passed
              </span>
            </div>
          </div>

          {/* Charts Row */}
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-8">
            {/* Chart 1: Runtime vs n on log scale */}
            <div className="bg-slate-900/60 border border-slate-800 rounded-xl p-6 shadow-xl space-y-4">
              <div className="flex items-center justify-between">
                <div>
                  <h3 className="text-base font-semibold text-white flex items-center">
                    <TrendingUp className="w-4 h-4 mr-2 text-indigo-400" />
                    Runtime vs. Input Size (Log Scale)
                  </h3>
                  <p className="text-xs text-slate-400">Empirical duration (seconds) across sizes n</p>
                </div>
              </div>

              <div className="h-72 w-full">
                <ResponsiveContainer width="100%" height="100%">
                  <LineChart data={runtimeChartData} margin={{ top: 10, right: 20, left: 10, bottom: 10 }}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#334155" />
                    <XAxis dataKey="n" stroke="#94a3b8" />
                    <YAxis
                      scale="log"
                      domain={['auto', 'auto']}
                      stroke="#94a3b8"
                      tickFormatter={(val) => Number(val).toExponential(1)}
                    />
                    <Tooltip
                      contentStyle={{ backgroundColor: '#0f172a', borderColor: '#334155', borderRadius: '8px' }}
                      labelStyle={{ color: '#e2e8f0', fontWeight: 'bold' }}
                    />
                    <Legend wrapperStyle={{ paddingTop: '10px' }} />
                    {entrypointsList.map((ep, idx) => (
                      <Line
                        key={ep.function}
                        type="monotone"
                        dataKey={ep.function}
                        stroke={COLORS[idx % COLORS.length]}
                        strokeWidth={2}
                        dot={{ r: 4 }}
                        activeDot={{ r: 6 }}
                      />
                    ))}
                  </LineChart>
                </ResponsiveContainer>
              </div>
            </div>

            {/* Chart 2: Top functions by cumulative time */}
            <div className="bg-slate-900/60 border border-slate-800 rounded-xl p-6 shadow-xl space-y-4">
              <div className="flex items-center justify-between">
                <div>
                  <h3 className="text-base font-semibold text-white flex items-center">
                    <Clock className="w-4 h-4 mr-2 text-indigo-400" />
                    Top Functions by Cumulative Time
                  </h3>
                  <p className="text-xs text-slate-400">cProfile execution breakdown (seconds)</p>
                </div>
              </div>

              <div className="h-72 w-full">
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={topFuncChartData} margin={{ top: 10, right: 20, left: 10, bottom: 10 }}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#334155" />
                    <XAxis dataKey="function" stroke="#94a3b8" tick={{ fontSize: 11 }} />
                    <YAxis stroke="#94a3b8" tickFormatter={(val) => Number(val).toFixed(4)} />
                    <Tooltip
                      contentStyle={{ backgroundColor: '#0f172a', borderColor: '#334155', borderRadius: '8px' }}
                      labelStyle={{ color: '#e2e8f0', fontWeight: 'bold' }}
                    />
                    <Bar dataKey="cumulative_time" fill="#6366f1" radius={[4, 4, 0, 0]} />
                  </BarChart>
                </ResponsiveContainer>
              </div>
            </div>
          </div>

          {/* Growth Exponent & Complexity Comparison Table */}
          <div className="bg-slate-900/60 border border-slate-800 rounded-xl overflow-hidden shadow-xl">
            <div className="px-6 py-4 border-b border-slate-800 bg-slate-950/60">
              <h3 className="text-base font-semibold text-white flex items-center">
                <Zap className="w-4 h-4 mr-2 text-amber-400" />
                Empirical Growth Exponent vs. Static Complexity
              </h3>
              <p className="text-xs text-slate-400 mt-0.5">
                Comparing log-log runtime growth slope against static AST heuristic estimates
              </p>
            </div>

            <div className="overflow-x-auto">
              <table className="w-full text-left text-sm text-slate-300">
                <thead className="bg-slate-950/80 text-xs uppercase font-semibold text-slate-400 border-b border-slate-800">
                  <tr>
                    <th className="px-6 py-3">Entrypoint Function</th>
                    <th className="px-6 py-3 text-center">Empirical Exponent (α)</th>
                    <th className="px-6 py-3 text-center">Static Complexity</th>
                    <th className="px-6 py-3 text-center">Severity</th>
                    <th className="px-6 py-3 text-center">Peak Memory (KB)</th>
                    <th className="px-6 py-3 text-right">Status</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-800/60 font-mono text-xs">
                  {entrypointsList.map((ep) => {
                    const fnName = ep.function.split(':').pop() || ep.function;
                    const staticMatch = staticMap[fnName] || staticMap[ep.function];
                    const maxMem = (ep.measurements || []).reduce(
                      (max, m) => Math.max(max, m.peak_memory_kb),
                      0
                    );

                    return (
                      <tr key={ep.function} className="hover:bg-slate-800/40 transition">
                        <td className="px-6 py-4 font-semibold text-white">
                          {ep.function}
                        </td>
                        <td className="px-6 py-4 text-center">
                          <span
                            className={`px-2.5 py-1 rounded-full font-bold ${
                              ep.growth_exponent >= 1.5
                                ? 'bg-rose-500/10 text-rose-400 border border-rose-500/30'
                                : ep.growth_exponent >= 1.0
                                ? 'bg-amber-500/10 text-amber-400 border border-amber-500/30'
                                : 'bg-emerald-500/10 text-emerald-400 border border-emerald-500/30'
                            }`}
                          >
                            α = {ep.growth_exponent.toFixed(3)}
                          </span>
                        </td>
                        <td className="px-6 py-4 text-center">
                          <span className="px-2 py-0.5 rounded bg-slate-800 text-slate-200 border border-slate-700">
                            {staticMatch?.complexity_class || 'N/A'}
                          </span>
                        </td>
                        <td className="px-6 py-4 text-center">
                          <span
                            className={`px-2 py-0.5 rounded-full text-xs font-semibold ${
                              staticMatch?.severity === 'CRITICAL'
                                ? 'bg-rose-500/20 text-rose-300 border border-rose-500/40'
                                : staticMatch?.severity === 'HIGH'
                                ? 'bg-orange-500/20 text-orange-300 border border-orange-500/40'
                                : staticMatch?.severity === 'MEDIUM'
                                ? 'bg-amber-500/20 text-amber-300 border border-amber-500/40'
                                : 'bg-emerald-500/20 text-emerald-300 border border-emerald-500/40'
                            }`}
                          >
                            {staticMatch?.severity || 'LOW'}
                          </span>
                        </td>
                        <td className="px-6 py-4 text-center text-slate-400">
                          {maxMem > 0 ? `${maxMem} KB` : '-'}
                        </td>
                        <td className="px-6 py-4 text-right">
                          <span
                            className={`px-2 py-0.5 rounded text-xs ${
                              ep.status === 'success'
                                ? 'text-emerald-400 bg-emerald-500/10'
                                : 'text-rose-400 bg-rose-500/10'
                            }`}
                          >
                            {ep.status}
                          </span>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </div>
        </div>
      )}

      {/* Bottlenecks Section */}
      {run?.status === 'completed' && (
        <div className="space-y-4 pt-6 border-t border-slate-800">
          <div className="flex items-center justify-between">
            <div>
              <h2 className="text-lg font-bold text-white flex items-center gap-2">
                <Zap className="w-5 h-5 text-indigo-400" />
                Ranked Bottlenecks & Evidence
              </h2>
              <p className="text-sm text-slate-400">
                Performance bottlenecks ranked by composite impact score combining static and runtime evidence.
              </p>
            </div>
            <Link
              to={`/analysis-runs/${runId}/bottlenecks`}
              className="text-xs font-semibold text-indigo-400 hover:text-indigo-300"
            >
              Open Full Explorer →
            </Link>
          </div>
          <BottleneckExplorer
            bottlenecks={bottlenecks}
            repositoryId={run.repository_id || repositoryId}
            isStaticOnly={!profile}
          />
        </div>
      )}
    </div>
  );
};
