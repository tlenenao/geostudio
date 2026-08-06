# SP-15d — Pipeline : sidecar `qgis_process` (étage 2) (design)

> **Date : 2026-08-06 · Statut : validé (brainstorm tenu en session, spike D2 exécuté
> pour de vrai contre un conteneur QGIS réel — pas de simulation)**
> Quatrième sous-partie de **SP-15 — ETL no-code « équivalent FME »** (feuille de
> route, jalon **M14**, arbitrage **A39** déjà tranché — ce document ne rediscute
> pas le Go/No-Go GPL-sidecar, il l'exécute), correspondant à l'**étage 2** de la
> Phase 3 de l'étude de faisabilité
> [`2026-07-22-etude-faisabilite-etl-fme-nocode-design.md`](2026-07-22-etude-faisabilite-etl-fme-nocode-design.md)
> (§5 « Spatial & largeur FME », difficulté **D2** « contrat & isolation du
> sidecar `qgis_process` », classée spike d'ouverture obligatoire).
>
> **Découpage de la Phase 3** (acté dans
> [`2026-08-06-sp15c-spatial-writer-dataset-design.md`](2026-08-06-sp15c-spatial-writer-dataset-design.md)) :
> - SP-15c (livré) : opérations spatiales étage 1 (DuckDB) + `writer.dataset`.
> - **SP-15d (ce document)** : sidecar `qgis_process` étage 2.
> - SP-15e (à venir) : `reader.connector` dlt (REST + Postgres).
>
> Références : feuille de route (§SP-15, A39) · `CLAUDE.md` (règles d'architecture
> #1-4, règle non négociable procrastinate/pas de broker, égress SSRF SP-12d) ·
> [`2026-08-05-sp15a-pipeline-socle-design.md`](2026-08-05-sp15a-pipeline-socle-design.md)
> (document `Pipeline`, `ops/schemas.py`, `runtime.py`, `config_validation.py`,
> `CORE_ETL_ENABLED`) · SP-15c (`srid_by_node`, garde CRS, patron
> `_write_dataset`) · SP-6a (isolation scratch/clés préfixées tenant, patron
> repris pour l'isolation du sidecar) · `core/Dockerfile:24` et
> `core/app/analytics/duckdb_conn.py:23-24` (précédent `INSTALL ... FROM
> community` au build, `LOAD` au runtime sans accès réseau — même patron
> réutilisé ici pour `grassprovider`).

## 1. Objectif & non-buts

**Objectif.** Un nouvel op générique `transform.qgis` (kind `transform`) qui
invoque, via un sidecar isolé, un algorithme QGIS Processing parmi une
**allowlist v0 de 50 ids gelée dans le dépôt** (§10). Ferme la « longue traîne
géo profonde » que l'étage 1 DuckDB ne couvre pas (hydrologie GRASS,
simplification/généralisation cartographique, interpolation, raster terrain).

**Non-buts explicites** (reportés) :
- **Canvas shell** — `transform.qgis` reste authorable **MCP/REST/JSON
  uniquement** en v0, comme SP-15a Phase 1 avant que SP-15b n'ajoute le canvas.
  Éviter d'imposer un redesign du menu d'insertion (`INSERTABLE_TRANSFORMS`,
  aujourd'hui ~10 entrées non filtrables) à 60 entrées dans ce sous-plan — un
  menu recherchable est un vrai sujet UX, pas un sous-produit d'un sous-plan
  déjà consistant côté backend.
- **`reader.connector` dlt** — SP-15e.
- **`transform.sql`** échappatoire DuckDB brut réservé à l'analyste — Phase 4.
- **Réconciliation automatique de CRS** entre l'entrée d'un `transform.qgis`
  et ce que l'algorithme attend — même posture que SP-15c (§3.3/3.4) :
  l'auteur insère un `transform.reproject` explicite si besoin, jamais de
  reprojection implicite. Aggravé ici par un constat du spike (§2) : les
  algorithmes QGIS ne convertissent pas automatiquement les unités de
  distance vers le mètre pour un CRS géographique.
- **Extension de l'allowlist au-delà de 50 dans ce sous-plan** — le mécanisme
  (§5) supporte l'ajout d'ids par simple édition du fichier gelé, sans
  nouveau sous-plan ; seule la liste v0 est bornée ici.
- **Daemon QGIS tenu chaud entre invocations** — chaque appel au sidecar
  shelle un nouveau process `qgis_process` (§2 : ~2.5s d'overhead d'init
  mesuré). Acceptable pour de l'ETL différé/planifié, pas un chemin temps
  réel ; optimiser (pool de process, cache de provider registry) est hors
  périmètre v0.

## 2. Spike D2 — résultats (fermeture du spike d'ouverture)

Exécuté pour de vrai contre `docker.io/qgis/qgis` (Docker daemon local,
réseau disponible), pas en simulation. Résultats qui **contraignent le
design** ci-dessous :

1. **`qgis/qgis:latest` pointe vers un build `4.3.0-Master` instable**
   (branche de développement), pas une release. Le tag stable correct est
   **`qgis/qgis:release-3_34`** (QGIS 3.34.5 « Prizren », LTR), confirmé par
   `qgis_process --version`. Le contrat JSON (§3) est identique entre les
   deux versions testées (seul `--skip-loading-plugins` est absent en 3.34).
   **`release-3_34` est le tag retenu pour le service compose** (§4).
2. **`QT_QPA_PLATFORM=offscreen` est obligatoire.** Sans cette variable
   d'environnement, `qgis_process` échoue avant même d'atteindre la commande
   demandée (Qt tente de se connecter à un display X11 absent). Doit être
   fixé dans le service compose, pas laissé à la charge de l'appelant.
3. **Contrat JSON confirmé stable et machine-parseable** :
   - `qgis_process help <id> --json` retourne un schéma structuré complet par
     algorithme (paramètres typés, valeurs par défaut, enums, bornes) — base
     du mécanisme d'allowlist schema-dérivée (§5).
   - `qgis_process run <id> -` avec un objet JSON `{"inputs": {...}}` sur
     stdin exécute l'algorithme ; succès = **exit 0 + JSON complet sur
     stdout** (clé `results` = chemins de sortie) ; échec = **exit ≠0 + stdout
     vide (0 octet, vérifié) + `ERROR: <résumé>` sur stderr** (mêlé aux logs
     verbeux d'initialisation des providers, mais toujours préfixé `ERROR:`).
     Contrat sans ambiguïté pour un wrapper : lire stdout seulement si
     exit=0, sinon extraire la ligne `ERROR:` de stderr.
4. **Overhead d'initialisation mesuré : ~2.5s par invocation** (chargement de
   36 providers + support Python), aucun mode démon/serveur natif — chaque
   `run` est un process frais. Dimensionne le timeout (§8), pas un problème
   pour de l'ETL différé.
5. **Gotcha CRS confirmé** : `native:buffer` avec une couche en EPSG:4326
   interprète `DISTANCE` **dans les unités du CRS de la couche** (degrés),
   pas en mètres auto-convertis — aucune conversion implicite comme celle que
   SP-15c a dû construire côté DuckDB (`unit="meters"` de
   `transform.buffer`). Documenté en non-but §1 : reprojection explicite à la
   charge de l'auteur.
6. **`grassprovider` (fournissant les ids `grass:*`, dont `grass:r.watershed`
   — le cas hydrologie #11 de l'étude) est présent dans l'image mais
   désactivé par défaut.** `qgis_process plugins list` le montre non chargé ;
   `qgis_process plugins enable grassprovider` l'active (308 algorithmes
   `grass:*` apparaissent alors dans `list`). **Doit être activé au build de
   l'image** (`RUN qgis_process plugins enable grassprovider` dans le
   Dockerfile du sidecar), pas à chaque requête — le paramètre est écrit dans
   le profil QGIS du conteneur, qui doit donc être gravé dans l'image, pas
   recréé à chaque `docker run --rm`.
   Correction à l'étude : la nomenclature réelle est **`grass:*`**, pas
   `grass7:*` comme écrit dans l'étude de faisabilité (convention d'une
   version QGIS antérieure).
7. **`COPY <table> TO '<fichier>' WITH (FORMAT GDAL, DRIVER 'GPKG')` et
   `ST_Read(<fichier>)` fonctionnent tels quels** avec l'extension `spatial`
   DuckDB déjà chargée par le runtime existant (vérifié par un aller-retour
   réel table→GeoPackage→table). Confirme le mécanisme de rupture étage 2
   (§6) sans nouvelle dépendance.
8. **Image volumineuse : 6.53 Go** (`qgis/qgis:latest` ; `release-3_34` du
   même ordre de grandeur). Cohérent avec D6 de l'étude (« coût mémoire/
   empreinte du sidecar », classé faible gravité, non bloquant, service
   opt-in derrière le profil `etl`).

## 3. Contrat du sidecar `qgis-worker`

Service HTTP interne minimal, **stdlib `http.server`** (pas de FastAPI/
uvicorn : une seule route, éviter d'alourdir la dépendance d'un conteneur
déjà réduit à sa plus simple isolation). Une route :

```
POST /run
{
  "algorithmId": "native:simplifygeometries",
  "inputs": { "INPUT": "/scratch/<runId>/<nodeId>/in.gpkg",
              "TOLERANCE": 1.0,
              "OUTPUT": "/scratch/<runId>/<nodeId>/out.gpkg" }
}
```

En interne, le wrapper :
1. Vérifie `algorithmId` contre une **liste plate d'ids autorisés**
   (`/app/allowlist.txt`, un id par ligne — pas les schémas complets,
   seulement les ids, générée par le même script §5 et copiée dans l'image
   `deploy/qgis-worker/` au build). Défense en profondeur : le cœur a déjà
   validé la présence de l'id + ses params requis avant d'envoyer la requête
   (§5, §7) ; ce contrôle attrape le cas où les deux listes divergent (ex.
   une entrée retirée de l'allowlist cœur sans rebuild du sidecar). Un
   contrôle d'appartenance à une liste n'est pas de la « logique métier
   cachée » au sens de la règle d'archi #2 (aucune transformation de
   données) — c'est une garde de sécurité, au même titre que `can()`.
2. Shelle `qgis_process run <algorithmId> -` avec `{"inputs": ...}` sur
   stdin, `QT_QPA_PLATFORM=offscreen` déjà fixé dans l'environnement du
   conteneur.
3. `exit=0` → relit le JSON stdout, répond `200 {"results": {...}}`.
4. `exit≠0` → extrait la ligne `ERROR:` (et sa suite indentée) de stderr,
   répond `502 {"error": "<message>"}`.
5. Timeout process interne (§8) → tue le sous-process, répond `504`.

Au-delà de ce contrôle d'id, aucune traduction de formats dans le wrapper :
il shelle `qgis_process` et retranscrit son contrat tel quel, le cœur (§6)
est seul responsable de préparer les fichiers d'entrée et d'interpréter la
sortie.

## 4. Docker Compose & isolation

```yaml
qgis-worker:
  build: ./deploy/qgis-worker
  profiles: ["etl"]                 # même porte que CORE_ETL_ENABLED
  environment:
    QT_QPA_PLATFORM: offscreen
  volumes:
    - etl-scratch:/scratch          # partagé avec `worker`, RW
  networks: [gis-net]
  # PAS de DATABASE_URL, PAS de S3_*, PAS de dépendance à pgbouncer/minio —
  # garde anti-confused-deputy (patron SP-6a) : le sidecar ne voit que le
  # volume scratch, jamais une credential.
```

`deploy/qgis-worker/Dockerfile` (précédent de style : `deploy/postgis/`, base
image + personnalisation minimale, pas un service applicatif complet comme
`core/`) :

```dockerfile
FROM qgis/qgis:release-3_34
RUN qgis_process plugins enable grassprovider
COPY server.py /app/server.py
COPY allowlist.txt /app/allowlist.txt
ENV QT_QPA_PLATFORM=offscreen
CMD ["python3", "/app/server.py"]
```

`worker` (service existant, `docker-compose.yml:156`) gagne :
- `QGIS_WORKER_URL: http://qgis-worker:8000` (nouvelle variable d'env, lue
  uniquement par le dispatch `transform.qgis`, §6).
- Le même volume nommé `etl-scratch:/scratch` en RW.
- **`worker` reste responsable de nettoyer `/scratch/<runId>/` après le run**
  (succès ou échec) — le sidecar ne fait aucune gestion de cycle de vie de
  fichiers au-delà de lire/écrire ce qu'on lui demande.

Nouveau volume nommé `etl-scratch` dans la section `volumes:` du compose.
Aucun nouveau datastore (cohérent avec la contrainte de la feuille de route
« pas de Redis, pas de DB tierce »).

## 5. Nouvel op cœur : `transform.qgis` + allowlist schema-dérivée

Un seul op générique, pas 50 classes Pydantic à la main (décision de
brainstorm — 50 classes aurait dépassé de loin l'ampleur de SP-15a/SP-15c
combinés) :

```python
class TransformQgisParams(BaseModel):
    algorithmId: str
    params: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _check_allowlisted(self) -> "TransformQgisParams":
        schema = QGIS_ALGORITHMS.get(self.algorithmId)
        if schema is None:
            raise ValueError(f"algorithme non autorisé : {self.algorithmId}")
        required = {p["name"] for p in schema["parameters"] if not p["optional"]}
        missing = required - self.params.keys()
        if missing:
            raise ValueError(f"{self.algorithmId} : paramètres requis manquants {missing}")
        return self
```

`core/app/pipelines/ops/qgis_algorithms.py` porte `QGIS_ALGORITHMS: dict[str,
dict]` — **gelé/versionné dans le dépôt**, une entrée par id de l'allowlist
v0 (§10), chacune portant le schéma JSON de ses paramètres tel que retourné
par `qgis_process help <id> --json --skip-loading-plugins` (champs
pertinents extraits : nom, type, requis/optionnel, valeur par défaut, enum).

**Portée de la validation config-time, précisée** (même philosophie que le
reste du module, cf. docstring `ops/schemas.py` — « FORME des params, pas la
sémantique ») : seule la **présence** des noms de paramètres non-optionnels
déclarés par le schéma gelé de l'algorithme est vérifiée à la sauvegarde
(`missing` ci-dessus). Les **types/valeurs** (ex. un enum QGIS qui n'accepte
que `"0"`/`"1"`, une distance qui doit être positive) ne sont **pas**
vérifiés ici — comme `filter.expr`/`derive.expr`, une valeur mal formée
produit une erreur `qgis_process` claire à l'exécution (§3, §8), jamais un
résultat silencieusement faux, mais jamais un blocage à la sauvegarde non
plus.

**Génération, pas saisie manuelle** : `scripts/generate_qgis_algorithm_schemas.py`
tourne dans l'image `qgis/qgis:release-3_34` pinnée (via `docker run`, pas au
runtime du cœur) pour chaque id de l'allowlist v0, et régénère
`qgis_algorithms.py`. Le fichier gelé est ensuite **la seule source de
vérité consultée à la validation de config** — aucune dépendance live au
sidecar pour valider une config (`config_validation.py` reste rapide/
offline, cohérent avec le reste du module).

