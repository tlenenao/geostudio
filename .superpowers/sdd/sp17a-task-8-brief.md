### Task 8: Shell — types + itemClient (printLayout round-trip, ExportJob)

> **Point critique** : `PUT /configs/by-item/{pk}` remplace le document entier (pas de fusion partielle côté cœur — chaque révision est un snapshot complet, nécessaire au rollback versionné, SP-0). `saveMapConfig`/`saveAppConfig` construisent déjà leur corps de requête en énumérant explicitement chaque champ (jamais un spread `...config`) — omettre `printLayout` dans cette énumération ferait perdre silencieusement toute mise en page déjà enregistrée dès la prochaine sauvegarde d'un layer ou d'un widget, sans aucune erreur visible. Ce risque est réel dans ce dépôt (cf. CLAUDE.md, bugs de champ manquant/asymétrie lecture-écriture trouvés en revue SP-16a/SP-16b) — chaque test ci-dessous vérifie explicitement ce round-trip.

**Files:**
- Modify: `shell/src/api/types.ts`
- Modify: `shell/src/api/itemClient.ts:590-606,760-832`
- Test: `shell/src/api/itemClient.test.ts` (ajouter aux tests existants du fichier)

**Interfaces:**
- Produces: `PrintLayoutConfig` (type TS), `MapConfig.printLayout?: PrintLayoutConfig | null`, `AppConfig.printLayout?: PrintLayoutConfig | null`, `ExportFormat = "png" | "pdf"`, `ExportJobStatus = "pending" | "running" | "done" | "error"`, `ExportJob = { id: string; status: ExportJobStatus; resultUrl: string | null; error: string | null }`. `itemClient.createExport(itemId: string, format: ExportFormat): Promise<{ jobId: string }>`, `itemClient.getExportJob(jobId: string): Promise<ExportJob>`.

- [ ] **Step 1: Écrire les tests qui échouent**

Ajouter à `shell/src/api/itemClient.test.ts` (mirror des tests existants du même fichier pour le style exact des mocks `fetch`/`request` — s'inspirer du test déjà présent pour `saveMapConfig`/`saveAppConfig` s'il y en a un, sinon suivre le style des tests `exportDataSource`) :

```typescript
describe("printLayout round-trip", () => {
  it("getMapConfig reads printLayout from the top level of the config, not nested under map", async () => {
    mockFetchOnce({
      config: {
        map: { basemap: { style: "s" }, view: { center: [0, 0], zoom: 1 }, layers: [] },
        printLayout: { pageSize: "a3", orientation: "landscape", showLegend: true, showScaleBar: true, showNorthArrow: false },
      },
    });
    const config = await client.getMapConfig("pk-1");
    expect(config.printLayout).toEqual({ pageSize: "a3", orientation: "landscape", showLegend: true, showScaleBar: true, showNorthArrow: false });
  });

  it("saveMapConfig sends printLayout back at the top level, sibling of map", async () => {
    const fetchSpy = mockFetchOnce({});
    await client.saveMapConfig("pk-1", {
      basemap: { style: "s" }, view: { center: [0, 0], zoom: 1 }, layers: [],
      printLayout: { pageSize: "a4", orientation: "portrait", showLegend: false, showScaleBar: false, showNorthArrow: false },
    });
    const body = JSON.parse(fetchSpy.mock.calls[0][1].body);
    expect(body.printLayout).toEqual({ pageSize: "a4", orientation: "portrait", showLegend: false, showScaleBar: false, showNorthArrow: false });
    expect(body.map).toBeDefined();
  });

  it("getAppConfig reads printLayout", async () => {
    mockFetchOnce({ config: { kind: "app", theme: {}, dataSources: [], messages: [], layout: { type: "grid", items: [] }, printLayout: { pageSize: "a4", orientation: "portrait", title: "Rapport" } } });
    const config = await client.getAppConfig("pk-2");
    expect(config.printLayout).toEqual({ pageSize: "a4", orientation: "portrait", title: "Rapport" });
  });

  it("saveAppConfig round-trips printLayout without dropping it", async () => {
    const fetchSpy = mockFetchOnce({});
    await client.saveAppConfig("pk-2", {
      kind: "app", theme: {}, dataSources: [], messages: [], layout: { type: "grid", items: [] },
      printLayout: { pageSize: "a3", orientation: "landscape" },
    });
    const body = JSON.parse(fetchSpy.mock.calls[0][1].body);
    expect(body.printLayout).toEqual({ pageSize: "a3", orientation: "landscape" });
  });
});

describe("createExport / getExportJob", () => {
  it("createExport POSTs itemId and format", async () => {
    const fetchSpy = mockFetchOnce({ jobId: "job-1" });
    const result = await client.createExport("pk-1", "pdf");
    expect(result).toEqual({ jobId: "job-1" });
    const [url, init] = fetchSpy.mock.calls[0];
    expect(url).toContain("/export");
    expect(JSON.parse(init.body)).toEqual({ itemId: "pk-1", format: "pdf" });
  });

  it("getExportJob GETs the job status by id", async () => {
    mockFetchOnce({ id: "job-1", status: "done", resultUrl: "https://minio.test/x.pdf", error: null });
    const job = await client.getExportJob("job-1");
    expect(job).toEqual({ id: "job-1", status: "done", resultUrl: "https://minio.test/x.pdf", error: null });
  });
});
```

