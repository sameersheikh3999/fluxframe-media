import type { Metadata } from "next";
import Link from "next/link";
import type { ReactNode } from "react";

/**
 * Chrome for the internal tools.
 *
 * A completely different layout from the public site — no marketing header, no
 * footer, no CTA. That separation is the reason `(marketing)` and `(internal)`
 * are route groups rather than one shared layout with conditionals.
 *
 * These pages are also explicitly noindex. They sit on the same public domain
 * as the marketing site, and a dashboard appearing in search results would be
 * an embarrassing way to discover that.
 */
export const metadata: Metadata = {
  robots: { index: false, follow: false, nocache: true },
};

const NAV = [
  { href: "/dashboard/leads", label: "Leads" },
  { href: "/demo", label: "Demo generator" },
];

export default function InternalLayout({ children }: Readonly<{ children: ReactNode }>) {
  return (
    <>
      <header className="border-b border-line bg-paper-raised">
        <div className="mx-auto flex w-full max-w-7xl flex-wrap items-center justify-between gap-4 px-6 py-4 sm:px-8">
          <div className="flex items-center gap-8">
            <Link href="/dashboard/leads" className="flex items-center gap-2.5">
              <span className="block h-3.5 w-3.5 rounded-[2px] bg-accent" aria-hidden="true" />
              <span className="font-display text-sm font-semibold tracking-tight">
                Fluxframe Ops
              </span>
            </Link>
            <nav aria-label="Internal" className="flex items-center gap-6">
              {NAV.map((item) => (
                <Link
                  key={item.href}
                  href={item.href}
                  className="text-sm text-ink-muted transition-colors hover:text-ink"
                >
                  {item.label}
                </Link>
              ))}
            </nav>
          </div>
          <Link
            href="/"
            className="text-xs text-ink-muted underline underline-offset-4 hover:text-ink"
          >
            Public site
          </Link>
        </div>
      </header>
      <main className="flex-1 bg-paper">{children}</main>
    </>
  );
}
