# SP-57b — Contrat d'API `/v1/`, ADR, guide de contribution (vague 5, volets 5.3+5.4+5.5)

Date : 2026-09-06. Ferme la seconde moitié de **GAP-14** (« Vague 5, qualité
transverse, quasiment non livrée »,
`docs/revue/2026-09-04-analyse-gaps.md:58`) : préfixe de version `/v1/` sur
l'API du cœur (volet 5.3), Architecture Decision Records (volet 5.4), guide
de contribution externe (volet 5.5). Le volet i18n+a11y (5.1+5.2) est traité
par le document jumeau **SP-57a**
(`docs/superpowers/specs/2026-09-06-sp57a-i18n-a11y-design.md`, qui explique
aussi la décision de découpage §0).

## 0. Rappel du découpage

Cf. `docs/superpowers/specs/2026-09-06-sp57a-i18n-a11y-design.md` §0 pour la
justification complète. En résumé : ce document regroupe les trois volets
restants parce qu'ils partagent un profil (gouvernance/infrastructure, pas de
contenu shell) distinct de i18n/a11y, et parce qu'aucun des deux SP ne
dépend de l'autre.

## 1. Vérifié avant d'écrire (piège CLAUDE.md n°3/12)

### 1.1 Volet 5.5 (guide de contribution) — **l'affirmation de GAP-14 est fausse**

GAP-14 affirme : « guide de contribution externe (5.5) — absent ». Vérifié
directement :

```bash
find . -maxdepth 1 -iname "CONTRIBUTING*"   # → ./CONTRIBUTING.md
find . -maxdepth 1 -iname "CODE_OF_CONDUCT*"  # → ./CODE_OF_CONDUCT.md
git log --diff-filter=A --format=%H\ %ad --date=short -- CONTRIBUTING.md
# → 1d025d74 2026-07-16 (SP-9, "docs: add CONTRIBUTING.md, link it from README")
```

