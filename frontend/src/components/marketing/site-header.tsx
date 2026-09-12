"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

import { MobileNav } from "@/components/marketing/mobile-nav";
import { ButtonLink } from "@/components/ui/button-link";
import { Container } from "@/components/ui/container";
import { navigation, primaryCta, site } from "@/config/site";

/**
 * Site header.
 *
 * Renders from `navigation` in src/config/site.ts, which is also why
 * /dashboard and /demo can never appear here by accident — they are not in
 * that list, and adding a page does not add a nav entry.
 *
 * A Client Component only because it marks the current page with
 * `aria-current` and hosts the mobile disclosure. That is a fair trade: it is a
 * few kilobytes, and without it a screen reader user has no way to tell which
 * page they are on, and a phone user cannot reach four of the five routes.
 */
export function SiteHeader() {
  const pathname = usePathname();

  return (
    <header className="sticky top-0 z-50 border-b border-line bg-paper/85 backdrop-blur-sm">
      <Container className="relative flex h-16 items-center justify-between gap-6">
        <Link
          href="/"
          className="flex min-h-touch items-center gap-2.5"
          aria-label={`${site.name} — home`}
        >
          <span className="block h-4 w-4 rounded-[2px] bg-accent" aria-hidden="true" />
          <span className="font-display text-base font-semibold tracking-tight">
            {site.name}
          </span>
        </Link>

        <nav aria-label="Primary" className="hidden items-center gap-8 md:flex">
          {navigation.map((item) => {
            const active = pathname === item.href;
            return (
              <Link
                key={item.href}
                href={item.href}
                aria-current={active ? "page" : undefined}
                className={`relative py-2 text-sm transition-colors duration-instant ${
                  active ? "text-ink" : "text-ink-muted hover:text-ink"
                }`}
              >
                {item.label}
                {/* A 2px rule under the current page. Position, not colour
                    alone — colour alone is not a reliable signal. */}
                {active ? (
                  <span
                    className="absolute inset-x-0 -bottom-px h-0.5 bg-accent"
                    aria-hidden="true"
                  />
                ) : null}
              </Link>
            );
          })}
        </nav>

        <div className="hidden md:block">
          <ButtonLink href={primaryCta.href} size="sm" icon="arrow-right">
            {primaryCta.label}
          </ButtonLink>
        </div>

        <MobileNav />
      </Container>
    </header>
  );
}
