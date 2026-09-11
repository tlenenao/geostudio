# REV-102/GAP-08 — Géocodage : contrôle de recherche d'adresse (BAN)

Date : 2026-09-07. Ferme le chantier **4.13** de la vague 4
(`docs/vision/2026-08-20-revue-projet-et-plan-daction.md:408`), recensé par
la revue SP-42 sous **GAP-08** (`docs/revue/2026-09-04-analyse-gaps.md:169`)
et **REV-102** (`docs/revue/2026-09-04-backlog.md:1011`) :

> Chantier 4.13 (géocodage, fournisseur enfichable BAN
> `api-adresse.data.gouv.fr`) absent, aucun contrôle de carte ni widget de
> recherche d'adresse.

**Ce chantier n'a PAS été discuté en détail avec Tanguy** (contrairement aux
autres chantiers GAP fermés par les SP listées dans `CLAUDE.md` § Livré, qui
avaient chacune une spec relue avant exécution). En l'absence d'arbitrage
produit, ce document choisit délibérément la lecture la plus étroite du
texte du chantier 4.13 et documente chaque exclusion explicitement (§5) —
charge à Tanguy de redemander une extension s'il en veut une.

## Contexte

**Vérifié avant d'écrire ce document, contre le dépôt réel** (piège
CLAUDE.md n°3, ne jamais supposer) :

- Aucun module `core/app/geocoding/` n'existe. Aucun composant
  `shell/src/map/*Geocod*`/`*AddressSearch*` n'existe. `grep -ri geocod`
  sur `core/` et `shell/src/` ne trouve rien hors ce document.
- Le patron « fournisseur enfichable » cité par le chantier 4.13 existe
  déjà deux fois dans le dépôt et est directement réutilisable :
  - `core/app/search/providers.py::EmbeddingProvider` (SP-7) — `Protocol`
    + une implémentation réseau + un réglage par variable d'environnement.
  - `core/app/copilot/llm_provider.py::LLMProvider` (SP-20) — même patron,
    plus un exemple récent de garde d'egress dédiée
    (`core/app/copilot/egress.py`) et de factory (`get_llm_provider()`
    lisant `CORE_LLM_PROVIDER`).
