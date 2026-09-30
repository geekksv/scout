"use client";

import { ArrowDown, ArrowUp, Download, Search } from "lucide-react";
import { useMemo, useState } from "react";
import { api, type DataRecord, type RecordStatus } from "@/lib/api";
import { RecordStatusPill } from "./parts";

type Sort = { col: string; dir: 1 | -1 } | null;
const TRUST_ORDER: Record<RecordStatus, number> = { verified: 0, conflict: 1, single: 2 };

function formatCell(v: unknown) {
  if (v == null || v === "") return <span className="text-muted">—</span>;
  const s = String(v);
  if (/^https?:\/\//.test(s))
    return (
      <a href={s} target="_blank" rel="noreferrer" onClick={(e) => e.stopPropagation()} className="text-accent hover:underline">
        {s.replace(/^https?:\/\/(www\.)?/, "").replace(/\/$/, "")}
      </a>
    );
  return s;
}

function compare(a: unknown, b: unknown) {
  if (a == null || a === "") return 1;
  if (b == null || b === "") return -1;
  if (typeof a === "number" && typeof b === "number") return a - b;
  return String(a).localeCompare(String(b), undefined, { numeric: true, sensitivity: "base" });
}

export function DatasetView({
  runId,
  rows,
  columns,
  exportable,
  onOpen,
}: {
  runId: number;
  rows: DataRecord[];
  columns: string[];
  exportable: boolean;
  onOpen: (r: DataRecord, field: string | null) => void;
}) {
  const [query, setQuery] = useState("");
  const [trust, setTrust] = useState<RecordStatus | "all">("all");
  const [sort, setSort] = useState<Sort>(null);
  const cols = columns.length ? columns : Object.keys(rows[0]?.data ?? {});

  const visible = useMemo(() => {
    const q = query.trim().toLowerCase();
    let out = rows.filter(
      (r) =>
        (trust === "all" || r.status === trust) &&
        (!q || cols.some((c) => String(r.data[c] ?? "").toLowerCase().includes(q))),
    );
    if (sort) {
      out = [...out].sort((a, b) =>
        sort.col === "__trust"
          ? (TRUST_ORDER[a.status] - TRUST_ORDER[b.status]) * sort.dir
          : compare(a.data[sort.col], b.data[sort.col]) * sort.dir,
      );
    }
    return out;
  }, [rows, query, trust, sort, cols]);

  const toggleSort = (col: string) =>
    setSort((s) => (s?.col !== col ? { col, dir: 1 } : s.dir === 1 ? { col, dir: -1 } : null));

  const header = (col: string, label: string) => (
    <th key={col} className="px-4 py-2 font-medium">
      <button onClick={() => toggleSort(col)} className="inline-flex items-center gap-1 hover:text-fg">
        {label}
        {sort?.col === col && (sort.dir === 1 ? <ArrowUp className="size-3" /> : <ArrowDown className="size-3" />)}
      </button>
    </th>
  );

  return (
    <div>
      <div className="flex flex-wrap items-center gap-2 border-b border-line px-3 py-2">
        <label className="flex min-w-48 flex-1 items-center gap-2 rounded-md border border-line bg-bg px-2 py-1.5">
          <Search className="size-4 text-muted" />
          <input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Search rows…"
            className="w-full bg-transparent text-sm outline-none placeholder:text-muted"
          />
        </label>
        <select
          value={trust}
          onChange={(e) => setTrust(e.target.value as RecordStatus | "all")}
          className="rounded-md border border-line bg-bg px-2 py-1.5 text-sm"
          aria-label="Filter by trust"
        >
          <option value="all">All rows</option>
          <option value="verified">Verified only</option>
          <option value="conflict">Conflicts only</option>
          <option value="single">Single source only</option>
        </select>
        {exportable && (
          <div className="flex items-center gap-1">
            <Download className="size-4 text-muted" />
            {(["csv", "xlsx", "json"] as const).map((f) => (
              <a
                key={f}
                href={api.exportUrl(runId, f)}
                className="rounded-md border border-line px-2 py-1 text-xs uppercase hover:border-accent hover:text-accent"
              >
                {f}
              </a>
            ))}
          </div>
        )}
      </div>
      <div className="max-h-[440px] overflow-auto">
        <table className="w-full text-sm">
          <thead className="sticky top-0 z-10 bg-panel-2 text-left text-xs text-muted">
            <tr>
              {cols.map((c) => header(c, c.replaceAll("_", " ")))}
              {header("__trust", "trust")}
            </tr>
          </thead>
          <tbody>
            {visible.length === 0 && (
              <tr>
                <td colSpan={cols.length + 1} className="px-4 py-10 text-center text-muted">
                  {rows.length === 0 ? "Rows appear here as soon as they are verified." : "No rows match these filters."}
                </td>
              </tr>
            )}
            {visible.map((r) => (
              // The highlight animation runs once when a row mounts.
              <tr
                key={r.id}
                onClick={() => onOpen(r, null)}
                className="row-new cursor-pointer border-t border-line hover:bg-panel-2"
                title="Click to see the evidence for this row"
              >
                {cols.map((c) => {
                  const m = r.field_meta?.[c];
                  return (
                    <td
                      key={c}
                      onClick={(e) => {
                        e.stopPropagation();
                        onOpen(r, c);
                      }}
                      className={`whitespace-nowrap px-4 py-2 ${m?.conflict ? "bg-warn-soft" : ""}`}
                    >
                      <span className="inline-flex items-center gap-1.5">
                        {m && (m.sources >= 2 || m.resolved) && !m.conflict && (
                          <span className="size-1.5 rounded-full bg-ok" title={`Confirmed by ${m.sources} sources`} />
                        )}
                        {formatCell(r.data[c])}
                      </span>
                    </td>
                  );
                })}
                <td className="px-4 py-2">
                  <RecordStatusPill status={r.status} />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {rows.length > 0 && (
        <p className="border-t border-line px-4 py-2 text-xs text-muted">
          Showing {visible.length} of {rows.length} rows. Click any cell to see the exact quote behind it. A green dot
          means independent sources agree; amber cells are conflicts.
        </p>
      )}
    </div>
  );
}
