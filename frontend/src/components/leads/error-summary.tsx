"use client";

import { useEffect, useRef } from "react";

import { Icon } from "@/components/ui/icon";

/**
 * A focusable error summary for a failed form submission.
 *
 * The UI/UX audit flagged the previous banner as "High" severity, and the
 * reasoning is worth keeping: inline field errors are invisible to someone who
 * has just pressed Submit and is at the *bottom* of a twelve-field form. They
 * get no announcement, and no indication of where the problem is.
 *
 * Four things make a summary actually work, and omitting any one of them
 * returns it to being decoration:
 *
 * 1. **It receives focus after a failed submit** — `tabIndex={-1}` plus a
 *    `.focus()` — so a screen reader lands on it and reads it out.
 * 2. **Each item links to its field.** `href="#email"` jumps straight there.
 *    A list of problems you then have to hunt for is barely better than none.
 * 3. **Inline errors stay.** The summary complements them; it does not replace
 *    them. You need the error next to the field when you fix it.
 * 4. **Focus moves on submit, never on blur.** Stealing focus while someone is
 *    still typing is worse than the original problem.
 */
export type SummaryItem = { field: string; message: string };

export function ErrorSummary({
  items,
  heading = "There is a problem",
  requestId,
}: {
  items: SummaryItem[];
  heading?: string;
  requestId?: string | null;
}) {
  const container = useRef<HTMLDivElement>(null);

  // Move focus here whenever the set of errors changes — i.e. on each failed
  // submit, including a second failed submit with the same errors.
  useEffect(() => {
    if (items.length > 0) container.current?.focus();
  }, [items]);

  if (items.length === 0) return null;

  return (
    <div
      ref={container}
      role="alert"
      tabIndex={-1}
      aria-labelledby="error-summary-heading"
      className="border-l-2 border-accent bg-accent/5 px-5 py-4 focus-visible:outline-accent"
    >
      <p
        id="error-summary-heading"
        className="flex items-center gap-2 font-display text-base font-semibold"
      >
        <Icon name="alert" size="md" className="text-accent" />
        {heading}
      </p>

      <ul className="mt-3 space-y-1.5">
        {items.map((item) => (
          <li key={item.field}>
            <a
              href={`#${item.field}`}
              className="text-sm text-ink underline decoration-accent underline-offset-4 hover:text-accent"
              onClick={(event) => {
                // Move focus to the field itself, not just scroll to it —
                // otherwise the next Tab starts from the summary again.
                event.preventDefault();
                const target = document.getElementById(item.field);
                target?.focus();
                target?.scrollIntoView({ block: "center", behavior: "smooth" });
              }}
            >
              {item.message}
            </a>
          </li>
        ))}
      </ul>

      {requestId ? (
        <p className="mt-3 text-xs text-ink-muted">
          Reference: <span className="font-mono">{requestId}</span>
        </p>
      ) : null}
    </div>
  );
}
