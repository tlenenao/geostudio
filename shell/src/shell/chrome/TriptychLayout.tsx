// SPDX-License-Identifier: Apache-2.0
import { useRef, useState, type KeyboardEvent, type ReactNode } from "react";
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
  const tabRefs = useRef<(HTMLButtonElement | null)[]>([]);

  if (!narrow) {
    return (
      // grid-rows-[minmax(0,1fr)] (P31.03) : sans piste bornée, la ligne
      // implicite (auto) grandit avec la colonne la plus haute et les
      // `overflow-y-auto` des colonnes ne défilent jamais — la page entière
      // dépasse alors la fenêtre.
      <div className="grid flex-1 grid-cols-[minmax(220px,280px)_minmax(360px,1fr)_minmax(260px,320px)] grid-rows-[minmax(0,1fr)] overflow-hidden">
        <div className="overflow-y-auto border-r border-rule">{browse.content}</div>
        <div className="overflow-hidden">{work.content}</div>
        <div className="overflow-y-auto border-l border-rule">{inspect.content}</div>
      </div>
    );
  }

  const active = tabs.find((tabItem) => tabItem.id === activeId) ?? work;

  // Patron WAI-ARIA tablist (P31.10) : flèches/Home/End déplacent la sélection
  // ET le focus ; tabindex itinérant (un seul onglet dans l'ordre de tabulation).
  function onTabKeyDown(e: KeyboardEvent, index: number) {
    const last = tabs.length - 1;
    const next =
      e.key === "ArrowRight"
        ? (index + 1) % tabs.length
        : e.key === "ArrowLeft"
          ? (index + last) % tabs.length
          : e.key === "Home"
            ? 0
            : e.key === "End"
              ? last
              : -1;
    if (next < 0) return;
    e.preventDefault();
    setActiveId(tabs[next].id);
    tabRefs.current[next]?.focus();
  }
  return (
    <div className="flex flex-1 flex-col overflow-hidden">
      <div role="tablist" className="flex border-b border-rule">
        {tabs.map((tabItem, index) => (
          <button
            key={tabItem.id}
            ref={(el) => {
              tabRefs.current[index] = el;
            }}
            role="tab"
            id={`triptych-tab-${tabItem.id}`}
            aria-controls="triptych-panel"
            aria-selected={tabItem.id === active.id}
            tabIndex={tabItem.id === active.id ? 0 : -1}
            onKeyDown={(e) => onTabKeyDown(e, index)}
            className="min-h-6 flex-1 px-3 py-2 text-sm pointer-coarse:min-h-11 text-ink-2 aria-selected:border-b-2 aria-selected:border-accent aria-selected:font-semibold aria-selected:text-ink"
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
      {/* P31.03 : piste `minmax(0,1fr)` + défilement interne — la zone de travail
          est bornée à la fenêtre (AppLayout `h-dvh`), le contenu long d'un onglet
          défile ici plutôt que d'étirer la page. */}
      <div
        role="tabpanel"
        id="triptych-panel"
        aria-labelledby={`triptych-tab-${active.id}`}
        className="grid flex-1 grid-rows-[minmax(0,1fr)] overflow-y-auto"
      >
        {active.content}
      </div>
    </div>
  );
}
