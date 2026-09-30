"use client";

import { ArrowRight, Loader2, Plus, Trash2, X } from "lucide-react";
import { useParams, useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { api, FIELD_TYPES, type Intent, type IntentField, type Workflow } from "@/lib/api";

const input =
  "w-full rounded-md border border-line bg-bg px-2 py-1.5 text-sm outline-none focus:border-accent";

function Section({ title, hint, children }: { title: string; hint: string; children: React.ReactNode }) {
  return (
    <section className="rounded-xl border border-line bg-panel p-4">
      <h2 className="text-sm font-semibold">{title}</h2>
      <p className="mb-3 text-xs text-muted">{hint}</p>
      {children}
    </section>
  );
}

function ChipEditor({
  values,
  onChange,
  placeholder,
  tone = "accent",
}: {
  values: string[];
  onChange: (v: string[]) => void;
  placeholder: string;
  tone?: "accent" | "err";
}) {
  const [draft, setDraft] = useState("");
  const add = () => {
    const v = draft.trim();
    if (v && !values.includes(v)) onChange([...values, v]);
    setDraft("");
  };
  const chip = tone === "accent" ? "bg-accent-soft text-accent" : "bg-err-soft text-err";
  return (
    <div className="flex flex-wrap items-center gap-2">
      {values.map((v) => (
        <span key={v} className={`inline-flex items-center gap-1 rounded-md px-2 py-1 text-xs ${chip}`}>
          {v}
          <button onClick={() => onChange(values.filter((x) => x !== v))} aria-label={`Remove ${v}`}>
            <X className="size-3" />
          </button>
        </span>
      ))}
      <input
        value={draft}
        onChange={(e) => setDraft(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === "Enter") {
            e.preventDefault();
            add();
          }
        }}
        onBlur={add}
        placeholder={placeholder}
        className="min-w-40 flex-1 bg-transparent text-sm outline-none placeholder:text-muted"
      />
    </div>
  );
}