`GET /pipelines/ops` publie `transform.qgis` avec son schéma générique
(`algorithmId`, `params` en `dict` libre — un JSON Schema de dict générique
ne peut pas décrire les 50 formes possibles). Une ressource additionnelle
**`GET /pipelines/ops/qgis-algorithms`** publie l'allowlist complète +
schéma par id, consommée par les outils MCP d'auteur (`explain_pipeline` et
équivalents) pour guider un agent vers des params valides — même esprit que
le catalogue d'op publié comme ressource pour le schéma AppConfig (SP-2).

## 6. Runtime : rupture étage 2

Nouvelle branche de dispatch dans `runtime.py`, à côté des branches
`transform.*` existantes (compilées en SQL) :

```python
elif node.op == "transform.qgis":
    params = TransformQgisParams.model_validate(node.params)
    in_path = f"/scratch/{run_id}/{node.id}/in.gpkg"
    out_path = f"/scratch/{run_id}/{node.id}/out.gpkg"
    conn.execute(
        f"COPY {view_by_node[input_id]} TO '{in_path}' "
        f"WITH (FORMAT GDAL, DRIVER 'GPKG')"
    )
    result = _call_qgis_worker(
        algorithm_id=params.algorithmId,
        inputs={**params.params, "INPUT": in_path, "OUTPUT": out_path},
    )  # POST http://qgis-worker:8000/run, timeout §8
    conn.execute(
        f"CREATE TABLE {view_name} AS SELECT * FROM ST_Read('{out_path}')"
    )
```

