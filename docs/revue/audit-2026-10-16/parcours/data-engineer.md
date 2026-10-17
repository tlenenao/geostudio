# Parcours persona : Data engineer (stack réelle locale, OIDC Keycloak)

Date : 2026-10-16, HEAD `c0251b66`. Scénario : construire un pipeline (connecteur REST + transformations + `writer.collection`), planifier, relancer après échec, lineage.
Captures : `docs/revue/audit-2026-10-16/parcours/data-engineer/*.png` (plus `_console.log` et `_network.log`, journaux bruts de la session). Aucun fichier source édité, rien commité, ni `postgis-test` ni suite de tests.

## 0. Conditions de test (à lire avant les notes)

- Compte Keycloak `alice` (rôle Créateur : `automation.manage`, `automation.secrets.manage`, `data.manage`, pas admin ; `GET /v1/me`). Chromium headless (Playwright `connectOverCDP`, 1440x900, TZ Europe/Paris), scripts hors dépôt.
- Deux adaptations d'environnement (déjà constatées par l'audit « analyste SIG », F1/F2 de leur rapport) : le shell servi sur `:8300` est en `VITE_AUTH_MODE=mock` alors que le cœur est en `oidc` ; j'ai réécrit `env-config.js` côté navigateur (`route`) au lieu de relancer le conteneur, et lancé Chrome avec `--disable-web-security` car le cœur (`:8200`) n'a pas de CORS pour l'origine `:8300`. Rien changé dans la stack.
- **Limite majeure : l'image qui tourne est périmée.** `docker images` : `geostudio-core`/`geostudio-shell` créées le 2026-10-11 11:59, HEAD du 2026-10-16. Preuves directes dans le conteneur : `docker exec geostudio-core-1 grep -c upsert /app/app/pipelines/ops/schemas.py` donne 0 (le mode upsert, commit `fbe98a22` du 10-13, est absent) ; les routes `/pipelines/runs/{id}/retry`, `/reader-state` et tout le module `app/lineage` n'existent pas dans le conteneur (`GET /v1/items/{id}/impact` : 404). Conséquence : « relancer après échec » et « lineage » **ne sont pas jouables** sur cette stack ; je les juge par lecture du code HEAD (marqué « code seulement » ci-dessous). Une tentative de monter une seconde instance HEAD isolée (base jetable + cœur HEAD) a été refusée par le classificateur de permissions (copie des variables d'environnement du conteneur, donc des secrets) : non rejouée.
- Données de test créées sur l'instance : item pipeline `8937aaa64e8e4f238d5355442d67c874` (titre vide, voir F1), collection cible `ingest_f4f78b925185` « DE audit - departements (cible) » (+ la carte créée en effet de bord par l'import, F6), secret `de-audit-geoapi` (clé factice), jeton webhook créé puis révoqué. Planification remise à « désactivée ». Source REST : `https://geo.api.gouv.fr/departements` (publique, 101 lignes).
- Mesures : LCP 0,79 à 0,88 s (éditeur de pipeline 880 ms, liste 788 ms, `/tasks` 812 ms) ; réseau idle 1,7 à 1,9 s ; axe-core (wcag2a/aa/21aa) : **0 violation** sur ces trois pages ; console : aucune erreur applicative hors les 422/500 provoqués (F4, F5, F9).

## 1. Chronologie et notes

