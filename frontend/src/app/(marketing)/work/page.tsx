import type { Metadata } from "next";

import { PlaceholderPage } from "@/components/marketing/placeholder-page";

export const metadata: Metadata = { title: "Work" };

export default function WorkPage() {
  return (
    <PlaceholderPage
      eyebrow="Work"
      title="Case studies."
      description="Every case study published here will be labelled 'Illustrative demo — not a real client'. Fluxframe Media is a fictional agency built as a portfolio project, and inventing testimonials would make the rest of it untrustworthy."
      phase="a later marketing pass"
    />
  );
}
