"use client";

import { Check, ExternalLink, Loader2, ShieldCheck, TriangleAlert, X } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { api, type DataRecord, type Evidence, type FieldMeta, type Proof } from "@/lib/api";
import { RecordStatusPill } from "./parts";

function FieldBadge({ meta }: { meta: Partial<FieldMeta> }) {
  if (meta.conflict)
    return (
      <span className="inline-flex items-center gap-1 rounded-full bg-warn-soft px-2 py-0.5 text-[11px] font-medium text-warn">
        <TriangleAlert className="size-3" /> Sources disagree
      </span>
    );
  if (meta.resolved)
    return <span className="rounded-full bg-accent-soft px-2 py-0.5 text-[11px] font-medium text-accent">Resolved by you</span>;
  if ((meta.sources ?? 1) >= 2)
    return (
      <span className="inline-flex items-center gap-1 rounded-full bg-ok-soft px-2 py-0.5 text-[11px] font-medium text-ok">
        <ShieldCheck className="size-3" /> Verified by {meta.sources} sources
      </span>
    );
  return <span className="rounded-full bg-panel-2 px-2 py-0.5 text-[11px] font-medium text-muted">Single source</span>;
}

function EvidenceCard({ ev }: { ev: Evidence }) {
  const shot = ev.source.screenshot_url ? api.fileUrl(ev.source.screenshot_url) : null;
  return (
    <div className="rounded-lg border border-line bg-bg p-3">
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <div className="truncate text-sm font-medium">{ev.source.title || ev.source.domain}</div>
          <div className="truncate text-xs text-muted">
            {ev.source.domain}
            {ev.source.fetched_at && ` · fetched ${new Date(ev.source.fetched_at).toLocaleString()}`}
          </div>
        </div>
        <a
          href={ev.source.url}
          target="_blank"
          rel="noreferrer"
          className="inline-flex shrink-0 items-center gap-1 text-xs text-accent hover:underline"
        >
          Open source <ExternalLink className="size-3" />
        </a>
      </div>
      <p className="mt-2 text-[13px] leading-relaxed text-muted">
        {ev.context.before}
        <mark className="rounded bg-[color-mix(in_srgb,var(--warn)_30%,transparent)] px-0.5 text-fg">
          {ev.context.match}
        </mark>
        {ev.context.after}
      </p>
      <div className="mt-2 flex items-center justify-between gap-2 text-[11px] text-muted">
        <span>
          Extracted value: <b className="text-fg">{ev.value}</b>
        </span>
        <span>{ev.context.exact ? "Exact quote match" : "Near-exact match (formatting differs)"}</span>
      </div>
      {shot && (
        <a href={shot} target="_blank" rel="noreferrer" className="mt-2 block overflow-hidden rounded-md border border-line">
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img src={shot} alt={`Screenshot of ${ev.source.domain}`} className="max-h-40 w-full object-cover object-top" />
        </a>
      )}
    </div>
  );
}

export function ProofPanel({
  record,
  focusField,
  entity,
  onClose,
  onResolved,
}: {
  record: DataRecord;
  focusField: string | null;
  entity: string;
  onClose: () => void;
  onResolved: (r: DataRecord) => void;
}) {
  const [proof, setProof] = useState<Proof | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState<string | null>(null);
  const focusRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    setProof(null);
    api.proof(record.id).then(setProof).catch((e) => setError(e.message));
  }, [record.id]);

  useEffect(() => {
    focusRef.current?.scrollIntoView({ block: "start", behavior: "smooth" });
  }, [proof, focusField]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  const resolve = async (field: string, value: unknown) => {
    setSaving(`${field}:${String(value)}`);
    try {
      const updated = await api.resolve(record.id, field, value);
      onResolved(updated);
      setProof(await api.proof(record.id));
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setSaving(null);
    }
  };

  const name = String(Object.values(record.data)[0] ?? "Row");

  return (
    <div className="fixed inset-0 z-40 flex justify-end bg-black/40" onClick={onClose}>
      <aside
        className="flex h-full w-full max-w-xl flex-col border-l border-line bg-panel shadow-2xl"
        onClick={(e) => e.stopPropagation()}
        aria-label="Evidence for this row"
      >
        <header className="flex items-start justify-between gap-3 border-b border-line p-4">
          <div className="min-w-0">
            <p className="text-xs uppercase tracking-wide text-muted">Click-to-Proof · {entity}</p>
            <h2 className="truncate text-lg font-semibold">{name}</h2>
            <div className="mt-1 flex items-center gap-2 text-xs text-muted">
              <RecordStatusPill status={(proof?.record ?? record).status} />
              <span>confidence {Math.round((proof?.record ?? record).confidence * 100)}%</span>
            </div>
          </div>
          <button onClick={onClose} className="rounded-md p-1 text-muted hover:bg-panel-2 hover:text-fg" aria-label="Close">
            <X className="size-5" />
          </button>
        </header>

        <div className="flex-1 space-y-5 overflow-y-auto p-4">
          {error && <p className="rounded-lg border border-err bg-err-soft p-3 text-sm text-err">{error}</p>}
          {!proof && !error && (
            <div className="flex items-center gap-2 text-sm text-muted">
              <Loader2 className="size-4 animate-spin" /> Loading evidence…
            </div>
          )}
          {proof?.fields.map((f) => {
            const values = f.meta.conflict
              ? [f.value, ...(f.meta.alternatives ?? [])].filter((v, i, a) => a.findIndex((x) => String(x) === String(v)) === i)
              : [];
            return (
              <section
                key={f.field}
                ref={f.field === focusField ? focusRef : undefined}
                className={`scroll-mt-4 rounded-xl p-1 ${f.field === focusField ? "ring-2 ring-accent" : ""}`}
              >
                <div className="flex flex-wrap items-center justify-between gap-2 px-1">
                  <div className="min-w-0">
                    <div className="font-mono text-xs text-muted">{f.field}</div>
                    <div className="break-words font-medium">{String(f.value ?? "—")}</div>
                  </div>
                  <FieldBadge meta={f.meta} />
                </div>
                {values.length > 1 && (
                  <div className="mt-2 rounded-lg border border-warn bg-warn-soft p-3">
                    <p className="text-xs text-warn">Independent sources report different values. Pick the correct one:</p>
                    <div className="mt-2 flex flex-wrap gap-2">
                      {values.map((v) => (
                        <button
                          key={String(v)}
                          onClick={() => resolve(f.field, v)}
                          disabled={!!saving}
                          className="inline-flex items-center gap-1 rounded-md border border-line bg-panel px-2.5 py-1 text-sm hover:border-accent disabled:opacity-50"
                        >
                          {saving === `${f.field}:${String(v)}` ? <Loader2 className="size-3 animate-spin" /> : <Check className="size-3" />}
                          Use “{String(v)}”
                        </button>
                      ))}
                    </div>
                  </div>
                )}
                <div className="mt-2 space-y-2">
                  {f.evidence.map((ev, i) => <EvidenceCard key={i} ev={ev} />)}
                </div>
              </section>
            );
          })}
        </div>
      </aside>
    </div>
  );
}
