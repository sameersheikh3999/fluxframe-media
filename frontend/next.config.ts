import type { NextConfig } from "next";

/**
 * Where this Next.js server should forward API traffic.
 *
 * Only used by the rewrites below, which only matter in the SINGLE-SERVICE
 * deployment. In the two-service deployment the browser calls the backend's
 * public URL directly and these rewrites never fire.
 */
const BACKEND_INTERNAL_URL = (
  process.env.BACKEND_INTERNAL_URL ?? "http://127.0.0.1:8000"
).replace(/\/+$/, "");

const nextConfig: NextConfig = {
  /**
   * Trace exactly which node_modules files the app imports and copy only those
   * into `.next/standalone`. Turns a ~400MB runtime image into a ~60MB one,
   * which is what makes bundling Node and Python in one container reasonable.
   */
  output: "standalone",

  /**
   * Same-origin API proxying — the mechanism behind the one-service deployment.
   *
   * The browser posts to `/api/v1/leads` on the page's own origin; Next.js
   * forwards it to the FastAPI process running beside it in the same container.
   *
   * Three things fall out of this, and they are the reason it is worth doing
   * rather than just being a convenience:
   *
   * 1. **CORS disappears entirely.** Same origin means no preflight, no
   *    `FRONTEND_ORIGINS` to keep in sync, and no "it works in curl but the
   *    browser blocks it" class of bug.
   * 2. **`NEXT_PUBLIC_API_URL` becomes unnecessary.** It is baked in at build
   *    time, so getting it wrong normally means a rebuild. Here there is
   *    nothing to get wrong.
   * 3. **One domain, one certificate, one service.**
   *
   * Returning an ARRAY (rather than an object with `beforeFiles`) matters:
   * array-form rewrites run *after* filesystem routes, so the real
   * `/api/internal/[...path]` route handler still wins and is never shadowed
   * by this proxy.
   */
  async rewrites() {
    return [
      // The public API and every internal endpoint the dashboard uses.
      {
        source: "/api/v1/:path*",
        destination: `${BACKEND_INTERNAL_URL}/api/v1/:path*`,
      },
      // Interactive API docs, served from the same domain.
      { source: "/docs", destination: `${BACKEND_INTERNAL_URL}/docs` },
      { source: "/openapi.json", destination: `${BACKEND_INTERNAL_URL}/openapi.json` },
      // The platform health check. Proxied on purpose: it then verifies BOTH
      // processes are alive, which is the only thing worth restarting a
      // container over. A check that only proved Next.js was up would report
      // healthy while every API call 502'd.
      { source: "/health", destination: `${BACKEND_INTERNAL_URL}/health` },
    ];
  },

  /**
   * Security headers.
   *
   * Deliberately conservative rather than exhaustive: each of these closes a
   * real hole and none of them break the site.
   *
   * No Content-Security-Policy yet — a CSP that is wrong is worse than none,
   * because it breaks the page in ways that are hard to attribute. It belongs
   * in a change of its own, tested against a preview deployment.
   */
  async headers() {
    return [
      {
        source: "/:path*",
        headers: [
          // Stop a browser second-guessing a declared content type, which is
          // how a text file becomes an executed script.
          { key: "X-Content-Type-Options", value: "nosniff" },
          // No framing: this site is never legitimately embedded.
          { key: "X-Frame-Options", value: "DENY" },
          // Send the origin to other sites, the full URL to our own — so an
          // outbound link cannot leak a lead id in the path.
          { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
          // Nothing here needs these.
          {
            key: "Permissions-Policy",
            value: "camera=(), microphone=(), geolocation=(), interest-cohort=()",
          },
        ],
      },
      {
        // Belt and braces with the noindex metadata in the (internal) layout:
        // a header covers responses that never render metadata at all.
        source: "/dashboard/:path*",
        headers: [{ key: "X-Robots-Tag", value: "noindex, nofollow" }],
      },
      {
        source: "/demo/:path*",
        headers: [{ key: "X-Robots-Tag", value: "noindex, nofollow" }],
      },
    ];
  },
};

export default nextConfig;
