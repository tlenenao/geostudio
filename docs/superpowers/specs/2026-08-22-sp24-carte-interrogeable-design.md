# Carte interrogeable (SP-24)

> Étape 5 du séquencement recommandé du plan d'action
> `docs/vision/2026-08-20-revue-projet-et-plan-daction.md` (§6) : premier
> chantier du **lot Carte** de la vague 4, soit **4.1** (constats **D1** et
> **D2** du §7). Spec écrite le 2026-08-22, après vérification de l'état réel
> du dépôt — le chantier s'est révélé plus large que ce que le plan supposait,
> pour une raison de sécurité que le plan ne nomme pas (§3.1, §4).

## 1. Contexte & objectif

SP-23 a clos les quatre bouchons à coût faible (étape 4 du séquencement). Le
§6 place ensuite le lot Carte « sans attendre la vague 3 », avec un argument
que la spec reprend tel quel : *une carte qu'on ne peut ni interroger ni
styliser reste un fond d'écran*. Le lot compte cinq chantiers ; celui-ci en
livre le premier, marqué **L** à lui seul.

Ce que dit le plan, vérifié contre le code :

| Constat | Vérification |
|---|---|
| **D1** — aucun popup, nulle part | Exact. Le clic existe (`shell/src/map/MapView.tsx:120-131`) mais alimente la sélection (édition SP-4) et le cross-filter (SP-14n), jamais un affichage |
| **D2** — interactivité et passage à l'échelle mutuellement exclusifs | Exact, et pire que décrit : une couche `kind: "vector"` n'a aucun handler de clic **et** est toujours ajoutée en `type: "fill"` (`MapView.tsx:82-88`), donc une collection de points tuilée ne s'affiche pas du tout |

Deux faits que le plan ne mentionne pas et qui commandent le dessin :