`CONTRIBUTING.md` (155 lignes) existe depuis le 2026-07-16 (SP-9), maintenu
depuis (3 commits de suivi jusqu'au 2026-07-16 inclus), et couvre déjà :
prérequis, démarrage local (`bootstrap-env.sh`), commandes de test des deux
suites, convention de commit avec exemples réels tirés de l'historique,
process de pull request (5 étapes), pointeurs de contexte
(`CLAUDE.md`/`docs/vision/`/`docs/superpowers/`), **process de release
complet** (bump de version, `CHANGELOG.md`, tag, CI de release, vérification
des images publiées), process de signalement de bug/feature (avec lien vers
GitHub issues et vers la feuille de route), en-têtes SPDX, et un lien vers
`CODE_OF_CONDUCT.md` (Contributor Covenant, présent aussi). **Ce n'est pas un
squelette** : c'est un document opérationnel complet, à jour au 2026-07-16 au
minimum.

Ce que GAP-14 a probablement voulu dire, ou ce qui manque réellement une fois
`CONTRIBUTING.md` relu : pas de gabarits GitHub structurés. Vérifié :

```bash
find .github -maxdepth 2 -type f
# → dependabot.yml, workflows/{ci,codeql,release,gitleaks}.yml
# → PAS de ISSUE_TEMPLATE/, PAS de PULL_REQUEST_TEMPLATE.md
find . -maxdepth 1 -iname "SECURITY*"   # → rien
```

**Ce volet est donc déjà satisfait aux trois quarts.** Le périmètre réel de
ce SP pour 5.5 se réduit à : gabarits GitHub (issue bug/feature,
pull-request) qui structurent ce que `CONTRIBUTING.md` demande déjà en
prose, et un `SECURITY.md` (politique de signalement de vulnérabilité,
absente — distincte du "reporting a bug" déjà couvert, et un fichier que
GitHub affiche spécifiquement dans l'onglet Security d'un dépôt public).
Coût réel : quelques heures, pas un jour — **la spec le documente noir sur
blanc plutôt que de laisser croire qu'un "guide de contribution" entier
reste à écrire**, exactement le genre d'écart que CLAUDE.md demande de
corriger sans re-demander, en le consignant (piège n°3).

### 1.2 Volet 5.4 (ADR) — l'absence est réelle, mais le contenu source existe déjà

```bash
ls docs/adr   # → No such file or directory
```

Confirmé absent. Mais `docs/vision/2026-07-04-feuille-de-route-geostudio.md`
§7-8 (« Points d'arbitrage technique » / « Décisions d'arbitrage ») contient
déjà ~35 arbitrages numérotés (A1-A35+, vérifié par `grep -n "^### A"` :
A1 à A35 au moins), chacun sous la forme options/avantages-inconvénients/
recommandation — le contenu de fond d'un ADR, déjà écrit, jamais reformaté
au standard ADR. `CLAUDE.md` a aussi sa propre liste de « Décisions figées »
(licence, cœur Python/FastAPI, `can()` unique, OIDC/Keycloak, OGC API
Features, procrastinate, CEL, Web Components, etc.) qui recoupe largement
ces arbitrages. **Ce volet est donc majoritairement un travail
d'extraction/reformatage rétroactif, pas de recherche/décision nouvelle** —
budget réaliste plus proche de 1-1,5j que d'un chantier de conception.

### 1.3 Volet 5.3 (contrat d'API `/v1/`) — l'absence est réelle et le couplage
caché est bien plus large que le texte de GAP-14 ne le suggère

```bash
grep -n "include_router\|prefix=" core/app/main.py
```

31 routeurs enregistrés dans `create_app()` (`core/app/main.py`), aucun sous
`/v1`. 27 routeurs sont créés sans préfixe (`APIRouter()` nu — chaque route
porte son chemin complet, ex. `@router.get("/items")`) ; 4 portent déjà un
préfixe **de domaine**, pas de version : `stac` (`/stac`), `dcat` (`/dcat`),
`public` (`/public`), `compliance` (`/compliance`). `/health` est un
`@app.get` direct sur `app` (hors `include_router`). Le serveur MCP est monté
séparément : `app.mount("/", mcp_server.streamable_http_app())` — une
sous-application ASGI distincte, pas un routeur FastAPI.

**Ce que versionner et ce qu'il faut exclure** — décision de conception :
tous les routeurs `include_router` (31, y compris `stac`/`dcat`/`public`/
`compliance` qui deviennent `/v1/stac` etc.) passent sous `/v1` ; `/health`
(contrat de healthcheck Docker,
`docker-compose.yml:366` : `urlopen('http://localhost:8200/health')`) et le
montage `/mcp` (contrat de protocole MCP + découverte OAuth
`.well-known/oauth-protected-resource/mcp`, SP-2) **restent hors
versionnement, immuables**. Justification : ce sont des contrats externes à
protocole fixe (Docker healthcheck, spec MCP/OAuth), pas des ressources REST
du cœur — les verser sous `/v1` casserait un contrat qui n'appartient pas à
GeoStudio de faire évoluer.

**Vérifié : le shell atteint le cœur par un unique point de construction
d'URL par requête, mais PAS un unique point de construction de `coreUrl`
lui-même** — nuance importante :

- `shell/src/api/base.ts::createBase()` construit un `ItemClientBase` avec
  un champ `coreUrl` et deux fonctions `request<T>()`/`requestBlob()` qui
  interpolent `` `${coreUrl}${path}` ``. C'est le point d'entrée principal,
  utilisé par la majorité des domaines (`shell/src/api/domains/*.ts`).
- **Mais au moins 4 fichiers de domaine construisent leur propre `fetch()`
  directement avec `coreUrl`, en contournant `request()`** (vérifié par
  grep, pas supposé) :
  - `shell/src/api/domains/layers.ts` (3 sites : `/harvest/feature-layers`,
    `/map-icons`, `/map-icons/{id}/file`)
  - `shell/src/api/domains/exportsIngestion.ts` (1 site : `/analytics/sql`,
    plus un `fetch(url)` vers une URL présignée S3 externe — **celui-là ne
    doit PAS recevoir `/v1`**, ce n'est pas le cœur)
  - `shell/src/api/domains/extensionsAdminTools.ts` (2 sites : `/extensions`,
    `/extensions?all=true`)
  - `shell/src/api/domains/items.ts` (2 sites :
    `/items/{pk}/thumbnail`, `/configs/by-item/{pk}`)
  - `shell/src/api/domains/features.ts` (3 sites, via un helper local
    `requestFeatureWrite(url, ...)` : create/update/delete feature sur
    `/collections/{id}/items[/{fid}]`)

  Éditer `request()`/`requestBlob()` seuls **laisserait ces 11 sites
  inchangés** — un oubli de cette classe (piège CLAUDE.md n°5 : chemin
  oublié) casserait silencieusement l'upload d'icône, l'écriture de
  features, `/analytics/sql`, les extensions et les vignettes le jour où le
  cœur bascule sous `/v1`.

- **Design retenu, qui couvre tous les sites d'un coup sans les toucher
  individuellement** : redéfinir ce que **`coreUrl` lui-même contient**,
  au point unique où il est construit (`createBase(opts)`), plutôt que
  d'ajouter `/v1` à chaque site d'appel. Concrètement :

  ```ts
  export function createBase(opts: { coreUrl: string; getToken: () => string | undefined }): ItemClientBase {
    const coreUrl = `${opts.coreUrl}/v1`;
    // ... request()/requestBlob() utilisent `coreUrl` (déjà versionné) sans autre changement
    return { coreUrl, request, requestBlob, ... };
  }
  ```

  Tous les fichiers ci-dessus lisent `coreUrl` depuis l'objet `base`/`opts`
  retourné par `createBase()` (vérifié : `shell/src/api/itemClient.ts` ne
  lit `base.coreUrl` qu'à un seul endroit,
  `getCoreUrl: () => base.coreUrl`) — **aucun ne relit `VITE_CORE_URL`/
  `import.meta.env` directement**. Un seul point de redéfinition suffit
  donc à couvrir les 5 fichiers de domaine ET `request()`/`requestBlob()`
  ET tout futur domaine qui suivrait le même patron.

- **Pourquoi ce choix précis (pas un ajout de `/v1` dans chaque
  `fetch()`)** : le dépôt a déjà payé exactement cette classe de bug une
  fois. Le commentaire de `shell/src/map/MapView.tsx::isHostedCoreUrl`
  (fonction de sécurité qui décide si une URL de tuile doit recevoir le
  jeton d'auth) documente que la revue finale SP-24 (C1) a trouvé un bug où
  `VITE_CORE_URL` valait `https://hôte/api` en prod mais une comparaison de
  chemin ne le prenait pas en compte, désactivant silencieusement l'auth
  sur les tuiles non publiques. Cette fonction compare déjà `coreUrl`
  (comme "base" via `new URL(coreUrl).pathname`) contre l'URL réelle des
  tuiles — **et les URLs de tuiles sont, elles aussi, construites à partir
  du même champ `coreUrl`** (`shell/src/api/domains/layers.ts`,
  `fetchHostedTileset3dSources`/`fetchHostedTerrain3dSources`). Si `coreUrl`
  est redéfini une seule fois à la source, la fonction de vérification et
  le code de construction d'URL restent automatiquement synchronisés (les
  deux lisent le même champ) — c'est le seul design qui exclut *par
  construction* une resucée du bug SP-24 C1 sur `/v1`.

### 1.4 Chemins de routage bruts, hors du routage FastAPI — la vraie surprise
de cette vérification

Plusieurs endroits du cœur comparent `request.url.path` à des chaînes/regex
**littérales**, en dehors de tout `include_router` — ajouter `/v1` au niveau
du routeur FastAPI ne les met PAS à jour automatiquement. Liste complète
(grep exhaustif, `core/app/main.py` + `core/app/ratelimit/limiter.py`) :

**`core/app/main.py`** :
- `_AGGREGATE_PATH_RE = re.compile(r"^/collections/[^/]+/aggregate$")`
- `_EXPORT_PATH_RE` (alternatives : `/collections/{id}/export[/items]`,
  `/datasets/{id}/arcgis/export`, `/export`, `/app-exports`)
- `_APPEXPORT_CORS_PATH_RE` (alternatives : `/collections[/{id}]`,
  `/collections/{id}/schema`, `/collections/{id}/items[/{id}]`,
  `/collections/{id}/aggregate`, `/extensions`, `/public/items`)
- `_APPEXPORT_CORS_RULES` (7 couples regex+méthode, mêmes chemins que
  ci-dessus)
- `read_only_guard` (middleware) : comparaisons littérales
  `request.url.path != "/mcp"` (**ne change pas** — `/mcp` reste hors
  versionnement) et `!= "/analytics/sql"` (**change** en `/v1/analytics/sql`)

**`core/app/ratelimit/limiter.py`** (`route_group()`) :
- `_SQL_RE = re.compile(r"^/analytics/sql$")` → `/v1/analytics/sql`
- `_LLM_RE = re.compile(r"^/mcp$|^/copilot/turn$")` → **seule la seconde
  alternative change** : `^/mcp$|^/v1/copilot/turn$` (`/mcp` reste fixe,
  `/copilot/turn` est une route normale versionnée)
- `_HARVEST_RE = re.compile(r"^/harvest/")` → `^/v1/harvest/`
- `_COLLECTIONS_EMPTY_RE = re.compile(r"^/collections/empty$")` →
  `^/v1/collections/empty$`
- `_ARCGIS_LIVE_QUERY_RE = re.compile(r"^/datasets/[^/]+/arcgis/(items|aggregate)$")`
  → préfixer `/v1`
- `_WEBHOOK_TRIGGER_RE = re.compile(r"^/pipelines/[^/]+/trigger$")` →
  préfixer `/v1`

**`docker-compose.yml`** (labels Traefik, server-to-server, indépendants du
navigateur/`coreUrl`) :
- `traefik.http.middlewares.admin-auth.forwardauth.address=http://core:8200/admin-tools/verify`
  → `.../v1/admin-tools/verify` (SP-32, passerelle admin `/admin/martin`
  etc.)
- `traefik.http.middlewares.seo-static-rewrite.replacepathregex.replacement=/public/$$1`
  → `/v1/public/$$1` (SP-55, `sitemap.xml`/`robots.txt`)
- `traefik.http.middlewares.seo-bots-rewrite.replacepathregex.replacement=/public/sites/$$1/social-preview`
  → `/v1/public/sites/$$1/social-preview` (SP-55, aperçu social)

**`core/app` — construction d'URLs absolues embarquées dans des réponses**
(via `CORE_BASE_URL`/`CORE_INTERNAL_BASE_URL`, 13 fichiers identifiés par
`grep -rln "CORE_BASE_URL\|base_url" core/app/*/*.py`, à trier un par un —
pas tous ne construisent une URL d'API v1, certains construisent une URL
MCP interne qui ne doit PAS bouger) : `admin_tools/routes.py`,
`analytics/duckdb_conn.py`, `appexport/jobs.py`, `collections/routes.py`,
`features/routes.py`, `ingestion/importer.py`, `items/routes.py`,
`pipelines/connector_runtime.py`, `dcat/routes.py`, `public/routes.py`,
`copilot/mcp_loopback.py` (**ne doit pas changer** — loopback interne vers
`/mcp`, jamais `/v1`), `mcp/server.py` (**ne doit pas changer**, même
raison), `jobs/__init__.py`.

Cette liste n'a pas vocation à être exhaustive au sens où chaque ligne a été
lue en détail (ça, c'est le travail de la Task 4 du plan) — mais elle
prouve, avant même de commencer, que « ajouter un préfixe `/v1` » est un
changement à surface bien plus large qu'un simple `APIRouter(prefix="/v1")`
dans `main.py`. C'est le risque principal de ce SP (§5).

### 1.5 Impact sur la suite de tests — vérifié, pas estimé

```bash
grep -rln 'page.route("https://core.test' shell/e2e/*.spec.ts | wc -l   # → 28 fichiers
grep -ron 'page.route("https://core.test' shell/e2e/*.spec.ts | wc -l  # → 80 occurrences
grep -rln "core.test" shell/src --include=*.test.ts --include=*.test.tsx | wc -l  # → 39 fichiers
```

**Bonne nouvelle partielle** : une partie des mocks E2E utilise déjà un
glob Playwright `**/chemin*` (ex. `page.route("**/extensions*", ...)`,
`shell/e2e/action-bus-containment.spec.ts:32`) — ce style continue de
matcher après l'ajout de `/v1` sans modification (`**` traverse les
segments de chemin). **Mauvaise nouvelle, dominante** : 80 occurrences
réparties sur 28 fichiers utilisent une URL **absolue**
(`https://core.test/items/...`, `https://core.test/instance`, etc., cf.
`shell/.env.e2e:VITE_CORE_URL=https://core.test`) — celles-là ne matchent
plus rien une fois le chemin réel devenu `https://core.test/v1/items/...`,
et échoueraient silencieusement en timeout (Playwright n'intercepterait
jamais la requête, qui partirait en réseau réel et échouerait autrement).
Plus 39 fichiers de test Vitest qui référencent `core.test` (mocks `fetch`
avec des URLs absolues, à vérifier au cas par cas — certains peuvent déjà
utiliser des assertions partielles insensibles au préfixe). **Ce volet de
migration mécanique de test est le plus gros poste de coût réel de ce SP**,
plus gros que le changement de production lui-même.

## 2. Volet 5.3 — Contrat d'API `/v1/`

### 2.1 Cœur — routeur imbriqué

Dans `create_app()` (`core/app/main.py`), après la construction de tous les
routeurs existants : créer `v1_router = APIRouter(prefix="/v1")`, y appeler
`v1_router.include_router(x.router)` pour les 31 routeurs (au lieu de
`app.include_router(x.router)` direct), puis `app.include_router(v1_router)`
une seule fois. `/health` (`@app.get` direct) et le montage MCP
(`app.mount("/", ...)`) restent inchangés, ajoutés à `app` comme aujourd'hui.

### 2.2 Chemins bruts hors routage (§1.4) — mis à jour en lockstep

Chaque regex/comparaison littérale énumérée en §1.4 (`main.py` +
`limiter.py`) reçoit son `/v1` là où la route sous-jacente en a un ; `/mcp`
reste inchangé partout où il apparaît. Un test de régression dédié par
mécanisme concerné (rate-limit, CORS appexport, garde lecture-seule) —
détail en plan.

### 2.3 Infra — Traefik + `CORE_BASE_URL`

Les 3 labels Traefik de `docker-compose.yml` identifiés en §1.4 sont mis à
jour. Les 13 fichiers `core/app/*/*.py` qui construisent une URL absolue via
`CORE_BASE_URL`/`CORE_INTERNAL_BASE_URL` sont audités un par un — ceux qui
pointent vers une route désormais sous `/v1` (thumbnails, liens STAC/DCAT
self, proxy de pièce jointe, liens de notification, export appexport)
reçoivent le préfixe ; ceux qui pointent vers `/mcp` (`copilot/mcp_loopback.py`,
`mcp/server.py`) ou vers une URL non-API (ex. `PUBLIC_BASE_URL` pour le
sitemap, distinct de `CORE_BASE_URL`, déjà traité par SP-55) n'y touchent
pas.

### 2.4 Shell — redéfinition unique de `coreUrl`

`shell/src/api/base.ts::createBase()` : la ligne unique décrite en §1.3.
Aucun autre fichier de domaine n'a besoin d'édition individuelle — c'est
précisément ce que le design évite.

### 2.5 Tests — migration mécanique des mocks

80 occurrences sur 28 fichiers E2E + jusqu'à 39 fichiers Vitest (§1.5) : une
substitution mécanique (`https://core.test/` → `https://core.test/v1/`,
appliquée sélectivement — **pas** sur les mocks qui visent une URL non-API
comme l'upload S3 présigné `http://localhost/upload` dans
`shell/e2e/attachments.spec.ts:45`, à exclure explicitement). Vérifiée par
un grep final qui confirme l'absence de toute occurrence orpheline de
`core.test/` non suivie de `/v1` sur un chemin d'API (en excluant les
domaines explicitement hors `/v1` : aucun, puisque `/mcp`/`/health` ne sont
jamais mockés directement par le shell, cf. SP-57a spec §1.3 confirmant
qu'aucun appel direct à `/mcp` n'existe côté shell).

### 2.6 Pas de compatibilité ascendante — décision assumée

Aucun consommateur externe réel de l'API du cœur n'existe à ce jour (Q2 du
comparatif §8 — « premiers utilisateurs réels » — reste ouverte,
`CLAUDE.md`). Le produit est en v0.1, encore non engagé sur une politique de
stabilité d'API publique. **Décision : migration directe, sans alias de
rétrocompatibilité** (pas de double montage `/items` **et**
`/v1/items` en parallèle) — c'est précisément le moment le moins coûteux
pour introduire le préfixe, avant qu'un vrai consommateur externe existe.
Si un déployeur self-hosted a des scripts contre l'API non préfixée (peu
probable, produit encore jeune), la mise à niveau nécessite de les adapter —
documenté dans `CHANGELOG.md`/notes de version, pas un problème à absorber
silencieusement dans ce SP.

