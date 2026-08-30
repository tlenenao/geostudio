// SPDX-License-Identifier: Apache-2.0
import * as AvatarPrimitive from "@radix-ui/react-avatar";

export function Avatar({ src, alt, fallback }: { src?: string; alt: string; fallback: string }) {
  return (
    <AvatarPrimitive.Root className="flex h-8 w-8 items-center justify-center overflow-hidden rounded-full bg-sunken">
      {src && <AvatarPrimitive.Image src={src} alt={alt} className="h-full w-full object-cover" />}
      <AvatarPrimitive.Fallback className="text-xs font-medium text-ink-2" delayMs={0}>
        {fallback}
      </AvatarPrimitive.Fallback>
    </AvatarPrimitive.Root>
  );
}