| Étape | Durée mesurée | Note /10 | Résumé |
|---|---|---|---|
| 0. Connexion OIDC | 0,6 s redirection Keycloak, 2,35 s total | 8 | Fluide. |
| 1. Créer le pipeline (Nouveau > Pipeline > titre) | 1,0 à 1,9 s jusqu'au canevas | 5 | Le titre saisi est perdu (F1). Pas d'entrée « Nouveau pipeline » dans la vue Automatisation. |
| 2. Préparer la collection cible | import CSV 2 lignes ~2 s | 3 | Aucun moyen de créer une collection vide depuis le builder (F2) ; import CSV imposant lat/lon et créant une carte (F6). |
| 3. Poser et configurer reader REST + derive + writer | 4,7 s scripté (4 interactions par nœud) | 5 | Inspecteur brut (noms de champs techniques, F7), nœuds superposés (F3), ids d'op partout. Connexion par clic OK. |
| 4. Prévisualiser | 0,58 à 0,71 s par nœud | 7 | Rapide, pagination, révèle la normalisation de colonnes. Erreur de preview muette (F4), 500 sur expression invalide (F5). |
| 5. Exécuter, diagnostiquer 3 échecs | run serveur 0,6 à 0,85 s ; retour UI 5,0 à 6,6 s | 4 | 3 échecs successifs de schéma jamais détectés avant l'écriture (F8) ; messages bruts Python ; retour UI lent (sondage). |
| 6. Corriger et sauvegarder | enregistrement 116 ms | 3 | Les positions fractionnaires par glisser-déposer sont rejetées en 422 (F9, image périmée, corrigé HEAD). Contournement API nécessaire. |
| 7. Secret inline et exécution authentifiée | création 1,8 s | 8 | Création de secret dans l'inspecteur, liée à `baseUrl`, sélectionnable immédiatement. |
| 8. Planifier | enregistrement 1,2 s ; tir réel à 16:10:03 | 4 | « Toutes les 1 minute » accepté et prochaine échéance affichée à la minute, mais le balayage est */5 (F10) ; heures de l'historique décalées de 2 h (F11). |
| 9. Relancer après échec | n/a | 2 (stack) / 6 (code) | Sur la stack : aucun bouton, seulement « Exécuter » (nouveau run). Code HEAD : boutons Reprendre/Relancer (F12). |
| 10. Lineage | n/a | 1 | Aucune vue de lineage dans le shell, même au HEAD (F13). |
| 11. Webhook entrant | création 1,2 s ; déclenchement API 33 ms (202) | 7 | Fonctionne, jeton affiché une fois. |

