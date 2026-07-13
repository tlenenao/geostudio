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
    PropsPanel: makeGeneratedPropsPanel(manifest),
    Component: makeLazyWcHost(manifest),
  });
}
