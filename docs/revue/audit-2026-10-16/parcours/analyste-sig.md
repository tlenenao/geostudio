# Parcours persona : Analyste SIG (stack réelle locale, OIDC Keycloak)

Date : 2026-10-16, HEAD `c0251b66`. Scénario : importer un GeoPackage de 50 000 entités, styliser, popups, publier, partager à un groupe, imprimer un atlas.
Captures : `docs/revue/audit-2026-10-16/parcours/analyste-sig/*.png`. Aucun fichier source édité, rien commité, pas de `postgis-test`, pas de suite de tests.

## 0. Conditions de test (à lire avant les notes)

- Stack `docker compose` déjà levée. Comptes Keycloak `alice` (propriétaire) et `bob` (membre du groupe) du realm (`deploy/keycloak/geostudio-realm.json:2290,2305`). Navigateur : Chromium headless Playwright 1.x (viewport 1440x900), scripts hors dépôt.
- Jeu de test : `parcelles50k.gpkg` (6,2 Mo, 50 000 points WGS84, colonnes `num, nom, classe, usage, surface`), généré par DuckDB spatial. Données de test créées sur l'instance : item carte `eb801bce45c9469ab035505e9f3ae3a0` « Parcelles audit 50k », collection `ingest_41adedde12db`, groupe « Equipe SIG audit » (membre `bob`), carte publiée. Rien de destructif.
- Deux adaptations d'environnement, elles-mêmes des constats (F1, F2) :
  1. Le shell tournait en `VITE_AUTH_MODE=mock` alors que `CORE_AUTH_MODE=oidc` : relancé avec `VITE_AUTH_MODE=oidc docker compose up -d shell` puis remis au défaut en fin de session.
  2. Shell (`:8300`) et cœur (`:8200`) sont deux origines sans CORS côté cœur : j'ai ajouté les en-têtes CORS dans le contexte Playwright (`route`), pas dans la stack.
- Images obsolètes (F3) : `geostudio-core` et `geostudio-shell` datent du 2026-10-11 (`docker images`), donc antérieures au correctif REV-349/350/351 (commit `b064254b`, 10-16) et à l'atlas ARC-30 (commit `da974035`, 10-13). Les constats ci-dessous portent sur ce qui tourne ; je distingue ce qui est confirmé dans le code HEAD.
- LCP mesuré : 0,79 à 1,05 s (catalogue, éditeur de carte, page partage) ; chargement réseau idle : 4,4 à 6,2 s. Axe-core (wcag2a/aa/21aa) : 0 violation sur les 3 pages (catalogue, éditeur, partage). Console : aucune erreur applicative (seulement des avertissements GL « GPU stall », headless).

## 1. Chronologie et notes

| Étape | Durée mesurée | Note /10 | Résumé |
|---|---|---|---|
| 0. Connexion OIDC | 2,1 à 3,8 s | 8 | Redirection Keycloak puis retour OK. |
| 1. Import GPKG 50k | ~13 s (hors blocage F4) | 4 | Bloquant tel quel sur gpkg (F4), erreur SQL brute (F5). |
| 2. Styliser | champ + recalcul 0,9 s ; enregistrement 1,5 s | 6 | Fonctionne, persiste au rechargement ; zones d'ombre sur les agrégats (F8). |
| 3. Popups | popup 214 ms après clic | 8 | Titre `nom`, champs choisis, persisté. |
| 4. Publier | 3,9 s | 5 | Dialogue d'avertissement utile, mais carte invisible pour un anonyme (F6). |
| 5. Partager à un groupe | création groupe 1,5 s, enregistrement 1,5 s | 5 | Mécanique correcte, panneau débordant (F7), liste de membres non rafraîchie (F9). |
| 6. Imprimer (export PDF carte) | échec en 5 s | 2 | Inutilisable sur la stack locale par défaut (F10). |
| 7. Atlas | non rejouable | 1 | Image obsolète, aucune UI d'édition d'atlas (F11). |

Note globale du parcours : 4,4 / 10 (moyenne des étapes pondérées par l'importance du scénario ; l'import et la publication sont les deux étapes critiques).

