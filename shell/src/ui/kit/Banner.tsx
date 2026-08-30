// SPDX-License-Identifier: Apache-2.0
import { cva, type VariantProps } from "class-variance-authority";
import { cn } from "../../lib/utils";

const bannerVariants = cva("rounded-md border p-3 text-sm", {
  variants: {
    variant: {
      info: "border-accent-soft bg-accent-soft text-accent-ink",
      warn: "border-warn-soft bg-warn-soft text-warn",
      danger: "border-danger-soft bg-danger-soft text-danger",
    },
  },
  defaultVariants: { variant: "info" },
});

export function Banner({
  variant,
  children,
}: { children: React.ReactNode } & VariantProps<typeof bannerVariants>) {
  return (
    <div
      className={cn(bannerVariants({ variant }))}
      role={variant === "danger" ? "alert" : undefined}
    >
      {children}
    </div>
  );
}
