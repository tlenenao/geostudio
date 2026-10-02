# Audit pré-release — 2026-09-29

**Périmètre** : tout depuis le tag `v0.1.0` (2026-08-21) — 3152 commits, 1584
fichiers modifiés. Ce serait donc une release majeure, couvrant SP-21 jusqu'à
la clôture de la Vague C.

**Méthode** : 20 agents en fork parallèle (7 audit technique + 13 personas
fonctionnelles), puis vérification croisée directe (pas de récit — commandes
réelles, logs CI réels, grep du code réel) sur les points contradictoires.
Détail des personas et des directives dans la conversation source ; ce
document ne garde que les résultats vérifiés.

## Résumé exécutif

- **4 items bloquants**, tous réels et déjà root-causés — aucun ne demande
  d'investigation supplémentaire, seulement une décision ou un correctif.
- Le cœur technique (qualité statique, sécurité, déployabilité, doc/inventaire)
  est globalement sain : la plupart des inquiétudes de départ se sont révélées
  être des faux positifs d'environnement local, pas des défauts de code.
- La revue fonctionnelle (13 personas) n'a trouvé aucun défaut bloquant côté
  produit — c'est une liste d'améliorations/nouvelles fonctionnalités pour le
  backlog, pas un obstacle à la release.

## Vérifications croisées — contradictions tranchées

| Sujet | Ce que disaient les agents | Vérification directe | Verdict |
|---|---|---|---|
| Worktrees orphelins | F4/F13/T7 : présents. T6 : absents. | `git worktree list` ne montre rien (T6 avait raison sur cette commande précise), mais le filesystem contient 6 répertoires orphelins non trackés : `.claude/worktrees/agent-{a43ef82eded5231ca,a64f2443aa73d0b5e,a805d8d613a116895}` (2026-09-06) + `.worktrees/{sp1c-partage-publication,sp1d3-geonode-removal,sp2a-mcp-oauth}`, dont `sp1c-partage-publication` **root-owned**. | **Réel** — violation de la règle CLAUDE.md "supprimés dès leur fusion dans dev". |
| CI rouge sur `dev` HEAD | T2 : rouge sur `feature-health`. T5 : `--check` vert en local (santé 99.1). | Les deux ont raison : `--check` passe, mais `--check-fresh` (commande différente, plus stricte) échoue sur `03a984fe` **et** sur le commit précédent `29c75a7e` — y compris sur le commit `[ci-bot]` censé justement régénérer le bilan. Log CI : `PÉRIMÉ : docs/revue/bilan-fonctionnalites.md/.html`. | **Bug réel** dans le mécanisme d'auto-régénération, pas une dérive doc. |
| `CORE_TEST_DATABASE_URL` en CI | T1 : inquiétude, non vérifiable en local. | `ci.yml:40` — bien câblée (`postgresql+psycopg://gis:gis@localhost:5432/gis_test`). | Faux positif d'environnement local, écarté. |
| Incohérence `wfs` moissonnage | F5 : `wfs` dans `COPY_TYPES` mais absent du `<select>`. | `CreateHarvestSourcePanel.tsx:57` — `wfs` est bien présent dans les deux. | **Fausse alerte**, écartée. |

## Checklist technique priorisée

### Bloquant

