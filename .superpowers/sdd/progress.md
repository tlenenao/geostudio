# SP-14k — Source `arcgis` (référencement live) — Progress Ledger

Plan: docs/superpowers/plans/2026-08-04-sp14k-source-arcgis.md
Workspace: checkout principal, branche `dev` (convention établie depuis SP-6a, pas de worktree).
Base globale: dev@1bd8a2d (plan + spec SP-14k committés ; ledger SP-14j committé
en amont par hygiène de dépôt, commit 1bd8a2d).

Note : ce fichier remplace le ledger SP-14j (complet, READY TO MERGE, poussé,
HEAD=700084e) — même fichier scratch réutilisé par convention du dépôt ;
contenu SP-14j préservé dans l'historique git (commit 1bd8a2d).

## Pré-vol

Scan des 9 tâches (1: `DatasetPayload.source="arcgis"` + registre de
validateurs par source ; 2: `harvest_repo.get/list_feature_layer_record` ;
3: `GET /harvest/feature-layers` ; 4: `app/harvest/live_query.py` — traduction
pure filtres/bbox/groupBy → ArcGIS REST + cache TTL ; 5:
`GET/POST /datasets/{itemId}/arcgis/items|aggregate` — proxy live ; 6:
shell `itemClient.ts` — branchement par source ; 7: `useFeatureLayers` +
`NewItemButton` ; 8: `DataContext` — résolution pk sûre pour les datasets
arcgis ; 9: E2E `dataset-arcgis.spec.ts`) contre les 9 contraintes globales
(additive only — aucun `DatasetPayload`/`DatasetConfig` source="collection"
ne change de comportement ; `bucket`/`split`/`bins` sur l'aggregate arcgis →
400 explicite, jamais ignoré silencieusement ; posture ArcGIS
services-publics-seulement inchangée ; tout egress sortant via
`build_guarded_client()` ; en-tête SPDX sur tout nouveau fichier Python ;
contrat importlinter vert ; UI shell en français ; commits conventionnels
suffixés (SP-14k) ; 82+ E2E + suites unitaires (pytest/vitest) restent
vertes, vérifiées à la fin de chaque tâche) :

- **Point vérifié, pas une lacune** : Task 5 (`app/harvest/routes.py`)
  importe `app.analytics.aggregate` depuis `app.harvest`. Le texte de la
  tâche liste les modules autorisés sans citer `app.analytics` — vérifié
  directement dans `core/pyproject.toml` `[tool.importlinter]` : `app.analytics`
  n'apparaît dans aucune des 17 couches du contrat `layered architecture`
  (seul contrat déclaré), donc cet import n'est contraint par rien — déjà le
  cas aujourd'hui pour `app.features.routes` qui importe la même chose.
  Aucune action requise, `lint-imports` restera vert.
