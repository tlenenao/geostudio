// SPDX-License-Identifier: Apache-2.0
// Implémentation "sidecar loopback" d'ItemClient pour le desktop-etl (Phase
// G, docs/superpowers/plans/2026-09-18-desktop-etl-phase-fg.md, Tâche 4).
// Même discipline que StaticItemClient.ts (SP-18a) : chaque méthode de
// l'interface est listée explicitement — rejet clair pour tout ce qui n'a
// pas de sens sans backend cœur (catalogue, partage, harvest, connecteurs,
// secrets, 3D, MCP…), implémentation réelle seulement pour les méthodes
// pipeline. Pas de Proxy, pas de `as unknown as ItemClient` : TypeScript
// doit prouver qu'aucune méthode n'a été oubliée.
import type {
  ConfigRevisionInfo,
  Item,
  ItemClient,
  PageParams,
  PipelineOpsCatalog,
  PipelinePayload,
  PipelineRun,
} from "../api/types";
import { OWNER_PERMISSIONS } from "../auth/permissions";

const UNSUPPORTED = "Non disponible en mode desktop.";

function unsupported<T = never>(): Promise<T> {
  return Promise.reject(new Error(UNSUPPORTED));
}

export function createDesktopItemClient(connection: {
  baseUrl: string;
  token: string;
}): ItemClient {
  const { baseUrl, token } = connection;
  // Le sidecar n'a pas de GET /pipelines/{id} (contrat verrouillé, roadmap
  // §3.1 — seul un PUT existe) : le payload actif doit donc être gardé ici,
  // côté client desktop, en plus d'être poussé au sidecar à chaque PUT.
  const localPayloads = new Map<string, PipelinePayload>();
  // PipelineBuilderPage (route /pipelines/:pk/edit) appelle aussi
  // useItem(pk) -> client.getItem(pk) pour le garde de permission
  // (hasPermission(itemQuery.data, "write")) — sans ce cache, getItem()
  // rejetait toujours (méthode générique "hors périmètre desktop"),
  // itemQuery passait en isError, et la page affichait "Pipeline
  // introuvable." juste après un Enregistrer réussi. Trouvé en exécutant
  // le golden path réel sur Windows (Tâche 6).
  const localItems = new Map<string, Item>();

  async function sidecarFetch<T>(method: string, path: string, body?: unknown): Promise<T> {
    const res = await fetch(`${baseUrl}${path}`, {
      method,
      headers: {
        Authorization: `Bearer ${token}`,
        ...(body !== undefined ? { "Content-Type": "application/json" } : {}),
      },
      body: body !== undefined ? JSON.stringify(body) : undefined,
    });
    if (!res.ok) throw new Error(`sidecar ${method} ${path} -> ${res.status}`);
    if (res.status === 204) return undefined as T;
    return (await res.json()) as T;
  }

  return {
    async createPipelineItem(input: {
      title: string;
      owner: string;
      pipeline: PipelinePayload;
    }): Promise<Item> {
      const pk = crypto.randomUUID();
      localPayloads.set(pk, input.pipeline);
      await sidecarFetch<void>("PUT", `/pipelines/${pk}`, input.pipeline);
      const item: Item = {
        pk,
        resourceType: "pipeline",
        title: input.title,
        abstract: "",
        owner: input.owner,
        thumbnailUrl: null,
        date: new Date().toISOString(),
        configId: pk,
        isPublished: false,
        license: "",
        language: "fr",
        permissions: OWNER_PERMISSIONS,
      };
      localItems.set(pk, item);
      return item;
    },

    async getPipelineConfig(pk: string): Promise<PipelinePayload> {
      const payload = localPayloads.get(pk);
      if (!payload) throw new Error(`getPipelineConfig: no local pipeline for ${pk}`);
      return payload;
    },

    async savePipelineConfig(pk: string, payload: PipelinePayload): Promise<void> {
      localPayloads.set(pk, payload);
      await sidecarFetch<void>("PUT", `/pipelines/${pk}`, payload);
    },

    async getPipelineOps(): Promise<PipelineOpsCatalog> {
      return sidecarFetch<PipelineOpsCatalog>("GET", "/pipelines/ops");
    },

    async runPipeline(pk: string): Promise<{ runId: string }> {
      return sidecarFetch<{ runId: string }>("POST", `/pipelines/${pk}/run`);
    },

    async getPipelineRuns(pk: string, params?: PageParams): Promise<PipelineRun[]> {
      const query = new URLSearchParams();
      if (params?.limit !== undefined) query.set("limit", String(params.limit));
      if (params?.offset !== undefined) query.set("offset", String(params.offset));
      const qs = query.toString();
      return sidecarFetch<PipelineRun[]>("GET", `/pipelines/${pk}/runs${qs ? `?${qs}` : ""}`);
    },

    async previewPipeline(pk: string, upToNodeId: string): Promise<Record<string, unknown>[]> {
      return sidecarFetch<Record<string, unknown>[]>(
        "POST",
        `/pipelines/${pk}/preview?upTo=${encodeURIComponent(upToNodeId)}`,
      );
    },

    // Exception délibérée à la discipline "rejet explicite" ci-dessous :
    // ConfigHistoryPanel.tsx (rendu inconditionnellement par
    // PipelineBuilderPage dès pk !== null) affiche un bandeau d'erreur
    // visible en permanence sur un rejet ; [] est une réponse vraie (aucune
    // révision n'existe en desktop, design §1 non-but) et rend un panneau
    // "aucune version" au lieu d'un faux état d'erreur, pour zéro coût.
    async listConfigRevisions(_pk: string): Promise<ConfigRevisionInfo[]> {
      return [];
    },

    async rollbackConfig(..._args: unknown[]) {
      return unsupported();
    },

    // --- Reste de l'interface : aucun backend desktop, rejet explicite
    // (copié de StaticItemClient.ts) ---
    async getAppConfig(..._args: unknown[]) {
      return unsupported();
    },
    async getPublicAppConfig(..._args: unknown[]) {
      return unsupported();
    },
    async getAppConfigSchema(..._args: unknown[]) {
      return unsupported();
    },
    async queryDataSource(..._args: unknown[]) {
      return unsupported();
    },
    // Pas de cache dataset côté sidecar (queryDataSource est
    // unsupported() en mode desktop, aucune résolution de DataSource) —
    // no-op plutôt qu'un rejet : signature synchrone (void, pas Promise),
    // même prudence que featuresUrl() ci-dessous vis-à-vis d'un appel
    // synchrone pendant un rendu.
    invalidateDatasetCache(): void {},
    // Must NOT throw: unlike every other method here, this one has a
    // non-Promise signature and can be called synchronously during render
    // (e.g. ExplorerDrawer.tsx builds a MapConfig on every render whenever
    // the Explorer is open) — a throw there unmounts the whole tree with no
    // recovery. "about:blank" is an inert placeholder MapView's
    // maplibregl geojson source can fail to fetch asynchronously (logged,
    // layer skipped) rather than crash synchronously (SP-18a review, I6).
    featuresUrl(): string {
      return "about:blank";
    },
    async createFeature(..._args: unknown[]) {
      return unsupported();
    },
    async updateFeature(..._args: unknown[]) {
      return unsupported();
    },
    async deleteFeature(..._args: unknown[]) {
      return unsupported();
    },
    async exportDataSource(..._args: unknown[]) {
      return unsupported();
    },
    async runAnalyticsSql(..._args: unknown[]) {
      return unsupported();
    },

    // --- Reste de l'interface : aucun backend, rejet explicite ---
    async listItems(..._args: unknown[]) {
      return unsupported();
    },
    async getItemFacets(..._args: unknown[]) {
      return unsupported();
    },
    async getItem(pk: string): Promise<Item> {
      const item = localItems.get(pk);
      if (!item) throw new Error(`getItem: no local pipeline for ${pk}`);
      return item;
    },
    async getItemBySlug(..._args: unknown[]) {
      return unsupported();
    },
    async listPublicItems(..._args: unknown[]) {
      return unsupported();
    },
    async getMe(..._args: unknown[]) {
      return unsupported();
    },
    async getInstanceInfo(..._args: unknown[]) {
      return unsupported();
    },
    async createConfigItem(..._args: unknown[]) {
      return unsupported();
    },
    async updateItem(..._args: unknown[]) {
      return unsupported();
    },
    async uploadThumbnail(..._args: unknown[]) {
      return unsupported();
    },
    async deleteItem(..._args: unknown[]) {
      return unsupported();
    },
    async listGroups(..._args: unknown[]) {
      return unsupported();
    },
    async createGroup(..._args: unknown[]) {
      return unsupported();
    },
    async addGroupMember(..._args: unknown[]) {
      return unsupported();
    },
    async getSharing(..._args: unknown[]) {
      return unsupported();
    },
    async setSharing(..._args: unknown[]) {
      return unsupported();
    },
    async createShareLink(..._args: unknown[]) {
      return unsupported();
    },
    async listShareLinks(..._args: unknown[]) {
      return unsupported();
    },
    async revokeShareLink(..._args: unknown[]) {
      return unsupported();
    },
    async listLayerSources(..._args: unknown[]) {
      return unsupported();
    },
    async sampleCollectionField(..._args: unknown[]) {
      return unsupported();
    },
    async sampleDataSourceField(..._args: unknown[]) {
      return unsupported();
    },
    async uploadMapIcon(..._args: unknown[]) {
      return unsupported();
    },
    async listMapIcons() {
      return unsupported();
    },
    async deleteMapIcon(..._args: unknown[]) {
      return unsupported();
    },
    async fetchMapIconBlob(..._args: unknown[]) {
      return unsupported();
    },
    async listActiveExtensions(..._args: unknown[]) {
      return unsupported();
    },
    async listAllExtensions(..._args: unknown[]) {
      return unsupported();
    },
    async setExtensionEnabled(..._args: unknown[]) {
      return unsupported();
    },
    async getMetadataCatalog(..._args: unknown[]) {
      return unsupported();
    },
    async listCollections(..._args: unknown[]) {
      return unsupported();
    },
    async listCandidateTables(..._args: unknown[]) {
      return unsupported();
    },
    async createCollection(..._args: unknown[]) {
      return unsupported();
    },
    async createEmptyCollection(..._args: unknown[]) {
      return unsupported();
    },
    async updateCollection(..._args: unknown[]) {
      return unsupported();
    },
    async deleteCollection(..._args: unknown[]) {
      return unsupported();
    },
    async listHarvestSources(..._args: unknown[]) {
      return unsupported();
    },
    async createHarvestSource(..._args: unknown[]) {
      return unsupported();
    },
    async updateHarvestSource(..._args: unknown[]) {
      return unsupported();
    },
    async deleteHarvestSource(..._args: unknown[]) {
      return unsupported();
    },
    async runHarvestSource(..._args: unknown[]) {
      return unsupported();
    },
    async launchAdminTool(..._args: unknown[]) {
      return unsupported();
    },
    async getCollectionSharing(..._args: unknown[]) {
      return unsupported();
    },
    async setCollectionSharing(..._args: unknown[]) {
      return unsupported();
    },
    async createMapItem(..._args: unknown[]) {
      return unsupported();
    },
    async getMapConfig(..._args: unknown[]) {
      return unsupported();
    },
    async saveMapConfig(..._args: unknown[]) {
      return unsupported();
    },
    async createDatasetItem(..._args: unknown[]) {
      return unsupported();
    },
    async createBookmarkItem(..._args: unknown[]) {
      return unsupported();
    },
    async getBookmarkConfig(..._args: unknown[]) {
      return unsupported();
    },
    async createAlertRuleItem(..._args: unknown[]) {
      return unsupported();
    },
    async getAlertRuleConfig(..._args: unknown[]) {
      return unsupported();
    },
    async saveAlertRuleConfig(..._args: unknown[]) {
      return unsupported();
    },
    async listAlertRulesForDataset(..._args: unknown[]) {
      return unsupported();
    },
    async getAlertEvaluations(..._args: unknown[]) {
      return unsupported();
    },
    async createReportScheduleItem(..._args: unknown[]) {
      return unsupported();
    },
    async getReportScheduleConfig(..._args: unknown[]) {
      return unsupported();
    },
    async saveReportScheduleConfig(..._args: unknown[]) {
      return unsupported();
    },
    async getReportRuns(..._args: unknown[]) {
      return unsupported();
    },
    async listFeatureLayers(..._args: unknown[]) {
      return unsupported();
    },
    async getDatasetConfig(..._args: unknown[]) {
      return unsupported();
    },
    async saveDatasetConfig(..._args: unknown[]) {
      return unsupported();
    },
    async saveAppConfig(..._args: unknown[]) {
      return unsupported();
    },
    async getCollectionSchema(..._args: unknown[]) {
      return unsupported();
    },
    async presignAttachmentUpload(..._args: unknown[]) {
      return unsupported();
    },
    async confirmAttachmentUpload(..._args: unknown[]) {
      return unsupported();
    },
    async listAttachments(..._args: unknown[]) {
      return unsupported();
    },
    async deleteAttachment(..._args: unknown[]) {
      return unsupported();
    },
    // Même raisonnement que featuresUrl() ci-dessus : signature synchrone,
    // potentiellement appelée pendant un rendu (popup carte, widget
    // Formulaire) — un throw synchrone démonterait tout l'arbre sans
    // recours. "about:blank" est un placeholder inerte, aucune pièce jointe
    // n'a de sens sans backend réel.
    attachmentFileUrl(): string {
      return "about:blank";
    },
    async downloadAttachment(..._args: unknown[]) {
      return unsupported();
    },
    async getCollection(..._args: unknown[]) {
      return unsupported();
    },
    async getCollectionPermission(..._args: unknown[]) {
      return unsupported();
    },
    async presignUpload(..._args: unknown[]) {
      return unsupported();
    },
    async uploadToPresignedUrl(..._args: unknown[]) {
      return unsupported();
    },
    async inspectUpload(..._args: unknown[]) {
      return unsupported();
    },
    async createIngestionJob(..._args: unknown[]) {
      return unsupported();
    },
    async getIngestionJob(..._args: unknown[]) {
      return unsupported();
    },
    async createExport(..._args: unknown[]) {
      return unsupported();
    },
    async getExportJob(..._args: unknown[]) {
      return unsupported();
    },
    async createAppExport(..._args: unknown[]) {
      return unsupported();
    },
    async getAppExportJob(..._args: unknown[]) {
      return unsupported();
    },
    async copilotTurn(..._args: unknown[]) {
      return unsupported();
    },
    async createTileset3DUpload(..._args: unknown[]) {
      return unsupported();
    },
    async presignTileset3DUploadPart(..._args: unknown[]) {
      return unsupported();
    },
    async completeTileset3DUpload(..._args: unknown[]) {
      return unsupported();
    },
    async getTileset3DUploadJob(..._args: unknown[]) {
      return unsupported();
    },
    async listHostedTerrain3DSources(..._args: unknown[]) {
      return unsupported();
    },
    async presignTerrain3DUpload(..._args: unknown[]) {
      return unsupported();
    },
    async createTerrain3DUpload(..._args: unknown[]) {
      return unsupported();
    },
    async getTerrain3DUploadJob(..._args: unknown[]) {
      return unsupported();
    },
    async getPrivilegeCatalog(..._args: unknown[]) {
      return unsupported();
    },
    async listRoles(..._args: unknown[]) {
      return unsupported();
    },
    async createRole(..._args: unknown[]) {
      return unsupported();
    },
    async updateRole(..._args: unknown[]) {
      return unsupported();
    },
    async deleteRole(..._args: unknown[]) {
      return unsupported();
    },
    async listUsers(..._args: unknown[]) {
      return unsupported();
    },
    async updateUserRole(..._args: unknown[]) {
      return unsupported();
    },
    async eraseUser(..._args: unknown[]) {
      return unsupported();
    },
    async requestTenantPurge(..._args: unknown[]) {
      return unsupported();
    },
    async getPurgeStatus(..._args: unknown[]) {
      return unsupported();
    },
    async listNotifications(..._args: unknown[]) {
      return unsupported();
    },
    async getUnreadNotificationCount(..._args: unknown[]) {
      return unsupported();
    },
    async markNotificationRead(..._args: unknown[]) {
      return unsupported();
    },
    async markAllNotificationsRead(..._args: unknown[]) {
      return unsupported();
    },
    async getNotificationPreference(..._args: unknown[]) {
      return unsupported();
    },
    async updateNotificationPreference(..._args: unknown[]) {
      return unsupported();
    },
    async listUsageTasks(..._args: unknown[]) {
      return unsupported();
    },
    async getUsageSummary(..._args: unknown[]) {
      return unsupported();
    },
    async listSecrets(..._args: unknown[]) {
      return unsupported();
    },
    async createSecret(..._args: unknown[]) {
      return unsupported();
    },
    async deleteSecret(..._args: unknown[]) {
      return unsupported();
    },
    async listPipelineWebhookTokens(..._args: unknown[]) {
      return unsupported();
    },
    async createPipelineWebhookToken(..._args: unknown[]) {
      return unsupported();
    },
    async revokePipelineWebhookToken(..._args: unknown[]) {
      return unsupported();
    },
    // getAuthToken?() et getCoreUrl?() sont optionnels sur ItemClient et
    // n'ont pas de sens sans backend réel (aucun jeton, aucune base URL de
    // cœur) : omis intentionnellement plutôt qu'implémentés pour rejeter.
    // getShareLinkToken?() est réservé à l'ItemClient de la page /embed —
    // omis pour la même raison.
  };
}
