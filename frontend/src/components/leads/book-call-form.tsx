"use client";

/**
 * The strategy-call form — the only interactive component on the public site,
 * and the reason the whole backend exists.
 *
 * Three things worth reading for:
 *
 * 1. **The idempotency key is generated ONCE, on mount**, not per submit.
 *    That is the entire double-click defence: both requests carry the same
 *    key, so the server recognises the second as a replay and returns the
 *    original lead instead of creating a duplicate.
 *
 * 2. **The button is disabled while submitting AND after success.** Belt and
 *    braces with the key above — one prevents the request, the other makes the
 *    request harmless if it happens anyway.
 *
 * 3. **It computes nothing.** No score, no temperature, no qualification logic.
 *    It collects, validates for UX, and posts. Every decision is the backend's.
 */

import { zodResolver } from "@hookform/resolvers/zod";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { useForm } from "react-hook-form";

import {
  SelectField,
  TextAreaField,
  TextField,
} from "@/components/leads/form-fields";
import {
  contentVolumes,
  industries,
  marketingBudgets,
  monthlyRevenues,
  primaryGoals,
  startTimelines,
} from "@/config/lead-options";
import { ApiError, submitLead } from "@/lib/api-client";
import {
  captureAttribution,
  emptyLeadForm,
  leadFormSchema,
  readAttribution,
  type LeadFormValues,
} from "@/lib/lead-form-schema";

type SubmitState = "idle" | "submitting" | "error";

