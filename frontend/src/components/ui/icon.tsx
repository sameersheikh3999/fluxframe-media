import type { SVGProps } from "react";

/**
 * The icon set.
 *
 * Inline SVG, drawn from the Lucide geometry (ISC licensed), rather than a
 * dependency: eleven icons do not justify shipping an icon library, and
 * inlining them means zero runtime, zero network request and no flash of
 * missing glyph.
 *
 * Three rules hold across all of them, and they are why a set looks coherent:
 *
 * 1. **One stroke width.** 1.5 everywhere. Mixed strokes are the single most
 *    common reason an interface looks slightly cheap without anyone being able
 *    to say why.
 * 2. **Sizes come from tokens, not from taste.** sm/md/lg, never an arbitrary
 *    21px because it happened to look right in one place.
 * 3. **Semantics come from use, not from the glyph.** The same arrow is
 *    decorative beside a text label and meaningful in an icon-only button. So
 *    `Icon` is `aria-hidden` by default, and passing a `label` makes it an
 *    `img` with an accessible name. There is no third option where a
 *    meaningful icon is silently invisible to a screen reader.
 */

const SIZES = {
  sm: "1rem", // 16px — inline with body text
  md: "1.25rem", // 20px — buttons, list markers
  lg: "1.5rem", // 24px — section headings
} as const;

export type IconName =
  | "arrow-right"
  | "arrow-left"
  | "check"
  | "alert"
  | "search"
  | "menu"
  | "close"
  | "chevron-down"
  | "refresh"
  | "sparkles"
  | "external";

/** Path data only — every icon shares the same 24×24 box and stroke settings. */
const PATHS: Record<IconName, React.ReactNode> = {
  "arrow-right": (
    <>
      <path d="M5 12h14" />
      <path d="m12 5 7 7-7 7" />
    </>
  ),
  "arrow-left": (
    <>
      <path d="M19 12H5" />
      <path d="m12 19-7-7 7-7" />
    </>
  ),
  check: <path d="M20 6 9 17l-5-5" />,
  alert: (
    <>
      <circle cx="12" cy="12" r="10" />
      <path d="M12 8v4" />
      <path d="M12 16h.01" />
    </>
  ),
  search: (
    <>
      <circle cx="11" cy="11" r="8" />
      <path d="m21 21-4.3-4.3" />
    </>
  ),
  menu: (
    <>
      <path d="M4 6h16" />
      <path d="M4 12h16" />
      <path d="M4 18h16" />
    </>
  ),
  close: (
    <>
      <path d="M18 6 6 18" />
      <path d="m6 6 12 12" />
    </>
  ),
  "chevron-down": <path d="m6 9 6 6 6-6" />,
  refresh: (
    <>
      <path d="M3 12a9 9 0 0 1 9-9 9.75 9.75 0 0 1 6.74 2.74L21 8" />
      <path d="M21 3v5h-5" />
      <path d="M21 12a9 9 0 0 1-9 9 9.75 9.75 0 0 1-6.74-2.74L3 16" />
      <path d="M8 16H3v5" />
    </>
  ),
  sparkles: (
    <>
      <path d="M9.94 14.06 8 20l-1.94-5.94L0 12l6.06-2.06L8 4l1.94 5.94L16 12z" />
      <path d="M18 3v4" />
      <path d="M20 5h-4" />
    </>
  ),
  external: (
    <>
      <path d="M15 3h6v6" />
      <path d="M10 14 21 3" />
      <path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6" />
    </>
  ),
};

export type IconProps = {
  name: IconName;
  size?: keyof typeof SIZES;
  /**
   * Supply this ONLY when the icon carries meaning on its own — an icon-only
   * button, or a status indicator with no adjacent text. Beside a visible
   * label, leave it out: announcing "arrow right, Book a call" is noise.
   */
  label?: string;
  className?: string;
} & Omit<SVGProps<SVGSVGElement>, "ref" | "name">;

export function Icon({ name, size = "md", label, className = "", ...rest }: IconProps) {
  const dimension = SIZES[size];
  return (
    <svg
      viewBox="0 0 24 24"
      width={dimension}
      height={dimension}
      fill="none"
      stroke="currentColor"
      strokeWidth={1.5}
      strokeLinecap="round"
      strokeLinejoin="round"
      // Decorative by default; an accessible name only when one was asked for.
      aria-hidden={label ? undefined : true}
      role={label ? "img" : undefined}
      aria-label={label}
      focusable="false"
      className={`shrink-0 ${className}`}
      {...rest}
    >
      {PATHS[name]}
    </svg>
  );
}
