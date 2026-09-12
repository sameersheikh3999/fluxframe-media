/**
 * The browser's HTTP client for the public API.
 *
 * Used by the lead form and nothing else. It carries no credentials, because
 * `POST /api/v1/leads` is a public endpoint that anonymous visitors call —
 * which is exactly why this path goes straight to FastAPI rather than through a
 * Next.js proxy. See docs/decisions/0005.
 *
 * The one job beyond `fetch` is normalising errors. The backend returns one
 * envelope for every failure, so this turns any of them into a single
 * `ApiError` type and the form writes one error handler instead of five.
 */

import { env } from "@/config/env";
import type { ApiErrorBody, LeadCreateResponse } from "@/types/lead";

export class ApiError extends Error {
  readonly status: number;
  readonly code: string;
  readonly fieldErrors: Record<string, string>;
  readonly requestId: string | null;

  constructor(
    status: number,
    code: string,
    message: string,
    fieldErrors: Record<string, string> = {},
    requestId: string | null = null,
  ) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
    this.fieldErrors = fieldErrors;
    this.requestId = requestId;
  }

  /** Wording a visitor should actually see, by failure class. */
  get friendlyMessage(): string {
    if (this.status === 429) {
      return "Too many submissions from this connection. Please wait a moment and try again.";
    }
    if (this.status === 503) {
      return "We are briefly unable to accept enquiries. Please try again shortly.";
    }
    if (this.status >= 500) {
      return "Something went wrong on our side. Please try again, or email us directly.";
    }
    if (this.status === 422 && Object.keys(this.fieldErrors).length > 0) {
      return "Please check the highlighted fields and try again.";
    }
    return this.message;
  }
}

async function toApiError(response: Response): Promise<ApiError> {
  let code = `http_${response.status}`;
  let message = "Something went wrong.";
  const fieldErrors: Record<string, string> = {};
  let requestId: string | null = response.headers.get("X-Request-ID");

  try {
    const body = (await response.json()) as Partial<ApiErrorBody>;
    if (body.error) {
      code = body.error.code ?? code;
      message = body.error.message ?? message;
      requestId = body.error.request_id ?? requestId;
      for (const detail of body.error.details ?? []) {
        if (detail.field) fieldErrors[detail.field] = detail.message;
      }
    }
  } catch {
    // A non-JSON body (a proxy error page, say) is still a failure we can
    // report; there is just nothing more to extract from it.
  }

  return new ApiError(response.status, code, message, fieldErrors, requestId);
}

export type SubmitLeadPayload = Record<string, unknown>;

/**
 * Submit the strategy-call form.
 *
 * `idempotencyKey` is generated once per form mount and sent on every attempt,
 * so a double-click or a retry after a flaky connection produces exactly one
 * lead — the server returns the original instead of creating a second.
 */
export async function submitLead(
  payload: SubmitLeadPayload,
  idempotencyKey: string,
  signal?: AbortSignal,
): Promise<LeadCreateResponse> {
  let response: Response;
  try {
    response = await fetch(`${env.apiUrl}/api/v1/leads`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "Idempotency-Key": idempotencyKey,
      },
      body: JSON.stringify(payload),
      signal,
    });
  } catch {
    // fetch only rejects on a network-level failure, never on a 4xx/5xx.
    throw new ApiError(
      0,
      "network_error",
      "We could not reach the server. Please check your connection and try again.",
      {},
      null,
    );
  }

  if (!response.ok) {
    throw await toApiError(response);
  }

  return (await response.json()) as LeadCreateResponse;
}
