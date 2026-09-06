# SP-60 — Performance frontend & filets de test

**Date** : 2026-09-06
**Statut** : spec, prête à devenir un plan
**Demandeur** : Tanguy (via SP-42, référentiel 3)
**Documents liés** : `docs/revue/2026-09-04-analyse-gaps.md` (GAP-68, GAP-69),
`docs/revue/2026-09-04-backlog.md` (REV-072 à REV-077, REV-163),
`.superpowers/sdd/sp42-findings.jsonl` (`F-performances-09/10/11`,
`F-tests-01` à `F-tests-06`), `docs/superpowers/plans/2026-09-05-sp43-refactorisation-structurelle.md`
(travail déjà livré sur une partie de GAP-69), `CLAUDE.md` §« Pièges
récurrents ».

**Portée de ce document** : fermer GAP-68 (performance frontend) et le
reliquat de GAP-69 (filets de test troués sur l'infrastructure de qualité
elle-même), tous deux du référentiel 3 de la revue SP-42. Indépendant des 12
chantiers déjà livrés depuis (SP-45 à SP-58) — aucune dépendance dure.
Chaque affirmation ci-dessous a été **revérifiée par lecture directe du code
et/ou exécution réelle** le 2026-09-06 sur `dev` (piège n°3 CLAUDE.md : le
texte littéral d'un GAP ou d'un backlog peut être faux ou périmé) ; les
écarts trouvés entre le texte des GAP et l'état réel du dépôt sont
explicitement signalés ci-dessous plutôt que recopiés tels quels.

---

## 1. Ce que SP-43 a déjà fermé de GAP-69 — vérifié, pas supposé

GAP-69 liste 6 manques. SP-43 (« refactorisation structurelle », clos et
mergé sur `dev` avant cette spec) en a fermé **1 entièrement** et **1
partiellement** :

- **Fermé — comparateur modèle SQLAlchemy / schéma Alembic.**
  `core/tests/test_model_alembic_parity.py` existe, joue `alembic upgrade
  head` sur une base Postgres jetable puis `compare_metadata()` contre
  `Base.metadata`, avec un filtre `_filter_real_diff()` nommé et falsifié
  (`test_filter_real_diff_absorbs_a_nested_geometry_modify_type`,
  `test_filter_real_diff_absorbs_the_four_known_functional_indexes`). C'est
  exactement le filet que réclamait `F-tests-01`/REV-072. **Rien à refaire
  ici.**
