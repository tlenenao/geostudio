# Feuille de route révisée — SP-44 et suivants

**Date du document :** 2026-09-04 (rédigé 2026-09-05). **Commit de base :**
`87eb55ad` + les commits SP-42 survenus depuis (spec de refactorisation
SP-43 incluse). **Tâche 16 de SP-42** (plan
`docs/superpowers/plans/2026-09-04-sp42-revue-globale.md`, lignes 1207-1245,
brief `.superpowers/sdd/sp42-task-16-brief.md`).

Ce document ne modifie aucun fichier existant de `docs/vision/` — il les
cite. Il phase les 79 gaps de
`docs/revue/2026-09-04-analyse-gaps.md` (`GAP-01` à `GAP-79`) en propositions
de SP numérotées à partir de **SP-44** : SP-43 (refactorisation structurelle,
`docs/superpowers/specs/2026-09-04-sp43-refactorisation-structurelle-design.md`)
est déjà pris par la Tâche 15 de cette même revue et n'est pas renuméroté ici.

Chaque gap retenu est rattaché à un numéro de SP ci-dessous. **Chaque gap non
retenu est explicitement listé au §3** et part au backlog unique
(`docs/revue/2026-09-04-backlog.md`, produit en parallèle par la Tâche 14) —
aucun ne disparaît silencieusement. **60 gaps sont retenus dans un SP,
19 partent au backlog** (60 + 19 = 79).

Ce que ce document **ne fait pas** : il ne rouvre aucun point que la revue a
vérifié comme déjà fermé — profil « Lecteur » dérivable (SP-31),
`CollectionPermissions` (SP-30a/SP-35), métadonnées et licence par jeu
(SP-41), restauration de sauvegarde côté données (runbook déjà rejoué une
fois, SP-Deploy-b) — voir `docs/revue/2026-09-04-analyse-gaps.md` §« Déjà
fermé, vérifié ici ». Il ne tranche pas non plus les questions produit
ouvertes du comparatif (§3) : une feuille de route qui prétend tout savoir
est fausse.

---

## 1. Pourquoi SP-43 vient tôt

SP-43 n'est pas un chantier de confort esthétique : c'est la condition pour
que les SP de ce document ne reproduisent pas la classe de défaut la plus
coûteuse déjà mesurée sur ce dépôt. Deux faits établis par la revue le
montrent directement :

- **Le mapping kind→privilège** (`core/app/configs/routes.py:127-139`) a
  quatre implémentations distinctes ; le critical d'autorisation qui en
  découle (`F-securite-autorisation-01`) **a été déclaré clos trois fois et
  rouvert deux fois** pendant l'exécution même de SP-42, précisément parce
  que chaque correctif touchait un des quatre sites sans vérifier les trois
  autres.
- **`toFrontLayer()`** (`shell/src/api/itemClient.ts:98-145`) a perdu
  **quatre champs successifs** au fil des sessions (`popup`, `symbology`,
  `renderAs`, puis `collectionId`/`pkColumn` — piège récurrent n°5 de
  `CLAUDE.md`) parce qu'ajouter un champ à `RawMapLayer`/`MapLayer` n'oblige
  mécaniquement à rien côté traduction.

