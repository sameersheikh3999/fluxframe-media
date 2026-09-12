/**
 * Environment configuration, validated once at module load.
 *
 * The split in this file is the security boundary of the whole frontend.
 *
 * `NEXT_PUBLIC_*` is inlined into the JavaScript bundle at build time and is
 * readable by anyone who opens devtools. That is fine for a site URL and an API
 * base URL. It is never acceptable for a token or a secret.
 *
 * Server-only variables (no prefix) are read inside Server Components, Route
 * Handlers and middleware, which never ship to the browser. `serverEnv()` is a
 * function rather than a constant so that importing this module from a Client
 * Component cannot accidentally pull a secret into the bundle — and it throws
 * loudly if it is ever called in the browser.
 */

function requiredUrl(name: string, value: string | undefined, fallback: string): string {
  const raw = (value ?? fallback).trim();
  try {
    new URL(raw);
  } catch {
    throw new Error(`${name} must be an absolute URL. Received: ${JSON.stringify(raw)}`);
  }
  // Trailing slashes make `${base}/api/v1/leads` produce a double slash.
  return raw.replace(/\/+$/, "");
}

/** Safe to use anywhere, including the browser. */
export const env = {
  siteUrl: requiredUrl(
    "NEXT_PUBLIC_SITE_URL",
    process.env.NEXT_PUBLIC_SITE_URL,
    "http://localhost:3000",
  ),
  apiUrl: requiredUrl(
    "NEXT_PUBLIC_API_URL",
    process.env.NEXT_PUBLIC_API_URL,
    "http://localhost:8000",
  ),
} as const;

export type ServerEnv = {
  /** Shared secret for the backend's internal endpoints. Never sent to a browser. */
  internalApiSecret: string;
  /** Optional HTTP basic auth over /dashboard and /demo. */
  dashboardUser: string;
  dashboardPassword: string;
};

/**
 * Server-only configuration.
 *
 * Throws if called in the browser. That is a deliberate tripwire: if this ever
 * fires, a secret was about to be bundled into client-side JavaScript.
 */
export function serverEnv(): ServerEnv {
  if (typeof window !== "undefined") {
    throw new Error("serverEnv() was called in the browser. This must never happen.");
  }
  return {
    internalApiSecret: process.env.INTERNAL_API_SECRET ?? "",
    dashboardUser: process.env.DASHBOARD_BASIC_AUTH_USER ?? "",
    dashboardPassword: process.env.DASHBOARD_BASIC_AUTH_PASSWORD ?? "",
  };
}
