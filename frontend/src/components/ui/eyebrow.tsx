import type { ReactNode } from "react";

/** The small uppercase label that introduces a section. */
export function Eyebrow({ children }: Readonly<{ children: ReactNode }>) {
  return (
    <p className="text-eyebrow font-medium uppercase text-ink-muted">
      <span className="mr-3 inline-block h-px w-6 align-middle bg-accent" aria-hidden="true" />
      {children}
    </p>
  );
}
