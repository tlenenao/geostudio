// SPDX-License-Identifier: Apache-2.0
import * as ProgressPrimitive from "@radix-ui/react-progress";

export function Progress({
  value,
  max = 100,
  "aria-label": ariaLabel,
}: {
  value: number;
  max?: number;
  "aria-label": string;
}) {
  return (
    <ProgressPrimitive.Root
      aria-label={ariaLabel}
      value={value}
      max={max}
      className="h-2 w-full overflow-hidden rounded-full bg-sunken"
    >
      <ProgressPrimitive.Indicator
        style={{ transform: `translateX(-${100 - (value / max) * 100}%)` }}
        className="h-full w-full bg-accent transition-transform"
      />
    </ProgressPrimitive.Root>
  );
}
