### Task 8: Shell types — `ResourceType`, `LayerSource`, `InstanceInfo`, `ItemClient`

**Files:**
- Modify: `shell/src/api/types.ts`

**Interfaces:**
- Produces: `ResourceType` gains `"tileset3d"`; `LayerSource.service` gains `"tileset3d"`, `.kind` gains `"tiles3d"`; `InstanceInfo` gains `tileset3dEnabled: boolean`; `ItemClient` gains `createTileset3DUpload`, `presignTileset3DUploadPart`, `completeTileset3DUpload`, `getTileset3DUploadJob`, `getAuthToken?`. Consumed by Task 9 (`itemClient.ts` implementation), Task 10 (`LayerPicker`), Task 11 (`MapView`), Task 12 (`Tileset3DUploadButton`).

This task is a type-only change with no runtime behavior — `tsc --noEmit` is the verification, no new test file.

- [ ] **Step 1: Verify the baseline compiles**

Run: `cd shell && npm run build`
Expected: PASS (establishes the pre-change baseline before editing).

- [ ] **Step 2: Extend `ResourceType`**

In `shell/src/api/types.ts`, line 2:

```ts
export type ResourceType = "app" | "dashboard" | "map" | "site" | "dataset" | "external" | "bookmark" | "pipeline" | "alert" | "report" | "tileset3d";
```

- [ ] **Step 3: Extend `LayerSource`**

Replace the `LayerSource` type (currently lines 84-93):

```ts
export type LayerSource = {
  id: string;
  title: string;
  service: "martin" | "core" | "external" | "tileset3d";
  kind: "vector" | "feature" | "raster" | "tiles3d";
  tilesUrl?: string;
  sourceLayer?: string;
  url?: string;
  featureCount?: number | null;
};
```

- [ ] **Step 4: Extend `InstanceInfo`**

Line 35:

```ts
export type InstanceInfo = { readOnly: boolean; etlEnabled: boolean; exportEnabled: boolean; tileset3dEnabled: boolean };
```

- [ ] **Step 5: Extend `ItemClient`**

In the `ItemClient` interface, insert before the closing `}` (currently line 216, right after `getExportJob(jobId: string): Promise<ExportJob>;`):

```ts
  createTileset3DUpload(input: { filename: string; title: string }): Promise<{ jobId: string }>;
  presignTileset3DUploadPart(jobId: string, partNumber: number): Promise<{ uploadUrl: string }>;
  completeTileset3DUpload(jobId: string, parts: { partNumber: number; etag: string }[]): Promise<void>;
  getTileset3DUploadJob(jobId: string): Promise<{
    status: "pending" | "finalizing" | "done" | "error";
    errorMessage: string | null;
    itemId: string | null;
  }>;
  // Optional: absent on any ItemClient that doesn't need it (e.g. test mocks
  // cast via `as unknown as ItemClient`). Used by MapView to authenticate
  // Tile3DLayer requests against a hosted tileset's proxy route (design §4).
  getAuthToken?(): string | undefined;
```

- [ ] **Step 6: Verify it still compiles**

Run: `cd shell && npm run build`
Expected: FAIL — `createItemClient`'s returned object (in `itemClient.ts`) doesn't yet implement the four new required `ItemClient` methods (`getAuthToken` is optional, so it alone wouldn't fail the build, but the four upload/job methods are required).

This confirms the type change is wired correctly; Task 9 implements the missing methods.

- [ ] **Step 7: Commit**

```bash
cd shell && git add src/api/types.ts
git commit -m "feat(shell): types for hosted tileset3d items and upload client"
```

---

