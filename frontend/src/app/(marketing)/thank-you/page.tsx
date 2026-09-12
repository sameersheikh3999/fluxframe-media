import type { Metadata } from "next";

import { ButtonLink } from "@/components/ui/button-link";
import { Container } from "@/components/ui/container";
import { Icon } from "@/components/ui/icon";

export const metadata: Metadata = {
  title: "Thank you",
  description: "Your enquiry is with us.",
  // Nothing to gain from indexing a confirmation page, and it would be an odd
  // search result to land on.
  robots: { index: false, follow: true },
};

export default function ThankYouPage() {
  return (
    <Container className="py-24 sm:py-32 lg:py-40">
      <div className="max-w-2xl">
        <p className="flex items-center gap-2.5 text-eyebrow font-medium uppercase text-accent">
          <Icon name="check" size="md" />
          Enquiry received
        </p>
        <h1 className="mt-8 font-display text-headline font-semibold text-balance">
          Thanks — that is with us.
        </h1>
        <p className="mt-6 text-lead text-ink-muted text-pretty">
          A real person will read it and come back to you within one business day. No
          automated sequence, no drip campaign.
        </p>

        <ol className="mt-12 space-y-6 border-t border-line pt-8">
          {[
            "We read your answers and look at what you are publishing now.",
            "We come back with a view on fit and a suggested first move.",
            "If it looks right, we book thirty minutes to talk it through.",
          ].map((step, index) => (
            <li key={step} className="flex gap-5">
              <span className="font-mono text-xs text-accent tabular-nums">
                {String(index + 1).padStart(2, "0")}
              </span>
              <span className="text-sm leading-relaxed text-ink-muted">{step}</span>
            </li>
          ))}
        </ol>

        <div className="mt-12 flex flex-wrap gap-4">
          <ButtonLink href="/" icon="arrow-left" iconPosition="left">
            Back to home
          </ButtonLink>
          <ButtonLink href="/work" variant="secondary" icon="arrow-right">
            See the work
          </ButtonLink>
        </div>
      </div>
    </Container>
  );
}
