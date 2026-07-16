# SP-10a — Instrumentation OTel (cœur + worker)

Date : 2026-07-16
Statut : validé (brainstorm), en attente de plan

## Contexte

SP-10 (« Observabilité & SLO », cf.
`docs/vision/2026-07-04-feuille-de-route-geostudio.md` §SP-10, arbitrage A26)
équipe la plateforme pour s'exploiter : traces, métriques et logs standards,
SLO packagés, au moment où la démo publique (SP-9, clos) commence à recevoir
du trafic réel. A26 tranche déjà la stack de référence (SDK OTel + profil
compose `grafana/otel-lgtm`, export OTLP configurable). Le chantier est trop
gros pour un seul plan (25–45 h estimées) et suit le patron des autres SP
récents (SP-6, SP-8, SP-9) : découpage en sous-parties.

**SP-10a** couvre l'instrumentation elle-même — SDK OTel dans `core`/`worker`,
spans auto+manuels, logs corrélés, métriques métier. **SP-10b** (à
brainstormer séparément) couvrira le profil compose `--profile observability`,
les dashboards packagés, les 4 SLO/alertes, et le critère d'acceptation
« une alerte de test se déclenche ». SP-10b dépend de SP-10a (il a besoin de
spans/métriques réels à visualiser).

Aujourd'hui, le cœur n'a aucune instrumentation OTel, aucune configuration de
logging explicite (le `logging` stdlib par défaut), et `docker-compose.yml`
ne définit aucun service d'observabilité.

## Objectif de SP-10a

Un déploiement qui pointe `OTEL_EXPORTER_OTLP_ENDPOINT` vers un collecteur OTLP
voit des traces corrélées bout en bout (FastAPI → SQLAlchemy → httpx/botocore,
et jobs procrastinate), des logs structurés portant `trace_id`/`span_id`, et
quelques métriques métier — **sans** endpoint configuré (mode par défaut, et
toute la suite de tests), le comportement est strictement identique à
aujourd'hui : aucune erreur réseau, aucun flake, zéro changement visible.

## Architecture

Nouveau module `core/app/observability.py`, responsable de construire et
mémoïser process-wide un `TracerProvider`, un `MeterProvider` et un
`LoggerProvider` — une seule fois par processus, quel que soit le nombre
d'appels à `create_app()` (la suite de tests l'appelle des dizaines de fois
avec des `DATABASE_URL`/`CORE_AUTH_MODE` différents ; un second appel à
`observability.setup()` doit être un no-op silencieux, pas une tentative de
remplacer les providers globaux déjà posés).

### Configuration

Variables d'environnement **standard OTel**, pas préfixées `CORE_` (n'importe
quel collecteur OTLP générique doit pouvoir être branché sans connaître les
conventions internes de ce projet) :

- `OTEL_SERVICE_NAME` — défaut `geostudio-core` (service `core`) /
  `geostudio-worker` (service `worker`).
- `OTEL_EXPORTER_OTLP_ENDPOINT` — absent par défaut. Absence = pas
  d'exportateur attaché (spans/métriques/logs créés en mémoire mais jamais
  exportés, coût négligeable). Défini = exportateurs OTLP réels attachés.
- `OTEL_EXPORTER_OTLP_PROTOCOL` — défaut `http/protobuf` (pas de dépendance
  `grpcio`, cohérent avec le reste du cœur qui n'utilise que `httpx`/`psycopg`,
  aucun gRPC existant dans le projet).

SP-10a ne modifie **pas** le `docker-compose.yml` par défaut (les services
`core`/`worker` actuels ne définissent pas ces variables → comportement
inchangé). SP-10b posera ces variables sous le profil `--profile
observability`.

### Signaux instrumentés

- **FastAPI** : `FastAPIInstrumentor.instrument_app(app)` dans `create_app()`
  — un span par requête HTTP, par instance d'app (pas un état global partagé,
  donc pas de problème d'idempotence ici : chaque test crée sa propre
  instance `FastAPI`).
- **SQLAlchemy** : `SQLAlchemyInstrumentor().instrument(engine=engine)` sur le
  moteur construit par `make_engine()` — spans enfants sur chaque requête SQL.
