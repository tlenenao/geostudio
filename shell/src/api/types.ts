// SPDX-License-Identifier: Apache-2.0
import type { ItemPermissions } from "../auth/permissions";

export type ResourceType =
  | "app"
  | "dashboard"
  | "map"
  | "site"
  | "dataset"
  | "external"
  | "bookmark"
  | "pipeline"
  | "alert"
  | "report"
  | "tileset3d"
  | "terrain3d";

export type CreateKind = "app" | "dashboard" | "site";

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
  slug?: string;
  keywords?: string[];
  permissions: ItemPermissions;
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
  hasAnyEditorRole: boolean;
};

export type InstanceInfo = {
  readOnly: boolean;
  etlEnabled: boolean;
  exportEnabled: boolean;
  appExportEnabled: boolean;
  tileset3dEnabled: boolean;
  terrain3dEnabled: boolean;
  copilotEnabled: boolean;
};

export type CopilotMessage = { role: "user" | "assistant"; content: string };
export type CopilotClientOp = { op: string; args: Record<string, unknown> };
export type CopilotTurnResult = { reply: string; clientOps: CopilotClientOp[] };
export type CopilotToolSchema = {
  name: string;
  description: string;
  inputSchema: Record<string, unknown>;
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

export type UpdatePatch = {
  title?: string;
  abstract?: string;
  keywords?: string[];
  isPublished?: boolean;
  slug?: string;
};

export type Group = { id: string; title: string };
export type ShareRole = "viewer" | "editor";
export type Sharing = {
  public: boolean;
  groups: { groupId: string; role: ShareRole }[];
};

export type MapViewport = {
  center: [number, number];
  zoom: number;
  pitch?: number;
  bearing?: number;
};
export type BaseMap = { style: string };
export type PopupField = { name: string; label?: string };
// Le popup d'une couche, déclaratif (règle 2 de CLAUDE.md). `template` non
// vide l'emporte sur titleField/fields. L'absence de `popup` sur la couche EST
// l'état désactivé : il n'y a pas de drapeau `enabled`.
export type PopupConfig = {
  titleField?: string;
  fields?: PopupField[];
  template?: string;
};
export type MapLayer =
  | {
      id: string;
      title: string;
      visible: boolean;
      kind: "vector";
      tilesUrl: string;
      sourceLayer: string;
      paint?: Record<string, unknown>;
      collectionId?: string;
      geometryKind?: "point" | "line" | "polygon";
      pkColumn?: string;
      popup?: PopupConfig;
      symbology?: import("../builder/widgets/mapSymbology").LayerSymbology;
    }
  | {
      id: string;
      title: string;
      visible: boolean;
      kind: "raster";
      tilesUrl: string;
      opacity?: number;
    }
  | {
      id: string;
      title: string;
      visible: boolean;
      kind: "feature";
      url: string;
      paint?: Record<string, unknown>;
      renderAs?: "fill" | "circle" | "line";
      popup?: PopupConfig;
      symbology?: import("../builder/widgets/mapSymbology").LayerSymbology;
    }
  | {
      id: string;
      title: string;
      visible: boolean;
      kind: "deck";
      deckType: "heatmap" | "hexbin" | "column";
      dataUrl: string;
      props?: Record<string, unknown>;
    }
  | { id: string; title: string; visible: boolean; kind: "tiles3d"; url: string };
export type MapTerrainConfig = { tilesUrl: string; encoding: "terrarium"; exaggeration?: number };
export type PrintLayoutConfig = {
  pageSize?: "a4" | "a3";
  orientation?: "portrait" | "landscape";
  title?: string | null;
  showLegend?: boolean;
  showScaleBar?: boolean;
  showNorthArrow?: boolean;
  cartouche?: string | null;
};

export type MapConfig = {
  basemap: BaseMap;
  view: MapViewport;
  layers: MapLayer[];
  printLayout?: PrintLayoutConfig | null;
  terrain?: MapTerrainConfig | null;
};

export type LayerSource = {
  id: string;
  title: string;
  service: "core" | "external" | "tileset3d";
  kind: "vector" | "feature" | "raster" | "tiles3d";
  tilesUrl?: string;
  sourceLayer?: string;
  url?: string;
  featureCount?: number | null;
  collectionId?: string;
  geometryKind?: "point" | "line" | "polygon";
  pkColumn?: string;
};

export type CollectionFieldType =
  "string" | "integer" | "number" | "boolean" | "date" | "datetime" | "enum" | "unsupported";

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

export type EmptyCollectionColumn = { name: string; sqlType: string };

export type CreateEmptyCollectionInput = {
  title: string;
  columns: EmptyCollectionColumn[];
  geometryType: string | null;
  srid: number | null;
};

export type FieldError = { field: string; code: string; message: string };

export type GeoJSONFeatureInput = {
  type: "Feature";
  properties: Record<string, unknown>;
  geometry: unknown | null;
};

export type ConfigRevisionInfo = { version: number; createdAt: string };

export type MapIconOut = {
  id: string;
  title: string;
  category: string;
  contentType: string;
  createdAt: string;
};

export interface ItemClient {
  listItems(params?: ListItemsParams): Promise<ItemPage>;
  getItem(pk: string): Promise<Item>;
  getItemBySlug(slug: string): Promise<Item>;
  listPublicItems(params?: {
    type?: ResourceType;
    tag?: string;
    page?: number;
    pageSize?: number;
  }): Promise<ItemPage>;
  getMe(): Promise<Me>;
  getInstanceInfo(): Promise<InstanceInfo>;
  copilotTurn(
    itemId: string,
    payload: {
      message: string;
      history: CopilotMessage[];
      mcpToken: string;
      currentConfig: AppConfig;
      clientTools: CopilotToolSchema[];
    },
  ): Promise<CopilotTurnResult>;
  createConfigItem(input: {
    kind: CreateKind;
    title: string;
    owner: string;
    templateId?: string;
    slug?: string;
  }): Promise<Item>;
  updateItem(pk: string, patch: UpdatePatch): Promise<Item>;
  uploadThumbnail(pk: string, file: File): Promise<void>;
  deleteItem(pk: string): Promise<void>;
  listGroups(): Promise<Group[]>;
  getSharing(pk: string): Promise<Sharing>;
  setSharing(pk: string, sharing: Sharing): Promise<void>;
  listLayerSources(params?: { q?: string }): Promise<LayerSource[]>;
  sampleCollectionField(collectionId: string, field: string, limit: number): Promise<number[]>;
  // Un SEUL appel : le cœur reçoit les octets (D7). Pas de presign, donc pas
  // de séquence presign → PUT → POST à orchestrer côté client.
  uploadMapIcon(file: File, title: string, category: string): Promise<MapIconOut>;
  listMapIcons(): Promise<MapIconOut[]>;
  deleteMapIcon(iconId: string): Promise<void>;
  // Blob, pas URL : la route est gardée par bearer token, qu'une balise
  // <img> ne porterait pas. Le jeton ne sort jamais d'itemClient.ts.
  fetchMapIconBlob(iconId: string): Promise<Blob>;
  listActiveExtensions(): Promise<ExtensionManifest[]>;
  listAllExtensions(): Promise<AdminExtension[]>;
  setExtensionEnabled(id: string, enabled: boolean): Promise<void>;
  listCollections(): Promise<CollectionAdmin[]>;
  listCandidateTables(): Promise<CandidateTable[]>;
  createCollection(input: CollectionCreateInput): Promise<CollectionAdmin>;
  createEmptyCollection(input: CreateEmptyCollectionInput): Promise<{ id: string }>;
  updateCollection(id: string, patch: CollectionPatchInput): Promise<CollectionAdmin>;
  deleteCollection(id: string): Promise<void>;
  listHarvestSources(): Promise<HarvestSource[]>;
  createHarvestSource(input: HarvestSourceCreateInput): Promise<HarvestSource>;
  updateHarvestSource(id: string, patch: HarvestSourcePatchInput): Promise<HarvestSource>;
  deleteHarvestSource(id: string): Promise<void>;
  runHarvestSource(id: string): Promise<void>;
  getCollectionSharing(id: string): Promise<Sharing>;
  setCollectionSharing(id: string, sharing: Sharing): Promise<void>;
  createMapItem(input: { title: string; owner: string }): Promise<Item>;
  getMapConfig(pk: string): Promise<MapConfig>;
  saveMapConfig(pk: string, config: MapConfig): Promise<void>;
  // Historique de versions (SP-23, chantier 4.18). Clés par `pk` d'item et
  // non par `configId` : aucun éditeur du shell ne connaît son configId.
  listConfigRevisions(pk: string): Promise<ConfigRevisionInfo[]>;
  rollbackConfig(pk: string, version: number): Promise<void>;
  createDatasetItem(input: CreateDatasetInput): Promise<Item>;
  createBookmarkItem(input: CreateBookmarkInput): Promise<Item>;
  getBookmarkConfig(pk: string): Promise<BookmarkPayload>;
  createPipelineItem(input: {
    title: string;
    owner: string;
    pipeline: PipelinePayload;
  }): Promise<Item>;
  getPipelineConfig(pk: string): Promise<PipelinePayload>;
  savePipelineConfig(pk: string, payload: PipelinePayload): Promise<void>;
  getPipelineOps(): Promise<PipelineOpsCatalog>;
  runPipeline(pk: string): Promise<{ runId: string }>;
  getPipelineRuns(pk: string): Promise<PipelineRun[]>;
  previewPipeline(pk: string, upToNodeId: string): Promise<Record<string, unknown>[]>;
  createAlertRuleItem(input: {
    title: string;
    owner: string;
    alert: AlertRulePayload;
  }): Promise<Item>;
  getAlertRuleConfig(pk: string): Promise<AlertRulePayload>;
  saveAlertRuleConfig(pk: string, payload: AlertRulePayload): Promise<void>;
  listAlertRulesForDataset(datasetItemId: string): Promise<AlertRuleSummary[]>;
  getAlertEvaluations(alertItemId: string): Promise<AlertEvaluation[]>;
  createReportScheduleItem(input: {
    title: string;
    owner: string;
    report: ReportSchedulePayload;
  }): Promise<Item>;
  getReportScheduleConfig(pk: string): Promise<ReportSchedulePayload>;
  saveReportScheduleConfig(pk: string, payload: ReportSchedulePayload): Promise<void>;
  getReportRuns(pk: string): Promise<ReportRunStatus[]>;
  listFeatureLayers(params?: { q?: string }): Promise<FeatureLayerSource[]>;
  getDatasetConfig(pk: string): Promise<DatasetConfig>;
  saveDatasetConfig(pk: string, config: DatasetConfig): Promise<void>;
  getAppConfig(pk: string, mode?: "runtime"): Promise<AppConfig>;
  getPublicAppConfig(pk: string): Promise<AppConfig>;
  saveAppConfig(pk: string, config: AppConfig): Promise<void>;
  queryDataSource(source: DataSource): Promise<DataRecord[]>;
  featuresUrl(source: DataSource): string;
  exportDataSource(source: DataSource, format: string): Promise<{ blob: Blob; filename: string }>;
  getCollectionSchema(collectionId: string): Promise<CollectionSchema>;
  getCollection(collectionId: string): Promise<CollectionAdmin>;
  getCollectionPermission(collectionId: string): Promise<boolean>;
  createFeature(
    collectionId: string,
    feature: GeoJSONFeatureInput,
  ): Promise<{ id: string | number }>;
  updateFeature(collectionId: string, fid: string, feature: GeoJSONFeatureInput): Promise<void>;
  deleteFeature(collectionId: string, fid: string): Promise<void>;
  presignUpload(filename: string, contentType: string): Promise<{ uploadUrl: string; key: string }>;
  uploadToPresignedUrl(url: string, file: File): Promise<void>;
  inspectUpload(input: { key: string; filename: string }): Promise<{
    layers: { name: string; featureCount: number; geometryType: string }[];
  }>;
  createIngestionJob(input: {
    key: string;
    filename: string;
    collectionTitle: string;
    latField?: string;
    lonField?: string;
    layerName?: string;
  }): Promise<{ jobId: string }>;
  getIngestionJob(jobId: string): Promise<{
    status: "pending" | "running" | "done" | "error";
    errorMessage: string | null;
    collectionId: string | null;
    itemId: string | null;
  }>;
  runAnalyticsSql(
    sql: string,
  ): Promise<{ columns: string[]; rows: unknown[][]; truncated: boolean }>;
  createExport(itemId: string, format: ExportFormat): Promise<{ jobId: string }>;
  getExportJob(jobId: string): Promise<ExportJob>;
  createAppExport(itemId: string, mode: AppExportMode): Promise<{ jobId: string }>;
  getAppExportJob(itemId: string, jobId: string): Promise<AppExportJobStatus>;
  createTileset3DUpload(input: { filename: string; title: string }): Promise<{ jobId: string }>;
  presignTileset3DUploadPart(jobId: string, partNumber: number): Promise<{ uploadUrl: string }>;
  completeTileset3DUpload(
    jobId: string,
    parts: { partNumber: number; etag: string }[],
  ): Promise<void>;
  getTileset3DUploadJob(jobId: string): Promise<{
    status: "pending" | "finalizing" | "done" | "error";
    errorMessage: string | null;
    itemId: string | null;
  }>;
  // Optional: absent on any ItemClient that doesn't need it (e.g. test mocks
  // cast via `as unknown as ItemClient`). Used by MapView to authenticate
  // Tile3DLayer requests against a hosted tileset's proxy route (design §4).
  getAuthToken?(): string | undefined;
  // Exposes the core API's base URL so MapView can verify a tiles3d layer's
  // URL actually belongs to our own authenticated proxy before attaching a
  // bearer token — never trust a bare "/tileset3d/" substring match, since
  // layer URLs are freeform (an author can type any external URL).
  getCoreUrl?(): string;
  listHostedTerrain3DSources(q?: string): Promise<{ id: string; title: string }[]>;
  // Dédiée, jamais presignUpload() : la générique signe dans
  // S3_UPLOADS_BUCKET alors que le worker de conversion lit le DEM brut dans
  // S3_TERRAIN3D_BUCKET (et n'y purgerait jamais l'upload brut).
  presignTerrain3DUpload(
    filename: string,
    contentType: string,
  ): Promise<{ uploadUrl: string; key: string }>;
  createTerrain3DUpload(input: {
    key: string;
    filename: string;
    title: string;
  }): Promise<{ jobId: string }>;
  getTerrain3DUploadJob(jobId: string): Promise<{
    status: "uploaded" | "converting" | "done" | "error";
    errorMessage: string | null;
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
  // Messages déclenchés à l'entrée du chapitre en mode story (SP storytelling).
  onEnter?: ActionMessage[];
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
  layer: string; // résolu automatiquement si datasetId est présent
  datasetId?: string;
  query: Record<string, unknown>;
};

export type DatasetColumnMeta = {
  label?: string;
  description?: string;
  format?: string;
};

export type CrossFilterLink =
  | { targetDatasetId: string; mode: "attribute"; sourceField: string; targetField: string }
  | { targetDatasetId: string; mode: "spatial"; precision: "bbox" | "exact" };

export type DatasetConfig =
  | {
      source: "collection";
      collectionId: string;
      columns: Record<string, DatasetColumnMeta>;
      timeField?: string | null;
      reactsToExtent?: boolean;
      crossFilterLinks?: CrossFilterLink[];
      sourcePipelineId?: string | null;
    }
  | {
      source: "arcgis";
      arcgisItemId: string;
      columns: Record<string, DatasetColumnMeta>;
      timeField?: string | null;
      reactsToExtent?: boolean;
      crossFilterLinks?: CrossFilterLink[];
      sourcePipelineId?: string | null;
    };

export type FeatureLayerSource = { id: string; title: string };

export type CreateDatasetInput =
  | { title: string; owner: string; source: "collection"; collectionId: string }
  | { title: string; owner: string; source: "arcgis"; arcgisItemId: string };

// Écho documenté de AnalyticsContextState (shell/src/builder/AnalyticsContext.tsx)
// — même forme, dupliquée ici plutôt qu'importée : api/ ne dépend jamais de
// builder/. Si AnalyticsContextState change de forme, répercuter le
// changement ici aussi.
export type BookmarkCrossFilterValue = string | string[] | { from: string; to: string };
export type BookmarkCrossFilterEntry = {
  field: string;
  value: BookmarkCrossFilterValue;
  originSourceId: string;
};

export type BookmarkPayload = {
  appId: string;
  pageId: string;
  timeRange: { from: string; to: string } | null;
  extent: [number, number, number, number] | null;
  crossFilter: Record<string, BookmarkCrossFilterEntry | undefined>;
};

export type CreateBookmarkInput = { title: string; owner: string } & BookmarkPayload;

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
  permissions: ItemPermissions;
  featureCount: number | null;
  owner: string | null;
};

export type CandidateTable =
  | {
      tableName: string;
      registrable: true;
      geometryType: string | null;
      srid: number | null;
      columnCount: number;
    }
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

export type HarvestSourceType =
  "stac" | "arcgis" | "wms" | "wfs" | "wmts" | "csw" | "ogc-records" | "ckan";
export type HarvestSourceMode = "reference" | "copy";
export type HarvestSourceStatus = "running" | "ok" | "error" | null;

export type HarvestSource = {
  id: string;
  type: HarvestSourceType;
  url: string;
  mode: HarvestSourceMode;
  enabled: boolean;
  intervalMinutes: number | null;
  lastRunAt: string | null;
  lastStatus: HarvestSourceStatus;
  lastError: string | null;
};

export type HarvestSourceCreateInput = {
  type: HarvestSourceType;
  url: string;
  mode: HarvestSourceMode;
  enabled: boolean;
  intervalMinutes?: number;
};

export type HarvestSourcePatchInput = {
  url?: string;
  mode?: HarvestSourceMode;
  enabled?: boolean;
  intervalMinutes?: number;
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
  datasetId?: string;
  pkColumn?: string;
  resolvedSource?: DataSource;
  hasGeometry?: boolean;
};

export type ActionMessage = {
  id: string;
  from: string;
  event: string;
  to: string;
  action: string;
  when?: string;
  // Payload statique porté par un message onEnter de page (SP storytelling) :
  // un chapitre configure ici l'emprise cible de son map.flyTo. Ignoré par les
  // messages de wiring classiques, dont le payload vient de l'émetteur runtime.
  payload?: Record<string, unknown>;
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
  navigationMode?: "tabs" | "story";
  interactions?: "auto" | "manual"; // absent = "manual"
  printLayout?: PrintLayoutConfig | null;
};

export type PipelineNodeKind = "reader" | "transform" | "writer";

export type PipelineNode = {
  id: string;
  kind: PipelineNodeKind;
  op: string;
  x: number;
  y: number;
  params: Record<string, unknown>;
  title?: string | null;
};

// Wire-format alias "from" comes straight from the core's PipelineEdge
// (Pydantic Field(alias="from") — "from" is a reserved word in Python but a
// perfectly valid object-literal key in TS/JS, so no remapping is needed on
// either side of the wire (core/app/configs/schemas.py::PipelineEdge).
export type PipelineEdge = {
  id: string;
  from: string;
  to: string;
  when?: string | null;
  role?: "primary" | "secondary" | null;
};

export type PipelineRefreshPolicy = {
  enabled: boolean;
  cron: string;
};

export type PipelinePayload = {
  nodes: PipelineNode[];
  edges: PipelineEdge[];
  refreshPolicy?: PipelineRefreshPolicy | null;
};

export interface AlertCondition {
  expr: string;
}

export type AlertChannel =
  { kind: "webhook"; url: string } | { kind: "email"; to: string; smtpSecretName: string };

export interface AlertRulePayload {
  datasetItemId: string;
  // Untyped query bag, same convention as DataSource.query (line ~222) — every
  // widget/query-shaped field in this codebase is a Record<string, unknown>
  // read/written dynamically, not a named structured interface.
  query: Record<string, unknown>;
  condition: AlertCondition;
  refreshPolicy: PipelineRefreshPolicy; // reused verbatim, same shape as pipeline scheduling
  channels: AlertChannel[];
  messageTemplate: string;
}

export interface AlertRuleSummary {
  itemId: string;
  title: string;
}

export interface AlertEvaluation {
  id: string;
  value: number | null;
  state: "pending" | "ok" | "firing" | "error";
  transitioned: boolean;
  error: string | null;
  createdAt: string;
}

export interface ReportSchedulePayload {
  bookmarkItemId: string;
  refreshPolicy: PipelineRefreshPolicy; // réutilisé tel quel, même forme que la planification pipeline/alerte
  channels: AlertChannel[]; // réutilisé tel quel depuis AlertRule (SP-16b)
}

export interface ReportRunStatus {
  id: string;
  status: "pending" | "running" | "done" | "error" | "unknown";
  resultUrl: string | null;
  error: string | null;
  notifiedAt: string | null;
  createdAt: string;
}

// Minimal typed subset of JSON Schema actually consumed by
// PipelineNodeInspector (builder/pipeline/PipelineNodeInspector.tsx) — not a
// general JSON Schema type, deliberately narrow to what
// core/app/pipelines/ops/schemas.py's model_json_schema() output is used for.
export type PipelineOpParamProperty = {
  type?: "string" | "number" | "integer" | "boolean" | "array" | "object";
  format?: string;
  enum?: string[];
  default?: unknown;
  items?: { type?: string };
  description?: string;
};

export type PipelineOpEntry = {
  kind: PipelineNodeKind;
  paramsSchema: {
    properties: Record<string, PipelineOpParamProperty>;
    required?: string[];
  };
  acceptsSecondaryInput?: boolean;
};

export type PipelineOpsCatalog = Record<string, PipelineOpEntry>;

export type ExportFormat = "png" | "pdf";
export type ExportJobStatus = "pending" | "running" | "done" | "error";
export type ExportJob = {
  id: string;
  status: ExportJobStatus;
  resultUrl: string | null;
  error: string | null;
};

export type AppExportMode = "static" | "connected" | "standalone";
export type AppExportJobStatus = {
  id: string;
  status: string;
  resultUrl: string | null;
  error: string | null;
};

export type PipelineRunStatus = "queued" | "running" | "succeeded" | "failed";

export type PipelineNodeStat = { nodeId: string; op: string; rowCount: number | null };

export type PipelineRun = {
  id: string;
  status: PipelineRunStatus;
  startedAt: string | null;
  finishedAt: string | null;
  error: string | null;
  nodeStats: Record<string, PipelineNodeStat>;
};
