# Plan L11 — i18n et accessibilité

Spec : `docs/superpowers/specs/2026-10-18-l11-i18n-accessibilite-design.md`. TDD, un commit par tâche.

1. Mécanisme de langue (`i18n/index.ts`), chunk anglais typé, parité testée (`locale.test.ts`).
2. `lib/format.ts` paramétré + remplacement des sites `fr-FR` + règle ESLint.
3. Sélecteur de langue (Paramètres) + claim OIDC + E2E `i18n-language.spec.ts`.
4. Buckets temporels au fuseau demandé (cœur + shell) ; libellé XLSForm déterministe.
5. Graphiques accessibles (`EChart`, `chartTable`) ; liste d'entités de la carte (`MapFeatureList`).
6. Palette de commandes ; polices et jetons sémantiques d'app.
7. Revue finale (jumelles de garde) + porte complète.
