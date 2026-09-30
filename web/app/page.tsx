"use client";

import { ArrowRight, Loader2 } from "lucide-react";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { api } from "@/lib/api";

const EXAMPLES = [
  "Find AI startups in Bangalore with their funding stage, founding year, founders and website",
  "List upcoming developer conferences in India in 2026 with dates, city, and sponsorship contact",
  "Find D2C skincare brands in India with their founders, website, and Instagram handle",
  "Open remote frontend developer jobs posted this month with company, salary range, and apply link",
];

export default function Home() {
  const router = useRouter();
  const [prompt, setPrompt] = useState("");
  const [busy, setBusy] = useState<"plan" | "demo" | null>(null);
  const [error, setError] = useState<string | null>(null);

  const start = async () => {
    if (!prompt.trim() || busy) return;
    setBusy("plan");
    setError(null);
    try {
      const wf = await api.createWorkflow(prompt);
      router.push(`/plan/${wf.id}`);
    } catch (e) {
      setError((e as Error).message);
      setBusy(null);
    }
  };

  const demo = async () => {
    if (busy) return;
    setBusy("demo");
    try {
      const { run_id } = await api.createDemoRun(prompt.trim() || EXAMPLES[0]);
      router.push(`/runs/${run_id}`);
    } catch (e) {
      setError((e as Error).message);
      setBusy(null);
    }
  };

  return (
    <div className="mx-auto max-w-3xl pt-12 sm:pt-20">
      <h1 className="text-center text-3xl sm:text-5xl font-semibold tracking-tight">
        Describe the data you need.
      </h1>
      <p className="mt-3 text-center text-muted">
        Scout designs the workflow, collects from permitted sources, and proves every value with a quote.
      </p>

      <div className="mt-8 rounded-2xl border border-line bg-panel p-3 shadow-sm focus-within:border-accent">
        <textarea
          value={prompt}
          onChange={(e) => setPrompt(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) start();
          }}
          rows={3}
          placeholder="e.g. Find AI startups in Bangalore hiring ML engineers, with funding stage and careers page"
          className="w-full resize-none bg-transparent px-2 py-1 text-base outline-none placeholder:text-muted"
        />
        <div className="flex items-center justify-between gap-3 px-1">
          <span className="text-xs text-muted">Ctrl + Enter to plan</span>
          <div className="flex items-center gap-2">
            <button
              onClick={demo}
              disabled={!!busy}
              title="Scripted run with fictional data, no network needed"
              className="rounded-lg px-3 py-2 text-sm text-muted hover:text-fg disabled:opacity-40"
            >
              {busy === "demo" ? "Starting…" : "Demo run"}
            </button>
            <button
              onClick={start}
              disabled={!prompt.trim() || !!busy}
              className="inline-flex items-center gap-2 rounded-lg bg-accent px-4 py-2 text-sm font-medium text-white disabled:opacity-40"
            >
              {busy === "plan" ? <Loader2 className="size-4 animate-spin" /> : <ArrowRight className="size-4" />}
              {busy === "plan" ? "Planning…" : "Plan dataset"}
            </button>
          </div>
        </div>
      </div>
      {error && <p className="mt-3 text-sm text-err">{error}</p>}

      <div className="mt-6 grid gap-2 sm:grid-cols-2">
        {EXAMPLES.map((ex) => (
          <button
            key={ex}
            onClick={() => setPrompt(ex)}
            className="rounded-xl border border-line bg-panel px-4 py-3 text-left text-sm text-muted hover:border-accent hover:text-fg"
          >
            {ex}
          </button>
        ))}
      </div>
    </div>
  );
}
