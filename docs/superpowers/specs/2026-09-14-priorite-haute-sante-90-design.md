# Faire passer les 7 fonctionnalités « priorité haute » sous 90 au-dessus de 90

**Date** : 2026-09-14
**Demande** : « propose moi une spec/plan pour faire passer toutes les fonctionnalités priorité haute au-dessus de 90% ».
**Référence outil** : bilan de fonctionnalités SP-61 (`docs/revue/bilan-fonctionnalites.{html,md}`,
`core/scripts/feature_health/`), généré aujourd'hui même (commit `1911e9e6`) — santé médiane
mesurée 98.2, mais 7 fonctionnalités `priorite: "haute"` restent sous 90.

## 1. État mesuré au démarrage

| Santé | Domaine | Fonctionnalité | id |
|---|---|---|---|
| 40.0 | Déploiement | Créer le premier compte administrateur pendant l'installation | `deploiement-creer-le-premier-compte-administrateur-pendant-l-installation` |
| 40.0 | Déploiement | Installeur guidé interactif | `deploiement-installeur-guide-interactif-docker-jq-profils-env-tailscale-sauvegar` |
| 40.0 | Sauvegarde | Restaurer une sauvegarde | `sauvegarde-restaurer-une-sauvegarde` |
| 66.6 | Fédération des données | Fraîcheur quasi temps réel (CDC → GeoParquet) | `federation-des-donnees-fraicheur-quasi-temps-reel-des-donnees-pour-l-analytique-` |
| 87.1 | Features (OGC API) | Tuiles vectorielles MVT servies par le cœur (avec RLS) | `features-ogc-api-tuiles-vectorielles-mvt-servies-par-le-cur-avec-rls` |
| 89.7 | Builder — Données | Panneau des sources de données (features/statistics/static) | `builder-donnees-panneau-des-sources-de-donnees-features-statistics-static` |
| 89.8 | Automatisation | Lancer l'exécution d'un pipeline à la demande | `automatisation-lancer-l-execution-d-un-pipeline-a-la-demande` |

La santé est `Σ(sous-score × poids) / Σ(poids applicables)` sur 4 sous-scores (tests 0.30,
atteignabilité 0.25, garde 0.25, dette 0.20 — `core/scripts/feature_health_thresholds.json`).
Un sous-score `None` (surface non applicable) sort du calcul et les poids se renormalisent —
c'est pourquoi les 3 lignes à 40.0 (aucune surface REST/MCP) ne pondèrent que sur
tests (0.30) + dette (0.20) : `(0×0.30 + 100×0.20) / 0.50 = 40.0`.

**Diagnostic par cause, établi en lisant le code réel (pas la doc)** :

- **Preuve d'inventaire périmée** (2 cas) : le chemin de fichier cité dans `preuve` décrit un
  état du dépôt antérieur à une SP qui a réellement livré/déplacé la fonctionnalité.
- **Angle mort de l'analyseur de garde** (2 cas) : la garde existe réellement dans le code,
  vérifiée par lecture directe, mais l'AST de `rest_surface.py` ne la voit pas — soit parce
  qu'elle vit dans un module importé (couche de service SP-43), soit parce qu'elle est
  invoquée via un paramètre `Depends(...)` renommé localement.
- **Vrai trou produit** (3 cas) : `scripts/install.sh` n'a aucun test automatisé ; le panneau
  Statique du builder a une note d'inventaire obsolète mais sa couverture de lignes réelle
  reste sous le seuil.

## 2. Volet A — Corriger l'outil de mesure (`core/scripts/feature_health/rest_surface.py`)

### A.1 — Résolution de garde cross-module (un saut de plus)

**Constat vérifié** (`core/app/pipelines/routes.py` / `core/app/pipelines/service.py`) :
6 des 9 routes REST de « Lancer un pipeline à la demande » appellent une fonction de service
importée (`run_pipeline_service`, `create_webhook_token_service`, `revoke_webhook_token_service`,
`list_webhook_tokens_route` → `require_pipeline_access` directement) qui, elle, appelle
`require_pipeline_access(...)` → `can(session, user_id=..., action=..., item=facts)`. C'est le
patron introduit par SP-43 précisément pour partager la garde entre REST et MCP
(« 3 couches de service partagées REST↔MCP pour la première fois »). L'analyseur actuel
(`_called_names` + `local_functions.get(name)`) ne résout que les fonctions définies dans le
**même fichier** que la route — un service importé n'est jamais suivi.

