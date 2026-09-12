/**
 * The shapes the backend actually returns.
 *
 * Hand-written for now, and mirroring `backend/app/schemas/leads.py`. The
 * upgrade path is `openapi-typescript`, generating these from the live
 * `/openapi.json` so a backend enum change becomes a frontend compile error
 * rather than a runtime surprise. That is worth doing once the contract stops
 * moving; until then, a generated file would churn on every commit.
 *
 * The enum value strings here are the same literals the backend validates, the
 * database stores and HubSpot receives — one vocabulary, end to end.
 */

export type LeadTemperature = "hot" | "warm" | "cold";

export type LeadStatus =
  | "new"
  | "qualified"
  | "contacted"
  | "booked"
  | "won"
  | "lost"
  | "disqualified";

export type CrmSyncStatus = "pending" | "synced" | "failed" | "skipped";

export type LeadSummary = {
  id: string;
  full_name: string;
  email: string;
  company_name: string;
  industry: string;
  monthly_marketing_budget: string;
  content_volume: string;
  score: number | null;
  temperature: LeadTemperature | null;
  status: LeadStatus;
  crm_sync_status: CrmSyncStatus;
  source: string;
  is_demo: boolean;
  created_at: string;
};

export type LeadListResponse = {
  items: LeadSummary[];
  total: number;
  limit: number;
  offset: number;
  has_more: boolean;
};

export type ScoreComponent = {
  dimension: string;
  input_value: string;
  points: number;
  reason: string;
};

/** Mirrors `ScoreResult.to_breakdown()`. This is the answer to "why 87?". */
export type ScoreBreakdown = {
  version: string;
  raw_total: number;
  final_score: number;
  temperature: string;
  was_clamped: boolean;
  components: ScoreComponent[];
};

export type LeadActivity = {
  id: string;
  activity_type: string;
  description: string;
  actor: string;
  occurred_at: string;
  metadata: Record<string, unknown>;
};

export type SalesBrief = {
  summary: string;
  pain_points: string[];
  urgency: string;
  suggested_service: string;
  opening_line: string;
  confidence: string;
  model: string;
  generated_at: string;
};

export type LeadDetail = {
  id: string;
  first_name: string;
  last_name: string;
  email: string;
  phone: string | null;
  company_name: string;
  website: string | null;

  industry: string;
  monthly_revenue: string;
  monthly_marketing_budget: string;
  content_volume: string;
  primary_goal: string;
  start_timeline: string;
  message: string | null;

  score: number | null;
  temperature: LeadTemperature | null;
  score_version: string | null;
  score_breakdown: ScoreBreakdown | null;

  status: LeadStatus;
  /** Supplied by the domain, so the UI cannot offer an illegal transition. */
  allowed_next_statuses: LeadStatus[];
  source: string;
  is_demo: boolean;

  crm_sync_status: CrmSyncStatus;
  crm_contact_id: string | null;
  crm_synced_at: string | null;
  crm_sync_error: string | null;
  crm_sync_attempts: number;

  attribution: Record<string, string | null>;
  activities: LeadActivity[];
  sales_brief: SalesBrief | null;

  created_at: string;
  updated_at: string;
};

export type DashboardStats = {
  total_leads: number;
  hot_leads: number;
  warm_leads: number;
  cold_leads: number;
  crm_sync_failures: number;
  crm_sync_pending: number;
  demo_leads: number;
  new_last_7_days: number;
  outbox_pending: number;
  outbox_dead_lettered: number;
};

export type GeneratedLead = {
  lead_id: string;
  full_name: string;
  company_name: string;
  email: string;
  industry: string;
  intended_temperature: string;
};

export type GenerateDemoLeadsResponse = {
  generated: GeneratedLead[];
  requested: number;
  message: string;
};

export type LeadCreateResponse = {
  id: string;
  created_at: string;
  message: string;
};

/** The single error envelope every failing endpoint returns. */
export type ApiErrorBody = {
  error: {
    code: string;
    message: string;
    details: { field: string | null; message: string }[];
    request_id: string | null;
  };
};
