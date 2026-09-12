/**
 * Fluxframe Media — brand and content configuration.
 *
 * Marketing copy lives here rather than being scattered through JSX, so that
 * changing a service name is one edit in one file, and so that the same list
 * can feed a page, a footer and (later) a form's dropdown without drifting.
 */

export const site = {
  name: "Fluxframe Media",
  tagline: "Content that moves businesses forward.",
  description:
    "Fluxframe Media is a content and social media agency helping service businesses grow " +
    "through strategy, short-form video, paid media and performance-driven creative.",
  email: "hello@fluxframe.media",
} as const;

export type NavItem = {
  readonly label: string;
  readonly href: string;
};

/** Public navigation. /dashboard and /demo are deliberately absent. */
export const navigation: readonly NavItem[] = [
  { label: "Services", href: "/services" },
  { label: "Process", href: "/process" },
  { label: "Work", href: "/work" },
  { label: "About", href: "/about" },
] as const;

export const primaryCta = {
  label: "Book a strategy call",
  href: "/book-call",
} as const;

export type Service = {
  readonly name: string;
  readonly description: string;
};

export const services: readonly Service[] = [
  {
    name: "Short-form video",
    description:
      "Vertical video built for reach and retention — scripted, shot and edited as a system, not as one-off posts.",
  },
  {
    name: "Social media management",
    description:
      "Owning the channel end to end: calendar, publishing, community and the reporting that keeps it honest.",
  },
  {
    name: "Content strategy",
    description:
      "Deciding what to make and why, grounded in the audience you actually sell to and the outcome you need.",
  },
  {
    name: "Paid social",
    description:
      "Creative-led paid media that treats the ad as the variable worth testing, not the targeting.",
  },
  {
    name: "Creator campaigns",
    description:
      "Matching your brand with creators whose audience overlaps your buyers, then measuring what it returned.",
  },
] as const;

export type ProcessStep = {
  readonly name: string;
  readonly description: string;
};

/**
 * The agency lifecycle, and — not coincidentally — the workflow this codebase
 * is built to automate over time. Phase 8 of docs/implementation-plan.md turns
 * these seven words into state machines.
 */
export const processSteps: readonly ProcessStep[] = [
  { name: "Strategy", description: "Audience, offer and the outcome we are actually optimising for." },
  { name: "Scripting", description: "Hooks and structure written before anyone picks up a camera." },
  { name: "Shoot", description: "Batched production days that yield weeks of content, not hours." },
  { name: "Editing", description: "Pacing, captions and framing tuned per platform." },
  { name: "Approval", description: "One review loop with a clear decision, not an endless thread." },
  { name: "Publishing", description: "Scheduled and shipped on a cadence the algorithm rewards." },
  { name: "Performance", description: "What worked, what did not, and what we change next cycle." },
] as const;
