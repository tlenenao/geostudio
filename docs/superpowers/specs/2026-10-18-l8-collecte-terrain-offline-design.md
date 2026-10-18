# Spec — L8 « Collecte terrain » : XLSForm fidèle, collecte publique, offline restreint

Date : 2026-10-18. Statut : **spec, en attente de l'accord explicite de Tanguy** (aucune
exécution lancée). Références : `docs/revue/audit-2026-10-16/99-synthese.md` (ligne L8,
décision **D6** : « SP offline restreint = formulaires + file de sync + photos, pas de cartes
hors-ligne vectorielles complètes »), fiches `dimensions/d07.md` (C1, I1-I7, M1, M2) et
`dimensions/d35.md` (I4). Plan jumeau : `docs/superpowers/plans/2026-10-18-l8-collecte-terrain-offline.md`.
Migrations réservées : **0160 à 0179**.

## 0. État réel du code, revérifié (piège n°12)

Relu le 2026-10-18 sur `dev` (`32575b3a`). Les fiches d'audit datent du 2026-10-16 : deux
constats sont déjà corrigés, ne pas les refaire.

| Constat | État dans le code | Preuve |
|---|---|---|
| AUD-004 / C1 offline | **Confirmé, rien n'existe.** Ni service worker, ni manifest, ni IndexedDB (`grep serviceWorker\|indexedDB` : 0 hors i18n/`ConnectivityBanner`). `shell/public` = `fixtures/`. `ConnectivityBanner.tsx` n'affiche qu'une bannière. Playwright sert le **build** (`npm run build && npm run preview`, port 4173) : un SW est donc testable en E2E. | `shell/playwright.config.ts:37-45`, `vite.config.ts` |
| I1 photo perdue après échec | **Déjà corrigé** : `mutationFn` renvoie `{fid, failed}` et ne fait plus échouer la saisie créée (commentaire explicite `form.tsx:~777`). À re-tester seulement (régression), pas à re-concevoir. | `shell/src/builder/widgets/form.tsx:777-791` |
| I2 PUT S3 / Content-Type | **Déjà corrigé** : `contentType = file.type \|\| "application/octet-stream"` réutilisé, `if (!res.ok) throw`. | `form.tsx:300-311` |
| AUD-070 / I3 libellés de choix | **Confirmé** : `choices[list_name].append(c["name"])`, `label` jamais lu. | `core/app/xlsform/parser.py:~266` |
| AUD-070 / I4 repeat, calculate, default, select_multiple, choice_filter | **Confirmé** : `begin_repeat` et ses questions → `not_ported` ; `calculate` → `not_ported` ; `default`/`choice_filter`/`appearance`/… dans `_UNSUPPORTED_COLS` ; select_multiple en texte libre. Le rapport reste honnête (`ReportItem`). | `parser.py:~293-317` |
| AUD-070 / M2 `required` serveur | **Confirmé** : `required` n'existe que dans `form_fields` (validation client). Une géométrie requise est déclarée « approximated : non imposée ». Rien côté `validate_for_write`. | `parser.py:338-346` |
| AUD-070 / réimport | **Confirmé** : `POST /xlsform/import` crée toujours une collection (`create_empty_collection`). Pas d'export XLSForm. | `xlsform/routes.py:56-72` |
| AUD-071 / I5 géométrie | **Confirmé** : `form.tsx` ne saisit que `Point` (lon/lat, `geometryType === "Point"`) ; `loadedGeometry` nul à la création pour ligne/polygone ; précision GNSS non lue. Le parseur mappe pourtant geotrace→LineString, geoshape→Polygon. | `form.tsx:705, 925-929, 1085-1098` |
| AUD-071 / I6 audio/vidéo | **Confirmé** : `_FILES` = image/photo/audio/video/file → tous `attachment` ; champ rendu `accept="image/*" capture="environment"` ; `_SNIFF` public = JPEG/PNG/GIF/WEBP/PDF. | `form.tsx:420-421`, `public_submit/service.py:42` |
| AUD-071 / I7 page citoyenne | **Confirmé** : `POST /public/submit/{token}` existe (honeypot, quota, modération, un fichier) mais **aucune route shell** (`/collect/:token` absente ; seule `/embed/:token` existe, `routes.tsx:378`). | `public_submit/routes.py:61`, `shell/src/shell/routes.tsx` |
| Idempotence d'écriture | **Absente** : `POST /collections/{id}/items` génère le fid ; un rejeu après timeout crée un doublon. `ETag`/`If-Match` existent sur PUT/DELETE (ARC-04) mais pas de clé d'idempotence (le mot `idempot` n'apparaît que sur d'autres sujets). | `core/app/features/routes.py:904-1060` |
| Pièces jointes | Presign → PUT S3 → confirm, **exige un `fid` existant**, sous `can()` ; pas d'unicité `(tenant_id, s3_key)` (M1 non vérifié, à traiter dans ce lot car le rejeu offline le rend plausible). | `attachments/routes.py:171-295` |
| « Mes saisies » | `GET /collections/{id}/my-entries` dérive du journal `EntityHistory` (`op=create`, `actor_id`), masquage appliqué. Aucune notion d'état de synchro. | `xlsform/routes.py:102-139` |