## 2. Blocages (classés)

1. **F4 : l'import d'un `.gpkg` échoue au stockage S3 pour tout navigateur qui ne connaît pas le type MIME** (cas par défaut Chromium/Linux, `file.type === ""`).
2. **F6 : une carte publiée n'est visible par personne hors authentification** dans le shell.
3. **F10 : l'export PDF/PNG est impossible sur la configuration locale par défaut** ; **F11** : l'atlas n'est pas testable ni éditable.
4. **F3 : la stack locale de développement sert des images périmées** : l'import avec une colonne `id` (cas banal) y échoue.

## 3. Constats détaillés

### F4. Bloquant : PUT S3 présigné rejeté (403 SignatureDoesNotMatch) quand `file.type` est vide
- `shell/src/shell/ImportFileButton.tsx:375` présigne avec `file.type || "application/octet-stream"` ; `shell/src/api/domains/exportsIngestion.ts:89` envoie `fetch(url, {method:"PUT", body:file})` sans en-tête `Content-Type`. Pour un `File` sans type, le navigateur n'en envoie aucun, alors que `core/app/ingestion/storage.py:118-120` signe `ContentType` dans l'URL (`content-type=application%2Foctet-stream`).
- Preuve : `file.type=""` pour le `.gpkg` (Playwright, Chromium 151) ; le `PUT` capturé n'a pas d'en-tête `content-type` ; rejeu du même PUT avec `fetch(url,{method:'PUT',body})` -> **403 SignatureDoesNotMatch**, avec `content-type: application/octet-stream` -> **200**. Capture : `02c-import-progress.png` (message « Échec de l'envoi du fichier. »).
- Impact : un analyste qui dépose un GeoPackage (type MIME inconnu sur la majorité des postes Linux/macOS) ne peut pas importer. Les `.csv`, `.zip`, `.geojson` selon l'OS ont un type et passent. Correctif trivial : envoyer `headers: {"Content-Type": file.type || "application/octet-stream"}`.
- Contournement utilisé pour la suite : fichier fourni avec `mimeType: application/geopackage+sqlite3` (type signé = type envoyé).

### F5. Erreur d'import = SQL brut affiché à l'utilisateur
- `core/app/ingestion/tasks.py:227,241` : `error_message=f"erreur interne : {exc}"`, affiché tel quel par `ImportFileButton.tsx` (`setError(job.errorMessage ...)`, branche `status === "error"`).
- Preuve : import d'un gpkg avec colonne `id` -> tiroir « erreur interne : (psycopg.errors.DuplicateColumn) column "id" specified more than once [SQL: CREATE TABLE public.ingest_cdc346021882 (id serial PRIMARY KEY, tenant_id text NOT NULL, id bigint, ...] ». Fuite du schéma interne, illisible pour un analyste.

### F3. Stack locale servie par des images en retard sur `HEAD`
- `docker images geostudio-core/geostudio-shell` : 2026-10-11 11:59. `git log -S"_rename_reserved_property_keys(props, fmt)"` : le correctif de la colonne `id` (REV-350) est du 2026-10-16 (`b064254b`). Dans le conteneur worker, `grep` de la ligne dans `/app/app/ingestion/importer.py` ne renvoie rien, alors que `core/app/ingestion/importer.py:271` la contient : l'import d'un gpkg avec `id` échoue sur la stack (F5 en est la trace) et passerait au HEAD.
- Même cause pour l'atlas (F11) : `docker exec core grep atlas /app/app/export/*.py` vide, alors que le dépôt a `core/app/export/routes.py`/`jobs.py` ; le shell servi n'a pas `atlas-par-entite` (le dialogue « Nouveau » liste 4 modèles d'application, `templates.data.json` en a 9).
- Piège n°2 de la maison (livré/mergé != câblé), côté déploiement local : rien n'avertit que l'image est périmée ; aucun contrôle de version entre l'UI et le cœur (`v0.1.0 · default` dans le pied de page quel que soit le commit).

### F1/F2. Configuration locale par défaut : OIDC inutilisable sans retouche
- `docker-compose.yml:994` : `VITE_AUTH_MODE` vaut `mock` par défaut alors que `.env` met `CORE_AUTH_MODE=oidc` ; `docker-compose.yml:986` : `VITE_CORE_URL` vaut `http://localhost:8200`, origine distincte du shell `:8300`. Le cœur ne pose aucun en-tête CORS pour ces routes (seule exception : `core/app/main.py:382-401`, liste étroite de l'export Connecté) : en mode OIDC, **toutes** les requêtes du shell sont bloquées par le navigateur (« blocked by CORS policy », 8 requêtes sur le premier chargement). Traefik n'est pas une issue locale : `Host(localhost)` + `certresolver=letsencrypt` échoue (`Cannot issue for "localhost"`), `middleware "csp-dynamic@file" does not exist` dans ses logs, `https://localhost/` -> 404.
- Déjà signalé en partie par `00-baseline-stack-reelle.md` §3 ; ici l'effet est plus grave : même avec `VITE_AUTH_MODE=oidc`, l'application est inutilisable depuis un navigateur sans proxy.

### F6. Carte publiée : aucun visiteur anonyme ne peut la voir
- Publication : `PATCH /v1/items/{id}` 200 + `PUT /v1/collections/ingest_41adedde12db/sharing` -> `public:true` (bouton « Publier aussi les collections » ; `08c-published.png`). L'API publique répond : `GET /v1/public/items/{id}` 200, `GET /v1/public/configs/by-item/{id}` 200 (kind `map`, `layout: null`).
- Mais la page publique `shell/src/pages/PublicItemPage.tsx:18` appelle `client.getItem(pk)` = `GET /v1/items/{pk}` (`shell/src/api/domains/items.ts:102`) qui exige un jeton : 401 `missing bearer token` (curl et trace réseau). Résultat : « Page introuvable » (`08d-anon-public.png`). Même si l'appel passait, `shell/src/api/domains/apps.ts:85` lève `config has no layout` pour une config de kind `map` (`layout` nul) ; et `/maps/:pk` est sous `ProtectedLayout` (`shell/src/shell/routes.tsx:269-271`) : un anonyme est renvoyé vers Keycloak (`08d-anon.png`).
- Conclusion : « Publier » une carte n'ouvre rien aux anonymes côté interface ; seul le sitemap/aperçu social serveur est alimenté. Le texte de l'UI promet l'inverse : « Menu ⋯ -> Publier pour l'ouvrir aux anonymes ».
- Atténuation : le dialogue de publication (`PublishDialog.tsx`) avertit correctement que les collections lues sont privées (bon point, `08b-publish-dialog.png`).

### F7. Panneau de partage : contrôles qui débordent de la colonne
- Mesure Playwright (1440 px) : le `<select>` du rôle (Lecteur/Éditeur/Gestionnaire) a `right=1553` > `innerWidth=1440` ; le bouton « Supprimer » (groupe) `right=1513`. Captures `06b-group-created.png`, `06f-share-overflow.png` : le bouton rouge est coupé au bord. La case du groupe replie le nom sur 3 lignes (« Equipe / SIG / audit »). Le placeholder « Rechercher un groupe (2 caractères minimum) » est tronqué ; le bouton « Créer le groupe » est écrasé sur 3 lignes. Cause : `shell/src/shell/ShareForm.tsx` (lignes 519-540, rangée groupe+rôle sans `min-w-0`/`flex-wrap`).
- Les contrôles restent atteignables au clavier, d'où les 0 violation axe-core : le défaut est visuel, non détecté par l'audit automatique.

### F8. Rendu 50k : tuiles agrégées + symbologie
- À l'ouverture (zoom France) : 17 requêtes dont les tuiles `/v1/collections/ingest_41adedde12db/tiles/z/x/y.mvt` en <= 308 ms, 292 Ko au total (bon). La couche affiche un badge « Tuiles agrégées : zoomez pour le détail » et une grille de gros disques teal uniformes (`04b-style-computed.png`) : la symbologie par `usage` n'y apparaît pas (couleur fixe `aggregateDefaultColor()`, `shell/src/map/mapLayerBuild.ts:30`), alors qu'une tuile en haut à gauche, sous le seuil de 5000 entités (`core/app/features/tiles.py:49`), est dessinée en points colorés. Mélange de deux rendus sur une même vue. Conforme au code mais déroutant pour l'analyste ; la légende (agricole/eau/forêt...) annonce des couleurs absentes de la vue.
- À fort zoom : points individuels colorés par catégorie, popup à 214 ms (`05c-zoomed.png`, `05d-popup.png`).
- Le fond de carte « Clair » charge `https://demotiles.maplibre.org/style.json` et ses tuiles (requêtes externes), à noter pour un déploiement air-gap.

### F9. Liste des membres non rafraîchie après ajout
- `shell/src/api/domains/items.hooks.ts:174-180` : `useAddGroupMember` n'a pas d'`onSuccess` qui invalide `["groupMembers", groupId]`, contrairement à `useRemoveGroupMember` (l. 191-199). Observé : après « Ajouter un membre (bob -> Equipe SIG audit) », `POST /v1/groups/{id}/members` répond 204 mais l'écran garde « Aucun membre. » (1 s et 2,5 s après) alors que `GET /v1/groups/{id}/members` renvoie bien `bob`. L'utilisateur croit que l'ajout a échoué et peut le refaire.

### F12. Défauts mineurs observés
- Les collections sont désignées par leur identifiant technique, jamais par leur titre, dans le partage et la publication : « Les données « ingest_41adedde12db » ne sont pas partagées... » (`ShareForm.tsx:557-561`, `PublishDialog.tsx:33-56`), alors que l'analyste a saisi « Parcelles audit 50k » à l'import.
- `Modifié` de l'item ne bouge pas quand on enregistre le style/les popups : `core/app/items/models.py:59` (`onupdate` sur la ligne item) et aucune écriture sur l'item dans `core/app/configs/routes.py`. Observé : « Modifié 16/10/2026 15:43:47 » (`06a-share-panel.png`) alors que la config a été enregistrée à ~15:46 UTC (version 4 côté API). Conséquence : le tri « Date de modification » du catalogue ne reflète pas le travail cartographique.
- L'import n'affiche qu'un texte « Import en cours… » sans progression pour 50k (13 s : 4,3 s d'attente de file `deferred 15:43:33,4` -> `started 15:43:37,7` selon `procrastinate_events`, 5,9 s d'ingestion, ~2 s de navigation). Acceptable ici ; la mesure initiale de 42 s dans mon script était un artefact de mon propre `innerText` sur un dialogue fermé (timeout de 30 s).
- Un utilisateur en lecture seule (bob, rôle sans `write` sur la carte) ouvre l'éditeur complet avec tous les champs actifs ; seul « Enregistrer » est désactivé et l'explication `locked.needWrite` est tout en bas de la colonne droite (`MapEditorPage.tsx:330,345`, `07a-bob-view.png`). Pas de bandeau « lecture seule » en haut.
- Le catalogue des couches de l'éditeur liste en vrac toutes les collections du tenant (dizaines de `aud-j*`) sans pagination visible ; recherche présente (« Rechercher une source de couche »).

### F10. Export PDF/PNG de la carte : échec immédiat sur la stack locale
- `ExportPanel` affiche PNG/PDF (`10a-export-picker.png`). `POST /v1/export` -> 202, puis `status: "error"` après 5 s : « le cœur (http://localhost:8200), que la page d'export appelle (VITE_CORE_URL du shell), n'est pas joignable depuis export-worker... » (`core/app/export/jobs.py:132-155`). C'est le comportement documenté de `.env` (lignes 118-148) : aucune valeur de `VITE_CORE_URL` par défaut ne marche à la fois pour le navigateur de l'hôte et pour export-worker. Le message est clair (bon point), mais l'impression, étape finale du scénario, est inatteignable sur un poste de développement sans domaine public.
- Une conséquence : l'export Playwright de bout en bout (auth du rendu OIDC, `data-export-ready`) n'a pas pu être évalué ici.

### F11. Atlas
- Non rejoué : le cœur et le shell déployés n'ont pas le code (F3). Lecture du code HEAD : l'atlas est une `printLayout.atlas` d'**application** (`shell/src/pages/AppRuntimePage.tsx:75-78,232-234`, `shell/src/builder/print/AtlasPages.tsx`), pas de carte ; il faut donc d'abord créer une application. Seul le gabarit « atlas-par-entite » (`shell/src/builder/templates.data.json:890-960`) le pose, avec une source codée en dur `layer: "communes"`. Aucun formulaire d'édition de l'atlas : `grep -i atlas` dans `shell/src` ne trouve que `AtlasPages`, `EntityFiche`, `ExportPanel`, `AppRuntimePage`, les gabarits et 2 clés i18n ; `PrintLayoutPanel.tsx` n'en parle pas. L'analyste doit rebrancher la source sur sa collection et éditer le JSON à la main, ou passer par MCP/copilote (le copilote est désactivé ici : `copilotEnabled:false`).
- Atlas final = export PDF, donc soumis à F10 aussi.

## 4. Ce qui fonctionne bien

- Persistance : style (champ couleur `usage`, classes calculées 5 valeurs) et popup (titre, champs) survivent au rechargement (`champ couleur = usage`, `popup coché = true`).
- Popup : titre, libellés, valeurs formatées (`surface 53,54`), 214 ms.
- Tuiles du 50k : réponses < 310 ms, 292 Ko ; carte entièrement chargée en 3,6 s ; LCP ~1 s.
- Partage : propagation du partage de la carte et de la collection au groupe (`GET .../sharing` -> `groups:[{role:"viewer"}]` pour les deux), avertissement « données non partagées » utile et bouton d'action directe ; vue de `bob` OK (6,2 s, tuiles lues sous RLS).
- Accessibilité : 0 violation axe sur 3 pages, ordre de tabulation cohérent (lien d'évitement, recherche, actions, navigation).
- Messages d'erreur d'export explicites (F10).

## 5. Recommandations (ordre de priorité)

1. F4 : envoyer le `Content-Type` signé dans le PUT S3 (une ligne) + test E2E avec un `File` sans type.
2. F6 : un vrai visualiseur public de carte (`getPublicItem` côté `PublicItemPage`, kind `map`) ou retirer la promesse du texte de publication.
3. F3/F1/F2 : ajouter à `docker compose up`/runbook un contrôle de fraîcheur d'image et la combinaison `VITE_AUTH_MODE=oidc` + `VITE_CORE_URL` joignable ; ou un CORS dev explicite.
4. F10/F11 : documenter une valeur locale fonctionnelle pour l'export (ex. `host.docker.internal`) ; ajouter un éditeur d'atlas dans `PrintLayoutPanel` et un chemin carte -> atlas.
5. F5 : message d'erreur d'import sans SQL (journaliser, afficher un libellé).
6. F7 : `min-w-0`/`flex-wrap` sur la rangée de groupe ; F9 : `onSuccess: invalidateQueries(["groupMembers", groupId])` ; F12 : titres de collection au lieu des identifiants, bump de `updated_at` à l'enregistrement d'une config.

## 6. Limites de l'audit

- Atlas et export PDF/PNG jamais produits (F3, F10) : notes 1 et 2 correspondent à l'impossibilité, pas à un jugement sur le code.
- Le correctif REV-350 (colonne `id`) n'est pas rejoué : vérifié par lecture du code seulement.
- Pas de test sur appareil tactile ni lecteur d'écran réel ; axe-core limité à 3 pages.
- Chromium headless : le « GPU stall ReadPixels » est un avertissement de l'environnement, non évalué.
- Le shell a été remis à sa configuration initiale (`docker compose up -d shell`, `mock`) ; les données de test (carte, collection `ingest_41adedde12db`, groupe, publication) restent sur l'instance.
