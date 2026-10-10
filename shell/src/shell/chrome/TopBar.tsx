// SPDX-License-Identifier: Apache-2.0
import { lazy, Suspense, useState } from "react";
import { Menu, Search } from "lucide-react";
const NewItemButton = lazy(() =>
  import("../NewItemButton").then((m) => ({ default: m.NewItemButton })),
);
const ImportFileButton = lazy(() =>
  import("../ImportFileButton").then((m) => ({ default: m.ImportFileButton })),
);
const Tileset3DUploadButton = lazy(() =>
  import("../Tileset3DUploadButton").then((m) => ({ default: m.Tileset3DUploadButton })),
);
import { AccountMenu } from "./AccountMenu";
import { NotificationBell } from "./NotificationBell";
import { Kbd } from "../../ui/kit/Kbd";
import { t } from "../../i18n";

export function TopBar({
  tileset3dEnabled,
  onOpenPalette,
}: {
  tileset3dEnabled: boolean;
  onOpenPalette: () => void;
}) {
  // P31.02 : sous 640 px les actions de création (palette, Nouveau, Importer,
  // 3D) sont repliées derrière un bouton « Actions » (aria-expanded) ; Notifications
  // et Compte restent sur la 1re ligne. Elles restent MONTÉES quand elles sont
  // repliées (`hidden`) : un tiroir ouvert ne doit pas se démonter avec elles.
  const [actionsOpen, setActionsOpen] = useState(false);
  return (
    <header className="flex flex-wrap items-center justify-between gap-y-2 border-b border-rule px-6 py-3 max-sm:px-3 [@media(max-height:500px)]:py-1">
      <span className="text-lg font-bold text-ink">GeoStudio</span>
      <div
        id="topbar-actions"
        className={`${actionsOpen ? "flex" : "max-sm:hidden"} w-full sm:flex flex-wrap items-center gap-2 text-sm max-sm:order-last sm:ml-auto sm:mr-3 sm:w-auto sm:gap-3`}
      >
        <button
          type="button"
          onClick={onOpenPalette}
          className="flex min-h-6 items-center gap-1.5 rounded-md border border-rule px-2 py-1 text-xs text-ink-2 hover:bg-sunken pointer-coarse:min-h-11 pointer-coarse:min-w-11 pointer-coarse:justify-center"
        >
          {/* Pointeur grossier (P31.12) : simple icône de recherche, sans
              libellé visible ni raccourci clavier (pas de clavier physique). */}
          <Search aria-hidden className="hidden size-4 pointer-coarse:block" />
          <span className="pointer-coarse:sr-only">{t("commandPalette.triggerLabel")}</span>
          <span className="pointer-coarse:hidden">
            <Kbd>⌘K</Kbd>
          </span>
        </button>
        <Suspense fallback={null}>
          <NewItemButton />
          <ImportFileButton />
          {tileset3dEnabled && <Tileset3DUploadButton />}
        </Suspense>
      </div>
      <div className="flex items-center gap-1 sm:gap-3 sm:text-sm">
        <button
          type="button"
          aria-expanded={actionsOpen}
          aria-controls="topbar-actions"
          aria-label={t("topbar.actions")}
          onClick={() => setActionsOpen((o) => !o)}
          className="inline-flex min-h-6 min-w-6 items-center justify-center rounded-md p-2 text-ink-2 hover:bg-sunken pointer-coarse:min-h-11 pointer-coarse:min-w-11 sm:hidden"
        >
          <Menu aria-hidden className="size-4" />
        </button>
        <NotificationBell />
        <AccountMenu />
      </div>
    </header>
  );
}