Tout le reste de la chaîne (RLS, `can()`, masquage de champ sensible GAP-22, quotas items,
géo-limites, relations ARC-21, règles CEL ARC-14, domaines ARC-13) est **réutilisé tel quel**.

## 1. Périmètre

### Dans le lot (D6 restreint)
1. **AUD-070 — XLSForm fidèle** : libellés de choix (+ `label::fr`), `required` appliqué côté
   serveur (attribute_rule `constraint`), `default`, `calculate` (règle `calculation`
   `derived`), `select_multiple` (colonne `text[]`), `choice_filter` simple (voir §2.4),
   géométrie requise, réimport sur collection existante avec rapport de différences.
   `repeat` : **hors lot** (reste `not_ported`, voir Q4).
2. **AUD-071 — Collecte** : saisie ligne/polygone/trace GPS (outil de croquis SP-27/SP-51
   réutilisé), précision GNSS en colonnes optionnelles, champs audio/vidéo/fichier typés,
   plusieurs fichiers par soumission publique, page citoyenne `/collect/:token`.
3. **AUD-004 — Offline restreint** : PWA installable, service worker de coquille applicative,
   cache du « kit de collecte » (schéma + domaines + config d'App) en IndexedDB, file locale
   de saisies **création seule** (feature + photos), rejeu idempotent, écran d'état de synchro
   dans « Mes saisies », mode hors-ligne aussi pour la page publique.

### Hors lot (explicite)
- Fonds de carte / tuiles vectorielles hors-ligne (D6). La carte hors-ligne affiche un fond
  neutre ; les saisies point se font par GPS/coordonnées, ligne/polygone par croquis sur fond neutre.
- Lecture hors-ligne de données existantes, édition **hors-ligne d'enregistrements déjà
  serveur** (donc pas de `If-Match` rejoué ; voir Q1), suppression hors-ligne.
- `repeat` XLSForm → collection fille (Q4), export XLSForm, annotation d'image, compression avancée.
- Chiffrement au repos de l'IndexedDB (Q3).
- Background Sync API comme **seul** mécanisme (Chromium uniquement) : c'est un bonus (§4.4).

## 2. Modèle de données et contrats

### 2.1 Idempotence : table `collect_client_ops` (migration **0160**)
Colonnes : `id`, `tenant_id` (FK), `collection_id` (FK `ON DELETE CASCADE`), `actor_id`,
`client_op_id` (UUID v4 généré par le client), `kind` (`feature`|`attachment`), `result`
(JSON : `{fid}` ou `{attachment_id}`), `created_at`. Contrainte unique
`(tenant_id, collection_id, actor_id, kind, client_op_id)`. RLS/`tenant_id` comme toute table
du cœur ; purge par `purge_tenant` (27 → 28 tables : mettre à jour la liste et son test) ;
balayage de rétention 30 jours (cron existant des balayages).

Contrat : `POST /v1/collections/{id}/items` accepte l'en-tête `Idempotency-Key: <client_op_id>`.
- Clé inconnue : écriture normale + insertion de la ligne **dans la même transaction**
  (donc rollback commun) → `201 {id}`.
- Clé connue (même acteur, même collection) : **aucune écriture**, `200 {id}` + en-tête
  `Idempotent-Replay: true` (le client traite 200/201 comme succès).
- Course (2 requêtes simultanées) : la contrainte unique tranche, la perdante relit et rend 200.
- Même clé, charge différente : on **ne compare pas** (le premier gagne) ; documenté.
Sans en-tête : comportement inchangé (rétro-compatible, OpenAPI additive).
Même mécanisme sur `POST …/items/{fid}/attachments/confirm` (kind `attachment`) : le rejeu d'un
confirm ne crée pas une 2e ligne. En plus : index unique `(tenant_id, s3_key)` sur
`attachments` et contrôle d'existence du `fid` sous `rls_scope` (M1) — **migration 0161**
(précédée d'un dédoublonnage ; test sur base non vide, piège n°8).

### 2.2 Soumission publique : `submissions.client_op_id` (migration **0162**)
Colonne nullable + index unique partiel `(token_id, client_op_id) WHERE client_op_id IS NOT NULL`.
`POST /public/submit/{token}` accepte `clientOpId` (champ de formulaire) ; rejeu → `202`
identique sans nouveau slot de quota. Plusieurs fichiers : table `submission_files`
(`id`, `tenant_id`, `submission_id` FK cascade, `field_key`, `attachment` JSON, `attachment_key`)
dans la même migration **0162** ; l'ancienne colonne `attachment` est conservée et lue
(compatibilité des soumissions en attente), l'approbation lit les deux. Plafonds : 5 fichiers,
10 Mo chacun, 25 Mo total (constantes dans `public_submit/service.py`).

### 2.3 Kit de collecte (lecture, pas de table)
`GET /v1/collections/{id}/collect-kit` (nouvelle route, en lecture seule) renvoie en un appel :
colonnes + types (sans champs masqués/sensibles de l'appelant, GAP-22 : même
`hide_sensitive_columns` que les routes de lecture), domaines avec libellés, règles CEL
(`constraint`/`calculation`), `attachment_fields` typés, `geometryType`, `required`,
`updatedAt` du schéma et un `etag` de kit. `ETag` fort + `If-None-Match` pour la revalidation.
Côté public : `GET /public/submit/{token}/kit` (mêmes garanties que le POST : 404/410, limite
par IP, **aucun champ sensible**, aucune donnée de la collection). Le kit d'App est la config
d'App déjà servie par `/v1/configs` ; le client la met en cache avec le kit.

### 2.4 XLSForm (migration : aucune, sauf Q2)
- `FieldDomain` gagne `labels: dict[str, str] | None` (clé = valeur, extra="forbid" conservé ;
  schéma OpenAPI + types TS régénérés, piège n°1). `label::fr` prioritaire sur `label`, sinon
  premier `label::*`. Propagé à `applyDomains`, popup, tables, `form.tsx`.
- `required` → `AttributeRule(kind="constraint", expression="<col> != null", message=…)`
  générée à l'import ; la validation d'écriture existante (`validate_for_write` +
  `with_attribute_rules`) l'applique donc à **tous** les chemins (REST, MCP, public, sync).
  Géométrie requise : règle serveur `geometry != null` si le moteur CEL l'expose, sinon
  contrôle dédié dans `validate_for_write` (à trancher en T4 après lecture de `cell_safety`/CEL ; défaut : contrôle dédié).
- `default` → `AttributeRule(kind="calculation", mode="default")`.
  `calculate` → `kind="calculation", mode="derived"` quand `to_cel` sait traduire ; sinon
  `not_ported` comme aujourd'hui. `to_cel` étendu : `today()`, `string-length`, `coalesce`,
  `if(c,a,b)`, `regex` — uniquement si la sémantique CEL est identique (tests de parité).
- `select_multiple` → colonne `text[]` (le type `list/array` de FieldType existe depuis
  REV-193) + widget multi-choix.
- `choice_filter` simple (`list_col=${autre}`) → domaine conditionnel côté client uniquement
  (filtrage de la liste dans le formulaire) **et** contrainte serveur CEL
  (`valeur in <table de correspondance>`) ; les formes complexes → `not_ported`.
  Si la contrainte serveur n'est pas faisable proprement, rester sur `not_ported` (Q2).
- Réimport : `POST /xlsform/import?collectionId=…` : compare colonnes/domaines/règles, applique
  uniquement les **ajouts** et mises à jour de libellés/règles, **jamais** de suppression/retypage
  (rapport `differences` : `added`/`changed`/`blocked`). Pas d'export XLSForm (hors lot).

## 3. Saisie : géométrie, médias, page publique (shell)
- `form.tsx` : pour LineString/Polygon (+Multi), ouvre l'outil de croquis existant ; trace GPS
  via `watchPosition` (échantillon ≥ 5 m, précision ≤ 50 m configurable) ; point au tap carte ;
  colonnes **optionnelles** `gps_accuracy`, `gps_altitude`, `gps_time` (déclarées par l'import
  XLSForm seulement, jamais imposées) ; géométrie requise bloquante côté client **et** serveur.
- Champs médias : `attachment_fields` porte `{key,label,kind: image|audio|video|file}` ;
  `accept`/`capture` en dérivent (`image/*`+`environment`, `audio/*`+`capture`, `video/*`).
  Magic numbers audio/vidéo ajoutés à la liste blanche **serveur** (ogg, mp3, m4a/mp4, webm,
  wav) en un seul endroit partagé par `attachments` et `public_submit` (jumelles, piège n°14).
- Page `/collect/:token` : route publique hors `ProtectedLayout` (patron `EmbedPage`/`EmbedRoute`),
  charge le kit public, rend `form.tsx` en mode `public`. Anti-abus : honeypot + limite par IP
  existants + **preuve de travail** SHA-256 côté client (hashcash, 18 bits, défi signé HMAC par
  le cœur, 60 s) — aucune dépendance tierce (Q5). QR code de partage depuis la fiche du jeton.
  Titre de route i18n (`docTitle.collect`), `<main>`/`<h1>`, a11y AA.

## 4. Offline restreint

### 4.1 PWA et service worker
- `shell/public/manifest.webmanifest` (nom, icônes 192/512 maskable, `display: standalone`,
  `start_url: /`, `scope: /`), `<link rel=manifest>` + `theme-color` dans `index.html`.
- `shell/public/sw.js` **écrit à la main** (≈ 100 lignes, pas de Workbox : une dépendance et un
  build à épingler pour une seule stratégie). Stratégies :
  - navigation : réseau d'abord, repli sur `index.html` précaché (`/`, `/collect/*`, `/apps/*`) ;
  - `/assets/*` (noms hachés Vite) : cache-first, `CACHE = gs-shell-<hash du build>`, purge des
    anciens caches à l'`activate` ;
  - **jamais** de cache de `core` (`/v1/*`), ni de `/mcp`, ni de `/embed`, ni de réponses avec
    `Authorization` : le SW ne voit que la coquille. Les données hors-ligne vivent dans
    IndexedDB, sous contrôle applicatif.
  - le `CACHE` est versionné par un define Vite (`__BUILD_ID__`) injecté dans `sw.js` par un
    petit plugin Vite (génération de `dist/sw.js`) ; test : le hash change avec le build.
- Enregistrement : `shell/src/offline/registerSw.ts`, **production uniquement**
  (`import.meta.env.PROD`), échec silencieux ; mise à jour : bannière « Nouvelle version
  disponible » (`skipWaiting` sur clic, jamais en cours de saisie).
- CSP : `worker-src 'self'` et `manifest-src 'self'` à ajouter à la CSP calculée
  (SP-48, `CORE_CSP_MODE`) — **vérifier l'enforcing sur Traefik/nginx**, piège n°2 (jumelle nginx
  `.mjs`/cache : `sw.js` en `Cache-Control: no-cache`, sinon une SW périmée se fige).

### 4.2 Stockage local (IndexedDB, `shell/src/offline/db.ts`)
Wrapper natif minimal (≈ 80 lignes, pas de dépendance ; `fake-indexeddb` en devDependency
de test seulement — Q7). Base `gs-collect-v1`, version de schéma migrée par `onupgradeneeded`.
Stores :
- `kits` : clé `${tenantId}:${userSub}:${collectionId}` (ou `public:${tokenPrefix}`) →
  `{kit, appConfig, fetchedAt, etag}`. Revalidation `If-None-Match` à l'ouverture si en ligne ;
  **péremption dure 14 jours** (au-delà : « kit trop ancien, reconnectez-vous » sans bloquer
  les saisies déjà en file).
- `outbox` : `{opId (UUID v4), ownerKey (tenant:sub | public:token), collectionId, kind:
  "feature", payload {properties, geometry}, createdAt, updatedAt, state, attempts, lastError,
  nextTryAt, serverFid?}` ; `state` ∈ `queued` | `sending` | `needs_photos` | `sent` |
  `conflict` | `failed_permanent`.
- `blobs` : `{blobId, opId, fieldKey, kind, name, type, size, blob, clientOpId, uploaded}`
  (les `Blob` sont stockés tels quels, jamais en base64).
- `meta` : horloge de dernière synchro, estimation de quota.
Isolation : **toute lecture/écriture est filtrée par `ownerKey`** ; un autre utilisateur sur
le même appareil ne voit ni n'envoie la file d'autrui. Au logout explicite : la file est
**conservée** (perdre des saisies de terrain est pire), mais les kits sont purgés ; bannière
« N saisies en attente de synchronisation, connectez-vous pour les envoyer ».
Garde-fous : `navigator.storage.persist()` demandé à la première mise en file ;
plafond 200 Mo de blobs et 100 saisies par `ownerKey` (refus explicite à la mise en file,
message traduit) ; `QuotaExceededError` capturée → saisie non perdue (l'utilisateur garde le
formulaire ouvert).

### 4.3 Protocole de synchronisation (`shell/src/offline/sync.ts`)
Moteur unique, séquentiel par `ownerKey` (pas de parallélisme : l'ordre des saisies est
conservé et le limiteur serveur est ménagé) :
1. Déclencheurs : événement `online`, retour au premier plan (`visibilitychange`), ouverture
   de « Mes saisies », bouton « Synchroniser maintenant », Background Sync `gs-sync` si
   disponible (le SW réveille la page/`clients.matchAll` ; **pas de logique d'envoi dans le SW**
   : le jeton OIDC vit dans la page).
2. Pour chaque entrée `queued`/`failed` dont `nextTryAt` est échu :
   `POST /items` avec `Idempotency-Key = opId` (public : `POST /public/submit/{token}` avec
   `clientOpId`). Succès (200/201) → `serverFid` mémorisé, `state=needs_photos` s'il reste
   des blobs, sinon `sent`.
3. Photos : pour chaque blob non envoyé : presign → PUT S3 (`res.ok` vérifié, mêmes
   `contentType`) → confirm avec `Idempotency-Key = blob.clientOpId`. Reprise exacte après
   coupure : l'état `uploaded` est persisté **après** chaque confirm ; un rejeu d'un confirm
   déjà passé est inoffensif (2.1).
4. Classement des erreurs (une table de décision testée) :
   | Réponse | Action |
   |---|---|
   | réseau / 5xx / 429 / 408 | `queued`, backoff exponentiel 5 s→15 min (`Retry-After` respecté), `attempts++` |
   | 401 | pause globale, signal « reconnexion requise », file intacte ; reprise après renouvellement du jeton |
   | 403 / 404 / 410 (droit retiré, collection ou lien supprimé/expiré) | `conflict` (raison affichée), jamais rejoué automatiquement |
   | 413 / 415 / 422 | `conflict` avec les erreurs de champ du serveur ; **l'utilisateur corrige et renvoie** (la saisie reste éditable en local) |
   | 409 | `conflict` (« contrainte d'unicité ») |
   | 429 sur quota de jeton public épuisé | `failed_permanent` |
5. Jeton OIDC expiré hors-ligne : la file attend ; au retour réseau le renouvellement silencieux
   est tenté (mécanisme OIDC existant), sinon redirection de connexion avec `returnTo`
   (session `returnTo` existante, P07) vers « Mes saisies ». Mode mock E2E : jeton fictif.
6. Les entrées `sent` sont gardées 7 jours (historique « envoyée ») puis purgées.

### 4.4 Résolution de conflits
Choix restreint et assumé : **création seule hors-ligne**. Les conflits possibles sont donc
bornés à des *rejets de validité*, pas à des fusions concurrentes :
- doublon (rejeu) → impossible par construction (idempotence) ;
- schéma ayant évolué depuis la mise en cache (colonne supprimée/typée autrement, nouvelle règle) →
  422 → `conflict` avec message de champ ; l'utilisateur modifie la saisie locale (le formulaire
  se rouvre sur la charge locale, contre le kit **rafraîchi**) et renvoie ;
- droit/collection retirés → `conflict` non rejouable, l'utilisateur peut **exporter la saisie en JSON**
  (bouton « Copier / télécharger ») ou l'abandonner (avec confirmation, `ConfirmDialog`) ;
- géo-limites/quotas items : refus serveur affichés tels quels.
Pas de « dernier gagnant » silencieux nulle part. L'édition d'enregistrements serveur avec
`If-Match` hors-ligne est reportée (Q1) — l'infrastructure (`opId`, états, écran) la
supportera sans changement de modèle.

### 4.5 Écran « Mes saisies » et indicateurs
`MyEntriesPanel` fusionne `my-entries` (serveur, quand en ligne) et `outbox` : badge par ligne
(En attente / Envoi… / Photos à envoyer / Envoyée / En conflit / Échec définitif), compteur dans la
barre du haut (`SyncStatusPill`, `aria-live=polite`), actions : synchroniser, modifier (si
`queued|conflict`), abandonner, détails de l'erreur. `ConnectivityBanner` existante est
étendue (n'affiche plus « hors ligne » comme une erreur sur les routes de collecte : message
« Mode hors-ligne : vos saisies seront envoyées au retour du réseau »). i18n : tout en
français via catalogue par domaine (détecteur de couverture CI).

## 5. Sécurité
- **`can()` / RLS** : aucun nouveau chemin d'écriture. La synchro passe par les routes
  existantes (`_get_writable`, `rls_scope`, géo-limites, quotas, `validate_for_write`).
  `collect-kit` exige le droit de **lecture** de la collection ; la création reste vérifiée à
  l'écriture (le client ne se fie jamais au kit pour l'autorisation).
