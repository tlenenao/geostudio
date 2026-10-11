# Vague 0 « quick wins » ARC-01 à ARC-09 — Plan d'exécution parallèle

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans. Steps use checkbox (`- [ ]`) syntax.

**Goal :** livrer d'ici le 2026-11-11 les 9 chantiers de la Vague 0 de rattrapage ArcGIS Enterprise (26 j-h) en 5 voies parallèles, sans collision de fichiers ni de migrations.

**Source de vérité des chantiers :** `docs/revue/2026-10-11-comparatif-fme-arcgis-enterprise.md` §6.1.2, lignes ARC-01 à ARC-09 (livrable, critères d'acceptation, dépendances). Ce plan ne les recopie pas : il les **ordonne, les répartit et fixe le protocole**. Chaque critère d'acceptation du comparatif devient un test écrit en premier (TDD).

**Architecture :** 5 voies indépendantes, une branche de travail éphémère par voie (`arc0-lane-<x>`, worktree), fusionnées une à une dans `dev` par le contrôleur. Une **tâche d'intégration** finale (seule à toucher aux fichiers partagés) régénère OpenAPI/types TS, l'inventaire et le bilan.

**Tech Stack :** FastAPI/SQLAlchemy/Alembic/pytest (`core/`), React/Vitest/Playwright (`shell/`), MapLibre, procrastinate, DuckDB.

## Global Constraints

- Arbitrages A1–A40 non rediscutés (`docs/vision/2026-07-04-feuille-de-route-geostudio.md` §8) ; toute écriture passe par `can()` ; `tenant_id` + `audit_log` sur toute table/écriture ; frontières `lint-imports` (40 entrées) vertes.
- Branche de promotion : `dev` seulement ; commits conventionnels, petits, un sujet ; trailer `Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>` ; docs et messages utilisateur en français, code en anglais.
- TDD systématique ; chaque fonctionnalité visible a sa spec E2E Playwright ; toute nouvelle surface (route REST, outil MCP, route shell) est ajoutée à `docs/revue/inventaire-fonctionnalites.jsonl` (porte CI).
- Pièges du dépôt applicables : n°1 (OpenAPI/types), n°5 (`toFrontLayer()`), n°8 (migration sur base non vide, deux sens), n°9 (ledgers nommés `.superpowers/sdd/arc0-<voie>-*`), n°14 (jumelles de garde listées avant clôture), n°3 (vérifier chaque ligne:ligne du plan dans le code avant de s'y fier).

## Répartition en voies

| Voie | Chantiers (ordre) | Effort | Zone de fichiers (exclusive) |
|---|---|---|---|
| **A — OGC/features** | ARC-08 (REV-352, 353, 359) → ARC-02 → ARC-04 | 9 j | `core/app/features/*`, `core/app/tileset3d/routes.py`, `core/app/terrain3d/routes.py`, `core/app/mapicons/routes.py` |
| **B — Items/rôles** | ARC-07 (inclut REV-335) → ARC-05 | 5 j | `core/app/items/*`, `core/app/roles/*`, `shell/src/catalog/*`, migrations 0052/0054 |
| **C — Carte shell** | ARC-01 → ARC-09a (`timeField`, fonds de carte, légende) ; ARC-09b après fusion d'ARC-02 | 6 j | `shell/src/map/*`, `shell/src/api/itemClient.ts` (`toFrontLayer`), `core/app/configs/schemas.py` |
| **D — Clés d'API** | ARC-06 | 3 j | nouveau `core/app/apikeys/`, `core/app/auth/` (point d'entrée), migration 0053 |
| **E — Géocodage lot** | ARC-03 | 3 j | `core/app/geocoding/*`, `core/app/mcp/tools/geocode.py`, op pipeline `transform.geocode` |

Chemin critique : voie A (9 j). Total 26 j-h ; 5 subagents en parallèle ≈ 9 j calendaires de travail effectif + intégration 2 j.

**Pourquoi ces regroupements (collisions réelles) :** `features/routes.py` et `repository.py` sont touchés par ARC-02, ARC-04 et ARC-08 → même voie, séquentiels. `items/routes.py:165` est touché par ARC-07 et par REV-335 (ARC-08) → **REV-335 est traité par la voie B**, pas par A. ARC-01 et ARC-09 modifient tous deux `MapLayer` et `toFrontLayer()` → même voie. ARC-09b dépend du paramètre `datetime` d'ARC-02 (voie A).

**Migrations (numéros réservés, tête actuelle = 0051) :** ARC-05 → `0052_item_content_status`, ARC-06 → `0053_api_keys`, ARC-07 → `0054_role_items_publish`. ARC-02/03/04/01/09/08 : aucune migration (ETag d'ARC-04 = hash de ligne, pas de colonne). Si une voie découvre qu'il lui faut une migration non listée, elle s'arrête et le signale au contrôleur (collision de `down_revision`).

**Fichiers interdits aux voies (réservés à l'intégration) :** `core/openapi.json`, `shell/src/api/generated/core-schema.d.ts`, `docs/revue/inventaire-fonctionnalites.jsonl`, `docs/revue/bilan-fonctionnalites.*`, `docs/revue/2026-09-04-backlog.md`, `docs/revue/2026-09-04-analyse-gaps.md`, `CLAUDE.md`, `core/app/main.py` (enregistrement des routeurs : la voie D et E donnent le diff exact dans leur rapport, l'intégration l'applique).

## Protocole commun à chaque voie (le contrôleur le reprend dans chaque prompt)

- [ ] **Étape 0 — Vérifier le plan contre le code** (piège n°3) : relire chaque `fichier:ligne` de la ligne ARC correspondante du comparatif et de la section « Tâches » ci-dessous ; corriger sans redemander, consigner l'écart dans `.superpowers/sdd/arc0-<voie>-ledger.md`.
- [ ] **Étape 1 — Environnement isolé** : worktree `arc0-lane-<x>` depuis `dev` ; base de test dédiée `CORE_TEST_DATABASE_URL=…/postgis_test_<x>` (créer la base ; sessions concurrentes sur la même base = collisions, piège SP-49) ; migrations de la voie appliquées à cette base (le conteneur n'est pas tracké par Alembic).
- [ ] **Étape 2 — Par chantier : test d'abord** (un test par critère d'acceptation du comparatif, vu échouer), implémentation minimale, test vert, `ruff check` + `ruff format --check` + `mypy --strict` (modules concernés) + `lint-imports`, commit conventionnel. Vérifier `git show --stat` et le trailer de chaque commit (les sous-agents dérivent : fichiers non liés, attribution).
- [ ] **Étape 3 — Revue par tâche** par un second subagent frais (spec : critères d'acceptation du comparatif), puis corrections.
- [ ] **Étape 4 — Revue finale de voie** (piège n°4) : défauts de croisement entre tâches, jumelles de garde (piège n°14) listées explicitement dans le rapport.
- [ ] **Étape 5 — Rapport** : commits, tests ajoutés, suites lancées (sorties réelles), écarts au plan, `Surfaces nouvelles` (routes/outils MCP/routes shell à inventorier), diff `main.py` si routeur ajouté. Aucune fusion par la voie elle-même.

## Tâches par voie

### Voie A — OGC/features

**Task A1 : ARC-08 (partie features/3D), 3 j.** Fermer REV-352 (collection `GEOMETRY` mixte, Polygon→MultiPolygon), REV-353 (`bbox` hors bornes/NaN → 400 RFC 7807 au lieu de 500), REV-359 (401 anonyme sur tuiles 3D/terrain/icônes d'un item public : `tileset3d/routes.py:238-245`, `terrain3d/routes.py:157-164`, `mapicons/routes.py:188,197`).
**Files :** Modify `core/app/features/routes.py` (~l.169 bbox, validation géométrie), `core/app/features/validation.py`, les 3 routes 3D/icônes ; Test : réutiliser et faire passer au vert `core/tests/audit/test_audit_lot*.py` correspondants (retirer le `xfail` dans le même commit) + nouveaux tests de non-régression dans `core/tests/`.
**Interfaces — Produces :** `parse_bbox(raw: str) -> tuple[float, float, float, float]` levant `ProblemError(400)` ; contrat inchangé pour les appelants.
Critères : `bbox=999,0,0,0` = 400 ; `bbox=nan,…` = 400 ; Polygon accepté sur couche MultiPolygon (conversion) ; tuile d'un item public lue anonymement = 200.

**Task A2 : ARC-02, 3 j.** `sortby=±champ` (allowlist de colonnes via `sql_ident.quote_ident`, colonne inconnue = 400), `datetime=` (instant/intervalle ouvert sur colonne temporelle déclarée), `crs`/`bbox-crs` (EPSG 4326, 3857, 2154 minimum, `ST_Transform`), `conformsTo` mis à jour (`features/routes.py:118-120`), pagination par curseur `__after` désactivée (offset) quand `sortby` ≠ PK. **Files :** Modify `core/app/features/routes.py`, `core/app/features/repository.py:231`, `core/app/features/schemas.py` ; Test `core/tests/test_features_sortby_datetime_crs.py`.
**Produces (consommé par ARC-09b et ARC-11) :** query param `datetime: str | None` sur `GET /v1/collections/{id}/items`.
Critères (du comparatif) : `sortby=-nom` ordonne ; `datetime=2025-01-01/..` filtre ; `crs=EPSG:2154` = Lambert-93 vérifié contre `ST_Transform` ; pagination correcte sous tri personnalisé.

**Task A3 : ARC-04, 3 j.** ETag par entité (hash de la ligne sérialisée), `If-Match` optionnel sur `PUT`/`DELETE /items/{fid}` (`features/routes.py:784`), 412 RFC 7807, `ETag` renvoyé sur `GET`/`POST`/`PUT` ; formulaire shell : conflit → message + rechargement (`shell/src/forms/*`, fichier à localiser à l'étape 0 ; seul fichier shell de la voie A). Sans en-tête : comportement inchangé. Test sur base non vide (piège n°8). Rapprocher de REV-343 (`rollback_config`) seulement si trivial, sinon laisser ouvert.

### Voie B — Items/rôles

**Task B1 : ARC-07 + REV-335, 3 j.** Privilège `items.publish` dans `core/app/roles/privileges.py` (20 → 21), migration `0054_role_items_publish.py` (ajout aux rôles prédéfinis Administrateur/Créateur uniquement, via donnée, **sans modifier la définition immuable** : suivre le mécanisme de migration de rôles de SP-31/0050), garde sur `PATCH /items/{id}` quand la visibilité passe à public (`items/routes.py:165`) et sur l'outil MCP équivalent. Critères : rôle sur mesure sans `items.publish` ne peut pas passer un item en public (REST + MCP, **jumelles listées**) ; Lecteur inchangé ; REV-335 (éditeur → public) fermé, son test `audit/` passe au vert. Test migration base non vide, up et down.

**Task B2 : ARC-05, 3 j.** Champs `content_status` (`none|authoritative|deprecated`) et `categories[]` sur `Item`, migration `0052_item_content_status.py`, filtre `GET /items?status=`, facette dans `GET /items/facets`, boost « Référence » dans le tri catalogue, déprécié exclu du catalogue public par défaut, badge shell (`shell/src/catalog/*`), écriture réservée à `catalog.manage` ; ajouter les champs à `toFrontItem`/lecture shell (piège n°5 : chemin de lecture). Dépend de B1 (même fichiers `items/*`).

### Voie C — Carte shell

**Task C1 : ARC-01, 3 j.** Option `cluster: {radius, maxZoom, label}` sur `MapLayer` pour couches `feature`/GeoJSON (MapLibre `cluster: true`), calques cercle + compte, clic = zoom ; champ ajouté à `MapLayer` **et** `toFrontLayer()` (`shell/src/api/itemClient.ts`) **et** au schéma core `core/app/configs/schemas.py` (piège REV-356 : champ rejeté en 422 si le schéma core ne le connaît pas, le filet de parité TS ne voit pas les champs en trop) ; incompatibilité heatmap signalée dans l'éditeur. Tests : Vitest (10 000 points : 1 cluster à z4, points individuels à z14), E2E round-trip rechargement. Noter dans le rapport la nuance : les tuiles denses sont déjà agrégées côté serveur (`features/tiles.py:138-148,293`).

**Task C2 : ARC-09a, 2 j.** `MapLayer.timeField` / `attachmentField` acceptés par `core/app/configs/schemas.py:113,122` (REV-356 fermé ; son test `audit/` passe), collection de fonds de carte par tenant (admin : `core/app/` module à choisir à l'étape 0, par défaut dans `collections` ou un petit module `basemaps` — vérifier lint-imports), CSP `img-src` via l'allowlist dynamique SP-48, légende exportée. Critère : PUT carte avec `timeField` = 200 et relecture identique ; un admin ajoute un fond WMTS/XYZ visible par tous.

**Task C3 : ARC-09b, 1 j — après fusion d'ARC-02.** Lecteur temps de l'éditeur de carte pilote le filtre `datetime` ; persisté dans la config. Si ARC-02 n'est pas fusionné à temps : livrer C2 seul et reporter C3 en vague 1 (le consigner).

### Voie D — Clés d'API

**Task D1 : ARC-06, 3 j.** **ADR court d'abord** (`docs/adr/00xx-cles-api-service.md`, numéro libre à vérifier) : une clé = secret machine, pas un mot de passe (A « jamais de mots de passe dans le cœur » respecté). Module `core/app/apikeys/` (+ entrée dans le contrat de couches `lint-imports`), migration `0053_api_keys.py` (hash SHA-256 stocké, préfixe visible, `expires_at ≤ 1 an`, `revoked_at`, `tenant_id`, `created_by`), vérification dans la **même** porte `can()` (la clé hérite des privilèges du créateur, jamais plus : test d'invariant), usage tracé dans `audit_log`, rate limit existant (REV-336), UI Paramètres (`shell/src/settings/*`). Critères : clé expirée = 401 ; révoquée = 401 ; ne dépasse jamais les privilèges du créateur ; secret affiché une seule fois ; comparaison à temps constant. Livre le diff `main.py` dans son rapport.

### Voie E — Géocodage lot

**Task E1 : ARC-03, 3 j.** `POST /v1/geocode/batch` (≤ 500 adresses, job procrastinate **avec balayage de reprise** — piège n°14 ; écriture du statut dans un `try/except` séparé de la notification, patron SP-39), `GET /v1/geocode/reverse`, garde d'egress existante (`geocoding/egress.py`), outil MCP `geocode_batch` audité (`mcp/tools/geocode.py:23`), op pipeline `transform.geocode` si le registre `OPERATIONS` (`OperationContract`) l'accepte sans refonte — sinon reporter l'op en vague 1 et le consigner. Critères : lot de 500 adresses < 60 s avec rapport `non_trouvé` (BAN simulée par un faux transport, jamais le réseau réel) ; reverse renvoie une adresse ; plafond BAN respecté. Livre le diff `main.py`.

## Tâche I — Intégration (contrôleur, après fusion des 5 voies)

- [ ] Fusionner chaque voie dans `dev` une à une (`git fetch` + `git rev-list --left-right --count origin/dev...dev` avant ; résoudre les conflits à la main, jamais `-X theirs`) ; supprimer worktrees et branches `arc0-lane-*` dès fusion (règle de dépôt).
- [ ] Appliquer les diffs `main.py` des voies D et E ; vérifier l'ordre des migrations `0052 → 0053 → 0054` (`alembic heads` = une seule tête) ; test des migrations sur base non vide, upgrade puis downgrade.
- [ ] Régénérer OpenAPI + types TS (incantation de CLAUDE.md § Commandes) — diff non vide attendu (nouvelles routes).
- [ ] Ajouter les surfaces nouvelles à `docs/revue/inventaire-fonctionnalites.jsonl`, puis `cd core && PYTHONPATH=. uv run python scripts/feature_health_cli.py --repo .. --write`.
- [ ] Fermer dans le backlog REV-335, 352, 353, 356, 359 (et partiellement 343 si traité) avec le commit ; mettre à jour `scripts/revue/count-backlog-etat.sh` ; mettre à jour les `GAP-nn` concernés dans `analyse-gaps.md`.
- [ ] Mettre à jour le comparatif : ARC-01…09 `livré`, corriger la ligne « clustering absent côté serveur » de §3.1 en MOINS BIEN→ISO selon ARC-01, recalculer ISO+MIEUX.
- [ ] Une ligne dans `CLAUDE.md` § Livré + entrée détaillée dans `docs/superpowers/2026-08-27-historique-execution-continu.md` ; `python3 scripts/check_claude_md_size.py CLAUDE.md .claude-md-size-threshold`.
- [ ] **Portes complètes (sorties réelles à citer)** : `uv run pytest` (avec `CORE_TEST_DATABASE_URL` réel, sinon ~185 tests skippent silencieusement), ruff, mypy strict, `lint-imports`, couverture ≥ seuil ; shell : `npm run test`, `npm run lint`, `npm run format:check`, `npm run build` (jamais exécuté par les revues par tâche : piège vécu), `npm run e2e` **complet** (piège n°6) ; `uvx pre-commit run --all-files`.
- [ ] Revue finale de branche (subagent opus, hors des auteurs) sur l'ensemble du diff `dev` vs `origin/dev`, puis PR `origin/dev` → `main` (jamais de merge local sur `main`).

## Risques et garde-fous

| Risque | Mitigation |
|---|---|
| Deux voies modifient `items/*` ou `features/*` | Zones exclusives du tableau ; REV-335 attribué à la voie B seulement |
| Collision de migrations | Numéros 0052/0053/0054 réservés ; une seule tête vérifiée à l'intégration |
| Base `postgis-test` partagée → faux échecs | Une base par voie ; rejouer en isolation avant de s'imputer une régression |
| Mémoire WSL2 (~12 Go) sous 5 subagents + suites | Lancer pytest/vitest **au premier plan**, par fichier ; au plus 3 suites lourdes simultanées ; E2E complet seulement à l'intégration |
| Planning ARC-09b dépend d'ARC-02 | C3 scindé et reportable sans bloquer la vague |
| Plan désynchronisé du code (piège n°3) | Étape 0 de chaque voie |
| Worktrees orphelins existants (`.claude/worktrees/agent-*`) | Les lister (`git worktree list`) avant de créer les nouveaux ; supprimer seulement avec confirmation de Tanguy |

## Calendrier indicatif

| Jours | Voie A | B | C | D | E |
|---|---|---|---|---|---|
| J1–J3 | A1 ARC-08 | B1 ARC-07 | C1 ARC-01 | D1 ARC-06 | E1 ARC-03 |
| J4–J6 | A2 ARC-02 | B2 ARC-05 | C2 ARC-09a | (revue/ADR) | (revue) |
| J7–J9 | A3 ARC-04 | — | C3 ARC-09b (après A2) | — | — |
| J10–J11 | Tâche I d'intégration + revue finale + PR | | | | |

Marge : 2026-11-11 laisse ~4 semaines pour ~11 jours ouvrés d'exécution parallèle ; la marge absorbe revues finales et corrections.
