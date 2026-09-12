import type { Metadata } from "next";

import { BookCallForm } from "@/components/leads/book-call-form";
import { Container } from "@/components/ui/container";
import { Eyebrow } from "@/components/ui/eyebrow";

export const metadata: Metadata = {
  title: "Book a strategy call",
  description:
    "Tell us what you are trying to grow. We will come back within one business day with a view on whether we can help.",
};

/**
 * The conversion point of the whole site.
 *
 * A Server Component that renders static content, with one Client Component
 * island for the form itself. Everything except the form ships as HTML with no
 * JavaScript — which is why the page is fast even though the form is not small.
 */
export default function BookCallPage() {
  return (
    <Container className="py-20 sm:py-28">
      <div className="grid gap-16 lg:grid-cols-[minmax(0,1fr)_minmax(0,1.4fr)] lg:gap-24">
        <aside className="lg:sticky lg:top-28 lg:self-start">
          <Eyebrow>Book a strategy call</Eyebrow>
          <h1 className="mt-8 font-display text-headline font-semibold text-balance">
            Tell us what you are trying to grow.
          </h1>
          <p className="mt-6 text-lead text-ink-muted text-pretty">
            Thirty minutes, no pitch deck. We will look at what you are doing now, where
            the gap is, and whether we are the right people to close it.
          </p>

          <dl className="mt-12 space-y-6 border-t border-line pt-8">
            {[
              { term: "What happens next", detail: "We reply within one business day." },
              {
                term: "What we will ask",
                detail: "Your current channels, what you have tried, and what success looks like.",
              },
              {
                term: "What you get",
                detail: "A straight answer on fit, and a view on what we would do first.",
              },
            ].map((item) => (
              <div key={item.term}>
                <dt className="text-sm font-medium">{item.term}</dt>
                <dd className="mt-1.5 text-sm leading-relaxed text-ink-muted">{item.detail}</dd>
              </div>
            ))}
          </dl>
        </aside>

        <div className="border-t border-line pt-12 lg:border-l lg:border-t-0 lg:pl-16 lg:pt-0">
          <BookCallForm />
        </div>
      </div>
    </Container>
  );
}