- **GAP-22** : le kit ne contient aucun champ masqué pour l'appelant ; l'écriture d'un champ sensible
  reste refusée par le serveur même si une file locale en contient un (cas schéma changé).
- **Jetons publics** : le kit public ne révèle ni le nom de table ni les champs sensibles, ne
  décompte aucun slot ; le POST décompte un slot par `clientOpId` distinct (rejeu gratuit mais borné
  par la limite IP). PoW signée HMAC (secret `CORE_*` existant dérivé, pas de nouveau secret en clair).
- **Appareil** : IndexedDB non chiffrée (Q3), documenté dans `SECURITY.md` (appareil partagé :
  recommandation de déconnexion + purge). Aucun jeton OIDC ni secret n'est écrit en IndexedDB.
- **XSS/charge** : les charges locales sont validées par le même schéma que le serveur avant envoi ;
  un nom de fichier est assaini (`_sanitize_filename` miroir côté client).
- **SW** : périmètre `/`, ne cache jamais d'API ; `sw.js` servi sans cache ; origine unique.
- **Rate limiting** : groupe de route dédié `collect_sync` (budget plus généreux que l'écriture
  générale) car une file de 100 saisies se vide en rafale ; backoff client sur 429.
- **Audit** : `feature.create` conserve l'acteur réel ; nouvel attribut `payload.clientOpId` et
  `payload.offline: true` quand l'en-tête `X-GS-Offline-Created-At` (horodatage client, informatif,
  jamais fiable) est présent.

