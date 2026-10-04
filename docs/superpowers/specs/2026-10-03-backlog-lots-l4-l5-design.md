# Backlog — Plan B : lots L4 (reliquats backend P16–P29) et L5 (shell UX, copilote, features)

**Date :** 2026-10-03. **Source :** `docs/revue/2026-09-04-backlog.md`. Revérifié dans le code le
2026-10-03 (piège n°12). Plan : `docs/superpowers/plans/2026-10-03-backlog-lots-l4-l5.md`.
Sous-points « rejeu stack réelle » → lot L6 ; « décision produit » → lot L1 : tous **hors périmètre**.

REV couvertes : 274, 276, 277, 278, 279, 280, 281, 282, 283, 288, 289 (L4) ;
239, 254, 265, 251, 284, 285, 286, 287, 293, 183, 184, 102, 104 (L5).

**Écarts avec le backlog (déjà fermés, à clore au backlog sans code) :** 277(b) (`page=0` → 422
déjà en place ; reste la bascule du test j09-005 → L6), 282(d) (quota à la création du job), 288(a)
côté ingestion (reste les tâches pipeline), REV-239 (cf. plan A).

## L4 — Reliquats backend

### REV-274 (codables : c, d)
- (c) `instance/routes.py:93-96` seuil « stalled » codé en dur → `CORE_STALLED_JOB_MINUTES`
  (documentée dans `.env.example`, injectée dans l'`environment:` compose) ; sonde CDC `routes.py:77-81` :
  slot absent → `{"configured": false}` et état distinct côté shell ; `_CDC_SLOT` (l.27) remplacé par
  `from app.cdc.consumer import SLOT_NAME` (vérifier `lint-imports`, frontière `instance`→`cdc`).
- (d) `docker-compose.yml:765` Grafana : `127.0.0.1:${GRAFANA_HOST_PORT:-3001}:3000` ; auditer les autres
  ports hôte d'observabilité/Martin/TiTiler ; règle dans `test_deployability.py`.

### REV-276 (b, c, d)
- (b) Lien « enregistrements » dans `HarvestSourcesAdminPage.tsx` vers `GET /harvest/sources/{id}/records`
  (méthode `ItemClient`, hook, clé i18n, test).
- (c) Unicité `(tenant_id, type, url)` : normalisation d'URL (slash final, schéma/hôte en minuscules)
  dans le service **avant** `find_duplicate_source` et à l'écriture ; migration Alembic
  `UNIQUE (tenant_id, type, url)` qui dédoublonne explicitement ou échoue proprement ; `Index(unique=True)`
  déclaré dans le modèle (comparateur modèle↔Alembic) ; `IntegrityError` → 409. **Migration testée sur
  base non vide**, avec/sans doublons, upgrade et downgrade (piège n°8).
- (d) Backoff : colonne `consecutive_failures` (même migration), intervalle × 2^n plafonné dans
  `list_due_sources`.

### REV-277 (c, d)
- (c) Règle « lac sans fichier → ligne à 0 » reportée dans `run_collection_aggregate`
  (`aggregate.py:533`), à la source (jumelle du chemin d'alerte `alerts/jobs.py:222`). Test : `agg=count`
  sans groupBy sur collection sans parquet → `[{"count": 0}]`.
- (d) `notify_channels` JSON par canal (migration, base non vide) ; relance des seuls canaux en échec ;
  notification in-app posée une seule fois par épisode (`alerts/jobs.py:543-556`).

### REV-278 (c, e)
- (c) Valider que `m.to`/`m.from_` référencent un widget ou une variable existants
  (`configs/document_validation.py:112-117`) — **risque de rejeter des configs existantes** : appliquer
  à l'écriture seulement (règle déjà posée P21), jamais à la relecture ; test de refus.
- (e) Afficher `errors[]` du 7807 côté shell (re-vérifier P22.02/P22.04 avant de rouvrir).
- (b) cel-python : dépendance neuve + compatibilité de grammaire cel-js → **décision L1**, hors plan.

### REV-279 (b, d, e)
- (b) Filtre `refreshPolicy.enabled` en SQL (JSON) au lieu de Python dans `alerts/repository.py:149-160`
  (idem pipelines/rapports) ; pas de colonne dérivée sauf nécessité mesurée.
- (d) `introspection_pg.py:83` : cache LRU borné (`OrderedDict`, ~512) + test.
- (e) Filtre `tag` (`items/repository.py:598-640`) : `keywords::jsonb @> :v` côté Postgres.
- (a) estimation `reltuples` au-delà d'un seuil : **hors plan** (keyset = changement d'API, L1).

### REV-280 (c, g)
- (c) Test jsdom de `sqlEditorKeys` (`SqlLabPage.tsx:54`) dans `SqlLabPage.test.tsx`.
- (g) `-c timezone=UTC` à la connexion du moteur ; test `SHOW timezone`.

### REV-281 (a, c, e, f, g)
- (a) rapport de couverture par module en CI ; (c) règle d'alerte/sonde sur `.last_success` ;
  (e) hook `actionlint` pre-commit (jumelles `_build-and-push.yml`, `release.yml`, `publish-edge.yml`
  à passer au hook) ; (f) `backup.sh:123-129` : exécuter la rotation hors-site même si l'envoi échoue,
  puis `exit 75` ; (g) entrypoint Traefik :8080 non joignable depuis le tailnet dans
  `docker-compose.prod.yml` + règle `test_deployability`.
- (b) cosign/digests : L1. (d) `stack-smoke` : L6.

### REV-282 (b, c, e)
- (b) `importer.py:375` renvoie `item_id=ds_item.id` **et** le type de ressource dans le job ; le shell
  (`ImportFileButton.tsx:252`) navigue selon le type (`/datasets/{id}` vs `/maps/{id}`) — ne pas
  renseigner `item_id` seul (navigation fausse). OpenAPI + types TS à régénérer ; round-trip côté lecture
  (piège n°5). Test : import CSV → job porte l'id dataset, le shell ouvre `/datasets/{id}`.
- (c) `_FLOAT_RE` (`importer.py:106`) accepte la virgule décimale ; **ambiguïté `1,234`
  (milliers/décimal) : seule la forme `\d+,\d{1,2}` hors séparateur détecté `,` est convertie ; sinon
  inchangé** ; tests des deux cas.
- (e) Message du 409 de `DELETE /collections/{id}` (`collections/routes.py:658`) orienté utilisateur.

### REV-283 (b, c, d)
- (b) `ETag` (hash des octets) + 304 sur `If-None-Match` dans `features/tiles.py:191` ; tests des
  deux chemins ; `Vary: Authorization` conservé.
- (c) `harvest/routes.py:550` `_EXPORT_ITEMS_CAP` → constante commune lue de `CORE_EXPORT_ITEMS_MAX`
  (même source que `features/routes.py:383`) ; vérifier la variable dans l'`environment:` du service core.
- (d) `map/viewportTiles.ts:10` : store par carte ou publication à `null` au démontage.
- (a)(e) clustering bas zoom, export en flux : L1. (f) mesure `EXPLAIN` 10^6 : L6.

### REV-288 (a)
Vérifier que les tâches pipeline d'écriture appellent `check_quota_or_raise` ; attraper
`QuotaExceededError` (comme `ingestion/tasks.py:153`) → statut de job lisible + notification
(jumelle : piège n°14). (b) plancher dérivé d'un artefact CI : L1.

### REV-289 (a, b)
- (a) `/sitemap.xml` rend un `<sitemapindex>` et `/sitemap-{n}.xml` au-delà du plafond ; test avec
  plafond abaissé par monkeypatch.
- (b) `public/routes.py:86` : préfixe `/api/v1` dérivé d'un réglage de déploiement (comme `base_url`) ;
  grep des autres `"/api/v1"` dans `core/app`.

## L5 — Shell UX, accessibilité, copilote

### REV-254 — bannière de connectivité sur les mutations
`shell/ConnectivityBanner.tsx:28` n'écoute que le `QueryCache`. Ajouter un abonnement au `MutationCache`
(`updated` + `status==="error"` + `CoreUnreachableError`, clé `mutationId`, retrait au succès). Test :
mutation rejetant `CoreUnreachableError` → bannière. (`PUT` S3 présigné de `exportsIngestion.ts:78` :
exception assumée.) Coupure réelle du cœur → L6.

### REV-265 — autocomplétion SQL Lab après restauration d'historique
`SqlLabPage.tsx:104-158` : ajouter `collectionsQuery.data` (pas `knownCollectionIds`, tableau neuf à chaque
rendu) aux dépendances ; la condition `!(id in schemaByCollection)` empêche déjà le refetch par frappe.
Test : `GET /v1/collections` retardé + `?historyId=` → autocomplétion sans frappe supplémentaire.

### REV-251 — `readOnly` pendant le chargement
`VisualQueryWizardPage.tsx:68-69` : `readOnly = pipelinePk !== null && itemQuery.isSuccess && !hasPermission(…)`,
bouton désactivé pendant `isLoading`. **Relire le patron réel de `PipelineBuilderPage.tsx`** avant de le
copier (non vérifié). Test : `getItem` en attente → pas de « Modification réservée ».

### REV-284 (b, c, e)
(b) `<h1 className="sr-only">` (titre de l'item) dans `EmbedPage`, `SitePublicPage`, `PublicItemPage` ;
(c) `<h2 sr-only>` « Résultats » avant la grille de `CatalogPage` ; (e) ratio de contraste WCAG
(`muted` vs `background`) avec avertissement dans `ThemePanel`. Tests `getByRole("heading",{level})`.
(a)(d) rejeu/lecteur d'écran : L6.

### REV-285 (c, d, f, g)
(g) `lib/format.ts` : garde `Number.isFinite` (« — ») pour les nombres, test ; (c) détecteur de clés i18n
inutilisées (scan catalogue vs sources) ; (d) `scripts/check-raw-colors.mjs` étendu à `.ts` avec pragma pour
les palettes de dataviz ; (f) `UsagePage.tsx:21-30` : résolution groupée des titres (un appel API d'usage
enrichi, pas un `getItem` par ligne — OpenAPI + types TS). (b) 73 `h-8` : migration à l'occasion, hors plan.

### REV-286 (d, e, f)
(e) `touchcancel` → annulation du tracé (`MapMeasureSketchToolbar.tsx:380`), pas validation ; (d)
`ResizeObserver` sur le conteneur de `MapPopup` (clamp recalculé) ; (f) `ScrollRestoration`/reset au
changement de route. (a) mode 2 volets de `TriptychLayout` : chantier à part, L1. (c) appareil réel : L6.

### REV-287 — copilote
(a) `CopilotChat.tsx:75-96` : `invalidateQueries` des requêtes de l'item **après** `copilotTurn` réussi
(clés réelles à chercher dans `api/hooks`, non vérifiées) ; (b) `core/app/copilot/routes.py:376-383`
`except Exception: pass` → `logger.exception("copilot.turn audit failed")` ; test `caplog`, réponse 200.

### REV-293 — double montage StrictMode
`mapDeckTerrain.ts:85-94` : libération idempotente (`WeakSet` de contextes détruits), dev uniquement ;
test sur double appel.

### REV-184 — 5 Minor GAP-17
1. `applyVisualQueryClientOp.ts` : statut par jambe (filters/join/summary) et message listant les jambes
   ignorées ; 2. `visualQueryClientTools.ts` : `sourceColumn ?? null`, `p ?? null` côté client ;
3. valider `join.on` contre le schéma de base (vérifier qu'il ne faut pas inclure les colonnes ajoutées
   par la jointure) ; 4. commentaire `knownColumnNames` (relire, peut-être déjà corrigé) ;
5. `SqlLabPage.tsx:85` : commentaire sur la troncature à 100 collections / course de chargement.

### REV-183 — NL→CEL v1 (`visibleWhen` uniquement)
Outil MCP `generate_cel_expression(itemId, question, availableFields)` dans
`core/app/mcp/tools/query_generation.py`, **même patron génération pure / jamais d'exécution** que
`generate_sql_query` ; ajouté à `copilot/tools_allowlist.py` ; shell : bouton « Générer » à côté de
`visibleWhen` (`builder/PropsPanel.tsx:36-42`), brouillon validé par `validateExpression`
(`builder/expr.ts`) et **jamais appliqué sans validation humaine**. Hors v1 : colonnes calculées,
actions, bindings. Inventaire de fonctionnalités + OpenAPI à mettre à jour.

### REV-102 — géocodage BAN v1
Module `core/app/geocoding/` : `GET /v1/geocode?q=` en **proxy côté cœur** (CSP `connect-src`, garde
d'egress SSRF), fournisseur enfichable derrière une petite interface, un seul fournisseur BAN
(`api-adresse.data.gouv.fr`) ; hôte dans l'allowlist d'egress ; module déclaré dans `lint-imports` ;
shell : contrôle de recherche d'adresse dans `map/` près de `CameraControls.tsx` avec `flyTo`.
Inventaire de fonctionnalités, OpenAPI + types TS. Hors v1 : widget de recherche, outil MCP.

### REV-104 — animation temporelle v1
`builder/TimePlayer.tsx` (play/pause, vitesse, pas fixe) faisant avancer une fenêtre glissante via
`setTimeRange` (`builder/AnalyticsContext.tsx`), timer nettoyé au démontage ; bornes et pas dans la config
(nouvelle propriété d'`AppConfig`/widget → `configs/schemas.py`, OpenAPI + types TS). **À vérifier avant
plan : que le widget carte applique réellement `timeRange` à ses couches** (non confirmé dans `MapView`).
Tests `vi.useFakeTimers` + une spec E2E. Hors v1 : interpolation, export vidéo, pas irréguliers.

## Transverse
Régénérer OpenAPI + types TS ; inventaire de fonctionnalités et bilan à la clôture ; `lint-imports`
(nouveau module `geocoding`) ; migrations testées sur base non vide (276, 277) ; `CLAUDE.md` §Livré
(une ligne) + archive ; ledger `.superpowers/sdd/backlogB-*`. Les sous-lots 102/104/183 sont des
fonctionnalités : chacun peut être planifié/exécuté séparément du reste de B.

## Hors périmètre
L1 (278(a)(b), 279(a) keyset, 280(a)(e)(f), 281(b), 283(a)(e), 286(a), 288(b)) ; L6 (274(a)(b),
276(a), 277(a), 278(d), 279(c), 280(b)(d), 281(d), 282(a), 283(f), 284(a)(d), 285(i), 286(c)).
