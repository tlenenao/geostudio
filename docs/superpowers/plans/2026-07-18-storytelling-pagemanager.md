# Storytelling — mode narratif sur `PageManager` : plan d'implémentation

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Un auteur active un mode « story » sur une app existante, associe à chaque
page/chapitre une action de navigation (`map.flyTo` vers une emprise), et obtient une
narration séquencée (barre de progression + Précédent/Suivant) — sans nouveau widget,
sans nouveau backend, sans code.

**Architecture:** Shell quasi exclusivement. Deux nouveaux champs de config, tous deux
optionnels et rétrocompatibles : `AppConfig.navigationMode?: "tabs" | "story"` (défaut
`"tabs"`) et `Page.onEnter?: ActionMessage[]` (messages déclenchés à l'entrée du
chapitre). Le rendu story vit dans `AppRenderer` (barre de progression + Précédent/
Suivant, dispatch des `onEnter` de la page active en preview/runtime) ; l'édition dans
un nouveau panneau `NavigationPanel` du builder. Le seul changement cœur est la
**déclaration Pydantic** de ces champs, pour ne pas répéter la régression silencieuse de
SP-5b (un champ non déclaré est supprimé au round-trip `model_validate`/`model_dump`).

**Tech Stack:** React 18 + TypeScript (shell), Vitest + Testing Library, Playwright
(E2E), FastAPI + Pydantic v2 (cœur), pytest.

## Global Constraints

- **Rétrocompatibilité stricte** : une config `version: 1` sans `navigationMode` ni
  `onEnter` se comporte **exactement** comme aujourd'hui (mode `tabs`, aucune barre de
  progression, aucun dispatch d'`onEnter`). Test de non-régression explicite obligatoire.
- **Aucun nouveau widget, aucun nouveau modèle de permission, aucun nouvel endpoint.**
- **Aucune écriture cœur nouvelle** : seule `core/app/configs/schemas.py` change (déclaration
  de champs). Ne pas répéter la régression SP-5b : tout nouveau champ de config **doit** être
  déclaré côté Pydantic, prouvé par un test de round-trip.
- **Les `onEnter` d'une page ne ciblent que des widgets présents sur cette même page** :
  l'action est câblée quand la page devient active et que ses widgets sont montés.
- Code/identifiants en anglais ; libellés UI et messages en français.
- En-tête SPDX `// SPDX-License-Identifier: Apache-2.0` (TS) / `# SPDX-License-Identifier: Apache-2.0`
  (Python) en tête de **tout nouveau fichier**.
- Vérifier en fin de branche : `cd shell && npm run test && npm run build` verts,
  `cd core && uv run pytest` vert, `npm run e2e` vert.

---

## Contexte technique vérifié (lire avant de commencer)

Ces faits ont été établis en lisant le code au moment de la rédaction du plan. Ils
corrigent deux optimismes de la spec (`docs/superpowers/specs/2026-07-14-storytelling-pagemanager-design.md`) :

1. **Il n'y a pas de « menu d'onglets » automatique à remplacer.** Au runtime, la
   navigation entre pages passe par un **widget Navigation** posé sur le canvas
   (`shell/src/builder/widgets/navigation.tsx`) + la route `/apps/{pk}/{pageId}`
   (`shell/src/pages/AppRuntimePage.tsx`). `AppRenderer` ne rend que le layout de la page
   active. Donc le mode story n'enlève rien : il **ajoute** une barre de progression +
   Précédent/Suivant qui pilotent `handleNavigate` (déjà présent dans `AppRenderer`).

2. **`ActionsPanel` n'est PAS réutilisable tel quel pour `onEnter`** (contrairement à ce
   que dit la spec §3). `ActionsPanel` est centré émetteur : sélecteurs « Widget émetteur »
   / « Événement » + filtre `resolvesOnThisPage(m.from)`. Pour `onEnter`, l'émetteur est la
   page (pas un widget). On écrit donc un `NavigationPanel` focalisé qui réutilise les
   **primitives** (sélection de widget cible, sélection d'action, validation `when` via
   `validateExpression`), pas le composant entier. Déviation assumée et documentée.

3. **Un message `onEnter` a besoin d'un payload statique.** Le mécanisme `ActionBus` route
   `emit(widgetId, event, payload)` → appelle `actions.get(\`${to} ${action}\`)(payload)`,
   où `payload` vient de l'émetteur runtime. Une carte reçoit son centre via ce payload
   (`centerFromPayload` dans `mapWidget.tsx` lit `{ center: [lon, lat] }` ou une géométrie
   Point). Un chapitre story n'a **pas** d'émetteur runtime : l'emprise cible est statique,
   configurée par l'auteur. Il faut donc un champ `payload?` sur le message `onEnter`
   (le `flyTo` de `mapWidget` accepte `{ center: [lon, lat] }`, il volera à `zoom: 12`).
   `ActionMessage` gagne un `payload?` optionnel (ignoré par les messages de wiring
   existants — aucun changement de comportement pour eux).

**Formes exactes en jeu :**

- `shell/src/api/types.ts` :
  - `ActionMessage = { id; from; event; to; action; when? }` (ligne ~265).
  - `Page = { id; name; layout: AppLayout }` (ligne ~173).
  - `AppConfig` (ligne ~290).
  - `RenderMode = "edit" | "preview" | "runtime"` (ligne 153).
- `shell/src/builder/ActionBus.ts` : `emit`, `configure`, `register`, `setContext`,
  `context: ExprContext`, `evaluateExpression(when, { ...context, record })`.
- `shell/src/builder/pages.ts` : `getPages(config)`, `getPageLayout`, `setPageLayout`.
- `shell/src/builder/AppRenderer.tsx` : `handleNavigate(nextPageId)`, `const pages =
  getPages(config)`, `const activePageId = pageId ?? internalPageId ?? pages[0].id`.
- `mapWidget` (`shell/src/builder/widgets/mapWidget.tsx`) : `events: ["extentChanged",
  "itemSelected"]`, `actions: ["flyTo", "highlight"]`, `flyTo` lit `{ center: [lon, lat] }`.
- `core/app/configs/schemas.py` : `class Page`, `class Message` (alias `from`), `class
  BuilderConfig`.

---

## Task 1 : Cœur — déclarer `navigationMode`, `Page.onEnter`, `Message.payload`

**Files:**
- Modify: `core/app/configs/schemas.py`
- Test: `core/tests/test_schemas.py`

**Interfaces:**
- Produces: `BuilderConfig.navigationMode: Literal["tabs", "story"]` (défaut `"tabs"`) ;
  `Page.onEnter: list[Message]` (défaut `[]`) ; `Message.payload: dict | None` (défaut
  `None`). Ces champs survivent au round-trip `model_validate` → `model_dump(by_alias=True)`.

- [ ] **Step 1: Écrire les tests qui échouent**

Dans `core/tests/test_schemas.py`, ajouter à la fin :

