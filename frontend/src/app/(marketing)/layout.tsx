import type { ReactNode } from "react";

import { SiteFooter } from "@/components/marketing/site-footer";
import { SiteHeader } from "@/components/marketing/site-header";

/**
 * Chrome for the public marketing site.
 *
 * `(marketing)` is a route group: the parentheses mean the folder name does not
 * appear in any URL. /services is still /services. What the group buys is a
 * shared layout and a visible boundary — everything under it is public, and the
 * (internal) group added in Phase 2 will be everything that is not.
 */
export default function MarketingLayout({ children }: Readonly<{ children: ReactNode }>) {
  return (
    <>
      <SiteHeader />
      <main className="flex-1">{children}</main>
      <SiteFooter />
    </>
  );
}
