// SPDX-License-Identifier: Apache-2.0
import { useState } from "react";
import { Input } from "./Input";

const HEX_COLOR = /^#[0-9a-fA-F]{6}$/;

export function ColorField({
  value,
  onValueChange,
  "aria-label": ariaLabel,
}: {
  value: string;
  onValueChange: (value: string) => void;
  "aria-label": string;
}) {
  const [text, setText] = useState(value);

  return (
    <div className="flex items-center gap-2">
      <input
        type="color"
        aria-label={`${ariaLabel} (sélecteur)`}
        value={value}
        onChange={(e) => {
          setText(e.target.value);
          onValueChange(e.target.value);
        }}
        className="h-9 w-9 cursor-pointer rounded-md border border-rule bg-surface p-0.5"
      />
      <Input
        aria-label={ariaLabel}
        value={text}
        onChange={(e) => {
          setText(e.target.value);
          if (HEX_COLOR.test(e.target.value)) {
            onValueChange(e.target.value);
          }
        }}
        className="w-28 font-mono"
      />
    </div>
  );
}
