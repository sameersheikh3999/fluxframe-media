import type { Metadata } from "next";

import { PlaceholderPage } from "@/components/marketing/placeholder-page";

export const metadata: Metadata = { title: "About" };

export default function AboutPage() {
  return (
    <PlaceholderPage
      eyebrow="About"
      title="Who we are."
      description="Positioning, point of view and how the agency is structured."
      phase="a later marketing pass"
    />
  );
}
