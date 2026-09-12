import { ButtonLink } from "@/components/ui/button-link";
import { Container } from "@/components/ui/container";
import { Eyebrow } from "@/components/ui/eyebrow";

/**
 * A branded placeholder for a page that is scaffolded but not yet built.
 *
 * It states plainly which phase fills it in. A placeholder that pretends to be
 * finished is worse than an empty page, because it hides the remaining work.
 */
export function PlaceholderPage({
  eyebrow,
  title,
  description,
  phase,
}: Readonly<{ eyebrow: string; title: string; description: string; phase: string }>) {
  return (
    <Container className="py-24 sm:py-32 lg:py-40">
      <div className="max-w-3xl">
        <Eyebrow>{eyebrow}</Eyebrow>
        <h1 className="mt-8 font-display text-headline font-semibold text-balance">{title}</h1>
        <p className="mt-6 text-lead text-ink-muted text-pretty">{description}</p>

        <p className="mt-10 inline-block border border-line-strong px-4 py-2 text-xs text-ink-muted">
          Scaffolded in Phase 0 · built in {phase}
        </p>

        <div className="mt-12">
          <ButtonLink href="/" variant="secondary" icon="arrow-left" iconPosition="left">
            Back to home
          </ButtonLink>
        </div>
      </div>
    </Container>
  );
}
