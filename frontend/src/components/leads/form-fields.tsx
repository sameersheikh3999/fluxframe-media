"use client";

import type { ReactNode } from "react";
import type { FieldError } from "react-hook-form";

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
        <p id={`${id}-error`} role="alert" className="text-xs text-accent">
          {error.message}
        </p>
      ) : null}
    </div>
  );
}

const controlClasses =
  "w-full rounded-none border bg-paper-raised px-4 py-3 text-sm transition-colors " +
  "placeholder:text-ink-muted/70 focus:outline-none focus-visible:border-ink";

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
        className={`${controlClasses} ${error ? "border-accent" : "border-line-strong"}`}
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
      <select
        id={id}
        defaultValue=""
        aria-invalid={error ? "true" : undefined}
        aria-describedby={describedBy(id, error, hint)}
        className={`${controlClasses} appearance-none ${
          error ? "border-accent" : "border-line-strong"
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
          error ? "border-accent" : "border-line-strong"
        }`}
        {...registration}
      />
    </FieldShell>
  );
}