Plusieurs SP de ce document touchent exactement ces deux surfaces (guides de
privilège, couches de carte). Les exécuter avant que SP-43 ait posé un
registre unique et un test caractéristique reproduirait la même classe de
défaut une 5e fois, au lieu de la fermer. C'est pourquoi le tableau ci-dessous
fait dépendre plusieurs SP de sous-étapes précises de SP-43 (pas de tout SP-43
en bloc — sa spec §5 l'ordonne elle-même du moins risqué au plus risqué), et
pourquoi **SP-44 (le seul gap bloquant) doit être traité avant l'étape 9 de
SP-43** : le découpage de `pipelines/runtime.py` (le plus risqué des neuf
étapes) ne doit pas être mené sans qu'au moins un test QGIS réel ait tourné
contre le sidecar une seule fois.

---

## 2. Tableau de phasage

Les coûts sont repris ou agrégés depuis `docs/revue/2026-09-04-analyse-gaps.md`
(colonne « Coût (j-h) » de chaque gap). Un SP marqué « dépend de SP-43/étape
N » suppose cette étape **fusionnée sur `dev`**, pas seulement planifiée.

| SP | Titre | Gaps couverts | Dépendances / prérequis | Coût (j-h) |
|---|---|---|---|---|
| **SP-44** ✅ | Débloquer M14 : exécution réelle des 5 tests `@pytest.mark.qgis` — **clos 2026-09-05**, cf. `CLAUDE.md` §Livré. A trouvé et corrigé 2 défauts de production réels (`transform.qgis` cassé par `_lock_down()`, `fid` GeoPackage non filtré) — l'étape 9 de SP-43 peut désormais être planifiée. Reste hors périmètre : câblage CI (session manuelle uniquement pour l'instant). | GAP-01 | ~~Prérequis : sidecar QGIS réel disponible (conteneur `qgis-worker`, profil `etl`, `CORE_TEST_QGIS_WORKER_URL` câblé en CI ou en session manuelle).~~ **Ne bloque plus l'étape 9 de SP-43.** | 1-3 |
| **SP-45** | Durcissement sécurité immédiat | GAP-02, GAP-41, GAP-58, GAP-61, GAP-77, GAP-78, GAP-79 | Aucune. Sept correctifs indépendants et bon marché (garde d'egress LLM, câblage du secret Martin, rate-limit sur `POST /collections/empty` et les 4 routes ArcGIS live-query, purge de la clé `age` de l'historique git, bascule `secret_scanning`/`dependabot_security_updates`, `restart:` sur `traefik`) — regroupés pour leur faible risque et leur valeur immédiate, pas pour un mécanisme commun. Bon candidat en tout début de vague. | 5-10 |
| **SP-46** | Découvrabilité : navigation manquante | GAP-30, GAP-32, GAP-39, GAP-67 | Aucune. Quatre écrans complets et testés, seulement inatteignables faute de lien de navigation (collections admin, catalogue de rapports, moissonnage, garde de privilège sur les liens d'`AdminExtensionsPage`) — même mécanisme (« livré mais inatteignable »), correctif mécanique. | 2-3 |
| **SP-47** | Audit, gouvernance des privilèges et vue d'usage | GAP-71, GAP-28 (même manque), GAP-03 | Recommandé après l'**étape 1 de SP-43** (registre kind→privilège unique) : nettoyer les 2 privilèges morts sur un registre déjà consolidé évite de le faire sur les quatre implémentations divergentes actuelles. | 4-7 |
| **SP-48** | CSP en enforcing | GAP-72 | Recommandé après SP-45 (même surface, Traefik/en-têtes). **Prérequis produit** : lever ou accepter formellement les 4 blocages documentés dans `docker-compose.prod.yml:167-184`, en particulier la décision sur le sandboxing des widgets d'extension tiers (`script-src 'self'`) — pas un simple réglage technique. | 3-6 |
| **SP-49** | Fiabilité des jobs & cohérence des migrations | GAP-56, GAP-63, GAP-64, GAP-76 (même manque que GAP-56 + réglage `GRAFANA_ALERT_WEBHOOK_URL`) | Dépend de l'**étape 4 de SP-43** (report des `server_default=` manquants, ~27 colonnes) et de l'**étape 5** (module de support de job partagé) : ce SP doit construire la reprise de jobs et l'indexation *sur* le module consolidé, pas sur les cinq copies actuelles. Le correctif du `downgrade()` cassé de la migration 0024 et les index manquants (`alert_evaluations`, `pipeline_runs`) restent hors du périmètre de SP-43 (non retenus par sa spec) — à faire ici. | 9-15 |
| **SP-50** | Robustesse des surfaces publiques (fédération) | GAP-57, GAP-59, GAP-60, GAP-62 | Aucune dépendance sur SP-43. Indépendant, peut courir en parallèle de la phase B. | 7-12 |
| **SP-51** | Parité carte : widget App Builder vs éditeur autonome | GAP-52, GAP-53, GAP-35, GAP-45, GAP-46, GAP-36 | Dépend de l'**étape 2 de SP-43** (test caractéristique de `toFrontLayer()` + nettoyage) et de l'**étape 7** (découpage `itemClient.ts` par domaine) : GAP-46 touche directement `toFrontLayer()` — l'exécuter avant que SP-43 ait posé son filet créerait une 5e occurrence du piège n°5 plutôt que de le fermer. | 12-20 |
| **SP-52** | App Builder : UX d'édition | GAP-33, GAP-54, GAP-66, GAP-51, GAP-13 | Aucune dépendance bloquante. Regroupe les défauts d'édition (suppression de widget absente, `setFilter` qui écrase au lieu de fusionner, variables orphelines, source Statique sans champ de saisie, widget de saisie de variable) et un retrait de code mort (`resizeItem`). | 7-12 |
| **SP-53** | Automatisation : compléter les éditeurs + déclenchement par webhook | GAP-43, GAP-44, GAP-48, GAP-50, GAP-49, GAP-24 | Aucune dépendance bloquante. GAP-24 reprend le suivi déjà nommé par `CLAUDE.md` (« SP-15 : événements/déclencheurs durables au-delà du cron, non planifié ») — devient concret ici plutôt que de rester un suivi permanent. | 10-15 |
| **SP-54** | API shell (`ItemClient`) : combler les surfaces + partage avancé | GAP-42, GAP-65, GAP-40, GAP-47, GAP-38, GAP-12 | Recommandé après l'**étape 7 de SP-43** (découpage `itemClient.ts`/`hooks.ts` par domaine) : ajouter `createGroup`/`addMember`, la recherche hybride des collections, un TTL de cache dataset et les liens de partage à échéance sur le fichier déjà scindé évite d'alourdir le monolithe juste avant sa découpe. | 10-18 |
| **SP-55** | Catalogue : tri, facettes, recherche spatiale, SEO | GAP-05, GAP-06, GAP-07 | Aucune dépendance. Chantiers 4.7/4.8/4.10 du plan d'action, jamais entamés. | 8-13 |
| **SP-56** | Import : formats manquants (XLSX, KML/KMZ, GeoParquet) | GAP-09, GAP-29 (même manque) | Aucune dépendance. Chantier 4.14 du plan d'action ; GAP-29 mesure le même écart côté benchmark, sans coût additionnel. | 3-6 |
| **SP-57** | Vague 5 — qualité transverse : i18n, accessibilité, contrat d'API, ADR | GAP-14 | L'**étape 6 de SP-43** pose déjà la primitive `aria-expanded`/`aria-controls` et l'applique aux 7 sites déjà identifiés — ce SP part de cette base plutôt que de la reconstruire, mais le reste (adoption i18n à l'échelle de 124 fichiers, dépendance `axe-core`, préfixe `/v1/`, `docs/adr/`, guide de contribution) reste un chantier entier, jamais entamé malgré son statut de « vague » nommée depuis 2026-08-20. Signalé par la revue comme angle mort complet — priorité élevée malgré sa taille, à ne pas repousser indéfiniment. Candidat à un découpage en sous-parties (a/b) comme d'autres SP l'ont fait. | 8-15 |
| **SP-58** | Conformité : quotas par tenant & droit à l'effacement (RGPD) | GAP-73, GAP-74, GAP-11 (même manque que GAP-73) | Aucune dépendance technique. Pertinent dès qu'un tenant réel autre que l'opérateur est onboardé — voir Q2 au §3. | 10-18 |
| **SP-59** | Exploitation : sauvegarde automatisée + vérification OIDC réelle, rotation des secrets | GAP-70, GAP-75 | **Prérequis** : un environnement Keycloak réel pour rejouer la restauration sans substituer `CORE_AUTH_MODE=mock` — même limite d'environnement que celle déjà rencontrée par SP-32 pour le smoke Traefik. | 6-10 |
| **SP-60** | Performance frontend & filets de test | GAP-68, GAP-69 | L'**étape 3 de SP-43** (fixture de collection E2E unique) ferme déjà la moitié de GAP-69 (mocks E2E qui servent une forme que le cœur ne produit jamais) — ce SP part de cette fixture pour le reste (comparateur modèle/Alembic, ancre positive de `triptych-narrow.spec.ts`, sécurité des routeurs Traefik, extracteur `core_env_vars()`, assertion « lisible anonymement » trop faible) et pour le volet performance (code-splitting par route, `MapView` non lazy, sondages non annulés au démontage). | 6-11 |

