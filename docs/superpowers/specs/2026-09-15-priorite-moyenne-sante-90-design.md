# Faire passer les 33 fonctionnalités « priorité moyenne » sous 90 au-dessus de 90

**Date** : 2026-09-15
**Demande** : « lance une spec pour passer toutes les fonctionnalités priorité moyenne au dessus de 90% ».
**Référence outil** : bilan de fonctionnalités SP-61 (`docs/revue/bilan-fonctionnalites.{html,md}`,
`core/scripts/feature_health/`), régénéré et vérifié (`--check`) au démarrage de ce chantier — santé
médiane globale 98,6 — sur la base `dev` telle que laissée par le plan
`2026-09-14-priorite-haute-sante-90` (mergé le jour même, `plancher_priorite_haute` déjà relevé à 90).
Ce chantier en est la suite directe : même outil, même méthodologie, cette fois sur `priorite:
"moyenne"`.

## 1. État mesuré au démarrage

221 fonctionnalités `priorite: "moyenne"` au total, dont **33 sous 90** :

| Santé | Domaine | Fonctionnalité | id |
|---|---|---|---|
| 40.0 | CI/Qualité | Analyser statiquement le code (CodeQL) | `ci-qualite-analyser-statiquement-le-code-a-la-recherche-de-vulnerabilites-codeql` |
| 40.0 | CI/Qualité | Bloquer un push/PR contenant un secret (gitleaks) | `ci-qualite-bloquer-un-push-pr-contenant-un-secret-detecte-dans-l-arbre-de-travai` |
| 40.0 | Provisioning | Provisionner une VM sur Proxmox | `provisioning-provisionner-automatiquement-une-vm-et-y-deployer-geostudio-sur-un-` |
| 40.0 | Réseau/Sécurité | Conteneurs applicatifs non-root | `reseau-securite-executer-les-conteneurs-applicatifs-en-utilisateur-non-root` |
| 40.0 | Sauvegarde | Rotation automatique des sauvegardes | `sauvegarde-rotation-automatique-des-sauvegardes-7-quotidiennes-4-hebdomadaires-l` |
| 40.0 | Supervision | Alerte SLO par webhook | `supervision-recevoir-une-alerte-slo-par-webhook-latence-api-tuiles-backlog-de-jo` |
| 67.3 | auth | Déconnexion | `auth-deconnexion` |
| 70.0 | Automatisation | Transformer spatialement via QGIS Processing | `automatisation-transformer-spatialement-des-donnees-via-qgis-processing-buffer-d` |
| 75.5 | Builder — Widgets | Widget Hero | `builder-widgets-widget-hero-bandeau-avec-validation-de-schema-d-url-anti-injecti` |
| 76.9 | Fédération des données | Compaction périodique GeoParquet | `federation-des-donnees-compaction-periodique-des-petits-fichiers-geoparquet-du-l` |
| 77.7 | Catalogue | Mes vues (signets) | `catalogue-mes-vues-signets` |
| 78.8 | Builder — Runtime | Déplacement d'un widget par boutons fléchés | `builder-runtime-deplacement-d-un-widget-par-boutons-fleches-canevas` |
| 84.2 | Builder — Widgets | Widget Fiche jeu de données (datasetCard) | `builder-widgets-widget-fiche-jeu-de-donnees-datasetcard` |
| 85.0 | Builder — Widgets | Widget Galerie | `builder-widgets-widget-galerie-catalogue-public-filtrable` |
| 85.0 | Builder — Widgets | Widget Section riche | `builder-widgets-widget-section-riche-markdown-assaini` |
| 85.2 | Builder — Widgets | Comparaison de période (widget Graphique) | `builder-widgets-comparaison-de-periode-sur-le-widget-graphique-lignes-aires` |
| 86.1 | Automatisation | Marquer les notifications comme lues | `automatisation-marquer-une-ou-toutes-les-notifications-comme-lues` |
| 86.2 | Cartographie | Upload d'icône SVG (bibliothèque tenant) | `cartographie-uploader-une-icone-svg-personnalisee-dans-une-bibliotheque-d-icones` |
| 86.3 | Administration | Copilote IA du builder (loopback MCP) | `administration-copilote-ia-dans-le-builder-d-app-orchestrant-des-outils-mcp-reel` |
| 86.7 | Builder — Requête visuelle | Jointure entre collections | `builder-requete-visuelle-jointure-entre-collections-dans-l-assistant-de-requete-` |
| 86.8 | Automatisation | Préférence de notification | `automatisation-choisir-sa-preference-de-notification-toutes-echecs-seulement-auc` |
| 86.8 | Automatisation | Cloche de notifications persistante | `automatisation-etre-notifie-dans-une-cloche-persistante-du-shell-des-jobs-en-ech` |
| 86.8 | Builder — Widgets | Widget Onglets | `builder-widgets-widget-onglets-conteneur-layout-imbrique-par-onglet` |
| 87.5 | Catalogue/Métadonnées | Catalogue curaté de licences/fréquences/langues | `catalogue-metadonnees-catalogue-curate-de-licences-frequences-langues` |
| 88.0 | Builder — Export d'app | Détection des widgets consommateurs d'écriture | `builder-export-d-app-detection-des-widgets-consommateurs-d-ecriture-pour-l-avert` |
| 88.0 | Builder — Variables | Variables typées d'app | `builder-variables-variables-typees-d-app-string-number-bool-date-record-list` |
| 88.0 | Builder — Widgets | Widget Navigation | `builder-widgets-widget-navigation-menu-de-pages-automatique` |
| 88.3 | Builder — Automatisation (pipelines) | Planification cron partagée | `builder-automatisation-pipelines-planification-cron-partagee-pipelines-rapports-` |
| 88.5 | Automatisation | Rapport PDF planifié d'un Bookmark | `automatisation-recevoir-un-rapport-pdf-periodique-d-un-bookmark-envoye-par-email` |
| 88.6 | Données | Config. champs de pièces jointes | `donnees-configuration-des-champs-de-pieces-jointes-d-une-collection` |
| 88.6 | Données | Édition des métadonnées DCAT | `donnees-edition-des-metadonnees-ouvertes-dcat-d-une-collection` |
| 89.4 | Builder — Cross-filter | Lien de cross-filter entre deux datasets | `builder-cross-filter-lien-de-cross-filter-entre-deux-datasets-attribut-ou-spatia` |
| 89.7 | Builder — Widgets | Widget Sélecteur | `builder-widgets-widget-selecteur-valeurs-distinctes-cross-filter-multi-valeur` |

