# SP-12c — Moteur de moissonnage + connecteur STAC externe — design

**Date.** 2026-07-19
**Phase.** SP-12c, troisième sous-phase de SP-12 « Catalogue interopérable :
STAC, DCAT, moissonnage » — suit SP-12a (API STAC native, lecture seule, clos)
et SP-12b (export DCAT-AP, clos). Première brique du volet **consommation** :
SP-12a/b *produisaient* des standards, SP-12c en *lit* un.
**Références.** Feuille de route §SP-12 (« Moteur de moissonnage » + « Connecteurs »)
et arbitrages **A22** (les 5 connecteurs, ordre `STAC → ArcGIS FS →
GetCapabilities → CSW/ISO → CKAN` — chacun livrable séparément, STAC en premier)
et **A23** (référencement pur par défaut, copie opt-in par source, qui route vers
le pipeline d'ingestion SP-6). §« Hors périmètre » des specs SP-12a/b qui scopent
explicitement le moissonnage à « SP-12c… ».

## 1. Objectif & périmètre

**Objectif.** Un admin déclare une **source de moissonnage** pointant un catalogue
STAC externe (une API STAC ou un catalogue statique) ; le cœur la moissonne en job
procrastinate et **référence** chaque jeu de données distant comme un item de
catalogue « externe » — cherchable, avec un lien vers la source, une fraîcheur, et
un re-moissonnage qui **met à jour sans dupliquer**. Par source, l'admin peut opter
pour la **copie** (A23) qui route la donnée distante vers le pipeline d'ingestion
SP-6 et produit une collection PostGIS locale au lieu d'une simple référence.

**Dans le périmètre.**
- **Moteur de moissonnage générique** : table déclarative `harvest_sources`
  (type, URL, mode, activation, planification, statut/fraîcheur), CRUD **admin-only
  audité**, exécution en **job procrastinate** (déclenchement manuel + balayage
  périodique des sources dues).
- **Un seul connecteur : STAC externe** (①  de A22). Abstraction `HarvestConnector`
  posée mais **une seule implémentation** livrée ; ArcGIS FS/GetCapabilities/
  CSW/CKAN = SP-12d…g.
- **Les deux modes d'A23** : `reference` (défaut) crée un item « externe »
  pointant la source ; `copy` route la donnée distante à travers
  `app.ingestion.importer.run_import` (SP-6) → collection PostGIS locale.
- **Idempotence du re-moissonnage** : mapping stable `(source, id externe) → item/
  collection local`, upsert (existant mis à jour, nouveau créé, disparu marqué
  périmé — jamais de doublon).
- **Surface shell minimale** : page d'admin des sources (`/admin/harvest`, miroir de
  `CollectionsAdminPage`), badge « Externe » sur les items moissonnés dans le
  catalogue, ≥1 spec E2E.

**Hors périmètre (sous-phases ultérieures / autres SP).**
- **SP-12d…g** : les 4 autres connecteurs (ArcGIS FS, GetCapabilities WMS/WFS,
  CSW/ISO 19139, CKAN). L'abstraction `HarvestConnector` est dimensionnée pour eux
  mais aucun n'est écrit ici.
- **Copie des octets d'assets** (COG/rasters d'un Item STAC) : la « copie » d'une
  source STAC copie l'**index interrogeable** (footprints + propriétés des items,
  en GeoJSON, via SP-6), **pas** les octets des assets raster. Le miroir d'assets
  est explicitement différé (§2.5, §11).
- **Ajout d'une couche WMS/WFS moissonnée à une carte sans copie** (critère UI de
  SP-12 global) : appartient au connecteur GetCapabilities (SP-12e), pas à STAC.
- **Ré-export** : un item moissonné n'est **jamais** re-exposé par notre STAC/DCAT
  (SP-12a/b) — ceux-ci n'exportent que nos `collections`, pas les items `external`
  (§2.6). Pas de blanchiment de catalogue tiers sous notre autorité.

## 2. Décisions de modélisation

### 2.1 `harvest_sources` — table déclarative, admin-only

Une source = une intention de moissonnage. Symétrique à `extensions`
(`app/extensions/models.py`) pour le patron admin CRUD audité.

