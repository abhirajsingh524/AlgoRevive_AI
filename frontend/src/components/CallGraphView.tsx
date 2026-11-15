import React, { useMemo } from 'react';
import ReactFlow, {
  Background,
  Controls,
  Edge,
  MiniMap,
  Node,
} from 'reactflow';
import 'reactflow/dist/style.css';
import { CallGraphData, CallGraphNode } from '../types';
import { Network } from 'lucide-react';

interface CallGraphViewProps {
  data: CallGraphData | null;
  onSelectNode?: (nodeId: string) => void;
  isLoading?: boolean;
}

const getSeverityColor = (severity: string): { border: string; bg: string; text: string } => {
  switch (severity?.toUpperCase()) {
    case 'CRITICAL':
      return { border: '#f43f5e', bg: 'rgba(244, 63, 94, 0.1)', text: '#fb7185' };
    case 'HIGH':
      return { border: '#f97316', bg: 'rgba(249, 115, 22, 0.1)', text: '#fb923c' };
    case 'MEDIUM':
      return { border: '#eab308', bg: 'rgba(234, 179, 8, 0.1)', text: '#fde047' };
    case 'LOW':
    default:
      return { border: '#10b981', bg: 'rgba(16, 185, 129, 0.1)', text: '#34d399' };
  }
};

/**
 * Self-written layered layout algorithm.
 * Groups nodes into topological rank layers and assigns 2D positions.
 */
function computeLayeredLayout(
  nodes: CallGraphNode[],
  edges: { source: string; target: string }[]
): { x: number; y: number; id: string }[] {
  if (nodes.length === 0) return [];

  const inDegree: Record<string, number> = {};
  const children: Record<string, string[]> = {};

  nodes.forEach((n) => {
    inDegree[n.id] = 0;
    children[n.id] = [];
  });

  edges.forEach((e) => {
    // Ignore self-loops for layer ranking
    if (e.source !== e.target && children[e.source] && inDegree[e.target] !== undefined) {
      children[e.source].push(e.target);
      inDegree[e.target] = (inDegree[e.target] || 0) + 1;
    }
  });

  // Layer assignment
  const layerMap: Record<string, number> = {};
  const queue: string[] = [];

  // Start with nodes having inDegree == 0
  nodes.forEach((n) => {
    if (inDegree[n.id] === 0) {
      layerMap[n.id] = 0;
      queue.push(n.id);
    }
  });

  // If no node has in-degree 0 (cyclic), pick the one with lowest in-degree
  if (queue.length === 0 && nodes.length > 0) {
    const sortedByInDegree = [...nodes].sort((a, b) => inDegree[a.id] - inDegree[b.id]);
    const root = sortedByInDegree[0].id;
    layerMap[root] = 0;
    queue.push(root);
  }

  // BFS / topological relaxation
  let safetyCounter = 0;
  while (queue.length > 0 && safetyCounter < nodes.length * 3) {
    safetyCounter++;
    const curr = queue.shift()!;
    const currLayer = layerMap[curr] ?? 0;

    for (const child of children[curr] || []) {
      const nextLayer = currLayer + 1;
      if (layerMap[child] === undefined || layerMap[child] < nextLayer) {
        layerMap[child] = nextLayer;
        queue.push(child);
      }
    }
  }

  // Ensure every node has a layer
  nodes.forEach((n) => {
    if (layerMap[n.id] === undefined) {
      layerMap[n.id] = 0;
    }
  });

  // Group nodes by layer
  const layers: Record<number, string[]> = {};
  nodes.forEach((n) => {
    const l = layerMap[n.id];
    if (!layers[l]) layers[l] = [];
    layers[l].push(n.id);
  });

  // Calculate coordinates
  const positions: { x: number; y: number; id: string }[] = [];
  Object.keys(layers).forEach((layerStr) => {
    const l = parseInt(layerStr, 10);
    const nodeIds = layers[l];
    const count = nodeIds.length;

    nodeIds.forEach((id, idx) => {
      // Center horizontally:
      const x = (idx - (count - 1) / 2) * 260 + 500;
      const y = l * 150 + 60;
      positions.push({ id, x, y });
    });
  });

  return positions;
}