Note globale du parcours : **4,3 / 10** (moyenne pondérée ; la construction/exécution et le diagnostic d'échec comptent le plus). Le moteur est solide (runs de 1 s, scheduling réel, webhook), c'est l'outillage d'auteur (titre, positions, messages, schémas cible) qui pénalise.

## 2. Blocages (classés)

1. **F8 : trois échecs de schéma d'affilée à l'écriture, rien ne prévient en amont** (nom de colonne normalisé par le lecteur REST, type entier de la cible, absence de renommage visible). Sans l'erreur Python brute, un data engineer n'a aucune piste.
2. **F2 : impossible de créer la collection cible depuis le pipeline** ; il faut un import de fichier détourné (CSV avec colonnes lat/lon fictives, carte créée en prime).
3. **F9 : le glisser-déposer des nœuds rend le pipeline inenregistrable** sur l'image qui tourne (422 sur positions fractionnaires). Corrigé en HEAD, mais l'image servie ne l'est pas (F3 du rapport analyste-sig).
4. **F13 : pas de lineage affichable** (aucune surface shell appelle `/lineage`), alors que c'est une exigence du scénario.
5. **F1 : titre du pipeline perdu** à la création (item enregistré avec `title: ""`), ce qui casse le catalogue et les notifications.

## 3. Constats détaillés

### F1. Titre perdu : l'item est créé avec un titre vide
- Observé : après « Nouveau > Pipeline > titre `DE audit - departements REST` », le H1 devient « Pipeline » dès la sélection du premier nœud ; `GET /v1/items/8937aaa6…` renvoie `"title":""` ; `GET /v1/notifications` renvoie `itemTitle: ""` et la cloche affiche « Élément supprimé » pour ces runs (capture `13a-cloche-notifications.png`).
- Cause (code) : le titre ne vit que dans `location.state` (`shell/src/shell/routes.tsx:164` et `:171`), lu par `PipelineBuilderPage` (`initialTitle`, `shell/src/pages/PipelineBuilderPage.tsx:385` : `title: initialTitle ?? ""`). Sélectionner un nœud écrit `?node=` via `setSearchParams(..., { replace: true })` (`shell/src/lib/useUrlSyncedState.ts:15-26`), qui ne repasse pas `state` : `initialTitle` devient `undefined`. Reproduit au clic sur n'importe quel nœud avant « Enregistrer ».
- Gravité : Important. Correctif évident : conserver `state` dans `setSearchParams` (option `state`) ou copier le titre dans un `useState` initial.

### F2. Aucune création de collection cible dans le builder
- `CollectionParamSelect` n'offre que « Choisir… » + les collections inscriptibles existantes (`shell/src/builder/pipeline/CollectionParamSelect.tsx:25-43`), sans action « Créer ». `createEmptyCollection` n'est utilisé que par l'assistant de requête visuelle (`shell/src/pages/VisualQueryWizardPage.tsx:367`) ; `/admin/collections` répond « Accès réservé aux administrateurs » à un Créateur (capture `03a-admin-collections.png`).
- Contournement vécu : import d'un CSV de 2 lignes avec colonnes `lat,lon` fictives. Sur l'image servie, l'import CSV exige lat/lon (le bouton « Importer » ne ferme pas la fenêtre sans elles, boucle de 30 s mesurée, `03e`) ; le code HEAD propose « sans géométrie » (`shell/src/shell/ImportFileButton.tsx:540`, `importFile.geometryModeNone`), donc ce volet est corrigé HEAD, pas le manque de création de collection. L'import redirige en outre vers l'éditeur de carte (F6).
- Gravité : Important (le schéma de la cible doit en plus être deviné, voir F8).

### F3. Positionnement des nœuds : superposition, graphe partiellement hors canevas
- Ajout par la palette : position `(40, 40 + n*90)` (`PipelineBuilderPage.tsx:376-377`) ; insertion sur une arête : `x: 0, y: 0` (`PipelineBuilderPage.tsx:349-351`). Constaté : le nœud inséré recouvre le lecteur, coupé à gauche du canevas, et **son bouton « + » est masqué** par le nœud voisin (Playwright : « subtree intercepts pointer events », 30 s de timeout ; capture `08z-layout-chevauchement.png`, `08d-apres-insert.png`).
- Gravité : Moyen (contournable par glisser, mais voir F9).

### F4. Erreur d'aperçu muette
- Toute erreur de `preview` s'affiche « Aperçu indisponible. » (`shell/src/builder/pipeline/PipelinePreviewPanel.tsx:76-80`, i18n `pipelinePreview.unavailable`), sans le `detail` RFC 7807 que l'API fournit. Pendant la saisie, des 422 de preview partent aussi à chaque frappe sur un nœud incomplet (`_network.log` : 6 POST `preview` en 422 sur 100 ms).
- Gravité : Moyen.

### F5. Expression SQL invalide dans `derive` : HTTP 500 sur l'aperçu
- Reproduit par API (`POST /v1/pipelines/{id}/preview?upTo=<derive>` avec `expr: "nom || ("`) : `500 {"detail":"internal server error"}` ; le journal du cœur montre `SqlSandboxError: syntax error at or near ")"` levée par `validate_bounded_expr` (`core/app/pipelines/expr_validation.py:21` via `_validate_node_exprs`, `core/app/pipelines/runtime.py:667-681`).
- Vérifié sur HEAD : `_validate_node_exprs(conn, node)` est appelé à `runtime.py:895`, **avant** le `try ... except duckdb.Error` du nœud (`runtime.py:955`), et la route ne convertit que `PipelineRuntimeError` (`core/app/pipelines/routes.py:295`) ; `SqlSandboxError` (`core/app/analytics/sql_sandbox.py:38`, « destinée à un 400 ») n'en hérite pas. Le défaut est donc **toujours présent en HEAD**. L'utilisateur voit « Aperçu indisponible » (F4) et la console un 500.
- Gravité : Important (faute de frappe courante = erreur serveur et journal d'exception).

### F6. Import de CSV : effets de bord inattendus pour un data engineer
- L'import d'un CSV crée en plus un item carte « DE audit - departements (cible) » et redirige vers `/maps/dbaf6af7…` (« Éditeur de carte », capture `03h-import-fin.png`). Le catalogue se remplit de cartes issues d'imports de pure donnée.
- `featureCount` de la collection reste à 2 après un run écrivant 101 lignes (voir F14).
- Gravité : Mineur.

### F7. Inspecteur de nœud : champs techniques bruts, aucune aide
- Noms Python/JSON bruts (`baseUrl`, `recordsPath`, `paginator`, `paginatorConfig`, `column`, `expr`, `columns`), options `none/page_number/cursor/offset`, aucune description de champ ni exemple ; `derive.expr` est du SQL DuckDB brut, sans indication. Palette : identifiants d'op (`reader.connector.rest`, `transform.bulkRenameAttributes`…) comme libellés (`shell/src/builder/pipeline/PipelinePalette.tsx:117`) avec la docstring Python comme description (`:124-126`, 58 entrées ; contient des références internes type « REV-110 », « vérifié empiriquement contre DuckDB »). Titres de nœuds = id d'op (`PipelineBuilderPage.tsx:354`, `:368`). Capture `02c-inspector-rest.png`, `02b-reader-ajoute.png`.
- Le mode d'écriture n'offre que `append`/`replace` sur l'image servie ; HEAD déclare `upsert/update/delete` (`core/app/pipelines/ops/schemas.py:68`) : non vérifié dans l'UI faute d'instance HEAD.
- Gravité : Moyen (parcours long à apprendre pour un public non développeur ; atout pour un data engineer).

### F8. Échecs de schéma à l'écriture, jamais détectés en amont
Trois runs consécutifs échouent (`/v1/pipelines/{id}/runs`, captures `05b`, `07b`, `08f`) :
1. `unknown property 'code_region'` : le lecteur REST (dlt) renomme `codeRegion` en `code_region`. L'aperçu du nœud reader le montre (colonnes `nom code code_region`), mais rien ne rapproche ce nom du schéma de la cible.
2. `codeRegion: expected integer` : l'API source renvoie `"84"` (chaîne), la cible est un entier. `transform.select` ne sait que renommer ; il faut un `derive` avec `CAST(... AS INTEGER)` puis un `select`.
3. Le message affiché est la représentation Python brute `writer.collection: invalid row: [{'field': ..., 'code': ..., 'message': ...}]`, sans numéro de ligne ni nœud ; le détail du run liste seulement les nœuds réussis (`reader.connector.rest : 101`, `transform.derive : 101`, `transform.select : 101`), pas le nœud en échec (capture `11a-detail-run-echoue.png`).
- L'aperçu s'arrête avant l'écriture : il ne confronte jamais le flux au schéma de la collection cible.
- Gravité : Important (cœur de la douleur du parcours).

### F9. Positions fractionnaires : le pipeline devient inenregistrable après un glisser (image périmée, corrigé HEAD)
- Après avoir déplacé deux nœuds à la souris, « Enregistrer » renvoie 422 `pipeline.nodes.3.y: Input should be a valid integer, got a number with a fractional part` (`_network.log`, PUT `/v1/configs/by-item/…` 16:07:08). Image : `PipelineNode.x/y: int` (`docker exec geostudio-core-1 sed -n '/class PipelineNode/,/^class PipelineEdge/p' /app/app/configs/schemas.py`). HEAD : `x: float`, `y: float` (`core/app/configs/schemas.py:315-316`). Corrigé dans le code, absent de la stack.
- Contournement : `PUT /v1/configs/by-item/{id}` avec positions entières (ajout du nœud de conversion et réécriture du graphe par API).

### F10. Planification : granularité réelle de 5 minutes, non signalée
- L'éditeur accepte « Toutes les 1 minute » (`min={1}`, `shell/src/builder/pipeline/PipelineScheduleEditor.tsx:160`) et affiche « Prochaine exécution : 16/10/2026 18:10:00 » (capture `12a`). Réalité : le balayage est `@app.periodic(cron="*/5 * * * *")` (`core/app/pipelines/jobs.py:433`). Mesuré : unique tir à 16:10:03 (5,3 s de latence après l'échéance), rien à 16:11 ni 16:12 (journal worker : `run_pipeline_sweep_task(timestamp=1792167000)` 16:10:03, `lasted 0.240 s`).
- Aucun texte n'explique cette granularité. Gravité : Moyen (promesse d'UI fausse).

