"use client";

import { Loader2, RefreshCw, ServerCrash } from "lucide-react";
import { useEffect, useState } from "react";
import { ensureAwake, retryWake, useBackend } from "@/lib/backend";

/** Small status pill for the header. */
export function BackendPill() {
  const { state } = useBackend();
  const cfg = {
    checking: { dot: "bg-muted", label: "Connecting" },
    waking: { dot: "bg-warn animate-pulse", label: "Waking server" },
    ready: { dot: "bg-ok", label: "Online" },
    down: { dot: "bg-err", label: "Offline" },
  }[state];
  return (
    <span className="hidden items-center gap-1.5 rounded-full border border-line bg-panel px-2.5 py-1 text-xs text-muted sm:inline-flex">
      <span className={`size-1.5 rounded-full ${cfg.dot}`} />
      {cfg.label}
    </span>
  );
}

/** Full-width banner shown while the free-tier server wakes up. */
export function BackendBanner() {
  const { state, since } = useBackend();
  const [now, setNow] = useState(() => Date.now());

  useEffect(() => {
    // Wake the server as soon as anyone opens the site.
    void ensureAwake().catch(() => {});
  }, []);

  useEffect(() => {
    if (state !== "waking") return;
    const t = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(t);
  }, [state]);

  if (state === "waking") {
    const secs = Math.max(0, Math.round((now - since) / 1000));
    return (
      <div className="border-b border-line bg-warn-soft">
        <div className="mx-auto flex max-w-7xl items-center gap-3 px-4 py-2.5 text-sm">
          <Loader2 className="size-4 shrink-0 animate-spin text-warn" />
          <p className="min-w-0 flex-1">
            <b className="font-medium">Waking up the server…</b>{" "}
            <span className="text-muted">
              Free hosting sleeps when idle; this takes up to a minute. Anything you start now runs as soon as it&apos;s ready.
            </span>
          </p>
          <span className="shrink-0 tabular-nums text-xs text-muted">{secs}s</span>
        </div>
        <div className="relative h-0.5 overflow-hidden bg-line">
          <div className="shimmer absolute inset-y-0 w-1/3 brand-gradient" />
        </div>
      </div>
    );
  }
  if (state === "down") {
    return (
      <div className="border-b border-line bg-err-soft">
        <div className="mx-auto flex max-w-7xl items-center gap-3 px-4 py-2.5 text-sm">
          <ServerCrash className="size-4 shrink-0 text-err" />
          <p className="flex-1">The server isn&apos;t responding right now.</p>
          <button
            onClick={retryWake}
            className="inline-flex items-center gap-1.5 rounded-md border border-line bg-panel px-2.5 py-1 text-xs hover:border-accent"
          >
            <RefreshCw className="size-3" /> Try again
          </button>
        </div>
      </div>
    );
  }
  return null;
}