Confirmé par le spike (§2.7) : `COPY ... WITH (FORMAT GDAL, DRIVER 'GPKG')`
et `ST_Read(...)` fonctionnent avec l'extension `spatial` déjà chargée par le
runtime — aucune nouvelle dépendance DuckDB. Aucune fusion à casser : la
Phase 1 est déjà **nœud-par-nœud, matérialisation systématique** (pas de
push-down entre op) — ce nœud ajoute un aller-retour fichier au lieu d'une
requête SQL, cohérent avec le reste de l'exécution.

`srid_by_node` (mécanisme SP-15c §2) : `transform.qgis` **invalide le
suivi de SRID** pour sa sortie (marqué inconnu) — un algorithme QGIS
arbitraire peut changer le CRS silencieusement (ex. un algo de reprojection
raster). Toute op spatiale étage 1 en aval qui a besoin d'un SRID connu
(`transform.intersection`, `transform.countWithin`, `transform.h3Aggregate`)
échoue à la compilation avec le même message de garde que SP-15c, sauf si un
`transform.reproject` explicite suit `transform.qgis` pour rétablir un SRID
connu.

## 7. Sécurité & permissions

- `transform.qgis` n'introduit **aucun nouveau modèle d'autorisation** : il
  ne référence ni lit ni n'écrit de collection — les entrées/sorties sont
  des tables déjà résolues par le reste du graphe (dont les lectures/
  écritures sont déjà validées par les op `reader.*`/`writer.*` voisines).
  Rien à ajouter à `_COLLECTION_PARAM_FIELD`/`_WRITE_OPS`
  (`config_validation.py:25-31`).