### F11. Heures de l'historique décalées de 2 h (UTC naïf lu comme local)
- Panneau d'exécution : « Terminé 16/10/2026 16:08:02 » alors que l'heure locale réelle était 18:08 (`date` : 18:08 CEST / 16:08 UTC) ; le même panneau affiche « Prochaine exécution : 16/10/2026 18:15:00 » (correct). Cause : `startedAt` est un `DateTime` naïf (`core/app/pipelines/models.py:38`) sérialisé sans fuseau (`startedAt=r.started_at.isoformat()`, `core/app/pipelines/routes.py:160-161`, valeur `2026-10-16T16:08:02.666938`) alors que `nextRun` porte `+00:00` ; `formatDateTime` (`shell/src/lib/format.ts:12-17`) fait `new Date(iso)` qui lit une chaîne sans fuseau comme heure locale, puis affiche en `Europe/Paris`. Même chose pour `/tasks` (dates ISO brutes `2026-10-16T16:10:02.976592`) et les jetons webhook (image périmée : ISO brut).
- Toujours présent en HEAD (même sérialisation et même formateur). Gravité : Important (un data engineer corrèle des runs avec des logs ; erreur de 1 à 2 h selon la saison).

### F12. Relancer après échec : pas de bouton sur la stack, présent en code HEAD
- Stack : après un échec, l'UI ne propose qu'« Exécuter » (nouveau run, brouillon éventuellement non enregistré) ; la route `retry` n'existe pas dans le conteneur. Avec `replace` (seul mode idempotent sur l'image) et `append`, une relance sans réflexion duplique ou vide la cible ; la notice « replace supprime TOUTES les données » existe.
- Code seulement : HEAD a `POST /pipelines/runs/{run_id}/retry` (`core/app/pipelines/routes.py:120-134`) et, dans le panneau, « Reprendre » / relancer depuis le début sur un run `failed` (`shell/src/builder/pipeline/PipelineRunPanel.tsx:85-99`, handler `:275-282`, i18n `pipelineRun.resumeButton`). Non rejoué.
- Les erreurs de lancement : le run `failed` est conservé dans l'historique avec le message ; la cloche liste chaque échec (non lu).

