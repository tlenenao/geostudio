// SPDX-License-Identifier: Apache-2.0
import { createContext, useCallback, useContext, useState, type ReactNode } from "react";
import * as ToastPrimitive from "@radix-ui/react-toast";
import { t } from "../../i18n";

type ToastVariant = "success" | "error";
type ToastEntry = { id: string; message: string; variant: ToastVariant };

type ToastContextValue = {
  showToast: (message: string, options?: { variant?: ToastVariant }) => void;
};

const ToastContext = createContext<ToastContextValue | null>(null);

export function useToast(): ToastContextValue {
  const ctx = useContext(ToastContext);
  if (!ctx) {
    throw new Error(t("toast.providerMissing"));
  }
  return ctx;
}

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<ToastEntry[]>([]);

  const showToast = useCallback((message: string, options?: { variant?: ToastVariant }) => {
    const id = crypto.randomUUID();
    const variant = options?.variant ?? "success";
    setToasts((prev) => [...prev, { id, message, variant }]);
  }, []);

  const dismiss = useCallback((id: string) => {
    setToasts((prev) => prev.filter((toast) => toast.id !== id));
  }, []);

  return (
    <ToastContext.Provider value={{ showToast }}>
      {children}
      {toasts.map((toast) => (
        <ToastPrimitive.Root
          key={toast.id}
          duration={4000}
          onOpenChange={(open) => {
            if (!open) dismiss(toast.id);
          }}
          role={toast.variant === "error" ? "alert" : "status"}
          className={
            toast.variant === "error"
              ? "rounded-md border border-danger bg-surface px-4 py-3 text-sm text-danger shadow-md"
              : "rounded-md border border-rule bg-surface px-4 py-3 text-sm text-ink shadow-md"
          }
        >
          <ToastPrimitive.Description>{toast.message}</ToastPrimitive.Description>
        </ToastPrimitive.Root>
      ))}
    </ToastContext.Provider>
  );
}
