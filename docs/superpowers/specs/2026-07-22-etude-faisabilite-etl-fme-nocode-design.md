# Étude de faisabilité — moteur ETL no-code « équivalent FME » dans GeoStudio

> Date : 2026-07-22 · Statut : **étude de faisabilité (brainstorm → spec)**, à valider
> avant tout plan d'exécution. Ce document tranche un **Go/No-Go** et propose les
> amendements d'arbitrages à acter dans la feuille de route avant lancement.
>
> Références : feuille de route `docs/vision/2026-07-04-feuille-de-route-geostudio.md`
> (SP-14/A28 « datasets = pipeline de transformations déclaratif », §9 « moteur de
> workflow différé ») · brainstorm analytics `docs/vision/2026-07-09-brainstorm-…` ·
> `CLAUDE.md` (règles d'archi non négociables #1–#4, arbitrages figés).

---

## 0. Résumé exécutif — la recommandation en une page

**Cible (nord-star) :** doter GeoStudio d'un **atelier de transformation de données
no-code visuel, équivalent open-source de FME** — câbler `readers → transformers →
writers` sur un canvas, sur des données **tabulaires pures autant que géospatiales**,
exécuté côté serveur avec planification.

**Recommandation : GO — mais pas sur n8n comme moteur central.** L'étude recommande
une approche **cœur-first qui embarque des librairies OSS permissives tournant dans le
worker existant**, sous les objets déclaratifs et la porte `can()` de GeoStudio :

- **Runtime de transformers à deux étages** :
  - **Étage 1 (in-process, par défaut)** — **DuckDB SQL + CEL + pandas/pyarrow + dlt**.
    Couvre **tous les transformers de données pures** (filter, join, aggregate, pivot,
    dedupe, cast, derive, regex, parse date, flatten JSON…) **et** le spatial courant
    (reproject, buffer, intersection, within, H3). Zéro service externe, licence
    permissive, maintenance quasi nulle. *Déjà présent dans le dépôt (SP-6/SP-11).*
  - **Étage 2 (sidecar, longue traîne géo)** — **`qgis_process`** (QGIS Processing :
    natif + GDAL + GRASS + SAGA ≈ 1000+ algorithmes) **invoqué comme sous-processus**
    dans un conteneur isolé. QGIS est GPL ; l'appel binaire en processus séparé est une
    *agrégation*, pas une œuvre dérivée → le cœur GeoStudio reste Apache-2.0 propre.
- **Formats** (readers/writers) : **GDAL/OGR via pyogrio**, déjà en place.
- **Connecteurs externes récurrents** : **dlt** (librairie Python Apache-2.0,
  embarquable, schema inference, incrémental) enveloppée dans un objet déclaratif.
- **Orchestration/planification/triggers** : **procrastinate + OTel** (déjà en place),
  un document déclaratif `Pipeline` en source de vérité.
- **n8n / Kestra / Apache Hop** : **cartes de repli nommées**, jamais le centre —
  connecteurs d'issue-de-secours optionnels, opt-in, hors chemin critique.

**Pourquoi pas n8n au centre.** Deux des trois critères pondérés par Tanguy
(maintenance solo, cohérence MCP/déclaratif) l'excluent : service Node lourd (DB
propre, mode queue = Redis qu'on a *retiré* au jalon M1), workflows au format
propriétaire hors du modèle déclaratif (viole la règle d'archi #2), permissions/audit/
tenant hors `can()`, licence *fair-code* non-OSS en friction avec la distribution
Apache-2.0. Le troisième critère (time-to-value) est satisfait **autrement** : par la
largeur immédiate de QGIS/GDAL/dlt, sans porter la charge d'un service.

**Effort :** ≈ **20–29 semaines** pour un dev expérimenté à plein temps (soit, au
rythme solo 10–25 h/sem + agents, un chantier pluri-mensuel à découper en 4 phases —
comparable en ampleur à SP-11 lakehouse). Le **poste de risque n°1 est le canvas de
graphe** ; le runtime, lui, réutilise massivement l'existant.

**Relation à la feuille de route :** ce chantier **subsume et étend SP-14/A28** (le
« pipeline de transformations déclaratif » y était déjà nommé). Il nécessite d'**amender
explicitement le §9** (le « moteur de workflow » n'est plus totalement différé : on en
livre une forme bornée, sans triggers durables au départ) — cf. §6.

---

## 1. Valeur ajoutée & cas d'usage

Aujourd'hui, GeoStudio sait **ingérer** un fichier (SP-6), **moissonner** un catalogue
(SP-12), **répliquer** en lakehouse (SP-11) et **agréger** pour l'analyse (SP-11b). Il
lui manque la brique qui **transforme, nettoie, enrichit et recombine** la donnée entre
la source et la publication — sans code. C'est le trou que comble un ETL no-code.

| # | Cas d'usage | Domaine | Ce que l'ETL débloque |
|---|---|---|---|
| 1 | Nettoyer/normaliser un CSV métier avant publication (trim, cast, dédup, valider les codes INSEE) | Transverse | **Data prep pur** — aucun géo, étage 1 seul |
| 2 | Joindre un référentiel attributaire (Excel/API) à une couche parcellaire par clé | Urbanisme | `join` tabulaire + `writer.collection` |
| 3 | Buffer de 500 m autour des écoles + compter les incidents inclus, par commune | Sécurité / crise | `spatial.buffer` + `spatial.within` + `aggregate` |
| 4 | Synchroniser chaque nuit un Feature Service ArcGIS distant en collection locale | Interop | `reader.connector` (dlt/harvest) + `refreshPolicy` |
| 5 | Reprojeter + simplifier un jeu Lambert-93 lourd avant diffusion web | Environnement | `spatial.reproject` + `qgis:native:simplifygeometries` (étage 2) |
| 6 | Agréger des relevés capteurs en indicateurs H3 horaires pour un dashboard | Environnement | `aggregate` + `spatial.h3` → `writer.dataset` (SP-14) |
| 7 | Fusionner 3 exports communaux hétérogènes en un schéma cible unique | Aménagement | `select`/`rename`/`cast` multi-sources + `union` |
| 8 | Enrichir des points d'intérêt via une API REST (géocodage inverse, météo) | Crise / logistique | `reader.connector` REST (dlt) + `derive` CEL |
| 9 | Détecter et router les enregistrements invalides vers une table de rejet | Qualité de données | `edge.when` (CEL) = routage conditionnel |
| 10 | Publier automatiquement un extrait filtré (données ouvertes) en GeoJSON/CSV sur S3 | Open data / portails | `filter` + `writer.export`, déclenché planifié |
| 11 | Pipeline hydrologie : MNT → accumulation → bassins versants | Environnement | Étage 2 `qgis:grass7:*` (longue traîne géo profonde) |

**Valeur produit :** ces cas 1–2–7–9 sont **purement tabulaires** — l'ETL n'est pas
qu'un outil géo, c'est le chaînon manquant du « cycle de vie complet » (ETL → stockage →
catalogue → analyse → viz) qui distingue une plateforme d'un simple visualiseur.

---

## 2. Options techniques

### 2.1 Cadre d'évaluation

Trois critères pondérés (arbitrés par Tanguy) : **time-to-value / richesse**,
**maintenance solo** (10–25 h/sem), **cohérence MCP/IA/déclaratif** (`can()`, audit,
tenant, documents schématisés). La **licence** est un facteur de diligence (produit
public Apache-2.0), non un couperet. Critère transverse décisif : **l'embarquabilité**
— un outil qui tourne *dans le worker procrastinate existant* ne réintroduit aucune
surface et reste sous `can()`.

### 2.2 Point 1 — Automatisation récurrente & connecteurs externes

| Candidat | Licence | Embarquable | Time-to-value | Maintenance | Cohérence | Verdict |
|---|---|---|---|---|---|---|
| n8n | fair-code (non-OSS) | ❌ service+DB(+Redis) | 🟢 | 🔴 | 🔴 propriétaire, hors `can()` | **Repli seulement** |
| Node-RED | Apache-2.0 | ❌ service Node | 🟡 | 🔴 | 🔴 même tension | Écarté |
| Apache NiFi | Apache-2.0 | ❌ JVM lourd | 🟡 | 🔴 | 🔴 | Écarté |
| Airbyte | Elv2 (plateforme) | ❌ stack propre | 🟢 | 🔴 | 🔴 | Écarté |
| Meltano/Singer | MIT | 🟡 CLI | 🟡 (taps variables) | 🟡 | 🟡 YAML | Alternative mineure |
| **dlt** | **Apache-2.0** | ✅ **lib Python, 0 backend** | 🟢 | 🟢 | 🟢 in-proc, agent-friendly | **✅ RETENU** |
| From scratch (`HarvestConnector`) | — | ✅ | 🔴 | 🟡 | 🟢 | Complément |

**Retenu : dlt embarqué**, enveloppé dans un objet déclaratif `reader.connector`,
étendant l'abstraction `HarvestConnector` existante (SP-12c).

### 2.3 Point 2 — Transformation (data **et** spatial)

**Transformers de données pures** — la famille sur laquelle on insiste — sont
couverts **sans nouvelle dépendance** :

| Moteur | Rôle | État |
|---|---|---|
| **DuckDB SQL** | join, aggregate, filter, pivot, window, cast, string/date/regex | ✅ déjà (SP-11) |
| **CEL** | `derive` (champ calculé), conditions de routage | ✅ déjà (A8) |
| **pandas/pyarrow** | manipulations dataframe, flatten JSON | ✅ déjà |
| **dlt** | normalisation, schema inference | ✅ (point 1) |

**Transformers spatiaux :**

| Moteur | Rôle | Licence | Runtime |
|---|---|---|---|
| DuckDB spatial + GeoPandas/Shapely | reproject, buffer, intersection, within, H3 (courant) | MIT/BSD | ✅ in-proc (étage 1) |
| **`qgis_process`** (natif+GDAL+GRASS+SAGA, ~1000+ algos) | longue traîne géo profonde | **GPL → sidecar** | 🟡 sous-processus (étage 2) |
| Apache SedonaDB | moteur mono-nœud géo-first si volumétrie dépasse DuckDB | Apache-2.0 | 🔵 watchlist |
| FME | gold standard propriétaire | 🔴 propriétaire | ❌ hors OSS |

**Conclusion :** aucun *deuxième moteur analytique* (règle #3). On étend le runtime
DuckDB de SP-11 pour l'étage 1 et on ajoute un **sidecar `qgis_process`** pour l'étage 2.

### 2.4 Point 3 — Orchestration / chaînes

| Candidat | Licence | Modèle workflow | Fit règle #2 (doc déclaratif) | Verdict |
|---|---|---|---|---|
| Airflow | Apache-2.0 | DAG en code Python | 🔴 code, service lourd | Écarté |
| Prefect | Apache-2.0 | flows en code Python | 🔴 code | Écarté |
| Dagster | Apache-2.0 | assets Python (élégant pour datasets) | 🟡 lourd | Écarté (réf. conceptuelle) |
| **Kestra** | **Apache-2.0** | **YAML déclaratif**, 1200+ plugins, triggers | 🟢 mais service JVM | **Repli nommé** |
| **procrastinate** | — | file Postgres, chaînage | 🟢 déjà là | **✅ RETENU** |
| From scratch : doc `Pipeline` + procrastinate + OTel | — | déclaratif schématisé | 🟢 maximal | **✅ RETENU** |

**Conclusion :** un **document `Pipeline` déclaratif orchestré par procrastinate**,
observé par l'OTel déjà branché (SP-10). **Kestra** est la seule carte de repli externe
compatible avec la règle #2, à n'activer que sur demande réelle d'orchestration durable
multi-systèmes (cohérent §9).

### 2.5 Références de conception (jamais dépendances centrales)

- **Apache Hop** (Apache-2.0, designer visuel pipelines+workflows, 400+ plugins,
  metadata-driven) : l'**architecture la plus proche** de ce qu'on bâtit — référence de
  conception, éventuel moteur d'exécution sidecar en repli. GUI JVM non intégrable au
  shell React.
- **QGIS Graphical Modeler** + **pipeline PDAL** (JSON de stages) : références du
  **format de document graphe** et de l'exécution headless.

---

## 3. Architecture proposée

### 3.1 Le document `Pipeline` (déclaratif, schématisé — règle #2)

Nouveau type d'item de plateforme (comme `site`, SP-16a), catalogué, partageable via
`can()`, versionné, audité. Graphe nœuds + arêtes, dans le style `LayoutItem`/`Message` :

```jsonc
Pipeline {
  id, name,
  nodes: PipelineNode[],
  edges: PipelineEdge[],
  refreshPolicy?: { mode: "manual"|"interval"|"scheduled", intervalMinutes?, cron? },
  triggers?: Trigger[]          // événementiel — phase 4
}
PipelineNode {
  id, kind: "reader"|"transform"|"writer",
  op: string,                   // "reader.collection", "transform.filter", "transform.qgis:native:dissolve"
  x: int, y: int,               // idiome LayoutItem
  params: dict,                 // bindable { $expr } / {{var:nom}}
  title?: string
}
PipelineEdge {
  id, from: string, to: string, // nodeId (+ port "to:right" pour join)
  when?: string                 // CEL = routage conditionnel (idiome Message.when)
}
```

**Chaque `op` porte un manifeste de params typé** — mécanisme `WcWidgetManifest`
(SP-8a). Le panneau de params d'un transformer est **auto-généré** depuis ce manifeste,
comme `PropsPanel`. Catalogue d'`op` : cf. §2.3 (readers / transform data / transform
spatial étage 1 / transform spatial étage 2 `qgis:*` / writers). Modèles Pydantic
déclarés dans `core/app/pipelines/schemas.py` (round-trip testé explicitement pour
éviter la régression `visibleWhen` de SP-5b).

### 3.2 Compilation & exécution (réutilise SP-6/SP-11)

1. Validation du graphe (DAG acyclique, ports typés, params vs manifeste, expressions
   CEL via `expr.ts`/serveur), **tri topologique** → plan.
2. **Fusion étage 1** : nœuds data + spatial-DuckDB contigus → **une requête DuckDB**
   (push-down, comme l'agrégat SP-11b).
3. **Rupture étage 2** : un nœud `qgis:*` matérialise son entrée (GDAL) → **sidecar
   `qgis_process`** → relit la sortie.
4. **Readers/writers** via GDAL/pyogrio et les primitives **déjà auditées**
   (`run_import` SP-6, `create_feature`/enregistrement collection).
5. **Run** = job **procrastinate** (queue dédiée `etl`), tracé **OTel** (span par nœud),
   **audité** (`pipeline.run`), statut poll-able ; `refreshPolicy` → tâche périodique
   (patron sweep harvest SP-12c). Les jobs court-circuitent le middleware read-only
   (mutation hors requête HTTP — cf. leçon SP-12c/SP-9).

### 3.3 Sécurité & permissions

- Le Pipeline est un item : `can(user, action, pipeline)`, `audit_log`, `tenant_id`.
- **Lire une source** exige la perm de lecture de la collection ; **écrire une
  collection** passe par le **même chemin d'écriture OGC** (frontière = 403 serveur
  inchangé). Aucun nouveau modèle d'autorisation.
- **Sidecar `qgis_process`** : conteneur **isolé, sans credentials DB ni accès réseau
  large**, ne voit qu'un **volume scratch** d'entrées/sorties (garde
  anti-confused-deputy, patron des clés S3 préfixées tenant de SP-6a). L'égress dlt est
  soumis à l'allowlist SSRF prévue en SP-12d.
- Nœud `transform.sql` (échappatoire DuckDB brut) **réservé au rôle analyste** et
  sandboxé exactement comme `POST /analytics/sql` (SP-11c : `enable_external_access=
  false`, `lock_configuration=true`).

### 3.4 Exposition dans le Shell (no-code)

- Route builder `PipelineBuilderPage` (modes edit/preview/run, philosophie
  `AppRenderer`).
- **Canvas de graphe** : cartes-nœuds positionnées `x/y` + arêtes béziers SVG.
  - **MVP : hand-rolled SVG minimal** (0 dépendance, cohérent avec `GridCanvas` déjà
    hand-rollé).
  - **Évolution : React Flow (`@xyflow/react`, MIT)** si l'interaction devient riche.
- **Palette d'`op`** groupée *data* / *spatial* (idiome `WidgetPalette`).
- **Inspecteur de nœud** : params auto-générés du manifeste, champs `$expr` validés
  inline (`configExpressionErrors`).
- **Aperçu de données** (« Inspect » façon FME) : `POST /pipelines/{id}/preview?upTo=
  <nodeId>` exécute le **plan partiel borné** (LIMIT N) → 1res lignes.
- **Run + statut** : bouton Run → défère le job → poll (patron ingestion SP-6a).
- **Gabarit de galerie** « Pipeline de données » pré-câblé.

### 3.5 API cœur & MCP

- REST : `GET/POST/PUT/DELETE /pipelines`, `POST /pipelines/{id}/run`,
  `POST /pipelines/{id}/preview`, `GET /pipelines/{id}/runs` (historique). Nouveau
  module `core/app/pipelines/` (frontière import-linter déclarée).
- Catalogue d'`op` publié en ressource (`GET /pipelines/ops` + schéma JSON), comme le
  schéma AppConfig MCP (SP-2).
- **MCP** : `create_pipeline`, `run_pipeline`, `explain_pipeline` (mêmes fonctions de
  repository + `can()` que REST, `actor_kind=agent`), calqué sur `create_dataset`
  (SP-14). Un agent écrit un Pipeline comme un AppConfig.

### 3.6 Docker Compose

- **Nouveau service `qgis-worker`** (sidecar étage 2) : image basée sur `qgis/qgis`
  headless, sans creds, monté sur un volume scratch partagé avec le `worker`. Profil
  `etl` (optionnel — un `docker compose up` par défaut ne le démarre pas ; l'étage 1
  fonctionne sans lui).
- `worker` : `+dlt` dans `pyproject.toml`/`Dockerfile`.
- Aucun nouveau datastore (pas de Redis, pas de DB tierce).

---

## 4. Faisabilité technique

### 4.1 Points bloquants ou difficiles

| # | Difficulté | Gravité | Mitigation |
|---|---|---|---|
| D1 | **Canvas de graphe** (drag, ports, arêtes, layout) — surface frontend neuve | 🔴 Élevée | MVP hand-rolled minimal, React Flow (MIT) en évolution ; borne le MVP à une topologie linéaire+join avant le DAG complet |
| D2 | **Contrat & isolation du sidecar `qgis_process`** (I/O fichiers, mapping params, codes d'erreur, absence de creds) | 🟠 Moyenne | Spike d'ouverture obligatoire (gate) contre un conteneur QGIS réel ; matérialisation via GDAL déjà maîtrisée (SP-6b) |
| D3 | **Posture licence GPL** (sidecar vs distribution Apache-2.0) | 🟠 Moyenne | Sous-processus = agrégation ; à confirmer avant distribution (pas un avis juridique). Étage 2 optionnel (profil `etl`) → le produit de base reste 100 % permissif |
| D4 | **Fusion/push-down étage 1** (quels nœuds fusionnent en une requête DuckDB) | 🟡 Faible | Réutilise le patron SP-11b ; démarrer nœud-par-nœud (matérialisation systématique), optimiser ensuite |
| D5 | **Qualité/versioning des sources dlt** | 🟡 Faible | Périmètre initial : REST générique + Postgres ; élargir sur demande |
| D6 | **Coût mémoire du sidecar QGIS** (empreinte, cold start) | 🟡 Faible | Service opt-in, hors budget « 8 Go » (non bloquant, Q7) |

### 4.2 Estimation d'effort (1 dev expérimenté, plein temps)

| Lot | Contenu | Semaines |
|---|---|---|
| Runtime étage 1 + doc `Pipeline` + exécution procrastinate + 6–8 `op` data | Socle sans UI (auteur via MCP/JSON) | 4–6 |
| Canvas MVP + inspecteur + palette + aperçu de données | Le poste de risque | 5–7 |
| Spatial étage 1 + sidecar `qgis_process` + writers + readers connecteurs dlt | Largeur | 5–7 |
| Planification/`refreshPolicy` + triggers + `transform.sql` sandboxé + outils MCP + gabarit + parité FME | Finition | 6–9 |
| **Total** | | **20–29** |

Au rythme solo 10–25 h/sem (+ agents), c'est un chantier **pluri-mensuel** comparable à
SP-11. Découpage en 4 phases livrables (§5) impératif — jamais de tunnel (principe #1).

### 4.3 Dépendances & customisations

- **Ajouts** : `dlt` (Apache-2.0, in-proc) ; image sidecar `qgis/qgis` (GPL, profil
  `etl`) ; optionnel `@xyflow/react` (MIT) pour le canvas avancé.
- **Réutilisé tel quel** : DuckDB+spatial (SP-11), CEL (`expr.ts`, A8), procrastinate
  (SP-6), OTel (SP-10), GDAL/pyogrio (SP-6b), primitives d'ingestion/collection
  auditées, mécanisme de manifeste→panneau (SP-8a), `can()`/audit/tenant.
- **Customisations GeoStudio** : manifestes d'`op` (un par transformer), compilateur
  DAG→plan, contrat sidecar, canvas.

---

## 5. Roadmap phasée

Chaque phase est un produit démontrable (principe #1) ; les specs E2E existantes
restent vertes.

### Phase 1 — Socle « data pipeline » headless (MVP moteur)
- Document `Pipeline` (Pydantic + TS), module `core/app/pipelines/`, `can()`/audit.
- Runtime étage 1 (DuckDB+CEL+pandas), 6–8 `op` data (`reader.collection`, `filter`,
  `select`, `derive`, `aggregate`, `join`, `writer.collection`, `writer.export`).
- Exécution procrastinate (queue `etl`), historique des runs, OTel.
- Auteur **via MCP/JSON** (pas encore de canvas) — `create_pipeline`/`run_pipeline`.
- **Livrable démontrable :** un agent crée un pipeline « nettoyer CSV → collection ».

### Phase 2 — Canvas no-code (le cœur produit)
- `PipelineBuilderPage`, canvas hand-rolled, palette, inspecteur auto-généré, aperçu de
  données borné, bouton Run + poll.
- Spec E2E « construire visuellement un pipeline data et l'exécuter ».
- **Livrable :** un utilisateur non-technicien bâtit le cas d'usage #1 sans code.

### Phase 3 — Spatial & largeur FME
- Étage 1 spatial (reproject/buffer/intersection/within/H3), writers dataset (SP-14).
- **Sidecar `qgis_process`** (profil `etl`) + `op` `qgis:*` (spike gate D2 en ouverture).
- `reader.connector` dlt (REST + Postgres).
- **Livrable :** cas #3 (buffer+within+aggregate) et #5 (reproject+simplify) end-to-end.

### Phase 4 — Automatisation & finition
- `refreshPolicy` (interval/scheduled), triggers événementiels, `transform.sql`
  sandboxé (analyste), egress connecteurs (allowlist SSRF SP-12d), gabarit galerie,
  parité FME sur les transformers les plus demandés, outils MCP complets.
- **Livrable :** cas #4/#10 (sync ArcGIS nocturne, export open-data planifié).

---

## 6. Risques, mitigations & arbitrages

### 6.1 Risques

| Risque | Impact | Mitigation |
|---|---|---|
| Le canvas dérape (temps/complexité) | Chantier qui gonfle | Borner le MVP (topologie linéaire+join), livrer Phase 1 sans UI d'abord |
| GPL/QGIS mal posé pour la distribution | Blocage légal | Étage 2 opt-in (profil `etl`), sidecar = sous-processus ; confirmer la posture avant release |
| Deux moteurs de transformation (ce chantier vs SP-14) | Viole règle #3 | **Unifier** : SP-14 dataset = un `Pipeline` avec `writer.dataset` ; pas de moteur parallèle |
| Empreinte mémoire sidecar QGIS | Confort dev | Optionnel, non bloquant (Q7) |
| Sur-ambition « équivalent FME » complet | Tunnel | Parité FME *progressive*, pilotée par les cas d'usage réels, pas exhaustive |
| Sécurité du sidecar (confused deputy) | Fuite tenant | Isolation sans creds + volume scratch, patron SP-6a |

### 6.2 Arbitrages à acter dans la feuille de route (avant lancement)

1. **Amender §9** : le « moteur de workflow / workflows durables » n'est plus
   totalement différé — on livre un **ETL déclaratif borné** (DAG sans triggers durables
   au départ ; triggers en Phase 4). À écrire explicitement (CLAUDE.md : un arbitrage se
   met à jour, ne se contourne pas en session).
2. **Subsumer SP-14/A28** : le « pipeline de transformations déclaratif » des datasets
   **devient** le document `Pipeline` de ce chantier (`writer.dataset`). Éviter deux
   specs concurrentes. Nouvel arbitrage à numéroter (p. ex. **A39**) + nouveau chantier
   (**SP-17 « ETL no-code »** ou extension explicite de SP-14).
3. **Acter la posture GPL-sidecar** comme arbitrage (étage 2 optionnel, agrégation par
   sous-processus, cœur Apache-2.0 intact).
4. **Confirmer les règles #2/#3** : le `Pipeline` est un document déclaratif (règle #2
   OK) ; le runtime DuckDB est *le* runtime analytique (pas de second moteur, règle #3
   OK) ; l'`AppRenderer` reste distinct du `PipelineBuilder` (deux surfaces d'édition,
   un seul moteur analytique en dessous).

---

## 7. Recommandation finale

**GO**, sur l'approche **cœur-first + libs OSS embarquées (dlt / DuckDB / GDAL) +
sidecar `qgis_process` opt-in**, document `Pipeline` déclaratif et canvas no-code dans
le shell, orchestration procrastinate. **NO-GO sur n8n au centre** (repli nommé
seulement, avec Kestra et Apache Hop).

Cette voie est la seule qui satisfait **simultanément** les trois critères pondérés :
largeur fonctionnelle façon FME (QGIS ~1000 algos + GDAL + dlt, sans réécriture),
maintenance solo tenable (un sidecar sans état + des libs, aucun service à état
supplémentaire), cohérence MCP/déclaratif maximale (`Pipeline` = document GeoStudio,
opérable par agent, sous `can()`/audit/tenant).

### Prochaines étapes concrètes

1. **Acter les arbitrages §6.2** dans `docs/vision/2026-07-04-feuille-de-route-…` (§8/§9
   + numéro A39 + SP-17) — avant tout code.
2. **Spike gate D2** : un conteneur `qgis/qgis` headless, `qgis_process run
   native:buffer` sur un GeoPackage réel, I/O par volume scratch, mesure cold start &
   empreinte. Décide de la faisabilité de l'étage 2.
3. **Écrire le plan d'exécution de la Phase 1** (writing-plans) : premiers fichiers
   `core/app/pipelines/{schemas,models,repository,routes,runtime,jobs}.py`,
   `core/app/pipelines/ops/` (manifestes + compilateurs), migration `00NN_pipelines.py`
   (`tenant_id`/audit), frontière import-linter, `+dlt` dans `pyproject.toml`/
   `Dockerfile`, service `qgis-worker` (profil `etl`) dans `docker-compose.yml`.
4. **Découper en 4 phases** (§5), chacune sa spec/plan datée, TDD + E2E, jamais de
   tunnel.

---

## Annexe — Sources externes consultées (2026-07-22)

- dlt (Apache-2.0, librairie embarquable) — dlthub.com/docs/intro
- Kestra vs Windmill/Node-RED (licences, YAML déclaratif) — kestra.io/vs/windmill
- Alternatives OSS à n8n 2026 — synta.io
- Node-RED vs Apache NiFi — toolradar.com
- Sedona / DuckDB / GeoPandas comparés — forrest.nyc
- Airflow vs Prefect vs Dagster 2026 — getbruin.com
- Apache Hop (Apache-2.0, ETL visuel) — altiacompany.com, integrate.io
- QGIS Processing headless `qgis_process` — docs.qgis.org, spatialthoughts.com
