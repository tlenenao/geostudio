// SPDX-License-Identifier: Apache-2.0
export function Kbd({ children }: { children: React.ReactNode }) {
  return (
    <kbd className="rounded border border-rule bg-sunken px-1.5 py-0.5 font-mono text-xs text-ink-2">
      {children}
    </kbd>
  );
}
