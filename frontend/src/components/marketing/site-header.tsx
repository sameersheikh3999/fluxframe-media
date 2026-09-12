import Link from "next/link";

import { ButtonLink } from "@/components/ui/button-link";
import { Container } from "@/components/ui/container";
import { navigation, primaryCta, site } from "@/config/site";

/**
 * Site header.
 *
 * Renders from `navigation` in src/config/site.ts, which is also why
 * /dashboard and /demo can never appear here by accident — they are not in
 * that list, and adding a page does not add a nav entry.
 */
export function SiteHeader() {
  return (
    <header className="sticky top-0 z-50 border-b border-line bg-paper/85 backdrop-blur-sm">
      <Container className="flex h-16 items-center justify-between gap-6">
        <Link href="/" className="flex items-center gap-2.5">
          <span className="block h-4 w-4 rounded-[2px] bg-accent" aria-hidden="true" />
          <span className="font-display text-base font-semibold tracking-tight">{site.name}</span>
        </Link>

        <nav aria-label="Primary" className="hidden items-center gap-8 md:flex">
          {navigation.map((item) => (
            <Link
              key={item.href}
              href={item.href}
              className="text-sm text-ink-muted transition-colors hover:text-ink"
            >
              {item.label}
            </Link>
          ))}
        </nav>

        <div className="hidden md:block">
          <ButtonLink href={primaryCta.href}>{primaryCta.label}</ButtonLink>
        </div>

        {/* Below md the nav collapses to the one action that matters. A full
            mobile menu arrives when there are enough pages to justify it. */}
        <div className="md:hidden">
          <ButtonLink href={primaryCta.href}>Book a call</ButtonLink>
        </div>
      </Container>
    </header>
  );
}
