"use client";

/**
 * The synthetic lead generator's controls.
 *
 * A Client Component because it is genuinely interactive, posting through the
 * same-origin `/api/internal/*` proxy so the shared secret stays on the server.
 *
 * The important thing this UI communicates — and the reason the copy below says
 * it explicitly — is that generated leads are NOT inserted directly into the
 * database. They go through the same `LeadService` as the public form, so they
 * are scored by the real scorer, write real activity rows and emit real outbox
 * events. A demo batch is a genuine end-to-end exercise of production code.
 */

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";

import { demoQualities, demoScenarios, industries } from "@/config/lead-options";
import type { GenerateDemoLeadsResponse } from "@/types/lead";

const COUNTS = [1, 5, 10] as const;

type Result =
  | { kind: "idle" }
  | { kind: "success"; data: GenerateDemoLeadsResponse }
  | { kind: "error"; message: string };

export function DemoGenerator() {
  const router = useRouter();
  const [count, setCount] = useState<number>(5);
  const [quality, setQuality] = useState("random");
  const [scenario, setScenario] = useState("normal_week");
  const [industry, setIndustry] = useState("");
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<Result>({ kind: "idle" });

  async function generate() {
    setBusy(true);
    setResult({ kind: "idle" });
    try {
      const response = await fetch("/api/internal/demo/leads", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          count,
          quality,
          scenario,
          industry: industry || null,
        }),
      });
      const body = await response.json();
      if (!response.ok) {
        throw new Error(body?.error?.message ?? "Generation failed.");
      }
      setResult({ kind: "success", data: body as GenerateDemoLeadsResponse });
      // The dashboard's counters are now stale.
      router.refresh();
    } catch (error) {
      setResult({
        kind: "error",
        message: error instanceof Error ? error.message : "Generation failed.",
      });
    } finally {
      setBusy(false);
    }
  }

  const selectClasses =
    "w-full border border-line-strong bg-paper-raised px-3 py-2.5 text-sm focus:outline-none focus-visible:border-ink";

  return (
    <div className="space-y-8">
      <div className="grid gap-6 sm:grid-cols-2">
        <div className="flex flex-col gap-2">
          <span className="text-xs uppercase tracking-wider text-ink-muted">
            How many
          </span>
          <div className="flex gap-2" role="group" aria-label="Number of leads">
            {COUNTS.map((option) => (
              <button
                key={option}
                type="button"
                aria-pressed={count === option}
                onClick={() => setCount(option)}
                className={`flex-1 border px-4 py-2.5 text-sm transition-colors ${
                  count === option
                    ? "border-ink bg-ink text-ink-inverse"
                    : "border-line-strong hover:border-ink"
                }`}
              >
                {option}
              </button>
            ))}
          </div>
        </div>

        <div className="flex flex-col gap-2">
          <label
            htmlFor="quality"
            className="text-xs uppercase tracking-wider text-ink-muted"
          >
            Quality mix
          </label>
          <select
            id="quality"
            value={quality}
            onChange={(event) => setQuality(event.target.value)}
            className={selectClasses}
          >
            {demoQualities.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </select>
        </div>

        <div className="flex flex-col gap-2">
          <label
            htmlFor="scenario"
            className="text-xs uppercase tracking-wider text-ink-muted"
          >
            Scenario
          </label>
          <select
            id="scenario"
            value={scenario}
            onChange={(event) => setScenario(event.target.value)}
            className={selectClasses}
          >
            {demoScenarios.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </select>
        </div>

        <div className="flex flex-col gap-2">
          <label
            htmlFor="industry"
            className="text-xs uppercase tracking-wider text-ink-muted"
          >
            Industry
          </label>
          <select
            id="industry"
            value={industry}
            onChange={(event) => setIndustry(event.target.value)}
            className={selectClasses}
          >
            <option value="">Realistic mix</option>
            {industries.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </select>
        </div>
      </div>

      <div className="flex flex-wrap items-center gap-4 border-t border-line pt-6">
        <button
          type="button"
          onClick={generate}
          disabled={busy}
          className="border border-ink bg-ink px-6 py-3 text-sm font-medium text-ink-inverse transition-colors hover:border-accent hover:bg-accent disabled:cursor-not-allowed disabled:opacity-60"
        >
          {busy ? "Generating…" : `Generate ${count} demo lead${count > 1 ? "s" : ""}`}
        </button>
        <p className="text-xs text-ink-muted">
          Maximum 10 per batch. Every address uses @example.com.
        </p>
      </div>

      {result.kind === "error" ? (
        <div
          role="alert"
          className="border border-accent bg-accent/5 px-5 py-4 text-sm"
        >
          {result.message}
        </div>
      ) : null}

      {result.kind === "success" ? (
        <div className="border border-line bg-paper-raised">
          <p className="border-b border-line px-5 py-3 text-sm font-medium">
            {result.data.message}
          </p>
          <ul className="divide-y divide-line">
            {result.data.generated.map((lead) => (
              <li key={lead.lead_id} className="flex flex-wrap gap-x-4 gap-y-1 px-5 py-3">
                <span className="text-sm font-medium">{lead.full_name}</span>
                <span className="text-sm text-ink-muted">{lead.company_name}</span>
                <span className="ml-auto font-mono text-xs text-ink-muted">
                  {lead.email}
                </span>
              </li>
            ))}
          </ul>
          <div className="border-t border-line px-5 py-3">
            <Link
              href="/dashboard/leads"
              className="text-sm underline underline-offset-4 hover:text-accent"
            >
              View them on the dashboard →
            </Link>
          </div>
        </div>
      ) : null}
    </div>
  );
}