**Total retenu : 60 gaps sur 17 SP** (SP-44 à SP-60), coût agrégé
approximatif **112-186 jours-homme** (somme des bornes par SP — indicatif,
ne tient pas compte du chevauchement possible entre SP indépendants).

### Ordre d'exécution suggéré

1. **Phase A — indépendante, à lancer dès la fin de SP-43 (ou en parallèle
   de ses étapes 0-3, qui ne touchent aucune des surfaces ci-dessous) :**
   SP-44 (débloque M14 **et** l'étape 9 de SP-43), SP-45, SP-46.
2. **Phase B — dépend d'étapes précises de SP-43, à ne lancer qu'une fois
   ces étapes fusionnées sur `dev` :** SP-47 (étape 1), SP-48 (après SP-45),
   SP-49 (étapes 4+5, et après SP-44 pour l'étape 9 sous-jacente), SP-51
   (étapes 2+7), SP-54 (étape 7), SP-60 (étape 3, en partie).
3. **Phase C — indépendante de SP-43, ordre libre selon priorité produit :**
   SP-50, SP-52, SP-53, SP-55, SP-56, SP-57, SP-58, SP-59.

---

## 3. Gaps renvoyés au backlog (19)

Aucun gap non retenu ci-dessus ne disparaît : chacun devient une entrée
`REV-nnn` dans `docs/revue/2026-09-04-backlog.md` (Tâche 14, produite en
parallèle de cette feuille de route). Liste explicite et raison du renvoi :

| GAP | Manque (résumé) | Raison du renvoi |
|---|---|---|
| GAP-04 | Conformité STAC non vérifiée en CI (`stac-api-validator`) | Confort, coût 1-2j, aucun incident constaté à ce jour ; à reprendre au rythme normal du backlog. |
| GAP-08 | Géocodage (fournisseur BAN) | Dépend d'une décision produit (fournisseur enfichable à choisir) plus que d'un manque technique urgent ; attend Q2/Q3 (cas d'usage prioritaire). |
| GAP-10 | Animation temporelle play/pause/vitesse | Confort, chantier 4.17, aucune demande utilisateur connue à ce jour. |
| GAP-15 | Helper de quoting SQL dupliqué (17 fichiers) + `itemClient.ts` grossi | **Partiellement couvert par SP-43** (étape 7, découpage d'`itemClient.ts` par domaine, répond au second volet). Le premier volet — factoriser le helper `_qi`/`quote_ident` dupliqué sur 17 fichiers `core/app` — n'est retenu par aucune étape de la spec SP-43 ; renvoyé au backlog comme prolongement mécanique à faible risque, à faire dans la foulée de SP-43 plutôt que dans un SP dédié. |
| GAP-16 | Aucun connecteur natif entrepôt cloud analytique | Référentiel 2 (benchmark, non vérifiable dans le code), coût 5-10j, dépend directement de Q2 (le marché cible détermine si un connecteur BigQuery/Snowflake a un utilisateur réel). |
| GAP-17 | Aucune génération NL→SQL/CEL avec revue humaine | Référentiel 2, dépend de Q2 et d'une décision de fournisseur LLM déjà expérimentale (copilote SP-20) ; à ne pas engager avant d'avoir mesuré l'usage du copilote existant. |
| GAP-18 | Aucun marketplace/registre public d'extensions inter-tenants | Référentiel 2, coût 8-15j (infrastructure de partage + modération), suppose un écosystème de tiers qui n'existe pas encore ; dépend de Q2/Q1 (produit diffusé publiquement avec contributeurs tiers ?). |
| GAP-19 | Aucun SDK d'embedding avec authentification déléguée | Référentiel 2, pertinent seulement dans un scénario B2B/SaaS ; dépend directement de Q2. |
| GAP-20 | Aucune édition collaborative temps réel | Référentiel 2, chantier lourd (10-20j, CRDT ou équivalent) ; recoupe directement **Q10** (temps réel) — non engageable avant réponse. |
| GAP-21 | Aucun workflow d'édition versionnée à conflits (branch versioning) | Référentiel 2, niche, dépend du marché cible (Q2) ; coût 10-15j disproportionné sans utilisateur identifié. |
| GAP-22 | Aucune sécurité au niveau colonne | Référentiel 2, pertinent seulement si des rôles fins doivent un jour partager une même collection — scénario non confirmé ; dépend de Q2/Q9 (multi-tenant réel). |
| GAP-23 | Aucune exploration automatique façon « X-rays » | Référentiel 2, confort, coût 5-8j, aucune demande connue. |
| GAP-25 | Aucune couche sémantique/synchronisation de métriques centralisée | Référentiel 2, confort, chantier en discussion même chez Superset (SIP non stabilisé) — prématuré de s'aligner dessus. |
| GAP-26 | Aucune app mobile de collecte terrain | Référentiel 2, gros chantier (15-30j) ; recoupe directement **Q11** (terrain/offline) — non engageable avant réponse. |
| GAP-27 | Aucune restriction géographique de permission (« Geo Limits ») | Référentiel 2, niche, coût 5-8j, aucun scénario identifié. |
| GAP-31 | `capabilities` sur `GET /me` jamais consommé par le shell | Confort, coût 0.5-1j (câbler `AppLayout.tsx` sur le champ déjà servi plutôt que de refaire un second appel `GET /instance`) ; correctif isolé et sans risque, à faire au fil de l'eau plutôt que dans un SP dédié. |
| GAP-34 | Options de gabarit d'impression (échelle, flèche du nord) non rendues | Confort ; nécessite d'abord une décision produit (implémenter le rendu à 2-3j, ou retirer les champs du schéma à coût nul) avant tout chiffrage définitif — non tranché ici, cf. §4. |
| GAP-37 | Script `generate-pmtiles.sh` orphelin | Confort ; décision binaire (retirer à coût nul, ou réactiver à 3-5j) sans utilisateur actuel — non urgent. |
| GAP-55 | Éditeur d'actions narratif limité à un payload de centrage carte | Confort, coût 1-2j, fonctionnalité de niche (mode narratif) sans demande connue. |

---

## 4. Ce qui reste non arbitré

Cette feuille de route ne prétend pas trancher ce que seule une décision
produit peut trancher. Trois catégories restent explicitement ouvertes :

### 4.1 Les trois questions produit du comparatif (2026-07-04)

- **Q2 — Premiers utilisateurs réels** (`docs/vision/2026-07-04-comparatif-
  projet-actuel-vs-vision.md:463-465`) : qui sont les 1 à 3 premiers
  utilisateurs/déploiements visés à 12 mois, et quel est LE cas d'usage
  qu'ils doivent réussir ? **C'est la seule question qui puisse réordonner
  tout ce phasage.** Une réponse concrète changerait directement la
  priorité relative de SP-55/56 (catalogue, import — utile à tout
  utilisateur), SP-58 (quotas/RGPD — urgent seulement si un tenant externe
  réel est onboardé), et de la totalité des 11 gaps référentiel 2 renvoyés
  au backlog par Q2 au §3 (GAP-16 à GAP-27 sauf GAP-24/28/29).
- **Q10 — Temps réel et alertes** (`…comparatif…:507-508`) : besoin concret
  identifié (flotte, capteurs, crues…) ou spéculatif ? Conditionne
  directement GAP-20 (édition collaborative temps réel), laissé au backlog
  faute de réponse.
- **Q11 — Terrain / offline** (`…comparatif…:512-513`) : la collecte
  terrain hors connexion est-elle dans le périmètre des deux prochaines
  années ? Conditionne directement GAP-26 (app mobile de collecte),
  également laissé au backlog. Le comparatif le note lui-même comme « le
  chantier le plus structurant côté client » — à trancher avant de figer
  quoi que ce soit sur le SDK si la réponse devient oui.

Ces trois questions sont listées comme non arbitrées par `CLAUDE.md` lui-même
(§Questions produit ouvertes) depuis le 2026-07-04 ; cette revue ne les a pas
rapprochées d'une réponse, elle confirme seulement quels gaps en dépendent
directement.

### 4.2 Arbitrages que cette revue a fait remonter sans les trancher

- **Sandboxing des widgets d'extension tiers** (SP-48/GAP-72) : basculer la
  CSP en enforcing suppose une décision sur `script-src` pour les widgets
  d'extension — aucune option n'a été évaluée ici (nonce, hash, origine
  déclarée par extension, ou renoncement au chargement dynamique de script
  arbitraire).
- **Implémenter ou retirer le rendu des options de gabarit d'impression**
  (GAP-34, backlog) : le schéma promet un rendu que `PrintLayoutPanel.tsx` a
  délibérément retiré (correctif de revue finale SP-17a) — les deux issues
  (implémenter à 2-3j, ou retirer les champs du schéma à coût nul) sont
  également valables, aucune n'a été choisie.
- **Réactiver ou retirer `scripts/generate-pmtiles.sh`** (GAP-37, backlog) :
  même situation binaire, non tranchée.
- **Ordonnancement fin de la Phase B** (§2) : les dépendances vers des
  étapes précises de SP-43 sont explicitées, mais l'ordre relatif *entre*
  SP-47/48/49/51/54 une fois leurs prérequis SP-43 satisfaits n'est pas
  imposé — il peut suivre la disponibilité de session plutôt qu'un ordre
  technique strict.
- **Découpage de SP-57** (vague 5) : signalé comme candidat à un
  sous-découpage (a/b, comme SP-9 ou SP-15 l'ont fait) vu son coût agrégé
  (8-15j) et sa nature de « vague » entière plutôt que d'un chantier
  ponctuel — le découpage exact (i18n+a11y d'un côté, contrat d'API+ADR+
  contribution de l'autre, ou une autre coupe) n'est pas fixé ici.

Une feuille de route qui prétendrait avoir réponse à tout serait fausse :
les points ci-dessus restent au jugement de Tanguy, pas de cette revue.