## 6. Quotas
Serveur : quotas items/stockage au point unique de création (déjà en place) s'appliquent à la sync ;
`collect_client_ops` n'est pas décomptée. Client : 200 Mo / 100 saisies / 5 photos par saisie /
10 Mo par photo après compression (redimensionnement canvas à 2048 px côté long, JPEG 0,85 si
`image/*` > 2 Mo ; mesuré en T11). Publique : plafonds §2.2.

## 7. Plan de test (résumé ; détail par tâche dans le plan)
- **Cœur (pytest, base PostGIS réelle)** : idempotence (rejeu, course à 2 threads — mesurer
  par contrainte unique, piège n°7), confirm idempotent, unicité `s3_key`, soumission publique
  `clientOpId` + multi-fichiers + magic numbers, `collect-kit` (masquage GAP-22, ETag 304,
  droit de lecture), PoW (défi expiré/rejoué), XLSForm (libellés, required, default,
  calculate, select_multiple, réimport), migrations **sur base non vide dans les deux sens**
  (piège n°8), `purge_tenant`, OpenAPI/TS régénérés (piège n°1), inventaire des surfaces
  (`inventaire-fonctionnalites.jsonl` : **à faire à la clôture, hors ce commit de spec**).
- **Shell (Vitest, `fake-indexeddb` local au fichier — piège n°10)** : `db.ts`, `sync.ts`
  (table de décision complète, backoff, reprise après coupure au milieu des photos, isolation
  par `ownerKey`, 401 en pause), `form.tsx` (géométries, médias, mise en file hors-ligne),
  `MyEntriesPanel`, `registerSw`. Falsification obligatoire des filets (injecter le défaut,
  voir échouer, retirer).
