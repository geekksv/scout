import { ensureAwake, markUnreachable } from "./backend";

export const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export type RunStatus = "queued" | "running" | "done" | "failed" | "cancelled";
export type StepStatus = "idle" | "running" | "done" | "failed";
export type RecordStatus = "verified" | "single" | "conflict";

export interface GraphNode { id: string; label: string; description: string }
export interface GraphEdge { id: string; source: string; target: string; loop?: boolean; label?: string }
export interface Graph { nodes: GraphNode[]; edges: GraphEdge[] }

export interface IntentField { name: string; type: string; required: boolean; description: string }
export interface Intent {
  entity: string;
  fields: IntentField[];
  filters: string[];
  target_count: number;
  queries: string[];
  blocked_domains: string[];
  region: string;
}

export const FIELD_TYPES = ["string", "integer", "number", "url", "email", "date", "boolean"] as const;

export interface Workflow {
  id: number;
  prompt: string;
  intent: Intent;
  parent_id: number | null;
  created_at: string;
}

export interface Source {
  id: number;
  run_id: number;
  url: string;
  domain: string;
  title: string;
  snippet: string;
  robots_allowed: boolean;
  status: "pending" | "fetched" | "blocked" | "failed";
  screenshot_path: string | null;
  screenshot_url: string | null;
  fetched_at: string | null;
}

export interface RunInfo {
  id: number;
  workflow_id: number;
  prompt: string;
  mode: "live" | "demo" | "replay";
  replay_of: number | null;
  status: RunStatus;
  progress: number;
  stats: Record<string, number>;
  error: string | null;
  started_at: string;
  finished_at: string | null;
  active: boolean;
  intent?: Intent;
}

export interface FieldMeta { sources: number; conflict: boolean; alternatives: unknown[]; resolved?: boolean }

export interface DataRecord {
  id: number;
  data: Record<string, unknown>;
  status: RecordStatus;
  confidence: number;
  field_meta?: Record<string, FieldMeta>;
}

export interface Evidence {
  value: string;
  quote: string;
  context: { before: string; match: string; after: string; exact: boolean };
  source: { id: number; url: string; domain: string; title: string; fetched_at: string | null; screenshot_url: string | null };
}

export interface Proof {
  record: DataRecord;
  fields: { field: string; value: unknown; meta: Partial<FieldMeta>; evidence: Evidence[] }[];
}

export interface RunDiff {
  previous_run_id: number | null;
  added?: string[];
  removed?: string[];
  changed?: { name: string; record_id: number; fields: string[] }[];
  unchanged?: number;
}

export interface RunEvent {
  seq: number;
  ts: string;
  type: "run" | "plan" | "step" | "log" | "row" | "stats";
  step: string | null;
  payload: Record<string, unknown>;
}

interface RunStarted { run_id: number; workflow_id: number }

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  await ensureAwake();
  let res: Response;
  try {
    res = await fetch(`${API_URL}${path}`, {
      ...init,
      headers: { "content-type": "application/json", ...init?.headers },
      cache: "no-store",
    });
  } catch (e) {
    // Network failure: the server may have gone back to sleep. Wake it, and retry
    // reads once (never writes, which might already have reached the server).
    markUnreachable();
    await ensureAwake();
    if ((init?.method ?? "GET") !== "GET") throw e;
    res = await fetch(`${API_URL}${path}`, {
      ...init,
      headers: { "content-type": "application/json", ...init?.headers },
      cache: "no-store",
    });
  }
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.detail ?? `${res.status} ${res.statusText}`);
  }
  return res.json();
}

export const api = {
  graph: () => request<Graph>("/api/graph"),
  runs: () => request<RunInfo[]>("/api/runs"),
  run: (id: number) => request<RunInfo>(`/api/runs/${id}`),
  records: (id: number) => request<DataRecord[]>(`/api/runs/${id}/records`),
  sources: (id: number) => request<Source[]>(`/api/runs/${id}/sources`),
  createDemoRun: (prompt: string) =>
    request<RunStarted>("/api/runs", { method: "POST", body: JSON.stringify({ prompt }) }),
  createWorkflow: (prompt: string) =>
    request<Workflow>("/api/workflows", { method: "POST", body: JSON.stringify({ prompt }) }),
  workflow: (id: number) => request<Workflow>(`/api/workflows/${id}`),
  updateWorkflow: (id: number, intent: Intent) =>
    request<Workflow>(`/api/workflows/${id}`, { method: "PUT", body: JSON.stringify({ intent }) }),
  runWorkflow: (id: number, mode: "live" | "demo" = "live") =>
    request<RunStarted>(`/api/workflows/${id}/runs`, { method: "POST", body: JSON.stringify({ mode }) }),
  proof: (recordId: number) => request<Proof>(`/api/records/${recordId}/provenance`),
  resolve: (recordId: number, field: string, value: unknown) =>
    request<DataRecord>(`/api/records/${recordId}/resolve`, { method: "POST", body: JSON.stringify({ field, value }) }),
  diff: (id: number) => request<RunDiff>(`/api/runs/${id}/diff`),
  replay: (id: number) => request<RunStarted>(`/api/runs/${id}/replay`, { method: "POST" }),
  exportUrl: (id: number, format: "csv" | "json" | "xlsx") => `${API_URL}/api/runs/${id}/export?format=${format}`,
  fileUrl: (path: string) => `${API_URL}${path}`,
  cancelRun: (id: number) => request<{ ok: boolean }>(`/api/runs/${id}/cancel`, { method: "POST" }),
  eventsUrl: (id: number) => `${API_URL}/api/runs/${id}/events`,
};