- **Double contrôle allowlist** : `algorithmId` validé à la sauvegarde
  (Pydantic, §5) **et** re-vérifié par le wrapper sidecar avant `shell` (§3,
  point 1) — même patron que le double contrôle de permission config-time/
  execution-time de SP-15c, défense en profondeur si l'allowlist gelée
  rétrécit entre la sauvegarde d'un pipeline et son exécution.
- **Isolation du sidecar** (patron SP-6a, garde anti-confused-deputy) :
  aucune credential DB, aucun accès S3, aucun accès réseau externe — seul le
  volume `etl-scratch` monté. L'égress dlt (SP-15e, hors périmètre ici) sera
  soumis à l'allowlist SSRF SP-12d séparément ; `transform.qgis` n'a aucune
  fonctionnalité réseau.
- **Posture GPL** : arbitrage A39 déjà tranché (sous-processus = agrégation,
  cœur Apache-2.0 intact, étage 2 optionnel via `profiles: ["etl"]`). Ce
  document exécute l'arbitrage, ne le rediscute pas.

## 8. Erreurs, timeouts, observabilité

- Timeout HTTP `worker → qgis-worker` configurable
  (`QGIS_WORKER_TIMEOUT_SECONDS`, défaut **600** — les algorithmes GRASS
  d'hydrologie peuvent tourner plusieurs minutes sur un DEM réel, contre
  l'overhead d'init de ~2.5s mesuré §2). Dépassement → `PipelineRuntimeError`
  sur le nœud, run marqué `failed`, message explicite (« timeout après
  {n}s » ) — même patron d'échec propre que les autres nœuds.
