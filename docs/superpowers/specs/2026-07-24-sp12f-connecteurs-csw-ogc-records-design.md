# SP-12f — Connecteurs métadonnées CSW (2.0.2) et OGC API - Records

- **Date** : 2026-07-24
- **Statut** : spec validée (brainstorm)
- **Prérequis** : SP-12c (moteur de moissonnage + connecteur STAC), SP-12d
  (connecteur ArcGIS FS + garde d'egress SSRF), SP-12e (connecteurs
  GetCapabilities + module XML partagé `ows.py`, dépendance `defusedxml`).
- **Suite** : SP-12g (CKAN).

## 1. Contexte et objectif

SP-12 fédère des catalogues externes par moissonnage (référencement par défaut,
copie opt-in). Quatre connecteurs existent déjà, tous branchés sur le
`HarvestConnector` (protocole `fetch` → `HarvestedRecord`, plus
`fetch_copy_geojson`) et sur la garde d'egress SSRF : STAC (SP-12c), ArcGIS
Feature Service (SP-12d), WMS/WFS/WMTS (SP-12e, avec le module XML partagé
`ows.py`).

SP-12f livre le connecteur ③ de la feuille de route (A22) : **CSW/ISO 19139**
(GeoNetwork/geOrchestra), en ciblant CSW 2.0.2. Le brainstorm a étendu le
périmètre à son protocole successeur, **OGC API - Records** (JSON/REST), pour
couvrir aussi les catalogues qui l'exposent déjà — cette extension d'A22 ③ est
documentée explicitement (§9) plutôt que silencieuse, conformément à la règle
CLAUDE.md sur les arbitrages figés.

Les deux protocoles partagent le même rôle (cataloguer des **métadonnées**
décrivant des ressources, pas les ressources elles-mêmes) mais des formes
radicalement différentes (XML imbriqué ISO19139 vs JSON REST paginé). Ce sont
donc **deux connecteurs distincts** au registre — `csw` et `ogc-records` — livrés
dans le même spec/plan, en phases séparées, comme SP-12e avait livré WMS+WFS+WMTS
ensemble.

### Décisions de cadrage (brainstorm)

1. **Requête CSW** : GET-KVP uniquement (cohérent avec les 4 connecteurs
   existants), pas de POST-XML `csw:GetRecords`.
2. **Format de sortie CSW** : ISO19139 (`gmd:MD_Metadata`) en priorité, avec
   repli **Dublin Core** (`csw:Record`) si le serveur ne supporte pas
   l'`outputSchema` ISO.
3. **Mode copie** : `supports_copy = False` pour les **deux** connecteurs — une
   fiche de métadonnées décrit une ressource, elle n'est pas elle-même
   récupérable de façon fiable et générique (cf. §9).
4. **Portée OGC API - Records** : un 2ᵉ type de connecteur dans le même spec
   (pas un incrément séparé) ; l'URL fournie par l'admin est la racine de l'API,
   le connecteur tape des chemins fixes (`/collections`,
   `/collections/{id}/items`) plutôt que de suivre les `links` de la page
   d'accueil (moins de surface de redirection dynamique).
5. **E2E** : un spec Playwright par connecteur (pas un spec combiné).

## 2. Architecture

```
core/app/harvest/connectors/
  base.py         ← inchangé
  ows.py          ← existant (SP-12e), réutilisé par csw.py (XML)
  csw.py          ← NOUVEAU : CswConnector (CSW 2.0.2, ISO19139 + repli DC)
  ogc_records.py  ← NOUVEAU : OgcRecordsConnector (JSON REST)
  __init__.py     ← _REGISTRY += csw / ogc-records
```

Aucune nouvelle colonne `harvest_records` : les colonnes `external_url` /
`tiles_url` / `layer_kind` ajoutées en migration 0017 (SP-12e) couvrent déjà ce
besoin — `tiles_url`/`layer_kind` restent `NULL` pour ces deux connecteurs
(reference-only, jamais de `raster_tiles_url` ni `items_url`). **Aucune
migration Alembic dans SP-12f.**

## 3. Connecteur CSW (`CswConnector`, `supports_copy = False`)

