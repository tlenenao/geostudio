# 98 — Trous de couverture de l'audit 2026-10-16

Critique de complétude de `99-synthese.md` et de l'arborescence `docs/revue/audit-2026-10-16/` (HEAD `c0251b66`, branche `dev`). Méthode : inventaire de `core/app/*`, `shell/src/*`, `deploy/*`, `scripts/*`, `.github/workflows/*`, `desktop-etl/`, puis recherche, dans les 35 dimensions, 6 parcours, 8 fichiers concurrents et 3 baselines, des chemins cités. Lecture seule : aucun fichier source touché. Chiffres de couverture = nombre de fichiers `.md` de l'audit qui citent le chemin (recherche par sous-chaîne : un « 0 » veut dire jamais cité par chemin, pas forcément jamais lu).

## 1. Ce qui est solide (pour calibrer)

- Les constats Critical que j'ai recoupés dans le code tiennent : `compiler.py:168-192` buffer en mètres via EPSG:3857 (AUD-005) ; `rules.yaml` : 5 occurrences de `noDataState: OK` aux lignes 29/56/85/112/141 (AUD-018). Pas de dérive récit/code sur ces deux-là.
- Les 35 dimensions couvrent les domaines fonctionnels et transverses ; les 8 comparatifs concurrents sont présents.

## 2. Angles morts, priorisés

### P1 — Affirmations fausses ou incomplètes dans la synthèse, vérifiables tout de suite

**T1. La neutralisation d'injection de formule est présentée comme acquise ; deux chemins d'écriture CSV la contournent.**
- `parcours/auditeur-securite.md:88` classe « Export CSV : neutralisation des formules » parmi les points sains, en citant `cell_safety.py:7,16` et `analytics/export.py:170-171`. Aucune dimension (d15, d16, d30) ne cherche les écritures CSV hors de ces deux fichiers.
- Preuve : `sanitize_cell` n'est importé que par `analytics/export.py:23` et `pipelines/runtime.py:44` (plus parsers/xlsform en lecture). Or `core/app/pipelines/ops/cloudfiles.py:859` écrit un CSV par `frame.to_csv(index=False)` sans aucune neutralisation (writer de fichiers cloud, contenu issu de données utilisateur). Et `core/app/pipelines/runtime.py:1435` (`writer.file`, `COPY ... FORMAT GDAL, DRIVER p.driver`) écrit avec le pilote choisi par l'utilisateur sans passer par `sanitize_cell` (le pilote CSV de GDAL est exposé, cf. `ops/schemas.py:543`).
- À faire : lister toutes les jumelles d'écriture tabulaire (piège n°14), puis neutraliser au point unique ou documenter la limite.

**T2. Le « parcours non rejoué » des baselines n'est pas répercuté dans les scores.**
- `00-baseline-stack-reelle.md` §4 liste 9 stages non rejoués (`journeys --lane all --verify`, `restore-oidc`, `plans`, `measure`, `rebuild-images`, `smoke`, `admin-tools`, `e2e-mock`) et `99-synthese.md` ne le dit qu'en dernière ligne (« les parcours n'ont pas rejoué la restauration destructive ni le build complet »). Résultat : la synthèse ne signale pas que REV-266/267/292/318/319 (rejeu réel) restent ouverts, ni que les 8 REV de la lettre « journeys » n'ont aucune preuve fraîche.
- `parcours/analyste-sig.md:89` : « Non rejoué : le cœur et le shell déployés n'ont pas le code (F3) ». Donc plusieurs parcours se sont exécutés contre une stack **en retard sur HEAD** : les constats d'UI de ces parcours décrivent l'image déployée, pas `c0251b66`. La synthèse n'en tient pas compte (ex. AUD-050, popups, vient de ce parcours).
- À faire : ajouter à la synthèse un tableau « preuve par exécution » (rejoué sur HEAD / rejoué sur image ancienne / lu dans le code seulement) par AUD.

**T3. Constats « non vérifié » repris tels quels dans le backlog.**
- 183 occurrences de « non rejoué / non vérifié / non lu » dans `dimensions/` ; 20 dimensions au moins en contiennent (d01, d02, d03, d06, d07, d08, d13, d15, d17, d18, d19, d22, d24, d25, d27, d29, d30, d31, d32, d33). `99-synthese.md:3` l'admet (« repris tels quels, sévérité Minor ou marqués »), mais le backlog de 150 AUD n'a pas de colonne « vérifié ». Un lot exécutable (§4) peut donc s'appuyer sur un constat jamais reproduit.
- À faire : colonne « preuve » (rejeu / code / hypothèse) et vérification des Important non reproduits avant de les lotir.

### P2 — Zones du dépôt jamais ouvertes ou à peine ouvertes