- 4 gardes d'egress SSRF existent déjà, une par domaine consommateur
  (`app.harvest.egress`, `app.pipelines.egress`, `app.alerts.egress`,
  `app.copilot.egress`) — chacune sa propre variable d'environnement
  d'allowlist, doctrine documentée explicitement dans
  `app/copilot/egress.py` (« chacun sa propre variable d'environnement,
  pour la même raison qu'eux »). Ce chantier ajoute une 5e garde,
  `app.geocoding.egress`, même doctrine.
- `shell/src/map/MapView.tsx` documente déjà, en commentaire, la règle qui
  s'applique ici : les fetches vers le cœur pour des besoins propres à la
  carte (pièces jointes de popup, authentification des tuiles 3D hébergées)
  passent par un **fetch nu via `getCoreUrl`/`getAuthToken`, jamais
  `useItemClient()`/React Query** — parce que `MapView` doit continuer de
  fonctionner hors `ItemClientProvider` (export d'app SP-18b « Connecté »,
  qui passe `getCoreUrl`/`getAuthToken` sans monter le client complet).
  Le contrôle de recherche d'adresse suit exactement cette même règle
  (§3.2) : ce n'est pas une exception nouvelle, c'est le patron déjà en
  vigueur dans ce fichier précis.
- `shell/src/map/MapView.tsx` a déjà un précédent direct pour « monter un
  contrôle optionnel sur la carte, jamais par défaut » :
  `interactiveTools?: boolean` (SP-27) mont e `MapMeasureSketchToolbar`
  quand l'appelant le demande, jamais sinon. `MapEditorPage.tsx` le passe
  inconditionnellement (`interactiveTools` sans valeur, donc `true`) sur
  l'onglet carte ; `mapWidget.tsx` le passe conditionnellement
  (`interactiveTools={ctx.mode !== "edit"}` — actif en aperçu/exécution,
  pas pendant l'édition du widget lui-même, pour ne pas interférer avec la
  manipulation du widget sur le canevas).
- **Vérifié par appel réel à l'API BAN** (`curl`, 2026-09-07, aucune clé,
  aucun en-tête), pas supposé (piège CLAUDE.md n°3) :

  ```
  GET https://api-adresse.data.gouv.fr/search/?q=12+rue+de+la+republique+Tulle&limit=3
  → 200, Content-Type JSON, GeoJSON FeatureCollection :
  {
    "type": "FeatureCollection",
    "features": [
      {
        "type": "Feature",
        "geometry": {"type": "Point", "coordinates": [5.482758, 45.298546]},
        "properties": {
          "label": "12 Rue de la République 38210 Tullins",
          "score": 0.7638590615835777,
          "housenumber": "12", "id": "38517_0580_00012",
          "banId": "62431716-...", "name": "12 Rue de la République",
          "postcode": "38210", "citycode": "38517", "x": 894565.19,
          "y": 6469634.76, "city": "Tullins",
          "context": "38, Isère, Auvergne-Rhône-Alpes",
          "type": "housenumber", "importance": 0.56374, "depcode": "38",
          "street": "Rue de la République", "_type": "address"
        }
      },
      ...
    ],
    "query": "12 rue de la republique Tulle"
  }
  ```

  Points de contrat confirmés empiriquement, pas dans la doc (qui aurait pu
  avoir dérivé) :
  - `coordinates` est `[lon, lat]` (GeoJSON standard), **pas** `[lat, lon]`.
  - `properties.type` a été observé avec 4 valeurs distinctes sur des
    requêtes réelles : `housenumber` (adresse précise), `street` (voie
    seule, testé avec `type=street`), `locality` (lieu-dit), `municipality`
    (commune, testé avec `q=Tulle`) — utilisé pour choisir un niveau de
    zoom à la sélection (§3.3).
  - Une requête sans résultat renvoie `200` avec `"features": []`, pas une
    erreur — testé avec une chaîne aléatoire improbable.
  - `q` vide ou absent renvoie **400** (`Failed parsing query`) — testé
    (`?q=`, sans aucun paramètre, `?q=%20`).
  - `limit` est borné par l'API elle-même à l'intervalle `[1, 50]` — testé
    (`limit=0` → 400, `limit=100` → 400 `"must be an integer between 1 and
    50"`). Notre propre proxy impose un plafond plus bas (§3.3, 20) : une
    liste déroulante n'a jamais besoin de 50 résultats, et border plus bas
    limite le volume renvoyé par tout futur fournisseur qui n'aurait pas la
    même borne native.
  - Aucune clé, aucun en-tête, aucune authentification requise — service
    public gratuit, confirmé par le code 200 sans configuration.

## Décision de scope — minimal et réversible

Aucun arbitrage détaillé n'existe pour ce chantier (cf. avertissement en
tête de document). Périmètre retenu, au plus près de la phrase du chantier
4.13 (« fournisseur enfichable... premier fournisseur BAN... exposé en
contrôle de carte et en widget ») :

1. **Un seul verbe : rechercher une adresse texte libre et recentrer/zoomer
   la carte sur le résultat choisi.** Pas de géocodage inversé, pas de
   géocodage par lot, pas de sauvegarde du résultat.
2. **Un seul fournisseur implémenté** (BAN), derrière un contrat
   `GeocodingProvider` qui en admettrait un second sans toucher aux routes
   ni au contrôle carte — la seule promesse concrète du mot « enfichable »
   que ce plan tient, sans construire de mécanisme de sélection UI ou de
   configuration par tenant (aucun signal que ça sera nécessaire un jour).
3. **Aucun nouvel objet de plateforme.** Ni table, ni `kind` d'item, ni
   champ persistant dans `MapConfig`/`AppConfig`. Le résultat d'une
   recherche est éphémère, exactement comme une mesure ou un croquis
   (SP-27) — jamais renvoyé au serveur autrement que pour la requête de
   recherche elle-même.
4. **Aucune capacité instance-wide (`CORE_..._ENABLED`).** Contrairement à
   `CORE_ETL_ENABLED`/`CORE_LLM_PROVIDER`, ce service ne coûte rien à
   l'opérateur (gratuit, sans clé, sans configuration) et ne présente
   aucun risque à être monté par défaut — la route est inconditionnelle,
   comme `stac`/`dcat`/`harvest`/`usage`. Il n'y a donc rien à activer :
   « ça marche tout de suite », qui est explicitement le critère de sortie
   du chantier 4.13.
