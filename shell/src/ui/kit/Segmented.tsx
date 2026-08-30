// SPDX-License-Identifier: Apache-2.0
import * as ToggleGroupPrimitive from "@radix-ui/react-toggle-group";
import { cn } from "../../lib/utils";

export function Segmented({
  className,
  value,
  onValueChange,
  options,
  ...props
}: {
  className?: string;
  value: string;
  onValueChange: (value: string) => void;
  options: { value: string; label: string }[];
} & Omit<
  React.ComponentPropsWithoutRef<typeof ToggleGroupPrimitive.Root>,
  "type" | "value" | "onValueChange" | "defaultValue"
>) {
  return (
    <ToggleGroupPrimitive.Root
      type="single"
      value={value}
      onValueChange={(next) => {
        if (next) onValueChange(next);
      }}
      className={cn("inline-flex rounded-md border border-rule bg-surface p-0.5", className)}
      {...props}
    >
      {options.map((option) => (
        <ToggleGroupPrimitive.Item
          key={option.value}
          value={option.value}
          className="rounded-sm px-3 py-1 text-sm text-ink data-[state=on]:bg-accent data-[state=on]:text-surface focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent"
        >
          {option.label}
        </ToggleGroupPrimitive.Item>
      ))}
    </ToggleGroupPrimitive.Root>
  );
}
