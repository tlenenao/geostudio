# SP-12b — Export DCAT-AP (JSON-LD moissonnable) — design

**Date.** 2026-07-19
**Phase.** SP-12b, deuxième sous-phase de SP-12 « Catalogue interopérable :
STAC, DCAT, moissonnage » — suit SP-12a (API STAC native, lecture seule, clos).
**Références.** Feuille de route §SP-12 et arbitrage **A21** (export DCAT-AP
moissonnable, JSON-LD, pas d'API DCAT complète ni SPARQL — « peu de code, couvre
l'obligation open-data des collectivités ») ; §« Hors périmètre » de la spec
SP-12a qui scope explicitement SP-12b à ce périmètre.

## 1. Objectif & périmètre

**Objectif.** Un portail open-data (data.gouv.fr, ou tout moissonneur DCAT-AP —
CKAN, GeoNetwork) moissonne le catalogue GeoStudio en pointant une seule URL :
il obtient un document JSON-LD DCAT-AP décrivant chaque collection publique
comme un `dcat:Dataset` avec au moins une `dcat:Distribution` exploitable
(GeoJSON via OGC API Features, déjà existant). Aucune API DCAT interactive,
aucun SPARQL (A21 tranché) — un export, pas un service.

**Dans le périmètre.**
- Deux routes **lecture seule, cœur uniquement** : le dump complet du catalogue
  (`GET /dcat/catalog`) et un nœud `dcat:Dataset` dé-référençable individuellement
  (`GET /dcat/datasets/{id}`).
- Mapping **plateforme `Collection` → `dcat:Dataset`** (même granularité que STAC
  Collection en SP-12a — pas de mapping feature-à-feature, DCAT décrit des jeux de
  données, pas des enregistrements individuels).
- Distribution(s) pointant vers des endpoints **déjà existants** : OGC API
  Features (`GET /collections/{id}/items`, GeoJSON, SP-3b) et, en second,
  STAC item-search de la collection (`GET /stac/collections/{id}/items`,
  SP-12a) — zéro nouvel endpoint de données.
- Validation structurelle bloquante offline (SHACL, DCAT-AP officiel) + smoke
  documenté non bloquant contre le vrai validateur data.gouv.fr.

**Hors périmètre (sous-phases ultérieures de SP-12).**
- **SP-12c…** : moteur de moissonnage (`harvest_sources`) + les 5 connecteurs
  (STAC externes → ArcGIS FS → GetCapabilities → CSW/ISO 19139 → CKAN, A22/A23).
  SP-12b exporte ; il ne consomme aucun catalogue externe.
- **UI** : rien côté shell. Comme STAC (SP-12a), DCAT est une API machine pour
  moissonneurs externes — le shell n'est pas touché, **les 43 specs E2E restent
  inchangées**.
- Thématisation métier (`dcat:theme`), point de contact structuré
  (`dcat:contactPoint`) : la plateforme n'a pas ces données ; documentés comme
  gaps v0 plutôt que remplis avec des valeurs inventées (cf. §5, §9).

**Cœur uniquement.** Aucune surface shell ni MCP (même choix que SP-12a).

## 2. Décisions de modélisation

### 2.1 Ce qu'est un `dcat:Dataset` (arbitré)

DCAT organise Catalog → Dataset → Distribution. Le mapping retenu, symétrique à
celui de STAC en SP-12a :

| DCAT-AP | GeoStudio |
|---|---|
| `dcat:Catalog` | Le catalogue du tenant courant |
| **`dcat:Dataset`** | Une plateforme `Collection` (même granularité que STAC Collection) |
| **`dcat:Distribution`** | Un point d'accès *existant* à cette collection : GeoJSON (OGC API Features) en premier, STAC item-search en second |

Conséquence : **aucun nouveau chemin de requête sur les features**. Contrairement
à STAC (qui expose chaque feature comme un Item), DCAT ne descend jamais à la
feature — une `Collection` vide de géométrie (table non spatiale) reste un
`dcat:Dataset` valide (distribution GeoJSON toujours pertinente : OGC API
Features sert aussi des tables non géométriques). Les apps/dashboards/maps
(`items`) ne sont **pas** exposés (même exclusion qu'en SP-12a, A7).

### 2.2 `dct:accessRights` reflète `is_public`, jamais une constante

Contrairement à STAC (dont l'audience anonyme est filtrée en amont par
`list_visible_collections`, donc *toute* réponse anonyme est publique par
construction), un appelant **authentifié** peut voir des collections partagées
mais non publiques. Asserter `PUBLIC` en dur serait alors trompeur. Valeur
dérivée : `collection.is_public` → autorité EU `access-right`
(`.../PUBLIC` sinon `.../RESTRICTED`). En pratique le consommateur réel est
anonyme (moissonnage externe data.gouv.fr), donc toujours `PUBLIC` — mais la
route ne suppose pas son appelant.

### 2.3 `dct:license` — simplification documentée, symétrique à STAC

Comme `Collection` n'a pas de champ licence (même constat qu'en SP-12a §2.4),
**v0 :** URI fixe de l'autorité EU *licence* pour « autre / non précisée » —
`http://publications.europa.eu/resource/authority/licence/OTHER` — plutôt qu'un
lien vers une licence française supposée (Etalab/Licence Ouverte) que rien ne
garantit. Choix délibérément symétrique au `license: "other"` de STAC (même
information, encodée dans le vocabulaire DCAT). À raffiner si un champ licence
est ajouté au modèle de collection (même note qu'en SP-12a).

### 2.4 `dct:spatial` — réutilise `estimated_bbox_4326` de SP-12a

Pas de nouveau calcul d'emprise : `app.stac.extent.estimated_bbox_4326` (déjà
écrit, testé, en Task 4 de SP-12a) est réutilisé tel quel. Repli **emprise
monde** silencieux si `None` (collection sans géométrie ou table vide) — à la
différence de STAC, DCAT-AP n'a pas de propriété `note`/extension ad-hoc pour
documenter l'approximation in-band ; le fait que ce repli existe est documenté
ici, pas dans la charge utile JSON-LD (§9).

`dct:spatial` sérialisé en `dct:Location` avec `locn:geometry` (littéral GeoJSON,
`@type: "https://www.iana.org/assignments/media-types/application/vnd.geo+json"` — la
forme recommandée par DCAT-AP pour une emprise sans passer par WKT).

### 2.5 `dct:temporal` — même simplification que STAC (§2.2 spec SP-12a)

`Collection` n'a pas de dimension temporelle propre. Repris identique à
l'intervalle STAC : `dcat:startDate = collection.created_at`, pas de
`dcat:endDate` (ouvert vers le futur). Documenté comme simplification, pas
raffiné plus qu'en SP-12a.

### 2.6 `dct:publisher` — réutilise `Tenant.name`, aucun nouveau champ

Le modèle `Tenant` (`app/tenants/models.py`) porte déjà un champ `name`.
`dct:publisher` = `foaf:Agent` avec `foaf:name: tenant.name`, résolu pour le
tenant de l'appelant (anonyme → tenant `default`, même résolution que SP-12a
§6/A33). **Aucune nouvelle variable d'environnement** (pas de
`CORE_DCAT_PUBLISHER_*`) : le champ existe déjà, l'utiliser est plus honnête et
moins de code qu'un réglage dupliqué.

