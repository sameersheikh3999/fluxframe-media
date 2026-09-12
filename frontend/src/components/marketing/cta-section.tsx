import { ButtonLink } from "@/components/ui/button-link";
import { Container } from "@/components/ui/container";
import { primaryCta } from "@/config/site";

export function CtaSection() {
  return (
    <section className="bg-paper-inverse text-ink-inverse">
      <Container className="py-24 sm:py-32">
        <div className="flex flex-col gap-10 lg:flex-row lg:items-end lg:justify-between">
          <h2 className="max-w-2xl font-display text-headline font-semibold text-balance">
            Tell us what you are trying to grow.
          </h2>
          <div className="shrink-0">
            <ButtonLink href={primaryCta.href} variant="secondary">
              {primaryCta.label}
            </ButtonLink>
          </div>
        </div>
      </Container>
    </section>
  );
}
