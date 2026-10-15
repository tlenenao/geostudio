# Brief commun des voies FME (à lire en premier)

Tu es l'implémenteur d'UNE voie du plan `docs/superpowers/plans/2026-10-15-fme-fermeture-108-planned.md`
(lis §0 garde-fous mémoire, §2 définition de « fait » ; les décisions actées en tête priment).
Lis aussi `CLAUDE.md` (pièges) et `docs/superpowers/plans/_fme-lane-template.md` (comment ajouter une op via ton module de voie :
tu n'édites JAMAIS contracts.py / schemas.py / registries.py ni les tests existants à listes figées).
La liste exacte de tes lignes et l'état réel (ce qui est déjà couvert) : `docs/revue/2026-10-15-audit-peremption-fme.md` +
`docs/revue/matrice-couverture-fme.jsonl` (champ `coverage_status` encore `planned_*`/`unknown` pour ta voie).

Règles d'exécution
- Travaille UNIQUEMENT dans ton worktree (cwd donné) sur ta branche ; commits conventionnels en français, petits, un sujet,
  terminés par la ligne exacte `Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>`. `git add` ciblé (jamais `-A`).
- TDD : test rouge d'abord, falsifie (le test doit échouer si on casse l'op). Pour chaque op : checklist §2 (contrat+licence,
  masquage GAP-22, egress/secrets si réseau, aperçu, test d'entrée dégénérée, ligne matrice jsonl).
- Matrice : mets à jour ta ligne dans `docs/revue/matrice-couverture-fme.jsonl` (`implemented`, `geostudio_equivalent`,
  `engine`, `engine_license`, notes) ; NE régénère PAS le .md (le contrôleur le fait à la fusion, évite les conflits).
  Si une op ne peut pas être faite honnêtement (licence copyleft, driver absent, dépendance interdite, risque sécurité),
  NE la bricole pas : laisse la ligne `planned_*` et liste-la dans ton rapport avec la raison (le contrôleur tranchera).
- Dépendances : n'ajoute une dépendance Python que si MIT/BSD/Apache, déjà dans `core/pyproject.toml` ou clairement nécessaire ;
  jamais de copyleft ; mentionne-la dans le rapport (uv.lock inclus dans ton commit).
- RAM (machine 16 Go partagée par 3 voies) : pytest CIBLÉ sur tes fichiers de test uniquement, en FOREGROUND, jamais la suite
  complète, jamais `-n`, pas de docker build, fixtures < 1 Mo. DuckDB: `SET memory_limit='768MB'; SET threads=2`.
  Env de test : `cd <worktree>/core && uv sync` puis
  `CORE_TEST_DATABASE_URL=postgresql+psycopg://gis:gis@localhost:5433/gs_fme_<voie> uv run pytest <tes tests> -q --basetemp=<scratchpad>/pt-<voie>`
  (la base existe déjà avec postgis). Portes avant le dernier commit : `uv run ruff check . && uv run ruff format --check .`,
  `uv run lint-imports`, et `uv run pytest tests/test_pipeline_operation_contract*.py tests/test_fme_coverage_cli.py -q` (nom
  exact : trouve les tests de contrat/matrice existants) pour prouver l'absence de régression de la couture.
- Pas d'OpenAPI/types TS à régénérer sauf si tu ajoutes une ROUTE/un modèle d'API (les ops n'en ajoutent pas) — si doute, dis-le.
- Ledger/rapport : écris ton rapport complet dans le fichier indiqué ; retourne seulement : statut (DONE / DONE_WITH_CONCERNS /
  BLOCKED), liste des commits, 1 ligne de résultat de tests (commande + n passed), lignes laissées `planned_*` avec raison, concerns.
