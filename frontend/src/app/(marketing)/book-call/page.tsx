import type { Metadata } from "next";

import { PlaceholderPage } from "@/components/marketing/placeholder-page";

export const metadata: Metadata = { title: "Book a strategy call" };

/**
 * The primary conversion point of the whole site — and the first real vertical
 * slice through the architecture.
 *
 * In Phase 1 this page gains a client component holding the lead form, which
 * POSTs to the FastAPI backend at /api/v1/leads and redirects to /thank-you.
 * It is a placeholder today because Phase 0 ships no business functionality.
 */
export default function BookCallPage() {
  return (
    <PlaceholderPage
      eyebrow="Book a strategy call"
      title="Tell us what you are trying to grow."
      description="The lead capture form goes here: contact details, budget, content volume, goal and timeline. It will post to the FastAPI backend, which scores the lead and stores it."
      phase="Phase 1"
    />
  );
}
