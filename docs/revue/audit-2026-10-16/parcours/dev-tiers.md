# Parcours persona : Développeur tiers (stack réelle locale, OIDC Keycloak)

Date : 2026-10-16, HEAD `c0251b66`. Scénario : API `/v1` + OpenAPI, clé de service, MCP, embedding, extension widget, premier « hello world » chronométré.
Captures : `docs/revue/audit-2026-10-16/parcours/dev-tiers/` (4 PNG). Aucun fichier source édité, rien commité, ni `postgis-test` ni suite de tests. Scripts Playwright/curl hors dépôt (scratchpad).

## 0. Conditions de test

- Compte `alice` (Créateur, pas admin ; `GET /v1/me` 200), jeton OIDC par grant password sur le client `geostudio-shell` (`deploy/keycloak/geostudio-realm.json:713`, `directAccessGrantsEnabled: true`) : 0,23 s. Le realm ne contient que `alice` et `bob` (`geostudio-realm.json:2290,2305`) : aucun admin, donc l'étape « extension » ne peut pas être rejouée en écriture.
- **Limite majeure : l'image `geostudio-core` qui tourne date du 2026-10-11** (`docker images`). Preuve : `docker exec geostudio-core-1 ls /app/app/apikeys` donne « No such file » alors que `core/app/main.py:21,450` monte le routeur ; `GET /v1/api-keys` répond 404 en live. **L'étape « clé de service » n'a donc pas pu être jouée sur la stack**, elle est évaluée sur le code. Le serveur MCP annonce aussi `version 1.29.1`.
- Le shell servi sur `:8300` est en `VITE_AUTH_MODE=mock` et `VITE_CORE_URL=http://localhost:8200` (`curl localhost:8300/env-config.js`) : appel cross-origin du cœur (voir F8).
- Données de test créées : item app `af3b360208a34ffaa28d6fb3e15a6360` « DT audit hello » (+ lien de partage 1 jour), **un client Keycloak anonyme enregistré par DCR** (`c35fb271-05f5-4383-a610-566c9415c70d`, `audit-dev-tiers`) que je n'ai pas pu supprimer (jeton d'enregistrement non conservé, pas d'identifiants admin dans `.env` utilisables) ; un second client DCR a été supprimé proprement. A nettoyer par le propriétaire.

## 1. Chronologie et notes

| Étape | Durée mesurée | Note /10 | Résumé |
|---|---|---|---|
| 1. Obtenir un jeton, `GET /v1/me` | 0,23 s + 27 ms | 7 | Rapide ; mais rien n'explique à un tiers comment s'authentifier (F3). |
| 2. Découvrir l'API : OpenAPI + Swagger | `/openapi.json` 2 ms, 18 Ko de schéma ; `/docs` 2,4 s | 3 | 170 opérations, 9 avec description, 0 exemple, 0 `securitySchemes` (F1). Swagger cassé derrière Traefik (F2). |
| 3. Hello world REST (créer un item) | 4 essais (3 x 422, 1 x 201 à 29 ms) ; ~4 min de lecture de schéma | 5 | Erreurs 422 RFC 7807 avec champ et message : bonnes. Mais schéma `BuilderConfig` à plat (11 `kind`), aucun exemple minimal (F4). |
| 4. Clé de service | non jouée (image périmée) | 4 (code) | Clé liée au créateur, sans portée, refusée au MCP (F5, F6). |
| 5. MCP | initialize 14 ms, `tools/list` 17 ms, 33 outils, `whoami`/`search_catalog` OK | 6 | Fonctionne dès qu'on a le bon jeton (audience `geostudio-mcp`) ; découverte OAuth cassée derrière le proxy (F7). |
| 6. Embedding (lien de partage + iframe site tiers) | création de lien 29 ms ; iframe : échec en config locale, LCP 128 ms une fois le cœur same-origin | 6 | Mécanisme sain, mais CORS/URL du cœur piégeux (F8) et pas de doc d'embarquement tiers. |
| 7. Extension widget | non rejouée (admin absent) | 4 (code/doc) | Guide unique, périmé sur le chemin et sur `moduleUrl` ; HTTPS obligatoire, aucun test local possible (F9). |
| 8. Premier « hello world » chronométré de bout en bout | ~12 min pour token + item + lien + iframe (hors clé) | 5 | Voir §3. |

Note globale : **5,0 / 10**. Le cœur répond vite (toutes les latences < 30 ms) et les erreurs sont lisibles ; ce qui pénalise est l'outillage d'accueil du développeur tiers : documentation, sécurité d'accès documentée, découvrabilité, et trois défauts de câblage derrière le proxy de production.

## 2. Constats

