// SPDX-License-Identifier: Apache-2.0
export function Spinner({ "aria-label": ariaLabel }: { "aria-label": string }) {
  return (
    <div
      role="status"
      aria-label={ariaLabel}
      className="h-4 w-4 animate-spin rounded-full border-2 border-rule border-t-accent"
    />
  );
}
