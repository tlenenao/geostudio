# Rapport — fixes revue finale SP-15f (Finding #1 + #6)

Branche `dev`, base HEAD 7341d35, pas de worktree (convention du dépôt).

## Finding #1 (Important) — traduction des échecs dlt en cours d'extraction

### Problème

`_run_dlt_and_attach` (`core/app/pipelines/connector_runtime.py`) n'attrapait
aucune exception autour de `pipeline.run(resource)`. Tout échec **pendant**
l'extraction dlt elle-même (garde SSRF bloquant l'URL de DONNÉES — pas
seulement l'URL de jeton OAuth2, déjà couverte —, erreur HTTP distante,
échec de connexion/requête Postgres, JSON malformé) ressortait enveloppé
dans un type dlt (`PipelineStepFailed`/`ResourceExtractionError`), pas
`ConnectorRuntimeError`. `runtime.py::_prepare()` ne traduit que
`ConnectorRuntimeError` → `PipelineRuntimeError` ; tout le reste fuit tel
quel jusqu'à :
- `routes.py::preview_pipeline_route` : seul `PipelineRuntimeError` devient
  un 400 propre (`except PipelineRuntimeError as exc: raise HTTPException(400, ...)`)
  — une exception dlt brute retombe dans le gestionnaire d'erreur générique
  FastAPI (500).
- `jobs.py::run_pipeline_task` : `except (PipelineRuntimeError, ValueError)`
  produit `mark_failed(error=str(exc))` propre ; le `except Exception`
  générique produit `error=f"erreur interne : {exc}"` — le run finit bien
  "failed" (jamais zombie), mais avec le pire message possible pour le cas
  le plus sécuritairement significatif (blocage SSRF).

### Fix

Dans `_run_dlt_and_attach` (`core/app/pipelines/connector_runtime.py`),
englobé `pipeline.run(resource)` **et** le bloc ATTACH/sélection/DETACH dans
un `try/except` :

```python
def _find_egress_blocked_cause(exc: BaseException) -> EgressBlockedError | None:
    seen: set[int] = set()
    current: BaseException | None = exc
    while current is not None and id(current) not in seen:
        if isinstance(current, EgressBlockedError):
            return current
        seen.add(id(current))
        current = current.__cause__ or current.__context__
    return None


def _run_dlt_and_attach(conn, resource, *, node_id: str, view_name: str) -> None:
    scratch_dir = tempfile.mkdtemp(prefix=f"sp15f-{node_id}-")
    db_path = f"{scratch_dir}/extract.duckdb"
    try:
        pipeline = dlt.pipeline(...)
        try:
            pipeline.run(resource)
            conn.execute(f"ATTACH '{db_path}' AS dlt_extract (READ_ONLY)")
            try:
                ...  # inchangé : select_list, CREATE TEMP TABLE
            finally:
                conn.execute("DETACH dlt_extract")
        except ConnectorRuntimeError:
            raise  # jamais de double-enveloppe si une ConnectorRuntimeError
                   # venait à naître à l'intérieur de ce bloc
        except Exception as exc:
            egress_cause = _find_egress_blocked_cause(exc)
            if egress_cause is not None:
                raise ConnectorRuntimeError(f"egress blocked: {egress_cause}") from exc
            raise ConnectorRuntimeError(f"reader.connector extraction failed: {exc}") from exc
    finally:
        shutil.rmtree(scratch_dir, ignore_errors=True)
```

Ce helper est partagé par `materialize_rest_connector` ET
`materialize_postgres_connector` — les deux bénéficient sans duplication.

### Décisions / arbitrages

1. **Déroulement de la chaîne de causes** : `__cause__` puis `__context__`,
   avec un set `seen` par `id()` pour éviter toute boucle infinie si jamais
   une chaîne se referme sur elle-même (défense en profondeur, pas rencontré
   empiriquement). dlt chaîne systématiquement via `__cause__`
   (`raise ... from ...`), vérifié sur le cas OAuth2 existant.
2. **Portée du wrapping** : `pipeline.run()` **et** le bloc ATTACH/SELECT
   (pas seulement `pipeline.run()` comme le minimum demandé) — le fichier
   DuckDB écrit par dlt pourrait en théorie être tronqué/corrompu si
   l'extraction s'arrête à mi-chemin dans un état inattendu ; autant que
   toute erreur DuckDB de cette phase bénéficie de la même traduction propre.
3. **Message pour le cas SSRF** : `f"egress blocked: {egress_cause}"` — le
   texte de `EgressBlockedError` est déjà descriptif et sûr (ex.
   `cible réseau interne bloquée : '127.0.0.1' → 127.0.0.1`, ou
   `hôte non résoluble : '...'`), aucune donnée sensible dedans par
   construction (`app/pipelines/egress.py`).
4. **Message pour les autres échecs** : `f"reader.connector extraction failed: {exc}"`.
   Vérifié EMPIRIQUEMENT (pas supposé) qu'aucune des deux formes réalistes
   d'échec Postgres ne fait fuiter le mot de passe du DSN :
   - Connexion refusée (port fermé) : `(psycopg.OperationalError) connection
     failed: connection to server at "127.0.0.1", port 1 failed: Connection
     refused` — pas de DSN, pas de mot de passe.
   - Authentification échouée (contre le conteneur Postgres de test réel,
     `gis:gis@127.0.0.1:5433/gis_test`, mot de passe substitué par un faux) :
     `(psycopg2.OperationalError) connection to server at "127.0.0.1", port
     5433 failed: FATAL:  password authentication failed for user "gis"` —
     toujours aucun mot de passe dans le message.
   Ces deux vérifications ont été faites via `uv run python -c "..."` contre
   `sqlalchemy.create_engine(...)` avant d'écrire le message, pas supposées
   depuis la doc.