| Colonne | Rôle |
|---|---|
| `id` (uuid, PK) | Surrogate stable |
| `tenant_id` (FK, NOT NULL) | Cloisonnement — une source appartient à un tenant |
| `owner_id` (FK) | L'admin créateur (propriétaire des items produits) |
| `type` (str) | `"stac"` en v0 — discrimine le connecteur (extensible) |
| `url` (str) | URL du catalogue/API STAC distant |
| `mode` (str) | `"reference"` (défaut) \| `"copy"` (A23) |
| `enabled` (bool) | Balayage périodique actif ou non |
| `interval_minutes` (int, nullable) | Cadence de re-moissonnage ; `null` = manuel seul |
| `last_run_at` (datetime, nullable) | Fraîcheur — dernier moissonnage réussi |
| `last_status` (str, nullable) | `"ok"` \| `"error"` \| `"running"` \| `null` (jamais lancé) |
| `last_error` (str, nullable) | Message de la dernière erreur (tronqué), pour l'UI admin |
| `created_at` / `updated_at` | Standard |

**Écritures admin-only auditées** (`_require_admin`, `write_audit
actor_kind="user"`, action `harvest_source.create`/`update`/`delete`/`run`) —
exactement le patron `extensions`. Anonyme/non-admin → 403.

### 2.2 Item moissonné en mode `reference` = `Item` de `resource_type="external"`

Le roadmap tranche : « items moissonnés typés *référence externe* ». On réutilise le
modèle `Item` existant (aucune migration de colonne : `resource_type` est un `String`
libre, exactement comme `"site"` posé par SP-16a sans migration). Un jeu de données
STAC distant → un `Item` :

- `resource_type = "external"`, `title` ← STAC `title`/`id`, `abstract` ← STAC
  `description`, `keywords` ← STAC `keywords` (déjà colonne JSON sur `items`).
- `owner_id`/`tenant_id` ← ceux de la source. `is_published`/`is_public` : **faux
  par défaut** (l'admin publie explicitement, comme tout item — un moissonnage ne
  publie pas de lui-même de la donnée tierce).
- Le **lien vers la source distante** et la métadonnée de provenance ne vivent
  **pas** sur `Item` (pas de sur-largeur du modèle catalogue) mais sur la table de
  liaison `harvest_records` (§2.3), qui porte l'`external_url` dé-référençable.

Conséquence : un item externe apparaît dans `list_items` comme tout item (badge
« Externe » côté shell, §6), respecte `can()`/RLS sans nouveau chemin d'autorisation.

### 2.3 `harvest_records` — la table qui garantit l'idempotence

C'est **le** cœur du « re-moissonner sans dupliquer ». Une ligne par entité distante
déjà vue :

| Colonne | Rôle |
|---|---|
| `id` (uuid, PK) | |
| `tenant_id` (FK) | Cloisonnement + RLS |
| `source_id` (FK → harvest_sources) | Quelle source l'a produit |
| `external_id` (str) | Id stable de l'entité distante (STAC Collection `id`, ou `self` href à défaut) |
| `item_id` (FK → items, nullable) | L'item local produit (mode `reference`) |
| `collection_id` (FK → collections, nullable) | La collection locale produite (mode `copy`) |
| `content_hash` (str, nullable) | Empreinte de la charge distante — court-circuite l'écriture si inchangé |
| `harvested_at` (datetime) | Dernière fois vue dans un moissonnage |
| `is_stale` (bool, défaut faux) | Vraie quand l'entité a **disparu** de la source au dernier passage |

**Contrainte d'unicité `(tenant_id, source_id, external_id)`** (index unique, non
couvrable par SQLite → vérifié contre Postgres réel, même discipline que
l'`uq_items_tenant_slug` de SP-16a). C'est elle qui rend le re-moissonnage un
**upsert** : `SELECT ... WHERE source_id=? AND external_id=?` → trouvé ⇒ mise à jour
de l'item/collection existant + `harvested_at` ; absent ⇒ création. Aucun doublon
possible même sur exécutions concurrentes (l'index tient l'intégrité, TOCTOU →
retry/skip, jamais duplication).