5. **Aucun outil MCP.** Ni demandé par le chantier 4.13, ni par REV-102 ;
   le copilote (SP-20) n'a aucun besoin identifié de recentrer une carte
   par adresse pour l'instant — s'ajoute librement plus tard sans rien
   changer à ce plan (le contrat `GeocodingProvider` est déjà consommable
   depuis un futur outil MCP).
6. **Aucune bascule auteur pour désactiver le contrôle par carte/widget.**
   Même doctrine que `interactiveTools` (§Contexte) : actif partout où une
   carte interactive est réellement montrée, jamais persistant dans la
   config. Une bascule par item ajouterait un champ `MapConfig` (migration
   implicite du contrat de config, régénération OpenAPI/TS, piège
   CLAUDE.md n°5) pour un besoin non demandé.

## Architecture

### 1. Cœur — `core/app/geocoding/` (nouveau module)

Nouveau domaine de couche, positionné dans le contrat `import-linter`
(`core/pyproject.toml`, `[[tool.importlinter.contracts]] layers`) juste
**en dessous de `app.harvest`** (même famille : un domaine dont la seule
route effectue un appel sortant gardé, sans dépendre d'aucun autre domaine
de plus haut niveau) et **au-dessus de `app.pipelines`**. Ses seuls imports
descendants : `app.auth.dependency` (`get_current_user`) et
`app.users.models.User` — tous deux très bas dans le contrat, aucune
exemption `ignore_imports` nécessaire (vérifié : aucun cycle, ce module
n'est importé par personne d'autre que `app.main`).

```
core/app/geocoding/
  __init__.py
  provider.py   # GeocodeResult (dataclass), GeocodingProvider (Protocol),
                # BanGeocodingProvider, get_geocoding_provider()
  egress.py     # garde SSRF dédiée, patron app.harvest.egress
  routes.py     # GET /geocoding/search
```

#### 1.1 `provider.py` — contrat enfichable

Même patron que `app/copilot/llm_provider.py` :

```python
@dataclass(frozen=True)
class GeocodeResult:
    label: str
    lon: float
    lat: float
    score: float
    type: str  # "housenumber" | "street" | "locality" | "municipality" | autre valeur BAN non listée, transmise telle quelle
    city: str | None = None
    postcode: str | None = None

class GeocodingProvider(Protocol):
    def search(self, query: str, limit: int) -> list[GeocodeResult]: ...
```

Synchrone (pas de `Protocol` async) : contrairement à `LLMProvider.chat`
(appelé depuis une route `async def` avec un budget de tour de 30s sur
plusieurs itérations), cette route est un aller-retour HTTP unique et
rapide — même choix que `app.harvest.live_query.fetch_query`/les routes
`GET /datasets/{id}/arcgis/items` (routes `def`, pas `async def`, FastAPI
les exécute dans son threadpool). Documenté explicitement dans le
docstring du module pour qu'un futur lecteur ne s'étonne pas de l'absence
de variante async, contrairement au copilote.

`BanGeocodingProvider` :

```python
class BanGeocodingProvider:
    def __init__(self, *, api_url: str, http_client: httpx.Client | None = None):
        self._api_url = api_url  # défaut : CORE_GEOCODING_BAN_URL ou
                                  # "https://api-adresse.data.gouv.fr/search/"
        self._client = http_client  # seam d'injection pour les tests
                                     # (httpx.MockTransport), même patron
                                     # que OpenAICompatibleLLMProvider

    def search(self, query: str, limit: int) -> list[GeocodeResult]:
        params = {"q": query, "limit": str(limit)}
        if self._client is not None:
            response = self._client.get(self._api_url, params=params)
        else:
            with build_guarded_client() as client:
                response = client.get(self._api_url, params=params)
        response.raise_for_status()
        data = response.json()
        return [
            GeocodeResult(
                label=f["properties"]["label"],
                lon=f["geometry"]["coordinates"][0],
                lat=f["geometry"]["coordinates"][1],
                score=f["properties"].get("score", 0.0),
                type=f["properties"].get("type", "unknown"),
                city=f["properties"].get("city"),
                postcode=f["properties"].get("postcode"),
            )
            for f in data.get("features", [])
        ]
```

