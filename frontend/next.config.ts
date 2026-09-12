import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  /**
   * Trace exactly which node_modules files the app imports and copy only those
   * into `.next/standalone`. Turns a ~400MB runtime image into a ~60MB one,
   * which is the difference between a fast Railway deploy and a slow one.
   */
  output: "standalone",

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
