# Purge du backlog (27 entrées « ouvertes ») + 2 corrections réelles restantes (design)

**Date :** 2026-09-11. Origine : demande directe de Tanguy (« corrige tous les points REV-003,
005, 011, 042, 094, 098, 102, 104, 110, 111, 112, 113, 114, 115, 116, 117, 119, 120, 121, 128,
149, 174, 175, 176, 178, 180, 181 ») — soit, vérification faite, **exactement** la liste actuelle
de la section « 🔴 Ouvert » de `docs/revue/2026-09-04-backlog.md`.

## 1. Objectif & non-buts

**Constat de départ (vérifié dans le code, pas supposé)** : sur les 27 entrées demandées, **20
sont déjà résolues** par des commits du 2026-09-06/07 qui citent nommément le REV concerné, sans
que le champ `État :` de `backlog.md` n'ait jamais été mis à jour — la classe de dérive documentée
par CLAUDE.md piège n°12, appliquée cette fois au backlog plutôt qu'à la matrice de
fonctionnalités (et par le fait que REV-181, censé endiguer *exactement* ce piège, ne couvre que
le bilan de fonctionnalités, pas ce document-ci). Cela inclut REV-175 : le spike qu'il réclamait a
été mené et documenté (`core/tests/test_model_alembic_parity.py`, commit `a1579cd3`), conclusion
**négative et actée** (ne pas matérialiser les 4 index en `Base.metadata` — Alembic est
structurellement aveugle à toute dérive sur `postgresql_ops`/`postgresql_with`, matérialiser
donnerait une fausse impression de vérification). 2 entrées supplémentaires (REV-102, REV-111) ont
déjà leur propre spec + plan validés par ailleurs, non exécutés ou partiellement exécutés. Il ne
reste que **2 corrections de code réelles** à faire (REV-094, REV-176), plus les 12 « gaps non
retenus » du référentiel benchmark (REV-104, 112–117, 119–121) qui sont des décisions produit
délibérément non planifiées, pas des défauts — ce plan ne les touche pas.

**Objectif de ce plan :**

1. Remettre `backlog.md` en cohérence avec l'état réel du code pour les 13 entrées déjà fermées ou
   partiellement fermées (bookkeeping seul, aucun changement de comportement).
2. Corriger réellement les 2 entrées encore ouvertes de bonne foi : REV-094 (migration UI),
   REV-176 (contraste d'un token de design).

**Non-buts (explicites) :**

- Ne pas toucher REV-102 (géocodage BAN) ni REV-111 (NL→SQL/requête visuelle) : chacun a déjà sa
  propre spec + plan mergés (`docs/superpowers/specs/2026-09-07-rev102-geocodage-ban-design.md`,
  `docs/superpowers/specs/2026-09-06-gap17-nl-sql-copilote-design.md`) — les exécuter relève d'un
  plan séparé, pas d'une nouvelle conception. REV-111 a même un début d'implémentation non commité
  dans `.claude/worktrees/gap17-nl-sql-copilote` (Tâche 1, Étape 3 du plan existant) : à reprendre
  tel quel, pas à redémarrer.
- Ne pas construire, ni même esquisser, les 12 gaps benchmark restants (REV-104, 112 à 117, 119 à
  121) : ce sont des choix de roadmap déjà tranchés comme « non retenus », leur statut `ouvert`
  dans le backlog reste correct en l'état et n'est pas une anomalie à corriger.
- Ne pas re-vérifier le texte de correctif proposé par chaque entrée du backlog au-delà de ce qui
  est nécessaire pour écrire une ligne de fermeture honnête — le travail de fond a déjà été fait et
  revu par les sessions qui ont produit les commits cités en §2.

## 2. Tâche 1 — Bookkeeping `backlog.md` (13 entrées, aucun code touché)

Pour chaque entrée listée ci-dessous : remplacer la ligne `- **État :** ouvert...` par une seule
ligne `- **État :** fermé — commit \`<sha>\` : <résumé>` ou `- **État :** partiellement fermé —
commit(s) \`<sha>\` : <résumé>` (résumé factuel, pas une paraphrase du titre), au même gabarit que
les fermetures déjà rédigées ailleurs dans le document (cf. REV-177). Ne toucher à rien d'autre
dans le corps de l'entrée (preuve/correctif minimal d'origine, et toute ligne `**Renvoi :**`
préexistante pointant vers `analyse-gaps.md` reste telle quelle).