`get_geocoding_provider()` :

```python
def get_geocoding_provider() -> GeocodingProvider:
    kind = os.environ.get("CORE_GEOCODING_PROVIDER")
    if kind is None or kind == "ban":
        api_url = os.environ.get(
            "CORE_GEOCODING_BAN_URL", "https://api-adresse.data.gouv.fr/search/"
        )
        return BanGeocodingProvider(api_url=api_url)
    raise ValueError(f"unknown CORE_GEOCODING_PROVIDER: {kind}")
```

#### 1.2 `egress.py` — garde SSRF, **écart assumé et documenté** vis-à-vis
des 4 gardes existantes

Les 4 gardes existantes (`harvest`/`pipelines`/`alerts`/`copilot`) ont
toutes la même règle : allowlist vide (défaut) = tout hôte externe est
autorisé, seules les plages réseau internes sont bloquées — cohérent avec
leur cas d'usage, où **l'hôte cible est fourni par un utilisateur ou un
opérateur** (URL de moissonnage, webhook d'alerte, endpoint LLM
compatible OpenAI).

Ici, l'hôte cible n'est **fourni par personne** : il est fixé par le code
(`BanGeocodingProvider`'s `api_url` par défaut) et ne varie que si un
opérateur redéfinit explicitement `CORE_GEOCODING_BAN_URL` — un réglage de
déploiement, pas une entrée utilisateur. Reproduire la doctrine « vide =
tout autoriser » ouvrirait donc, par défaut, un SSRF total sur une route
qui n'a jamais besoin de parler à autre chose que BAN. Décision : **la
garde de `app.geocoding` retombe sur une allowlist par défaut non vide**
(`{"api-adresse.data.gouv.fr"}`) quand `CORE_GEOCODING_EGRESS_ALLOWLIST`
n'est pas réglée — fail-closed par défaut, à l'inverse des 4 gardes
sœurs. Conséquence documentée dans le docstring du module : un opérateur
qui redéfinit `CORE_GEOCODING_BAN_URL` vers un miroir auto-hébergé de la
BAN doit **aussi** ajouter cet hôte à `CORE_GEOCODING_EGRESS_ALLOWLIST`,
sinon la garde bloque toute requête (échec explicite en 502, jamais un
SSRF silencieusement permis).

Pas de plafond de taille de réponse dédié (contrairement à
`app.harvest.egress`, qui streame et coupe à
`CORE_HARVEST_MAX_RESPONSE_BYTES`) : `app.harvest` récupère des documents
de taille arbitraire fournis par un tiers (catalogues STAC, capacités
WMS) ; ici la réponse est bornée par construction (`limit` plafonné à 20
par notre route, BAN lui-même refuse `limit > 50`), donc quelques
kilooctets au pire — même choix d'absence de plafond que
`app.copilot.egress`/`app.alerts.egress`, qui n'en ont pas non plus.

Sinon, code identique aux 4 gardes existantes (résolution DNS, blocage
loopback/privé/link-local/réservé/multicast/unspecified, résiduel
DNS-rebinding TOCTOU documenté à l'identique) : `build_guarded_client()`
sur `httpx.Client`/`httpx.BaseTransport` (synchrone, comme
`app.harvest.egress`/`app.alerts.egress`, pas `app.copilot.egress` qui est
asynchrone pour une raison propre au copilote qui ne s'applique pas ici).

#### 1.3 `routes.py` — `GET /geocoding/search`

```python
router = APIRouter()

_MAX_LIMIT = 20
_MAX_QUERY_CHARS = 200

class GeocodeResultOut(BaseModel):
    label: str
    lon: float
    lat: float
    score: float
    type: str
    city: str | None = None
    postcode: str | None = None

class GeocodeSearchResponse(BaseModel):
    results: list[GeocodeResultOut]

@router.get("/geocoding/search")
def search_address(
    q: str = Query(..., min_length=1, max_length=_MAX_QUERY_CHARS),
    limit: int = Query(5, ge=1, le=_MAX_LIMIT),
    user: User = Depends(get_current_user),
) -> GeocodeSearchResponse:
    provider = get_geocoding_provider()
    try:
        results = provider.search(q, limit)
    except EgressBlockedError as exc:
        raise HTTPException(
            status_code=502,
            detail=f"garde d'egress géocodage : cible bloquée ({exc})",
        ) from exc
    except httpx.HTTPError as exc:
        raise HTTPException(
            status_code=502, detail="service de géocodage indisponible"
        ) from exc
    return GeocodeSearchResponse(
        results=[GeocodeResultOut(**r.__dict__) for r in results]
    )
```

Aucune garde de privilège au-delà de l'authentification — même niveau que
`GET /harvest/layers`/`GET /harvest/feature-layers` (lecture pure, sans
donnée sensible du tenant, consultée à chaque frappe par un contrôle de
carte). Pas de garde de mode démo/lecture-seule : c'est une lecture,
`is_read_only_mode()` ne bloque que les écritures.

Montée **inconditionnellement** dans `core/app/main.py`, aux côtés de
`harvest_routes`/`stac_routes`/`dcat_routes` (bloc de routeurs sans garde
de capacité) — pas dans le bloc `if is_..._enabled():` en bas de la
fonction (§Décision de scope, point 4).

#### 1.4 Rate limiting (`app/ratelimit/limiter.py`)

Le seul appel sortant potentiellement à chaque frappe de l'utilisateur —
même classe de risque que les 2 routes ArcGIS live-query (GAP-61.b,
SP-45) et le budget dédié `harvest` (10/60s, écrit après la découverte que
`LayerPicker.tsx` interroge sans debounce à chaque frappe). Le contrôle de
recherche d'adresse **debounce côté client** (§2.2, 350 ms + 3 caractères
minimum) — contrairement à `LayerPicker.tsx` — mais un budget serveur reste
la seule protection qui ne dépend pas du bon comportement du client :

```python
_GEOCODING_RE = re.compile(r"^/v1/geocoding/search$")
...
_BUDGETS = {
    ...,
    "geocoding": 20,
}
...
def route_group(path, method, export_path_re):
    ...
    if _GEOCODING_RE.match(path):
        return "geocoding"
    ...
```

#### 1.5 Variables d'environnement (`.env.example`, `docker-compose.yml`)

Trois nouvelles, toutes optionnelles (valeurs par défaut fonctionnelles
sans rien régler) :

- `CORE_GEOCODING_PROVIDER` — vide/absent (défaut) ou `ban` (seule valeur
  reconnue aujourd'hui).
- `CORE_GEOCODING_BAN_URL` — vide (défaut : URL publique BAN en dur dans
  le code).
- `CORE_GEOCODING_EGRESS_ALLOWLIST` — vide (défaut : `api-adresse.data.gouv.fr`
  uniquement, cf. §1.2 — **différent** des autres allowlists d'egress où
  vide = tout autoriser, souligné en commentaire dans `.env.example` pour
  qu'un opérateur qui connaît déjà `CORE_LLM_EGRESS_ALLOWLIST` ne suppose
  pas la même sémantique).

Câblées uniquement sur le service `core` de `docker-compose.yml` (pas
`worker` : aucun job asynchrone n'est concerné, contrairement à
`CORE_HARVEST_EGRESS_ALLOWLIST` qui sert aussi au worker de moissonnage).

### 2. Shell — contrôle de carte

#### 2.1 `shell/src/map/addressSearch.ts` (nouveau, logique pure)

Même séparation que `measureSketch.ts`/`MapMeasureSketchToolbar.tsx` :
logique testable sans DOM, composant React mince par-dessus.

```ts
export type GeocodeResult = {
  label: string;
  lon: number;
  lat: number;
  score: number;
  type: string;
  city?: string;
  postcode?: string;
};

// Heuristique de zoom par type BAN (§Contexte, valeurs observées
// empiriquement) : un futur type non listé retombe sur le zoom le plus
// prudent (le plus dézoomé), jamais une exception.
export function zoomForResultType(type: string): number {
  switch (type) {
    case "housenumber":
    case "street":
      return 17;
    case "locality":
      return 14;
    case "municipality":
      return 13;
    default:
      return 12;
  }
}

export async function searchAddress(
  coreUrl: string,
  getAuthToken: (() => string | undefined) | undefined,
  query: string,
  limit = 5,
): Promise<GeocodeResult[]> {
  const token = getAuthToken?.();
  const url = `${coreUrl}/geocoding/search?q=${encodeURIComponent(query)}&limit=${limit}`;
  const res = await fetch(url, { headers: token ? { Authorization: `Bearer ${token}` } : {} });
  if (!res.ok) throw new Error(`Request failed: ${res.status} geocoding/search`);
  const data = (await res.json()) as { results?: GeocodeResult[] };
  return data.results ?? [];
}
```

`coreUrl` attendu déjà versionné (`.../v1`, cf. `createBase()` — le même
champ que `getCoreUrl()` renvoie côté `MapView`).

#### 2.2 `shell/src/map/AddressSearchControl.tsx` (nouveau, composant)

```tsx
export function AddressSearchControl({
  getCoreUrl,
  getAuthToken,
  onSelect,
}: {
  getCoreUrl?: () => string;
  getAuthToken?: () => string | undefined;
  onSelect: (result: GeocodeResult) => void;
}) { ... }
```

- Champ texte contrôlé + liste de résultats (`<ul>` positionnée sous le
  champ, fermée après sélection ou `Escape`).
- **Debounce 350 ms**, déclenchement seulement à partir de **3
  caractères** (constantes nommées, pas magiques) — décision de confort,
  pas une contrainte de l'API BAN (qui n'impose aucun minimum, testé),
  motivée par le précédent documenté de `LayerPicker.tsx` (§1.4).
- `getCoreUrl`/`getAuthToken` absents (hors `ItemClientProvider`, export
  statique sans core) ⇒ le contrôle se rend mais n'effectue jamais de
  requête — dégrade silencieusement, pas d'erreur affichée pour une
  absence de capacité attendue.
- Erreur réseau/502 de la route ⇒ message d'erreur inline traduit
  (`t("addressSearch.error")`), pas une exception non gérée.
- i18n : toutes les chaînes via `t()` — `shell/src/map/` est un des 4
  répertoires couverts par `shell/scripts/check-i18n-coverage.mjs`
  (garde permanente dans `npm run lint`, SP-57a), nouvelles clés dans
  `shell/src/i18n/catalog.fr.ts`.
- `onSelect` ne fait **aucun** fetch ni `flyTo` lui-même : l'appelant
  (`MapView`) reste seul propriétaire de l'instance `maplibregl.Map`,
  même séparation que `MapMeasureSketchToolbar` (qui reçoit `map` en prop
  au lieu de le recevoir).

#### 2.3 `shell/src/map/MapView.tsx`

Nouvelle prop optionnelle, même doctrine que `interactiveTools` (jamais
montée par défaut, commentaire de type identique) :

```ts
// Monte le contrôle de recherche d'adresse (REV-102/GAP-08) : jamais
// câblé par défaut, comme interactiveTools.
addressSearch?: boolean;
```

Rendu conditionnel, à côté du montage existant d'`interactiveTools` :

```tsx
{addressSearch && readyMap && (
  <AddressSearchControl
    getCoreUrl={getCoreUrl}
    getAuthToken={getAuthToken}
    onSelect={(r) => readyMap.flyTo({ center: [r.lon, r.lat], zoom: zoomForResultType(r.type) })}
  />
)}
```

Positionné visuellement à l'opposé de la légende (ex. coin supérieur
gauche) — pas de recouvrement avec `MapLegend`/`MapMeasureSketchToolbar`,
vérifié par un test de rendu simultané des trois.

#### 2.4 Sites de montage

- `shell/src/pages/MapEditorPage.tsx` : `addressSearch` (sans valeur, donc
  `true`) sur le `<MapView>` de l'onglet `work` (même traitement que
  `interactiveTools` sur cette même carte) — **pas** sur la carte du mode
  `isExportRender` (une capture d'export n'a aucun utilisateur pour taper
  dans un champ, même raison que `interactiveTools` n'y est pas non plus
  passé aujourd'hui).
- `shell/src/builder/widgets/mapWidget.tsx` : `addressSearch={ctx.mode !==
  "edit"}` sur le `<MapView>` du `Component`, exactement le même prédicat
  que `interactiveTools` déjà présent à cet endroit.

Aucun autre site de montage de `MapView` dans le dépôt (vérifié :
`grep -rn "<MapView" shell/src` avant d'écrire ce document) — donc aucun
autre fichier à toucher pour la couverture éditeur+widget demandée par le
chantier 4.13.

### 3. Ce que ce chantier NE touche PAS

- `shell/src/api/itemClient.ts`/`types.ts`/`domains/*` : aucune méthode
  ajoutée (§Contexte — `MapView` fait son propre fetch, comme pour les
  pièces jointes de popup et l'authentification tuiles 3D). Aucun impact
  sur `StaticItemClient.ts`.
- `shell/src/auth/capabilities.ts` : aucune capacité, aucun domaine — ce
  n'est pas un nouveau domaine produit, c'est un contrôle à l'intérieur du
  domaine « Cartes » existant.
- `MapConfig`/`AppConfig` (schéma, migrations, OpenAPI côté forme des
  objets) : aucun champ ajouté. Le diff OpenAPI/types TS attendu à ce
  chantier est **uniquement** la nouvelle route `GET /geocoding/search` et
  son schéma de réponse — aucun schéma de config existant ne change de
  forme.
- CSP (`core/app/security/`, si présent sur la branche d'exécution) :
  aucune modification. Le navigateur ne parle jamais à
  `api-adresse.data.gouv.fr` — seul le cœur le fait — donc aucun hôte
  supplémentaire n'a besoin d'entrer dans `connect-src`/`img-src`.

## Critères de sortie

- `GET /v1/geocoding/search?q=12+rue+de+la+republique+Tulle` (utilisateur
  authentifié) répond `200` avec au moins un résultat dont le label
  contient « République ».
- Taper « 12 rue de la République, Tulle » dans le contrôle de recherche
  de l'éditeur de carte (`/maps/{id}`, onglet carte) puis sélectionner un
  résultat recentre et zoome la carte dessus — prouvé au niveau unitaire
  (`MapView.test.tsx`, contre le mock MapLibre qui expose `flyToArgs`) :
  ce dépôt n'expose délibérément aucun global de test sur l'instance
  MapLibre réelle (précédent documenté dans
  `map-measure-sketch.spec.ts`), donc l'E2E ne peut pas — et ne doit pas
  chercher à — observer l'état interne de la caméra ; il couvre à la
  place le parcours utilisateur (recherche → sélection, sur le vrai
  composant monté dans `/maps/{id}`) et la garantie réseau ci-dessous.
- Le même contrôle, monté par le widget carte de l'App Builder, fonctionne
  en aperçu/exécution (`ctx.mode !== "edit"`) — absent pendant l'édition
  du widget sur le canevas.
- Aucune requête réseau du navigateur ne vise
  `api-adresse.data.gouv.fr` : uniquement `.../v1/geocoding/search` sur
  l'origine du cœur (vérifiable en E2E : le mock ne répond que sur
  `https://core.test/v1/geocoding/search`, jamais sur un domaine BAN, et
  un test dédié échoue si le contrôle appelait BAN directement — une
  route `page.route("https://api-adresse.data.gouv.fr/**", ...)` détecte
  l'appel s'il se produit).
- Un hôte hors allowlist (test avec un hôte falsifié) est bloqué par la
  garde d'egress et remonte en `502`, jamais un appel sortant réel.
- `CORE_GEOCODING_PROVIDER` non réglé ou réglé à `ban` fonctionne de façon
  identique (valeur par défaut) ; une valeur inconnue échoue explicitement
  (`ValueError`) plutôt que de retomber silencieusement sur BAN.
- Une recherche vide n'est jamais envoyée par le contrôle (garde client) ;
  le cœur refuse lui-même une requête `q` vide en 422 (défense en
  profondeur, testé indépendamment du comportement du client).
- Diff `openapi.json`/`core-schema.d.ts` non vide et cohérent (une seule
  route nouvelle, un seul schéma de réponse nouveau).
- Suite complète core + shell (unitaires) verte ; au moins un test E2E
  dédié (`shell/e2e/map-address-search.spec.ts`, patron
  `map-measure-sketch.spec.ts`) couvrant le scénario de l'éditeur de carte.

## Hors périmètre explicite

- **Géocodage par lot** (import CSV d'adresses à géocoder en masse) —
  chantier distinct, non demandé par 4.13/GAP-08/REV-102.
- **Fournisseurs alternatifs ou payants** (Google Maps, HERE, Mapbox,
  Nominatim/OSM auto-hébergé, adresse.data.gouv.fr en variante payante...)
  — le contrat `GeocodingProvider` les admettrait sans rien casser, mais
  aucun n'est implémenté ici.
- **Géocodage inversé** (coordonnées → adresse) — la BAN expose un
  endpoint `/reverse/` distinct, non consommé par ce chantier.
- **Sauvegarde de l'adresse recherchée** en base, comme propriété d'un
  item, ou comme nouvel objet de plateforme — un résultat de recherche
  est aussi éphémère qu'une mesure/un croquis (SP-27), jamais persisté.
- **Outil MCP de géocodage** — non demandé, ajoutable librement plus tard
  sans toucher à ce plan (le contrat `GeocodingProvider` est déjà
  consommable depuis un futur outil).
- **Bascule auteur pour activer/désactiver le contrôle** par carte ou par
  widget — toujours actif là où l'éditeur de carte et le widget carte le
  montent aujourd'hui, comme `interactiveTools`. Aucun champ `MapConfig`
  nouveau.
- **Autocomplétion « as you type » avancée** (surlignage des termes
  correspondants, historique de recherche, favoris) — une liste simple de
  résultats cliquables, rien de plus.
- **Cache serveur des résultats de recherche** (contrairement à
  `app.harvest.live_query`, qui cache 20s les réponses ArcGIS) — un
  aller-retour BAN est déjà rapide et peu coûteux ; pas de cache ajouté,
  décision assumée plutôt qu'un oubli.
- **Fonctionnement dans l'export statique autoporté** (SP-18a) : cet
  export n'a par construction aucun cœur à joindre — le contrôle s'y rend
  mais ne fait jamais de requête (§2.2), ce qui n'est pas un objectif
  fonctionnel de ce chantier, seulement un garde-fou pour ne pas planter.
- **Audit d'accessibilité dédié** au-delà de la baseline attendue de tout
  nouveau composant (`label` associé, focus clavier, rôle ARIA
  approprié sur la liste de résultats) — l'échantillon a11y de SP-57a
  (9 pages) n'est pas étendu par ce chantier (`REV-178`, déjà documenté
  comme hors périmètre par SP-57a).

## Auto-revue

- Pas de TBD ni de point laissé en suspens : chaque décision de §1/§2 a sa
  justification écrite, chaque exclusion de §Hors périmètre a sa raison.
- Pas de contradiction : la seule règle qui diffère volontairement du
  reste du dépôt (allowlist d'egress non vide par défaut, §1.2) est
  signalée à l'endroit où un lecteur la découvrirait naturellement
  (§1.2) et rappelée dans les critères de sortie et dans `.env.example`
  (§1.5) — pas seulement énoncée une fois puis oubliée.
- Portée bornée : un seul module cœur, deux fichiers shell nouveaux, deux
  fichiers shell modifiés (sites de montage), aucune migration Alembic,
  aucun nouveau kind d'item, aucune nouvelle capacité.
- Vérifié empiriquement plutôt que supposé (piège CLAUDE.md n°3) : forme
  exacte de la réponse BAN, comportement sur requête vide/limite invalide,
  absence d'authentification requise, tous confirmés par `curl` réel
  avant d'écrire ce document (§Contexte).

## Décomposition en tâches (indicatif, affiné en plan)

1. `app.geocoding.egress` (garde SSRF, allowlist par défaut non vide) +
   tests.
2. `app.geocoding.provider` (`GeocodeResult`, `GeocodingProvider`,
   `BanGeocodingProvider`, `get_geocoding_provider`) + tests (mock
   transport httpx).
3. `app.geocoding.routes` (`GET /geocoding/search`) + montage `main.py` +
   contrat de couches (`pyproject.toml`) + tests d'intégration.
4. Rate limiting (`app/ratelimit/limiter.py`) + tests.
5. Variables d'environnement (`.env.example`, `docker-compose.yml`) +
   vérification `test_deployability.py`.
6. Régénération OpenAPI + types TS.
7. `shell/src/map/addressSearch.ts` (logique pure) + tests.
8. `shell/src/map/AddressSearchControl.tsx` (composant) + i18n + tests.
9. `shell/src/map/MapView.tsx` (prop `addressSearch`) + tests.
10. Sites de montage (`MapEditorPage.tsx`, `mapWidget.tsx`) + tests.
11. E2E `shell/e2e/map-address-search.spec.ts`.
