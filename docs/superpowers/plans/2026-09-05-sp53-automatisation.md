# SP-53 — Automatisation : implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fermer 6 manques catalogués par la revue SP-42 dans le domaine
Automatisation : GAP-44 (planification du moissonnage), GAP-49 (avertissement
proactif collections d'extension), GAP-43 (sélecteur de secret pipeline),
GAP-50 (parité `AlertRuleEditor`/`ReportScheduleEditor`), GAP-48 (MCP
create/run pour `AlertRule`), GAP-24 (déclenchement de pipeline par webhook
entrant).

**Architecture:** 7 tâches, ordonnées du plus petit/indépendant au plus gros,
avec dépendance interne explicite : la Tâche 3 (secret picker) est un
prérequis de la Tâche 4 (canal email de l'alerte). Les Tâches 6 et 7 (GAP-24)
sont séparées cœur/shell parce que c'est le seul chantier qui introduit une
capacité réellement nouvelle (les 5 autres n'exposent qu'une UI sur une
capacité déjà servie par le cœur).

**Tech Stack:** Python/FastAPI + SQLAlchemy + Alembic + pytest (cœur),
TypeScript/React + Vitest + Playwright (shell), procrastinate (queue `etl`).

**Document source :**
`docs/superpowers/specs/2026-09-05-sp53-automatisation-design.md` (sections
citées : §1 GAP-43, §2 GAP-44, §3 GAP-50, §4 GAP-48, §5 GAP-49, §6 GAP-24,
§7 questions ouvertes).

## Global Constraints

- **TDD / filet-avant-code** : chaque tâche écrit son test AVANT le code
  qu'il protège (composant, route, ou service).
- Commits **conventional**, un sujet par commit, français dans les messages
  (`feat(shell): …`, `feat(core): …`, `test(core): …`).
- **Suite complète rejouée avant de clore chaque tâche** — jamais un
  sous-ensemble (piège CLAUDE.md n°6) : `cd core && uv run pytest`,
  `cd shell && npm run test`, et pour les tâches qui touchent des routes/UI
  observables, `npm run e2e`.
- **Régénérer la spec OpenAPI + types TS** dès qu'une route ou un modèle de
  réponse change (piège CLAUDE.md n°1) — Tâches 1, 3, 5, 6 (aucune route
  nouvelle), 6/7 (routes nouvelles, diff non vide attendu) :
  ```bash
  cd core && PYTHONPATH=. \
    CORE_SECRETS_MASTER_KEY="AAECAwQFBgcICQoLDA0ODxAREhMUFRYXGBkaGxwdHh8=" \
    uv run python scripts/export_openapi.py openapi.json
  cd ../shell && npm run gen:api-types
  ```
- **Chemin de lecture** (piège CLAUDE.md n°5) : tout nouveau champ de
  config (`intervalMinutes`, canal `email`, requête d'alerte) doit survivre à
  un rechargement — vérifier qu'il est bien lu par le composant d'édition
  correspondant à l'ouverture, pas seulement écrit à la création.
- **Conteneur `postgis-test` non tracké par Alembic** (Tâche 6) : après la
  migration `0035`, un `ALTER TABLE` manuel peut être nécessaire sur ce
  conteneur avant de rejouer la suite complète contre lui.
- **`core/tests/test_model_alembic_parity.py` existe déjà** (héritage SP-43) :
  tout modèle ajouté par la Tâche 6 doit porter son `server_default=` dès
  l'écriture — ne pas réintroduire la dette qu'il vient de fermer.
- **Hors périmètre explicite** (spec §8) : `REV-097`
  (`tasks.view_all`, l'autre moitié du suivi, non touchée par ce plan),
  signature HMAC de payload webhook, idempotency-key, déclenchement
  webhook pour `AlertRule`/`ReportSchedule`, écran d'édition dédié pour
  `AlertRule`.

---

## Task 1 (GAP-44) : planification du moissonnage exposée dans les 2 panneaux

Le plus petit et le plus indépendant — sert d'échauffement. Le champ
`intervalMinutes` existe déjà de bout en bout côté API/types
(`shell/src/api/types.ts:753,764,771` ; `core/app/harvest/schemas.py:12,19` ;
`core/app/harvest/repository.py:204-229`) — seule l'UI manque.

**Files:**
- Modify: `shell/src/shell/CreateHarvestSourcePanel.tsx`,
  `shell/src/shell/EditHarvestSourcePanel.tsx`
- Create: `shell/src/shell/CreateHarvestSourcePanel.test.tsx`,
  `shell/src/shell/EditHarvestSourcePanel.test.tsx` (aucun test unitaire
  n'existe aujourd'hui pour ces deux fichiers — à vérifier avant de
  commencer, ne pas supposer qu'ils sont couverts ailleurs)

**Interfaces:**
- Consumes: `HarvestSourceCreateInput.intervalMinutes?: number`,
  `HarvestSourcePatchInput.intervalMinutes?: number`,
  `HarvestSource.intervalMinutes: number | null` (`shell/src/api/types.ts`).
- Produces: rien de nouveau côté API — champ déjà servi.

- [ ] **Step 1 : confirmer l'absence de test existant**

```bash
find shell/src/shell -iname "*Harvest*test*"
```

Expected: aucun résultat. Si un résultat apparaît, l'étendre plutôt que d'en
créer un nouveau.

- [ ] **Step 2 : écrire le test de `CreateHarvestSourcePanel` (avant le code)**

```tsx
// shell/src/shell/CreateHarvestSourcePanel.test.tsx
import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, test, vi } from "vitest";
import { CreateHarvestSourcePanel } from "./CreateHarvestSourcePanel";

const mutateAsync = vi.fn().mockResolvedValue(undefined);
vi.mock("../api/hooks", () => ({
  useCreateHarvestSource: () => ({ mutateAsync, isPending: false, isError: false }),
  useInstanceInfo: () => ({ data: { readOnly: false } }),
}));

describe("CreateHarvestSourcePanel — intervalMinutes", () => {
  test("un intervalle renseigné est transmis à la création", async () => {
    render(<CreateHarvestSourcePanel onClose={() => {}} />);
    fireEvent.change(screen.getByLabelText("URL"), { target: { value: "https://x" } });
    fireEvent.change(screen.getByLabelText(/Intervalle/), { target: { value: "30" } });
    fireEvent.click(screen.getByText("Enregistrer"));
    await vi.waitFor(() =>
      expect(mutateAsync).toHaveBeenCalledWith(
        expect.objectContaining({ intervalMinutes: 30 }),
      ),
    );
  });

  test("un intervalle vide n'est pas transmis (undefined, pas 0/NaN)", async () => {
    render(<CreateHarvestSourcePanel onClose={() => {}} />);
    fireEvent.change(screen.getByLabelText("URL"), { target: { value: "https://x" } });
    fireEvent.click(screen.getByText("Enregistrer"));
    await vi.waitFor(() => expect(mutateAsync).toHaveBeenCalled());
    expect(mutateAsync.mock.calls[0][0]).not.toHaveProperty("intervalMinutes");
  });
});
```

- [ ] **Step 3 : lancer le test, vérifier qu'il échoue (champ absent)**

```bash
cd shell && npx vitest run src/shell/CreateHarvestSourcePanel.test.tsx
```

Expected: `getByLabelText(/Intervalle/)` lève (élément introuvable).

- [ ] **Step 4 : ajouter le champ dans `CreateHarvestSourcePanel.tsx`**

```tsx
const [intervalMinutes, setIntervalMinutes] = useState("");
// ...
await createSource.mutateAsync({
  type, url, mode, enabled: true,
  ...(intervalMinutes ? { intervalMinutes: Number(intervalMinutes) } : {}),
});
```

Champ rendu juste après « Mode » :

```tsx
<label className="flex flex-col gap-1 text-sm text-ink">
  Intervalle de rafraîchissement (minutes)
  <Input
    aria-label="Intervalle de rafraîchissement (minutes)"
    type="number"
    min={1}
    value={intervalMinutes}
    onChange={(e) => setIntervalMinutes(e.target.value)}
  />
</label>
```

- [ ] **Step 5 : lancer le test, vérifier qu'il passe**

```bash
cd shell && npx vitest run src/shell/CreateHarvestSourcePanel.test.tsx
```

- [ ] **Step 6 : même patron pour `EditHarvestSourcePanel` — écrire le test d'abord**

```tsx
// shell/src/shell/EditHarvestSourcePanel.test.tsx
import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, test, vi } from "vitest";
import { EditHarvestSourcePanel } from "./EditHarvestSourcePanel";

const mutateAsync = vi.fn().mockResolvedValue(undefined);
vi.mock("../api/hooks", () => ({
  useUpdateHarvestSource: () => ({ mutateAsync, isPending: false, isError: false }),
  useInstanceInfo: () => ({ data: { readOnly: false } }),
}));

const SOURCE = {
  id: "s1", type: "stac" as const, url: "https://x", mode: "reference" as const,
  enabled: true, intervalMinutes: 45, lastRunAt: null, lastStatus: null, lastError: null,
};

describe("EditHarvestSourcePanel — intervalMinutes", () => {
  test("l'intervalle existant est pré-rempli et modifiable", async () => {
    render(<EditHarvestSourcePanel source={SOURCE} onClose={() => {}} />);
    expect(screen.getByLabelText(/Intervalle/)).toHaveValue(45);
    fireEvent.change(screen.getByLabelText(/Intervalle/), { target: { value: "10" } });
    fireEvent.click(screen.getByText("Enregistrer"));
    await vi.waitFor(() =>
      expect(mutateAsync).toHaveBeenCalledWith(
        expect.objectContaining({ intervalMinutes: 10 }),
      ),
    );
  });
});
```

- [ ] **Step 7 : lancer, vérifier l'échec, puis ajouter le champ dans `EditHarvestSourcePanel.tsx`**

```tsx
const [intervalMinutes, setIntervalMinutes] = useState(
  source.intervalMinutes != null ? String(source.intervalMinutes) : "",
);
// submit :
await updateSource.mutateAsync({
  url, enabled,
  ...(intervalMinutes ? { intervalMinutes: Number(intervalMinutes) } : {}),
});
```

Même bloc JSX que l'étape 4, juste après le champ « Actif ».

- [ ] **Step 8 : lancer les 2 fichiers de test**

```bash
cd shell && npx vitest run src/shell/CreateHarvestSourcePanel.test.tsx src/shell/EditHarvestSourcePanel.test.tsx
```

- [ ] **Step 9 : suite complète shell + E2E moissonnage**

```bash
cd shell && npm run test
cd shell && npx playwright test harvest-
```

- [ ] **Step 10 : commit**

```bash
git add shell/src/shell/CreateHarvestSourcePanel.tsx shell/src/shell/EditHarvestSourcePanel.tsx \
  shell/src/shell/CreateHarvestSourcePanel.test.tsx shell/src/shell/EditHarvestSourcePanel.test.tsx
git commit -m "$(cat <<'EOF'
feat(shell): expose intervalMinutes dans les panneaux de source de moissonnage

Le champ existait déjà côté API/types (HarvestSourceCreateInput/
PatchInput) mais aucun des deux formulaires ne le rendait — seul un
appel API direct pouvait activer la planification périodique (GAP-44).
EOF
)"
```

---

## Task 2 (GAP-49) : avertissement proactif sur un binding de collection hors périmètre

Indépendant, petit. Le filtre proactif existe déjà pour les **nouvelles**
sélections (`permittedDataSources`, `generatedPropsPanel.tsx:8-14`, livré par
SP-8b) — le manque réel est plus étroit que ce que dit le GAP : un binding
**déjà écrit** hors périmètre (permissions resserrées après coup, config
écrite par MCP) n'affiche aucun avertissement, seulement un `<select>` vide
silencieux.

**Files:**
- Modify: `shell/src/builder/wc/generatedPropsPanel.tsx`
- Modify: `shell/src/builder/wc/generatedPropsPanel.test.tsx`

**Interfaces:**
- Consumes: `WcWidgetManifest.permissions.collections`
  (`shell/src/builder/wc/manifest.ts`), `DataSource.layer`
  (`shell/src/api/types.ts`).
- Produces: rien de nouveau consommé ailleurs — alerte UI pure.

- [ ] **Step 1 : lire le test existant pour connaître le patron de rendu**

```bash
sed -n '1,60p' shell/src/builder/wc/generatedPropsPanel.test.tsx
```

- [ ] **Step 2 : écrire le test AVANT le code**

```tsx
test("affiche un avertissement si le binding actuel est hors périmètre déclaré", () => {
  const manifest: WcWidgetManifest = {
    id: "w1", tag: "w-1", label: "W",
    props: [{ name: "source", label: "Source", type: "dataSource" }],
    permissions: { collections: ["allowed_layer"] },
  } as WcWidgetManifest;
  const dataSources: DataSource[] = [
    { id: "ds1", type: "features", service: "core", layer: "forbidden_layer", query: {} },
  ];
  const Panel = makeGeneratedPropsPanel(manifest);
  render(<Panel props={{ source: "ds1" }} dataSources={dataSources} onChange={() => {}} />);
  expect(screen.getByRole("alert")).toHaveTextContent(/hors de ses permissions déclarées/);
});

test("n'affiche aucun avertissement si le binding actuel est permis", () => {
  const manifest: WcWidgetManifest = {
    id: "w1", tag: "w-1", label: "W",
    props: [{ name: "source", label: "Source", type: "dataSource" }],
    permissions: { collections: ["allowed_layer"] },
  } as WcWidgetManifest;
  const dataSources: DataSource[] = [
    { id: "ds1", type: "features", service: "core", layer: "allowed_layer", query: {} },
  ];
  const Panel = makeGeneratedPropsPanel(manifest);
  render(<Panel props={{ source: "ds1" }} dataSources={dataSources} onChange={() => {}} />);
  expect(screen.queryByRole("alert")).not.toBeInTheDocument();
});
```

- [ ] **Step 3 : lancer, vérifier l'échec (pas d'alerte aujourd'hui)**

```bash
cd shell && npx vitest run src/builder/wc/generatedPropsPanel.test.tsx -t "hors périmètre"
```

- [ ] **Step 4 : ajouter la détection + l'alerte dans `generatedPropsPanel.tsx`**

```tsx
function boundOutsidePermissions(
  value: string,
  dataSources: DataSource[],
  manifest: WcWidgetManifest,
): boolean {
  const perm = manifest.permissions;
  if (!perm || perm.collections === "all" || !value) return false;
  const source = dataSources.find((ds) => ds.id === value);
  if (!source) return false;
  return !new Set(perm.collections).has(source.layer);
}
```

Dans le rendu de la branche `dataSource` :

```tsx
p.type === "dataSource" ? (
  <div key={p.name} className="flex flex-col gap-1">
    <DataSourceSelect
      value={String(props[p.name] ?? "")}
      dataSources={permittedDataSources(dataSources, manifest)}
      onChange={(id) => onChange({ ...props, [p.name]: id })}
    />
    {boundOutsidePermissions(String(props[p.name] ?? ""), dataSources, manifest) && (
      <p role="alert" className="text-xs text-danger">
        Cette source est hors de ses permissions déclarées — la sauvegarde
        échouera tant qu'une source autorisée n'est pas choisie.
      </p>
    )}
  </div>
) : ( /* ... */ )
```

- [ ] **Step 5 : lancer les 2 nouveaux tests, vérifier qu'ils passent**

```bash
cd shell && npx vitest run src/builder/wc/generatedPropsPanel.test.tsx
```

- [ ] **Step 6 : suite complète shell**

```bash
cd shell && npm run test
```

- [ ] **Step 7 : commit**

```bash
git add shell/src/builder/wc/generatedPropsPanel.tsx shell/src/builder/wc/generatedPropsPanel.test.tsx
git commit -m "$(cat <<'EOF'
feat(shell): avertit d'un binding de widget hors permissions déclarées

permittedDataSources() filtrait déjà les nouvelles sélections (SP-8b)
mais un binding déjà écrit hors périmètre (permissions resserrées
après coup, config écrite par MCP) n'affichait aucun signal avant
l'échec de sauvegarde côté cœur (ExtensionPermissionError, GAP-49).
EOF
)"
```

---

## Task 3 (GAP-43) : sélecteur de secret pour les connecteurs pipeline

Prérequis de la Tâche 4 (canal email de l'alerte réutilise le même
composant). Le coffre de secrets existe déjà en entier côté cœur
(`core/app/secrets/routes.py`, 3 routes admin-only) — cette tâche n'ajoute
qu'un marqueur de format + une UI de sélection/création, aucune route
nouvelle côté secrets eux-mêmes.

**Files:**
- Modify: `core/app/pipelines/ops/schemas.py` (marqueur `format`)
- Test: `core/tests/test_pipeline_ops_catalog.py` (existant probable — à
  vérifier son nom exact avant de l'étendre, ne pas supposer)
- Create: `shell/src/api/domains/secrets.ts`, `secrets.hooks.ts`,
  `shell/src/builder/pipeline/SecretParamSelect.tsx`
- Modify: `shell/src/builder/pipeline/PipelineNodeInspector.tsx`
- Test: `shell/src/builder/pipeline/SecretParamSelect.test.tsx`,
  `shell/src/builder/pipeline/PipelineNodeInspector.test.tsx`

**Interfaces:**
- Consumes: `GET/POST/DELETE /secrets` (`core/app/secrets/routes.py`,
  `ConnectorSecretOut = {id, name, kind, createdAt, updatedAt}`),
  `SecretPayload` (union à 6 variantes, `core/app/secrets/schemas.py`).
- Produces: `shell/src/api/domains/secrets.ts::createSecretsMethods` (patron
  identique aux 11 domaines déjà découpés), `SecretParamSelect` consommé par
  `PipelineNodeInspector` (cette tâche) et `AlertRuleEditor` (Tâche 4).

- [ ] **Step 1 : localiser le test existant du catalogue d'ops côté cœur**

```bash
grep -rln "ops_catalog\|paramsSchema" core/tests/*.py
```

- [ ] **Step 2 : écrire le test du marqueur de format (avant le changement)**

```python
# ajout dans le fichier trouvé au Step 1
def test_reader_connector_rest_secret_name_has_secret_name_format() -> None:
    schema = ops_catalog()["reader.connector.rest"]["paramsSchema"]
    assert schema["properties"]["secretName"]["format"] == "secret-name"

def test_reader_connector_postgres_secret_name_has_secret_name_format() -> None:
    schema = ops_catalog()["reader.connector.postgres"]["paramsSchema"]
    assert schema["properties"]["secretName"]["format"] == "secret-name"
```

- [ ] **Step 3 : lancer, vérifier l'échec (`format` absent aujourd'hui)**

```bash
cd core && uv run pytest tests/<fichier_trouvé_step_1> -k secret_name_format -v
```

- [ ] **Step 4 : ajouter le marqueur dans `core/app/pipelines/ops/schemas.py`**

```python
class ReaderConnectorRestParams(BaseModel):
    # ...
    secretName: str | None = Field(default=None, json_schema_extra={"format": "secret-name"})

class ReaderConnectorPostgresParams(BaseModel):
    secretName: str = Field(..., json_schema_extra={"format": "secret-name"})
    query: str
```

- [ ] **Step 5 : lancer le test, vérifier qu'il passe**

```bash
cd core && uv run pytest tests/<fichier> -k secret_name_format -v
```

- [ ] **Step 6 : régénérer OpenAPI + types TS (diff attendu, pas vide cette fois)**

```bash
cd core && PYTHONPATH=. \
  CORE_SECRETS_MASTER_KEY="AAECAwQFBgcICQoLDA0ODxAREhMUFRYXGBkaGxwdHh8=" \
  uv run python scripts/export_openapi.py openapi.json
cd ../shell && npm run gen:api-types
git diff core/openapi.json shell/src/api/generated/core-schema.d.ts
```

Expected: diff limité au champ `format` des deux schémas de paramètres.

- [ ] **Step 7 : écrire le test du domaine `secrets.ts` côté shell (avant de l'écrire)**

```ts
// shell/src/api/domains/secrets.test.ts (ou intégré à itemClient.test.ts,
// selon le patron déjà en place pour les 11 domaines SP-43 — vérifier lequel
// avant de créer un nouveau fichier)
test("listSecrets GET /secrets", async () => {
  mockFetch({ method: "GET", path: "/secrets", json: [{ id: "s1", name: "arcgis-key", kind: "api_key", createdAt: "t", updatedAt: "t" }] });
  const result = await makeClient().listSecrets();
  expect(result).toEqual([{ id: "s1", name: "arcgis-key", kind: "api_key", createdAt: "t", updatedAt: "t" }]);
});

test("createSecret POST /secrets", async () => {
  mockFetch({ method: "POST", path: "/secrets", json: { id: "s2", name: "n", kind: "bearer_token", createdAt: "t", updatedAt: "t" } });
  const result = await makeClient().createSecret({ name: "n", payload: { kind: "bearer_token", token: "x" } });
  expect(result.id).toBe("s2");
});

test("deleteSecret DELETE /secrets/{id}", async () => {
  mockFetch({ method: "DELETE", path: "/secrets/s1", status: 204 });
  await makeClient().deleteSecret("s1");
});
```

Suivre exactement le patron de mock déjà utilisé par un domaine existant
(ex. `shell/src/api/domains/alerts.ts` + ses tests dans
`itemClient.test.ts`) — vérifier lequel avant d'écrire, ne pas deviner la
forme de `mockFetch`.

- [ ] **Step 8 : lancer, vérifier l'échec (domaine inexistant)**

```bash
cd shell && npx vitest run -t "listSecrets\|createSecret\|deleteSecret"
```

- [ ] **Step 9 : créer `shell/src/api/domains/secrets.ts` + `secrets.hooks.ts`**

```ts
// shell/src/api/domains/secrets.ts
import type { ItemClientBase } from "../base";

export type SecretSummary = { id: string; name: string; kind: string; createdAt: string; updatedAt: string };
export type SecretPayload =
  | { kind: "api_key"; location: "header" | "query"; key: string; value: string }
  | { kind: "bearer_token"; token: string }
  | { kind: "basic_auth"; username: string; password: string }
  | { kind: "oauth2_client_credentials"; tokenUrl: string; clientId: string; clientSecret: string }
  | { kind: "postgres_dsn"; dsn: string }
  | { kind: "smtp"; host: string; port: number; username: string; password: string; useTls: boolean; fromAddress: string };

type SecretsMethods = {
  listSecrets(): Promise<SecretSummary[]>;
  createSecret(input: { name: string; payload: SecretPayload }): Promise<SecretSummary>;
  deleteSecret(id: string): Promise<void>;
};

export function createSecretsMethods(base: ItemClientBase): SecretsMethods {
  const { request } = base;
  return {
    listSecrets: () => request<SecretSummary[]>("GET", "/secrets"),
    createSecret: (input) => request<SecretSummary>("POST", "/secrets", input),
    deleteSecret: (id) => request<void>("DELETE", `/secrets/${id}`),
  };
}
```

Câbler dans le point de composition final d'`itemClient.ts` (même patron que
les 11 domaines déjà composés par SP-43 — lire la fin du fichier pour le
point d'assemblage exact avant d'ajouter celui-ci).

```ts
// shell/src/api/domains/secrets.hooks.ts
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useItemClient as useItemClientInternal } from "../ItemClientProvider";
import type { SecretPayload } from "./secrets";

export function useListSecrets() {
  const client = useItemClientInternal();
  return useQuery({ queryKey: ["secrets"], queryFn: () => client.listSecrets() });
}

export function useCreateSecret() {
  const client = useItemClientInternal();
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (input: { name: string; payload: SecretPayload }) => client.createSecret(input),
    onSuccess: () => void qc.invalidateQueries({ queryKey: ["secrets"] }),
  });
}

export function useDeleteSecret() {
  const client = useItemClientInternal();
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => client.deleteSecret(id),
    onSuccess: () => void qc.invalidateQueries({ queryKey: ["secrets"] }),
  });
}
```

- [ ] **Step 10 : lancer les tests du domaine, vérifier qu'ils passent**

```bash
cd shell && npx vitest run -t "listSecrets\|createSecret\|deleteSecret"
```

- [ ] **Step 11 : écrire le test de `SecretParamSelect` (avant le composant)**

```tsx
// shell/src/builder/pipeline/SecretParamSelect.test.tsx
test("liste les secrets existants filtrés par kind", () => {
  vi.mocked(useListSecrets).mockReturnValue({
    data: [
      { id: "s1", name: "arcgis", kind: "api_key", createdAt: "", updatedAt: "" },
      { id: "s2", name: "pg", kind: "postgres_dsn", createdAt: "", updatedAt: "" },
    ],
  } as never);
  render(<SecretParamSelect ariaLabel="secretName" value="" kindFilter="postgres_dsn" onChange={() => {}} />);
  expect(screen.getByText("pg")).toBeInTheDocument();
  expect(screen.queryByText("arcgis")).not.toBeInTheDocument();
});

test("un nouveau secret créé est immédiatement sélectionné", async () => {
  // ... simuler l'ouverture du formulaire "Créer un secret", la soumission,
  // vérifier onChange appelé avec l'id du secret créé.
});
```

- [ ] **Step 12 : lancer, vérifier l'échec (composant inexistant)**

- [ ] **Step 13 : créer `SecretParamSelect.tsx` (patron `CollectionParamSelect.tsx`)**

```tsx
// shell/src/builder/pipeline/SecretParamSelect.tsx
import { useState } from "react";
import { useCreateSecret, useListSecrets } from "../../api/domains/secrets.hooks";
import type { SecretPayload } from "../../api/domains/secrets";

// Filtre d'affichage : ne montre jamais le payload déchiffré (le cœur ne
// le retourne de toute façon jamais, ConnectorSecretOut = {id,name,kind,
// createdAt,updatedAt}) — même discipline documentée par
// core/app/secrets/routes.py.
export function SecretParamSelect({
  value, onChange, ariaLabel, kindFilter,
}: {
  value: string; onChange: (name: string) => void; ariaLabel: string;
  kindFilter?: SecretPayload["kind"];
}) {
  const secretsQuery = useListSecrets();
  const createSecret = useCreateSecret();
  const [creating, setCreating] = useState(false);
  const options = (secretsQuery.data ?? []).filter((s) => !kindFilter || s.kind === kindFilter);

  return (
    <div className="flex flex-col gap-1">
      <select aria-label={ariaLabel} className="h-9 rounded-md border border-rule bg-surface px-2 text-sm text-ink"
        value={value} onChange={(e) => onChange(e.target.value)}>
        <option value="">Choisir…</option>
        {options.map((s) => <option key={s.id} value={s.name}>{s.name}</option>)}
      </select>
      <button type="button" className="w-fit text-xs text-accent hover:underline" onClick={() => setCreating(true)}>
        Créer un secret
      </button>
      {creating && (
        <SecretCreateForm
          kindFilter={kindFilter}
          onCreated={(name) => { onChange(name); setCreating(false); }}
          onCancel={() => setCreating(false)}
          createSecret={createSecret}
        />
      )}
    </div>
  );
}
```

`SecretCreateForm` (composant interne, même fichier ou fichier voisin) : champ
« Nom », un `<select>` de `kind` (limité à `kindFilter` si fourni, sinon les 6
variantes), puis les champs propres à la variante choisie (patron identique à
`renderControl` de `PipelineNodeInspector` — un formulaire minimal, pas un
générateur JSON Schema complet, les 6 variantes sont fixes et connues).

- [ ] **Step 14 : lancer les tests de `SecretParamSelect`, vérifier qu'ils passent**

```bash
cd shell && npx vitest run src/builder/pipeline/SecretParamSelect.test.tsx
```

- [ ] **Step 15 : câbler dans `PipelineNodeInspector.renderControl`**

```tsx
// AVANT prop.enum (pour rester cohérent avec l'ordre existant : format
// spécifique d'abord, enum ensuite, type générique en dernier)
if (prop.format === "secret-name") {
  return (
    <SecretParamSelect
      key={name}
      ariaLabel={name}
      value={String(params[name] ?? "")}
      onChange={(v) => setField(name, v)}
    />
  );
}
```

- [ ] **Step 16 : test caractéristique — un champ `format: "secret-name"` rend un `SecretParamSelect`, pas un input texte**

Ajouter dans `PipelineNodeInspector.test.tsx`, même patron que le test
existant `"a collection-id format field renders a CollectionParamSelect"`
(ligne 51) :

```tsx
test("a secret-name format field renders a SecretParamSelect", async () => {
  // ... opEntry avec paramsSchema.properties.secretName.format === "secret-name"
  render(<PipelineNodeInspector ... />);
  expect(screen.getByLabelText("secretName")).toBeInTheDocument();
  // vérifier que c'est bien un <select> (SecretParamSelect), pas un <input type="text">
});
```

- [ ] **Step 17 : lancer, vérifier l'échec puis le succès après le Step 15**

```bash
cd shell && npx vitest run src/builder/pipeline/PipelineNodeInspector.test.tsx
```

- [ ] **Step 18 : suite complète cœur + shell**

```bash
cd core && uv run pytest
cd shell && npm run test
```

- [ ] **Step 19 : commit**

```bash
git add core/app/pipelines/ops/schemas.py core/openapi.json \
  shell/src/api/generated/core-schema.d.ts \
  shell/src/api/domains/secrets.ts shell/src/api/domains/secrets.hooks.ts \
  shell/src/builder/pipeline/SecretParamSelect.tsx \
  shell/src/builder/pipeline/PipelineNodeInspector.tsx \
  shell/src/builder/pipeline/SecretParamSelect.test.tsx \
  shell/src/builder/pipeline/PipelineNodeInspector.test.tsx
git commit -m "$(cat <<'EOF'
feat(core,shell): sélecteur de secret pour les connecteurs pipeline

secretName était un simple champ texte libre (GAP-43) — le coffre de
secrets existait déjà en entier côté cœur (SP-15e) mais aucune UI shell
ne permettait de créer/lister un secret. Marqueur format="secret-name"
sur les 2 schémas de connecteur REST/Postgres, nouveau domaine
secrets.ts/hooks, SecretParamSelect câblé dans PipelineNodeInspector.
EOF
)"
```

---

## Task 4 (GAP-50) : parité `AlertRuleEditor` / `ReportScheduleEditor`

Dépend de la Tâche 3 (`SecretParamSelect`, réutilisé pour `smtpSecretName`).

**Files:**
- Modify: `shell/src/builder/AlertRuleEditor.tsx`,
  `shell/src/builder/AlertRuleEditor.test.tsx`

**Interfaces:**
- Consumes: `AlertChannel` (union `webhook`/`email`, `shell/src/api/types.ts:878-879`),
  `ANALYTICS_AGGREGATES`/`aggregateNeedsP`/`DEFAULT_PERCENTILE`
  (`shell/src/builder/aggregates.ts`), `SecretParamSelect` (Tâche 3).
- Produces: rien de nouveau consommé ailleurs — enrichissement du formulaire
  de création existant.

- [ ] **Step 1 : lire le test existant pour connaître le patron de mock des hooks**

```bash
sed -n '1,60p' shell/src/builder/AlertRuleEditor.test.tsx
```

- [ ] **Step 2 : écrire les tests AVANT le changement — canal email**

```tsx
test("le canal email envoie AlertChannelEmail avec smtpSecretName choisi via SecretParamSelect", async () => {
  render(<AlertRuleEditor datasetItemId="d1" owner="alice" />);
  fireEvent.change(screen.getByLabelText("Nom de la règle"), { target: { value: "R" } });
  fireEvent.change(screen.getByLabelText("Condition (expression)"), { target: { value: "value > 1" } });
  fireEvent.change(screen.getByLabelText("Canal"), { target: { value: "email" } });
  fireEvent.change(screen.getByLabelText("Destinataire"), { target: { value: "a@b.c" } });
  fireEvent.change(screen.getByLabelText("secretName"), { target: { value: "smtp-prod" } });
  fireEvent.click(screen.getByText("Créer la règle"));
  await vi.waitFor(() =>
    expect(mutateAsync).toHaveBeenCalledWith(
      expect.objectContaining({
        alert: expect.objectContaining({
          channels: [{ kind: "email", to: "a@b.c", smtpSecretName: "smtp-prod" }],
        }),
      }),
    ),
  );
});
```

- [ ] **Step 3 : écrire le test AVANT le changement — requête configurable**

```tsx
test("la requête envoyée reflète agg/field/p choisis, pas {agg:'count'} figé", async () => {
  render(<AlertRuleEditor datasetItemId="d1" owner="alice" />);
  fireEvent.change(screen.getByLabelText("Agrégat"), { target: { value: "percentile" } });
  fireEvent.change(screen.getByLabelText("Champ"), { target: { value: "amount" } });
  fireEvent.change(screen.getByLabelText("Centile"), { target: { value: "90" } });
  // ... remplir nom/condition/webhook minimal
  fireEvent.click(screen.getByText("Créer la règle"));
  await vi.waitFor(() =>
    expect(mutateAsync).toHaveBeenCalledWith(
      expect.objectContaining({
        alert: expect.objectContaining({ query: { agg: "percentile", field: "amount", p: 90 } }),
      }),
    ),
  );
});
```

- [ ] **Step 4 : lancer, vérifier l'échec des 2 nouveaux tests**

```bash
cd shell && npx vitest run src/builder/AlertRuleEditor.test.tsx -t "canal email\|requête envoyée"
```

- [ ] **Step 5 : réécrire `AlertRuleEditor.tsx` — état de requête et de canal**

```tsx
import { ANALYTICS_AGGREGATES, aggregateNeedsP, DEFAULT_PERCENTILE } from "./aggregates";
import { SecretParamSelect } from "./pipeline/SecretParamSelect";
import type { AlertChannel } from "../api/types";

// dans le composant, remplacer webhookUrl par :
const [channel, setChannel] = useState<AlertChannel>({ kind: "webhook", url: "" });
const [agg, setAgg] = useState("count");
const [field, setField] = useState("");
const [p, setP] = useState(DEFAULT_PERCENTILE);

// handleCreate() :
const query: Record<string, unknown> = { agg };
if (field) query.field = field;
if (aggregateNeedsP(agg)) query.p = p;
await createRule.mutateAsync({
  title: name, owner,
  alert: {
    datasetItemId, query, condition: { expr },
    refreshPolicy: refreshPolicy ?? { enabled: true, cron: "*/15 * * * *" },
    channels: [channel],
    messageTemplate: "Alert {ruleName}: value={value} ({state})",
  },
});
```

Rendu — canal (même patron `<select>` que `ReportScheduleEditor.tsx:32-45`,
copié presque à l'identique) :

```tsx
<label className="flex flex-col gap-1 text-xs">
  Canal
  <select aria-label="Canal" className="h-8 rounded border border-rule bg-surface px-2 text-ink"
    value={channel.kind}
    onChange={(e) =>
      setChannel(e.target.value === "webhook" ? { kind: "webhook", url: "" } : { kind: "email", to: "", smtpSecretName: "" })
    }>
    <option value="webhook">Webhook</option>
    <option value="email">E-mail</option>
  </select>
</label>
{channel.kind === "webhook" && (
  <label className="flex flex-col gap-1 text-xs">
    URL du webhook
    <input aria-label="URL du webhook" className="h-8 rounded border border-rule bg-surface px-2 text-ink"
      value={channel.url} onChange={(e) => setChannel({ kind: "webhook", url: e.target.value })} />
  </label>
)}
{channel.kind === "email" && (
  <>
    <label className="flex flex-col gap-1 text-xs">
      Destinataire
      <input aria-label="Destinataire" className="h-8 rounded border border-rule bg-surface px-2 text-ink"
        value={channel.to}
        onChange={(e) => setChannel({ kind: "email", to: e.target.value, smtpSecretName: channel.smtpSecretName })} />
    </label>
    <SecretParamSelect ariaLabel="secretName" kindFilter="smtp" value={channel.smtpSecretName}
      onChange={(v) => setChannel({ kind: "email", to: channel.to, smtpSecretName: v })} />
  </>
)}
```

Rendu — requête (patron `DataSourcePanel.tsx:161-193`, réduit à un seul
triplet, pas de liste de mesures) :

```tsx
<label className="flex flex-col gap-1 text-xs">
  Agrégat
  <select aria-label="Agrégat" className="h-8 rounded border border-rule bg-surface px-2 text-ink"
    value={agg} onChange={(e) => setAgg(e.target.value)}>
    {ANALYTICS_AGGREGATES.map((a) => <option key={a.value} value={a.value}>{a.label}</option>)}
  </select>
</label>
{agg !== "count" && (
  <label className="flex flex-col gap-1 text-xs">
    Champ
    <input aria-label="Champ" className="h-8 rounded border border-rule bg-surface px-2 text-ink"
      value={field} onChange={(e) => setField(e.target.value)} />
  </label>
)}
{aggregateNeedsP(agg) && (
  <label className="flex flex-col gap-1 text-xs">
    Centile
    <input aria-label="Centile" type="number" className="h-8 rounded border border-rule bg-surface px-2 text-ink"
      value={p} onChange={(e) => setP(Number(e.target.value))} />
  </label>
)}
```

- [ ] **Step 6 : lancer les 2 nouveaux tests + toute la suite du fichier**

```bash
cd shell && npx vitest run src/builder/AlertRuleEditor.test.tsx
```

- [ ] **Step 7 : suite complète shell + E2E si une spec couvre `AlertRuleEditor`**

```bash
cd shell && npm run test
grep -rl "AlertRuleEditor\|Alertes" shell/e2e/*.spec.ts
# si un résultat : npx playwright test <le fichier trouvé>
```

- [ ] **Step 8 : commit**

```bash
git add shell/src/builder/AlertRuleEditor.tsx shell/src/builder/AlertRuleEditor.test.tsx
git commit -m "$(cat <<'EOF'
feat(shell): AlertRuleEditor gagne le canal email et une requête configurable

Jusqu'ici figé sur webhook + {agg:"count"} (GAP-50, F-shell-builder-04),
très en retrait par rapport à ReportScheduleEditor. Réutilise le patron
canal de ReportScheduleEditor et le triplet agg/field/p déjà éprouvé
par DataSourcePanel — smtpSecretName passe par SecretParamSelect
(Tâche 3) plutôt qu'un texte libre.
EOF
)"
```

---

## Task 5 (GAP-48) : outils MCP `create_alert_rule` / `run_alert_rule`

Indépendant des tâches précédentes.

**Files:**
- Modify: `core/app/mcp/tools/alerts.py`
- Modify: `core/tests/test_mcp_tools_alert.py`,
  `core/tests/test_mcp_rest_parity.py`

**Interfaces:**
- Consumes: `app.configs.service.create_config_service` (déjà réutilisée par
  `create_pipeline`), `app.alerts.repository.create_evaluation`,
  `app.alerts.jobs.evaluate_alert_task`.
- Produces: 2 tools MCP nouveaux, montés inconditionnellement (comme
  `explain_alert_rule` aujourd'hui — pas de garde `CORE_ETL_ENABLED`, les
  alertes n'y sont pas soumises).

- [ ] **Step 1 : lire `mcp/tools/pipelines.py` en entier pour le patron exact à reproduire**

```bash
cat core/app/mcp/tools/pipelines.py
```

- [ ] **Step 2 : écrire le test de `create_alert_rule` (avant le tool)**

```python
# core/tests/test_mcp_tools_alert.py
async def test_create_alert_rule_creates_a_config_kind_alert(mcp_session):
    result = await call_tool(mcp_session, "create_alert_rule", {
        "title": "R1",
        "datasetItemId": dataset_item_id,
        "query": {"agg": "count"},
        "condition": {"expr": "value > 10"},
        "refreshPolicy": {"enabled": True, "cron": "*/15 * * * *"},
        "channels": [{"kind": "webhook", "url": "https://example.test"}],
        "messageTemplate": "x",
    })
    assert result["resourceType"] == "alert"
    # vérifier en base : configs_repo.get_config_by_item(...).kind == "alert"
```

- [ ] **Step 3 : lancer, vérifier l'échec (tool inexistant)**

```bash
cd core && uv run pytest tests/test_mcp_tools_alert.py -k create_alert_rule -v
```

- [ ] **Step 4 : écrire le test de `run_alert_rule` (avant le tool)**

```python
async def test_run_alert_rule_creates_a_pending_evaluation_and_defers(mcp_session, monkeypatch):
    deferred = []
    monkeypatch.setattr(
        "app.alerts.jobs.evaluate_alert_task.defer",
        lambda **kw: deferred.append(kw),
    )
    result = await call_tool(mcp_session, "run_alert_rule", {"alertRuleId": alert_item_id})
    assert "evaluationId" in result
    assert deferred == [{"evaluation_id": result["evaluationId"], "tenant_id": tenant.id}]
```

- [ ] **Step 5 : lancer, vérifier l'échec**

- [ ] **Step 6 : implémenter les 2 tools dans `core/app/mcp/tools/alerts.py`**

```python
from app.alerts import jobs as alerts_jobs
from app.configs.schemas import AlertRulePayload, BuilderConfig
from app.configs.service import create_config_service
from app.items.schemas import ItemRead

def register(server: FastMCP, session_factory) -> None:
    @server.tool()
    async def explain_alert_rule(...):
        ...  # inchangé

    @server.tool()
    async def create_alert_rule(
        ctx: Context, title: str, datasetItemId: str, query: dict,
        condition: dict, refreshPolicy: dict, channels: list[dict],
        messageTemplate: str = "Alert {ruleName}: value={value} ({state})",
    ) -> ItemRead:
        """Create an AlertRule — mirrors POST /configs with kind="alert".
        Registered unconditionally (alerts are not gated by
        CORE_ETL_ENABLED). SP-53."""
        access_token = get_access_token()
        with request_scoped_session(session_factory) as session:
            user = resolve_actor(session, access_token)
            payload = AlertRulePayload(
                datasetItemId=datasetItemId, query=query, condition=condition,
                refreshPolicy=refreshPolicy, channels=channels, messageTemplate=messageTemplate,
            )
            config = BuilderConfig(version=1, kind="alert", alert=payload)
            try:
                created = create_config_service(session, config, title=title, user=user)
            except HTTPException as exc:
                raise http_exception_to_value_error(exc) from exc
            write_audit(session, tenant_id=user.tenant_id, actor_id=user.id, actor_kind="agent",
                        action="item.create", object_type="item", object_id=created.item.id,
                        payload={"title": title})
            write_audit(session, tenant_id=user.tenant_id, actor_id=user.id, actor_kind="agent",
                        action="config.create", object_type="config", object_id=created.config.id,
                        payload={"title": title, "kind": "alert"})
            result = items_repo.get_item(session, tenant_id=user.tenant_id, item_id=created.item.id,
                                          current_user_id=user.id)
            assert result is not None
            return without_thumbnail_url(result)

    @server.tool()
    async def run_alert_rule(ctx: Context, alertRuleId: str) -> dict:
        """Defer an immediate evaluation of an AlertRule — mirrors, for a
        single rule, what sweep_alert_rules_task does for all due rules.
        No REST route equivalent exists (evaluation is periodic-only via
        REST); this is the MCP-only manual trigger. SP-53."""
        access_token = get_access_token()
        with request_scoped_session(session_factory) as session:
            user = resolve_actor(session, access_token)
            config = configs_repo.get_config_by_item(session, alertRuleId)
            if config is None or config.config.kind != "alert":
                raise ValueError("alert rule not found")
            facts = items_repo.get_access_facts(session, tenant_id=user.tenant_id, item_id=alertRuleId)
            if facts is None or not can(session, user_id=user.id, action="read", item=facts):
                raise ValueError("alert rule not found")
            evaluation = alerts_repo.create_evaluation(
                session, tenant_id=user.tenant_id, alert_rule_item_id=alertRuleId,
            )
            session.commit()
            alerts_jobs.evaluate_alert_task.defer(
                evaluation_id=evaluation.id, tenant_id=user.tenant_id,
            )
            return {"evaluationId": evaluation.id}
```

Importer les symboles supplémentaires nécessaires en tête de fichier
(`http_exception_to_value_error`, `without_thumbnail_url`, `HTTPException`,
`write_audit` — vérifier lesquels manquent réellement avant d'ajouter des
imports inutilisés).

- [ ] **Step 7 : lancer les 2 tests, vérifier qu'ils passent**

```bash
cd core && uv run pytest tests/test_mcp_tools_alert.py -v
```

- [ ] **Step 8 : étendre le test de parité MCP↔REST**

Ajouter le cas alerte à `core/tests/test_mcp_rest_parity.py` (créé par
SP-43 Étape 8) — comparer l'effet observable de `run_alert_rule` (une ligne
`AlertEvaluation` `pending`, un déféré sur `evaluate_alert_task`) à celui
d'un passage de `sweep_alert_rules_task` limité à cette seule règle
(mocker `list_due_rules` pour ne renvoyer que cette règle, comparer l'état
avant/après).

```bash
cd core && uv run pytest tests/test_mcp_rest_parity.py -v
```

- [ ] **Step 9 : suite complète cœur**

```bash
cd core && uv run pytest
```

- [ ] **Step 10 : régénération OpenAPI (diff vide attendu — aucune route REST ne change, seulement des tools MCP)**

```bash
cd core && PYTHONPATH=. \
  CORE_SECRETS_MASTER_KEY="AAECAwQFBgcICQoLDA0ODxAREhMUFRYXGBkaGxwdHh8=" \
  uv run python scripts/export_openapi.py openapi.json
git diff core/openapi.json
```

- [ ] **Step 11 : commit**

```bash
git add core/app/mcp/tools/alerts.py core/tests/test_mcp_tools_alert.py core/tests/test_mcp_rest_parity.py
git commit -m "$(cat <<'EOF'
feat(core): create_alert_rule/run_alert_rule côté MCP

explain_alert_rule était le seul tool du domaine (GAP-48), contrairement
au pipeline (create/run/explain). create_alert_rule mirrors POST
/configs kind=alert ; run_alert_rule reproduit, pour une seule règle,
ce que sweep_alert_rules_task fait pour toutes les règles dues — pas de
route REST "exécuter maintenant" équivalente, MCP-only.
EOF
)"
```

---

## Task 6 (GAP-24, cœur) : modèle, service et routes du déclenchement webhook

Le chantier le plus gros. **Vérification obligatoire avant de commencer**
(cf. spec §6.1) : confirmer par lecture directe que
`run_pipeline_service()` (`core/app/pipelines/service.py`) est bien
inchangé depuis la spec — c'est le point de passage que cette tâche
réutilise, jamais qu'elle ne duplique.

**Files:**
- Create: `core/alembic/versions/0035_pipeline_webhook_tokens.py`
- Modify: `core/app/pipelines/models.py`, `core/app/pipelines/repository.py`,
  `core/app/pipelines/service.py`, `core/app/pipelines/routes.py`,
  `core/app/ratelimit/limiter.py`
- Test: `core/tests/test_pipeline_webhook_tokens.py` (nouveau),
  `core/tests/test_model_alembic_parity.py` (doit rester vert),
  `core/tests/test_pipeline_routes.py` (étendu)

**Interfaces:**
- Consumes: `app.jobs.common.resolve_owner_user`,
  `app.pipelines.service.run_pipeline_service` (réutilisé tel quel, seul
  `actor_kind="webhook"` diffère), `app.roles.guards.require_privilege`,
  `Privilege.AUTOMATION_SECRETS_MANAGE` (orphelin jusqu'ici, `REV-097`).
- Produces: `PipelineWebhookToken` (modèle), 4 routes REST, un nouveau
  groupe de rate limiting `"webhook-trigger"`.

- [ ] **Step 1 : relire `run_pipeline_service` et `run_pipeline_sweep_task` en entier, confirmer qu'ils divergent bien comme décrit (spec §6.1)**

```bash
cat core/app/pipelines/service.py
sed -n '1,50p;180,210p' core/app/pipelines/jobs.py
```

Confirmer : `run_pipeline_sweep_task` ne passe **pas** par
`run_pipeline_service` — si ce constat a changé depuis l'écriture de la
spec, arrêter et documenter l'écart avant de continuer (ne pas supposer).

- [ ] **Step 2 : écrire le test du modèle + migration (avant de les créer)**

```python
# core/tests/test_pipeline_webhook_tokens.py — partie modèle
def test_pipeline_webhook_token_table_matches_migrated_schema(throwaway_database_url):
    # même patron que test_model_alembic_parity.py, ciblé sur cette seule table
    ...

def test_token_hash_is_unique_across_tenants(pg_engine):
    # deux insertions avec le même token_hash doivent violer une contrainte unique
    ...
```

- [ ] **Step 3 : lancer, vérifier l'échec (table inexistante)**

```bash
cd core && uv run pytest tests/test_pipeline_webhook_tokens.py -v
```

- [ ] **Step 4 : ajouter le modèle dans `core/app/pipelines/models.py`**

```python
class PipelineWebhookToken(Base):
    __tablename__ = "pipeline_webhook_tokens"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id"), nullable=False)
    pipeline_item_id: Mapped[str] = mapped_column(ForeignKey("items.id"), nullable=False)
    token_hash: Mapped[str] = mapped_column(String, nullable=False, unique=True)
    created_by: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
```

- [ ] **Step 5 : écrire la migration `0035` (patron `0031_notifications.py`)**

```python
# core/alembic/versions/0035_pipeline_webhook_tokens.py
revision = "0035"
down_revision = "0034"

def upgrade() -> None:
    op.create_table(
        "pipeline_webhook_tokens",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("tenant_id", sa.String(), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("pipeline_item_id", sa.String(), sa.ForeignKey("items.id"), nullable=False),
        sa.Column("token_hash", sa.String(), nullable=False, unique=True),
        sa.Column("created_by", sa.String(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("last_used_at", sa.DateTime(), nullable=True),
    )
    op.create_index(
        "ix_pipeline_webhook_tokens_pipeline",
        "pipeline_webhook_tokens", ["tenant_id", "pipeline_item_id"],
    )

def downgrade() -> None:
    op.drop_index("ix_pipeline_webhook_tokens_pipeline", table_name="pipeline_webhook_tokens")
    op.drop_table("pipeline_webhook_tokens")
```

- [ ] **Step 6 : tester la migration dans les 2 sens sur base non vide (piège CLAUDE.md n°8)**

```bash
cd core && uv run pytest tests/test_pipeline_webhook_tokens.py -v
```

- [ ] **Step 7 : vérifier `test_model_alembic_parity.py` reste vert (le nouveau modèle ne doit créer aucun écart)**

```bash
cd core && uv run pytest tests/test_model_alembic_parity.py -v
```

- [ ] **Step 8 : écrire les tests du service (avant de l'écrire)**

```python
def test_create_webhook_token_returns_cleartext_once_and_persists_only_hash(...):
    ...
    assert token_row.token_hash != raw_token
    assert hashlib.sha256(raw_token.encode()).hexdigest() == token_row.token_hash

def test_trigger_by_webhook_calls_run_pipeline_service_not_a_parallel_path(monkeypatch, ...):
    calls = []
    monkeypatch.setattr(
        "app.pipelines.service.run_pipeline_service",
        lambda *a, **kw: calls.append(kw) or "run-1",
    )
    run_id = trigger_pipeline_by_webhook_service(session, item_id=pk, raw_token=raw, defer_task=noop)
    assert run_id == "run-1"
    assert calls[0]["actor_kind"] == "webhook"

def test_trigger_with_unknown_token_raises_404_never_leaks_existence():
    ...

def test_trigger_with_token_for_a_different_pipeline_id_raises_404():
    ...
```

- [ ] **Step 9 : lancer, vérifier l'échec**

- [ ] **Step 10 : implémenter le service dans `core/app/pipelines/service.py`**

```python
import hashlib
import secrets as py_secrets

from app.jobs.common import resolve_owner_user
from app.pipelines.models import PipelineWebhookToken
from app.roles.privileges import Privilege


def _hash_token(raw_token: str) -> str:
    return hashlib.sha256(raw_token.encode()).hexdigest()


def create_webhook_token_service(
    session: Session, *, user: User, item_id: str
) -> tuple[PipelineWebhookToken, str]:
    require_pipeline_access(session, user=user, item_id=item_id, action="write")
    require_privilege(session, user, Privilege.AUTOMATION_SECRETS_MANAGE.value)
    raw_token = py_secrets.token_urlsafe(32)
    token = pipelines_repo.create_webhook_token(
        session, tenant_id=user.tenant_id, pipeline_item_id=item_id,
        token_hash=_hash_token(raw_token), created_by=user.id,
    )
    write_audit(session, tenant_id=user.tenant_id, actor_id=user.id, actor_kind="user",
                action="pipeline.webhook_token.create", object_type="pipeline_webhook_token",
                object_id=token.id, payload={"pipelineItemId": item_id})
    session.commit()
    return token, raw_token


def revoke_webhook_token_service(session: Session, *, user: User, item_id: str, token_id: str) -> None:
    require_pipeline_access(session, user=user, item_id=item_id, action="write")
    token = pipelines_repo.get_webhook_token(session, tenant_id=user.tenant_id, token_id=token_id)
    if token is None or token.pipeline_item_id != item_id:
        raise HTTPException(status_code=404, detail="webhook token not found")
    pipelines_repo.delete_webhook_token(session, token)
    write_audit(session, tenant_id=user.tenant_id, actor_id=user.id, actor_kind="user",
                action="pipeline.webhook_token.delete", object_type="pipeline_webhook_token",
                object_id=token_id, payload={"pipelineItemId": item_id})
    session.commit()


def trigger_pipeline_by_webhook_service(
    session: Session, *, item_id: str, raw_token: str, defer_task: Callable[[str, str], None],
) -> str:
    token = pipelines_repo.get_webhook_token_by_hash(session, token_hash=_hash_token(raw_token))
    if token is None or token.pipeline_item_id != item_id:
        raise HTTPException(status_code=404, detail="pipeline not found")
    owner = resolve_owner_user(session, tenant_id=token.tenant_id, item_id=token.pipeline_item_id)
    run_id = run_pipeline_service(
        session, user=owner, item_id=token.pipeline_item_id, defer_task=defer_task, actor_kind="webhook",
    )
    pipelines_repo.touch_webhook_token(session, token)
    return run_id
```

Ajouter les 5 fonctions correspondantes dans
`core/app/pipelines/repository.py` (`create_webhook_token`,
`get_webhook_token`, `get_webhook_token_by_hash`, `delete_webhook_token`,
`touch_webhook_token`, `list_webhook_tokens_for_pipeline`) — patron déjà
connu (`create_run`/`get_run`/`list_runs` du même fichier).

- [ ] **Step 11 : lancer les tests du service, vérifier qu'ils passent**

```bash
cd core && uv run pytest tests/test_pipeline_webhook_tokens.py -v
```

- [ ] **Step 12 : écrire les tests des 4 routes (avant de les écrire)**

```python
def test_post_webhook_tokens_requires_automation_secrets_manage_privilege(...):
    ...  # utilisateur sans le privilège -> 403

def test_post_webhook_tokens_returns_cleartext_token_once(...):
    resp = client.post(f"/pipelines/{pk}/webhook-tokens")
    assert "token" in resp.json()

def test_get_webhook_tokens_never_returns_token_or_hash(...):
    resp = client.get(f"/pipelines/{pk}/webhook-tokens")
    for row in resp.json():
        assert "token" not in row and "tokenHash" not in row

def test_trigger_route_has_no_get_current_user_dependency(...):
    # sans en-tête Authorization du tout -> 401/404, jamais une redirection OIDC
    resp = client.post(f"/pipelines/{pk}/trigger")
    assert resp.status_code in (401, 404)

def test_trigger_route_runs_the_pipeline_with_a_valid_token(...):
    resp = client.post(f"/pipelines/{pk}/trigger", headers={"Authorization": f"Bearer {raw_token}"})
    assert resp.status_code == 202
    assert "runId" in resp.json()

def test_trigger_route_rejects_a_revoked_token(...):
    ...

def test_pipelines_trigger_route_absent_when_etl_disabled(...):
    # même garde is_etl_enabled() que le reste du routeur
```

- [ ] **Step 13 : lancer, vérifier l'échec**

- [ ] **Step 14 : implémenter les 4 routes dans `core/app/pipelines/routes.py`**

```python
from fastapi import Header

class WebhookTokenCreated(BaseModel):
    id: str
    token: str
    createdAt: str

class WebhookTokenSummary(BaseModel):
    id: str
    createdAt: str
    lastUsedAt: str | None

@router.post("/pipelines/{item_id}/webhook-tokens", response_model=WebhookTokenCreated, status_code=201)
def create_webhook_token_route(
    item_id: str, session: Session = Depends(get_session), user: User = Depends(get_current_user),
) -> WebhookTokenCreated:
    token, raw = create_webhook_token_service(session, user=user, item_id=item_id)
    return WebhookTokenCreated(id=token.id, token=raw, createdAt=token.created_at.isoformat())

@router.get("/pipelines/{item_id}/webhook-tokens", response_model=list[WebhookTokenSummary])
def list_webhook_tokens_route(
    item_id: str, session: Session = Depends(get_session), user: User = Depends(get_current_user),
) -> list[WebhookTokenSummary]:
    require_pipeline_access(session, user=user, item_id=item_id, action="read")
    rows = pipelines_repo.list_webhook_tokens_for_pipeline(session, tenant_id=user.tenant_id, pipeline_item_id=item_id)
    return [
        WebhookTokenSummary(id=r.id, createdAt=r.created_at.isoformat(),
                             lastUsedAt=r.last_used_at.isoformat() if r.last_used_at else None)
        for r in rows
    ]

@router.delete("/pipelines/{item_id}/webhook-tokens/{token_id}", status_code=204)
def delete_webhook_token_route(
    item_id: str, token_id: str, session: Session = Depends(get_session), user: User = Depends(get_current_user),
) -> None:
    revoke_webhook_token_service(session, user=user, item_id=item_id, token_id=token_id)

@router.post("/pipelines/{item_id}/trigger", response_model=RunResponse, status_code=202)
def trigger_pipeline_webhook_route(
    item_id: str,
    authorization: str | None = Header(default=None),
    session: Session = Depends(get_session),
    defer_task: Callable[[str, str], None] = Depends(get_task_deferrer),
) -> RunResponse:
    """Seule route de tout le dépôt sans Depends(get_current_user) — un
    appelant externe (CI, capteur) n'a pas de session OIDC. Le secret
    bearer remplace entièrement l'authentification OIDC pour cette route
    précise ; SP-53/GAP-24."""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="missing bearer token")
    raw_token = authorization.removeprefix("Bearer ")
    run_id = trigger_pipeline_by_webhook_service(
        session, item_id=item_id, raw_token=raw_token, defer_task=defer_task,
    )
    return RunResponse(runId=run_id)
```

- [ ] **Step 15 : ajouter le groupe de rate limiting dans `core/app/ratelimit/limiter.py`**

```python
_WEBHOOK_TRIGGER_RE = re.compile(r"^/pipelines/[^/]+/trigger$")

_BUDGETS = {
    "sql": 10, "llm": 20, "jobs": 15, "harvest": 10,
    "webhook-trigger": 30,  # cf. spec SP-53 §7, question ouverte sur le budget exact
}

def route_group(path: str, method: str, export_path_re: re.Pattern[str]) -> str | None:
    if _SQL_RE.match(path):
        return "sql"
    if _LLM_RE.match(path):
        return "llm"
    if export_path_re.match(path):
        return "jobs"
    if _HARVEST_RE.match(path) and method != "GET":
        return "harvest"
    if _WEBHOOK_TRIGGER_RE.match(path) and method == "POST":
        return "webhook-trigger"
    return None
```

- [ ] **Step 16 : lancer les tests des routes + du rate limiter**

```bash
cd core && uv run pytest tests/test_pipeline_routes.py tests/test_ratelimit.py -v
```

(nom exact du fichier de test du rate limiter à vérifier — `grep -rl
RateLimiter core/tests/*.py` avant de supposer `test_ratelimit.py`.)

- [ ] **Step 17 : suite complète cœur**

```bash
cd core && uv run pytest
```

- [ ] **Step 18 : mettre à jour le conteneur `postgis-test` si utilisé en session locale (piège CLAUDE.md)**

- [ ] **Step 19 : régénérer OpenAPI + types TS (diff non vide attendu — 4 nouvelles routes)**

```bash
cd core && PYTHONPATH=. \
  CORE_SECRETS_MASTER_KEY="AAECAwQFBgcICQoLDA0ODxAREhMUFRYXGBkaGxwdHh8=" \
  uv run python scripts/export_openapi.py openapi.json
cd ../shell && npm run gen:api-types
```

- [ ] **Step 20 : grep de clôture — confirmer qu'aucun 2e chemin d'exécution de pipeline n'a été créé**

```bash
grep -n "pipelines_repo.create_run\|run_pipeline_task.defer" core/app/pipelines/*.py
```

Expected : exactement 2 sites (`jobs.py::run_pipeline_sweep_task`, déjà
existant, et `service.py::run_pipeline_service`, réutilisé par REST/MCP/
webhook) — si un 3e site apparaît, la Tâche a dupliqué le chemin
d'exécution au lieu de le réutiliser, cf. spec §6.1.

- [ ] **Step 21 : commit**

```bash
git add core/alembic/versions/0035_pipeline_webhook_tokens.py \
  core/app/pipelines/models.py core/app/pipelines/repository.py \
  core/app/pipelines/service.py core/app/pipelines/routes.py \
  core/app/ratelimit/limiter.py core/tests/test_pipeline_webhook_tokens.py \
  core/openapi.json shell/src/api/generated/core-schema.d.ts
git commit -m "$(cat <<'EOF'
feat(core): déclenchement de pipeline par webhook entrant (GAP-24)

PipelineWebhookToken (migration 0035) : jeton bearer haché en base,
jamais relisible après sa création. POST /pipelines/{id}/trigger est
la seule route du dépôt sans Depends(get_current_user) — le secret
bearer remplace l'authentification OIDC pour cette route précise.
Réutilise run_pipeline_service (REST/MCP) tel quel avec
actor_kind="webhook", jamais un 3e chemin d'exécution parallèle au
balayage cron. La génération/révocation de jeton exige désormais
Privilege.AUTOMATION_SECRETS_MANAGE — referme un des deux privilèges
orphelins de REV-097 en sous-produit de cette tâche.
EOF
)"
```

---

## Task 7 (GAP-24, shell) : panneau de gestion des jetons de déclenchement

Dépend de la Tâche 6 (routes REST).

**Files:**
- Modify: `shell/src/api/domains/pipelines.ts`, `pipelines.hooks.ts`
- Create: `shell/src/builder/pipeline/PipelineWebhookTrigger.tsx`,
  `PipelineWebhookTrigger.test.tsx`
- Modify: `shell/src/pages/PipelineBuilderPage.tsx`

**Interfaces:**
- Consumes: `POST/GET/DELETE /pipelines/{id}/webhook-tokens` (Tâche 6).
- Produces: `usePipelineWebhookTokens`, `useCreatePipelineWebhookToken`,
  `useRevokePipelineWebhookToken`, consommés par `PipelineBuilderPage.tsx`.

- [ ] **Step 1 : écrire le test du domaine pipelines étendu (avant le code)**

```ts
test("listPipelineWebhookTokens GET /pipelines/{id}/webhook-tokens", async () => { ... });
test("createPipelineWebhookToken POST retourne le jeton en clair", async () => { ... });
test("revokePipelineWebhookToken DELETE", async () => { ... });
```

- [ ] **Step 2 : lancer, vérifier l'échec**

- [ ] **Step 3 : étendre `shell/src/api/domains/pipelines.ts` + `pipelines.hooks.ts`**

```ts
// pipelines.ts
export type PipelineWebhookToken = { id: string; createdAt: string; lastUsedAt: string | null };

listPipelineWebhookTokens: (pk: string) => request<PipelineWebhookToken[]>("GET", `/pipelines/${pk}/webhook-tokens`),
createPipelineWebhookToken: (pk: string) => request<{ id: string; token: string; createdAt: string }>("POST", `/pipelines/${pk}/webhook-tokens`),
revokePipelineWebhookToken: (pk: string, tokenId: string) => request<void>("DELETE", `/pipelines/${pk}/webhook-tokens/${tokenId}`),
```

```ts
// pipelines.hooks.ts
export function usePipelineWebhookTokens(pk: string) {
  const client = useItemClientInternal();
  return useQuery({ queryKey: ["pipeline-webhook-tokens", pk], queryFn: () => client.listPipelineWebhookTokens(pk) });
}
export function useCreatePipelineWebhookToken(pk: string) {
  const client = useItemClientInternal();
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => client.createPipelineWebhookToken(pk),
    onSuccess: () => void qc.invalidateQueries({ queryKey: ["pipeline-webhook-tokens", pk] }),
  });
}
export function useRevokePipelineWebhookToken(pk: string) {
  const client = useItemClientInternal();
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (tokenId: string) => client.revokePipelineWebhookToken(pk, tokenId),
    onSuccess: () => void qc.invalidateQueries({ queryKey: ["pipeline-webhook-tokens", pk] }),
  });
}
```

- [ ] **Step 4 : lancer les tests du domaine, vérifier qu'ils passent**

- [ ] **Step 5 : écrire le test de `PipelineWebhookTrigger` (avant le composant)**

```tsx
test("le jeton généré s'affiche une seule fois avec un avertissement", async () => {
  vi.mocked(useCreatePipelineWebhookToken).mockReturnValue({
    mutateAsync: vi.fn().mockResolvedValue({ id: "t1", token: "clear-value", createdAt: "" }),
    isPending: false,
  } as never);
  render(<PipelineWebhookTrigger pipelineId="p1" />);
  fireEvent.click(screen.getByText("Générer un jeton"));
  await screen.findByText("clear-value");
  expect(screen.getByText(/ne sera plus jamais affiché/)).toBeInTheDocument();
});

test("liste les jetons existants et permet la révocation", async () => {
  vi.mocked(usePipelineWebhookTokens).mockReturnValue({
    data: [{ id: "t1", createdAt: "2026-09-01T00:00:00Z", lastUsedAt: null }],
  } as never);
  render(<PipelineWebhookTrigger pipelineId="p1" />);
  expect(screen.getByText(/t1/)).toBeInTheDocument();
  fireEvent.click(screen.getByLabelText("Révoquer t1"));
  // vérifier l'appel de la mutation de révocation
});
```

- [ ] **Step 6 : lancer, vérifier l'échec (composant inexistant)**

- [ ] **Step 7 : implémenter `PipelineWebhookTrigger.tsx`**

```tsx
export function PipelineWebhookTrigger({ pipelineId }: { pipelineId: string }) {
  const tokensQuery = usePipelineWebhookTokens(pipelineId);
  const createToken = useCreatePipelineWebhookToken(pipelineId);
  const revokeToken = useRevokePipelineWebhookToken(pipelineId);
  const [justCreated, setJustCreated] = useState<{ id: string; token: string } | null>(null);

  return (
    <div className="flex flex-col gap-2 border-t border-rule pt-2 text-xs">
      <p className="font-medium text-ink-2">Déclenchement par webhook</p>
      {(tokensQuery.data ?? []).map((t) => (
        <div key={t.id} className="flex items-center justify-between">
          <span>{t.id.slice(0, 8)}… — créé le {t.createdAt}</span>
          <button type="button" aria-label={`Révoquer ${t.id.slice(0, 8)}`}
            onClick={() => void revokeToken.mutateAsync(t.id)}>
            Révoquer
          </button>
        </div>
      ))}
      <Button type="button" variant="outline" size="sm" onClick={async () => {
        const result = await createToken.mutateAsync();
        setJustCreated(result);
      }}>
        Générer un jeton
      </Button>
      {justCreated && (
        <div role="status" className="flex flex-col gap-1 rounded border border-rule bg-surface p-2">
          <p className="font-mono">{justCreated.token}</p>
          <p className="text-danger">
            Ce jeton ne sera plus jamais affiché — copiez-le maintenant.
          </p>
          <p className="font-mono text-ink-2">
            POST {"{coreBaseUrl}"}/pipelines/{pipelineId}/trigger — en-tête
            Authorization: Bearer {justCreated.token}
          </p>
        </div>
      )}
    </div>
  );
}
```

- [ ] **Step 8 : lancer les tests, vérifier qu'ils passent**

```bash
cd shell && npx vitest run src/builder/pipeline/PipelineWebhookTrigger.test.tsx
```

- [ ] **Step 9 : câbler dans `PipelineBuilderPage.tsx`, juste après le bloc `PipelineScheduleEditor` (lignes 220-228)**

```tsx
{pk !== null && (
  <>
    <p className="mb-1 mt-3 text-xs font-medium text-ink-2">Planification</p>
    <PipelineScheduleEditor value={draft.refreshPolicy ?? null} onChange={setRefreshPolicy} />
    <PipelineWebhookTrigger pipelineId={pk} />
  </>
)}
```

- [ ] **Step 10 : suite complète shell + E2E pipeline**

```bash
cd shell && npm run test
cd shell && npx playwright test pipeline
```

- [ ] **Step 11 : E2E complète (VITE_AUTH_MODE=mock) — dernière tâche du plan, filet complet obligatoire**

```bash
cd shell && npm run e2e
cd core && uv run pytest
```

- [ ] **Step 12 : commit**

```bash
git add shell/src/api/domains/pipelines.ts shell/src/api/domains/pipelines.hooks.ts \
  shell/src/builder/pipeline/PipelineWebhookTrigger.tsx \
  shell/src/builder/pipeline/PipelineWebhookTrigger.test.tsx \
  shell/src/pages/PipelineBuilderPage.tsx
git commit -m "$(cat <<'EOF'
feat(shell): panneau de gestion des jetons de déclenchement webhook

Génération (affiche le jeton en clair une seule fois, avec avertissement
explicite), liste et révocation, sous le pipeline (section
"Déclenchement par webhook", juste après "Planification"). Clôt GAP-24.
EOF
)"
```
