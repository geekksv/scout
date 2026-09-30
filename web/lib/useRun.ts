"use client";

import { useEffect, useReducer } from "react";
import {
  api,
  type DataRecord,
  type Intent,
  type RunEvent,
  type RunStatus,
  type StepStatus,
} from "./api";
import { ensureAwake } from "./backend";

export interface StepState {
  status: StepStatus;
  message?: string;
  counts?: Record<string, number>;
  iteration?: number;
}

export interface LogLine { seq: number; ts: string; step: string | null; level: string; message: string }

export interface RunState {
  status: RunStatus;
  error?: string;
  intent?: Intent;
  steps: Record<string, StepState>;
  loop: StepStatus; // gap-fill edge
  logs: LogLine[];
  rows: DataRecord[];
  stats: Record<string, number>;
  lastSeq: number;
  connected: boolean;
}

const initial: RunState = {
  status: "queued",
  steps: {},
  loop: "idle",
  logs: [],
  rows: [],
  stats: {},
  lastSeq: -1,
  connected: false,
};

type Action = { kind: "reset" } | { kind: "connected"; value: boolean } | { kind: "event"; evt: RunEvent };

function reduce(state: RunState, action: Action): RunState {
  if (action.kind === "reset") return initial;
  if (action.kind === "connected") return { ...state, connected: action.value };

  const { evt } = action;
  if (evt.seq <= state.lastSeq) return state; // replayed after a reconnect
  const s: RunState = { ...state, lastSeq: evt.seq };
  const p = evt.payload;

  switch (evt.type) {
    case "run":
      s.status = p.status as RunStatus;
      if (p.error) s.error = String(p.error);
      if (s.status !== "running") {
        // Nothing stays "running" once the run is over.
        s.steps = Object.fromEntries(
          Object.entries(s.steps).map(([k, v]) => [
            k,
            v.status === "running" ? { ...v, status: s.status === "done" ? "done" : "failed" } : v,
          ]),
        );
        if (s.loop === "running") s.loop = "done";
      }
      break;
    case "plan":
      s.intent = p.intent as Intent;
      break;
    case "step":
      if (evt.step === "gapfill") {
        s.loop = p.status as StepStatus;
      } else if (evt.step) {
        s.steps = {
          ...s.steps,
          [evt.step]: {
            ...s.steps[evt.step],
            status: p.status as StepStatus,
            message: (p.message as string) ?? s.steps[evt.step]?.message,
            counts: (p.counts as Record<string, number>) ?? s.steps[evt.step]?.counts,
            iteration: (p.iteration as number) ?? s.steps[evt.step]?.iteration,
          },
        };
      }
      break;
    case "log":
      s.logs = [
        ...s.logs,
        { seq: evt.seq, ts: evt.ts, step: evt.step, level: String(p.level), message: String(p.message) },
      ];
      break;
    case "row": {
      // The live pipeline re-sends a row whenever new evidence changes it.
      const rec = p.record as DataRecord;
      const i = s.rows.findIndex((r) => r.id === rec.id);
      s.rows = i === -1 ? [...s.rows, rec] : s.rows.map((r, j) => (j === i ? rec : r));
      break;
    }
    case "stats":
      s.stats = p as Record<string, number>;
      break;
  }
  return s;
}

export function useRun(runId: number) {
  const [state, dispatch] = useReducer(reduce, initial);

  useEffect(() => {
    if (!Number.isFinite(runId)) return;
    dispatch({ kind: "reset" });
    let es: EventSource | null = null;
    let cancelled = false;
    // Open the live stream only once the (possibly sleeping) server is awake.
    ensureAwake()
      .then(() => {
        if (cancelled) return;
        es = new EventSource(api.eventsUrl(runId));
        es.onopen = () => dispatch({ kind: "connected", value: true });
        es.onmessage = (m) => dispatch({ kind: "event", evt: JSON.parse(m.data) });
        es.addEventListener("end", () => {
          dispatch({ kind: "connected", value: false });
          es?.close();
        });
        es.onerror = () => dispatch({ kind: "connected", value: false });
      })
      .catch(() => {});
    return () => {
      cancelled = true;
      es?.close();
    };
  }, [runId]);

  return state;
}
