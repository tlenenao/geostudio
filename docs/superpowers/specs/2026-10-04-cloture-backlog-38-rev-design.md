# Clôture des 38 REV « partiellement fermées » — spec

Date : 2026-10-04. Suite des plans A (`2026-10-03-backlog-lots-l0-l2-l3`) et B
(`2026-10-03-backlog-lots-l4-l5`), qui avaient laissé hors périmètre les lettres
**L1** (décision produit) et **L6** (rejeu sur stack réelle).

**Cible** : REV-008, 059, 063, 088, 093, 102, 109, 110, 123, 151, 164, 166, 183,
207, 210, 215, 216, 219, 223, 226, 268, 271, 272, 273, 274, 275, 276, 277, 278,
279, 280, 281, 282, 283, 284, 285, 286, 288.

**Règle de fermeture** : une REV passe `fermé` quand chacune de ses lettres est
(i) livrée en code + test, (ii) tranchée par ADR, ou (iii) rejouée sur stack réelle
avec preuve consignée. Piège n°12 : **la première tâche de chaque lot re-vérifie
chaque lettre dans le code** (plusieurs sont peut-être déjà closes, p. ex. REV-210
clés orphelines après `adb20afe`, REV-215 annulation après `request_cancel` de
REV-275) ; on ne code que ce qui est réellement ouvert.

## Arbitrages (QCM du 2026-10-04, tous « recommandé »)

| REV | Décision |
|---|---|
| 166 | `script-src` : **allowlist d'origines d'extensions par tenant**, défaut `'self'` (rien ne change sans action admin). |
| 281(b) | **cosign keyless + attestation SBOM** sur les 9 images, compose prod en `@sha256`, bases épinglées par digest. |
| 272(a) | **Statu quo documenté** : pas de tombstone ; ADR conformité ; validation DPO hors code. |
| 278(a) | **Refuser les types de widget inconnus** (422 RFC 7807) ; registre = natifs + extensions du tenant lues côté cœur. |
| 278(b) | **cel-python en validation à l'écriture** (parse seul), après évaluation licence/poids. |
| 279(a) | **Keyset sur PK** (curseur opaque, `offset` conservé) + `numberMatched` estimé au-delà d'un seuil. |
| 280(a,e,f) | **Snapshot « état courant » périodique** du lac + `lake_as_of` mesuré par LSN ; balayage mensuel optionnel des vieilles partitions. |
| 283(a) | **Agrégation en cellules** (`ST_SnapToGrid` + count) sous un zoom seuil ; badge de troncature conservé au-dessus. |
| 283(e) | **Bascule auto en job `export` asynchrone** au-dessus d'un seuil (file + notification existantes). |
| 286(a) | **Mode 2 volets** 640–899 px dans `TriptychLayout`. |
| 110/123 | Redshift (vérifié ou documenté) + Databricks livrés ; REV-110 close ; **REV-123 close par ADR** (la parité de connecteurs est un objectif continu suivi par la matrice FME, pas un défaut fermable). |
| 102/183 | **Tout livrer** : géocodage (widget app, outil MCP `geocode`, 2ᵉ fournisseur), NL→CEL sur colonnes calculées, actions composées, bindings. |

Défauts tranchés sans QCM (à contester à la relecture) : REV-063 close par
décision (seul le document gelé porte le chiffre, non éditable) ; REV-288(b) le
plancher de santé lit un snapshot committé, plus des artefacts de couverture locaux ;
REV-151 le shell consomme `limit/offset` via « Charger plus » sur les listes
catalogue/collections/moissonnage.

## Lots

Chaque lot : TDD, revue par tâche + revue finale de branche (CLAUDE.md), régénération
OpenAPI/types TS si route/modèle change, inventaire des fonctionnalités à jour.

