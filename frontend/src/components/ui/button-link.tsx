import Link from "next/link";
import type { ReactNode } from "react";

import { Icon, type IconName } from "@/components/ui/icon";

type Variant = "primary" | "secondary" | "quiet";
type Size = "md" | "sm";

/**
 * A link styled as a button.
 *
 * It renders an anchor, not a `<button>`, because it navigates — which means
 * middle-click, open-in-new-tab, and "Copy link address" all behave the way
 * people expect, and screen readers announce it as a link rather than a
 * control that does something on this page.
 *
 * Two details that came out of the UI/UX audit:
 *
 * - **Every size clears 44px.** Even `sm` uses `min-h-touch`, because the WCAG
 *   target-size rule and the touch guidance both bite hardest on the controls
 *   you are tempted to shrink.
 * - **`secondary` uses `border-line-control`, not `border-line-strong`.** A
 *   control boundary carries meaning, so it needs 3:1 against the surface.
 *   The decorative rule colour measured 1.49:1 and was a real failure.
 */
const VARIANTS: Record<Variant, string> = {
  primary:
    "bg-ink text-ink-inverse border-ink hover:bg-accent hover:border-accent",
  secondary:
    "bg-transparent text-ink border-line-control hover:border-ink hover:bg-ink/5",
  quiet:
    "bg-transparent text-ink-muted border-transparent hover:text-ink hover:bg-ink/5",
};

const SIZES: Record<Size, string> = {
  md: "px-6 py-3 text-sm",
  sm: "px-4 py-2.5 text-sm",
};

export function ButtonLink({
  href,
  children,
  variant = "primary",
  size = "md",
  icon,
  iconPosition = "right",
  className = "",
}: Readonly<{
  href: string;
  children: ReactNode;
  variant?: Variant;
  size?: Size;
  icon?: IconName;
  iconPosition?: "left" | "right";
  className?: string;
}>) {
  const glyph = icon ? <Icon name={icon} size="sm" /> : null;
  return (
    <Link
      href={href}
      className={`inline-flex min-h-touch items-center justify-center gap-2 rounded-full border font-medium transition-colors duration-instant ${VARIANTS[variant]} ${SIZES[size]} ${className}`}
    >
      {iconPosition === "left" ? glyph : null}
      {children}
      {iconPosition === "right" ? glyph : null}
    </Link>
  );
}

/**
 * The same visual language for a real `<button>` — something that acts on this
 * page rather than navigating.
 *
 * Kept beside ButtonLink deliberately: when the two live apart they drift, and
 * then a "button" and a "link that looks like a button" no longer match.
 */
export function Button({
  children,
  variant = "primary",
  size = "md",
  icon,
  iconPosition = "left",
  className = "",
  type = "button",
  ...rest
}: Readonly<{
  children: ReactNode;
  variant?: Variant;
  size?: Size;
  icon?: IconName;
  iconPosition?: "left" | "right";
  className?: string;
}> &
  React.ButtonHTMLAttributes<HTMLButtonElement>) {
  const glyph = icon ? <Icon name={icon} size="sm" /> : null;
  return (
    <button
      type={type}
      className={`inline-flex min-h-touch items-center justify-center gap-2 rounded-full border font-medium transition-colors duration-instant disabled:opacity-60 ${VARIANTS[variant]} ${SIZES[size]} ${className}`}
      {...rest}
    >
      {iconPosition === "left" ? glyph : null}
      {children}
      {iconPosition === "right" ? glyph : null}
    </button>
  );
}