| REV | Nouvel état | Commit(s) | Résumé à écrire |
|---|---|---|---|
| REV-003 | fermé | `6101e9eb` | Vérification bout-en-bout Keycloak réelle + `X-Frame-Options: DENY` documentée dans `useMcpToken.ts` (chemin réel : `shell/src/builder/copilot/useMcpToken.ts`, pas `shell/src/copilot/...`) : `signinSilent({forceIframeAuth:true})` réussit malgré le middleware, aucun correctif de contournement nécessaire. |
| REV-005 | fermé | `e0119c79` (intégration SP-45, GAP-61.c) | Cache `_cache` de `live_query.py` gagne un TTL + un `_sweep` périodique (patron `RateLimiter._sweep`) ; 2 des 4 routes ArcGIS live-query rattachées au groupe rate-limit `harvest`, les 2 autres déjà couvertes par le groupe `jobs` via `_EXPORT_PATH_RE`. |
| REV-011 | fermé | `c721c3fa` | `register_collection` vérifie désormais un conflit d'id **cross-tenant** (409 explicite) via `get_collection_by_id_any_tenant` ; `list_candidate_tables` exclut les tables déjà enregistrées par n'importe quel tenant. |
| REV-042 | fermé | `7a2f9414` | `OpenAICompatibleProvider.embed` construit son client via `build_guarded_client()` (`app.search.egress`) au lieu d'un `httpx.post` nu. |
| REV-098 | fermé | `e11fda2b` | Job CI `stac-conformance` : `stac-api-validator` sur core/collections/features (bloquant), item-search en `continue-on-error` documenté (non bloquant, ~25 erreurs réelles restantes, hors périmètre de cette fermeture). |
| REV-110 | **partiellement fermé** | `163a0278`, `e7133941`, `44f1d228`, `95267b68` | Snowflake livré (`reader.connector.snowflake`, secret `snowflake_dsn`, testé manuellement via `@pytest.mark.snowflake`, jamais câblé en CI faute d'émulateur). Redshift compatible par construction avec `reader.connector.postgres` existant, jamais vérifié contre un cluster réel (littérature AWS seule). Databricks mécaniquement faisable (même patron DSN), non fait. BigQuery bloqué par la conception actuelle de `SecretPayload` (DSN texte simple, incompatible avec un compte de service JSON) — nécessiterait une conception dédiée, hors périmètre. |
| REV-128 | fermé | `ff018dc3` | Option retenue : retrait de `showScaleBar`/`showNorthArrow` du schéma `PrintLayout` (`core/app/configs/schemas.py`) plutôt que l'implémentation du rendu — ces champs étaient authorables/validés/round-trippés mais jamais rendus nulle part. |
| REV-149 | fermé | `edff7592` | `shell/src/builder/NavigationPanel.tsx` (pas un fichier « chapitre » dédié) ne construit un payload `{center:[lon,lat]}` que pour l'action `flyTo` ; les autres actions ne reçoivent plus ce payload sans rapport. |
| REV-174 | fermé | `346e9bb9` | `save_app_config` (MCP) exécute désormais la même séquence de gardes de capacité + validateurs par kind que `PUT /configs/by-item/{id}` (regroupée via `app.configs.service`), plus d'écart outil↔route. |
| REV-175 | fermé | `a1579cd3` | Spike mené sur Postgres+pgvector jetable : les 2 formes `Index()` SQLAlchemy équivalentes émettent un DDL byte-pour-byte identique au DDL brut existant, **mais** Alembic (`compare_metadata()`) est structurellement aveugle à toute dérive réelle sur `postgresql_ops`/`postgresql_with` (lève un `UserWarning` et renonce). Décision actée : ne pas matérialiser en `Base.metadata` — le filtre nommé `_KNOWN_FUNCTIONAL_INDEXES` reste en l'état, documenté comme délibéré (pas un oubli), à revérifier lors d'une montée de version majeure d'Alembic/SQLAlchemy. |
| REV-178 | **partiellement fermé** | `802d4daa` | Échantillon d'audit a11y élargi de 9 à 17 pages, `eslint-plugin-jsx-a11y` ajouté en complément statique — les deux suivis explicitement proposés par l'entrée d'origine sont faits. Reste hors périmètre, assumé : exhaustivité du catalogue de routes (centaine de pages), navigation clavier exhaustive, contraste en mode sombre (le shell n'a qu'une ambiance aujourd'hui). |
| REV-180 | fermé | `e11fda2b` | `bilan.js` lit désormais `priorite_source` (`isReviewedPrioritySource`, `priorityBadge`) et affiche une tuile de synthèse « priorités encore amorcées ». Seul `render_md.py` reste sans colonne dédiée — jugé non bloquant (le rendu HTML est la vue de référence). |
| REV-181 | fermé | `e11fda2b` | `feature_health_cli.py` gagne un mode `--check-fresh` (recalcule en mémoire, diffe contre les fichiers committés), câblé dans le job CI dédié. |