- **httpx** : `HTTPXClientInstrumentor().instrument()`, process-wide (couvre
  la récupération JWKS Keycloak et tout appel httpx sortant).
- **botocore** : `BotocoreInstrumentor().instrument()`, process-wide (couvre
  la présignature S3/MinIO — décidé au périmètre malgré des appels courts et
  hors des 4 SLO, sur demande explicite).
- **procrastinate** : pas d'auto-instrumentor existant pour cette
  bibliothèque. Procrastinate expose un hook natif, `worker_middleware`
  (`middleware.py`, `WorkerOptions`), configurable via `worker_defaults` sur
  l'`App` partagée (`app/jobs.py`) — s'applique même quand le worker est
  lancé par le CLI (`python -m procrastinate --app app.jobs.app worker`,
  la commande exacte de `docker-compose.yml`), puisque le CLI charge cette
  même instance d'`App`. Un middleware maison ouvre un span par job exécuté
  (nom de tâche, id de job, file), enregistre l'exception et passe le span en
  erreur si le job échoue.
- **Logs** : `LoggingInstrumentor().instrument()` injecte `trace_id`/
  `span_id` dans chaque `LogRecord` du logger racine. Un `Formatter` JSON
  (un objet par ligne) est posé **inconditionnellement** sur la sortie
  standard — que l'endpoint OTLP soit configuré ou non — pour que `docker
  compose logs` reste structuré et corrélable dans les deux cas (choix
  assumé : moins agréable à l'œil nu qu'un texte libre, mais un seul chemin
  de code, pas de bascule conditionnelle à tester). Quand l'endpoint est
  configuré, un second `Handler` (OTLP log exporter) pousse en plus ces mêmes
  `LogRecord` vers le collecteur.

### Idempotence

`observability.setup()` est gardé par un flag module-level : le premier appel
construit providers + instrumentors + attache les exporteurs (si endpoint
présent) ; tout appel suivant dans le même process est un no-op. C'est ce qui
protège la suite de tests (qui appelle `create_app()` en boucle) contre les
erreurs "already instrumented" des instrumentors process-wide (httpx,
botocore) et contre le warning OTel "Overriding of current TracerProvider is
not allowed" sur les providers globaux.

## Métriques métier

Trois compteurs OTel (`Counter`), incrémentés **dans les fonctions de
repository** (`app.items.repository`) plutôt que dans les routes REST — ces
fonctions sont déjà le point de passage commun REST + MCP (cf. SP-2/SP-7 :
`create_item`/`save_app_config`/`create_form_app` appellent les mêmes
fonctions qu'une route REST), donc un compteur posé ici capture les deux
canaux sans duplication ni sous-comptage :

- `geostudio.items.created` — incrémenté dans `app.items.repository.create_item`.
- `geostudio.configs.published` — incrémenté dans
  `app.items.repository.update_item` (c'est `Item.is_published`, pas un champ
  de `Config`, qui porte la publication) quand la transition est bien
  False→True (pas à chaque `update_item` sur un item déjà publié).
- `geostudio.apps.runtime_executions` — incrémenté sur `GET` config avec
  `mode=runtime`.

### Distinction edit/preview vs runtime

`AppRuntimePage` (shell) et l'éditeur du builder appellent aujourd'hui le
même endpoint `GET` config, sans paramètre distinguant le mode. Pour compter
« exécutions runtime » sans SDK OTel côté navigateur (explicitement hors
périmètre, cf. plus bas), `AppRuntimePage.getAppConfig` gagne un paramètre
`?mode=runtime` (changement minimal `ItemClient`/`CoreItemClient`) ; la route
cœur incrémente le compteur seulement quand ce paramètre vaut `runtime`. Pas
d'effet sur l'autorisation ni le rendu — un signal de métrique seulement.

## Hors périmètre de SP-10a (déféré à SP-10b)

- Le profil compose `--profile observability` et le conteneur
  `grafana/otel-lgtm` lui-même.
- Les dashboards Grafana packagés (santé cœur, tuiles Martin, jobs, Postgres).
- Les 4 SLO et leurs règles d'alerte.
- Le critère d'acceptation « une alerte de test se déclenche ».
- Le scraping Prometheus des métriques déjà existantes de Martin, et tout
  export de métriques Postgres (postgres_exporter ou équivalent).
- Toute télémétrie OTel côté shell (navigateur) — le texte du roadmap ne
  mentionne que « le cœur et les workers » ; le critère « trace de bout en
  bout shell → cœur → SQL » se satisfait par la propagation W3C `traceparent`
  sur les requêtes HTTP déjà émises par le shell (aucun SDK OTel navigateur
  nécessaire), et reste de toute façon un critère d'acceptation de SP-10
  global, pas spécifiquement de SP-10a.

## Tests

- Dépendances de test : `opentelemetry-sdk` fournit des exporteurs en mémoire
  (`InMemorySpanExporter`) — les tests assertent la présence/les attributs
  des spans sans jamais parler à un vrai collecteur.
- Test de non-régression explicite : `create_app()` appelé plusieurs fois de
  suite (comme le fait déjà la suite existante) ne lève pas d'exception et ne
  double-instrumente pas httpx/botocore.
- Test que sans `OTEL_EXPORTER_OTLP_ENDPOINT`, aucune tentative de connexion
  réseau n'est faite (pas de warning/erreur de connexion dans les logs).
- Test des 3 compteurs métier : un `create_item` via une route REST et via
  l'outil MCP `create_item` incrémentent tous les deux
  `geostudio.items.created` ; publier une config incrémente
  `geostudio.configs.published` une seule fois (pas à chaque sauvegarde
  ultérieure d'une config déjà publiée) ; `GET` config avec et sans
  `mode=runtime` distingue bien l'incrément de
  `geostudio.apps.runtime_executions`.
- Test qu'un job procrastinate qui lève une exception produit un span en
  statut erreur portant l'exception, sans empêcher la propagation normale de
  l'erreur au reste du système (le comportement d'échec de job existant,
  inchangé).

## Dépendances ajoutées (`core/pyproject.toml`)

`opentelemetry-sdk`, `opentelemetry-exporter-otlp-proto-http`,
`opentelemetry-instrumentation-fastapi`,
`opentelemetry-instrumentation-sqlalchemy`,
`opentelemetry-instrumentation-httpx`,
`opentelemetry-instrumentation-botocore`,
`opentelemetry-instrumentation-logging`.

## Risques

- Poids d'image Docker/temps de build accru par les nouvelles dépendances —
  mitigé par le choix `http/protobuf` (pas de `grpcio`).
- Instrumentors process-wide (httpx, botocore) non ré-entrants : une
  ré-instrumentation accidentelle lèverait une erreur au second
  `create_app()` — mitigé par le flag d'idempotence module-level et un test
  dédié qui exerce explicitement l'appel répété.
- `worker_middleware` est une API procrastinate relativement peu utilisée
  dans l'écosystème — vérifiée présente et fonctionnelle sur la version
  installée (3.9.0, `middleware.py`) avant d'en dépendre.

## Critères d'acceptation

1. `OTEL_EXPORTER_OTLP_ENDPOINT` configuré → une requête HTTP vers le cœur
   produit une trace avec des spans FastAPI → SQLAlchemy (et httpx/botocore
   si la requête en déclenche), exportée en OTLP.
2. Les logs stdout sont en JSON et portent `trace_id`/`span_id` cohérents
   avec le span actif au moment du log, que l'endpoint OTLP soit configuré
   ou non.
3. Un job procrastinate exécuté produit un span (nom de tâche, id, file) ;
   un job en échec produit un span en erreur avec l'exception attachée.
4. `geostudio.items.created` s'incrémente aussi bien via REST que via MCP ;
   `geostudio.configs.published` s'incrémente à la publication (pas à
   chaque sauvegarde) ; `geostudio.apps.runtime_executions` distingue une
   ouverture runtime d'une ouverture éditeur.
5. Sans `OTEL_EXPORTER_OTLP_ENDPOINT` (comportement par défaut de
   `docker compose up`, et de toute la suite de tests) : zéro changement de
   comportement observable, zéro nouvelle erreur/warning réseau, tous les
   tests existants restent verts.