**Résultat final vérifié en exécutant ce plan (§4.bis)** : 32 des 33 atteignent ≥ 90.
`catalogue-mes-vues-signets` (« Mes vues (signets) ») ne peut pas franchir 90 dans ce périmètre —
documentée comme exception assumée plutôt que forcée artificiellement.

**4 familles causales, établies en lisant le code réel (pas la doc)** :

- **Famille 1 — plafond « garde » (6 items, 86.1 à 87.5)** : notifications (×3 lignes d'inventaire
  pointant sur les 6 mêmes routes), upload d'icône, copilote IA, catalogue de métadonnées. Ces
  routes exigent `get_current_user` et rien d'autre reconnu par `score_guard` — mais elles sont
  **déjà correctement autorisées** par un mécanisme que l'analyseur ne modélise pas (§2.3).
- **Famille 2 — zéro preuve de test détectée (6 items à 40.0 pile)** : CodeQL, gitleaks, Proxmox,
  conteneurs non-root, rotation de sauvegarde, alerte SLO. Cause détaillée en §2.1/§2.2/§4.
- **Famille 3 — écart large sur un seul fichier (2 items)** : `Déconnexion` (67.3,
  `shell/src/auth/useAuth.ts`) et `Transformer spatialement via QGIS` (70.0, moyenne de
  `core/app/pipelines/ops/schemas.py` et `deploy/qgis-worker/server.py` — ce dernier relève de la
  Famille 2 par sa cause, fermé au même endroit, §2.2).
- **Famille 4 — écart étroit à modéré, un seul fichier shell par fonctionnalité (19 items)** :
  chaque ligne cite un unique fichier `shell/src/...` (widgets, panneaux, pages) dont la couverture
  de lignes réelle est sous le seuil. Deux fichiers sont partagés par deux fonctionnalités
  (`EditCollectionPanel.tsx`, `shell/src/builder/widgets/data.tsx`) — une seule tâche pour les deux
  dans chaque cas.

