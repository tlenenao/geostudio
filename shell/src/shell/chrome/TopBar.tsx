// SPDX-License-Identifier: Apache-2.0
import { NewItemButton } from "../NewItemButton";
import { ImportFileButton } from "../ImportFileButton";
import { Tileset3DUploadButton } from "../Tileset3DUploadButton";
import { AccountMenu } from "./AccountMenu";
import { NotificationBell } from "./NotificationBell";

export function TopBar({ tileset3dEnabled }: { tileset3dEnabled: boolean }) {
  return (
    <header className="flex items-center justify-between border-b border-rule px-6 py-3">
      <span className="text-lg font-bold text-ink">GeoStudio</span>
      <div className="flex items-center gap-3 text-sm">
        <NewItemButton />
        <ImportFileButton />
        {tileset3dEnabled && <Tileset3DUploadButton />}
        <NotificationBell />
        <AccountMenu />
      </div>
    </header>
  );
}
