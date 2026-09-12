import { ButtonLink } from "@/components/ui/button-link";
import { Container } from "@/components/ui/container";
import { Eyebrow } from "@/components/ui/eyebrow";
import { primaryCta, site } from "@/config/site";

export function Hero() {
  return (
    <section className="border-b border-line">
      <Container className="py-24 sm:py-32 lg:py-40">
        <div className="max-w-4xl">
          <Eyebrow>Content &amp; social media agency</Eyebrow>

          <h1 className="mt-8 font-display text-display font-semibold text-balance">
            {site.tagline}
          </h1>

          <p className="mt-8 max-w-2xl text-lead text-ink-muted text-pretty">
            We help service businesses turn attention into pipeline — strategy, short-form video,
            paid social and creative that is measured by what it returns, not by what it looks like.
          </p>

          <div className="mt-12 flex flex-wrap items-center gap-4">
            <ButtonLink href={primaryCta.href} icon="arrow-right">
              {primaryCta.label}
            </ButtonLink>
            <ButtonLink href="/work" variant="secondary">
              See the work
            </ButtonLink>
          </div>
        </div>
      </Container>
    </section>
  );
}