- Échec du sidecar (HTTP 502, `ERROR:` extrait de stderr, §3) → propagé tel
  quel dans le message de `PipelineRuntimeError`, pas de traduction/
  enrichissement côté cœur (le message QGIS est déjà explicite, ex.
  « Could not load source layer for INPUT »).
- Un span OTel par invocation `transform.qgis` (durée, `algorithmId`, statut)
  — même granularité que le span par nœud déjà posé par SP-15a (§3.2 de
  l'étude), pas de nouvelle instrumentation à inventer.

## 9. Exposition MCP/API — pas de canvas

- REST : aucune nouvelle route hors `GET /pipelines/ops/qgis-algorithms`
  (§5). `transform.qgis` est un nœud comme un autre dans le graphe `Pipeline`
  existant — `POST /pipelines`, `POST /pipelines/{id}/run`,
  `POST /pipelines/{id}/preview` inchangés.
- MCP : `create_pipeline`/`run_pipeline`/`explain_pipeline` (déjà livrés,
  SP-15a) gèrent `transform.qgis` sans modification — un agent l'écrit comme
  n'importe quel nœud, guidé par le schéma publié (§5). Aucun nouvel outil
  MCP nécessaire pour ce sous-plan.
- Shell : **zéro changement** (`INSERTABLE_TRANSFORMS`, `PipelinePalette.tsx`,
  `PipelineNodeInspector.tsx` intouchés) — non-but explicite §1.

## 10. Allowlist v0 (50 algorithmes)

Tous les ids ci-dessous sont **vérifiés réels** contre la sortie de
`qgis_process list` (base + `grassprovider` activé) pendant le spike — aucun
id inventé. Choisis pour ne pas recouvrir les 5 op spatiales étage 1 déjà
livrées par SP-15c (`buffer`, `reproject` vecteur, `intersection`,
`countWithin`, `h3Aggregate` sont **exclus**, notamment `native:reprojectlayer`
qui ferait doublon avec `transform.reproject`).

**Géométrie vectorielle (15)** — `native:dissolve`, `native:simplifygeometries`,
`native:smoothgeometry`, `native:centroids`, `native:convexhull`,
`native:multiparttosingleparts`, `native:fixgeometries`, `native:deleteholes`,
`native:extractvertices`, `native:pointsalonglines`,
`native:densifygeometriesgivenaninterval`, `native:snapgeometries`,
`native:minimumboundinggeometry`, `native:voronoipolygons`,
`native:delaunaytriangulation`

**Overlay vectoriel (7)** — `native:union`, `native:difference`,
`native:symmetricaldifference`, `native:clip`, `native:mergevectorlayers`,
`native:splitvectorlayer`, `native:multiringconstantbuffer`

**Analyse vectorielle (10)** — `native:joinattributesbylocation`,
`native:extractbylocation`, `native:extractbyattribute`,
`native:selectbyattribute`, `native:nearestneighbouranalysis`,
`native:zonalstatisticsfb`, `native:rasterlayerzonalstats`,
`native:heatmapkerneldensityestimation`, `native:creategrid`,
`native:fieldcalculator`

**Interpolation (2)** — `qgis:tininterpolation`, `qgis:idwinterpolation`

**Réseau (2)** — `native:shortestpathpointtopoint`,
`native:serviceareafrompoint`

**Raster / terrain (10)** — `native:hillshade`, `native:slope`,
`native:aspect`, `gdal:contour`, `gdal:polygonize`, `gdal:rasterize`,
`gdal:sieve`, `gdal:proximity`, `gdal:warpreproject`, `gdal:viewshed`

**GRASS hydrologie (4)** — `grass:r.watershed`, `grass:r.slope.aspect`,
`grass:r.fill.dir`, `grass:r.flow` (nécessitent `grassprovider` activé au
build, §2.6 ; nomenclature réelle `grass:*`, corrige `grass7:*` de l'étude).

## 11. Compatibilité & tests

- **Aucune migration DB** (pas de nouvelle table).
- **Aucun changement de comportement** pour les 14 op existantes
  (SP-15a+SP-15c) ni pour `PipelineBuilderPage`/canvas/palette.
- Nouveau service `qgis-worker` : profil `etl` uniquement, un
  `docker compose up` par défaut ne le démarre pas — cohérent avec
  `CORE_ETL_ENABLED`.
- Tests contre un **vrai conteneur `qgis/qgis:release-3_34`** (pas de mock du
  sidecar) dans la CI/les tests locaux marqués (nouveau marker pytest
  `qgis`, même esprit que le marker `postgis` existant — skippé si le
  conteneur n'est pas disponible) :
  - Round-trip `COPY ... GDAL` → sidecar → `ST_Read` sur un cas simple
    (`native:simplifygeometries`).
  - Cas d'erreur : `algorithmId` hors allowlist (rejeté à la validation,
    jamais envoyé au sidecar), fichier d'entrée manquant (erreur sidecar
    propagée), timeout (mock du sous-process qui ne répond jamais, pas besoin
    du vrai conteneur pour ce cas).
  - `srid_by_node` invalidé après `transform.qgis`, garde de compilation
    déclenchée pour une op étage 1 spatiale en aval sans `reproject`
    explicite.
  - Génération de schéma : `scripts/generate_qgis_algorithm_schemas.py`
    testé contre au moins 3 ids réels de l'allowlist (un par catégorie de
    paramètre : booléen, enum, distance) — vérifie que le fichier gelé
    régénéré est byte-identique au commit (pas de dérive silencieuse).
