// SPDX-License-Identifier: Apache-2.0
import { registerWidget } from "../registry";
import { makeGeneratedPropsPanel } from "../wc/generatedPropsPanel";
import { makeLazyWcHost } from "./LazyWcHost";
import type { ExtensionManifest } from "../../api/types";

export function registerExtensionWidget(manifest: ExtensionManifest): void {
  registerWidget({
    type: manifest.type,
    label: manifest.label,
    defaultProps: Object.fromEntries(manifest.props.map((p) => [p.name, p.default])),
    defaultSize: manifest.defaultSize,
    events: manifest.events,
    actions: manifest.actions,
    // Sans ça, toute écriture de prop passant par le configSchema du
    // registre (copilote SP-20, applyClientOp) est silencieusement filtrée
    // pour un widget d'extension.
    configSchema: manifest.props,
    PropsPanel: makeGeneratedPropsPanel(manifest),
    Component: makeLazyWcHost(manifest),
  });
}
