// SPDX-License-Identifier: Apache-2.0
import { useEffect, useState } from "react";
import type { MapTerrainConfig } from "../api/types";
import { useInstanceInfo, useItemClient } from "../api/hooks";
import { Terrain3DUploadButton } from "./Terrain3DUploadButton";
import { t } from "../i18n";

export function TerrainPanel({
  value,
  onChange,
}: {
  value: MapTerrainConfig | null;
  onChange: (next: MapTerrainConfig | null) => void;
}) {
  const enabled = value != null;
  const client = useItemClient();
  const instanceQuery = useInstanceInfo();
  // Gate the hosted picker + upload button behind the capability flag, not
  // just the routes: an instance with CORE_TERRAIN3D_ENABLED=false must not
  // even offer UI that would hit a 404'd /terrain3d/* route (same discipline
  // as ExportPanel/exportEnabled in MapEditorPage.tsx). The external URL
  // field is never gated — it has no dependency on this capability.
  const terrain3dEnabled = instanceQuery.data?.terrain3dEnabled === true;
  const [hostedSources, setHostedSources] = useState<{ id: string; title: string }[]>([]);

  async function refreshHostedSources() {
    try {
      setHostedSources(await client.listHostedTerrain3DSources());
    } catch {
      setHostedSources([]); // liste vide plutôt qu'une erreur bloquante pour le champ URL manuelle
    }
  }

  useEffect(() => {
    if (enabled && terrain3dEnabled) void refreshHostedSources();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [enabled, terrain3dEnabled]);

  function toggle(checked: boolean) {
    onChange(checked ? { tilesUrl: "", encoding: "terrarium", exaggeration: 1 } : null);
  }

  function patch(partial: Partial<MapTerrainConfig>) {
    if (!value) return;
    onChange({ ...value, ...partial });
  }

  // `Number("") === 0`: clearing the field must not silently flatten the
  // terrain. An empty (or otherwise unparseable) input leaves the current
  // exaggeration untouched.
  function patchExaggeration(raw: string) {
    if (raw.trim() === "") return;
    const next = Number(raw);
    if (!Number.isFinite(next)) return;
    patch({ exaggeration: next });
  }

  function selectHosted(itemId: string) {
    if (!itemId) return;
    const coreUrl = client.getCoreUrl?.();
    if (!coreUrl) return;
    patch({
      tilesUrl: `${coreUrl}/terrain3d/${itemId}/tiles/{z}/{x}/{y}.png`,
      encoding: "terrarium",
    });
  }

  return (
    <div className="flex flex-col gap-2">
      <p className="mb-1 mt-3 text-xs font-medium text-ink-2">{t("terrainPanel.heading")}</p>
      <label className="flex items-center gap-2 text-sm">
        <input
          aria-label={t("terrainPanel.enableLabel")}
          type="checkbox"
          checked={enabled}
          onChange={(e) => toggle(e.target.checked)}
        />
        {t("terrainPanel.enableLabel")}
      </label>
      {enabled && value && (
        <>
          {terrain3dEnabled && (
            <>
              <label className="flex flex-col gap-1 text-sm">
                {t("terrainPanel.hostedLabel")}
                <select
                  aria-label={t("terrainPanel.hostedLabel")}
                  defaultValue=""
                  onChange={(e) => selectHosted(e.target.value)}
                >
                  <option value="">{t("terrainPanel.chooseHostedOption")}</option>
                  {hostedSources.map((s) => (
                    <option key={s.id} value={s.id}>
                      {s.title}
                    </option>
                  ))}
                </select>
              </label>
              <Terrain3DUploadButton
                onUploaded={(itemId) => {
                  void refreshHostedSources();
                  selectHosted(itemId);
                }}
              />
            </>
          )}
          <label className="flex flex-col gap-1 text-sm">
            {t("terrainPanel.tilesUrlLabel")}
            <input
              aria-label={t("terrainPanel.tilesUrlAria")}
              type="text"
              placeholder="https://…/{z}/{x}/{y}.png"
              value={value.tilesUrl}
              onChange={(e) => patch({ tilesUrl: e.target.value })}
            />
          </label>
          <label className="flex flex-col gap-1 text-sm">
            Exaggeration
            <input
              aria-label={t("terrainPanel.exaggerationAria")}
              type="number"
              step={0.1}
              min={0}
              value={value.exaggeration ?? 1}
              onChange={(e) => patchExaggeration(e.target.value)}
            />
          </label>
        </>
      )}
    </div>
  );
}
