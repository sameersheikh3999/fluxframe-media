/**
 * A transport-only proxy from the browser to the backend's internal endpoints.
 *
 * The demo page and the dashboard's action buttons are Client Components, so
 * they cannot hold `INTERNAL_API_SECRET`. They post here instead; this handler
 * runs on the server, attaches the secret and forwards.
 *
 * THE RULE: this file attaches a header and forwards. Nothing else. No
 * validation beyond a path allowlist, no transformation, no business logic. A
 * proxy is exactly where "just a little logic" starts accumulating, and the
 * whole point of this architecture is that Next.js holds none — see
 * docs/decisions/0005. If this file ever grows past about a hundred lines,
 * something has migrated into the wrong layer.
 */

import { NextResponse } from "next/server";

import { env, serverEnv } from "@/config/env";

/**
 * Only these backend paths are reachable through the proxy.
 *
 * Without an allowlist, this handler forwards ANY path with a valid internal
 * secret attached — turning a convenience into a way to reach every endpoint on
 * the backend from a browser. Default-deny is the only safe posture for a
 * wildcard route.
 */
const ALLOWED = [
  /^demo\/leads$/,
  /^admin\/outbox\/dispatch$/,
  /^dashboard\/leads\/[0-9a-f-]{36}\/status$/,
  /^dashboard\/leads\/[0-9a-f-]{36}\/rescore$/,
  /^dashboard\/leads\/[0-9a-f-]{36}\/sales-brief$/,
];

function isAllowed(path: string): boolean {
  return ALLOWED.some((pattern) => pattern.test(path));
}

async function forward(
  request: Request,
  segments: string[],
  method: "POST" | "PATCH",
): Promise<NextResponse> {
  const path = segments.join("/");

  if (!isAllowed(path)) {
    return NextResponse.json(
      { error: { code: "not_allowed", message: "Unknown internal route." } },
      { status: 404 },
    );
  }

  const { internalApiSecret } = serverEnv();
  const body = await request.text();

  try {
    const response = await fetch(`${env.apiUrl}/api/v1/${path}`, {
      method,
      headers: {
        "Content-Type": "application/json",
        "X-Internal-Secret": internalApiSecret,
      },
      body: body || undefined,
      cache: "no-store",
    });

    const text = await response.text();
    return new NextResponse(text || null, {
      status: response.status,
      headers: { "Content-Type": "application/json" },
    });
  } catch {
    return NextResponse.json(
      {
        error: {
          code: "backend_unreachable",
          message: `Could not reach the API at ${env.apiUrl}.`,
        },
      },
      { status: 502 },
    );
  }
}

export async function POST(
  request: Request,
  context: { params: Promise<{ path: string[] }> },
): Promise<NextResponse> {
  const { path } = await context.params;
  return forward(request, path, "POST");
}

export async function PATCH(
  request: Request,
  context: { params: Promise<{ path: string[] }> },
): Promise<NextResponse> {
  const { path } = await context.params;
  return forward(request, path, "PATCH");
}
