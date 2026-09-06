# SP-48 — Bascule de la CSP en enforcing : design

## 0. Cadrage

Ce SP referme **GAP-72** (`docs/revue/2026-09-04-analyse-gaps.md`, ligne
226 ; coût annoncé 3-6 j-h) : la CSP du shell reste en
`Content-Security-Policy-Report-Only` depuis sa pose (SP-26/3.3), jamais
basculée en `Content-Security-Policy` (enforcing), à cause de **4 blocages
concrets documentés en commentaire** dans
`docker-compose.prod.yml:172-188` (numéros de ligne relus en session
2026-09-06 — le commentaire couvre exactement ces 17 lignes, avant la ligne
189 qui porte la valeur elle-même ; GAP-72 les cite `167-184`, léger
décalage sans conséquence, piège CLAUDE.md n°3 appliqué : vérifié contre le
fichier réel, pas contre le texte du gap). Recommandé comme suite logique
de SP-45 (`docs/superpowers/specs/2026-09-05-sp45-durcissement-securite-design.md`
§9) et par la feuille de route révisée
(`docs/vision/2026-09-04-feuille-de-route-revisee.md:77`), qui pose déjà
comme **prérequis produit** : « lever ou accepter formellement les 4
blocages […], en particulier la décision sur le sandboxing des widgets
d'extension tiers — pas un simple réglage technique » (même document,
ligne 77, et §4.2 ligne 173-177).

