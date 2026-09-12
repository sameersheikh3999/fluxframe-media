import Link from "next/link";
import type { ReactNode } from "react";

type Variant = "primary" | "secondary";

const styles: Record<Variant, string> = {
  primary:
    "bg-ink text-ink-inverse hover:bg-accent border-ink hover:border-accent",
  secondary:
    "bg-transparent text-ink hover:border-ink-muted border-line-strong",
};

/**
 * A link styled as a button.
 *
 * Note that it renders an anchor, not a <button>. It navigates, so it is a
 * link — which means middle-click, open-in-new-tab and screen readers all
 * behave the way people expect.
 */
export function ButtonLink({
  href,
  children,
  variant = "primary",
}: Readonly<{ href: string; children: ReactNode; variant?: Variant }>) {
  return (
    <Link
      href={href}
      className={`inline-flex items-center justify-center rounded-full border px-6 py-3 text-sm font-medium transition-colors duration-200 ${styles[variant]}`}
    >
      {children}
    </Link>
  );
}
