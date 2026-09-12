import type { ReactNode } from "react";

/**
 * The single source of truth for page gutters and maximum line length.
 *
 * Every section wraps its content in this. Nothing sets its own horizontal
 * padding, which is why the site stays aligned at every breakpoint without
 * anyone maintaining it.
 */
export function Container({
  children,
  className = "",
}: Readonly<{ children: ReactNode; className?: string }>) {
  return <div className={`mx-auto w-full max-w-6xl px-6 sm:px-8 ${className}`}>{children}</div>;
}
