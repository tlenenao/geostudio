// SPDX-License-Identifier: Apache-2.0
// REV-102 : recherche d'adresse (BAN/Nominatim via GET /v1/geocode) pour le
// builder d'apps. Fine enveloppe de map/AddressSearch ; émet `addressSelected`
// {center:[lon,lat]} que l'auteur câble à l'action flyTo du widget carte.
// Absent des exports statique/autoporté (pas de géocodage cœur) : cf.
// core/app/appexport/guard.py, volontairement non listé.
import { lazy, Suspense } from "react";
import { registerWidget } from "../registry";
import { t } from "../../i18n";

// Chargé à la demande : reste hors du chunk initial (seuil de bundle).
const AddressSearch = lazy(() =>
  import("../../map/AddressSearch").then((m) => ({ default: m.AddressSearch })),
);

export function registerAddressSearchWidget(): void {
  registerWidget({
    type: "addressSearch",
    label: t("widgetAddressSearch.paletteLabel"),
    defaultProps: {},
    defaultSize: { w: 4, h: 2 },
    events: ["addressSelected"],
    actions: [],
    configSchema: [],
    PropsPanel: () => <p className="text-xs">{t("widgetAddressSearch.propsHint")}</p>,
    Component: ({ ctx }) =>
      // En édition, aucun appel réseau : simple repère visuel.
      ctx.mode === "edit" ? (
        <p className="text-sm text-[var(--gs-color-text)]">{t("widgetAddressSearch.editHint")}</p>
      ) : (
        <Suspense fallback={null}>
          <AddressSearch
            onSelect={(center) => ctx.bus?.emit(ctx.widgetId ?? "", "addressSelected", { center })}
          />
        </Suspense>
      ),
  });
}
