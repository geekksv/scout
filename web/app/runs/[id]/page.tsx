"use client";

import { Pencil, Play, RotateCw } from "lucide-react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import { RunGraph } from "@/components/flow/RunGraph";
import { DatasetView } from "@/components/run/DatasetView";
import { Insights } from "@/components/run/Insights";
import { LogPanel, RunStatusPill, SourcesTable, StatsBar } from "@/components/run/parts";
import { ProofPanel } from "@/components/run/ProofPanel";
import { api, type DataRecord, type Graph, type RunDiff, type RunInfo, type Source } from "@/lib/api";
import { useRun } from "@/lib/useRun";

const btn =
  "inline-flex items-center gap-1.5 rounded-lg border border-line bg-panel px-3 py-1.5 text-sm hover:border-accent hover:text-accent disabled:opacity-50";

export default function RunPage() {
  const runId = Number(useParams<{ id: string }>().id);
  const router = useRouter();
  const [graph, setGraph] = useState<Graph | null>(null);
  const [info, setInfo] = useState<RunInfo | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [sources, setSources] = useState<Source[]>([]);
  const [records, setRecords] = useState<DataRecord[] | null>(null);
  const [diff, setDiff] = useState<RunDiff | null>(null);
  const [tab, setTab] = useState<"dataset" | "sources" | null>(null);
  const [open, setOpen] = useState<{ record: DataRecord; field: string | null } | null>(null);
  const [busy, setBusy] = useState(false);
  const run = useRun(runId);
  const finished = run.status === "done" || run.status === "failed" || run.status === "cancelled";

  useEffect(() => {
    api.graph().then(setGraph).catch((e) => setError(e.message));
    api.run(runId).then(setInfo).catch((e) => setError(e.message));
  }, [runId]);

  // Refresh the source list whenever discovery or fetching moves the counters.
  const sourceKey = `${run.stats.sources ?? 0}-${run.stats.fetched ?? 0}-${run.stats.failed ?? 0}-${run.status}`;
  useEffect(() => {
    api.sources(runId).then(setSources).catch(() => {});
  }, [runId, sourceKey]);

  // Once finished, the stored records are the source of truth (they include conflict resolutions).
  useEffect(() => {
    if (!finished) return;
    api.records(runId).then(setRecords).catch(() => {});
    api.diff(runId).then(setDiff).catch(() => {});
    api.run(runId).then(setInfo).catch(() => {});
  }, [runId, finished]);

  const rows = records ?? run.rows;
  const activeTab = tab ?? (rows.length === 0 && sources.length > 0 ? "sources" : "dataset");
  const intent = run.intent ?? info?.intent;
  const columns = intent?.fields.map((f) => f.name) ?? [];

  const onResolved = useCallback((r: DataRecord) => {
    setRecords((prev) => (prev ?? []).map((x) => (x.id === r.id ? r : x)));
    setOpen((o) => (o ? { ...o, record: r } : o));
  }, []);
  const closeProof = useCallback(() => setOpen(null), []);

  const go = async (action: () => Promise<{ run_id: number }>) => {
    setBusy(true);
    try {
      const { run_id } = await action();
      router.push(`/runs/${run_id}`);
    } catch (e) {
      setError((e as Error).message);
      setBusy(false);
    }
  };

  if (error && !info) {
    return <p className="rounded-lg border border-err bg-err-soft p-4 text-sm text-err">Could not load run: {error}</p>;
  }

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2 text-xs text-muted">
            <span>Run #{runId}</span>
            {info && <span className="rounded bg-panel-2 px-1.5 py-0.5 uppercase tracking-wide">{info.mode}</span>}
            {info?.replay_of && (
              <Link href={`/runs/${info.replay_of}`} className="text-accent hover:underline">
                replay of run #{info.replay_of}
              </Link>
            )}
            <RunStatusPill status={run.status} />
          </div>
          <h1 className="mt-1 text-xl font-semibold tracking-tight">{info?.prompt ?? "…"}</h1>
          {run.error && <p className="mt-1 text-sm text-err">{run.error}</p>}
          {error && info && <p className="mt-1 text-sm text-err">{error}</p>}
        </div>
        <div className="flex flex-wrap gap-2">
          {run.status === "running" && (
            <button onClick={() => api.cancelRun(runId).catch((e) => setError(e.message))} className={`${btn} hover:!border-err hover:!text-err`}>
              Cancel run
            </button>
          )}
          {finished && info && info.mode !== "demo" && (
            <Link href={`/plan/${info.workflow_id}`} className={btn}>
              <Pencil className="size-4" /> Edit plan
            </Link>
          )}
          {finished && info && (
            <button
              disabled={busy}
              onClick={() => go(() => api.runWorkflow(info.workflow_id, info.mode === "demo" ? "demo" : "live"))}
              className={btn}
              title="Run the same workflow again and compare"
            >
              <RotateCw className="size-4" /> Re-run
            </button>
          )}
          {finished && run.status === "done" && (
            <button
              disabled={busy}
              onClick={() => go(() => api.replay(runId))}
              className={btn}
              title="Replay this run's recorded events: no network or AI quota needed"
            >
              <Play className="size-4" /> Replay
            </button>
          )}
        </div>
      </div>

      {graph ? (
        <RunGraph graph={graph} steps={run.steps} loop={run.loop} />
      ) : (
        <div className="h-[230px] animate-pulse card" />
      )}

      <StatsBar stats={run.stats} />

      {diff?.previous_run_id && (
        <div className="flex flex-wrap items-center gap-x-4 gap-y-1 card px-4 py-2 text-sm">
          <span className="text-muted">
            Compared with <Link href={`/runs/${diff.previous_run_id}`} className="text-accent hover:underline">run #{diff.previous_run_id}</Link>:
          </span>
          <span className="text-ok">+{diff.added?.length ?? 0} new</span>
          <span className="text-warn">~{diff.changed?.length ?? 0} changed</span>
          <span className="text-err">−{diff.removed?.length ?? 0} removed</span>
          <span className="text-muted">{diff.unchanged ?? 0} unchanged</span>
          {!!diff.added?.length && (
            <span className="truncate text-xs text-muted">New: {diff.added.slice(0, 5).join(", ")}{diff.added.length > 5 ? "…" : ""}</span>
          )}
        </div>
      )}

      {intent && (
        <div className="flex flex-wrap items-center gap-2 text-xs">
          <span className="text-muted">Schema for <b className="text-fg">{intent.entity}</b>:</span>
          {intent.fields.map((f) => (
            <span key={f.name} className="rounded-md border border-line bg-panel px-2 py-0.5 font-mono">
              {f.name}
              <span className="text-muted">: {f.type}{f.required ? "" : "?"}</span>
            </span>
          ))}
          {intent.filters.map((f) => (
            <span key={f} className="rounded-md bg-accent-soft px-2 py-0.5 text-accent">{f}</span>
          ))}
        </div>
      )}

      <div className="grid gap-4 lg:grid-cols-[1fr_340px]">
        <div className="min-w-0 overflow-hidden card">
          <div className="flex items-center gap-1 border-b border-line px-2 py-1.5">
            {(["dataset", "sources"] as const).map((t) => (
              <button
                key={t}
                onClick={() => setTab(t)}
                className={`rounded-md px-3 py-1 text-sm capitalize ${
                  activeTab === t ? "bg-panel-2 font-medium text-fg" : "text-muted hover:text-fg"
                }`}
              >
                {t}
                <span className="ml-1.5 text-xs text-muted">{t === "dataset" ? rows.length : sources.length}</span>
              </button>
            ))}
          </div>
          {activeTab === "dataset" ? (
            <DatasetView
              runId={runId}
              rows={rows}
              columns={columns}
              exportable={finished && rows.length > 0}
              onOpen={(record, field) => setOpen({ record, field })}
            />
          ) : (
            <SourcesTable sources={sources} />
          )}
        </div>
        <div className="h-[520px]">
          <LogPanel logs={run.logs} />
        </div>
      </div>

      {finished && <Insights rows={rows} columns={columns} sources={sources} />}

      {open && (
        <ProofPanel
          record={open.record}
          focusField={open.field}
          entity={intent?.entity ?? "row"}
          onClose={closeProof}
          onResolved={onResolved}
        />
      )}
    </div>
  );
}