### 2.7 `dcat:keyword` et `dcat:theme` — omis si absents, jamais inventés

`Collection` n'a pas de champ mots-clés (contrairement à `Item.keywords`, non
concerné ici — DCAT ne mappe pas les items). `dcat:keyword` est donc **omis**
(pas de tableau vide qui ferait semblant d'avoir une valeur). `dcat:theme`
(thème métier, table d'autorité EU) n'a également aucune source de données —
omis, documenté comme gap v0 (§9), pas comblé par une valeur générique inventée
(ex. un thème "GOVE" par défaut serait faux pour un jeu de données qui ne
concerne pas le gouvernement).

## 3. Nouveau module `core/app/dcat/`

- **`serializers.py`** — fonctions **pures** construisant des dicts JSON-LD
  (`catalog()`, `dataset()`, `distribution()`) à partir de primitives. Zéro I/O,
  même discipline que `app/stac/serializers.py`. `@context` DCAT-AP défini en
  dur (prefixes `dcat`, `dct`, `foaf`, `locn`, `xsd` — pas de dépendance à un
  contexte JSON-LD distant chargé au runtime, même philosophie que STAC : la
  forme est vérifiée en test, pas résolue en ligne).
- **`routes.py`** — routeur `APIRouter` monté sous `/dcat` dans `app.main`.
  Réutilise `list_visible_collections` (dump), `get_readable_collection`
  (dataset unique, 404 non-fuyant), `get_or_create_default_tenant` (résolution
  tenant anonyme), et **importe `app.stac.extent.estimated_bbox_4326`** (§2.4 —
  aucune duplication de la logique d'emprise).

**Frontière de modules (import-linter).** `app.dcat` inséré **entre
`app.ingestion` et `app.stac`** dans la liste `layers` (pas après `app.stac`) :
c'est ce qui permet à `app.dcat` d'importer `app.stac.extent` sans inverser la
dépendance. `app.dcat` peut aussi importer `app.collections`, `app.tenants`,
`app.auth`, `app.db` ; jamais l'inverse.

```
layers = [
    "app.main",
    "app.mcp",
    "app.public",
    "app.ingestion",
    "app.dcat",      # nouveau — au-dessus de app.stac : peut l'importer
    "app.stac",
    "app.features",
    "app.collections",
    ...
]
```

## 4. Surface d'endpoints

Toutes les routes `GET`, lecture seule. Préfixe `/dcat`.

| Endpoint | Rôle |
|---|---|
| `GET /dcat/catalog` | Dump complet : un `dcat:Catalog` avec tous les `dcat:Dataset` visibles **embarqués** (pas de liens paresseux — un moissonneur DCAT récupère un document, pas un flux paginé, cf. §7) |
| `GET /dcat/datasets/{id}` | Un seul nœud `dcat:Dataset`, dé-référençable (les `@id` du dump y pointent) ; **404 non-fuyant** si non lisible/inexistant (même convention que `GET /stac/collections/{id}`) |

**Content-Type : `application/ld+json`**, pas le défaut FastAPI
(`application/json`). Contrairement à STAC (SP-12a n'a pas pris cette peine,
`application/json` suffisant pour un client STAC typé), c'est ici **porteur de
sens** : c'est le Content-Type qui indique à un moissonneur générique (data.gouv.fr,
CKAN) que le corps est du JSON-LD plutôt que du JSON brut. Réglé explicitement
par route (`Response(..., media_type="application/ld+json")`), pas la valeur
par défaut de FastAPI.

## 5. Objets DCAT-AP

### 5.1 `@context` (fixe, en dur)

```json
{
  "dcat": "http://www.w3.org/ns/dcat#",
  "dct": "http://purl.org/dc/terms/",
  "foaf": "http://xmlns.com/foaf/0.1/",
  "locn": "http://www.w3.org/ns/locn#",
  "xsd": "http://www.w3.org/2001/XMLSchema#"
}
```

### 5.2 `dcat:Catalog`

```json
{
  "@context": { … },
  "@id": "<base>/dcat/catalog",
  "@type": "dcat:Catalog",
  "dct:title": "Catalogue GeoStudio",
  "dct:description": "Export DCAT-AP du catalogue de données GeoStudio (lecture seule).",
  "dct:publisher": { "@id": "<base>/dcat/publisher", "@type": "foaf:Agent", "foaf:name": "<tenant.name>" },
  "dct:language": "fr",
  "dcat:dataset": [ /* dcat:Dataset embarqués, §5.3 */ ]
}
```

### 5.3 `dcat:Dataset` ← plateforme `Collection`

```json
{
  "@id": "<base>/dcat/datasets/{id}",
  "@type": "dcat:Dataset",
  "dct:identifier": "{id}",
  "dct:title": "<collection.title>",
  "dct:description": "<collection.description ou repli titre, même règle qu'en SP-12a §2.2 T2>",
  "dct:issued": { "@value": "<created_at RFC3339>", "@type": "xsd:dateTime" },
  "dct:modified": { "@value": "<updated_at RFC3339>", "@type": "xsd:dateTime" },
  "dct:license": { "@id": "http://publications.europa.eu/resource/authority/licence/OTHER" },
  "dct:accessRights": { "@id": "http://publications.europa.eu/resource/authority/access-right/PUBLIC" },
  "dct:publisher": { "@id": "<base>/dcat/publisher" },
  "dct:spatial": {
    "@type": "dct:Location",
    "locn:geometry": { "@value": "<GeoJSON bbox polygon>", "@type": "https://www.iana.org/assignments/media-types/application/vnd.geo+json" }
  },
  "dct:temporal": { "@type": "dct:PeriodOfTime", "dcat:startDate": { "@value": "<created_at>", "@type": "xsd:dateTime" } },
  "dcat:distribution": [ /* dcat:Distribution, §5.4 */ ]
}
```

(`dcat:keyword`, `dcat:theme` omis — §2.7.)

### 5.4 `dcat:Distribution`

Une par point d'accès existant, jamais une donnée copiée :

```json
[
  {
    "@type": "dcat:Distribution",
    "dct:title": "GeoJSON (OGC API Features)",
    "dcat:accessURL": { "@id": "<base>/collections/{id}/items" },
    "dcat:mediaType": { "@id": "https://www.iana.org/assignments/media-types/application/geo+json" },
    "dct:format": { "@id": "http://publications.europa.eu/resource/authority/file-type/GEOJSON" }
  },
  {
    "@type": "dcat:Distribution",
    "dct:title": "STAC item-search",
    "dcat:accessURL": { "@id": "<base>/stac/collections/{id}/items" },
    "dct:format": { "@id": "http://publications.europa.eu/resource/authority/file-type/JSON" }
  }
]
```

## 6. Permissions & visibilité (non négociable — réutilise l'existant)

- Portée = **exactement celle de STAC** (SP-12a §6) : `list_visible_collections`
  pour le dump, `get_readable_collection` pour un dataset unique.
- **Anonyme → tenant `default` + publié/public seulement**, résolu via
  `get_or_create_default_tenant` (A33). Collection non lisible → **404
  non-fuyant** sur `GET /dcat/datasets/{id}` (pas de fuite d'existence).
- Le consommateur réel visé (moissonneur data.gouv.fr) est anonyme — mais la
  route ne fait aucune supposition dessus : un appelant authentifié obtient son
  propre périmètre de permission, symétrique à STAC.
- **Test adversarial dédié** (même patron que SP-12a Task 8) : anonyme ne voit
  que le public sur `/dcat/catalog` et `/dcat/datasets/{id}` ; aucune fuite
  cross-tenant.

## 7. Pas de pagination — dump complet assumé

`GET /dcat/catalog` embarque **tous** les datasets visibles en une réponse,
sans `limit`/`next`. Assumé (YAGNI, cf. A21 « peu de code ») : un moissonneur
DCAT-AP récupère typiquement **un document**, pas un flux paginé (à la
différence de l'item-search STAC, pensé pour des clients qui filtrent). Risque
documenté §11 si le catalogue grossit fortement.

## 8. Tests & validation de conformité

- **Gate CI (bloquant, offline, always-run).** Les serializers purs validés en
  deux temps :
  1. Round-trip **`rdflib`** (`Graph().parse(data=json.dumps(doc), format="json-ld")`)
     — preuve que le JSON-LD produit est syntaxiquement valide (parse sans
     exception, triples non vides), même rôle que le parsing GeoJSON dans
     `stac-pydantic`.
  2. **`pyshacl`** contre les shapes SHACL officielles **DCAT-AP** vendues
     hors-ligne dans `core/tests/fixtures/dcat/dcat-ap-SHACL.ttl` (copie
     statique versionnée du dépôt public SEMICeu/DCAT-AP — **jamais** de
     récupération réseau en test, même discipline que les fixtures
     `stac-pydantic`). `pyshacl`/`rdflib` ajoutés en **dépendance de test**
     (`pyproject.toml`), comme `stac-pydantic` en SP-12a.
- **Intégration (marqueur `postgis`).** Seed d'une collection, chaque endpoint
  exercé : dump avec ≥1 dataset, dataset unique dé-référençable, 404 non-fuyant,
  portée RLS anonyme, `dct:spatial` reprojeté (réutilise directement le test
  Lambert-93 de SP-12a Task 4 comme preuve que `estimated_bbox_4326` est bien le
  même chemin, pas une redite).
- **Smoke d'acceptation documenté (non bloquant).** Le vrai validateur DCAT-AP
  data.gouv.fr (ou son équivalent SHACL en ligne) contre une instance vive
  seedée — même patron que le smoke `stac-api-validator` de SP-12a. **Si ce
  smoke révèle un champ obligatoire non couvert par le profil SHACL générique
  vendu hors-ligne** (ex. `dcat:theme` exigé par le profil FR strict), le
  constat est documenté ici en suivi, **pas deviné par avance** dans ce spec.

## 9. Dérive OpenAPI

Nouveaux endpoints → `core/openapi.json` et
`shell/src/api/generated/core-schema.d.ts` régénérés (même si le shell ne les
appelle pas — le job `api-types-drift` les verrait sinon diverger, même
discipline que SP-12a Task 9).

## 10. Critères d'acceptation (sous-ensemble SP-12b de SP-12)

1. `GET /dcat/catalog` renvoie un document JSON-LD `dcat:Catalog` valide
   (`Content-Type: application/ld+json`) embarquant un `dcat:Dataset` par
   collection visible, chacun avec ≥1 `dcat:Distribution` pointant un endpoint
   de données réel et navigable (GeoJSON OGC API Features).
2. `GET /dcat/datasets/{id}` dé-référence individuellement un `dcat:Dataset` ;
   404 non-fuyant sur non-lisible/inexistant.
3. Le DCAT anonyme n'expose que le publié/public (test adversarial, sans fuite
   d'existence ni cross-tenant) — même garantie que STAC.
4. `rdflib` parse tout payload produit sans exception ; `pyshacl` valide contre
   les shapes DCAT-AP officielles vendues hors-ligne, dans la suite de tests
   (bloquant) ; le smoke contre le validateur data.gouv.fr passe ou documente
   précisément ce qui manque (non bloquant).

## 11. Risques & simplifications assumées

- **`dct:license`/`dct:accessRights`** : le premier reste une constante
  générique EU « autre » (§2.3, symétrique à STAC) ; le second est dérivé
  correctement de `is_public`, jamais une constante aveugle (§2.2).
- **`dct:spatial` en repli monde silencieux** (§2.4) : DCAT-AP n'a pas
  d'équivalent au champ `note` custom de STAC pour documenter l'approximation
  in-band — le repli reste invisible dans la charge utile, documenté ici
  seulement.
- **`dcat:keyword`/`dcat:theme` omis** (§2.7) : gap v0 assumé plutôt qu'une
  valeur inventée ; le smoke data.gouv.fr dira empiriquement si c'est bloquant
  pour un profil FR strict.
- **Dump non paginé** (§7) : suffisant à l'échelle catalogue actuelle : le
  moissonnage massif appartient à SP-12c (côté *consommation*, pas ce SP côté
  *production*).
- **Shapes SHACL vendues hors-ligne** : une copie statique peut driver du
  profil réellement appliqué par data.gouv.fr au fil du temps — le smoke non
  bloquant est le garde-fou réel, pas la gate CI offline (qui vise la
  conformité DCAT-AP de base, pas le profil FR exact).
