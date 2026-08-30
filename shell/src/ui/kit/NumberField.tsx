// SPDX-License-Identifier: Apache-2.0
import { useEffect, useState } from "react";
import { Minus, Plus } from "lucide-react";
import { t } from "../../i18n";
import { IconButton } from "./IconButton";
import { Input } from "./Input";

export function NumberField({
  value,
  onValueChange,
  min,
  max,
  step = 1,
  "aria-label": ariaLabel,
}: {
  value: number;
  onValueChange: (value: number) => void;
  min?: number;
  max?: number;
  step?: number;
  "aria-label": string;
}) {
  const [displayValue, setDisplayValue] = useState(String(value));

  useEffect(() => {
    setDisplayValue(String(value));
  }, [value]);

  const clamp = (n: number) => {
    let clamped = n;
    if (min !== undefined) clamped = Math.max(min, clamped);
    if (max !== undefined) clamped = Math.min(max, clamped);
    return clamped;
  };

  return (
    <div className="flex items-center gap-1">
      <IconButton
        icon={<Minus size={14} />}
        aria-label={t("numberField.decrease")}
        size="sm"
        disabled={min !== undefined && value <= min}
        onClick={() => {
          const next = clamp(value - step);
          if (next !== value) onValueChange(next);
        }}
      />
      <Input
        type="number"
        aria-label={ariaLabel}
        value={displayValue}
        min={min}
        max={max}
        step={step}
        onChange={(e) => {
          setDisplayValue(e.target.value);
          const parsed = Number(e.target.value);
          if (!Number.isNaN(parsed)) onValueChange(clamp(parsed));
        }}
        className="w-20 text-center"
      />
      <IconButton
        icon={<Plus size={14} />}
        aria-label={t("numberField.increase")}
        size="sm"
        disabled={max !== undefined && value >= max}
        onClick={() => {
          const next = clamp(value + step);
          if (next !== value) onValueChange(next);
        }}
      />
    </div>
  );
}
