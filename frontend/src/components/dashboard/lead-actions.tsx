"use client";

/**
 * The interactive controls on the lead detail page.
 *
 * The one thing worth understanding here: the status buttons are rendered from
 * `allowedNextStatuses`, which the BACKEND supplied — it comes from the domain's
 * lifecycle table. The UI therefore cannot offer a transition the entity would
 * reject, and adding a new lifecycle rule updates the buttons automatically
 * with no frontend change.
 *
 * The alternative — hardcoding the button list here — means the UI and the
 * rules drift the first time someone edits the state machine, and the symptom
 * is a user clicking a button that errors.
 *
 * These call the same-origin `/api/internal/*` proxy rather than the backend
 * directly, because the internal secret must stay on the server.
 */

import { useRouter } from "next/navigation";
import { useState, useTransition } from "react";

import { Icon } from "@/components/ui/icon";
import { labelFor } from "@/config/lead-options";
import type { LeadStatus, SalesBrief } from "@/types/lead";

type ActionState = { kind: "idle" } | { kind: "error"; message: string };

async function callInternal(path: string, method: "POST" | "PATCH", body?: unknown) {
  const response = await fetch(`/api/internal/${path}`, {
    method,
    headers: { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  const text = await response.text();
  const parsed = text ? JSON.parse(text) : null;
  if (!response.ok) {
    throw new Error(parsed?.error?.message ?? `Request failed (${response.status})`);
  }
  return parsed;
}

export function LeadActions({
  leadId,
  allowedNextStatuses,
}: {
  leadId: string;
  allowedNextStatuses: LeadStatus[];
}) {
  const router = useRouter();
  const [pending, startTransition] = useTransition();
  const [busy, setBusy] = useState<string | null>(null);
  const [state, setState] = useState<ActionState>({ kind: "idle" });

  async function run(label: string, work: () => Promise<unknown>) {
    setBusy(label);
    setState({ kind: "idle" });
    try {
      await work();
      // Re-fetch the Server Component so the timeline and badges reflect the
      // change, without a full page reload.
      startTransition(() => router.refresh());
    } catch (error) {
      setState({
        kind: "error",
        message: error instanceof Error ? error.message : "Something went wrong.",
      });
    } finally {
      setBusy(null);
    }
  }

  const disabled = pending || busy !== null;

  return (
    <div className="space-y-4">
      {allowedNextStatuses.length === 0 ? (
        <p className="text-sm text-ink-muted">
          This lead is in a terminal state. Reopening it would mean creating a new lead,
          which keeps the history of what actually happened intact.
        </p>
      ) : (
        <div className="flex flex-wrap gap-2">
          {allowedNextStatuses.map((status) => (
            <button
              key={status}
              type="button"
              disabled={disabled}
              onClick={() =>
                run(status, () =>
                  callInternal(`dashboard/leads/${leadId}/status`, "PATCH", { status }),
                )
              }
              className="inline-flex min-h-touch items-center gap-2 rounded-full border border-line-control px-4 text-sm transition-colors duration-instant hover:border-ink disabled:cursor-not-allowed disabled:opacity-50"
            >
              {busy === status ? "Saving…" : `Mark ${labelFor(status)}`}
            </button>
          ))}
        </div>
      )}

      <div className="flex flex-wrap gap-2 border-t border-line pt-4">
        <button
          type="button"
          disabled={disabled}
          onClick={() =>
            run("rescore", () =>
              callInternal(`dashboard/leads/${leadId}/rescore`, "POST"),
            )
          }
          className="inline-flex min-h-touch items-center gap-2 rounded-full border border-line-control px-4 text-sm transition-colors duration-instant hover:border-ink disabled:cursor-not-allowed disabled:opacity-50"
          title="Recompute the score under the current rules"
        >
          <Icon name="refresh" size="sm" />
          {busy === "rescore" ? "Rescoring…" : "Rescore"}
        </button>
        <button
          type="button"
          disabled={disabled}
          onClick={() =>
            run("dispatch", () => callInternal("admin/outbox/dispatch", "POST"))
          }
          className="inline-flex min-h-touch items-center gap-2 rounded-full border border-line-control px-4 text-sm transition-colors duration-instant hover:border-ink disabled:cursor-not-allowed disabled:opacity-50"
          title="Run one outbox dispatch pass now instead of waiting for the poll interval"
        >
          <Icon name="arrow-right" size="sm" />
          {busy === "dispatch" ? "Dispatching…" : "Run outbox dispatch"}
        </button>
      </div>

      {/* aria-live so the outcome is announced, not only rendered — the
          button that triggered it may already have lost focus. */}
      <p aria-live="polite" className="sr-only">
        {busy ? `Working on ${busy}…` : ""}
      </p>
      {state.kind === "error" ? (
        <p role="alert" className="flex items-center gap-2 text-sm text-accent">
          <Icon name="alert" size="sm" />
          {state.message}
        </p>
      ) : null}
    </div>
  );
}

/**
 * The AI sales brief control.
 *
 * Separated from the status actions because its failure mode is different and
 * worth handling explicitly: with no ANTHROPIC_API_KEY the backend returns 503
 * with a clear message, and this shows that message rather than pretending the
 * feature is broken — or worse, inventing a brief.
 */
export function SalesBriefAction({
  leadId,
  existing,
}: {
  leadId: string;
  existing: SalesBrief | null;
}) {
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function generate() {
    setBusy(true);
    setError(null);
    try {
      await callInternal(`dashboard/leads/${leadId}/sales-brief`, "POST");
      router.refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not generate a brief.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-3">
      <button
        type="button"
        onClick={generate}
        disabled={busy}
        className="inline-flex min-h-touch items-center gap-2 rounded-full border border-line-control px-4 text-sm transition-colors duration-instant hover:border-ink disabled:cursor-not-allowed disabled:opacity-50"
      >
        <Icon name="sparkles" size="sm" />
        {busy ? "Generating…" : existing ? "Regenerate brief" : "Generate AI brief"}
      </button>
      {error ? (
        <p role="alert" className="flex items-center gap-2 text-sm text-accent">
          <Icon name="alert" size="sm" />
          {error}
        </p>
      ) : null}
    </div>
  );
}