1. **Le chemin tuilé n'est protégé par rien.** Martin est routé publiquement
   sans authentification (`docker-compose.prod.yml:36-43`, `PathPrefix(/tiles)`,
   aucun middleware d'auth), se connecte en `gis` — le **propriétaire** des
   tables (`docker-compose.yml:20` et `:103`) —, et `apply_collection_ddl`
   pose `ENABLE ROW LEVEL SECURITY` sans `FORCE` (`core/app/collections/ddl.py:24-28`) :
   un propriétaire contourne la RLS par construction Postgres. `martin-config.yaml`
   ne déclare aucune table, donc Martin les découvre toutes. Conséquence
   mesurable : `GET /tiles/catalog` puis `/tiles/{table}/{z}/{x}/{y}` rend à un
   visiteur **anonyme** l'intégralité de n'importe quelle collection de
   n'importe quel tenant, colonne `tenant_id` incluse, y compris privée.
   Poser un popup sur ce chemin, c'est bénir une surface qui contourne `can()`
   et la RLS.
2. **Il n'existe aucun index spatial dans le dépôt.** `apply_collection_ddl`
   n'indexe que `tenant_id` (`ddl.py:31-36`), l'ingestion n'en crée pas, et
   `grep -i gist` sur `core/app` et `core/alembic` ne rend rien. Tout filtre
   bbox déjà livré (le `bbox` d'OGC Features, le `geom_intersects` du
   cross-filter SP-14n) est donc un scan complet de table.

Objectif de sortie : le critère du plan est atteint et prouvé — *cliquer une
entité d'une collection servie en tuiles MVT ouvre un popup renseigné, sur une
carte publiée, sans widget d'app à côté* — sur un chemin tuilé qui passe par
le cœur, donc autorisé par `can()` et isolé par la RLS.

## 2. Périmètre

Le chantier 4.1, avec **deux élargissements assumés et tranchés en session**
(§4) :

1. **Les tuiles vectorielles sont servies par le cœur**, pas par Martin. Ce
   n'est pas un détour : c'est ce qui donne à une couche tuilée un lien vers
   sa collection — donc un schéma de champs pour le popup, une porte `can()`,
   et le socle dont SP-25 (symbologie, 4.2/4.3) aura besoin pour calculer des
   bornes de classes. Et c'est ce qui ferme le trou du §1.
2. **La route publique `/tiles` est retirée** dans ce SP, pas dans un suivi.
   Le trou se ferme dans le même chantier que la capacité qui le rendait
   tentant.

Un index spatial GiST entre au périmètre par nécessité : sans lui,
« le chemin performant » serait une affirmation fausse.

**Hors périmètre, explicitement** :

- **La symbologie** (4.2, 4.3, 4.4). SP-25, qui consommera le `collectionId`
  posé ici.
- **Mesure et croquis** (4.5).
- **Le widget carte d'app reste sur une couche `kind: "feature"`** alimentée
  par sa `DataSource` : son filtrage et son cross-filter côté client en
  dépendent, et tuiler une DataSource filtrée exigerait de pousser le filtre
  côté serveur. Le constat **D2 reste donc vrai à l'intérieur du widget carte
  d'app**, y compris son plafond silencieux de 100 entités
  (`core/app/features/routes.py:181` — `limit` vaut 100 par défaut et le
  sélecteur construit l'URL sans paramètre). Le widget gagne le popup, pas le
  tuilage. Suivi non bloquant, pas un oubli.
- **La conformité OGC API - Tiles.** On sert du MVT à notre propre chemin :
  pas de `tileMatrixSets`, pas de TileJSON, pas de déclaration de conformance.
  MapLibre consomme `tiles: [url]` directement.
- **Popup sur `raster`, `deck` et `tiles3d`.** Ces trois kinds n'ont pas
  d'attributs interrogeables par le même mécanisme.
- **Toute correction trouvée hors des fichiers déjà touchés** : notée en suivi
  non bloquant, pas corrigée ici.

## 3. Mécanisme

### 3.1 — Cœur : les tuiles passent par le cœur

Nouveau fichier `core/app/features/tiles.py`. Même paquet que
`features/routes.py` (641 lignes déjà) mais fichier séparé. **Aucun nouveau
module, donc aucune entrée au contrat de couches import-linter** :
`app.features` est déjà au-dessus d'`app.collections`, `app.sharing` et
`app.audit`, et `features/routes.py:34` importe déjà
`get_readable_collection`.

Route : `GET /collections/{collection_id}/tiles/{z}/{x}/{y}.mvt`

| Point | Décision |
|---|---|
| **Autorisation** | `get_readable_collection` réutilisée **verbatim** (`collections/routes.py:154`) : 404 avant 403, anonyme accepté sur une collection publique. Exactement la porte de `/items`, aucune variante |
| **Isolation tenant** | La requête s'exécute **dans `rls_scope`** (`core/app/features/rls.py` : rôle `gis_rls` + GUC transactionnel `app.tenant_id`). C'est la RLS qui isole, pas un `WHERE` que l'implémenteur pourrait oublier |
| **SQL** | `ST_AsMVT` / `ST_AsMVTGeom` / `ST_TileEnvelope`. Tous les identifiants passent par le `quote_ident` existant (`collections/ddl.py:13`) |
| **Colonnes** | Dérivées d'`introspect_table` (`TableInfo.columns`). **`tenant_id` exclu explicitement.** La PK (`TableInfo.pk_column`) devient le `feature_id` MVT, donc le clic rend un `id` réutilisable par `GET /items/{fid}` et par le cross-filter SP-14n |
| **Bornes** | `z` dans `[0, 24]`, `x`/`y` dans la plage valide de `z` → 400 sinon. Une collection sans géométrie (`geometry_column is None`) → 400 |
| **Tuile vide** | `204`, jamais un `200` à corps vide |
| **Cache** | `Cache-Control: private, max-age=300` ; `public, max-age=300` quand `is_public` |
| **Audit** | **Pas** d'entrée `audit_log` par tuile : une seule vue de carte en produit des centaines, ce serait un déni de service sur la table d'audit. La règle non négociable de CLAUDE.md porte sur les écritures, qui sont inchangées |

### 3.2 — Cœur : l'index spatial manquant

- `apply_collection_ddl` gagne un `CREATE INDEX IF NOT EXISTS … USING GIST (<geometry_column>)`,
  idempotent comme le reste de la fonction, nom borné comme l'index
  `tenant_id` existant (`tableName` est plafonné à 50 par `CollectionCreate`).
- **Migration 0028** (la dernière est `0027_app_export_jobs.py`) : balaie le
  registre `collections` et crée l'index manquant sur chaque table déjà
  enregistrée. Le `downgrade()` supprime les index créés.
- Une collection sans colonne de géométrie est ignorée sans erreur.

### 3.3 — Shell : les types déclaratifs

`shell/src/api/types.ts`. Additif, **aucune migration** — un `MapConfig` est
un document JSON de `BuilderConfig`.

- `MapLayer` kind `"vector"` gagne `collectionId?: string`,
  `geometryKind?: "point" | "line" | "polygon"` et `popup?: PopupConfig`.
- `MapLayer` kind `"feature"` gagne `popup?: PopupConfig`.
- Nouveau type partagé :

```ts
export type PopupField = { name: string; label?: string };
export type PopupConfig = {
  titleField?: string;   // champ servant de titre
  fields?: PopupField[]; // absent = tous les champs du schéma, dans son ordre
  template?: string;     // échappatoire ; non vide, il remplace titleField/fields
};
```

Côté cœur, `core/app/configs/schemas.py` porte les mêmes champs sur la
variante correspondante de sa propre union de couches (`schemas.py:81-92`),
sans quoi une config sauvegardée les perdrait silencieusement — c'est le
défaut pré-existant que SP-17a avait trouvé sur `printLayout`
(`saveMapConfig` perdait le champ).

### 3.4 — Shell : rendu et clic dans `MapView`

`shell/src/map/MapView.tsx`, dans `applyLayers` :

1. **Le type MapLibre d'une couche `vector` est dérivé de `geometryKind`**
   (`circle` / `line` / `fill`), au lieu du `type: "fill"` inconditionnel
   actuel. Sans ce correctif, une collection de points tuilée reste
   invisible et son popup inatteignable — c'est un prérequis du chantier,
   pas un bonus.
2. **Le handler de clic est posé sur `vector` comme sur `feature`.** Il reste
   **additif** : il continue d'émettre `itemSelected` et d'alimenter le
   cross-filter ; le popup s'ouvre en plus, jamais à leur place.
3. Les propriétés viennent de `queryRenderedFeatures` — donc de la tuile
   elle-même, sans aller-retour supplémentaire. La tuile est produite par le
   cœur sous `can()` + RLS (§3.1) : ce qu'elle contient est exactement ce que
   l'utilisateur a le droit de lire.
4. Les tuiles du cœur sont authentifiées et réutilisent le `transformRequest`
   + `isHostedCoreUrl` déjà en place pour tileset3d/terrain3d
   (`MapView.tsx:31-48`) : même vérification d'origine réelle, jamais un
   `includes()` sur le chemin. `getAuthToken` est déjà passé par les quatre
   appelants.

Nouveau composant `shell/src/map/MapPopup.tsx`, **chemin de rendu unique**.
Vérifié : `MapView` n'a que **trois** consommateurs dans tout le dépôt —
`pages/MapEditorPage.tsx` (éditeur et visionneuse de carte),
`builder/widgets/mapWidget.tsx` et `builder/ExplorerDrawer.tsx`. Le popup de
`/sites/{slug}` vient gratuitement : `SitePublicPage` rend les widgets
builtin, donc le widget carte. Il n'y a rien à câbler quatre fois.

### 3.5 — Le popup : modèle et gabarit

**Mode liste** (défaut). Libellés pré-remplis depuis `getCollectionSchema`
(déjà sur `ItemClient`, `types.ts:302`), surchargeables par l'auteur. `fields`
absent = tous les champs du schéma, dans son ordre.

**Mode gabarit.** Markdown libre où chaque `${expression}` est évaluée en CEL
contre l'`ExprContext` existant (`builder/expr.ts`), dont `record` porte les
propriétés de l'entité cliquée. Le dépôt a déjà une convention d'expression
— le binding JSON `{ $expr: … }` de `builder/exprBindings.ts` — et le gabarit
en introduit une seconde, assumée (§4) : c'est la seule forme qui donne une
mise en forme libre. Règles explicites, parce que ce sont elles qui seront
testées :

- Recherche de `${`, puis du `}` correspondant **en comptant la profondeur
  d'accolades** (une expression CEL peut contenir un littéral de map).
- `${` sans `}` correspondant → le texte est laissé **littéral**, jamais
  d'exception. L'éditeur d'auteur signale l'erreur via `validateExpression`.
- Expression invalide ou champ absent → chaîne vide. `evaluateExpression`
  rend déjà `undefined` avec un `console.warn`, on ne le change pas.
- Valeurs : scalaire → `String(value)` ; `null`/`undefined` → chaîne vide ;
  objet/tableau → `JSON.stringify`.
- **Ordre d'opérations : interpoler d'abord, assainir ensuite.** Le markdown
  assemblé passe **entièrement** par `sanitizeMarkdown()`
  (`builder/widgets/sanitizeMarkdown.ts`, `marked` + DOMPurify, chemin unique
  et non contournable). Conséquence assumée et documentée : une valeur de
  propriété est interprétée **comme du markdown** — c'est ce qui permet de
  mettre un champ URL dans un lien. DOMPurify est la garantie contre
  l'injection, pas l'échappement. La règle ESLint `no-restricted-syntax` de
  SP-22 interdit `dangerouslySetInnerHTML` hors `richSection.tsx` :
  `MapPopup.tsx` **rejoint son bloc d'exception de fichier**, comme deuxième
  consommateur légitime de `sanitizeMarkdown()`. Écarté : extraire un
  composant `<SanitizedMarkdown>` partagé pour n'avoir qu'une seule
  exception — ce serait toucher un widget déjà livré pour un gain de forme,
  hors du périmètre de ce chantier.

### 3.6 — Éditeur d'auteur

Un seul composant, `PopupEditor`, monté sur les **deux** surfaces :

- `shell/src/map/LayersPanel.tsx` — par couche ; liste de champs proposée
  depuis `getCollectionSchema(collectionId)`.
- Le `PropsPanel` du widget carte (`builder/widgets/mapWidget.tsx:118-179`) —
  liste de champs proposée depuis les clés du premier enregistrement de
  `ctx.data.records`, donc **aucune nouvelle route**.

Ce partage est délibéré : l'écart **I2** de la revue finale SP-23 était
exactement un garde-fou écrit pour une surface et jamais reporté sur sa
jumelle.

Contenu : une bascule d'activation qui **pose ou retire le champ `popup`**
de la couche (il n'y a pas de drapeau `enabled` : l'absence de `popup` est
l'état désactivé, une valeur de moins à faire round-tripper), un sélecteur de
champ titre, une liste ordonnée de champs avec libellé surchargeable, et un
mode « Avancé (gabarit) » — même patron de préréglages + échappatoire que
`PipelineScheduleEditor` (SP-15h).

### 3.7 — Sélecteur de couches et retrait de Martin

`shell/src/api/itemClient.ts` :

- `fetchMartinSources` (l.393-411) **retiré**. `listLayerSources` (l.619)
  passe de quatre agrégats à trois.
- `fetchCoreCollections` (l.413-431) rend désormais une source
  **`kind: "vector"`** par collection : `tilesUrl` pointant sur la route du
  cœur, `collectionId`, et `geometryKind` déduit du `geometryType` déjà
  présent dans la réponse `/collections` (`collections/routes.py:132-146`).
  Une entrée par collection, plus deux.
- `LayerSource` perd `service: "martin"` de son union.

Câblage retiré : labels Traefik de `martin` et middleware `strip-tiles`
(`docker-compose.prod.yml:36-43`), `VITE_MARTIN_URL` (overlay prod l.147,
`shell/src/config.ts:55`, `shell/playwright.config.ts:15`). Le service
`martin` **reste** sur le réseau interne. `MARTIN_SECRET` reste ce qu'il est
— une variable orpheline documentée comme telle depuis SP-1d3, hors
périmètre.

## 4. Décisions prises en session (2026-08-22)

1. **Périmètre = 4.1 seul.** 4.2/4.3 (symbologie, classes, palettes) partent
   en SP-25. Raison : lier une couche tuilée à sa collection est le prérequis
   **commun** au popup et aux bornes de classes ; le faire d'abord donne un
   ordre de dépendance propre.
2. **Les tuiles sont servies par le cœur**, pas par Martin, plutôt que de
   poser un popup sur le chemin non authentifié ou de deviner le
   `collectionId` par identité de nom de table.
3. **La route publique `/tiles` est retirée dans ce SP**, pas renvoyée à un
   suivi de sécurité.
4. **Modèle de popup = liste de champs + gabarit en échappatoire.** Écarté :
   « tous les champs, masquage opt-out » (l'auteur ne contrôle ni l'ordre ni
   les libellés) et « gabarit seul ».
5. **Le gabarit est du markdown à placeholders `${…}` évalués en CEL.**
   Écarté : les lignes `{label, value: {$expr}}` (pas de mise en forme
   libre), et le gabarit-comme-expression-CEL-unique (hostile à écrire à la
   main). Coût accepté : une seconde syntaxe d'expression dans le dépôt, à
   documenter et à tester.
6. **Une seule entrée par collection dans le sélecteur**, tuilée. Écarté :
   deux entrées « tuilé ou GeoJSON » — ce serait demander à l'auteur un
   arbitrage technique qu'il n'a pas les moyens de trancher.
7. **L'index GiST entre au périmètre**, avec sa migration de rattrapage.

## 5. Ordre d'exécution recommandé

Le cœur d'abord : le shell ne peut pas être prouvé sans la route.

1. Route MVT + garde + RLS + bornes + 204 (`features/tiles.py`), montée dans
   `main.py`.
2. Index GiST dans `apply_collection_ddl` + migration 0028.
3. Régénération OpenAPI + types TS. **Le diff sera non vide** : la route est
   montée inconditionnellement, contrairement au précédent `CORE_ETL_ENABLED`
   où la spec régénérée ne bougeait pas.
4. Types `PopupConfig`/`MapLayer` des deux côtés (TS + `configs/schemas.py`).
5. `MapView` : type dérivé de `geometryKind`, handler de clic sur `vector`,
   `transformRequest` sur les tuiles du cœur.
6. `MapPopup` + interpolation du gabarit (module pur, testable seul).
7. `PopupEditor`, monté sur les deux surfaces.
8. `listLayerSources` : retrait de Martin, collections en `vector`.
9. Retrait du câblage Martin (compose, `config.ts`, `playwright.config.ts`).
10. Spec E2E de la preuve du plan.

## 6. Validation & preuves de sortie

1. **La preuve du plan**, en spec E2E Playwright : cliquer une entité d'une
   collection servie en tuiles MVT ouvre un popup renseigné, sur une carte
   publiée, sans widget d'app à côté.
2. `@pytest.mark.postgis` sur la route MVT : tuile non vide portant les
   colonnes attendues et **jamais** `tenant_id` ; un tenant B ne voit pas les
   lignes du tenant A — **preuve de RLS, pas preuve de `WHERE`** (le test
   passe par `rls_scope`, pas par un filtre applicatif) ; collection privée +
   anonyme → 404 ; collection publique + anonyme → 200.
3. `z`/`x`/`y` hors bornes → 400 ; collection sans géométrie → 400 ; tuile
   vide → 204.
4. Index GiST : créé par `apply_collection_ddl` (test postgis) ; migration
   0028 rattrape une collection préexistante ; `downgrade()` testé sur base
   non vide (le défaut de la migration 0024 de SP-17b, qui échouait sur des
   lignes existantes).
5. Interpolation du gabarit, module pur : placeholder non fermé, accolades
   imbriquées, expression invalide, champ absent, valeur objet, et
   **`<img onerror=…>` dans une valeur de propriété neutralisé** par
   `sanitizeMarkdown`.
6. Régression du `type: "fill"` inconditionnel : une collection de points
   tuilée est rendue en `circle`.
7. Un test de `PopupEditor` **par surface** (visionneuse et widget carte).
8. Le clic reste additif : un test prouve que `itemSelected` est toujours
   émis et que le cross-filter est toujours alimenté quand un popup est
   configuré.
9. Portes habituelles. Cœur : `uv run pytest` sans baisse par rapport à la
   référence (1675 passed / 154 skipped au 2026-08-22), `ruff check`,
   `ruff format --check`, `mypy --strict` sur les 4 modules, `lint-imports`,
   couverture ≥ 85. Shell : `npm run lint`, `format:check`, `test` (référence
   155 fichiers / 1302 tests), `build`, `e2e`, couverture ≥ 88 — **mesurée
   après nettoyage de `dist/` et `dist-export/`**, piège documenté par SP-22
   tâche 5 et reconfirmé par SP-23.
10. **OpenAPI et types TS régénérés**, diff non vide et committé. Classe
    d'oubli la plus récurrente du dépôt. La commande littérale
    `uv run python scripts/export_openapi.py` **échoue seule**
    (`ModuleNotFoundError: app`) : il faut l'incantation réelle de `ci.yml`
    (`PYTHONPATH=.` + `CORE_SECRETS_MASTER_KEY` de test), écart documenté par
    SP-23 tâche 19.
11. `core/tests/test_deployability.py` toujours vert après le retrait de
    `VITE_MARTIN_URL` et des labels Traefik.

## 7. Risques et limites connues

- **Changement cassant.** Le retrait de la route publique `/tiles` casse
  l'affichage des couches Martin des cartes existantes, sur une `v0.1.0`
  déjà publiée. Pour une collection, l'auteur retrouve strictement mieux en
  la re-ajoutant depuis le sélecteur (tuilée, interrogeable, autorisée) ;
  pour une table PostGIS ajoutée à la main hors registre, **il n'y a pas de
  chemin de remplacement dans SP-24**. À écrire dans les notes de version.
- **D2 reste vrai dans le widget carte d'app** (§2), plafond de 100 entités
  inclus.
- **Une seconde syntaxe d'expression** entre dans le dépôt avec le gabarit
  (§3.5). Assumé, mais c'est une divergence de convention qu'une revue
  future signalera légitimement.
- **Une valeur de propriété est interprétée comme du markdown** (§3.5).
  DOMPurify borne le risque à l'injection HTML, pas au rendu inattendu.
- **Le coût des tuiles n'est pas mesuré.** L'index GiST supprime le scan de
  table, mais aucun chiffre de latence par tuile n'est produit par cette
  spec. Si l'usage réel le justifie, un cache de tuiles est une décision
  produit séparée — et pas Redis, sorti au jalon M1.
- **Aucune entrée d'audit par tuile** (§3.1). Une lecture massive de données
  par le chemin tuilé ne laisse donc pas de trace individuelle ; seul le
  `can()` la borne.
