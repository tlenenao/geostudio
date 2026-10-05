// SPDX-License-Identifier: Apache-2.0
import { cloneElement, isValidElement } from "react";

export function Field({
  label,
  htmlFor,
  error,
  hint,
  children,
}: {
  label: string;
  htmlFor: string;
  error?: string;
  hint?: string;
  children: React.ReactNode;
}) {
  const messageId = `${htmlFor}-${error ? "error" : "hint"}`;
  // REV-223 : l'erreur/l'indice décrit le contrôle (relecture clavier), pas seulement
  // annoncé une fois par role="alert". Le contrôle relaie ses props (Input/Select/Textarea du kit).
  const control = isValidElement<Record<string, unknown>>(children)
    ? cloneElement(children, {
        "aria-invalid": error ? true : undefined,
        "aria-describedby": error || hint ? messageId : undefined,
      })
    : children;
  return (
    <div className="flex flex-col gap-1">
      <label htmlFor={htmlFor} className="text-sm font-medium text-ink">
        {label}
      </label>
      {control}
      {error ? (
        <p id={messageId} role="alert" className="text-xs text-danger">
          {error}
        </p>
      ) : hint ? (
        <p id={messageId} className="text-xs text-ink-3">
          {hint}
        </p>
      ) : null}
    </div>
  );
}