### Lot A — Cœur : sécurité, intégrité, contrats (REV-008, 109, 166, 268, 271, 273, 275, 278)
- **008** : `READ_ONLY_TOOLS` dérivée d'un décorateur `@write_tool` (plus de liste à la main) ; test runtime du refus de `create_pipeline`.
- **109** : migrer `quote_ident` dans `pipelines/{compiler,connector_runtime,runtime}.py` (exclus en 2026-09-06), suite pipelines intégralement verte avant/après.
- **166** : modèle `ExtensionOrigin` par tenant (migration, `tenant_id` + `audit_log`), CRUD admin gardé par privilège, `traefik_render.py` ajoute les origines à `script-src` ; tests de rendu (défaut `'self'` inchangé).
- **268** : lecture partielle (range) pour l'inspection csv/geojson ; balayage d'orphelins étendu aux buckets d'échec post-upload.
- **271** : `If-Match` sur la branche d'édition de `VisualQueryWizardPage` et sur l'éditeur d'alerte existant (client déjà prêt, câbler l'éditeur).
- **273** : résidus (d) — épingler DSN mssql/oracle, essayer toutes les adresses résolues (pas seulement la première), IP masquée dans les messages, garde `Location` relative dans `pin_httpx_request` ; (b) listage glob borné avant plafond de fichiers, plafond d'octets **décompressés** gzip.
- **275** : jumelles de `mark_running` sur les autres tâches (REV-295) ; clé IP du limiteur non falsifiable (X-Forwarded-For honoré seulement depuis le réseau Traefik, REV-299).
- **278** : (a) registre de widgets côté cœur ; (b) cel-python ; migration douce des apps préexistantes incohérentes (REV-305 : avertir à la lecture, refuser à l'écriture).

### Lot B — Cœur : données, lac, export, intégrations (REV-102, 110, 123, 183, 279, 280, 283)
- **279(a)** curseur keyset + estimation de `numberMatched` ; OGC Features expose `next` en curseur, `offset` rétro-compatible. **(c)** relancer `index_plans.py` → lot D.
- **280** snapshot périodique (job procrastinate, file existante), lecture snapshot + delta, `lake_as_of` par LSN, balayage mensuel optionnel (e) ; **(d)** mesurer la mémoire du `GROUP BY` sur gros lac et fixer `memory_limit`/`MAX_GROUPS` d'après la mesure.
- **283** tuiles agrégées sous zoom seuil (`build_mvt_sql`, plafond et ETag conservés) ; export asynchrone au-dessus de `CORE_EXPORT_SYNC_MAX` (défaut 10^5), réponse 202 + job + notification.
- **110/123** Redshift, Databricks ; ADR positionnement connecteurs.
- **102** widget « adresse » (app builder), outil MCP `geocode`, 2ᵉ fournisseur derrière une interface unique, mêmes gardes d'egress.
- **183** `generate_cel_expression` étendu à colonnes calculées, actions composées, bindings (brouillon jamais appliqué sans clic, limites de REV-303 traitées).

### Lot C — Shell : UX, a11y, cohérence (REV-059, 063, 088, 093, 151, 207, 210, 215, 216, 219, 223, 226, 276, 284, 285, 286, 288)
- **059/088** règle ESLint locale : tout déclencheur de panneau en ligne sans `aria-expanded`/`aria-controls` (ou sans `usePanelTrigger`) échoue ; falsification obligatoire (piège n°10).
- **093** tests de `DatasetEditPage` et `AppBuilderPage`.
- **151** « Charger plus » (limit/offset ou curseur) sur catalogue, collections, enregistrements de moissonnage.
- **207** `MapEditorPage` adopte `useUrlSyncedState`.
- **210** purge des clés i18n orphelines restantes (le détecteur de 285(c) fait foi).
- **215** bouton Annuler sur un run en cours (API `request_cancel` existante).
- **216** `jobStatusLabel` sur `ExportPanel`, `AppExportPanel`, `PipelineCanvas`, `VisualQueryWizardPage`, `SqlLabPage`.
- **219** `beforeunload` branché sur `useDirtyGuard`.
- **223** résumé d'erreurs de formulaire + focus sur le 1ᵉʳ champ invalide ; `Field` du kit porte `aria-describedby`/`aria-invalid`.
- **226** audit exhaustif des `<label>` sans association ; règle `jsx-a11y/label-has-associated-control` en erreur.
- **276** (a) → lot D. **284** (b) reste lot D ; **285** (b) `h-8` résiduels → `h-9`, (d) `map/*` dans le détecteur de couleurs, (e) `readToken` réactif au thème, (g) fuseau fixé, (h) noms accessibles stables (index stocké, pas dérivé de l'ordre).
- **286** mode 2 volets ; (g) thème revérifié.
- **288(b)** plancher de santé lu d'un snapshot committé.

### Lot D — Rejeu sur stack réelle (L6) (REV-164, 272(b,c), 273(a), 274, 275, 276, 277, 278(d), 279(c), 280(b), 281(d), 282, 283(f), 284, 285(i), 286(c))
- Livrable : `docs/runbooks/2026-10-04-rejeu-stack-reelle.md` (checklist exécutable) + script `scripts/replay/run.sh` qui monte la stack, rejoue les journeys (`j01…j12`, `t01…t04`, `e2e-oidc`), la restauration de sauvegarde **avec reconnexion OIDC (REV-164)**, `index_plans.py`, `stack-smoke` et l'E2E `CORE_ADMIN_TOOLS_ENABLED` derrière Traefik, puis écrit un rapport daté dans `docs/revue/`.
- Bascule `bug(`→`test(` **uniquement après** rejeu vert (consigne REV-275).
- Mesure : `EXPLAIN` tri PK sur 10^6 entités (283f), mémoire `GROUP BY` (280d).
- **Non automatisable** : appareil tactile réel (286c) et lecteur d'écran réel (284d). Ils sont clos par procédure manuelle datée consignée dans le rapport ; si non exécutés, ces deux lettres restent explicitement `externe` sur la REV (non masquées).

### Lot E — Documentation et clôture
- ADR : `script-src`, supply chain, tombstone RGPD (statu quo), positionnement connecteurs.
- Pour chaque REV : ligne `**État**` mise à jour avec commits ; sommaire du backlog **recalculé mécaniquement** ; `analyse-gaps.md` (GAP-08/15/16/17/29/57/70/72…) ; inventaire des fonctionnalités + `feature_health_cli.py --write` ; `CHANGELOG.md` (migrations, variables `CORE_*` nouvelles, rupture éventuelle de 278(a)) ; une ligne dans `CLAUDE.md § Livré` + entrée détaillée dans l'historique.

## Ordre et dépendances
D dépend de A–C (on rejoue le code final). E en dernier. A, B, C sont indépendants
(fichiers disjoints, sauf `ItemClient`/OpenAPI : régénérer à chaque lot). Taille : plan
à découper en ≥ 3 branches de revue (A, B, C) puis D/E ; chaque lot a son ledger
`.superpowers/sdd/cloture38-<lot>-*` (piège n°9).

## Risques
- **278(a)** durcit l'écriture : une app existante avec widget inconnu devient non réenregistrable → avertissement à la lecture d'abord, note de montée de version.
- **280/283(e)** gros chantiers (L) : chacun peut devenir son propre SP si le plan l'estime > 2 jours.
- **cel-python** : vérifier licence (Apache-2.0 attendue) et divergences avec cel-js avant d'adopter ; sinon repli documenté.
- REV-272(a) fermée sans avis DPO : la fermeture est conditionnelle à sa validation.
- Pièges 1, 2, 5, 14 applicables : OpenAPI/types, câblage compose par valeur, `toFrontLayer`, jumelles de garde.