export default function PlanPage() {
  const wfId = Number(useParams<{ id: string }>().id);
  const router = useRouter();
  const [wf, setWf] = useState<Workflow | null>(null);
  const [intent, setIntent] = useState<Intent | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [starting, setStarting] = useState(false);

  useEffect(() => {
    api
      .workflow(wfId)
      .then((w) => {
        setWf(w);
        setIntent(w.intent);
      })
      .catch((e) => setError(e.message));
  }, [wfId]);

  if (!intent) {
    return error ? (
      <p className="rounded-lg border border-err bg-err-soft p-4 text-sm text-err">{error}</p>
    ) : (
      <div className="h-96 animate-pulse rounded-xl border border-line bg-panel" />
    );
  }

  const set = (patch: Partial<Intent>) => setIntent({ ...intent, ...patch });
  const setField = (i: number, patch: Partial<IntentField>) =>
    set({ fields: intent.fields.map((f, j) => (j === i ? { ...f, ...patch } : f)) });

  const run = async () => {
    setStarting(true);
    setError(null);
    try {
      const cleaned: Intent = {
        ...intent,
        fields: intent.fields.filter((f) => f.name.trim()),
        queries: intent.queries.filter((q) => q.trim()),
      };
      await api.updateWorkflow(wfId, cleaned);
      const { run_id } = await api.runWorkflow(wfId, "live");
      router.push(`/runs/${run_id}`);
    } catch (e) {
      setError((e as Error).message);
      setStarting(false);
    }
  };

  return (
    <div className="mx-auto max-w-4xl space-y-4">
      <div>
        <p className="text-xs uppercase tracking-wide text-muted">Review the plan</p>
        <h1 className="mt-1 text-xl font-semibold tracking-tight">{wf?.prompt}</h1>
        <p className="mt-1 text-sm text-muted">
          Scout turned your request into this plan. Edit anything, then run it.
        </p>
      </div>

      <Section title="What is one row?" hint="The kind of thing each row in the dataset describes.">
        <input className={input} value={intent.entity} onChange={(e) => set({ entity: e.target.value })} />
      </Section>

      <Section
        title="Fields"
        hint="The columns to extract. The first field identifies a row and is always required."
      >
        <div className="space-y-2">
          <div className="hidden grid-cols-[1fr_120px_80px_2fr_32px] gap-2 px-1 text-xs text-muted sm:grid">
            <span>Name</span><span>Type</span><span>Required</span><span>What to extract</span><span />
          </div>
          {intent.fields.map((f, i) => (
            <div key={i} className="grid grid-cols-2 gap-2 sm:grid-cols-[1fr_120px_80px_2fr_32px] sm:items-center">
              <input
                className={`${input} font-mono`}
                value={f.name}
                onChange={(e) => setField(i, { name: e.target.value })}
                aria-label="Field name"
              />
              <select
                className={input}
                value={f.type}
                onChange={(e) => setField(i, { type: e.target.value })}
                aria-label="Field type"
              >
                {FIELD_TYPES.map((t) => <option key={t}>{t}</option>)}
              </select>
              <label className="flex items-center gap-2 text-sm">
                <input
                  type="checkbox"
                  checked={i === 0 || f.required}
                  disabled={i === 0}
                  onChange={(e) => setField(i, { required: e.target.checked })}
                  className="accent-[var(--accent)]"
                />
                <span className="sm:hidden">Required</span>
              </label>
              <input
                className={`${input} col-span-2 sm:col-span-1`}
                value={f.description}
                onChange={(e) => setField(i, { description: e.target.value })}
                aria-label="Field description"
              />
              <button
                onClick={() => set({ fields: intent.fields.filter((_, j) => j !== i) })}
                disabled={intent.fields.length === 1}
                className="grid place-items-center text-muted hover:text-err disabled:opacity-30"
                aria-label="Remove field"
              >
                <Trash2 className="size-4" />
              </button>
            </div>
          ))}
          <button
            onClick={() =>
              set({ fields: [...intent.fields, { name: "", type: "string", required: false, description: "" }] })
            }
            className="inline-flex items-center gap-1 text-sm text-accent"
          >
            <Plus className="size-4" /> Add field
          </button>
        </div>
      </Section>

      <div className="grid gap-4 md:grid-cols-2">
        <Section title="Filters" hint="Every row must satisfy these. Press Enter to add one.">
          <ChipEditor values={intent.filters} onChange={(filters) => set({ filters })} placeholder="e.g. founded after 2020" />
        </Section>
        <Section title="How many rows?" hint="Scout keeps searching until it reaches this or runs out of sources.">
          <input
            type="number"
            min={5}
            max={50}
            className={input}
            value={intent.target_count}
            onChange={(e) => set({ target_count: Number(e.target.value) })}
          />
        </Section>
      </div>

      <Section title="Search queries" hint="Scout runs these to discover candidate sources.">
        <div className="space-y-2">
          {intent.queries.map((q, i) => (
            <div key={i} className="flex gap-2">
              <input
                className={input}
                value={q}
                onChange={(e) => set({ queries: intent.queries.map((x, j) => (j === i ? e.target.value : x)) })}
                aria-label={`Query ${i + 1}`}
              />
              <button
                onClick={() => set({ queries: intent.queries.filter((_, j) => j !== i) })}
                disabled={intent.queries.length === 1}
                className="text-muted hover:text-err disabled:opacity-30"
                aria-label="Remove query"
              >
                <Trash2 className="size-4" />
              </button>
            </div>
          ))}
          <button
            onClick={() => set({ queries: [...intent.queries, ""] })}
            className="inline-flex items-center gap-1 text-sm text-accent"
          >
            <Plus className="size-4" /> Add query
          </button>
        </div>
      </Section>

      <Section
        title="Blocked domains"
        hint="Never collect from these. Social networks and login-only sites are always blocked, and robots.txt is always respected."
      >
        <ChipEditor
          values={intent.blocked_domains}
          onChange={(blocked_domains) => set({ blocked_domains })}
          placeholder="e.g. example.com"
          tone="err"
        />
      </Section>

      {error && <p className="rounded-lg border border-err bg-err-soft p-3 text-sm text-err">{error}</p>}

      <div className="sticky bottom-0 -mx-4 flex justify-end border-t border-line bg-bg/90 px-4 py-3 backdrop-blur">
        <button
          onClick={run}
          disabled={starting}
          className="inline-flex items-center gap-2 rounded-lg bg-accent px-5 py-2.5 text-sm font-medium text-white disabled:opacity-50"
        >
          {starting ? <Loader2 className="size-4 animate-spin" /> : <ArrowRight className="size-4" />}
          Run workflow
        </button>
      </div>
    </div>
  );
}
