import type { Metadata } from "next";

import { PlaceholderPage } from "@/components/marketing/placeholder-page";

export const metadata: Metadata = { title: "Services" };

export default function ServicesPage() {
  return (
    <PlaceholderPage
      eyebrow="Services"
      title="Short-form video, social, strategy, paid and creators."
      description="The full services page — what each engagement includes, how teams are staffed and what the deliverables look like."
      phase="a later marketing pass"
    />
  );
}