- **E2E Playwright (`shell/e2e/collect-offline.spec.ts`, sur le build servi par `preview`)** :
  `context.setOffline(true)` ; scénarios : (1) installer/charger, couper, saisir point + photo,
  recharger **hors ligne** (coquille servie par le SW, saisie conservée), rétablir, vérifier l'envoi
  et l'état « Envoyée » ; (2) coupure au milieu de l'envoi des photos puis reprise sans
  doublon ; (3) 422 simulé → « En conflit » → correction → envoi ; (4) page `/collect/:token`
  hors-ligne puis sync ; (5) 401 → file intacte puis reprise ; (6) deux utilisateurs mock,
  isolation. Mocks `mocks.ts` à étendre (`Idempotency-Key`, kit). Chromium, projet
  `mobile-touch` pour la saisie tactile. Suite complète E2E verte avant clôture (piège n°6).
- **Rejeu sur stack réelle** (`scripts/replay`) : un vrai téléphone/émulation réseau CDP
  (`Network.emulateNetworkConditions offline`) avec Keycloak réel — le service worker et le jeton OIDC
  se comportent différemment du mode mock ; non exécutable en CI, **prévu comme étape de clôture**.
- Garde-fous : `check-bundle-size` (SW hors bundle d'entrée), couverture ≥ seuils, `i18n`, ESLint (règle
  `fetch`: la sync passe par `authFetch`/`ItemClient`, jamais `fetch` nu vers le cœur).