export function BookCallForm() {
  const router = useRouter();
  const [state, setState] = useState<SubmitState>("idle");
  const [formError, setFormError] = useState<string | null>(null);
  const [requestId, setRequestId] = useState<string | null>(null);

  // Generated ONCE, on mount. `useState` with a lazy initialiser rather than
  // `useRef`: the value is stable for the component's life, React never reads
  // it during render, and crypto.randomUUID() is not re-run on every keystroke.
  //
  // This single line is the double-click defence. Both requests carry the same
  // key, so the server recognises the second as a replay and returns the
  // original lead instead of creating a duplicate.
  const [idempotencyKey] = useState(() => crypto.randomUUID());

  const {
    register,
    handleSubmit,
    setError,
    formState: { errors },
  } = useForm<LeadFormValues>({
    resolver: zodResolver(leadFormSchema),
    defaultValues: emptyLeadForm,
    mode: "onBlur",
  });

  // Stash UTM parameters on arrival, so they survive the visitor browsing a
  // few pages before reaching this form.
  useEffect(() => {
    captureAttribution();
  }, []);

  async function onSubmit(values: LeadFormValues) {
    setState("submitting");
    setFormError(null);
    setRequestId(null);

    try {
      await submitLead(
        {
          ...values,
          // Blank optionals mean "not provided", not "provided as empty".
          phone: values.phone || undefined,
          website: values.website || undefined,
          message: values.message || undefined,
          idempotency_key: idempotencyKey,
          attribution: readAttribution(),
        },
        idempotencyKey,
      );

      // Deliberately NOT resetting to "idle": the button stays disabled through
      // the navigation, so an impatient second click cannot fire.
      router.push("/thank-you");
    } catch (error) {
      setState("error");

      if (error instanceof ApiError) {
        setRequestId(error.requestId);
        // Server-side field errors are mapped onto the matching inputs, so a
        // rejection the client validator did not catch still lands in the
        // right place instead of as an opaque banner.
        for (const [field, message] of Object.entries(error.fieldErrors)) {
          if (field in emptyLeadForm) {
            setError(field as keyof LeadFormValues, { type: "server", message });
          }
        }
        setFormError(error.friendlyMessage);
      } else {
        setFormError("Something went wrong. Please try again, or email us directly.");
      }
    }
  }

  const busy = state === "submitting";

  return (
    <form onSubmit={handleSubmit(onSubmit)} noValidate className="space-y-10">
      <fieldset disabled={busy} className="space-y-10">
        <legend className="sr-only">Book a strategy call</legend>

        {/* --- about you --- */}
        <div className="space-y-6">
          <h2 className="font-display text-title font-semibold">About you</h2>
          <div className="grid gap-6 sm:grid-cols-2">
            <TextField
              id="first_name"
              label="First name"
              autoComplete="given-name"
              error={errors.first_name}
              registration={register("first_name")}
            />
            <TextField
              id="last_name"
              label="Last name"
              autoComplete="family-name"
              error={errors.last_name}
              registration={register("last_name")}
            />
            <TextField
              id="email"
              label="Work email"
              type="email"
              autoComplete="email"
              placeholder="you@company.com"
              error={errors.email}
              registration={register("email")}
            />
            <TextField
              id="phone"
              label="Phone"
              type="tel"
              autoComplete="tel"
              optional
              error={errors.phone}
              registration={register("phone")}
            />
          </div>
        </div>

        {/* --- about the business --- */}
        <div className="space-y-6">
          <h2 className="font-display text-title font-semibold">Your business</h2>
          <div className="grid gap-6 sm:grid-cols-2">
            <TextField
              id="company_name"
              label="Company name"
              autoComplete="organization"
              error={errors.company_name}
              registration={register("company_name")}
            />
            <TextField
              id="website"
              label="Website"
              optional
              placeholder="acme.com"
              hint="No need for https:// — we will add it."
              error={errors.website}
              registration={register("website")}
            />
            <SelectField
              id="industry"
              label="Industry"
              options={industries}
              placeholder="Select your industry"
              error={errors.industry}
              registration={register("industry")}
            />
            <SelectField
              id="monthly_revenue"
              label="Monthly revenue"
              options={monthlyRevenues}
              placeholder="Select a range"
              error={errors.monthly_revenue}
              registration={register("monthly_revenue")}
            />
          </div>
        </div>

        {/* --- the engagement --- */}
        <div className="space-y-6">
          <h2 className="font-display text-title font-semibold">What you need</h2>
          <div className="grid gap-6 sm:grid-cols-2">
            <SelectField
              id="monthly_marketing_budget"
              label="Monthly marketing budget"
              options={marketingBudgets}
              placeholder="Select a range"
              error={errors.monthly_marketing_budget}
              registration={register("monthly_marketing_budget")}
            />
            <SelectField
              id="content_volume"
              label="Content volume"
              options={contentVolumes}
              placeholder="Select a volume"
              error={errors.content_volume}
              registration={register("content_volume")}
            />
            <SelectField
              id="primary_goal"
              label="Primary goal"
              options={primaryGoals}
              placeholder="Select a goal"
              error={errors.primary_goal}
              registration={register("primary_goal")}
            />
            <SelectField
              id="start_timeline"
              label="When would you start?"
              options={startTimelines}
              placeholder="Select a timeline"
              error={errors.start_timeline}
              registration={register("start_timeline")}
            />
          </div>

          <TextAreaField
            id="message"
            label="Anything else we should know?"
            optional
            placeholder="What are you trying to grow, and what has not worked so far?"
            hint="The more specific you are, the more useful the call will be."
            error={errors.message}
            registration={register("message")}
          />
        </div>
      </fieldset>

      {/* role="alert" so the failure is announced, not just shown. */}
      {formError ? (
        <div
          role="alert"
          className="border border-accent bg-accent/5 px-5 py-4 text-sm text-ink"
        >
          <p className="font-medium">{formError}</p>
          {requestId ? (
            <p className="mt-2 text-xs text-ink-muted">
              Reference: <span className="font-mono">{requestId}</span>
            </p>
          ) : null}
        </div>
      ) : null}

      <div className="flex flex-wrap items-center gap-4 border-t border-line pt-8">
        <button
          type="submit"
          disabled={busy}
          className="inline-flex items-center justify-center rounded-full border border-ink bg-ink px-8 py-3.5 text-sm font-medium text-ink-inverse transition-colors hover:border-accent hover:bg-accent disabled:cursor-not-allowed disabled:opacity-60"
        >
          {busy ? "Sending…" : "Book my strategy call"}
        </button>
        <p className="text-xs text-ink-muted">
          We reply within one business day. No automated sequences.
        </p>
      </div>
    </form>
  );
}
