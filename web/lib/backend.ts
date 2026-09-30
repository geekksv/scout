"use client";

/**
 * Free hosting puts the API to sleep when idle; the first request can take up to
 * a minute while it wakes. Every API call awaits ensureAwake(), which pings
 * /api/health until the server answers, and components can show that state.
 */

import { useSyncExternalStore } from "react";

export type BackendState = "checking" | "waking" | "ready" | "down";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
const WAKE_TIMEOUT_MS = 120_000;
const KEEPALIVE_MS = 8 * 60_000; // hosts typically sleep after ~15 idle minutes

let state: BackendState = "checking";
let since = Date.now();
let pending: Promise<void> | null = null;
let keepAlive: ReturnType<typeof setInterval> | null = null;
const listeners = new Set<() => void>();

function set(next: BackendState) {
  if (next === state) return;
  state = next;
  since = Date.now();
  listeners.forEach((l) => l());
}

async function ping(timeoutMs: number): Promise<boolean> {
  const ctrl = new AbortController();
  const t = setTimeout(() => ctrl.abort(), timeoutMs);
  try {
    const res = await fetch(`${API_URL}/api/health`, { signal: ctrl.signal, cache: "no-store" });
    return res.ok;
  } catch {
    return false;
  } finally {
    clearTimeout(t);
  }
}

function startKeepAlive() {
  if (keepAlive || typeof window === "undefined") return;
  keepAlive = setInterval(() => {
    if (document.visibilityState === "visible") void ping(10_000);
  }, KEEPALIVE_MS);
}

/** Resolves once the API answers; rejects if it stays unreachable. */
export function ensureAwake(): Promise<void> {
  if (state === "ready") return Promise.resolve();
  if (pending) return pending;
  pending = (async () => {
    const start = Date.now();
    // A quick first try: an awake server answers in well under a second.
    if (await ping(4_000)) {
      set("ready");
      startKeepAlive();
      return;
    }
    set("waking");
    while (Date.now() - start < WAKE_TIMEOUT_MS) {
      if (await ping(15_000)) {
        set("ready");
        startKeepAlive();
        return;
      }
      await new Promise((r) => setTimeout(r, 2_500));
    }
    set("down");
    throw new Error("The server did not respond. Please try again in a minute.");
  })().finally(() => {
    pending = null;
  });
  return pending;
}

/** Call after a request failed at the network level: the server may have gone back to sleep. */
export function markUnreachable() {
  if (state === "ready") set("checking");
}

export function retryWake() {
  set("checking");
  void ensureAwake().catch(() => {});
}

function subscribe(l: () => void) {
  listeners.add(l);
  return () => listeners.delete(l);
}

export function useBackend(): { state: BackendState; since: number } {
  const s = useSyncExternalStore(subscribe, () => state, () => "checking" as BackendState);
  return { state: s, since };
}
