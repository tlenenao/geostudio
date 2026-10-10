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
        // Ne pose que les clés utiles : ne jamais écraser celles de l'enfant.
        ...(error && children.props["aria-invalid"] === undefined ? { "aria-invalid": true } : {}),
        ...(error || hint
          ? {
              "aria-describedby": [children.props["aria-describedby"], messageId]
                .filter(Boolean)
                .join(" "),
            }
          : {}),
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