**Disparition.** Après un moissonnage complet, toute `harvest_record` de la source
**non revue** dans ce passage est marquée `is_stale=true` (jamais supprimée dur :
l'item local peut être référencé par une app/carte ; suppression destructrice
réservée à une action admin explicite). L'UI pourra distinguer « périmé ». L'item
sous-jacent n'est pas dépublié automatiquement (décision produit v0 : périmé ≠
retiré ; documenté §11).

### 2.4 Granularité STAC : **Collection distante → 1 item externe** (mode reference)

Un catalogue STAC expose Catalog → Collections → Items (features). Le moissonnage se
fait à la **granularité Collection** (symétrique à ce que SP-12a/b exposent de
*notre* côté : un `dcat:Dataset`/une STAC Collection = un jeu de données ; jamais
feature-à-feature). Une STAC Collection distante = un item externe local. Descendre à
l'Item STAC ferait exploser le catalogue (des milliers d'items par collection) pour
un référencement — non pertinent.

- Source = API STAC (`/collections` navigable) : on liste `/collections`.
- Source = Catalog statique (`catalog.json` avec `links rel=child`) : on suit les
  liens `child` jusqu'aux `Collection` (profondeur bornée, §2.7).

### 2.5 Mode `copy` STAC = footprints via SP-6, **pas** les assets

Quand `mode="copy"`, le connecteur STAC récupère les **items** de la collection
distante (`/collections/{id}/items`, GeoJSON `FeatureCollection` — la géométrie est
obligatoire sur un STAC Item) et les route **tels quels** dans
`run_import(session, ..., filename="harvest.geojson", content=<bytes GeoJSON>,
collection_title=...)`. Réutilise **exactement** le pipeline SP-6a (parseur GeoJSON,
création de table PostGIS, enregistrement collection + item carte, `tenant_id` réel
de la source, audit) — zéro nouveau chemin d'ingestion.

Ce que « copie » copie donc : l'**index interrogeable** (empreintes/footprints +
propriétés des items STAC), comme une collection PostGIS locale requêtable. Ce
qu'elle **ne** copie **pas** : les octets des assets (COG rasters, etc.) — le miroir
d'assets est un chantier à part (bande passante, stockage, licences), explicitement
différé (§11). C'est la lecture honnête d'A23 pour STAC : le connecteur où la copie
est la plus naturelle est ArcGIS FS (SP-12d), pas STAC — mais la copie d'index STAC
est cohérente et démontrable, elle reste au périmètre.

**Capabilité par connecteur.** Le moteur ne suppose pas que tout connecteur sait
copier. `HarvestConnector` expose `supports_copy: bool`. Le connecteur STAC v0 :
`supports_copy=True` (index). Une source `mode="copy"` sur un connecteur
`supports_copy=False` est **refusée à la création** (400, message clair) plutôt
qu'échouée silencieusement au runtime.

### 2.6 Un item moissonné n'est jamais re-exporté

Les routes SP-12a (STAC) et SP-12b (DCAT) exportent **nos `collections`**, pas les
`items`. Un item `resource_type="external"` (mode reference) n'est donc jamais
re-exposé par notre STAC/DCAT — pas de blanchiment de catalogue tiers sous notre
`@id`. En mode `copy`, la donnée devient une **vraie collection locale** (nous en
sommes le producteur au sens strict : table PostGIS chez nous) et est légitimement
exportable comme les autres — comportement voulu, cohérent avec « copier = héberger ».

### 2.7 Parsing STAC tolérant, borné

Même philosophie que le futur parseur ISO « tolérant » du roadmap : ne jamais
faire tomber tout un moissonnage sur une collection distante malformée. Champs
minimaux (`id`, `title`/`description`, `extent.spatial`, `keywords`) ; champs
manquants → repli documenté (titre ← id, bbox ← monde), jamais d'exception qui
fuite. Bornes dures : profondeur de suivi de liens `child` plafonnée, nombre de
collections par moissonnage plafonné, timeout HTTP par requête — un catalogue
distant hostile/cyclique ne doit pas bloquer le worker (§8, §11).

## 3. Nouveau module `core/app/harvest/`

- **`models.py`** — ORM `HarvestSource`, `HarvestRecord` (§2.1, §2.3), tous deux
  `tenant_id` NOT NULL.