## 2. Volet A — Corriger l'outil de mesure (`core/scripts/feature_health/coverage_facts.py`)

### A.1 — Suivre une chaîne de divisions, pas un seul saut

**Constat vérifié** (exécution directe de `deployability_rules()` sur ce dépôt, pas une lecture de
la doc) :

```
deploy/qgis-worker/Dockerfile -> AUCUNE RÈGLE
```

... alors que `core/tests/test_deployability.py:828` porte bien
`QGIS_DOCKERFILE = REPO / "deploy" / "qgis-worker" / "Dockerfile"`, référencée par deux tests réels
(`test_uid_pinned_consistently_between_core_and_qgis_worker_dockerfiles`,
`..._creates_scratch_before_switching_to_qgis_user`). Le détecteur actuel ne reconnaît qu'un
`ast.BinOp` dont le `.left` est **directement** le `ast.Name` `REPO` — une chaîne
`REPO / "a" / "b" / "c"` a pour `.left` un autre `BinOp`, jamais suivi.

**Règle ajoutée** : résolution récursive côté gauche —

```python
def _resolve_repo_relative(value: ast.expr) -> str | None:
    if isinstance(value, ast.Name) and value.id == "REPO":
        return ""
    if (
        isinstance(value, ast.BinOp)
        and isinstance(value.op, ast.Div)
        and isinstance(value.right, ast.Constant)
    ):
        base = _resolve_repo_relative(value.left)
        if base is None:
            return None
        segment = str(value.right.value)
        return f"{base}/{segment}" if base else segment
    return None
```

Remplace l'actuel test à un seul niveau ; le cas à un seul saut (déjà couvert) reste identique —
généralisation strictement additive, aucune règle existante ne change de verdict.

**Effet mesuré attendu** : `deploy/qgis-worker/Dockerfile` obtient sa vraie règle (2 tests), sans
aucun nouveau test à écrire.

### A.2 — Scanner tous les fichiers `test_*.py`, pas le seul `test_deployability.py` (généralise REV-189)

**Rappel du constat déjà disclosé** (`docs/revue/2026-09-04-backlog.md`, REV-189, trouvé le
2026-09-14, non corrigé) : `deployability_rules()` ne lit que
`core/tests/test_deployability.py`. Deux fichiers de preuve visés ici ont un vrai test **ailleurs**,
qui ne construit d'ailleurs **aucune** constante `REPO / "..."` — un import nu
(`deploy/backup/test_retention.py: from retention import select_files_to_delete`) ou un test
comportemental HTTP sans aucune référence textuelle au fichier qu'il exerce
(`core/tests/test_qgis_worker_sidecar.py`, vérifié : ni le nom du fichier ni son chemin n'y
apparaissent, il appelle un sidecar déjà démarré par HTTP).

**Deux règles ajoutées, cumulatives** :

1. Le parseur de constantes (A.1) tourne sur `core/tests/test_*.py` **et** `deploy/**/test_*.py`
   (glob, pas de liste en dur) au lieu du seul fichier nommé — capture tout futur cas du même
   moule sans intervention manuelle, comme le proposait REV-189.
2. Repli par sous-chaîne littérale (même esprit que `e2e_specs()`, déjà dans ce module) : pour
   toute preuve sous préfixe infra encore sans règle après (1), si son chemin repo-relatif apparaît
   **littéralement** (docstring, commentaire ou chaîne) dans le texte brut d'un des fichiers scannés
   à l'étape (1), c'est une règle valide.

Vérifié en exécutant réellement cette règle sur le dépôt : `deploy/qgis-worker/server.py` est déjà
détecté sans rien changer — `core/tests/test_qgis_worker_server_handler.py` (un test léger,
indépendant du sidecar réel, `_SERVER_PATH = Path(__file__).resolve().parents[2] / "deploy" /
"qgis-worker" / "server.py"`) le cite en toutes lettres dans son docstring de module ; le repli par
sous-chaîne littérale le capture. Seul `deploy/backup/retention.py` en a besoin : son unique test
(`deploy/backup/test_retention.py`) n'a aucun docstring de module. Le Volet C (§4.1) ajoute une seule
ligne de docstring véridique à ce fichier (« Exerce réellement `deploy/backup/retention.py` »).