```python
def test_navigation_mode_round_trips():
    payload = _valid_payload("app")
    payload["navigationMode"] = "story"
    config = BuilderConfig.model_validate(payload)
    assert config.navigationMode == "story"
    dumped = config.model_dump(by_alias=True)
    assert dumped["navigationMode"] == "story"


def test_navigation_mode_defaults_to_tabs():
    config = BuilderConfig.model_validate(_valid_payload("app"))
    assert config.navigationMode == "tabs"


def test_navigation_mode_rejects_unknown_value():
    payload = _valid_payload("app")
    payload["navigationMode"] = "carousel"
    with pytest.raises(ValidationError):
        BuilderConfig.model_validate(payload)


def test_page_on_enter_round_trips_with_payload():
    payload = _valid_payload("app")
    payload["pages"] = [
        {
            "id": "p1",
            "name": "Chapitre 1",
            "layout": payload["layout"],
            "onEnter": [
                {
                    "id": "oe1",
                    "from": "p1",
                    "event": "enter",
                    "to": "map",
                    "action": "flyTo",
                    "payload": {"center": [2.35, 48.85]},
                    "when": None,
                }
            ],
        }
    ]
    config = BuilderConfig.model_validate(payload)
    assert len(config.pages[0].onEnter) == 1
    assert config.pages[0].onEnter[0].payload == {"center": [2.35, 48.85]}
    dumped = config.model_dump(by_alias=True)
    assert dumped["pages"][0]["onEnter"][0]["payload"] == {"center": [2.35, 48.85]}
    # from est bien re-sérialisé sous son alias, comme les messages de wiring
    assert dumped["pages"][0]["onEnter"][0]["from"] == "p1"


def test_page_on_enter_defaults_empty():
    payload = _valid_payload("app")
    payload["pages"] = [{"id": "p1", "name": "Chapitre 1", "layout": payload["layout"]}]
    config = BuilderConfig.model_validate(payload)
    assert config.pages[0].onEnter == []
```

- [ ] **Step 2: Lancer les tests, vérifier l'échec**

Run: `cd core && uv run pytest tests/test_schemas.py -k "navigation_mode or on_enter" -v`
Expected: FAIL — `navigationMode` inexistant (`onEnter` silencieusement absent du dump,
`config.navigationMode` lève `AttributeError`).

- [ ] **Step 3: Implémenter la déclaration Pydantic**

Dans `core/app/configs/schemas.py`, ajouter `payload` à `Message` :

```python
class Message(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    from_: str = Field(alias="from")
    event: str
    to: str
    action: str
    when: str | None = None
    payload: dict | None = None
```

Ajouter `onEnter` à `Page` :

```python
class Page(BaseModel):
    id: str
    name: str
    layout: Layout
    onEnter: list[Message] = Field(default_factory=list)
```

Ajouter `navigationMode` à `BuilderConfig` (à côté de `messages`/`pages`) :

```python
class BuilderConfig(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    version: int = 1
    itemId: str | None = None
    kind: Literal["app", "dashboard", "map"]
    theme: dict = Field(default_factory=dict)
    dataSources: list[DataSource] = Field(default_factory=list)
    layout: Layout | None = None
    messages: list[Message] = Field(default_factory=list)
    pages: list[Page] = Field(default_factory=list)
    navigationMode: Literal["tabs", "story"] = "tabs"
    variables: list[Variable] = Field(default_factory=list)
    map: MapConfig | None = None
```

- [ ] **Step 4: Lancer les tests, vérifier le succès**

Run: `cd core && uv run pytest tests/test_schemas.py -v`
Expected: PASS (les nouveaux tests + tous les existants).

- [ ] **Step 5: Commit**

```bash
git add core/app/configs/schemas.py core/tests/test_schemas.py
git commit -m "feat(core): storytelling — déclare navigationMode, Page.onEnter, Message.payload (évite la régression SP-5b)"
```

---

## Task 2 : Shell — `ActionMessage.payload` + `ActionBus.dispatch`

**Files:**
- Modify: `shell/src/api/types.ts` (type `ActionMessage`, ligne ~265)
- Modify: `shell/src/builder/ActionBus.ts`
- Test: `shell/src/builder/ActionBus.test.ts`

