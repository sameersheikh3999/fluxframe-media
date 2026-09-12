/**
 * Public environment variables, validated once at module load.
 *
 * Anything prefixed NEXT_PUBLIC_ is inlined into the JavaScript bundle at build
 * time and is readable by anyone who opens devtools. That is fine for a site
 * URL and an API base URL. It is never acceptable for a token, a secret or a
 * database credential — those stay in server-only variables (no prefix) and are
 * read inside Server Components and Route Handlers, which never ship to the
 * browser.
 *
 * Validating here rather than at each call site means a typo fails the build
 * with a clear message, instead of producing `undefined` somewhere in a URL.
 *
 * Phase 0 needs only the site URL. NEXT_PUBLIC_API_URL is documented in
 * .env.local.example and starts being read in Phase 1, when there is finally
 * an API call to make.
 */

function requiredUrl(name: string, value: string | undefined, fallback: string): string {
  const raw = value ?? fallback;
  try {
    new URL(raw);
  } catch {
    throw new Error(`${name} must be an absolute URL. Received: ${JSON.stringify(raw)}`);
  }
  return raw.replace(/\/$/, "");
}

export const env = {
  siteUrl: requiredUrl(
    "NEXT_PUBLIC_SITE_URL",
    process.env.NEXT_PUBLIC_SITE_URL,
    "http://localhost:3000",
  ),
} as const;
