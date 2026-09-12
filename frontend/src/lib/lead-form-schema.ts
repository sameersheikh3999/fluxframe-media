/**
 * Client-side validation for the strategy-call form.
 *
 * This exists for UX, not for security. It gives inline errors as someone
 * types, instead of a round trip to discover a typo. The authoritative
 * validation is Pydantic in `backend/app/schemas/leads.py`, and the form must
 * handle a 422 from the server gracefully even though "it can't happen" —
 * because anyone can POST to the API without ever loading this page.
 *
 * The enum values come from `lead-options.ts` rather than being retyped, so the
 * validator and the dropdown are physically incapable of disagreeing.
 */

import { z } from "zod";

import {
  contentVolumes,
  industries,
  marketingBudgets,
  primaryGoals,
  startTimelines,
  valuesOf,
  monthlyRevenues,
} from "@/config/lead-options";

const requiredSelect = (options: readonly { value: string }[], message: string) =>
  z.enum(valuesOf(options as never), { message });

export const leadFormSchema = z.object({
  first_name: z
    .string()
    .trim()
    .min(1, "Please enter your first name.")
    .max(120, "That name is too long."),
  last_name: z
    .string()
    .trim()
    .min(1, "Please enter your last name.")
    .max(120, "That name is too long."),
  email: z
    .string()
    .trim()
    .min(1, "Please enter your email address.")
    .email("That does not look like a valid email address."),
  phone: z.string().trim().max(50, "That phone number is too long.").optional(),
  company_name: z
    .string()
    .trim()
    .min(1, "Please enter your company name.")
    .max(255, "That company name is too long."),
  // Accepts "acme.com" — the backend adds the scheme. People do not type
  // "https://", and rejecting them for it would lose real leads.
  website: z.string().trim().max(512, "That URL is too long.").optional(),

  industry: requiredSelect(industries, "Please choose your industry."),
  monthly_revenue: requiredSelect(
    monthlyRevenues,
    "Please choose a revenue range.",
  ),
  monthly_marketing_budget: requiredSelect(
    marketingBudgets,
    "Please choose a budget range.",
  ),
  content_volume: requiredSelect(
    contentVolumes,
    "Please choose how much content you need.",
  ),
  primary_goal: requiredSelect(primaryGoals, "Please choose your main goal."),
  start_timeline: requiredSelect(startTimelines, "Please choose a timeline."),

  message: z
    .string()
    .trim()
    .max(5000, "Please keep this under 5000 characters.")
    .optional(),
});

export type LeadFormValues = z.infer<typeof leadFormSchema>;

export const emptyLeadForm: LeadFormValues = {
  first_name: "",
  last_name: "",
  email: "",
  phone: "",
  company_name: "",
  website: "",
  industry: "" as LeadFormValues["industry"],
  monthly_revenue: "" as LeadFormValues["monthly_revenue"],
  monthly_marketing_budget: "" as LeadFormValues["monthly_marketing_budget"],
  content_volume: "" as LeadFormValues["content_volume"],
  primary_goal: "" as LeadFormValues["primary_goal"],
  start_timeline: "" as LeadFormValues["start_timeline"],
  message: "",
};

/**
 * Marketing attribution, read from the URL and the referrer.
 *
 * Collected because "which campaign produced our hot leads?" is the question
 * this whole system exists to answer. Note what is NOT collected: no IP
 * address, no fingerprint, no third-party tracker.
 */
export type Attribution = {
  utm_source?: string;
  utm_medium?: string;
  utm_campaign?: string;
  utm_content?: string;
  utm_term?: string;
  referrer?: string;
  landing_page?: string;
};

const UTM_KEYS = [
  "utm_source",
  "utm_medium",
  "utm_campaign",
  "utm_content",
  "utm_term",
] as const;

const STORAGE_KEY = "fluxframe_attribution";

/**
 * Capture attribution on first arrival and remember it for the session.
 *
 * Someone lands from an ad, browses three pages, then fills the form. By then
 * the UTM parameters are long gone from the URL, so they are stashed in
 * sessionStorage on first sight and read back at submit time.
 *
 * Every storage access is wrapped: private browsing and blocked site data both
 * make sessionStorage throw, and losing attribution must never break the form.
 */
export function captureAttribution(): void {
  if (typeof window === "undefined") return;

  try {
    const params = new URLSearchParams(window.location.search);
    const existing = window.sessionStorage.getItem(STORAGE_KEY);
    const hasUtm = UTM_KEYS.some((key) => params.get(key));

    // First touch wins: do not overwrite the campaign that actually brought
    // them here with a later internal navigation.
    if (existing && !hasUtm) return;

    const attribution: Attribution = {
      landing_page: window.location.pathname,
      referrer: document.referrer || undefined,
    };
    for (const key of UTM_KEYS) {
      const value = params.get(key);
      if (value) attribution[key] = value.slice(0, 255);
    }

    window.sessionStorage.setItem(STORAGE_KEY, JSON.stringify(attribution));
  } catch {
    // sessionStorage unavailable. Attribution is a nice-to-have.
  }
}

export function readAttribution(): Attribution {
  if (typeof window === "undefined") return {};
  try {
    const raw = window.sessionStorage.getItem(STORAGE_KEY);
    return raw ? (JSON.parse(raw) as Attribution) : {};
  } catch {
    return {};
  }
}
