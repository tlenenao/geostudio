export type WcWidgetManifest = {
  type: string;
  tag: string;
  label: string;
  props: Array<{
    name: string;
    type: "string" | "number" | "boolean";
    label: string;
    default: unknown;
  }>;
  events?: readonly string[];
  actions?: readonly string[];
  defaultSize: { w: number; h: number };
};
