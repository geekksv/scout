"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { RunStatusPill } from "@/components/run/parts";
import { api, type RunInfo } from "@/lib/api";

export default function RunsPage() {
  const [runs, setRuns] = useState<RunInfo[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const load = () => api.runs().then(setRuns).catch((e) => setError(e.message));
    load();
    const t = setInterval(load, 3000);
    return () => clearInterval(t);
  }, []);

  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-xl font-semibold tracking-tight">Runs</h1>
        <p className="text-sm text-muted">Every workflow run, newest first. Open one to re-run it, replay it or compare it with its previous run.</p>
      </div>
      {error && <p className="text-sm text-err">{error}</p>}
      <div className="overflow-hidden rounded-xl border border-line bg-panel">
        <table className="w-full text-sm">
          <thead className="bg-panel-2 text-left text-xs text-muted">
            <tr>
              <th className="px-4 py-2 font-medium">#</th>
              <th className="px-4 py-2 font-medium">Request</th>
              <th className="px-4 py-2 font-medium">Mode</th>
              <th className="px-4 py-2 font-medium">Status</th>
              <th className="px-4 py-2 font-medium">Progress</th>
              <th className="px-4 py-2 font-medium">Rows</th>
              <th className="px-4 py-2 font-medium">Started</th>
            </tr>
          </thead>
          <tbody>
            {runs?.length === 0 && (
              <tr>
                <td colSpan={7} className="px-4 py-10 text-center text-muted">
                  No runs yet. <Link href="/" className="text-accent">Start one</Link>.
                </td>
              </tr>
            )}
            {runs?.map((r) => (
              <tr key={r.id} className="border-t border-line hover:bg-panel-2">
                <td className="px-4 py-2 text-muted">{r.id}</td>
                <td className="max-w-md truncate px-4 py-2">
                  <Link href={`/runs/${r.id}`} className="hover:text-accent">{r.prompt}</Link>
                </td>
                <td className="px-4 py-2">
                  <span className="rounded bg-panel-2 px-1.5 py-0.5 text-[11px] uppercase tracking-wide text-muted">
                    {r.mode}{r.replay_of ? ` of #${r.replay_of}` : ""}
                  </span>
                </td>
                <td className="px-4 py-2"><RunStatusPill status={r.status} /></td>
                <td className="px-4 py-2">
                  <div className="h-1.5 w-24 overflow-hidden rounded-full bg-panel-2">
                    <div className="h-full bg-accent transition-all" style={{ width: `${r.progress * 100}%` }} />
                  </div>
                </td>
                <td className="px-4 py-2 tabular-nums">{r.stats?.clean ?? "—"}</td>
                <td className="px-4 py-2 text-muted">{new Date(r.started_at).toLocaleString()}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