## 8. Migrations (réservées 0160-0179)
| N° | Contenu | Test base non vide |
|---|---|---|
| 0160 | `collect_client_ops` (+ index unique, RLS/tenant) | oui, up/down |
| 0161 | `attachments` : dédoublonnage + index unique `(tenant_id, s3_key)` | oui (doublons existants) |
| 0162 | `submissions.client_op_id` + index partiel ; table `submission_files` | oui, soumissions en attente |
| 0163-0179 | libres (réserve : Q2 `choice_filter`, colonnes GNSS si stockage dédié) | — |
`down_revision` = tête Alembic **à l'instant de l'exécution** (d'autres lots migrent en parallèle :
`alembic heads` avant de numéroter, un seul head attendu). Le conteneur `postgis-test` n'est pas
suivi par Alembic : `ALTER TABLE` manuel après migration (piège SP-42).

## 9. Risques
1. **Service worker périmé** (figé sur une vieille coquille) : mitigé par `sw.js` en no-cache, cache versionné, bannière de
   mise à jour, test de changement de hash.
2. **Perte de saisie** (pire défaut possible) : file écrite *avant* tout envoi, jamais supprimée en
   erreur, `persist()` demandé, export JSON manuel, éviction navigateur (iOS Safari ~7 jours sans usage hors PWA
   installée) documentée dans l'aide contextuelle.
