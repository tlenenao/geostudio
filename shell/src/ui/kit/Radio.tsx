// SPDX-License-Identifier: Apache-2.0
import * as RadioGroupPrimitive from "@radix-ui/react-radio-group";
import React, { useRef } from "react";
import { cn } from "../../lib/utils";

function RadioGroup({
  className,
  value,
  onValueChange,
  disabled,
  children,
  ...props
}: React.ComponentPropsWithoutRef<typeof RadioGroupPrimitive.Root> & {
  children?: React.ReactNode;
}) {
  const itemsRef = useRef<Map<string, HTMLButtonElement>>(new Map());

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (disabled || !value || !onValueChange) return;

    const items = Array.from(itemsRef.current.values());
    const currentIndex = items.findIndex((item) => item.getAttribute("value") === value);

    let nextIndex = -1;
    if (e.key === "ArrowDown" || e.key === "ArrowRight") {
      e.preventDefault();
      nextIndex = (currentIndex + 1) % items.length;
    } else if (e.key === "ArrowUp" || e.key === "ArrowLeft") {
      e.preventDefault();
      nextIndex = (currentIndex - 1 + items.length) % items.length;
    }

    if (nextIndex !== -1) {
      const nextValue = items[nextIndex].getAttribute("value");
      if (nextValue) {
        onValueChange(nextValue);
        items[nextIndex].focus();
      }
    }
  };

  return (
    <RadioGroupPrimitive.Root
      className={cn("flex flex-col gap-2", className)}
      value={value}
      onValueChange={onValueChange}
      disabled={disabled}
      onKeyDown={handleKeyDown}
      {...props}
    >
      <RadioGroupContextProvider itemsRef={itemsRef}>{children}</RadioGroupContextProvider>
    </RadioGroupPrimitive.Root>
  );
}

const RadioGroupItemsContext = React.createContext<
  React.MutableRefObject<Map<string, HTMLButtonElement>>
>({ current: new Map() });

function RadioGroupContextProvider({
  itemsRef,
  children,
}: {
  itemsRef: React.MutableRefObject<Map<string, HTMLButtonElement>>;
  children?: React.ReactNode;
}) {
  return (
    <RadioGroupItemsContext.Provider value={itemsRef}>{children}</RadioGroupItemsContext.Provider>
  );
}

function RadioItem({ value, children }: { value: string; children: React.ReactNode }) {
  const id = `radio-${value}`;
  const itemsRef = React.useContext(RadioGroupItemsContext);
  const itemRef = useRef<HTMLButtonElement>(null);

  React.useEffect(() => {
    if (itemRef.current) {
      itemsRef.current.set(value, itemRef.current);
      return () => {
        itemsRef.current.delete(value);
      };
    }
  }, [value, itemsRef]);

  return (
    <div className="flex items-center gap-2">
      <RadioGroupPrimitive.Item
        ref={itemRef}
        id={id}
        value={value}
        aria-label={typeof children === "string" ? children : undefined}
        className="flex h-4 w-4 items-center justify-center rounded-full border border-rule bg-surface data-[state=checked]:border-accent focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent disabled:cursor-not-allowed disabled:opacity-50"
      >
        <RadioGroupPrimitive.Indicator className="block h-2 w-2 rounded-full bg-accent" />
      </RadioGroupPrimitive.Item>
      <label htmlFor={id} className="text-sm text-ink">
        {children}
      </label>
    </div>
  );
}

export const Radio = { Group: RadioGroup, Item: RadioItem };