### A.3 — Nouvelle catégorie déclarée : garde auto-scopée / donnée de référence sans propriétaire

**Constat vérifié route par route** (lecture directe, pas supposée) :

- `core/app/notifications/routes.py` — les 6 routes filtrent systématiquement par
  `recipient_user_id=user.id` / `user_id=user.id` : un utilisateur ne peut jamais lire ni modifier
  que ses propres notifications/préférence. Isolation réelle, portée par le filtre de requête, pas
  par une fonction de garde nommée.
- `core/app/mapicons/routes.py` — les 4 routes filtrent par `tenant_id=user.tenant_id` : n'importe
  quel membre authentifié du tenant peut gérer la bibliothèque d'icônes du tenant — **arbitrage
  produit déjà assumé et documenté** dans `note_sp42` de cette ligne d'inventaire (« ouvert à tout
  utilisateur authentifié du tenant, pas admin-only »).
- `core/app/copilot/routes.py::copilot_turn` — vérification explicite avant tout traitement :
  `if token_subject != user.oidc_sub: raise HTTPException(403, ...)`. C'est une garde réelle, juste
  écrite en ligne plutôt qu'extraite en fonction nommée — même nature que
  `get_readable_collection`/`require_pipeline_access`, déjà ajoutées à `GUARD_NAMES` par le plan
  précédent, mais ici il n'existe **aucun nom de fonction séparé à ajouter** sans en fabriquer un
  fictif.
- `core/app/catalog/routes.py::get_metadata_catalog` — sert une liste fixe identique pour tout
  utilisateur authentifié de tout tenant. Aucune notion de propriétaire ou de portée n'est
  applicable ; il n'y a rien à autoriser au-delà de l'authentification.

**Décision retenue (validée avec Tanguy avant cette spec)** : étendre le modèle de l'outil plutôt
que d'ajouter une garde fictive ou de renoncer au seuil. Nouvelle clé JSONL, au même niveau que
`publiques` :

```json
"garde_auto_scopee": ["GET /v1/notifications", "POST /v1/notifications/{notification_id}/read", ...]
```

- `Feature` (`model.py`) gagne un champ `auto_scoped_guard: tuple[str, ...]`, chargé depuis
  `garde_auto_scopee` exactement comme `public` l'est depuis `publiques`.
- `score_guard` (`rest_surface.py`) gagne une branche, avant le test d'absence de garde :
  `elif surface in feature.auto_scoped_guard: scores.append(100.0); evidence[surface] = "auto-restreint (tenant/utilisateur) ou donnée de référence sans propriétaire — déclaré, vérifié en lecture de code"`.
- Chaque entrée de la liste est ajoutée **une route à la fois**, avec la ligne de code qui la
  justifie citée dans le commit — même discipline que l'ajout de `GUARD_NAMES` par le plan
  précédent (« jamais un nom ajouté sans relecture de son implémentation réelle »).
- Déclaré pour les 4 groupes de routes ci-dessus (6 + 4 + 1 + 1 = 12 routes), au 4e champ des 6
  lignes d'inventaire concernées.

**Non-régression** : cette branche ne peut que faire **monter** un score de garde (aucune route
retirée de `GUARD_NAMES`/`public`), donc aucun risque de repasser une autre fonctionnalité sous son
seuil. Un test négatif (route authentifiée mais réellement ouverte à tout le monde, jamais scopée)
doit rester à 50, pour prouver que la déclaration ne devient pas un totem qu'on colle par confort.

### A.4 — Effet de bord attendu

Comme pour le plan précédent : régénérer le bilan complet et lire le diff en entier avant de
committer, pas seulement les 33 lignes visées — d'autres fonctionnalités hors périmètre peuvent
voir leur « garde » ou leurs « tests » remonter (tout ce qui partage `deploy/qgis-worker/Dockerfile`,
tout futur usage de `deploy/**/test_*.py`).

## 3. Volet B — Preuves d'inventaire