3. **iOS** : pas de Background Sync ; `visibilitychange`/`online` suffisent ; la PWA installée est recommandée.
4. **Jeton OIDC expiré en zone blanche** : géré par la pause 401 ; durée de vie du refresh token Keycloak à
   documenter (réglage `SSO Session Idle` du realm) — ne pas la modifier dans ce lot (Q6).
5. **Dérive de schéma** entre kit et serveur : 422 → conflit explicite, jamais d'écriture partielle.
6. **Idempotence sans comparaison de charge** : un client buggé réutilisant un `opId` écrase silencieusement
   l'intention ; UUID v4 par saisie générés à la création du brouillon, test dédié.
7. **Surcharge de la route d'écriture** par une file de 100 saisies : groupe de rate-limit dédié, backoff.
8. **Piège n°14 (jumelles)** : tout durcissement `attachments` se reporte sur `public_submit` et inversement
   (magic numbers, plafonds, `s3_key`) : checklist en revue finale.
9. **Bundle** : code offline en chunk `lazy()` de la route de collecte, pas dans l'entrée.
10. **Complexité XLSForm** : `to_cel` étendu seulement avec tests de parité ; tout doute → `not_ported` (rapport honnête conservé).

## 10. Critères d'acceptation
1. Une App de collecte installée sur mobile s'ouvre **hors ligne** (coquille + kit en cache), une saisie
   point/ligne/polygone + 2 photos peut être enregistrée, survit à un rechargement et à la fermeture du navigateur.
