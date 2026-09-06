// SPDX-License-Identifier: Apache-2.0
// Implémentation "zéro backend" d'ItemClient pour le mode Statique (SP-18a).
// Le cœur a déjà réécrit toute DataSource "features" en "static" avant
// l'export (core/app/appexport/freeze.py) — queryDataSource n'a donc besoin
// que de la même branche "static" que createItemClient (itemClient.ts)
// utilise déjà en direct, jamais de réseau.
//
// Toutes les autres méthodes d'ItemClient (catalogue, partage, harvest,
// ingestion, pipelines, alertes, rapports, 3D, MCP…) n'ont aucun sens sans
// backend : chaque méthode rejette explicitement plutôt que d'être omise,
// afin que TypeScript prouve qu'aucune n'a été oubliée (pas de
// `as unknown as ItemClient`, contrairement au sketch illustratif du plan).
import type {
  AppConfig,
  DataRecord,
  DataSource,
  GeoJSONFeatureInput,
  ItemClient,
} from "../api/types";

const UNSUPPORTED = "Non disponible dans un export statique (aucun backend).";

function unsupported<T = never>(): Promise<T> {
  return Promise.reject(new Error(UNSUPPORTED));
}

export function createStaticItemClient(config: AppConfig): ItemClient {
  return {
    // --- Implémentées réellement (Step 3) ---
    async getAppConfig() {
      return config;
    },
    async getPublicAppConfig() {
      return config;
    },
    async queryDataSource(source: DataSource): Promise<DataRecord[]> {
      return (source.query.records as DataRecord[] | undefined) ?? [];
    },
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
    async createFeature(_collectionId: string, _feature: GeoJSONFeatureInput) {
      return unsupported();
    },
    async updateFeature(_collectionId: string, _fid: string, _feature: GeoJSONFeatureInput) {
      return unsupported();
    },
    async deleteFeature(_collectionId: string, _fid: string) {
      return unsupported();
    },
    async exportDataSource(_source: DataSource, _format: string) {
      return unsupported();
    },
    async runAnalyticsSql(_sql: string) {
      return unsupported();
    },

    // --- Reste de l'interface : aucun backend, rejet explicite ---
    async listItems(..._args: unknown[]) {
      return unsupported();
    },
    async getItem(..._args: unknown[]) {
      return unsupported();
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
    async getSharing(..._args: unknown[]) {
      return unsupported();
    },
    async setSharing(..._args: unknown[]) {
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
    async listConfigRevisions(..._args: unknown[]) {
      return unsupported();
    },
    async rollbackConfig(..._args: unknown[]) {
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
    async createPipelineItem(..._args: unknown[]) {
      return unsupported();
    },
    async getPipelineConfig(..._args: unknown[]) {
      return unsupported();
    },
    async savePipelineConfig(..._args: unknown[]) {
      return unsupported();
    },
    async getPipelineOps(..._args: unknown[]) {
      return unsupported();
    },
    async runPipeline(..._args: unknown[]) {
      return unsupported();
    },
    async getPipelineRuns(..._args: unknown[]) {
      return unsupported();
    },
    async previewPipeline(..._args: unknown[]) {
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
    // getAuthToken?() et getCoreUrl?() sont optionnels sur ItemClient et
    // n'ont pas de sens sans backend réel (aucun jeton, aucune base URL de
    // cœur) : omis intentionnellement plutôt qu'implémentés pour rejeter.
  };
}
