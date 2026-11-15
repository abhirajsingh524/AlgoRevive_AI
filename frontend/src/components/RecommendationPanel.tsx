import React from 'react';
import {
  ArrowRight,
  Bot,
  CheckCircle2,
  Cpu,
  Layers,
  Sparkles,
  TrendingUp,
} from 'lucide-react';
import {
  Bar,
  BarChart,
  Cell,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import { BottleneckRecord, Recommendation } from '../types';

interface RecommendationPanelProps {
  bottleneck: BottleneckRecord;
  recommendation?: Recommendation | null;
  loading?: boolean;
}

export const RecommendationPanel: React.FC<RecommendationPanelProps> = ({
  bottleneck,
  recommendation,
  loading = false,
}) => {
  // Try prop first, then bottleneck.recommendation, then evidence.recommendation
  const rec: Recommendation | undefined =
    recommendation ||
    bottleneck.recommendation ||
    bottleneck.evidence?.recommendation;

  if (loading) {
    return (
      <div className="p-8 text-center space-y-3">
        <div className="w-8 h-8 border-2 border-indigo-500 border-t-transparent rounded-full animate-spin mx-auto" />
        <div className="text-sm text-slate-400">Loading ML recommendation...</div>
      </div>
    );
  }

  if (!rec) {
    return (
      <div className="p-6 rounded-xl bg-slate-950/60 border border-slate-800 text-center space-y-2">
        <Sparkles className="w-8 h-8 text-slate-500 mx-auto" />
        <div className="text-sm font-semibold text-slate-300">
          No Recommendation Available
        </div>
        <div className="text-xs text-slate-500 max-w-sm mx-auto">
          Run analysis with a workload specification to generate ML and rule-based optimization recommendations.
        </div>
      </div>
    );
  }

  // Calculate confidence percentage
  const confidencePct = Math.round(Math.min(1.0, Math.max(0.0, rec.confidence)) * 100);
  const strokeDash = `${confidencePct}, 100`;

  // Prepare chart data for Recharts (horizontal bars)
  const importanceItems = rec.feature_importance || [];
  const chartData = importanceItems.slice(0, 7).map((item) => ({
    name: item.display_name,
    rawName: item.feature,
    importance: Math.round(item.importance * 1000) / 10, // percentage e.g. 34.5%
    formattedValue: item.formatted_value,
  }));

  const isML = rec.source === 'ml';

  return (
    <div className="space-y-5 animate-in fade-in duration-200" data-testid="recommendation-panel">
      {/* 1. Header Card: Current -> Recommended & Source Badge */}
      <div className="p-5 rounded-xl bg-gradient-to-br from-slate-900 to-slate-950 border border-slate-800 shadow-lg space-y-4">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <span className="text-xs font-mono uppercase tracking-wider text-slate-400">
              Algorithm Recommendation
            </span>
            <span
              className={`px-2.5 py-0.5 rounded-full text-xs font-bold uppercase tracking-wider flex items-center gap-1 border ${
                isML
                  ? 'bg-purple-950/80 text-purple-300 border-purple-800'
                  : 'bg-cyan-950/80 text-cyan-300 border-cyan-800'
              }`}
              data-testid="recommendation-source-badge"
            >
              {isML ? <Bot className="w-3 h-3" /> : <Sparkles className="w-3 h-3" />}
              Source: {rec.source.toUpperCase()}
            </span>
          </div>

          {/* Expected complexity pill */}
          {rec.expected_complexity && (
            <span className="px-3 py-1 rounded-lg text-xs font-mono font-semibold bg-indigo-950/60 text-indigo-300 border border-indigo-800/60 flex items-center gap-1.5">
              <TrendingUp className="w-3.5 h-3.5 text-indigo-400" />
              {rec.expected_complexity}
            </span>
          )}
        </div>

        {/* Transition Arrow */}
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 p-4 rounded-lg bg-slate-950/80 border border-slate-800/80">
          <div className="flex-1">
            <div className="text-[10px] font-mono text-slate-500 uppercase">Current Implementation</div>
            <div className="text-sm font-mono text-slate-300 font-semibold truncate mt-0.5">
              {rec.current_algorithm}
            </div>
          </div>

          <div className="flex items-center justify-center p-2 rounded-full bg-indigo-950/40 text-indigo-400 border border-indigo-800/40 shrink-0">
            <ArrowRight className="w-5 h-5" />
          </div>

          <div className="flex-1 sm:text-right">
            <div className="text-[10px] font-mono text-emerald-400 uppercase font-semibold">Recommended</div>
            <div className="text-base font-mono text-emerald-300 font-bold truncate mt-0.5">
              {rec.recommended_algorithm}
            </div>
          </div>
        </div>

        {/* Confidence Ring & Alternatives */}
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 pt-1">
          {/* Circular Confidence Ring */}
          <div className="p-3 rounded-lg bg-slate-950/40 border border-slate-850 flex items-center gap-3">
            <div className="relative w-12 h-12 shrink-0">
              <svg className="w-12 h-12 -rotate-90" viewBox="0 0 36 36">
                <path
                  className="text-slate-800"
                  strokeWidth="3.2"
                  stroke="currentColor"
                  fill="none"
                  d="M18 2.0845 a 15.9155 15.9155 0 0 1 0 31.831 a 15.9155 15.9155 0 0 1 0 -31.831"
                />
                <path
                  className={
                    confidencePct >= 70
                      ? 'text-emerald-400'
                      : confidencePct >= 50
                      ? 'text-amber-400'
                      : 'text-rose-400'
                  }
                  strokeDasharray={strokeDash}
                  strokeWidth="3.2"
                  strokeLinecap="round"
                  stroke="currentColor"
                  fill="none"
                  d="M18 2.0845 a 15.9155 15.9155 0 0 1 0 31.831 a 15.9155 15.9155 0 0 1 0 -31.831"
                />
              </svg>
              <div className="absolute inset-0 flex items-center justify-center text-xs font-mono font-bold text-white">
                {confidencePct}%
              </div>
            </div>
            <div>
              <div className="text-xs font-semibold text-slate-200">Confidence</div>
              <div className="text-[11px] text-slate-400">
                {confidencePct >= 70 ? 'High certainty' : confidencePct >= 50 ? 'Moderate' : 'Low certainty'}
              </div>
            </div>
          </div>

          {/* Alternatives */}
          <div className="sm:col-span-2 p-3 rounded-lg bg-slate-950/40 border border-slate-850 space-y-1.5">
            <div className="text-[11px] font-mono uppercase text-slate-400 flex items-center gap-1">
              <Layers className="w-3.5 h-3.5 text-slate-400" />
              Alternative Candidates
            </div>
            <div className="flex flex-wrap gap-1.5">
              {rec.alternatives && rec.alternatives.length > 0 ? (
                rec.alternatives.map((alt) => (
                  <span
                    key={alt}
                    className="px-2 py-0.5 rounded text-xs font-mono bg-slate-800 text-slate-300 border border-slate-700"
                  >
                    {alt}
                  </span>
                ))
              ) : (
                <span className="text-xs text-slate-500 font-mono">None</span>
              )}
            </div>
          </div>
        </div>
      </div>

      {/* 2. Plain-English Reason Sentence */}
      <div className="p-4 rounded-xl bg-slate-900/80 border border-slate-800 space-y-1.5">
        <div className="text-xs font-mono uppercase tracking-wider text-slate-400 flex items-center gap-1.5">
          <CheckCircle2 className="w-3.5 h-3.5 text-emerald-400" />
          Recommendation Explanation
        </div>
        <p className="text-sm text-slate-200 leading-relaxed font-sans">
          {rec.reason}
        </p>
      </div>

      {/* 3. Data Structure Recommendation Card */}
      {rec.data_structure && (
        <div className="p-4 rounded-xl bg-slate-900/60 border border-slate-800 space-y-2">
          <div className="text-xs font-mono uppercase tracking-wider text-slate-400 flex items-center gap-1.5">
            <Cpu className="w-3.5 h-3.5 text-indigo-400" />
            Data Structure Optimization
          </div>
          <div className="flex items-center gap-2 text-sm font-mono">
            <span className="px-2 py-1 rounded bg-slate-950 text-slate-300 border border-slate-800">
              {rec.data_structure.current_structure}
            </span>
            <ArrowRight className="w-4 h-4 text-slate-500" />
            <span className="px-2 py-1 rounded bg-emerald-950/80 text-emerald-300 border border-emerald-800 font-semibold">
              {rec.data_structure.recommended_structure}
            </span>
          </div>
          <div className="text-xs text-slate-400">
            {rec.data_structure.workload_reason}
          </div>
        </div>
      )}

      {/* 4. Horizontal Recharts Bar Chart: Feature Importance */}
      {chartData.length > 0 && (
        <div className="p-5 rounded-xl bg-slate-900/60 border border-slate-800 space-y-3">
          <div className="flex items-center justify-between">
            <div className="text-xs font-mono uppercase tracking-wider text-slate-400">
              Feature Importance Driving Recommendation
            </div>
            <span className="text-[10px] text-slate-500 font-mono">
              Sum ≈ 100%
            </span>
          </div>

          <div className="h-64 w-full min-w-0 min-h-[250px]">
            <ResponsiveContainer width="100%" height="100%" minWidth={200} minHeight={200}>
              <BarChart
                data={chartData}
                layout="vertical"
                margin={{ top: 5, right: 30, left: 20, bottom: 5 }}
              >
                <XAxis
                  type="number"
                  tick={{ fill: '#94a3b8', fontSize: 11 }}
                  tickFormatter={(val) => `${val}%`}
                />
                <YAxis
                  dataKey="name"
                  type="category"
                  width={140}
                  tick={{ fill: '#cbd5e1', fontSize: 11 }}
                />
                <Tooltip
                  content={({ active, payload }) => {
                    if (active && payload && payload.length) {
                      const data = payload[0].payload;
                      return (
                        <div className="p-2.5 rounded-lg bg-slate-950 border border-slate-700 shadow-xl text-xs space-y-1">
                          <div className="font-bold text-white">{data.name}</div>
                          <div className="text-indigo-300 font-mono">
                            Importance: {data.importance}%
                          </div>
                          <div className="text-slate-400 font-mono">
                            Actual Value: {data.formattedValue}
                          </div>
                        </div>
                      );
                    }
                    return null;
                  }}
                />
                <Bar dataKey="importance" radius={[0, 4, 4, 0]}>
                  {chartData.map((_, index) => (
                    <Cell
                      key={`cell-${index}`}
                      fill={index === 0 ? '#818cf8' : index === 1 ? '#6366f1' : '#4f46e5'}
                    />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>
      )}
    </div>
  );
};
