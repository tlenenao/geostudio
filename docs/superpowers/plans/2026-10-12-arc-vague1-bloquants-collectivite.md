# Vague 1 « bloquants collectivité » ARC-10 à ARC-19 — Plan d'exécution parallèle

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans. Steps use checkbox (`- [ ]`) syntax.

**Goal :** livrer d'ici le 2027-01-11 les 10 chantiers de la Vague 1 de rattrapage ArcGIS Enterprise (86 j-h) en 5 voies parallèles, sans collision de fichiers ni de migrations.

**Source de vérité des chantiers :** `docs/revue/2026-10-11-comparatif-fme-arcgis-enterprise.md` §6.1.2, lignes ARC-10 à ARC-19 (livrable, critères d'acceptation, dépendances). Ce plan ne les recopie pas : il les **ordonne, les répartit et fixe le protocole**. Chaque critère d'acceptation de la ligne ARC est un test à écrire (TDD).

**Architecture :** 5 voies, une branche éphémère par voie (`arc1-lane-<x>`, worktree), fusionnées une à une dans `dev` par le contrôleur. Une **tâche d'intégration** finale (seule à toucher aux fichiers partagés) régénère OpenAPI/types TS, l'inventaire et le bilan, et met à jour la documentation.

**Tech Stack :** FastAPI/SQLAlchemy/Alembic/pytest (`core/`), React/Vitest/Playwright (`shell/`), MapLibre, procrastinate, DuckDB, Docker Compose/Traefik.

## Global Constraints

- Arbitrages A1–A40 non rediscutés ; toute écriture passe par `can()` ; `tenant_id` + `audit_log` sur toute table/écriture ; `lint-imports` vert.
- Branche de promotion : `dev` seulement ; commits conventionnels, petits, un sujet ; trailer `Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>` ; docs en français, code en anglais.
- TDD systématique ; chaque fonctionnalité visible a sa spec E2E Playwright ; toute nouvelle surface (route REST, outil MCP, route shell) est ajoutée à `docs/revue/inventaire-fonctionnalites.jsonl` (porte CI, tâche d'intégration).
- Pièges applicables : n°1 (OpenAPI/types), n°2 (câblage compose par valeur), n°3 (vérifier chaque `fichier:ligne` dans le code), n°4 (revue par tâche **et** finale), n°5 (`toFrontLayer()`), n°8 (migration sur base non vide, deux sens), n°9 (ledgers `.superpowers/sdd/arc1-<voie>-*`), n°14 (jumelles de garde listées avant clôture).
- Ne jamais utiliser le `postgis-test` partagé pour un test destructif (piège SP-49).

## Répartition en voies

| Voie | Chantiers (ordre) | Effort | Zone de fichiers (exclusive) |
|---|---|---|---|
| **A — OGC lecture** | ARC-12 (CQL2) → ARC-11 (WFS 2.0 + OGC Tiles) | 16 j | `core/app/features/` (filtres/lecture), nouveau `core/app/ows/`, `core/pyproject.toml` (contrat `lint-imports`) |
| **B — Qualité de données** | ARC-13 (domaines/sous-types) → ARC-14 (règles CEL) | 18 j | `features/validation.py`, `core/app/collections/` (schéma), `ingestion/` (rejets), formulaires shell (`shell/src/builder/widgets/form.tsx`) |
| **C — Historique et soumission publique** | ARC-15 (historique d'entité) → ARC-10 (soumission publique) | 18 j | nouveau `core/app/history/`, nouveau `core/app/public_submit/`, `attachments/`, `notifications/` |
| **D — Symbologie et impression** | ARC-17 (4 modes de symbologie) → ARC-16 (gabarits d'impression) | 18 j | `shell/src/builder/widgets/mapSymbology.ts`, `MapSymbologyEditor`, `core/app/export/`, `core/app/configs/schemas.py` (`printLayout`) |
| **E — Exploitation** | ARC-19 (drill de restauration) → ARC-18 (HA testée) | 16 j | `deploy/`, `scripts/replay/`, `.github/workflows/`, `core/app/ratelimit/`, `docs/runbooks/` |

Chemin critique : 18 j (voies B, C, D). Total 86 j-h ; 5 subagents en parallèle ≈ 18 j de travail effectif + intégration 3 j.

**Pourquoi ces regroupements :**
- `features/*` est touché par ARC-10/12/13/14/15 (collision principale). Chaque voie a une **sous-zone** : A = lecture/filtres, B = validation, C = journal d'écriture (un seul crochet dans les fonctions d'écriture de `repository.py`) puis garde `pending`. Les conflits résiduels sont arbitrés par le contrôleur à la fusion.
- ARC-10 passe **en dernier de la voie C** : la garde `pending` touche toutes les lectures ; la voie se rebase sur A et B déjà fusionnées.
- ARC-17 avant ARC-16 : la légende imprimée doit refléter les nouveaux modes.
- ARC-19 avant ARC-18 : la bascule HA s'appuie sur un drill de restauration fiable.

**Migrations (tête actuelle = 0054, à revérifier au départ) :** ARC-15 → `0055_entity_history`, ARC-13 → `0056_collection_domains`, ARC-14 → `0057_attribute_rules`, ARC-10 → `0058_submission_tokens`, ARC-11 → `0059` seulement si le drapeau d'activation par collection exige une colonne. Une voie qui découvre un besoin supplémentaire le consigne dans son ledger et prend le numéro suivant auprès du contrôleur.

**Fichiers interdits aux voies (réservés à l'intégration) :** `core/openapi.json`, `shell/src/api/generated/core-schema.d.ts`, `docs/revue/inventaire-fonctionnalites.jsonl`, `docs/revue/bilan-fonctionnalites.*`, `docs/revue/2026-09-04-backlog.md`, `docs/revue/2026-09-04-analyse-gaps.md`, `CLAUDE.md`, archive d'historique.

## ADR courts à écrire avant lancement (contrôleur)

- [ ] **ADR soumission publique (ARC-10)** : nouvel écart contrôlé à `can()` (jeton de soumission, écriture `pending` seulement, aucune lecture anonyme élargie) ; captcha = honeypot + rate limit dédié, sans service tiers.
- [ ] **ADR OWS (ARC-11)** : rendu/lecture par le cœur sous `rls_scope` + `can()`, aucun sidecar GPL (précédent `transform.qgis`), capacité activée par collection, absente du compose si le flag est éteint.
- [ ] **Borne HA (ARC-18)** : runbook + test de bascule + invariants à 2 réplicas ; limiteur partagé et élection `cdc-worker` restent dans ARC-32 (hors périmètre).

## Protocole commun à chaque voie (repris dans chaque prompt de subagent)

- [ ] **Étape 0 — Vérifier le plan contre le code** (piège n°3) : relire chaque `fichier:ligne` de la ligne ARC ; corriger sans redemander, consigner l'écart dans `.superpowers/sdd/arc1-<voie>-ledger.md`.
- [ ] **Étape 1 — Worktree dédié** `arc1-lane-<x>` (`EnterWorktree`), base = `dev` à jour ; jamais d'écriture hors de la zone exclusive de la voie.
- [ ] **Étape 2 — Par chantier** : tests d'acceptation en premier (rouges), implémentation, tests verts, E2E si surface visible, commit conventionnel.
- [ ] **Étape 3 — Revue par tâche** (sous-agent distinct) ; **jumelles de garde listées** (piège n°14) avant clôture du chantier.
- [ ] **Étape 4 — Rapport de voie** : fichiers touchés, migrations, nouvelles surfaces (routes/outils/pages) à inventorier, écarts au plan. Le contrôleur vérifie `git show --stat` lui-même (hygiène de commit des sous-agents).

## Tâches par voie (points d'attention propres)

### Voie A
- [ ] **ARC-12** : parseur CQL2-text → SQL **paramétré** (aucune interpolation, noms de colonnes via `sql_ident`) ; réutiliser la validation `geom_intersects` ; `conformsTo` mis à jour ; 40 expressions de référence + cas d'injection (`filter=1=1; DROP` = 400).
- [ ] **ARC-11** : module `app/ows/` (couche `features` → `ows`, entrée `lint-imports`) ; WFS 2.0 GetCapabilities/DescribeFeatureType/GetFeature (GML 3.2 + GeoJSON), OGC API Tiles ; **mêmes `rls_scope`/`can()` + masquage de champs GAP-22** ; activation par collection ; flag câblé dans le compose **par valeur** (piège n°2). Jumelles : STAC, MVT, exports.

### Voie B
- [ ] **ARC-13** : domaines `list`/`range` + sous-types sur le schéma de collection, appliqués à l'écriture (REST, import, `writer.collection`) et dans les formulaires générés ; pas de rétro-application (rapport seulement) ; migration sur base non vide.
- [ ] **ARC-14** : règles CEL `calculation`/`constraint`/`batch` (rapport de qualité en job, réutilise le port Rejected) ; NL→règle par MCP avec revue humaine ; batch 50 000 entités < 60 s mesuré.

### Voie C
- [ ] **ARC-15** : journal `before/after` écrit **dans la même transaction** que l'écriture ; `GET …/items/{fid}/history`, `GET …/changes?since=`, restauration d'une version, onglet Historique shell ; champs masqués restent masqués ; anonymisation SP-58 efface l'auteur ; quotas + purge.
- [ ] **ARC-10** : `SubmissionToken` (quota, expiration), `POST /v1/public/submit/{token}`, statut `pending/approved/rejected` **invisible** dans lectures, tuiles, STAC, DCAT, exports, MCP, DuckDB (liste des jumelles dans le ledger) ; honeypot, rate limit dédié (101e requête/h/IP = 429), pièce jointe ≤ 25 Mo contrôlée par type, notifications aux modérateurs, audit du modérateur ; test d'invariant RLS.

### Voie D
- [ ] **ARC-17** : 4 modes (Dot Density, Predominant, bivarié, Compare A to B) + effets, dans `mapSymbology.ts` **et** `toFrontLayer()` (piège n°5) ; légende associée ; identiques éditeur et widget carte (SP-25).
- [ ] **ARC-16** : gabarits A4/A3 portrait/paysage, cartouche, légende, échelle graphique (±1 % mesuré), flèche du nord, logo ; export PDF/PNG/SVG par le worker Playwright (A25), timeout 120 s, annulable ; éditeur de gabarit dans le builder.

### Voie E
- [ ] **ARC-19** : drill automatisé (sauvegarde → `down -v` → restauration → fumée OIDC) en CI hebdomadaire sur stack **jetable** ; échec si buckets/realm manquent ; temps de restauration publié ; ferme REV-164.
- [ ] **ARC-18** : runbook 2 instances `core` derrière Traefik, Postgres primaire/standby, MinIO distribué, RPO/RTO ; `docker compose up --scale core=2` passe la fumée ; bascule < 5 s mesurée ; correctifs REV-354/355/345 ; écart du limiteur en mémoire documenté.

## Tâche d'intégration finale (contrôleur, après fusion des 5 voies)

- [ ] Fusion voie par voie dans `dev` (ordre : E, D, A, B, C) ; conflits `features/*` résolus à la main, tests de la voie rejoués après chaque fusion.
- [ ] Régénérer OpenAPI + types TS (incantation `api-types-drift`) ; ajouter les surfaces à `inventaire-fonctionnalites.jsonl` ; `feature_health_cli.py --write`.
- [ ] Portes : `ruff`, `mypy --strict`, `lint-imports`, `pytest` (base réelle, couverture ≥ seuil), `npm run test`, `npm run build`, **E2E complète verte**, `test_deployability`.
- [ ] **Revue finale de branche** (sous-agent opus) sur le diff agrégé : jumelles de garde croisées entre voies (ex. `pending` d'ARC-10 × WFS d'ARC-11 × historique d'ARC-15).
- [ ] Documentation : ligne dans `### Livré` de `CLAUDE.md`, entrée détaillée dans l'archive, statut d'exécution dans le comparatif, `GAP-nn` fermés, REV mis à jour.
- [ ] Supprimer worktrees et branches `arc1-lane-*` fusionnés ; PR `dev` → `main`.

## Pré-lancement

- [ ] Supprimer les worktrees/branches orphelins existants (`worktree-agent-*`, `/tmp/base`) — **avec confirmation explicite de Tanguy** (certains peuvent contenir des fichiers root-owned).
- [ ] Vérifier `git fetch` + `git rev-list --left-right --count origin/dev...dev` ; vérifier la tête Alembic.