export const CallGraphView: React.FC<CallGraphViewProps> = ({
  data,
  onSelectNode,
  isLoading = false,
}) => {
  const { flowNodes, flowEdges } = useMemo(() => {
    if (!data || !data.nodes || data.nodes.length === 0) {
      return { flowNodes: [], flowEdges: [] };
    }

    const positions = computeLayeredLayout(data.nodes, data.edges);
    const posMap = new Map(positions.map((p) => [p.id, p]));

    const flowNodes: Node[] = data.nodes.map((node) => {
      const pos = posMap.get(node.id) || { x: 100, y: 100 };
      const colors = getSeverityColor(node.severity);

      return {
        id: node.id,
        position: { x: pos.x, y: pos.y },
        data: {
          label: (
            <div className="flex flex-col gap-1">
              <div className="flex items-center justify-between gap-2">
                <span className="font-mono font-semibold text-slate-100 truncate max-w-[140px]">
                  {node.name}
                </span>
                <span
                  className="px-1.5 py-0.5 rounded text-[10px] font-bold"
                  style={{ backgroundColor: colors.bg, color: colors.text }}
                >
                  {node.severity}
                </span>
              </div>
              <div className="flex items-center justify-between text-[11px] text-slate-400">
                <span className="font-mono text-indigo-300">{node.complexity_class}</span>
                <span className="text-[10px] text-slate-500">
                  in:{node.fan_in} out:{node.fan_out}
                </span>
              </div>
            </div>
          ),
          ...node,
        },
        style: {
          background: '#0f172a',
          color: '#f8fafc',
          border: `1.5px solid ${colors.border}`,
          borderRadius: '8px',
          padding: '8px 12px',
          width: 190,
          boxShadow: '0 4px 6px -1px rgba(0, 0, 0, 0.4)',
        },
      };
    });

    const flowEdges: Edge[] = data.edges.map((e) => ({
      id: `e-${e.source}-${e.target}`,
      source: e.source,
      target: e.target,
      label: e.call_count > 1 ? `${e.call_count} calls` : undefined,
      animated: true,
      style: { stroke: '#6366f1', strokeWidth: 1.5 },
      labelStyle: { fill: '#94a3b8', fontSize: 10, fontFamily: 'monospace' },
      labelBgStyle: { fill: '#1e293b', fillOpacity: 0.9 },
    }));

    return { flowNodes, flowEdges };
  }, [data]);

  if (isLoading) {
    return (
      <div className="flex flex-1 items-center justify-center p-12 text-slate-400">
        <div className="h-6 w-6 animate-spin rounded-full border-2 border-indigo-500 border-t-transparent mr-3" />
        <span>Loading call graph...</span>
      </div>
    );
  }

  if (!data || data.nodes.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center flex-1 h-full p-12 text-slate-500">
        <Network className="h-12 w-12 text-slate-600 mb-3" />
        <p className="text-base font-medium text-slate-300 mb-1">No Call Graph Generated Yet</p>
        <p className="text-xs text-slate-500 max-w-sm text-center">
          Click the "Run Analysis" button above to parse your repository and generate the function call hierarchy.
        </p>
      </div>
    );
  }

  return (
    <div className="w-full h-full bg-slate-950 relative">
      <ReactFlow
        nodes={flowNodes}
        edges={flowEdges}
        onNodeClick={(_, node) => {
          if (onSelectNode) {
            onSelectNode(node.id);
          }
        }}
        fitView
      >
        <Background color="#1e293b" gap={16} />
        <Controls className="bg-slate-900 border border-slate-800 text-slate-300 fill-slate-300" />
        <MiniMap
          nodeColor={(n) => {
            const nodeData = n.data as CallGraphNode;
            return getSeverityColor(nodeData?.severity).border;
          }}
          className="bg-slate-900 border border-slate-800 rounded-lg overflow-hidden"
          maskColor="rgba(15, 23, 42, 0.7)"
        />
      </ReactFlow>
    </div>
  );
};