- **Partiellement fermé — fixture `mockCollection()`.**
  `shell/e2e/mocks.ts:182-210` déclare `DEFAULT_COLLECTION` (23 clés,
  synchronisées par commentaire avec `core/tests/test_collections_json_contract.py`)
  et l'exporte via `mockCollection(overrides)`. C'est le correctif exact
  demandé par REV-074/`F-tests-06`, et il ferme bien son unique preuve citée
  (`shell/e2e/admin-collections.spec.ts` — qui utilise la fixture). **Mais
  REV-074 ne portait que sur ce seul fichier** : un grep plus large
  (`grep -rln "geometryType" e2e | grep -v mocks.ts`) trouve encore **9
  fichiers** de specs E2E qui construisent leur propre littéral de
  collection à la main, sans passer par `mockCollection()` :
  `ingestion-gpkg.spec.ts`, `admin-collections.spec.ts` (partiellement —
  d'autres littéraux du même fichier n'utilisent pas la fixture, à
  vérifier lit par lit à l'exécution), `alert-rule.spec.ts`,
  `bookmarks.spec.ts`, `pipeline-builder.spec.ts`, `dataset-export.spec.ts`,
  `incident-form.spec.ts`, `datasets-shared.spec.ts`, `visual-query.spec.ts`,
  `analytics-context.spec.ts`. Exemple vérifié —
  `pipeline-builder.spec.ts:44-61` et `bookmarks.spec.ts:20-28` servent un
  objet collection avec seulement 10 champs (`id`, `title`, `description`,
  `tableName`, `isPublic`, `editable`, `geometryType`, `srid`, `pkColumn`,
  `permissions`, `featureCount`, `owner`) — il leur manque les 11 champs
  ajoutés depuis (`attachmentFields`, `license`, `licenseUri`, `producer`,
  `contact`, `updateFrequency`, `lineage`, `language`, `version`,
  `temporalStart`, `temporalEnd`), soit une forme que `_collection_json()`
  ne produit plus jamais en réel. Le manque décrit par la phrase de GAP-69
  (« les mocks de collection des specs E2E servent une forme que le cœur ne
  produit jamais ») **persiste donc, dans 9 fichiers sur 10**, malgré la
  fixture disponible et déjà adoptée ailleurs.

Les **5 autres** manques de GAP-69 sont intacts, vérifiés un par un ci-dessous
(§2). SP-60 les ferme tous, plus l'adoption manquante de `mockCollection()`.

---

## 2. GAP-69 — analyse par manque, vérifiée sur le code réel

### 2.1 `triptych-narrow.spec.ts` — boucle 900px sans ancre positive

`shell/e2e/triptych-narrow.spec.ts`. La boucle 390px (lignes 244-270)
asserte `expect(page.getByRole("navigation", { name: "Navigation"
})).toBeVisible()` **avant** `expectNoClippedContent()` — une vraie ancre
positive. La boucle 900px (lignes 291-305, « juste au-dessus du seuil
relevé ») n'a **aucune** assertion de ce genre :

```ts
await page.setViewportSize({ width: WIDE_BOUNDARY_WIDTH, height: WIDE_HEIGHT });
await mockCore(page);
if (screen.before) { await screen.before(page); }
await page.goto(screen.path);
await expectNoClippedContent(page);
```

Un écran resté bloqué sur `<p role="status">Chargement…</p>` (le
scénario documenté en commentaire ligne 110-120 pour l'écran
Automatisation, déjà rencontré une fois par cette même suite) mesurerait 0
offenseur `overflow-x` et **passerait**, sans avoir jamais exercé la grille
`TriptychLayout`. Confirmé exact — `F-tests-02`/REV-075.

Nuance à ne pas perdre : deux écrans de `SCREENS` (« Tâches »,
« Paramètres ») ne rendent **jamais** de grille `TriptychLayout`
(`TasksComingSoonPage`/`SettingsComingSoonPage` ne rendent qu'un
`<EmptyState>`, cf. commentaires lignes 224-227/238-241 déjà vérifiés par
SP-33/37) — pour ces deux-là, 0 offenseur est une mesure légitime, mais rien
n'assure aujourd'hui qu'ils ont bien atteint cet état stable plutôt qu'un
`Chargement…` qui se trouve aussi avoir 0 offenseur pour la même raison
accidentelle.

### 2.2 `test_deployability.py` — routeurs `core`/`shell` non couverts

`core/tests/test_deployability.py` a bien un test équivalent pour
**Keycloak** (`test_keycloak_router_carries_security_and_rate_limit_middlewares`,
ligne 1016, ne porte que sur `PROD` — Keycloak n'est routé par Traefik qu'en
prod) et un ensemble de tests pour les 3 routeurs admin
(`test_admin_tool_router_is_gated_by_admin_auth`, etc.), mais **aucun test
ne vérifie que les routeurs `core` et `shell` eux-mêmes** portent
`security-headers@docker` et `rate-limit@docker` — alors que
`docker-compose.yml:377,780` et `docker-compose.prod.yml:165,257` les
portent bien tous les deux aujourd'hui (vérifié par grep direct sur les
deux fichiers). Le commentaire du test Keycloak (ligne 1022-1023) affirme
même explicitement que c'est le cas pour « core/shell/martin/titiler/
grafana » — une affirmation vraie aujourd'hui, mais **non gardée par un
test**, contrairement à ce que sa présence dans un commentaire pourrait
laisser croire (piège n°12 CLAUDE.md : un récit, même dans le code, n'est
pas une preuve). Confirmé exact — `F-tests-03`/REV-073.

Aucun test n'existe non plus pour le contenu des définitions de middleware
elles-mêmes (`stsSeconds`, `contentTypeNosniff`, `frameDeny`,
`referrerPolicy` sur `security-headers` ; `average`/`burst` sur
`rate-limit`) — REV-073 suggère aussi cette extension, peu coûteuse
(labels déjà présents, lignes 168-171/191 de `docker-compose.prod.yml` et
380-384 de `docker-compose.yml`).

### 2.3 `core_env_vars()` (et jumelles) — pas de garde-fou sur l'extracteur lui-même