**Ce document ferme 3 des 4 blocages (1, 2, 4) par une conception
vérifiée contre le code réel, et documente le 4e (3, sandboxing des
extensions tierces) comme une décision produit non tranchée, avec 4 options
analysées et une recommandation — sans présupposer que le plan associé
peut la clore.** Le plan qui suit ce document doit pouvoir s'exécuter et
livrer une CSP enforcing utile même si Tanguy ne tranche jamais le
blocage 3 (l'installation reste alors avec `script-src 'self'`, un
sous-ensemble strictement plus restrictif — jamais plus permissif — que ce
qui existe aujourd'hui).

## 1. Constat vérifié : les 4 blocages, un par un

### 1.a — Le mécanisme actuel (un seul header statique)

`docker-compose.prod.yml:189` (label Traefik `customResponseHeaders` sur la
middleware `security-headers`) porte une **unique chaîne statique**,
partagée par tous les routeurs qui référencent
`security-headers@docker` dans leurs `middlewares=` : `core` (ligne 165),
`seo-static` (204), `seo-bots` (211), et **`shell`** (257 — vérifié : c'est
bien ce routeur qui sert le document HTML de la SPA, donc celui dont la CSP
protège effectivement contre l'XSS). Il n'existe **aucun mécanisme de
calcul dynamique** aujourd'hui — la valeur est fixée à la construction du
fichier compose, pas à chaque requête.

En parallèle, `shell/nginx.conf` porte sa **propre** valeur statique
(`Content-Security-Policy-Report-Only`, `connect-src 'self'`), servie par
le conteneur `shell` lui-même — un deuxième mécanisme, indépendant du
premier, qui peut diverger (blocage 4).

### 1.b — Blocage 1 : tuiles WMS/WMTS moissonnées + terrain raster-dem externe (`img-src`)

Deux sources d'hôtes externes distinctes, toutes deux **non captées par
aucune garde d'egress existante** parce qu'elles ne passent jamais par le
cœur — le navigateur les charge **directement** :

- **WMS/WMTS moissonnées** : `HarvestSource` (`core/app/harvest/models.py:15-33`)
  stocke `url` par tenant, créé via `POST /harvest/sources`
  (`core/app/harvest/routes.py:123-124`, `create_source`). C'est une table
  déjà peuplée, par utilisateur privilégié, à chaque source moissonnée —
  **un allowlist déjà en base**, au sens littéral.
- **Terrain raster-dem externe** : `MapTerrain.tilesUrl`
  (`core/app/configs/schemas.py:114-117`), un champ libre à l'intérieur du
  document `MapConfig` (`core/app/configs/schemas.py:120-124`, champ
  `terrain`). **Pas de table dédiée, pas de validation d'hôte à
  l'écriture** — vérifié : `core/app/configs/repository.py` (fonctions
  `create_config`/`update_config`, lignes 49/211) ne valide que le kind et
  la forme du document, jamais les hôtes qu'il référence. À distinguer du
  kind `"terrain3d"` (converti, servi en proxy authentifié par le cœur —
  `core/app/configs/terrain3d_validation.py`) : **ce n'est pas le même
  terrain**. `MapTerrain` (le champ `terrain` d'un `MapConfig` de carte
  normale) pointe toujours vers un service tiers, jamais vers le proxy du
  cœur.

### 1.c — Blocage 2 : tuilesets 3D externes (`connect-src`/`img-src`)

`MapLayer.tilesUrl`/`url` (`core/app/configs/schemas.py:90-111`), kind
`"tiles3d"` ou `"raster"`, même situation que le terrain : champ libre dans
le document `MapConfig`, aucune validation d'hôte à l'écriture. À
distinguer, comme le terrain, du kind `"tileset3d"` (uploadé, converti,
servi par le proxy authentifié `GET /tileset3d/{item_id}/{path}` —
`core/app/configs/tileset3d_validation.py`) : un `MapLayer` de kind
`"tiles3d"` référençant un **service Cesium ion / 3D Tiles tiers** (pas un
tileset uploadé sur cette instance) est le cas visé par ce blocage.

**Point de vérification à faire en tâche d'exécution, pas supposé ici** :
le type shell `LayerSource.service: "core" | "external" | "tileset3d"`
(`shell/src/api/types.ts:311`) suggère une distinction "interne vs externe"
côté éditeur, mais **cette distinction n'existe pas dans le schéma
persistant `MapLayer`** ct-dessus (pas de champ `service`). L'heuristique
proposée ci-dessous (§3.2) pour décider si une URL de couche est "externe"
doit être vérifiée contre de vrais documents `MapConfig` en base avant
d'être câblée — ne pas supposer que le type shell et le schéma cœur
coïncident.

### 1.d — Blocage 3 : `script-src 'self'` bloque les widgets d'extension tiers

`Extension.module_url` (`core/app/extensions/models.py:29`) est chargé côté
shell par un **vrai `import()` ES dynamique**, pas une balise `<script>`
statique : `shell/src/builder/extensions/moduleCache.ts:4-5`
(`import(/* @vite-ignore */ url)`), appelé depuis
`shell/src/builder/extensions/LazyWcHost.tsx:28` (`ensureModuleLoaded(manifest.moduleUrl)`).
Le cas d'un widget hébergé sur une **origine différente** de celle du
shell est un scénario **déjà testé** (pas hypothétique) :
`shell/e2e/external-widget.spec.ts:8`, `moduleUrl: "http://localhost:4174/widget.js"`
— une origine distincte de `http://localhost:4173` (base URL Playwright).
Cet E2E tourne contre `vite preview` (`shell/playwright.config.ts:9`), qui
**ne sert aucun header CSP** (ni nginx ni Traefik n'entrent en jeu) — donc
cette suite reste verte quelle que soit la décision de ce SP, mais elle
**prouve que l'origine tierce est une capacité réellement utilisée du SDK
(SP-8, jalon M5)**, pas un cas d'école.

Selon la spécification CSP (niveau 3, largement implémentée), `import()`
dynamique est gouverné par `script-src`/`script-src-elem` exactement comme
une balise `<script src>` — **vérifié contre la spécification, pas contre
la mémoire seule** (comportement documenté MDN/W3C CSP3, cohérent avec le
constat empirique que Chrome/Firefox bloquent un `import()` hors
`script-src` en mode enforcing). Une CSP enforcing avec `script-src 'self'`
inchangé **bloquerait donc, dans toute instance qui a réellement enregistré
une extension d'origine étrangère**, le chargement de cette extension —
sans casser aucune extension hébergée sur la même origine que le shell
(par ex. servie sous `/extensions/*` du même domaine).

### 1.e — Blocage 4 : incohérence `nginx.conf` / overlay prod

`shell/nginx.conf:14` porte son propre commentaire, écrit à la pose de la
CSP (SP-26/3.3) : « `connect-src 'self'` est FAUX pour le compose de base
(hors overlay prod), où shell/core sont deux origines distinctes ». Vérifié
en session :

- **Fichier de base (`docker-compose.yml`)** : le service `shell`
  (ligne 741) a pour défaut `VITE_CORE_URL: ${VITE_CORE_URL:-http://localhost:8200}`
  — un port direct, **distinct** du port `8300` de `shell` — donc, dans le
  flux d'accès par défaut documenté par `CLAUDE.md` (`docker compose up -d`
  puis accès direct aux ports publiés), shell et core **sont bien deux
  origines distinctes**. `connect-src 'self'` y bloquerait tout appel du
  shell vers le cœur si la valeur de `nginx.conf` devenait un jour
  enforcing.
- **Le fichier de base a pourtant AUSSI un Traefik complet** (lignes
  372-410 pour `core`, 775-780 pour `shell`), routant les deux sous un même
  `${DOMAIN}` avec `core` en `PathPrefix(/api)` — **exactement le même
  schéma que l'overlay prod**. Mais la middleware `security-headers` du
  fichier de base (lignes 380-383) **ne porte aucune valeur de CSP du
  tout** — seulement HSTS/nosniff/frameDeny/referrerPolicy. Seul l'overlay
  prod (`docker-compose.prod.yml:189`) ajoute la ligne CSP.
- **Conséquence** : dans la topologie « base seul, via Traefik/`${DOMAIN}`
  », le shell/core sont same-origin (comme en prod) mais aucun Traefik n'y
  affirme de CSP — c'est `nginx.conf` (Report-Only, jamais enforcing dans
  ce SP) qui sert de seul filet, avec une valeur `'self'` qui *serait*
  correcte dans ce sous-cas précis. Dans la topologie « base seul, via les
  ports publiés directement » (le flux par défaut du dépôt), shell/core
  sont cross-origin et **la même valeur `'self'` de `nginx.conf` est
  fausse**. Une seule valeur statique ne peut pas être juste dans les deux
  cas à la fois.