**F1. OpenAPI sans schéma de sécurité ni exemples.** `GET /openapi.json` : 170 opérations, `security` sur 0, exemples 0, `description` sur 9, `servers` absent. 150 opérations déclarent `authorization` comme simple paramètre d'en-tête optionnel (`core/app/apikeys/routes.py:19`, même motif partout) au lieu d'un `securitySchemes` : le bouton « Authorize » de Swagger n'existe pas (`.authorize` absent, capture `02a`), et les clients générés n'ont aucune notion d'auth. Preuve : `python3 -I` sur `/tmp/.../openapi.json`.

**F2. Swagger inutilisable via la route publique de production.** `https://localhost/api/docs` renvoie 200 mais le HTML pointe `url: '/openapi.json'` (non préfixé par `/api`) ; le navigateur reçoit la page du shell : « Unable to render this definition » (capture `02b`). `core/app/main.py` ne positionne ni `root_path` ni `docs_url`/`openapi_url` (grep vide). De plus la CSP de Traefik (`script-src 'self'`) bloque `cdn.jsdelivr.net` : violations constatées en console (passeront en blocage en mode enforce, CLAUDE.md décrit `CORE_CSP_MODE`). `/api/openapi.json` fonctionne, seul l'UI est cassé.

**F3. Aucune documentation d'accueil API.** `docs/guides/` ne contient qu'un guide (widget). `README.md` cite REST/OGC/MCP (l.56, 111-124) sans exemple d'appel ni d'authentification. Un tiers doit deviner que le jeton se prend sur Keycloak, que l'audience du client shell est `geostudio-core` (jeton décodé : `aud: geostudio-core`) et que le MCP exige une autre audience.

**F4. Hello world REST : schéma opaque.** `POST /v1/configs` (pas de `POST /v1/items`) attend `{title, config}` ; `config.kind` seul → 422 « app config requires a layout » ; `layout.widgets` → 422 « unknown keys: widgets » (la clé est `items`). Le minimum valide est `{"title":"…","config":{"kind":"app","layout":{"type":"grid","items":[]}}}`. `BuilderConfig` est une union plate de tous les `kind` (`components/schemas/BuilderConfig`), alors que `GET /v1/schemas/app-config` (18,6 Ko) existe mais n'est pas référencé comme exemple. Le « hello world » coûte 3 allers-retours d'essais.

**F5. Clé de service : puissante et sans portée.** `core/app/apikeys/service.py:1-6` : une clé résout vers son créateur et hérite de tous ses privilèges ; `create_api_key` (l.41-60) n'a ni portée, ni liste d'opérations, ni contrainte d'IP ; seulement une expiration 1 à 365 jours. Elle ne peut pas gérer d'autres clés (`routes.py:19-24`, bien). Un tiers donne donc à son script les droits complets de son compte.

**F6. La clé de service n'ouvre pas le MCP.** `core/app/mcp/auth.py:25-50` : `KeycloakTokenVerifier` ne décode que du JWT RS256 d'audience `geostudio-mcp` ; un jeton `gsk_…` est rejeté (401 constaté sur le live avec `gsk_abcdef012345_xxx`). La résolution `gsk_` n'existe que dans `app/auth/dependency.py:211`. Un agent headless doit donc passer par OAuth 2.1 interactif ; pas de chemin « clé de service vers MCP ».

**F7. Découverte OAuth du MCP incomplète derrière le proxy.** `GET https://localhost/api/mcp` répond bien 401, mais l'en-tête `WWW-Authenticate` annonce `resource_metadata="http://localhost:8200/.well-known/oauth-protected-resource/mcp"` (base `CORE_BASE_URL`, `core/app/main.py:169`, défaut `localhost:8200` dans `docker-compose.yml:262` et **absent de `.env.example`**). Sur le domaine public, `https://localhost/.well-known/oauth-protected-resource/mcp` est servi par nginx du shell (405) : aucune règle Traefik `well-known` (grep `docker-compose.yml` vide). Un client MCP standard ne découvre donc pas Keycloak. Positif : l'enregistrement dynamique (DCR) Keycloak anonyme fonctionne (`registration_endpoint` publié) et j'ai obtenu un jeton MCP valide en demandant `scope=geostudio-mcp-audience` (`geostudio-realm.json:753`, scope optionnel du client shell) ; `tools/list` renvoie 33 outils. Mais le DCR anonyme crée un client public sans limite (voir données de test).

