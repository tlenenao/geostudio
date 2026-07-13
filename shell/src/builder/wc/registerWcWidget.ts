import { registerWidget } from "../registry";
import { makeGeneratedPropsPanel } from "./generatedPropsPanel";
import { makeWcHost } from "./WcHost";
import type { WcWidgetManifest } from "./manifest";

export function registerWcWidget(manifest: WcWidgetManifest): void {
  registerWidget({
    type: manifest.type,
    label: manifest.label,
    defaultProps: Object.fromEntries(manifest.props.map((p) => [p.name, p.default])),
    defaultSize: manifest.defaultSize,
    events: manifest.events,
    actions: manifest.actions,
    PropsPanel: makeGeneratedPropsPanel(manifest),
    Component: makeWcHost(manifest),
  });
}
