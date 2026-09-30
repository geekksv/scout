"use client";

import { useEffect, useRef } from "react";
import type { RecordStatus, RunStatus, Source } from "@/lib/api";
import type { LogLine } from "@/lib/useRun";

const runPill: Record<RunStatus, string> = {
  queued: "bg-panel-2 text-muted",
  running: "bg-accent-soft text-accent",
  done: "bg-ok-soft text-ok",
  failed: "bg-err-soft text-err",
  cancelled: "bg-panel-2 text-muted",
};

export function RunStatusPill({ status }: { status: RunStatus }) {
  return (
    <span className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.5 text-xs font-medium ${runPill[status]}`}>
      {status === "running" && <span className="size-1.5 rounded-full bg-accent animate-pulse" />}
      {status}
    </span>
  );
}

const recordPill: Record<RecordStatus, { cls: string; label: string }> = {
  verified: { cls: "bg-ok-soft text-ok", label: "Verified" },
  single: { cls: "bg-panel-2 text-muted", label: "Single source" },
  conflict: { cls: "bg-warn-soft text-warn", label: "Conflict" },
};

export function RecordStatusPill({ status }: { status: RecordStatus }) {
  const { cls, label } = recordPill[status];
  return <span className={`whitespace-nowrap rounded-full px-2 py-0.5 text-[11px] font-medium ${cls}`}>{label}</span>;
}

const STAT_LABELS: [string, string, string][] = [
  ["sources", "Sources found", ""],
  ["fetched", "Pages fetched", ""],
  ["blocked", "Blocked by robots", ""],
  ["raw", "Raw rows", ""],
  ["duplicates", "Duplicates merged", ""],
  ["rejected", "Unproven values dropped", "text-warn"],
  ["clean", "Clean rows", "text-accent"],
];

export function StatsBar({ stats }: { stats: Record<string, number> }) {
  return (
    <div className="grid grid-cols-2 gap-px overflow-hidden rounded-xl border border-line bg-line sm:grid-cols-4 lg:grid-cols-7">
      {STAT_LABELS.map(([key, label, tone]) => (
        <div key={key} className="bg-panel px-4 py-3">
          <div className={`text-2xl font-semibold tabular-nums ${tone}`}>
            {stats[key] ?? 0}
          </div>
          <div className="text-xs text-muted">{label}</div>
        </div>
      ))}
    </div>
  );
}

const levelCls: Record<string, string> = { info: "text-muted", warn: "text-warn", error: "text-err" };

export function LogPanel({ logs }: { logs: LogLine[] }) {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    ref.current?.scrollTo({ top: ref.current.scrollHeight });
  }, [logs.length]);
  return (
    <div className="flex h-full min-h-0 flex-col rounded-xl border border-line bg-panel">
      <div className="border-b border-line px-4 py-2 text-sm font-medium">Activity</div>
      <div ref={ref} className="flex-1 min-h-0 overflow-y-auto px-4 py-2 font-mono text-[12px] leading-relaxed">
        {logs.length === 0 && <p className="text-muted">Waiting for the first event…</p>}
        {logs.map((l) => (
          <div key={l.seq} className="flex gap-2">
            <span className="shrink-0 text-muted/70">{new Date(l.ts).toLocaleTimeString([], { hour12: false })}</span>
            {l.step && <span className="shrink-0 text-accent">{l.step}</span>}
            <span className={`break-all ${levelCls[l.level] ?? ""}`}>{l.message}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

const sourcePill: Record<Source["status"], string> = {
  pending: "bg-panel-2 text-muted",
  fetched: "bg-ok-soft text-ok",
  blocked: "bg-err-soft text-err",
  failed: "bg-warn-soft text-warn",
};

export function SourcesTable({ sources }: { sources: Source[] }) {
  return (
    <div className="max-h-[420px] overflow-auto">
      <table className="w-full text-sm">
        <thead className="sticky top-0 bg-panel-2 text-left text-xs text-muted">
          <tr>
            <th className="px-4 py-2 font-medium">Page</th>
            <th className="w-28 px-4 py-2 font-medium">robots.txt</th>
            <th className="w-24 px-4 py-2 font-medium">Status</th>
          </tr>
        </thead>
        <tbody>
          {sources.length === 0 && (
            <tr>
              <td colSpan={3} className="px-4 py-10 text-center text-muted">Sources appear here after discovery.</td>
            </tr>
          )}
          {sources.map((s) => (
            <tr key={s.id} className="border-t border-line align-top">
              <td className="max-w-0 px-4 py-2">
                <a href={s.url} target="_blank" rel="noreferrer" className="block truncate font-medium hover:text-accent">
                  {s.title || s.url}
                </a>
                <div className="truncate text-xs text-muted">{s.domain}</div>
              </td>
              <td className="px-4 py-2 whitespace-nowrap text-xs">
                {s.robots_allowed ? <span className="text-ok">Allowed</span> : <span className="text-err">Disallowed</span>}
              </td>
              <td className="px-4 py-2">
                <span className={`rounded-full px-2 py-0.5 text-[11px] font-medium ${sourcePill[s.status]}`}>{s.status}</span>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