## Regression test (Finding #3, minor, inclus)

Nouveau test dans `core/tests/test_pipeline_connector_runtime.py` :
`test_materialize_rest_connector_data_url_egress_block_raises_connector_runtime_error`.

Réactive la VRAIE garde SSRF pour ce seul test (même technique que
`test_materialize_rest_connector_oauth2_token_exchange_goes_through_ssrf_guard` :
capture de `_REAL_ASSERT_EGRESS_ALLOWED` au chargement du module, avant que
l'autouse fixture `_no_ssrf_guard` ne la neutralise, puis
`monkeypatch.setattr` pour la restaurer dans ce test précis). Cible
`baseUrl="http://127.0.0.1:1/"` (loopback, port fermé — jamais de vraie
connexion tentée puisque la garde bloque avant l'envoi de la requête) et
vérifie :

```python
with pytest.raises(connector_runtime.ConnectorRuntimeError, match="egress blocked"):
    connector_runtime.materialize_rest_connector(...)
```

Ce test échouait avant le fix (l'exception qui sortait était un type dlt
brut, pas `ConnectorRuntimeError`) et passe après.

## `.env.example`

Ajouté après `CORE_ETL_ENABLED=false` (racine, `/.env.example` — pas de
`core/.env.example` dans ce dépôt) :

```
# Allowlist d'hôtes pour la garde d'egress SSRF des connecteurs de pipeline
# (reader.connector.rest, SP-15f) — liste séparée par des virgules ; vide
# (défaut) = seules les plages réseau internes/privées sont bloquées, aucune
# restriction d'hôte supplémentaire.
CORE_PIPELINES_EGRESS_ALLOWLIST=
```

Note : `CORE_HARVEST_EGRESS_ALLOWLIST` (le pendant côté `app.harvest`, SP-12d)
n'est en fait PAS documenté dans `.env.example` non plus — pas de convention
préexistante à reproduire pour cette variable précise ; placé au plus proche
de `CORE_ETL_ENABLED` (la capacité qui active toute la surface pipelines,
donc ce connecteur) plutôt que dans la section SP-15e (coffre de secrets),
qui est un sujet distinct.

## Ce qui n'a PAS été touché (findings différés, par consigne)

- #2 : `test_run_pipeline_reader_connector_rest_never_leaks_secret_value` —
  laissé tel quel.
- #4 : heuristique du garde SELECT-only — laissé tel quel.
- #5 : absence de borne lignes/taille sur l'extraction connecteur — laissé
  tel quel.

## Preuves TDD

1. Lu en entier `connector_runtime.py`, `runtime.py`, `routes.py`, `jobs.py`
   avant toute modification (confirmé la chaîne d'erreurs décrite ci-dessus).
2. Vérification empirique préalable (avant d'écrire le message d'erreur) du
   contenu de `str(exc)` pour deux échecs Postgres réalistes (connexion
   refusée + mot de passe erroné contre le conteneur `gis_test` réel) — voir
   §"Décisions" point 4.
3. Écrit le nouveau test AVANT de vérifier qu'il échouait sur le code
   d'origine (exécution locale confirmée : sans le fix, l'exception levée
   n'était pas `ConnectorRuntimeError`), puis appliqué le fix, puis confirmé
   le test vert.
4. Confirmé qu'aucun test existant (wrong-secret-kind, missing-secret,
   SELECT-only-rejection, régression OAuth2) n'a changé de comportement
   observable — leurs assertions `match=...`/chaîne de causes tiennent
   toujours, car :
   - Les rejets pré-flight (`_resolve_secret`, `_build_auth`,
     `validate_select_only`) sont levés AVANT tout appel à
     `_run_dlt_and_attach`, donc hors de la nouvelle zone de wrapping — ils
     ne passent pas par le nouveau code, aucun changement possible.
   - Le test OAuth2 marche par déroulement manuel de `__cause__` jusqu'à
     trouver `EgressBlockedError` (`pytest.raises(Exception)`, pas un type
     précis) — la nouvelle `ConnectorRuntimeError` s'ajoute un niveau
     au-dessus dans la chaîne, sans casser la recherche.

## Résultats de tests

### Fichiers ciblés

```
cd core && CORE_TEST_DATABASE_URL="postgresql+psycopg://gis:gis@127.0.0.1:5433/gis_test" \
  uv run pytest tests/test_pipeline_connector_runtime.py tests/test_pipeline_runtime.py -v
```

→ **38 passed, 2 skipped** (les 2 skips sont les tests `@pytest.mark.qgis`
préexistants nécessitant le sidecar réel, non touchés par ce fix, cf. notes
SP-15d — inchangés).

### Suite complète

```
cd core && CORE_TEST_DATABASE_URL="postgresql+psycopg://gis:gis@127.0.0.1:5433/gis_test" \
  uv run pytest -q
```

→ **1238 passed, 5 skipped** en 93.67s. Zéro régression branche entière.

## Fichiers modifiés

- `core/app/pipelines/connector_runtime.py` — wrapping `_run_dlt_and_attach`
  + helper `_find_egress_blocked_cause`, import `EgressBlockedError`.
- `core/tests/test_pipeline_connector_runtime.py` — nouveau test de
  régression.
- `.env.example` — documentation `CORE_PIPELINES_EGRESS_ALLOWLIST`.
