"use client";

/** API readiness as an explicit state machine.
 *
 * The API runs on a free plan that sleeps when idle, so "not answering yet" and "broken" are different situations and
 * must look different. A single indefinite spinner told the investigator nothing and a single failed probe declared the
 * service down while it was merely waking.
 *
 * States: checking (first probe in flight) · waking (still no answer after a few seconds, which is what a cold start
 * looks like) · ready · degraded (answers, but reports a subsystem problem) · auth_required (401/403) ·
 * timed_out (gave up after the budget; retry is offered) · unavailable (answered with a server error).
 *
 * Probes are retried with bounded exponential backoff plus jitter, one at a time, and never while the tab is hidden.
 */
import { useCallback, useEffect, useRef, useState } from "react";

export type ApiState = "checking" | "waking" | "ready" | "degraded" | "auth_required" | "timed_out" | "unavailable";

export const API_STATE_LABEL: Record<ApiState, string> = {
  checking: "Checking API",
  waking: "API waking",
  ready: "API ready",
  degraded: "API degraded",
  auth_required: "Sign in required",
  timed_out: "API not responding",
  unavailable: "API unavailable",
};

export const API_STATE_DETAIL: Record<ApiState, string> = {
  checking: "Contacting the analysis API.",
  waking: "The analysis API is starting. Free-plan services sleep when idle and can take up to a minute to answer the first request.",
  ready: "The analysis API answered and reports its database and migrations healthy.",
  degraded: "The analysis API answered but reports a subsystem problem. Some screens may be incomplete.",
  auth_required: "The session is not accepted. Sign in again to continue.",
  timed_out: "No answer within the time budget. Your work on this page is kept; retry when ready.",
  unavailable: "The analysis API returned an error. Retry, or try again shortly.",
};

const WAKING_AFTER_MS = 3_000;   // a cold start looks like this
const BUDGET_MS = 90_000;        // total time before we stop retrying and offer the decision to the person
const PROBE_TIMEOUT_MS = 20_000;
const BACKOFF_MS = [1_000, 2_000, 4_000, 8_000, 12_000];

const jitter = (ms: number) => Math.round(ms * (0.75 + Math.random() * 0.5));

export function useApiState() {
  const [state, setState] = useState<ApiState>("checking");
  const [elapsed, setElapsed] = useState(0);
  const [detail, setDetail] = useState<Record<string, unknown> | null>(null);
  const [attempt, setAttempt] = useState(0);
  const started = useRef(Date.now());
  const inFlight = useRef(false);          // one probe at a time: no duplicate wake requests
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const alive = useRef(true);

  const probe = useCallback(async function run(n: number) {
    if (!alive.current || inFlight.current) return;
    inFlight.current = true;
    const ctl = new AbortController();
    const cut = setTimeout(() => ctl.abort(), PROBE_TIMEOUT_MS);
    try {
      const res = await fetch("/api/proxy/health/ready", { cache: "no-store", credentials: "same-origin", signal: ctl.signal });
      if (!alive.current) return;
      if (res.status === 401 || res.status === 403) { setState("auth_required"); return; }
      if (res.ok) {
        const body = await res.json().catch(() => ({}));
        setDetail(body);
        // The API reports each subsystem. "ready" means nothing required is failing and nothing optional is missing;
        // anything else is named rather than smoothed over.
        setState(body?.status === "ready" ? "ready" : "degraded");
        return;
      }
      if (res.status >= 500) setState("unavailable");
    } catch {
      /* network error or probe timeout: treat as still waking until the budget runs out */
    } finally {
      clearTimeout(cut);
      inFlight.current = false;
    }
    if (!alive.current) return;
    const spent = Date.now() - started.current;
    if (spent >= BUDGET_MS) { setState("timed_out"); return; }
    setState((s) => (s === "ready" || s === "degraded" || s === "auth_required" ? s : "waking"));
    const wait = jitter(BACKOFF_MS[Math.min(n, BACKOFF_MS.length - 1)]);
    timer.current = setTimeout(() => run(n + 1), wait);
  }, []);

  const retry = useCallback(() => {
    if (timer.current) clearTimeout(timer.current);
    started.current = Date.now();
    setElapsed(0);
    setState("checking");
    setAttempt((a) => a + 1);
  }, []);

  useEffect(() => {
    alive.current = true;
    started.current = Date.now();
    void probe(0);
    const tick = setInterval(() => {
      setState((s) => {
        if (s === "checking" && Date.now() - started.current > WAKING_AFTER_MS) return "waking";
        return s;
      });
      setElapsed(Math.round((Date.now() - started.current) / 1000));
    }, 1000);
    return () => { alive.current = false; clearInterval(tick); if (timer.current) clearTimeout(timer.current); };
  }, [probe, attempt]);

  const settled = state === "ready" || state === "degraded" || state === "auth_required";
  const unavailable: string[] = (detail?.optional_unavailable as string[] | undefined) ?? [];
  const failed: string[] = (detail?.required_failed as string[] | undefined) ?? [];
  const named = [...failed, ...unavailable].map((k) => k.replace(/_/g, " ")).join(", ");
  const label = state === "degraded" && named ? `API degraded: ${named} unavailable` : API_STATE_LABEL[state];
  const subsystems = (detail?.subsystems as Record<string, { status: string; required: boolean; note?: string }>) || {};
  const notes = Object.entries(subsystems).filter(([, v]) => v.note).map(([k, v]) => `${k.replace(/_/g, " ")}: ${v.note}`);
  const description = notes.length ? `${API_STATE_DETAIL[state]} ${notes.join(" ")}` : API_STATE_DETAIL[state];
  return { state, elapsed: settled ? 0 : elapsed, detail, retry, label, description, subsystems };
}
