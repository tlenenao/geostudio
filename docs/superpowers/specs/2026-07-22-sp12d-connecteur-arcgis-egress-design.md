# SP-12d — Connecteur ArcGIS Feature Services + durcissement egress SSRF — design

**Date.** 2026-07-22
**Phase.** SP-12d, quatrième sous-phase de SP-12 « Catalogue interopérable :
STAC, DCAT, moissonnage » — suit SP-12a (API STAC native, clos), SP-12b (export
DCAT-AP, clos) et SP-12c (moteur de moissonnage + connecteur STAC externe, clos).
Deuxième brique du volet **consommation** : SP-12c a posé le moteur générique et
lit un premier standard (STAC) ; SP-12d branche le **2ᵉ connecteur** et livre le
**durcissement réseau** (allowlist/blocage d'egress) que SP-12c a explicitement
différé à cette sous-phase.
**Références.** Feuille de route §SP-12 (« Connecteurs ») et arbitrage **A22**
(les 5 connecteurs, ordre `STAC → **ArcGIS FS** → GetCapabilities → CSW/ISO →
CKAN` — chacun livrable séparément ; l'amendement 2026-07-09 insère ArcGIS FS en
2ᵉ position : « la donnée existante des collectivités équipées Esri, le pont de
sortie ») et **A23** (référencement pur par défaut, copie opt-in par source).
Spec SP-12c (`2026-07-19-sp12c-moissonnage-stac-design.md`) §5 et §11 : « SSRF —
risque réel documenté … allowlist d'egress différée à SP-12d, signalée en suivi ».
CLAUDE.md, entrée SP-12c, « Suivis post-merge signalés, non implémentés ».

## 1. Objectif & périmètre

**Objectif.** Un admin déclare une source de moissonnage de type `arcgis` pointant
un **ArcGIS Feature Service** distant ; le cœur la moissonne via le moteur SP-12c
et **référence chaque couche** du service comme un item de catalogue « externe »
(cherchable, lien dé-référençable, fraîcheur, re-moissonnage sans doublon). Par
source, l'admin peut opter pour la **copie** (A23) qui récupère les entités
GeoJSON paginées de la couche distante et les route dans le pipeline d'ingestion
SP-6 → collection PostGIS locale. En parallèle, le worker qui émet des requêtes
HTTP vers une URL admin-fournie est protégé par une **garde d'egress** (blocage
des cibles réseau interne), partagée par **tous** les connecteurs réseau (STAC
inclus) et la récupération copie.

**Dans le périmètre.**
- **Connecteur ArcGIS FS** (② de A22) : `ArcgisConnector` (`type="arcgis"`,
  `supports_copy=True`), enregistré dans le registre existant. **Une couche =
  un jeu de données** (§2.1). Réutilise strictement l'abstraction
  `HarvestConnector` et le moteur `service.harvest_source` de SP-12c — zéro
  nouveau chemin de moissonnage, zéro nouvelle route.
- **Mode copy ArcGIS = GeoJSON paginé complet** → `run_import` (SP-6), avec
  gestion de la pagination ArcGIS (`resultOffset`/`resultRecordCount`/
  `exceededTransferLimit`) jusqu'à un plafond borné (§2.2).
- **Durcissement egress SSRF** (§3) : denylist des plages IP privées/loopback/
  link-local + allowlist optionnelle par env, appliqué au client HTTP **par
  défaut** de tous les connecteurs et de la récupération copie. Rétrofit sur le
  connecteur STAC de SP-12c (même garde).
- **Trois suivis SP-12c repliés** (§4) : cap global de documents fetchés côté
  STAC, sweep périodique qui saute les sources déjà `running` (avec reclaim par
  âge), masquage des boutons d'écriture de `/admin/harvest` en mode démo.
- **Surface shell minimale** : sélecteur de type de source (`stac`/`arcgis`)
  dans les dialogues créer/éditer, masquage démo, ≥1 spec E2E `harvest-arcgis`.

