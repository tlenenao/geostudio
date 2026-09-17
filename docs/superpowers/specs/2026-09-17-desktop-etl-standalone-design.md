# Desktop ETL standalone (.exe) — design

> **Date : 2026-09-17 · Statut : brainstorm validé, pas encore planifié.**
> Nouveau produit distinct du cœur/shell : une release desktop autonome du
> module pipeline no-code (`core/app/pipelines/`), sans QGIS, pour un
> utilisateur qui n'a pas de serveur GeoStudio. Ce document est l'issue du
> brainstorm ; il n'a pas encore de plan d'exécution (`writing-plans`) ni de
> découpage en sous-parties façon SP-15a→h.
>
> Références : `CLAUDE.md` (arbitrages figés — API d'écriture = OGC API
> Features, identité = OIDC/Keycloak jamais de mot de passe, jobs =
> procrastinate côté serveur) · `docs/superpowers/specs/2026-08-05-sp15a-pipeline-socle-design.md`
> et suivants (SP-15a→h, le moteur qu'on réutilise) · `docs/superpowers/specs/2026-09-16-operation-contract-design.md`
> (registre unique `OPERATIONS`, base de toute cette réutilisation) ·
> `docs/superpowers/specs/2026-09-08-app-builder-package-extraction-postmortem.md`
> (postmortem d'une extraction npm workspace ratée — le risque à ne pas
> reproduire en réutilisant le canvas React).

## 1. Objectif & non-buts

**Objectif.** Un exécutable Windows autonome (« ETL desktop ») qui permet à
un utilisateur sans serveur GeoStudio de construire visuellement un pipeline
de transformation de données géospatiales (fichiers locaux + connecteurs
REST/Postgres/Snowflake), de l'exécuter localement, et optionnellement de
pousser le résultat vers un cœur GeoStudio distant. Le moteur (compilateur
d'op, `OPERATIONS`, connecteurs dlt) et l'UI (canvas DAG) doivent être **le
même code** que le cœur/shell, pas une réécriture ni un fork figé : toute
évolution future du moteur serveur (nouvel op, nouveau connecteur, correctif)
doit atteindre le desktop au rebuild suivant, sans travail de portage manuel.

**Non-buts explicites (v1)** :

- **`transform.qgis`** — abandonné complètement pour ce produit. Aucune
  dépendance copyleft (GPL) dans la chaîne desktop ; le binaire reste
  distribuable sous Apache-2.0 comme le reste du dépôt.
- **Planification cron / déclenchement webhook** — le desktop exécute à la
  demande (bouton « Exécuter »), pas de file de tâches périodiques.
- **Historique de versions du pipeline** — un pipeline = un fichier local
  `.gspipeline` (JSON), pas de mécanisme de rollback en v1.
- **macOS / Linux** — Windows seul pour la v1 ; Tauri et PyInstaller
  supportent les deux autres OS mais ce n'est pas testé avant que Windows
  marche de bout en bout.
- **Multi-utilisateur / partage** — un poste, un utilisateur, pas de notion
  de tenant côté desktop.
- **Flux OIDC réutilisant un client Keycloak existant sans modification** —
  il faut déclarer un nouveau client public `desktop-etl` (PKCE, sans
  secret) dans le realm ; c'est une entrée de config infra, pas un nouveau
  protocole.

Le modèle reste additif côté cœur : les seuls changements dans
`core/app/pipelines/` sont des ajouts au registre partagé (2 op, 1 seam de
secrets) — rien à défaire pour que le cœur continue de fonctionner tel quel.

## 2. Architecture — process model & repo

Nouveau dossier racine **`desktop-etl/`**, sibling de `shell/` et `core/`.

- **Shell applicatif** : app Tauri (Rust + webview système). Au démarrage,
  Tauri lance un **sidecar** — un binaire Python figé (PyInstaller) qui
  embarque `core/app/pipelines/` (+ les modules dont il dépend
  transitivement, cf. §3) sans FastAPI complet, sans Postgres, sans
  procrastinate.
- **API du sidecar** : HTTP loopback (`127.0.0.1`, port éphémère négocié au
  lancement), qui rejoue la forme utile de l'API pipeline du cœur :
  `GET /ops` (= `ops_catalog()`), `POST /pipelines/validate`
  (= `config_validation.py`), `POST /pipelines/run` (exécution synchrone,
  progression en SSE), `GET /pipelines/preview`.
- **UI** : la webview charge une build Vite du **même** code React que
  `shell/src/builder/pipeline/` (Canvas, Palette, NodeInspector, RunPanel,
  PreviewMap), pointée sur le loopback du sidecar au lieu de l'API du cœur.
  Deux sélecteurs sont remplacés (§6, §7) : `CollectionParamSelect` →
  sélecteur de fichier local, `SecretParamSelect` → trousseau OS.

**Réutilisation du canvas React — risque identifié, traité par un périmètre
réduit.** Le postmortem de l'extraction npm workspace du shell entier
(2026-09-08, 7 classes de bugs : scan Tailwind, contexte Docker, lockfile,
seuils de couverture, signatures d'interface non vérifiées) ne doit pas se
reproduire. Ici le périmètre est ~10 fichiers de `builder/pipeline/`, pas le
shell entier. Deux options, à trancher au moment du plan selon ce qui
s'avère praticable :

1. Package workspace **minimal et isolé** (`packages/pipeline-canvas/`),
   consommé par `shell/` et `desktop-etl/` — seulement ce sous-arbre, pas une
   extraction générale.
2. Repli : copie ciblée de ces ~10 fichiers dans `desktop-etl/`, acceptée
   comme duplication délibérée et documentée (patron déjà en usage dans ce
   dépôt : `_qi()` dupliqué 3 fois dans `core/app/pipelines/` plutôt qu'un
   import inter-module d'un nom `_`-préfixé).

## 3. Réutilisation du moteur cœur — ajouts au registre partagé

Le sidecar n'est pas un fork figé : c'est le **même** `OPERATIONS`
(`core/app/pipelines/ops/contracts.py`) augmenté de 2 op et d'un seam.

**`reader.file` / `writer.file` (nouveaux, ajoutés au registre partagé, pas
desktop-only).** Les lecteurs/écrivains suivent déjà une signature uniforme
dispatchée par le registre `READERS` (`registries.py`) :
`(conn, *, session, tenant_id, node_id, params, view_name, user, base_uri) -> srid`
(cf. `_read_connector_rest` qui ignore déjà `user`/`base_uri`). `reader.file`
matérialise un fichier local via `ST_Read()` (DuckDB spatial/GDAL) — **le
même mécanisme déjà utilisé pour matérialiser la sortie du sidecar QGIS**
(`runtime.py:472-486`), pas un chemin parallèle, pas de dépendance à
`app/ingestion/parsers.py`. `writer.file` symétrique en écriture (`COPY ...
FORMAT GDAL DRIVER ...`, déjà le mécanisme de `writer.export`).

**Garde-fou obligatoire côté cœur** : ces deux op font de l'accès disque
arbitraire — un risque de traversée de chemin inacceptable sur un cœur
hébergé multi-tenant. Elles sont gatées par un flag au même patron que
`CORE_ETL_ENABLED`/le gate sidecar de `is_copyleft` : actives par défaut
côté sidecar desktop, désactivées par défaut côté cœur serveur. Le contrat
`OperationContract` gagne un moyen de les exclure du catalogue exposé par
`GET /pipelines/ops` quand le flag est éteint (même traitement que
`engine`/`execution_model`, déjà invisibles côté shell).

**`writer.core.collection` (nouveau, spécifique à l'usage desktop→cœur, mais
pas un op « spécial desktop »).** Ce n'est **pas** une variante de
`writer.collection` (qui écrit en SQL direct dans la table Postgres — hors de
portée sans session DB locale). C'est un client HTTP OGC API Features comme
un autre tiers : `POST /collections/{id}/items` sur l'URL du cœur configuré
+ jeton porteur (§5). Le cœur ne reçoit aucun traitement de faveur — il
applique son contrat public existant.

**Seam de secrets — le vrai point de couplage, corrigé plutôt que contourné.**
`connector_runtime.py` importe aujourd'hui `app.secrets.repository` en dur
(`Session` Postgres + `tenant_id`). On introduit un `Protocol`
`SecretResolver` (`get(name: str) -> SecretPayload`) injecté dans
`connector_runtime.py` au lieu de l'import direct. Le cœur garde son
implémentation Postgres actuelle ; le sidecar desktop fournit une
implémentation trousseau OS (§6). Les 18 op DuckDB restantes et le
compilateur n'ont aucune dépendance équivalente — SQL généré à partir de
params Pydantic déjà validés, purs.

**Dépendances transitives auditées, pas juste supposées inertes.**
`connector_runtime.py` → `app.analytics.sql_sandbox` (validation SQL du
connecteur Postgres) → `app.collections.introspection` (dataclass
`TableInfo`, `Session` SQLAlchemy en type hint seulement). Vérifié à la
lecture : ce sont des imports inertes, aucune connexion DB réelle à
l'import. Le desktop n'appelle jamais les chemins qui utiliseraient
`reader.collection`/`writer.collection`/`writer.dataset` (absents de son
palette), donc ce code est présent dans le binaire mais mort à l'exécution
— acceptable, mais **à confirmer par le spike du §9 avant toute autre
chose**, PyInstaller pouvant échouer à figer certains imports dynamiques de
`dlt` indépendamment de cette question.

**Dérive version cœur/desktop.** Réutilisation réelle seulement si le
sidecar est **rebuild** à chaque évolution de `core/app/pipelines/` — sinon
c'est le fork qu'on voulait éviter, sous un autre nom. Un job CI reconstruit
et fait tourner les tests du sidecar desktop dès qu'un fichier de
`core/app/pipelines/` change (même logique de porte que
`test_feature_inventory.py` : une porte, pas une discipline).

## 4. Exécution & preview

**Un seam d'exécution existe déjà dans le cœur, à réutiliser tel quel.**
`run_pipeline_service()` (`service.py:78`) prend un
`defer_task: Callable[[str, str], None]` injecté ; en prod,
`default_task_deferrer()` appelle `run_pipeline_task.defer(...)`
(procrastinate). Le sidecar desktop fournit un **autre** `defer_task` qui
exécute la même logique que `run_pipeline_task` (`jobs.py:142`),
**synchrone, in-process**, sans file Postgres. On sépare, dans
`run_pipeline_task`, la partie réellement partagée (l'appel au moteur DAG
sur `OPERATIONS`) de ce qui est spécifique serveur (S3, ORM `PipelineRun`,
notifications in-app) — cette dernière est remplacée côté desktop par un
suivi de run local en mémoire, exposé par le sidecar avec la **même forme
JSON** que `RunResponse`/`RunStatus` (`routes.py:33-37`), pour que
`PipelineRunPanel.tsx` n'ait rien à changer côté UI.

**Preview** : `preview_pipeline_route` est déjà synchrone (pas de file) —
réutilisation directe, aucun seam à ajouter.

## 5. Push vers un cœur distant

Fonctionnalité additive (l'utilisateur n'a pas besoin d'un cœur pour utiliser
le desktop) exposée par le nouvel op `writer.core.collection` (§3).

**Authentification — flux OIDC complet, pas un jeton collé à la main.** Au
clic « Connecter un cœur GeoStudio », Tauri ouvre le navigateur système sur
l'`/authorize` Keycloak (PKCE), un listener loopback local récupère le code
de retour (patron `gh auth login`/`aws sso login`), échange contre les
jetons. Le refresh token est stocké dans le même trousseau OS que les
secrets connecteurs (§6). Prérequis infra : un nouveau client Keycloak
public `desktop-etl` dans le realm existant.

## 6. Secrets locaux

`app.secrets` (AES-GCM + Postgres, tenant-scopé) est hors périmètre
desktop. Le `SecretResolver` desktop (§3) s'appuie sur le **trousseau natif
de l'OS** (Credential Manager Windows en v1, via une crate Tauri) — pas de
mot de passe maître supplémentaire à gérer côté utilisateur, cohérent avec
la règle du dépôt « jamais de mots de passe dans le cœur » étendue au
desktop.

## 7. Persistance du pipeline

Un pipeline = un fichier JSON local (`.gspipeline`), ouvert/sauvegardé via
les dialogues fichier natifs de l'OS (plugin Tauri fs/dialog). Pas
d'historique de versions en v1 (cf. non-buts §1).

## 8. Packaging

- **Sidecar** : `core/app/pipelines/` (+ dépendances §3) gelé en binaire
  autonome via PyInstaller, invoqué par Tauri comme sous-processus local.
- **Cible v1** : Windows uniquement. Signature de code pour éviter
  l'avertissement SmartScreen — question produit ouverte, non tranchée ici
  (dépend du canal de distribution).
- **Taille attendue** : le sidecar embarque `dlt` + `sqlalchemy` +
  `geopandas`/`pyarrow`/`shapely`/`pyproj`/`duckdb` — de l'ordre de
  150-300 Mo non compressé. Nettement plus lourd qu'un Tauri typique
  (~10 Mo), mais sans commune mesure avec la stack Docker+Postgres+QGIS du
  produit serveur.
- **Licence** : QGIS abandonné ⇒ aucune dépendance copyleft. `dlt`
  (Apache-2.0), `duckdb`/`pyproj` (MIT), `geopandas`/`shapely` (BSD) — le
  binaire reste distribuable sous Apache-2.0, sans notice GPL/AGPL à
  embarquer (contrairement à `qgis-worker` en prod).

## 9. Risques & spike initial obligatoire

**Avant d'écrire la moindre ligne de Tauri** : figer `core/app/pipelines/` +
`connector_runtime.py` en binaire PyInstaller, exécuter un
`reader.connector.rest` réel dans ce binaire, confirmer que ça tourne.
`dlt` fait des imports dynamiques par destination — c'est le point le plus
susceptible de faire échouer un freeze PyInstaller silencieusement (module
manquant découvert seulement à l'exécution). Si ça casse, on le découvre
dans ce spike isolé, pas après avoir construit l'UI autour.

Risques secondaires déjà couverts par les choix ci-dessus (pas de nouveau
protocole d'auth, pas de mécanisme d'op parallèle, pas d'extraction de
package à l'échelle du shell entier) — voir §2, §3, §5.

## 10. Tests

- **Canvas React** : tests Vitest existants (`PipelineCanvas.test.tsx` etc.)
  continuent de s'appliquer une fois les 2 sélecteurs couplés remplacés
  (§2, §6, §7).
- **Sidecar Python** : TDD pytest sur l'API loopback ; les formes JSON étant
  identiques à celles du cœur (`RunResponse`/`RunStatus`/`ops_catalog()`),
  les tests de contrat existants servent de référence directe.
- **E2E desktop** : Tauri expose un pilotage WebDriver — un parcours golden
  path (créer un pipeline fichier→fichier, exécuter, vérifier le fichier de
  sortie) avant de considérer une v1 terminée, cohérent avec la règle du
  dépôt de tester dans l'app réelle avant de déclarer fini.

## 11. Découpage attendu pour le plan

Chantier trop large pour un plan unique (patron déjà utilisé pour SP-14a et
SP-15a→h) — candidats de découpage à trancher au moment de `writing-plans` :
spike de freeze (§9) en tout premier et bloquant ; puis socle sidecar (API
loopback + seam `defer_task` + seam secrets) ; puis `reader.file`/
`writer.file` côté cœur (gate inclus) ; puis intégration Tauri + réutilisation
UI ; puis `writer.core.collection` + flux OIDC (peut être une phase
ultérieure séparée, le desktop étant déjà utilisable sans elle).
