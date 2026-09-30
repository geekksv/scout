"use client";

import "@xyflow/react/dist/style.css";
import {
  Background,
  Handle,
  MarkerType,
  Position,
  ReactFlow,
  type Edge,
  type Node,
  type NodeProps,
} from "@xyflow/react";
import { Check, Loader2, X } from "lucide-react";
import { useMemo } from "react";
import type { Graph, StepStatus } from "@/lib/api";
import type { StepState } from "@/lib/useRun";

type StepData = {
  label: string;
  description: string;
  state?: StepState;
  hasLoopOut?: boolean;
  hasLoopIn?: boolean;
};
type StepNodeType = Node<StepData, "step">;

const ring: Record<StepStatus, string> = {
  idle: "border-line bg-panel text-muted",
  running: "border-accent bg-accent-soft text-fg node-running",
  done: "border-ok bg-panel text-fg",
  failed: "border-err bg-err-soft text-fg",
};

function StatusIcon({ status }: { status: StepStatus }) {
  if (status === "running") return <Loader2 className="size-3.5 animate-spin text-accent" />;
  if (status === "done") return <Check className="size-3.5 text-ok" />;
  if (status === "failed") return <X className="size-3.5 text-err" />;
  return <span className="size-2 rounded-full bg-line" />;
}

function StepNode({ data }: NodeProps<StepNodeType>) {
  const status = data.state?.status ?? "idle";
  const counts = data.state?.counts;
  const detail =
    data.state?.message ?? (counts ? Object.entries(counts).map(([k, v]) => `${v} ${k}`).join(" · ") : "");
  return (
    <div className={`w-[156px] rounded-lg border-2 px-3 py-2 transition-colors ${ring[status]}`}>
      <Handle type="target" position={Position.Left} className="!opacity-0" />
      <Handle type="source" position={Position.Right} className="!opacity-0" />
      {data.hasLoopOut && <Handle id="loop-out" type="source" position={Position.Bottom} className="!opacity-0" />}
      {data.hasLoopIn && <Handle id="loop-in" type="target" position={Position.Bottom} className="!opacity-0" />}
      <div className="flex items-center justify-between">
        <span className="text-sm font-semibold">{data.label}</span>
        <StatusIcon status={status} />
      </div>
      <p className="mt-0.5 text-[11px] leading-snug text-muted line-clamp-2">{detail || data.description}</p>
    </div>
  );
}

const nodeTypes = { step: StepNode };

export function RunGraph({
  graph,
  steps,
  loop,
}: {
  graph: Graph;
  steps: Record<string, StepState>;
  loop: StepStatus;
}) {
  const loopEdge = graph.edges.find((e) => e.loop);

  const nodes: StepNodeType[] = useMemo(
    () =>
      graph.nodes.map((n, i) => ({
        id: n.id,
        type: "step",
        position: { x: i * 190, y: 0 },
        draggable: false,
        data: {
          label: n.label,
          description: n.description,
          state: steps[n.id],
          hasLoopOut: loopEdge?.source === n.id,
          hasLoopIn: loopEdge?.target === n.id,
        },
      })),
    [graph, steps, loopEdge],
  );

  const edges: Edge[] = useMemo(
    () =>
      graph.edges.map((e) => {
        if (e.loop) {
          const active = loop !== "idle";
          const color = active ? "var(--warn)" : "var(--border)";
          return {
            id: e.id,
            source: e.source,
            target: e.target,
            sourceHandle: "loop-out",
            targetHandle: "loop-in",
            type: "smoothstep",
            label: e.label,
            animated: loop === "running",
            labelStyle: { fill: active ? "var(--warn)" : "var(--muted)", fontSize: 11, fontWeight: 600 },
            labelBgStyle: { fill: "var(--bg)" },
            style: { stroke: color, strokeWidth: 2, strokeDasharray: "6 4" },
            markerEnd: { type: MarkerType.ArrowClosed, color },
          };
        }
        const src = steps[e.source]?.status;
        const tgt = steps[e.target]?.status;
        const color = src === "done" ? "var(--ok)" : "var(--border)";
        return {
          id: e.id,
          source: e.source,
          target: e.target,
          animated: tgt === "running",
          style: { stroke: tgt === "running" ? "var(--accent)" : color, strokeWidth: 2 },
          markerEnd: { type: MarkerType.ArrowClosed, color: tgt === "running" ? "var(--accent)" : color },
        };
      }),
    [graph, steps, loop],
  );

  return (
    <div className="h-[230px] rounded-xl border border-line bg-panel">
      <ReactFlow
        nodes={nodes}
        edges={edges}
        nodeTypes={nodeTypes}
        fitView
        fitViewOptions={{ padding: 0.15 }}
        nodesConnectable={false}
        elementsSelectable={false}
        panOnDrag={false}
        zoomOnScroll={false}
        zoomOnPinch={false}
        zoomOnDoubleClick={false}
        preventScrolling={false}
        proOptions={{ hideAttribution: true }}
      >
        <Background gap={20} size={1} color="var(--border)" />
      </ReactFlow>
    </div>
  );
}