**Hors périmètre (sous-phases ultérieures / autres SP).**
- **SP-12e…g** : les 3 connecteurs restants (GetCapabilities WMS/WFS, CSW/ISO
  19139, CKAN). L'abstraction `HarvestConnector` les accueille, aucun n'est écrit
  ici.
- **Authentification vers l'ArcGIS distant** : v0 = **services publics seulement**
  (open data des collectivités, ArcGIS Hub public — cible directe d'A22). Aucun
  token/API-key/OAuth vers le distant ; différé en suivi (§8).
- **DNS-rebinding par pinning-IP** : la garde d'egress résout et valide le host
  avant la requête ; le pinning strict (connexion forcée à l'IP validée) est
  différé et signalé comme résiduel (§3, §8).
- **Miroir des octets d'assets** (rasters/tuiles référencés par une couche) :
  la copie ArcGIS copie l'index interrogeable (entités GeoJSON), pas des octets
  d'assets externes — cohérent avec la lecture d'A23 déjà actée en SP-12c.
- **Re-export** : un item moissonné (mode reference) n'est jamais re-exposé par
  notre STAC/DCAT (invariant SP-12c §2.6, inchangé).

## 2. Connecteur ArcGIS FS

### 2.1 Granularité : une couche = un jeu de données

Un Feature Service ArcGIS expose plusieurs **couches** (`{service}/FeatureServer/0`,
`/1`, …), chacune avec son propre schéma, sa géométrie et son emprise — exactement
le grain d'une `Collection` du cœur (« une couche = une collection », déjà le
modèle d'ingestion SP-6/SP-3). Le moissonnage se fait donc à la granularité
**couche** (symétrique à STAC Collection → item de SP-12c) : chaque couche du
service distant devient **un** `HarvestedRecord`, donc un item externe (reference)
ou une collection (copy). Le service entier n'est jamais un seul item agrégé — ce
serait mal typé (schémas hétérogènes, mode copy impossible).

`ArcgisConnector.fetch(url)` (contrat `HarvestConnector`, **HTTP seul, zéro I/O
DB**, tolérant §2.4) :
1. GET `{url}?f=json` → métadonnées du service (`layers: [{id, name, ...}]`,
   éventuel `documentInfo.Keywords`). L'URL fournie par l'admin est l'URL du
   FeatureServer (sans `?f=json`, ajouté par le connecteur).
2. Pour chaque entrée de `layers` (bornée par `_MAX_LAYERS`) : GET
   `{url}/{layerId}?f=json` → métadonnées de la couche (`name`, `description`,
   `extent`, `geometryType`, `maxRecordCount`) ; construit un `HarvestedRecord`.
   Les `tables` (sans géométrie) sont ignorées en v0.

Mapping couche → `HarvestedRecord` (dataclass existante de SP-12c) :

| Champ record | Source ArcGIS | Repli tolérant |
|---|---|---|
| `external_id` | URL stable de la couche `{service}/{layerId}` (normalisée) | — (couche sans URL dérivable ignorée) |
| `title` | `layer.name` | `str(layerId)` |
| `abstract` | `layer.description` | `""` |
| `keywords` | `documentInfo.Keywords` du service (split), sinon `[]` | `[]` |
| `bbox` | `layer.extent` **reprojeté en WGS84** (§2.3) | bbox monde `[-180,-90,180,90]` |
| `external_url` | URL dé-référençable de la couche | URL du service |
| `items_url` | `{layerUrl}/query?where=1=1&outFields=*&f=geojson` (base, paginée en copie §2.2) | `None` (couche non copiable) |

**Bornes dures** (valeurs exactes fixées au plan) : `_MAX_LAYERS` (nombre de
couches par service), timeout HTTP par requête, `_MAX_DOCUMENTS` (nombre total de
requêtes HTTP d'un `fetch`, protège contre un service au nombre de couches
délirant). Un service distant malformé/hostile ne bloque jamais le worker.

### 2.2 Mode copy = GeoJSON paginé complet → `run_import`

La copie est « la plus naturelle » sur ArcGIS FS (argument A22). ArcGIS pagine la
sortie `query` : `resultOffset`/`resultRecordCount` (taille de page bornée par le
`maxRecordCount` de la couche) et signale le dépassement par `exceededTransferLimit`
(`true` tant qu'il reste des entités). Une seule requête tronquerait silencieusement
un gros service — inacceptable pour « le pont de sortie Esri ».

La pagination est **spécifique au connecteur**, pas au moteur. On étend
`HarvestConnector` d'une méthode de récupération copie :

```
def fetch_copy_geojson(self, record: HarvestedRecord, *, http_get) -> bytes | None
```

- `http_get` = le getter HTTP **gardé** (§3) injecté par le moteur — la pagination
  passe donc par la même garde d'egress.
- Retourne les bytes d'**une seule** `FeatureCollection` GeoJSON assemblée à partir
  de toutes les pages, ou `None` si la couche n'est pas copiable (`items_url is
  None`).
- `ArcgisConnector.fetch_copy_geojson` boucle `resultOffset += page` en
  concaténant `features[]` jusqu'à `exceededTransferLimit=false` **ou** le plafond
  `_MAX_COPY_FEATURES` atteint (au-delà : tronqué au plafond, journalisé — un
  service géant reste borné, documenté §8). Parsing tolérant : une page malformée
  arrête proprement la copie plutôt que de crasher.

Le moteur (`service.harvest_source`, mode `copy`) appelle
`connector.fetch_copy_geojson(rec, http_get=guarded_get)` puis route les bytes
assemblés dans `run_import(session, ..., filename="harvest.geojson",
content=<bytes>, collection_title=rec.title)` — **inchangé** depuis SP-6a/SP-12c.
Tout le I/O DB (upsert item/collection, audit, `run_import`) reste dans le moteur.

**Rétrofit STAC.** Le connecteur STAC de SP-12c est porté sur la même méthode :
`StacConnector.fetch_copy_geojson(record, http_get)` fait `http_get(items_url).
content if items_url else None` (une seule requête, comme aujourd'hui). Cela
**remplace le seam `items_fetcher(url) -> bytes`** de `service.harvest_source`
(SP-12c) par un unique `connector.fetch_copy_geojson(rec, http_get=...)` : le
comportement STAC est préservé (mêmes bytes, un seul appel), et le point
d'injection de test devient `http_get` (le getter gardé), homogène pour les deux
connecteurs. `_default_items_fetcher` disparaît au profit du getter gardé (§3).

**`supports_copy`.** ArcGIS `supports_copy=True` (comme STAC). La garde SP-12c —
refus à la création d'un `mode="copy"` sur un connecteur `supports_copy=False` —
reste en place pour les futurs connecteurs (GetCapabilities/CSW pourront être
`False`), même si aucun connecteur v0 ne la déclenche.

### 2.3 Reprojection de l'emprise en WGS84

Une `layer.extent` ArcGIS est exprimée dans le référentiel de la couche
(`spatialReference.latestWkid`/`wkid`), rarement 4326. Le `bbox` d'un
`HarvestedRecord` (et donc le `dcat:spatial`/STAC extent futur du catalogue) doit
être en WGS84. Le connecteur reprojette les coins de l'emprise via **pyproj**
(déjà dépendance depuis SP-6b) :
- `wkid` 4326 → passthrough.
- Autre `wkid` résoluble → `pyproj.Transformer` vers EPSG:4326.
- `wkid` absent/non résoluble/échec de transformation → **bbox monde** (repli
  tolérant §2.4), jamais d'exception qui fuite.

La reprojection d'une enveloppe (coins seuls) est une approximation de catalogue
suffisante — on ne reprojette pas la géométrie des entités ici (le mode copy passe
la géométrie **telle quelle** via `run_import`, dont la reprojection éventuelle
est le problème de SP-6, hors périmètre). *Note* : la reprojection **de la donnée
copiée** n'est pas dans ce périmètre — `run_import` ingère le GeoJSON tel que
renvoyé par ArcGIS (`f=geojson` renvoie du WGS84 par convention GeoJSON RFC 7946,
donc cohérent) ; seul le `bbox` du record est reprojeté par le connecteur.

### 2.4 Parsing tolérant, borné (identique à la philosophie STAC §2.7 SP-12c)

Ne jamais faire tomber tout un moissonnage sur une couche distante malformée.
Champs manquants → replis documentés (table §2.1). `layers` absent/non-liste → `[]`
(aucun record, source `ok` avec 0 item, pas d'erreur). Réponse non-JSON / non-objet
→ ignorée avec `logger.warning`, jamais d'exception qui fuite. Bornes dures §2.1
et §2.2 : un service cyclique/hostile/géant ne bloque pas le worker.

## 3. Durcissement egress SSRF (`core/app/harvest/egress.py`)

**Le risque.** Le worker émet des requêtes HTTP sortantes vers une URL fournie par
un admin (SSRF/confused-deputy contre le réseau interne : `http://169.254.169.254/`
métadonnées cloud, `http://localhost:…`, `http://10.x`…). SP-12c mitigeait par
admin-only + timeouts et **différait la garde d'egress à SP-12d**. Avec un 2ᵉ
connecteur réseau, c'est le moment.

**Politique : denylist des plages privées + allowlist optionnelle.**
- `assert_egress_allowed(url)` (lève `EgressBlockedError`) :
  1. Schéma ∈ `{http, https}` (sinon rejet).
  2. Résout le host (`socket.getaddrinfo`) → pour **chaque** IP résolue, rejet si
     `ipaddress` la classe loopback / private / link-local (169.254/16, fe80::/10)
     / reserved / multicast / unspecified (couvre 127/8, 10/8, 172.16/12,
     192.168/16, ::1, fc00::/7, etc.). Les **IP-littérales** dans l'URL sont
     vérifiées directement (pas de DNS nécessaire — couvre le cas SSRF le plus
     courant).
  3. Si `CORE_HARVEST_EGRESS_ALLOWLIST` (env, hosts séparés par virgule) est
     **défini et non vide**, le host doit y figurer (restriction supplémentaire,
     opt-in opérateur) ; s'il est absent, seule la denylist (2) s'applique — le
     moissonnage public « juste ça marche » sans configuration.

**Point d'enforcement : le client HTTP par défaut.** `build_guarded_client(timeout)
-> httpx.Client` construit un client dont le **transport** appelle
`assert_egress_allowed(request.url)` avant toute connexion (transport enveloppant
`httpx.HTTPTransport`). Les deux connecteurs construisent leur client par défaut
via cette factory, et la récupération copie utilise un getter `guarded_get`
adossé au même client. Conséquence propre sur les tests :
- **Production** : aucun client injecté → client gardé → garde active partout.
- **Tests unitaires connecteurs** : `httpx.MockTransport` injecté (seam `client=`
  existant de SP-12c) → la garde n'est pas dans le chemin → tests **offline
  rapides**, aucune résolution DNS.
- **`egress.py` a ses propres tests unitaires** (§6) : IP-littérales (127/
  169.254/10/::1/fc00 → bloquées ; IP publique → autorisée) sans DNS ; cas
  hostname via resolver monkeypatché ; allowlist restreignant un host public
  autrement autorisé.

**Résiduel documenté : DNS-rebinding TOCTOU.** La garde valide l'IP résolue **avant**
la requête ; httpx re-résout le host au connect, donc un attaquant contrôlant un
DNS à TTL 0 pourrait présenter une IP publique à la validation puis une IP interne
au connect. Le **pinning-IP** (forcer la connexion sur l'IP validée, avec SNI/Host
préservés) est différé (fragile avec TLS/vhosts) et **signalé** (§8), pas passé
sous silence. Les cibles SSRF à forte valeur (métadonnées cloud, localhost) sont
des IP-littérales ou résolvent stablement — couvertes en v0.

**Intégration moteur.** Quand `harvest_source` (SP-12c) attrape une exception de
fetch, un `EgressBlockedError` suit exactement le chemin existant : `source.
last_status = "error"`, `last_error` = message tronqué, **aucun item créé**, le
job ne retente pas de zombie. Aucune modification du contrat « ne lève jamais » du
moteur — la garde lève **dans** le connecteur/getter, capturée par le `try` déjà
en place.

## 4. Suivis SP-12c repliés

Trois suivis non bloquants signalés à la clôture de SP-12c, tous proches du travail
réseau/robustesse de cette sous-phase :

1. **Cap global de documents fetchés côté STAC.** `StacConnector._walk` borne déjà
   `_MAX_COLLECTIONS` et `_MAX_CATALOG_DEPTH` mais pas le **nombre total de
   requêtes HTTP** (un catalogue en éventail large sous le plafond de collections
   peut multiplier les requêtes). Ajout d'un `_MAX_DOCUMENTS` comptant chaque GET
   de `_walk` (via la taille de `seen_docs`), arrêt propre au plafond. Homogène
   avec le `_MAX_DOCUMENTS` d'ArcGIS (§2.1).
2. **Sweep périodique saute les sources déjà `running`.** `list_due_sources`
   (repository) exclut les sources `last_status="running"` pour éviter un
   double-moissonnage concurrent (gap 2-phase-commit : crash entre le passage à
   `running` et la fin de `harvest_source`). **Reclaim par âge** : une source
   `running` dont `last_run_at` est plus ancien qu'une fenêtre de sécurité (run
   présumé planté) **redevient éligible** — sinon un crash la coince en `running`
   à jamais et le sweep l'ignore définitivement. Le déclenchement manuel
   (`POST .../run`) reste toujours disponible.
3. **Masquage des boutons d'écriture de `/admin/harvest` en mode démo.**
   `HarvestSourcesAdminPage` consomme `useInstanceInfo()` (fail-open, jamais de
   faux positif `readOnly` sur panne réseau) et masque Créer/Éditer/Supprimer/
   « Moissonner maintenant » en mode read-only — même pattern que les autres pages
   admin durcies en SP-9 « démo lecture seule ». La frontière réelle reste le 403
   serveur (middleware ASGI + garde read-only du moteur).

## 5. Surface (endpoints, modules, shell)

### 5.1 Endpoints — aucun nouveau
Le moteur, la table et les routes `/harvest/*` de SP-12c sont réutilisés tels
quels. `POST /harvest/sources` accepte désormais `type="arcgis"` — **validé via le
registre de connecteurs** (`get_connector` lève `ValueError` sur type inconnu →
400, garde déjà en place SP-12c §4). `harvest_source.type` reste un `str` libre
(extensible, cf. futurs connecteurs) → **pas de dérive OpenAPI attendue** sur ce
champ ; régénération `core/openapi.json` + `core-schema.d.ts` seulement si un
schéma change réellement (le job `api-types-drift` doit rester vert).

### 5.2 Nouveau code cœur (dans `app.harvest`, pas de nouveau module de haut niveau)
- **`connectors/arcgis.py`** — `ArcgisConnector` (§2). HTTP via `httpx` (client
  gardé §3), reprojection via `pyproj` (dépendance existante).
- **`connectors/base.py`** — `HarvestConnector` gagne `fetch_copy_geojson(record,
  *, http_get) -> bytes | None` (§2.2). Rétrocompatible : STAC l'implémente aussi.
- **`connectors/stac.py`** — ajout de `fetch_copy_geojson` (§2.2), comportement
  inchangé ; ajout du `_MAX_DOCUMENTS` (§4.1).
- **`connectors/__init__.py`** — `_REGISTRY["arcgis"] = ArcgisConnector()`.
- **`egress.py`** (nouveau, dans `app.harvest`) — `assert_egress_allowed`,
  `EgressBlockedError`, `build_guarded_client`, `guarded_get` (§3).
- **`service.py`** — remplace le seam `items_fetcher` par `connector.
  fetch_copy_geojson(rec, http_get=guarded_get)` (§2.2) ; le mode copy passe par
  le client gardé.
- **`repository.py`** — `list_due_sources` exclut `running` avec reclaim par âge
  (§4.2).

**Frontière de modules (import-linter).** `app.harvest` est déjà placé au-dessus
de `app.ingestion` dans `layers` (SP-12c). ArcGIS/egress n'ajoutent aucun import
de module `app.*` nouveau (`httpx`/`pyproj`/`socket`/`ipaddress` sont des libs
tierces, hors contrat). Le contrat `layers` reste **inchangé** — à vérifier
`lint-imports` clean.

### 5.3 Shell (minimal)
- **Sélecteur de type** (`stac` | `arcgis`) dans les dialogues créer/éditer d'une
  source (`RegisterHarvestSourceDialog`/`EditHarvestSourceDialog` de SP-12c) —
  champ `<select>`, défaut `stac` (rétrocompatible).
- **Masquage démo** (§4.3) sur `HarvestSourcesAdminPage`.
- **Badge « Externe »** inchangé (déjà sur les items `resource_type==="external"`).
- **≥1 spec E2E** `harvest-arcgis.spec.ts` : Playwright route un FeatureServer
  mocké (`?f=json` service + `/0?f=json` couche + `/0/query?f=geojson`), l'admin
  crée une source `arcgis`, la moissonne, voit ≥1 item externe au catalogue avec
  badge « Externe » ; re-moissonnage → compte stable (magasin mocké keyé par
  `external_id`, assertion sans-doublon non tautologique, comme `harvest-stac`).
  Jamais d'appel réseau réel.

## 6. Tests & validation

- **Unitaires (always-run, offline).**
  - `ArcgisConnector.fetch` contre `httpx.MockTransport` : service à N couches →
    N records ; mapping champs (name/description/keywords) ; **reprojection bbox
    non-4326** (cas EPSG:2154 Lambert-93 → 4326, **échoue si on retire pyproj** —
    même discipline anti-régression que le test d'emprise STAC de SP-12a) ;
    tolérance (couche sans extent → bbox monde, `layers` absent → `[]`, réponse
    non-objet ignorée) ; bornes (`_MAX_LAYERS`, `_MAX_DOCUMENTS`).
  - `ArcgisConnector.fetch_copy_geojson` : pagination — page 1
    `exceededTransferLimit=true` puis page finale `false` → `FeatureCollection`
    assemblée contenant **toutes** les entités ; plafond `_MAX_COPY_FEATURES`
    tronque proprement ; `items_url is None` → `None`.
  - `egress` : `assert_egress_allowed` bloque 127.0.0.1, 169.254.169.254, 10.x,
    192.168.x, `::1`, `fc00::…` (IP-littérales, sans DNS) ; autorise une IP
    publique ; hostname résolu vers IP interne (resolver monkeypatché) → bloqué ;
    `CORE_HARVEST_EGRESS_ALLOWLIST` restreint un host public sinon autorisé ;
    schéma non-http → bloqué.
  - `StacConnector` : `fetch_copy_geojson` (parité — un seul GET) ; `_MAX_DOCUMENTS`
    borne le nombre de requêtes.
- **Intégration (marqueur `postgis`, contre Postgres réel).**
  - Moissonnage `arcgis` mode `reference` bout-en-bout (distant mocké par client
    injecté) → items externes créés ; re-moissonnage **sans doublon**, entité
    disparue → `is_stale` (réutilise l'infra SP-12c).
  - Moissonnage `arcgis` mode `copy` → `run_import` → **collection PostGIS locale**
    + item carte (réutilise l'infra ingestion SP-6), GeoJSON paginé complet.
  - **Source (STAC ou ArcGIS) vers une URL interne** (ex. `http://127.0.0.1/…` ou
    host résolvant en privé) → `EgressBlockedError` capturé → `last_status=
    "error"`, `last_error` renseigné, **aucun item créé**. La garde partagée par
    les deux connecteurs est prouvée.
  - Mutation en **read-only mode** court-circuitée (aucun item ; garde SP-12c
    inchangée).
- **Adversarial.** Non-admin/anonyme sur toute route `/harvest/*` → 403 ; 404
  non-fuyant cross-tenant (patron SP-12c, inchangé).
- **Sweep `running`.** Test unitaire `list_due_sources` : source `running`
  récente exclue ; source `running` ancienne (au-delà de la fenêtre) réincluse
  (reclaim par âge, §4.2).
- **E2E shell.** `harvest-arcgis.spec.ts` (§5.3).

## 7. Critères d'acceptation

1. Un admin crée une source `arcgis` (`POST /harvest/sources`), la moissonne ;
   **chaque couche** du Feature Service distant devient un **item externe
   cherchable** (`GET /items`, badge « Externe » au shell) avec un lien
   dé-référençable vers la couche distante.
2. **Le re-moissonnage met à jour sans dupliquer** (index unique `(tenant_id,
   source_id, external_id)`, prouvé contre Postgres) ; une couche disparue de la
   source est marquée `is_stale`, jamais un doublon créé.
3. Une source `arcgis` `mode="copy"` produit une **collection PostGIS locale** via
   le pipeline SP-6, avec le **GeoJSON paginé complet** de la couche (pas tronqué
   à la première page ; borné par `_MAX_COPY_FEATURES`).
4. Une source (STAC **ou** ArcGIS) pointant une **cible réseau interne** est
   **bloquée** par la garde d'egress (loopback/link-local/privée) : `last_status
   ="error"`, aucun item créé — la garde est partagée par les deux connecteurs
   et la récupération copie.
5. Le balayage périodique **ne double-moissonne pas** une source déjà `running`
   (avec reclaim par âge d'un run planté) ; les boutons d'écriture de
   `/admin/harvest` sont **masqués en mode démo** ; la spec E2E `harvest-arcgis`
   prouve le parcours admin → moissonnage → item externe, sans régression sur les
   44 specs existantes.

## 8. Risques & simplifications assumées

- **DNS-rebinding TOCTOU** (§3) : la garde valide l'IP résolue avant la requête,
  httpx re-résout au connect. Pinning-IP différé (fragile avec TLS/vhosts),
  **signalé**, pas ignoré. Les cibles SSRF à forte valeur (métadonnées cloud,
  localhost) sont couvertes (IP-littérales / résolution stable).
- **Auth distante = services publics seulement** (v0) : pas de token/OAuth vers
  l'ArcGIS distant. Couvre l'open data Esri (cible A22). Services sécurisés →
  suivi.
- **Copie ArcGIS bornée** (§2.2) : `_MAX_COPY_FEATURES` plafonne un service géant
  (tronqué au plafond, journalisé). Le miroir intégral de très gros services et
  la copie incrémentale sont hors périmètre.
- **Reprojection bbox = enveloppe seule** (§2.3) : approximation de catalogue
  (coins reprojetés), suffisante pour un `bbox` de référencement.
- **`type` free string** (§5.1) : pas d'enum serveur, validation par le registre
  de connecteurs (400 si inconnu). Cohérent avec l'extensibilité SP-12c.
- **Concurrence** : l'anti-doublon repose sur l'index unique (SP-12c), pas sur un
  lock ; le skip `running` du sweep (§4.2) réduit le double-travail sans être un
  verrou fort.
- **Connecteurs restants** : GetCapabilities WMS/WFS (SP-12e), CSW/ISO 19139
  (SP-12f), CKAN (SP-12g). L'abstraction `HarvestConnector` (désormais avec
  `fetch_copy_geojson`) et la garde d'egress partagée sont dimensionnées pour eux.