Adapter `mockFetchOnce`/le nom exact du helper de mock `fetch` à celui déjà utilisé dans le reste de `shell/src/api/itemClient.test.ts` — inspecter le fichier avant d'écrire ces tests pour réutiliser le harnais existant tel quel (nom de la fonction de mock, forme de `client`, base URL).

- [ ] **Step 2: Vérifier que les tests échouent**

Run: `cd shell && npx vitest run src/api/itemClient.test.ts`
Expected: FAIL — `printLayout` absent des types/du round-trip, `createExport`/`getExportJob` n'existent pas.

- [ ] **Step 3: Implémenter les types**

Dans `shell/src/api/types.ts`, ajouter avant `export type MapConfig = ...` (ligne 64) :

```typescript
export type PrintLayoutConfig = {
  pageSize?: "a4" | "a3";
  orientation?: "portrait" | "landscape";
  title?: string | null;
  showLegend?: boolean;
  showScaleBar?: boolean;
  showNorthArrow?: boolean;
  cartouche?: string | null;
};
```

Remplacer :

```typescript
export type MapConfig = { basemap: BaseMap; view: MapViewport; layers: MapLayer[] };
```

par :

```typescript
export type MapConfig = { basemap: BaseMap; view: MapViewport; layers: MapLayer[]; printLayout?: PrintLayoutConfig | null };
```

Dans `AppConfig` (ligne 414), ajouter le champ à la fin :

```typescript
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
```

Ajouter, n'importe où dans le fichier près des autres types de statut (ex. à côté de `PipelineRunStatus`) :

```typescript
export type ExportFormat = "png" | "pdf";
export type ExportJobStatus = "pending" | "running" | "done" | "error";
export type ExportJob = { id: string; status: ExportJobStatus; resultUrl: string | null; error: string | null };
```

- [ ] **Step 4: Implémenter le round-trip dans `itemClient.ts`**

Remplacer `getMapConfig` (lignes 590-602) :

```typescript
    async getMapConfig(pk: string): Promise<MapConfig> {
      // ConfigRead nests the builder config under "config"; the map is config.map,
      // printLayout is a sibling top-level field (core/app/configs/schemas.py::BuilderConfig).
      const data = await request<{
        config?: {
          map?: { basemap: { style: string }; view: { center: [number, number]; zoom: number }; layers: RawMapLayer[] } | null;
          printLayout?: PrintLayoutConfig | null;
        };
      }>("GET", `/configs/by-item/${pk}`);
      const map = data.config?.map;
      if (!map) throw new Error("getMapConfig: config has no map payload");
      return {
        basemap: map.basemap,
        view: map.view,
        layers: (map.layers ?? []).map(toFrontLayer),
        printLayout: data.config?.printLayout ?? null,
      };
    },
```

