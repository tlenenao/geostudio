// SPDX-License-Identifier: Apache-2.0
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
  isAdmin: boolean;
  isAnalyst: boolean;
};

export type InstanceInfo = { readOnly: boolean };

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
  featureCount?: number | null;
};

export type CollectionFieldType =
  | "string" | "integer" | "number" | "boolean" | "date" | "datetime" | "enum" | "unsupported";

export type CollectionSchemaField = {
  name: string;
  type: CollectionFieldType;
  required: boolean;
  maxLength?: number;
  values?: string[];
};

export type CollectionSchema = {
  collection: string;
  pk: string;
  geometry: { column: string; type: string | null; srid: number } | null;
  fields: CollectionSchemaField[];
};

export type FieldError = { field: string; code: string; message: string };

export type GeoJSONFeatureInput = {
  type: "Feature";
  properties: Record<string, unknown>;
  geometry: unknown | null;
};

export interface ItemClient {
  listItems(params?: ListItemsParams): Promise<ItemPage>;
  getItem(pk: string): Promise<Item>;
  getMe(): Promise<Me>;
  getInstanceInfo(): Promise<InstanceInfo>;
  createConfigItem(input: { kind: CreateKind; title: string; owner: string; templateId?: string }): Promise<Item>;
  updateItem(pk: string, patch: UpdatePatch): Promise<Item>;
  uploadThumbnail(pk: string, file: File): Promise<void>;
  deleteItem(pk: string): Promise<void>;
  listGroups(): Promise<Group[]>;
  getSharing(pk: string): Promise<Sharing>;
  setSharing(pk: string, sharing: Sharing): Promise<void>;
  listLayerSources(params?: { q?: string }): Promise<LayerSource[]>;
  listActiveExtensions(): Promise<ExtensionManifest[]>;
  listAllExtensions(): Promise<AdminExtension[]>;
  setExtensionEnabled(id: string, enabled: boolean): Promise<void>;
  listCollections(): Promise<CollectionAdmin[]>;
  listCandidateTables(): Promise<CandidateTable[]>;
  createCollection(input: CollectionCreateInput): Promise<CollectionAdmin>;
  updateCollection(id: string, patch: CollectionPatchInput): Promise<CollectionAdmin>;
  deleteCollection(id: string): Promise<void>;
  getCollectionSharing(id: string): Promise<Sharing>;
  setCollectionSharing(id: string, sharing: Sharing): Promise<void>;
  createMapItem(input: { title: string; owner: string }): Promise<Item>;
  getMapConfig(pk: string): Promise<MapConfig>;
  saveMapConfig(pk: string, config: MapConfig): Promise<void>;
  getAppConfig(pk: string, mode?: "runtime"): Promise<AppConfig>;
  saveAppConfig(pk: string, config: AppConfig): Promise<void>;
  queryDataSource(source: DataSource): Promise<DataRecord[]>;
  featuresUrl(source: DataSource): string;
  getCollectionSchema(collectionId: string): Promise<CollectionSchema>;
  getCollectionPermission(collectionId: string): Promise<boolean>;
  createFeature(collectionId: string, feature: GeoJSONFeatureInput): Promise<{ id: string | number }>;
  updateFeature(collectionId: string, fid: string, feature: GeoJSONFeatureInput): Promise<void>;
  deleteFeature(collectionId: string, fid: string): Promise<void>;
  presignUpload(filename: string, contentType: string): Promise<{ uploadUrl: string; key: string }>;
  uploadToPresignedUrl(url: string, file: File): Promise<void>;
  inspectUpload(input: { key: string; filename: string }): Promise<{
    layers: { name: string; featureCount: number; geometryType: string }[];
  }>;
  createIngestionJob(input: {
    key: string; filename: string; collectionTitle: string;
    latField?: string; lonField?: string; layerName?: string;
  }): Promise<{ jobId: string }>;
  getIngestionJob(jobId: string): Promise<{
    status: "pending" | "running" | "done" | "error";
    errorMessage: string | null;
    collectionId: string | null;
    itemId: string | null;
  }>;
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
  visibleWhen?: string;
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

export type VariableType = "string" | "number" | "bool" | "date" | "record" | "list";

export type Variable = {
  id: string;
  name: string;
  type?: VariableType;
  initialValue: string | number | boolean | Record<string, unknown> | unknown[] | null;
};

export type DataSource = {
  id: string;
  type: "features" | "static" | "statistics";
  service: string;
  layer: string;
  query: Record<string, unknown>;
};

// Écho documenté de WcWidgetManifest (shell/src/builder/wc/manifest.ts) — même
// forme, dupliquée ici plutôt qu'importée : api/ ne dépend jamais de builder/.
// Si WcWidgetManifest change de forme, répercuter le changement ici aussi.
export type ExtensionManifest = {
  type: string;
  tag: string;
  label: string;
  props: Array<{
    name: string;
    type: "string" | "number" | "boolean" | "dataSource";
    label: string;
    default: unknown;
  }>;
  events?: string[];
  actions?: string[];
  defaultSize: { w: number; h: number };
  permissions?: { collections: string[] | "all" };
  moduleUrl: string;
};

export type AdminExtension = ExtensionManifest & { enabled: boolean };

export type CollectionAdmin = {
  id: string;
  title: string;
  description: string;
  tableName: string;
  isPublic: boolean;
  editable: boolean;
  geometryType: string | null;
  srid: number | null;
  pkColumn: string;
  canWrite: boolean;
  featureCount: number | null;
  owner: string | null;
};

export type CandidateTable =
  | { tableName: string; registrable: true; geometryType: string | null; srid: number | null; columnCount: number }
  | { tableName: string; registrable: false; reason: string };

export type CollectionCreateInput = {
  tableName: string;
  title?: string;
  description?: string;
  isPublic?: boolean;
};

export type CollectionPatchInput = {
  title?: string;
  description?: string;
  isPublic?: boolean;
  editable?: boolean;
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
  layer?: string;
  url?: string;
};

export type ActionMessage = {
  id: string;
  from: string;
  event: string;
  to: string;
  action: string;
  when?: string;
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
