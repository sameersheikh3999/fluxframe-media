import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";

import { LeadActions, SalesBriefAction } from "@/components/dashboard/lead-actions";
import {
  DemoBadge,
  EnumField,
  ErrorState,
  Field,
  SectionCard,
  StatusBadge,
  SyncBadge,
  TemperatureBadge,
  formatDate,
} from "@/components/dashboard/primitives";
import { labelFor } from "@/config/lead-options";
import { BackendError, getLead } from "@/lib/api-server";
import type { LeadDetail } from "@/types/lead";

export const metadata: Metadata = { title: "Lead" };
export const dynamic = "force-dynamic";

type LoadResult =
  | { kind: "ok"; lead: LeadDetail }
  | { kind: "missing" }
  | { kind: "error"; detail: string };

/**
 * Fetch the lead, turning failures into data rather than exceptions.
 *
 * Keeping the try/catch out of the component body means no JSX is constructed
 * inside a catch block — React's lint rules flag that, and rightly: throwing
 * during render is what error boundaries are for, and mixing the two makes the
 * failure path hard to follow.
 */
async function load(id: string): Promise<LoadResult> {
  try {
    return { kind: "ok", lead: await getLead(id) };
  } catch (error) {
    if (error instanceof BackendError && error.status === 404) {
      return { kind: "missing" };
    }
    return {
      kind: "error",
      detail: error instanceof Error ? error.message : "Unexpected error.",
    };
  }
}

/**
 * One lead, in full.
 *
 * The centrepiece is the score breakdown: the stored explanation of exactly why
 * this lead scored what it did, component by component. That is the payoff of
 * persisting `score_breakdown` — six months and two rule changes later, the
 * number attached to this lead is still explainable.
 */