**Interfaces:**
- Consumes: rien de nouveau.
- Produces: `ActionMessage.payload?: Record<string, unknown>` (optionnel, rétrocompatible) ;
  `ActionBus.dispatch(messages: ActionMessage[]): void` — dispatch d'une liste fixe de
  messages (les `onEnter` d'une page), chacun avec son propre `payload` statique ; même
  évaluation de `when` (sans `record`) et même isolation try/catch que `emit`.

- [ ] **Step 1: Écrire les tests qui échouent**

Dans `shell/src/builder/ActionBus.test.ts`, ajouter à la fin :

```typescript
test("dispatch calls each message's target handler with the message's static payload", () => {
  const bus = new ActionBus();
  const fly = vi.fn();
  bus.register("map1", "flyTo", fly);
  bus.dispatch([
    { id: "oe1", from: "p1", event: "enter", to: "map1", action: "flyTo", payload: { center: [2, 48] } },
  ]);
  expect(fly).toHaveBeenCalledWith({ center: [2, 48] });
});

test("dispatch skips a message whose when condition is false", () => {
  const bus = new ActionBus();
  const fly = vi.fn();
  bus.register("map1", "flyTo", fly);
  bus.setContext({ vars: { ready: false }, user: { name: "" } });
  bus.dispatch([
    { id: "oe1", from: "p1", event: "enter", to: "map1", action: "flyTo", payload: {}, when: "vars.ready" },
  ]);
  expect(fly).not.toHaveBeenCalled();
});

test("dispatch is a no-op when no handler is registered for the target", () => {
  const bus = new ActionBus();
  expect(() =>
    bus.dispatch([{ id: "oe1", from: "p1", event: "enter", to: "ghost", action: "flyTo", payload: {} }]),
  ).not.toThrow();
});

test("dispatch isolates a throwing handler so later messages still run", () => {
  const bus = new ActionBus();
  const boom = vi.fn(() => { throw new Error("boom"); });
  const ok = vi.fn();
  bus.register("a", "x", boom);
  bus.register("b", "y", ok);
  bus.dispatch([
    { id: "1", from: "p1", event: "enter", to: "a", action: "x", payload: {} },
    { id: "2", from: "p1", event: "enter", to: "b", action: "y", payload: {} },
  ]);
  expect(ok).toHaveBeenCalled();
});
```

- [ ] **Step 2: Lancer les tests, vérifier l'échec**

Run: `cd shell && npx vitest run src/builder/ActionBus.test.ts`
Expected: FAIL — `bus.dispatch is not a function` (et erreurs de type sur `payload`).

- [ ] **Step 3: Implémenter**

Dans `shell/src/api/types.ts`, étendre `ActionMessage` :

```typescript
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
```

Dans `shell/src/builder/ActionBus.ts`, ajouter la méthode `dispatch` (après `emit`) :

```typescript
  // Dispatch a fixed list of messages (a page's onEnter) directly, bypassing the
  // wiring map. Each message carries its own static payload. Same when-evaluation
  // (no emitter record) and per-handler isolation as emit.
  dispatch(messages: ActionMessage[]): void {
    for (const m of messages) {
      if (m.when && !evaluateExpression(m.when, { ...this.context })) continue;
      try {
        this.actions.get(`${m.to} ${m.action}`)?.(m.payload);
      } catch (err) {
        console.error(`Action bus: onEnter handler for "${m.to} ${m.action}" threw`, err);
      }
    }
  }
```

- [ ] **Step 4: Lancer les tests, vérifier le succès**

Run: `cd shell && npx vitest run src/builder/ActionBus.test.ts`
Expected: PASS (nouveaux + existants).

- [ ] **Step 5: Commit**

```bash
git add shell/src/api/types.ts shell/src/builder/ActionBus.ts shell/src/builder/ActionBus.test.ts
git commit -m "feat(shell): storytelling — ActionMessage.payload + ActionBus.dispatch(onEnter)"
```

---

## Task 3 : Shell — `AppRenderer` mode story (barre de progression + dispatch onEnter)

**Files:**
- Modify: `shell/src/api/types.ts` (`AppConfig`, `Page`)
- Modify: `shell/src/builder/AppRenderer.tsx`
- Test: `shell/src/builder/AppRenderer.test.tsx`

**Interfaces:**
- Consumes: `ActionBus.dispatch` (Task 2) ; `getPages` (`pages.ts`).
- Produces: en mode `preview`/`runtime` avec `config.navigationMode === "story"`,
  `AppRenderer` rend une barre de story (texte `Chapitre {i+1} / {N}` + boutons
  `Précédent`/`Suivant`) et déclenche `bus.dispatch(page.onEnter)` à chaque changement de
  page active. En `edit` ou en mode `tabs` : comportement inchangé.

- [ ] **Step 1: Écrire les tests qui échouent**

Dans `shell/src/builder/AppRenderer.test.tsx`, ajouter (après les imports existants) un
widget cible stub qui enregistre une action `flyTo` observable, puis les tests story. Le
fichier importe déjà `registerWidget`, `_resetRegistry`, `userEvent`. Ajouter en haut du
fichier l'import du hook bus :

```typescript
import { useBusAction } from "./ActionBusContext";
```

Ajouter la spy + un helper de config story et les tests (à la fin du fichier) :

```typescript
const flySpy = vi.fn();

function registerFlyTarget() {
  registerWidget({
    type: "flytarget",
    label: "FlyTarget",
    defaultProps: {},
    defaultSize: { w: 2, h: 1 },
    actions: ["flyTo"],
    PropsPanel: () => null,
    Component: ({ ctx }) => {
      useBusAction(ctx.bus, ctx.widgetId, "flyTo", (p) => flySpy(p));
      return <div>cible</div>;
    },
  });
}

function storyConfig(): AppConfig {
  return {
    kind: "app",
    theme: {},
    dataSources: [],
    messages: [],
    navigationMode: "story",
    layout: { type: "grid", breakpoints: {}, items: [] },
    pages: [
      {
        id: "p1", name: "Intro",
        layout: { type: "grid", breakpoints: {}, items: [
          { id: "m1", widget: "flytarget", x: 0, y: 0, w: 2, h: 1, props: {} },
          { id: "txt1", widget: "text", x: 0, y: 1, w: 4, h: 1, props: { text: "Chapitre un" } },
        ] },
        onEnter: [{ id: "oe1", from: "p1", event: "enter", to: "m1", action: "flyTo", payload: { center: [1, 2] } }],
      },
      {
        id: "p2", name: "Suite",
        layout: { type: "grid", breakpoints: {}, items: [
          { id: "txt2", widget: "text", x: 0, y: 0, w: 4, h: 1, props: { text: "Chapitre deux" } },
        ] },
        onEnter: [],
      },
    ],
  };
}

test("story mode shows a progress bar and prev/next; prev is disabled on the first chapter", () => {
  registerFlyTarget();
  render(<AppRenderer config={storyConfig()} mode="runtime" />, { wrapper: Wrapper });
  expect(screen.getByText("Chapitre 1 / 2")).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Précédent" })).toBeDisabled();
  expect(screen.getByRole("button", { name: "Suivant" })).toBeEnabled();
});

test("story mode dispatches the active page's onEnter to its widget on entry", () => {
  flySpy.mockClear();
  registerFlyTarget();
  render(<AppRenderer config={storyConfig()} mode="runtime" />, { wrapper: Wrapper });
  expect(flySpy).toHaveBeenCalledWith({ center: [1, 2] });
});

test("story mode navigates to the next chapter and updates the progress counter", async () => {
  registerFlyTarget();
  render(<AppRenderer config={storyConfig()} mode="runtime" />, { wrapper: Wrapper });
  expect(screen.getByText("Chapitre un")).toBeInTheDocument();
  await userEvent.click(screen.getByRole("button", { name: "Suivant" }));
  expect(screen.getByText("Chapitre 2 / 2")).toBeInTheDocument();
  expect(screen.getByText("Chapitre deux")).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Suivant" })).toBeDisabled();
});

test("tabs-mode config (no navigationMode) shows no story chrome and no onEnter dispatch", () => {
  flySpy.mockClear();
  registerFlyTarget();
  const cfg = storyConfig();
  cfg.navigationMode = "tabs";
  render(<AppRenderer config={cfg} mode="runtime" />, { wrapper: Wrapper });
  expect(screen.queryByText(/Chapitre 1 \/ 2/)).toBeNull();
  expect(screen.queryByRole("button", { name: "Suivant" })).toBeNull();
  expect(flySpy).not.toHaveBeenCalled();
});

test("edit mode never dispatches onEnter and shows no story chrome", () => {
  flySpy.mockClear();
  registerFlyTarget();
  render(<AppRenderer config={storyConfig()} mode="edit" />, { wrapper: Wrapper });
  expect(screen.queryByRole("button", { name: "Suivant" })).toBeNull();
  expect(flySpy).not.toHaveBeenCalled();
});
```

> Note : le widget stub `flytarget` enregistre son handler `flyTo` via `useBusAction`
> **dans son Component**. React exécute les effets des enfants (le widget) avant ceux du
> parent (`AppRenderer`), donc le handler est enregistré avant que l'effet `onEnter` du
> parent ne s'exécute — le dispatch trouve toujours le handler. C'est l'ordre d'effet sur
> lequel repose ce mécanisme (documenté ici pour l'implémenteur).

- [ ] **Step 2: Lancer les tests, vérifier l'échec**

Run: `cd shell && npx vitest run src/builder/AppRenderer.test.tsx`
Expected: FAIL — pas de « Chapitre 1 / 2 », pas de bouton « Suivant », `flySpy` jamais appelé.

- [ ] **Step 3: Étendre les types**

Dans `shell/src/api/types.ts`, étendre `Page` et `AppConfig`. `Page` (ligne ~173) :

```typescript
export type Page = {
  id: string;
  name: string;
  layout: AppLayout;
  // Messages déclenchés à l'entrée du chapitre en mode story (SP storytelling).
  onEnter?: ActionMessage[];
};
```

Repérer le type `AppConfig` (ligne ~290) et lui ajouter le champ optionnel
`navigationMode` (à côté de `pages`/`messages`) :

```typescript
  navigationMode?: "tabs" | "story";
```

- [ ] **Step 4: Implémenter le rendu story dans `AppRenderer`**

Dans `shell/src/builder/AppRenderer.tsx` :

a) Remplacer `const pages = getPages(config);` (ligne ~114) par une version mémoïsée pour
que l'effet `onEnter` ne se redéclenche pas à chaque rendu :

```typescript
  const pages = useMemo(() => getPages(config), [config]);
```

b) Juste après le calcul de `activePageId`/`activeLayout` et `handleNavigate` (après la
ligne ~122), ajouter la logique story :

