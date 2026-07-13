export type WcWidgetManifest = {
  type: string;
  tag: string;
  label: string;
  props: Array<{
    name: string;
    type: "string" | "number" | "boolean" | "dataSource";
    label: string;
    default: unknown;
  }>;
  events?: readonly string[];
  actions?: readonly string[];
  defaultSize: { w: number; h: number };
  permissions?: { collections: string[] | "all" };
};
