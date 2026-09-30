"use client";

import {
  ArrowRight,
  BadgeCheck,
  Briefcase,
  CalendarDays,
  FileSpreadsheet,
  Loader2,
  MousePointerClick,
  Quote,
  Rocket,
  Search,
  ShieldCheck,
  Sparkles,
  Workflow,
} from "lucide-react";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { api } from "@/lib/api";
import { useBackend } from "@/lib/backend";

const EXAMPLES = [
  { icon: Rocket, text: "Find AI startups in Bangalore with their funding stage, founding year, founders and website" },
  { icon: CalendarDays, text: "List upcoming developer conferences in India in 2026 with dates, city, and sponsorship contact" },
  { icon: Sparkles, text: "Find D2C skincare brands in India with their founders, website, and Instagram handle" },
  { icon: Briefcase, text: "Open remote frontend developer jobs posted this month with company, salary range, and apply link" },
];

const STEPS = [
  { icon: Workflow, title: "Plan", text: "AI turns your request into fields, filters and search queries you can edit." },
  { icon: Search, title: "Collect", text: "Searches the web, checks robots.txt, and reads only permitted pages." },
  { icon: Quote, title: "Prove", text: "Every value needs a verbatim quote from its page, or it is dropped." },
  { icon: BadgeCheck, title: "Verify", text: "Merges duplicates and cross-checks fields across independent sites." },
];

const PROOF_POINTS = [
  { icon: ShieldCheck, text: "robots.txt respected" },
  { icon: Quote, text: "No quote, no value" },
  { icon: MousePointerClick, text: "Click any cell for its evidence" },
  { icon: FileSpreadsheet, text: "CSV · XLSX · JSON export" },
];

export default function Home() {
  const router = useRouter();
  const backend = useBackend();
  const [prompt, setPrompt] = useState("");
  const [busy, setBusy] = useState<"plan" | "demo" | null>(null);
  const [error, setError] = useState<string | null>(null);
  const waking = backend.state === "waking" || backend.state === "checking";

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
    setError(null);
    try {
      const { run_id } = await api.createDemoRun(prompt.trim() || EXAMPLES[0].text);
      router.push(`/runs/${run_id}`);
    } catch (e) {
      setError((e as Error).message);
      setBusy(null);
    }
  };

  const planLabel = busy === "plan" ? (waking ? "Waiting for server…" : "Planning…") : "Plan dataset";

  return (
    <div className="mx-auto max-w-4xl pb-6 pt-8 sm:pt-16">
      <div className="flex justify-center">
        <span className="inline-flex items-center gap-2 rounded-full border border-line bg-panel/80 px-3 py-1 text-xs text-muted backdrop-blur">
          <span className="size-1.5 rounded-full bg-ok" />
          Source-backed web data · every cell proven by a quote
        </span>
      </div>
      <h1 className="mt-5 text-center text-4xl font-semibold tracking-tight sm:text-6xl">
        Describe the data. <br className="hidden sm:block" />
        <span className="brand-text">Scout proves every value.</span>
      </h1>
      <p className="mx-auto mt-4 max-w-2xl text-center text-base text-muted sm:text-lg">
        Ask in plain English. Scout designs the collection workflow, gathers data from permitted sources, and hands
        you a clean dataset where every cell links back to the sentence it came from.
      </p>

      <div className="brand-ring mt-9 rounded-2xl p-3 shadow-[0_20px_60px_-25px_var(--glow-1)]">
        <textarea
          value={prompt}
          onChange={(e) => setPrompt(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) start();
          }}
          rows={3}
          placeholder="e.g. Find AI startups in Bangalore with their funding stage, founding year and website"
          className="w-full resize-none bg-transparent px-2 py-1.5 text-base outline-none placeholder:text-muted/80"
          aria-label="Describe the data you need"
        />
        <div className="flex flex-wrap items-center justify-between gap-3 px-1">
          <span className="text-xs text-muted">Ctrl + Enter to plan</span>
          <div className="flex items-center gap-2">
            <button
              onClick={demo}
              disabled={!!busy}
              title="Scripted run with fictional data: instant, no AI quota needed"
              className="rounded-lg px-3 py-2 text-sm text-muted hover:bg-panel-2 hover:text-fg disabled:opacity-40"
            >
              {busy === "demo" ? "Starting…" : "Try a demo run"}
            </button>
            <button
              onClick={start}
              disabled={!prompt.trim() || !!busy}
              className="brand-gradient inline-flex items-center gap-2 rounded-lg px-4 py-2 text-sm font-semibold text-accent-fg shadow-sm transition hover:brightness-110 disabled:opacity-40"
            >
              {busy === "plan" ? <Loader2 className="size-4 animate-spin" /> : <ArrowRight className="size-4" />}
              {planLabel}
            </button>
          </div>
        </div>
      </div>
      {error && <p className="mt-3 rounded-lg border border-err bg-err-soft px-3 py-2 text-sm text-err">{error}</p>}

      <div className="mt-5 grid gap-2 sm:grid-cols-2">
        {EXAMPLES.map(({ icon: Icon, text }) => (
          <button
            key={text}
            onClick={() => setPrompt(text)}
            className={`group flex items-start gap-3 rounded-xl border bg-panel/80 px-4 py-3 text-left text-sm backdrop-blur transition hover:border-accent ${
              prompt === text ? "border-accent" : "border-line"
            }`}
          >
            <span className="grid size-7 shrink-0 place-items-center rounded-lg bg-accent-soft text-accent">
              <Icon className="size-4" />
            </span>
            <span className="text-muted group-hover:text-fg">{text}</span>
          </button>
        ))}
      </div>

      <section className="mt-14">
        <h2 className="text-center text-xs font-semibold uppercase tracking-[0.18em] text-muted">How it works</h2>
        <ol className="mt-5 grid gap-3 sm:grid-cols-4">
          {STEPS.map(({ icon: Icon, title, text }, i) => (
            <li key={title} className="card p-4">
              <div className="flex items-center gap-2">
                <span className="brand-gradient grid size-8 place-items-center rounded-lg text-accent-fg">
                  <Icon className="size-4" />
                </span>
                <span className="text-xs font-medium text-muted">0{i + 1}</span>
              </div>
              <h3 className="mt-3 font-semibold">{title}</h3>
              <p className="mt-1 text-sm leading-relaxed text-muted">{text}</p>
            </li>
          ))}
        </ol>
      </section>

      <ul className="mt-8 flex flex-wrap justify-center gap-x-6 gap-y-2 text-sm text-muted">
        {PROOF_POINTS.map(({ icon: Icon, text }) => (
          <li key={text} className="inline-flex items-center gap-2">
            <Icon className="size-4 text-accent" /> {text}
          </li>
        ))}
      </ul>
    </div>
  );
}