```typescript
  const storyMode = config.navigationMode === "story" && mode !== "edit";
  const chapterIndex = pages.findIndex((p) => p.id === activePageId);

  // À l'entrée d'un chapitre (preview/runtime, mode story), déclenche ses onEnter.
  // Ré-émis à chaque entrée, y compris en revenant en arrière — cohérent avec
  // map.flyTo qui est idempotent (comportement par défaut acté au plan).
  useEffect(() => {
    if (!storyMode) return;
    const page = pages.find((p) => p.id === activePageId);
    if (page?.onEnter && page.onEnter.length > 0) bus.dispatch(page.onEnter);
  }, [storyMode, activePageId, pages, bus]);
```

c) Envelopper le rendu pour insérer la barre de story. Remplacer le `return (...)` final
(à partir de la ligne ~130) de façon à ajouter la barre au-dessus du canvas quand
`storyMode` est vrai. Le contenu existant `<ActionBusProvider>…</ActionBusProvider>` reste
identique ; on ajoute seulement la barre avant lui :

```typescript
  return (
    <div ref={containerRef} className="flex h-full w-full flex-col bg-[var(--gs-color-background)] font-[var(--gs-font)]" style={themeToCssVars(config.theme)}>
      {storyMode && (
        <nav className="flex items-center gap-2 border-b border-[var(--gs-color-border)] p-2 text-sm">
          <button
            type="button"
            className="rounded-[var(--gs-radius)] border border-[var(--gs-color-border)] px-2 py-1 disabled:opacity-30"
            disabled={chapterIndex <= 0}
            onClick={() => handleNavigate(pages[chapterIndex - 1].id)}
          >
            Précédent
          </button>
          <span className="text-[var(--gs-color-muted)]">Chapitre {chapterIndex + 1} / {pages.length}</span>
          <button
            type="button"
            className="rounded-[var(--gs-radius)] border border-[var(--gs-color-border)] px-2 py-1 disabled:opacity-30"
            disabled={chapterIndex >= pages.length - 1}
            onClick={() => handleNavigate(pages[chapterIndex + 1].id)}
          >
            Suivant
          </button>
        </nav>
      )}
      <div className="min-h-0 flex-1">
        <ActionBusProvider bus={bus}>
          <VariablesProvider variables={config.variables ?? []}>
            <ActionConditionBridge bus={bus} />
            {(config.variables ?? []).map((v) => (
              <VariableBusBridge key={v.id} variable={v} bus={bus} />
            ))}
            <DataProvider sources={config.dataSources}>
              <GridCanvas
                items={activeLayout.items}
                breakpoint={bp}
                editable={editable}
                selectedId={selectedId}
                onSelect={(id) => onSelect?.(id)}
                onMoveItem={handleMove}
                renderItem={(item) => <WidgetHost item={item} mode={mode} pages={pages} navigate={handleNavigate} />}
              />
            </DataProvider>
          </VariablesProvider>
        </ActionBusProvider>
      </div>
    </div>
  );
```

d) S'assurer que `useEffect`, `useMemo` sont bien importés (ils le sont déjà, ligne 2).

- [ ] **Step 5: Lancer les tests, vérifier le succès**

Run: `cd shell && npx vitest run src/builder/AppRenderer.test.tsx`
Expected: PASS (nouveaux + existants — dont « runtime mode renders widgets without edit chrome »).

- [ ] **Step 6: Commit**

```bash
git add shell/src/api/types.ts shell/src/builder/AppRenderer.tsx shell/src/builder/AppRenderer.test.tsx
git commit -m "feat(shell): storytelling — AppRenderer mode story (progression + dispatch onEnter)"
```

---

## Task 4 : Shell — valider les conditions `onEnter.when`

**Files:**
- Modify: `shell/src/builder/configExpressionErrors.ts`
- Test: `shell/src/builder/configExpressionErrors.test.ts`

**Interfaces:**
- Consumes: `getPages`, `validateExpression`.
- Produces: `getConfigExpressionErrors(config)` inclut désormais les erreurs de condition
  `when` des messages `onEnter` de chaque page (préfixe `Chapitre "{name}", action {id}
  (condition) : …`). Le bouton **Enregistrer** du builder (qui lit déjà cette fonction) se
  désactive donc automatiquement sur une condition `onEnter` invalide.

- [ ] **Step 1: Écrire les tests qui échouent**

Dans `shell/src/builder/configExpressionErrors.test.ts`, ajouter :

```typescript
test("reports an invalid when condition on a page onEnter message", () => {
  const config: AppConfig = {
    kind: "app", theme: {}, dataSources: [], messages: [],
    navigationMode: "story",
    layout: { type: "grid", breakpoints: {}, items: [] },
    pages: [
      {
        id: "p1", name: "Intro",
        layout: { type: "grid", breakpoints: {}, items: [] },
        onEnter: [{ id: "oe1", from: "p1", event: "enter", to: "m1", action: "flyTo", payload: {}, when: "vars.(" }],
      },
    ],
  };
  const errors = getConfigExpressionErrors(config);
  expect(errors.some((e) => e.includes("Intro") && e.includes("oe1"))).toBe(true);
});

test("accepts a valid when condition on a page onEnter message", () => {
  const config: AppConfig = {
    kind: "app", theme: {}, dataSources: [], messages: [],
    navigationMode: "story",
    layout: { type: "grid", breakpoints: {}, items: [] },
    pages: [
      {
        id: "p1", name: "Intro",
        layout: { type: "grid", breakpoints: {}, items: [] },
        onEnter: [{ id: "oe1", from: "p1", event: "enter", to: "m1", action: "flyTo", payload: {}, when: "vars.ready" }],
      },
    ],
  };
  expect(getConfigExpressionErrors(config)).toEqual([]);
});
```

> Vérifier que le fichier de test importe déjà `AppConfig` et `getConfigExpressionErrors` ;
> sinon ajouter `import type { AppConfig } from "../api/types";` et
> `import { getConfigExpressionErrors } from "./configExpressionErrors";`.

- [ ] **Step 2: Lancer les tests, vérifier l'échec**

Run: `cd shell && npx vitest run src/builder/configExpressionErrors.test.ts`
Expected: FAIL — l'erreur `onEnter` n'est pas remontée (le premier test échoue).

- [ ] **Step 3: Implémenter**

Dans `shell/src/builder/configExpressionErrors.ts`, dans la boucle `for (const page of
getPages(config))` existante (après la boucle sur `page.layout.items`, avant sa
fermeture), ajouter la validation des `onEnter` :

