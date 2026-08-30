// SPDX-License-Identifier: Apache-2.0
import * as ToolbarPrimitive from "@radix-ui/react-toolbar";
import { cn } from "../../lib/utils";

function ToolbarRoot({
  className,
  ...props
}: React.ComponentPropsWithoutRef<typeof ToolbarPrimitive.Root>) {
  return (
    <ToolbarPrimitive.Root
      className={cn(
        "flex items-center gap-1 rounded-md border border-rule bg-surface p-1",
        className,
      )}
      {...props}
    />
  );
}

function ToolbarButtonItem({
  className,
  ...props
}: React.ComponentPropsWithoutRef<typeof ToolbarPrimitive.Button>) {
  return (
    <ToolbarPrimitive.Button
      className={cn(
        "rounded-sm px-2 py-1 text-sm text-ink hover:bg-sunken focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent disabled:cursor-not-allowed disabled:opacity-50",
        className,
      )}
      {...props}
    />
  );
}

function ToolbarSeparatorItem() {
  return <ToolbarPrimitive.Separator className="mx-1 h-5 w-px bg-rule" />;
}

export const Toolbar = {
  Root: ToolbarRoot,
  Button: ToolbarButtonItem,
  Separator: ToolbarSeparatorItem,
};