**Vérification requise avant d'écrire chaque ligne** (ne pas recopier le tableau ci-dessus les yeux
fermés) : `git show --stat <sha>` puis relire le fichier réel pour confirmer que le commit est bien
sur `dev` (`git merge-base --is-ancestor <sha> dev`) et que le contenu correspond toujours à la
description — le dépôt continue de bouger, un nouveau décalage entre l'écriture de cette spec et
son exécution est possible.

### 2.1 Recalcul de la section « Répartition par statut »

Après application du tableau ci-dessus **et** des Tâches 2-3 (§3-4, en supposant qu'elles
aboutissent toutes les deux à une fermeture réelle) :

- **Fermé** : 144 (compte actuel, vérifié par comptage direct de la liste — l'en-tête `✅ Fermé
  (143)` est lui-même déjà décalé d'une unité par rapport à la liste et à la phrase de synthèse,
  corriger les deux au passage) + 11 (REV-003/005/011/042/098/128/149/174/175/180/181) + 2
  (REV-094/176, si les deux aboutissent) = **157**.
- **Partiellement fermé** : 11 + 2 (REV-110, REV-178) = **13**.
- **Ouvert** : 27 − 11 − 2 − 2 = **12** (REV-102, 104, 111, 112, 113, 114, 115, 116, 117, 119, 120,
  121 — inchangé, correct).

Si un axe d'accessibilité de la Tâche 3 (REV-176) révèle un obstacle imprévu, recalculer ces trois
nombres en conséquence plutôt que de forcer les totaux ci-dessus — ils sont un résultat attendu,
pas une contrainte à satisfaire coûte que coûte. Régénérer les trois listes à virgules (déplacer
chaque REV de sa liste d'origine vers sa nouvelle liste) et corriger la phrase de synthèse en tête
de section (qui doit rester la source de vérité, cf. sa propre consigne : « recompter
mécaniquement, ne pas rééditer à la main entrée par entrée » — ici la mise à jour du champ `État`
de chaque entrée correspond bien à « l'entrée concernée », la régénération des listes reste
néanmoins manuelle faute de script de recoupement dans le dépôt).

## 3. Tâche 2 — REV-094 : migrer les 2 derniers consommateurs de `ui/dialog.tsx`

**Constat vérifié** : `wide` (`ui/dialog.tsx` : `max-w-2xl` vs `max-w-md`) est un réglage
utilisateur réel et actif du widget runtime « Modale » (`builder/widgets/modal.tsx`, case à cocher
`widgetModal.wideToggle`), pas du code mort. `ui/kit/Dialog` (Radix) n'a aujourd'hui aucune prop de
taille — largeur fixée en dur à `max-w-md`. Une migration qui ignorerait ce point ferait régresser
silencieusement ce réglage.

**Correctif :**

1. `shell/src/ui/kit/Dialog.tsx` gagne une prop `size?: "md" | "lg"` (défaut `"md"`, comportement
   actuel inchangé pour tout consommateur existant) — `"lg"` mappe sur la largeur `max-w-2xl`
   actuelle d'`ui/dialog.tsx`.
2. `shell/src/pages/AppRuntimePage.tsx` migre vers `ui/kit/Dialog` (n'utilise pas `wide` —
   vérifié : aucune occurrence).
3. `shell/src/builder/widgets/modal.tsx` migre vers `ui/kit/Dialog` avec `size={wide ? "lg" :
   "md"}` ; `onClose={() => setOpen(false)}` devient `onOpenChange={setOpen}`.
4. Si `shell/src/ui/dialog.tsx` n'a plus aucun consommateur après ces deux migrations (à vérifier
   par grep, pas supposé), le supprimer.
5. Tests : adapter les tests existants des deux fichiers migrés à la nouvelle API ; ajouter un test
   sur `ui/kit/Dialog` qui vérifie concrètement que `size="lg"` rend la classe de largeur attendue
   (pas seulement que le composant s'affiche).

**Critère d'acceptation** : `grep -rn "ui/dialog\"" shell/src` ne retourne plus rien (hors le
fichier lui-même, s'il est conservé pour une raison imprévue — auquel cas la documenter). Le widget
« Modale » en mode large visuel inchangé (vérifié à l'œil dans le builder, pas seulement par les
tests).

## 4. Tâche 3 — REV-176 : contraste du token `--gs-ink-3`

**Contexte vérifié** : `--gs-ink-3` vaut `#6e8087` (clair, sur fond `--gs-background: #eff2f1`,
contraste mesuré 3.65:1) et `#7c8f94` (sombre) dans `shell/src/styles/tokens.css` (lignes 40, 91,
134) — sous le seuil WCAG AA de 4.5:1 pour du texte normal, trouvé par `@axe-core/playwright` et
actuellement exclu nommément (par valeur de couleur) dans `shell/e2e/a11y-audit.spec.ts::EXCLUSIONS`.
La hiérarchie de texte du design system a 3 niveaux : `--gs-ink` (`#0e1a20`, le plus foncé) >
`--gs-ink-2` (`#3b4c54`) > `--gs-ink-3` (le plus atténué) — environ 20 fichiers consommateurs.