### F13. Lineage : aucune surface dans le shell, route absente de la stack
- Stack : `GET /v1/items/{id}/lineage` et `/impact` : 404.
- Code : le cœur HEAD expose `/items|collections/{id}/impact|lineage` (`core/app/lineage/routes.py:68-104`, outil MCP `get_item_impact`), mais le shell n'appelle que `/impact` (`shell/src/api/domains/impact.ts:10-12`), utilisé uniquement dans le dialogue de **suppression** (`shell/src/shell/ItemActions.tsx:114`, `shell/src/pages/CollectionsAdminPage.tsx:374`). Aucun appel à `/lineage` côté shell, aucun graphe amont/aval dans l'éditeur de pipeline, la fiche dataset ou la collection. Le champ « lineage » des collections est un simple texte libre de métadonnées (`shell/src/shell/EditCollectionPanel.tsx:219-220`).
- Gravité : Important pour ce persona (le lineage n'est consultable que par API/MCP).

### F14. `featureCount` périmé après écriture de pipeline
- Constaté : collection importée avec 2 lignes ; après run `replace` de 101 lignes, `GET /v1/collections/ingest_f4f78b925185/items` donne `numberMatched: 101` mais `GET /v1/collections` donne `featureCount: 2`. Image périmée certes, mais le code HEAD ne corrige pas : `collection_writer.py:496-497` (`delta = res.inserted - res.deleted if mode in ("upsert", "update", "delete") else 0`) ne met à jour `collections.feature_count` que pour ces trois modes ; **`append` et `replace` ne touchent jamais le compteur** (aucune autre écriture dans `core/app/pipelines/`, `insert_features` ne compte pas non plus). Le compteur alimente le catalogue/DCAT/STAC et le plafond d'analyse (`core/app/pipelines/analysis.py:334, 452`).
- Gravité : Important (métadonnées fausses, garde d'analyse faussée).

### Points positifs vérifiés
- Garde de brouillon : quitter une page avec modification non enregistrée déclenche bien la confirmation navigateur (rejet de `goto`, `ERR_ABORTED`).
- Badges de comptage de lignes par nœud sur le canevas (101) après un run ; aperçu paginé (« Lignes 1–20 sur 50 », plafonné à 50 sur 101 sans l'indiquer, mineur).
- Secret inline lié à `baseUrl`, jeton webhook (202 en 33 ms, `succeeded` en 1 s), jeton non ré-affichable ; révocation immédiate sans confirmation sur l'image servie (HEAD a un dialogue : `PipelineWebhookTrigger.tsx:57`).
- Run côté serveur de 0,6 à 1,2 s ; latence d'affichage de l'état final 5,0 à 6,6 s (sondage), perceptible (F8, étape 5).
- a11y : 0 violation axe sur les trois pages ; LCP < 0,9 s.

## 4. Non rejoué, et pourquoi

| Point | Statut | Raison |
|---|---|---|
| Reprise depuis un point de contrôle, retry exponentiel, `writer.collection` upsert/quarantaine `__rejected` | non rejoué | absents de l'image servie (F3 du rapport analyste-sig) ; seconde instance HEAD refusée par les permissions (secrets du conteneur) |
| Lineage / impact graphique | non rejoué | route 404 sur la stack ; aucune UI shell au HEAD (F13) |
| Planification cron avancée, incrémental dlt | non rejoués | hors temps raisonnable ; seule la planification par intervalle a été vérifiée (tir réel) |
| Vue d'impact à la suppression d'un pipeline | non rejoué | suppression non nécessaire ; absente de l'image |

## 5. Recommandations

1. Corriger F1 (titre via `state`) et F14 (compteur sur `append`/`replace`) : deux défauts de HEAD à portée de main.
2. Convertir `SqlSandboxError` en `PipelineRuntimeError` avant le `try` de `runtime.py:895` (F5) et afficher le `detail` dans le panneau d'aperçu (F4).
3. Ajouter à l'aperçu du nœud writer une comparaison au schéma de la cible (colonnes inconnues, types) avant exécution (F8), et un « Créer la collection depuis ce flux » (F2).
4. Sérialiser `startedAt`/`finishedAt` avec fuseau (`isoformat` sur UTC aware) ou normaliser dans `formatDateTime` (F11) ; documenter ou changer la granularité du balayage (F10).
5. Reconstruire et redéployer l'image locale à chaque jalon (F9, F12 et le mode upsert ne sont visibles qu'avec HEAD), avant de rejouer ce parcours.
6. Exposer le lineage dans le shell (`/lineage` côté `ItemClient`, vue graphe sur la fiche collection et l'éditeur de pipeline) (F13).