2. Au retour du réseau, la saisie arrive **exactement une fois** (y compris après coupure au milieu d'un envoi
   ou rejeu d'une requête), photos comprises, et l'état passe à « Envoyée » dans « Mes saisies ».
3. Un rejet serveur (422/403/404/410) rend la saisie « En conflit », éditable ou exportable, jamais perdue ni
   rejouée en boucle.
4. Aucun champ sensible n'apparaît dans le kit ; un autre utilisateur du même appareil ne voit pas la file.
5. XLSForm : libellés de choix visibles dans l'App ; `required` refusé par le **serveur** (REST, public, sync) ;
   `default`/`calculate`/`select_multiple` portés ; réimport sans doublon avec rapport de différences.
6. Page `/collect/:token` fonctionnelle (en ligne et hors ligne), plusieurs fichiers, audio/vidéo acceptés,
   PoW vérifiée, a11y axe sans violation.
7. Suites core + shell + E2E **entièrement vertes**, couverture ≥ seuils, OpenAPI/TS régénérés (diff attendu non vide),
   migrations testées base non vide, i18n/lint/bundle verts, rejeu stack réelle consigné dans `docs/revue/`.
8. Clôture documentaire dans le même geste (CLAUDE.md `### Livré` une ligne, archive, GAP/REV, inventaire,
   `feature_health_cli --write`) — **hors du commit de spec**.

## 11. Découpage en tâches (détail dans le plan)
Lot A (cœur, indépendant) T1-T5 : idempotence + `collect_client_ops`, unicité attachments, kit, soumission publique,
PoW. Lot B (XLSForm) T6-T8. Lot C (saisie) T9-T11. Lot D (offline) T12-T18. Lot E (clôture) T19-T21.
Ordre recommandé : A → D (en parallèle de B/C) → E. Revue par tâche **et** revue finale de branche
(piège n°4).

## 12. Décisions retenues par défaut (selon la synthèse) et questions ouvertes
Retenues (D6, §L8 de la synthèse) : offline = formulaires + file de sync + photos, **création seule**, pas de cartes
hors-ligne ; IDs idempotents côté client ; SW de coquille écrit à la main ; IndexedDB natif ; file conservée au
logout ; conflits explicites sans fusion.

Questions à arbitrer par Tanguy avant exécution :
- **Q1** Édition hors-ligne d'enregistrements déjà serveur (If-Match, vraie résolution de conflits) : v2 ou dans ce lot ?
  (défaut : v2).
- **Q2** `choice_filter` : filtrage client + contrainte serveur dans ce lot, ou `not_ported` (défaut : client + contrainte si CEL le permet, sinon `not_ported`).
- **Q3** Chiffrement au repos de l'IndexedDB (Web Crypto, clé non extractible) : hors lot (défaut) ou obligatoire pour appareils partagés ?
- **Q4** `repeat` → collection fille ARC-21 + sous-formulaire (dépendance de fid parent dans la file) : hors lot (défaut) ?
- **Q5** Anti-abus public : PoW maison (défaut) ou captcha tiers (hCaptcha/Turnstile : égress + RGPD + mode « sans fond externe » 0095) ?
- **Q6** Durée de session Keycloak hors-ligne : fixer une recommandation (ex. 30 j) dans le realm importé, ou seulement documenter ?
- **Q7** Dépendance dev `fake-indexeddb` acceptable (défaut oui, test seulement) ?
- **Q8** Plafonds client (200 Mo / 100 saisies / 5 photos) et rétention (14 j kit, 7 j « envoyée », 30 j `collect_client_ops`) : valeurs par défaut OK ?
- **Q9** Positionnement : D6 laisse l'alternative « retirer la promesse de collecte terrain » ; cette spec suppose D6 tranchée « faire ».