```typescript
    for (const m of page.onEnter ?? []) {
      if (!m.when || typeof m.when !== "string") continue;
      const err = validateExpression(m.when);
      if (err) errors.push(`Chapitre "${page.name}", action ${m.id} (condition) : ${err}`);
    }
```

- [ ] **Step 4: Lancer les tests, vérifier le succès**

Run: `cd shell && npx vitest run src/builder/configExpressionErrors.test.ts`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add shell/src/builder/configExpressionErrors.ts shell/src/builder/configExpressionErrors.test.ts
git commit -m "feat(shell): storytelling — valide les conditions when des onEnter (désactive Enregistrer si invalide)"
```

---

## Task 5 : Shell — `NavigationPanel` + intégration dans le builder

**Files:**
- Create: `shell/src/builder/NavigationPanel.tsx`
- Create: `shell/src/builder/NavigationPanel.test.tsx`
- Modify: `shell/src/pages/AppBuilderPage.tsx`

**Interfaces:**
- Consumes: `getWidget` (`registry.ts`), `validateExpression` (`expr.ts`), types `Page`,
  `WidgetItem`, `ActionMessage`.
- Produces: composant

  ```typescript
  NavigationPanel({
    navigationMode,
    onNavigationModeChange,
    page,
    onPageChange,
  }: {
    navigationMode: "tabs" | "story";
    onNavigationModeChange: (m: "tabs" | "story") => void;
    page: Page;                       // page active en cours d'édition
    onPageChange: (page: Page) => void; // page active mise à jour (onEnter modifié)
  })
  ```

  Bascule tabs/story ; en mode story, édite les `onEnter` de la page active : liste
  (cible.action + condition + emprise), ajout (cible parmi les widgets de la page ayant des
  actions, action, longitude, latitude → `payload: { center: [lon, lat] }`), suppression.

- [ ] **Step 1: Écrire les tests qui échouent**

Créer `shell/src/builder/NavigationPanel.test.tsx` :

```tsx
// SPDX-License-Identifier: Apache-2.0
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, expect, test, vi } from "vitest";
import { NavigationPanel } from "./NavigationPanel";
import { _resetRegistry, registerBuiltinWidgets } from "./widgets";
import type { Page } from "../api/types";

beforeEach(() => {
  _resetRegistry();
  registerBuiltinWidgets();
});

function pageWithMap(): Page {
  return {
    id: "p1", name: "Intro",
    layout: { type: "grid", breakpoints: {}, items: [
      { id: "m1", widget: "map", x: 0, y: 0, w: 4, h: 3, props: {} },
    ] },
    onEnter: [],
  };
}

test("toggles the navigation mode", async () => {
  const onMode = vi.fn();
  render(
    <NavigationPanel navigationMode="tabs" onNavigationModeChange={onMode} page={pageWithMap()} onPageChange={vi.fn()} />,
  );
  await userEvent.selectOptions(screen.getByLabelText("Mode de navigation"), "story");
  expect(onMode).toHaveBeenCalledWith("story");
});

test("adds an onEnter flyTo with a center payload to the active page", async () => {
  const onPageChange = vi.fn();
  render(
    <NavigationPanel navigationMode="story" onNavigationModeChange={vi.fn()} page={pageWithMap()} onPageChange={onPageChange} />,
  );
  await userEvent.selectOptions(screen.getByLabelText("Widget cible"), "m1");
  await userEvent.selectOptions(screen.getByLabelText("Action"), "flyTo");
  await userEvent.type(screen.getByLabelText("Longitude"), "2.35");
  await userEvent.type(screen.getByLabelText("Latitude"), "48.85");
  await userEvent.click(screen.getByRole("button", { name: "Ajouter à ce chapitre" }));

  expect(onPageChange).toHaveBeenCalledTimes(1);
  const updated = onPageChange.mock.calls[0][0] as Page;
  expect(updated.onEnter).toHaveLength(1);
  expect(updated.onEnter![0]).toMatchObject({
    from: "p1", event: "enter", to: "m1", action: "flyTo", payload: { center: [2.35, 48.85] },
  });
});