`core/tests/test_deployability.py:306-332` (`core_env_vars()`),
`:376-382` (`compose_substitutions()`), `:385-393`
(`documented_env_vars()`) : trois extracteurs basés sur un parcours AST ou
une regex, dont dépend `test_every_core_env_var_is_wired_to_a_service`
(ligne 368) et `test_every_compose_substitution_is_documented` (ligne 396).
Aucun des tests existants **du fichier** n'exerce ces fonctions
elles-mêmes de façon isolée — si `core_env_vars()` régressait vers
l'ensemble vide (ex. un refactor qui déplace `CORE_APP` sans mettre à jour
son chemin), `unwired = core_env_vars() - _wired_env_vars() -
ENV_WIRING_EXEMPTIONS` resterait vide par construction et le test passerait
malgré tout — silencieusement, sur la garantie de sécurité la plus
structurante du fichier (câblage effectif des variables d'environnement
lues par le cœur). Confirmé exact — `F-tests-04`/REV-076.

Mesure réelle sur `dev` (exécution directe des 3 fonctions, 2026-09-06,
`CORE_SECRETS_MASTER_KEY` de test) :

| Fonction | Valeur mesurée |
|---|---|
| `core_env_vars()` | 68 |
| `compose_substitutions()` | 64 |
| `documented_env_vars(include_commented=True)` | 76 |
| `documented_env_vars(include_commented=False)` | 54 |

`"CORE_AUTH_MODE" in core_env_vars()` et `"S3_ATTACHMENTS_BUCKET" in
core_env_vars()` sont tous deux vrais aujourd'hui — les deux noms
sentinelles suggérés par REV-076.

### 2.4 « Lisible anonymement » — deux tests distincts, tous deux faibles

Le texte de GAP-69 (« le test "lisible anonymement" n'assert que le code
200 ») pointe en réalité vers **deux tests distincts**, tous deux réels et
tous deux faibles — le backlog (REV-077/`F-tests-05`) désigne précisément
le premier, mais le second (trouvé indépendamment pendant la vérification
de cette spec) partage exactement le même défaut :

- **`core/tests/test_attachments_read_routes.py:199-211`**
  (`test_list_and_file_are_readable_anonymously_on_a_public_collection`,
  cible de REV-077) :
  ```python
  list_res = api.get("/collections/col1/items/f1/attachments")
  assert list_res.status_code == 200
  file_res = api.get(f"/collections/col1/items/f1/attachments/{attachment_id}/file")
  assert file_res.status_code == 200
  ```
  Ni le contenu de la liste (`list_res.json()["attachments"]`) ni le corps
  du fichier téléchargé ne sont vérifiés — une liste vide ou un corps vide
  passeraient. Le même fichier montre déjà le bon patron 15 lignes plus
  loin (`test_delete_removes_row_and_object_and_requires_write_access`,
  ligne 226 : `assert missing.json()["attachments"] == []`) — la
  correction n'introduit aucune nouvelle façon de faire.
- **`core/tests/test_features_routes_read.py:169-181`**
  (`test_anonymous_reads_public_only`), non catalogué par un `F-tests-nn`
  distinct mais du même défaut : `assert client.get(...).status_code ==
  200` sans lire `response.json()`. Ce test utilise un `_repo` factice
  (`make_fake_repo`, ligne 33) qui renvoie toujours le même
  `FeaturePage(features=[FEAT], ...)` quel que soit l'appelant — il ne peut
  donc jamais, avec ce fake, exercer un vrai filtrage RLS par tenant/scope
  (ce n'est pas son rôle : il vérifie la porte HTTP 404↔200 au niveau
  route, pas le filtrage de lignes). Une régression qui viderait quand même
  la réponse en aval (un bug de sérialisation, par exemple) ne serait pas
  détectée pour autant. Renforcement au même coût que le premier :
  `assert client.get(...).json()["numberReturned"] == 1`.

### 2.5 Adoption de `mockCollection()` — reliquat non catalogué explicitement

Cf. §1 : 9 fichiers de specs E2E servent encore un littéral de collection à
la main, sans les 11 champs ajoutés côté cœur depuis l'introduction de la
fixture. Ce n'est pas un `F-tests-nn` distinct (REV-074 ne portait que sur
`admin-collections.spec.ts`, déjà migré), mais c'est la persistance du même
symptôme que décrit la phrase de GAP-69 — traité comme faisant partie du
même manque, pas un manque à part.

---

## 3. GAP-68 — analyse par manque, vérifiée sur le code réel

### 3.1 Aucun code-splitting par route

