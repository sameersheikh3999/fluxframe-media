import Link from "next/link";

import {
  DemoBadge,
  StatusBadge,
  SyncBadge,
  TemperatureBadge,
  formatRelative,
} from "@/components/dashboard/primitives";
import { Icon } from "@/components/ui/icon";
import { labelFor } from "@/config/lead-options";
import type { LeadSummary } from "@/types/lead";

/**
 * The leads list, rendered two ways.
 *
 * The UI/UX audit's guidance on tables is "horizontal scroll **or** card
 * layout". The previous version only did the first, which technically works and
 * is genuinely unpleasant: a nine-column table on a 375px screen means dragging
 * sideways to read a single row, and losing the name column as soon as you do.
 *
 * So: cards below `lg`, table at `lg` and up. Same data, same order, same
 * links — one DOM, two presentations. The table keeps `overflow-x-auto` as a
 * backstop for narrow desktop windows.
 *
 * Both are Server Components. Rendering both costs a little markup and no
 * JavaScript, which is a better trade than a resize listener.
 */
export function LeadTable({ leads }: { leads: readonly LeadSummary[] }) {
  return (
    <>
      {/* --- cards: below lg ------------------------------------------- */}
      <ul className="mt-8 space-y-3 lg:hidden">
        {leads.map((lead) => (
          <li key={lead.id}>
            <Link
              href={`/dashboard/leads/${lead.id}`}
              className="block border border-line bg-paper-raised p-5 transition-colors duration-instant hover:border-line-control"
            >
              <div className="flex items-start justify-between gap-3">
                <div className="min-w-0">
                  <p className="truncate font-medium">{lead.full_name}</p>
                  <p className="mt-0.5 truncate text-sm text-ink-muted">
                    {lead.company_name}
                  </p>
                </div>
                <TemperatureBadge temperature={lead.temperature} score={lead.score} />
              </div>

              <dl className="mt-4 grid grid-cols-2 gap-x-4 gap-y-2 border-t border-line pt-4 text-sm">
                <div>
                  <dt className="text-xs uppercase tracking-wider text-ink-muted">
                    Budget
                  </dt>
                  <dd className="mt-0.5">{labelFor(lead.monthly_marketing_budget)}</dd>
                </div>
                <div>
                  <dt className="text-xs uppercase tracking-wider text-ink-muted">
                    Volume
                  </dt>
                  <dd className="mt-0.5">{labelFor(lead.content_volume)}</dd>
                </div>
              </dl>

              <div className="mt-4 flex flex-wrap items-center gap-3 border-t border-line pt-4">
                <StatusBadge status={lead.status} />
                <SyncBadge status={lead.crm_sync_status} />
                {lead.is_demo ? <DemoBadge /> : null}
                <span className="ml-auto flex items-center gap-1.5 text-xs text-ink-muted">
                  {formatRelative(lead.created_at)}
                  <Icon name="arrow-right" size="sm" />
                </span>
              </div>
            </Link>
          </li>
        ))}
      </ul>

      {/* --- table: lg and up ------------------------------------------- */}
      <div className="mt-8 hidden overflow-x-auto border border-line lg:block">
        <table className="w-full border-collapse text-sm">
          <caption className="sr-only">
            Captured leads, newest first. Select a name to open the full record.
          </caption>
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
            {leads.map((lead) => (
              <tr
                key={lead.id}
                className="border-b border-line last:border-b-0 hover:bg-paper-raised"
              >
                {/* `th scope="row"` rather than a td: it is the row's label,
                    and screen readers repeat it when reading other cells. */}
                <th scope="row" className="px-4 py-3 text-left font-normal">
                  <Link
                    href={`/dashboard/leads/${lead.id}`}
                    className="font-medium underline-offset-4 hover:underline"
                  >
                    {lead.full_name}
                  </Link>
                  <span className="mt-0.5 block text-xs font-normal text-ink-muted">
                    {lead.email}
                  </span>
                </th>
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
    </>
  );
}
