// SPDX-License-Identifier: Apache-2.0
import type { ExportedFile, ExportJobHandler } from "./base";
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
  | "terrain3d"
  | "raster";

export type RasterInfo = {
  itemId: string;
  srid: number;
  bounds: [number, number, number, number];
  width: number;
  height: number;
  dtype: string;
  nodata: number | null;
  bands: {
    index: number;
    min: number | null;
    max: number | null;
    mean: number | null;
    std: number | null;
  }[];
};

export type CreateKind = "app" | "dashboard" | "site";

/** Cible d'une vue d'impact (ARC4-F15). */
export type ImpactTarget = { type: "item" | "collection"; id: string };
export type ImpactDependent = {
  type: "item" | "collection";
  id: string;
  title: string;
  resourceType: string;
  /** 1 = dépendant direct, >1 = transitif. */
  depth: number;
  direct: boolean;
};
export type Impact = {
  target: { type: "item" | "collection"; id: string; title: string; resourceType: string };
  dependents: ImpactDependent[];
  /** Dépendants que l'utilisateur ne peut pas lire : comptés, jamais nommés. */
  hiddenCount: number;
};

export type Item = {
  pk: string;
  resourceType: ResourceType;
  title: string;
  abstract: string;
  owner: string;
  thumbnailUrl: string | null;
  date: string;
  // SP-42 F-shell-api-07 : `date` reste `created_at` (rétrocompatibilité) ;
  // `updatedAt` est le champ à lire pour un « Modifié » qui change
  // réellement après une édition (core/app/items/repository.py::_to_read).
  updatedAt?: string;
  configId: string | null;
  isPublished: boolean;
  slug?: string;
  keywords?: string[];
  license: string;
  language: string;
  // ARC-05 : statut de contenu et catégories (optionnels : absents des items
  // construits localement, "none"/[] côté cœur).
  contentStatus?: ContentStatus;
  categories?: string[];
  // D18 : emprise spatiale de l'item (SP-55), consommée par l'auto-cadrage
  // de l'éditeur de carte autonome (MapEditorPage) — cf. `fitBounds`.
  bbox?: [number, number, number, number] | null;
  permissions: ItemPermissions;
};

export type ContentStatus = "none" | "authoritative" | "deprecated";

export type ItemPage = {
  items: Item[];
  total: number;
  page: number;
  pageSize: number;
};

export type LicenseCatalogEntry = {
  id: string;
  label: string;
  dcatUri: string | null;
  spdxId: string;
};
export type FrequencyCatalogEntry = { id: string; label: string };
export type LanguageCatalogEntry = { id: string; label: string };
export type MetadataCatalog = {
  licenses: LicenseCatalogEntry[];
  frequencies: FrequencyCatalogEntry[];
  languages: LanguageCatalogEntry[];
};

export type RoleSummary = {
  id: string;
  name: string;
  slug: string;
};

export type Me = {
  id: string;
  tenantId: string;
  tenantSlug: string;
  username: string;
  email: string | null;
  firstName: string;
  lastName: string;
  role: RoleSummary;
  privileges: string[];
  version: string;
  // GAP-65 (1/3) : GET /me sert ce profil de capacités depuis longtemps
  // (MeResponse, core/app/auth/routes.py) — doublon délibéré de GET
  // /instance (InstanceInfo, même forme exacte), gardé identique par un
  // test dédié côté cœur. getInstanceInfo()/useInstanceInfo() ne sont pas
  // retirés, cette lecture s'ajoute sans migrer leurs consommateurs.
  capabilities: InstanceInfo;
};

export type Role = {
  id: string;
  name: string;
  slug: string;
  isBuiltIn: boolean;
  privileges: string[];
};

export type UserSummary = {
  id: string;
  username: string;
  roleSlug: string;
  email?: string | null;
  firstName?: string;
  lastName?: string;
  createdAt?: string;
  /** Horodatage ISO de l'anonymisation ; absent/null = compte actif. */
  erasedAt?: string | null;
};

export type PurgeReceipt = {
  id: string;
  tenantSlug: string;
  requestedByUserId: string;
  requestedAt: string;
  completedAt?: string | null;
  counts: Record<string, number>;
  status?: "pending" | "running" | "done" | "failed";
  error?: string | null;
};

export type NotificationSummary = {
  id: string;
  kind:
    | "ingestion"
    | "pipeline"
    | "export"
    | "appexport"
    | "report"
    | "alert"
    | "harvest"
    | "tileset3d"
    | "terrain3d"
    | "raster"
    | "data_export"
    | "submission"
    | "webhook_disabled";
  status: "success" | "failure";
  itemId: string | null;
  itemResourceType: ResourceType | null;
  itemTitle: string;
  errorMessage: string | null;
  createdAt: string;
  readAt: string | null;
};

export type NotificationPreferenceValue = "all" | "failuresOnly" | "none";

export type ApiKeySummary = {
  id: string;
  name: string;
  prefix: string;
  createdAt: string;
  expiresAt: string;
  revokedAt: string | null;
  lastUsedAt: string | null;
};
/** Seule réponse qui porte le secret (`token`), affiché une seule fois. */
export type ApiKeyCreated = ApiKeySummary & { token: string };

export type UsageTask = {
  id: number;
  actorId: string | null;
  actorUsername?: string | null;
  action: string;
  objectType: string;
  objectId: string;
  objectTitle?: string | null;
  createdAt: string;
};

export type UsageActorStat = {
  actorId: string | null;
  actorUsername: string | null;
  count: number;
};

export type UsageResourceStat = {
  objectType: string;
  objectId: string;
  count: number;
  objectTitle?: string | null;
};

export type UsageSummary = {
  byActor: UsageActorStat[];
  byResource: UsageResourceStat[];
  totalActions: number;
  windowStart: string;
  windowEnd: string;
};

export type QuotaUsage = {
  itemCount: number;
  collectionCount: number;
  userCount: number;
  storageBytes: number;
  maxItems: number | null;
  maxCollections: number | null;
  maxStorageBytes: number | null;
};

export type PrivilegeCatalogEntry = {
  privilege: string;
  domain: string;
  labelKey: string;
};