- **`connectors/base.py`** — `HarvestConnector` (protocole) : `type: str`,
  `supports_copy: bool`, `fetch(url) -> Iterable[HarvestedRecord]` où
  `HarvestedRecord` = dataclass pure `(external_id, title, abstract, keywords, bbox,
  external_url, items_url | None)`. **Zéro I/O DB** dans le connecteur — il ne fait
  que parler HTTP au distant et produire des records ; l'écriture DB (upsert item/
  collection) est faite par le moteur (`service.py`), pas le connecteur.
- **`connectors/stac.py`** — `StacConnector` (`type="stac"`, `supports_copy=True`).
  HTTP via **`httpx`** (déjà dépendance, déjà auto-instrumenté OTel SP-10a). Parsing
  tolérant (§2.7).
- **`service.py`** — le moteur : `harvest_source(session, source)` = fetch via le
  connecteur du type, puis upsert idempotent (§2.3), dispatch `reference`/`copy`
  (§2.5), marquage `is_stale`, mise à jour `last_run_at`/`last_status`/`last_error`.
  Fonctions repository partagées (comme SP-2/SP-7 : mêmes fonctions REST↔MCP — ici
  REST↔job).
- **`repository.py`** — CRUD `harvest_sources` (create/list/get/update/delete),
  admin-scopé tenant.
