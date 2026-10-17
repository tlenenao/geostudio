# SP-L4 — plan d'exécution

Spec : `docs/superpowers/specs/2026-10-18-sp-l4-multi-tenant-gouvernance-design.md`. TDD, un commit
par sujet, revue finale de branche avec liste des jumelles de garde (piège n°14).

1. AUD-011 — `drop_managed_table` + test postgis (commit e221d09e).
2. AUD-093 — `masked_attachment_keys` sur les 4 lecteurs (c12a16d0).
3. AUD-095 — groupe de débit `discovery` + timeout d'emprise STAC (77b12d0c).
4. AUD-092/120/121 — migrations 0120/0121, chaîne, rétention, export, journal S3, rattrapage (bdcde35d).
5. AUD-097 — migration 0123, `share_active` sur les lecteurs, `expiresAt` en écriture (e2ff1dc9).
6. AUD-098 — migration 0122, `TenantLimits`, plafonds utilisateurs/runs, câblage env (e9a943fd).
7. AUD-010 — décision de report consignée dans la spec.
8. Porte de clôture : ruff, mypy strict, lint-imports, pytest base réelle sans skip silencieux,
   vitest, lint/format shell, build, E2E complète.
9. Revue finale : jumelles de garde, migrations sur base non vide dans les deux sens.
