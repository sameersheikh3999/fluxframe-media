"use client";

import type { ReactNode } from "react";
import type { FieldError } from "react-hook-form";

import { Icon } from "@/components/ui/icon";
import type { Option } from "@/config/lead-options";

/**
 * Form primitives shared by the lead form.
 *
 * Accessibility is the point of these wrappers rather than styling. Each field
 * wires `htmlFor`/`id`, sets `aria-invalid` and `aria-describedby`, and renders
 * its error with `role="alert"` — so a screen reader announces the problem
 * instead of a sighted-only red border.
 */

type FieldShellProps = {
  id: string;
  label: string;
  error?: FieldError;
  hint?: string;
  optional?: boolean;
  children: ReactNode;
};

function FieldShell({ id, label, error, hint, optional, children }: FieldShellProps) {
  return (
    <div className="flex flex-col gap-2">
      <label htmlFor={id} className="text-sm font-medium">
        {label}
        {optional ? <span className="ml-2 text-ink-muted font-normal">optional</span> : null}
      </label>
      {children}
      {hint && !error ? (
        <p id={`${id}-hint`} className="text-xs text-ink-muted">
          {hint}
        </p>
      ) : null}
      {error ? (
        // An icon beside the colour: colour alone is not a reliable signal for
        // anyone with a colour vision deficiency.
        <p
          id={`${id}-error`}
          role="alert"
          className="flex items-center gap-1.5 text-xs text-accent"
        >
          <Icon name="alert" size="sm" />
          {error.message}
        </p>
      ) : null}
    </div>
  );
}

// `border-line-control` rather than `border-line-strong`: a form control's
// boundary carries meaning, so WCAG 1.4.11 requires 3:1 against the surface.
// The decorative rule colour measured 1.49:1 — a real failure for anyone with
// reduced contrast sensitivity, and invisible to everyone else.
//
// `min-h-touch` keeps every field at least 44px tall.
const controlClasses =
  "w-full min-h-touch rounded-none border bg-paper-raised px-4 py-3 text-sm " +
  "transition-colors duration-instant placeholder:text-ink-muted/70 " +
  "focus:outline-none focus-visible:border-ink";

function describedBy(id: string, error?: FieldError, hint?: string): string | undefined {
  if (error) return `${id}-error`;
  if (hint) return `${id}-hint`;
  return undefined;
}

export type TextFieldProps = {
  id: string;
  label: string;
  type?: "text" | "email" | "tel" | "url";
  placeholder?: string;
  autoComplete?: string;
  error?: FieldError;
  hint?: string;
  optional?: boolean;
  registration: Record<string, unknown>;
};

export function TextField({
  id,
  label,
  type = "text",
  placeholder,
  autoComplete,
  error,
  hint,
  optional,
  registration,
}: TextFieldProps) {
  return (
    <FieldShell id={id} label={label} error={error} hint={hint} optional={optional}>
      <input
        id={id}
        type={type}
        placeholder={placeholder}
        autoComplete={autoComplete}
        aria-invalid={error ? "true" : undefined}
        aria-describedby={describedBy(id, error, hint)}
        className={`${controlClasses} ${error ? "border-accent" : "border-line-control"}`}
        {...registration}
      />
    </FieldShell>
  );
}

export type SelectFieldProps = {
  id: string;
  label: string;
  options: readonly Option[];
  placeholder: string;
  error?: FieldError;
  hint?: string;
  registration: Record<string, unknown>;
};

export function SelectField({
  id,
  label,
  options,
  placeholder,
  error,
  hint,
  registration,
}: SelectFieldProps) {
  return (
    <FieldShell id={id} label={label} error={error} hint={hint}>
      <div className="relative">
        <Icon
          name="chevron-down"
          size="sm"
          className="pointer-events-none absolute right-4 top-1/2 -translate-y-1/2 text-ink-muted"
        />
      <select
        id={id}
        defaultValue=""
        aria-invalid={error ? "true" : undefined}
        aria-describedby={describedBy(id, error, hint)}
        className={`${controlClasses} appearance-none pr-10 ${
          error ? "border-accent" : "border-line-control"
        }`}
        {...registration}
      >
        <option value="" disabled>
          {placeholder}
        </option>
        {options.map((option) => (
          <option key={option.value} value={option.value}>
            {option.label}
          </option>
        ))}
      </select>
      </div>
    </FieldShell>
  );
}

export type TextAreaFieldProps = {
  id: string;
  label: string;
  placeholder?: string;
  rows?: number;
  error?: FieldError;
  hint?: string;
  optional?: boolean;
  registration: Record<string, unknown>;
};

export function TextAreaField({
  id,
  label,
  placeholder,
  rows = 5,
  error,
  hint,
  optional,
  registration,
}: TextAreaFieldProps) {
  return (
    <FieldShell id={id} label={label} error={error} hint={hint} optional={optional}>
      <textarea
        id={id}
        rows={rows}
        placeholder={placeholder}
        aria-invalid={error ? "true" : undefined}
        aria-describedby={describedBy(id, error, hint)}
        className={`${controlClasses} resize-y ${
          error ? "border-accent" : "border-line-control"
        }`}
        {...registration}
      />
    </FieldShell>
  );
}
