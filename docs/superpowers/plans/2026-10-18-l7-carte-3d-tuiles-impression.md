# Lot L7 — plan d'exécution

Spec : `docs/superpowers/specs/2026-10-18-l7-carte-3d-tuiles-impression-design.md`. TDD, un commit
conventionnel par constat, revue par tâche puis revue finale de branche.

1. AUD-049/053 — rendu carte (remontage du fond, filtre temporel, `pkColumn`, glyphs, jeton 3D).
2. AUD-055/056/099 — budget de tuiles, TiTiler sans connexion tenue, échantillon par hash,
   `statement_timeout` et plafond d'`offset`.
3. AUD-054 — proxy tileset3d en cache, zip à dossier racine, plafond du `tileset.json`.
4. AUD-058 — format et rejeu du rapport, dpi d'export.
5. AUD-057 — atlas plafonné/trié côté cœur, bandeau de troncature.
6. AUD-060 — géométrie du signet.
7. AUD-059 — pivot, fenêtre de référence, widget Période.
8. AUD-051 — plage d'échelle par couche.
9. AUD-061 — retard du lac sur les widgets.
10. Portes de clôture (ruff, mypy strict, lint-imports, pytest base réelle, vitest, lint/format
    shell, build, E2E complète), revue finale, rapport.