### 2.7 Hors périmètre explicite

- **Pas de `/v2` ni de politique de dépréciation formelle.** Ce SP pose la
  convention (`/v1` maintenant, avant qu'un futur breaking change n'exige
  un `/v2`) — pas le mécanisme de coexistence multi-version (hors besoin
  tant qu'une seule version existe).
- **Pas de changement de forme des réponses.** Seuls les chemins bougent ;
  aucun schéma Pydantic/TS ne change de forme dans ce SP (le diff OpenAPI
  attendu est un déplacement de préfixe sur chaque route, pas un changement
  de schéma).
- **`/stac`/`/dcat` restent des sous-chemins de `/v1`** (`/v1/stac`,
  `/v1/dcat`) plutôt que hors versionnement — décision simplificatrice
  assumée : STAC/DCAT ont leur propre versionnement de protocole
  (conformance classes STAC, ex. `stac_version` dans le document racine)
  indépendant du chemin HTTP qui les sert ; les faire cohabiter sous `/v1`
  ne viole aucune norme externe, juste une préférence de certains
  déploiements STAC de les servir à la racine — non retenue ici pour garder
  une seule règle simple (« tout ce qui est `include_router` passe sous
  `/v1` ») plutôt que des exceptions par domaine.

## 3. Volet 5.4 — ADR (Architecture Decision Records)

### 3.1 Format retenu

Format léger façon MADR (Markdown Architecture Decision Records), un
fichier par décision : `docs/adr/NNNN-titre-court.md`, sections
`## Contexte`, `## Décision`, `## Conséquences`, plus un en-tête
`Statut: acceptée|remplacée par ADR-xxxx` et une ligne `Source :` pointant
vers l'arbitrage `Axx` du document vision d'origine quand il en existe un
(traçabilité — ne pas dupliquer le tableau options/avantages/inconvénients,
juste le résumer et pointer vers la source complète).

`docs/adr/README.md` : index (tableau numéro/titre/statut), et le
processus : quand écrire un ADR (« toute décision qui contraint
durablement l'architecture et qu'on ne veut pas re-débattre — le
pendant, au niveau du code, des arbitrages `Axx` de la feuille de route
produit »), comment le proposer (PR normale, cf. `CONTRIBUTING.md`).

### 3.2 ADR rétroactifs à écrire (sourcés depuis les arbitrages déjà tranchés)

Sélection des décisions les plus fondamentales et les plus susceptibles
d'être re-débattues sans ce filet (pas les 35 arbitrages en entier — un
sous-ensemble représentatif, au jugement de l'exécutant, minimum couvrant) :

1. Moteur d'autorisation maison + `can()` unique (source : A1)
2. Groupes gérés par le cœur, pas par Keycloak (source : A2)
3. RLS PostGIS différée à SP-3, sur les données métier seulement (source : A3)
4. OGC API Features comme API d'écriture (source : A4)
5. procrastinate comme file de jobs (source : A5)
6. CEL comme langage d'expressions (source : A8)
7. Web Components (Lit) comme technique de SDK (source : A10)
8. Structure du dépôt / module `core/` (source : A14)
9. `tenant_id`+`audit_log` sur toute table dès la première migration
   (source : CLAUDE.md « Décisions figées », pas d'`Axx` dédié — noté
   comme tel dans l'ADR)
10. Client TS généré depuis l'OpenAPI du cœur (source : A11)
11. Sortie de GeoNode/Superset/Redis, jalon M1 (source : CLAUDE.md
    « Décisions figées »)

Onze ADR rétroactifs — un nombre suffisant pour amorcer l'index sans en
faire une transcription mécanique des 35 arbitrages (qui resteraient de
toute façon lisibles dans le document vision d'origine, cité en `Source :`
de chaque ADR).

### 3.3 Hors périmètre explicite

- **Pas de rétro-ADR pour les 35 arbitrages en entier** — les 24 restants ne
  sont pas dupliqués ; `docs/vision/2026-07-04-feuille-de-route-geostudio.md`
  §7-8 reste la référence complète, l'ADR n'en est qu'un sous-ensemble
  distillé pour les décisions les plus structurantes.
- **Pas d'outillage automatisé** (pas de générateur de numéro d'ADR, pas de
  lint qui vérifie le format) — un `README.md` qui explique le processus en
  prose suffit à ce stade (cohérent avec le reste du dépôt : pas
  d'outillage disproportionné pour un seul committer humain, même
  raisonnement que la décision « release manuelle et tag-driven » déjà
  actée dans `CONTRIBUTING.md`).

## 4. Volet 5.5 — guide de contribution externe

Cf. §1.1 : le gros du travail est déjà fait. Reste :

1. `.github/ISSUE_TEMPLATE/bug_report.md` et
   `.github/ISSUE_TEMPLATE/feature_request.md` — structurent ce que
   `CONTRIBUTING.md` §« Reporting a bug or proposing a feature » demande
   déjà en prose (repro/attendu/observé/environnement pour un bug ;
   problème/esquisse de solution pour une feature, avec le rappel de
   vérifier `docs/vision/...feuille-de-route...` d'abord).
2. `.github/PULL_REQUEST_TEMPLATE.md` — checklist reprenant les 5 étapes du
   process PR déjà décrites en prose dans `CONTRIBUTING.md` (branché sur
   `dev`, tests verts, lien vers spec/plan si applicable).
3. `SECURITY.md` — politique de signalement de vulnérabilité (contact,
   délai de réponse indicatif, périmètre couvert) ; absent aujourd'hui,
   distinct du "reporting a bug" déjà couvert (une vulnérabilité de
   sécurité ne doit pas être signalée par une issue publique). Lier depuis
   `README.md` (à côté de la ligne `CONTRIBUTING.md` déjà présente,
   `README.md:178`).

### 4.1 Hors périmètre explicite

- **Ne pas réécrire `CONTRIBUTING.md`** — il est déjà complet et à jour ; ce
  SP y ajoute au plus un lien vers les nouveaux gabarits/`SECURITY.md`, pas
  une réécriture.
- **Pas de bot de triage automatique** (labels auto, stale-bot) — hors
  périmètre, aucun signal que ce soit un besoin réel pour un dépôt à un
  seul committer humain aujourd'hui.

## 5. Risques et questions ouvertes

- **Le volume caché du volet 5.3 dépasse probablement l'estimation
  agrégée de GAP-14** (8-15j pour toute la vague). La vérification de ce
  document (§1.3-1.5) a trouvé un couplage (chemins bruts hors routage,
  13 fichiers `CORE_BASE_URL` à trier, 80+39 mocks de test) que le texte
  original de GAP-14 ne pouvait pas connaître sans lire le code — le
  budget réel de ce seul volet peut approcher 4-6j à lui seul (versus une
  lecture naïve du texte qui suggérerait un après-midi). Documenté ici
  plutôt que masqué : ne pas couper la Task 2 du plan (chemins bruts) ou
  la Task 6 (mocks de test) pour tenir un budget optimiste — c'est
  précisément la partie qui, non faite, romprait silencieusement le
  rate-limiting, le CORS appexport et le garde-fou lecture-seule en
  production.
- **`SECURITY.md` et un vrai canal de signalement** : ce SP écrit le
  fichier mais ne met en place aucun canal réel (pas d'email dédié, pas de
  GitHub Security Advisories activé — `secret_scanning`/
  `dependabot_security_updates` sont déjà désactivés sur ce dépôt d'après
  `CLAUDE.md`) — le contenu du fichier doit rester honnête sur ce point
  (ex. contact = l'email de contact déjà public du mainteneur, pas un
  processus qui n'existe pas).
- **13 fichiers `CORE_BASE_URL` (§1.4)** : cette spec ne tranche pas au cas
  par cas lesquels doivent recevoir `/v1` — c'est le travail de la Task 4
  du plan, avec vérification individuelle de chacun (piège CLAUDE.md n°3 :
  ne pas supposer, lire).
- **Ordre des trois volets** : indépendants entre eux (ADR et guide de
  contribution ne touchent aucun code) — traiter le volet 5.3 en dernier
  dans le plan pour ne pas bloquer la clôture du SP sur son risque le plus
  élevé si le temps manque (ADR/contribution peuvent être livrés
  isolément si 5.3 déborde et doit être scindé en un SP-57c, décision à
  prendre avec Tanguy si ce risque se matérialise, pas unilatéralement).

## 6. Ordre d'exécution recommandé

1. ADR (§3) — aucune dépendance, aucun risque de régression, rapide.
2. Guide de contribution (§4) — idem, plus rapide encore vu §1.1.
3. Contrat d'API `/v1/` (§2) — le plus long et le plus risqué, cf. §5 ;
   traité en dernier pour ne pas retarder la livraison des deux volets
   sans risque si son budget déborde.

## 7. Décomposition en tâches (indicatif, affiné en plan)

1. `docs/adr/` : template + `README.md` (processus) + 11 ADR rétroactifs.
2. `.github/ISSUE_TEMPLATE/` (2 gabarits) + `PULL_REQUEST_TEMPLATE.md` +
   `SECURITY.md` + lien depuis `README.md`.
3. Cœur : routeur `/v1` imbriqué sur les 31 routeurs existants + OpenAPI/
   types TS régénérés.
4. Cœur : mise à jour de tous les chemins bruts hors routage (`main.py`,
   `ratelimit/limiter.py`) + tri des 13 fichiers `CORE_BASE_URL` + tests de
   régression dédiés (rate-limit, CORS appexport, garde lecture-seule).
5. Infra : 3 labels Traefik (`docker-compose.yml`) + vérification manuelle
   contre une stack réelle (pas seulement `docker compose config`).
6. Shell : redéfinition unique de `coreUrl` dans `createBase()` + test de
   régression sur `isHostedCoreUrl`/tuiles.
7. Tests : migration mécanique des 80 occurrences E2E (28 fichiers) + audit
   des 39 fichiers Vitest référençant `core.test`.
8. Clôture : suite complète (core+shell+e2e), vérification manuelle Docker,
   mise à jour `CLAUDE.md`.
