import type { Metadata } from "next";
import Link from "next/link";

import {
  DemoBadge,
  EmptyState,
  ErrorState,
  StatCard,
  StatusBadge,
  SyncBadge,
  TemperatureBadge,
  formatRelative,
} from "@/components/dashboard/primitives";
import { ButtonLink } from "@/components/ui/button-link";
import { labelFor } from "@/config/lead-options";
import {
  BackendError,
  getDashboardStats,
  listLeads,
  type LeadListQuery,
} from "@/lib/api-server";
import type { DashboardStats, LeadListResponse } from "@/types/lead";

export const metadata: Metadata = { title: "Leads" };

/**
 * The sales dashboard.
 *
 * A Server Component. It fetches on the server with the internal secret
 * attached and streams HTML — so the secret never enters a browser bundle, and
 * the page ships almost no JavaScript despite showing live data.
 *
 * `force-dynamic` because a cached dashboard is a lie: the reason you opened it
 * is to see what is there right now.
 */
export const dynamic = "force-dynamic";

const PAGE_SIZE = 25;

type SearchParams = Promise<Record<string, string | string[] | undefined>>;

type LoadResult =
  | { ok: true; stats: DashboardStats; leads: LeadListResponse }
  | { ok: false; detail: string };

function single(value: string | string[] | undefined): string | undefined {
  return Array.isArray(value) ? value[0] : value;
}

/**
 * Fetch everything the page needs, turning failures into data rather than
 * exceptions.
 *
 * Keeping the try/catch here — out of the component body — means no JSX is
 * constructed inside a catch block, which React's lint rules flag for good
 * reason: throwing during render is what error boundaries are for, and mixing
 * the two makes the failure path hard to follow.
 */
async function load(query: LeadListQuery): Promise<LoadResult> {
  try {
    // Both requests in parallel: the counters and the table are independent,
    // and waiting for one before starting the other would double the latency.
    const [stats, leads] = await Promise.all([
      getDashboardStats(),
      listLeads(query),
    ]);
    return { ok: true, stats, leads };
  } catch (error) {
    // A blank page tells an operator nothing. Name the likely cause instead.
    if (error instanceof BackendError) {
      if (error.status === 401) {
        return {
          ok: false,
          detail:
            "The backend rejected the internal secret. Check that INTERNAL_API_SECRET is identical on the frontend and the backend.",
        };
      }
      if (error.status === 503) {
        return {
          ok: false,
          detail:
            "The backend has no database configured. Set DATABASE_URL and run the migrations.",
        };
      }
      return { ok: false, detail: error.message };
    }
    return { ok: false, detail: "An unexpected error occurred loading the dashboard." };
  }
}

