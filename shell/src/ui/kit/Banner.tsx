// SPDX-License-Identifier: Apache-2.0
import { cva, type VariantProps } from "class-variance-authority";
import { t } from "../../i18n";
import { cn } from "../../lib/utils";
import { Button } from "./Button";

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

// `onRetry` : état d'erreur de chargement uniforme (message + « Réessayer »).
export function Banner({
  variant,
  children,
  onRetry,
}: { children: React.ReactNode; onRetry?: () => void } & VariantProps<typeof bannerVariants>) {
  return (
    <div
      className={cn(bannerVariants({ variant }))}
      role={variant === "danger" ? "alert" : undefined}
    >
      {children}
      {onRetry && (
        <>
          {" "}
          <Button size="sm" variant="outline" onClick={onRetry}>
            {t("common.retry")}
          </Button>
        </>
      )}
    </div>
  );
}