| Zone | Citée par | Constat | Priorité |
|---|---|---|---|
| `desktop-etl/` (application Tauri + sidecar) | 1 fichier (d25, chaîne d'approvisionnement) | Aucune dimension sécurité/fiabilité. Éléments à examiner : `src-tauri/capabilities/default.json` (`core:default` seul, pourtant `tauri_plugin_shell` est chargé, `src/main.rs:32`) ; `tauri.conf.json` sans `app.security.csp` (clé absente, lignes 9-17) ; sidecar HTTP `127.0.0.1:{port}` + jeton `GEOSTUDIO_SIDECAR_TOKEN` (`main.rs:36-64`, `core/scripts/pipeline_sidecar.py:45`) : le jeton est optionnel (`or None`), donc le serveur peut tourner sans authentification ; `reader.file`/`writer.file` derrière `CORE_PIPELINE_FILE_IO_ENABLED`. Trois workflows CI desktop jamais audités. | Haute |
| `shell/src/desktop/` (`DesktopItemClient.ts`, 1013 lignes) | d31 (couverture 14 %) | Second `ItemClient` : conformité à l'interface, droits (`can()` absent côté local), pas lu hors couverture de tests. | Moyenne |
| `core/app/relations/` (522 lignes de service) | 2 fichiers (d15/d16 par mention de nom) | ARC-21 : relations parent/enfant, lecture en `rls()` : un seul contrôle `DATA_MANAGE` à la déclaration (`routes.py:42,52`) ; la lecture d'une relation traversante (`service.py:211,275,291`, jointure sur la collection de liaison) n'a jamais été confrontée au masquage de colonne GAP-22 ni aux limites géographiques de la collection **liée**. | Haute |
| `core/app/instance/routes.py` | 5 (par nom) | `GET /instance` (`routes.py:46`) sans authentification expose 12 drapeaux de configuration (`adminToolsEnabled`, `routingEnabled`, …) : fuite d'empreinte de configuration jamais discutée. À qualifier (probablement voulu pour le shell non connecté). | Basse |
| `core/app/notifications/`, `outbox/`, `webhooks/`, `history/`, `mapicons/`, `styles/`, `tenants/`, `catalog/`, `dataexport/`, `filter_values.py`, `bbox.py`, `ogc_crs.py`, `errors.py`, `schemas_routes.py`, `db.py`, `job_timeouts.py` | 0 à 2 | Modules petits ou transverses cités uniquement incidemment. `outbox` (ADR 0027, webhooks sortants, retry) : un seul fichier d'audit ; ses jumelles `defer()`/balayage (piège n°14) ne sont pas dans la liste AUD-025. | Moyenne (outbox, history), basse (le reste) |
| `core/app/ows/`, `routing/`, `raster/`, `terrain3d/`, `quality/`, `lineage/`, `xlsform/`, `public_submit/`, `geocoding/` | 2 à 4 | Couverts par une dimension fonctionnelle mais pas par les dimensions transverses (autorisation d15/d16, performance d18) : par exemple `public_submit` (soumission anonyme) n'apparaît pas dans la matrice d'autorisation. | Moyenne |
| `deploy/drill/`, `deploy/valhalla/`, `deploy/ha/` (compose de test), `deploy/oci/`, `deploy/ansible/`, `deploy/minio/`, `deploy/postgis/`, `deploy/titiler/`, `deploy/appexport-standalone/` | 0 à 1 | `restore-drill.yml` (cron hebdomadaire lundi 03:17) : résultat jamais consulté, alors qu'AUD-016/027 portent sur Helm. Provisioning OCI/Proxmox : lu seulement via les parcours admin. | Moyenne |
| `.github/workflows/` : `desktop-etl-*`, `restore-drill.yml`, `helm-chart.yml`, `publish-edge.yml`, `codeql.yml` | 0 à 2 | Seul `ci.yml`/`release.yml` est analysé (d25, d31). Aucune vérification que `restore-drill` réussit réellement en CI (historique `gh run`). | Moyenne |
| `core/scripts/` : `audit_findings.py`, `audit_prompts.py`, `bootstrap_feature_inventory.py`, `pin_compose_digests.py`, `seed_demo.py`, `spike_*` (5 spikes) | 0 | Scripts livrés dans l'image ou le dépôt, jamais passés en revue (dette d32 n'en parle pas). | Basse |
| `sql/init.sql` (tables `communes`/`points_interet` d'exemple, extensions `postgis_raster`, `postgis_topology`) | 5 (par mot générique) | Jamais lu comme fichier : vérifier s'il est monté en prod (piège n°2 : monté ou inerte ?) et s'il crée des tables hors RLS/`tenant_id`. | Moyenne |
| `examples/external-widget/`, `docs/guides/` (1 seul guide), `docs/ops/` (1 fichier) | 3 / 3 / 0 | d24 audite le SDK ; l'exemple est-il exécutable contre le contrat actuel (versionné) ? Non rejoué. | Basse |
| `shell/src/audit/audit-lot5.test.tsx`, `AppErrorBoundary`, `config.ts`, `main.tsx` | 0 | Sans enjeu majeur ; `AppErrorBoundary.tsx:12-25` affiche un texte français en dur (hors i18n, d27 ne le cite pas). | Basse |
| `core/alembic/versions` (74 fichiers) | 3 | Seules 6 migrations récentes ont été relues pour leur `downgrade` (d19:85). Migrations 0001-0069 et 0073-0081 : jamais testées sur base non vide (piège n°8). | Moyenne |

### P3 — Dimensions absentes ou trop minces

1. **Sécurité de la chaîne de build des images** (digests, signature cosign : ADR 0014 « cible non implémentée ») : d25 la mentionne ; pas de vérification du Dockerfile de chaque image (9 images) pour utilisateur non-root, `HEALTHCHECK`, secrets de build.
2. **Confidentialité des journaux** : aucune dimension ne cherche les secrets/jetons/DSN dans `logger.*` (OIDC, jetons d'export en URL : AUD-024 mentionne l'URL mais pas leur présence dans les journaux traefik/uvicorn).
3. **Intégrité de la restauration** : AUD sur sauvegarde (d20) mais la restauration scriptée n'a pas été rejouée (T2) ; la convergence « sauvegarde bornée + restauration » n'a donc aucune preuve fraîche.
4. **Coûts et capacité** : aucun chiffrage mémoire/CPU par service (limites compose, `deploy.resources`) hors d18 sur import/lac.
5. **Mobile/tablette réel** : `touch-map.spec.ts` simulé par CDP ; d26/d28 n'ont pas mesuré sur appareil (limite déjà acceptée dans CLAUDE.md, à réécrire dans la synthèse).
6. **Cycle de vie des données utilisateur** (RGPD d30) : l'export de données personnelles (Art. 15/20) n'est pas listé dans la matrice d'autorisation ; vérifier qu'il existe ou le noter comme absent.
7. **Concurrence applicative** (deux auteurs, `If-Match`) : couvert pour 4 éditeurs (REV-271), pas pour les kinds non listés (`Bookmark`, `ReportSchedule`, `Site`) ; d06 ne les énumère pas.
8. **Régression entre l'audit et HEAD** : l'audit est figé à `c0251b66` ; `docs/revue/audit-2026-10-16/` est non commité, aucun mécanisme n'attache chaque AUD à un commit/ligne pour détecter une dérive (piège n°12 : les récits vieillissent vite dans ce dépôt).

### P4 — Faiblesses de méthode

- **Pas de vérification croisée à deux lecteurs** : chaque dimension a un seul auteur ; seuls les Critical ont été recoupés (par moi ici, 2 sur 22). Proposition : échantillon de 10 AUD tirés au hasard, re-vérifiés par un second agent (code seul).
- **Scores de parité** (§2 de la synthèse) : barème 1/0,5/0 sans pondération par usage (D1 « horizontal ») ; la moyenne « 61 % » n'a pas de sens décisionnel.
- **Dédoublonnage** : 150 AUD, dimensions notées « d04,d15 » ; pas de lien vers l'identifiant d'origine de chaque dimension, donc impossible de retrouver la preuve sans rechercher à la main.
- **Pas d'AUD positif négatif** : les « avantages réels » (§2) ne sont pas vérifiés un par un dans le code (« sécurité unifiée », « masquage sur toutes les surfaces ») ; T1 montre qu'une telle affirmation peut cacher une jumelle oubliée.

## 3. Proposition de prochaine passe (ordre)

1. **Passe A — jumelles et vérification (1 jour, lecture seule)** : T1 (toutes les écritures tabulaires), vérifier 10 AUD Important aléatoires, ajouter la colonne « preuve » à la synthèse (T2/T3).
2. **Passe B — surfaces jamais ouvertes (2 jours)** : `desktop-etl/` + `shell/src/desktop/` (sidecar sans jeton obligatoire, CSP Tauri, capacités), `core/app/relations/` (masquage et limites géographiques à travers une relation), `outbox`/`webhooks`/`history`, `public_submit`.
3. **Passe C — exploitation (1 jour)** : consulter l'historique `gh run` de `restore-drill.yml`, `helm-chart.yml`, `desktop-etl-*` ; lire `sql/init.sql` (monté ou non), Dockerfiles des 9 images, `deploy/drill` et `deploy/oci`.
4. **Passe D — rejeu réel, session dédiée, machine seule** : `journeys --lane all --verify`, `plans`/`measure`, `restore-oidc` (exige `down -v`, donc décision de Tanguy sur un jeu de données jetable), `rebuild-images`, `smoke`. À faire APRÈS reconstruction des images sur HEAD (sinon répéter le défaut de T2).
5. **Passe E — migrations** : jeu de migrations 0001-0081 sur base non vide dans les deux sens, hors `postgis-test` partagé (base séparée).

Contraintes : aucun de ces points ne modifie le code ; T1 et la passe B peuvent produire de nouveaux AUD à ajouter au lot L2 (sécurité) de `99-synthese.md` §4.