**F8. Embedding : fonctionne seulement si le cœur est same-origin.** Lien de partage : `POST /v1/items/{id}/share-links {ttlDays}` 29 ms, `GET /v1/share-links/{token}` 200, `url` = `…/embed/<jwt>`, extrait iframe fourni par `shell/src/shell/ShareForm.tsx:206`. Sur une page hôte d'une autre origine (`:9100`), l'iframe `http://localhost:8300/embed/…` affiche « Ce lien de partage est expiré ou révoqué » à tort : CORS bloqué (« Access to fetch … `localhost:8200/v1/share-links/…` ») car `VITE_CORE_URL=http://localhost:8200` est cross-origin et la CORS du cœur (`core/app/main.py:119-150, 380-410`) ne couvre que des GET en liste blanche, pas `/v1/share-links`, avec `Access-Control-Allow-Headers: Content-Type` seul (l.392, pas `X-Share-Link-Token`). Avec `VITE_CORE_URL=https://localhost/api` (réécriture de `env-config.js` dans le navigateur), l'embed charge en 2,5 s, LCP 128 ms, sans erreur console (capture `05b`, app vide). Message d'erreur trompeur : un défaut CORS est présenté comme « lien expiré ». `/embed` n'a pas `X-Frame-Options` (bon) alors que `/` a `DENY` (`curl -I https://localhost/`). Hors périmètre : aucune CORS pour une SPA tierce appelant l'API avec `Authorization` (preflight `/v1/me` : 404, `/v1/collections` : 204 sans `Authorization` autorisé) : l'API n'est utilisable que depuis un backend.

**F9. Extension widget : guide périmé, test local impossible.** `docs/guides/2026-07-13-ecrire-un-widget-web-component.md:116` indique `POST /extensions` (chemin réel `/v1/extensions`, `core/app/extensions/routes.py:32` sous le préfixe `/v1` de `main.py`) ; le manifeste d'exemple `examples/external-widget/manifest.json:5` a `moduleUrl: "widget.js"` alors que le cœur exige `^https://…` (`core/app/extensions/schemas.py:9`, 422 constaté en postant ce manifeste : « moduleUrl: String should match pattern »). Le guide demande une `moduleUrl` absolue sans préciser HTTPS ; aucune URL `http://localhost` n'est tolérée, donc impossible de tester un widget en local sans TLS. Enregistrement réservé à `admin.extensions.manage` (`routes.py:38`) et `ExtensionCreate` est validé avant le contrôle de privilège (un non-admin reçoit 422 plutôt que 403). Pas de sandbox (assumé par le guide).

**F10. Divers positifs.** Erreurs RFC 7807 avec `errors[].field` (`422` constatés) ; `GET /v1/instance` public décrit les capacités ; MCP en 14 ms ; `X-Frame-Options`/CSP présents sur le shell ; rate limit en 429 + `Retry-After: 60` (`core/app/main.py:369`), mais aucun en-tête `X-RateLimit-*` sur les 200 (grep vide), donc un client ne peut pas se réguler.

## 3. Premier « hello world » chronométré

Du jeton au premier objet servi dans un iframe tiers : jeton 0,2 s ; découverte du schéma + 3 essais 422 ~4 min ; item 29 ms ; lien de partage 29 ms ; diagnostic CORS ~5 min ; total ~12 min sur un projet que je connais déjà. Pour un vrai tiers sans l'accès au code : estimé > 1 h (pas de guide d'API, pas d'exemple minimal, Swagger cassé en prod).

## 4. Mesures

LCP du contenu iframe embed : 128 ms (Chromium headless, 1280x800). `/docs` direct : 2,4 s réseau idle (dépend du CDN). Latences API : `/v1/me` 27 ms, `/v1/items` 20 ms, `/v1/collections` 55 ms, `POST /v1/configs` 29 ms, MCP `tools/list` 17 ms. a11y : non auditée sur le shell (aucune surface d'auteur du shell parcourue, parcours API-centré) ; Swagger UI tiers non évalué.

## 5. Blocages (classés)

1. **F2 : Swagger/`/docs` inutilisable derrière Traefik (et CSP)** : la vitrine d'API est cassée en production.
2. **F1 + F3 : pas de `securitySchemes`, pas d'exemples, pas de guide d'accueil API** : le tiers ne sait pas s'authentifier ni quoi envoyer.
3. **F7 : découverte OAuth du MCP renvoie `localhost:8200` et n'est pas routée sur le domaine public** (`CORE_BASE_URL` absent de `.env.example`).
4. **F6 + F5 : clé de service sans portée et inutilisable avec le MCP** : pas de chemin sûr pour un agent headless.
5. **F8 : défaut CORS présenté comme « lien expiré » ; API non appelable depuis un navigateur tiers.**
6. **F9 : guide d'extension périmé (chemin, `moduleUrl`), pas de test local possible.**
7. **Environnement : image `core` périmée de 5 jours** (routes `api-keys` absentes) ; il faut reconstruire avant tout rejeu de l'étape clé de service.

## 6. Non fait, et pourquoi

Création/usage réel d'une clé de service et contrôle de portée (image périmée) ; enregistrement d'une extension (aucun compte admin dans le realm ; pas d'hôte HTTPS pour `widget.js`) ; rendu d'une app avec widget dans l'iframe (app de test vide) ; audit axe-core de pages shell (hors scénario API).
