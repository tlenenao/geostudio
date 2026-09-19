# Pipeline builder — corrections et améliorations UX Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Corriger les 3 bugs réels et livrer les améliorations non-structurelles listées dans `docs/superpowers/specs/2026-09-18-pipeline-builder-ux-improvements-design.md` (§0-§7), sur le pipeline builder no-code (`shell/src/pages/PipelineBuilderPage.tsx` et `shell/src/builder/pipeline/*`).

**Architecture:** Corrections et ajouts ciblés dans les composants existants du pipeline builder (canvas React Flow, palette, inspecteur de paramètres, aperçus carte/tableau, panneau d'exécution, éditeur de planification) — aucun nouveau runtime, aucune nouvelle page. Deux tâches touchent le cœur (`core/app/pipelines/`, `core/app/configs/schemas.py`) pour des changements additifs sans migration Alembic (le payload de pipeline est un blob JSON validé par Pydantic, pas des colonnes SQL).

**Tech Stack:** React 18 + TypeScript + React Flow (`@xyflow/react`) + React Query côté shell ; FastAPI + Pydantic + SQLAlchemy côté cœur ; Vitest/Testing Library côté shell, pytest côté cœur.

## Constats corrigés vs le design du 2026-09-18

Le design initial contenait plusieurs affirmations invalidées par une lecture directe du code (piège n°12 du dépôt) — corrigées ici, pas dans le design (archive figée) :

- **Le catalogue de 34 opérations est DÉJÀ dynamique côté palette** (`PipelinePalette.tsx` via `usePipelineOps()` / `GET /pipelines/ops`). Seule `INSERTABLE_TRANSFORMS` (menu d'insertion sur une arête, `PipelineCanvas.tsx`) reste une liste de 11 op codée en dur — Task 4 ne corrige que celle-ci.
- **L'audit a11y (SP-57a, `shell/e2e/a11y-audit.spec.ts`) couvre déjà `PipelineBuilderPage`** et **le filet anti-clipping 390px/900px (`shell/e2e/triptych-narrow.spec.ts`) couvre déjà l'écran Automatisation (`/pipelines/new`)**. Aucune tâche dédiée "responsive/a11y générique" dans ce plan — seuls les items concrets (recherche clavier, connexion clavier, cf. Tasks 8/9) apportent une vraie navigation clavier là où il n'y en avait aucune.
- **`GET /pipelines/{id}/runs` renvoie déjà `nodeStats` par run** (pas seulement le dernier) — `core/app/pipelines/models.py::PipelineRun.node_stats`, colonne JSON peuplée à chaque run. Task 20 est donc frontend seul (affichage), aucun changement cœur.
- **`croniter` est déjà une dépendance du cœur** (`pyproject.toml`, utilisé dans `core/app/{pipelines,reports,alerts}/repository.py` via `croniter.croniter(cron, base).get_next(datetime)`). Task 22 expose ce calcul déjà existant via une route dédiée, au lieu de le réimplémenter côté client pour un sous-ensemble de cas.
- **"Exécuter jusqu'à ce nœud" (breakpoint persistant) est RETIRÉ de ce plan.** `previewPipeline`/`preview_pipeline()` exécute déjà "jusqu'à un nœud" mais de façon éphémère (jamais persisté comme un run) ; un vrai run tronqué et persisté toucherait `app/pipelines/jobs.py` (le worker), pas seulement la route — hors taille de ce plan, comme les items ⚙️. À respécifier séparément si retenu.
- Les "bookmarks/zones" du design sont bien dans ce plan (Task 10) mais **persistés côté cœur** (pas seulement client) : `PipelinePayload` est un blob JSON, un nouveau champ optionnel ne nécessite aucune migration Alembic.

## Global Constraints

- Toute nouvelle chaîne visible passe par `t()` / `shell/src/i18n/catalog.fr.ts` (jamais de texte français en dur dans un composant) — `npm run lint` le bloque (SP-29a).
- Composants de `shell/src/ui/kit/` réutilisés en priorité sur tout nouveau contrôle (`Banner`, `Badge`, `IconButton`, `Input`) — jamais de HTML brut réinventant un composant déjà présent dans ce kit.
- `aria-expanded`/`aria-controls` obligatoire sur tout nouveau déclencheur de panneau en ligne, via `shell/src/ui/kit/usePanelTrigger.ts` (convention 2026-09-01, déjà utilisée par `PipelineCanvas.tsx`'s `InsertOnEdgeButton`).
- **Ajouter une méthode à l'interface `ItemClient` (`shell/src/api/types.ts`) impose de l'implémenter dans les 3 classes qui la satisfont** : `api/domains/*.ts` (cœur réel), `shell/src/staticExport/StaticItemClient.ts` (stub `unsupported()`), `shell/src/desktop/DesktopItemClient.ts` (`sidecarFetch`). `tsc --noEmit` échoue sinon (`npm run build`).
- Test Vitest pour chaque comportement frontend nouveau ; test pytest pour chaque route/comportement backend nouveau ; suite complète (`cd shell && npm run test` / `cd core && uv run pytest`) verte avant chaque commit de tâche.
- Après toute route/modèle backend touché (Tasks 2, 10, 22) : régénérer OpenAPI + types TS avant de commiter cette tâche —
  ```bash
  cd core && PYTHONPATH=. \
    CORE_SECRETS_MASTER_KEY="AAECAwQFBgcICQoLDA0ODxAREhMUFRYXGBkaGxwdHh8=" \
    uv run python scripts/export_openapi.py openapi.json
  cd ../shell && npm run gen:api-types
  ```
  Diff vide = anomalie à investiguer (pas un signe de succès), sauf si la surface est déjà exposée ailleurs dans le même format.
- Toute chaîne ajoutée à `shell/src/i18n/catalog.fr.ts` s'insère par **ancrage sur une clé existante voisine** (jamais par numéro de ligne : plusieurs tâches de ce plan modifient ce fichier, les numéros de ligne dérivent d'une tâche à l'autre).
- Pas de commentaire narrant CE que le code fait — uniquement le WHY quand non-obvious (convention du dépôt).
- Les 3 items ⚙️ du design (sous-pipelines réutilisables, éditeur CEL dédié, suivi live SSE) et "Exécuter jusqu'à ce nœud" (cf. ci-dessus) ne sont PAS dans ce plan — ne pas les ajouter en cours d'exécution.
- Régénérer le bilan de fonctionnalités seulement si une tâche ajoute une route REST/MCP nouvellement inventoriable (Tasks 2, 22 ajoutent des routes cœur — vérifier `docs/revue/inventaire-fonctionnalites.jsonl`, la CI (`test_feature_inventory.py`) refuse une surface non inventoriée).

---

### Task 1: Bannière d'erreurs de graphe + badge d'erreur par nœud

**Files:**
- Modify: `shell/src/pages/PipelineBuilderPage.tsx`
- Modify: `shell/src/builder/pipeline/PipelineCanvas.tsx`
- Modify: `shell/src/i18n/catalog.fr.ts`
- Test: `shell/src/pages/PipelineBuilderPage.test.tsx`
- Test: `shell/src/builder/pipeline/PipelineCanvas.test.tsx`

**Interfaces:**
- Consumes: `PipelineValidationResult` existant (`validation.ts`) — `{ graphErrors: string[], nodeErrors: Record<string, string[]> }`, déjà calculé dans `PipelineBuilderPage.tsx:99` mais `graphErrors` n'est actuellement rendu nulle part.
- Produces: `PipelineCanvas` gagne une prop optionnelle `nodeErrors?: Record<string, string[]>`.

- [ ] **Step 1: Ajouter les clés i18n**

Dans `shell/src/i18n/catalog.fr.ts`, ancrer sur la ligne existante `"pipelineBuilder.scheduleLabel": "Planification",` (ligne ~464) et ajouter juste après :

```ts
  "pipelineBuilder.saveDisabledReason":
    "Le graphe contient des erreurs à corriger avant l'enregistrement.",
```

Ancrer sur la ligne existante `"pipelineCanvas.insertStepAria": "Insérer une étape sur cette arête",` et ajouter juste après :

```ts
  "pipelineCanvas.nodeErrorAria": "{count} erreur(s) sur ce nœud",
```

- [ ] **Step 2: Étendre `PipelineCanvas` pour accepter et afficher `nodeErrors`**

Dans `shell/src/builder/pipeline/PipelineCanvas.tsx`, modifier `CanvasNodeData` (ligne ~60) :

```ts
type CanvasNodeData = PipelineNode & {
  acceptsSecondaryInput: boolean;
  nodeStat?: PipelineNodeStat;
  isNext: boolean;
  errorCount: number;
};
```

Modifier `PipelineNodeBox` (ligne ~66) pour appliquer un contour rouge et afficher un badge quand `errorCount > 0` :

```tsx
function PipelineNodeBox({ data, selected }: NodeProps) {
  const node = data as unknown as CanvasNodeData;
  return (
    <div
      className={`relative rounded-md border-2 px-3 py-2 text-xs ${KIND_COLOR[node.kind]} ${selected ? "ring-2 ring-accent" : ""} ${node.errorCount > 0 ? "border-danger" : ""}`}
    >
      <Handle type="target" position={Position.Left} id="primary" />
      {node.acceptsSecondaryInput && (
        <Handle
          type="target"
          position={Position.Top}
          id="secondary"
          style={{ borderStyle: "dashed" }}
        />
      )}
      <div className="font-medium">{node.title ?? node.op}</div>
      <div className="text-[10px] text-ink-2">{node.op}</div>
      <Handle type="source" position={Position.Right} />
      {node.errorCount > 0 && (
        <span
          role="status"
          aria-label={t("pipelineCanvas.nodeErrorAria", { count: node.errorCount })}
          className="absolute -left-2 -top-2 flex h-4 w-4 items-center justify-center rounded-full bg-danger text-[10px] text-surface"
        >
          !
        </span>
      )}
      {node.nodeStat && (
        <span
          role="status"
          className="absolute -right-2 -top-2 rounded-full bg-emerald-600 px-1.5 py-0.5 text-[10px] text-white"
        >
          {node.nodeStat.rowCount ?? "?"}
        </span>
      )}
      {node.isNext && !node.nodeStat && (
        <span
          role="status"
          aria-label={t("pipelineCanvas.runningAria")}
          className="absolute -right-2 -top-2 h-3 w-3 animate-spin rounded-full border-2 border-accent border-t-transparent"
        />
      )}
    </div>
  );
}
```

Modifier `toFlowNode` (ligne ~174) pour propager `errorCount` :

```ts
function toFlowNode(
  n: PipelineNode,
  selected: boolean,
  extra: {
    acceptsSecondaryInput: boolean;
    nodeStat?: PipelineNodeStat;
    isNext: boolean;
    errorCount: number;
  },
): Node {
  return {
    id: n.id,
    position: { x: n.x, y: n.y },
    data: { ...n, ...extra } as unknown as Record<string, unknown>,
    type: "pipelineNode",
    selected,
  };
}
```

Modifier `PipelineCanvasInner` (ligne ~198) pour accepter `nodeErrors` et le propager dans l'appel à `toFlowNode` :

```ts
function PipelineCanvasInner({
  nodes,
  edges,
  selectedNodeId,
  onSelectNode,
  onNodesChange,
  onEdgesChange,
  onInsertOnEdge,
  opsCatalog,
  nodeStats,
  runStatus,
  nodeErrors,
}: {
  nodes: PipelineNode[];
  edges: PipelineEdge[];
  selectedNodeId: string | null;
  onSelectNode: (id: string | null) => void;
  onNodesChange: (nodes: PipelineNode[]) => void;
  onEdgesChange: (edges: PipelineEdge[]) => void;
  onInsertOnEdge: (edgeId: string, op: string) => void;
  opsCatalog: PipelineOpsCatalog;
  nodeStats?: Record<string, PipelineNodeStat>;
  runStatus?: "queued" | "running" | "succeeded" | "failed";
  nodeErrors?: Record<string, string[]>;
}) {
```

Et dans le JSX de `<ReactFlow nodes={...}>` :

```tsx
        nodes={nodes.map((n) =>
          toFlowNode(n, n.id === selectedNodeId, {
            acceptsSecondaryInput: opsCatalog[n.op]?.acceptsSecondaryInput ?? false,
            nodeStat: nodeStats?.[n.id],
            isNext: n.id === nextNodeId,
            errorCount: nodeErrors?.[n.id]?.length ?? 0,
          }),
        )}
```

- [ ] **Step 3: Test — badge d'erreur visible sans sélection**

Ajouter dans `shell/src/builder/pipeline/PipelineCanvas.test.tsx` (après le dernier test du fichier) :

```tsx
test("a node with validation errors shows an error badge even when not selected", () => {
  render(
    <PipelineCanvas
      nodes={NODES}
      edges={EDGES}
      selectedNodeId={null}
      onSelectNode={vi.fn()}
      onNodesChange={vi.fn()}
      onEdgesChange={vi.fn()}
      onInsertOnEdge={vi.fn()}
      opsCatalog={{}}
      nodeErrors={{ r1: ["collectionId est requis."] }}
    />,
  );
  expect(screen.getByRole("status", { name: "1 erreur(s) sur ce nœud" })).toBeInTheDocument();
});

test("a node with no validation errors shows no error badge", () => {
  render(
    <PipelineCanvas
      nodes={NODES}
      edges={EDGES}
      selectedNodeId={null}
      onSelectNode={vi.fn()}
      onNodesChange={vi.fn()}
      onEdgesChange={vi.fn()}
      onInsertOnEdge={vi.fn()}
      opsCatalog={{}}
      nodeErrors={{ r1: [] }}
    />,
  );
  expect(screen.queryByText("!")).not.toBeInTheDocument();
});
```

- [ ] **Step 4: Run the new PipelineCanvas tests**

```bash
cd shell && npx vitest run src/builder/pipeline/PipelineCanvas.test.tsx
```
Expected: FAIL (prop `nodeErrors` not yet wired to a badge — wait, Step 2 already implements it; if Step 2 was applied before this point, expect PASS). Run and confirm both new tests PASS along with the pre-existing 9 tests in this file.

- [ ] **Step 5: Wire the banner and the disabled-save reason into `PipelineBuilderPage.tsx`**

Modify the `work` panel's content (around line 184-205) to insert a `Banner` between the header and the canvas:

```tsx
          content: (
            <div className="flex h-full flex-col overflow-hidden">
              <div className="border-b border-rule p-2">
                <h2 className="text-lg font-semibold text-ink">
                  {initialTitle ?? t("pipelineBuilder.defaultTitle")}
                </h2>
              </div>
              {validation.graphErrors.length > 0 && (
                <div className="p-2">
                  <Banner variant="danger">
                    <ul className="list-disc pl-4">
                      {validation.graphErrors.map((err) => (
                        <li key={err}>{err}</li>
                      ))}
                    </ul>
                  </Banner>
                </div>
              )}
              <div className="flex-1 overflow-auto p-2">
                <PipelineCanvas
                  nodes={draft.nodes}
                  edges={draft.edges}
                  selectedNodeId={selectedNodeId}
                  onSelectNode={setSelectedNodeId}
                  onNodesChange={setNodes}
                  onEdgesChange={setEdges}
                  onInsertOnEdge={onInsertOnEdge}
                  opsCatalog={catalog}
                  nodeStats={latestRun?.nodeStats}
                  runStatus={latestRun?.status}
                  nodeErrors={validation.nodeErrors}
                />
              </div>
            </div>
          ),
```

Add the import near the top (with the other `../ui/kit/*` imports):

```ts
import { Banner } from "../ui/kit/Banner";
```

Add the disabled-save reason, right after the existing `{readOnly && <p ...>}` block in the `inspect` panel (around line 267):

```tsx
                {readOnly && <p className="text-xs text-ink-2">{t("locked.needWrite")}</p>}
                {!valid && !readOnly && (
                  <p className="text-xs text-ink-2">{t("pipelineBuilder.saveDisabledReason")}</p>
                )}
```

- [ ] **Step 6: Test — graph errors appear as a banner, and the disabled-save reason is shown**

Add to `shell/src/pages/PipelineBuilderPage.test.tsx`:

```tsx
test("unsaved mode: graph-level errors are shown in a banner", async () => {
  renderPage(null);
  await waitFor(() => expect(screen.getByText("reader.collection")).toBeInTheDocument());
  expect(
    screen.getByText("Le pipeline doit contenir au moins une source."),
  ).toBeInTheDocument();
  expect(
    screen.getByText("Le pipeline doit contenir au moins une écriture."),
  ).toBeInTheDocument();
});

test("unsaved mode: shows a reason why Enregistrer is disabled", async () => {
  renderPage(null);
  await waitFor(() => expect(screen.getByText("reader.collection")).toBeInTheDocument());
  expect(
    screen.getByText("Le graphe contient des erreurs à corriger avant l'enregistrement."),
  ).toBeInTheDocument();
});
```

- [ ] **Step 7: Run the full frontend test suite for this task and commit**

```bash
cd shell && npx vitest run src/pages/PipelineBuilderPage.test.tsx src/builder/pipeline/PipelineCanvas.test.tsx
```
Expected: PASS (all tests, old and new).

```bash
git add shell/src/pages/PipelineBuilderPage.tsx shell/src/builder/pipeline/PipelineCanvas.tsx shell/src/i18n/catalog.fr.ts shell/src/pages/PipelineBuilderPage.test.tsx shell/src/builder/pipeline/PipelineCanvas.test.tsx
git commit -m "fix(shell): surface pipeline graph-level validation errors"
```

---

### Task 2: Aperçu de pipeline qui reflète le brouillon en cours d'édition (backend + frontend)

**Files:**
- Modify: `core/app/pipelines/routes.py`
- Test: `core/tests/test_pipeline_routes.py`
- Modify: `shell/src/api/domains/pipelines.ts`
- Modify: `shell/src/api/domains/pipelines.hooks.ts`
- Modify: `shell/src/api/types.ts`
- Modify: `shell/src/staticExport/StaticItemClient.ts`
- Modify: `shell/src/desktop/DesktopItemClient.ts`
- Modify: `shell/src/builder/pipeline/PipelinePreviewPanel.tsx`
- Modify: `shell/src/pages/PipelineBuilderPage.tsx`
- Modify: `shell/src/i18n/catalog.fr.ts`
- Test: `shell/src/builder/pipeline/PipelinePreviewPanel.test.tsx`
- Test: `shell/src/pages/PipelineBuilderPage.test.tsx`

**Interfaces:**
- Consumes: `preview_pipeline(payload: PipelinePayload, ...)` déjà découplé de la config persistée (`core/app/pipelines/runtime.py:748`) — seule la ROUTE force aujourd'hui `payload=config.config.pipeline`.
- Produces: `ItemClient.previewPipeline(pk, upToNodeId, draft?)` — 3e paramètre optionnel ; `usePipelinePreview(pipelineId, nodeId, draft)`.

#### Partie cœur

- [ ] **Step 1: Test backend — le corps de requête, quand fourni, prime sur la config persistée**

Ajouter dans `core/tests/test_pipeline_routes.py`, après `test_preview_route_rejects_unknown_pipeline` :

```python
def _seed_preview_pipeline(client):
    Session = client.session_factory  # type: ignore[attr-defined]
    tenant = client.tenant  # type: ignore[attr-defined]
    owner = client.user  # type: ignore[attr-defined]
    with Session() as s:
        item = items_repo.create_item(
            s,
            tenant_id=tenant.id,
            owner_id=owner.id,
            resource_type="pipeline",
            title="Pipeline preview",
        )
        configs_repo.create_config(
            s,
            BuilderConfig.model_validate(
                {
                    "version": 1,
                    "kind": "pipeline",
                    "pipeline": {
                        "nodes": [
                            {
                                "id": "r1",
                                "kind": "reader",
                                "op": "reader.collection",
                                "params": {"collectionId": "x"},
                            },
                            {
                                "id": "w1",
                                "kind": "writer",
                                "op": "writer.export",
                                "params": {"format": "csv", "key": "o.csv"},
                            },
                        ],
                        "edges": [{"id": "e1", "from": "r1", "to": "w1"}],
                    },
                }
            ),
            item_id=item.id,
            tenant_id=tenant.id,
        )
        s.commit()
        return item.id


def test_preview_route_uses_the_persisted_config_when_no_body_is_sent(monkeypatch):
    client = _make_app(monkeypatch, etl_enabled=True)
    item_id = _seed_preview_pipeline(client)
    captured = {}

    def fake_preview_pipeline(*, payload, **kwargs):
        captured["collectionId"] = payload.nodes[0].params["collectionId"]
        return [{"id": 1}]

    monkeypatch.setattr("app.pipelines.routes.preview_pipeline", fake_preview_pipeline)
    response = client.post(f"/v1/pipelines/{item_id}/preview?upTo=r1")
    assert response.status_code == 200
    assert captured["collectionId"] == "x"


def test_preview_route_uses_the_request_body_pipeline_when_provided(monkeypatch):
    client = _make_app(monkeypatch, etl_enabled=True)
    item_id = _seed_preview_pipeline(client)
    captured = {}

    def fake_preview_pipeline(*, payload, **kwargs):
        captured["collectionId"] = payload.nodes[0].params["collectionId"]
        return [{"id": 1}]

    monkeypatch.setattr("app.pipelines.routes.preview_pipeline", fake_preview_pipeline)
    draft = {
        "nodes": [
            {
                "id": "r1",
                "kind": "reader",
                "op": "reader.collection",
                "params": {"collectionId": "y"},
            },
            {
                "id": "w1",
                "kind": "writer",
                "op": "writer.export",
                "params": {"format": "csv", "key": "o.csv"},
            },
        ],
        "edges": [{"id": "e1", "from": "r1", "to": "w1"}],
    }
    response = client.post(
        f"/v1/pipelines/{item_id}/preview?upTo=r1", json={"pipeline": draft}
    )
    assert response.status_code == 200
    assert captured["collectionId"] == "y"
```

`items_repo`/`configs_repo`/`BuilderConfig` sont déjà importés en tête de `test_pipeline_routes.py` (mêmes imports que `_seed_webhook_pipeline`, réutilisés tels quels).

- [ ] **Step 2: Run the new tests to verify they fail**

```bash
cd core && uv run pytest tests/test_pipeline_routes.py -k preview_route_uses -v
```
Expected: FAIL — `test_preview_route_uses_the_request_body_pipeline_when_provided` fails (route ignores the body), `test_preview_route_uses_the_persisted_config_when_no_body_is_sent` should already PASS (current behavior).

- [ ] **Step 3: Accept an optional request body in the preview route**

Modify `core/app/pipelines/routes.py`. Add the import (near the top, with the other `PipelinePayload`-adjacent imports):

```python
from app.configs.schemas import PipelinePayload
```

Add a request body model near the other `BaseModel` classes (after `RunStatus`):

```python
class PipelinePreviewRequest(BaseModel):
    pipeline: PipelinePayload | None = None
```

Replace the `preview_pipeline_route` function body:

```python
@router.post("/pipelines/{item_id}/preview")
def preview_pipeline_route(
    item_id: str,
    upTo: str = Query(...),
    body: PipelinePreviewRequest | None = None,
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
) -> list[dict]:
    require_pipeline_access(session, user=user, item_id=item_id, action="read")
    config = require_pipeline_config(session, item_id)
    payload = body.pipeline if body and body.pipeline is not None else config.config.pipeline
    try:
        return preview_pipeline(
            session=session,
            payload=payload,
            tenant_id=user.tenant_id,
            user=user,
            up_to=upTo,
            endpoint_url=os.environ.get("S3_ENDPOINT_URL", ""),
            access_key=os.environ.get("S3_ACCESS_KEY", ""),
            secret_key=os.environ.get("S3_SECRET_KEY", ""),
            base_uri=f"s3://{os.environ.get('S3_CDC_BUCKET', 'geostudio-cdc')}/cdc",
            qgis_worker_url=os.environ.get("QGIS_WORKER_URL", ""),
            qgis_worker_timeout_seconds=int(os.environ.get("QGIS_WORKER_TIMEOUT_SECONDS", "600")),
        )
    except PipelineRuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
```

- [ ] **Step 4: Run the backend tests**

```bash
cd core && uv run pytest tests/test_pipeline_routes.py -v
```
Expected: PASS (all tests in the file, including the 2 new ones and the pre-existing `test_preview_route_rejects_unknown_pipeline`).

- [ ] **Step 5: Regenerate OpenAPI + TS types**

```bash
cd core && PYTHONPATH=. \
  CORE_SECRETS_MASTER_KEY="AAECAwQFBgcICQoLDA0ODxAREhMUFRYXGBkaGxwdHh8=" \
  uv run python scripts/export_openapi.py openapi.json
cd ../shell && npm run gen:api-types
```

#### Partie shell

- [ ] **Step 6: Add the optional draft parameter to `ItemClient.previewPipeline` and its 3 implementations**

Modify `shell/src/api/types.ts` line 531:

```ts
  previewPipeline(
    pk: string,
    upToNodeId: string,
    draft?: PipelinePayload,
  ): Promise<Record<string, unknown>[]>;
```

Modify `shell/src/api/domains/pipelines.ts`:

```ts
    async previewPipeline(
      pk: string,
      upToNodeId: string,
      draft?: PipelinePayload,
    ): Promise<Record<string, unknown>[]> {
      return request<Record<string, unknown>[]>(
        "POST",
        `/pipelines/${pk}/preview?upTo=${encodeURIComponent(upToNodeId)}`,
        draft !== undefined ? { pipeline: draft } : undefined,
      );
    },
```

Confirm `request()`'s 4th argument is the JSON body by checking `ItemClientBase["request"]`'s signature in `shell/src/api/base.ts` before writing this call — if the parameter order differs, match the real signature rather than this sketch.

Modify `shell/src/staticExport/StaticItemClient.ts` — no change needed: `previewPipeline(..._args: unknown[])` already accepts any arity.

Modify `shell/src/desktop/DesktopItemClient.ts`:

```ts
    async previewPipeline(
      pk: string,
      upToNodeId: string,
      draft?: PipelinePayload,
    ): Promise<Record<string, unknown>[]> {
      return sidecarFetch<Record<string, unknown>[]>(
        "POST",
        `/pipelines/${pk}/preview?upTo=${encodeURIComponent(upToNodeId)}`,
        draft !== undefined ? { pipeline: draft } : undefined,
      );
    },
```

Confirm `sidecarFetch`'s signature accepts an optional body 3rd argument by reading its definition in this same file before writing this call — match the real signature.

- [ ] **Step 7: Thread the draft through `usePipelinePreview` and `PipelinePreviewPanel`**

Modify `shell/src/api/domains/pipelines.hooks.ts`:

```ts
export function usePipelinePreview(
  pipelineId: string,
  nodeId: string | null,
  draft?: PipelinePayload,
) {
  const client = useItemClientInternal();
  return useQuery({
    queryKey: ["pipeline-preview", pipelineId, nodeId, draft],
    queryFn: () => client.previewPipeline(pipelineId, nodeId!, draft),
    enabled: nodeId !== null,
  });
}
```

Add `PipelinePayload` to this file's type import (`import type { PipelinePayload } from "../types";`).

Modify `shell/src/builder/pipeline/PipelinePreviewPanel.tsx` to accept and forward the draft, and to show a freshness indicator:

```tsx
// SPDX-License-Identifier: Apache-2.0
import { useState } from "react";
import { usePipelinePreview } from "../../api/hooks";
import type { PipelinePayload } from "../../api/types";
import { t } from "../../i18n";
import { PipelinePreviewMap } from "./PipelinePreviewMap";

export function PipelinePreviewPanel({
  pipelineId,
  nodeId,
  draft,
  isDraftStale,
}: {
  pipelineId: string;
  nodeId: string | null;
  draft?: PipelinePayload;
  isDraftStale?: boolean;
}) {
  const previewQuery = usePipelinePreview(pipelineId, nodeId, draft);
  const [view, setView] = useState<"table" | "map">("table");

  if (nodeId === null) return null;
  if (previewQuery.isLoading) return <p role="status">{t("pipelinePreview.loading")}</p>;
  if (previewQuery.isError)
    return (
      <p role="alert" className="text-sm text-danger">
        {t("pipelinePreview.unavailable")}
      </p>
    );

  const rows = previewQuery.data ?? [];
  const columns = rows.length > 0 ? Object.keys(rows[0]) : [];
  const hasGeometry = columns.includes("geometry");

  return (
    <div className="flex flex-col gap-2">
      {isDraftStale && (
        <p role="status" className="w-fit rounded-full bg-warn-soft px-2 py-0.5 text-[10px] text-warn">
          {t("pipelinePreview.stale")}
        </p>
      )}
      {hasGeometry && (
        <div className="flex gap-1 text-xs">
          <button
            type="button"
            onClick={() => setView("table")}
            className={`rounded px-2 py-1 ${view === "table" ? "bg-sunken" : ""}`}
          >
            {t("pipelinePreview.tableView")}
          </button>
          <button
            type="button"
            onClick={() => setView("map")}
            className={`rounded px-2 py-1 ${view === "map" ? "bg-sunken" : ""}`}
          >
            {t("pipelinePreview.mapView")}
          </button>
        </div>
      )}
      {hasGeometry && view === "map" ? (
        <PipelinePreviewMap rows={rows} />
      ) : (
        <table className="w-full text-xs">
          <thead>
            <tr>
              {columns.map((c) => (
                <th key={c} className="p-1 text-left">
                  {c}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((row, i) => (
              <tr key={i} className="border-t border-rule">
                {columns.map((c) => (
                  <td key={c} className="p-1">
                    {String(row[c])}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}
```

`isDraftStale` is a signal computed by the caller (Step 8) — this component only renders it, it doesn't compute staleness itself, since it has no notion of "saved" state.

Add i18n key, anchored after `"pipelinePreview.mapView": "Carte",`:

```ts
  "pipelinePreview.stale": "Aperçu à régénérer (paramètres modifiés depuis le dernier calcul)",
```

- [ ] **Step 8: Send the current draft from `PipelineBuilderPage.tsx`, and compute staleness**

`PipelinePreviewPanel` is rendered at `PipelineBuilderPage.tsx:224`. Replace:

```tsx
                  {pk !== null && <PipelinePreviewPanel pipelineId={pk} nodeId={selectedNode.id} />}
```

with:

```tsx
                  {pk !== null && (
                    <PipelinePreviewPanel
                      pipelineId={pk}
                      nodeId={selectedNode.id}
                      draft={draft}
                      isDraftStale={configQuery.data !== undefined && configQuery.data !== draft}
                    />
                  )}
```

`configQuery.data !== draft` is a reference comparison, not a deep-equal: it is `true` the instant any edit creates a new `draft` object (every `setDraft` call replaces the object), and becomes `false` again only once `configQuery.data` itself is refetched with the saved content (after a successful save, `useSavePipeline`'s `onSuccess` already invalidates `["pipeline", pk]` — cf. `pipelines.hooks.ts:33`). This is intentionally coarse (any edit ⇒ "stale", not a semantic diff) — sufficient for a freshness hint, not a correctness guarantee.

- [ ] **Step 9: Test — preview receives the draft, and shows the staleness hint**

Modify `shell/src/builder/pipeline/PipelinePreviewPanel.test.tsx`. Update the `renderPanel` helper to accept and pass through `draft`/`isDraftStale`:

```tsx
function renderPanel(
  previewPipeline = vi.fn().mockResolvedValue([{ id: 1, pop: 1200 }]),
  extraProps: { draft?: PipelinePayload; isDraftStale?: boolean } = {},
) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const client: Partial<ItemClient> = { previewPipeline };
  render(
    <QueryClientProvider client={qc}>
      <ItemClientProvider client={client as ItemClient}>
        <PipelinePreviewPanel pipelineId="p-1" nodeId="r1" {...extraProps} />
      </ItemClientProvider>
    </QueryClientProvider>,
  );
  return { previewPipeline };
}
```

Add `import type { ItemClient, PipelinePayload } from "../../api/types";` (extend the existing type import).

Add two tests:

```tsx
test("forwards the draft to previewPipeline when provided", async () => {
  const draft: PipelinePayload = { nodes: [], edges: [] };
  const { previewPipeline } = renderPanel(undefined, { draft });
  await waitFor(() => expect(previewPipeline).toHaveBeenCalledWith("p-1", "r1", draft));
});

test("shows a staleness hint when isDraftStale is true", async () => {
  renderPanel(undefined, { isDraftStale: true });
  await waitFor(() => expect(screen.getByRole("status")).toHaveTextContent("Aperçu à régénérer"));
});

test("shows no staleness hint by default", async () => {
  renderPanel();
  await waitFor(() => expect(previewPipeline).toHaveBeenCalled());
  expect(screen.queryByText("Aperçu à régénérer", { exact: false })).not.toBeInTheDocument();
});
```

The third test's `previewPipeline` reference must come from the local `const { previewPipeline } = renderPanel();` in that test body, not the outer scope — write it as such.

- [ ] **Step 10: Run the frontend tests**

```bash
cd shell && npx vitest run src/builder/pipeline/PipelinePreviewPanel.test.tsx src/pages/PipelineBuilderPage.test.tsx
```
Expected: PASS. If `PipelineBuilderPage.test.tsx`'s existing tests fail because `previewPipeline` is not mocked on `renderPage`'s default client, check whether any existing test triggers the preview panel (selecting a node) — if so, add `previewPipeline: vi.fn().mockResolvedValue([])` to that test's overrides.

- [ ] **Step 11: Commit**

```bash
cd core && git add app/pipelines/routes.py tests/test_pipeline_routes.py openapi.json
git commit -m "fix(core): accept a draft pipeline body on the preview route"
cd ../shell && git add src/api/domains/pipelines.ts src/api/domains/pipelines.hooks.ts src/api/types.ts src/desktop/DesktopItemClient.ts src/builder/pipeline/PipelinePreviewPanel.tsx src/pages/PipelineBuilderPage.tsx src/i18n/catalog.fr.ts src/builder/pipeline/PipelinePreviewPanel.test.tsx src/pages/PipelineBuilderPage.test.tsx src/api/generated/core-schema.d.ts
git commit -m "fix(shell): pipeline preview now reflects the in-progress draft"
```

---

### Task 3: Corrige la carte de preview figée sur le nœud précédent

**Files:**
- Modify: `shell/src/builder/pipeline/PipelinePreviewMap.tsx`
- Test: `shell/src/builder/pipeline/PipelinePreviewMap.test.tsx`

**Interfaces:**
- Consumes: none new.
- Produces: none new — pure bugfix, same public props.

- [ ] **Step 1: Write the failing test**

Add to `shell/src/builder/pipeline/PipelinePreviewMap.test.tsx`:

```tsx
test("rebuilds the map when the rows prop changes (different selected node)", () => {
  const { rerender } = render(
    <PipelinePreviewMap
      rows={[{ id: 1, geometry: { type: "Point", coordinates: [1.0, 1.0] } }]}
    />,
  );
  expect(mapInstances).toHaveLength(1);
  rerender(
    <PipelinePreviewMap
      rows={[{ id: 2, geometry: { type: "Point", coordinates: [9.0, 9.0] } }]}
    />,
  );
  expect(mapInstances).toHaveLength(2); // a fresh map, not the stale one
  const latestMap = mapInstances[1];
  const source = latestMap.getSource("pipeline-preview") as {
    spec: { data: GeoJSON.FeatureCollection };
  };
  expect(source.spec.data.features[0].geometry).toEqual({ type: "Point", coordinates: [9.0, 9.0] });
});
```

- [ ] **Step 2: Run it to verify it fails**

```bash
cd shell && npx vitest run src/builder/pipeline/PipelinePreviewMap.test.tsx -t "rebuilds the map"
```
Expected: FAIL — `mapInstances` has length 1 (the effect never re-runs; `rerender` reuses the same mounted `maplibregl.Map`).

- [ ] **Step 3: Fix the effect's dependency array**

In `shell/src/builder/pipeline/PipelinePreviewMap.tsx`, change the closing of the main `useEffect` (currently `}, []); // eslint-disable-next-line react-hooks/exhaustive-deps` placed before the deps array) to depend on `rows`:

```tsx
  }, [rows]);
```

Remove the now-unneeded `// eslint-disable-next-line react-hooks/exhaustive-deps` comment line immediately above it (the effect's only external reference is `rows`, now correctly listed).

- [ ] **Step 4: Run the test to verify it passes**

```bash
cd shell && npx vitest run src/builder/pipeline/PipelinePreviewMap.test.tsx
```
Expected: PASS (all tests in the file, including the pre-existing 3).

- [ ] **Step 5: Commit**

```bash
git add shell/src/builder/pipeline/PipelinePreviewMap.tsx shell/src/builder/pipeline/PipelinePreviewMap.test.tsx
git commit -m "fix(shell): rebuild the pipeline preview map when the selected node changes"
```

---

### Task 4: Menu d'insertion sur arête — liste dynamique dérivée du catalogue

**Files:**
- Modify: `shell/src/builder/pipeline/PipelineCanvas.tsx`
- Test: `shell/src/builder/pipeline/PipelineCanvas.test.tsx`

**Interfaces:**
- Consumes: `opsCatalog: PipelineOpsCatalog` (déjà une prop de `PipelineCanvasInner` — déjà accessible dans `InsertOnEdgeButton` moyennant son passage explicite).
- Produces: aucun changement de forme externe — `INSERTABLE_TRANSFORMS` disparaît en tant que constante module-level.

- [ ] **Step 1: Write the failing test**

Add to `shell/src/builder/pipeline/PipelineCanvas.test.tsx`, a catalog with a transform op absent from the old hardcoded list:

```tsx
test("the edge insertion menu is derived from opsCatalog, including an op not in the old hardcoded list", () => {
  const catalog: PipelineOpsCatalog = {
    "reader.collection": { kind: "reader", paramsSchema: { properties: {} } },
    "writer.collection": { kind: "writer", paramsSchema: { properties: {} } },
    "transform.swapCoordinates": {
      kind: "transform",
      paramsSchema: { properties: {}, description: "Permuter lat/lng" },
    },
  };
  render(
    <PipelineCanvas
      nodes={NODES}
      edges={EDGES}
      selectedNodeId={null}
      onSelectNode={vi.fn()}
      onNodesChange={vi.fn()}
      onEdgesChange={vi.fn()}
      onInsertOnEdge={vi.fn()}
      opsCatalog={catalog}
    />,
  );
  fireEvent.click(screen.getByRole("button", { name: "Insérer une étape sur cette arête" }));
  expect(screen.getByRole("menuitem", { name: "transform.swapCoordinates" })).toBeInTheDocument();
  // readers/writers never appear in this menu — only transform.* ops.
  expect(screen.queryByRole("menuitem", { name: "reader.collection" })).not.toBeInTheDocument();
});
```

- [ ] **Step 2: Run it to verify it fails**

```bash
cd shell && npx vitest run src/builder/pipeline/PipelineCanvas.test.tsx -t "derived from opsCatalog"
```
Expected: FAIL — the menu still only offers the 11 hardcoded ops, `transform.swapCoordinates` absent.

- [ ] **Step 3: Derive the menu from `opsCatalog` instead of the hardcoded list**

In `shell/src/builder/pipeline/PipelineCanvas.tsx`, remove the `INSERTABLE_TRANSFORMS` constant (lines 31-48) entirely.

Modify `InsertOnEdgeButton` to receive `opsCatalog` and compute the list from it:

```tsx
function InsertOnEdgeButton({
  id,
  sourceX,
  sourceY,
  targetX,
  targetY,
  data,
  onInsert,
  opsCatalog,
}: EdgeProps & { onInsert: (edgeId: string, op: string) => void; opsCatalog: PipelineOpsCatalog }) {
  const [open, setOpen] = useState(false);
  const insertMenu = usePanelTrigger(open);
  const [edgePath, labelX, labelY] = getBezierPath({ sourceX, sourceY, targetX, targetY });
  const role = (data as { role?: string } | undefined)?.role;
  const insertableTransforms = Object.entries(opsCatalog)
    .filter(([, entry]) => entry.kind === "transform")
    .map(([op]) => op)
    .sort();
  return (
    <>
      <path
        id={id}
        className="react-flow__edge-path"
        d={edgePath}
        style={role === "secondary" ? { strokeDasharray: "4 4" } : undefined}
      />
      <EdgeLabelRenderer>
        <div
          style={{
            position: "absolute",
            transform: `translate(-50%, -50%) translate(${labelX}px,${labelY}px)`,
            pointerEvents: "all",
          }}
        >
          <button
            type="button"
            aria-label={t("pipelineCanvas.insertStepAria")}
            aria-expanded={insertMenu.triggerProps["aria-expanded"]}
            aria-controls={insertMenu.triggerProps["aria-controls"]}
            className="h-5 w-5 rounded-full border border-rule bg-surface text-xs leading-none hover:bg-sunken"
            onClick={() => setOpen((o) => !o)}
          >
            +
          </button>
          {open && (
            <ul
              id={insertMenu.panelId}
              role="menu"
              className="absolute z-10 mt-1 rounded border border-rule bg-surface text-xs shadow"
            >
              {insertableTransforms.map((op) => (
                <li key={op}>
                  <button
                    type="button"
                    role="menuitem"
                    className="block w-full whitespace-nowrap px-2 py-1 text-left hover:bg-sunken"
                    onClick={() => {
                      onInsert(id, op);
                      setOpen(false);
                    }}
                  >
                    {op}
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>
      </EdgeLabelRenderer>
    </>
  );
}
```

Update the `edgeTypes` wiring in `PipelineCanvasInner` to pass `opsCatalog` through:

```tsx
  const edgeTypes = {
    insertable: (props: EdgeProps) => (
      <InsertOnEdgeButton {...props} onInsert={onInsertOnEdge} opsCatalog={opsCatalog} />
    ),
  };
```

- [ ] **Step 4: Update the 3 pre-existing tests that asserted French labels on the old hardcoded menu**

The tests `"the edge insertion menu offers the 5 spatial transform ops"` and `"the edge insertion menu offers Fusionner (transform.merge)"` and the `onInsertOnEdge` assertion inside `"the edge's insert button is present..."` currently assert French labels (`"Buffer"`, `"Reprojeter"`, `"Filtrer"`, …) that came from `t("pipelineCanvas.transform*")`. The menu now renders the raw op id instead (consistent with the rest of the palette, which already renders raw op ids — cf. `PipelinePalette.tsx`). Update these 3 tests' expectations from the French labels to the op ids:

- `"the edge's insert button is present and triggers onInsertOnEdge..."`: replace `screen.getByRole("menuitem", { name: "Filtrer" })` with `screen.getByRole("menuitem", { name: "transform.filter" })`, and the `toHaveBeenCalledWith("e1", "transform.filter")` assertion is unchanged.
- `"the edge insertion menu offers the 5 spatial transform ops"`: replace the label loop with op ids:
  ```tsx
  for (const op of [
    "transform.buffer",
    "transform.reproject",
    "transform.intersection",
    "transform.countWithin",
    "transform.h3Aggregate",
  ]) {
    expect(screen.getByRole("menuitem", { name: op })).toBeInTheDocument();
  }
  ```
  This test passes `opsCatalog={{}}` today (no catalog) — the menu would now be empty. Give it a catalog with these 5 ops as `kind: "transform"` (mirroring `BINARY_CATALOG`'s shape further down in the same file), e.g.:
  ```tsx
  const catalog: PipelineOpsCatalog = Object.fromEntries(
    ["transform.buffer", "transform.reproject", "transform.intersection", "transform.countWithin", "transform.h3Aggregate"].map(
      (op) => [op, { kind: "transform", paramsSchema: { properties: {} } }],
    ),
  );
  ```
  and pass `opsCatalog={catalog}` to `<PipelineCanvas>` in this test.
- `"the edge insertion menu offers Fusionner (transform.merge)"`: same treatment — give it a 1-entry catalog `{ "transform.merge": { kind: "transform", paramsSchema: { properties: {} } } }`, replace `getByRole("menuitem", { name: "Fusionner" })` with `getByRole("menuitem", { name: "transform.merge" })`.

The `"the edge's insert button is present..."` test currently passes `opsCatalog={{}}` too — give it `{ "transform.filter": { kind: "transform", paramsSchema: { properties: {} } } }`.

- [ ] **Step 5: Run all PipelineCanvas tests**

```bash
cd shell && npx vitest run src/builder/pipeline/PipelineCanvas.test.tsx
```
Expected: PASS (all tests, including the new one and the 3 updated ones).

- [ ] **Step 6: Delete now-orphaned i18n keys**

In `shell/src/i18n/catalog.fr.ts`, remove the 11 keys `pipelineCanvas.transform*` (lines ~1045-1055) — no longer referenced anywhere (`t()`'s `MessageKey` type would otherwise keep them as dead entries, and `npm run lint`'s unused-key detector, if any, would flag them). Verify with:

```bash
cd shell && grep -rn "pipelineCanvas\.transform" src/ --include=*.ts --include=*.tsx
```
Expected: no output (only the catalog file itself, about to be edited, would have matched).

- [ ] **Step 7: Run the full shell test suite and commit**

```bash
cd shell && npm run test
```
Expected: PASS.

```bash
git add shell/src/builder/pipeline/PipelineCanvas.tsx shell/src/builder/pipeline/PipelineCanvas.test.tsx shell/src/i18n/catalog.fr.ts
git commit -m "refactor(shell): derive the edge-insertion transform menu from the ops catalog"
```

---

### Task 5: Mini-map sur le canvas

**Files:**
- Modify: `shell/src/builder/pipeline/PipelineCanvas.tsx`
- Test: `shell/src/builder/pipeline/PipelineCanvas.test.tsx`

**Interfaces:** none new.

- [ ] **Step 1: Write the failing test**

```tsx
test("renders a minimap", () => {
  render(
    <PipelineCanvas
      nodes={NODES}
      edges={EDGES}
      selectedNodeId={null}
      onSelectNode={vi.fn()}
      onNodesChange={vi.fn()}
      onEdgesChange={vi.fn()}
      onInsertOnEdge={vi.fn()}
      opsCatalog={{}}
    />,
  );
  expect(document.querySelector(".react-flow__minimap")).not.toBeNull();
});
```

- [ ] **Step 2: Run it to verify it fails**

```bash
cd shell && npx vitest run src/builder/pipeline/PipelineCanvas.test.tsx -t "renders a minimap"
```
Expected: FAIL — no `.react-flow__minimap` element in the DOM.

- [ ] **Step 3: Add `MiniMap`**

In `shell/src/builder/pipeline/PipelineCanvas.tsx`, add `MiniMap` to the `@xyflow/react` import list (line 3-19):

```tsx
import {
  Background,
  Controls,
  EdgeLabelRenderer,
  Handle,
  MiniMap,
  Position,
  ReactFlow,
  ReactFlowProvider,
  getBezierPath,
  ...
```

Add `<MiniMap />` inside `<ReactFlow>`, after `<Controls />`:

```tsx
        <Background />
        <Controls />
        <MiniMap
          nodeColor={(n) => (KIND_COLOR[(n.data as unknown as CanvasNodeData).kind] ? "#94a3b8" : "#cbd5e1")}
          pannable
          zoomable
        />
```

`KIND_COLOR` values are Tailwind class strings, not usable directly as a `nodeColor` return — this callback only needs *a* color, not the exact same one as the node's border; keep it simple with a single flat color for all node types (`"#94a3b8"`), since React Flow's `MiniMap` renders each node in a single fill color and distinguishing kinds there is not part of this task's scope:

```tsx
        <MiniMap pannable zoomable />
```

(This simpler line replaces the `nodeColor` callback sketch above — use this one.)

- [ ] **Step 4: Run the test to verify it passes**

```bash
cd shell && npx vitest run src/builder/pipeline/PipelineCanvas.test.tsx
```
Expected: PASS (all tests). The `MiniMap` component uses the same `ResizeObserver`/`DOMMatrixReadOnly` stubs already set up in this test file's `beforeEach` — no new stub needed.

- [ ] **Step 5: Commit**

```bash
git add shell/src/builder/pipeline/PipelineCanvas.tsx shell/src/builder/pipeline/PipelineCanvas.test.tsx
git commit -m "feat(shell): add a minimap to the pipeline canvas"
```

---

### Task 6: Undo/redo sur le pipeline builder (généralise `useUndoableDraft`)

**Files:**
- Modify: `shell/src/builder/useUndoableDraft.ts`
- Modify: `shell/src/builder/useUndoableDraft.test.tsx`
- Modify: `shell/src/pages/AppBuilderPage.tsx`
- Modify: `shell/src/pages/PipelineBuilderPage.tsx`
- Modify: `shell/src/i18n/catalog.fr.ts`
- Test: `shell/src/pages/PipelineBuilderPage.test.tsx`

**Interfaces:**
- Produces: `useUndoableDraft<T>(): UndoableDraft<T>` (was hardcoded to `AppConfig`) — the only other consumer, `AppBuilderPage.tsx`, must pass `<AppConfig>` explicitly since there is no argument for TS to infer `T` from.

- [ ] **Step 1: Genericize `useUndoableDraft.ts`**

In `shell/src/builder/useUndoableDraft.ts`, remove the import `import type { AppConfig } from "../api/types";` and replace every occurrence of `AppConfig` with a type parameter `T`:

```ts
export type UndoableDraft<T> = {
  draft: T | null;
  setDraft: (update: T | null | ((prev: T | null) => T | null)) => void;
  seedDraft: (value: T) => void;
  resetDraft: (value: T) => void;
  undo: () => void;
  redo: () => void;
  canUndo: boolean;
  canRedo: boolean;
};

export function useUndoableDraft<T>(): UndoableDraft<T> {
  const [draft, setDraftState] = useState<T | null>(null);
  const draftRef = useRef<T | null>(null);
  const stackRef = useRef<UndoStack<T>>(createUndoStack());
  const pendingBaselineRef = useRef<T | null>(null);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const [canUndo, setCanUndo] = useState(false);
  const [canRedo, setCanRedo] = useState(false);

  const flush = useCallback(() => {
    if (timerRef.current !== null) {
      clearTimeout(timerRef.current);
      timerRef.current = null;
    }
    if (pendingBaselineRef.current === null) return;
    stackRef.current = pushUndo(stackRef.current, pendingBaselineRef.current);
    pendingBaselineRef.current = null;
    setCanUndo(true);
    setCanRedo(false);
  }, []);

  useEffect(
    () => () => {
      if (timerRef.current !== null) clearTimeout(timerRef.current);
    },
    [],
  );

  const setDraft = useCallback<UndoableDraft<T>["setDraft"]>(
    (update) => {
      const prev = draftRef.current;
      const next =
        typeof update === "function" ? (update as (p: T | null) => T | null)(prev) : update;
      if (next !== prev && prev !== null) {
        if (pendingBaselineRef.current === null) pendingBaselineRef.current = prev;
        if (timerRef.current !== null) clearTimeout(timerRef.current);
        timerRef.current = setTimeout(flush, COALESCE_WINDOW_MS);
      }
      draftRef.current = next;
      setDraftState(next);
    },
    [flush],
  );

  const seedDraft = useCallback((value: T) => {
    if (draftRef.current !== null) return;
    draftRef.current = value;
    setDraftState(value);
  }, []);

  const resetDraft = useCallback((value: T) => {
    if (timerRef.current !== null) {
      clearTimeout(timerRef.current);
      timerRef.current = null;
    }
    pendingBaselineRef.current = null;
    stackRef.current = createUndoStack();
    draftRef.current = value;
    setCanUndo(false);
    setCanRedo(false);
    setDraftState(value);
  }, []);

  const undo = useCallback(() => {
    flush();
    const prev = draftRef.current;
    if (prev === null) return;
    const result = applyUndo(stackRef.current, prev);
    if (result === null) return;
    stackRef.current = result.stack;
    draftRef.current = result.value;
    setCanUndo(result.stack.past.length > 0);
    setCanRedo(true);
    setDraftState(result.value);
  }, [flush]);

  const redo = useCallback(() => {
    flush();
    const prev = draftRef.current;
    if (prev === null) return;
    const result = applyRedo(stackRef.current, prev);
    if (result === null) return;
    stackRef.current = result.stack;
    draftRef.current = result.value;
    setCanUndo(true);
    setCanRedo(result.stack.future.length > 0);
    setDraftState(result.value);
  }, [flush]);

  return { draft, setDraft, seedDraft, resetDraft, undo, redo, canUndo, canRedo };
}
```

The module's top-of-file explanatory comment block (lines 2-30, explaining the coalescing design) is untouched — it documents behavior, not the `AppConfig` type, and remains accurate.

- [ ] **Step 2: Update `useUndoableDraft.test.tsx`'s 12 call sites to pin `T` explicitly**

In `shell/src/builder/useUndoableDraft.test.tsx`, every `useUndoableDraft()` call must become `useUndoableDraft<AppConfig>()` — `AppConfig` is already imported (line 5). Two of these tests (`"setDraft supports the functional-updater form"` and `"two setDraft calls issued synchronously..."`) read `prev.layout.items[0]...` inside the updater callback and will fail to type-check (`prev` typed `unknown`) without this change — this is not optional. Apply to all 12 occurrences (`renderHook(() => useUndoableDraft())` and the 2 with `{ wrapper: StrictMode }`):

```bash
cd shell && sed -i 's/useUndoableDraft()/useUndoableDraft<AppConfig>()/g' src/builder/useUndoableDraft.test.tsx
```

Verify the count matches expectations:

```bash
grep -c "useUndoableDraft<AppConfig>()" src/builder/useUndoableDraft.test.tsx
```
Expected: `12`.

- [ ] **Step 3: Update `AppBuilderPage.tsx`'s call site**

Add `AppConfig` to the existing type-only import on line 14:

```ts
import type { AppConfig, PrintLayoutConfig, RenderMode, WidgetItem } from "../api/types";
```

Change line 74 (`useUndoableDraft();`) to:

```ts
    useUndoableDraft<AppConfig>();
```

- [ ] **Step 4: Run the tests touched so far**

```bash
cd shell && npx vitest run src/builder/useUndoableDraft.test.tsx src/pages/AppBuilderPage.test.tsx
```
Expected: PASS.

```bash
cd shell && npx tsc --noEmit
```
Expected: no errors (confirms every `useUndoableDraft` call site across the repo — there are only these two consumer files plus the one this task is about to add — type-checks).

- [ ] **Step 5: Wire undo/redo into `PipelineBuilderPage.tsx`**

Add to the import list:

```ts
import { useUndoableDraft } from "../builder/useUndoableDraft";
```

Replace:

```ts
  const [draft, setDraft] = useState<PipelinePayload>(EMPTY_PAYLOAD);
```

with:

```ts
  const { draft, setDraft, seedDraft, resetDraft, undo, redo, canUndo, canRedo } =
    useUndoableDraft<PipelinePayload>();
```

Replace the existing seeding effect:

```ts
  useEffect(() => {
    if (pk !== null && configQuery.data) setDraft(configQuery.data);
  }, [pk, configQuery.data]);
```

with:

```ts
  useEffect(() => {
    if (pk === null) {
      seedDraft(EMPTY_PAYLOAD);
      return;
    }
    if (configQuery.data) seedDraft(configQuery.data);
  }, [pk, configQuery.data, seedDraft]);
```

Add a loading guard for the brief window before the draft is seeded, right after the existing `if (opsQuery.isLoading || !opsQuery.data) return ...;` guard:

```ts
  if (draft === null) return <p role="status">{t("common.loading")}</p>;
```

From this point on in the function body, `draft` is narrowed to `PipelinePayload` by TypeScript's control-flow analysis (the early return above makes every use of `draft` below it non-null) — `const validation = validatePipelineGraphLocally(draft.nodes, draft.edges, catalog);` and the rest of the function need no further change on that account.

Update the 4 mutator functions to use `setDraft`'s updater form defensively (the updater's own parameter type is still `PipelinePayload | null`, independent of the outer `draft` narrowing):

```ts
  function setNodes(nodes: PipelineNode[]) {
    setDraft((d) => (d ? { ...d, nodes } : d));
  }
  function setEdges(edges: PipelineEdge[]) {
    setDraft((d) => (d ? { ...d, edges } : d));
  }
  function setRefreshPolicy(refreshPolicy: PipelineRefreshPolicy | null) {
    setDraft((d) => (d ? { ...d, refreshPolicy } : d));
  }
  function updateSelectedNodeParams(params: Record<string, unknown>) {
    if (!selectedNode) return;
    setDraft((d) => (d ? { ...d, nodes: d.nodes.map((n) => (n.id === selectedNode.id ? { ...n, params } : n)) } : d));
  }
```

`onInsertOnEdge` and `onDropOnCanvas` call `setNodes`/the equivalent `setDraft` form already — no change needed there since they go through the now-updated `setNodes`/build a full node list; re-check `onInsertOnEdge`'s body (`setDraft(result);` where `result` is `{nodes, edges}` from `insertNodeOnEdge`) and give it the same defensive form:

```ts
  function onInsertOnEdge(edgeId: string, op: string) {
    const kind = catalog[op]?.kind ?? "transform";
    const result = insertNodeOnEdge(draft.nodes, draft.edges, edgeId, {
      id: genNodeId(),
      kind,
      op,
      x: 0,
      y: 0,
      params: {},
      title: op,
    });
    setDraft((d) => (d ? { ...d, ...result } : d));
  }
```

Replace the `ConfigHistoryPanel`'s `onRestored` (line ~252):

```tsx
                    onRestored={async () => setDraft(await client.getPipelineConfig(pk))}
```

with:

```tsx
                    onRestored={async () => resetDraft(await client.getPipelineConfig(pk))}
```

Add a keyboard shortcut effect, mirroring `AppBuilderPage.tsx`'s pattern exactly (Ctrl/Cmd+Z, Shift for redo) — place it near the other effects, before the early-return guards so hook ordering stays stable across renders:

```ts
  useEffect(() => {
    function onKeyDown(e: KeyboardEvent) {
      const target = document.activeElement;
      const isTextField =
        target instanceof HTMLInputElement ||
        target instanceof HTMLTextAreaElement ||
        (target instanceof HTMLElement && target.isContentEditable);
      if (isTextField) return;
      if (!(e.metaKey || e.ctrlKey) || e.key.toLowerCase() !== "z") return;
      e.preventDefault();
      if (e.shiftKey) redo();
      else undo();
    }
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [undo, redo]);
```

This effect must be declared before any early `return` in the component body (same constraint as the other `useEffect`/`useState` calls already there — React's rules of hooks forbid conditional hook calls).

Add undo/redo buttons in the canvas header, next to the title (`work` panel content, around line 185-189):

```tsx
              <div className="flex items-center justify-between border-b border-rule p-2">
                <h2 className="text-lg font-semibold text-ink">
                  {initialTitle ?? t("pipelineBuilder.defaultTitle")}
                </h2>
                <div className="flex items-center gap-1">
                  <Button size="sm" variant="outline" disabled={!canUndo} onClick={undo}>
                    {t("pipelineBuilder.undo")}
                  </Button>
                  <Button size="sm" variant="outline" disabled={!canRedo} onClick={redo}>
                    {t("pipelineBuilder.redo")}
                  </Button>
                </div>
              </div>
```

(This replaces the existing `<div className="border-b border-rule p-2"><h2 ...>...</h2></div>` block — note the `flex items-center justify-between` added to the wrapping `div`.)

Add i18n keys, anchored after `"pipelineBuilder.executionLabel": "Exécution",`:

```ts
  "pipelineBuilder.undo": "Annuler",
  "pipelineBuilder.redo": "Rétablir",
```

- [ ] **Step 6: Test — undo/redo work end to end on the pipeline builder**

Add to `shell/src/pages/PipelineBuilderPage.test.tsx`:

```tsx
test("unsaved mode: Annuler reverts the last palette-added node", async () => {
  renderPage(null);
  await waitFor(() => expect(screen.getByText("reader.collection")).toBeInTheDocument());
  await userEvent.click(screen.getByRole("button", { name: "reader.collection" }));
  await waitFor(() => expect(screen.getAllByText("reader.collection").length).toBeGreaterThan(1));
  expect(screen.getByRole("button", { name: "Annuler" })).toBeEnabled();
  await userEvent.click(screen.getByRole("button", { name: "Annuler" }));
  await waitFor(() => expect(screen.getAllByText("reader.collection")).toHaveLength(1));
  expect(screen.getByRole("button", { name: "Rétablir" })).toBeEnabled();
});

test("unsaved mode: Annuler and Rétablir start disabled", async () => {
  renderPage(null);
  await waitFor(() => expect(screen.getByText("reader.collection")).toBeInTheDocument());
  expect(screen.getByRole("button", { name: "Annuler" })).toBeDisabled();
  expect(screen.getByRole("button", { name: "Rétablir" })).toBeDisabled();
});
```

`useUndoableDraft`'s 400ms coalescing window (`COALESCE_WINDOW_MS`) means `canUndo` only flips `true` after that delay elapses following a `setDraft` call — but the palette-click path in this test goes through `onAddViaPalette` → `onDropOnCanvas` → `setNodes` → `setDraft`, and this test's own `waitFor` polling (default interval ~50ms, default timeout 1000ms+) comfortably outlasts 400ms, so no `vi.advanceTimersByTime` is needed here (unlike `useUndoableDraft.test.tsx`, this file does not use fake timers).

- [ ] **Step 7: Run the tests**

```bash
cd shell && npx vitest run src/pages/PipelineBuilderPage.test.tsx
```
Expected: PASS (all tests, old and new — in particular, the "unsaved mode: Enregistrer is disabled on an empty graph" test must still pass now that `draft` starts as `null` for one tick before `EMPTY_PAYLOAD` is seeded).

- [ ] **Step 8: Run the full shell suite and commit**

```bash
cd shell && npm run test && npx tsc --noEmit
```
Expected: PASS.

```bash
git add shell/src/builder/useUndoableDraft.ts shell/src/builder/useUndoableDraft.test.tsx shell/src/pages/AppBuilderPage.tsx shell/src/pages/PipelineBuilderPage.tsx shell/src/pages/PipelineBuilderPage.test.tsx shell/src/i18n/catalog.fr.ts
git commit -m "feat(shell): generalize useUndoableDraft and wire undo/redo into the pipeline builder"
```

---

### Task 7: Bouton de suppression visible sur un nœud

**Files:**
- Modify: `shell/src/builder/pipeline/PipelineCanvas.tsx`
- Modify: `shell/src/i18n/catalog.fr.ts`
- Test: `shell/src/builder/pipeline/PipelineCanvas.test.tsx`

**Interfaces:**
- `CanvasNodeData` gains `onDelete: (nodeId: string) => void` (passed via `data`, same pattern as the existing `nodeStat`/`errorCount` fields from Task 1).

- [ ] **Step 1: Write the failing test**

```tsx
test("a visible delete button on a node removes it via onNodesChange", () => {
  const onNodesChange = vi.fn();
  render(
    <PipelineCanvas
      nodes={NODES}
      edges={EDGES}
      selectedNodeId={null}
      onSelectNode={vi.fn()}
      onNodesChange={onNodesChange}
      onEdgesChange={vi.fn()}
      onInsertOnEdge={vi.fn()}
      opsCatalog={{}}
    />,
  );
  fireEvent.click(screen.getByRole("button", { name: "Supprimer Villes" }));
  expect(onNodesChange).toHaveBeenCalledWith(NODES.filter((n) => n.id !== "r1"));
});
```

- [ ] **Step 2: Run it to verify it fails**

```bash
cd shell && npx vitest run src/builder/pipeline/PipelineCanvas.test.tsx -t "visible delete button"
```
Expected: FAIL — no such button exists yet.

- [ ] **Step 3: Add the button**

In `CanvasNodeData` (Task 1 already added `errorCount`), add:

```ts
type CanvasNodeData = PipelineNode & {
  acceptsSecondaryInput: boolean;
  nodeStat?: PipelineNodeStat;
  isNext: boolean;
  errorCount: number;
  onDelete: (nodeId: string) => void;
};
```

In `PipelineNodeBox`, add the button (placed so it doesn't overlap the existing top-right/top-left badges — bottom-right corner):

```tsx
      <button
        type="button"
        aria-label={t("pipelineCanvas.deleteNodeAria", { title: node.title ?? node.op })}
        className="absolute -bottom-2 -right-2 flex h-4 w-4 items-center justify-center rounded-full border border-rule bg-surface text-[10px] leading-none text-ink-2 hover:bg-sunken hover:text-danger"
        onClick={(e) => {
          e.stopPropagation();
          node.onDelete(node.id);
        }}
      >
        ×
      </button>
```

`e.stopPropagation()` matters: without it, the click would also bubble into React Flow's own node-click/selection handling, selecting the node an instant before it's removed — harmless but wasteful and liable to trigger a stray `onSelectNode` call after the node no longer exists.

Update `toFlowNode` to accept and forward `onDelete`:

```ts
function toFlowNode(
  n: PipelineNode,
  selected: boolean,
  extra: {
    acceptsSecondaryInput: boolean;
    nodeStat?: PipelineNodeStat;
    isNext: boolean;
    errorCount: number;
    onDelete: (nodeId: string) => void;
  },
): Node {
```

In `PipelineCanvasInner`, add a `deleteNode` callback and pass it through:

```ts
  const deleteNode = useCallback(
    (nodeId: string) => {
      onNodesChange(nodes.filter((n) => n.id !== nodeId));
      onEdgesChange(edges.filter((e) => e.from !== nodeId && e.to !== nodeId));
    },
    [nodes, edges, onNodesChange, onEdgesChange],
  );
```

and in the `<ReactFlow nodes={...}>` mapping:

```tsx
        nodes={nodes.map((n) =>
          toFlowNode(n, n.id === selectedNodeId, {
            acceptsSecondaryInput: opsCatalog[n.op]?.acceptsSecondaryInput ?? false,
            nodeStat: nodeStats?.[n.id],
            isNext: n.id === nextNodeId,
            errorCount: nodeErrors?.[n.id]?.length ?? 0,
            onDelete: deleteNode,
          }),
        )}
```

Add the i18n key, anchored after `"pipelineCanvas.nodeErrorAria": "{count} erreur(s) sur ce nœud",`:

```ts
  "pipelineCanvas.deleteNodeAria": "Supprimer {title}",
```

- [ ] **Step 4: Run the test to verify it passes, then run the full file**

```bash
cd shell && npx vitest run src/builder/pipeline/PipelineCanvas.test.tsx
```
Expected: PASS (all tests). Note the test asserts `onNodesChange` was called but not `onEdgesChange` — `NODES`/`EDGES` in this file has exactly one edge `r1->w1`, so deleting `r1` also fires `onEdgesChange([])`; the test as written only checks the `onNodesChange` call, which is sufficient to prove the button works — no change needed to the assertion.

- [ ] **Step 5: Commit**

```bash
git add shell/src/builder/pipeline/PipelineCanvas.tsx shell/src/builder/pipeline/PipelineCanvas.test.tsx shell/src/i18n/catalog.fr.ts
git commit -m "feat(shell): add a visible delete button on pipeline canvas nodes"
```

---

### Task 8: Recherche dans la palette + ajout au clavier depuis le canvas

**Files:**
- Modify: `shell/src/builder/pipeline/PipelinePalette.tsx`
- Modify: `shell/src/pages/PipelineBuilderPage.tsx`
- Modify: `shell/src/i18n/catalog.fr.ts`
- Test: `shell/src/builder/pipeline/PipelinePalette.test.tsx`
- Test: `shell/src/pages/PipelineBuilderPage.test.tsx`

**Interfaces:**
- Produces: `PipelinePalette` gains a text `Input` filtering its list; exposes `id="pipeline-palette-search"` on that input so `PipelineBuilderPage.tsx` can focus it programmatically on `/`.

- [ ] **Step 1: Write the failing test for the search filter**

Add to `shell/src/builder/pipeline/PipelinePalette.test.tsx` (read the file first to match its existing `usePipelineOps` mock pattern before writing this):

```tsx
test("typing in the search field filters the op list by id", async () => {
  render(<PipelinePalette onAdd={vi.fn()} />);
  await waitFor(() => expect(screen.getByText("reader.collection")).toBeInTheDocument());
  await userEvent.type(screen.getByRole("searchbox", { name: "Rechercher une opération" }), "filter");
  expect(screen.getByText("transform.filter")).toBeInTheDocument();
  expect(screen.queryByText("reader.collection")).not.toBeInTheDocument();
});
```

- [ ] **Step 2: Run it to verify it fails**

```bash
cd shell && npx vitest run src/builder/pipeline/PipelinePalette.test.tsx -t "filters the op list"
```
Expected: FAIL — no search field exists.

- [ ] **Step 3: Add the search input and filtering**

Modify `shell/src/builder/pipeline/PipelinePalette.tsx`:

```tsx
// SPDX-License-Identifier: Apache-2.0
import { useState } from "react";
import { usePipelineOps } from "../../api/hooks";
import type { PipelineNodeKind } from "../../api/types";
import { Input } from "../../ui/kit/Input";
import { t } from "../../i18n";

export const PIPELINE_OP_DND_TYPE = "application/x-geostudio-pipeline-op";
export const PIPELINE_PALETTE_SEARCH_ID = "pipeline-palette-search";

const SECTION_LABEL: Record<PipelineNodeKind, string> = {
  reader: t("pipelinePalette.sectionSources"),
  transform: t("pipelinePalette.sectionTransforms"),
  writer: t("pipelinePalette.sectionWriters"),
};

export function PipelinePalette({ onAdd }: { onAdd?: (op: string) => void }) {
  const opsQuery = usePipelineOps();
  const catalog = opsQuery.data ?? {};
  const [query, setQuery] = useState("");
  const normalizedQuery = query.trim().toLowerCase();
  const byKind: Record<PipelineNodeKind, string[]> = { reader: [], transform: [], writer: [] };
  for (const [op, entry] of Object.entries(catalog)) {
    if (normalizedQuery && !op.toLowerCase().includes(normalizedQuery)) continue;
    byKind[entry.kind].push(op);
  }

  return (
    <div className="flex flex-col gap-3 p-2 text-xs">
      <Input
        id={PIPELINE_PALETTE_SEARCH_ID}
        role="searchbox"
        aria-label={t("pipelinePalette.searchAria")}
        placeholder={t("pipelinePalette.searchPlaceholder")}
        value={query}
        onChange={(e) => setQuery(e.target.value)}
      />
      {(["reader", "transform", "writer"] as const).map((kind) => (
        <div key={kind}>
          <h3 className="mb-1 font-semibold text-ink-2">{SECTION_LABEL[kind]}</h3>
          <ul className="flex flex-col gap-1">
            {byKind[kind].map((op) => (
              <li key={op}>
                <button
                  type="button"
                  draggable
                  onDragStart={(e) => {
                    e.dataTransfer.setData(PIPELINE_OP_DND_TYPE, op);
                    e.dataTransfer.effectAllowed = "move";
                  }}
                  onClick={() => onAdd?.(op)}
                  title={catalog[op]?.paramsSchema.description}
                  className="w-full cursor-grab rounded border border-rule bg-surface px-2 py-1 text-left text-ink hover:bg-sunken"
                >
                  {op}
                </button>
              </li>
            ))}
          </ul>
        </div>
      ))}
    </div>
  );
}
```

Add i18n keys, anchored after `"pipelinePalette.sectionWriters": "Écritures",`:

```ts
  "pipelinePalette.searchAria": "Rechercher une opération",
  "pipelinePalette.searchPlaceholder": "Rechercher…",
```

- [ ] **Step 4: Run the palette test**

```bash
cd shell && npx vitest run src/builder/pipeline/PipelinePalette.test.tsx
```
Expected: PASS (all tests, old and new — verify no pre-existing test asserted the exact DOM structure of the palette's first child, which has now shifted down by one element).

- [ ] **Step 5: Write the failing test for the `/` keyboard shortcut**

Add to `shell/src/pages/PipelineBuilderPage.test.tsx`:

```tsx
test("unsaved mode: pressing / focuses the palette search field", async () => {
  renderPage(null);
  await waitFor(() => expect(screen.getByText("reader.collection")).toBeInTheDocument());
  await userEvent.keyboard("/");
  expect(screen.getByRole("searchbox", { name: "Rechercher une opération" })).toHaveFocus();
});

test("unsaved mode: pressing / while typing in a text field does not steal focus", async () => {
  renderPage(null);
  await waitFor(() => expect(screen.getByText("reader.collection")).toBeInTheDocument());
  await userEvent.click(screen.getByRole("searchbox", { name: "Rechercher une opération" }));
  await userEvent.type(
    screen.getByRole("searchbox", { name: "Rechercher une opération" }),
    "a/b",
  );
  expect(screen.getByRole("searchbox", { name: "Rechercher une opération" })).toHaveValue("a/b");
});
```

- [ ] **Step 6: Run these 2 tests to verify the first fails**

```bash
cd shell && npx vitest run src/pages/PipelineBuilderPage.test.tsx -t "pressing /"
```
Expected: the first FAILS (nothing listens for `/` yet), the second PASSES trivially (typing in a focused field already works without any new code — it exists only to pin down the "don't hijack `/` while already typing" requirement once Step 7 is applied, so re-run it after Step 7 too).

- [ ] **Step 7: Add the `/` shortcut**

In `shell/src/pages/PipelineBuilderPage.tsx`, add this effect near the undo/redo keyboard effect from Task 6 (both are keyboard-shortcut effects for this page, keep them adjacent):

```ts
  useEffect(() => {
    function onKeyDown(e: KeyboardEvent) {
      if (e.key !== "/") return;
      const target = document.activeElement;
      const isTextField =
        target instanceof HTMLInputElement ||
        target instanceof HTMLTextAreaElement ||
        (target instanceof HTMLElement && target.isContentEditable);
      if (isTextField) return;
      e.preventDefault();
      document.getElementById(PIPELINE_PALETTE_SEARCH_ID)?.focus();
    }
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, []);
```

Import `PIPELINE_PALETTE_SEARCH_ID` alongside the existing `PipelinePalette` import:

```ts
import { PipelinePalette, PIPELINE_OP_DND_TYPE, PIPELINE_PALETTE_SEARCH_ID } from "../builder/pipeline/PipelinePalette";
```

- [ ] **Step 8: Run the tests**

```bash
cd shell && npx vitest run src/pages/PipelineBuilderPage.test.tsx
```
Expected: PASS (all tests, including both new ones).

- [ ] **Step 9: Run the full shell suite and commit**

```bash
cd shell && npm run test
```
Expected: PASS.

```bash
git add shell/src/builder/pipeline/PipelinePalette.tsx shell/src/builder/pipeline/PipelinePalette.test.tsx shell/src/pages/PipelineBuilderPage.tsx shell/src/pages/PipelineBuilderPage.test.tsx shell/src/i18n/catalog.fr.ts
git commit -m "feat(shell): searchable pipeline palette with a / keyboard shortcut"
```

---

### Task 9: Connexion d'arêtes accessible au clavier/à la souris sans drag

**Files:**
- Modify: `shell/src/builder/pipeline/PipelineCanvas.tsx`
- Modify: `shell/src/i18n/catalog.fr.ts`
- Test: `shell/src/builder/pipeline/PipelineCanvas.test.tsx`

**Interfaces:**
- `CanvasNodeData` gains `onStartConnect: (nodeId: string) => void` and `isConnectingSource: boolean`.

- [ ] **Step 1: Write the failing test**

```tsx
test("clicking the connect affordance on a node, then clicking another node, creates a primary edge between them", () => {
  const onEdgesChange = vi.fn();
  const nodes: PipelineNode[] = [
    { id: "r1", kind: "reader", op: "reader.collection", x: 0, y: 0, params: {}, title: "R" },
    { id: "t1", kind: "transform", op: "transform.filter", x: 300, y: 0, params: {}, title: "T" },
  ];
  render(
    <PipelineCanvas
      nodes={nodes}
      edges={[]}
      selectedNodeId={null}
      onSelectNode={vi.fn()}
      onNodesChange={vi.fn()}
      onEdgesChange={onEdgesChange}
      onInsertOnEdge={vi.fn()}
      opsCatalog={{}}
    />,
  );
  fireEvent.click(screen.getByRole("button", { name: "Connecter depuis R" }));
  fireEvent.click(screen.getByText("T"));
  expect(onEdgesChange).toHaveBeenCalledWith([
    expect.objectContaining({ from: "r1", to: "t1", id: expect.any(String) }),
  ]);
});

test("pressing Escape cancels an in-progress connection", () => {
  const onEdgesChange = vi.fn();
  const nodes: PipelineNode[] = [
    { id: "r1", kind: "reader", op: "reader.collection", x: 0, y: 0, params: {}, title: "R" },
    { id: "t1", kind: "transform", op: "transform.filter", x: 300, y: 0, params: {}, title: "T" },
  ];
  render(
    <PipelineCanvas
      nodes={nodes}
      edges={[]}
      selectedNodeId={null}
      onSelectNode={vi.fn()}
      onNodesChange={vi.fn()}
      onEdgesChange={onEdgesChange}
      onInsertOnEdge={vi.fn()}
      opsCatalog={{}}
    />,
  );
  fireEvent.click(screen.getByRole("button", { name: "Connecter depuis R" }));
  fireEvent.keyDown(window, { key: "Escape" });
  fireEvent.click(screen.getByText("T"));
  expect(onEdgesChange).not.toHaveBeenCalled();
});
```

- [ ] **Step 2: Run them to verify they fail**

```bash
cd shell && npx vitest run src/builder/pipeline/PipelineCanvas.test.tsx -t "connect affordance"
```
Expected: FAIL — no "Connecter depuis R" button exists.

- [ ] **Step 3: Add the connect affordance and connect-mode state**

Extend `CanvasNodeData`:

```ts
type CanvasNodeData = PipelineNode & {
  acceptsSecondaryInput: boolean;
  nodeStat?: PipelineNodeStat;
  isNext: boolean;
  errorCount: number;
  onDelete: (nodeId: string) => void;
  onStartConnect: (nodeId: string) => void;
  isConnectingSource: boolean;
};
```

In `PipelineNodeBox`, apply a ring when `isConnectingSource` and add the trigger button (placed bottom-left, the delete button from Task 7 already occupies bottom-right):

```tsx
    <div
      className={`relative rounded-md border-2 px-3 py-2 text-xs ${KIND_COLOR[node.kind]} ${selected ? "ring-2 ring-accent" : ""} ${node.errorCount > 0 ? "border-danger" : ""} ${node.isConnectingSource ? "ring-2 ring-accent" : ""}`}
    >
```

```tsx
      <button
        type="button"
        aria-label={t("pipelineCanvas.startConnectAria", { title: node.title ?? node.op })}
        aria-pressed={node.isConnectingSource}
        className="absolute -bottom-2 -left-2 flex h-4 w-4 items-center justify-center rounded-full border border-rule bg-surface text-[10px] leading-none text-ink-2 hover:bg-sunken"
        onClick={(e) => {
          e.stopPropagation();
          node.onStartConnect(node.id);
        }}
      >
        ↝
      </button>
```

In `PipelineCanvasInner`, add the connect-mode state, completion logic, and Escape handling:

```ts
  const [connectingFromId, setConnectingFromId] = useState<string | null>(null);

  const completeConnection = useCallback(
    (targetId: string) => {
      if (!connectingFromId) return;
      setConnectingFromId(null);
      if (hasIncomingEdge(edges, targetId)) return;
      if (wouldCreateCycle(nodes, edges, { from: connectingFromId, to: targetId })) return;
      onEdgesChange([...edges, { id: genEdgeId(), from: connectingFromId, to: targetId }]);
    },
    [connectingFromId, nodes, edges, onEdgesChange],
  );

  useEffect(() => {
    if (!connectingFromId) return;
    function onKeyDown(e: KeyboardEvent) {
      if (e.key === "Escape") setConnectingFromId(null);
    }
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [connectingFromId]);
```

Import `useEffect` in this file's React import (currently `import { useCallback, useState } from "react";` — add `useEffect`).

Pass `onNodeClick` to `<ReactFlow>` and update the node-mapping to supply `onStartConnect`/`isConnectingSource`:

```tsx
        nodes={nodes.map((n) =>
          toFlowNode(n, n.id === selectedNodeId, {
            acceptsSecondaryInput: opsCatalog[n.op]?.acceptsSecondaryInput ?? false,
            nodeStat: nodeStats?.[n.id],
            isNext: n.id === nextNodeId,
            errorCount: nodeErrors?.[n.id]?.length ?? 0,
            onDelete: deleteNode,
            onStartConnect: (id) => setConnectingFromId(id),
            isConnectingSource: n.id === connectingFromId,
          }),
        )}
        edges={edges.map(toFlowEdge)}
        nodeTypes={nodeTypes}
        edgeTypes={edgeTypes}
        onConnect={onConnect}
        onNodesChange={handleNodesChange}
        onEdgesChange={handleEdgesChange}
        onNodeClick={(_, flowNode) => {
          if (connectingFromId && flowNode.id !== connectingFromId) completeConnection(flowNode.id);
        }}
        onPaneClick={() => onSelectNode(null)}
        deleteKeyCode={["Backspace", "Delete"]}
```

Update `toFlowNode`'s `extra` parameter type to include the 2 new fields (same treatment as Task 7's `onDelete`):

```ts
function toFlowNode(
  n: PipelineNode,
  selected: boolean,
  extra: {
    acceptsSecondaryInput: boolean;
    nodeStat?: PipelineNodeStat;
    isNext: boolean;
    errorCount: number;
    onDelete: (nodeId: string) => void;
    onStartConnect: (nodeId: string) => void;
    isConnectingSource: boolean;
  },
): Node {
```

Add the i18n key, anchored after `"pipelineCanvas.deleteNodeAria": "Supprimer {title}",`:

```ts
  "pipelineCanvas.startConnectAria": "Connecter depuis {title}",
```

- [ ] **Step 4: Run the tests**

```bash
cd shell && npx vitest run src/builder/pipeline/PipelineCanvas.test.tsx
```
Expected: PASS (all tests, old and new). If `onNodeClick` also fires for a click that already goes through the existing `handleNodesChange`'s `select` branch (both fire on the same underlying DOM click), verify the pre-existing test `"clicking a node calls onSelectNode with its id"` still passes unmodified — `onNodeClick`'s body only acts `if (connectingFromId ...)`, a no-op when not connecting, so it must not interfere.

- [ ] **Step 5: Commit**

```bash
git add shell/src/builder/pipeline/PipelineCanvas.tsx shell/src/builder/pipeline/PipelineCanvas.test.tsx shell/src/i18n/catalog.fr.ts
git commit -m "feat(shell): keyboard/click-only edge connection on the pipeline canvas"
```

---

### Task 10: Zones annotées sur le canvas (bookmarks), persistées

**Files:**
- Modify: `core/app/configs/schemas.py`
- Test: `core/tests/test_pipeline_config_validation.py`
- Modify: `shell/src/api/types.ts`
- Modify: `shell/src/builder/pipeline/graphOps.ts`
- Modify: `shell/src/builder/pipeline/PipelineCanvas.tsx`
- Modify: `shell/src/pages/PipelineBuilderPage.tsx`
- Modify: `shell/src/i18n/catalog.fr.ts`
- Test: `shell/src/builder/pipeline/graphOps.test.ts`
- Test: `shell/src/builder/pipeline/PipelineCanvas.test.tsx`
- Test: `shell/src/pages/PipelineBuilderPage.test.tsx`

**Interfaces:**
- Produces (cœur): `PipelinePayload.notes: list[PipelineCanvasNote]` (nouveau champ optionnel, défaut `[]`) — pas de migration (blob JSON).
- Produces (shell): `PipelineCanvasNote` type ; `PipelineCanvas` gagne les props `notes`/`onNotesChange`.

#### Partie cœur

- [ ] **Step 1: Write the failing backend test**

Add to `core/tests/test_pipeline_config_validation.py`:

```python
def test_pipeline_payload_round_trips_canvas_notes(env):
    body = _linear_pipeline()
    body["config"]["pipeline"]["notes"] = [
        {"id": "note-1", "label": "Étape de nettoyage", "x": 10, "y": 20, "width": 200, "height": 120}
    ]
    response = env.post("/v1/configs", json=body)
    assert response.status_code == 201
    item_id = response.json()["itemId"]
    fetched = env.get(f"/v1/configs/by-item/{item_id}")
    assert fetched.json()["config"]["pipeline"]["notes"] == [
        {"id": "note-1", "label": "Étape de nettoyage", "x": 10, "y": 20, "width": 200, "height": 120}
    ]


def test_pipeline_payload_defaults_notes_to_empty_list(env):
    response = env.post("/v1/configs", json=_linear_pipeline())
    assert response.status_code == 201
    item_id = response.json()["itemId"]
    fetched = env.get(f"/v1/configs/by-item/{item_id}")
    assert fetched.json()["config"]["pipeline"]["notes"] == []
```

- [ ] **Step 2: Run them to verify they fail**

```bash
cd core && uv run pytest tests/test_pipeline_config_validation.py -k canvas_notes -v
```
Expected: FAIL — `notes` is an unknown field, silently dropped by Pydantic's default `extra="ignore"` behavior (round-trips as absent, not as the posted value).

- [ ] **Step 3: Add `PipelineCanvasNote` and the `notes` field**

In `core/app/configs/schemas.py`, add a new model right after `PipelineEdge` (before `PipelineRefreshPolicy`):

```python
class PipelineCanvasNote(BaseModel):
    id: str
    label: str
    x: int = 0
    y: int = 0
    width: int = 200
    height: int = 120
```

Modify `PipelinePayload`:

```python
class PipelinePayload(BaseModel):
    nodes: list[PipelineNode] = Field(default_factory=list)
    edges: list[PipelineEdge] = Field(default_factory=list)
    refreshPolicy: PipelineRefreshPolicy | None = None
    notes: list[PipelineCanvasNote] = Field(default_factory=list)
```

- [ ] **Step 4: Run the backend tests**

```bash
cd core && uv run pytest tests/test_pipeline_config_validation.py -v
```
Expected: PASS (all tests in the file, including the 2 new ones — no other test in this file sets `notes`, so the default-`[]` behavior must not break any existing assertion that inspects the full posted/fetched payload shape; check `test_valid_linear_pipeline_saves` and neighbors do not assert an exact full-payload equality that would now be missing the `notes: []` key — if any does, add `"notes": []` to its expected dict).

- [ ] **Step 5: Regenerate OpenAPI + TS types**

```bash
cd core && PYTHONPATH=. \
  CORE_SECRETS_MASTER_KEY="AAECAwQFBgcICQoLDA0ODxAREhMUFRYXGBkaGxwdHh8=" \
  uv run python scripts/export_openapi.py openapi.json
cd ../shell && npm run gen:api-types
```

#### Partie shell

- [ ] **Step 6: Add `PipelineCanvasNote` to the hand-written types and to `PipelinePayload`**

In `shell/src/api/types.ts`, add near `PipelineRefreshPolicy` (line ~1018):

```ts
export type PipelineCanvasNote = {
  id: string;
  label: string;
  x: number;
  y: number;
  width: number;
  height: number;
};
```

Modify `PipelinePayload` (line ~1023):

```ts
export type PipelinePayload = {
  nodes: PipelineNode[];
  edges: PipelineEdge[];
  refreshPolicy?: PipelineRefreshPolicy | null;
  notes?: PipelineCanvasNote[];
};
```

- [ ] **Step 7: Add `genNoteId` to `graphOps.ts`**

In `shell/src/builder/pipeline/graphOps.ts`, add next to `genNodeId`/`genEdgeId`:

```ts
export function genNoteId(): string {
  return genId("note");
}
```

Add to `shell/src/builder/pipeline/graphOps.test.ts`:

```tsx
test("genNoteId produces ids prefixed note-", () => {
  expect(genNoteId()).toMatch(/^note-/);
});
```

Run: `cd shell && npx vitest run src/builder/pipeline/graphOps.test.ts` — expected PASS.

- [ ] **Step 8: Render notes as a second React Flow node type in `PipelineCanvas.tsx`**

Add `PipelineCanvasNote` to the type import list. Add a note-box component, placed after `PipelineNodeBox`:

```tsx
type CanvasNoteData = PipelineCanvasNote & {
  onLabelChange: (id: string, label: string) => void;
};

function CanvasNoteBox({ data }: NodeProps) {
  const note = data as unknown as CanvasNoteData;
  return (
    <div
      style={{ width: note.width, height: note.height }}
      className="rounded-md border-2 border-dashed border-rule bg-sunken/40 p-2"
    >
      <input
        aria-label={t("pipelineCanvas.noteLabelAria")}
        className="w-full bg-transparent text-xs font-medium text-ink-2 outline-none"
        value={note.label}
        onChange={(e) => note.onLabelChange(note.id, e.target.value)}
      />
    </div>
  );
}

function toFlowNoteNode(
  n: PipelineCanvasNote,
  onLabelChange: (id: string, label: string) => void,
): Node {
  return {
    id: n.id,
    position: { x: n.x, y: n.y },
    data: { ...n, onLabelChange } as unknown as Record<string, unknown>,
    type: "canvasNote",
    zIndex: -1,
  };
}
```

Extend `PipelineCanvasInner`'s props with `notes: PipelineCanvasNote[]` and `onNotesChange: (notes: PipelineCanvasNote[]) => void`.

Register the new node type:

```ts
  const nodeTypes = { pipelineNode: PipelineNodeBox, canvasNote: CanvasNoteBox };
```

Replace `handleNodesChange` to branch on note vs. graph node by id prefix:

```ts
  const handleNodesChange = useCallback(
    (changes: NodeChange[]) => {
      let nextNodes = nodes;
      let nextNotes = notes;
      for (const change of changes) {
        const isNote = change.id.startsWith("note-");
        if (change.type === "position" && change.position) {
          if (isNote) {
            nextNotes = nextNotes.map((n) =>
              n.id === change.id ? { ...n, x: change.position!.x, y: change.position!.y } : n,
            );
          } else {
            nextNodes = nextNodes.map((n) =>
              n.id === change.id ? { ...n, x: change.position!.x, y: change.position!.y } : n,
            );
          }
        }
        if (change.type === "remove") {
          if (isNote) nextNotes = nextNotes.filter((n) => n.id !== change.id);
          else nextNodes = nextNodes.filter((n) => n.id !== change.id);
        }
        if (change.type === "select" && change.selected && !isNote) {
          onSelectNode(change.id);
        }
      }
      if (nextNodes !== nodes) onNodesChange(nextNodes);
      if (nextNotes !== notes) onNotesChange(nextNotes);
    },
    [nodes, notes, onNodesChange, onNotesChange, onSelectNode],
  );
```

Merge notes into the `<ReactFlow nodes={...}>` array:

```tsx
        nodes={[
          ...nodes.map((n) =>
            toFlowNode(n, n.id === selectedNodeId, {
              acceptsSecondaryInput: opsCatalog[n.op]?.acceptsSecondaryInput ?? false,
              nodeStat: nodeStats?.[n.id],
              isNext: n.id === nextNodeId,
              errorCount: nodeErrors?.[n.id]?.length ?? 0,
              onDelete: deleteNode,
              onStartConnect: (id) => setConnectingFromId(id),
              isConnectingSource: n.id === connectingFromId,
            }),
          ),
          ...notes.map((n) =>
            toFlowNoteNode(n, (id, label) =>
              onNotesChange(notes.map((x) => (x.id === id ? { ...x, label } : x))),
            ),
          ),
        ]}
```

- [ ] **Step 9: Test — a note renders, is draggable-tracked, and doesn't select as the active node**

Add to `shell/src/builder/pipeline/PipelineCanvas.test.tsx`:

```tsx
test("renders a canvas note and editing its label calls onNotesChange", () => {
  const onNotesChange = vi.fn();
  render(
    <PipelineCanvas
      nodes={NODES}
      edges={EDGES}
      selectedNodeId={null}
      onSelectNode={vi.fn()}
      onNodesChange={vi.fn()}
      onEdgesChange={vi.fn()}
      onInsertOnEdge={vi.fn()}
      opsCatalog={{}}
      notes={[{ id: "note-1", label: "Étape 1", x: 0, y: 0, width: 200, height: 120 }]}
      onNotesChange={onNotesChange}
    />,
  );
  fireEvent.change(screen.getByLabelText("Étiquette de la zone"), {
    target: { value: "Étape 1 renommée" },
  });
  expect(onNotesChange).toHaveBeenCalledWith([
    { id: "note-1", label: "Étape 1 renommée", x: 0, y: 0, width: 200, height: 120 },
  ]);
});

test("clicking a note does not call onSelectNode", () => {
  const onSelectNode = vi.fn();
  render(
    <PipelineCanvas
      nodes={NODES}
      edges={EDGES}
      selectedNodeId={null}
      onSelectNode={onSelectNode}
      onNodesChange={vi.fn()}
      onEdgesChange={vi.fn()}
      onInsertOnEdge={vi.fn()}
      opsCatalog={{}}
      notes={[{ id: "note-1", label: "Étape 1", x: 0, y: 0, width: 200, height: 120 }]}
      onNotesChange={vi.fn()}
    />,
  );
  fireEvent.click(screen.getByLabelText("Étiquette de la zone"));
  expect(onSelectNode).not.toHaveBeenCalled();
});
```

Add the i18n key, anchored after `"pipelineCanvas.startConnectAria": "Connecter depuis {title}",`:

```ts
  "pipelineCanvas.noteLabelAria": "Étiquette de la zone",
```

Every other `<PipelineCanvas>` invocation in this test file now needs `notes={[]}` and `onNotesChange={vi.fn()}` added — these props are required (not optional) on `PipelineCanvasInner`. Add them to every existing test in this file that renders `<PipelineCanvas ...>` without these 2 props.

- [ ] **Step 10: Run the canvas tests**

```bash
cd shell && npx vitest run src/builder/pipeline/PipelineCanvas.test.tsx
```
Expected: PASS (all tests). If any pre-existing test fails with a TypeScript prop-shape error rather than a runtime failure, that confirms a missed `notes`/`onNotesChange` addition from Step 9's last instruction — add them.

- [ ] **Step 11: Wire notes into `PipelineBuilderPage.tsx`**

Add a `setNotes`/`onAddNote` pair alongside the existing mutators:

```ts
  function setNotes(notes: PipelineCanvasNote[]) {
    setDraft((d) => (d ? { ...d, notes } : d));
  }
  function onAddNote() {
    setNotes([
      ...(draft.notes ?? []),
      { id: genNoteId(), label: t("pipelineBuilder.newNoteLabel"), x: 40, y: 40, width: 200, height: 120 },
    ]);
  }
```

Import `PipelineCanvasNote` (type) and `genNoteId` alongside the existing imports from `graphOps`/`types`.

Add an "Ajouter une zone" button next to the undo/redo buttons added in Task 6:

```tsx
                <div className="flex items-center gap-1">
                  <Button size="sm" variant="outline" disabled={!canUndo} onClick={undo}>
                    {t("pipelineBuilder.undo")}
                  </Button>
                  <Button size="sm" variant="outline" disabled={!canRedo} onClick={redo}>
                    {t("pipelineBuilder.redo")}
                  </Button>
                  <Button size="sm" variant="outline" onClick={onAddNote}>
                    {t("pipelineBuilder.addNoteButton")}
                  </Button>
                </div>
```

Pass `notes`/`onNotesChange` to `<PipelineCanvas>`:

```tsx
                <PipelineCanvas
                  nodes={draft.nodes}
                  edges={draft.edges}
                  selectedNodeId={selectedNodeId}
                  onSelectNode={setSelectedNodeId}
                  onNodesChange={setNodes}
                  onEdgesChange={setEdges}
                  onInsertOnEdge={onInsertOnEdge}
                  opsCatalog={catalog}
                  nodeStats={latestRun?.nodeStats}
                  runStatus={latestRun?.status}
                  nodeErrors={validation.nodeErrors}
                  notes={draft.notes ?? []}
                  onNotesChange={setNotes}
                />
```

Add i18n keys, anchored after `"pipelineBuilder.redo": "Rétablir",`:

```ts
  "pipelineBuilder.addNoteButton": "Ajouter une zone",
  "pipelineBuilder.newNoteLabel": "Nouvelle zone",
```

- [ ] **Step 12: Test — adding a note from the builder page, and saving includes it**

Add to `shell/src/pages/PipelineBuilderPage.test.tsx`:

```tsx
test("unsaved mode: Ajouter une zone adds an editable note to the canvas", async () => {
  renderPage(null);
  await waitFor(() => expect(screen.getByText("reader.collection")).toBeInTheDocument());
  await userEvent.click(screen.getByRole("button", { name: "Ajouter une zone" }));
  expect(screen.getByLabelText("Étiquette de la zone")).toHaveValue("Nouvelle zone");
});

test("persisted mode: saving includes notes added on the canvas", async () => {
  const payload: PipelinePayload = {
    nodes: [
      { id: "r1", kind: "reader", op: "reader.collection", x: 0, y: 0, params: { collectionId: "villes" }, title: "Villes" },
      { id: "w1", kind: "writer", op: "writer.collection", x: 300, y: 0, params: { collectionId: "villes_propres" }, title: "Écriture" },
    ],
    edges: [{ id: "e1", from: "r1", to: "w1" }],
  };
  const savePipelineConfig = vi.fn().mockResolvedValue(undefined);
  renderPage("p-1", { getPipelineConfig: () => Promise.resolve(payload), savePipelineConfig });
  await waitFor(() => expect(screen.getByRole("button", { name: "Enregistrer" })).toBeEnabled());
  await userEvent.click(screen.getByRole("button", { name: "Ajouter une zone" }));
  await userEvent.click(screen.getByRole("button", { name: "Enregistrer" }));
  await waitFor(() =>
    expect(savePipelineConfig).toHaveBeenCalledWith(
      "p-1",
      expect.objectContaining({
        notes: [expect.objectContaining({ label: "Nouvelle zone" })],
      }),
    ),
  );
});
```

- [ ] **Step 13: Run the tests, then the full shell suite, then commit**

```bash
cd shell && npx vitest run src/pages/PipelineBuilderPage.test.tsx src/builder/pipeline/PipelineCanvas.test.tsx src/builder/pipeline/graphOps.test.ts
```
Expected: PASS.

```bash
cd shell && npm run test && npx tsc --noEmit
cd ../core && uv run pytest
```
Expected: PASS.

```bash
cd core && git add app/configs/schemas.py tests/test_pipeline_config_validation.py openapi.json
git commit -m "feat(core): persist named annotation zones on a pipeline's canvas"
cd ../shell && git add src/api/types.ts src/api/generated/core-schema.d.ts src/builder/pipeline/graphOps.ts src/builder/pipeline/graphOps.test.ts src/builder/pipeline/PipelineCanvas.tsx src/builder/pipeline/PipelineCanvas.test.tsx src/pages/PipelineBuilderPage.tsx src/pages/PipelineBuilderPage.test.tsx src/i18n/catalog.fr.ts
git commit -m "feat(shell): add and persist named annotation zones on the pipeline canvas"
```

---

### Task 11: Icônes par catégorie + description toujours visible dans la palette

**Files:**
- Modify: `shell/src/builder/pipeline/PipelinePalette.tsx`
- Test: `shell/src/builder/pipeline/PipelinePalette.test.tsx`

**Interfaces:** none new.

- [ ] **Step 1: Write the failing test**

```tsx
test("shows the operation's description as visible text, not only on hover", async () => {
  render(<PipelinePalette onAdd={vi.fn()} />);
  await waitFor(() => expect(screen.getByText("reader.collection")).toBeInTheDocument());
  // The mocked usePipelineOps catalog in this file's own setup must give
  // reader.collection a paramsSchema.description — read the file's existing
  // mock before writing this assertion and align the expected text with it,
  // or extend the mock with a description if it currently has none.
});
```

Before writing this test's body for real, read `shell/src/builder/pipeline/PipelinePalette.test.tsx`'s `usePipelineOps` mock (added by Task 8, or pre-existing) to know the exact op ids/descriptions available, then assert on one of them appearing as plain rendered text (e.g. `screen.getByText(<that description>)`), not merely as a `title` attribute.

- [ ] **Step 2: Run it to verify it fails**

```bash
cd shell && npx vitest run src/builder/pipeline/PipelinePalette.test.tsx -t "visible text"
```
Expected: FAIL — the description is currently only in the `title=` attribute (hover-only), never rendered as text.

- [ ] **Step 3: Add icons and visible descriptions**

Modify `shell/src/builder/pipeline/PipelinePalette.tsx`. Add the icon import:

```ts
import { Database, Save, Wand2 } from "lucide-react";
```

Add the icon map, next to `SECTION_LABEL`:

```ts
const KIND_ICON: Record<PipelineNodeKind, React.ComponentType<{ className?: string }>> = {
  reader: Database,
  transform: Wand2,
  writer: Save,
};
```

Replace the `<li>` body:

```tsx
            {byKind[kind].map((op) => {
              const Icon = KIND_ICON[kind];
              const description = catalog[op]?.paramsSchema.description;
              return (
                <li key={op}>
                  <button
                    type="button"
                    draggable
                    onDragStart={(e) => {
                      e.dataTransfer.setData(PIPELINE_OP_DND_TYPE, op);
                      e.dataTransfer.effectAllowed = "move";
                    }}
                    onClick={() => onAdd?.(op)}
                    className="flex w-full cursor-grab items-start gap-2 rounded border border-rule bg-surface px-2 py-1 text-left text-ink hover:bg-sunken"
                  >
                    <Icon className="mt-0.5 h-3.5 w-3.5 shrink-0 text-ink-2" />
                    <span className="flex flex-col">
                      <span>{op}</span>
                      {description && (
                        <span className="text-[10px] text-ink-2">{description}</span>
                      )}
                    </span>
                  </button>
                </li>
              );
            })}
```

The `title=` attribute is removed (superseded by the always-visible description).

- [ ] **Step 4: Run the tests**

```bash
cd shell && npx vitest run src/builder/pipeline/PipelinePalette.test.tsx
```
Expected: PASS (all tests, old and new). If any pre-existing test used `getByTitle(...)` to find an op button, it must be updated to `getByRole("button", { name: ... })` — the accessible name of the button is now the full text content (op id + description), so match on the op id substring via `getByRole("button", { name: /reader\.collection/ })` if an exact match breaks.

- [ ] **Step 5: Commit**

```bash
git add shell/src/builder/pipeline/PipelinePalette.tsx shell/src/builder/pipeline/PipelinePalette.test.tsx
git commit -m "feat(shell): icons and always-visible descriptions in the pipeline palette"
```

---

### Task 12: Opérations récemment utilisées dans la palette

**Files:**
- Create: `shell/src/builder/pipeline/useRecentPipelineOps.ts`
- Create: `shell/src/builder/pipeline/useRecentPipelineOps.test.ts`
- Modify: `shell/src/builder/pipeline/PipelinePalette.tsx`
- Modify: `shell/src/i18n/catalog.fr.ts`
- Test: `shell/src/builder/pipeline/PipelinePalette.test.tsx`

**Interfaces:**
- Produces: `useRecentPipelineOps(): { recent: string[]; recordUse: (op: string) => void }`.

- [ ] **Step 1: Write the failing test for the hook**

```ts
// SPDX-License-Identifier: Apache-2.0
import { act, renderHook } from "@testing-library/react";
import { beforeEach, expect, test } from "vitest";
import { useRecentPipelineOps } from "./useRecentPipelineOps";

beforeEach(() => localStorage.clear());

test("recordUse adds an op to the front of the recent list", () => {
  const { result } = renderHook(() => useRecentPipelineOps());
  act(() => result.current.recordUse("reader.collection"));
  expect(result.current.recent).toEqual(["reader.collection"]);
});

test("recordUse moves an already-recorded op to the front instead of duplicating it", () => {
  const { result } = renderHook(() => useRecentPipelineOps());
  act(() => result.current.recordUse("reader.collection"));
  act(() => result.current.recordUse("transform.filter"));
  act(() => result.current.recordUse("reader.collection"));
  expect(result.current.recent).toEqual(["reader.collection", "transform.filter"]);
});

test("keeps only the 5 most recently used ops", () => {
  const { result } = renderHook(() => useRecentPipelineOps());
  act(() => {
    for (const op of ["a", "b", "c", "d", "e", "f"]) result.current.recordUse(op);
  });
  expect(result.current.recent).toEqual(["f", "e", "d", "c", "b"]);
});

test("persists across hook instances via localStorage", () => {
  const first = renderHook(() => useRecentPipelineOps());
  act(() => first.result.current.recordUse("reader.collection"));
  const second = renderHook(() => useRecentPipelineOps());
  expect(second.result.current.recent).toEqual(["reader.collection"]);
});
```

- [ ] **Step 2: Run it to verify it fails**

```bash
cd shell && npx vitest run src/builder/pipeline/useRecentPipelineOps.test.ts
```
Expected: FAIL — the module doesn't exist yet.

- [ ] **Step 3: Implement the hook**

```ts
// SPDX-License-Identifier: Apache-2.0
import { useCallback, useState } from "react";

const STORAGE_KEY = "geostudio.pipeline.recentOps";
const MAX_RECENT = 5;

function readStored(): string[] {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return [];
    const parsed: unknown = JSON.parse(raw);
    return Array.isArray(parsed) ? parsed.filter((v): v is string => typeof v === "string") : [];
  } catch {
    return [];
  }
}

function writeStored(recent: string[]) {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(recent));
  } catch {
    // Quota exceeded or storage disabled (private browsing) — a convenience
    // feature, never worth surfacing an error for.
  }
}

export function useRecentPipelineOps(): { recent: string[]; recordUse: (op: string) => void } {
  const [recent, setRecent] = useState<string[]>(readStored);

  const recordUse = useCallback((op: string) => {
    setRecent((prev) => {
      const next = [op, ...prev.filter((o) => o !== op)].slice(0, MAX_RECENT);
      writeStored(next);
      return next;
    });
  }, []);

  return { recent, recordUse };
}
```

- [ ] **Step 4: Run the hook tests**

```bash
cd shell && npx vitest run src/builder/pipeline/useRecentPipelineOps.test.ts
```
Expected: PASS.

- [ ] **Step 5: Wire it into `PipelinePalette.tsx`**

Add the import and call:

```ts
import { useRecentPipelineOps } from "./useRecentPipelineOps";
```

```ts
  const { recent, recordUse } = useRecentPipelineOps();
```

Call `recordUse(op)` in both the drag start and the click handlers of the op button (added in Task 11):

```tsx
                    onDragStart={(e) => {
                      recordUse(op);
                      e.dataTransfer.setData(PIPELINE_OP_DND_TYPE, op);
                      e.dataTransfer.effectAllowed = "move";
                    }}
                    onClick={() => {
                      recordUse(op);
                      onAdd?.(op);
                    }}
```

Add a "Récemment utilisés" section above the 3 kind sections, only when non-empty and only listing ops still present in the catalog (an op removed from a later catalog version should silently disappear from this list rather than render a broken entry):

```tsx
      {recent.length > 0 && (
        <div>
          <h3 className="mb-1 font-semibold text-ink-2">{t("pipelinePalette.sectionRecent")}</h3>
          <ul className="flex flex-col gap-1">
            {recent
              .filter((op) => catalog[op])
              .map((op) => {
                const Icon = KIND_ICON[catalog[op].kind];
                const description = catalog[op].paramsSchema.description;
                return (
                  <li key={op}>
                    <button
                      type="button"
                      draggable
                      onDragStart={(e) => {
                        recordUse(op);
                        e.dataTransfer.setData(PIPELINE_OP_DND_TYPE, op);
                        e.dataTransfer.effectAllowed = "move";
                      }}
                      onClick={() => {
                        recordUse(op);
                        onAdd?.(op);
                      }}
                      className="flex w-full cursor-grab items-start gap-2 rounded border border-rule bg-surface px-2 py-1 text-left text-ink hover:bg-sunken"
                    >
                      <Icon className="mt-0.5 h-3.5 w-3.5 shrink-0 text-ink-2" />
                      <span className="flex flex-col">
                        <span>{op}</span>
                        {description && (
                          <span className="text-[10px] text-ink-2">{description}</span>
                        )}
                      </span>
                    </button>
                  </li>
                );
              })}
          </ul>
        </div>
      )}
```

This duplicates the button markup from Task 11's kind sections — acceptable here (2 call sites, each already small); if a 3rd render site of this button ever appears, extract a shared `OpButton` component at that point, not before (YAGNI).

Add the i18n key, anchored after `"pipelinePalette.sectionWriters": "Écritures",`:

```ts
  "pipelinePalette.sectionRecent": "Récemment utilisés",
```

- [ ] **Step 6: Test — the recent section appears after use and survives a re-render**

Add to `shell/src/builder/pipeline/PipelinePalette.test.tsx`:

```tsx
test("using an op via the palette adds it to a Récemment utilisés section", async () => {
  render(<PipelinePalette onAdd={vi.fn()} />);
  await waitFor(() => expect(screen.getByText("reader.collection")).toBeInTheDocument());
  expect(screen.queryByText("Récemment utilisés")).not.toBeInTheDocument();
  await userEvent.click(screen.getAllByRole("button", { name: /reader\.collection/ })[0]);
  expect(screen.getByText("Récemment utilisés")).toBeInTheDocument();
  expect(screen.getAllByText("reader.collection")).toHaveLength(2); // once in Sources, once in Récemment utilisés
});
```

Add `beforeEach(() => localStorage.clear());` at the top of this test file if not already present, so this test doesn't leak state into others via real `jsdom` `localStorage`.

- [ ] **Step 7: Run the tests, then the full shell suite, then commit**

```bash
cd shell && npx vitest run src/builder/pipeline/PipelinePalette.test.tsx src/builder/pipeline/useRecentPipelineOps.test.ts
cd shell && npm run test
```
Expected: PASS.

```bash
git add shell/src/builder/pipeline/useRecentPipelineOps.ts shell/src/builder/pipeline/useRecentPipelineOps.test.ts shell/src/builder/pipeline/PipelinePalette.tsx shell/src/builder/pipeline/PipelinePalette.test.tsx shell/src/i18n/catalog.fr.ts
git commit -m "feat(shell): recently-used operations section in the pipeline palette"
```

---

### Task 13: Regroupement requis/optionnel dans l'inspecteur de paramètres

**Files:**
- Modify: `shell/src/builder/pipeline/PipelineNodeInspector.tsx`
- Modify: `shell/src/i18n/catalog.fr.ts`
- Test: `shell/src/builder/pipeline/PipelineNodeInspector.test.tsx`

**Interfaces:** none new.

- [ ] **Step 1: Write the failing test**

Read `shell/src/builder/pipeline/PipelineNodeInspector.test.tsx` first to match its existing render helper before writing this. Add:

```tsx
test("groups fields into Paramètres requis and Paramètres optionnels sections", () => {
  render(
    <PipelineNodeInspector
      node={{ id: "n1", kind: "reader", op: "reader.collection", x: 0, y: 0, params: {}, title: "R" }}
      opEntry={{
        kind: "reader",
        paramsSchema: {
          properties: {
            collectionId: { type: "string" },
            limit: { type: "number" },
          },
          required: ["collectionId"],
        },
      }}
      errors={[]}
      onChange={vi.fn()}
    />,
  );
  const requiredHeading = screen.getByText("Paramètres requis");
  const optionalHeading = screen.getByText("Paramètres optionnels");
  expect(requiredHeading.compareDocumentPosition(screen.getByLabelText("collectionId"))).toBe(
    Node.DOCUMENT_POSITION_FOLLOWING,
  );
  expect(optionalHeading.compareDocumentPosition(screen.getByLabelText("limit"))).toBe(
    Node.DOCUMENT_POSITION_FOLLOWING,
  );
});

test("omits the optional section heading when every field is required", () => {
  render(
    <PipelineNodeInspector
      node={{ id: "n1", kind: "reader", op: "reader.collection", x: 0, y: 0, params: {}, title: "R" }}
      opEntry={{
        kind: "reader",
        paramsSchema: { properties: { collectionId: { type: "string" } }, required: ["collectionId"] },
      }}
      errors={[]}
      onChange={vi.fn()}
    />,
  );
  expect(screen.queryByText("Paramètres optionnels")).not.toBeInTheDocument();
});
```

- [ ] **Step 2: Run them to verify they fail**

```bash
cd shell && npx vitest run src/builder/pipeline/PipelineNodeInspector.test.tsx -t "groups fields"
```
Expected: FAIL — no such headings exist.

- [ ] **Step 3: Add the grouping**

In `shell/src/builder/pipeline/PipelineNodeInspector.tsx`, replace the return statement's field-rendering line:

```tsx
  return (
    <div className="flex flex-col gap-2 p-2">
      {Object.entries(opEntry.paramsSchema.properties).map(([name, prop]) =>
        renderField(name, prop),
      )}
      {errors.map((err) => (
        <p key={err} role="alert" className="text-xs text-danger">
          {err}
        </p>
      ))}
    </div>
  );
```

with:

```tsx
  const requiredNames = new Set(opEntry.paramsSchema.required ?? []);
  const entries = Object.entries(opEntry.paramsSchema.properties);
  const requiredEntries = entries.filter(([name]) => requiredNames.has(name));
  const optionalEntries = entries.filter(([name]) => !requiredNames.has(name));

  return (
    <div className="flex flex-col gap-2 p-2">
      {requiredEntries.length > 0 && (
        <div className="flex flex-col gap-2">
          {optionalEntries.length > 0 && (
            <h4 className="text-[10px] font-semibold uppercase text-ink-2">
              {t("pipelineNodeInspector.requiredSection")}
            </h4>
          )}
          {requiredEntries.map(([name, prop]) => renderField(name, prop))}
        </div>
      )}
      {optionalEntries.length > 0 && (
        <div className="flex flex-col gap-2">
          {requiredEntries.length > 0 && (
            <h4 className="text-[10px] font-semibold uppercase text-ink-2">
              {t("pipelineNodeInspector.optionalSection")}
            </h4>
          )}
          {optionalEntries.map(([name, prop]) => renderField(name, prop))}
        </div>
      )}
      {errors.map((err) => (
        <p key={err} role="alert" className="text-xs text-danger">
          {err}
        </p>
      ))}
    </div>
  );
```

Both headings are conditioned on the OTHER group being non-empty too — an op with only required (or only optional) fields shows no heading at all (a single, unlabeled section), matching the second test above. Add the `t` import for `i18n` — already imported (`../../i18n`, present at the top of the file already since `renderField`'s sibling functions don't use it yet, but `PipelineNodeInspector.tsx` doesn't currently import `t` at all: check the top of the file and add `import { t } from "../../i18n";` if absent).

Add i18n keys, anchored after `"pipelineBuilder.newNoteLabel": "Nouvelle zone",` (or the nearest existing pipeline* key if that one was not yet added by an earlier task in this plan when this task runs — anchor on whichever `"pipelineBuilder.*"` key is present):

```ts
  "pipelineNodeInspector.requiredSection": "Paramètres requis",
  "pipelineNodeInspector.optionalSection": "Paramètres optionnels",
```

- [ ] **Step 4: Run the tests**

```bash
cd shell && npx vitest run src/builder/pipeline/PipelineNodeInspector.test.tsx
```
Expected: PASS (all tests, old and new).

- [ ] **Step 5: Commit**

```bash
git add shell/src/builder/pipeline/PipelineNodeInspector.tsx shell/src/builder/pipeline/PipelineNodeInspector.test.tsx shell/src/i18n/catalog.fr.ts
git commit -m "feat(shell): group required and optional fields in the pipeline node inspector"
```

---

### Task 14: Erreurs de validation affichées sous le champ concerné

**Files:**
- Modify: `shell/src/builder/pipeline/validation.ts`
- Modify: `shell/src/builder/pipeline/PipelineNodeInspector.tsx`
- Test: `shell/src/builder/pipeline/validation.test.ts`
- Test: `shell/src/builder/pipeline/PipelineNodeInspector.test.tsx`

**Interfaces:**
- Produces: `fieldErrorsFor(field: string, errors: string[]): string[]` — new exported pure helper in `validation.ts`. `PipelineValidationResult`'s shape is unchanged (still `string[]` per node) to avoid touching its 3 existing consumers (`PipelineBuilderPage.tsx`, `PipelineCanvas.tsx`'s badge from Task 1, `PipelineNodeInspector.tsx`) — this task only adds a client-side matcher on top of the existing string format.

- [ ] **Step 1: Write the failing test for the helper**

Add to `shell/src/builder/pipeline/validation.test.ts`:

```ts
test("fieldErrorsFor returns only errors that start with '<field> '", () => {
  const errors = ["collectionId est requis.", "reader.collection : requiert une arête primaire entrante."];
  expect(fieldErrorsFor("collectionId", errors)).toEqual(["collectionId est requis."]);
  expect(fieldErrorsFor("other", errors)).toEqual([]);
});
```

Add `fieldErrorsFor` to this file's import from `./validation`.

- [ ] **Step 2: Run it to verify it fails**

```bash
cd shell && npx vitest run src/builder/pipeline/validation.test.ts -t "fieldErrorsFor"
```
Expected: FAIL — `fieldErrorsFor` is not exported.

- [ ] **Step 3: Add the helper**

In `shell/src/builder/pipeline/validation.ts`, add after `isPipelineValid`:

```ts
// Matches validateNodeParamsShape's message format ("${field} est requis.")
// by prefix — a pure convenience matcher, not a change to
// PipelineValidationResult's shape. An error that doesn't start with any
// known field name (a structural op-level error, e.g. "requiert une arête
// primaire entrante") never matches any field and keeps rendering in the
// node-level fallback list.
export function fieldErrorsFor(field: string, errors: string[]): string[] {
  return errors.filter((e) => e.startsWith(`${field} `));
}
```

- [ ] **Step 4: Run the validation tests**

```bash
cd shell && npx vitest run src/builder/pipeline/validation.test.ts
```
Expected: PASS (all tests, old and new).

- [ ] **Step 5: Write the failing test for inline rendering**

Add to `shell/src/builder/pipeline/PipelineNodeInspector.test.tsx`:

```tsx
test("a field-specific error renders under its own control, not only in the bottom list", () => {
  render(
    <PipelineNodeInspector
      node={{ id: "n1", kind: "reader", op: "reader.collection", x: 0, y: 0, params: {}, title: "R" }}
      opEntry={{
        kind: "reader",
        paramsSchema: { properties: { collectionId: { type: "string" } }, required: ["collectionId"] },
      }}
      errors={["collectionId est requis."]}
      onChange={vi.fn()}
    />,
  );
  const field = screen.getByLabelText("collectionId").closest("div")!;
  expect(within(field).getByText("collectionId est requis.")).toBeInTheDocument();
});

test("an unmatched, node-level error still renders in the bottom fallback list", () => {
  render(
    <PipelineNodeInspector
      node={{ id: "n1", kind: "transform", op: "transform.join", x: 0, y: 0, params: {}, title: "J" }}
      opEntry={{ kind: "transform", paramsSchema: { properties: {} }, acceptsSecondaryInput: true }}
      errors={["transform.join : requiert une arête primaire entrante."]}
      onChange={vi.fn()}
    />,
  );
  expect(
    screen.getByText("transform.join : requiert une arête primaire entrante."),
  ).toBeInTheDocument();
});
```

Add `within` to this test file's `@testing-library/react` import.

- [ ] **Step 6: Run them to verify the first fails**

```bash
cd shell && npx vitest run src/builder/pipeline/PipelineNodeInspector.test.tsx -t "under its own control"
```
Expected: FAIL — today every error in `errors` renders once, in the bottom list only.

- [ ] **Step 7: Render field-matched errors inline, and filter them out of the bottom list**

Modify `renderField` in `shell/src/builder/pipeline/PipelineNodeInspector.tsx`:

```tsx
  function renderField(name: string, prop: PipelineOpParamProperty) {
    const control = renderControl(name, prop);
    const fieldErrors = fieldErrorsFor(name, errors);
    return (
      <div key={name} className="flex flex-col gap-1">
        {control}
        {prop.description && <p className="text-xs text-ink-2">{prop.description}</p>}
        {fieldErrors.map((err) => (
          <p key={err} role="alert" className="text-xs text-danger">
            {err}
          </p>
        ))}
      </div>
    );
  }
```

Add the import:

```ts
import { fieldErrorsFor } from "./validation";
```

Filter the bottom-of-form error list (Task 13 already restructured this return statement — apply this change on top of it) to exclude anything matched to a known field:

```tsx
  const allFieldNames = Object.keys(opEntry.paramsSchema.properties);
  const unmatchedErrors = errors.filter(
    (e) => !allFieldNames.some((name) => fieldErrorsFor(name, [e]).length > 0),
  );
```

and replace the final `{errors.map((err) => ...)}` block with `{unmatchedErrors.map((err) => ...)}` (same JSX body, different source array).

- [ ] **Step 8: Run the tests**

```bash
cd shell && npx vitest run src/builder/pipeline/PipelineNodeInspector.test.tsx
```
Expected: PASS (all tests, old and new — in particular, re-check the pre-existing tests that assert on `errors` rendering at the bottom still find their text, since a matched field error would now have moved next to its control instead).

- [ ] **Step 9: Run the full shell suite and commit**

```bash
cd shell && npm run test
```
Expected: PASS.

```bash
git add shell/src/builder/pipeline/validation.ts shell/src/builder/pipeline/validation.test.ts shell/src/builder/pipeline/PipelineNodeInspector.tsx shell/src/builder/pipeline/PipelineNodeInspector.test.tsx
git commit -m "feat(shell): show pipeline field validation errors under their own control"
```

---

### Task 15: Couleur distincte par type de géométrie + légende minimale

**Files:**
- Modify: `shell/src/builder/pipeline/PipelinePreviewMap.tsx`
- Modify: `shell/src/i18n/catalog.fr.ts`
- Test: `shell/src/builder/pipeline/PipelinePreviewMap.test.tsx`

**Interfaces:** none new.

- [ ] **Step 1: Write the failing test**

```tsx
test("uses a distinct fill color for polygons, line color for lines, and circle color for points", () => {
  render(
    <PipelinePreviewMap
      rows={[{ id: 1, geometry: { type: "Point", coordinates: [1, 1] } }]}
    />,
  );
  const map = mapInstances[0];
  const fillLayer = map.getLayer("pipeline-preview-fill") as { paint: { "fill-color": string } };
  const lineLayer = map.getLayer("pipeline-preview-line") as { paint: { "line-color": string } };
  const circleLayer = map.getLayer("pipeline-preview-circle") as {
    paint: { "circle-color": string };
  };
  expect(fillLayer.paint["fill-color"]).not.toBe(lineLayer.paint["line-color"]);
  expect(lineLayer.paint["line-color"]).not.toBe(circleLayer.paint["circle-color"]);
});

test("renders a legend swatch only for geometry kinds actually present in rows", () => {
  render(<PipelinePreviewMap rows={[{ id: 1, geometry: { type: "Point", coordinates: [1, 1] } }]} />);
  expect(screen.getByText("Point")).toBeInTheDocument();
  expect(screen.queryByText("Polygone")).not.toBeInTheDocument();
  expect(screen.queryByText("Ligne")).not.toBeInTheDocument();
});
```

Add `import { render, screen } from "@testing-library/react";` — this file currently only imports `render` (verify before editing and add `screen` to the existing import if missing).

- [ ] **Step 2: Run them to verify they fail**

```bash
cd shell && npx vitest run src/builder/pipeline/PipelinePreviewMap.test.tsx -t "distinct fill color"
```
Expected: FAIL — all 3 layers currently paint `#2563eb`; no legend exists.

- [ ] **Step 3: Distinct colors + legend**

In `shell/src/builder/pipeline/PipelinePreviewMap.tsx`, change the 3 `paint` blocks inside the `map.on("load", ...)` handler:

```tsx
      map.addLayer({
        id: `${SOURCE_ID}-fill`,
        type: "fill",
        source: SOURCE_ID,
        filter: ["==", ["geometry-type"], "Polygon"],
        paint: { "fill-color": "#2563eb", "fill-opacity": 0.4 },
      });
      map.addLayer({
        id: `${SOURCE_ID}-line`,
        type: "line",
        source: SOURCE_ID,
        filter: ["==", ["geometry-type"], "LineString"],
        paint: { "line-color": "#16a34a", "line-width": 2 },
      });
      map.addLayer({
        id: `${SOURCE_ID}-circle`,
        type: "circle",
        source: SOURCE_ID,
        filter: ["==", ["geometry-type"], "Point"],
        paint: { "circle-color": "#dc2626", "circle-radius": 5 },
      });
```

Add a small helper (module scope, above the component) to know which kinds are present, and render a legend below the map container:

```ts
function presentGeometryKinds(rows: Record<string, unknown>[]): Set<"Point" | "LineString" | "Polygon"> {
  const kinds = new Set<"Point" | "LineString" | "Polygon">();
  for (const r of rows) {
    const type = (r.geometry as GeoJSON.Geometry | null | undefined)?.type;
    if (type === "Point" || type === "MultiPoint") kinds.add("Point");
    else if (type === "LineString" || type === "MultiLineString") kinds.add("LineString");
    else if (type === "Polygon" || type === "MultiPolygon") kinds.add("Polygon");
  }
  return kinds;
}

const LEGEND_ENTRIES: { kind: "Point" | "LineString" | "Polygon"; color: string; labelKey: MessageKey }[] = [
  { kind: "Polygon", color: "#2563eb", labelKey: "pipelinePreviewMap.legendPolygon" },
  { kind: "LineString", color: "#16a34a", labelKey: "pipelinePreviewMap.legendLine" },
  { kind: "Point", color: "#dc2626", labelKey: "pipelinePreviewMap.legendPoint" },
];
```

Import `MessageKey` and `t` (this file does not currently import `t` — check the top of the file and add `import { t } from "../../i18n";` and `import type { MessageKey } from "../../i18n";` if absent).

Change the component's return statement:

```tsx
  const kinds = presentGeometryKinds(rows);
  return (
    <div className="flex flex-col gap-1">
      <div ref={containerRef} data-testid="pipeline-preview-map" style={{ height: 300 }} />
      {kinds.size > 0 && (
        <div className="flex gap-3 text-[10px] text-ink-2">
          {LEGEND_ENTRIES.filter((e) => kinds.has(e.kind)).map((e) => (
            <span key={e.kind} className="flex items-center gap-1">
              <span
                className="h-2 w-2 rounded-full"
                style={{ backgroundColor: e.color }}
              />
              {t(e.labelKey)}
            </span>
          ))}
        </div>
      )}
    </div>
  );
```

Add i18n keys, anchored after `"pipelinePreview.stale": "Aperçu à régénérer (paramètres modifiés depuis le dernier calcul)",`:

```ts
  "pipelinePreviewMap.legendPolygon": "Polygone",
  "pipelinePreviewMap.legendLine": "Ligne",
  "pipelinePreviewMap.legendPoint": "Point",
```

- [ ] **Step 4: Run the tests**

```bash
cd shell && npx vitest run src/builder/pipeline/PipelinePreviewMap.test.tsx
```
Expected: PASS (all tests, old and new — `MockMaplibreMap.getLayer` already exists and returns the raw layer spec object passed to `addLayer`, so `layer.paint["fill-color"]` reads correctly in the test).

- [ ] **Step 5: Commit**

```bash
git add shell/src/builder/pipeline/PipelinePreviewMap.tsx shell/src/builder/pipeline/PipelinePreviewMap.test.tsx shell/src/i18n/catalog.fr.ts
git commit -m "feat(shell): distinct per-geometry colors and a legend in the pipeline preview map"
```

---

### Task 16: Sélection de feature partagée entre tableau et carte + panneau d'attributs

**Files:**
- Modify: `shell/src/builder/pipeline/PipelinePreviewMap.tsx`
- Modify: `shell/src/builder/pipeline/PipelinePreviewPanel.tsx`
- Modify: `shell/src/i18n/catalog.fr.ts`
- Test: `shell/src/builder/pipeline/PipelinePreviewMap.test.tsx`
- Test: `shell/src/builder/pipeline/PipelinePreviewPanel.test.tsx`

**Interfaces:**
- Produces: `PipelinePreviewMap` gains `selectedIndex?: number | null` and `onSelectIndex?: (index: number) => void`. Selection state (`selectedIndex`) lives in `PipelinePreviewPanel`, shared across the table/map toggle (Task 3 already made the map rebuild per `rows` change — this task adds a second effect reacting to `selectedIndex` alone, without rebuilding the whole map).

- [ ] **Step 1: Write the failing tests for the map side**

Add to `shell/src/builder/pipeline/PipelinePreviewMap.test.tsx`:

```tsx
test("clicking a rendered feature calls onSelectIndex with that feature's row index", () => {
  const onSelectIndex = vi.fn();
  render(
    <PipelinePreviewMap
      rows={[
        { id: 1, geometry: { type: "Point", coordinates: [1, 1] } },
        { id: 2, geometry: { type: "Point", coordinates: [2, 2] } },
      ]}
      onSelectIndex={onSelectIndex}
    />,
  );
  const map = mapInstances[0];
  map.fireOnLayer("click", "pipeline-preview-circle", {
    features: [{ properties: { __rowIndex: 1 } }],
  });
  expect(onSelectIndex).toHaveBeenCalledWith(1);
});

test("filters the selection outline layer to the selectedIndex", () => {
  render(
    <PipelinePreviewMap
      rows={[{ id: 1, geometry: { type: "Point", coordinates: [1, 1] } }]}
      selectedIndex={0}
    />,
  );
  const map = mapInstances[0];
  expect(map.getLayer("pipeline-preview-selected")).toBeDefined();
});
```

`MockMap.getLayer` needs no change (already returns whatever `addLayer` recorded); `fireOnLayer` already exists on `MockMap` — read it in `shell/src/test/MockMaplibreMap.ts` before writing this test if any signature detail is unclear.

- [ ] **Step 2: Run them to verify they fail**

```bash
cd shell && npx vitest run src/builder/pipeline/PipelinePreviewMap.test.tsx -t "onSelectIndex"
```
Expected: FAIL — no click handler, no `__rowIndex` property, no `pipeline-preview-selected` layer exist yet.

- [ ] **Step 3: Tag features with their row index, add click handlers and a selection outline layer**

In `shell/src/builder/pipeline/PipelinePreviewMap.tsx`, change the component signature and the feature-building code:

```tsx
export function PipelinePreviewMap({
  rows,
  selectedIndex = null,
  onSelectIndex,
}: {
  rows: Record<string, unknown>[];
  selectedIndex?: number | null;
  onSelectIndex?: (index: number) => void;
}) {
  const containerRef = useRef<HTMLDivElement>(null);
  const mapRef = useRef<maplibregl.Map | null>(null);

  useEffect(() => {
    if (!containerRef.current) return;
    const features: GeoJSON.Feature[] = rows
      .map((r, i) => ({ r, i }))
      .filter(({ r }) => r.geometry != null)
      .map(({ r, i }) => ({
        type: "Feature",
        properties: { __rowIndex: i },
        geometry: r.geometry as GeoJSON.Geometry,
      }));
    const featureCollection: GeoJSON.FeatureCollection = { type: "FeatureCollection", features };

    const map = new maplibregl.Map({
      container: containerRef.current,
      style: DEFAULT_BASEMAP.style,
      center: [0, 0],
      zoom: 1,
    });
    mapRef.current = map;
    map.on("load", () => {
      map.addSource(SOURCE_ID, { type: "geojson", data: featureCollection });
      map.addLayer({
        id: `${SOURCE_ID}-fill`,
        type: "fill",
        source: SOURCE_ID,
        filter: ["==", ["geometry-type"], "Polygon"],
        paint: { "fill-color": "#2563eb", "fill-opacity": 0.4 },
      });
      map.addLayer({
        id: `${SOURCE_ID}-line`,
        type: "line",
        source: SOURCE_ID,
        filter: ["==", ["geometry-type"], "LineString"],
        paint: { "line-color": "#16a34a", "line-width": 2 },
      });
      map.addLayer({
        id: `${SOURCE_ID}-circle`,
        type: "circle",
        source: SOURCE_ID,
        filter: ["==", ["geometry-type"], "Point"],
        paint: { "circle-color": "#dc2626", "circle-radius": 5 },
      });
      map.addLayer({
        id: `${SOURCE_ID}-selected`,
        type: "line",
        source: SOURCE_ID,
        filter: ["==", ["get", "__rowIndex"], selectedIndex ?? -1],
        paint: { "line-color": "#facc15", "line-width": 3 },
      });
      const handleClick = (e: maplibregl.MapLayerMouseEvent) => {
        const idx = e.features?.[0]?.properties?.__rowIndex;
        if (typeof idx === "number") onSelectIndex?.(idx);
      };
      map.on("click", `${SOURCE_ID}-fill`, handleClick);
      map.on("click", `${SOURCE_ID}-line`, handleClick);
      map.on("click", `${SOURCE_ID}-circle`, handleClick);
      const bounds = computeBounds(rows.filter((r) => r.geometry != null).map((r) => ({ type: "Feature", properties: {}, geometry: r.geometry as GeoJSON.Geometry })));
      if (bounds) map.fitBounds(bounds, { padding: 20, maxZoom: 16 });
    });
    return () => {
      mapRef.current = null;
      map.remove();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [rows]);

  useEffect(() => {
    if (mapRef.current?.getLayer(`${SOURCE_ID}-selected`)) {
      mapRef.current.setFilter(`${SOURCE_ID}-selected`, ["==", ["get", "__rowIndex"], selectedIndex ?? -1]);
    }
  }, [selectedIndex]);
```

The `computeBounds(features)` call at the end of the load handler previously read the already-built `features` array directly — keep using that same `features` variable (already in scope) rather than rebuilding it a second time as sketched above; write it as:

```tsx
      const bounds = computeBounds(features);
      if (bounds) map.fitBounds(bounds, { padding: 20, maxZoom: 16 });
```

(This replaces the redundant rebuild shown in the snippet above — `features` is already the filtered, geometry-bearing list computed earlier in this same effect.)

The rest of the component (legend rendering, from Task 15) is unchanged; only the `useEffect`(s) and function signature change.

- [ ] **Step 4: Run the map tests**

```bash
cd shell && npx vitest run src/builder/pipeline/PipelinePreviewMap.test.tsx
```
Expected: PASS (all tests, old and new).

- [ ] **Step 5: Write the failing tests for the panel side (shared selection + attributes)**

Add to `shell/src/builder/pipeline/PipelinePreviewPanel.test.tsx`:

```tsx
test("clicking a table row shows its attributes below the table", async () => {
  renderPanel(vi.fn().mockResolvedValue([{ id: 1, pop: 1200 }, { id: 2, pop: 800 }]));
  await waitFor(() => expect(screen.getByRole("cell", { name: "1200" })).toBeInTheDocument());
  await userEvent.click(screen.getByRole("cell", { name: "800" }).closest("tr")!);
  expect(screen.getByText("Attributs de la feature")).toBeInTheDocument();
  expect(screen.getByText("800")).toBeInTheDocument();
});

test("selecting a feature on the map is reflected when switching back to the table", async () => {
  renderPanel(
    vi.fn().mockResolvedValue([
      { id: 1, geometry: { type: "Point", coordinates: [1, 1] } },
      { id: 2, geometry: { type: "Point", coordinates: [2, 2] } },
    ]),
  );
  await waitFor(() => expect(screen.getByRole("button", { name: "Carte" })).toBeInTheDocument());
  await userEvent.click(screen.getByRole("button", { name: "Carte" }));
  const map = mapInstances[0];
  map.fireOnLayer("click", "pipeline-preview-circle", { features: [{ properties: { __rowIndex: 1 } }] });
  await userEvent.click(screen.getByRole("button", { name: "Tableau" }));
  const rows = screen.getAllByRole("row");
  expect(rows[2]).toHaveClass("bg-sunken"); // header row + row 0 + selected row 1
});
```

Add `import userEvent from "@testing-library/user-event";` and `import { mapInstances } from "../../test/MockMaplibreMap";` to this test file if not already present.

- [ ] **Step 6: Run them to verify they fail**

```bash
cd shell && npx vitest run src/builder/pipeline/PipelinePreviewPanel.test.tsx -t "attributes"
```
Expected: FAIL — no click handler, no attributes panel, no selection highlight exist yet.

- [ ] **Step 7: Wire shared selection into `PipelinePreviewPanel.tsx`**

Add state and pass it through:

```tsx
  const [selectedIndex, setSelectedIndex] = useState<number | null>(null);
```

Pass `selectedIndex`/`onSelectIndex` to `<PipelinePreviewMap>`:

```tsx
      {hasGeometry && view === "map" ? (
        <PipelinePreviewMap rows={rows} selectedIndex={selectedIndex} onSelectIndex={setSelectedIndex} />
      ) : (
```

Make table rows clickable and highlight the selected one:

```tsx
          <tbody>
            {rows.map((row, i) => (
              <tr
                key={i}
                onClick={() => setSelectedIndex(i)}
                className={`cursor-pointer border-t border-rule ${i === selectedIndex ? "bg-sunken" : ""}`}
              >
                {columns.map((c) => (
                  <td key={c} className="p-1">
                    {String(row[c])}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
```

Add the attributes panel, right after the table/map block, before the closing `</div>` of the component:

```tsx
      {selectedIndex !== null && rows[selectedIndex] && (
        <div className="rounded border border-rule p-2 text-xs">
          <p className="mb-1 font-medium text-ink-2">{t("pipelinePreview.featureAttributes")}</p>
          <dl className="grid grid-cols-2 gap-x-2 gap-y-1">
            {Object.entries(rows[selectedIndex])
              .filter(([c]) => c !== "geometry")
              .map(([k, v]) => (
                <div key={k} className="contents">
                  <dt className="text-ink-2">{k}</dt>
                  <dd className="text-ink">{String(v)}</dd>
                </div>
              ))}
          </dl>
        </div>
      )}
```

Add the i18n key, anchored after `"pipelinePreview.mapView": "Carte",`:

```ts
  "pipelinePreview.featureAttributes": "Attributs de la feature",
```

- [ ] **Step 8: Run the panel tests**

```bash
cd shell && npx vitest run src/builder/pipeline/PipelinePreviewPanel.test.tsx
```
Expected: PASS (all tests, old and new). Note the pre-existing test `"fetches the preview for the given node and renders it as a table"` clicks nothing and asserts on `getByRole("cell", ...)` only — unaffected by the new `onClick` on `<tr>`.

- [ ] **Step 9: Run the full shell suite and commit**

```bash
cd shell && npm run test
```
Expected: PASS.

```bash
git add shell/src/builder/pipeline/PipelinePreviewMap.tsx shell/src/builder/pipeline/PipelinePreviewPanel.tsx shell/src/builder/pipeline/PipelinePreviewMap.test.tsx shell/src/builder/pipeline/PipelinePreviewPanel.test.tsx shell/src/i18n/catalog.fr.ts
git commit -m "feat(shell): shared feature selection and attributes panel across pipeline preview table and map"
```

---

### Task 17: Pagination et compteur de lignes dans l'aperçu tableau

**Files:**
- Modify: `shell/src/builder/pipeline/PipelinePreviewPanel.tsx`
- Modify: `shell/src/i18n/catalog.fr.ts`
- Test: `shell/src/builder/pipeline/PipelinePreviewPanel.test.tsx`

**Interfaces:** none new.

- [ ] **Step 1: Write the failing test**

```tsx
test("paginates rows at 20 per page and shows a counter", async () => {
  const rows = Array.from({ length: 45 }, (_, i) => ({ id: i, pop: i * 10 }));
  renderPanel(vi.fn().mockResolvedValue(rows));
  await waitFor(() => expect(screen.getAllByRole("row")).toHaveLength(21)); // header + 20
  expect(screen.getByText("Lignes 1–20 sur 45")).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Précédent" })).toBeDisabled();
  await userEvent.click(screen.getByRole("button", { name: "Suivant" }));
  expect(screen.getByText("Lignes 21–40 sur 45")).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Précédent" })).toBeEnabled();
});

test("resets to the first page when the previewed rows change", async () => {
  const rows45 = Array.from({ length: 45 }, (_, i) => ({ id: i }));
  const rows5 = Array.from({ length: 5 }, (_, i) => ({ id: i }));
  const previewPipeline = vi.fn().mockResolvedValueOnce(rows45).mockResolvedValueOnce(rows5);
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const client: Partial<ItemClient> = { previewPipeline };
  const { rerender } = render(
    <QueryClientProvider client={qc}>
      <ItemClientProvider client={client as ItemClient}>
        <PipelinePreviewPanel pipelineId="p-1" nodeId="r1" />
      </ItemClientProvider>
    </QueryClientProvider>,
  );
  await waitFor(() => expect(screen.getByText("Lignes 1–20 sur 45")).toBeInTheDocument());
  await userEvent.click(screen.getByRole("button", { name: "Suivant" }));
  expect(screen.getByText("Lignes 21–40 sur 45")).toBeInTheDocument();
  rerender(
    <QueryClientProvider client={qc}>
      <ItemClientProvider client={client as ItemClient}>
        <PipelinePreviewPanel pipelineId="p-1" nodeId="w1" />
      </ItemClientProvider>
    </QueryClientProvider>,
  );
  await waitFor(() => expect(screen.getByText("Lignes 1–5 sur 5")).toBeInTheDocument());
});
```

- [ ] **Step 2: Run them to verify they fail**

```bash
cd shell && npx vitest run src/builder/pipeline/PipelinePreviewPanel.test.tsx -t "paginates"
```
Expected: FAIL — no pagination exists; all 45 rows render at once.

- [ ] **Step 3: Add pagination**

In `shell/src/builder/pipeline/PipelinePreviewPanel.tsx`, add:

```ts
const PAGE_SIZE = 20;
```

```ts
  const [page, setPage] = useState(0);
  useEffect(() => {
    setPage(0);
  }, [rows]);
```

Add `useEffect` to this file's React import (currently `import { useState } from "react";`).

Slice the rendered rows and add the pager UI. Replace the `<tbody>` rows source and add controls after the `</table>`:

```tsx
          <tbody>
            {rows.slice(page * PAGE_SIZE, (page + 1) * PAGE_SIZE).map((row, sliceIndex) => {
              const i = page * PAGE_SIZE + sliceIndex;
              return (
                <tr
                  key={i}
                  onClick={() => setSelectedIndex(i)}
                  className={`cursor-pointer border-t border-rule ${i === selectedIndex ? "bg-sunken" : ""}`}
                >
                  {columns.map((c) => (
                    <td key={c} className="p-1">
                      {String(row[c])}
                    </td>
                  ))}
                </tr>
              );
            })}
          </tbody>
        </table>
      )}
      {rows.length > 0 && (
        <div className="flex items-center gap-2 text-xs">
          <Button
            size="sm"
            variant="outline"
            disabled={page === 0}
            onClick={() => setPage((p) => p - 1)}
          >
            {t("pipelinePreview.previousPage")}
          </Button>
          <span>
            {t("pipelinePreview.rowRange", {
              from: page * PAGE_SIZE + 1,
              to: Math.min((page + 1) * PAGE_SIZE, rows.length),
              total: rows.length,
            })}
          </span>
          <Button
            size="sm"
            variant="outline"
            disabled={(page + 1) * PAGE_SIZE >= rows.length}
            onClick={() => setPage((p) => p + 1)}
          >
            {t("pipelinePreview.nextPage")}
          </Button>
        </div>
      )}
```

The pager block sits after the `{hasGeometry && view === "map" ? ... : (<table>...</table>)}` conditional, not inside it — it applies to the table view only, so wrap the whole existing conditional and the new pager together such that the pager is only rendered `view === "table"` (or always rendered but only meaningful there — since map view doesn't paginate, gate it explicitly):

```tsx
      {hasGeometry && view === "map" ? (
        <PipelinePreviewMap rows={rows} selectedIndex={selectedIndex} onSelectIndex={setSelectedIndex} />
      ) : (
        <>
          <table className="w-full text-xs">
            {/* ...thead + the paginated tbody above... */}
          </table>
          {rows.length > 0 && (
            <div className="flex items-center gap-2 text-xs">
              {/* ...pager controls above... */}
            </div>
          )}
        </>
      )}
```

Add `import { Button } from "../../ui/kit/Button";`.

Add i18n keys, anchored after `"pipelinePreview.featureAttributes": "Attributs de la feature",`:

```ts
  "pipelinePreview.previousPage": "Précédent",
  "pipelinePreview.nextPage": "Suivant",
  "pipelinePreview.rowRange": "Lignes {from}–{to} sur {total}",
```

- [ ] **Step 4: Run the tests**

```bash
cd shell && npx vitest run src/builder/pipeline/PipelinePreviewPanel.test.tsx
```
Expected: PASS (all tests, old and new — the pre-existing small-row-count tests, e.g. 1-2 rows, are unaffected since they never exceed `PAGE_SIZE`).

- [ ] **Step 5: Commit**

```bash
git add shell/src/builder/pipeline/PipelinePreviewPanel.tsx shell/src/builder/pipeline/PipelinePreviewPanel.test.tsx shell/src/i18n/catalog.fr.ts
git commit -m "feat(shell): paginate the pipeline preview table and show a row counter"
```

---

### Task 18: Formatage par type + géométrie renvoyée vers la carte

**Files:**
- Modify: `shell/src/builder/pipeline/PipelinePreviewPanel.tsx`
- Modify: `shell/src/i18n/catalog.fr.ts`
- Test: `shell/src/builder/pipeline/PipelinePreviewPanel.test.tsx`

**Interfaces:** none new.

- [ ] **Step 1: Write the failing test**

```tsx
test("formats a number with French thousands separators", async () => {
  renderPanel(vi.fn().mockResolvedValue([{ id: 1, pop: 1234567 }]));
  await waitFor(() => expect(screen.getByRole("cell", { name: "1 234 567" })).toBeInTheDocument());
});

test("shows a Voir sur la carte button instead of raw geometry JSON", async () => {
  renderPanel(
    vi.fn().mockResolvedValue([{ id: 1, geometry: { type: "Point", coordinates: [1, 2] } }]),
  );
  await waitFor(() =>
    expect(screen.getByRole("button", { name: "Voir sur la carte" })).toBeInTheDocument(),
  );
  expect(screen.queryByText("[object Object]")).not.toBeInTheDocument();
});

test("clicking Voir sur la carte switches to map view with that row selected", async () => {
  renderPanel(
    vi.fn().mockResolvedValue([
      { id: 1, geometry: { type: "Point", coordinates: [1, 2] } },
      { id: 2, geometry: { type: "Point", coordinates: [3, 4] } },
    ]),
  );
  await waitFor(() => expect(screen.getAllByRole("button", { name: "Voir sur la carte" })).toHaveLength(2));
  await userEvent.click(screen.getAllByRole("button", { name: "Voir sur la carte" })[1]);
  expect(screen.getByTestId("pipeline-preview-map")).toBeInTheDocument();
});
```

- [ ] **Step 2: Run them to verify they fail**

```bash
cd shell && npx vitest run src/builder/pipeline/PipelinePreviewPanel.test.tsx -t "French thousands"
```
Expected: FAIL — `String(row[c])` renders `1234567` (no separator) and `[object Object]` for the geometry cell.

- [ ] **Step 3: Add `formatCell` and the geometry button**

In `shell/src/builder/pipeline/PipelinePreviewPanel.tsx`, add a module-level helper:

```ts
const ISO_DATE_RE = /^\d{4}-\d{2}-\d{2}/;

function formatCell(value: unknown): string {
  if (typeof value === "number") return value.toLocaleString("fr-FR");
  if (typeof value === "string" && ISO_DATE_RE.test(value)) {
    const parsed = new Date(value);
    if (!Number.isNaN(parsed.getTime())) return parsed.toLocaleString("fr-FR");
  }
  return String(value);
}
```

Replace the cell rendering in the `<tbody>` (from Task 17's slice loop):

```tsx
                  {columns.map((c) =>
                    c === "geometry" ? (
                      <td key={c} className="p-1">
                        <button
                          type="button"
                          onClick={(e) => {
                            e.stopPropagation();
                            setSelectedIndex(i);
                            setView("map");
                          }}
                          className="text-accent underline"
                        >
                          {t("pipelinePreview.viewOnMap")}
                        </button>
                      </td>
                    ) : (
                      <td key={c} className="p-1">
                        {formatCell(row[c])}
                      </td>
                    ),
                  )}
```

`e.stopPropagation()` prevents the row's own `onClick={() => setSelectedIndex(i)}` (Task 16) from also firing redundantly — harmless either way since both set the same index, but avoids a double state update.

Add the i18n key, anchored after `"pipelinePreview.rowRange": "Lignes {from}–{to} sur {total}",`:

```ts
  "pipelinePreview.viewOnMap": "Voir sur la carte",
```

- [ ] **Step 4: Run the tests**

```bash
cd shell && npx vitest run src/builder/pipeline/PipelinePreviewPanel.test.tsx
```
Expected: PASS (all tests, old and new — re-check the pre-existing map-toggle tests still find their `geometry`-bearing rows correctly, since the `geometry` column cell now renders a button rather than raw text; none of them assert on the geometry cell's own content, only on the tableau/carte toggle buttons, so they should be unaffected).

- [ ] **Step 5: Commit**

```bash
git add shell/src/builder/pipeline/PipelinePreviewPanel.tsx shell/src/builder/pipeline/PipelinePreviewPanel.test.tsx shell/src/i18n/catalog.fr.ts
git commit -m "feat(shell): type-aware cell formatting and a map shortcut for geometry cells"
```

---

### Task 19: Tri des colonnes dans l'aperçu tableau

**Files:**
- Modify: `shell/src/builder/pipeline/PipelinePreviewPanel.tsx`
- Test: `shell/src/builder/pipeline/PipelinePreviewPanel.test.tsx`

**Interfaces:** none new.

- [ ] **Step 1: Write the failing test**

```tsx
test("clicking a column header sorts rows ascending, then descending on a second click", async () => {
  renderPanel(vi.fn().mockResolvedValue([{ id: 1, pop: 300 }, { id: 2, pop: 100 }, { id: 3, pop: 200 }]));
  await waitFor(() => expect(screen.getByRole("cell", { name: "300" })).toBeInTheDocument());
  await userEvent.click(screen.getByRole("columnheader", { name: "pop" }));
  let cells = screen.getAllByRole("row").slice(1).map((r) => within(r).getAllByRole("cell")[1].textContent);
  expect(cells).toEqual(["100", "200", "300"]);
  await userEvent.click(screen.getByRole("columnheader", { name: "pop" }));
  cells = screen.getAllByRole("row").slice(1).map((r) => within(r).getAllByRole("cell")[1].textContent);
  expect(cells).toEqual(["300", "200", "100"]);
});
```

Add `within` to this test file's `@testing-library/react` import.

- [ ] **Step 2: Run it to verify it fails**

```bash
cd shell && npx vitest run src/builder/pipeline/PipelinePreviewPanel.test.tsx -t "sorts rows ascending"
```
Expected: FAIL — no `columnheader` click handler exists; `<th>` has no `aria-sort`/sorting behavior (`role="columnheader"` is `<th>`'s implicit ARIA role, already present without change).

- [ ] **Step 3: Add sort state and a comparator**

Add state and a pure comparator function:

```ts
  const [sortColumn, setSortColumn] = useState<string | null>(null);
  const [sortDirection, setSortDirection] = useState<"asc" | "desc">("asc");
```

```ts
function compareCells(a: unknown, b: unknown): number {
  if (typeof a === "number" && typeof b === "number") return a - b;
  return String(a).localeCompare(String(b));
}
```

Compute the sorted rows before slicing for pagination:

```ts
  const sortedRows =
    sortColumn === null
      ? rows
      : [...rows].sort((a, b) => {
          const cmp = compareCells(a[sortColumn], b[sortColumn]);
          return sortDirection === "asc" ? cmp : -cmp;
        });
```

Use `sortedRows` (not `rows`) as the source for `.slice(page * PAGE_SIZE, ...)` in the `<tbody>` (Task 17/18's slice loop) — everywhere that currently reads `rows.slice(...)`/`rows.length` for pagination and row lookups should keep reading `rows.length`/`rows[selectedIndex]` for the total count and the attributes panel (those must stay stable against sort order, since `selectedIndex` refers to `rows`' original index, established by Task 16's `__rowIndex` tagging) — only the **slice used to render table rows** switches to `sortedRows`. Since `sortedRows` reorders but does not reindex, `i = page * PAGE_SIZE + sliceIndex` computed against `sortedRows` no longer equals a row's position in the original `rows` array — this breaks the `selectedIndex`/`__rowIndex` correspondence from Task 16 once sorting is active.

Resolve this by keying rows by their **original** index instead of position: change the mapping to find each sorted row's original index via a stable per-row key computed once, before sorting:

```ts
  const rowsWithIndex = rows.map((row, i) => ({ row, i }));
  const sortedRows =
    sortColumn === null
      ? rowsWithIndex
      : [...rowsWithIndex].sort((a, b) => {
          const cmp = compareCells(a.row[sortColumn], b.row[sortColumn]);
          return sortDirection === "asc" ? cmp : -cmp;
        });
```

and in the `<tbody>`:

```tsx
            {sortedRows.slice(page * PAGE_SIZE, (page + 1) * PAGE_SIZE).map(({ row, i }) => (
              <tr
                key={i}
                onClick={() => setSelectedIndex(i)}
                className={`cursor-pointer border-t border-rule ${i === selectedIndex ? "bg-sunken" : ""}`}
              >
                {columns.map((c) =>
                  c === "geometry" ? (
                    <td key={c} className="p-1">
                      <button
                        type="button"
                        onClick={(e) => {
                          e.stopPropagation();
                          setSelectedIndex(i);
                          setView("map");
                        }}
                        className="text-accent underline"
                      >
                        {t("pipelinePreview.viewOnMap")}
                      </button>
                    </td>
                  ) : (
                    <td key={c} className="p-1">
                      {formatCell(row[c])}
                    </td>
                  ),
                )}
              </tr>
            ))}
```

(This replaces Task 18's `.map((row, sliceIndex) => { const i = page * PAGE_SIZE + sliceIndex; ... })` — `i` now comes from `rowsWithIndex`, correctly tracking each row's true original position through a sort.)

Add click handlers and `aria-sort` on the headers:

```tsx
            <tr>
              {columns.map((c) => (
                <th
                  key={c}
                  className="cursor-pointer p-1 text-left"
                  onClick={() =>
                    sortColumn === c
                      ? setSortDirection((d) => (d === "asc" ? "desc" : "asc"))
                      : (setSortColumn(c), setSortDirection("asc"))
                  }
                  aria-sort={sortColumn === c ? (sortDirection === "desc" ? "descending" : "ascending") : "none"}
                >
                  {c}
                </th>
              ))}
            </tr>
```

The `onClick` uses a comma expression to call 2 setters in one arrow — write it instead as an explicit block body for clarity and to avoid an ESLint no-sequences violation:

```tsx
                  onClick={() => {
                    if (sortColumn === c) {
                      setSortDirection((d) => (d === "asc" ? "desc" : "asc"));
                    } else {
                      setSortColumn(c);
                      setSortDirection("asc");
                    }
                  }}
```

Reset `page` to 0 when the sort changes too (a sort while on page 2 could otherwise show a confusing tail), by adding `sortColumn`/`sortDirection` to the existing `useEffect(() => setPage(0), [rows])` from Task 17:

```ts
  useEffect(() => {
    setPage(0);
  }, [rows, sortColumn, sortDirection]);
```

- [ ] **Step 4: Run the tests**

```bash
cd shell && npx vitest run src/builder/pipeline/PipelinePreviewPanel.test.tsx
```
Expected: PASS (all tests, old and new).

- [ ] **Step 5: Run the full shell suite and commit**

```bash
cd shell && npm run test
```
Expected: PASS.

```bash
git add shell/src/builder/pipeline/PipelinePreviewPanel.tsx shell/src/builder/pipeline/PipelinePreviewPanel.test.tsx
git commit -m "feat(shell): sortable columns in the pipeline preview table"
```

---

### Task 20: Détail par nœud pour chaque run historique

**Files:**
- Modify: `shell/src/builder/pipeline/PipelineRunPanel.tsx`
- Modify: `shell/src/i18n/catalog.fr.ts`
- Test: `shell/src/builder/pipeline/PipelineRunPanel.test.tsx`

**Interfaces:**
- Consumes: `PipelineRun.nodeStats: Record<string, PipelineNodeStat>` — already returned by `GET /pipelines/{id}/runs` for every run (confirmed in `core/app/pipelines/routes.py::list_pipeline_runs`, `core/app/pipelines/models.py::PipelineRun.node_stats`), not only the latest one. No backend change.

- [ ] **Step 1: Write the failing test**

```tsx
test("expanding a run shows its per-node row counts", async () => {
  renderPanel({
    getPipelineRuns: vi.fn().mockResolvedValue([
      {
        id: "run-0",
        status: "succeeded",
        startedAt: "2026-08-06T10:00:00Z",
        finishedAt: "2026-08-06T10:00:02Z",
        error: null,
        nodeStats: {
          r1: { nodeId: "r1", op: "reader.collection", rowCount: 42 },
          w1: { nodeId: "w1", op: "writer.collection", rowCount: 40 },
        },
      },
    ]),
  });
  await waitFor(() => expect(screen.getByText("succeeded")).toBeInTheDocument());
  expect(screen.queryByText("reader.collection : 42")).not.toBeInTheDocument();
  await userEvent.click(screen.getByRole("button", { name: "Détail du run run-0" }));
  expect(screen.getByText("reader.collection : 42")).toBeInTheDocument();
  expect(screen.getByText("writer.collection : 40")).toBeInTheDocument();
});

test("a run with no nodeStats shows no expand toggle", async () => {
  renderPanel({
    getPipelineRuns: vi.fn().mockResolvedValue([
      {
        id: "run-0",
        status: "queued",
        startedAt: null,
        finishedAt: null,
        error: null,
        nodeStats: {},
      },
    ]),
  });
  await waitFor(() => expect(screen.getByText("En attente")).toBeInTheDocument());
  expect(screen.queryByRole("button", { name: "Détail du run run-0" })).not.toBeInTheDocument();
});
```

Add `import userEvent from "@testing-library/user-event";` to this test file if not already present.

- [ ] **Step 2: Run them to verify they fail**

```bash
cd shell && npx vitest run src/builder/pipeline/PipelineRunPanel.test.tsx -t "per-node row counts"
```
Expected: FAIL — no expand toggle exists; `nodeStats` is fetched but never rendered.

- [ ] **Step 3: Extract a `RunRow` component with an expand toggle**

In `shell/src/builder/pipeline/PipelineRunPanel.tsx`, add the import:

```ts
import { usePanelTrigger } from "../../ui/kit/usePanelTrigger";
```

Add a `RunRow` component, above `PipelineRunPanel` (it needs its own `usePanelTrigger` instance per run, which requires a real component, not an inline callback inside a `.map()`):

```tsx
function RunRow({ run }: { run: PipelineRun }) {
  const [open, setOpen] = useState(false);
  const detail = usePanelTrigger(open);
  const nodeEntries = Object.values(run.nodeStats);
  return (
    <li className="border-t border-rule pt-1">
      <div className="flex items-center gap-2">
        <span>{STATUS_LABEL[run.status]}</span>
        {run.startedAt && <span className="text-ink-2">{run.startedAt}</span>}
        {nodeEntries.length > 0 && (
          <button
            type="button"
            aria-label={t("pipelineRun.detailAria", { id: run.id })}
            aria-expanded={detail.triggerProps["aria-expanded"]}
            aria-controls={detail.triggerProps["aria-controls"]}
            className="text-accent underline"
            onClick={() => setOpen((o) => !o)}
          >
            {open ? t("pipelineRun.hideDetail") : t("pipelineRun.showDetail")}
          </button>
        )}
      </div>
      {run.error && (
        <p role="alert" className="text-danger">
          {run.error}
        </p>
      )}
      {open && nodeEntries.length > 0 && (
        <ul {...detail.panelProps} className="ml-4 mt-1 flex flex-col gap-0.5 text-ink-2">
          {nodeEntries.map((stat) => (
            <li key={stat.nodeId}>
              {stat.op} : {stat.rowCount ?? "—"}
            </li>
          ))}
        </ul>
      )}
    </li>
  );
}
```

Import `PipelineRun` is already imported in this file (`import type { PipelineRun } from "../../api/types";`).

Replace the `<ul>` inside `PipelineRunPanel`'s return statement:

```tsx
      <ul className="flex flex-col gap-1 text-xs">
        {runs.map((run) => (
          <li key={run.id} className="border-t border-rule pt-1">
            <span>{STATUS_LABEL[run.status]}</span>
            {run.startedAt && <span className="ml-2 text-ink-2">{run.startedAt}</span>}
            {run.error && (
              <p role="alert" className="text-danger">
                {run.error}
              </p>
            )}
          </li>
        ))}
      </ul>
```

with:

```tsx
      <ul className="flex flex-col gap-1 text-xs">
        {runs.map((run) => (
          <RunRow key={run.id} run={run} />
        ))}
      </ul>
```

Add i18n keys, anchored after `"pipelineRun.loadMore": "Charger plus",`:

```ts
  "pipelineRun.detailAria": "Détail du run {id}",
  "pipelineRun.showDetail": "Détail",
  "pipelineRun.hideDetail": "Masquer le détail",
```

- [ ] **Step 4: Run the tests**

```bash
cd shell && npx vitest run src/builder/pipeline/PipelineRunPanel.test.tsx
```
Expected: PASS (all tests, old and new — the pre-existing tests only assert on `STATUS_LABEL`/`run.error` text, both still rendered by `RunRow`, so they should be unaffected by the extraction).

- [ ] **Step 5: Commit**

```bash
git add shell/src/builder/pipeline/PipelineRunPanel.tsx shell/src/builder/pipeline/PipelineRunPanel.test.tsx shell/src/i18n/catalog.fr.ts
git commit -m "feat(shell): expandable per-node detail on each pipeline run in the history"
```

---

### Task 21: Durée calculée et dates localisées dans le panneau d'exécution

**Files:**
- Modify: `shell/src/builder/pipeline/PipelineRunPanel.tsx`
- Modify: `shell/src/i18n/catalog.fr.ts`
- Test: `shell/src/builder/pipeline/PipelineRunPanel.test.tsx`

**Interfaces:** none new.

- [ ] **Step 1: Write the failing test**

```tsx
test("shows a computed duration and a localized date for a finished run", async () => {
  renderPanel({
    getPipelineRuns: vi.fn().mockResolvedValue([
      {
        id: "run-0",
        status: "succeeded",
        startedAt: "2026-08-06T10:00:00.000Z",
        finishedAt: "2026-08-06T10:00:05.000Z",
        error: null,
        nodeStats: {},
      },
    ]),
  });
  await waitFor(() => expect(screen.getByText("succeeded")).toBeInTheDocument());
  expect(screen.getByText("5 s")).toBeInTheDocument();
  expect(screen.getByText(new Date("2026-08-06T10:00:00.000Z").toLocaleString("fr-FR"))).toBeInTheDocument();
});

test("shows no duration for a run still in progress", async () => {
  renderPanel({
    getPipelineRuns: vi.fn().mockResolvedValue([
      {
        id: "run-0",
        status: "running",
        startedAt: "2026-08-06T10:00:00.000Z",
        finishedAt: null,
        error: null,
        nodeStats: {},
      },
    ]),
  });
  await waitFor(() => expect(screen.getByText("En cours")).toBeInTheDocument());
  expect(screen.queryByText(/^\d+ s$/)).not.toBeInTheDocument();
});
```

- [ ] **Step 2: Run them to verify they fail**

```bash
cd shell && npx vitest run src/builder/pipeline/PipelineRunPanel.test.tsx -t "computed duration"
```
Expected: FAIL — `startedAt` is currently rendered as the raw ISO string, no duration exists.

- [ ] **Step 3: Add `formatDuration` and localized date rendering**

Add a module-level helper in `shell/src/builder/pipeline/PipelineRunPanel.tsx`:

```ts
function formatDuration(startedAt: string | null, finishedAt: string | null): string | null {
  if (!startedAt || !finishedAt) return null;
  const ms = new Date(finishedAt).getTime() - new Date(startedAt).getTime();
  if (!Number.isFinite(ms) || ms < 0) return null;
  const totalSeconds = Math.round(ms / 1000);
  if (totalSeconds < 60) return `${totalSeconds} s`;
  const minutes = Math.floor(totalSeconds / 60);
  const seconds = totalSeconds % 60;
  return `${minutes} min ${seconds} s`;
}
```

In `RunRow` (added by Task 20), replace the header line:

```tsx
      <div className="flex items-center gap-2">
        <span>{STATUS_LABEL[run.status]}</span>
        {run.startedAt && <span className="text-ink-2">{run.startedAt}</span>}
        {nodeEntries.length > 0 && (
```

with:

```tsx
      <div className="flex items-center gap-2">
        <span>{STATUS_LABEL[run.status]}</span>
        {run.startedAt && (
          <span className="text-ink-2">{new Date(run.startedAt).toLocaleString("fr-FR")}</span>
        )}
        {formatDuration(run.startedAt, run.finishedAt) && (
          <span className="text-ink-2">{formatDuration(run.startedAt, run.finishedAt)}</span>
        )}
        {nodeEntries.length > 0 && (
```

- [ ] **Step 4: Run the tests**

```bash
cd shell && npx vitest run src/builder/pipeline/PipelineRunPanel.test.tsx
```
Expected: PASS (all tests, old and new — the pre-existing tests reference `run.startedAt` in their fixtures but never assert on its rendered text directly, only on `STATUS_LABEL`/`run.error`, so the localized-date change should not break them; if any test does assert the raw ISO string is present, update that assertion to the localized form).

- [ ] **Step 5: Commit**

```bash
git add shell/src/builder/pipeline/PipelineRunPanel.tsx shell/src/builder/pipeline/PipelineRunPanel.test.tsx
git commit -m "feat(shell): show computed run duration and localized dates in the pipeline run history"
```

---

### Task 22: Prochaine exécution planifiée affichée en clair (backend + frontend)

**Files:**
- Modify: `core/app/pipelines/routes.py`
- Test: `core/tests/test_pipeline_routes.py`
- Modify: `shell/src/api/types.ts`
- Modify: `shell/src/api/domains/pipelines.ts`
- Modify: `shell/src/api/domains/pipelines.hooks.ts`
- Modify: `shell/src/staticExport/StaticItemClient.ts`
- Modify: `shell/src/desktop/DesktopItemClient.ts`
- Modify: `shell/src/builder/pipeline/PipelineScheduleEditor.tsx`
- Modify: `shell/src/i18n/catalog.fr.ts`
- Test: `shell/src/builder/pipeline/PipelineScheduleEditor.test.tsx`

**Interfaces:**
- Produces: `GET /pipelines/next-run?cron=<expr>` → `{ nextRun: string }` (ISO 8601) or 400 on an invalid expression. `ItemClient.getPipelineNextRun(cron: string): Promise<{ nextRun: string }>`; `usePipelineNextRun(cron: string, enabled: boolean)`.

#### Partie cœur

- [ ] **Step 1: Write the failing backend tests**

Add to `core/tests/test_pipeline_routes.py`:

```python
def test_next_run_route_computes_the_next_occurrence(monkeypatch):
    client = _make_app(monkeypatch, etl_enabled=True)
    response = client.get("/v1/pipelines/next-run?cron=0+2+*+*+*")
    assert response.status_code == 200
    body = response.json()
    assert "nextRun" in body
    from datetime import UTC, datetime

    next_run = datetime.fromisoformat(body["nextRun"])
    assert next_run > datetime.now(UTC)


def test_next_run_route_rejects_an_invalid_cron_expression(monkeypatch):
    client = _make_app(monkeypatch, etl_enabled=True)
    response = client.get("/v1/pipelines/next-run?cron=not-a-cron")
    assert response.status_code == 400


def test_next_run_route_absent_when_etl_disabled(monkeypatch):
    client = _make_app(monkeypatch, etl_enabled=False)
    assert client.get("/v1/pipelines/next-run?cron=0+2+*+*+*").status_code == 404
```

- [ ] **Step 2: Run them to verify they fail**

```bash
cd core && uv run pytest tests/test_pipeline_routes.py -k next_run -v
```
Expected: FAIL — the route doesn't exist (404 on all 3, including the ones expecting 200/400).

- [ ] **Step 3: Add the route**

In `core/app/pipelines/routes.py`, add the import:

```python
from datetime import UTC, datetime

import croniter
```

Add a response model near `RunResponse`:

```python
class NextRunResponse(BaseModel):
    nextRun: str
```

Add the route (placed near `get_pipeline_ops`, both are unauthenticated-by-item, catalog-style endpoints — though this one still requires `Depends(get_current_user)` per this router's own convention, since only `/trigger` is the documented exception):

```python
@router.get("/pipelines/next-run", response_model=NextRunResponse)
def get_pipeline_next_run(
    cron: str = Query(...),
    user: User = Depends(get_current_user),
) -> NextRunResponse:
    if not croniter.croniter.is_valid(cron):
        raise HTTPException(status_code=400, detail=f"invalid cron expression: {cron!r}")
    next_tick = croniter.croniter(cron, datetime.now(UTC)).get_next(datetime)
    return NextRunResponse(nextRun=next_tick.isoformat())
```

- [ ] **Step 4: Run the backend tests**

```bash
cd core && uv run pytest tests/test_pipeline_routes.py -v
```
Expected: PASS (all tests in the file).

- [ ] **Step 5: Regenerate OpenAPI + TS types**

```bash
cd core && PYTHONPATH=. \
  CORE_SECRETS_MASTER_KEY="AAECAwQFBgcICQoLDA0ODxAREhMUFRYXGBkaGxwdHh8=" \
  uv run python scripts/export_openapi.py openapi.json
cd ../shell && npm run gen:api-types
```

#### Partie shell

- [ ] **Step 6: Add `getPipelineNextRun` to `ItemClient` and its 3 implementations**

Modify `shell/src/api/types.ts`, adding near `getPipelineOps` (line ~525):

```ts
  getPipelineNextRun(cron: string): Promise<{ nextRun: string }>;
```

Modify `shell/src/api/domains/pipelines.ts` — add `"getPipelineNextRun"` to the `PipelinesMethods` `Pick<...>` union, and implement it:

```ts
    async getPipelineNextRun(cron: string): Promise<{ nextRun: string }> {
      return request<{ nextRun: string }>(
        "GET",
        `/pipelines/next-run?cron=${encodeURIComponent(cron)}`,
      );
    },
```

Modify `shell/src/staticExport/StaticItemClient.ts`, adding next to the other pipeline stubs:

```ts
    async getPipelineNextRun(..._args: unknown[]) {
      return unsupported();
    },
```

Modify `shell/src/desktop/DesktopItemClient.ts`, adding next to `getPipelineOps`:

```ts
    async getPipelineNextRun(cron: string): Promise<{ nextRun: string }> {
      return sidecarFetch<{ nextRun: string }>(
        "GET",
        `/pipelines/next-run?cron=${encodeURIComponent(cron)}`,
      );
    },
```

- [ ] **Step 7: Add the hook**

Add to `shell/src/api/domains/pipelines.hooks.ts`, next to `usePipelineOps`:

```ts
export function usePipelineNextRun(cron: string, enabled: boolean) {
  const client = useItemClientInternal();
  return useQuery({
    queryKey: ["pipeline-next-run", cron],
    queryFn: () => client.getPipelineNextRun(cron),
    enabled,
  });
}
```

- [ ] **Step 8: Write the failing test for the schedule editor**

Read `shell/src/builder/pipeline/PipelineScheduleEditor.test.tsx` first to match its existing render helper (it likely doesn't wrap in `QueryClientProvider`/`ItemClientProvider` today, since `PipelineScheduleEditor` has no data dependency yet — this task adds one) before writing this. Add:

```tsx
test("shows the next scheduled run time when scheduling is enabled", async () => {
  const getPipelineNextRun = vi
    .fn()
    .mockResolvedValue({ nextRun: "2026-08-07T02:00:00.000Z" });
  // Wrap in the providers this component now needs — mirror the pattern
  // from PipelinePreviewPanel.test.tsx's renderPanel helper (QueryClient +
  // ItemClientProvider), adapted to this file's existing render call.
  await waitFor(() =>
    expect(
      screen.getByText(new Date("2026-08-07T02:00:00.000Z").toLocaleString("fr-FR")),
    ).toBeInTheDocument(),
  );
});
```

This test's exact render wiring depends on `PipelineScheduleEditor.test.tsx`'s current structure (unread at plan-writing time) — write the full test body against that file's real existing render helper, following the shape above, rather than the placeholder comment.

- [ ] **Step 9: Run it to verify it fails**

```bash
cd shell && npx vitest run src/builder/pipeline/PipelineScheduleEditor.test.tsx -t "next scheduled run"
```
Expected: FAIL (component not wrapped in the required providers yet / no next-run text rendered).

- [ ] **Step 10: Wire the hook into `PipelineScheduleEditor.tsx`**

Add the import and call, then render the result when `enabled` is true:

```ts
import { usePipelineNextRun } from "../../api/hooks";
```

```ts
  const nextRunQuery = usePipelineNextRun(cron, enabled);
```

Add rendering right after the mode `<select>` block closes, before the mode-specific sub-forms:

```tsx
      {enabled && nextRunQuery.data && (
        <p className="text-xs text-ink-2">
          {t("pipelineSchedule.nextRun", {
            when: new Date(nextRunQuery.data.nextRun).toLocaleString("fr-FR"),
          })}
        </p>
      )}
```

Add the i18n key, anchored after `"pipelineSchedule.invalidCronFormat"` (find its exact existing key text before anchoring — it is present in the file per the earlier read, near the advanced-mode error message):

```ts
  "pipelineSchedule.nextRun": "Prochaine exécution : {when}",
```

Since `PipelineScheduleEditor` now calls a React Query hook, every existing render of this component (in its own test file, and everywhere it's mounted as part of `PipelineBuilderPage.tsx`) must run inside a `QueryClientProvider`/`ItemClientProvider` — `PipelineBuilderPage.tsx` already wraps its whole tree in both (verify via its own test file's `renderPage` helper, already reading from `QueryClientProvider`/`ItemClientProvider` at the top), so no change is needed there. Only `PipelineScheduleEditor.test.tsx`'s OWN render helper needs the new wrapping — apply it to every test in that file, not just the new one, since the hook now runs unconditionally on every render of this component regardless of `enabled`'s value (`useQuery`'s `enabled` option only gates the network call, not the hook's own requirement for a `QueryClientProvider` ancestor).

- [ ] **Step 11: Run the schedule editor tests**

```bash
cd shell && npx vitest run src/builder/pipeline/PipelineScheduleEditor.test.tsx
```
Expected: PASS (all tests, old and new, now that every render in this file is wrapped in the required providers).

- [ ] **Step 12: Run the full shell suite, the full core suite, and commit**

```bash
cd shell && npm run test && npx tsc --noEmit
cd ../core && uv run pytest
```
Expected: PASS.

```bash
cd core && git add app/pipelines/routes.py tests/test_pipeline_routes.py openapi.json
git commit -m "feat(core): expose the next scheduled pipeline run via croniter"
cd ../shell && git add src/api/types.ts src/api/domains/pipelines.ts src/api/domains/pipelines.hooks.ts src/staticExport/StaticItemClient.ts src/desktop/DesktopItemClient.ts src/builder/pipeline/PipelineScheduleEditor.tsx src/builder/pipeline/PipelineScheduleEditor.test.tsx src/i18n/catalog.fr.ts src/api/generated/core-schema.d.ts
git commit -m "feat(shell): show the next scheduled pipeline run in clear text"
```

---

## Self-Review

**Spec coverage** — every non-⚙️ item from `docs/superpowers/specs/2026-09-18-pipeline-builder-ux-improvements-design.md` §0-§7 maps to a task: §0 bugs → Tasks 1-3; §1 canvas → Tasks 4-10 (sous-pipelines réutilisables excluded, ⚙️); §2 palette → Tasks 8, 11-12; §3 inspecteur → Tasks 13-14 (éditeur CEL excluded, ⚙️); §4 preview carte → Tasks 15-16; §5 preview tableau → Tasks 17-19; §6 exécution/planification → Tasks 20-22 (suivi SSE excluded, ⚙️; "exécuter jusqu'à ce nœud" excluded, cf. Constats corrigés); §7 a11y/responsive → covered by Tasks 8/9's keyboard work plus the pre-existing filets noted in Constats corrigés, no standalone task needed.

**Placeholder scan** — no TBD/TODO; every step carries real code or an explicit, narrow instruction to read a named file first when its exact current content determines the step's shape (Tasks 2 Step 6, 22 Steps 8/10) — these are not vague "figure it out" placeholders, they name the exact file and the exact fallback pattern to mirror.

**Type consistency** — `PipelineCanvasNote`, `CanvasNodeData`'s accumulated fields (`errorCount` Task 1, `onDelete` Task 7, `onStartConnect`/`isConnectingSource` Task 9), `toFlowNode`'s `extra` parameter, and `PipelineCanvasInner`'s prop list are threaded consistently task-to-task — each task that extends one of these types shows the full updated shape, not a diff fragment, so a reader executing Task 9 after Task 7 sees `onDelete` still present alongside the new fields.

**Scope check** — 22 tasks is large; each is independently testable and revertable, matching this repo's own precedent (SP-27 shipped 20 tasks in one plan). The 3 ⚙️ items and the newly-descoped "exécuter jusqu'à ce nœud" remain out, as agreed with Tanguy before this plan was written.