**Deux mécanismes indépendants, capables de diverger silencieusement,
avec une valeur reconnue fausse dans un sous-cas documenté** : c'est la
définition même de l'incohérence signalée par GAP-72.

## 2. Décision d'architecture pour les blocages 1, 2 et 4 : allowlist calculée, poussée à Traefik par provider fichier

### 2.1 Pourquoi pas une valeur statique élargie (`img-src https:`)

Une option plus simple existe : élargir statiquement `img-src`/`connect-src`
à tout schéma `https:` (n'importe quel hôte), acceptant une perte de
précision sur ces deux directives au profit de la simplicité. **Rejetée** :
GAP-72 qualifie explicitement les 4 blocages d'hôtes « arbitraires », mais
2 des 3 catégories (WMS/WMTS moissonnées, extensions) sont en réalité
**déjà énumérables en base** (`HarvestSource.url`, `Extension.module_url`)
— renoncer à cette précision reviendrait à ouvrir `img-src`/`connect-src` à
n'importe quel hôte HTTPS de la planète alors qu'une allowlist réelle,
dérivée des données déjà écrites par les utilisateurs privilégiés de
l'instance, est atteignable pour un coût raisonnable. Seuls le terrain
(`MapTerrain.tilesUrl`) et les couches `tiles3d`/`raster` externes
(`MapLayer.tilesUrl`/`url`) n'ont pas de table dédiée — mais ils vivent
dans le document `MapConfig` déjà stocké, donc restent également
énumérables par une requête sur `configs.body_json`, pas par un hôte
véritablement inconnu de l'instance.

### 2.2 Conception retenue

**Nouveau module `core/app/security/`** (pure lecture, aucune nouvelle
table, aucune migration Alembic) :

- `core/app/security/csp_hosts.py` — fonctions pures d'extraction d'hôte
  (à partir d'une URL déjà validée par Pydantic comme `str`, jamais d'appel
  réseau) :
  - `extract_harvest_hosts(sources: Sequence[HarvestSource]) -> set[str]`
    — origine (schéma+hôte+port) de chaque `HarvestSource.url` dont
    `type` est `"wms"` ou `"wmts"` (les autres types de moissonnage —
    ArcGIS FS, CSW, CKAN — sont consommés côté serveur par le worker, avec
    sa propre garde d'egress `app.harvest.egress` ; ils ne posent pas de
    problème de CSP puisque le navigateur ne les contacte jamais
    directement — **à vérifier en tâche d'exécution contre
    `core/app/harvest/schemas.py`/le code des connecteurs**, ne pas
    supposer que la liste des types est figée par ce document).
  - `extract_config_external_hosts(body: dict) -> set[str]` — parcourt un
    `MapConfig.terrain.tilesUrl` et chaque `MapConfig.layers[].tilesUrl`/
    `.url` de kind `"raster"`/`"tiles3d"`, retourne l'origine de chaque URL
    **absolue** (schéma `http`/`https`) — une URL relative ou vide est
    ignorée (déjà same-origin par construction). Documenter et falsifier
    l'heuristique retenue pour ignorer les couches internes (`kind ==
    "tiles3d"` avec un `collectionId` renseigné, ou une URL qui commence
    par un chemin de proxy connu comme `/tileset3d/` ou `/terrain3d/`) —
    **contre de vrais documents en base**, cf. §1.c.
  - `extract_extension_hosts(extensions: Sequence[Extension]) -> set[str]`
    — origine de chaque `Extension.module_url`. Calculée dans tous les cas
    (utile dès que le blocage 3 sera tranché, cf. §4), mais **non branchée
    dans la valeur enforcée de `script-src`** tant que la décision n'est
    pas prise (§4, tâche dédiée avec test de garde).
- `core/app/security/service.py` — `compute_csp_allowlist(session: Session) -> CspAllowlist`
  (dataclass `img_hosts: set[str]`, `connect_hosts: set[str]`,
  `script_hosts: set[str]`), orchestre les requêtes DB (`HarvestSource`
  toutes tenants confondus — la CSP protège **un domaine public par
  installation**, `GEOSTUDIO_PUBLIC_HOST`, pas par tenant ; il n'existe
  qu'une seule origine à protéger, donc un seul jeu de directives, agrégé
  sur l'instance entière — décision explicite, à documenter en commentaire
  dans le code) + tous les `Config` de `kind == "map"`, dont on relit la
  **dernière révision** (`ConfigRevision.data`, la colonne JSON qui porte
  le document — vérifié contre `core/app/configs/models.py:15-35` :
  `Config` ne porte pas le document lui-même, seulement `current_version`
  ; `core/app/configs/repository.py:41-45` (`_latest_revision`) montre le
  patron de requête à réutiliser : `ConfigRevision` filtré sur
  `config_id`, trié par `version.desc()`, premier résultat) via
  `extract_config_external_hosts` + tous les `Extension` via
  `extract_extension_hosts`.

**Contrat de couches** (`core/pyproject.toml`, `[[tool.importlinter.contracts]]`,
liste `layers`) : `app.security` a besoin d'importer les modèles de
`app.harvest`, `app.configs`, `app.extensions` — trois modules situés à des
hauteurs différentes du contrat actuel. **Même problème structurel que
`app.compliance`** (déjà résolu dans ce contrat, commentaire lignes
205-216 : « purge_tenant doit pouvoir importer les modèles/repositories de
presque tout le reste de l'application… aucune place plus basse ne
permettrait ces imports sans dizaines d'exemptions »). Solution retenue :
placer `"app.security"` **juste après `"app.compliance"`**, avant
`"app.harvest"`, dans la liste `layers` — consommé uniquement par
`app.main` (montage éventuel d'une route de debug, cf. §2.4) et par le
processus `worker` (tâche périodique, §2.3), jamais par `app.mcp` (même
restriction qu'`app.compliance`, à vérifier explicitement par grep en
clôture de plan plutôt que supposée).

### 2.3 Calcul périodique, pas synchrone à chaque écriture

**Rejeté** : recalculer l'allowlist à chaque écriture d'un `HarvestSource`
(`POST`/`PATCH /harvest/sources`), d'un `Extension`
(`POST`/`PATCH /extensions`) et d'un `Config` de kind `"map"` (`POST`/
`PUT`/`PATCH` via `app.configs.routes`) — **trois points d'écriture
distincts**, dans trois modules différents, à instrumenter et à ne jamais
oublier d'étendre si un 4e point d'écriture apparaît un jour (classe de
bug CLAUDE.md n°4/n°5 : chemin oublié). Une tâche périodique unique, qui
relit l'état complet de la base à intervalle fixe, ne peut par construction
jamais "oublier" un point d'écriture — elle n'en dépend d'aucun.

**Retenu** : nouvelle tâche procrastinate périodique,
`core/app/security/jobs.py::refresh_csp_dynamic_conf_task`, **même patron
que les 6 tâches `@app.periodic` déjà existantes** (`core/app/harvest/jobs.py:41`,
`core/app/alerts/jobs.py:435`, `core/app/reports/jobs.py:449`,
`core/app/appexport/jobs.py:169`, `core/app/cdc/jobs.py:19`,
`core/app/ingestion/tasks.py:159` — toutes `cron="*/5 * * * *"` sauf
`cdc`/`harvest` à 10/15 min). Cadence retenue : `*/5 * * * *`, cohérente
avec la majorité des tâches existantes plutôt qu'une nouvelle valeur.
Exécutée par le processus `worker` (même processus que toutes les tâches
`@app.periodic` existantes, confirmé par grep — jamais par `core`
directement).

**Risque résiduel assumé et documenté** : jusqu'à 5 minutes de délai de
propagation entre l'ajout d'un nouvel hôte externe (nouvelle source
moissonnée, nouveau terrain, nouvelle couche 3D externe) et sa prise en
compte dans la CSP enforcée — pendant cette fenêtre, la nouvelle carte/le
nouveau terrain ne charge pas (bloqué par la CSP), pas une faille de
sécurité (sens conservateur de l'échec : on bloque par défaut, on
n'autorise jamais par erreur). Comparable à la fenêtre de 45 s du sondage
`NotificationBell` (SP-39) ou aux cycles `*/5 * * * *` déjà acceptés
ailleurs — cohérent avec la tolérance déjà pratiquée dans ce dépôt pour ce
type de fraîcheur, pas une régression inventée pour ce SP.

### 2.4 Traefik : provider fichier dynamique, additif au provider Docker

Le mécanisme actuel (labels Docker, lus une fois au démarrage du
conteneur) ne peut pas être recalculé sans redémarrer `traefik`. Traefik
(image `traefik:v3.0.4`, confirmée dans `docker-compose.yml`) supporte
plusieurs providers simultanément, dont un **provider fichier** capable de
recharger sa configuration à chaud (`--providers.file.watch=true`) sans
redémarrer le conteneur — **capacité à reconfirmer contre l'image réelle
en tâche d'exécution (piège CLAUDE.md n°3)**, ce document ne fait
qu'affirmer un comportement documenté par Traefik, jamais vérifié
empiriquement dans cette session (aucun conteneur Traefik n'a tourné
pendant la rédaction de cette spec).

Conception :

- Nouveau volume nommé `csp-dynamic-conf` (déclaré au niveau `volumes:` du
  fichier de base, aux côtés de `pg-data`/`minio-data`/`keycloak-data`),
  monté :
  - dans `worker` (écrivain), à un chemin fixe convenu — pas de nouvelle
    variable d'environnement, juste une constante de chemin partagée entre
    la tâche périodique et la commande Traefik, par cohérence avec le
    reste du dépôt où les chemins de volumes nommés ne sont pas
    paramétrés par env (`pg-data:/var/lib/postgresql/data` etc.) ;
  - dans `traefik` (lecteur), au même chemin.
- `traefik: command:` (fichier de base **et** overlay prod — les deux
  déclarent leur propre bloc `command:`, vérifié ligne 787 base / 262 prod)
  gagne deux entrées : `--providers.file.directory=<chemin>` et
  `--providers.file.watch=true`, en plus de `--providers.docker=true`
  déjà présent.
- La tâche périodique (`refresh_csp_dynamic_conf_task`) écrit un fichier
  de configuration dynamique Traefik dans ce volume, définissant **une
  middleware distincte** (`csp-dynamic`, provider `@file`) qui porte
  `customResponseHeaders` avec un seul en-tête, dont le **nom** dépend
  d'un nouvel env `CORE_CSP_MODE` (`enforce` par défaut après ce SP,
  `report-only` pour un rollback opérateur sans nouveau déploiement
  d'image — même esprit que `CORE_AUTH_MODE`) :
  - `enforce` → en-tête `Content-Security-Policy`.
  - `report-only` → en-tête `Content-Security-Policy-Report-Only`.
- Chaque routeur qui référence aujourd'hui `security-headers@docker` dans
  ses `middlewares=` (`core`, `shell`, `seo-static`, `seo-bots`, dans les
  deux fichiers ; `martin`, `titiler`, `grafana` dans le fichier de base
  — présents mais **sans** `security-headers` aujourd'hui pour certains,
  à vérifier ligne par ligne en tâche d'exécution plutôt que supposé ici)
  gagne `csp-dynamic@file` en plus, **sans retirer** `security-headers@docker`
  (qui garde HSTS/nosniff/frameDeny/referrerPolicy — inchangés, aucune
  raison de les rendre dynamiques).
- La ligne statique `customResponseHeaders.Content-Security-Policy-Report-Only=…`
  de `docker-compose.prod.yml:189` est **retirée** (remplacée par le
  mécanisme dynamique ci-dessus).

**Choix de format sans nouvelle dépendance de production** : `pyyaml` est
aujourd'hui un dépendance de **développement uniquement**
(`core/pyproject.toml`, `[dependency-groups]`, ligne 90 — absent de
`[project.dependencies]`, vérifié). Plutôt que de faire glisser `pyyaml`
vers les dépendances de production pour un unique fichier à écrire, la
tâche périodique **génère le YAML par gabarit de chaîne** (le contenu est
entièrement composé d'un nom de middleware fixe et d'une valeur de CSP
dont les seuls éléments variables sont des noms d'hôte issus d'`urlparse`
— qui ne peuvent contenir ni guillemet ni retour à la ligne, donc aucun
risque d'échappement YAML mal formé). Un test dédié (§ plan, Task 3)
vérifie que la sortie **parse** avec `yaml.safe_load` (import réservé aux
tests, cohérent avec l'usage déjà fait de `pyyaml` dans
`core/tests/test_deployability.py`) — la production n'a jamais besoin
d'analyser sa propre sortie, seulement de l'écrire.

## 3. Fermeture du blocage 4 : Traefik devient la seule source de CSP

**Retenu** : retirer entièrement le bloc `Content-Security-Policy-Report-Only`
de `shell/nginx.conf` plutôt que de le maintenir synchronisé indéfiniment
avec la valeur Traefik — élimine la duplication (donc la classe de bug
« deux sources qui peuvent diverger ») au lieu de la corriger une fois de
plus. Confirmé sans risque : `traefik` fait partie des **11 services par
défaut** du dépôt (`CLAUDE.md`, §Commandes) — il n'existe aucune topologie
de déploiement documentée dans ce dépôt où `shell` sert sans `traefik` en
face.

Pour que le fichier de **base** (sans overlay prod) ne perde pas son filet
Report-Only existant, la middleware `security-headers` du fichier de base
gagne, elle aussi, `csp-dynamic@file` dans les `middlewares=` de ses
routeurs (§2.4 couvre déjà les deux fichiers) — avec `CORE_CSP_MODE`
valant `report-only` par défaut dans le fichier de **base** (jamais
enforcing par défaut hors overlay prod — cohérent avec le fait que GAP-72
et son commentaire d'origine ne visent que `docker-compose.prod.yml`) et
`enforce` par défaut dans l'overlay prod.

**Limite résiduelle documentée, pas corrigée par ce SP** : un opérateur qui
accède à `shell`/`core` par leurs ports publiés directement (le flux de
développement par défaut, `http://localhost:8300`/`:8200`, en dehors de
tout Traefik) ne voit **aucune** CSP du tout après ce SP (au lieu d'une
valeur Report-Only fausse aujourd'hui). Jugé acceptable : ce flux n'a
jamais été un flux de production documenté, et une absence de CSP dans un
contexte de développement local est moins trompeuse qu'une CSP présente
mais incorrecte.

## 4. Blocage 3 — options de sandboxing des widgets d'extension, non tranchées

**Ce SP ne tranche pas cette décision.** Il documente 4 options réelles,
évaluées contre le mécanisme de chargement effectif
(`import(/* @vite-ignore */ url)`, §1.d), avec une recommandation
argumentée — à valider explicitement par Tanguy avant toute tâche de
câblage. Le plan associé calcule déjà `script_hosts` (§2.2) mais ne
l'enforce jamais sur `script-src`, quelle que soit l'option retenue plus
tard (§ plan, Task 6, avec test de garde qui échoue si quelqu'un câble
silencieusement `script-src` sur `script_hosts` sans passer par une
décision explicite).

### Option A — Allowlist d'origine déclarée par extension (`Extension.module_url`)

**Constat qui change le calcul de coût** : cette option n'est *pas*
hypothétique à construire — son ingrédient technique (l'origine de chaque
extension, déjà déclarée et stockée) **existe déjà** dans
`Extension.module_url` (`core/app/extensions/models.py:29`), gated par
`Privilege.ADMIN_EXTENSIONS_MANAGE` à l'écriture
(`core/app/extensions/routes.py:38`). Le même mécanisme d'allowlist
dynamique construit pour les blocages 1/2 (§2) s'étend à `script-src` sans
nouvelle infrastructure — seul `extract_extension_hosts` (déjà écrit,
§2.2) doit être branché sur la directive enforcée.

Coût marginal : quasi nul une fois §2 livré. **Limite de sécurité** :
protège contre un hôte non déclaré (une extension compromise servie
*depuis* un autre domaine que celui déclaré à l'enregistrement), mais
**ne protège pas** contre un fichier malveillant remplacé *sur l'origine
déclarée elle-même* après coup — c'est une confiance à la granularité de
l'hôte, pas du contenu. Cohérent avec le niveau de confiance déjà accordé
implicitement à `Extension.module_url` aujourd'hui (n'importe quel
`ADMIN_EXTENSIONS_MANAGE` peut déjà pointer vers n'importe quel JS
exécuté avec les mêmes droits DOM que le shell — cette option ne *réduit*
aucune confiance existante, elle empêche seulement qu'un attaquant
extérieur au cercle des administrateurs de l'instance ajoute une origine
non voulue via une autre voie qu'`ADMIN_EXTENSIONS_MANAGE`).

### Option B — Nonce par requête (`'nonce-x' 'strict-dynamic'`)

Le mécanisme standard le plus robuste : un script racine porteur du bon
nonce peut charger, via `import()`, du code de **n'importe quelle
origine**, sans maintenir d'allowlist. Mais un nonce doit être **unique
par réponse HTTP** — incompatible par construction avec une valeur
statique posée par un label Traefik (labels Docker, lus une fois au
démarrage) et avec le service actuel de `index.html` en fichier statique
par nginx (`COPY --from=build /app/dist /usr/share/nginx/html`, aucune
génération par requête). Câbler cette option demanderait de faire sortir
la génération du document HTML de nginx-statique vers un processus qui
tourne par requête (nginx + module `njs`/Lua générant un nonce et
substituant à la fois le header et l'attribut `nonce` du script racine
dans le HTML, ou un petit service applicatif remplaçant nginx pour ce
document précis) — un changement d'architecture de service à part
entière, bien au-delà du budget 3-6 j-h de ce seul blocage.

### Option C — Hash du contenu du script

Bloqué par la nature même du chargement dynamique : un hash CSP
(`script-src 'sha256-…'`) épingle un contenu de fichier exact. Une
extension tierce mise à jour indépendamment de cette instance (le cas
d'usage explicite du SDK Web Components + registre d'extensions, jalon M5)
casserait son chargement à chaque changement de version, sans aucun moyen
pour l'instance de le détecter à l'avance. Contradictoire avec l'objectif
même du chargement dynamique ES documenté par `CLAUDE.md`
(« SDK public : Web Components (Lit) + pont React interne […] pas
d'ouverture aux tiers avant ça » — mais SP-8 a déjà livré le chargement
dynamique lui-même, jalon M5 atteint).

### Option D — Renoncer : bundlage statique obligatoire par extension

La plus sûre architecturalement (`script-src 'self'` reste vrai, sans
exception, pour toujours) mais **revient sur une capacité déjà livrée et
jalonnée** (SP-8, M5 « SDK ouvrable ») : chaque extension deviendrait un
module compilé dans le build du shell, perdant l'installation/mise à jour
sans rebuild qui est la raison d'être du registre `Extension`
(`core/app/extensions/`) et de la page `AdminExtensionsPage`. Un vrai
recul produit, pas un simple réglage — à ne considérer que si Tanguy juge
que la surface d'attaque d'Option A est inacceptable.

### Recommandation (non contraignante pour l'exécution)

**Option A**, pour son coût marginal quasi nul une fois l'infrastructure
du §2 livrée, et parce qu'elle ne fait que formaliser en CSP une confiance
déjà accordée en pratique (n'importe quel administrateur peut déjà
enregistrer n'importe quel JS arbitraire via `POST /extensions`). Options
B et C sont techniquement plus fortes mais respectivement hors budget
(B, changement d'architecture de service) et incompatibles avec l'usage
réel du SDK (C). Option D est un choix produit valide mais régressif, à
réserver à un futur re-arbitrage explicite de SP-8 plutôt qu'à ce SP.
**Cette recommandation reste soumise à l'accord explicite de Tanguy avant
toute tâche de câblage — jamais tranchée par une session d'exécution sur
son seul jugement.**

## 5. Critères d'acceptation

- Blocages 1, 2, 4 fermés : `img-src`/`connect-src` en production
  reflètent l'union de `HarvestSource.url` (wms/wmts), des hôtes externes
  de `MapConfig.terrain`/`MapConfig.layers[]` (kind raster/tiles3d), sans
  regression sur les couches internes (`collectionId` renseigné, kinds
  `tileset3d`/`terrain3d` convertis) ; `shell/nginx.conf` ne porte plus de
  CSP propre ; Traefik (base **et** prod) porte une CSP calculée via le
  provider fichier, avec `CORE_CSP_MODE` par défaut `report-only` (base)
  et `enforce` (prod).
- Blocage 3 documenté, non fermé : `script_hosts` calculé mais jamais
  câblé sur `script-src`, avec un test de garde qui échoue si quelqu'un le
  branche sans lever ce document.
- `cd core && uv run pytest` reste vert. `uv run lint-imports` vert avec
  la nouvelle entrée `app.security`. `uv run ruff check .`/`ruff format
  --check .`/`mypy --strict …` (périmètre inchangé, `app.security` n'y
  figure pas explicitement à moins d'y être ajouté — à trancher en tâche
  d'exécution si le module grossit).
- `docker compose -f docker-compose.yml -f docker-compose.prod.yml config`
  résout sans erreur avec un `.env`/`.env.prod` minimal, et le service
  `traefik` référence bien `csp-dynamic@file` sur chaque routeur attendu.
- Diff OpenAPI/types TS **vide attendu** : aucune route, aucun modèle de
  requête/réponse ne change — à vérifier explicitement (piège CLAUDE.md
  n°1), le calcul de l'allowlist ne s'expose sur aucune route publique
  dans ce périmètre.
- La bascule Traefik réelle (comportement du provider fichier, rechargement
  à chaud) est **vérifiée empiriquement contre l'image `traefik:v3.0.4`
  qui tourne**, jamais supposée depuis la documentation ou la mémoire
  (piège CLAUDE.md n°3) — condition de clôture de la tâche dédiée du plan,
  pas de ce document.

## 6. Hors périmètre explicite

- Toute décision définitive sur le blocage 3 (§4) — reste une question
  ouverte remontée à Tanguy, pas tranchée ici.
- GAP-73 (quotas par tenant), GAP-74 (purge RGPD), GAP-75 (rotation de
  secrets) — sans lien avec la CSP, non traités.
- Un mécanisme de recalcul synchrone à l'écriture (rejeté §2.3) — si un
  jour la fenêtre de 5 minutes s'avère inacceptable en usage réel, une
  tâche de suivi séparée pourra l'introduire en plus (pas à la place) du
  calcul périodique, jamais en le remplaçant seul (fragilité déjà motivée
  §2.3).
- Reporting/alerting sur les violations CSP (`report-uri`/`report-to`) —
  absent du périmètre actuel (Report-Only aujourd'hui n'a jamais eu de
  collecteur de rapports non plus, aucune régression introduite).