test("removes an existing onEnter message", async () => {
  const onPageChange = vi.fn();
  const page: Page = {
    ...pageWithMap(),
    onEnter: [{ id: "oe1", from: "p1", event: "enter", to: "m1", action: "flyTo", payload: { center: [1, 2] } }],
  };
  render(
    <NavigationPanel navigationMode="story" onNavigationModeChange={vi.fn()} page={page} onPageChange={onPageChange} />,
  );
  await userEvent.click(screen.getByRole("button", { name: /Retirer l'action oe1/ }));
  const updated = onPageChange.mock.calls[0][0] as Page;
  expect(updated.onEnter).toHaveLength(0);
});

test("shows an inline error for an invalid when condition", async () => {
  const page: Page = {
    ...pageWithMap(),
    onEnter: [{ id: "oe1", from: "p1", event: "enter", to: "m1", action: "flyTo", payload: {}, when: "vars.(" }],
  };
  render(
    <NavigationPanel navigationMode="story" onNavigationModeChange={vi.fn()} page={page} onPageChange={vi.fn()} />,
  );
  expect(screen.getByRole("alert")).toBeInTheDocument();
});
```

- [ ] **Step 2: Lancer les tests, vérifier l'échec**

Run: `cd shell && npx vitest run src/builder/NavigationPanel.test.tsx`
Expected: FAIL — module `./NavigationPanel` introuvable.

- [ ] **Step 3: Implémenter le composant**

Créer `shell/src/builder/NavigationPanel.tsx` :

```tsx
// SPDX-License-Identifier: Apache-2.0
import { useState } from "react";
import type { ActionMessage, Page, WidgetItem } from "../api/types";
import { getWidget } from "./registry";
import { validateExpression } from "./expr";

const selectCls = "h-8 rounded border border-slate-300 bg-white text-xs";

function widgetLabel(items: WidgetItem[], id: string): string {
  const it = items.find((i) => i.id === id);
  return (it && getWidget(it.widget)?.label) || id;
}
function actionsOf(items: WidgetItem[], id: string): readonly string[] {
  return getWidget(items.find((i) => i.id === id)?.widget ?? "")?.actions ?? [];
}

export function NavigationPanel({
  navigationMode,
  onNavigationModeChange,
  page,
  onPageChange,
}: {
  navigationMode: "tabs" | "story";
  onNavigationModeChange: (m: "tabs" | "story") => void;
  page: Page;
  onPageChange: (page: Page) => void;
}) {
  const items = page.layout.items;
  const receivers = items.filter((i) => (getWidget(i.widget)?.actions?.length ?? 0) > 0);
  const onEnter = page.onEnter ?? [];
  const [to, setTo] = useState("");
  const [action, setAction] = useState("");
  const [lon, setLon] = useState("");
  const [lat, setLat] = useState("");

  function add() {
    const lonNum = Number(lon);
    const latNum = Number(lat);
    if (!to || !action || Number.isNaN(lonNum) || Number.isNaN(latNum)) return;
    const message: ActionMessage = {
      id: crypto.randomUUID(),
      from: page.id,
      event: "enter",
      to,
      action,
      payload: { center: [lonNum, latNum] },
    };
    onPageChange({ ...page, onEnter: [...onEnter, message] });
    setTo(""); setAction(""); setLon(""); setLat("");
  }
  function remove(id: string) {
    onPageChange({ ...page, onEnter: onEnter.filter((m) => m.id !== id) });
  }
  function updateWhen(id: string, when: string) {
    onPageChange({
      ...page,
      onEnter: onEnter.map((m) => (m.id === id ? { ...m, when: when || undefined } : m)),
    });
  }

  return (
    <div className="flex flex-col gap-2 text-sm">
      <label className="flex flex-col gap-1 text-xs">
        Mode de navigation
        <select
          aria-label="Mode de navigation"
          className={selectCls}
          value={navigationMode}
          onChange={(e) => onNavigationModeChange(e.target.value as "tabs" | "story")}
        >
          <option value="tabs">Onglets</option>
          <option value="story">Story (chapitres)</option>
        </select>
      </label>

      {navigationMode === "story" && (
        <>
          <p className="text-[10px] text-slate-400">Actions à l'entrée du chapitre « {page.name} ».</p>
          <ul className="flex flex-col gap-1">
            {onEnter.map((m) => {
              const when = m.when ?? "";
              const error = when ? validateExpression(when) : null;
              const center = (m.payload?.center as [number, number] | undefined);
              return (
                <li key={m.id} className="flex flex-col gap-1 rounded border border-slate-200 p-1 text-xs">
                  <div className="flex items-center justify-between">
                    <span>
                      {widgetLabel(items, m.to)}.{m.action}
                      {center ? ` → [${center[0]}, ${center[1]}]` : ""}
                    </span>
                    <button type="button" aria-label={`Retirer l'action ${m.id}`} className="text-red-600" onClick={() => remove(m.id)}>✕</button>
                  </div>
                  <input
                    aria-label={`Condition de l'action ${m.id}`}
                    placeholder="Condition (optionnel)"
                    className="h-7 rounded border border-slate-300 px-1 font-mono"
                    value={when}
                    onChange={(e) => updateWhen(m.id, e.target.value)}
                  />
                  {error && <span role="alert" className="text-red-600">{error}</span>}
                </li>
              );
            })}
            {onEnter.length === 0 && <li className="text-xs text-slate-400">Aucune action à l'entrée.</li>}
          </ul>

          <select aria-label="Widget cible" className={selectCls} value={to}
            onChange={(e) => { setTo(e.target.value); setAction(""); }}>
            <option value="">Widget cible…</option>
            {receivers.map((i) => <option key={i.id} value={i.id}>{widgetLabel(items, i.id)}</option>)}
          </select>
          <select aria-label="Action" className={selectCls} value={action} disabled={!to}
            onChange={(e) => setAction(e.target.value)}>
            <option value="">Action…</option>
            {actionsOf(items, to).map((a) => <option key={a} value={a}>{a}</option>)}
          </select>
          <div className="flex gap-1">
            <input aria-label="Longitude" placeholder="Longitude" className="h-8 w-1/2 rounded border border-slate-300 px-1 text-xs"
              value={lon} onChange={(e) => setLon(e.target.value)} />
            <input aria-label="Latitude" placeholder="Latitude" className="h-8 w-1/2 rounded border border-slate-300 px-1 text-xs"
              value={lat} onChange={(e) => setLat(e.target.value)} />
          </div>
          <button type="button" className="rounded border border-slate-300 px-2 py-1 text-sm hover:bg-slate-100" onClick={add}>
            Ajouter à ce chapitre
          </button>
        </>
      )}
    </div>
  );
}
```

- [ ] **Step 4: Lancer les tests, vérifier le succès**

Run: `cd shell && npx vitest run src/builder/NavigationPanel.test.tsx`
Expected: PASS.

- [ ] **Step 5: Intégrer dans `AppBuilderPage`**

Dans `shell/src/pages/AppBuilderPage.tsx` :

a) Ajouter l'import (à côté des autres imports de builder) :

```typescript
import { NavigationPanel } from "../builder/NavigationPanel";
```

b) Ajouter deux setters à côté de `setPages`/`setMessages` (après la ligne ~130) :

```typescript
  const setNavigationMode = (navigationMode: "tabs" | "story") =>
    setDraft((d) => (d ? { ...d, navigationMode } : d));

  const setActivePageOnEnter = (updated: (typeof pages)[number]) =>
    setDraft((d) => (d ? { ...d, pages: getPages(d).map((p) => (p.id === updated.id ? updated : p)) } : d));
```

c) Dans l'aside gauche (mode edit), ajouter le panneau après le bloc « Actions »
(après la ligne ~180, `<ActionsPanel … />`) :

```tsx
            <p className="mb-1 mt-3 text-xs font-medium text-slate-500">Navigation</p>
            <NavigationPanel
              navigationMode={draft.navigationMode ?? "tabs"}
              onNavigationModeChange={setNavigationMode}
              page={pages.find((p) => p.id === activePage) ?? pages[0]}
              onPageChange={setActivePageOnEnter}
            />
```

> Note : `setActivePageOnEnter` matérialise `pages` explicitement (via `getPages`) — pour
> une config legacy mono-page (`config.pages` vide), éditer un `onEnter` transforme la page
> implicite en `pages` explicite, ce qui est le comportement voulu (le mode story implique
> des chapitres). `layout` reste cohérent car `getPages` renvoie la page implicite dont le
> layout est déjà `config.layout`.

- [ ] **Step 6: Vérifier le build + les tests du builder**

Run: `cd shell && npx vitest run src/builder/NavigationPanel.test.tsx src/pages/AppBuilderPage.test.tsx && npm run build`
Expected: PASS + build OK (tsc sans erreur).

- [ ] **Step 7: Commit**

```bash
git add shell/src/builder/NavigationPanel.tsx shell/src/builder/NavigationPanel.test.tsx shell/src/pages/AppBuilderPage.tsx
git commit -m "feat(shell): storytelling — panneau Navigation (mode + onEnter par chapitre)"
```

---

## Task 6 : Shell — gabarit de galerie « Story cartographique »

**Files:**
- Modify: `shell/src/builder/templates.ts`
- Modify: `shell/src/builder/templates.test.ts`
- Modify: `shell/src/api/itemClient.ts` (`createConfigItem`, ligne ~213)
- Modify: `shell/src/api/itemClient.test.ts`

**Interfaces:**
- Consumes: `Template`, `getTemplate`.
- Produces: `Template` gagne `pages?: Page[]` et `navigationMode?: "tabs" | "story"` ;
  nouveau template `story-cartographique` (kind `app`, 3 pages chacune avec un texte + une
  carte + un `onEnter: map.flyTo`, `navigationMode: "story"`) ; `createConfigItem` propage
  `pages` et `navigationMode` dans la config POSTée.

- [ ] **Step 1: Écrire/mettre à jour les tests qui échouent**

Dans `shell/src/builder/templates.test.ts` : mettre à jour le compte des templates app
(2 → 3) et ajouter un test de forme du template story. Remplacer le test existant
« exposes exactly one app template… » par :

```typescript
test("exposes the expected number of templates per kind", () => {
  expect(TEMPLATES.filter((t) => t.kind === "app")).toHaveLength(3);
  expect(TEMPLATES.filter((t) => t.kind === "dashboard")).toHaveLength(1);
});

test("story cartographique template has 3 chapters each with a flyTo onEnter", () => {
  const story = getTemplate("story-cartographique");
  expect(story?.navigationMode).toBe("story");
  expect(story?.pages).toHaveLength(3);
  for (const page of story!.pages!) {
    expect(page.onEnter).toHaveLength(1);
    expect(page.onEnter![0].action).toBe("flyTo");
    expect(page.onEnter![0].payload).toHaveProperty("center");
  }
});
```

Dans `shell/src/api/itemClient.test.ts`, ajouter (à côté des autres tests
`createConfigItem`) :

```typescript
test("createConfigItem seeds pages and navigationMode from a story template", async () => {
  let body: any = null;
  server.use(
    http.post("https://core.test/configs", async ({ request }) => {
      body = await request.json();
      return HttpResponse.json({ id: "cfg-1", kind: body.config.kind, itemId: "1", version: 1, config: body.config });
    }),
  );
  await makeClient().createConfigItem({ kind: "app", title: "T", owner: "o", templateId: "story-cartographique" });
  expect(body.config.navigationMode).toBe("story");
  expect(body.config.pages).toHaveLength(3);
  expect(body.config.pages[0].onEnter[0].action).toBe("flyTo");
  // layout top-level reflète la première page (le cœur l'exige pour app/dashboard)
  expect(body.config.layout.items.length).toBeGreaterThan(0);
});
```

- [ ] **Step 2: Lancer les tests, vérifier l'échec**

Run: `cd shell && npx vitest run src/builder/templates.test.ts src/api/itemClient.test.ts`
Expected: FAIL — template inconnu, compte à 2, `navigationMode`/`pages` absents du body.

- [ ] **Step 3: Étendre le type `Template` et ajouter le template**

Dans `shell/src/builder/templates.ts`, mettre à jour l'import et le type :

```typescript
import type { ActionMessage, AppLayout, DataSource, Page, Theme } from "../api/types";

export type Template = {
  id: string;
  name: string;
  kind: "app" | "dashboard";
  layout: AppLayout;
  theme?: Theme;
  dataSources?: DataSource[];
  messages?: ActionMessage[];
  pages?: Page[];
  navigationMode?: "tabs" | "story";
};
```

Ajouter les chapitres et le template (avant `export const TEMPLATES`) :

```typescript
function storyChapter(idx: number, title: string, center: [number, number]): Page {
  const mapId = `tpl-story-map-${idx}`;
  return {
    id: `tpl-story-page-${idx}`,
    name: title,
    layout: {
      type: "grid",
      breakpoints: {},
      items: [
        { id: `tpl-story-text-${idx}`, widget: "text", x: 0, y: 0, w: 4, h: 6,
          props: { text: `## ${title}\n\nRacontez ce chapitre ici.` } },
        { id: mapId, widget: "map", x: 4, y: 0, w: 8, h: 6, props: {} },
      ],
    },
    onEnter: [
      { id: `tpl-story-onenter-${idx}`, from: `tpl-story-page-${idx}`, event: "enter",
        to: mapId, action: "flyTo", payload: { center } },
    ],
  };
}

const STORY_PAGES: Page[] = [
  storyChapter(1, "Introduction", [2.35, 48.85]),
  storyChapter(2, "Développement", [4.83, 45.76]),
  storyChapter(3, "Conclusion", [-1.55, 47.22]),
];
```

Ajouter l'entrée à `TEMPLATES` (le champ `layout` reflète la première page, comme l'exige
le cœur pour un kind `app`) :

```typescript
  {
    id: "story-cartographique", name: "Story cartographique", kind: "app",
    layout: STORY_PAGES[0].layout, pages: STORY_PAGES, navigationMode: "story",
  },
```

- [ ] **Step 4: Propager `pages`/`navigationMode` dans `createConfigItem`**

Dans `shell/src/api/itemClient.ts`, dans `createConfigItem` (ligne ~213), remplacer l'objet
`config` par :

```typescript
      const template = input.templateId ? getTemplate(input.templateId) : undefined;
      const firstPageLayout = template?.pages?.[0]?.layout;
      const config = {
        version: 1,
        kind: input.kind,
        theme: template?.theme ?? {},
        dataSources: template?.dataSources ?? [],
        layout: firstPageLayout ?? template?.layout ?? { type: "grid", breakpoints: {}, items: [] },
        messages: template?.messages ?? [],
        pages: template?.pages ?? [],
        navigationMode: template?.navigationMode ?? "tabs",
      };
```

- [ ] **Step 5: Lancer les tests, vérifier le succès**

Run: `cd shell && npx vitest run src/builder/templates.test.ts src/api/itemClient.test.ts`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add shell/src/builder/templates.ts shell/src/builder/templates.test.ts shell/src/api/itemClient.ts shell/src/api/itemClient.test.ts
git commit -m "feat(shell): storytelling — gabarit de galerie « Story cartographique »"
```

---

## Task 7 : E2E — `storytelling.spec.ts`

**Files:**
- Create: `shell/e2e/storytelling.spec.ts`

**Interfaces:**
- Consumes: `mockCore` (`shell/e2e/mocks.ts`), le template `story-cartographique`, la
  barre de story de `AppRenderer`.

> Portée de la preuve : l'E2E prouve l'**authoring + la navigation par chapitres** de bout
> en bout (création depuis le gabarit, barre de progression, Précédent/Suivant, états
> désactivés, texte de chapitre qui change). Le **dispatch effectif de `map.flyTo`** à
> l'entrée d'un chapitre est prouvé de façon fiable par le test unitaire de la Task 3
> (handler stub) : la position caméra d'une carte MapLibre réelle n'est pas assertable de
> manière stable en Playwright, donc on ne l'assert pas ici (déviation assumée et
> documentée vs le libellé « vérifier que la carte se positionne » de la spec §5).

- [ ] **Step 1: Écrire la spec E2E**

Créer `shell/e2e/storytelling.spec.ts` :

```typescript
import { test, expect } from "@playwright/test";
import { mockCore } from "./mocks";

test("un auteur crée une story cartographique depuis le gabarit et la parcourt par chapitres", async ({ page }) => {
  await mockCore(page);
  await page.goto("/");

  // Créer une app depuis le gabarit « Story cartographique ».
  await page.getByRole("button", { name: "Nouveau" }).click();
  const dialog = page.getByRole("dialog", { name: "Nouvel élément" });
  await dialog.getByLabel("Type").selectOption("app");
  await dialog.getByLabel("Modèle").selectOption("story-cartographique");
  await dialog.getByLabel("Titre").fill("Ma story");
  await page.getByRole("button", { name: "Créer" }).click();
  await expect(page).toHaveURL(/\/apps\/9\/edit$/);

  // Le panneau Navigation expose le mode story.
  await expect(page.getByLabel("Mode de navigation")).toHaveValue("story");

  // Enregistrer puis ouvrir en runtime.
  await page.getByRole("button", { name: "Enregistrer" }).click();
  await page.goto("/apps/9");

  // Chapitre 1 : Précédent désactivé, narratif du chapitre 1 visible.
  await expect(page.getByText("Chapitre 1 / 3")).toBeVisible();
  await expect(page.getByRole("button", { name: "Précédent" })).toBeDisabled();
  await expect(page.getByText("Introduction")).toBeVisible();

  // Suivant → chapitre 2.
  await page.getByRole("button", { name: "Suivant" }).click();
  await expect(page.getByText("Chapitre 2 / 3")).toBeVisible();
  await expect(page.getByText("Développement")).toBeVisible();

  // Suivant → chapitre 3, Suivant désormais désactivé.
  await page.getByRole("button", { name: "Suivant" }).click();
  await expect(page.getByText("Chapitre 3 / 3")).toBeVisible();
  await expect(page.getByRole("button", { name: "Suivant" })).toBeDisabled();

  // Précédent revient au chapitre 2.
  await page.getByRole("button", { name: "Précédent" }).click();
  await expect(page.getByText("Chapitre 2 / 3")).toBeVisible();
});
```

> **Point d'attention pour l'implémenteur (à vérifier en ouverture de tâche) :** le mock
> `mockCore` doit servir la config enregistrée en runtime (`GET /configs/by-item/9?mode=runtime`)
> avec ses `pages`/`navigationMode`. Lire `shell/e2e/mocks.ts` : si le mock ne renvoie pas
> la config telle qu'enregistrée par le PUT/POST (i.e. s'il sert une config figée), adapter
> le mock pour refléter la config sauvegardée — même patron que les specs `pages-navigation.spec.ts`
> et `action-conditions.spec.ts`, qui enregistrent puis rechargent en runtime. Ne pas
> modifier le comportement du mock au-delà de ce qui est nécessaire pour servir la config
> story. Si le rendu « markdown » du widget Texte n'affiche pas littéralement le titre
> (`## Introduction` → « Introduction »), assujettir l'assertion au texte réellement rendu
> (vérifier le widget `text` : lit-il du markdown ou du texte brut ?) — ajuster le contenu
> `props.text` du gabarit à la Task 6 si besoin pour que « Introduction » soit un libellé
> visible et distinct par chapitre.

- [ ] **Step 2: Lancer la spec E2E, vérifier qu'elle passe**

Run: `cd shell && npm run e2e -- storytelling`
Expected: PASS. En cas d'échec sur la config runtime, corriger le mock (cf. note ci-dessus)
puis relancer.

- [ ] **Step 3: Lancer la suite E2E complète (non-régression)**

Run: `cd shell && npm run e2e`
Expected: toutes les specs vertes (les 37 existantes + `storytelling.spec.ts`).

- [ ] **Step 4: Commit**

```bash
git add shell/e2e/storytelling.spec.ts shell/e2e/mocks.ts
git commit -m "test(shell): storytelling — spec E2E (création depuis gabarit + navigation par chapitres)"
```

---

## Vérification finale de branche

- [ ] **Shell** : `cd shell && npm run test && npm run build` — verts.
- [ ] **Cœur** : `cd core && uv run pytest` — vert.
- [ ] **E2E** : `cd shell && npm run e2e` — vert (38 specs).
- [ ] **Dérive de types** : régénérer les types si nécessaire (le champ `navigationMode`/
  `onEnter`/`payload` a changé l'OpenAPI du cœur). Vérifier
  `shell/src/api/generated/core-schema.d.ts` vs `core/openapi.json` — les régénérer si le
  job `api-types-drift` diverge (même procédure que les SP précédents). Note : ces champs
  vivent dans le corps de config JSON, pas forcément dans le schéma OpenAPI typé ; vérifier
  avant de conclure à une dérive.
- [ ] **Revue finale** : `superpowers:requesting-code-review` sur toute la branche.
- [ ] Mettre à jour `CLAUDE.md` §État (nouvelle entrée « Storytelling livré et clos »,
  compte de tests shell/E2E mis à jour) — commit séparé.

---

## Auto-revue du plan (effectuée à la rédaction)

**Couverture de la spec :**
- `AppConfig.navigationMode?` + rétrocompat → Tasks 1 (cœur), 3 (shell).
- Barre de progression + Précédent/Suivant + layout immersif → Task 3. (« Immersif » : en
  preview/runtime `GridCanvas` n'affiche déjà aucune bordure d'édition ; le mode story
  ajoute uniquement la barre de navigation. Aucun travail de bordure supplémentaire requis.)
- `Page.onEnter?: ActionMessage[]` réutilisant `ActionBus` + condition `when` → Tasks 1, 2, 3, 4.
- Panneau « Navigation » dans le builder → Task 5 (via `NavigationPanel`, **pas** `ActionsPanel`
  tel quel — déviation documentée §Contexte technique #2).
- Gabarit galerie « Story cartographique » → Task 6.
- Bouton Enregistrer désactivé si condition `onEnter` invalide → Task 4 (via
  `getConfigExpressionErrors`, déjà lu par `AppBuilderPage`).
- Tests Vitest (PageManager/story, onEnter émis/non émis, validation, rétrocompat) →
  Tasks 2/3/4/5. (Le comportement « barre de progression / Précédent-Suivant » testé dans
  `AppRenderer.test.tsx` Task 3, pas dans `PageManager.test.tsx` — car la navigation runtime
  vit dans `AppRenderer`, pas dans le `PageManager` sidebar ; cf. §Contexte technique #1.)
- E2E `storytelling.spec.ts` → Task 7.
- Vigilance schéma Pydantic (régression SP-5b) → Task 1, avec test de round-trip dédié.

**Scan placeholders :** aucun TBD/TODO ; tout code de test et d'implémentation est complet.

**Cohérence des types :** `ActionMessage.payload?: Record<string, unknown>` (shell) ↔
`Message.payload: dict | None` (cœur) ↔ `payload: { center: [lon, lat] }` (usages Tasks 5/6)
↔ `centerFromPayload` lit `{ center: [lon, lat] }` (mapWidget). `ActionBus.dispatch(messages:
ActionMessage[])` défini Task 2, consommé Task 3. `NavigationPanel` signature définie Task 5,
consommée par `AppBuilderPage` même tâche. `Template.pages?`/`navigationMode?` définis Task 6,
consommés par `createConfigItem` même tâche. `storyChapter`/`STORY_PAGES` internes à `templates.ts`.

**Écart connu vs spec :** la spec §3 dit « ActionsPanel réutilisé tel quel » ; le plan écrit
un `NavigationPanel` focalisé (raison : `ActionsPanel` est centré émetteur, incompatible avec
un émetteur-page). La spec §5 dit « vérifier que la carte se positionne » en E2E ; le plan
délègue cette preuve au test unitaire de la Task 3 (position caméra MapLibre non assertable
de façon stable en Playwright) et prouve en E2E l'authoring + la navigation par chapitres.
Ces deux écarts sont des corrections de plan légitimes, cohérentes avec le patron des SP
précédents (le plan corrige l'optimisme de la spec au contact du code réel).