1. **`main` sans protection de branche** (`404` sur l'API GitHub) — n'importe
   quel commit rouge peut être mergé. Décision à prendre : activer
   `required_status_checks`, ou assumer consciemment ce mode pour l'instant.
2. **`feature_health_cli.py --check-fresh` rouge sur `dev` HEAD**, y compris
   sur le commit qui vient de régénérer le bilan — bug dans le calcul de
   fraîcheur (hash/horodatage probablement calculé avant le commit final).
   Root cause à trouver dans `core/scripts/feature_health_cli.py` avant de
   pouvoir dire "dev est vert".
3. **`desktop-etl WebDriver E2E` (job `e2e-windows`) rouge sur `main`** depuis
   3 exécutions consécutives (25/26/29-09-2026), feature absente de
   `CLAUDE.md § Livré`. Décision produit à prendre : spike non bloquant à
   documenter comme tel (et rendre non-required), ou vraie régression à
   corriger avant release.
4. **Suite `pytest` core invérifiable en local** (`/tmp/pytest-of-lenen`
   root-owned → 450 erreurs artefact, pas un défaut de code). La CI GitHub
   est verte sur ce point (vérifié par run réel) — non bloquant si on fait
   confiance à la CI, mais à rejouer proprement en local avant de signer des
   yeux.

### Important

5. 8 des 15 migrations Alembic ajoutées depuis v0.1.0 n'ont aucun test
   round-trip identifié : `0029` (map_icons), `0030` (roles), `0031`
   (notifications), `0034` (attachments_cascade_delete), `0037`
   (items_bbox), `0038` (export_appexport_byte_size), `0039` (erasure),
   `0041` (wkt_geometry_mode).
6. `core/tests/.../test_collections_spatial_index.py` (migration `0028`)
   porte le nom d'un test de migration mais n'appelle en réalité ni
   `command.upgrade` ni `command.downgrade` — faux sentiment de couverture.
7. Aucun runbook de release écrit (bump version `core/pyproject.toml` +
   `shell/package.json`, déplacement `CHANGELOG.md [Unreleased]→[vX.Y.Z]`,
   tag, push, vérification post-publication). La seule release existante
   (v0.1.0) reste tribale.
8. `REV-197` (impact sécurité, portée limitée) et `REV-254` (fiabilité
   perçue, perte de cœur invisible sur une partie des requêtes) à relire
   avant de clore la release.
9. Suite `stac-conformance` verte en CI mais masque ~25 erreurs de
   conformité réelles sur `item-search` (`continue-on-error`) — ne pas
   revendiquer "conforme STAC" sans nuance dans la communication de release.
10. 6 worktrees/branches orphelins à nettoyer (cf. tableau ci-dessus),
    dont un root-owned — suppression à confirmer explicitement avant de la
    faire.
11. 15 commits `dev` en avance sur `origin/main` — vérifier qu'une PR
    `dev→main` propre existe (aucune trouvée listée au moment de l'audit).

### Différable

12. `CLAUDE.md` § arm64 dit "8/9 images, qgis-worker exclu" — réalité
    actuelle : 9/9 images multi-arch depuis le retrait complet de QGIS.
13. `CLAUDE.md` § Suivis dit `secret_scanning`/`dependabot_security_updates`
    désactivés — en réalité activés (vérifié via l'API GitHub).
14. Warning ESLint `react-hooks/exhaustive-deps` sur
    `shell/src/ui/kit/Radio.tsx:83`.
15. Pas de runbook de rotation de secrets symétrique à celui de sauvegarde ;
    pas de `scripts/update.sh` pour une mise à jour guidée (parallèle à
    `install.sh`).

### Vérifié sain, aucune action requise

ruff / `mypy --strict` (6 modules) / `lint-imports` / ESLint / Prettier /
`pre-commit` (6/6) ; couverture shell 91.5% (seuil 89.8%) ; CSP `enforce` en
prod ; rate limiting différencié ; garde d'egress SSRF (connecteurs HTTP) ;
9/9 images multi-arch câblées par valeur dans le compose (pas de piège n°2) ;
`install.sh` resynchronise bien le realm Keycloak ; `restore.sh` couvre les 7
buckets MinIO ; OpenAPI/TS sans dérive ; bilan de fonctionnalités à 99.1 de
santé ; backlog/GAP réellement synchronisés avec le code (14 GAP ouverts, ~28
REV ouvertes, aucun n'est une régression active).

## Notes produit (13 personas — non bloquantes)

Classées **[A]**mélioration / **[N]**ouvelle fonctionnalité. Ne re-débattent
aucun des 40 arbitrages figés de la feuille de route.

**Découverte publique / SEO**
- **[N]** Fiche dataset publique invisible du SEO et sans aperçu social,
  contrairement aux sites (`/public/datasets/:id` hors `sitemap.xml`, hors
  règle Traefik `seo-bots-rewrite`, pas de `useDocumentMeta`).
- **[A]** Licence/auteur/date non affichés sur la fiche dataset alors que les
  champs SP-41 existent déjà en base.

**Fédération de catalogues**
- **[A]** Aucune indication avant moissonnage qu'un type de source
  (WMS/WMTS/CSW/Records) ne donnera jamais que des liens, jamais de données
  copiables.
- **[A]** `GET /harvest/layers`/`feature-layers` + tableau admin non paginés
  — casse sur les gros catalogues, l'argument de vente de la fédération.
- **[N]** Promouvoir une source `reference` existante en `copy` sans tout
  recréer.

**Analytique / décision**
- **[A]** Pas de mode "lecture dashboard" qui masque le chrome d'édition
  pour un décideur qui consulte juste.
- **[A]** Pont "Enregistrer comme widget" depuis SQL Lab vers un dashboard
  existant — présence à confirmer, non vérifiée avec certitude.

**Temps réel / offline (Q10/Q11, questions déjà ouvertes)**
- **[A]** Plancher cron d'alerte à 5 min quel que soit le réglage utilisateur
  — inadapté à un scénario de crise.
- **[N]** Canal SSE/WebSocket léger, scope MVP, pour notifications urgentes.
- **[A]** Brouillon local de formulaire en cours de saisie, restauré si le
  cœur devient injoignable — évite une perte sèche sans trancher Q11.

**Gestion de données**
- **[A]** Pas de "remplacer les données d'une collection existante" — chaque
  import recrée une collection, perdant symbologie/partage/RLS déjà
  configurés.

**Cartographie experte**
- **[A]** Pas de data-defined override CEL sur le `paint` lui-même, pas
  d'échelle de visibilité min/max zoom par couche, pas d'évitement de
  collision d'étiquettes.
- **[N]** Motifs/hachures pour polygones (cartographie réglementaire), export
  du croquis de mesure en feature réelle.

**Onboarding**
- **[A]** ⌘K ne cherche que les menus, jamais les items du catalogue de
  l'utilisateur.
- **[N]** Checklist "premiers pas" persistée pour un compte à 0 item.
- **[A]** Quota de stockage invisible pour un utilisateur non-admin avant
  qu'il échoue dessus.

**Conformité**
- **[N]** Aucune route d'export des données personnelles d'un utilisateur
  (Art. 15/20 RGPD) — le produit sait effacer mais pas restituer.
- **[A]** `anonymize_user` laisse vivants secrets connecteur/planifications
  créés par le compte anonymisé, sans revue.

**Administration**
- **[A]** Moissonnage : pas d'explication à l'écran de pourquoi "copie
  locale" est grisée pour certains protocoles.
- **[N]** Préférences de notification par catégorie, vue "budget de
  conformité" agrégée.

**SDK / intégration tierce**
- **[A]** Pas de mode local de test de widget sans passer par un admin de
  prod.
- **[A]** Guide public manquant pour consommer OGC API Features en écriture
  (symétrique au guide widget).

**Exploitation**
- **[A]** Restauration s'arrête sur une étape manuelle "vérifier la
  reconnexion OIDC" jamais scriptée (`REV-164`).
- **[N]** Alerte système native sur échec silencieux (sauvegarde, quota,
  certificat).

## Proposition de découpage en blocs d'implémentation

30 tâches, groupées en 11 blocs. Chaque bloc est un candidat à son propre
spec + plan (`superpowers:writing-plans` refuse un plan unique bite-sized
TDD sur des sous-systèmes indépendants — voir note en fin de document).
Priorité décroissante.

### Bloc 1 — Hygiène release immédiate (bloquant, à traiter avant toute proposition de release)
1. Root-causer et corriger `feature_health_cli.py --check-fresh` (diverge de `--check`).
2. Décider et appliquer la protection de branche sur `main`.
3. Diagnostiquer `desktop-etl WebDriver E2E` : classer spike non-bloquant (retirer des required checks) ou corriger la régression.
4. Nettoyer les 6 worktrees orphelins (confirmation explicite pour le répertoire root-owned).
5. Nettoyer `/tmp/pytest-of-lenen`, rejouer `pytest` core en local, confirmer parité avec la CI.

### Bloc 2 — Filet de tests migrations
6. Ajouter un test round-trip upgrade/downgrade pour `0029`, `0030`, `0031` (base non vide).
7. Idem pour `0034`, `0037`, `0038`, `0039`, `0041`.
8. Corriger `test_collections_spatial_index.py` pour qu'il exécute réellement upgrade/downgrade (`0028`).

### Bloc 3 — Process de release documenté
9. Écrire le runbook de release (versioning, CHANGELOG, tag, vérification post-publication).
10. Écrire le runbook de rotation de secrets + `scripts/update.sh` guidé.

### Bloc 4 — Nettoyage doc/dette rapide
11. Corriger `CLAUDE.md` (arm64 9/9, `secret_scanning` activé).
12. Relire et statuer sur `REV-197` et `REV-254`.

### Bloc 5 — Fédération : pagination & clarté
13. Paginer `GET /harvest/layers` + `/feature-layers` (API, patron `GET /dcat/catalog`).
14. Paginer `HarvestSourcesAdminPage` (shell).
15. Badge "catalogue seulement" vs "données copiées" dans `CreateHarvestSourcePanel`.

### Bloc 6 — Découvrabilité dataset public (SEO)
16. Étendre `sitemap.xml` + règle Traefik `seo-bots-rewrite` aux datasets publics.
17. `useDocumentMeta` sur `DatasetPage`.
18. Afficher licence/auteur/date sur la fiche dataset + endpoint `social-preview` équivalent.

### Bloc 7 — RGPD : export utilisateur
19. `GET /compliance/users/{id}/export` (backend, symétrique à la route d'effacement).
20. UI d'export + liste des objets encore actifs sous une identité anonymisée (secrets, planifications).

### Bloc 8 — Onboarding
21. Recherche full-text du catalogue utilisateur dans ⌘K.
22. Checklist "premiers pas" persistée sur compte à 0 item.
23. Affichage du quota de stockage pour un utilisateur non-admin.
24. Explication à l'écran de "pourquoi copie grisée" dans le moissonnage.

### Bloc 9 — Gestion de données : remplacement de collection
25. Endpoint "remplacer les données d'une collection existante".
26. UI de remplacement + garde-fou sur dérive de schéma entre deux livraisons.

### Bloc 10 — Analytique UX
27. Mode "lecture dashboard" (masque le chrome d'édition sur `AppRenderer`).
28. Pont SQL Lab → widget de dashboard (vérifier d'abord l'absence réelle avant de coder).

### Bloc 11 — Cartographie experte
29. Échelle de visibilité min/max zoom par couche.
30. Motifs/hachures pour polygones.

**Note méthode** : conformément au skill `superpowers:writing-plans` (scope
check), ces 30 tâches couvrent des sous-systèmes indépendants et ne peuvent
pas être un seul plan TDD bite-sized. Chaque bloc mérite son propre
spec/plan daté au moment de son exécution. Le Bloc 1 est le seul dont le
séquencement est contraint (à traiter avant toute release) ; les blocs 5-11
sont des candidats de backlog indépendants, à prioriser librement.
