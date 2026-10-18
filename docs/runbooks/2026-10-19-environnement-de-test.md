# Environnement de test du cœur : pièges et recette

Quatre pièges d'environnement ont coûté des heures de diagnostic (audit 2026-10-16,
AUD-139) ; aucun n'est un défaut du code sous test.

## Recette : une base de test jetable, à soi

```bash
docker run -d --name gs-pg-test -p 55480:5432 -e POSTGRES_PASSWORD=test -e POSTGRES_DB=gis_test \
  geostudio-postgis-test:local -c wal_level=logical      # image construite depuis deploy/postgis
export CORE_TEST_DATABASE_URL=postgresql+psycopg://postgres:test@localhost:55480/gis_test
export DATABASE_URL=$CORE_TEST_DATABASE_URL
cd core && uv run pytest -q -p no:cacheprovider --basetemp="$HOME/.cache/gs-pytest"
```

Un port hôte distinct par session évite les collisions (`UniqueViolation`,
`DuplicateTable`) quand plusieurs sessions partagent un même `postgis-test`.

## Les pièges

1. **`DATABASE_URL` non exporté** : tout test qui *défère* un job attend 60 s (la tâche
   procrastinate ouvre sa propre connexion via `DATABASE_URL`, pas via
   `CORE_TEST_DATABASE_URL`). Symptôme : ~10 tests à 60,5 s dans `--durations`, suite à
   45 min. Remède : exporter les deux variables avec la même valeur.
2. **`/tmp/pytest-of-<user>` appartenant à un autre utilisateur** (root, après un run en
   conteneur) : `OSError: The temporary directory ... is not owned by the current user`
   sur tout test utilisant `tmp_path`. Remède : `--basetemp=<dossier à soi>` (ou supprimer
   le dossier en root).
3. **Schéma de `gis_test` périmé** : le conteneur de test n'est pas suivi par Alembic ; le
   schéma est construit par `Base.metadata.create_all`, qui n'ajoute jamais une colonne à
   une table existante. Après une migration qui ajoute des colonnes : `UndefinedColumn` en
   cascade, sans rapport avec le code sous revue. Remède : recréer la base
   (`DROP DATABASE gis_test; CREATE DATABASE gis_test;` puis relancer) ou `ALTER TABLE`
   manuel ; ne pas essayer de « réparer » un test.
4. **`helm` absent** : `tests/test_helm_chart.py` saute 17 tests (`helm absent`), le chart
   n'est alors pas validé. Remède : installer `helm` (binaire unique) avant de toucher
   `deploy/helm/`.

`CORE_REQUIRE_DB=1` (posé en CI) transforme le saut silencieux des tests PostGIS en échec :
à poser aussi en local avant de conclure qu'une suite est verte.
