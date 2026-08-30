// SPDX-License-Identifier: Apache-2.0
import * as ToastPrimitive from "@radix-ui/react-toast";
import { t } from "../../i18n";

export function Toast({
  open,
  onOpenChange,
  title,
  description,
  action,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  title: string;
  description?: string;
  action?: { label: string; onClick: () => void };
}) {
  return (
    <ToastPrimitive.Root
      open={open}
      onOpenChange={onOpenChange}
      className="rounded-md border border-rule bg-raised p-3 shadow-md"
    >
      <ToastPrimitive.Title className="text-sm font-medium text-ink">{title}</ToastPrimitive.Title>
      {description && (
        <ToastPrimitive.Description className="mt-1 text-xs text-ink-2">
          {description}
        </ToastPrimitive.Description>
      )}
      {action && (
        <ToastPrimitive.Action altText={action.label} asChild>
          <button onClick={action.onClick} className="mt-2 text-xs font-medium text-accent">
            {action.label}
          </button>
        </ToastPrimitive.Action>
      )}
      <ToastPrimitive.Close
        aria-label={t("toast.close")}
        className="absolute right-2 top-2 text-ink-3"
      >
        ×
      </ToastPrimitive.Close>
    </ToastPrimitive.Root>
  );
}
