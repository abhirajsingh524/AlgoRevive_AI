import React, { useState } from 'react';
import { ArrowUpDown, Code2, Cpu, Filter, Flame, RefreshCw } from 'lucide-react';
import { FunctionRecord } from '../types';

interface FunctionsTableProps {
  functions: FunctionRecord[];
  onSelectFunction: (fn: FunctionRecord) => void;
  isLoading?: boolean;
}

type SortField = 'name' | 'complexity_rank' | 'severity' | 'loop_depth' | 'lineno';
type SortOrder = 'asc' | 'desc';

export const FunctionsTable: React.FC<FunctionsTableProps> = ({
  functions,
  onSelectFunction,
  isLoading = false,
}) => {
  const [searchTerm, setSearchTerm] = useState<string>('');
  const [severityFilter, setSeverityFilter] = useState<string>('ALL');
  const [sortField, setSortField] = useState<SortField>('complexity_rank');
  const [sortOrder, setSortOrder] = useState<SortOrder>('desc');

  const handleSort = (field: SortField) => {
    if (sortField === field) {
      setSortOrder(sortOrder === 'asc' ? 'desc' : 'asc');
    } else {
      setSortField(field);
      setSortOrder('desc');
    }
  };

  const severityOrder: Record<string, number> = {
    CRITICAL: 4,
    HIGH: 3,
    MEDIUM: 2,
    LOW: 1,
  };

  const filtered = functions.filter((fn) => {
    const matchesSearch =
      fn.name.toLowerCase().includes(searchTerm.toLowerCase()) ||
      fn.qualified_name.toLowerCase().includes(searchTerm.toLowerCase());
    const matchesSeverity =
      severityFilter === 'ALL' || fn.severity.toUpperCase() === severityFilter;
    return matchesSearch && matchesSeverity;
  });

  const sorted = [...filtered].sort((a, b) => {
    let cmp = 0;
    if (sortField === 'name') {
      cmp = a.name.localeCompare(b.name);
    } else if (sortField === 'complexity_rank') {
      cmp = a.complexity_rank - b.complexity_rank;
    } else if (sortField === 'severity') {
      cmp = (severityOrder[a.severity] || 0) - (severityOrder[b.severity] || 0);
    } else if (sortField === 'loop_depth') {
      cmp = a.loop_depth - b.loop_depth;
    } else if (sortField === 'lineno') {
      cmp = a.lineno - b.lineno;
    }
    return sortOrder === 'asc' ? cmp : -cmp;
  });

  const getSeverityBadge = (severity: string) => {
    switch (severity.toUpperCase()) {
      case 'CRITICAL':
        return 'bg-rose-500/10 text-rose-400 border-rose-500/30';
      case 'HIGH':
        return 'bg-orange-500/10 text-orange-400 border-orange-500/30';
      case 'MEDIUM':
        return 'bg-amber-500/10 text-amber-400 border-amber-500/30';
      case 'LOW':
      default:
        return 'bg-emerald-500/10 text-emerald-400 border-emerald-500/30';
    }
  };

  if (isLoading) {
    return (
      <div className="flex flex-1 items-center justify-center p-12 text-slate-400">
        <RefreshCw className="h-6 w-6 animate-spin text-indigo-500 mr-3" />
        <span>Loading analyzed functions...</span>
      </div>
    );
  }

  return (
    <div className="flex flex-col h-full bg-slate-950 overflow-hidden">
      {/* Table Toolbar */}
      <div className="p-4 border-b border-slate-800 bg-slate-900/40 flex flex-wrap items-center justify-between gap-4">
        <div className="flex items-center gap-3">
          <div className="relative">
            <input
              type="text"
              placeholder="Search functions..."
              value={searchTerm}
              onChange={(e) => setSearchTerm(e.target.value)}
              className="w-64 rounded-lg bg-slate-900 border border-slate-800 px-3 py-1.5 text-xs text-slate-200 placeholder-slate-500 focus:outline-none focus:border-indigo-500"
            />
          </div>

          <div className="flex items-center gap-1.5 text-xs text-slate-400">
            <Filter className="h-3.5 w-3.5 text-slate-500" />
            <span>Severity:</span>
            <select
              value={severityFilter}
              onChange={(e) => setSeverityFilter(e.target.value)}
              className="rounded-lg bg-slate-900 border border-slate-800 px-2 py-1 text-xs text-slate-200 focus:outline-none focus:border-indigo-500"
            >
              <option value="ALL">All Severities</option>
              <option value="CRITICAL">Critical</option>
              <option value="HIGH">High</option>
              <option value="MEDIUM">Medium</option>
              <option value="LOW">Low</option>
            </select>
          </div>
        </div>

        <div className="text-xs text-slate-400">
          Showing <span className="text-slate-200 font-semibold">{sorted.length}</span> of{' '}
          <span className="text-slate-200 font-semibold">{functions.length}</span> functions
        </div>
      </div>

      {/* Main Table */}
      <div className="flex-1 overflow-auto">
        {sorted.length === 0 ? (
          <div className="flex flex-col items-center justify-center h-64 text-slate-500 text-sm">
            <Code2 className="h-10 w-10 text-slate-600 mb-2" />
            <span>No functions found matching filters.</span>
          </div>
        ) : (
          <table className="w-full text-left text-xs">
            <thead className="bg-slate-900/80 sticky top-0 border-b border-slate-800 text-slate-400 z-10">
              <tr>
                <th
                  onClick={() => handleSort('name')}
                  className="py-3 px-4 font-medium cursor-pointer hover:text-slate-200"
                >
                  <div className="flex items-center gap-1">
                    <span>Function</span>
                    <ArrowUpDown className="h-3 w-3" />
                  </div>
                </th>
                <th
                  onClick={() => handleSort('complexity_rank')}
                  className="py-3 px-4 font-medium cursor-pointer hover:text-slate-200"
                >
                  <div className="flex items-center gap-1">
                    <span>Estimated Complexity</span>
                    <ArrowUpDown className="h-3 w-3" />
                  </div>
                </th>
                <th
                  onClick={() => handleSort('severity')}
                  className="py-3 px-4 font-medium cursor-pointer hover:text-slate-200"
                >
                  <div className="flex items-center gap-1">
                    <span>Severity</span>
                    <ArrowUpDown className="h-3 w-3" />
                  </div>
                </th>
                <th
                  onClick={() => handleSort('loop_depth')}
                  className="py-3 px-4 font-medium cursor-pointer hover:text-slate-200"
                >
                  <div className="flex items-center gap-1">
                    <span>Loop Depth</span>
                    <ArrowUpDown className="h-3 w-3" />
                  </div>
                </th>
                <th className="py-3 px-4 font-medium">Patterns Detected</th>
                <th className="py-3 px-4 font-medium text-right">Lines</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-800/60">
              {sorted.map((fn) => {
                const patterns = fn.patterns || [];
                return (
                  <tr
                    key={fn.id}
                    onClick={() => onSelectFunction(fn)}
                    className="hover:bg-slate-900/60 cursor-pointer transition-colors group"
                  >
                    <td className="py-3 px-4">
                      <div className="flex flex-col">
                        <span className="font-mono font-semibold text-slate-200 group-hover:text-indigo-400 transition-colors">
                          {fn.name}
                        </span>
                        <span className="font-mono text-[11px] text-slate-500">
                          {fn.qualified_name}
                        </span>
                      </div>
                    </td>

                    <td className="py-3 px-4">
                      <div className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-[11px] font-mono bg-slate-800 border border-slate-700 text-slate-200">
                        <Cpu className="h-3 w-3 text-indigo-400" />
                        <span>{fn.complexity_class || 'O(1)'}</span>
                      </div>
                    </td>

                    <td className="py-3 px-4">
                      <span
                        className={`inline-flex items-center gap-1 px-2 py-0.5 rounded border text-[11px] font-semibold tracking-wide ${getSeverityBadge(
                          fn.severity
                        )}`}
                      >
                        {fn.severity === 'CRITICAL' && <Flame className="h-3 w-3 text-rose-400" />}
                        <span>{fn.severity}</span>
                      </span>
                    </td>

                    <td className="py-3 px-4 text-slate-300">
                      <div className="flex items-center gap-2">
                        <span>{fn.loop_depth}</span>
                        {fn.has_recursion && (
                          <span className="px-1.5 py-0.2 rounded text-[10px] bg-purple-500/20 text-purple-300 border border-purple-500/30">
                            recursive
                          </span>
                        )}
                      </div>
                    </td>

                    <td className="py-3 px-4">
                      {patterns.length === 0 ? (
                        <span className="text-slate-600 italic">None</span>
                      ) : (
                        <div className="flex flex-wrap gap-1">
                          {patterns.map((p, pIdx) => (
                            <span
                              key={pIdx}
                              title={`Line ${p.line_number}: ${p.matched_snippet}`}
                              className="px-2 py-0.5 rounded-full text-[10px] font-mono bg-indigo-500/10 text-indigo-300 border border-indigo-500/20 cursor-help"
                            >
                              {p.pattern_id}
                            </span>
                          ))}
                        </div>
                      )}
                    </td>

                    <td className="py-3 px-4 text-right font-mono text-slate-500">
                      L{fn.lineno}-{fn.end_lineno}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
};
