/**
 * The form's dropdown options.
 *
 * Every `value` here is the exact string the backend validates, the database
 * stores and HubSpot receives. The `label` is the only part that is presentation.
 *
 * This file and `backend/app/domain/leads/enums.py` must agree. Today that is a
 * human responsibility; the mechanical fix is `openapi-typescript` generating
 * the union types from the live OpenAPI schema, at which point a mismatch
 * becomes a compile error. Worth doing once the contract stops moving — the
 * Zod schema below is built FROM these lists, so at least the form and its
 * validation can never disagree with each other.
 */

export type Option = { readonly value: string; readonly label: string };

export const industries: readonly Option[] = [
  { value: "dental", label: "Dental" },
  { value: "beauty", label: "Beauty & aesthetics" },
  { value: "fitness", label: "Fitness" },
  { value: "real_estate", label: "Real estate" },
  { value: "legal", label: "Legal" },
  { value: "physiotherapy", label: "Physiotherapy" },
  { value: "restaurant", label: "Restaurant & hospitality" },
  { value: "ecommerce", label: "E-commerce" },
  { value: "saas", label: "SaaS" },
  { value: "other", label: "Something else" },
] as const;

export const monthlyRevenues: readonly Option[] = [
  { value: "under_50k", label: "Under £50k / month" },
  { value: "50k_100k", label: "£50k – £100k / month" },
  { value: "100k_500k", label: "£100k – £500k / month" },
  { value: "500k_plus", label: "£500k+ / month" },
] as const;

export const marketingBudgets: readonly Option[] = [
  { value: "under_2k", label: "Under £2k / month" },
  { value: "2k_5k", label: "£2k – £5k / month" },
  { value: "5k_10k", label: "£5k – £10k / month" },
  { value: "10k_plus", label: "£10k+ / month" },
] as const;

export const contentVolumes: readonly Option[] = [
  { value: "4", label: "4 videos / month" },
  { value: "8", label: "8 videos / month" },
  { value: "12", label: "12 videos / month" },
  { value: "20", label: "20 videos / month" },
  { value: "30_plus", label: "30+ videos / month" },
] as const;

export const primaryGoals: readonly Option[] = [
  { value: "lead_generation", label: "Generate more leads" },
  { value: "sales", label: "Drive direct sales" },
  { value: "brand_awareness", label: "Build brand awareness" },
  { value: "social_growth", label: "Grow our social following" },
  { value: "product_launch", label: "Launch a product or location" },
] as const;

export const startTimelines: readonly Option[] = [
  { value: "immediately", label: "Immediately" },
  { value: "within_30_days", label: "Within 30 days" },
  { value: "one_to_three_months", label: "In 1 – 3 months" },
  { value: "researching", label: "Just researching for now" },
] as const;

/** Extracts the permitted values, so Zod and the <select> can never diverge. */
export function valuesOf(options: readonly Option[]): [string, ...string[]] {
  const values = options.map((option) => option.value);
  return values as [string, ...string[]];
}

// --- demo generator controls ------------------------------------------------

export const demoQualities: readonly Option[] = [
  { value: "random", label: "Realistic mix" },
  { value: "mostly_hot", label: "Mostly hot" },
  { value: "mostly_warm", label: "Mostly warm" },
  { value: "mostly_cold", label: "Mostly cold" },
] as const;

export const demoScenarios: readonly Option[] = [
  { value: "normal_week", label: "Normal week" },
  { value: "high_intent_campaign", label: "High-intent campaign" },
  { value: "low_quality_campaign", label: "Low-quality campaign" },
  { value: "lead_surge", label: "Lead surge" },
] as const;

// --- display helpers --------------------------------------------------------

const ALL_OPTIONS: readonly Option[] = [
  ...industries,
  ...monthlyRevenues,
  ...marketingBudgets,
  ...contentVolumes,
  ...primaryGoals,
  ...startTimelines,
  ...demoQualities,
  ...demoScenarios,
];

/**
 * Turn a stored enum value back into its human label.
 *
 * Presentation only — this is the sort of thing the frontend IS allowed to do.
 * Computing a temperature would not be.
 */
export function labelFor(value: string | null | undefined): string {
  if (!value) return "—";
  const match = ALL_OPTIONS.find((option) => option.value === value);
  if (match) return match.label;
  // Unknown value (a backend enum the frontend has not caught up with):
  // degrade to something readable rather than showing a raw snake_case token.
  return value.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}
