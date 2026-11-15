import React from 'react';
import { AlertTriangle, ChevronRight, HelpCircle, Layers, Zap } from 'lucide-react';
import { WhyFlaggedNodeData } from '../types';

interface WhyFlaggedTreeProps {
  node: WhyFlaggedNodeData;
  isRoot?: boolean;
}

export const WhyFlaggedTree: React.FC<WhyFlaggedTreeProps> = ({ node, isRoot = true }) => {
  const getMetricIcon = (metric: string) => {
    switch (metric) {
      case 'severity':
        return <AlertTriangle className="w-4 h-4 text-rose-500" />;
      case 'complexity_class':
        return <Layers className="w-4 h-4 text-purple-500" />;
      case 'runtime_pct':
        return <Zap className="w-4 h-4 text-amber-500" />;
      case 'call_count':
        return <ChevronRight className="w-4 h-4 text-blue-500" />;
      default:
        return <HelpCircle className="w-4 h-4 text-slate-400" />;
    }
  };

  return (
    <div className={`space-y-2 ${isRoot ? '' : 'ml-4 pl-3 border-l-2 border-slate-700/50'}`}>
      <div className="flex items-start justify-between gap-2 p-2.5 rounded-lg bg-slate-900/60 border border-slate-800">
        <div className="flex items-start gap-2.5">
          <div className="mt-0.5">{getMetricIcon(node.metric)}</div>
          <div>
            <div className="text-sm font-medium text-slate-200">{node.reason}</div>
            <div className="flex flex-wrap items-center gap-2 mt-1">
              <span className="text-xs font-mono px-2 py-0.5 rounded bg-slate-800 text-slate-300 border border-slate-700">
                {node.metric}: <strong className="text-white">{String(node.value)}</strong>
              </span>
              {node.weight !== null && node.weight !== undefined && (
                <span className="text-xs px-2 py-0.5 rounded bg-indigo-950/70 text-indigo-300 border border-indigo-800/60 font-mono">
                  Formula weight: {Math.round(node.weight * 100)}%
                </span>
              )}
            </div>
          </div>
        </div>
      </div>

      {node.children && node.children.length > 0 && (
        <div className="space-y-2 pt-1">
          {node.children.map((child, idx) => (
            <WhyFlaggedTree key={idx} node={child} isRoot={false} />
          ))}
        </div>
      )}
    </div>
  );
};