- **Écart auto-documenté par le plan, pas une contradiction à trancher** :
  Task 1 Step 10-12 committe `test_create_dataset_arcgis.py` alors que ce
  test échoue encore (`get_feature_layer_record` n'existe qu'après Task 2)
  — donc la suite complète `pytest` est rouge un temps très court entre le
  commit de Task 1 et celui de Task 2 (mêmes session, tâches consécutives,
  jamais poussé dans cet état). Le texte du plan l'anticipe et le justifie
  explicitement ligne par ligne (Step 12 : "test will go green once Task 2
  lands"). Précédent direct : la lacune SPDX de SP-14j (Task 8), déjà
  résolue sans interrompre l'exécution. Décision : appliquer Task 1 puis
  Task 2 sans pause, considérer le duo comme la fenêtre d'évaluation
  "fin de tâche" plutôt que d'exiger un vert intermédiaire artificiel. Pas
  de contradiction de fond, aucune question à poser.

Aucune autre lacune trouvée. Le plan fournit du code complet et littéral
pour chaque tâche (schémas, implémentation, tests unitaires, E2E) —
transcription + tests, pas de conception à faire, comme SP-14e→14j.
Dépendances d'interface notées : Task 1 dépend de Task 2 pour son propre
test HTTP (voir ci-dessus) ; Task 3 consomme `list_feature_layer_record`
(Task 2) ; Task 5 consomme `live_query` (Task 4), `get_feature_layer_record`
(Task 2) et le validateur/schema de Task 1 ; Tasks 6-8 (shell) consomment
les routes core (Tasks 1-5) au niveau contrat JSON seulement (mocks HTTP,
pas d'appel réel) ; Task 9 (E2E) exerce l'UI shell produite par Tasks 6-8,
mock `page.route()` uniquement — ne parle jamais au core Python réel ni à
un vrai service ArcGIS. Ordre du plan (1→9) respecté.

Poursuite sans confirmation utilisateur (scan de contradictions clean à
l'exception des deux points ci-dessus, résolus sans ambiguïté).

## Tasks

Base Task 1: 1bd8a2d
Task 1: complete (commit ed74164, review clean au premier passage — ✅
spec compliant, task quality Approved, 0 finding bloquant, 2 Minor
cosmétiques : ordre d'import dans main.py, type-narrowing non vérifié par
mypy). `DatasetPayload.source: Literal["collection","arcgis"]` +
`arcgisItemId`/`collectionId` optionnels avec `model_validator` mutuel-
exclusif ; registre de validateurs par source (`configs/dataset_validation.py`) ;
validateur arcgis (`harvest/dataset_validation.py`) — même message
d'erreur 422 "arcgis layer not found" pour item introuvable et item non
lisible (vérifié indépendamment par le reviewer contre du vrai `can()`,
pas un mock). Import-linter vert (vérifié indépendamment : `uv run
lint-imports`). 3 tests HTTP rouges de façon attendue (Task 2 les rend
verts) — cause confirmée = `AttributeError` sur `get_feature_layer_record`,
rien d'autre. 9/9 tests pydantic + 4/4 collection existants verts.

Base Task 2: ed74164
Task 2: complete (commit 8e05eb7, review clean au premier passage — ✅
spec compliant, task quality Approved, 0 finding bloquant, 1 Minor
cosmétique : fixture `tenant` ajoutée mais non utilisée par les 2 nouveaux
tests, qui unpack `tenant_and_user` directement). `get_feature_layer_record`
et `list_feature_layer_records` (`harvest/repository.py`), tous deux
filtrés par `tenant_id` (vérifié indépendamment par le reviewer — pas
seulement par `item_id`/`layer_kind`). Débloque les 3 tests rouges de
Task 1 (`test_create_dataset_arcgis.py`), vérifiés verts. 2/2 tests
nouveaux + 817/817 suite complète, plus de test rouge connu.

Base Task 3: 8e05eb7
Task 3: complete (commit de5aa0b, review clean au premier passage — ✅
spec compliant, task quality Approved, 0 finding bloquant, 2 Minor).
`GET /harvest/feature-layers?q=` (`harvest/routes.py`) : autorisation
`can()` par item appliquée dans la boucle avant ajout (pas de filtre
post-hoc, aucune fuite partielle possible — vérifié indépendamment par le
reviewer) ; réponse `{id, title}` seulement, `external_url` jamais exposé
(assertion explicite dans le test, pas seulement implicite). 2/2 tests
nouveaux + 819/819 suite complète.

Base Task 4: de5aa0b
Task 4: complete (commit 8d7dd3a, review clean au premier passage — ✅
spec compliant, task quality Approved, 0 finding bloquant, 3 Minor).
`harvest/live_query.py` (nouveau, pur, aucune route HTTP) : échappement
des quotes simples appliqué de façon cohérente sur les 3 branches de
`_build_where` (égalité/`__gte`/`__lte`/`__in`), vérifié indépendamment
par le reviewer avec assertion sur la chaîne échappée réelle (pas
seulement "pas d'exception") ; cache TTL 20s à éviction réelle (`del`
avant re-fetch, pas de lecture silencieuse de valeur périmée) ; test TTL
déterministe via `monkeypatch` de `time.monotonic` (pas de `sleep`).
15/15 tests nouveaux + 834/834 suite complète.

**Point de vigilance reporté explicitement à la revue de Task 5** (signalé
par le reviewer de Task 4, non bloquant ici — `_build_where` n'échappe que
les *valeurs* de filtre via `_sql_lit`, jamais les *noms de champ* utilisés
comme identifiants SQL bruts dans la clause. Task 4 seule ne construit pas
ces noms depuis une entrée non validée, donc rien à corriger ici. Mais le
texte de la Task 5 (lu en pré-vol) construit justement `filters` depuis
`request.query_params.items()` bruts, sans allowlist — c'est exactement le
vecteur anticipé. À vérifier explicitement à la revue de Task 5 : soit une
protection existe déjà dans le code produit, soit c'est une vraie lacune
à faire remonter comme finding.

Base Task 5: 8d7dd3a
Task 5: complete (commits 53e2cd0 + fix 05e99dd, 1 round de fix — 1
finding **Critical** trouvé et corrigé, ✅ spec compliant, task quality
Approved après re-revue). Implémentation initiale (53e2cd0) conforme au
brief : double autorisation dataset+couche dans `_resolve_arcgis_dataset`,
egress guard sans contournement, `bucket`/`split`/`bins` → 400 avant tout
appel réseau. **Finding critique confirmé par le reviewer** (anticipé dès
la revue de Task 4, cf. note ci-dessus) : les *noms* de champ de filtre
(clés `request.query_params` sur GET /items, clés `body.filters` sur POST
/aggregate) atteignaient la clause `where=` ArcGIS sans validation ni
échappement — seules les *valeurs* étaient échappées (`_sql_lit`).
Injection réelle démontrée (`?1) OR (1=1--=x`). Corrigé (05e99dd) :
regex d'identifiant strict `^[A-Za-z_][A-Za-z0-9_]*$` validée dans
`_build_where` (post-découpage de suffixe `__gte`/`__lte`/`__in`, avant
la construction de toute clause), `ArcgisQueryError` → 400 sur la route
GET (nouveau try/except, scindé proprement du try/except réseau existant)
et sur la route POST (déjà couverte gratuitement, même `_build_where`
partagé — vérifié par tracé direct du code par le reviewer, pas seulement
sur la foi du rapport). Re-revue : 5 points de vérification tous confirmés
indépendamment (rejet du payload exact, non-régression des noms légitimes
et des suffixes, portée du try/except, couverture gratuite de la route
POST, assertions de statut réelles dans les nouveaux tests). 1 Minor non
bloquant : regex ASCII-only, rejetterait un nom de champ accentué (pas un
souci de sécurité). 847/847 suite complète, `lint-imports` vert.

Base Task 6: 05e99dd
Task 6: complete (commit 14030ff, review clean au premier passage — ✅
spec compliant, task quality Approved, 0 finding bloquant, 2 Minor
cosmétiques). Les 3 fichiers du brief (`types.ts` union discriminée,
`itemClient.ts` branchement par source des 5 méthodes + `listFeatureLayers`,
`itemClient.test.ts` 6 nouveaux tests) conformes au code littéral, vérifiés
ligne à ligne par le reviewer.

**Extension de portée nécessaire, évaluée délibérément (pas un écart
caché)** : rendre `DatasetConfig` discriminé casse `tsc --noEmit` partout
où `.collectionId` était lu sans narrowing — 6 fichiers hors liste du brief
touchés par des fixes mécaniques minimaux, sans changement de comportement
pour `source:"collection"` (vérifié indépendamment par le reviewer,
notamment `.filter(Boolean)` dans `DataContext.tsx` jugé sûr — aucun
`collectionId` légitime ne peut être falsy) : `hooks.ts`, `DataContext.tsx`,
`ExplorerDrawer.tsx`, `AppBuilderPage.tsx(.test.tsx)`, `DatasetEditPage.tsx`,
`NewItemButton.tsx`. Build propre + 837/837 vitest.

**Conséquence pour Tasks 7 et 8** : leurs briefs (extraits littéralement du
plan, écrit *avant* cette découverte d'implémentation) supposent l'état
pré-Task-6 de `hooks.ts` (`mutationFn` typé en dur) et `DataContext.tsx`
(`collectionIds`/`pkColumn` sans narrowing) — ces deux fichiers sont déjà
partiellement modifiés. Task 8's deux changements prévus sur
`DataContext.tsx` (`collectionIds` + `pkColumn`) sont déjà fonctionnellement
faits par Task 6, mais avec un style différent du type-guard `Extract<...>`
du plan. Task 7's changement prévu sur `hooks.ts` (remplacer le type
littéral par `CreateDatasetInput` importé) trouvera `Parameters<typeof
client.createDatasetItem>[0]` à la place — même effet, style différent.
Décision : ne pas ré-ouvrir Task 6, dispatcher Tasks 7/8 avec le contexte
exact de l'état actuel des fichiers (pas le texte brut du plan) et laisser
leurs implémenteurs adapter l'intention (types nommés explicites, pattern
`Extract<>`) au lieu du diff littéral périmé — écart déjà signalé
proactivement, pas découvert a posteriori par un reviewer surpris.

Base Task 7: 14030ff
Task 7: complete (commit 674faad, review clean au premier passage — ✅
spec compliant, task quality Approved, 0 finding bloquant, 2 Minor déjà
présents dans la convention existante du fichier). `useFeatureLayers` hook
(`hooks.ts`) ; `useCreateDataset` finalisé vers `CreateDatasetInput`
explicite (résout la divergence notée à Task 6 — implémenteur a même
corrigé une erreur de chemin d'import du brief, `"./types"` au lieu de
`"../api/types"`, vérifié par le reviewer) ; `NewItemButton.tsx` —
sélecteur de type de source, picker de couche ArcGIS, branchement submit,
libellés français exacts. Test bout-en-bout réel (MSW + vrai
`createItemClient`, pas un mock superficiel) vérifiant le corps POST réel.
Chemin collection par défaut prouvé inchangé. Build + 838/838 vitest.

Base Task 8: 674faad
Task 8: complete (commit d3af851, review clean au premier passage — ✅
spec compliant, task quality Approved, 0 finding bloquant, 1 Minor
théorique). Tâche redirigée en restylage + couverture de test (le
comportement était déjà correct depuis Task 6) : `collectionIds` migré
vers le pattern `Extract<DatasetConfig,{source:"collection"}>` prévu par
le plan (typage sûr, sans cast, vérifié par le reviewer) ; `pkColumn`
confirmé déjà dans sa forme finale, inchangé. Nouveau test bout-en-bout
(vrai rendu à travers `QueryClientProvider`/`ItemClientProvider`/
`DataProvider`) prouvant `getCollectionSchema` jamais appelé + `pkColumn`
undefined + records peuplés pour un dataset arcgis. Build + 839/839
vitest. Divergence des Tasks 6-8 avec le texte littéral du plan
entièrement résorbée — Task 9 (E2E) peut repartir sur un état de fichiers
propre et conforme à l'intention du plan.

Base Task 9: d3af851
Task 9: complete (commits c656af1 + da99871, review clean au premier
passage — ✅ spec compliant, task quality Approved, 0 finding bloquant, 1
Minor prospectif). `shell/e2e/dataset-arcgis.spec.ts` créé, byte-for-byte
identique au code littéral du brief (vérifié par le reviewer) — mocke
uniquement l'API core via `page.route()`, jamais de backend réel. **Bug
de production latent trouvé et corrigé** (commit séparé c656af1, avant
le commit du test) : `addWidget`/`updateSelectedProps`/
`updateSelectedVisibleWhen` dans `AppBuilderPage.tsx` utilisaient
`setDraft(valeur calculée sur fermeture stale)` au lieu de la forme
fonctionnelle `setDraft(d => ...)` déjà utilisée par les 8 autres setters
du fichier — un widget lié directement à un dataset partagé existant via
l'optgroup "Datasets partagés" perdait silencieusement la `DataSource`
ajoutée juste avant dans le même batch React 18 (deux `setDraft`
synchrones dans le même handler, le second écrasant le premier). Aucun
test préexistant (unitaire ou E2E) n'exerçait ce chemin. Correctif validé
par le reviewer sur les 5 points requis : cause confirmée, les 3
fonctions dérivent désormais tout depuis `d` (aucune lecture de
`draft`/`activeLayout` restante), guards internes sûrs (`getPageLayout`
ne peut jamais crasher), couverture réelle par le nouveau test (pas
incidente — tracé jusqu'à `DataSourceSelect.handleChange` →
`onAdd`+`onChange` synchrones), portée strictement limitée aux 3
fonctions fautives. 83/83 E2E (1 seul run, aucun flake), 839/839 vitest,
build propre, 847/847 pytest + lint-imports inchangés (aucun fichier core
touché).

## SP-14k COMPLET — 9 tâches, 12 commits de tâches (ed74164, 8e05eb7,
## de5aa0b, 8d7dd3a, 53e2cd0, 05e99dd[fix], 14030ff, 674faad, d3af851,
## c656af1[fix], da99871), 2 rounds de fix (Task 5 : injection critique
## par nom de champ non validé, corrigée et re-revue verte ; Task 9 :
## bug de production trouvé et corrigé pendant le TDD du test, pas un
## round de revue). 7/9 tâches approuvées au premier passage (1, 2, 3,
## 4, 6, 7, 8), 2/9 avec un round de fix (5, 9 — dont 9 est un fix
## proactif, pas une réponse à un finding de reviewer). Divergences
## plan/réalité rencontrées et résolues sans bloquer : séquencement
## Task1→Task2 avec test rouge attendu (anticipé en pré-vol) ; extension
## de portée de Task 6 (discriminated union cassant tsc ailleurs) gérée
## proactivement et propagée explicitement aux dispatches Tasks 7/8.
## HEAD=da99871, prêt pour la revue finale de branche.

## Revue finale de branche (opus, 1bd8a2d..da99871, 11 commits) — 1
## finding **Critical** + 1 **Important**, corrigés en un round de fix,
## puis re-revue verte. **Critical trouvé** : incohérence shell↔core sur
## le paramètre de chemin — `itemClient.ts` construisait
## `/datasets/{arcgisItemId}/arcgis/items|aggregate` (id de la couche
## moissonnée), alors que `_resolve_arcgis_dataset` (routes.py) traite
## `{item_id}` comme l'id du **dataset lui-même** (résout `arcgisItemId`
## *depuis* la config du dataset). Un item de couche moissonnée n'a pas
## de Config `kind="dataset"` → 404 en production sur toute table/
## indicateur lié à un dataset arcgis. Passé inaperçu car les tests core
## utilisaient le bon id (côté core), les tests shell asserted/mockaient
## le mauvais contrat (verrouillant le bug), et l'E2E stubait la réponse
## core entièrement (jamais de vérification shell↔core croisée) — trouvé
## uniquement par la revue de branche entière, invisible à l'échelle
## d'une tâche. **Important trouvé** : `translate_aggregate_query` ne
## validait pas les noms de champ `groupBy`/mesures avec le même
## `_FIELD_NAME_RE` que la correction Task 5 sur `_build_where` (risque
## moindre, même classe de défaut, incohérence de posture dans le même
## module). Corrigé (2 commits, 8c2cba5 shell + 9f4ef1b core) : shell
## reclé sur `source.datasetId` (`buildArcgisItemsUrl` param renommé
## `datasetItemId` pour clarté), 3 tests shell corrigés + 1 nouveau test
## de non-régression avec id de dataset et id de couche délibérément
## différents, E2E `dataset-arcgis.spec.ts` reclé sur `dataset-1` au lieu
## de `layer-1` ; core valide désormais `group_by` et `measures[].field`
## non-null avec `_FIELD_NAME_RE` (laisse `None` passer pour les mesures
## `count`-only). Re-revue (opus) : les 6 points de vérification requis
## tous confirmés indépendamment (tracé bout-en-bout shell→core, 4
## assertions de test vérifiées littéralement, cohérence des mocks E2E,
## complétude de la validation core, autres usages d'`arcgisItemId`
## non affectés, balayage négatif pour une deuxième instance de la même
## classe de bug). 0 nouveau finding. Shell : build + 840/840 vitest +
## 83/83 E2E verts. Core : 850/850 pytest + lint-imports vert.
## **SP-14k READY TO MERGE** — HEAD=9f4ef1b, prêt pour
## finishing-a-development-branch.
