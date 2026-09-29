// SPDX-License-Identifier: Apache-2.0
import { NewItemButton } from "../NewItemButton";
import { ImportFileButton } from "../ImportFileButton";
import { Tileset3DUploadButton } from "../Tileset3DUploadButton";
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
  return (
    <header className="flex items-center justify-between border-b border-rule px-6 py-3">
      <span className="text-lg font-bold text-ink">GeoStudio</span>
      <div className="flex items-center gap-3 text-sm">
        <button
          type="button"
          onClick={onOpenPalette}
          className="flex items-center gap-1.5 rounded-md border border-rule px-2 py-1 text-xs text-ink-2 hover:bg-sunken"
        >
          {t("commandPalette.triggerLabel")}
          <Kbd>⌘K</Kbd>
        </button>
        <NewItemButton />
        <ImportFileButton />
        {tileset3dEnabled && <Tileset3DUploadButton />}
        <NotificationBell />
        <AccountMenu />
      </div>
    </header>
  );
}