### 3.1 Fetch : `GetRecords` paginé (GET-KVP)

Contrairement au `GetCapabilities` en un seul GET des connecteurs SP-12e,
`GetRecords` est intrinsèquement paginé (`startPosition`/`maxRecords`/
`nextRecord`). Le connecteur boucle en interne, avec son propre client gardé
(comme les autres — `fetch(url)` ne reçoit pas de `http_get` externe) :

```
GET {url}?service=CSW&version=2.0.2&request=GetRecords&resultType=results
    &outputSchema=http://www.isotc211.org/2005/gmd&elementSetName=full
    &typeNames=gmd:MD_Metadata&startPosition={n}&maxRecords=100
```

- Bornes : `_MAX_CSW_RECORDS = 500` (total émis, miroir de `ows._MAX_LAYERS`),
  `_MAX_CSW_PAGES = 50`, timeout 10 s par page (`ows._DEFAULT_TIMEOUT_SECONDS`).
- **Garde-fou de boucle** : si `nextRecord` n'avance pas au-delà du
  `startPosition` courant (serveur malformé/hostile), on arrête — jamais de
  boucle infinie.
- **Repli Dublin Core** : si la **première page** n'est pas une
  `csw:GetRecordsResponse` valide avec des enregistrements ISO (erreur HTTP,
  XML illisible, ou un `ows:ExceptionReport` — certains serveurs CSW rejettent
  ainsi un `outputSchema` non supporté), un seul nouvel essai est fait sans
  `outputSchema` (défaut serveur → `csw:Record`, Dublin Core), avec le
  parsing DC. Un seul essai de repli, décidé une fois pour tout le fetch (pas
  par page) : une fois le format déterminé sur la première page, les pages
  suivantes sont parsées avec ce même format. Si une page **suivante** échoue
  (HTTP/XML), la pagination s'arrête proprement et les enregistrements déjà
  accumulés sur les pages précédentes sont conservés (résultat partiel, pas de
  second essai de repli en cours de route).

### 3.2 Extraction des champs (tolérante, champs minimaux)

**ISO19139 (`gmd:MD_Metadata`)** :
- `external_id` = `gmd:fileIdentifier/gco:CharacterString`.
- `title` = `.../gmd:citation/gmd:CI_Citation/gmd:title/gco:CharacterString`
  (recherche via `ows.descendants`, premier trouvé).
