import React, { useMemo } from 'react';
import ReactFlow, {
  Background,
  Controls,
  Edge,
  MarkerType,
  Node,
} from 'reactflow';
import 'reactflow/dist/style.css';
import { AffectedFunctionData } from '../types';

interface MiniCallGraphProps {
  bottleneckName: string;
  affectedFunctions: AffectedFunctionData[];
}

export const MiniCallGraph: React.FC<MiniCallGraphProps> = ({
  bottleneckName,
  affectedFunctions,
}) => {
  const { nodes, edges } = useMemo(() => {
    const nodesList: Node[] = [];
    const edgesList: Edge[] = [];

    // Center / Target: Bottleneck function
    const targetId = 'target-bottleneck';
    nodesList.push({
      id: targetId,
      position: { x: 380, y: 120 },
      data: {
        label: (
          <div className="p-2 text-center">
            <div className="text-[10px] font-bold uppercase tracking-wider text-rose-400">
              Target Bottleneck
            </div>
            <div className="text-xs font-mono font-bold text-white truncate max-w-[180px]">
              {bottleneckName}
            </div>
          </div>
        ),
      },
      style: {
        background: '#1e1b4b',
        border: '2px solid #f43f5e',
        borderRadius: '8px',
        color: '#fff',
        width: 190,
      },
    });

    if (!affectedFunctions || affectedFunctions.length === 0) {
      return { nodes: nodesList, edges: edgesList };
    }

    // Group callers by depth
    const callersByDepth: Record<number, AffectedFunctionData[]> = {};
    affectedFunctions.forEach((af) => {
      const d = af.depth || 1;
      if (!callersByDepth[d]) callersByDepth[d] = [];
      callersByDepth[d].push(af);
    });

    Object.keys(callersByDepth).forEach((depthStr) => {
      const depth = parseInt(depthStr, 10);
      const callers = callersByDepth[depth];
      const xPos = Math.max(20, 380 - depth * 180);

      callers.forEach((caller, idx) => {
        const callerId = `caller-${caller.function_id || idx}`;
        const yPos = 40 + idx * 90;

        nodesList.push({
          id: callerId,
          position: { x: xPos, y: yPos },
          data: {
            label: (
              <div className="p-1.5 text-left">
                <div className="flex items-center justify-between gap-1 text-[9px]">
                  <span className="text-slate-400 font-mono">Depth {depth}</span>
                  {caller.covered_by_workload && (
                    <span className="px-1 py-0.2 rounded bg-emerald-950 text-emerald-400 border border-emerald-800 text-[8px]">
                      Workload Covered
                    </span>
                  )}
                </div>
                <div className="text-xs font-mono font-semibold text-slate-200 truncate max-w-[150px]">
                  {caller.name}
                </div>
                <div className="text-[9px] text-slate-400 truncate max-w-[150px]">
                  {caller.file_path}
                </div>
              </div>
            ),
          },
          style: {
            background: '#0f172a',
            border: caller.covered_by_workload ? '1.5px solid #10b981' : '1px solid #475569',
            borderRadius: '6px',
            color: '#fff',
            width: 160,
          },
        });

        // Edge from direct caller (depth 1) to bottleneck, or higher depth to lower depth
        const targetEdgeId = depth === 1 ? targetId : `caller-${callersByDepth[depth - 1]?.[0]?.function_id || targetId}`;
        edgesList.push({
          id: `edge-${callerId}-${targetEdgeId}`,
          source: callerId,
          target: targetEdgeId,
          animated: true,
          style: { stroke: caller.covered_by_workload ? '#10b981' : '#64748b', strokeWidth: 1.5 },
          markerEnd: {
            type: MarkerType.ArrowClosed,
            color: caller.covered_by_workload ? '#10b981' : '#64748b',
          },
        });
      });
    });

    return { nodes: nodesList, edges: edgesList };
  }, [bottleneckName, affectedFunctions]);

  return (
    <div className="h-[280px] w-full rounded-lg border border-slate-800 bg-slate-950/70 overflow-hidden relative">
      {(!affectedFunctions || affectedFunctions.length === 0) && (
        <div className="absolute top-2 left-2 z-10 px-2 py-1 rounded bg-slate-900/90 border border-slate-800 text-xs text-slate-400">
          No upstream callers detected (function is a top-level entrypoint)
        </div>
      )}
      <ReactFlow
        nodes={nodes}
        edges={edges}
        fitView
        nodesDraggable={false}
        nodesConnectable={false}
        attributionPosition="bottom-right"
      >
        <Background color="#334155" gap={16} />
        <Controls showInteractive={false} />
      </ReactFlow>
    </div>
  );
};