export type RoleCreateInput = {
  name: string;
  privileges: string[];
};

export type RolePatchInput = {
  name?: string;
  privileges?: string[];
};

export type InstanceInfo = {
  readOnly: boolean;
  etlEnabled: boolean;
  exportEnabled: boolean;
  appExportEnabled: boolean;
  tileset3dEnabled: boolean;
  terrain3dEnabled: boolean;
  copilotEnabled: boolean;
  adminToolsEnabled: boolean;
  quotasEnabled: boolean;
  rasterEnabled: boolean;
  routingEnabled: boolean;
};

export type ProbeStatus = { ok: boolean; error?: string };
export type InstanceStatus = {
  checkedAt: string;
  minioConsolePublished: boolean;
  postgres: ProbeStatus;
  s3: ProbeStatus;
  cdc: ProbeStatus & { slotActive?: boolean; configured?: boolean };
  jobs: ProbeStatus & {
    queues?: { queue: string; status: string; count: number }[];
    stalled?: number;
  };
};

// t02-013 : `GET /health` (non authentifié) expose la file de jobs ; un worker
// arrêté se lit à `oldestTodoAgeSeconds` qui grandit.
export type JobsBacklog = {
  todo: number;
  oldestTodoAgeSeconds: number | null;
  // REV-317 : ventilation par file (cœur récent) ; absente sur un cœur ancien.
  queues?: Record<string, { todo: number; oldestTodoAgeSeconds: number | null }>;
};

export type AdminToolName = "martin" | "titiler" | "grafana";

export type CopilotMessage = { role: "user" | "assistant"; content: string };
export type CopilotClientOp = { op: string; args: Record<string, unknown> };
export type CopilotTurnResult = { reply: string; clientOps: CopilotClientOp[] };
export type CopilotToolSchema = {
  name: string;
  description: string;
  inputSchema: Record<string, unknown>;
};
export type CopilotSurface =
  | "app_builder"
  | "sql_lab"
  | "visual_query"
  | "visible_when"
  | "computed_column"
  | "action_condition"
  | "binding";

// REV-102 : un résultat de GET /v1/geocode.
export type GeocodeResult = { label: string; lon: number; lat: number };

// ARC-34 : widget « Directions » — POST /v1/routing/route (Valhalla derrière le cœur, 503 si absent).
export type RouteCosting = "auto" | "bicycle" | "pedestrian" | "truck" | "bus" | "motor_scooter";
export type RoutePoint = { lon: number; lat: number };
export type RouteResult = {
  distance_km: number;
  duration_s: number;
  geometry: { type: "LineString"; coordinates: [number, number][] };
  legs: {
    distance_km: number;
    duration_s: number;
    maneuvers: { instruction: string; distance_km: number; duration_s: number }[];
  }[];
};

// ARC-25 : widget « Analyse » — outils d'analyse spatiale (GET /v1/analysis/tools).
export type AnalysisTool = {
  name: string;
  label: string;
  help: string;
  needsOtherCollection: boolean;
  paramsSchema: {
    properties?: Record<
      string,
      {
        type?: string;
        anyOf?: { type?: string }[];
        title?: string;
        description?: string;
        enum?: string[];
        default?: unknown;
      }
    >;
    required?: string[];
  };
};
export type AnalysisRequest = {
  tool: string;
  params: Record<string, unknown>;
  otherCollectionId?: string;
  output: "ephemeral" | "collection";
  title?: string;
  limit?: number;
};
export type AnalysisResult = {
  tool: string;
  output: "ephemeral" | "collection";
  srid: number;
  rowCount?: number;
  collectionId?: string;
  truncated?: boolean;
  featureCollection?: { type: "FeatureCollection"; features: unknown[] };
};

export type ItemScope = "all" | "mine" | "shared" | "public";

export type ItemSort =
  "relevance" | "date_desc" | "date_asc" | "updated_desc" | "title_asc" | "title_desc";

export type ListItemsParams = {
  q?: string;
  type?: ResourceType;
  page?: number;
  pageSize?: number;
  scope?: ItemScope;
  me?: string;
  sort?: ItemSort;
  owner?: string;
  keywords?: string[];
  bbox?: string; // "minLon,minLat,maxLon,maxLat"
  status?: ContentStatus;
};

export type OwnerFacet = { username: string; count: number };
export type KeywordFacet = { keyword: string; count: number };
export type StatusFacet = { status: ContentStatus; count: number };
export type ItemFacets = {
  owners: OwnerFacet[];
  keywords: KeywordFacet[];
  statuses?: StatusFacet[];
};

export type UpdatePatch = {
  title?: string;
  abstract?: string;
  keywords?: string[];
  isPublished?: boolean;
  slug?: string;
  license?: string;
  language?: string;
  contentStatus?: ContentStatus;
  categories?: string[];
  // REV-317 : `updatedAt` lu par l'éditeur ; envoyé en `If-Match` (jamais dans
  // le corps) -> 412 si l'item a changé depuis.
  baseUpdatedAt?: string;
};

