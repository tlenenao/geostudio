# Audit multi-agents : parcours utilisateurs, code, tests Playwright sur stack réelle

Date : 2026-09-29. Statut : architecture validée par Tanguy (3 échanges), en attente de relecture de ce document.

## 1. Objectif

Identifier de façon exhaustive et vérifiable ce qu'il faut corriger, combler, améliorer et ajouter dans GeoStudio, à partir de parcours utilisateurs réels et d'un audit de code au niveau de la ligne. Produire :

1. des specs Playwright exécutables sur **stack réelle** (nouveau projet `journeys`) ;
2. des rapports d'agents dans un format unique, validé par script ;
3. un document consolidé `PLAN-CONSOLIDE.md` : état des lieux + **30 tâches en 6 phases de 5**.

Hors périmètre : corriger quoi que ce soit (les agents sont en lecture seule sur le code source). La correction suit, par plan superpowers classique.

Entrée « déjà connu » : `docs/revue/2026-09-29-audit-pre-release.md` (audit de 20 agents du jour). Les agents ne re-signalent pas ses items, ils peuvent les référencer via `related_gap`.

## 2. Principes

- **Lecture seule sur le source.** Un agent n'écrit que dans `docs/revue/audit-2026-09-29/<agent-id>/` et (agents A/B) dans `shell/e2e/journeys/<agent-id>/`.
- **Preuve exécutée.** Un finding `verified` cite une exécution (Playwright ou commande). Piège n°12 : le récit ne compte pas. Piège n°11 : suivre le chemin d'exécution réel d'un garde, pas un `grep`.
- **Le contrôleur ne lit pas les rapports.** Il relit les prompts, le tableau de validation et le document consolidé.
- **Rejeu à 100 % des S1/S2** par un agent vérificateur indépendant, sur un autre tenant.

## 3. Format commun

Par agent : `findings.jsonl` (une ligne = un finding) et `resume.md` (périmètre couvert/non couvert, méthode). Validateur : `scripts/audit/validate_findings.py`, rejette tout fichier non conforme ; l'agent corrige avant de terminer.

| Champ | Valeurs / contenu |
|---|---|
| `id` | `<AGENT>-nnn` |
| `kind` | bug, gap, improvement, feature, debt, security, a11y, perf, test-gap |
| `severity` | S1 bloquant, S2 majeur, S3 mineur, S4 cosmétique |
| `effort` | XS, S, M, L, XL |
| `journey` | id du parcours ou `transverse` |
| `locations[]` | `{file, line_start, line_end, symbol}` ; obligatoire si `kind` ≠ `feature` |
| `observed`, `expected` | une phrase chacun |
| `evidence` | `{type: playwright-run / command-output / code-read / doc-read, ref}` |
| `repro` | spec + nom du test, ou commande exacte |
| `proposed_fix` | pistes + fichiers à toucher |
| `confidence` | verified, probable, hypothesis (`verified` exige une evidence exécutée) |
| `depends_on[]`, `related_gap` | liens (GAP-nn, REV-nnn, autre finding) |

Le validateur dédoublonne par `(file, symbol)` et fusionne les recoupements.

## 4. Agents (≈ 27)

**A. Parcours (13), Playwright obligatoire, 25 à 40 tests chacun** : visiteur anonyme ; lecteur connecté ; créateur de carte ; créateur d'app ; analyste ; data engineer ; data steward ; admin tenant ; ops ; sites/storytelling/export d'apps ; copilote IA + MCP ; terrain (mobile/tactile) ; partage et permissions.

**B. Transverses avec tests (4)** : accessibilité (axe + clavier) ; résilience (401/403/500, réseau coupé, quotas) ; performance perçue ; cohérence visuelle et i18n.

**C. Audit de code (9), `file:line`** : authz/RLS/IDOR ; correctness backend ; migrations et données (round-trip sur base non vide) ; qualité shell ; qualité des tests ; CI/déploiement/ops ; dérive doc et inventaire ; parité REST/MCP/`ItemClient` ; performance backend.

**D. Benchmark produit (1)** : Felt, ArcGIS, QGIS Server, Kepler/CARTO, FME → findings `feature`/`gap`.

**V. Vérificateur** : rejoue chaque S1/S2 `verified` sur un tenant distinct.

**K. Consolidateur** : produit `PLAN-CONSOLIDE.md`.

## 5. Exécution sur stack réelle

- Nouveau `shell/playwright.journeys.config.ts` : baseURL `http://localhost:8300`, `workers: 3`, pas de mock réseau. La suite mockée actuelle (166 tests) reste intacte.
- **Un tenant par agent** : fixture partagée `shell/e2e/journeys/_fixtures/tenant.ts` qui crée tenant + utilisateurs par rôle, et purge via `purge_tenant` en teardown. Auth OIDC réel (Keycloak) pour les parcours de rôles (admin, partage, permissions) ; `CORE_AUTH_MODE=mock` (dev seulement) ailleurs.
- **Plafond 3 agents Playwright en parallèle** (RAM ~12 Go, Chromium). Agents C en parallèle sans limite pratique.
- **Injection de fautes** (500, réseau coupé, quota, `docker stop` ciblé) dans un projet Playwright séparé, en série.
- **Isolation git** : agents A/B sur branche `audit/<agent-id>` en worktree éphémère (supprimé dès fusion, règle CLAUDE.md) ; ledgers nommés `.superpowers/sdd/audit-*`.
- **Sort des tests** : passe → suite de régression `e2e/journeys/` ; révèle un bug → `test.fixme` + ID du finding ; instable → `@audit-flaky`.

## 6. Vague 0 (avant tout lancement d'agent)

1. Diagnostic du `worker` (redémarré ~1 min avant relevé, cf. notes SP-10b) : stable, sinon parcours import/pipeline faussés.
2. `scripts/audit/validate_findings.py` + schéma JSON + tests.
3. `playwright.journeys.config.ts` + fixture tenant + un parcours témoin qui prouve le cycle création/purge.
4. Gabarit de prompt commun (format, règles de preuve, périmètre, interdiction d'écrire hors dossiers) ; 1 prompt par agent, **présentés à Tanguy avant lancement**.

## 7. Consolidation

`PLAN-CONSOLIDE.md` : état des lieux par parcours + matrice de couverture des tests ; 30 tâches en 6 phases de 5 (bloquants/hygiène ; sécurité/authz ; correctness des parcours ; filet de tests ; UX/a11y/résilience ; fonctionnalités du benchmark), chacune avec findings couverts, fichiers, effort, dépendances, test d'acceptation ; table de traçabilité (chaque S1/S2 → tâche ou rejet motivé).

## 8. Risques

- Stack partagée : collisions malgré les tenants (tables globales, `alembic_version`) → les agents signalent, ne « corrigent » pas l'environnement.
- Worker instable → traité en vague 0.
- Volume de findings : budget de tests par agent, pas de plafond de findings ; dédoublonnage par script.
- Coût : ~27 agents + vérificateur ; lancement par vagues, arrêt possible entre vagues.
