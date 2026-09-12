import "server-only";

/**
 * The server's HTTP client for the backend's INTERNAL endpoints.
 *
 * `import "server-only"` at the top is the enforcement, not a convention: if any
 * Client Component ever imports this module, the build fails. That is what
 * guarantees `INTERNAL_API_SECRET` cannot reach a browser bundle.
 *
 * Used by dashboard Server Components (which render on Vercel and stream HTML)
 * and by the `/api/internal/*` route handler (which forwards the demo
 * generator's calls). Both run on the server, both attach the shared secret,
 * neither exposes it.
 *
 * This module is transport only. It attaches a header, calls fetch and maps
 * errors. The moment it starts transforming data or making decisions, business
 * logic has begun migrating into Next.js — see docs/decisions/0005.
 */

import { serverApiUrl, serverEnv } from "@/config/env";
import type {
  DashboardStats,
  GenerateDemoLeadsResponse,
  LeadDetail,
  LeadListResponse,
  SalesBrief,
} from "@/types/lead";

export class BackendError extends Error {
  readonly status: number;
  readonly code: string;

  constructor(status: number, code: string, message: string) {
    super(message);
    this.name = "BackendError";
    this.status = status;
    this.code = code;
  }
}

type RequestOptions = {
  method?: "GET" | "POST" | "PATCH" | "DELETE";
  body?: unknown;
  /** Dashboard data must never be cached: it is why you opened the page. */
  cache?: RequestCache;
};

async function request<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const { internalApiSecret } = serverEnv();
  // `serverApiUrl()` rather than `env.apiUrl`: in the single-service
  // deployment this is http://127.0.0.1:8000, so a Server Component talks
  // straight to the FastAPI process beside it instead of taking a round trip
  // out through the public load balancer and back in.
  const base = serverApiUrl();

  let response: Response;
  try {
    response = await fetch(`${base}${path}`, {
      method: options.method ?? "GET",
      headers: {
        "Content-Type": "application/json",
        // The whole reason this module exists.
        "X-Internal-Secret": internalApiSecret,
      },
      body: options.body === undefined ? undefined : JSON.stringify(options.body),
      cache: options.cache ?? "no-store",
    });
  } catch {
    throw new BackendError(
      0,
      "backend_unreachable",
      `Could not reach the API at ${base}. Is the backend running?`,
    );
  }

  if (!response.ok) {
    let code = `http_${response.status}`;
    let message = response.statusText || "Request failed";
    try {
      const body = await response.json();
      code = body?.error?.code ?? code;
      message = body?.error?.message ?? message;
    } catch {
      // Nothing more to extract.
    }
    throw new BackendError(response.status, code, message);
  }

  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

// --- dashboard reads --------------------------------------------------------

export function getDashboardStats(): Promise<DashboardStats> {
  return request<DashboardStats>("/api/v1/dashboard/stats");
}

export type LeadListQuery = {
  temperature?: string;
  status?: string;
  crmSyncStatus?: string;
  search?: string;
  includeDemo?: boolean;
  limit?: number;
  offset?: number;
};

export function listLeads(query: LeadListQuery = {}): Promise<LeadListResponse> {
  const params = new URLSearchParams();
  if (query.temperature) params.set("temperature", query.temperature);
  if (query.status) params.set("status", query.status);
  if (query.crmSyncStatus) params.set("crm_sync_status", query.crmSyncStatus);
  if (query.search) params.set("search", query.search);
  if (query.includeDemo === false) params.set("include_demo", "false");
  params.set("limit", String(query.limit ?? 25));
  params.set("offset", String(query.offset ?? 0));

  return request<LeadListResponse>(`/api/v1/dashboard/leads?${params.toString()}`);
}

export function getLead(id: string): Promise<LeadDetail> {
  return request<LeadDetail>(`/api/v1/dashboard/leads/${id}`);
}

// --- dashboard writes -------------------------------------------------------

export function updateLeadStatus(id: string, status: string): Promise<LeadDetail> {
  return request<LeadDetail>(`/api/v1/dashboard/leads/${id}/status`, {
    method: "PATCH",
    body: { status, actor: "user:dashboard" },
  });
}

export function rescoreLead(id: string): Promise<LeadDetail> {
  return request<LeadDetail>(`/api/v1/dashboard/leads/${id}/rescore`, {
    method: "POST",
  });
}

export function generateSalesBrief(id: string): Promise<SalesBrief> {
  return request<SalesBrief>(`/api/v1/dashboard/leads/${id}/sales-brief`, {
    method: "POST",
  });
}

// --- demo and operations ----------------------------------------------------

export type GenerateDemoLeadsInput = {
  count: number;
  quality: string;
  scenario: string;
  industry?: string | null;
};

export function generateDemoLeads(
  input: GenerateDemoLeadsInput,
): Promise<GenerateDemoLeadsResponse> {
  return request<GenerateDemoLeadsResponse>("/api/v1/demo/leads", {
    method: "POST",
    body: {
      count: input.count,
      quality: input.quality,
      scenario: input.scenario,
      industry: input.industry || null,
    },
  });
}

export type DispatchReport = {
  claimed: number;
  processed: number;
  failed: number;
  dead_lettered: number;
  skipped: number;
};

export function dispatchOutbox(): Promise<DispatchReport> {
  return request<DispatchReport>("/api/v1/admin/outbox/dispatch", { method: "POST" });
}
