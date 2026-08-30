// SPDX-License-Identifier: Apache-2.0
import { useState, type ReactNode } from "react";
import { useNarrowViewport } from "./useNarrowViewport";

export type TriptychTab = { id: string; label: string; content: ReactNode };

export function TriptychLayout({
  browse,
  work,
  inspect,
  defaultTabId,
}: {
  browse: TriptychTab;
  work: TriptychTab;
  inspect: TriptychTab;
  defaultTabId?: string;
}) {
  const narrow = useNarrowViewport();
  const tabs = [browse, work, inspect];
  const [activeId, setActiveId] = useState(defaultTabId ?? work.id);

  if (!narrow) {
    return (
      <div className="grid flex-1 grid-cols-[minmax(220px,280px)_1fr_minmax(260px,320px)] overflow-hidden">
        <div className="overflow-y-auto border-r border-rule">{browse.content}</div>
        <div className="overflow-hidden">{work.content}</div>
        <div className="overflow-y-auto border-l border-rule">{inspect.content}</div>
      </div>
    );
  }

  const active = tabs.find((tabItem) => tabItem.id === activeId) ?? work;
  return (
    <div className="flex flex-1 flex-col overflow-hidden">
      <div role="tablist" className="flex border-b border-rule">
        {tabs.map((tabItem) => (
          <button
            key={tabItem.id}
            role="tab"
            aria-selected={tabItem.id === activeId}
            className="flex-1 px-3 py-2 text-sm text-ink-2 aria-selected:border-b-2 aria-selected:border-accent aria-selected:font-semibold aria-selected:text-ink"
            onClick={() => setActiveId(tabItem.id)}
          >
            {tabItem.label}
          </button>
        ))}
      </div>
      <div role="tabpanel" className="flex-1 overflow-y-auto">
        {active.content}
      </div>
    </div>
  );
}
