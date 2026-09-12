import { Container } from "@/components/ui/container";
import { Eyebrow } from "@/components/ui/eyebrow";
import { processSteps } from "@/config/site";

export function ProcessSection() {
  return (
    <section id="process" className="border-b border-line bg-paper-raised">
      <Container className="py-24 sm:py-32">
        <div className="max-w-2xl">
          <Eyebrow>Process</Eyebrow>
          <h2 className="mt-8 font-display text-headline font-semibold text-balance">
            A repeatable loop, not a series of favours.
          </h2>
          <p className="mt-6 text-lead text-ink-muted text-pretty">
            Every engagement runs the same seven stages. Knowing which stage a piece of content is
            in — at any moment — is what makes the work predictable.
          </p>
        </div>

        <ol className="mt-16 grid gap-8 sm:grid-cols-2 lg:grid-cols-4">
          {processSteps.map((step, index) => (
            <li key={step.name} className="border-t border-line-strong pt-6">
              <span className="font-mono text-xs text-accent tabular-nums">
                {String(index + 1).padStart(2, "0")}
              </span>
              <h3 className="mt-4 font-display text-title font-semibold">{step.name}</h3>
              <p className="mt-2 text-sm leading-relaxed text-ink-muted">{step.description}</p>
            </li>
          ))}
        </ol>
      </Container>
    </section>
  );
}