- `abstract` = `.../gmd:abstract/gco:CharacterString`.
- `keywords` = tous les `.../gmd:descriptiveKeywords//gmd:keyword/gco:CharacterString`.
- `bbox` = `.../gmd:EX_GeographicBoundingBox`, coordonnées imbriquées un niveau
  plus profond dans `gco:Decimal` (diffère du `EX_GeographicBoundingBox` plat de
  WMS — nouvelle fonction d'extraction dédiée) ; défaut `ows._WORLD_BBOX` si
  absent/illisible.

**Dublin Core (`csw:Record`, repli)** :
- `external_id` = `dc:identifier` ; `title` = `dc:title` ; `abstract` =
  `dct:abstract` ou `dc:description` ; `keywords` = tous les `dc:subject`.
- `bbox` = `ows:BoundingBox` (`ows:LowerCorner`/`ows:UpperCorner`) ou
  `ows:WGS84BoundingBox` ; défaut `_WORLD_BBOX`.

**Commun aux deux formes** :
- `external_url` = lien profond vers la fiche via `GetRecordById` (pas juste
  l'endpoint `GetRecords`) :
  `{base}?service=CSW&version=2.0.2&request=GetRecordById&id={identifier}&outputSchema=...&elementSetName=full`.
- Un enregistrement sans identifiant est ignoré (pas d'upsert idempotent
  possible sans `external_id`), même discipline que WMS/WFS ignorant les
  couches sans nom.
- `items_url = None`, `raster_tiles_url = None` toujours.

## 4. Connecteur OGC API - Records (`OgcRecordsConnector`, `supports_copy = False`)

### 4.1 Fetch : chemins fixes + pagination par lien `next`

L'admin fournit la **racine de l'API**. Le connecteur tape deux chemins fixes
(pas de découverte via les `links` de la page d'accueil) :

```
GET {root}/collections                          → liste des collections de fiches
GET {root}/collections/{id}/items?limit=100      → page de fiches (FeatureCollection GeoJSON)
```

- Pour chaque collection de l'étape 1 (bornée : `_MAX_OGC_COLLECTIONS = 50`),
  pagination des `items` via `links[rel="next"]` de la réponse (relation
  standard OGC, pas un offset/limit deviné) ; bornée par collection
  (`_MAX_OGC_PAGES_PER_COLLECTION = 50`) et au total
  (`_MAX_OGC_RECORDS = 500`, même plafond que CSW/WMS).
- Client gardé, timeout 10 s par requête, erreurs `(httpx.HTTPError, ValueError)`
  capturées comme dans `StacConnector`.
- **Tolérance** : `/collections` malformé/illisible → liste vide. Pour une
  collection donnée : si sa **première** page `items` échoue (HTTP/JSON), la
  collection est ignorée (zéro enregistrement pour elle, les autres
  collections continuent) ; si une page **suivante** échoue en cours de
  pagination, on arrête proprement pour cette collection en conservant les
  enregistrements déjà accumulés sur ses pages précédentes. Jamais d'abandon
  total du fetch — même philosophie que STAC/WFS (retour partiel plutôt
  qu'échec complet).

### 4.2 Extraction des champs

Chaque **Feature** GeoJSON d'une page `items` = un `HarvestedRecord` :
- `external_id` = `feature["id"]`.
- `title` = `properties.title` ; `abstract` = `properties.description`.
- `keywords` = `properties.keywords` (liste).
- `bbox` = le membre `bbox` de la Feature s'il est présent, sinon
  `_WORLD_BBOX` (pas de calcul d'enveloppe de géométrie — reste dans l'esprit
  « champs minimaux »).
- `external_url` = `links[rel="self"]` de la fiche si présent, sinon l'URL de la
  page `items`.
- `items_url = None`, `raster_tiles_url = None` toujours.
- Une Feature sans `id` est ignorée (même discipline que CSW).

## 5. Sécurité

Identique à SP-12e :
- **SSRF** : toutes les requêtes (CSW `GetRecords` paginé, OGC API `collections`
  + `items` paginés) passent par le client d'egress gardé
  (`build_guarded_client`), construit en interne par chaque connecteur (comme
  STAC/WMS/WFS/WMTS).
- **XML (CSW)** : `defusedxml` (déjà dépendance du cœur depuis SP-12e) neutralise
  XXE et l'expansion d'entités. Parsing tolérant : log-and-skip, jamais
  d'exception qui fuite hors du connecteur (contrat harvest : ne jamais lever,
  cf. SP-12c).
- **JSON (OGC API - Records)** : mêmes garde-fous que STAC — type-checking
  défensif de chaque document/feature avant extraction, `ValueError`/
  `httpx.HTTPError` capturés localement.

## 6. Plan de tests

### Unitaires CSW (fixtures GetRecords capturées)

- Page ISO19139 → records avec title/abstract/keywords/bbox/lien
  `GetRecordById` corrects.
- Pagination multi-pages : avance et s'arrête à `nextRecord=0` ; le
  garde-fou de boucle stoppe si `nextRecord` n'avance pas ; le plafond de
  pages/records tronque proprement.
- Première page malformée ou `ows:ExceptionReport` → repli Dublin Core réussi ;
  fixture DC → records via les champs `dc:*`.
- Sécurité : charge XXE/billion-laughs neutralisée.
- Enregistrement sans identifiant → ignoré, pas de crash.

### Unitaires OGC API - Records (fixtures JSON)

- `/collections` + une page `items` → records corrects (title/abstract/
  keywords/bbox/lien self).
- Pagination multi-pages via `links[rel="next"]` ; plafond de pages/records
  tronque proprement.
- `/collections` malformé → liste vide, pas de crash.
- Une collection dont la page `items` échoue → ignorée, les autres continuent
  (résultat partiel).
- Feature sans `id` → ignorée.

### Service / repository

- Upsert en référence déjà couvert par les tests service existants
  (agnostiques à la forme du `HarvestedRecord`) : confirmer que `tiles_url`/
  `layer_kind` restent `NULL` pour les enregistrements `csw` et `ogc-records`.

### Shell

- `CreateHarvestSourceDialog` : options CSW et OGC API - Records présentes,
  mode copie grisé pour les deux (jamais dans `COPY_TYPES`).

### E2E Playwright (mock) — un spec par connecteur

- **CSW** : admin crée une source CSW → moissonnage (mock GetRecords) → item
  « référence externe » avec le titre moissonné apparaît au catalogue,
  cherchable.
- **OGC API - Records** : même parcours, mock `/collections` +
  `/collections/{id}/items`.
- Aucune étape carte dans les deux cas (rien n'est ajoutable à une carte pour
  ces deux connecteurs).

## 7. Découpage pour le plan

1. **Connecteur CSW** : `csw.py` (TDD, fixtures ISO19139 + DC + XXE). Réutilise
   `ows.py` existant, aucune nouvelle dépendance.
2. **Connecteur OGC API - Records** : `ogc_records.py` (TDD, fixtures JSON).
3. **Registre & schémas** : `_REGISTRY` += `csw`/`ogc-records` ;
   `schemas.py` : `Literal[...] += "csw", "ogc-records"`.
4. **Shell** : `types.ts` + `core-schema.d.ts` régénéré ; `CreateHarvestSourceDialog`
   (deux options, mode copie grisé pour les deux).
5. **E2E + docs** : deux specs Playwright (un par connecteur) ; mise à jour
   `CLAUDE.md` / feuille de route (SP-12f livré, reste SP-12g ; note
   d'extension d'A22 ③, cf. §9).

## 8. Hors périmètre

- CSW 3.0 en tant que **révision de CSW** (nom historique parfois donné à OGC
  API - Records) : couvert par le connecteur `ogc-records` lui-même, pas de
  troisième type.
- POST-XML `csw:GetRecords` (requêtes `ogc:Filter` riches).
- Extraction d'un lien de téléchargement réel depuis `distributionInfo`/
  `onLine` (CSW) pour activer une copie ou un ajout carte.
- Découverte dynamique de collections OGC API - Records via les `links` de la
  page d'accueil (chemins fixes uniquement, cf. §1 décision 4).
- Filtrage avancé OGC API - Records (`filter`, `q`, `bbox` en paramètre de
  requête) : moissonnage plein-catalogue uniquement, comme les autres
  connecteurs.
- Endpoints CSW/OGC API - Records authentifiés.
- SP-12g (CKAN) — dernier connecteur d'A22.

## 9. Extension d'A22 ③ (feuille de route)

L'arbitrage A22 (§ *Connecteurs de moissonnage v1*, feuille de route) liste
« CSW/ISO 19139 » comme connecteur ③. SP-12f livre ce connecteur **et** son
protocole successeur **OGC API - Records**, sous le même numéro d'incrément
(③), tous deux réference-only. Ce n'est pas une redéfinition de l'arbitrage
(l'ordre A22 et le périmètre des quatre connecteurs restent inchangés) mais une
extension documentée de ce qu'③ couvre concrètement — à refléter dans le
tableau récapitulatif et la section SP-12 de
`docs/vision/2026-07-04-feuille-de-route-geostudio.md` lors de la livraison.

## 10. Hypothèses v0 et résiduels documentés

- **Services publics** uniquement (pas de token/OAuth distant) — même résiduel
  que les connecteurs précédents.
- **CSW** : cible CSW 2.0.2 GET-KVP ; un serveur qui ne supporte ni l'ISO19139
  ni le Dublin Core par défaut (rare) finit en erreur, sans repli
  supplémentaire.
- **OGC API - Records** : suppose les chemins `/collections` et
  `/collections/{id}/items` conformes à la spec ; un serveur qui ne les expose
  pas à cette racine (ex. exigeant une découverte via `links`) n'est pas
  moissonnable en v0.
- **Aucun affichage carte** pour ces deux connecteurs (métadonnées pures) —
  cohérent avec l'acceptation SP-12 qui ne l'exige que pour WMS (SP-12e).
- Résiduel DNS-rebinding TOCTOU de la garde d'egress inchangé (pinning-IP
  toujours différé).
