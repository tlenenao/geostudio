// SPDX-License-Identifier: Apache-2.0
import type { ItemClient } from "./types";
import {
  createBase,
  FeatureValidationError,
  SqlQueryError,
  toFrontLayer,
  type RawMapLayer,
} from "./base";
import { createAlertsMethods } from "./domains/alerts";
import { createAppsMethods } from "./domains/apps";
import { createAttachmentsMethods } from "./domains/attachments";
import { createCollectionsAdminMethods } from "./domains/collectionsAdmin";
import { createDatasetsMethods } from "./domains/datasets";
import { createExportsIngestionMethods } from "./domains/exportsIngestion";
import { createExtensionsAdminToolsMethods } from "./domains/extensionsAdminTools";
import { createFeaturesMethods } from "./domains/features";
import { createIdentityMethods } from "./domains/identity";
import { createItemsMethods } from "./domains/items";
import { createLayersMethods } from "./domains/layers";
import { createNotificationsMethods } from "./domains/notifications";
import { createPipelinesMethods } from "./domains/pipelines";
import { createReportsMethods } from "./domains/reports";
import { createTiles3dMethods } from "./domains/tiles3d";

export { FeatureValidationError, SqlQueryError, toFrontLayer, type RawMapLayer };

export function createItemClient(opts: {
  coreUrl: string;
  getToken: () => string | undefined;
}): ItemClient {
  const base = createBase(opts);

  return {
    ...createIdentityMethods(base),
    ...createNotificationsMethods(base),
    ...createItemsMethods(base),
    ...createCollectionsAdminMethods(base),
    ...createExtensionsAdminToolsMethods(base),
    ...createLayersMethods(base),
    ...createDatasetsMethods(base),
    ...createPipelinesMethods(base),
    ...createAlertsMethods(base),
    ...createReportsMethods(base),
    ...createAppsMethods(base),
    ...createAttachmentsMethods(base),
    ...createFeaturesMethods(base),
    ...createExportsIngestionMethods(base),
    ...createTiles3dMethods(base),
    getAuthToken: base.getToken,
    getCoreUrl: () => base.coreUrl,
  };
}
