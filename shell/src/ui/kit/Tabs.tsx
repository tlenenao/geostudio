// SPDX-License-Identifier: Apache-2.0
import * as TabsPrimitive from "@radix-ui/react-tabs";
import { cn } from "../../lib/utils";

export function Tabs({
  className,
  defaultValue,
  tabs,
  "aria-label": ariaLabel,
}: {
  className?: string;
  defaultValue: string;
  tabs: { value: string; label: string; content: React.ReactNode }[];
  "aria-label"?: string;
}) {
  return (
    <TabsPrimitive.Root
      defaultValue={defaultValue}
      className={cn("flex flex-col gap-2", className)}
    >
      <TabsPrimitive.List aria-label={ariaLabel} className="flex gap-1 border-b border-rule">
        {tabs.map((tab) => (
          <TabsPrimitive.Trigger
            key={tab.value}
            value={tab.value}
            className="border-b-2 border-transparent px-3 py-2 text-sm text-ink data-[state=active]:border-accent data-[state=active]:text-accent focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent"
          >
            {tab.label}
          </TabsPrimitive.Trigger>
        ))}
      </TabsPrimitive.List>
      {tabs.map((tab) => (
        <TabsPrimitive.Content key={tab.value} value={tab.value}>
          {tab.content}
        </TabsPrimitive.Content>
      ))}
    </TabsPrimitive.Root>
  );
}
