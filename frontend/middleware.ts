/**
 * Gate the internal tools with HTTP basic auth.
 *
 * This is deliberately minimal. There are no user accounts, no sessions and no
 * password hashing, because this application has exactly one operator and
 * building an identity system for one person is how portfolio projects die
 * before they ship.
 *
 * What it does do is stop a public URL from exposing a dashboard and a write
 * endpoint to anyone who guesses the path. Defence in depth, alongside the
 * backend's own `X-Internal-Secret` check — which is the real protection, since
 * it guards the API whether or not anyone goes through this frontend.
 *
 * Set DASHBOARD_BASIC_AUTH_USER and DASHBOARD_BASIC_AUTH_PASSWORD to enable it.
 * Leaving them unset keeps local development frictionless; in production you
 * want them set, and the README says so.
 */

import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";

const PROTECTED = ["/dashboard", "/demo"];

function unauthorised(): NextResponse {
  return new NextResponse("Authentication required.", {
    status: 401,
    headers: { "WWW-Authenticate": 'Basic realm="Fluxframe Ops", charset="UTF-8"' },
  });
}

/**
 * Compare two strings in time independent of how many characters match.
 *
 * A plain `===` short-circuits on the first difference, which leaks the secret
 * one character at a time to anyone who can measure response latency.
 */
function safeEqual(a: string, b: string): boolean {
  if (a.length !== b.length) return false;
  let mismatch = 0;
  for (let index = 0; index < a.length; index += 1) {
    mismatch |= a.charCodeAt(index) ^ b.charCodeAt(index);
  }
  return mismatch === 0;
}

export function middleware(request: NextRequest): NextResponse {
  const path = request.nextUrl.pathname;
  if (!PROTECTED.some((prefix) => path.startsWith(prefix))) {
    return NextResponse.next();
  }

  const user = process.env.DASHBOARD_BASIC_AUTH_USER ?? "";
  const password = process.env.DASHBOARD_BASIC_AUTH_PASSWORD ?? "";

  // Not configured: open. Convenient locally, and the backend's internal
  // secret still protects the data itself.
  if (!user || !password) return NextResponse.next();

  const header = request.headers.get("authorization");
  if (!header?.startsWith("Basic ")) return unauthorised();

  try {
    const decoded = atob(header.slice(6));
    const separator = decoded.indexOf(":");
    const suppliedUser = decoded.slice(0, separator);
    const suppliedPassword = decoded.slice(separator + 1);

    if (safeEqual(suppliedUser, user) && safeEqual(suppliedPassword, password)) {
      return NextResponse.next();
    }
  } catch {
    // Malformed credentials.
  }

  return unauthorised();
}

export const config = {
  matcher: ["/dashboard/:path*", "/demo/:path*"],
};
