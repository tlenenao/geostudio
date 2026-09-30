# c07 — Dérive doc et inventaire

## Couvert
- CLAUDE.md (Livré, Suivis, Commandes) recoupé avec code : pyproject, ci.yml, .pre-commit-config, compose, seuils, a11y spec, MCP save_app_config.
- Backlog REV (états fermé/ouvert vs code) et analyse GAP : échantillon GAP-03/30/32/39/46/47/67, REV-096/108/114/174/175/176/178/185/194.
- Inventaire jsonl : 308 lignes, ids uniques, tous les fichiers `preuve` existent ; routes inventoriées vs OpenAPI (les écarts viennent de routes derrière flag éteint à l'export, la porte est test_feature_inventory).
- OpenAPI : export régénéré identique à core/openapi.json ; types TS régénérés identiques à shell/src/api/generated/core-schema.d.ts (pas de dérive, piège n°1).
- Sains : GAP-03/30/32/39/46/47 fermés cohérents avec le code ; REV-096 (egress LLM), REV-194 (deploy/minio/Dockerfile), REV-185 (encore ouvert, cohérent).

## Non couvert
- Vérification exhaustive des 83 GAP et 265 REV (échantillon seulement).
- Routes/outils MCP/pages shell inventoriés un à un (délégué à test_feature_inventory).
- Items déjà connus de l'audit pré-release (arm64 8/9, secret_scanning, check-fresh) non re-signalés.
- `feature_health_cli --check` local échoue (25 features sous plancher) : artefact probable d'un coverage.xml local partiel, non imputé au code (piège documenté) ; non tracé en finding.

## Commandes
feature_health_cli --check / --check-fresh ; export_openapi.py (vers scratchpad) + diff ; openapi-typescript + diff ; tomllib layers ; check_claude_md_size.py ; greps CLAUDE.md/backlog/analyse-gaps.