Un sondage sur `catalogue-mes-vues-signets` (proof `shell/src/shell/routes.tsx`) confirme que le
fichier porte une vraie logique (restauration de contexte à l'ouverture d'un signet — `timeRange`,
`extent`, `crossFilter`), pas seulement de l'enregistrement de route : preuve plausible, pas
manifestement périmée. À la différence du plan précédent (7 items, audit exhaustif rentable), les 33
items ne sont **pas** tous pré-audités ici — l'investissement ne serait pas rentable avant
d'écrire les tests. Chaque tâche du plan vérifie sa propre preuve avant d'ajouter des tests
(discipline TDD déjà en vigueur) et corrige toute preuve trouvée périmée en cours de route, comme le
Volet B du plan précédent — sans bloc dédié ici puisqu'aucune n'est confirmée périmée à ce stade.

## 4. Volet C — Combler les vrais trous

### C.1 — Référence textuelle manquante (pair avec A.2)

Ajouter une ligne de docstring véridique à `deploy/backup/test_retention.py` : mention de
`deploy/backup/retention.py`. (`deploy/qgis-worker/server.py` n'a besoin de rien : déjà cité en
toutes lettres par `core/tests/test_qgis_worker_server_handler.py`, capturé par le repli littéral de
A.2 sans aucun changement — vérifié en exécutant.) Aucune logique de test changée.

### C.2 à C.6 — 5 tests structurels neufs (aucun test aujourd'hui, vérifié par grep sur tout le dépôt)

Même registre que les tests `docker-compose`/Traefik déjà présents dans `test_deployability.py` :
parser la configuration réelle et vérifier son câblage, jamais exécuter l'outil externe lui-même.

- **C.2 — CodeQL** (`.github/workflows/codeql.yml`) : le workflow se déclenche sur `push`
  (`main`/`dev`) et `pull_request`, la matrice couvre `python` et `javascript-typescript`,
  `permissions.security-events: write` est présent, les steps `github/codeql-action/init@v4` et
  `.../analyze@v4` sont bien là.