export default async function LeadsPage({
  searchParams,
}: {
  searchParams: SearchParams;
}) {
  const params = await searchParams;
  const temperature = single(params.temperature);
  const search = single(params.q);
  const page = Math.max(1, Number(single(params.page) ?? 1) || 1);

  const result = await load({
    temperature,
    search,
    limit: PAGE_SIZE,
    offset: (page - 1) * PAGE_SIZE,
  });

  if (!result.ok) {
    return (
      <div className="mx-auto w-full max-w-3xl px-6 py-16 sm:px-8">
        <ErrorState title="Could not load the dashboard" detail={result.detail} />
      </div>
    );
  }

  const { stats, leads } = result;
  const hasFilters = Boolean(temperature || search);

  const pageHref = (target: number) =>
    `/dashboard/leads?${new URLSearchParams({
      ...(search ? { q: search } : {}),
      ...(temperature ? { temperature } : {}),
      page: String(target),
    })}`;

  return (
    <div className="mx-auto w-full max-w-7xl px-6 py-10 sm:px-8">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="font-display text-headline font-semibold">Leads</h1>
          <p className="mt-2 max-w-2xl text-sm text-ink-muted">
            Everything the capture pipeline has produced, scored by the deterministic
            rules in the domain layer.
          </p>
        </div>
        <ButtonLink href="/demo" variant="secondary">
          Generate demo leads
        </ButtonLink>
      </div>

      <div className="mt-8 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <StatCard label="Total leads" value={stats.total_leads} />
        <StatCard label="Hot" value={stats.hot_leads} tone="hot" />
        <StatCard label="Warm" value={stats.warm_leads} tone="warm" />
        <StatCard label="Cold" value={stats.cold_leads} tone="cold" />
        <StatCard label="New this week" value={stats.new_last_7_days} />
        <StatCard
          label="CRM pending"
          value={stats.crm_sync_pending}
          hint="Queued for the outbox dispatcher"
        />
        <StatCard
          label="CRM failures"
          value={stats.crm_sync_failures}
          tone={stats.crm_sync_failures > 0 ? "alert" : "neutral"}
        />
        <StatCard
          label="Dead-lettered"
          value={stats.outbox_dead_lettered}
          tone={stats.outbox_dead_lettered > 0 ? "alert" : "neutral"}
          hint="Events that exhausted their retries"
        />
      </div>

      {/* A plain GET form: no JavaScript, bookmarkable, and the back button
          works. Filter state lives in the URL, not in component state. */}
      <form
        method="GET"
        className="mt-10 flex flex-wrap items-end gap-3 border-y border-line py-5"
      >
        <div className="flex flex-col gap-1.5">
          <label htmlFor="q" className="text-xs uppercase tracking-wider text-ink-muted">
            Search
          </label>
          <input
            id="q"
            name="q"
            defaultValue={search ?? ""}
            placeholder="Company, name or email"
            className="w-64 border border-line-strong bg-paper-raised px-3 py-2 text-sm focus:outline-none focus-visible:border-ink"
          />
        </div>
        <div className="flex flex-col gap-1.5">
          <label
            htmlFor="temperature"
            className="text-xs uppercase tracking-wider text-ink-muted"
          >
            Temperature
          </label>
          <select
            id="temperature"
            name="temperature"
            defaultValue={temperature ?? ""}
            className="w-40 border border-line-strong bg-paper-raised px-3 py-2 text-sm focus:outline-none focus-visible:border-ink"
          >
            <option value="">All</option>
            <option value="hot">Hot</option>
            <option value="warm">Warm</option>
            <option value="cold">Cold</option>
          </select>
        </div>
        <button
          type="submit"
          className="border border-ink bg-ink px-5 py-2 text-sm font-medium text-ink-inverse transition-colors hover:border-accent hover:bg-accent"
        >
          Apply
        </button>
        {hasFilters ? (
          <Link
            href="/dashboard/leads"
            className="px-2 py-2 text-sm text-ink-muted underline underline-offset-4 hover:text-ink"
          >
            Clear
          </Link>
        ) : null}
      </form>

      {leads.items.length === 0 ? (
        <div className="mt-10">
          <EmptyState
            title={hasFilters ? "No leads match those filters" : "No leads yet"}
            description={
              hasFilters
                ? "Try clearing the filters, or widen the search."
                : "Submit the form on /book-call, or generate a batch of synthetic leads to see the pipeline working end to end."
            }
            action={
              hasFilters ? null : <ButtonLink href="/demo">Generate demo leads</ButtonLink>
            }
          />
        </div>
      ) : (
        <>
          <div className="mt-8 overflow-x-auto border border-line">
            <table className="w-full min-w-[64rem] border-collapse text-sm">
              <thead>
                <tr className="border-b border-line bg-paper-raised text-left">
                  {[
                    "Lead",
                    "Company",
                    "Industry",
                    "Budget",
                    "Volume",
                    "Score",
                    "Status",
                    "CRM",
                    "Created",
                  ].map((heading) => (
                    <th
                      key={heading}
                      scope="col"
                      className="px-4 py-3 text-xs font-medium uppercase tracking-wider text-ink-muted"
                    >
                      {heading}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {leads.items.map((lead) => (
                  <tr
                    key={lead.id}
                    className="border-b border-line last:border-b-0 hover:bg-paper-raised"
                  >
                    <td className="px-4 py-3">
                      <Link
                        href={`/dashboard/leads/${lead.id}`}
                        className="font-medium underline-offset-4 hover:underline"
                      >
                        {lead.full_name}
                      </Link>
                      <div className="mt-0.5 text-xs text-ink-muted">{lead.email}</div>
                    </td>
                    <td className="px-4 py-3">
                      <span className="inline-flex items-center gap-2">
                        {lead.company_name}
                        {lead.is_demo ? <DemoBadge /> : null}
                      </span>
                    </td>
                    <td className="px-4 py-3 text-ink-muted">{labelFor(lead.industry)}</td>
                    <td className="px-4 py-3 text-ink-muted">
                      {labelFor(lead.monthly_marketing_budget)}
                    </td>
                    <td className="px-4 py-3 text-ink-muted">
                      {labelFor(lead.content_volume)}
                    </td>
                    <td className="px-4 py-3">
                      <TemperatureBadge temperature={lead.temperature} score={lead.score} />
                    </td>
                    <td className="px-4 py-3">
                      <StatusBadge status={lead.status} />
                    </td>
                    <td className="px-4 py-3">
                      <SyncBadge status={lead.crm_sync_status} />
                    </td>
                    <td className="px-4 py-3 text-xs text-ink-muted">
                      {formatRelative(lead.created_at)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <div className="mt-6 flex items-center justify-between gap-4">
            <p className="text-xs text-ink-muted">
              Showing {leads.offset + 1}–{leads.offset + leads.items.length} of{" "}
              {leads.total}
            </p>
            <div className="flex gap-3">
              {page > 1 ? (
                <Link
                  href={pageHref(page - 1)}
                  className="border border-line-strong px-4 py-2 text-sm hover:border-ink"
                >
                  Previous
                </Link>
              ) : null}
              {leads.has_more ? (
                <Link
                  href={pageHref(page + 1)}
                  className="border border-line-strong px-4 py-2 text-sm hover:border-ink"
                >
                  Next
                </Link>
              ) : null}
            </div>
          </div>
        </>
      )}
    </div>
  );
}
