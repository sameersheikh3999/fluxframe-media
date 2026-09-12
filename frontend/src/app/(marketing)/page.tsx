import { CtaSection } from "@/components/marketing/cta-section";
import { Hero } from "@/components/marketing/hero";
import { ProcessSection } from "@/components/marketing/process-section";
import { ServicesSection } from "@/components/marketing/services-section";

/**
 * Home.
 *
 * A Server Component with no client-side JavaScript of its own: it renders from
 * static configuration at build time. There is nothing interactive on this page,
 * so there is nothing to hydrate.
 */
export default function HomePage() {
  return (
    <>
      <Hero />
      <ServicesSection />
      <ProcessSection />
      <CtaSection />
    </>
  );
}