**Règle ajoutée** : quand un nom appelé (ou un nom passé à `Depends(...)`) résout, via la table
d'imports du module de la route, vers une fonction définie dans un **autre** module de
`core/app`, ce module est parsé (résultat mis en cache par chemin de fichier — le dépôt est
petit, pas de souci de performance) et on regarde si le corps de cette fonction appelle
lui-même un nom de `GUARD_NAMES` (résolution non récursive au-delà de ce seul saut
supplémentaire — toujours « grossier, robuste », dans l'esprit de `debt.py`).

Limite assumée et documentée dans le code (comme les limites déjà écrites dans ce module) :
un garde à 3 sauts ou plus (service → sous-service → `can()`) resterait invisible. Aucun cas
réel de ce type identifié dans les 7 fonctionnalités visées ; si un futur audit en trouve un,
même traitement (généraliser encore d'un cran, jamais un cas particulier nommé).

### A.2 — Fabriques de garde via `Depends`

**Constat vérifié** (`core/app/features/tiles.py::get_collection_tile`) :

```python
rls=Depends(get_rls_scope),
...
with rls(session, col.tenant_id, masked=masked):
```

`get_rls_scope()` (`core/app/features/routes.py:113`) est `def get_rls_scope(): from app.features.rls
import rls_scope; return rls_scope` — une fabrique qui **retourne** le garde sans l'appeler.
Le nom effectivement appelé dans le corps de route est `rls` (le paramètre local), jamais
`rls_scope` littéralement — invisible pour `GUARD_NAMES`.

**Règle ajoutée** : si une fonction passée à `Depends(...)` a pour corps un simple
`return <nom>` (directement, ou via une import locale suivie d'un `return`) où `<nom>` ∈
`GUARD_NAMES` (résolu avec la règle A.1 si besoin), alors tout appel du paramètre qui reçoit
cette dépendance, dans le corps de la route, compte comme un appel de ce garde.

Cette même route a par ailleurs un vrai contrôle d'accès direct
(`get_readable_collection(session, user, collection_id, guest=guest)`, appelé en corps de
fonction) — `get_readable_collection` n'est simplement pas dans `GUARD_NAMES` aujourd'hui alors
que c'est le chokepoint documenté par CLAUDE.md pour les collections (GAP-19/GAP-22/GAP-50/
GAP-60/SP-35). Il est ajouté à `GUARD_NAMES` dans ce même volet, avec sa justification écrite en
commentaire (vérifié : il retourne 404 si l'appelant ne peut pas lire la collection).

### A.3 — Non-régression

Deux règles génériques, jamais de nom de fonction ajouté sans relecture de son implémentation
réelle dans cette même session/tâche. Elles ne peuvent que **faire monter** un score de garde
(ajout de gardes reconnus), jamais le faire baisser — donc aucun risque de repasser une autre
fonctionnalité de l'inventaire sous un seuil. Un test négatif explicite (route sans aucun appel
de garde, même après résolution cross-module) doit rester à 0/50 pour prouver que la
généralisation ne sur-détecte pas.

Effet de bord attendu et souhaité : d'autres fonctionnalités de l'inventaire, hors des 7 visées
ici, peuvent voir leur sous-score « garde » remonter (n'importe quelle route qui passe par
`get_readable_collection` ou par une couche `service.py` SP-43). Le bilan complet est régénéré
et relu en diff avant de committer — pas seulement les 7 lignes ciblées.

## 3. Volet B — Corriger des preuves d'inventaire périmées

### B.1 — `sauvegarde-restaurer-une-sauvegarde`

`preuve: ["deploy/backup/entrypoint.sh"]` décrit un état antérieur à SP-59 (« aucun script de
restauration n'existe »—faux depuis SP-59). Le vrai fichier est `deploy/backup/restore.sh`,
déjà couvert par `core/tests/test_deployability.py::test_restore_recreates_every_bucket_backup_mirrors`
(constante `RESTORE_SH` déjà présente ligne 72) et par la suite dédiée
`core/tests/test_restore_script.py`. Correction : `preuve` → `["deploy/backup/restore.sh"]`,
description mise à jour (elle aussi périmée — décrit l'absence du script).

Calcul attendu : `deployability_rules()` trouve une règle réelle pour ce chemin → tests = 100.0.
Santé attendue : `(100×0.30 + 100×0.20) / 0.50 = 100.0`.

### B.2 — `federation-des-donnees-fraicheur-quasi-temps-reel...`

`preuve: ["core/app/cdc/main.py"]` ne cite que le point d'entrée (câblage, peu de logique
propre). La description de la fonctionnalité elle-même parle du worker complet
(« consomme le flux logique et écrit des fichiers GeoParquet partitionnés »／« déduplication
par `_lsn` décroissant ») — un comportement porté par `consumer.py`, `storage.py`,
`parquet_writer.py`, `buffer.py`, chacun couvert par un fichier de test dédié
(`test_cdc_consumer.py`, `test_cdc_consumer_postgis.py`, `test_cdc_storage.py`,
`test_cdc_parquet_writer.py`, `test_cdc_buffer.py`, `test_cdc_compaction.py`,
`test_cdc_backfill.py`, `test_cdc_shutdown.py`).

Correction : élargir `preuve` à ces fichiers réels. **Mesure requise avant de conclure** : une
tâche du plan régénère `core/coverage.xml` et vérifie la moyenne de couverture obtenue sur
l'ensemble élargi. Si elle atteint 90, c'est une correction de preuve pure (aucun code nouveau).
Si elle reste en dessous, la tâche ajoute les tests manquants sur le(s) fichier(s) le(s) moins
couverts plutôt que de retirer un fichier gênant de la preuve — jamais réduire le périmètre pour
gonfler la moyenne.

## 4. Volet C — Combler les vrais trous produit

### C.1 — `scripts/install.sh` (2 fonctionnalités : premier compte admin + installeur guidé)

**Constat** : le script (406 lignes, `set -euo pipefail`, exécution séquentielle en bas de
fichier, pas de `main()` gardé) porte déjà 3 échappatoires non-interactives manifestement
posées pour un usage de test jamais écrit :

```bash
confirm() { if [ "${INSTALL_YES:-0}" = "1" ]; then ...   # ligne 13
prompt_profiles() { if [ -n "${INSTALL_PROFILES+x}" ]; then ...   # ligne 128
                      if [ -n "${INSTALL_SEED_DEMO+x}" ]; then ...  # ligne 157
prompt_admin() { if [ -n "${INSTALL_ADMIN_EMAIL:-}" ]; then ...   # ligne 283
```

Le commentaire de `confirm()` dit littéralement : « INSTALL_YES=1 permet un mode non-interactif
pour les Steps de vérification de ce plan » — un plan antérieur avait prévu ce test, jamais
écrit. Trois prompts restent bloquants sans échappatoire : `prompt_public_host` (host public),
`activate_funnel` (Tailscale), `prompt_backup_target` (cible de sauvegarde).

**Travail** :
1. Ajouter 3 échappatoires additives, même patron `INSTALL_*` (par ex.
   `INSTALL_PUBLIC_HOST`, `INSTALL_FUNNEL` — `0`/`1`, `INSTALL_BACKUP_TARGET` — vide = aucune
   cible). Additives et inertes par défaut : un opérateur humain qui lance `install.sh` sans
   rien positionner garde le comportement interactif actuel à l'identique.
2. `core/tests/test_install_script.py`, même patron que `test_restore_script.py` (SP-59) :
   pas de framework de test shell dans ce dépôt, donc double de test — un exécutable `docker`
   factice sur un PATH de test qui reconnaît `compose up -d ...`, `compose exec -T keycloak
   /opt/keycloak/bin/kcadm.sh config credentials ...`, `... get users -r geostudio -q email=...`,
   `... create users -r geostudio ...`, journalise ses arguments et renvoie des réponses JSON
   canned plutôt que de toucher un vrai Keycloak/Docker.
3. Scénarios réels à couvrir (jamais juste « le fichier existe » ou `bash -n`) :
   - création d'un compte admin neuf → `CORE_ADMIN_SUBS` écrit dans `.env` avec l'id renvoyé
     par le double ;
   - relance sur un compte déjà existant → chemin idempotent (`existing_id`), pas de second
     `create users` ;
   - Keycloak qui ne répond jamais → sortie en erreur (`exit 1`) après la boucle d'attente,
     pas de faux succès ;
   - sélection de profils via `INSTALL_PROFILES`, `.env` généré (`ensure_env_file` invoque déjà
     `bootstrap-env.sh`, dont la génération de `CORE_SECRETS_MASTER_KEY` est déjà testée
     ailleurs — pas dupliqué ici) ;
   - `launch_stack` appelé avec les bons flags de profils.
4. Falsification systématique : chaque test doit casser si on retire son assertion clé (ex.
   commenter temporairement `set_env_var CORE_ADMIN_SUBS "$ADMIN_SUB"`, confirmer l'échec,
   restaurer) avant de le considérer fiable.

### C.2 — `builder-donnees-panneau-des-sources-de-donnees-features-statistics-static`

La note `note_sp42` de l'inventaire est périmée (« aucun champ n'apparaît pour saisir les
enregistrements [statiques] » — faux depuis SP-52, `StaticRecordRow` existe et
`DataSourcePanel.test.tsx` a déjà un test dédié, ligne 303). Mise à jour de la note. Le score
82.8 vient de la couverture de lignes réelle de `DataSourcePanel.tsx` : une tâche ajoute des cas
de test ciblés sur les branches non couvertes (mesurées via `npm run test -- --coverage` avant/
après, jamais devinées).

## 5. Volet D — Fermer la boucle : relever le plancher CI

Une fois les 7 fonctionnalités au-dessus de 90, régénérer le bilan
(`PYTHONPATH=. uv run python scripts/feature_health_cli.py --repo .. --write`) et lire la
nouvelle valeur de `plancher_priorite_haute` réellement atteinte. Relever
`core/scripts/feature_health_thresholds.json::plancher_priorite_haute` (actuellement 40) à
cette valeur mesurée — jamais arrondie à la hausse, même doctrine que `.coverage-threshold` /
`.bundle-size-threshold`. Sans ce geste, `--check` continue d'accepter un plancher à 40 et rien
n'empêche une régression future de repasser sous 90 sans faire échouer la CI — piège n°12
(un document/seuil qui dérive silencieusement de la réalité).

`plancher_sante_mediane` (96, mesuré 98.2) n'est pas touché par ce plan — hors périmètre, déjà
largement respecté.

## 6. Hors périmètre

- Les planchers `moyenne`/`basse` amorcés à 40 (CodeQL, secret-scanning, provisioning Proxmox,
  conteneurs non-root, SLO webhook, rotation de sauvegarde automatique) — non demandés,
  priorité non « haute ».
- GAP-72 (CSP `script-src` pour widgets d'extension tiers) — question produit ouverte,
  sans rapport avec ce chantier.
- Toute nouvelle route REST/MCP/shell — ce plan ferme des scores déjà mesurés, n'ouvre aucune
  surface nouvelle (donc `test_feature_inventory.py` ne doit voir aucune ligne d'inventaire
  nouvelle liée à une surface — seulement des `preuve`/notes corrigées).
- Extension de la résolution de garde au-delà d'un saut cross-module supplémentaire (A.1) —
  si un cas à 3 sauts apparaît plus tard, traitement séparé.

## 7. Points de vérification finale (avant clôture)

- `uv run pytest` (cœur) — 0 échec nouveau, en particulier `test_feature_health_*.py` et les
  nouveaux `test_install_script.py`.
- `npm run test` (shell) — 0 échec nouveau, couverture de `DataSourcePanel.tsx` mesurée ≥ 90 %
  de lignes.
- Bilan régénéré : les 7 lignes visées ≥ 90.0, diff complet relu (pas seulement ces 7 lignes),
  `plancher_priorite_haute` relevé à la valeur mesurée.
- `ruff check` / `ruff format --check` / `lint-imports` / `mypy --strict` (modules concernés) /
  `shellcheck scripts/install.sh deploy/backup/restore.sh` si disponible.
- Diff `openapi.json` / `core-schema.d.ts` attendu **vide** (aucune route/modèle REST touché par
  ce plan).
