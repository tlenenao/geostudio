# Vagues 2 et 3 ARC (ARC-20 à ARC-30) — Plan d'exécution parallèle

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans. Steps use checkbox (`- [ ]`) syntax.

**Goal :** livrer les 11 chantiers des Vagues 2 (ARC-22 à ARC-28, 54 j-h) et 3 (ARC-20, 21, 29, 30, 61 j-h) du rattrapage ArcGIS Enterprise, soit 115 j-h, en 5 voies parallèles.

**Source de vérité :** `docs/revue/2026-10-11-comparatif-fme-arcgis-enterprise.md` §6.1.2 (livrable, critères d'acceptation, dépendances de chaque ligne ARC). Ce plan les ordonne et les répartit. Protocole, contraintes globales et pièges : identiques à `2026-10-12-arc-vague1-bloquants-collectivite.md`.

**Base :** `dev` après la Vague 1 (migrations jusqu'à 0059). Les correctifs de revue finale de la Vague 1 (`features/routes.py`, `public_submit/`, `quality/`, `history/`) sont fusionnés pendant l'exécution : les voies se rebasent sur `dev` avant leur rapport.

## Répartition en voies

| Voie | Chantiers (ordre) | Effort | Zone exclusive |
|---|---|---|---|
| **F — Style et rendu OWS** | ARC-28 (export SLD/MapLibre) → ARC-20 (WMS 1.3.0/WMTS) | 31 j | `core/app/ows/` (extension), nouveau module de style, `shell/src/map/` (import de style) |
| **G — Builder et cartes** | ARC-26 (gabarits, Swipe, galerie de fonds, fiche d'entité) → ARC-30 (atlas) → ARC-22 (binning) | 20 j | `shell/src/builder/`, `core/app/features/tiles.py` (ARC-22 seulement), `core/app/export/` (atlas) |
| **H — Données** | ARC-23 (import FileGDB/DXF/GML/TAB) → ARC-21 (relations) | 26 j | `core/app/ingestion/`, `core/app/pipelines/ops` (GDAL), nouveau `core/app/relations/` ; ARC-21 touche `features/` **après** fusion des correctifs de revue |
| **I — Identité et formulaires** | ARC-24 (groupes ← claims) → ARC-27 (XLSForm, mobile, GPS/photo) | 16 j | `core/app/sharing/`, `core/app/auth/` (lecture de claims), `core/app/mcp/form_app.py`, `shell/src/builder/widgets/form.tsx` |
| **J — Plateforme et analyse** | ARC-29 (Helm) → ARC-25 (widget Analyse) | 22 j | `deploy/helm/`, `.github/workflows/` ; `shell/src/builder/widgets/` (analyse), `core/app/analytics/` |

Chemin critique : voie F (31 j). Total 115 j-h.

**Dépendances respectées :** ARC-28 avant ARC-20 (rendu sur symbologie déclarative) ; ARC-26 avant ARC-30 (atlas) ; ARC-23 avant ARC-21 (collision `features/` avec les correctifs de revue) ; ARC-10/13 (livrés) avant ARC-27 ; ARC-18 (livré) avant ARC-29.

**ADR rédigés avant lancement :** 0020 (renderer WMS/WMTS interne), 0021 (relations), 0022 (groupes ← claims, A2 précisé).

**Migrations (tête = 0059) :** ARC-21 → 0060, ARC-24 → 0061 ; une voie qui en découvre une autre demande le numéro suivant (0062+) au contrôleur. Les autres chantiers n'en prévoient pas.

**Fichiers réservés à l'intégration :** `core/openapi.json`, `shell/src/api/generated/*`, `docs/revue/inventaire-fonctionnalites.jsonl`, bilan, backlog, analyse-gaps, `CLAUDE.md`, archive.

## Points d'attention par voie

- **F** : ARC-28 — export SLD 1.1 validé par XSD sur 6 symbologies, import d'un style MapLibre ; ARC-20 — rendu **sous `rls_scope`/`can()`/masquage/limites géographiques** (ADR 0020), aucun sidecar GPL, p95 < 300 ms mesuré, activation par collection + flag d'instance câblé dans le compose par valeur.
- **G** : ARC-26 — 8 gabarits = données déclaratives passant le schéma `AppConfig`, a11y axe vert, `create_item` MCP accepte `template` ; ARC-30 — atlas 50 pages, annulable, CEL ; ARC-22 — plafond 5000 entités/tuile non contourné, comptes exacts vs `count(*)`.
- **H** : ARC-23 — VRT refusé (REV-333), mêmes bornes que SP-56, DWG exclu ; ARC-21 — ADR 0021, RLS et masquage des deux côtés, `restrict` par défaut, journal ARC-15.
- **I** : ARC-24 — additif, origine `manual`/`claim`, ADR 0022 ; ARC-27 — XLSForm 30 questions sans perte (`relevant` → `visibleWhen` CEL), soumission publique via ARC-10, hors ligne exclu.
- **J** : ARC-29 — `helm install` sur kind passe la fumée, images amd64+arm64, équivalent de `test_deployability` pour le chart ; ARC-25 — 8 à 12 outils, RLS/masquage par le même chemin que `/aggregate`.

## Tâche d'intégration finale

- [ ] Fusion voie par voie ; migrations re-chaînées ; OpenAPI/types ; inventaire ; bilan.
- [ ] Portes : ruff, mypy, lint-imports, pytest complet (base réelle), vitest, build, E2E complète.
- [ ] Revue finale de branche croisée entre voies (masquage/RLS/limites géographiques sur WMS, relations, atlas, import).
- [ ] Documentation (`CLAUDE.md` § Livré, archive, REV/GAP) ; nettoyage worktrees ; PR `dev` → `main`.
