import Link from "next/link";

import { Container } from "@/components/ui/container";
import { navigation, services, site } from "@/config/site";

export function SiteFooter() {
  const year = new Date().getFullYear();

  return (
    <footer className="mt-auto border-t border-line bg-paper">
      <Container className="py-16">
        <div className="grid gap-12 sm:grid-cols-2 lg:grid-cols-4">
          <div className="lg:col-span-2">
            <div className="flex items-center gap-2.5">
              <span className="block h-4 w-4 rounded-[2px] bg-accent" aria-hidden="true" />
              <span className="font-display text-base font-semibold tracking-tight">
                {site.name}
              </span>
            </div>
            <p className="mt-4 max-w-sm text-sm leading-relaxed text-ink-muted">
              {site.description}
            </p>
          </div>

          <div>
            <h2 className="text-sm font-medium">Agency</h2>
            <ul className="mt-4 space-y-3">
              {navigation.map((item) => (
                <li key={item.href}>
                  <Link
                    href={item.href}
                    className="text-sm text-ink-muted transition-colors hover:text-ink"
                  >
                    {item.label}
                  </Link>
                </li>
              ))}
            </ul>
          </div>

          <div>
            <h2 className="text-sm font-medium">Services</h2>
            <ul className="mt-4 space-y-3">
              {services.map((service) => (
                <li key={service.name} className="text-sm text-ink-muted">
                  {service.name}
                </li>
              ))}
            </ul>
          </div>
        </div>

        <div className="mt-16 flex flex-col gap-2 border-t border-line pt-8 text-xs text-ink-muted sm:flex-row sm:items-center sm:justify-between">
          <p>
            &copy; {year} {site.name}.
          </p>
          <p>
            A portfolio project. Fluxframe Media is a fictional agency; nothing on this site
            describes a real client.
          </p>
        </div>
      </Container>
    </footer>
  );
}
