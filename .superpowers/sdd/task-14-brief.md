### Task 14: `ItemClient` — révisions et rollback

**Files:**
- Modify: `shell/src/api/types.ts` (interface `ItemClient`),
  `shell/src/api/itemClient.ts`,
  `shell/src/staticExport/StaticItemClient.ts`
- Test: `shell/src/api/itemClient.test.ts`,
  `shell/src/staticExport/StaticItemClient.test.ts`

**Interfaces:**
- Consumes: Task 13.
- Produces, sur `ItemClient` :

```ts
  listConfigRevisions(pk: string): Promise<ConfigRevisionInfo[]>;
  rollbackConfig(pk: string, version: number): Promise<void>;
```

  avec `export type ConfigRevisionInfo = { version: number; createdAt: string };`
  dans `shell/src/api/types.ts`.

> **Clé par `pk` d'item, pas par `configId`** : aucun des cinq éditeurs ne
> connaît son `configId` (vérifié). `CoreItemClient` résout par
> `GET /configs/by-item/{pk}`, déjà la monnaie courante du client (dix
> appels existants), plutôt que d'ajouter deux routes `by-item` au serveur.

- [ ] **Step 1: Write the failing tests**

Ajouter à `shell/src/api/itemClient.test.ts` (en suivant le patron `msw` du
fichier — lire un test voisin qui intercepte `/configs/by-item/…`) :

```ts
test("listConfigRevisions résout la config par item puis lit ses révisions", async () => {
  // GET /configs/by-item/app-1 -> { id: "cfg-1", … }
  // GET /configs/cfg-1/revisions -> [{ version: 1, created_at: "2026-08-01T10:00:00" },
  //                                  { version: 2, created_at: "2026-08-02T11:00:00" }]
  const client = createItemClient({ coreUrl: CORE_URL, getToken: () => "t" });

  expect(await client.listConfigRevisions("app-1")).toEqual([
    { version: 1, createdAt: "2026-08-01T10:00:00" },
    { version: 2, createdAt: "2026-08-02T11:00:00" },
  ]);
});

test("rollbackConfig poste la version demandée sur la config résolue", async () => {
  let posted: { version: number } | null = null;
  // GET /configs/by-item/app-1 -> { id: "cfg-1" }
  // POST /configs/cfg-1/rollback -> capture le corps, renvoie 200 {}
  const client = createItemClient({ coreUrl: CORE_URL, getToken: () => "t" });

  await client.rollbackConfig("app-1", 3);

  expect(posted).toEqual({ version: 3 });
});

test("rollbackConfig propage l'erreur quand le serveur refuse la version", async () => {
  // POST /configs/cfg-1/rollback -> 422
  const client = createItemClient({ coreUrl: CORE_URL, getToken: () => "t" });

  await expect(client.rollbackConfig("app-1", 1)).rejects.toThrow();
});
```

Ajouter à `shell/src/staticExport/StaticItemClient.test.ts` :

```ts
test("les révisions ne sont pas disponibles hors ligne", async () => {
  const client = createStaticItemClient(CONFIG);
  await expect(client.listConfigRevisions("app-1")).rejects.toThrow(/export statique/);
  await expect(client.rollbackConfig("app-1", 1)).rejects.toThrow(/export statique/);
});
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd shell && npx vitest run src/api/itemClient.test.ts src/staticExport/StaticItemClient.test.ts`

Expected: FAIL — `listConfigRevisions` n'existe pas sur `ItemClient`.

- [ ] **Step 3: Extend the interface**

Dans `shell/src/api/types.ts`, ajouter le type et les deux signatures dans
l'interface `ItemClient` (à côté des autres méthodes de config) :

```ts
export type ConfigRevisionInfo = { version: number; createdAt: string };
```

```ts
  // Historique de versions (SP-23, chantier 4.18). Clés par `pk` d'item et
  // non par `configId` : aucun éditeur du shell ne connaît son configId.
  listConfigRevisions(pk: string): Promise<ConfigRevisionInfo[]>;
  rollbackConfig(pk: string, version: number): Promise<void>;
```

- [ ] **Step 4: Implement in `CoreItemClient`**

Dans `shell/src/api/itemClient.ts`, à l'intérieur de `createItemClient`,
ajouter à l'objet retourné :

```ts
    async listConfigRevisions(pk: string): Promise<ConfigRevisionInfo[]> {
      const { id } = await request<{ id: string }>("GET", `/configs/by-item/${pk}`);
      const rows = await request<{ version: number; created_at: string }[]>(
        "GET",
        `/configs/${id}/revisions`,
      );
      return rows.map((r) => ({ version: r.version, createdAt: r.created_at }));
    },
    async rollbackConfig(pk: string, version: number): Promise<void> {
      const { id } = await request<{ id: string }>("GET", `/configs/by-item/${pk}`);
      await request<unknown>("POST", `/configs/${id}/rollback`, { version });
    },
```

Importer `ConfigRevisionInfo` depuis `./types`.

- [ ] **Step 5: Implement in `StaticItemClient`**

Dans `shell/src/staticExport/StaticItemClient.ts`, ajouter aux méthodes non
supportées :

```ts
    async listConfigRevisions(..._args: unknown[]) {
      return unsupported();
    },
    async rollbackConfig(..._args: unknown[]) {
      return unsupported();
    },
```

- [ ] **Step 6: Run the tests and the type check**

Run: `cd shell && npx vitest run src/api/itemClient.test.ts src/staticExport/ && npm run build`

Expected: PASS et build vert. Si `npm run build` échoue sur une autre
implémentation d'`ItemClient` (mocks de test), l'y ajouter aussi.

- [ ] **Step 7: Commit**

```bash
git add shell/src/api/types.ts shell/src/api/itemClient.ts shell/src/api/itemClient.test.ts shell/src/staticExport/StaticItemClient.ts shell/src/staticExport/StaticItemClient.test.ts
git commit -m "feat(shell): expose les révisions de config et le rollback sur ItemClient"
```

---

