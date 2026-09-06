// SPDX-License-Identifier: Apache-2.0
import { Button } from "../ui/kit/Button";
import { t } from "../i18n";

export function CameraControls({
  pitch,
  bearing,
  onChange,
}: {
  pitch: number;
  bearing: number;
  onChange: (next: { pitch: number; bearing: number }) => void;
}) {
  // MapLibre's getBearing() returns (-180, 180]; the slider is [0, 360]. Left
  // raw, a bearing of -170 would clamp to 0 on the track while the label still
  // printed "-170°" — the control would misstate the actual orientation. This
  // is display-only: the value handed back on change (and thus saved) stays
  // whatever the slider emits, and the backend has no range constraint.
  const displayBearing = ((bearing % 360) + 360) % 360;
  return (
    <div className="flex flex-col gap-2">
      <p className="mb-1 mt-3 text-xs font-medium text-ink-2">{t("cameraControls.heading")}</p>
      <label className="flex flex-col gap-1 text-sm">
        {t("cameraControls.pitchLabel", { pitch })}
        <input
          aria-label={t("cameraControls.pitchAria")}
          type="range"
          min={0}
          max={60}
          step={1}
          value={pitch}
          onChange={(e) => onChange({ pitch: Number(e.target.value), bearing })}
        />
      </label>
      <label className="flex flex-col gap-1 text-sm">
        {t("cameraControls.bearingLabel", { bearing: displayBearing })}
        <input
          aria-label={t("cameraControls.bearingAria")}
          type="range"
          min={0}
          max={360}
          step={1}
          value={displayBearing}
          onChange={(e) => onChange({ pitch, bearing: Number(e.target.value) })}
        />
      </label>
      <Button
        type="button"
        size="sm"
        variant="outline"
        className="w-fit"
        onClick={() => onChange({ pitch: 0, bearing: 0 })}
      >
        {t("cameraControls.resetButton")}
      </Button>
    </div>
  );
}
