import Link from "next/link";
import type { ReactNode } from "react";

import { labelFor } from "@/config/lead-options";
import type { CrmSyncStatus, LeadStatus, LeadTemperature } from "@/types/lead";

/**
 * Display primitives for the dashboard.
 *
 * Everything here is presentation: turning a stored value into a colour and a
 * label. Note what is absent — nothing computes a temperature or decides which
 * transitions are legal. Those come from the backend, because they are
 * decisions and the frontend does not make decisions.
 */

export function StatCard({
  label,
  value,
  tone = "neutral",
  hint,
}: {
  label: string;
  value: number | string;
  tone?: "neutral" | "hot" | "warm" | "cold" | "alert";
  hint?: string;
}) {
  const toneClasses: Record<string, string> = {
    neutral: "text-ink",
    hot: "text-accent",
    warm: "text-ink",
    cold: "text-ink-muted",
    alert: "text-accent",
  };
  return (
    <div className="border border-line bg-paper-raised p-5">
      <p className="text-xs uppercase tracking-wider text-ink-muted">{label}</p>
      <p
        className={`mt-3 font-display text-3xl font-semibold tabular-nums ${toneClasses[tone]}`}
      >
        {value}
      </p>
      {hint ? <p className="mt-1.5 text-xs text-ink-muted">{hint}</p> : null}
    </div>
  );
}

const TEMPERATURE_STYLES: Record<LeadTemperature, string> = {
  hot: "border-accent/40 bg-accent/10 text-accent",
  warm: "border-line-strong bg-paper text-ink",
  cold: "border-line bg-paper text-ink-muted",
};

export function TemperatureBadge({
  temperature,
  score,
}: {
  temperature: LeadTemperature | null;
  score: number | null;
}) {
  if (!temperature) {
    return <span className="text-xs text-ink-muted">unscored</span>;
  }
  return (
    <span
      className={`inline-flex items-center gap-2 border px-2.5 py-1 text-xs font-medium uppercase tracking-wide ${TEMPERATURE_STYLES[temperature]}`}
    >
      {temperature}
      {score !== null ? <span className="tabular-nums font-mono">{score}</span> : null}
    </span>
  );
}

const STATUS_LABELS: Record<LeadStatus, string> = {
  new: "New",
  qualified: "Qualified",
  contacted: "Contacted",
  booked: "Booked",
  won: "Won",
  lost: "Lost",
  disqualified: "Disqualified",
};

export function StatusBadge({ status }: { status: LeadStatus }) {
  const emphasis =
    status === "won"
      ? "border-ink bg-ink text-ink-inverse"
      : status === "lost" || status === "disqualified"
        ? "border-line bg-paper text-ink-muted"
        : "border-line-strong bg-paper text-ink";
  return (
    <span className={`inline-flex border px-2.5 py-1 text-xs font-medium ${emphasis}`}>
      {STATUS_LABELS[status] ?? status}
    </span>
  );
}

const SYNC_LABELS: Record<CrmSyncStatus, { label: string; className: string }> = {
  synced: { label: "Synced", className: "text-ink" },
  pending: { label: "Pending", className: "text-ink-muted" },
  // "Skipped" is a normal state, not a warning: it is what you see when no
  // HubSpot token is configured, or for demo leads.
  skipped: { label: "Skipped", className: "text-ink-muted" },
  failed: { label: "Failed", className: "text-accent font-medium" },
};

export function SyncBadge({ status }: { status: CrmSyncStatus }) {
  const entry = SYNC_LABELS[status] ?? { label: status, className: "text-ink-muted" };
  return <span className={`text-xs ${entry.className}`}>{entry.label}</span>;
}

export function DemoBadge() {
  return (
    <span
      className="inline-flex border border-line-strong px-1.5 py-0.5 text-[10px] uppercase tracking-wider text-ink-muted"
      title="Synthetic lead created by the demo generator"
    >
      demo
    </span>
  );
}

export function Field({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div>
      <dt className="text-xs uppercase tracking-wider text-ink-muted">{label}</dt>
      <dd className="mt-1.5 text-sm break-words">{children ?? "—"}</dd>
    </div>
  );
}

export function EnumField({ label, value }: { label: string; value: string | null }) {
  return <Field label={label}>{labelFor(value)}</Field>;
}

export function SectionCard({
  title,
  action,
  children,
}: {
  title: string;
  action?: ReactNode;
  children: ReactNode;
}) {
  return (
    <section className="border border-line bg-paper-raised">
      <header className="flex items-center justify-between gap-4 border-b border-line px-6 py-4">
        <h2 className="font-display text-base font-semibold">{title}</h2>
        {action}
      </header>
      <div className="px-6 py-5">{children}</div>
    </section>
  );
}

export function EmptyState({
  title,
  description,
  action,
}: {
  title: string;
  description: string;
  action?: ReactNode;
}) {
  return (
    <div className="border border-dashed border-line-strong px-8 py-16 text-center">
      <p className="font-display text-title font-semibold">{title}</p>
      <p className="mx-auto mt-3 max-w-md text-sm leading-relaxed text-ink-muted">
        {description}
      </p>
      {action ? <div className="mt-8 flex justify-center">{action}</div> : null}
    </div>
  );
}

/**
 * A failure the operator can act on.
 *
 * Shown instead of a blank page when the backend is unreachable — the single
 * most likely thing to go wrong in local development, and the thing a stack
 * trace in a terminal does not tell you.
 */
export function ErrorState({ title, detail }: { title: string; detail: string }) {
  return (
    <div className="border border-accent/40 bg-accent/5 px-8 py-10">
      <p className="font-display text-title font-semibold">{title}</p>
      <p className="mt-3 max-w-xl text-sm leading-relaxed text-ink-muted">{detail}</p>
    </div>
  );
}

export function formatDate(value: string): string {
  const date = new Date(value);
  return new Intl.DateTimeFormat("en-GB", {
    day: "2-digit",
    month: "short",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  }).format(date);
}

export function formatRelative(value: string): string {
  const seconds = (Date.now() - new Date(value).getTime()) / 1000;
  const units: [Intl.RelativeTimeFormatUnit, number][] = [
    ["day", 86400],
    ["hour", 3600],
    ["minute", 60],
  ];
  const formatter = new Intl.RelativeTimeFormat("en-GB", { numeric: "auto" });
  for (const [unit, size] of units) {
    if (Math.abs(seconds) >= size) {
      return formatter.format(-Math.round(seconds / size), unit);
    }
  }
  return "just now";
}

export function DashboardLink({ href, children }: { href: string; children: ReactNode }) {
  return (
    <Link href={href} className="text-sm underline underline-offset-4 hover:text-accent">
      {children}
    </Link>
  );
}
