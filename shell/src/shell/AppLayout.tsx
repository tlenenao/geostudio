// SPDX-License-Identifier: Apache-2.0
import { lazy, Suspense, useEffect, useState } from "react";
import { useMe } from "../api/hooks";
import { TopBar } from "./chrome/TopBar";
import { DomainBar } from "./chrome/DomainBar";
import { BottomNav } from "./chrome/BottomNav";
import { StatusBar } from "./chrome/StatusBar";
import { useNarrowViewport } from "./chrome/useNarrowViewport";
import { useIsExportRender } from "./useIsExportRender";
import { t } from "../i18n";
import type { Profile } from "../auth/capabilities";

// D07 : chargé paresseusement — le chunk n'est demandé qu'au premier
// Ctrl/Cmd+K (ou clic sur le déclencheur visible de TopBar), jamais au
// chargement initial (patron déjà posé par SP-60 pour les routes, ici
// appliqué à un composant hors route).
const CommandPalette = lazy(() =>
  import("../ui/kit/CommandPalette").then((m) => ({ default: m.CommandPalette })),
);

export function AppLayout({ children }: { children: React.ReactNode }) {
  const meQuery = useMe();
  // GAP-31 : GET /me sert déjà `capabilities` sous la même forme exacte que
  // GET /instance (garanti par un test dédié côté cœur, cf. commentaire de
  // Me.capabilities dans api/types.ts) — un second appel réseau ici était
  // redondant. useInstanceInfo() reste utilisé ailleurs (TerrainPanel,
  // form.tsx, pages d'admin, NewItemButton, ItemActions, MapEditorPage...),
  // ce correctif ne touche que ce composant.
  const capabilities = meQuery.data?.capabilities;
  const readOnly = capabilities?.readOnly === true;
  const tileset3dEnabled = capabilities?.tileset3dEnabled === true;
  const isExportRender = useIsExportRender();
  const narrow = useNarrowViewport();
  const [paletteOpen, setPaletteOpen] = useState(false);

  useEffect(() => {
    function onKeyDown(e: KeyboardEvent) {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        setPaletteOpen(true);
      }
    }
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, []);

  // Cf. commentaire d'origine (conservé à l'identique) : le worker d'export
  // Playwright navigue directement sur une route protégée avec
  // ?exportRender=1 — le chrome (TopBar/DomainBar/StatusBar) ne doit pas
  // apparaître dans la capture.
  if (isExportRender) {
    return <div className="h-screen w-screen">{children}</div>;
  }

  const profile: Profile = {
    privileges: new Set(meQuery.data?.privileges ?? []),
    capabilities: {
      readOnly,
      etlEnabled: capabilities?.etlEnabled === true,
      exportEnabled: capabilities?.exportEnabled === true,
      appExportEnabled: capabilities?.appExportEnabled === true,
      tileset3dEnabled,
      terrain3dEnabled: capabilities?.terrain3dEnabled === true,
      copilotEnabled: capabilities?.copilotEnabled === true,
      quotasEnabled: capabilities?.quotasEnabled === true,
    },
  };

  // P31.03 : hauteur bornée à la fenêtre (h-dvh, pas min-h-screen) — c'est `main`
  // qui défile, TopBar/BottomNav/StatusBar restent ancrés et la carte ne dépasse
  // plus l'écran. `min-h-0` sur main : sans lui un flex-item ne descend pas sous
  // son contenu.
  return (
    <div className="flex h-dvh flex-col bg-background">
      {/* P33.05 : lien d'évitement, premier arrêt de tabulation. */}
      <a
        href="#main-content"
        className="sr-only focus:not-sr-only focus:absolute focus:left-2 focus:top-2 focus:z-50 focus:rounded-md focus:bg-raised focus:px-3 focus:py-2 focus:text-sm focus:text-ink focus:shadow-md"
      >
        {t("layout.skipToContent")}
      </a>
      {readOnly && (
        <p className="bg-warn-soft px-6 py-2 text-center text-sm text-warn">
          {t("layout.readOnlyBanner")}
        </p>
      )}
      <TopBar tileset3dEnabled={tileset3dEnabled} onOpenPalette={() => setPaletteOpen(true)} />
      {!narrow && <DomainBar profile={profile} />}
      <main
        id="main-content"
        tabIndex={-1}
        className="focus:outline-none flex min-h-0 flex-1 flex-col overflow-y-auto p-6"
      >
        {children}
      </main>
      {narrow && <BottomNav profile={profile} />}
      <StatusBar />
      {paletteOpen && (
        <Suspense fallback={null}>
          <CommandPalette open={paletteOpen} onOpenChange={setPaletteOpen} profile={profile} />
        </Suspense>
      )}
    </div>
  );
}