export default async function LeadDetailPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  const result = await load(id);

  if (result.kind === "missing") notFound();

  if (result.kind === "error") {
    return (
      <div className="mx-auto w-full max-w-3xl px-6 py-16 sm:px-8">
        <ErrorState title="Could not load this lead" detail={result.detail} />
      </div>
    );
  }

  const lead = result.lead;
  const breakdown = lead.score_breakdown;

  return (
    <div className="mx-auto w-full max-w-6xl px-6 py-10 sm:px-8">
      <Link
        href="/dashboard/leads"
        className="text-sm text-ink-muted underline underline-offset-4 hover:text-ink"
      >
        ← All leads
      </Link>

      <header className="mt-6 flex flex-wrap items-start justify-between gap-6 border-b border-line pb-8">
        <div>
          <h1 className="flex flex-wrap items-center gap-3 font-display text-headline font-semibold">
            {lead.first_name} {lead.last_name}
            {lead.is_demo ? <DemoBadge /> : null}
          </h1>
          <p className="mt-2 text-lead text-ink-muted">{lead.company_name}</p>
          <p className="mt-1 text-sm text-ink-muted">
            Captured {formatDate(lead.created_at)} · source {labelFor(lead.source)}
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-3">
          <TemperatureBadge temperature={lead.temperature} score={lead.score} />
          <StatusBadge status={lead.status} />
        </div>
      </header>

      <div className="mt-8 grid gap-6 lg:grid-cols-[minmax(0,2fr)_minmax(0,1fr)]">
        <div className="space-y-6">
          <SectionCard title="Contact">
            <dl className="grid gap-5 sm:grid-cols-2">
              <Field label="Email">
                <a
                  href={`mailto:${lead.email}`}
                  className="underline underline-offset-4 hover:text-accent"
                >
                  {lead.email}
                </a>
              </Field>
              <Field label="Phone">{lead.phone ?? "—"}</Field>
              <Field label="Company">{lead.company_name}</Field>
              <Field label="Website">
                {lead.website ? (
                  <a
                    href={lead.website}
                    target="_blank"
                    rel="noreferrer noopener"
                    className="underline underline-offset-4 hover:text-accent"
                  >
                    {lead.website}
                  </a>
                ) : (
                  "—"
                )}
              </Field>
            </dl>
          </SectionCard>

          <SectionCard title="Qualification">
            <dl className="grid gap-5 sm:grid-cols-2">
              <EnumField label="Industry" value={lead.industry} />
              <EnumField label="Monthly revenue" value={lead.monthly_revenue} />
              <EnumField label="Marketing budget" value={lead.monthly_marketing_budget} />
              <EnumField label="Content volume" value={lead.content_volume} />
              <EnumField label="Primary goal" value={lead.primary_goal} />
              <EnumField label="Start timeline" value={lead.start_timeline} />
            </dl>
            {lead.message ? (
              <div className="mt-6 border-t border-line pt-5">
                <p className="text-xs uppercase tracking-wider text-ink-muted">
                  What they wrote
                </p>
                <p className="mt-2 whitespace-pre-wrap text-sm leading-relaxed">
                  {lead.message}
                </p>
              </div>
            ) : null}
          </SectionCard>

          {/* The reason score_breakdown is persisted at all. */}
          <SectionCard
            title="Why this score"
            action={
              breakdown ? (
                <span className="font-mono text-xs text-ink-muted">
                  rules {breakdown.version}
                </span>
              ) : null
            }
          >
            {breakdown ? (
              <>
                <table className="w-full border-collapse text-sm">
                  <tbody>
                    {breakdown.components.map((component) => (
                      <tr key={component.dimension} className="border-b border-line">
                        <td className="py-3 pr-4 align-top">
                          <span className="font-medium">
                            {labelFor(component.dimension)}
                          </span>
                          <div className="mt-1 text-xs text-ink-muted">
                            {component.reason}
                          </div>
                        </td>
                        <td className="py-3 pr-4 align-top text-xs text-ink-muted">
                          {labelFor(component.input_value)}
                        </td>
                        <td
                          className={`py-3 text-right align-top font-mono tabular-nums ${
                            component.points < 0 ? "text-accent" : ""
                          }`}
                        >
                          {component.points > 0 ? "+" : ""}
                          {component.points}
                        </td>
                      </tr>
                    ))}
                    <tr>
                      <td className="py-3 font-medium" colSpan={2}>
                        Total
                      </td>
                      <td className="py-3 text-right font-mono text-base font-semibold tabular-nums">
                        {breakdown.final_score}
                      </td>
                    </tr>
                  </tbody>
                </table>
                {breakdown.was_clamped ? (
                  <p className="mt-3 text-xs text-ink-muted">
                    Raw total was {breakdown.raw_total}, clamped into the 0–100 range.
                  </p>
                ) : null}
              </>
            ) : (
              <p className="text-sm text-ink-muted">This lead has not been scored.</p>
            )}
          </SectionCard>

          <SectionCard title="AI sales brief">
            {lead.sales_brief ? (
              <div className="space-y-5">
                <p className="text-sm leading-relaxed">{lead.sales_brief.summary}</p>

                <div>
                  <p className="text-xs uppercase tracking-wider text-ink-muted">
                    Pain points
                  </p>
                  <ul className="mt-2 space-y-1.5">
                    {lead.sales_brief.pain_points.map((point) => (
                      <li key={point} className="flex gap-3 text-sm">
                        <span className="text-accent" aria-hidden="true">
                          ·
                        </span>
                        {point}
                      </li>
                    ))}
                  </ul>
                </div>

                <div className="border-l-2 border-accent pl-4">
                  <p className="text-xs uppercase tracking-wider text-ink-muted">
                    Suggested opening
                  </p>
                  <p className="mt-2 text-sm italic">
                    &ldquo;{lead.sales_brief.opening_line}&rdquo;
                  </p>
                </div>

                <dl className="grid gap-5 border-t border-line pt-4 sm:grid-cols-3">
                  <Field label="Urgency">{lead.sales_brief.urgency}</Field>
                  <Field label="Lead with">
                    {labelFor(lead.sales_brief.suggested_service)}
                  </Field>
                  <Field label="Confidence">{lead.sales_brief.confidence}</Field>
                </dl>

                <p className="text-xs text-ink-muted">
                  Generated by {lead.sales_brief.model} on{" "}
                  {formatDate(lead.sales_brief.generated_at)}. The brief interprets the
                  prospect&rsquo;s own words; it never changes the deterministic score
                  above.
                </p>
              </div>
            ) : (
              <p className="text-sm text-ink-muted">
                No brief yet. Generating one asks a language model to interpret the
                prospect&rsquo;s message into pain points, urgency and an opening line.
                It requires <span className="font-mono text-xs">ANTHROPIC_API_KEY</span>{" "}
                to be configured on the backend.
              </p>
            )}
            <div className="mt-5 border-t border-line pt-4">
              <SalesBriefAction leadId={lead.id} existing={lead.sales_brief} />
            </div>
          </SectionCard>
        </div>

        <div className="space-y-6">
          <SectionCard title="Actions">
            <LeadActions
              leadId={lead.id}
              allowedNextStatuses={lead.allowed_next_statuses}
            />
          </SectionCard>

          <SectionCard title="CRM sync">
            <dl className="space-y-4">
              <Field label="Status">
                <SyncBadge status={lead.crm_sync_status} />
              </Field>
              <Field label="Contact ID">{lead.crm_contact_id ?? "—"}</Field>
              <Field label="Synced at">
                {lead.crm_synced_at ? formatDate(lead.crm_synced_at) : "—"}
              </Field>
              <Field label="Attempts">{lead.crm_sync_attempts}</Field>
              {lead.crm_sync_error ? (
                <Field label="Last error">
                  <span className="text-accent">{lead.crm_sync_error}</span>
                </Field>
              ) : null}
            </dl>
          </SectionCard>

          <SectionCard title="Attribution">
            <dl className="space-y-4">
              {Object.entries(lead.attribution).map(([key, value]) => (
                <Field key={key} label={key.replace(/_/g, " ")}>
                  {value ? (
                    <span className="break-all font-mono text-xs">{value}</span>
                  ) : (
                    "—"
                  )}
                </Field>
              ))}
            </dl>
          </SectionCard>

          <SectionCard title="Timeline">
            <ol className="space-y-5">
              {lead.activities.map((activity) => (
                <li key={activity.id} className="border-l-2 border-line pl-4">
                  <p className="text-sm">{activity.description}</p>
                  <p className="mt-1 text-xs text-ink-muted">
                    {formatDate(activity.occurred_at)} · {activity.actor}
                  </p>
                </li>
              ))}
            </ol>
          </SectionCard>
        </div>
      </div>
    </div>
  );
}
