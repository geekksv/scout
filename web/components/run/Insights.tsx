"use client";

import type { DataRecord, Source } from "@/lib/api";

function Bar({ label, value, total, color }: { label: string; value: number; total: number; color: string }) {
  const pct = total ? Math.round((value / total) * 100) : 0;
  return (
    <div>
      <div className="flex justify-between text-xs">
        <span className="truncate text-muted">{label}</span>
        <span className="tabular-nums">{value} · {pct}%</span>
      </div>
      <div className="mt-1 h-1.5 overflow-hidden rounded-full bg-panel-2">
        <div className="h-full rounded-full" style={{ width: `${pct}%`, background: color }} />
      </div>
    </div>
  );
}

function Card({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="rounded-xl border border-line bg-panel p-4">
      <h3 className="mb-3 text-sm font-medium">{title}</h3>
      <div className="space-y-2.5">{children}</div>
    </div>
  );
}

export function Insights({ rows, columns, sources }: { rows: DataRecord[]; columns: string[]; sources: Source[] }) {
  if (rows.length === 0) return null;
  const n = rows.length;
  const count = (s: DataRecord["status"]) => rows.filter((r) => r.status === s).length;

  const byDomain = new Map<string, number>();
  for (const s of sources) if (s.status === "fetched") byDomain.set(s.domain, (byDomain.get(s.domain) ?? 0) + 1);
  const fetched = sources.filter((s) => s.status === "fetched").length;

  return (
    <div className="grid gap-4 md:grid-cols-3">
      <Card title="Trust">
        <Bar label="Verified by 2+ sources" value={count("verified")} total={n} color="var(--ok)" />
        <Bar label="Single source" value={count("single")} total={n} color="var(--muted)" />
        <Bar label="Conflicting sources" value={count("conflict")} total={n} color="var(--warn)" />
      </Card>
      <Card title="Field completeness">
        {columns.map((c) => (
          <Bar
            key={c}
            label={c.replaceAll("_", " ")}
            value={rows.filter((r) => r.data[c] != null && r.data[c] !== "").length}
            total={n}
            color="var(--accent)"
          />
        ))}
      </Card>
      <Card title="Sources">
        <Bar label="Pages fetched" value={fetched} total={sources.length} color="var(--ok)" />
        <Bar label="Blocked by robots.txt" value={sources.filter((s) => s.status === "blocked").length} total={sources.length} color="var(--err)" />
        <Bar label="Unreachable" value={sources.filter((s) => s.status === "failed").length} total={sources.length} color="var(--warn)" />
        <p className="pt-1 text-xs text-muted">{byDomain.size} distinct domains contributed pages.</p>
      </Card>
    </div>
  );
}
