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
      <div className="grid flex-1 grid-cols-[minmax(220px,280px)_minmax(360px,1fr)_minmax(260px,320px)] overflow-hidden">
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
      {/* Tâche 36 (SP-C6, D16) : `role="tabpanel"` était un `<div>` `flex-1
          overflow-y-auto` en `display:block` — un ITEM flex dont la hauteur
          réelle (mesurée : 514px) vient du flex-grow de son PARENT, mais qui
          ne compte PAS comme une taille "spécifiée" au sens CSS pour ses
          PROPRES enfants (essayé : le rendre lui-même `display:flex` avec un
          enfant `flex-1` ne suffit PAS non plus — vérifié empiriquement,
          toujours 0). Un onglet dont le contenu utilise `h-full` en cascade
          (la carte : `MapEditorPage` → `MapView` → canvas MapLibre) voyait
          cette chaîne entière résoudre à une hauteur de 0px : `overflow:
          hidden` sur `.maplibregl-map` (posé par MapLibre lui-même) rognait
          alors le canvas à cette boîte nulle — rien ne s'affichait, et aucun
          clic/tap sur la carte n'atteignait plus le canvas (il retombait sur
          ce `<div>` de panneau). La grille CSS (mode large, lignes 24-28
          ci-dessus) n'a jamais ce problème : CSS Grid donne explicitement une
          taille "définie" à ses items, utilisable par leurs propres enfants
          en pourcentage — flexbox ne le garantit pas. On reproduit donc ici
          le même mécanisme qui fait déjà marcher le mode large : une grille
          à une seule piste plutôt qu'un flex-item de plus. */}
      <div role="tabpanel" className="grid flex-1 grid-rows-[1fr] overflow-hidden">
        {active.content}
      </div>
    </div>
  );
}