// canManage : l'appelant est créateur du groupe ou administrateur des
// utilisateurs (membres, renommage, suppression) — calculé par le cœur (j13-006).
export type Group = { id: string; title: string; createdBy?: string; canManage?: boolean };
// ARC-24 (ADR 0022) : mapping administré valeur de claim IdP -> groupe du cœur.
export type GroupClaimMapping = { id: string; groupId: string; claimValue: string };
export type GroupMember = { userId: string; username: string; email: string | null };
export type DirectoryUser = { id: string; username: string; email: string | null };
export type ShareLinkInfo = {
  id: string;
  expiresAt: string;
  revoked: boolean;
  createdAt?: string;
  createdBy?: string;
};
export type ShareRole = "viewer" | "editor" | "manager";
export type GeoLimitTarget = "role" | "group";
export type GeoLimit = {
  targetType: GeoLimitTarget;
  targetId: string;
  geometry: Record<string, unknown>;
  updatedAt: string;
};
export type Sharing = {
  public: boolean;
  groups: { groupId: string; role: ShareRole; name?: string | null }[];
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
  attachmentField?: string;
};
// ARC-01 : regroupement de points d'une couche `feature` (MapLibre `cluster: true`).
// Défauts côté rendu : radius 50, maxZoom 14, label vrai.
export type ClusterConfig = { radius?: number; maxZoom?: number; label?: boolean };
export type MapLayer =
  | {
      id: string;
      title: string;
      visible: boolean;
      kind: "vector";
      tilesUrl: string;
      sourceLayer: string;
      // REV-304 : champ temporel filtré par le contexte temps global (widget carte).
      timeField?: string;
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
      cluster?: ClusterConfig;
      popup?: PopupConfig;
      symbology?: import("../builder/widgets/mapSymbology").LayerSymbology;
      collectionId?: string;
      pkColumn?: string;
      // REV-304 : champ temporel filtré par le contexte temps global (widget carte).
      timeField?: string;
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
// ARC-09b : état persisté du lecteur temps de l'éditeur de carte.
export type MapTimePlayerConfig = {
  start: string;
  end: string;
  stepDays: number;
  windowDays: number;
  intervalMs: number;
  windowIndex: number;
};
export type PrintLayoutConfig = {
  pageSize?: "a4" | "a3";
  orientation?: "portrait" | "landscape";
  title?: string | null;
  showLegend?: boolean;
  cartouche?: string | null;
  // ARC-16 : éléments de gabarit (logo = data URI, jamais une URL).
  scaleBar?: boolean;
  northArrow?: boolean;
  freeText?: string | null;
  logo?: string | null;
  // ARC-30 : atlas = une page par entité de la source (apps/dashboards).
  atlas?: AtlasConfig | null;
};

export type AtlasConfig = {
  dataSourceId: string;
  titleTemplate?: string | null;
  fields: { label: string; template: string }[];
  maxPages: number;
};

export type MapConfig = {
  basemap: BaseMap;
  view: MapViewport;
  layers: MapLayer[];
  printLayout?: PrintLayoutConfig | null;
  terrain?: MapTerrainConfig | null;
  timePlayer?: MapTimePlayerConfig | null;
  // Version serveur lue au chargement (REV-271) : renvoyée en `If-Match` à
  // l'enregistrement pour que le cœur refuse (412) une écriture périmée.
  // Jamais persistée dans le corps de la config.
  baseVersion?: number;
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
  | "string"
  | "integer"
  | "number"
  | "boolean"
  | "date"
  | "datetime"
  | "enum"
  | "list"
  | "attachment"
  | "unsupported";

// ARC-13 : domaine d'attribut (liste de valeurs admises ou plage bornée incluse).
export type FieldDomain =
  { type: "list"; values: (string | number)[] } | { type: "range"; min?: number; max?: number };

export type CollectionSubtypes = {
  field: string;
  items: {
    value: string | number;
    label: string;
    defaults?: Record<string, unknown>;
    domains?: Record<string, FieldDomain>;
  }[];
};

export type CollectionSchemaField = {
  name: string;
  type: CollectionFieldType;
  required: boolean;
  maxLength?: number;
  values?: string[];
  itemType?: CollectionFieldType;
  label?: string;
  domain?: FieldDomain;
};

export type CollectionSchema = {
  collection: string;
  pk: string;
  geometry: { column: string; type: string | null; srid: number } | null;
  fields: CollectionSchemaField[];
  subtypes?: CollectionSubtypes;
};

// REV-117 : profil exploratoire d'une collection (GET /collections/{id}/profile).
export type CollectionColumnProfile = {
  name: string;
  type: string;
  nonNull: number;
  nulls: number;
  distinct?: number | null;
  min?: number | string | null;
  max?: number | string | null;
  mean?: number | null;
  p25?: number | null;
  median?: number | null;
  p75?: number | null;
  topValues?: { value: string; count: number }[] | null;
  histogram?:
    { bucketIndex: number; bucketStart: number; bucketEnd: number; count: number }[] | null;
};

export type CollectionProfile = {
  rowCount: number;
  sampled: boolean;
  truncatedColumns: boolean;
  columns: CollectionColumnProfile[];
  geometry: {
    column: string;
    bbox: number[] | null;
    types: { type: string; count: number }[];
  } | null;
  asOf?: string | null;
  pending: boolean;
};

export type FeatureSnapshot = {
  properties: Record<string, unknown>;
  geometry: unknown;
};

export type FeatureVersion = {
  id: number;
  fid: string;
  op: "create" | "update" | "delete" | "restore";
  at: string;
  actor: { id: string; username: string } | null;
  before: FeatureSnapshot | null;
  after: FeatureSnapshot | null;
};

export type CollectionRelation = {
  id: string;
  name: string;
  cardinality: "one_to_one" | "one_to_many" | "many_to_many";
  parentCollectionId: string;
  childCollectionId: string;
  onDelete: "restrict" | "cascade";
};

export type RelatedRecords = {
  relation: CollectionRelation;
  direction: "children" | "parents";
  collectionId: string;
  features: { id: string | number; properties: Record<string, unknown> }[];
  numberReturned: number;
  numberMatched: number | null;
};

export type AttachmentSummary = {
  id: string;
  fieldKey: string;
  filename: string;
  contentType: string;
  byteSize: number;
  createdAt: string;
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

/** Fond de carte partagé du tenant (`GET /v1/basemaps`, REV-367 i). */
export type TenantBasemapOut = { id: string; label: string; style: string };

// Pagination générique pour les endpoints déjà paginés côté serveur mais dont
// les fonctions shell n'envoyaient jusqu'ici jamais `limit`/`offset` (SP-50,
// constat non corrigé côté shell) : GET /collections, GET /reports/{id}/runs,
// GET /pipelines/{id}/runs, GET /alerts/{id}/evaluations.
export type PageParams = { limit?: number; offset?: number };

export interface Submission {
  id: string;
  status: "pending" | "approved" | "rejected";
  properties: Record<string, unknown>;
  geometry: unknown;
  attachment: { filename: string; contentType: string; byteSize: number } | null;
  createdAt: string | null;
}

/** Saisie de l'appelant (« mes saisies », ARC-27). */
export interface MyEntry {
  fid: string;
  at: string;
  properties: Record<string, unknown>;
}

export interface XlsFormReportItem {
  code: "not_ported" | "approximated" | "renamed" | "ignored";
  message: string;
  row: number | null;
  name: string | null;
}

export interface XlsFormImportResult {
  collectionId: string;
  itemId: string;
  title: string;
  report: XlsFormReportItem[];
}

export interface SubmissionTokenInfo {
  id: string;
  name: string;
  prefix: string;
  expiresAt: string | null;
  maxSubmissions: number;
  submissionCount: number;
  revokedAt: string | null;
}

export interface ItemClient {
  listItems(params?: ListItemsParams): Promise<ItemPage>;
  getItemFacets(
    params?: Pick<ListItemsParams, "q" | "type" | "scope" | "owner" | "status">,
  ): Promise<ItemFacets>;
  getItem(pk: string): Promise<Item>;
  getItemBySlug(slug: string): Promise<Item>;
  listPublicItems(params?: {
    type?: ResourceType;
    tag?: string;
    page?: number;
    pageSize?: number;
  }): Promise<ItemPage>;
  getMe(): Promise<Me>;
  getPrivilegeCatalog(): Promise<PrivilegeCatalogEntry[]>;
  listRoles(): Promise<Role[]>;
  createRole(input: RoleCreateInput): Promise<Role>;
  updateRole(id: string, patch: RolePatchInput): Promise<Role>;
  deleteRole(id: string): Promise<void>;
  listUsers(params: {
    page: number;
    pageSize: number;
    q?: string;
  }): Promise<{ users: UserSummary[]; total: number }>;
  updateUserRole(id: string, roleId: string): Promise<UserSummary>;
  eraseUser(userId: string): Promise<void>;
  requestTenantPurge(tenantId: string, confirmSlug: string): Promise<{ jobId: string }>;
  getPurgeStatus(purgeId: string): Promise<PurgeReceipt | null>;
  listNotifications(params: {
    page: number;
    pageSize: number;
  }): Promise<{ notifications: NotificationSummary[]; total: number }>;
  getUnreadNotificationCount(): Promise<number>;
  markNotificationRead(id: string): Promise<NotificationSummary>;
  markAllNotificationsRead(): Promise<void>;
  getNotificationPreference(): Promise<NotificationPreferenceValue>;
  updateNotificationPreference(
    value: NotificationPreferenceValue,
  ): Promise<NotificationPreferenceValue>;
  listApiKeys(): Promise<ApiKeySummary[]>;
  createApiKey(params: { name: string; expiresInDays: number }): Promise<ApiKeyCreated>;
  revokeApiKey(id: string): Promise<ApiKeySummary>;
  listUsageTasks(params: {
    page: number;
    pageSize: number;
    actorId?: string;
  }): Promise<{ tasks: UsageTask[]; total: number }>;
  getUsageSummary(params?: {
    since?: string;
    until?: string;
    limit?: number;
  }): Promise<UsageSummary>;
  // REV-102 : recherche d'adresse (BAN via le cœur).
  geocode(q: string, limit?: number): Promise<GeocodeResult[]>;
  // ARC-34 : itinéraire (routage Valhalla via le cœur).
  computeRoute(points: RoutePoint[], costing?: RouteCosting): Promise<RouteResult>;
  // ARC-25 : widget « Analyse ».
  listAnalysisTools(): Promise<AnalysisTool[]>;
  runAnalysis(collectionId: string, body: AnalysisRequest): Promise<AnalysisResult>;
  getInstanceInfo(): Promise<InstanceInfo>;
  getQuotaUsage(): Promise<QuotaUsage>;
  copilotTurn(
    itemId: string | undefined,
    payload: {
      message: string;
      history: CopilotMessage[];
      mcpToken: string;
      currentConfig: Record<string, unknown>;
      clientTools: CopilotToolSchema[];
      surface?: CopilotSurface;
      // j11-012 : exécution d'un outil d'écriture après clic humain.
      confirmWrite?: { name: string; arguments: Record<string, unknown> };
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
  listGroups(q?: string): Promise<Group[]>;
  // GAP-42/65 : POST /groups + POST /groups/{id}/members existaient et
  // étaient testés côté cœur, mais aucune UI/MCP ne les exposait —
  // ShareForm.tsx ne pouvait qu'afficher des groupes déjà créés hors
  // produit. addGroupMember réserve le succès au créateur du groupe
  // (404 côté cœur si non — comportement délibéré, message clair ici
  // plutôt que masqué).
  createGroup(name: string): Promise<Group>;
  addGroupMember(groupId: string, userId: string): Promise<void>;
  // j13-004 : gestion d'un groupe par son créateur (ou un administrateur).
  listGroupMembers(groupId: string): Promise<GroupMember[]>;
  removeGroupMember(groupId: string, userId: string): Promise<void>;
  renameGroup(groupId: string, name: string): Promise<Group>;
  deleteGroup(groupId: string): Promise<void>;
  listGroupClaimMappings(): Promise<GroupClaimMapping[]>;
  createGroupClaimMapping(groupId: string, claimValue: string): Promise<GroupClaimMapping>;
  deleteGroupClaimMapping(mappingId: string): Promise<void>;
  // j13-005 : annuaire restreint (catalog.manage) pour ajouter un membre.
  searchUserDirectory(q: string): Promise<DirectoryUser[]>;
  getSharing(pk: string): Promise<Sharing>;
  setSharing(pk: string, sharing: Sharing): Promise<void>;
  // GAP-12 (chantier 4.23) : lien de partage à échéance, révocable — distinct
  // du partage groupe/rôle plat ci-dessus (présenté à un tiers externe).
  createShareLink(
    itemId: string,
    ttlDays: number,
  ): Promise<{ url: string; expiresAt: string; token: string }>;
  listShareLinks(itemId: string): Promise<ShareLinkInfo[]>;
  revokeShareLink(itemId: string, linkId: string): Promise<void>;
  listLayerSources(params?: { q?: string }): Promise<LayerSource[]>;
  sampleCollectionField(collectionId: string, field: string, limit: number): Promise<number[]>;
  // Un SEUL appel : le cœur reçoit les octets (D7). Pas de presign, donc pas
  // de séquence presign → PUT → POST à orchestrer côté client.
  uploadMapIcon(file: File, title: string, category: string): Promise<MapIconOut>;
  listMapIcons(): Promise<MapIconOut[]>;
  /** Optionnel : absent des clients sans cœur (export statique, desktop). */
  listTenantBasemaps?(): Promise<TenantBasemapOut[]>;
  deleteMapIcon(iconId: string): Promise<void>;
  // Blob, pas URL : la route est gardée par bearer token, qu'une balise
  // <img> ne porterait pas. Le jeton ne sort jamais d'itemClient.ts.
  fetchMapIconBlob(iconId: string): Promise<Blob>;
  listActiveExtensions(): Promise<ExtensionManifest[]>;
  listAllExtensions(): Promise<AdminExtension[]>;
  setExtensionEnabled(id: string, enabled: boolean): Promise<void>;
  createExtension(input: ExtensionCreateInput): Promise<void>;
  deleteExtension(id: string): Promise<void>;
  getMetadataCatalog(): Promise<MetadataCatalog>;
  listCollections(params?: { q?: string } & PageParams): Promise<CollectionAdmin[]>;
  listCandidateTables(): Promise<CandidateTable[]>;
  createCollection(input: CollectionCreateInput): Promise<CollectionAdmin>;
  createEmptyCollection(input: CreateEmptyCollectionInput): Promise<{ id: string }>;
  updateCollection(id: string, patch: CollectionPatchInput): Promise<CollectionAdmin>;
  deleteCollection(id: string): Promise<void>;
  /** ARC4-F15 : dépendants (visibles) d'un item/d'une collection + compte des masqués. */
  getImpact(target: ImpactTarget): Promise<Impact>;
  listHarvestSources(): Promise<HarvestSource[]>;
  createHarvestSource(input: HarvestSourceCreateInput): Promise<HarvestSource>;
  updateHarvestSource(id: string, patch: HarvestSourcePatchInput): Promise<HarvestSource>;
  deleteHarvestSource(id: string): Promise<void>;
  runHarvestSource(id: string): Promise<void>;
  listHarvestSourceRecords(
    id: string,
    params?: { limit?: number; offset?: number },
  ): Promise<HarvestSourceRecordsPage>;
  launchAdminTool(tool: AdminToolName): Promise<{ url: string }>;
  getInstanceStatus(): Promise<InstanceStatus>;
  getJobsBacklog(): Promise<JobsBacklog | null>;
  getCollectionSharing(id: string): Promise<Sharing>;
  setCollectionSharing(id: string, sharing: Sharing): Promise<void>;
  listGeoLimits(collectionId: string): Promise<GeoLimit[]>;
  putGeoLimit(
    collectionId: string,
    targetType: GeoLimitTarget,
    targetId: string,
    geometry: Record<string, unknown>,
  ): Promise<GeoLimit>;
  deleteGeoLimit(collectionId: string, targetType: GeoLimitTarget, targetId: string): Promise<void>;
  createMapItem(input: { title: string; owner: string }): Promise<Item>;
  getMapConfig(pk: string): Promise<MapConfig>;
  saveMapConfig(pk: string, config: MapConfig): Promise<number | undefined>;
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
  savePipelineConfig(pk: string, payload: PipelinePayload): Promise<number | undefined>;
  getPipelineOps(): Promise<PipelineOpsCatalog>;
  getPipelineNextRun(cron: string): Promise<{ nextRun: string }>;
  runPipeline(pk: string, params?: Record<string, unknown>): Promise<{ runId: string }>;
  getPipelineRuns(pk: string, params?: PageParams): Promise<PipelineRun[]>;
  // t03b-009 : absent côté sidecar desktop / export statique (pas d'annulation).
  cancelPipelineRun?(pk: string, runId: string): Promise<PipelineRun>;
  // ARC-K2/F5 : reprise (défaut) ou rejeu complet (fromStart) d'un run échoué.
  retryPipelineRun?(runId: string, opts?: { fromStart?: boolean }): Promise<{ runId: string }>;
  listPipelineWebhookTokens(pk: string): Promise<PipelineWebhookToken[]>;
  createPipelineWebhookToken(pk: string): Promise<{ id: string; token: string; createdAt: string }>;
  revokePipelineWebhookToken(pk: string, tokenId: string): Promise<void>;
  previewPipeline(
    pk: string,
    upToNodeId: string,
    draft?: PipelinePayload,
  ): Promise<Record<string, unknown>[]>;
  createAlertRuleItem(input: {
    title: string;
    owner: string;
    alert: AlertRulePayload;
  }): Promise<Item>;
  getAlertRuleConfig(pk: string): Promise<AlertRulePayload>;
  saveAlertRuleConfig(pk: string, payload: AlertRulePayload): Promise<number | undefined>;
  listAlertRulesForDataset(datasetItemId: string): Promise<AlertRuleSummary[]>;
  getAlertEvaluations(alertItemId: string, params?: PageParams): Promise<AlertEvaluation[]>;
  evaluateAlertRule(itemId: string): Promise<{ evaluationId: string; created: boolean }>;
  createReportScheduleItem(input: {
    title: string;
    owner: string;
    report: ReportSchedulePayload;
  }): Promise<Item>;
  getReportScheduleConfig(pk: string): Promise<ReportSchedulePayload>;
  saveReportScheduleConfig(pk: string, payload: ReportSchedulePayload): Promise<number | undefined>;
  getReportRuns(pk: string, params?: PageParams): Promise<ReportRunStatus[]>;
  listFeatureLayers(params?: { q?: string }): Promise<FeatureLayerSource[]>;
  getDatasetConfig(pk: string): Promise<DatasetConfig>;
  saveDatasetConfig(pk: string, config: DatasetConfig): Promise<number | undefined>;
  getAppConfig(pk: string, mode?: "runtime"): Promise<AppConfig>;
  getPublicAppConfig(pk: string): Promise<AppConfig>;
  // Retourne la nouvelle version serveur (absente si le cœur ne la renvoie pas).
  saveAppConfig(pk: string, config: AppConfig): Promise<number | undefined>;
  // GAP-38 : schéma JSON de BuilderConfig, factorisé côté cœur derrière
  // app_config_json_schema() — même source que la ressource MCP
  // schema://app-config (garanti identique par un test dédié côté cœur).
  getAppConfigSchema(): Promise<Record<string, unknown>>;
  queryDataSource(source: DataSource): Promise<DataRecord[]>;
  // P29.05 : comme queryDataSource, avec le total réel (`numberMatched`) quand
  // le cœur le donne — pour annoncer « N sur M » au lieu d'une troncature muette.
  // Optionnel : les clients sans cœur (export statique, desktop) ne l'ont pas.
  queryDataSourcePage?(
    source: DataSource,
  ): Promise<{ records: DataRecord[]; total: number | null }>;
  // Symétrique de sampleCollectionField, mais pour un hôte qui n'a qu'un
  // DataSource (pas déjà un collectionId résolu) : la couche `feature` du
  // widget carte de l'App Builder (Jenks, GAP-52 4/4). Résout collectionId
  // via resolveDataset() quand `source.datasetId` est fourni, sinon utilise
  // `source.layer` directement (même patron que queryDataSource).
  sampleDataSourceField(
    source: { layer: string; datasetId?: string },
    field: string,
    limit: number,
  ): Promise<number[]>;
  // GAP-65 (2/3) : datasetCache (interne à ItemClient, résolveDataset())
  // n'expirait jamais et n'était rafraîchi que par une écriture passant
  // par ce même ItemClient — TTL de 5 minutes + invalidation manuelle pour
  // un appelant qui saurait qu'un dataset a changé ailleurs.
  invalidateDatasetCache(pk?: string): void;
  featuresUrl(source: DataSource): string;
  exportDataSource(
    source: DataSource,
    format: string,
    signal?: AbortSignal,
    onJob?: ExportJobHandler,
  ): Promise<ExportedFile>;
  // D6 : annule un export asynchrone de données (409 si déjà terminé).
  cancelExportJob(collectionId: string, jobId: string): Promise<{ status: string }>;
  getCollectionSchema(collectionId: string): Promise<CollectionSchema>;
  getCollectionProfile(collectionId: string): Promise<CollectionProfile>;
  presignAttachmentUpload(
    collectionId: string,
    fid: string,
    input: { fieldKey: string; filename: string; contentType: string },
  ): Promise<{ uploadUrl: string; key: string }>;
  confirmAttachmentUpload(
    collectionId: string,
    fid: string,
    input: { key: string; fieldKey: string; filename: string; contentType: string },
  ): Promise<AttachmentSummary>;
  listAttachments(
    collectionId: string,
    fid: string,
    fieldKey?: string,
  ): Promise<AttachmentSummary[]>;
  deleteAttachment(collectionId: string, fid: string, attachmentId: string): Promise<void>;
  attachmentFileUrl(collectionId: string, fid: string, attachmentId: string): string;
  downloadAttachment(
    collectionId: string,
    fid: string,
    attachmentId: string,
  ): Promise<{ blob: Blob; filename: string }>;
  getCollection(collectionId: string): Promise<CollectionAdmin>;
  getCollectionPermission(collectionId: string): Promise<boolean>;
  createFeature(
    collectionId: string,
    feature: GeoJSONFeatureInput,
  ): Promise<{ id: string | number }>;
  /** `opts.ifMatch` (ARC-04) : ETag lu via `getFeature` ; périmé = ApiError 412. */
  updateFeature(
    collectionId: string,
    fid: string,
    feature: GeoJSONFeatureInput,
    opts?: { ifMatch?: string },
  ): Promise<void>;
  deleteFeature(collectionId: string, fid: string, opts?: { ifMatch?: string }): Promise<void>;
  /** Saisies créées par l'appelant (ARC-27), plus récentes d'abord. Optionnel : sans cœur. */
  listMyEntries?(collectionId: string, limit?: number): Promise<MyEntry[]>;
  /** Import XLSForm -> collection + App de collecte mobile (ARC-27). Optionnel : sans cœur. */
  importXlsForm?(file: File): Promise<XlsFormImportResult>;
  /** Soumission publique modérée (ARC-10). Optionnels : absents d'un client sans cœur. */
  listSubmissions?(collectionId: string): Promise<Submission[]>;
  approveSubmission?(collectionId: string, submissionId: string): Promise<void>;
  rejectSubmission?(collectionId: string, submissionId: string, reason: string): Promise<void>;
  listSubmissionTokens?(collectionId: string): Promise<SubmissionTokenInfo[]>;
  /** Le jeton en clair n'est renvoyé qu'ici, une seule fois. */
  createSubmissionToken?(
    collectionId: string,
    input: { name: string; expiresInDays: number; maxSubmissions: number },
  ): Promise<SubmissionTokenInfo & { token: string }>;
  revokeSubmissionToken?(collectionId: string, tokenId: string): Promise<void>;
  /** Historique d'une entité (ARC-15), plus récent d'abord. Optionnel : absent d'un client sans cœur. */
  listFeatureHistory?(collectionId: string, fid: string): Promise<FeatureVersion[]>;
  /** Restaure l'état APRÈS d'une version (ARC-15) : écriture normale, journalisée `restore`. */
  restoreFeatureVersion?(collectionId: string, fid: string, versionId: number): Promise<void>;
  /** Relations touchant une collection (ARC-21). Optionnel : absent d'un client sans cœur. */
  listCollectionRelations?(collectionId: string): Promise<CollectionRelation[]>;
  /** Enregistrements liés à une entité selon une relation (ARC-21), sous les droits du lecteur. */
  listRelatedRecords?(
    collectionId: string,
    fid: string,
    relationId: string,
  ): Promise<RelatedRecords>;
  /** Entité + ETag courant (ARC-04). Optionnel : absent d'un client sans écriture. */
  getFeature?(
    collectionId: string,
    fid: string,
  ): Promise<{
    id: string | number;
    properties: Record<string, unknown>;
    geometry: unknown;
    etag: string | null;
  }>;
  presignUpload(filename: string, contentType: string): Promise<{ uploadUrl: string; key: string }>;
  uploadToPresignedUrl(url: string, file: File): Promise<void>;
  inspectUpload(input: { key: string; filename: string; layerName?: string }): Promise<{
    layers: { name: string; featureCount: number; geometryType: string }[];
    fields?: string[] | null;
  }>;
  createIngestionJob(input: {
    key: string;
    filename: string;
    collectionTitle: string;
    latField?: string;
    lonField?: string;
    layerName?: string;
    wktField?: string;
    geometryMode?: "latlon" | "wkt" | "none";
  }): Promise<{ jobId: string }>;
  getIngestionJob(jobId: string): Promise<{
    status: "pending" | "running" | "done" | "error" | "cancelled" | "cancel_requested";
    errorMessage: string | null;
    collectionId: string | null;
    itemId: string | null;
    itemResourceType?: string | null;
  }>;
  // D6 : pending -> cancelled ; running -> cancel_requested ; 409 si terminé.
  cancelIngestionJob(jobId: string): Promise<{ status: string }>;
  runAnalyticsSql(
    sql: string,
  ): Promise<{ columns: string[]; rows: unknown[][]; truncated: boolean }>;
  // ARC-26/30 : `entityId` = fiche d'une entité, `atlas` = une page par entité.
  createExport(
    itemId: string,
    format: ExportFormat,
    scope?: { entityId?: string; atlas?: boolean },
  ): Promise<{ jobId: string }>;
  getExportJob(jobId: string): Promise<ExportJob>;
  cancelExport(jobId: string): Promise<ExportJob>;
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
  // Optionnel : présent uniquement sur l'ItemClient construit par la page
  // d'embed (/embed/:token, GAP-19) — le jeton de lien de partage voyage sur
  // un en-tête dédié, jamais sur Authorization (cf. getAuthToken ci-dessus,
  // qui reste undefined dans ce cas). Absent sur tout ItemClient normal.
  getShareLinkToken?(): string | undefined;
  // P30.03 : GET d'une URL de tuile/GeoJSON ; `authenticated` n'est posé que
  // pour une URL servie par le cœur. Optionnel (mocks partiels, client desktop).
  fetchUrl?(url: string, opts?: { authenticated?: boolean }): Promise<Response>;
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
  // ARC-33 : rasters COG hébergés (domaine `raster`, tuiles sous can()).
  listHostedRasterSources(q?: string): Promise<{ id: string; title: string }[]>;
  presignRasterUpload(
    filename: string,
    contentType: string,
  ): Promise<{ uploadUrl: string; key: string }>;
  createRasterUpload(input: {
    key: string;
    filename: string;
    title: string;
  }): Promise<{ jobId: string }>;
  getRasterUploadJob(jobId: string): Promise<{
    status: "uploaded" | "converting" | "done" | "error";
    errorMessage: string | null;
    itemId: string | null;
  }>;
  getRasterInfo(itemId: string): Promise<RasterInfo>;
  rasterZonalStats(
    itemId: string,
    body: {
      geojson?: Record<string, unknown>;
      collectionId?: string;
      band?: number;
      stats?: string[];
    },
  ): Promise<{
    count: number;
    results: { id: string | number | null; stats: Record<string, number | null> }[];
  }>;
  // Coffre de secrets connecteur (GAP-43, SP-53) : le cœur ne rend jamais un
  // payload déchiffré — listSecrets()/createSecret() ne portent que
  // {id,name,kind,createdAt,updatedAt}, jamais le SecretPayload lui-même.
  listSecrets(): Promise<SecretSummary[]>;
  createSecret(input: { name: string; payload: SecretPayload }): Promise<SecretSummary>;
  // PUT /secrets/{id} : remplace la valeur en place (nom et kind inchangés) ; le
  // payload entier est renvoyé, le cœur ne relit jamais l'ancien.
  updateSecret(id: string, payload: SecretPayload): Promise<SecretSummary>;
  deleteSecret(id: string): Promise<void>;
}

export type SecretSummary = {
  id: string;
  name: string;
  kind: string;
  createdAt: string;
  updatedAt: string;
};

export type SecretPayload =
  // REV-294 : les 4 kinds REST portent `baseUrl` (le secret n'est envoyé qu'à cette URL).
  | { kind: "api_key"; location: "header" | "query"; key: string; value: string; baseUrl?: string }
  | { kind: "bearer_token"; token: string; baseUrl?: string }
  | { kind: "basic_auth"; username: string; password: string; baseUrl?: string }
  | {
      kind: "oauth2_client_credentials";
      tokenUrl: string;
      clientId: string;
      clientSecret: string;
      baseUrl?: string;
    }
  | { kind: "postgres_dsn"; dsn: string }
  | {
      kind: "smtp";
      host: string;
      port: number;
      username: string;
      password: string;
      useTls: boolean;
      fromAddress: string;
    }
  | { kind: "snowflake_dsn"; dsn: string }
  | { kind: "bigquery_dsn"; dsn: string }
  | { kind: "mssql_dsn"; dsn: string }
  | { kind: "oracle_dsn"; dsn: string }
  | { kind: "databricks_dsn"; dsn: string }
  | {
      kind: "s3_credentials";
      awsAccessKeyId: string;
      awsSecretAccessKey: string;
      endpointUrl?: string;
      bucketUrl: string;
    }
  | { kind: "azure_blob_credentials"; accountName: string; accountKey: string; bucketUrl: string }
  | { kind: "gcs_credentials"; serviceAccountInfo: Record<string, unknown>; bucketUrl: string }
  // Voie R FME : jeton OAuth2 obtenu/renouvelé à l'exécution (client_credentials ou refresh_token).
  | {
      kind: "oauth2_client";
      grantType: "client_credentials" | "refresh_token";
      tokenUrl: string;
      clientId: string;
      clientSecret: string;
      refreshToken?: string;
      scope?: string;
      baseUrl?: string;
    }
  | { kind: "mongodb_uri"; uri: string };

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
  // REV-285(h) : rang stable parmi les widgets du même type (nom accessible).
  ordinal?: number | null;
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

export type DatasetConfig = (
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
    }
) & {
  // Version serveur lue au chargement (REV-271) — jamais persistée.
  baseVersion?: number;
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

export type ExtensionCreateInput = {
  id: string;
  tag: string;
  label: string;
  moduleUrl: string;
  defaultSize: { w: number; h: number };
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
  attachmentFields: { key: string; label: string }[];
  sensitiveFields: string[];
  license: string;
  licenseUri: string;
  producer: string;
  contact: string;
  updateFrequency: string;
  lineage: string;
  language: string;
  version: string;
  temporalStart: string | null;
  temporalEnd: string | null;
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
  attachmentFields?: { key: string; label: string }[];
  sensitiveFields?: string[];
  license?: string;
  licenseUri?: string;
  producer?: string;
  contact?: string;
  updateFrequency?: string;
  lineage?: string;
  language?: string;
  version?: string;
  temporalStart?: string | null;
  temporalEnd?: string | null;
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
  recordCount?: number;
  staleCount?: number;
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
  intervalMinutes?: number | null;
};

export type HarvestSourceRecord = {
  id: string;
  externalId: string;
  itemId: string | null;
  collectionId: string | null;
  state: "ok" | "stale";
  harvestedAt: string | null;
  externalUrl: string | null;
};

export type HarvestSourceRecordsPage = {
  total: number;
  staleCount: number;
  records: HarvestSourceRecord[];
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
  // Total réel côté cœur (numberMatched), null/absent si inconnu.
  total?: number | null;
  layer?: string;
  url?: string;
  datasetId?: string;
  pkColumn?: string;
  collectionId?: string;
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
  // Version serveur lue au chargement (P09.05) : renvoyée en `If-Match` à
  // l'enregistrement pour que le cœur refuse (412) une écriture périmée.
  // Jamais persistée dans le corps de la config.
  baseVersion?: number;
  // Avertissements du cœur sur une config relue devenue invalide (REV-305).
  // Jamais renvoyés à l'enregistrement.
  warnings?: string[];
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

export type PipelineCanvasNote = {
  id: string;
  label: string;
  x: number;
  y: number;
  width: number;
  height: number;
};

export type PipelinePayload = {
  nodes: PipelineNode[];
  edges: PipelineEdge[];
  refreshPolicy?: PipelineRefreshPolicy | null;
  notes?: PipelineCanvasNote[];
  parameters?: PipelineParameter[];
  retry?: PipelineRetryPolicy | null;
  baseVersion?: number; // version serveur lue (REV-271), jamais persistée
};

export interface AlertCondition {
  expr: string;
}

export type AlertChannel =
  | { kind: "webhook"; url: string; signingSecretName?: string }
  | { kind: "email"; to: string; smtpSecretName: string };

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
  baseVersion?: number; // version serveur lue (REV-271), jamais persistée
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
  // P20.01 : livraison de la notification (null = aucune tentative)
  notifyStatus?: "delivered" | "failed" | null;
  notifyError?: string | null;
  createdAt: string;
}

export interface ReportSchedulePayload {
  bookmarkItemId: string;
  refreshPolicy: PipelineRefreshPolicy; // réutilisé tel quel, même forme que la planification pipeline/alerte
  channels: AlertChannel[]; // réutilisé tel quel depuis AlertRule (SP-16b)
  baseVersion?: number; // version serveur lue (REV-271), jamais persistée
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
  // dict[str, X] : `true` = valeurs libres ; {type} / {anyOf} = valeurs typées (REV-325).
  additionalProperties?: boolean | { type?: string; anyOf?: { type?: string }[] };
  description?: string;
};

export type PipelineOpEntry = {
  kind: PipelineNodeKind;
  paramsSchema: {
    properties: Record<string, PipelineOpParamProperty>;
    required?: string[];
    description?: string;
  };
  acceptsSecondaryInput?: boolean;
};

export type PipelineOpsCatalog = Record<string, PipelineOpEntry>;

export type ExportFormat = "png" | "pdf" | "svg";
export type ExportJobStatus =
  "pending" | "running" | "done" | "error" | "cancelled" | "cancel_requested";
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

export type PipelineRunStatus =
  | "queued"
  | "running"
  | "succeeded"
  | "succeeded_with_rejects"
  | "failed"
  | "cancel_requested"
  | "cancelled"
  | "retrying";

// F1/F2 : `writer.collection` détaille son écriture, ses rejets (quarantaine
// `<cible>__rejected`) et un rapport qualité de l'entrée ; les autres ops n'ont que rowCount.
export type PipelineNodeQuality = {
  rowCount: number;
  columns: { name: string; nonNull: number; nulls: number; nullRate: number }[];
};
export type PipelineNodeStat = {
  nodeId: string;
  op: string;
  rowCount: number | null;
  inserted?: number;
  updated?: number;
  deleted?: number;
  unchanged?: number;
  rejected?: number;
  rejectedCollectionId?: string | null;
  rejectsByRule?: Record<string, number>;
  quality?: PipelineNodeQuality;
};

export type PipelineRun = {
  id: string;
  status: PipelineRunStatus;
  startedAt: string | null;
  finishedAt: string | null;
  error: string | null;
  nodeStats: Record<string, PipelineNodeStat>;
  // ARC-K2 (F3/F5) : paramètres du run, tentative en cours, prochaine reprise
  // automatique, run racine repris, points de reprise disponibles (« Reprendre »).
  params?: Record<string, unknown> | null;
  attempt?: number;
  nextRetryAt?: string | null;
  resumeOf?: string | null;
  resumable?: boolean;
};

export type PipelineParameter = {
  name: string;
  type: "string" | "number" | "integer" | "boolean" | "date";
  default?: unknown;
  required?: boolean;
};

export type PipelineRetryPolicy = {
  max: number;
  backoff?: "fixed" | "exponential";
  delaySeconds?: number;
};

// Jeton de déclenchement webhook (GAP-24, SP-53) : jamais le jeton en clair
// hors de la réponse de création (createPipelineWebhookToken) — la liste
// (listPipelineWebhookTokens) ne porte que id/createdAt/lastUsedAt.
export type PipelineWebhookToken = {
  id: string;
  createdAt: string;
  lastUsedAt: string | null;
};
