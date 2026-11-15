import React, { useMemo, useState } from 'react';
import {
  AlertTriangle,
  ChevronRight,
  Filter,
  Search,
} from 'lucide-react';
import { BottleneckRecord } from '../types';
import { BottleneckDetailDrawer } from './BottleneckDetailDrawer';

interface BottleneckExplorerProps {
  bottlenecks: BottleneckRecord[];
  repositoryId?: string;
  isStaticOnly?: boolean;
}

export const BottleneckExplorer: React.FC<BottleneckExplorerProps> = ({
  bottlenecks,
  repositoryId,
  isStaticOnly = false,
}) => {
  const [selectedBottleneck, setSelectedBottleneck] = useState<BottleneckRecord | null>(null);
  const [severityFilter, setSeverityFilter] = useState<string>('ALL');
  const [searchQuery, setSearchQuery] = useState<string>('');

  const filteredBottlenecks = useMemo(() => {
    return bottlenecks.filter((b) => {
      if (severityFilter !== 'ALL' && b.severity.toUpperCase() !== severityFilter) {
        return false;
      }
      if (searchQuery) {
        const q = searchQuery.toLowerCase();
        const fnName = b.function?.name?.toLowerCase() || '';
        const fnQual = b.function?.qualified_name?.toLowerCase() || '';
        return fnName.includes(q) || fnQual.includes(q);
      }
      return true;
    });
  }, [bottlenecks, severityFilter, searchQuery]);

  const getSeverityChip = (severity: string) => {
    switch (severity.toUpperCase()) {
      case 'CRITICAL':
        return (
          <span className="px-2.5 py-1 rounded-full text-xs font-bold uppercase tracking-wider bg-rose-950/80 text-rose-300 border border-rose-800">
            Critical
          </span>
        );
      case 'HIGH':
        return (
          <span className="px-2.5 py-1 rounded-full text-xs font-bold uppercase tracking-wider bg-amber-950/80 text-amber-300 border border-amber-800">
            High
          </span>
        );
      case 'MEDIUM':
        return (
          <span className="px-2.5 py-1 rounded-full text-xs font-bold uppercase tracking-wider bg-yellow-950/80 text-yellow-300 border border-yellow-800">
            Medium
          </span>
        );
      default:
        return (
          <span className="px-2.5 py-1 rounded-full text-xs font-bold uppercase tracking-wider bg-emerald-950/80 text-emerald-300 border border-emerald-800">
            Low
          </span>
        );
    }
  };

  return (
    <div className="space-y-4">
      {/* Controls & Badges */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 p-4 rounded-xl bg-slate-900/60 border border-slate-800">
        <div className="flex items-center gap-2">
          <div className="relative">
            <Search className="w-4 h-4 text-slate-400 absolute left-3 top-1/2 -translate-y-1/2" />
            <input
              type="text"
              placeholder="Filter by function name..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="pl-9 pr-3 py-1.5 rounded-lg bg-slate-950 border border-slate-800 text-sm text-slate-200 placeholder-slate-500 focus:outline-none focus:border-indigo-500"
            />
          </div>

          <div className="flex items-center gap-1.5">
            <Filter className="w-4 h-4 text-slate-400" />
            <select
              value={severityFilter}
              onChange={(e) => setSeverityFilter(e.target.value)}
              className="py-1.5 px-3 rounded-lg bg-slate-950 border border-slate-800 text-sm text-slate-200 focus:outline-none focus:border-indigo-500"
            >
              <option value="ALL">All Severities</option>
              <option value="CRITICAL">Critical</option>
              <option value="HIGH">High</option>
              <option value="MEDIUM">Medium</option>
              <option value="LOW">Low</option>
            </select>
          </div>
        </div>

        <div className="flex items-center gap-2">
          {isStaticOnly && (
            <span className="px-2.5 py-1 rounded-full text-xs font-bold uppercase tracking-wider bg-slate-800 text-amber-300 border border-amber-600/40 flex items-center gap-1">
              <AlertTriangle className="w-3.5 h-3.5" />
              Static-Only (No Profile)
            </span>
          )}
          <span className="text-xs text-slate-400 font-mono">
            {filteredBottlenecks.length} of {bottlenecks.length} candidate bottlenecks
          </span>
        </div>
      </div>

      {/* Table */}
      <div className="rounded-xl border border-slate-800 bg-slate-900/40 overflow-hidden">
        <table className="w-full text-left text-sm">
          <thead className="bg-slate-950/80 text-slate-400 text-xs uppercase tracking-wider border-b border-slate-800 font-mono">
            <tr>
              <th className="py-3 px-4">Impact</th>
              <th className="py-3 px-4">Severity</th>
              <th className="py-3 px-4">Function</th>
              <th className="py-3 px-4">Complexity</th>
              <th className="py-3 px-4">Runtime Contribution</th>
              <th className="py-3 px-4">Calls</th>
              <th className="py-3 px-4">Peak Memory</th>
              <th className="py-3 px-4 text-right">Actions</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-800/60">
            {filteredBottlenecks.length === 0 ? (
              <tr>
                <td colSpan={8} className="py-8 text-center text-slate-400 text-sm">
                  No bottlenecks match the selected filter.
                </td>
              </tr>
            ) : (
              filteredBottlenecks.map((b) => {
                const runtimePct = Math.round(b.runtime_pct * 100);
                const isSelected = selectedBottleneck?.id === b.id;

                return (
                  <tr
                    key={b.id}
                    onClick={() => setSelectedBottleneck(b)}
                    className={`cursor-pointer transition ${
                      isSelected
                        ? 'bg-indigo-950/40 border-l-2 border-indigo-500'
                        : 'hover:bg-slate-800/40'
                    }`}
                  >
                    <td className="py-3 px-4 font-mono font-bold text-white">
                      {b.impact_score.toFixed(3)}
                    </td>
                    <td className="py-3 px-4">{getSeverityChip(b.severity)}</td>
                    <td className="py-3 px-4">
                      <div className="font-mono font-semibold text-slate-200">
                        {b.function?.name || 'anonymous'}
                      </div>
                      <div className="text-xs text-slate-500 font-mono truncate max-w-xs">
                        {b.function?.qualified_name}
                      </div>
                    </td>
                    <td className="py-3 px-4">
                      <span className="px-2 py-0.5 rounded text-xs font-mono bg-slate-800 text-slate-300 border border-slate-700">
                        {b.function?.complexity_class || 'O(1)'}
                      </span>
                    </td>
                    <td className="py-3 px-4 w-48">
                      {isStaticOnly ? (
                        <span className="text-xs text-slate-500 italic">N/A (static)</span>
                      ) : (
                        <div className="space-y-1">
                          <div className="flex items-center justify-between text-xs font-mono">
                            <span className="text-slate-300 font-bold">{runtimePct}%</span>
                            <span className="text-slate-500 text-[10px]">of total</span>
                          </div>
                          <div className="w-full h-2 rounded-full bg-slate-800 overflow-hidden">
                            <div
                              className={`h-full rounded-full transition-all duration-300 ${
                                runtimePct > 70
                                  ? 'bg-rose-500'
                                  : runtimePct > 30
                                  ? 'bg-amber-500'
                                  : 'bg-emerald-500'
                              }`}
                              style={{ width: `${Math.min(100, Math.max(2, runtimePct))}%` }}
                            />
                          </div>
                        </div>
                      )}
                    </td>
                    <td className="py-3 px-4 font-mono text-slate-300">
                      {isStaticOnly ? '—' : b.call_count.toLocaleString()}
                    </td>
                    <td className="py-3 px-4 font-mono text-slate-300">
                      {isStaticOnly ? '—' : `${b.memory_peak_kb.toFixed(1)} KB`}
                    </td>
                    <td className="py-3 px-4 text-right">
                      <button
                        onClick={(e) => {
                          e.stopPropagation();
                          setSelectedBottleneck(b);
                        }}
                        className="inline-flex items-center gap-1 px-2.5 py-1 rounded-lg text-xs font-medium text-indigo-400 bg-indigo-950/60 border border-indigo-800/60 hover:bg-indigo-900/60 transition"
                      >
                        Inspect
                        <ChevronRight className="w-3.5 h-3.5" />
                      </button>
                    </td>
                  </tr>
                );
              })
            )}
          </tbody>
        </table>
      </div>

      {/* Drawer */}
      {selectedBottleneck && (
        <BottleneckDetailDrawer
          bottleneck={selectedBottleneck}
          repositoryId={repositoryId}
          onClose={() => setSelectedBottleneck(null)}
        />
      )}
    </div>
  );
};
