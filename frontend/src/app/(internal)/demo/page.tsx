import type { Metadata } from "next";

import { DemoGenerator } from "@/components/dashboard/demo-generator";
import { SectionCard } from "@/components/dashboard/primitives";

export const metadata: Metadata = { title: "Demo generator" };

/**
 * The synthetic lead generator.
 *
 * Deliberately absent from public navigation (it is not in `site.ts`), noindex
 * via the internal layout, and behind the internal secret on the backend.
 */
export default function DemoPage() {
  return (
    <div className="mx-auto w-full max-w-4xl px-6 py-10 sm:px-8">
      <h1 className="font-display text-headline font-semibold">Demo generator</h1>
      <p className="mt-3 max-w-2xl text-sm leading-relaxed text-ink-muted">
        Creates coherent synthetic leads so the pipeline can be demonstrated without
        real customers. Personas are generated as a whole rather than field by field:
        a hot lead gets a real budget <em>and</em> real urgency <em>and</em> a
        revenue-linked goal, so it reads like an actual enquiry.
      </p>

      <div className="mt-8 space-y-6">
        <SectionCard title="Generate a batch">
          <DemoGenerator />
        </SectionCard>

        <SectionCard title="How this works">
          <div className="space-y-4 text-sm leading-relaxed text-ink-muted">
            <p>
              <strong className="text-ink">Synthetic leads use the same code path.</strong>{" "}
              They are not inserted into the database directly. Each one goes through the
              same <code className="font-mono text-xs">LeadService.capture_lead()</code>{" "}
              as the public form, so it is scored by the real scorer, writes real activity
              rows and emits real outbox events. A demo batch genuinely exercises
              production code rather than a shortcut around it.
            </p>
            <p>
              <strong className="text-ink">Every address is @example.com.</strong> That
              domain is reserved by RFC 2606 and can never route, so synthetic data
              cannot reach a real person&rsquo;s inbox. Generating plausible Gmail
              addresses would mean writing real people&rsquo;s addresses into a CRM.
            </p>
            <p>
              <strong className="text-ink">They are flagged and excluded from the CRM.</strong>{" "}
              Every generated lead carries{" "}
              <code className="font-mono text-xs">is_demo = true</code> and{" "}
              <code className="font-mono text-xs">source = demo_generator</code>, and CRM
              syncing for demo leads is off by default — ten synthetic contacts per click
              would pollute a real HubSpot portal.
            </p>
            <p>
              <strong className="text-ink">The generator has to earn its temperatures.</strong>{" "}
              It aims for a band, then checks the deterministic scorer agrees, resampling
              if it does not. It cannot simply assert that a lead is hot.
            </p>
          </div>
        </SectionCard>
      </div>
    </div>
  );
}
