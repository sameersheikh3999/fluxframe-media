import type { Metadata } from "next";

import { PlaceholderPage } from "@/components/marketing/placeholder-page";

export const metadata: Metadata = { title: "Process" };

export default function ProcessPage() {
  return (
    <PlaceholderPage
      eyebrow="Process"
      title="Strategy through performance, in seven stages."
      description="A detailed walk through each stage of the loop, who is involved and what you receive at the end of it."
      phase="a later marketing pass"
    />
  );
}