Remplacer `saveMapConfig` (ligne 604-606) :

```typescript
    async saveMapConfig(pk: string, config: MapConfig): Promise<void> {
      await request<void>("PUT", `/configs/by-item/${pk}`, {
        version: 1, kind: "map",
        map: { basemap: config.basemap, view: config.view, layers: config.layers },
        printLayout: config.printLayout ?? null,
      });
    },
```

Remplacer `getAppConfig` (lignes 760-788), en ajoutant `printLayout` au type inline et au retour :

```typescript
    async getAppConfig(pk: string, mode?: "runtime"): Promise<AppConfig> {
      const qs = mode ? `?mode=${mode}` : "";
      const data = await request<{
        config?: {
          kind?: "app" | "dashboard";
          theme?: Theme;
          dataSources?: DataSource[];
          messages?: ActionMessage[];
          pages?: Page[];
          variables?: Variable[];
          layout?: AppConfig["layout"] | null;
          navigationMode?: "tabs" | "story";
          interactions?: "auto" | "manual";
          printLayout?: PrintLayoutConfig | null;
        };
      }>("GET", `/configs/by-item/${pk}${qs}`);
      const c = data.config;
      if (!c?.layout) throw new Error("getAppConfig: config has no layout");
      return {
        kind: c.kind ?? "app",
        theme: c.theme ?? {},
        dataSources: c.dataSources ?? [],
        messages: c.messages ?? [],
        pages: c.pages,
        variables: c.variables,
        layout: c.layout,
        navigationMode: c.navigationMode,
        interactions: c.interactions,
        printLayout: c.printLayout ?? null,
      };
    },
```

Remplacer `saveAppConfig` (lignes 819-832) :

```typescript
    async saveAppConfig(pk: string, config: AppConfig): Promise<void> {
      await request<void>("PUT", `/configs/by-item/${pk}`, {
        version: 1,
        kind: config.kind,
        theme: config.theme,
        dataSources: config.dataSources,
        messages: config.messages,
        pages: config.pages,
        variables: config.variables,
        layout: config.layout,
        navigationMode: config.navigationMode,
        interactions: config.interactions,
        printLayout: config.printLayout ?? null,
      });
    },
```

Ajouter les deux nouvelles méthodes, à la suite (n'importe où dans l'objet client, par exemple juste après `saveAppConfig`) :

```typescript
    async createExport(itemId: string, format: ExportFormat): Promise<{ jobId: string }> {
      return request<{ jobId: string }>("POST", `/export`, { itemId, format });
    },

    async getExportJob(jobId: string): Promise<ExportJob> {
      return request<ExportJob>("GET", `/export/jobs/${jobId}`);
    },
```

Ajouter les imports de type nécessaires en tête de fichier (`PrintLayoutConfig`, `ExportFormat`, `ExportJob`) à côté des autres imports depuis `"./types"`.

- [ ] **Step 5: Vérifier que les tests passent**

Run: `cd shell && npx vitest run src/api/itemClient.test.ts`
Expected: PASS

- [ ] **Step 6: `npm run build` (vérification de types stricte)**

Run: `cd shell && npm run build`
Expected: succès — `tsc --noEmit` ne remonte aucune erreur de type sur les fichiers modifiés.

- [ ] **Step 7: Commit**

```bash
git add shell/src/api/types.ts shell/src/api/itemClient.ts shell/src/api/itemClient.test.ts
git commit -m "feat(shell): SP-17a — round-trip printLayout + createExport/getExportJob"
```

---