**Correctif :**

1. Choisir, pour le clair et le sombre séparément, la valeur la plus proche de l'actuelle qui
   atteint ≥4.5:1 sur `--gs-background` de son ambiance, tout en restant strictement plus clair
   (moins contrasté) que `--gs-ink-2` de la même ambiance — préserver l'ordre de la hiérarchie, pas
   seulement le seuil AA de `--gs-ink-3` isolément.
2. Vérifier visuellement l'impact sur `/internal/kit-gallery` (galerie interne SP-29b, seul endroit
   qui rend toutes les primitives d'un coup) et sur 2-3 pages réelles citées par REV-176
   (`StatusBar`, `LayersPanel`) dans les deux ambiances.
3. Retirer l'exclusion `--gs-ink-3` de `shell/e2e/a11y-audit.spec.ts::EXCLUSIONS`.
4. **Falsifier avant de conclure** (cf. CLAUDE.md piège n°10) : remettre temporairement l'ancienne
   valeur avec l'exclusion retirée, confirmer que le test a11y échoue bien sur au moins une des 17
   pages de l'échantillon ; remettre la nouvelle valeur, confirmer qu'il passe.

**Critère d'acceptation** : le test a11y passe sans aucune exclusion `color-contrast` restante liée
à `--gs-ink-3` (si une autre violation `color-contrast` sans rapport existe déjà ailleurs, ne pas
la corriger dans cette tâche — hors périmètre).

## 5. Tests / validation d'ensemble

- Tâche 1 (bookkeeping) : aucun test de code — relecture croisée du tableau §2 contre les commits
  réels avant de committer les changements de `backlog.md`.
- Tâches 2-3 (REV-094, REV-176) : TDD standard du dépôt (test falsifié avant correctif). Suite
  complète shell (`npm run test`, `npm run build`) et E2E ciblée
  (`shell/e2e/a11y-audit.spec.ts` pour la Tâche 3).
- Revue finale de branche (CLAUDE.md piège n°4) : vérifier en particulier que la Tâche 1 ne
  contredit pas les Tâches 2-3 (une entrée passée « fermé » dans `backlog.md` avant que son
  correctif ne soit réellement mergé serait pire que l'état actuel — committer la ligne
  bookkeeping de REV-094/REV-176 dans le même commit que leur correctif réel, jamais avant).

## 6. Hors périmètre (explicite)

- REV-102, REV-111 : specs + plans propres, à exécuter séparément (cf. §1).
- REV-104, 112, 113, 114, 115, 116, 117, 119, 120, 121 : gaps benchmark non retenus par la feuille
  de route révisée, décision produit déjà actée, pas une correction de code.
- Databricks/BigQuery pour REV-110 : notés comme travail futur possible, pas construits ici.
- `render_md.py` sans colonne `priorite_source` (reliquat mineur de REV-180) : non corrigé, jugé
  non bloquant.
- Toute autre entrée du backlog non listée en §1 de la demande d'origine (y compris les 155 déjà
  `fermé`/`partiellement fermé` avant ce plan) : hors périmètre, ce plan ne les revérifie pas.
