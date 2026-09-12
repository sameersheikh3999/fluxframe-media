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
 *
 * ---------------------------------------------------------------------------
 * TWO DEPLOYMENT SHAPES, ONE CODEBASE
 *
 * `apiUrl` is allowed to be an EMPTY STRING, and that is the whole mechanism
 * behind supporting both:
 *
 *   Single service   NEXT_PUBLIC_API_URL=""      (or unset)
 *                    The browser posts to "/api/v1/leads" — same origin.
 *                    Next.js rewrites that to the FastAPI process running
 *                    beside it in the same container. No CORS involved at all.
 *
 *   Two services     NEXT_PUBLIC_API_URL="https://api.example.com"
 *                    The browser posts cross-origin and CORS applies.
 *
 * Nothing else in the application changes between the two. See
 * docs/deployment.md.
 * ---------------------------------------------------------------------------
 */

/**
 * An absolute URL, or an empty string meaning "same origin as this page".
 *
 * Empty is a deliberate, supported value rather than a missing one — hence no
 * fallback and no throw. A malformed non-empty value still fails loudly,
 * because that is a typo rather than a choice.
 */
function optionalBaseUrl(name: string, value: string | undefined): string {
  const raw = (value ?? "").trim();
  if (raw === "") return "";
  try {
    new URL(raw);
  } catch {
    throw new Error(
      `${name} must be an absolute URL, or empty for same-origin. ` +
        `Received: ${JSON.stringify(raw)}`,
    );
  }
  // Trailing slashes make `${base}/api/v1/leads` produce a double slash.
  return raw.replace(/\/+$/, "");
}

function requiredUrl(name: string, value: string | undefined, fallback: string): string {
  const raw = (value ?? fallback).trim();
  try {
    new URL(raw);
  } catch {
    throw new Error(`${name} must be an absolute URL. Received: ${JSON.stringify(raw)}`);
  }
  return raw.replace(/\/+$/, "");
}

/** Safe to use anywhere, including the browser. */
export const env = {
  siteUrl: requiredUrl(
    "NEXT_PUBLIC_SITE_URL",
    process.env.NEXT_PUBLIC_SITE_URL,
    "http://localhost:3000",
  ),
  /** Empty string = same origin. See the note above. */
  apiUrl: optionalBaseUrl("NEXT_PUBLIC_API_URL", process.env.NEXT_PUBLIC_API_URL),
} as const;

/**
 * Where the SERVER should reach the API.
 *
 * Distinct from `env.apiUrl`, which is what the browser uses, and the
 * difference matters in the single-service deployment: the browser must go
 * through the public origin, but a Server Component running inside the same
 * container should talk to `http://127.0.0.1:8000` directly. Going out to the
 * public URL and back in would add a network round trip, a TLS handshake and a
 * dependency on the load balancer to render a page from a process that is
 * already on the same machine.
 *
 * Resolution order:
 *   1. BACKEND_INTERNAL_URL   explicit, set by the combined Dockerfile
 *   2. NEXT_PUBLIC_API_URL    the two-service deployment
 *   3. http://127.0.0.1:8000  local development default
 */
export function serverApiUrl(): string {
  const internal = (process.env.BACKEND_INTERNAL_URL ?? "").trim();
  if (internal) return internal.replace(/\/+$/, "");
  if (env.apiUrl) return env.apiUrl;
  return "http://127.0.0.1:8000";
}

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
