export type ResourceType = "app" | "dashboard" | "map";

export type CreateKind = "app" | "dashboard";

export type Item = {
  pk: string;
  resourceType: ResourceType;
  title: string;
  abstract: string;
  owner: string;
  thumbnailUrl: string | null;
  date: string;
  configId: string | null;
  isPublished: boolean;
};

export type ItemPage = {
  items: Item[];
  total: number;
  page: number;
  pageSize: number;
};

export type Me = {
  username: string;
  firstName: string;
  lastName: string;
};

export type ItemScope = "all" | "mine" | "shared" | "public";

export type ListItemsParams = {
  q?: string;
  type?: ResourceType;
  page?: number;
  pageSize?: number;
  scope?: ItemScope;
  me?: string;
};

export type UpdatePatch = { title?: string; abstract?: string; keywords?: string[]; isPublished?: boolean };

export type Group = { id: string; title: string };
export type ShareRole = "viewer" | "editor";
export type Sharing = {
  public: boolean;
  groups: { groupId: string; role: ShareRole }[];
};

export type MapViewport = { center: [number, number]; zoom: number };
export type BaseMap = { style: string };
export type MapLayer =
  | { id: string; title: string; visible: boolean; kind: "vector"; tilesUrl: string; sourceLayer: string; paint?: Record<string, unknown> }
  | { id: string; title: string; visible: boolean; kind: "raster"; tilesUrl: string; opacity?: number }
  | { id: string; title: string; visible: boolean; kind: "feature"; url: string; paint?: Record<string, unknown> }
  | { id: string; title: string; visible: boolean; kind: "deck"; deckType: "heatmap" | "hexbin" | "column"; dataUrl: string; props?: Record<string, unknown> };
export type MapConfig = { basemap: BaseMap; view: MapViewport; layers: MapLayer[] };

export type LayerSource = {
  id: string;
  title: string;
  service: "martin" | "core";
  kind: "vector" | "feature";
  tilesUrl?: string;
  sourceLayer?: string;
  url?: string;
};

export interface ItemClient {
  listItems(params?: ListItemsParams): Promise<ItemPage>;
  getItem(pk: string): Promise<Item>;
  getMe(): Promise<Me>;
  createConfigItem(input: { kind: CreateKind; title: string; owner: string; templateId?: string }): Promise<Item>;
  updateItem(pk: string, patch: UpdatePatch): Promise<Item>;
  uploadThumbnail(pk: string, file: File): Promise<void>;
  deleteItem(pk: string): Promise<void>;
  listGroups(): Promise<Group[]>;
  getSharing(pk: string): Promise<Sharing>;
  setSharing(pk: string, sharing: Sharing): Promise<void>;
  listLayerSources(): Promise<LayerSource[]>;
  createMapItem(input: { title: string; owner: string }): Promise<Item>;
  getMapConfig(pk: string): Promise<MapConfig>;
  saveMapConfig(pk: string, config: MapConfig): Promise<void>;
  getAppConfig(pk: string): Promise<AppConfig>;
  saveAppConfig(pk: string, config: AppConfig): Promise<void>;
  queryDataSource(source: DataSource): Promise<DataRecord[]>;
  featuresUrl(source: DataSource): string;
}

export type RenderMode = "edit" | "preview" | "runtime";

export type WidgetItem = {
  id: string;
  widget: string;
  x: number;
  y: number;
  w: number;
  h: number;
  props: Record<string, unknown>;
  layouts?: Partial<Record<"sm" | "md" | "lg", { x: number; y: number; w: number; h: number }>>;
};

export type AppLayout = {
  type: "grid";
  breakpoints: Record<string, unknown>;
  items: WidgetItem[];
};

export type Page = {
  id: string;
  name: string;
  layout: AppLayout;
};

export type Variable = {
  id: string;
  name: string;
  initialValue: string;
};

export type DataSource = {
  id: string;
  type: "features" | "static" | "statistics";
  service: string;
  layer: string;
  query: Record<string, unknown>;
};

export type DataRecord = {
  id: string | number;
  properties: Record<string, unknown>;
  geometry?: unknown;
};

export type DataSourceState = {
  loading: boolean;
  error: boolean;
  records: DataRecord[];
  url?: string;
};

export type ActionMessage = {
  id: string;
  from: string;
  event: string;
  to: string;
  action: string;
};

export type ThemeColors = {
  primary?: string;
  background?: string;
  surface?: string;
  text?: string;
  muted?: string;
  border?: string;
};

export type Theme = {
  colors?: ThemeColors;
  font?: string;
  radius?: string;
  space?: string;
};

export type AppConfig = {
  kind: "app" | "dashboard";
  theme: Theme;
  dataSources: DataSource[];
  messages: ActionMessage[];
  layout: AppLayout;
  pages?: Page[];
  variables?: Variable[];
};
