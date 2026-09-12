import { Container } from "@/components/ui/container";
import { Eyebrow } from "@/components/ui/eyebrow";
import { services } from "@/config/site";

export function ServicesSection() {
  return (
    <section id="services" className="border-b border-line">
      <Container className="py-24 sm:py-32">
        <div className="max-w-2xl">
          <Eyebrow>Services</Eyebrow>
          <h2 className="mt-8 font-display text-headline font-semibold text-balance">
            Five disciplines, run as one system.
          </h2>
        </div>

        <ul className="mt-16 grid gap-px border-t border-line bg-line sm:grid-cols-2 lg:grid-cols-3">
          {services.map((service, index) => (
            <li key={service.name} className="bg-paper p-8 sm:p-10">
              <span className="font-mono text-xs text-ink-muted tabular-nums">
                {String(index + 1).padStart(2, "0")}
              </span>
              <h3 className="mt-5 font-display text-title font-semibold">{service.name}</h3>
              <p className="mt-3 text-sm leading-relaxed text-ink-muted">{service.description}</p>
            </li>
          ))}
        </ul>
      </Container>
    </section>
  );
}