`shell/src/shell/routes.tsx:4-26` importe les 23 pages du shell en import
statique en tête de fichier (`CatalogPage`, `MapEditorPage`,
`AppBuilderPage`, `SqlLabPage`, les 6 pages Admin, `PipelineBuilderPage`,
etc.) — aucun `React.lazy()` au niveau routeur. `shell/vite.config.ts` ne
déclare ni `build.rollupOptions.output.manualChunks` ni
`build.chunkSizeWarningLimit` : zéro configuration de découpage.

Mesure réelle (`npm run build` après nettoyage de `dist/`, 2026-09-06) :

```
dist/assets/index-Cw5te6tk.js   3,323.18 kB │ gzip: 926.38 kB
dist/assets/EChart-DBkn5YFF.js    819.49 kB │ gzip: 272.37 kB
```

Le chunk d'entrée pèse **3,32 Mo non compressés / 926 Ko gzippés** —
cohérent avec les « 3,2 Mo mesurés » du GAP (légèrement plus aujourd'hui,
le dépôt a grossi depuis la mesure d'origine). `EChart` est déjà
correctement scindé (819 Ko) grâce au `lazy()` de
`builder/widgets/chart.tsx`/`indicator.tsx` — la preuve que le mécanisme
`lazy()`+`Suspense` fonctionne bien dans ce projet quand rien ne le
neutralise (cf. §3.2). Toutes les autres pages (admin, SQL Lab, éditeur de
carte, builder de pipeline, builder d'app…) sont dans l'unique chunk
`index-*.js`, livré à chaque visiteur quel que soit l'écran demandé.

### 3.2 Le lazy-loading de `MapView` neutralisé par un import statique

Vite l'avertit littéralement au build (vérifié en relançant `npm run
build`, warning reproduit tel quel) :

```
[INEFFECTIVE_DYNAMIC_IMPORT] src/map/MapView.tsx is dynamically imported by
src/builder/ExplorerDrawer.tsx, src/builder/widgets/mapWidget.tsx but also
statically imported by src/pages/MapEditorPage.tsx, dynamic import will not
move module into another chunk.
```

Trois sites importent `MapView` :
- `shell/src/pages/MapEditorPage.tsx:7` — `import { MapView, type
  MapViewHandle } from "../map/MapView";` (**statique**).
- `shell/src/builder/widgets/mapWidget.tsx:25` — `const MapView =
  lazy(() => import("../../map/MapView").then((m) => ({ default:
  m.MapView })));` (dynamique).
- `shell/src/builder/ExplorerDrawer.tsx:11` — même patron dynamique.

Rollup ne peut jamais isoler `MapView` (et sa fermeture — maplibre-gl,
`deck.gl` pour le rendu 3D, très lourds) dans un chunk séparé tant qu'un
site statique existe : le module reste fusionné avec le chunk du seul
importeur statique. `MapEditorPage.tsx` étant lui-même importé
statiquement par `routes.tsx` (§3.1), `MapView` finit dans le chunk
d'entrée principal — exactement l'inverse de ce que ses deux autres
importeurs dynamiques cherchent à obtenir.

### 3.3 Boucles de sondage sans annulation au démontage

**Écart avec le texte littéral du GAP** (vérifié, piège n°3 CLAUDE.md) : le
GAP n'accuse que `Terrain3DUploadButton`/`Tileset3DUploadButton`, « contrairement
aux quatre autres sondages du shell » — sous-entendant que les 4 autres
sondages existants annulent tous correctement leur boucle au démontage.
Un inventaire complet des 8 implémentations de ce patron dans le dépôt
montre que ce n'est vrai que pour **4 d'entre elles**, mais les 4 autres
**ne se limitent pas** à Terrain3D/Tileset3D :

| Fichier | Annule au démontage ? | Mécanisme |
|---|---|---|
| `builder/print/ExportPanel.tsx` | ✅ | `mountedRef` + `timerRef` (+ plafond `MAX_POLL_ATTEMPTS`) |
| `builder/appexport/AppExportPanel.tsx` | ✅ | `mountedRef` + `timerRef` |
| `builder/report/ReportRunPanel.tsx` | ✅ | `stopped` ref, cadence adaptative |
| `pages/VisualQueryWizardPage.tsx` (poll interne, ligne 128-171) | ✅ | flag `cancelled` + `useEffect` cleanup |
| `builder/pipeline/PipelineRunPanel.tsx` | ❌ | boucle `for(;;)` nue, aucune garde |
| `shell/ImportFileButton.tsx` | ❌ | boucle `for(;;)` nue, aucune garde |
| `map/Terrain3DUploadButton.tsx` | ❌ | boucle `for(;;)` nue, aucune garde, plafond 5 min |
| `shell/Tileset3DUploadButton.tsx` | ❌ | boucle `for(;;)` nue, aucune garde, plafond 5 min |

Donc 4 sondages sur 8 ne s'arrêtent jamais au démontage, pas seulement les
2 nommés par le GAP. Nuance de risque réel entre les 4 :
`Tileset3DUploadButton`/`ImportFileButton` sont tous deux montés en
permanence dans `TopBar.tsx` (chrome, ne démonte jamais pendant la
navigation SPA) — leur fuite ne se matérialise qu'à la fermeture de
l'onglet ou à la déconnexion, un risque réel mais borné. `Terrain3DUploadButton`
est monté dans `TerrainPanel.tsx`, lui-même rendu par `MapEditorPage` — une
page de route qui démonte à chaque navigation, donc chaque changement de
page pendant une conversion DEM en cours laisse tourner le sondage
jusqu'à 5 minutes avec un risque réel de `setState` sur composant
démonté. `PipelineRunPanel` est monté par `PipelineBuilderPage`
et `VisualQueryWizardPage`, deux pages de route également démontées à la
navigation, avec un sondage **sans aucun plafond** (contrairement aux deux
précédents) — la boucle la plus longue-vivante des 4.

**Décision de périmètre pour cette spec** : les 4 corrigées ensemble, pas
seulement les 2 nommés par le GAP — le correctif est mécaniquement
identique (même patron `mountedRef`+`timerRef` que `ExportPanel.tsx`,
appliqué 4 fois), et laisser 2 bugs de la même classe fraîchement trouvés
sans correctif alors que le patron correct est déjà écrit deux fois dans
le dépôt serait la définition même du piège n°4 CLAUDE.md (croisement
entre tâches, ici entre « ce qui est nommé » et « ce qui est trouvé en
vérifiant »). Coût marginal négligeable : même test, même correctif, 2
fichiers de plus.

---

## 4. Décisions de conception

### 4.1 Découpage par route : `React.lazy()` + `Suspense`, pas un second mécanisme

Toutes les pages du shell utilisent déjà l'export nommé (aucun `export
default` dans `shell/src/pages/`, vérifié par grep) — le patron à
reproduire est celui déjà en place pour `MapView`/`EChart` :
`lazy(() => import("../pages/X").then((m) => ({ default: m.X })))`. Pas de
bibliothèque de routing différente, pas de `React.Suspense` par route
individuelle : un seul `<Suspense>` enveloppant `<Outlet />` dans
`ProtectedLayout` (et un second, symétrique, autour de `AppRuntimeRoute`/
`SitePublicRoute`/`PublicItemRoute`/`DatasetRoute`, qui vivent hors du
layout protégé) suffit — React affiche le fallback pour n'importe quelle
route enfant en cours de résolution, pas seulement la première. Fallback :
`<p role="status">Chargement…</p>`, réutilisant tel quel le libellé déjà
utilisé ailleurs dans le shell (`PipelineBuilderPage.tsx`, entre autres) —
convention déjà établie, aucune nouvelle chaîne à traduire.

**Conséquence sur `routes.test.tsx`** : ce fichier mocke déjà chaque page
par `vi.mock("../pages/X", () => ({ X: (...) => <div>...</div> }))` — ces
mocks continuent de fonctionner à l'identique avec un import dynamique
(`vi.mock` intercepte la résolution de module, statique ou dynamique).
Mais l'import devenant asynchrone (une micro-tâche au minimum, même mocké),
les assertions synchrones existantes après un rendu (`screen.getByText(...)`
sans `find`/`await waitFor` précédent) doivent devenir asynchrones
(`await screen.findByText(...)`). Vérifié : le fichier a 2 sites de ce
genre (`screen.getByText("map-editor-77")`, lignes 257 et 265) — à
convertir en `findByText`. Chaque test du fichier devra être exécuté après
conversion pour repérer d'éventuels autres sites analogues non listés
ci-dessus (recherche par grep imparfaite sur un fichier de 418 lignes,
vérification par exécution requise, pas seulement par grep — même
principe que §3.3).

### 4.2 Regroupement en chunks de vendeur pour les bibliothèques lourdes

Au-delà du découpage par route, les dépendances les plus volumineuses
(`maplibre-gl`, `@deck.gl/*` + `@loaders.gl/3d-tiles`, `echarts`,
`@xyflow/react` pour le canevas DAG du builder de pipeline, `lit` pour le
pont Web Components) profitent d'un `manualChunks` explicite dans
`vite.config.ts` (`build.rollupOptions.output.manualChunks`), pour qu'elles
ne soient chargées qu'une fois et partagées entre les routes qui les
consomment plutôt que dupliquées dans plusieurs chunks de route. Portée
volontairement limitée à un `manualChunks` **fonction** groupant par nom de
paquet (`id.includes("node_modules")` → sous-chunk par famille), pas une
liste statique fragile à maintenir à la main à chaque nouvelle dépendance.

### 4.3 Un filet de non-régression sur la taille du bundle — patron déjà établi par ce dépôt

Le dépôt a déjà exactement ce patron pour la couverture de tests :
`shell/scripts/check-coverage.mjs` + `shell/.coverage-threshold` (valeur
committée, seuil non régressif, invoqué en CI juste après la mesure). SP-60
introduit le même patron pour la taille du bundle d'entrée :
`shell/scripts/check-bundle-size.mjs` + `shell/.bundle-size-threshold`,
invoqué en CI **après** `npm run build` (aujourd'hui la dernière étape du
job `shell` dans `ci.yml`, ligne 118 — rien ne lit `dist/` après elle
actuellement). Le script active `build.manifest = true` dans
`vite.config.ts` (manifeste Vite `dist/.vite/manifest.json`), calcule la
charge JS initiale réellement nécessaire au premier rendu (l'entrée plus
tout ce qu'elle importe *statiquement*, en excluant récursivement tout ce
qui n'est atteint que par `dynamicImports` — c'est précisément la
distinction que le découpage par route introduit), somme les tailles de
fichiers correspondantes sous `dist/assets/`, et échoue si la somme dépasse
le seuil committé. Plus rigoureux qu'un simple glob sur
`dist/assets/index-*.js` : un glob ne verrait pas qu'un futur import
statique regonfle le chunk d'entrée sous un autre nom de fichier haché.

### 4.4 Boucles de sondage : patron `mountedRef`+`timerRef` de `ExportPanel.tsx`, répliqué 4 fois

Pas de hook `usePoll()` générique à extraire dans cette spec — 4 fichiers
à corriger avec un patron déjà écrit deux fois dans le dépôt
(`ExportPanel.tsx`, `AppExportPanel.tsx`) est un risque d'introduire une
abstraction prématurée (5e/6e call site avec des formes de retour
différentes : `PipelineRunPanel`/`ImportFileButton` n'ont pas la même
signature de sortie que `Terrain3DUploadButton`/`Tileset3DUploadButton`).
Chaque fichier reçoit son propre `mountedRef`/`timerRef` local, sur le
modèle exact de `ExportPanel.tsx:35-45,47-62` :

```ts
const mountedRef = useRef(true);
const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

useEffect(
  () => () => {
    mountedRef.current = false;
    if (timerRef.current) clearTimeout(timerRef.current);
  },
  [],
);
```

Chaque `setState` qui suit un `await` à l'intérieur de `poll()` est gardé
par `if (!mountedRef.current) return;` (ou équivalent), et l'attente entre
deux itérations passe par `timerRef.current = setTimeout(resolve,
intervalMs)` plutôt qu'un `setTimeout` anonyme non référencé — condition
nécessaire pour pouvoir l'annuler au démontage. Falsification obligatoire
avant de considérer chaque correctif terminé (patron déjà utilisé par
`ExportPanel.test.tsx:87-105`, cf. §5) : mesurer le nombre d'appels au
client mocké après démontage + attente au-delà de l'intervalle de
sondage, avec un espion sur `console.error` pour capter l'avertissement
React de `setState` sur composant démonté.

---

## 5. Ordre d'exécution et risques

Du moins au plus invasif, en séparant nettement GAP-69 (filets de test,
risque très bas, aucun comportement de production ne change) de GAP-68
(perf, risque moyen sur la surface de test existante) :

1. **GAP-69, tests core purs** (§2.2 à §2.4) — 3 correctifs indépendants
   sur `core/tests/test_deployability.py` et 2 fichiers de test features/
   attachments. Risque nul : aucun code de production ne change, seules des
   assertions se renforcent.
2. **GAP-69, `triptych-narrow.spec.ts`** (§2.1) — risque bas, un seul
   fichier E2E, ajoute des ancres sans changer le comportement des écrans
   testés.
3. **GAP-69, adoption de `mockCollection()`** (§2.5) — risque bas mais
   mécanique sur 9 fichiers : chaque littéral remplacé doit produire un
   diff de snapshot/assertion nul si le test ne dépendait d'aucun des 11
   champs manquants (le cas attendu), sinon révéler une dépendance
   implicite à vérifier au cas par cas.
4. **GAP-68, sondages** (§3.3/§4.4) — risque bas, 4 fichiers, patron déjà
   éprouvé deux fois dans le dépôt.
5. **GAP-68, `MapView` (§3.2/§4.1)** — risque bas, un seul import à
   convertir, mais la preuve de fermeture exige de relancer `npm run
   build` et de confirmer la disparition du warning Vite (pas seulement
   « les tests passent »).
6. **GAP-68, découpage par route + vendor chunks + filet de taille**
   (§3.1/§4.1-4.3) — le plus invasif : touche `routes.tsx` dans son
   intégralité, `routes.test.tsx` (conversions `findBy`), `vite.config.ts`
   (manifest + manualChunks), plus l'introduction du script et du seuil.
   Risque principal : un site de test qui suppose un rendu synchrone de
   page après navigation et casse silencieusement en CI si le passage en
   `findBy` est incomplet — mitigé par l'exécution complète de
   `routes.test.tsx` avant de considérer la tâche close (pas un grep).
7. **Vérification finale** — suite Vitest + Playwright complètes, portes
   de qualité (`ruff`, `tsc --noEmit`, `lint-imports`, ESLint/Prettier),
   confirmation qu'aucune régénération OpenAPI n'est nécessaire (aucune
   route ni modèle du cœur ne change de forme dans ce plan — seules des
   assertions de test et des fichiers `shell/`/`vite.config.ts` bougent),
   mesure finale du bundle et fixation du seuil committé à cette mesure.

---

## 6. Hors périmètre (explicite)

- **CSP en enforcing** (GAP-72) : indépendant, déjà catalogué séparément,
  4 blocages documentés non résolus ici.
- **Un `usePoll()` générique** extrait des 6 implémentations existantes de
  ce patron (cf. §4.4) : abstraction prématurée pour ce périmètre, les 4
  correctifs restent des copies locales du même patron.
- **Rendre les 5 tests `@pytest.mark.qgis` câblés en CI** (`REV-095`,
  suivi non bloquant post-SP-44) : sans rapport avec GAP-68/GAP-69.
- **Étendre `manualChunks` à un découpage plus fin par sous-widget** (par
  ex. séparer chaque widget du catalogue builder en chunk propre) : hors
  scope, le découpage par route (§4.1) couvre déjà l'essentiel du gain
  mesuré, un découpage plus fin est un raffinement ultérieur si la mesure
  du seuil de bundle le justifie après ce plan.
- **`shell/scripts/check-coverage.mjs` ne lit que `lines.pct`** (REV-078,
  minor, 4 métriques à vérifier séparément) : voisin par mécanisme
  (patron seuil/ratchet) mais un manque distinct, non catalogué sous
  GAP-68/GAP-69.
- **`compose_substitutions()`/`documented_env_vars()` : seule une garde de
  borne basse est ajoutée** (§2.3) — pas une refonte de ces extracteurs
  eux-mêmes vers une méthode plus robuste que regex/AST (limites déjà
  documentées en commentaire dans le fichier, assumées).

---

## 7. Ce que ce document ne tranche pas

- La valeur exacte du seuil `.bundle-size-threshold` committé à la
  clôture — dépend de la mesure réelle après découpage (§4.3), à fixer
  par le plan une fois le découpage en place, pas anticipée ici.
- Le détail du groupement `manualChunks` par famille de paquet (un seul
  chunk « cartographie » regroupant maplibre-gl+deck.gl+loaders.gl, ou un
  par paquet) — laissé au plan, à trancher en mesurant l'effet réel sur le
  nombre et la taille des chunks produits.
- Le nom exact de la fonction de purge/anchor ajoutée à
  `triptych-narrow.spec.ts` pour chaque écran (§2.1) — laissé au plan.