- **`routes.py`** — routeur `APIRouter` monté sous `/harvest` dans `app.main`.
- **`jobs.py`** — `@app.task(queue="harvest")` `run_harvest_task(source_id,
  tenant_id)` + `@app.periodic(cron=...)` balayage des sources dues. Ajouté à
  `import_paths` de `app/jobs.py` (sinon le worker ne connaît pas la tâche — leçon
  SP-7 : le worker réel n'importe que `app.jobs.app`).

**Frontière de modules (import-linter).** `app.harvest` importe `app.ingestion`
(`run_import`, mode copy), `app.items`, `app.collections`, `app.tenants`, `app.auth`,
`app.db` → il doit se placer **au-dessus de `app.ingestion`** dans `layers` :

```
layers = [
    "app.main",
    "app.mcp",
    "app.public",
    "app.harvest",   # nouveau — au-dessus de app.ingestion : peut l'importer
    "app.ingestion",
    "app.dcat",
    "app.stac",
    "app.features",
    "app.collections",
    ...
]
```

(`app.jobs` reste hors contrat, comme `app.db` — cf. son docstring.)

## 4. Surface d'endpoints

Préfixe `/harvest`. Gestion des sources = **admin-only**, mutations auditées.

| Endpoint | Rôle |
|---|---|
| `POST /harvest/sources` | Créer une source (valide `type`/`mode`/`supports_copy`, §2.5). 201. Admin-only. |
| `GET /harvest/sources` | Lister les sources du tenant (statut/fraîcheur inclus). Admin-only. |
| `GET /harvest/sources/{id}` | Détail d'une source. 404 non-fuyant si autre tenant/inexistante. Admin-only. |
| `PATCH /harvest/sources/{id}` | Éditer (url/mode/enabled/interval). Admin-only, audité. |
| `DELETE /harvest/sources/{id}` | Supprimer la source (les items/collections produits **survivent** ; `harvest_records` supprimés en cascade). Admin-only, audité. |
| `POST /harvest/sources/{id}/run` | Déclencher un moissonnage **maintenant** (défère `run_harvest_task`). 202. Admin-only, audité (`harvest_source.run`). |

Pas d'endpoint public : le moissonnage est une opération d'administration, ses
**résultats** (items externes, collections copiées) sont exposés par les surfaces
catalogue existantes (`GET /items`, `GET /collections`) sans route neuve.

## 5. Permissions, sécurité, modes read-only/démo

- **Toutes les routes `/harvest/*` sont admin-only** (`_require_admin`), auditées —
  aucune nouvelle notion d'autorisation, patron `extensions` réutilisé.
- **Items/collections produits** suivent le modèle de permission existant
  (`can()`, RLS, publication SP-1c). Un item externe non publié n'est visible que de
  son tenant, comme tout item.
- **Mode read-only / démo (SP-9).** Le middleware ASGI 403 déjà toute mutation
  `POST/PUT/PATCH/DELETE` → les routes de gestion des sources sont couvertes
  gratuitement. **Point critique** : le **balayage périodique** écrit des items
  (mutation hors requête HTTP, invisible au middleware) — `run_harvest_task` et le
  périodique doivent **court-circuiter si `is_read_only_mode()`** (une démo publique
  ne moissonne pas), même posture que la garde read-only des outils MCP d'écriture.
- **SSRF — risque réel documenté (§11).** Le worker émet des requêtes HTTP sortantes
  vers une **URL fournie par l'admin** : surface SSRF/confused-deputy contre le
  réseau interne. Mitigation v0 : **admin-only** (l'admin est déjà de confiance pour
  écrire partout) + timeouts/bornes. Une **allowlist d'egress**/blocage des plages
  loopback·link-local·privées est notée en **suivi** (SP-12d généralisera les
  connecteurs réseau) — pas implémentée ici, mais **explicitement signalée**, pas
  passée sous silence.

## 6. Surface shell (minimale)

- **`HarvestSourcesAdminPage`** (route `/admin/harvest`, **dans `ProtectedLayout`**,
  gate `isAdmin` fail-open côté client — la frontière réelle reste le 403 serveur,
  exactement comme `CollectionsAdminPage`/`AdminExtensionsPage`). Liste des sources
  (type, url, mode, `enabled`, `last_run_at`, `last_status`/`last_error`), dialogues
  créer/éditer/supprimer, bouton **« Moissonner maintenant »** (`POST .../run`).
- **`ItemClient`** : `listHarvestSources` / `createHarvestSource` /
  `getHarvestSource` / `updateHarvestSource` / `deleteHarvestSource` /
  `runHarvestSource` (+ hooks react-query, patron des méthodes collections-admin de
  SP-9).
- **Badge « Externe »** dans le catalogue sur les items `resource_type==="external"`
  (déjà sérialisé via `resourceType`) — indication de provenance, pas de contrôle.
- **Lien de nav** « Moissonnage » sous « Administration » (`AppLayout`, à côté de
  « Extensions »/« Collections », gate `isAdmin`).
- **≥1 spec E2E** (`harvest-stac.spec.ts`) : réseau **STAC distant mocké**
  (Playwright route un `/collections` STAC de fixture) — l'admin crée une source
  STAC, la moissonne, voit ≥1 item externe apparaître au catalogue avec badge
  « Externe » ; un re-moissonnage ne duplique pas (compte stable). Serveur de mock
  distinct/route mockée, jamais d'appel réseau réel en E2E.

## 7. Planification

- **Déclenchement manuel** (`POST .../run`) : chemin toujours disponible, testable
  déterministe (E2E, intégration).
- **Balayage périodique** : une tâche `@app.periodic` unique itère les sources
  `enabled` **dues** (`last_run_at` plus vieux que `interval_minutes`, ou jamais
  lancées) et défère un `run_harvest_task` par source. Pas de cron par source en v0
  (une entrée cron dynamique par ligne est un sur-chantier procrastinate) : un
  balayage régulier + un `interval_minutes` par source suffisent. Documenté §11.
- **Idempotence de l'exécution** : deux `run` concurrents sur la même source sont
  sûrs (l'upsert `(source_id, external_id)` tient l'intégrité) ; `last_status
  ="running"` sert d'indication UI, pas de verrou fort (documenté).

## 8. Tests & validation

- **Unitaires (always-run, offline).** `StacConnector.fetch` contre des **fixtures
  STAC statiques** (un `/collections` d'API STAC et un `catalog.json` statique avec
  `child` links) servies par un transport httpx mocké (`httpx.MockTransport` — zéro
  réseau) : mapping Collection→`HarvestedRecord` correct, tolérance aux champs
  manquants (bbox absent → monde, keywords absents → `[]`), bornes (profondeur/
  nombre plafonnés). Moteur : upsert idempotent (2ᵉ passage ne crée pas de doublon,
  `harvested_at` avancé), marquage `is_stale` d'une entité disparue, refus
  `mode="copy"` sur connecteur `supports_copy=False`.
- **Intégration (marqueur `postgis`).** Contrainte unique `(tenant_id, source_id,
  external_id)` vérifiée contre **Postgres réel** (2ᵉ insert même clé rejeté — non
  couvrable SQLite, discipline SP-16a). Moissonnage `reference` bout-en-bout : source
  seedée → items externes créés → re-moissonnage met à jour sans dupliquer. Moisson-
  nage `copy` : route `run_import` → collection PostGIS locale + item carte créés
  (réutilise l'infra de test ingestion SP-6). Mutation en **read-only mode** court-
  circuitée (aucun item créé).
- **Adversarial.** Non-admin/anonyme sur toute route `/harvest/*` → 403 (patron
  `extensions`/collections-admin). 404 non-fuyant cross-tenant sur
  `GET /harvest/sources/{id}`.
- **E2E shell.** `harvest-stac.spec.ts` (§6), réseau STAC distant mocké.

## 9. Dérive OpenAPI

Nouveaux endpoints `/harvest/*` → `core/openapi.json` +
`shell/src/api/generated/core-schema.d.ts` régénérés (le shell les consomme
réellement ici, contrairement à SP-12a/b — le job `api-types-drift` doit rester
vert).

## 10. Critères d'acceptation (sous-ensemble SP-12c de SP-12)

1. Un admin crée une source STAC (`POST /harvest/sources`), la moissonne
   (`POST .../run` ou balayage) ; chaque Collection du catalogue distant devient un
   **item externe cherchable** (`GET /items`, badge « Externe » au shell) avec un
   lien dé-référençable vers la source.
2. **Le re-moissonnage met à jour sans dupliquer** : re-lancer sur une source
   inchangée laisse le compte d'items stable et avance `harvested_at` ; une entité
   disparue de la source est marquée périmée, jamais un doublon créé (garanti par
   l'index unique `(tenant_id, source_id, external_id)`, prouvé contre Postgres).
3. Une source `mode="copy"` produit une **collection PostGIS locale** via le
   pipeline d'ingestion SP-6 (footprints + propriétés), pas une simple référence ;
   une source `copy` sur un connecteur sans capacité de copie est refusée à la
   création.
4. Gestion des sources **admin-only** (403 sinon), **auditée** ; le balayage
   périodique **ne moissonne pas** en mode read-only/démo.
5. La spec E2E prouve le parcours admin → moissonnage → item externe au catalogue,
   contre un STAC distant mocké, sans régression sur les 43 specs existantes.

## 11. Risques & simplifications assumées

- **SSRF/egress** (§5) : le worker fetch une URL admin-fournie. Mitigation v0 =
  admin-only + bornes/timeouts ; allowlist d'egress différée à SP-12d, **signalée**
  en suivi, non implémentée. Le point le plus sensible de cette sous-phase — traité
  explicitement, pas ignoré.
- **Copie STAC = index, pas assets** (§2.5) : « copier » une source STAC copie les
  footprints/propriétés interrogeables, pas les octets des COG/rasters. Miroir
  d'assets différé (bande passante/stockage/licences). Le connecteur où la copie est
  la plus naturelle (ArcGIS FS → GeoJSON) arrive en SP-12d.
- **Périmé ≠ retiré** (§2.3) : une entité disparue de la source est marquée
  `is_stale`, l'item local n'est pas dépublié/supprimé automatiquement (il peut être
  référencé par une app/carte). Nettoyage = action admin explicite (hors périmètre).
- **Planification simple** (§7) : balayage périodique + `interval_minutes` par
  source, pas de cron dynamique par ligne. Suffisant à l'échelle v0 ; à raffiner si
  un besoin de cadences fines apparaît.
- **Granularité Collection** (§2.4) : on référence des jeux de données, pas des
  features individuelles — un catalogue STAC de millions d'items reste N références
  (N = nombre de collections), pas N millions. Cohérent avec SP-12a/b.
- **Parsing tolérant borné** (§2.7) : profondeur de liens `child`, nombre de
  collections, timeout HTTP plafonnés — un catalogue distant cyclique/hostile ne
  bloque pas le worker. Les valeurs exactes des plafonds sont fixées au plan, pas
  devinées ici.
- **Concurrence** (§7) : `last_status="running"` est indicatif (UI), pas un verrou ;
  l'intégrité anti-doublon repose sur l'index unique, pas sur un lock applicatif.