- Suites existantes (`core` pytest, `shell` vitest/e2e) restent vertes —
  extension additive pure.

## 12. Risques

| Risque | Mitigation |
|---|---|
| Image 6.53 Go + ~2.5s d'overhead par invocation | Service opt-in (`profiles: ["etl"]`), ETL différé pas temps réel — accepté (D6 étude, faible gravité) |
| Un algorithme arbitraire de l'allowlist se comporte différemment de ce que son schéma JSON laisse deviner (ex. le gotcha CRS §2.5) | Chaque nouvel id ajouté à l'allowlist devrait être testé contre un cas réel avant merge — pas un mécanisme automatique de garde, une discipline de revue |
| `algorithmId` hors allowlist injecté directement en base (contournement de la validation Pydantic par écriture directe) | Improbable (toute écriture passe par les routes validées), mais le double contrôle sidecar (§7) l'attrape quand même |
| Fichiers scratch non nettoyés après un run en échec (crash du worker avant le nettoyage) | Accepté en v0 — un espace disque qui grossit progressivement est un problème d'exploitation mineur derrière un profil opt-in, pas un problème de sécurité ; nettoyage périodique différé si besoin réel observé |
| `grassprovider` activé au build peut ne pas survivre à une mise à jour de l'image de base sans re-vérification | Le générateur de schémas (§5) et les tests contre le vrai conteneur (§11) le détecteraient au premier run après un bump de version |
