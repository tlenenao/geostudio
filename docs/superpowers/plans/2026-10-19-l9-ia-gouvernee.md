# Lot L9 — plan d'exécution

Spec : `docs/superpowers/specs/2026-10-19-l9-ia-gouvernee-design.md`. TDD, un commit par tâche, revue par tâche puis finale.
Migrations : plage 0170–0179 uniquement (0170 = `llm_usage` + `tenant_llm_settings`).

1. AUD-103 — `turnId`, `argsSha256`, outcome d'erreur, `get_llm_provider()` dans le `try`, fusion dans `write_audit`.
2. AUD-102 — `confirmToken` HMAC côté cœur + résumé d'arguments et jeton côté shell.
3. AUD-104a — validation du SQL généré (AST, tables, réparation, warnings) + fencing des 4 générateurs.
4. AUD-105 — annotations MCP, prompts, outils `list_pipeline_ops`/`get_config_history`, test d'invariant.
5. AUD-106/149 — migration 0170, `usage` lu, quota, `llm_usage`, paramètres par tenant, routes, contexte résumé.
6. AUD-104b — `core/evals/copilot/` + commande + test hors ligne.
7. Portes (ruff, mypy strict, lint-imports, pytest, OpenAPI/types, vitest/lint/build, E2E), revue finale, rapport.