- **C.3 — gitleaks** (`.github/workflows/gitleaks.yml`) : déclenché sur `push`/`pull_request`
  seulement (pas de `schedule`/`workflow_dispatch`, cf. commentaire du fichier sur le risque
  d'historique), sous-commande `dir .` (jamais `git .`), aucun `continue-on-error`.
- **C.4 — Proxmox** (`deploy/proxmox/ansible/playbook.yml`) : parser le YAML, vérifier la présence
  des plays/tasks attendus (création VM, déploiement GeoStudio) — lire le fichier réel avant
  d'écrire l'assertion, jamais deviner sa structure.
- **C.5 — Conteneur `deploy/backup` non-root** (`deploy/backup/Dockerfile`) : même patron que le
  test `qgis-worker` déjà existant (constante `BACKUP_DOCKERFILE`, vérifie `/scratch` ou équivalent
  créé avant le `USER` non-root, `--uid` explicite si le Dockerfile en a un).
- **C.6 — Alerte SLO webhook** (`deploy/observability/grafana/provisioning/alerting/rules.yaml`) :
  parser le YAML, vérifier que les règles latence API/tuiles, backlog de jobs et taux de 5xx
  existent avec un récepteur webhook — lire le fichier réel avant d'écrire l'assertion.

### C.7 — `auth-deconnexion` (67.3)

`shell/src/auth/useAuth.ts` : mesurer la couverture réelle (`npm run test -- --coverage`) avant
d'écrire quoi que ce soit, cibler les branches non couvertes du flux de déconnexion (mock vs OIDC
réel, cf. les deux modes d'auth du dépôt).

### C.8 à C.13 — Cluster de couverture shell (19 fonctionnalités, un seul fichier chacune sauf 2 partagées)

Même méthode partout : mesurer la couverture de lignes réelle du fichier cité, écrire des tests
ciblés sur les branches non couvertes, remesurer — jamais de test qui ne fait qu'exécuter du code
déjà exercé pour gonfler un pourcentage sans intention (règle déjà appliquée par le plan précédent
sur `DataSourcePanel.tsx`).

- **C.8 — Widgets de contenu** : `hero.tsx` (75.5), `datasetCard.tsx` (84.2), `gallery.tsx` (85.0),
  `richSection.tsx` (85.0).
- **C.9 — Widgets d'interaction avancée** : `chart.tsx` (comparaison de période, 85.2),
  `tabs.tsx` (86.8), `navigation.tsx` (88.0).
- **C.10 — Cross-filter** : `CrossFilterLinkEditor.tsx` (lien de cross-filter, 89.4),
  `selectFilter.tsx` (widget Sélecteur, 89.7). (`dateRangeFilter.tsx`/`sliderFilter.tsx`/`data.tsx`
  sont déjà ≥ 90 aujourd'hui — vérifié dans l'inventaire, pas dans le périmètre de ce plan malgré
  leur proximité thématique.)
- **C.11 — Infra builder** : `GridCanvas.tsx` (déplacement par boutons fléchés, 78.8),
  `VariablesPanel.tsx` (variables typées, 88.0), `AppExportPanel.tsx` (détection widgets
  d'écriture, 88.0), `PipelineScheduleEditor.tsx` (planification cron partagée, 88.3 — proof
  shell seul, ne pas confondre avec `core/app/pipelines/jobs.py`, hors périmètre ici),
  `QueryJoinPicker.tsx` (jointure requête visuelle, 86.7).
- **C.12 — Pages shell** : `EditCollectionPanel.tsx` (partagé par 2 lignes d'inventaire : pièces
  jointes et métadonnées DCAT, 88.6 chacune — une seule tâche), `routes.tsx` (signets, 77.7).
  (`ItemActions.tsx`/`ItemDetailPage.tsx` sont déjà ≥ 90 — hors périmètre.)
- **C.13 — Mixte core+shell** : rapport PDF planifié (88.5 — `core/app/reports/jobs.py`,
  `core/app/configs/schemas.py`, `core/app/configs/routes.py`, `shell/src/pages/ReportEditPage.tsx`,
  `shell/src/builder/report/ReportScheduleEditor.tsx` : mesurer chaque fichier séparément, ne
  combler que ceux réellement sous le seuil) ; `core/app/cdc/jobs.py` (compaction GeoParquet, 76.9) ;
  `core/app/pipelines/ops/schemas.py` (transform QGIS, 70.0, à remesurer après A.1/A.2/C.1 — la
  moyenne avec `server.py` peut suffire à dépasser 90 sans toucher `schemas.py` si celui-ci est déjà
  proche de 100 ; ne pas ajouter de test dessus sans l'avoir mesuré). (`core/app/pipelines/jobs.py`,
  cron d'un pipeline unique, est une fonctionnalité distincte déjà ≥ 90 — hors périmètre, à ne pas
  confondre avec `PipelineScheduleEditor.tsx` de C.11.)

**Note pour les tâches C.8 à C.13** : certains scores affichés en §1 datent d'avant les corrections
du Volet A ; toute tâche commence par régénérer le bilan et lire le score réel du moment avant
d'écrire un seul test — ne jamais viser un score déjà obsolète.

### 4.bis — Trouvaille en exécutant : « Mes vues (signets) » ne peut pas atteindre 90 dans ce périmètre

Vérifié en écrivant réellement les tests (pas supposé) : la logique propre aux signets dans
`shell/src/shell/routes.tsx` (`getBookmarkConfig`, reconstruction d'URL avec `timeRange`/`extent`/
`crossFilter`) est déjà **100 % couverte**. Le déficit mesuré (77.7 de santé) vient du fait que
`routes.tsx` est un fichier de **124 lignes partagé par 20+ routes sans rapport** (Sites publics,
SQL Lab, 6 pages Admin, Dataset, Embed, VisualQueryWizard, Pipeline/Report/Alert…) — `proofs`
pointe sur le fichier entier, jamais des numéros de ligne (CLAUDE.md : « les numéros de ligne
dérivent en quelques jours »). Une tâche de ce plan (Task [C.12]) a poussé la couverture de
`useOpenItem` (les 8 branches par type d'item, dont les 4 non-signet) à 100 %, portant le fichier de
61.3 % à 70.96 % — **toujours sous le seuil ~83.3 % nécessaire**. Couvrir le reste exigerait
d'exercer des routes entièrement étrangères aux signets : hors périmètre, disproportionné, et
justement le genre de test qui ne prouverait plus rien sur la fonctionnalité visée.

**Décision retenue** : `catalogue-mes-vues-signets` reste sous 90 à l'issue de ce plan, documentée
comme exception assumée (même doctrine que `REV-176`) plutôt que forcée. Le plancher
`plancher_priorite_moyenne` (Volet D) est calculé en excluant explicitement cette fonctionnalité de
son calcul de minimum — une seule ligne nommée, jamais un mécanisme d'exclusion générique. Un futur
chantier distinct pourrait soit découper `routes.tsx` (un fichier `useOpenItem`/`bookmarkContext`
dédié réduirait mécaniquement la dilution) soit couvrir l'ensemble du fichier à l'occasion d'un
travail plus large sur `routes.tsx` — hors périmètre ici.

## 5. Volet D — Fermer la boucle : généraliser le plancher CI à `priorite: "moyenne"`

`plancher_priorite_haute` est aujourd'hui la seule clé de seuil par priorité
(`feature_health_thresholds.json`, `Thresholds.floor_high_priority`,
`feature_health_cli.py::_check()` filtré en dur sur `row["feature"].priority == "haute"`). Ce volet
généralise le mécanisme à un deuxième palier, sans toucher au premier :

- `Thresholds` gagne `floor_medium_priority: float`, chargé depuis une nouvelle clé
  `plancher_priorite_moyenne` du JSON de seuils.
- `_check()` ajoute une seconde boucle de échecs, filtrée sur `priority == "moyenne"`, contre ce
  nouveau plancher — la boucle existante sur `"haute"` reste identique, verbatim.
- Une fois les 33 fonctionnalités au-dessus de 90, régénérer le bilan et lire la valeur réellement
  atteinte pour `priorite: "moyenne"` (le minimum mesuré, jamais arrondi à la hausse — même doctrine
  que `.coverage-threshold`) ; l'écrire dans `plancher_priorite_moyenne`.
- `plancher_priorite_haute` (90) et `plancher_sante_mediane` (96, mesuré 98.6) ne sont pas touchés.

Sans ce geste, `--check` n'empêche aucune régression future de repasser une fonctionnalité `moyenne`
sous 90 — piège n°12 (un seuil qui dérive silencieusement de la réalité).

## 6. Hors périmètre

- Les 188 fonctionnalités `priorite: "moyenne"` déjà ≥ 90, et toute fonctionnalité `haute`/`basse`.
- `catalogue-mes-vues-signets` au-delà de ce que Task [C.12] apporte (61.3 → 70.96 de tests, encore
  sous le seuil ~83.3 nécessaire) — cf. §4.bis. Un futur découpage de `routes.tsx` ou une couverture
  plus large de ce fichier, hors périmètre ici.
- GAP-72 (CSP `script-src` pour widgets d'extension tiers) — question produit ouverte, sans rapport.
- Toute nouvelle route REST/MCP/shell — ce plan ferme des scores déjà mesurés ; `garde_auto_scopee`
  ne change le comportement d'aucune route, seulement sa description dans l'inventaire.
  `test_feature_inventory.py` ne doit voir aucune ligne d'inventaire nouvelle liée à une surface.
- Étendre la résolution de garde de `rest_surface.py` au-delà de ce que le plan précédent a déjà
  posé (cross-module 1 saut, fabriques `Depends`) — aucun des 33 items ne l'exige, vérifié.
- Généraliser `deployability_rules()` au-delà de `core/tests/test_*.py` et `deploy/**/test_*.py`
  (par ex. `shell/`) — aucun des 33 items ne cite de fichier shell comme preuve infra.

## 7. Points de vérification finale (avant clôture)

- `uv run pytest` (cœur) — 0 échec nouveau, en particulier `test_feature_health_*.py` et les 5
  nouveaux tests structurels (C.2 à C.6).
- `npm run test` (shell) — 0 échec nouveau ; couverture de chaque fichier ciblé (C.7 à C.13) mesurée
  ≥ 90 % de lignes, jamais supposée.
- Bilan régénéré : les 33 lignes visées ≥ 90.0, diff complet relu (pas seulement ces 33 lignes) ;
  `plancher_priorite_moyenne` ajouté et fixé à la valeur mesurée.
- `ruff check` / `ruff format --check` / `lint-imports` / `mypy --strict` (modules concernés).
- Diff `openapi.json` / `core-schema.d.ts` attendu **vide** (aucune route/modèle REST touché par ce
  plan — `garde_auto_scopee` est un champ d'inventaire, pas un schéma d'API).
- `docs/revue/inventaire-fonctionnalites.jsonl` : les 6 lignes touchées par A.3 gagnent
  `garde_auto_scopee`, aucune autre clé structurelle changée.
