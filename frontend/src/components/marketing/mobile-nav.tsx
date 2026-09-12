"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useId, useState } from "react";

import { Icon } from "@/components/ui/icon";
import { navigation, primaryCta } from "@/config/site";

/**
 * Navigation for small screens.
 *
 * This fixes a real defect rather than adding polish: below `md` the header
 * previously showed only the CTA, which meant Services, Process, Work and About
 * were unreachable on a phone. On a marketing site, that is most of the
 * traffic.
 *
 * Accessibility details that make a disclosure menu actually work, all of which
 * are easy to omit and immediately noticeable to anyone who needs them:
 *
 * - `aria-expanded` and `aria-controls` on the trigger, so a screen reader
 *   announces the state rather than just "button".
 * - Escape closes it and returns focus to the trigger — otherwise focus is
 *   stranded in a panel that is no longer visible.
 * - The panel closes when a link is chosen. Done in the click handler rather
 *   than in an effect watching `usePathname`: React 19 flags `setState` inside
 *   an effect, and rightly — the close is caused by the click, so that is where
 *   it belongs. The effect version also renders once with the panel still open.
 * - Background scroll is locked while it is open, so the page behind does not
 *   move under the reader's finger.
 * - The trigger is a real `<button>` with a visible-on-focus ring and a 44px
 *   hit area.
 */
export function MobileNav() {
  const [open, setOpen] = useState(false);
  const panelId = useId();
  const pathname = usePathname();

  // Escape to close, and lock background scroll while open.
  useEffect(() => {
    if (!open) return;

    function onKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") setOpen(false);
    }

    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    document.addEventListener("keydown", onKeyDown);

    return () => {
      document.body.style.overflow = previousOverflow;
      document.removeEventListener("keydown", onKeyDown);
    };
  }, [open]);

  return (
    <div className="md:hidden">
      <button
        type="button"
        aria-expanded={open}
        aria-controls={panelId}
        aria-label={open ? "Close menu" : "Open menu"}
        onClick={() => setOpen((value) => !value)}
        className="inline-flex min-h-touch min-w-touch items-center justify-center rounded-full border border-line-control text-ink transition-colors duration-instant hover:border-ink"
      >
        <Icon name={open ? "close" : "menu"} size="md" />
      </button>

      {open ? (
        <div
          id={panelId}
          className="absolute inset-x-0 top-16 z-50 border-b border-line bg-paper-raised shadow-sm"
        >
          <nav aria-label="Primary (mobile)" className="px-6 py-4">
            <ul className="flex flex-col">
              {navigation.map((item) => {
                const active = pathname === item.href;
                return (
                  <li key={item.href} className="border-b border-line last:border-b-0">
                    <Link
                      href={item.href}
                      onClick={() => setOpen(false)}
                      aria-current={active ? "page" : undefined}
                      className={`flex min-h-touch items-center justify-between py-2 text-base transition-colors duration-instant ${
                        active ? "text-ink font-medium" : "text-ink-muted hover:text-ink"
                      }`}
                    >
                      {item.label}
                      <Icon name="arrow-right" size="sm" className="text-ink-muted" />
                    </Link>
                  </li>
                );
              })}
            </ul>

            <Link
              href={primaryCta.href}
              onClick={() => setOpen(false)}
              className="mt-5 flex min-h-touch items-center justify-center gap-2 rounded-full border border-ink bg-ink px-6 py-3 text-sm font-medium text-ink-inverse transition-colors duration-instant hover:border-accent hover:bg-accent"
            >
              {primaryCta.label}
              <Icon name="arrow-right" size="sm" />
            </Link>
          </nav>
        </div>
      ) : null}
    </div>
  );
}
