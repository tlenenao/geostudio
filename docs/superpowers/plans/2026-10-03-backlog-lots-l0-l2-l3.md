# Backlog Plan A (L0 clôtures, L2 sécurité/intégrité, L3 pipelines) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fermer 18 entrées du backlog (REV-111/116/185/186/187/188/195/196/197/198/199/239/269/271/272/273/275/290) : clôtures documentaires, correctifs de sécurité/intégrité, robustesse des op de pipeline.

**Architecture:** Lots indépendants à correctifs ciblés, chacun en TDD ; aucune nouvelle capacité produit. Spec : `docs/superpowers/specs/2026-10-03-backlog-lots-l0-l2-l3-design.md`.

**Tech Stack:** Python/FastAPI (`core/`, pytest, postgis-test, ruff, mypy --strict, import-linter), React/TS (`shell/`, vitest, Playwright), Docker Compose.

## Global Constraints

- Docs et messages utilisateur en **français** ; code/identifiants en anglais.
- Commits conventionnels, petits, un sujet, terminés par `Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>`.
- Branche `dev` uniquement ; pas de branche `main` locale ; aucun push ni tag sans demande de Tanguy.
- TDD systématique ; un correctif de filet de test est vérifié par falsification (piège n°10).
- `CORE_TEST_DATABASE_URL` doit pointer un postgis-test réel, sinon les tests `postgis` skippent silencieusement (piège SP-43). Migration : tester sur base non vide, dans les deux sens.
- Régénérer OpenAPI + types TS dès qu'une route/un modèle change (commande exacte dans CLAUDE.md §Commandes).
- Jumelles de garde à traiter dans le même geste (piège n°14) ; vérifier dans le code, jamais dans le récit (piège n°12).
- Sous-points « rejeu stack réelle » et décisions produit : **hors périmètre**.
- Ledgers SDD nommés `.superpowers/sdd/backlogA-*`.

## Ordre d'exécution (contraintes entre lots)

1. **L0** (Tasks L0-*) en premier ; la tâche CLOSE en dernier.
2. **L3a avant L2a-REV-197** : L3a-11 (M12) et REV-197 touchent la même fonction `materialize_blob_connector` (zones disjointes).
3. **REV-197 (L2a) avant L2c-4 et L2c-9** (même fonction, nouveau helper `_blob_fs_kwargs`).
4. L2a-7 et L2a-8 s'enchaînent (le shell ne compile pas entre les deux).
5. Ordre global recommandé : L0 → L3a → L3b → L2a → L2b → L2c → CLOSE.

---

## Lot L0 — Clôtures documentaires (aucun code)

Spec : `docs/superpowers/specs/2026-10-03-backlog-lots-l0-l2-l3-design.md` § L0 + REV-269 + Transverse.
Toutes les tâches L0 ne touchent que de la documentation : pas de TDD, la « preuve » est un `grep`
ou le recomptage mécanique. Les fichiers sont tous sous `docs/revue/` sauf CLAUDE.md et l'archive.

Convention d'édition : chaque remplacement ci-dessous se fait avec l'outil Edit (`old_string` = texte
exact cité, unique dans le fichier ; si Edit refuse pour non-unicité, élargir avec la ligne `### REV-nnn`
qui précède). Le fichier backlog est `docs/revue/2026-09-04-backlog.md` (abrégé `BACKLOG`).

Outil de comptage (créé à la Task L0-1, réutilisé aux Tasks L0-5 et CLOSE) :
`.superpowers/sdd/backlogA-count-etat.sh` (dossier gitignoré, non commité).

---

### Task L0-1: Script de recomptage mécanique et baseline

**Files:**
- Create: `.superpowers/sdd/backlogA-count-etat.sh` (non commité)
- Read: `docs/revue/2026-09-04-backlog.md` (lignes `- **État :**`, 293 entrées `### REV-nnn`)

**Interfaces:**
- Consumes: le format réel des lignes d'état du backlog : `- **État :** fermé…`, `- **État : fermé par SP-xx**…` (astérisques autour), `**Fermé**`, `**Partiel**`, `**résolu`, `informationnel…`. Un état = la PREMIÈRE ligne `- **État` suivant un titre `### REV-nnn`.
- Produces: `count.sh <fichier> [lists]` → effectifs par statut (`ferme`/`partiel`/`ouvert`/`observation`/`AUTRE`) + total, ou la liste d'ids par statut.

- [ ] **Step 1: Écrire le script**

```bash
mkdir -p .superpowers/sdd && cat > .superpowers/sdd/backlogA-count-etat.sh <<'EOF'
#!/bin/sh
# usage: backlogA-count-etat.sh docs/revue/2026-09-04-backlog.md [lists]
awk -v lists="$2" '
/^### REV-/{id=$2}
/^- \*\*État :?\*?\*? ?/ && id!=""{
  s=$0; sub(/^- \*\*État :?\*?\*? */,"",s); gsub(/\*/,"",s); s=tolower(s)
  if(s ~ /^partiel/) k="partiel"
  else if(s ~ /^ferm|^résolu/) k="ferme"
  else if(s ~ /^ouvert/) k="ouvert"
  else if(s ~ /^observation|^informationnel/) k="observation"
  else k="AUTRE"
  n[k]++; tot++; l[k]=l[k] (l[k]==""?"":", ") id; id=""
}
END{ if(lists!="") {for(k in l) print k": "l[k]} else {for(k in n) print k"\t"n[k]; print "total\t"tot} }' "$1" | sort
EOF
chmod +x .superpowers/sdd/backlogA-count-etat.sh
```

- [ ] **Step 2: Mesurer la baseline (avant toute édition)**

Run : `sh .superpowers/sdd/backlogA-count-etat.sh docs/revue/2026-09-04-backlog.md`
Sortie attendue (mesurée le 2026-10-03, ligne à ligne) :
```
ferme	219
observation	2
ouvert	53
partiel	19
total	293
```
Cohérence avec le sommaire actuel (« 219 fermées, 19 partiellement fermées, 55 ouvertes sur 293 ») :
55 = 53 `ouvert` + 2 `informationnel` (REV-187/188, que le sommaire comptait parmi les ouvertes).
Aucune ligne `AUTRE` ne doit apparaître ; si `AUTRE` > 0, corriger la regex avant de continuer.

- [ ] **Step 3: Vérifier que les ids ciblés par le plan sont bien `ouvert` aujourd'hui**

Run : `sh .superpowers/sdd/backlogA-count-etat.sh docs/revue/2026-09-04-backlog.md lists | grep '^ouvert' | tr ',' '\n' | grep -E 'REV-(111|116|185|186|195|196|197|198|199|239|269|271|272|273|275|290)$' | wc -l`
Sortie attendue : `16` (les 16 ids non-observation du plan A sont tous `ouvert`).

Pas de commit (script de travail).

---

### Task L0-2: REV-111 et GAP-17 (fermé par SP-62)

**Files:**
- Modify: `docs/revue/2026-09-04-backlog.md` (entrée `### REV-111`, ligne d'état ≈ l.1218)
- Modify: `docs/revue/2026-09-04-analyse-gaps.md` (ligne de la table Référentiel 2 ≈ l.285 ; liste « Confort » ≈ l.483-486)

**Interfaces:**
- Consumes: la table « ✅ Fermé » d'`analyse-gaps.md` l.120 (GAP-17 y est DÉJÀ décrit fermé par SP-62, plan `2026-09-06-gap17-nl-sql-copilote.md`) — c'est la source de vérité ; REV-111 et la section détail sont en retard (piège n°12).
- Produces: REV-111 `fermé`, GAP-17 cohérent dans les 3 endroits d'`analyse-gaps.md`.

- [ ] **Step 1: Backlog REV-111 — remplacer la ligne d'état**

Ancien texte (exact, dans l'entrée REV-111) :
```
- **État :** ouvert (à défaut d'être repris comme SP par la feuille de route révisée, cf. `docs/vision/2026-09-04-feuille-de-route-revisee.md`)
- **Renvoi :** `docs/revue/2026-09-04-analyse-gaps.md` (section correspondant à GAP-17) pour le détail complet.
```
Nouveau texte :
```
- **État :** fermé par SP-62 (plan `docs/superpowers/plans/2026-09-06-gap17-nl-sql-copilote.md`) — outils MCP `generate_sql_query`/`generate_visual_query` (`core/app/mcp/tools/query_generation.py`), copilote monté sur `SqlLabPage`/`VisualQueryWizardPage` ; le brouillon généré n'est jamais exécuté ni écrit depuis l'outil, la revue humaine reste le seul chemin d'exécution. Alignement documentaire du 2026-10-03 (l'entrée était restée `ouvert` alors que `analyse-gaps.md` la déclarait fermée).
- **Renvoi :** `docs/revue/2026-09-04-analyse-gaps.md` (table « ✅ Fermé », ligne GAP-17) pour le détail complet.
```
Comme l'ancien texte est précédé de `### REV-111`, utiliser `old_string` = les 2 lignes ci-dessus **préfixées par** la phrase unique de l'entrée : `fme.safe.com/platform/ai-assist\n` (ligne « Preuve / source » juste avant) pour garantir l'unicité.

- [ ] **Step 2: analyse-gaps — section détail GAP-17 (Référentiel 2)**

Ancien texte (début de la ligne de table, ≈ l.285) :
```
| GAP-17 | Aucune génération de requête en langage naturel avec revue humaine avant exécution (NL→SQL ou NL→CEL)
```
Nouveau texte (préfixe de statut, le reste de la ligne est conservé tel quel) :
```
| GAP-17 | **[Fermé par SP-62, cf. table « ✅ Fermé » — texte d'origine conservé ci-dessous pour l'historique]** Aucune génération de requête en langage naturel avec revue humaine avant exécution (NL→SQL ou NL→CEL)
```

- [ ] **Step 3: analyse-gaps — liste Confort du classement final**

Ancien texte (≈ l.483-486) :
```
GAP-03, GAP-04, GAP-08, GAP-10, GAP-13, GAP-15, GAP-17, GAP-18, GAP-20,
```
Nouveau texte :
```
GAP-03, GAP-04, GAP-08, GAP-10, GAP-13, GAP-15, ~~GAP-17~~ (fermé SP-62), GAP-18, GAP-20,
```

- [ ] **Step 4: Vérifier**

Run : `grep -n "GAP-17" docs/revue/2026-09-04-analyse-gaps.md | cut -c1-120` → 4 lignes minimum, aucune sans mention « fermé »/« SP-62 » hors la table « ✅ Fermé » elle-même et la mention « hors doctrine GAP-17 » du diagnostic (autre fichier).
Run : `sh .superpowers/sdd/backlogA-count-etat.sh docs/revue/2026-09-04-backlog.md | grep ferme` → `ferme	220`.

- [ ] **Step 5: Commit**

```bash
git add docs/revue/2026-09-04-backlog.md docs/revue/2026-09-04-analyse-gaps.md
git commit -m "docs(revue): REV-111 fermé par SP-62, GAP-17 aligné dans analyse-gaps

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task L0-3: REV-116 et GAP-22 (fermé), REV-187/188 reclassés observation

**Files:**
- Modify: `docs/revue/2026-09-04-backlog.md` (entrées `### REV-116` ≈ l.1253, `### REV-187`, `### REV-188`)
- Modify: `docs/revue/2026-09-04-analyse-gaps.md` (ligne GAP-22 Référentiel 2 ≈ l.290 ; table « Sérieux » ≈ l.436)

**Interfaces:**
- Consumes: `analyse-gaps.md` l.98-101 et l.122 (GAP-22 fermé 2026-09-13, plan `2026-09-06-gap22-securite-colonne.md`) ; spec GAP-22 §1.5/§4 (exclusions de périmètre) ; fermeture des bypass pipelines/exports/MCP par l'audit P15 (2026-10-02, cf. CLAUDE.md §Livré « P12–P15 ») ; REV-185/186/270 (suivis).
- Produces: REV-116 `fermé` ; REV-187/188 état `observation` (compté à part par le script) ; GAP-22 cohérent.

- [ ] **Step 1: REV-116 — remplacer la ligne d'état**

Ancien texte :
```
- **État :** ouvert (à défaut d'être repris comme SP par la feuille de route révisée, cf. `docs/vision/2026-09-04-feuille-de-route-revisee.md`)
- **Renvoi :** `docs/revue/2026-09-04-analyse-gaps.md` (section correspondant à GAP-22) pour le détail complet.
```
(préfixer l'`old_string` de la ligne unique `- **Preuve / source :** [DOC OFFICIELLE] \`metabase.com/docs/latest/permissions/row-and-column-security\`` pour l'unicité.)
Nouveau texte :
```
- **État :** fermé par GAP-22 (2026-09-13, 16 tâches, spec `docs/superpowers/specs/2026-09-06-gap22-securite-colonne-design.md`, plan `docs/superpowers/plans/2026-09-06-gap22-securite-colonne.md`) : masquage de champ sensible sur les trois mécanismes de lecture (rôle Postgres `gis_rls_masked`, exclusion de la matérialisation DuckDB, routes STAC) ; les bypass pipelines/exports/MCP ont été refermés par l'audit pré-release P15 (2026-10-02). Suivis rattachés : REV-185 (privilège `can_manage_collections`), REV-186 (DDL), REV-187/188 (observations, limites de conception assumées), REV-270. Alignement documentaire du 2026-10-03.
- **Renvoi :** `docs/revue/2026-09-04-analyse-gaps.md` (table « ✅ Fermé », ligne GAP-22) pour le détail complet.
```

- [ ] **Step 2: REV-187 — reclasser observation**

Ancien texte :
```
- **État :** informationnel, non corrigé — cohérent avec le périmètre
  explicite de GAP-22, aucune action attendue sauf décision produit future
  sur le chiffrement/filtrage à la source CDC.
```
Nouveau texte :
```
- **État :** observation (reclassé le 2026-10-03, ex-« informationnel ») — limite de conception assumée, spec GAP-22 §1.5/§4 : le masquage est un contrôle à la requête, pas à la source CDC ; aucune action attendue sauf décision produit future sur le chiffrement/filtrage à la source CDC.
```

- [ ] **Step 3: REV-188 — reclasser observation**

Ancien texte :
```
- **État :** informationnel, non corrigé — comportement voulu, pas un
  défaut ; consigné pour qu'une future revue ne le redécouvre pas comme
  une trouvaille nouvelle (piège n°12).
```
Nouveau texte :
```
- **État :** observation (reclassé le 2026-10-03, ex-« informationnel ») — comportement voulu (spec GAP-22 §4 : le nom/type d'un champ n'est jamais masqué, seule la valeur l'est), pas un défaut ; consigné pour qu'une future revue ne le redécouvre pas comme une trouvaille nouvelle (piège n°12).
```

- [ ] **Step 4: analyse-gaps — détail GAP-22 (≈ l.290) et classement (≈ l.436)**

Ancien texte (début de ligne, Référentiel 2) :
```
| GAP-22 | Aucune sécurité au niveau colonne (masquage de champ par rôle) — GeoStudio a une RLS par ligne
```
Nouveau texte :
```
| GAP-22 | **[Fermé le 2026-09-13 (plan `2026-09-06-gap22-securite-colonne.md`), bypass pipelines/exports/MCP refermés par l'audit P15 le 2026-10-02 — cf. table « ✅ Fermé » ; texte d'origine conservé pour l'historique]** Aucune sécurité au niveau colonne (masquage de champ par rôle) — GeoStudio a une RLS par ligne
```
Ancien texte (table Sérieux) :
```
| GAP-22 | 2 | Aucune sécurité au niveau colonne |
```
Nouveau texte :
```
| GAP-22 | 2 | ~~Aucune sécurité au niveau colonne~~ — fermé (2026-09-13) |
```

- [ ] **Step 5: Vérifier**

Run : `sh .superpowers/sdd/backlogA-count-etat.sh docs/revue/2026-09-04-backlog.md`
Sortie attendue : `ferme 221`, `observation 2`, `ouvert 51`, `partiel 19`, `total 293` (REV-111 puis REV-116 fermées ; 187/188 inchangées en effectif `observation` car le script les rangeait déjà ainsi — le 2e `observation` provient de la regex étendue, pas d'un changement de nombre).

- [ ] **Step 6: Commit**

```bash
git add docs/revue/2026-09-04-backlog.md docs/revue/2026-09-04-analyse-gaps.md
git commit -m "docs(revue): REV-116 fermé (GAP-22), REV-187/188 reclassés observation

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task L0-4: REV-239 et D56 (historique local relisible)

**Files:**
- Modify: `docs/revue/2026-09-04-backlog.md` (entrée `### REV-239`, ligne d'état)
- Modify: `docs/revue/2026-09-24-diagnostic-ui-ux.md` (ligne D56 du tableau ≈ l.95 ; ligne REV-239 ≈ l.291)
- Read (vérification, lecture seule): `shell/src/lib/copilotHistory.ts`, `shell/src/builder/copilot/CopilotPanel.tsx`, `shell/src/builder/copilot/CopilotChat.tsx`

**Interfaces:**
- Consumes: l'annotation du 2026-10-03 déjà dans REV-239 (aperçu couvert par la confirmation au clic P23, j11-012) ; historique par compte livré en P07 (cf. CLAUDE.md §Livré P06–P11 « historiques par compte »).
- Produces: REV-239 `fermé` ; D56 annoté dans le diagnostic ; la persistance serveur est déclarée observation (hors plan sauf demande produit).

- [ ] **Step 1: Vérifier le code avant d'écrire (piège n°12)**

Run : `grep -n "export" shell/src/lib/copilotHistory.ts | head; grep -n "copilotHistory" shell/src/builder/copilot/CopilotPanel.tsx | head -3`
Attendu : au moins un export de lecture/écriture d'historique dans `copilotHistory.ts` et au moins un import de ce module dans `CopilotPanel.tsx`. Si l'un manque : STOP, ne pas fermer REV-239, signaler à Tanguy.

- [ ] **Step 2: Backlog REV-239 — remplacer la ligne d'état**

Ancien texte :
```
- **État :** ouvert. Note 2026-10-03 : l'aperçu préalable est couvert pour les écritures par la confirmation au clic de P23 (j11-012, `shell/src/builder/copilot/CopilotChat.tsx`) ; reste la persistance/lecture de l'historique.
```
Nouveau texte :
```
- **État :** fermé (2026-10-03) pour D56 au niveau « historique local relisible » : aperçu préalable des écritures par la confirmation au clic de P23 (j11-012, `shell/src/builder/copilot/CopilotChat.tsx`) ; historique conservé et relisible côté navigateur, par compte (`shell/src/lib/copilotHistory.ts`, `shell/src/builder/copilot/CopilotPanel.tsx`). Reste une éventuelle persistance **serveur** de l'historique (partage entre appareils/sessions) : observation, à ne traiter que sur demande produit.
```

- [ ] **Step 3: diagnostic UI/UX — D56**

Ancien texte (ligne du tableau D56, fin de la cellule « constat ») :
```
mitigé par Undo/Redo (SP-19), mais hors doctrine GAP-17 | lu |
```
Nouveau texte :
```
mitigé par Undo/Redo (SP-19), mais hors doctrine GAP-17. **Mise à jour 2026-10-03 : traité** — aperçu des écritures par confirmation au clic (P23, j11-012) et historique local relisible par compte (`copilotHistory.ts`) ; persistance serveur non faite (observation, cf. REV-239) | lu |
```
Ancien texte (≈ l.291) :
```
| REV-239 | D56 | Copilote : historique non persisté, opérations sans aperçu préalable | C | 4 | M |
```
Nouveau texte :
```
| REV-239 | D56 | Copilote : historique non persisté, opérations sans aperçu préalable — fermé 2026-10-03 (historique local + confirmation au clic) | C | 4 | M |
```

- [ ] **Step 4: Commit**

```bash
git add docs/revue/2026-09-04-backlog.md docs/revue/2026-09-24-diagnostic-ui-ux.md
git commit -m "docs(revue): REV-239 fermé pour D56 (historique local relisible)

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task L0-5: Recomptage mécanique du sommaire du backlog (partie L0)

**Files:**
- Modify: `docs/revue/2026-09-04-backlog.md` (section « Répartition par statut », ≈ l.30-120 : phrase d'effectifs, historique, 3 listes d'ids)
- Read: `.superpowers/sdd/backlogA-count-etat.sh`

**Interfaces:**
- Consumes: Tasks L0-2/3/4 faites (REV-111, 116, 239 `fermé`, REV-187/188 `observation`).
- Produces: sommaire cohérent avec les lignes d'état ; la même procédure est rejouée à la Task CLOSE après les fermetures du lot L2/L3.

- [ ] **Step 1: Mesurer**

Run : `sh .superpowers/sdd/backlogA-count-etat.sh docs/revue/2026-09-04-backlog.md`
Sortie attendue à ce stade : `ferme 222`, `observation 2`, `ouvert 50`, `partiel 19`, `total 293` (219 + 111 + 116 + 239).

- [ ] **Step 2: Réécrire la phrase d'effectifs**

Ancien texte (début de la section) :
```
**219 fermées, 19 partiellement fermées, 55 ouvertes** sur 293 entrées
```
Nouveau texte :
```
**222 fermées, 19 partiellement fermées, 50 ouvertes, 2 observations** sur 293 entrées
(2026-10-03, clôture documentaire L0 du plan A : REV-111, REV-116, REV-239 fermées ; REV-187/188 reclassées `observation`, qui ne sont plus comptées parmi les ouvertes. Recompté mécaniquement par `.superpowers/sdd/backlogA-count-etat.sh` : première ligne `- **État` suivant chaque titre `### REV-nnn`.)
Avant : 219 fermées, 19 partiellement fermées, 55 ouvertes (dont les 2 informationnelles) sur 293 entrées
```
Puis laisser en dessous le paragraphe « (2026-10-03, clôture documentaire des paquets P22/… » inchangé, mais retirer sa parenthèse d'ouverture orpheline : la ligne conservée doit commencer par `(2026-10-03, clôture documentaire des paquets P22/P23/P26/P30/P32/P35/P36 :` — ne pas toucher au reste.

- [ ] **Step 3: Régénérer les 3 listes d'ids**

Run : `sh .superpowers/sdd/backlogA-count-etat.sh docs/revue/2026-09-04-backlog.md lists`
Pour chaque ligne imprimée (`ferme: …`, `partiel: …`, `ouvert: …`, `observation: …`), remplacer par Edit la liste d'ids située sous le titre correspondant :
- `### ✅ Fermé (219)` → `### ✅ Fermé (222)` + liste `ferme:` (sous le titre, une ligne).
- `### 🟡 Partiellement fermé (19)` → inchangé (liste `partiel:` identique).
- `### 🔴 Ouvert (55)` → `### 🔴 Ouvert (50)` + liste `ouvert:` ; ajouter juste après une sous-section :
  ```
  ### 👁 Observation (2)

  REV-187, REV-188 — limites de conception assumées, aucune action attendue (cf. leurs entrées).
  ```
Les 4 nombres (222+19+50+2) doivent sommer à 293.

- [ ] **Step 4: Vérifier la cohérence titre/liste**

Run :
```bash
for k in ferme partiel ouvert observation; do
  n=$(sh .superpowers/sdd/backlogA-count-etat.sh docs/revue/2026-09-04-backlog.md lists | grep "^$k:" | tr ',' '\n' | wc -l); echo "$k $n"; done
grep -n "^### ✅ Fermé\|^### 🟡\|^### 🔴\|^### 👁" docs/revue/2026-09-04-backlog.md
```
Attendu : effectifs `222 / 19 / 50 / 2` identiques aux nombres entre parenthèses des 4 titres.

- [ ] **Step 5: Commit**

```bash
git add docs/revue/2026-09-04-backlog.md
git commit -m "docs(revue): recomptage mécanique du sommaire du backlog (222/19/50/2 sur 293)

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

---

### Task L0-6: Checklist REV-269 (actions hors code — PROPOSÉE, NON EXÉCUTÉE sans demande de Tanguy)

**Files:**
- Modify (lecture seule tant que Tanguy n'a pas dit « go »): `.env.example:398` (`GEOSTUDIO_VERSION=v0.1.0`), `deploy/proxmox/ansible/group_vars/all.yml:9` (`geostudio_version: "v0.1.0"`), `deploy/oci/ansible/group_vars/all.yml:14` (`geostudio_version: "v0.1.0"`), `CHANGELOG.md` (section `## [Unreleased]`), `deploy/keycloak/README.md` (§ « Enregistrement dynamique de clients (DCR) », l.45+)
- Garde de la release : `.github/workflows/release.yml:25-29` (job `verify-tag` : `.env.example` doit valoir le tag, sinon `::error::`)

**Interfaces:**
- Consumes: décision explicite de Tanguy. Cette tâche est une **checklist de propositions** ; l'agent exécutant NE crée AUCUN tag, NE touche AUCUN réglage GitHub, NE modifie AUCUN des fichiers ci-dessus tant que Tanguy n'a pas demandé chaque point (règle CLAUDE.md : promotion vers `main` = PR `dev`→`main`, jamais de push direct).
- Produces: un message de proposition à Tanguy, et REV-269 laissé `ouvert` (ou `partiellement fermé` si Tanguy valide un sous-point).

- [ ] **Step 1: Vérifier l'état réel des chemins (lecture seule)**

Run :
```bash
grep -n '^GEOSTUDIO_VERSION=' .env.example
grep -n 'geostudio_version' deploy/proxmox/ansible/group_vars/all.yml deploy/oci/ansible/group_vars/all.yml
git tag --list 'v*'
```
Sortie attendue : `398:GEOSTUDIO_VERSION=v0.1.0` ; `9:geostudio_version: "v0.1.0"` et `14:geostudio_version: "v0.1.0"` ; tag `v0.1.0` seul. Un autre résultat = rebaser la checklist sur le réel.

- [ ] **Step 2: Présenter la checklist à Tanguy (message, aucune action)**

Texte à transmettre :
```
REV-269 — 4 actions hors code, proposées, rien n'est exécuté :
1. Protection de `main` (réglage GitHub, hors dépôt) : exiger la PR, les checks CI requis (ci.yml), pas de push direct. Commande de vérification : `gh api repos/tlenenao/geostudio/branches/main/protection` (404 = non protégée).
2. Release v0.1.1, dans CET ordre (sinon le job `verify-tag` de release.yml échoue) :
   a. `.env.example:398` → `GEOSTUDIO_VERSION=v0.1.1`
   b. `deploy/proxmox/ansible/group_vars/all.yml:9` et `deploy/oci/ansible/group_vars/all.yml:14` → `geostudio_version: "v0.1.1"`
   c. `CHANGELOG.md` : transformer `## [Unreleased]` en `## [0.1.1] - <date>` et y mentionner explicitement les images `geostudio-minio` et `geostudio-titiler` (absentes de v0.1.0), le retrait de `transform.qgis` (rupture), et les corrections de l'audit pré-release.
   d. PR `dev`→`main` (`git push origin dev` puis `gh pr create --base main --head dev`), CI verte, merge, puis seulement `git tag v0.1.1 && git push origin v0.1.1`.
3. Note de migration Keycloak : la politique « Trusted Hosts » de l'enregistrement dynamique de clients (DCR) n'est appliquée par `geostudio-realm.json` qu'à une installation NEUVE ; sur une instance existante, la vérifier à la main (Realm settings → Client registration → Client registration policies → Anonymous access policies → Trusted Hosts : hôtes autorisés `localhost`, `127.0.0.1`, `claude.ai`). À ajouter dans `CHANGELOG.md` (rubrique `### Upgrade notes` de la 0.1.1) ; `deploy/keycloak/README.md` § DCR contient déjà le détail technique.
4. Hôtes MCP autorisés = décision produit (lot L1), non traitée ici.
Je n'agis que sur ton « go » par point.
```

- [ ] **Step 3: Si (et seulement si) Tanguy dit « go » pour le point 2 ou 3 — exécution**

Pour 2a-2c : Edit des 3 fichiers + CHANGELOG avec le texte ci-dessus ; vérification `grep -n 'v0.1.1' .env.example deploy/*/ansible/group_vars/all.yml` → 3 lignes ; `uv run python scripts/check_...` n'existe pas pour cela : le test `core/tests/test_deployability.py` doit rester vert (`cd core && uv run pytest tests/test_deployability.py -q`). Commit : `docs(release): préparation de la v0.1.1 (version, changelog, note de migration Keycloak)` + `Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>`. Le tag et la protection de branche restent des actions de Tanguy ou sur demande séparée.

- [ ] **Step 4: État de REV-269 dans le backlog**

Tant que rien n'est validé : laisser `- **État :** ouvert.` et y ajouter à la fin de la ligne : ` Checklist proposée à Tanguy le 2026-10-03 (plan A, tâche L0-6) ; aucune action exécutée.` — Edit sur la ligne unique située sous `### REV-269`. Commit : `docs(revue): REV-269 — checklist proposée, non exécutée` + Co-Authored-By.

---

(Les tâches L2, L3 et la clôture de plan sont dans les autres fragments ; la tâche suivante est la clôture globale.)


## Lot L3a — Pipelines : REV-195, REV-196, REV-198, REV-199 (M1-M12)

Toutes les commandes se lancent depuis `/home/lenen/projets/geostudio` ; `core/` = `cd core`. Code, signatures et tests ci-dessous ont été **exécutés dans une copie jetable** (20 tests `test_pipeline_ops_execute.py`, 13 `test_pipeline_ops_contracts.py`, 10 blob, snapToLayer, route preview : verts ; les 69 `ERROR` de `tests/test_pipeline_*.py` hors-copie sont des tests qui exigent postgis/sidecar, pas des échecs). Écarts constatés avec le backlog (piège n°12) :

- `ops/compiler.py` n'existe pas : c'est `core/app/pipelines/compiler.py` (`_compile_snap_to_layer`, l.760-772).
- Il y a **46** op `transform` (pas 45) dans le registre brut (59 op, 57 exposées sans `CORE_PIPELINE_FILE_IO_ENABLED`) ; **toutes** ont exactement un de `compile`/`execute`, donc la règle « exactement un » est vérifiable en test de registre.
- M3 : `.env.example:383-385` (pas 332-333) ; la liste omet aussi `geostudio-minio` (9 images : core, shell, postgis, titiler, appexport-standalone, export-worker, appexport-runtime-builder, backup, minio).
- M5 : `_build-and-push.yml` « 9 images » est **correct** (ne pas toucher) ; `terrain3d/jobs.py:31` (pas 29) ; le volume `etl-scratch` existe toujours (partagé par le service `worker`).
- Aucun consommateur de `contract.engine` hors `contracts.py:143` (la validation copyleft) et les assertions `engine is None` des connecteurs ; `scripts/fme_coverage_cli.py` lit `engine` dans la matrice JSONL, pas dans le registre -> M9 est sans effet de bord.
- Le DataFrame vide de `fetchdf()` garde une colonne `geometry` en `object` : `_write_geometry_rows` l'accepte tel quel ; seul `df.assign(geometry=[])` (densify) fabriquait un `float64` -> `BinderException`.
- Ordre recommandé : exécuter L3a **avant** la tâche REV-197 (qui modifie le même `materialize_blob_connector`, lignes au-dessus de l'appel `_run_dlt_and_attach` que touche L3a-12) ; en cas de conflit, ce sont deux zones disjointes de la fonction.

Variable d'environnement pour les commandes qui importent `app.main` ou le registre : `CORE_SECRETS_MASTER_KEY="AAECAwQFBgcICQoLDA0ODxAREhMUFRYXGBkaGxwdHh8="` (valeur de test de CLAUDE.md).

---

### Task L3a-1: REV-196 — entrées dégénérées des op `execute` (NULL, vide, non-point, sans colonne `geometry`)

**Files:**
- Modify: `core/app/pipelines/ops/execute.py` (imports l.10-12 ; `_read_geometry_rows` l.22-30 ; `_execute_triangulate` l.45-58 ; `_execute_densify` l.61-72 ; `_execute_minimum_bounding_circle` l.75-85)
- Modify: `core/tests/test_pipeline_ops_execute.py` (import l.1-5 ; ajout en fin de fichier)
- Modify: `core/tests/test_pipeline_routes.py` (ajout en fin de fichier)

**Interfaces:**
- Consumes: `PipelineRuntimeError` (`app.pipelines.errors`, module feuille sans dépendance : import de module sûr, pas de cycle) ; routes `preview_pipeline_route` (`core/app/pipelines/routes.py:166-190`) qui mappe déjà `PipelineRuntimeError` -> HTTP 400 ; fixture `conn` de `test_pipeline_ops_execute.py` (table `base(id INTEGER, geometry GEOMETRY)` à 2 points) ; helpers `_make_app`, `_seed_preview_pipeline` de `test_pipeline_routes.py`.
- Produces: signatures **inchangées** `_read_geometry_rows(conn, input_view: str) -> pd.DataFrame`, `_execute_*(conn, *, input_view: str, view_name: str, params: dict) -> None` (donc `OPERATIONS`/`OP_PARAMS` intacts). Nouveau comportement : lignes `geometry IS NULL` écartées ; entrée vide -> table de sortie à 0 ligne ; polygone/ligne passé à `triangulate` -> `PipelineRuntimeError("transform.triangulate expects Point geometries, got …")` ; table sans colonne `geometry` -> `PipelineRuntimeError`.

Reproduction préalable (déjà faite en lecture, résultats réels sur `main`) : polygone/`triangulate` -> `NotImplementedError` ; 0 ligne/`triangulate` -> `IndexError` ; 0 ligne/`densify` -> `BinderException: st_geomfromwkb(DOUBLE)` ; NULL/`densify` -> `TypeError: cannot convert 'NAType' object to bytes` ; 0 ligne/`minimumBoundingCircle` -> 1 ligne polygone vide silencieuse ; NULL/`minimumBoundingCircle` et NULL/`triangulate` -> `TypeError`. `_write_geometry_rows` tolère déjà une géométrie `None` et `LINESTRING EMPTY` après `segmentize` (jumelle vérifiée : tests ci-dessous gelés, ils passent avant et après).

- [ ] **Step 1: Écrire les tests (rouges)**

Dans `core/tests/test_pipeline_ops_execute.py`, remplacer l'en-tête

```python
import duckdb
import pytest

from app.pipelines.ops.execute import _read_geometry_rows, _write_geometry_rows
```

par

```python
import duckdb
import pytest

from app.pipelines.errors import PipelineRuntimeError
from app.pipelines.ops.execute import _read_geometry_rows, _write_geometry_rows
```

puis ajouter **en fin de fichier** :

```python
def test_triangulate_on_polygon_raises_pipeline_runtime_error(conn):
    conn.execute("CREATE TABLE poly (id INTEGER, geometry GEOMETRY)")
    conn.execute("INSERT INTO poly VALUES (1, ST_GeomFromText('POLYGON ((0 0, 1 0, 1 1, 0 0))'))")
    from app.pipelines.ops.execute import _execute_triangulate

    with pytest.raises(PipelineRuntimeError, match="Point"):
        _execute_triangulate(conn, input_view="poly", view_name="out", params={})


@pytest.mark.parametrize(
    ("fn_name", "params"),
    [
        ("_execute_triangulate", {}),
        ("_execute_densify", {"maxSegmentLength": 1}),
        ("_execute_minimum_bounding_circle", {}),
    ],
)
def test_empty_input_yields_empty_output(conn, fn_name, params):
    from app.pipelines.ops import execute

    conn.execute("CREATE TABLE empty_in (id INTEGER, geometry GEOMETRY)")
    getattr(execute, fn_name)(conn, input_view="empty_in", view_name="out", params=params)
    assert conn.execute("SELECT count(*) FROM out").fetchone() == (0,)


@pytest.mark.parametrize(
    ("fn_name", "params"),
    [
        ("_execute_densify", {"maxSegmentLength": 2}),
        ("_execute_minimum_bounding_circle", {}),
        ("_execute_triangulate", {}),
    ],
)
def test_null_geometry_rows_are_dropped(conn, fn_name, params):
    from app.pipelines.ops import execute

    conn.execute("CREATE TABLE with_null (id INTEGER, geometry GEOMETRY)")
    conn.execute(
        "INSERT INTO with_null VALUES (1, NULL), (2, ST_Point(0, 0)), "
        "(3, ST_Point(4, 0)), (4, ST_Point(2, 3))"
    )
    getattr(execute, fn_name)(conn, input_view="with_null", view_name="out", params=params)
    assert conn.execute("SELECT count(*) FROM out WHERE geometry IS NULL").fetchone() == (0,)
    assert conn.execute("SELECT count(*) FROM out").fetchone()[0] >= 1


def test_densify_with_empty_linestring_does_not_crash(conn):
    # Jumelle de _write_geometry_rows : segmentize d'une géométrie vide reste écrivable.
    conn.execute("CREATE TABLE empty_line (id INTEGER, geometry GEOMETRY)")
    conn.execute("INSERT INTO empty_line VALUES (1, ST_GeomFromText('LINESTRING EMPTY'))")
    from app.pipelines.ops.execute import _execute_densify

    _execute_densify(conn, input_view="empty_line", view_name="out", params={"maxSegmentLength": 1})
    assert conn.execute("SELECT count(*) FROM out").fetchone() == (1,)


def test_write_geometry_rows_tolerates_null_geometry(conn):
    import pandas as pd
    import shapely
    import shapely.wkb

    df = pd.DataFrame({"id": [1, 2], "geometry": [None, shapely.wkb.dumps(shapely.Point(1, 1))]})
    _write_geometry_rows(conn, df, view_name="out")
    assert conn.execute("SELECT id, ST_AsText(geometry) FROM out ORDER BY id").fetchall() == [
        (1, None),
        (2, "POINT (1 1)"),
    ]


def test_read_geometry_rows_without_geometry_column_raises(conn):
    conn.execute("CREATE TABLE no_geom (id INTEGER)")
    with pytest.raises(PipelineRuntimeError, match="geometry"):
        _read_geometry_rows(conn, "no_geom")
```

Dans `core/tests/test_pipeline_routes.py`, ajouter **en fin de fichier** :

```python
def test_preview_route_maps_degenerate_op_input_to_400(monkeypatch):
    # REV-196 : une op `execute` qui reçoit une entrée inadaptée (polygone passé à
    # `transform.triangulate`) lève PipelineRuntimeError -> 400 explicite, plus de 500.
    import duckdb

    from app.pipelines.ops.execute import _execute_triangulate

    client = _make_app(monkeypatch, etl_enabled=True)
    item_id = _seed_preview_pipeline(client)

    def fake_preview_pipeline(**kwargs):
        conn = duckdb.connect(":memory:")
        conn.execute("INSTALL spatial; LOAD spatial;")
        conn.execute("CREATE TABLE poly (id INTEGER, geometry GEOMETRY)")
        conn.execute(
            "INSERT INTO poly VALUES (1, ST_GeomFromText('POLYGON ((0 0, 1 0, 1 1, 0 0))'))"
        )
        _execute_triangulate(conn, input_view="poly", view_name="out", params={})
        return []

    monkeypatch.setattr("app.pipelines.routes.preview_pipeline", fake_preview_pipeline)
    response = client.post(f"/v1/pipelines/{item_id}/preview?upTo=r1")
    assert response.status_code == 400
    assert "Point" in response.text
```

- [ ] **Step 2: Lancer les tests, vérifier l'échec**

Run: `cd core && uv run pytest tests/test_pipeline_ops_execute.py tests/test_pipeline_routes.py::test_preview_route_maps_degenerate_op_input_to_400 -v`

Attendu : FAIL de `test_triangulate_on_polygon_raises_pipeline_runtime_error` (`NotImplementedError`), des 3 cas `test_empty_input_yields_empty_output` (`IndexError` / `BinderException` / `count == 1` au lieu de 0), des 3 cas `test_null_geometry_rows_are_dropped` (`TypeError`), de `test_read_geometry_rows_without_geometry_column_raises` (`DID NOT RAISE`) et du test de route (`NotImplementedError` remonte, `TestClient` relève l'exception serveur). `test_densify_with_empty_linestring_does_not_crash` et `test_write_geometry_rows_tolerates_null_geometry` **passent déjà** (garde-fous gelés, comportement correct).

- [ ] **Step 3: Implémenter les gardes dans `execute.py`**

Dans `core/app/pipelines/ops/execute.py`, après la ligne `from shapely.geometry import GeometryCollection, MultiPoint` ajouter :

```python

from app.pipelines.errors import PipelineRuntimeError
```

Remplacer `_read_geometry_rows` par :

```python
def _read_geometry_rows(conn, input_view: str) -> pd.DataFrame:
    """Lit toutes les colonnes de `input_view`, la géométrie sérialisée en WKB (bytearray,
    consommable par shapely.wkb.loads). Les lignes à géométrie NULL sont écartées en SQL
    (REV-196) : aucune op de ce module n'a de sens sur une géométrie absente, et un NULL
    ferait lever `TypeError` à `bytes(...)`."""
    cols = [d[0] for d in conn.execute(f"SELECT * FROM {_qi(input_view)} LIMIT 0").description]
    if "geometry" not in cols:
        raise PipelineRuntimeError(f"input has no 'geometry' column (columns: {cols})")
    select_list = ", ".join(
        f"ST_AsWKB({_qi(c)}) AS {_qi(c)}" if c == "geometry" else _qi(c) for c in cols
    )
    return conn.execute(
        f"SELECT {select_list} FROM {_qi(input_view)} WHERE {_qi('geometry')} IS NOT NULL"
    ).fetchdf()
```

Remplacer les trois `_execute_*` (de `def _execute_triangulate` jusqu'à la fin du fichier) par :

```python
def _execute_triangulate(conn, *, input_view: str, view_name: str, params: dict) -> None:
    from app.pipelines.ops.schemas import TransformTriangulateParams

    TransformTriangulateParams.model_validate(params)
    df = _read_geometry_rows(conn, input_view)
    if df.empty:
        _write_geometry_rows(conn, df, view_name=view_name)
        return
    points = [shapely.wkb.loads(bytes(wkb)) for wkb in df["geometry"]]
    bad = sorted({g.geom_type for g in points if g.geom_type != "Point"})
    if bad:
        raise PipelineRuntimeError(
            f"transform.triangulate expects Point geometries, got {', '.join(bad)}"
        )
    triangles = shapely.ops.triangulate(MultiPoint([p.coords[0] for p in points]))
    other_cols = [c for c in df.columns if c != "geometry"]
    out = pd.DataFrame(
        {
            **{c: [df[c].iloc[0]] * len(triangles) for c in other_cols},
            "geometry": [shapely.wkb.dumps(t) for t in triangles],
        }
    )
    _write_geometry_rows(conn, out, view_name=view_name)


def _execute_densify(conn, *, input_view: str, view_name: str, params: dict) -> None:
    from app.pipelines.ops.schemas import TransformDensifyParams

    p = TransformDensifyParams.model_validate(params)
    df = _read_geometry_rows(conn, input_view)
    if not df.empty:  # `assign(geometry=[])` fabriquerait une colonne float64 illisible par DuckDB
        df = df.assign(
            geometry=[
                shapely.wkb.dumps(
                    shapely.segmentize(shapely.wkb.loads(bytes(g)), p.maxSegmentLength)
                )
                for g in df["geometry"]
            ]
        )
    _write_geometry_rows(conn, df, view_name=view_name)


def _execute_minimum_bounding_circle(
    conn, *, input_view: str, view_name: str, params: dict
) -> None:
    from app.pipelines.ops.schemas import TransformMinimumBoundingCircleParams

    TransformMinimumBoundingCircleParams.model_validate(params)  # forme seulement
    df = _read_geometry_rows(conn, input_view)
    if df.empty:
        _write_geometry_rows(conn, df[["geometry"]], view_name=view_name)
        return
    geoms = [shapely.wkb.loads(bytes(g)) for g in df["geometry"]]
    circle = shapely.minimum_bounding_circle(GeometryCollection(geoms))
    out = pd.DataFrame({"geometry": [shapely.wkb.dumps(circle)]})
    _write_geometry_rows(conn, out, view_name=view_name)
```

- [ ] **Step 4: Relancer, vérifier le succès**

Run: `cd core && uv run pytest tests/test_pipeline_ops_execute.py tests/test_pipeline_routes.py -v`
Attendu : tout vert (les 5 tests historiques de `test_pipeline_ops_execute.py`, dont le test de pontage inter-groupes encore valide ici, inclus).

- [ ] **Step 5: Lint et commit**

Run: `cd core && uv run ruff check app/pipelines/ops/execute.py tests/test_pipeline_ops_execute.py tests/test_pipeline_routes.py && uv run ruff format --check app/pipelines/ops/execute.py tests/test_pipeline_ops_execute.py tests/test_pipeline_routes.py` (attendu : `All checks passed!` / already formatted ; sinon `uv run ruff format <fichier>`).

```bash
git add core/app/pipelines/ops/execute.py core/tests/test_pipeline_ops_execute.py core/tests/test_pipeline_routes.py
git commit -m "$(cat <<'EOF'
fix(core): les op execute rejettent proprement NULL, vide et non-point (REV-196)

_read_geometry_rows écarte les geometry NULL et exige la colonne geometry ;
entrée vide -> sortie vide (plus de IndexError/BinderException/cercle fantôme) ;
triangulate sur non-point lève PipelineRuntimeError (400 sur l'aperçu, plus 500).

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>
EOF
)"
```

---

### Task L3a-2: REV-195 — `groupBy` optionnel sur `triangulate` et `minimumBoundingCircle`

**Files:**
- Modify: `core/app/pipelines/ops/schemas.py` (`TransformTriangulateParams` l.628-630 ; `TransformMinimumBoundingCircleParams` l.640-642 ; `Field` déjà importé l.22)
- Modify: `core/app/pipelines/ops/execute.py` (ajout de `_group_frames`/`_apply_per_group` après `_write_geometry_rows` ; réécriture de `_execute_triangulate` et `_execute_minimum_bounding_circle`)
- Modify: `core/tests/test_pipeline_ops_execute.py` (remplacer le test de pontage l.31-65 ; ajouts en fin de fichier)

**Interfaces:**
- Consumes: `PipelineRuntimeError`, `_read_geometry_rows`, `_write_geometry_rows` (Task L3a-1), pydantic `Field(default_factory=list)` (même convention que `nonNullColumns`, `schemas.py:537`).
- Produces: `TransformTriangulateParams.groupBy: list[str]` et `TransformMinimumBoundingCircleParams.groupBy: list[str]` (défaut `[]` = comportement global actuel) ; `_group_frames(df: pd.DataFrame, group_by: list[str]) -> list[pd.DataFrame]` ; `_apply_per_group(df, group_by: list[str], one, columns: list[str]) -> pd.DataFrame` (`one: Callable[[pd.DataFrame], pd.DataFrame]`). Signature d'`execute` inchangée -> `OPERATIONS`/`OP_PARAMS`/`ops_catalog()` intacts (le catalogue expose juste un champ de plus ; l'inspecteur du shell rend déjà `type: "array"`, `PipelineNodeInspector.tsx:212`). `groupBy` contenant `geometry` ou une colonne absente -> `PipelineRuntimeError`. Sémantique : `triangulate` conserve toutes les colonnes non-géométriques (valeur de la 1re ligne du groupe, comme avant) ; `minimumBoundingCircle` produit `[*groupBy, "geometry"]` (un cercle par groupe, **0 ligne** si entrée vide). Un groupe de < 3 points ne produit aucun triangle.

- [ ] **Step 1: Écrire les tests (rouges)**

Dans `core/tests/test_pipeline_ops_execute.py`, **supprimer** la fonction `test_execute_triangulate_merges_distinct_groups_into_one_global_cloud` (de son `def` jusqu'à la ligne `assert bounds[0] < 50 and bounds[1] > 50  # …`, juste avant `def test_execute_densify_adds_vertices_every_max_segment_length`) — remplacée par le test ci-dessous, qui conserve le comportement global sans `groupBy` — et ajouter **en fin de fichier** :

```python
def test_execute_triangulate_without_group_by_stays_one_global_cloud(conn):
    # Sans groupBy (défaut), l'ancien comportement global est conservé : deux nuages distincts
    # sont fusionnés en une seule triangulation (un triangle « pont » traverse le vide).
    conn.execute("CREATE TABLE pts_grouped (id INTEGER, geometry GEOMETRY)")
    conn.execute(
        "INSERT INTO pts_grouped VALUES "
        "(1, ST_Point(0, 0)), (1, ST_Point(1, 0)), (1, ST_Point(0, 1)), "
        "(2, ST_Point(100, 100)), (2, ST_Point(101, 100)), (2, ST_Point(100, 101))"
    )
    from app.pipelines.ops.execute import _execute_triangulate

    _execute_triangulate(conn, input_view="pts_grouped", view_name="out_grouped", params={})
    assert conn.execute("SELECT DISTINCT id FROM out_grouped").fetchall() == [(1,)]
    bounds = conn.execute(
        "SELECT min(ST_XMin(geometry)), max(ST_XMax(geometry)) FROM out_grouped"
    ).fetchone()
    assert bounds[0] < 50 and bounds[1] > 50


def test_triangulate_group_by_triangulates_each_group_without_bridging(conn):
    conn.execute("CREATE TABLE pts_grouped (id INTEGER, geometry GEOMETRY)")
    conn.execute(
        "INSERT INTO pts_grouped VALUES "
        "(1, ST_Point(0, 0)), (1, ST_Point(1, 0)), (1, ST_Point(0, 1)), "
        "(2, ST_Point(100, 100)), (2, ST_Point(101, 100)), (2, ST_Point(100, 101))"
    )
    from app.pipelines.ops.execute import _execute_triangulate

    _execute_triangulate(
        conn, input_view="pts_grouped", view_name="out", params={"groupBy": ["id"]}
    )
    assert conn.execute("SELECT id, count(*) FROM out GROUP BY id ORDER BY id").fetchall() == [
        (1, 1),
        (2, 1),
    ]
    spans = conn.execute(
        "SELECT id, ST_XMax(geometry) - ST_XMin(geometry) FROM out ORDER BY id"
    ).fetchall()
    assert all(span <= 1.0 for _, span in spans)  # aucun triangle ne relie les deux nuages


def test_triangulate_group_with_fewer_than_three_points_yields_no_row(conn):
    conn.execute("CREATE TABLE two (id INTEGER, geometry GEOMETRY)")
    conn.execute("INSERT INTO two VALUES (1, ST_Point(0, 0)), (1, ST_Point(1, 0))")
    from app.pipelines.ops.execute import _execute_triangulate

    _execute_triangulate(conn, input_view="two", view_name="out", params={"groupBy": ["id"]})
    assert conn.execute("SELECT count(*) FROM out").fetchone() == (0,)


def test_minimum_bounding_circle_group_by_gives_one_circle_per_group(conn):
    conn.execute("CREATE TABLE pts_grouped (id INTEGER, geometry GEOMETRY)")
    conn.execute(
        "INSERT INTO pts_grouped VALUES "
        "(1, ST_Point(0, 0)), (1, ST_Point(4, 0)), (2, ST_Point(100, 100)), (2, ST_Point(100, 102))"
    )
    from app.pipelines.ops.execute import _execute_minimum_bounding_circle

    _execute_minimum_bounding_circle(
        conn, input_view="pts_grouped", view_name="out", params={"groupBy": ["id"]}
    )
    rows = conn.execute(
        "SELECT id, ST_GeometryType(geometry), ST_XMin(geometry) FROM out ORDER BY id"
    ).fetchall()
    assert [(r[0], r[1]) for r in rows] == [(1, "POLYGON"), (2, "POLYGON")]  # id conservé
    assert rows[0][2] < 1 and rows[1][2] > 90  # chaque cercle autour de son groupe


def test_group_by_unknown_column_raises_pipeline_runtime_error(conn):
    from app.pipelines.ops.execute import _execute_minimum_bounding_circle

    with pytest.raises(PipelineRuntimeError, match="nope"):
        _execute_minimum_bounding_circle(
            conn, input_view="base", view_name="out", params={"groupBy": ["nope"]}
        )


def test_group_by_geometry_column_is_rejected(conn):
    from app.pipelines.ops.execute import _execute_triangulate

    with pytest.raises(PipelineRuntimeError, match="geometry"):
        _execute_triangulate(
            conn, input_view="base", view_name="out", params={"groupBy": ["geometry"]}
        )
```

- [ ] **Step 2: Lancer, vérifier l'échec**

Run: `cd core && uv run pytest tests/test_pipeline_ops_execute.py -v`
Attendu : FAIL de `…group_by_triangulates_each_group_without_bridging` (`groupBy` ignoré : 1 seul `id`), `…fewer_than_three_points…` (triangles produits ou `count != 0`), `…one_circle_per_group` (1 seule ligne), `…unknown_column…` et `…geometry_column_is_rejected` (`DID NOT RAISE`). `…without_group_by_stays_one_global_cloud` passe (comportement actuel).

- [ ] **Step 3: Ajouter `groupBy` aux schémas**

Dans `core/app/pipelines/ops/schemas.py`, remplacer la classe `TransformTriangulateParams` par :

```python
class TransformTriangulateParams(BaseModel):
    """Triangulation de Delaunay de la géométrie (points) en entrée — une ligne de sortie par
    triangle. Calculée en process via Shapely (BSD-3-Clause), pas en SQL.

    `groupBy` (liste de colonnes) triangule chaque groupe séparément, sans pontage entre
    groupes ; vide = un seul nuage global."""

    groupBy: list[str] = Field(default_factory=list)
```

et `TransformMinimumBoundingCircleParams` par :

```python
class TransformMinimumBoundingCircleParams(BaseModel):
    """Remplace la géométrie par le plus petit cercle qui la contient entièrement. Calculé
    en process via Shapely (agrège toutes les lignes de l'entrée en un seul cercle).

    `groupBy` (liste de colonnes) produit un cercle par groupe, les colonnes de groupe étant
    conservées ; vide = un seul cercle global."""

    groupBy: list[str] = Field(default_factory=list)
```

(`ops_catalog()` n'expose que le 1er paragraphe du docstring : la description utilisateur reste inchangée.)

- [ ] **Step 4: Implémenter le groupement dans `execute.py`**

Après `_write_geometry_rows`, insérer :

```python
def _group_frames(df: pd.DataFrame, group_by: list[str]) -> list[pd.DataFrame]:
    """Découpe `df` en un sous-DataFrame par combinaison distincte des colonnes `group_by`
    (REV-195). `group_by` vide = un seul groupe (tout `df`) — le comportement global
    historique. NaN/NULL forme son propre groupe (`dropna=False`), l'ordre d'apparition est
    conservé (`sort=False`)."""
    if not group_by:
        return [df]
    if "geometry" in group_by:
        raise PipelineRuntimeError("groupBy cannot contain the 'geometry' column")
    missing = [c for c in group_by if c not in df.columns]
    if missing:
        raise PipelineRuntimeError(f"groupBy column(s) not found in input: {missing}")
    return [frame for _, frame in df.groupby(group_by, dropna=False, sort=False)]


def _apply_per_group(df: pd.DataFrame, group_by: list[str], one, columns: list[str]):
    """Applique `one(frame) -> DataFrame` à chaque groupe de `df` et concatène. Entrée vide
    (ou aucun groupe ne produisant de ligne) -> 0 ligne, colonnes `columns` typées comme
    en entrée (REV-196 : jamais de ligne fantôme ni d'IndexError)."""
    groups = _group_frames(df, group_by)  # valide groupBy même sur entrée vide
    frames = [one(f) for f in groups] if not df.empty else []
    out = pd.concat(frames, ignore_index=True) if frames else df[columns].iloc[0:0]
    return out if not out.empty else df[columns].iloc[0:0]
```

Puis remplacer `_execute_triangulate` et `_execute_minimum_bounding_circle` (laisser `_execute_densify` tel quel) par :

```python
def _execute_triangulate(conn, *, input_view: str, view_name: str, params: dict) -> None:
    from app.pipelines.ops.schemas import TransformTriangulateParams

    p = TransformTriangulateParams.model_validate(params)
    df = _read_geometry_rows(conn, input_view)
    other_cols = [c for c in df.columns if c != "geometry"]

    def _one(frame: pd.DataFrame) -> pd.DataFrame:
        points = [shapely.wkb.loads(bytes(wkb)) for wkb in frame["geometry"]]
        bad = sorted({g.geom_type for g in points if g.geom_type != "Point"})
        if bad:
            raise PipelineRuntimeError(
                f"transform.triangulate expects Point geometries, got {', '.join(bad)}"
            )
        triangles = shapely.ops.triangulate(MultiPoint([g.coords[0] for g in points]))
        return pd.DataFrame(
            {
                **{c: [frame[c].iloc[0]] * len(triangles) for c in other_cols},
                "geometry": [shapely.wkb.dumps(t) for t in triangles],
            }
        )

    out = _apply_per_group(df, p.groupBy, _one, list(df.columns))
    _write_geometry_rows(conn, out, view_name=view_name)
```

```python
def _execute_minimum_bounding_circle(
    conn, *, input_view: str, view_name: str, params: dict
) -> None:
    from app.pipelines.ops.schemas import TransformMinimumBoundingCircleParams

    p = TransformMinimumBoundingCircleParams.model_validate(params)
    df = _read_geometry_rows(conn, input_view)
    columns = [*p.groupBy, "geometry"]

    def _one(frame: pd.DataFrame) -> pd.DataFrame:
        geoms = [shapely.wkb.loads(bytes(g)) for g in frame["geometry"]]
        circle = shapely.minimum_bounding_circle(GeometryCollection(geoms))
        return pd.DataFrame(
            [{**{c: frame[c].iloc[0] for c in p.groupBy}, "geometry": shapely.wkb.dumps(circle)}]
        )

    out = _apply_per_group(df, p.groupBy, _one, columns)
    _write_geometry_rows(conn, out, view_name=view_name)
```

Mettre à jour le docstring d'en-tête de module : pas nécessaire (le contrat `_execute_xxx` est inchangé).

- [ ] **Step 5: Relancer, vérifier le succès**

Run: `cd core && uv run pytest tests/test_pipeline_ops_execute.py tests/test_pipeline_ops_schemas.py tests/test_pipeline_ops_contracts.py tests/test_pipeline_routes.py -v`
Attendu : tout vert (20 tests dans `test_pipeline_ops_execute.py`, y compris les cas L3a-1 et `test_execute_minimum_bounding_circle` sans groupBy -> 1 ligne).

- [ ] **Step 6: Lint et commit**

Run: `cd core && uv run ruff check app/pipelines/ops tests/test_pipeline_ops_execute.py && uv run ruff format --check app/pipelines/ops tests/test_pipeline_ops_execute.py`

```bash
git add core/app/pipelines/ops/schemas.py core/app/pipelines/ops/execute.py core/tests/test_pipeline_ops_execute.py
git commit -m "$(cat <<'EOF'
feat(core): groupBy optionnel sur transform.triangulate et minimumBoundingCircle (REV-195)

_group_frames/_apply_per_group : un cercle (colonnes de groupe conservées) ou une
triangulation par groupe, sans pontage inter-groupes ; groupBy vide = comportement
global inchangé ; colonne absente ou geometry -> PipelineRuntimeError.

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>
EOF
)"
```

---

### Task L3a-3: REV-195 — matrice de couverture FME + OpenAPI/types TS

**Files:**
- Modify: `docs/revue/matrice-couverture-fme.jsonl` (3 lignes : `MinimumSpanningCircleReplacer` l.57, `TINGenerator` l.59, `SurfaceModeller` l.269 — champ `notes` uniquement)
- Regenerate: `docs/revue/matrice-couverture-fme.md` (rendu), `core/openapi.json` et `shell/src/api/generated/core-schema.d.ts` (diff **vide et légitime** attendu : les params d'op ne sont pas dans l'OpenAPI, cf. piège n°1)

**Interfaces:**
- Consumes: format JSONL (1 objet par ligne, `json.dumps(..., ensure_ascii=False)`, round-trip vérifié sur les 289 lignes), `core/scripts/fme_coverage_cli.py --write --check` (`--check` valide `geostudio_equivalent` contre `ops_catalog()`).
- Produces: lignes `coverage_status` inchangé (`implemented`), `notes` réécrites (plus de « n'a aucun équivalent par feature »).

- [ ] **Step 1: Réécrire les 3 champs `notes`**

Créer le script jetable `/tmp/claude-1000/-home-lenen-projets-geostudio/decc043c-c62f-4b63-b6c0-5bfe4af3ec35/scratchpad/update_fme_notes.py` :

```python
import json
import pathlib

PATH = pathlib.Path("docs/revue/matrice-couverture-fme.jsonl")
NOTES = {
    "MinimumSpanningCircleReplacer": (
        "Correspondance partielle : `transform.minimumBoundingCircle` (retrait QGIS, Task 26) "
        "calcule le plus petit cercle englobant via `shapely.minimum_bounding_circle`. Sans "
        "paramètre, il agrège TOUTES les lignes de l'entrée en un seul cercle (une ligne de "
        "sortie, attributs non conservés) ; avec `groupBy` (REV-195, liste de colonnes) il "
        "produit UN cercle PAR groupe de lignes en conservant les colonnes de groupe — ce qui "
        "couvre « un cercle par feature » dès qu'une colonne identifiante existe. Restent hors "
        "couverture : les attributs autres que les colonnes de groupe, et le cercle par "
        "feature sans colonne de regroupement ; le mode sortie-attributs (centre+rayon) n'a "
        "toujours pas d'équivalent."
    ),
    "TINGenerator": (
        "Même algorithme sous-jacent (triangulation de Delaunay sur un nuage de points) : "
        "`transform.triangulate` (retrait QGIS, Task 24) calcule la triangulation via "
        "`shapely.ops.triangulate`, une ligne de sortie par triangle (attributs non "
        "significatifs, valeurs de la première ligne du groupe). Sans paramètre, toutes les "
        "géométries forment un nuage global ; avec `groupBy` (REV-195, liste de colonnes) "
        "chaque groupe est triangulé séparément, sans triangle reliant deux groupes. Une "
        "entrée non ponctuelle est rejetée par une erreur explicite (REV-196). Les lignes de "
        "rupture (breaklines) de TINGenerator, qui contraignent la triangulation, n'ont "
        "toujours pas d'équivalent (Delaunay pure, sans contrainte — même réserve que sous "
        "l'ancien mapping QGIS `native:delaunaytriangulation`)."
    ),
    "SurfaceModeller": (
        "Même op que TINGenerator dans ce même fichier (`transform.triangulate`, retrait QGIS "
        "Task 24, `groupBy` depuis REV-195) — FME expose les deux comme des transformers "
        "distincts mais le même algorithme sous-jacent (Delaunay) et la même limite "
        "s'appliquent : pas de support des lignes de rupture (breaklines) qui contraignent la "
        "triangulation."
    ),
}

lines = PATH.read_text(encoding="utf-8").splitlines()
done = set()
for i, line in enumerate(lines):
    if not line.strip():
        continue
    row = json.loads(line)
    if row["fme_transformer"] in NOTES:
        row["notes"] = NOTES[row["fme_transformer"]]
        lines[i] = json.dumps(row, ensure_ascii=False)
        done.add(row["fme_transformer"])
assert done == set(NOTES), done
PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")
```

Run: `python3 /tmp/claude-1000/-home-lenen-projets-geostudio/decc043c-c62f-4b63-b6c0-5bfe4af3ec35/scratchpad/update_fme_notes.py`
Puis : `git diff --stat docs/revue/matrice-couverture-fme.jsonl` — attendu : exactement 3 lignes modifiées (3 insertions, 3 suppressions) ; `git diff docs/revue/matrice-couverture-fme.jsonl | grep '^[-+]{' | cut -c1-60` doit montrer les 3 transformers ci-dessus.

- [ ] **Step 2: Valider et régénérer le rendu markdown**

Run: `cd core && PYTHONPATH=. uv run python scripts/fme_coverage_cli.py --repo .. --write --check`
Attendu : `289 lignes — docs/revue/matrice-couverture-fme.md régénéré.` puis `289 lignes vérifiées, aucune erreur.` ; `git diff --stat docs/revue/matrice-couverture-fme.md` : 3 lignes de tableau modifiées.
Run: `cd core && uv run pytest tests/test_fme_coverage_cli.py -v` — attendu : vert.

- [ ] **Step 3: Régénérer OpenAPI + types TS (commande exacte de CLAUDE.md)**

```bash
cd core && PYTHONPATH=. \
  CORE_SECRETS_MASTER_KEY="AAECAwQFBgcICQoLDA0ODxAREhMUFRYXGBkaGxwdHh8=" \
  uv run python scripts/export_openapi.py openapi.json
cd ../shell && npm run gen:api-types
cd .. && git status --short core/openapi.json shell/src/api/generated/core-schema.d.ts
```

Attendu : **aucune sortie** de `git status` pour ces deux fichiers (les `params` de nœud de pipeline sont des `dict` libres dans l'OpenAPI). Si un diff apparaît, le relire (il doit ne concerner que `groupBy`) et l'inclure dans le commit.

- [ ] **Step 4: Commit**

```bash
git add docs/revue/matrice-couverture-fme.jsonl docs/revue/matrice-couverture-fme.md
git commit -m "$(cat <<'EOF'
docs(revue): matrice FME alignée sur groupBy de triangulate/minimumBoundingCircle (REV-195)

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>
EOF
)"
```

(ajouter `core/openapi.json shell/src/api/generated/core-schema.d.ts` au `git add` uniquement s'ils ont changé.)

---

### Task L3a-4: REV-198 — dériver `_JOIN_PARAM_MODELS` de `BINARY_OPS` et fermer le test de synchronisation

**Files:**
- Modify: `core/app/pipelines/runtime.py` (imports l.46-72 ; table `_JOIN_PARAM_MODELS` l.96-104)
- Modify: `core/tests/test_pipeline_ops_contracts.py` (ajout en fin de fichier)

**Interfaces:**
- Consumes: `BINARY_OPS: set[str]` et `OP_PARAMS: dict[str, type[BaseModel]]` (`app.pipelines.ops.contracts`) ; `_COLLECTION_PARAM_FIELD: dict[str, str]` (`app.pipelines.config_validation:26`, contient aussi reader/writer -> **pas** d'égalité stricte avec `BINARY_OPS`, l'inclusion seule est vraie).
- Produces: `runtime._JOIN_PARAM_MODELS: dict[str, type] = {op: OP_PARAMS[op] for op in BINARY_OPS}` (mêmes 7 op : join, intersection, countWithin, merge, detectChanges, mergeChildren, snapToLayer). Import de niveau module de `contracts` dans `runtime.py` vérifié sans cycle (`import app.main` OK) ; l'import local existant l.761 n'a pas à bouger.

- [ ] **Step 1: Écrire le test de fermeture**

Ajouter en fin de `core/tests/test_pipeline_ops_contracts.py` :

```python
def test_binary_ops_are_covered_by_the_parallel_tables():
    # REV-198 : runtime._JOIN_PARAM_MODELS est dérivé de BINARY_OPS ;
    # config_validation._COLLECTION_PARAM_FIELD (qui contient aussi reader/writer) doit
    # désigner `withCollectionId` pour chaque op binaire.
    from app.pipelines.config_validation import _COLLECTION_PARAM_FIELD
    from app.pipelines.ops.contracts import BINARY_OPS, OP_PARAMS
    from app.pipelines.runtime import _JOIN_PARAM_MODELS

    assert set(_JOIN_PARAM_MODELS) == BINARY_OPS
    assert all(_JOIN_PARAM_MODELS[op] is OP_PARAMS[op] for op in BINARY_OPS)
    with_collection = {op for op, f in _COLLECTION_PARAM_FIELD.items() if f == "withCollectionId"}
    assert BINARY_OPS <= with_collection
```

- [ ] **Step 2: Lancer — le test passe déjà (état actuel synchronisé), le falsifier**

Run: `cd core && CORE_SECRETS_MASTER_KEY="AAECAwQFBgcICQoLDA0ODxAREhMUFRYXGBkaGxwdHh8=" uv run pytest tests/test_pipeline_ops_contracts.py::test_binary_ops_are_covered_by_the_parallel_tables -v` — attendu : PASS (les tables sont aujourd'hui alignées ; le test ferme la classe de défaut).
Falsification (piège n°10) : retirer temporairement la ligne `"transform.snapToLayer": TransformSnapToLayerParams,` de `_JOIN_PARAM_MODELS`, relancer -> FAIL (`set(_JOIN_PARAM_MODELS) == BINARY_OPS`), puis `git checkout core/app/pipelines/runtime.py`.

- [ ] **Step 3: Dériver la table**

Dans `core/app/pipelines/runtime.py`, remplacer le bloc

```python
_JOIN_PARAM_MODELS: dict[str, type] = {
    "transform.join": TransformJoinParams,
    ...
    "transform.snapToLayer": TransformSnapToLayerParams,
}
```

par

```python
# Dérivé de BINARY_OPS (REV-198) : une op binaire ajoutée au registre est ici d'office.
_JOIN_PARAM_MODELS: dict[str, type] = {op: OP_PARAMS[op] for op in BINARY_OPS}
```

Dans les imports, ajouter juste avant `from app.pipelines.ops.schemas import (` :

```python
from app.pipelines.ops.contracts import BINARY_OPS, OP_PARAMS
```

et retirer de la liste importée depuis `app.pipelines.ops.schemas` les 7 noms devenus inutilisés (`TransformCountWithinParams`, `TransformDetectChangesParams`, `TransformIntersectionParams`, `TransformJoinParams`, `TransformMergeChildrenParams`, `TransformMergeParams`, `TransformSnapToLayerParams`) ; **conserver** `TransformAggregateParams`, `TransformDeriveParams`, `TransformFilterParams`, `TransformH3AggregateParams` (utilisés l.589-599).

- [ ] **Step 4: Relancer**

Run: `cd core && CORE_SECRETS_MASTER_KEY="AAECAwQFBgcICQoLDA0ODxAREhMUFRYXGBkaGxwdHh8=" uv run pytest tests/test_pipeline_ops_contracts.py tests/test_pipeline_runtime.py tests/test_pipeline_config_validation.py tests/test_pipeline_routes.py -v`
Attendu : vert (les tests `test_pipeline_runtime.py` qui exigent postgis sont `skip`/`ERROR` d'environnement uniquement si `CORE_TEST_DATABASE_URL` est absent — avec le conteneur `postgis-test`, tout vert).
Run: `cd core && uv run ruff check app/pipelines/runtime.py && uv run ruff format --check app/pipelines/runtime.py && uv run lint-imports` — attendu : propre.

- [ ] **Step 5: Commit**

```bash
git add core/app/pipelines/runtime.py core/tests/test_pipeline_ops_contracts.py
git commit -m "$(cat <<'EOF'
refactor(core): _JOIN_PARAM_MODELS dérivé de BINARY_OPS + test de synchronisation (REV-198)

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>
EOF
)"
```

---

### Task L3a-5: REV-199 M1/M2 — noms de tests périmés et commentaire « décision ouverte »

**Files:**
- Modify: `core/tests/test_pipeline_ops_contracts.py` (l.46 et l.163)
- Modify: `core/tests/test_pipeline_ops_schemas.py` (l.108)
- Modify: `core/tests/test_pipeline_routes.py` (l.62 ; commentaire l.76-80)

**Interfaces:** aucun changement de comportement ; seuls des noms/commentaires. Les 4 fonctions assertent en réalité 59 op (registre brut) ou 57 (route).

- [ ] **Step 1: Vérifier les cibles (avant)**

Run: `grep -rn "fifty_one\|fifty-one" core/tests/` — attendu : exactement 4 lignes (`test_pipeline_ops_contracts.py:46`, `:163`, `test_pipeline_ops_schemas.py:108`, `test_pipeline_routes.py:62`). Run: `grep -n "décision ouverte" core/tests/test_pipeline_routes.py` — attendu : l.79.

- [ ] **Step 2: Renommer (4 `def`)**

- `test_operations_registry_has_exactly_the_fifty_one_known_ops` -> `test_operations_registry_has_exactly_the_known_ops`
- `test_operations_registry_has_fifty_one_entries_after_vague_2` -> `test_operations_registry_has_59_entries`
- `test_all_fifty_one_ops_are_registered` -> `test_all_known_ops_are_registered`
- `test_get_pipelines_ops_returns_all_fifty_one` -> `test_get_pipelines_ops_returns_all_exposed_ops`

```bash
sed -i 's/test_operations_registry_has_exactly_the_fifty_one_known_ops/test_operations_registry_has_exactly_the_known_ops/; s/test_operations_registry_has_fifty_one_entries_after_vague_2/test_operations_registry_has_59_entries/' core/tests/test_pipeline_ops_contracts.py
sed -i 's/test_all_fifty_one_ops_are_registered/test_all_known_ops_are_registered/' core/tests/test_pipeline_ops_schemas.py
sed -i 's/test_get_pipelines_ops_returns_all_fifty_one/test_get_pipelines_ops_returns_all_exposed_ops/' core/tests/test_pipeline_routes.py
```

- [ ] **Step 3: Réécrire le commentaire de `test_pipeline_routes.py`**

Remplacer (Edit) ce bloc exact :

```python
    # 57 total exposées par la route. Les 9 op de retrait QGIS couvrent 10 lignes
    # FME (transform.triangulate mappe TINGenerator ET SurfaceModeller) ; Clipper
    # et Dissolver sont 2 lignes FME distinctes, sans rapport avec ce compte de 9,
    # dont la reclassification (composition d'op vs. rester qgis_frozen) reste une
    # décision ouverte de Task 27 Step 3-4, pas encore tranchée ici — cf. plan
    # Task 27.
```

par :

```python
    # 57 total exposées par la route. Les 9 op de retrait QGIS couvrent 10 lignes
    # FME (transform.triangulate mappe TINGenerator ET SurfaceModeller) ; Clipper
    # et Dissolver, 2 lignes FME distinctes sans rapport avec ce compte de 9, sont
    # couverts par composition d'op existantes (transform.intersection avec
    # outputGeometry="intersection" ; transform.aggregate + ST_Union_Agg), sans op
    # dédiée — décision tranchée en Task 27 (cf. CHANGELOG.md, section Removed).
```

- [ ] **Step 4: Vérifier (après) et lancer**

Run: `grep -rn "fifty_one\|fifty-one\|décision ouverte" core/tests/test_pipeline_*.py` — attendu : aucune sortie.
Run: `cd core && CORE_SECRETS_MASTER_KEY="AAECAwQFBgcICQoLDA0ODxAREhMUFRYXGBkaGxwdHh8=" uv run pytest tests/test_pipeline_ops_contracts.py tests/test_pipeline_ops_schemas.py tests/test_pipeline_routes.py -v` — attendu : vert, 4 noms nouveaux visibles dans la sortie. `uv run ruff check tests && uv run ruff format --check tests` propre.

- [ ] **Step 5: Commit**

```bash
git add core/tests/test_pipeline_ops_contracts.py core/tests/test_pipeline_ops_schemas.py core/tests/test_pipeline_routes.py
git commit -m "$(cat <<'EOF'
test(core): noms de tests et commentaire périmés après le retrait QGIS (REV-199 M1/M2)

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>
EOF
)"
```

---

### Task L3a-6: REV-199 M3/M4/M5 — commentaires et listes périmés (QGIS, nombre d'images)

**Files:**
- Modify: `.env.example` (l.383-385)
- Modify: `deploy/postgis/Dockerfile` (l.25-26)
- Modify: `deploy/oci/ansible/group_vars/all.yml` (l.4-6 et l.9-10)
- Modify: `deploy/oci/README.md` (l.68-69 et l.83 — jumelles, piège n°14)
- Modify: `core/app/terrain3d/jobs.py` (l.31)
- **Ne pas toucher** `.github/workflows/_build-and-push.yml:120`, `publish-edge.yml`, `release.yml` (« 9 images » correct depuis MinIO) ni `CLAUDE.md`/`README.md` « huit images » de `v0.1.0` (historique exact).

**Interfaces:** commentaires uniquement ; `geostudio_version` et `GEOSTUDIO_VERSION` (parsés par `test_deployability`) ne changent pas.

- [ ] **Step 1: Vérifier chaque cible AVANT**

```bash
grep -n "huit images\|qgis-worker" .env.example                      # l.383, l.384
grep -n "core-qgis\|run-qgis-tests" deploy/postgis/Dockerfile        # l.25, l.26
grep -n "qgis\|etl" deploy/oci/ansible/group_vars/all.yml            # l.4, l.10 (+ l.11 geostudio_core_etl_enabled, à garder)
grep -n "qgis" deploy/oci/README.md core/app/terrain3d/jobs.py
grep -c "^          - image: " .github/workflows/_build-and-push.yml   # attendu : 9
ls scripts/run-qgis-tests.sh 2>&1 | tail -1                           # attendu : No such file
grep -n "core-qgis" .github/workflows/ci.yml                          # attendu : aucune sortie
```

- [ ] **Step 2: Appliquer les réécritures (Edit)**

`.env.example` — remplacer
```
# Tag des huit images ghcr.io/tlenenao/geostudio-* à déployer (core, shell,
# postgis, backup, export-worker, qgis-worker, appexport-runtime-builder,
# appexport-standalone). `latest` suit
```
par
```
# Tag des neuf images ghcr.io/tlenenao/geostudio-* à déployer (core, shell,
# postgis, titiler, backup, export-worker, appexport-runtime-builder,
# appexport-standalone, minio). `latest` suit
```

`deploy/postgis/Dockerfile` — remplacer
```
# tout `docker run` nu de cette image (CI core/core-qgis/stac-conformance,
# release.yml test-gate + test-gate-arm64, scripts/run-qgis-tests.sh) démarre
```
par
```
# tout `docker run` nu de cette image (CI core/stac-conformance,
# release.yml test-gate + test-gate-arm64) démarre
```

`deploy/oci/ansible/group_vars/all.yml` — remplacer
```
# Jamais "etl" ici : qgis-worker (mono-arch amd64) ne doit jamais tourner sur
# cette cible, quelle que soit l'architecture réelle de l'hôte — une
# décision de déploiement, pas une détection (cf. CLAUDE.md, spec §0/§4).
```
par
```
# Profils compose optionnels à activer (export, appexport, observability) ; vide =
# pile par défaut. Le profil "etl" a disparu avec le sidecar qgis-worker (retiré).
```
et
```
# Le moteur de pipelines (reader.connector, DuckDB) est indépendant du
# sidecar QGIS ci-dessus (profil compose etl) — activable seul (Task 1).
```
par
```
# Le moteur de pipelines (reader.connector, DuckDB) s'active par ce seul flag,
# sans profil compose dédié (Task 1).
```

`deploy/oci/README.md` — remplacer
```
# geostudio_profiles (doit rester vide : qgis-worker est mono-arch amd64,
# incompatible avec cette instance arm64)
```
par
```
# geostudio_profiles (vide par défaut ; export/appexport/observability sont
# optionnels, le profil etl a disparu avec qgis-worker)
```
et la ligne 4 de la liste de vérification
```
4. Vérifier que `qgis-worker` n'apparaît **jamais** dans `docker compose ps` sur cette instance (`geostudio_profiles` vide).
```
par
```
4. Vérifier que seuls les services du compose par défaut (et des profils activés dans `geostudio_profiles`) apparaissent dans `docker compose ps` sur cette instance.
```

`core/app/terrain3d/jobs.py` — remplacer la ligne
```python
_TERRAIN3D_SCRATCH_ROOT = "/scratch"  # même volume que qgis-worker/pipelines ; monkeypatché en test
```
par
```python
# Volume nommé `etl-scratch` du service worker (docker-compose.yml) ; monkeypatché en test.
_TERRAIN3D_SCRATCH_ROOT = "/scratch"
```

- [ ] **Step 3: Vérifier APRÈS et lancer les portes concernées**

```bash
grep -rn "qgis" .env.example deploy/postgis/Dockerfile deploy/oci core/app/terrain3d/jobs.py   # attendu : aucune sortie
cd core && uv run pytest tests/test_deployability.py tests/test_terrain3d_jobs.py -v            # attendu : vert
uv run ruff check app/terrain3d/jobs.py && uv run ruff format --check app/terrain3d/jobs.py
```

- [ ] **Step 4: Commit**

```bash
git add .env.example deploy/postgis/Dockerfile deploy/oci/ansible/group_vars/all.yml deploy/oci/README.md core/app/terrain3d/jobs.py
git commit -m "$(cat <<'EOF'
chore: retire les références périmées à qgis-worker et au compte d'images (REV-199 M3/M4/M5)

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>
EOF
)"
```

---

### Task L3a-7: REV-199 M6 — supprimer les 2 scripts QGIS morts

**Files:**
- Delete: `scripts/generate_qgis_worker_allowlist.py`, `scripts/generate_qgis_algorithm_schemas.py`
- Modify: `core/app/pipelines/ops/qgis_algorithms.py` (docstring l.2-12 : mentionne le script supprimé)

**Interfaces:** `QGIS_ALGORITHMS` (`qgis_algorithms.json` + module) **conservés** (référentiel historique, importés par `fme_coverage_cli.py --check`). Le 1er script importe `ALLOWLIST_IDS` du 2e : ils partent ensemble.

- [ ] **Step 1: Prouver que rien ne les référence (hors docs historiques)**

```bash
grep -rn "generate_qgis" . --include=* 2>/dev/null | grep -v "node_modules\|\.git/\|\.claude/worktrees\|\.codegraph\|docs/superpowers/\|docs/revue/2026-09-04-backlog.md"
```
Attendu : uniquement `scripts/generate_qgis_worker_allowlist.py` (se cite lui-même), `scripts/generate_qgis_algorithm_schemas.py` (usage en docstring), `core/app/pipelines/ops/qgis_algorithms.py` (docstring). **Aucun** test, `.pre-commit-config.yaml`, workflow `.github/` ni Dockerfile : sinon STOP et traiter la référence d'abord.
Run aussi : `grep -n "qgis" .pre-commit-config.yaml .github/workflows/*.yml` — attendu : aucune sortie.

- [ ] **Step 2: Supprimer et corriger le docstring**

```bash
git rm scripts/generate_qgis_worker_allowlist.py scripts/generate_qgis_algorithm_schemas.py
```

Dans `core/app/pipelines/ops/qgis_algorithms.py`, remplacer les 3 dernières lignes du docstring
```
referait référence à ces algorithmes). Généré par
scripts/generate_qgis_algorithm_schemas.py contre l'image pinnée
qgis/qgis:release-3_34 — ne pas éditer qgis_algorithms.json à la main,
relancer le script si l'allowlist doit changer."""
```
par
```
referait référence à ces algorithmes). Généré à l'origine contre l'image pinnée
qgis/qgis:release-3_34 par un script de génération supprimé avec le sidecar
(REV-199 M6) : `qgis_algorithms.json` est désormais figé, ne pas l'éditer."""
```

- [ ] **Step 3: Vérifier**

Run: `grep -rn "generate_qgis" core scripts .github .pre-commit-config.yaml` — attendu : aucune sortie.
Run: `cd core && PYTHONPATH=. uv run python scripts/fme_coverage_cli.py --repo .. --check && uv run pytest tests/test_fme_coverage_cli.py -v && uv run ruff check app/pipelines/ops/qgis_algorithms.py` — attendu : `289 lignes vérifiées`, vert.

- [ ] **Step 4: Commit**

```bash
git add core/app/pipelines/ops/qgis_algorithms.py
git commit -m "$(cat <<'EOF'
chore: supprime les scripts de génération de l'allowlist QGIS, sidecar retiré (REV-199 M6)

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>
EOF
)"
```

---

### Task L3a-8: REV-199 M8 — section `### Added` du CHANGELOG

**Files:**
- Modify: `CHANGELOG.md` (insérer `### Added` entre `## [Unreleased]` l.8 et `### Removed` l.10 : ordre Keep a Changelog)

**Interfaces:** aucune ; comptes **relus dans le code** (Step 1) avant écriture.

- [ ] **Step 1: Relire les comptes dans le code**

```bash
cd core && CORE_SECRETS_MASTER_KEY="AAECAwQFBgcICQoLDA0ODxAREhMUFRYXGBkaGxwdHh8=" PYTHONPATH=. uv run python - <<'EOF'
from app.pipelines.ops.contracts import OPERATIONS, ops_catalog
print("registre brut", len(OPERATIONS), "| exposées", len(ops_catalog()))
print("transform", sum(1 for c in OPERATIONS.values() if c.kind == "transform"))
v1 = {"swapCoordinates","translateGeometry","scaleGeometry","rotateGeometry","createGeometry",
      "concatCoordinates","roundCoordinates","extractElevation","extractDimension","countVertices",
      "extractCoordinates","extractSrid","setSrid","reprojectAttribute","formatCoordinates"}
v2 = {"bulkRemoveAttributes","bulkRenameAttributes","scanSchema","explodeList","explodeGeometry",
      "exposeAttributes","validateAttributes","sort","detectChanges","mergeChildren","mapSchema"}
qgis = {"centroid","convexHull","simplify","boundingGeometry","snapToLayer","resolveOverlaps",
        "triangulate","densify","minimumBoundingCircle"}
readers = {"reader.connector.bigquery","reader.connector.mssql","reader.connector.oracle",
           "reader.connector.blob"}
files = {"reader.file","writer.file"}
for name, ops in (("vague1", {f"transform.{x}" for x in v1}), ("vague2", {f"transform.{x}" for x in v2}),
                  ("qgis", {f"transform.{x}" for x in qgis}), ("readers", readers), ("files", files)):
    print(name, len(ops), "tous présents :", ops <= set(OPERATIONS))
EOF
```

Attendu (état du code au 2026-10-03) : `registre brut 59 | exposées 57`, `transform 46`, `vague1 15`, `vague2 11`, `qgis 9`, `readers 4`, `files 2`, chacun « tous présents : True ». **Si un compte diffère, ajuster le texte du Step 2 avant de l'écrire** (le backlog parle de « 24 » op : chiffre non reproductible, ne pas le reprendre).

- [ ] **Step 2: Insérer la section**

Dans `CHANGELOG.md`, insérer avant la ligne `### Removed` (l.10) :

```markdown
### Added

- **39 new pipeline operations**; the exposed catalogue is now 57 operations
  (59 in the raw registry, which also holds `reader.file` and `writer.file`,
  hidden unless `CORE_PIPELINE_FILE_IO_ENABLED=true`), all executed in DuckDB
  or in-process with Shapely (BSD-3-Clause):
  - 15 geometry/coordinate/SRID transformers: `swapCoordinates`,
    `translateGeometry`, `scaleGeometry`, `rotateGeometry`, `createGeometry`,
    `concatCoordinates`, `roundCoordinates`, `extractElevation`,
    `extractDimension`, `countVertices`, `extractCoordinates`, `extractSrid`,
    `setSrid`, `reprojectAttribute`, `formatCoordinates`;
  - 11 schema/cardinality transformers: `bulkRemoveAttributes`,
    `bulkRenameAttributes`, `scanSchema`, `explodeList`, `explodeGeometry`,
    `exposeAttributes`, `validateAttributes`, `sort`, `detectChanges`,
    `mergeChildren`, `mapSchema`;
  - 4 readers: `reader.connector.bigquery`, `reader.connector.mssql`,
    `reader.connector.oracle`, `reader.connector.blob`;
  - 9 replacements for the removed QGIS engine (see *Removed* below):
    `centroid`, `convexHull`, `simplify`, `boundingGeometry`, `snapToLayer`,
    `resolveOverlaps`, `triangulate`, `densify`, `minimumBoundingCircle`.
- `reader.file` / `writer.file` (local files through DuckDB spatial), disabled
  by default and gated by `CORE_PIPELINE_FILE_IO_ENABLED`.
- Optional `groupBy` (list of column names) on `transform.triangulate` and
  `transform.minimumBoundingCircle`: one triangulation / one circle per group
  instead of a single global result; empty (default) keeps the previous
  behaviour. Degenerate inputs (NULL geometry, empty input, non-point geometry
  for `triangulate`) now fail with an explicit pipeline error (HTTP 400 on
  preview) instead of an internal error.

```

(39 = 15 + 11 + 4 + 9 ; 57 exposées = 59 brutes - `reader.file` - `writer.file`. Si le Step 1 donne d'autres comptes, adapter ces chiffres avant de committer.)

- [ ] **Step 3: Vérifier**

Run: `sed -n 8,12p CHANGELOG.md && grep -n "^### " CHANGELOG.md | head -5` — attendu : `### Added` puis `### Removed` puis `### Changed` sous `[Unreleased]`.
Run: `python3 scripts/check_claude_md_size.py CLAUDE.md .claude-md-size-threshold` — attendu : OK (CLAUDE.md non touché).

- [ ] **Step 4: Commit**

```bash
git add CHANGELOG.md
git commit -m "$(cat <<'EOF'
docs: section Added du CHANGELOG pour les op de pipeline des vagues 1 et 2 (REV-199 M8)

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>
EOF
)"
```

---

### Task L3a-9: REV-199 M9/M10 — `engine="shapely"` et garde `compile`/`execute` exclusifs

**Files:**
- Modify: `core/app/pipelines/ops/contracts.py` (`__post_init__` l.140-144 ; entrées `transform.triangulate`/`densify`/`minimumBoundingCircle` l.~573-596 : `engine="duckdb"` -> `engine="shapely"`)
- Modify: `core/tests/test_pipeline_ops_contracts.py` (ajout en fin de fichier)

**Interfaces:**
- Consumes: `OperationContract` (`@dataclass(frozen=True)`, champs `compile: Callable[..., str] | None`, `execute: Callable[..., None] | None`, `engine`, `engine_license`, `is_copyleft`) ; `OPERATIONS`.
- Produces: `__post_init__` lève `ValueError("'<op>': compile et execute sont mutuellement exclusifs")` si les deux sont renseignés. **Décision M10** (spec : « vérifier d'abord les transforms, repli *pas les deux* ») : vérifié sur le code réel, **les 46 transforms** ont exactement un des deux et aucun reader/writer n'en a ; mais les fixtures de `test_pipeline_ops_contracts.py` construisent des `kind="transform"` sans aucun des deux -> la règle « ni aucun » ne va **pas** dans `__post_init__` (elle casserait ces fixtures) mais dans un test de registre. `engine` n'est lu nulle part hors validation copyleft (grep : seul `contracts.py:143`), `shapely` n'est pas copyleft -> aucun effet de bord ; la matrice FME garde `engine: "duckdb"` (moteur du pipeline, lu par `fme_coverage_cli`).

- [ ] **Step 1: Exploration — la règle tient-elle sur le registre ?**

```bash
cd core && CORE_SECRETS_MASTER_KEY="AAECAwQFBgcICQoLDA0ODxAREhMUFRYXGBkaGxwdHh8=" PYTHONPATH=. uv run python -c "
from app.pipelines.ops.contracts import OPERATIONS
print('transform != un-seul:', [o for o,c in OPERATIONS.items() if c.kind=='transform' and (c.compile is not None)==(c.execute is not None)])
print('non-transform avec compile/execute:', [o for o,c in OPERATIONS.items() if c.kind!='transform' and (c.compile or c.execute)])
print({o: c.engine for o,c in OPERATIONS.items() if c.execute})"
```
Attendu : `[]`, `[]`, `{'transform.triangulate': 'duckdb', 'transform.densify': 'duckdb', 'transform.minimumBoundingCircle': 'duckdb'}`. Si une liste n'est pas vide, STOP : ne garder que « pas les deux ».

- [ ] **Step 2: Écrire les tests (rouges)**

Ajouter en fin de `core/tests/test_pipeline_ops_contracts.py` :

```python
def test_compile_and_execute_are_mutually_exclusive():
    with pytest.raises(ValueError, match="mutuellement exclusifs"):
        OperationContract(
            op="transform.fake-both",
            kind="transform",
            params_schema=TransformFilterParams,
            compile=lambda params, **kw: "SELECT 1",
            execute=lambda conn, **kw: None,
        )


def test_every_registered_transform_has_exactly_one_of_compile_or_execute():
    from app.pipelines.ops.contracts import OPERATIONS

    for op, contract in OPERATIONS.items():
        has_both_or_none = (contract.compile is not None) == (contract.execute is not None)
        if contract.kind == "transform":
            assert not has_both_or_none, op
        else:
            assert contract.compile is None and contract.execute is None, op


def test_python_executed_ops_declare_the_shapely_engine():
    from app.pipelines.ops.contracts import OPERATIONS

    executed = {op: c for op, c in OPERATIONS.items() if c.execute is not None}
    assert set(executed) == {
        "transform.triangulate",
        "transform.densify",
        "transform.minimumBoundingCircle",
    }
    for op, contract in executed.items():
        assert contract.engine == "shapely", op
        assert contract.engine_license == "BSD-3-Clause (Shapely)", op
        assert contract.is_copyleft is False, op
```

- [ ] **Step 3: Lancer, vérifier l'échec**

Run: `cd core && CORE_SECRETS_MASTER_KEY="AAECAwQFBgcICQoLDA0ODxAREhMUFRYXGBkaGxwdHh8=" uv run pytest tests/test_pipeline_ops_contracts.py -v`
Attendu : FAIL de `…mutually_exclusive` (`DID NOT RAISE`) et de `…declare_the_shapely_engine` (`'duckdb' == 'shapely'`) ; `…exactly_one_of_compile_or_execute` PASSE déjà (garde-fou de registre).

- [ ] **Step 4: Implémenter**

Dans `contracts.py`, étendre `__post_init__` :

```python
    def __post_init__(self) -> None:
        if self.is_copyleft and self.execution_model != "sidecar":
            raise ValueError(
                f"'{self.op}': moteur copyleft ({self.engine}) exige execution_model='sidecar'"
            )
        if self.compile is not None and self.execute is not None:
            raise ValueError(f"'{self.op}': compile et execute sont mutuellement exclusifs")
```

et, pour les 3 entrées qui portent `execute=_execute._execute_…`, remplacer `engine="duckdb",` par `engine="shapely",` (conserver `engine_license="BSD-3-Clause (Shapely)"`). Contrôle : `grep -n 'engine="shapely"' core/app/pipelines/ops/contracts.py` -> 3 lignes.

- [ ] **Step 5: Relancer + commit**

Run: `cd core && CORE_SECRETS_MASTER_KEY="AAECAwQFBgcICQoLDA0ODxAREhMUFRYXGBkaGxwdHh8=" uv run pytest tests/test_pipeline_ops_contracts.py tests/test_pipeline_ops_schemas.py tests/test_pipeline_compiler.py tests/test_fme_coverage_cli.py -v && uv run ruff check app/pipelines/ops tests/test_pipeline_ops_contracts.py && uv run ruff format --check app/pipelines/ops tests/test_pipeline_ops_contracts.py` — attendu : vert.

```bash
git add core/app/pipelines/ops/contracts.py core/tests/test_pipeline_ops_contracts.py
git commit -m "$(cat <<'EOF'
fix(core): engine=shapely pour les op Python et compile/execute exclusifs (REV-199 M9/M10)

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>
EOF
)"
```

---

### Task L3a-10: REV-199 M11 — figer le produit cartésien de `snapToLayer` (sans changer le SQL)

**Files:**
- Modify: `core/tests/test_pipeline_compiler.py` (insérer avant `def test_compile_snap_to_layer_without_join_view_raises` l.~1055)
- **Aucune modification** de `core/app/pipelines/compiler.py` (`_compile_snap_to_layer`, `FROM {input} t, {join} o`)

**Interfaces:** fixture `conn_spatial` (`test_pipeline_compiler.py:164` : `base(id, geometry)` à 2 points) ; `compile_transform_sql("transform.snapToLayer", {"tolerance": …}, input_view=…, join_view=…) -> str`.

- [ ] **Step 1: Écrire le test**

```python
def test_compile_snap_to_layer_is_a_cross_join_with_every_reference_row(conn_spatial):
    # M11 (REV-199) : fige le produit cartésien documenté en docstring seulement
    # (`FROM input t, join o`) — N lignes d'entrée x M lignes de référence = N*M lignes de
    # sortie. L'entrée secondaire doit être réduite à UNE ligne en amont (cf.
    # TransformSnapToLayerParams) ; si le SQL change un jour, ce test doit être réécrit
    # volontairement, pas contourné.
    conn_spatial.execute("CREATE TABLE ref2 (id INTEGER, geometry GEOMETRY)")
    conn_spatial.execute(
        "INSERT INTO ref2 VALUES "
        "(1, ST_GeomFromText('POINT (3.0005 45.0005)')), "
        "(2, ST_GeomFromText('POINT (9 9)'))"
    )
    sql = compile_transform_sql(
        "transform.snapToLayer", {"tolerance": 0.01}, input_view="base", join_view="ref2"
    )
    conn_spatial.execute(f"CREATE TEMP VIEW out AS {sql}")
    assert conn_spatial.execute("SELECT count(*) FROM out").fetchone() == (4,)  # 2 x 2
    assert conn_spatial.execute(
        "SELECT id, count(*) FROM out GROUP BY id ORDER BY id"
    ).fetchall() == [
        (1, 2),
        (2, 2),
    ]
```

- [ ] **Step 2: Lancer**

Run: `cd core && uv run pytest tests/test_pipeline_compiler.py -k snap_to_layer -v`
Attendu : PASS (5 tests snap) — c'est un test de caractérisation : il passe dès l'écriture. Falsification : remplacer temporairement `FROM {_qi(input_view)} t, {_qi(join_view)} o` par `FROM {_qi(input_view)} t, (SELECT * FROM {_qi(join_view)} LIMIT 1) o` dans `compiler.py` -> le test échoue (`2 != 4`), puis `git checkout core/app/pipelines/compiler.py`.

- [ ] **Step 3: Lint et commit**

Run: `cd core && uv run ruff check tests/test_pipeline_compiler.py && uv run ruff format --check tests/test_pipeline_compiler.py && git diff --stat core/app` (attendu : aucun diff sous `core/app`).

```bash
git add core/tests/test_pipeline_compiler.py
git commit -m "$(cat <<'EOF'
test(core): fige le produit cartésien de transform.snapToLayer (REV-199 M11)

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>
EOF
)"
```

---

### Task L3a-11: REV-199 M12 — `reader.connector.blob` : 0 ligne avec glob littéral = erreur explicite

**Files:**
- Modify: `core/app/pipelines/connector_runtime.py` (constante `_GLOB_WILDCARDS` avant `def materialize_blob_connector` l.~590 ; fin de la fonction l.~652-658 : appel `_run_dlt_and_attach`)
- Modify: `core/tests/test_pipeline_connector_runtime.py` (`_patch_blob_internals` l.~1004 ; ajout de 3 tests en fin de fichier)

**Interfaces:**
- Consumes: `ConnectorRuntimeError`, `_run_dlt_and_attach(conn, resource, *, node_id: str, view_name: str) -> None` (**comportement réel mesuré** : sur ressource vide, dlt ne crée pas la table `records` et `_run_dlt_and_attach` lève `ConnectorRuntimeError("reader.connector extraction failed: Catalog Error: Table with name records does not exist!…")` — message cryptique ; le cas « table présente mais vide » n'est pas observé mais gardé par un `count(*)`), `_qi` (`connector_runtime.py:187`), helpers de test `_create_secret`, `_FakeBlobResource`, `_patch_blob_internals`, fixtures `conn`/`session`/`tenant`/`user`.
- Produces: `_GLOB_WILDCARDS: frozenset[str] = frozenset("*?[")` ; `materialize_blob_connector` lève `ConnectorRuntimeError("reader.connector.blob: no row loaded from '<path>' — the path matched no file or the file is empty (check the bucket and the object key)")` quand `file_glob` n'a aucun joker **et** (table absente ou 0 ligne). Avec joker (`*.csv`) : 0 ligne reste accepté. Aucun changement de signature.
- Dépendance de coordination : la tâche REV-197 (bucketUrl) édite la partie amont de la même fonction ; ne pas réordonner le bloc ajouté ici.

- [ ] **Step 1: Écrire les tests (rouges)**

Dans `test_pipeline_connector_runtime.py`, **dans `_patch_blob_internals`**, remplacer la dernière instruction
```python
    monkeypatch.setattr(connector_runtime, "_run_dlt_and_attach", lambda *a, **k: None)
```
par (le faux dlt doit maintenant matérialiser une table non vide, sinon le nouveau garde-fou se déclenche sur les 3 tests nominaux AWS/Azure/GCS) :
```python
    monkeypatch.setattr(
        connector_runtime,
        "_run_dlt_and_attach",
        lambda c, resource, *, node_id, view_name: c.execute(
            f'CREATE TEMP TABLE "{view_name}" AS SELECT 1 AS a'
        ),
    )
```

Ajouter en fin de fichier :

```python
def _blob_secret_and_resolver(session, tenant, user):
    _create_secret(
        session,
        tenant,
        user,
        name="s3-secret",
        kind="s3_credentials",
        payload={
            "kind": "s3_credentials",
            "awsAccessKeyId": "AKIA",
            "awsSecretAccessKey": "shh",
        },
    )
    return connector_runtime.PostgresSecretResolver(session, tenant.id, user)


def test_materialize_blob_connector_literal_glob_with_zero_rows_raises(
    monkeypatch, conn, session, tenant, user
):
    resolver = _blob_secret_and_resolver(session, tenant, user)
    _patch_blob_internals(monkeypatch, {})
    monkeypatch.setattr(
        connector_runtime,
        "_run_dlt_and_attach",
        lambda c, resource, *, node_id, view_name: c.execute(
            f'CREATE TEMP TABLE "{view_name}" (a INTEGER)'
        ),
    )
    with pytest.raises(connector_runtime.ConnectorRuntimeError, match="no row loaded"):
        connector_runtime.materialize_blob_connector(
            conn,
            secret_resolver=resolver,
            node_id="b10",
            params=ReaderConnectorBlobParams(
                secretName="s3-secret", path="s3://bucket/prefix/data.csv", format="csv"
            ),
            view_name="node_b10",
        )


def test_materialize_blob_connector_literal_glob_missing_table_gets_a_clear_message(
    monkeypatch, conn, session, tenant, user
):
    resolver = _blob_secret_and_resolver(session, tenant, user)
    _patch_blob_internals(monkeypatch, {})

    def _dlt_without_table(c, resource, *, node_id, view_name):
        raise connector_runtime.ConnectorRuntimeError(
            "reader.connector extraction failed: Catalog Error: Table with name records "
            "does not exist!"
        )

    monkeypatch.setattr(connector_runtime, "_run_dlt_and_attach", _dlt_without_table)
    with pytest.raises(connector_runtime.ConnectorRuntimeError, match="no row loaded"):
        connector_runtime.materialize_blob_connector(
            conn,
            secret_resolver=resolver,
            node_id="b11",
            params=ReaderConnectorBlobParams(
                secretName="s3-secret", path="s3://bucket/data.csv", format="csv"
            ),
            view_name="node_b11",
        )


def test_materialize_blob_connector_wildcard_glob_with_zero_rows_is_accepted(
    monkeypatch, conn, session, tenant, user
):
    resolver = _blob_secret_and_resolver(session, tenant, user)
    _patch_blob_internals(monkeypatch, {})
    monkeypatch.setattr(
        connector_runtime,
        "_run_dlt_and_attach",
        lambda c, resource, *, node_id, view_name: c.execute(
            f'CREATE TEMP TABLE "{view_name}" (a INTEGER)'
        ),
    )
    connector_runtime.materialize_blob_connector(
        conn,
        secret_resolver=resolver,
        node_id="b12",
        params=ReaderConnectorBlobParams(
            secretName="s3-secret", path="s3://bucket/prefix/*.csv", format="csv"
        ),
        view_name="node_b12",
    )
    assert conn.execute('SELECT count(*) FROM "node_b12"').fetchone() == (0,)
```

- [ ] **Step 2: Lancer, vérifier l'échec**

Run: `cd core && uv run pytest tests/test_pipeline_connector_runtime.py -k blob -v`
Attendu : FAIL des 2 premiers nouveaux tests (aucune exception levée / `ConnectorRuntimeError` avec le message « Catalog Error » ne matchant pas « no row loaded ») ; `…wildcard_glob…` et les tests AWS/Azure/GCS passent. (Postgres requis pour `session`/`tenant`/`user` : `CORE_TEST_DATABASE_URL` -> `postgis-test` ; sinon ces tests sont skippés **silencieusement** — vérifier `-rs` qu'aucun n'est skippé, piège SP-43.)

- [ ] **Step 3: Implémenter**

Dans `connector_runtime.py`, juste avant `def materialize_blob_connector(` ajouter :

```python
_GLOB_WILDCARDS = frozenset("*?[")


```

et remplacer la fin de la fonction

```python
    resource.apply_hints(table_name="records", write_disposition="replace")

    _run_dlt_and_attach(conn, resource, node_id=node_id, view_name=view_name)
```

par

```python
    resource.apply_hints(table_name="records", write_disposition="replace")

    # M12 (REV-199) : un `file_glob` littéral (sans joker) vise UN fichier — 0 ligne chargée
    # signifie chemin faux ou fichier vide, pas un jeu vide légitime. Avec un joker, 0 fichier
    # apparié reste un résultat acceptable.
    literal_glob = not set(file_glob) & _GLOB_WILDCARDS
    no_row_error = ConnectorRuntimeError(
        f"reader.connector.blob: no row loaded from '{params.path}' — the path matched no "
        "file or the file is empty (check the bucket and the object key)"
    )
    try:
        _run_dlt_and_attach(conn, resource, node_id=node_id, view_name=view_name)
    except ConnectorRuntimeError as exc:
        # dlt ne crée pas la table `records` quand rien n'est extrait : sans ce rattrapage,
        # l'utilisateur lirait « Catalog Error: Table with name records does not exist ».
        if literal_glob and "does not exist" in str(exc):
            raise no_row_error from exc
        raise
    if literal_glob and conn.execute(f"SELECT count(*) FROM {_qi(view_name)}").fetchone()[0] == 0:
        raise no_row_error
```

- [ ] **Step 4: Relancer**

Run: `cd core && uv run pytest tests/test_pipeline_connector_runtime.py -v -rs` — attendu : vert, aucun skip inattendu. Run: `uv run ruff check app/pipelines/connector_runtime.py tests/test_pipeline_connector_runtime.py && uv run ruff format --check app/pipelines/connector_runtime.py tests/test_pipeline_connector_runtime.py`.

- [ ] **Step 5: Commit**

```bash
git add core/app/pipelines/connector_runtime.py core/tests/test_pipeline_connector_runtime.py
git commit -m "$(cat <<'EOF'
fix(core): reader.connector.blob lève une erreur claire si 0 ligne avec glob littéral (REV-199 M12)

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>
EOF
)"
```

---

### Task L3a-12: Backlog — clôture REV-195/196/198/199 et note M7

**Files:**
- Modify: `docs/revue/2026-09-04-backlog.md` (sections `### REV-195`, `### REV-196`, `### REV-198`, `### REV-199` : ligne `- **État :** ouvert.` ; sommaire l.113 et table l.1899-1900 : recomptés par la tâche transverse de fin de plan, **pas ici**)

**Interfaces:** format existant des entrées (`- **État :** ouvert.` -> `fermé`). M7 (commit `ced5ea2e`, message inexact) est de l'historique git non corrigeable sans réécrire l'historique : noté, pas corrigé. Les commits de cette tâche citent les hash réels (à relire par `git log --oneline -12`).

- [ ] **Step 1: Appliquer la clôture**

Créer `/tmp/claude-1000/-home-lenen-projets-geostudio/decc043c-c62f-4b63-b6c0-5bfe4af3ec35/scratchpad/close_rev_l3a.py` :

```python
import pathlib
import re

PATH = pathlib.Path("docs/revue/2026-09-04-backlog.md")
text = PATH.read_text(encoding="utf-8")
CLOSURES = {
    "REV-195": "fermé — `groupBy` optionnel sur `transform.triangulate`/`minimumBoundingCircle` "
    "(plan 2026-10-03 backlog-lots-l0-l2-l3, lot L3a) ; matrice FME alignée.",
    "REV-196": "fermé — NULL écartés, entrée vide -> 0 ligne, non-point -> `PipelineRuntimeError` "
    "(400 sur l'aperçu), colonne `geometry` exigée (plan 2026-10-03, lot L3a).",
    "REV-198": "fermé — `_JOIN_PARAM_MODELS` dérivé de `BINARY_OPS` + test de synchronisation "
    "(plan 2026-10-03, lot L3a).",
    "REV-199": "fermé (M1-M6 et M8-M12 corrigés, plan 2026-10-03 lot L3a ; M7 non corrigeable : "
    "message du commit `ced5ea2e` conservé, l'historique git n'est pas réécrit).",
}
for rev, state in CLOSURES.items():
    m = re.search(rf"^### {rev} —.*?(?=^### REV-|\Z)", text, flags=re.S | re.M)
    assert m, rev
    section = m.group(0)
    assert section.count("- **État :** ouvert.") == 1, rev
    text = text.replace(section, section.replace("- **État :** ouvert.", f"- **État :** {state}"))
PATH.write_text(text, encoding="utf-8")
```

Run: `python3 /tmp/claude-1000/-home-lenen-projets-geostudio/decc043c-c62f-4b63-b6c0-5bfe4af3ec35/scratchpad/close_rev_l3a.py && git diff --stat docs/revue/2026-09-04-backlog.md` — attendu : 4 lignes modifiées.

- [ ] **Step 2: Commit**

```bash
git add docs/revue/2026-09-04-backlog.md
git commit -m "$(cat <<'EOF'
docs(revue): clôture REV-195, REV-196, REV-198 et REV-199 (M7 non corrigeable noté)

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>
EOF
)"
```

(Le sommaire agrégé du backlog — fermées/ouvertes — est recompté mécaniquement en fin de plan par la tâche transverse, pas ici.)

---

### Task L3a-13: Portes de qualité du lot L3a

**Files:** aucun.

- [ ] **Step 1: Lint, format, typage, frontières**

```bash
cd core
uv run ruff check . && uv run ruff format --check .
uv run mypy --strict app/auth app/secrets app/analytics app/copilot app/admin_tools app/roles   # modules inchangés par L3a : doit rester vert
uv run lint-imports
```
Attendu : tout vert (`lint-imports` : contrat de couches ; `runtime.py` -> `contracts.py` et `execute.py` -> `errors.py` restent dans `app.pipelines`).

- [ ] **Step 2: Suite pipelines complète contre un vrai postgis**

```bash
cd core && CORE_TEST_DATABASE_URL="$CORE_TEST_DATABASE_URL" \
  CORE_SECRETS_MASTER_KEY="AAECAwQFBgcICQoLDA0ODxAREhMUFRYXGBkaGxwdHh8=" \
  uv run pytest tests/test_pipeline_*.py tests/test_fme_coverage_cli.py tests/test_deployability.py tests/test_terrain3d_jobs.py -rs -q
```
Attendu : 0 failed ; vérifier dans `-rs` qu'aucun test marqué postgis n'est skippé (si `CORE_TEST_DATABASE_URL` est vide : l'exporter vers le conteneur `postgis-test`, sinon les tests runtime/blob skippent silencieusement, piège SP-43). Les échecs intermittents connus (`test_features_rls.py::test_scope_preserves_original_sql_error`, `test_deployability.py::test_every_compose_substitution_is_documented`) se rejouent en isolation avant de s'en imputer un.

- [ ] **Step 3: Contrôles croisés**

```bash
cd core && PYTHONPATH=. uv run python scripts/fme_coverage_cli.py --repo .. --check      # 289 lignes vérifiées, aucune erreur
cd .. && git status --short | grep -v "^?? .codegraph" ; git log --oneline -13           # 12 commits L3a, arbre propre
grep -rn "fifty_one\|generate_qgis\|qgis-worker" core/tests/test_pipeline_*.py .env.example deploy/postgis deploy/oci scripts 2>/dev/null   # aucune sortie
```

- [ ] **Step 4: Aucun commit** (porte de contrôle). Si un correctif est nécessaire, le committer avec le préfixe de la tâche fautive (`fix(core): …`) et relancer les Steps 1-3.

## Lot L3b — REV-275 (c)(d)(e) : annulation sans course, mem_limit du worker, limiteur `share-link`

Périmètre : (c) `mark_running` conditionnel + `cancel` idempotent, (d) `mem_limit` du service `worker`,
(e) groupe de limiteur `share-link`. (a)(b) (rejeu stack réelle, bascule `bug(`→`test(`) restent au lot L6.

Constats vérifiés dans le code (2026-10-03) :
- Appelants de `pipelines_repo.mark_running` : `PostgresRunTracker.mark_running` (`core/app/pipelines/jobs.py:181-183`)
  et tests (`test_pipeline_repository.py:153,174,184,373,391,428`, `test_pipeline_routes.py:747`, `test_pipeline_jobs.py:305` monkeypatch).
  Implémentations de `RunTracker` : `PostgresRunTracker` et `InMemoryRunTracker` (`core/app/pipelines/sidecar/tracker.py:56`), appelé par
  `core/app/pipelines/sidecar/runner.py:34`. Aucun autre fake (`grep -rn "RunTracker\|mark_running"` hors modules ingestion/export/harvest/appexport,
  qui ont leur propre `mark_running` hors périmètre). Pas de test de seam dédié « Protocol » : les tests de seam sont
  `core/tests/test_pipeline_run_tracker.py` (Postgres, sqlite mémoire) et `core/tests/test_pipeline_sidecar_tracker.py`.
- Conséquence assumée : aujourd'hui `mark_running` ressuscite aussi un run clos par `reclaim_stuck_runs` (`failed`) ; avec
  `WHERE status IN ('queued','pending')` un job tardif sur un run déjà réclamé sort sans exécuter (le balayage cron a déjà
  redéféré un run neuf). Le test `test_a_reclaimed_run_that_really_finishes_loses_its_stale_error` (dernier bloc) doit changer en conséquence (Task L3b-1).
- La garde `if run.status == "cancelled": return` de `run_pipeline_task` (`jobs.py:219`) reste (sortie rapide) ; elle ne couvre pas la
  fenêtre entre `get_run` et `mark_running`, que ferme le `UPDATE` conditionnel.

### Task L3b-1: `mark_running` conditionnel (dépôt)

**Files:**
- Modify: `core/app/pipelines/repository.py:103-113` (`mark_running`) ; vérifier que `update` est déjà importé (il l'est : `reclaim_stuck_runs` l.180)
- Modify: `core/tests/test_pipeline_repository.py` (ajout d'un test ; adaptation de `test_a_reclaimed_run_that_really_finishes_loses_its_stale_error`, l.~182-186)

**Interfaces:**
- Consumes: `PipelineRun`, `_now()`, `update` (déjà dans le module).
- Produces: `def mark_running(session: Session, *, run_id: str) -> bool` — `True` si la transition `queued|pending → running` a eu lieu, `False` sinon (run inconnu, `cancelled`, `cancel_requested`, terminé).

- [ ] **Step 1: Écrire les tests échouants** — ajouter à `core/tests/test_pipeline_repository.py` (après `test_mark_running_then_succeeded`) :

```python
def test_mark_running_returns_true_from_queued():
    Session = _make_session()
    with Session() as s:
        tenant = get_or_create_default_tenant(s)
        item_id = _make_pipeline_item(s, tenant_id=tenant.id)
        s.commit()
        run = repo.create_run(s, tenant_id=tenant.id, pipeline_item_id=item_id)
        s.commit()
        assert repo.mark_running(s, run_id=run.id) is True


def test_mark_running_does_not_overwrite_a_cancelled_run():
    # REV-275 (c) : course request_cancel (queued -> cancelled) puis mark_running du worker.
    Session = _make_session()
    with Session() as s:
        tenant = get_or_create_default_tenant(s)
        item_id = _make_pipeline_item(s, tenant_id=tenant.id)
        s.commit()
        run = repo.create_run(s, tenant_id=tenant.id, pipeline_item_id=item_id)
        s.commit()
        assert repo.request_cancel(s, run) == "cancelled"
        s.commit()
        assert repo.mark_running(s, run_id=run.id) is False
        s.commit()
        s.expire_all()
        fetched = repo.get_run(s, tenant_id=tenant.id, run_id=run.id)
        assert fetched.status == "cancelled"
        assert fetched.started_at is None


def test_mark_running_refuses_cancel_requested_and_unknown_run():
    Session = _make_session()
    with Session() as s:
        tenant = get_or_create_default_tenant(s)
        item_id = _make_pipeline_item(s, tenant_id=tenant.id)
        s.commit()
        run = repo.create_run(s, tenant_id=tenant.id, pipeline_item_id=item_id)
        s.commit()
        assert repo.mark_running(s, run_id=run.id) is True
        repo.request_cancel(s, run)  # running -> cancel_requested
        s.commit()
        assert repo.mark_running(s, run_id=run.id) is False
        assert repo.mark_running(s, run_id="does-not-exist") is False
```

Dans `test_a_reclaimed_run_that_really_finishes_loses_its_stale_error`, remplacer le dernier bloc (de `repo.mark_running(s, run_id=run.id)` à l'assertion `("running", None, None)`) par :

```python
        # REV-275 (c) : un run terminé n'est plus jamais ressuscité par un
        # mark_running tardif (le balayage cron a déjà redéféré un run neuf).
        assert repo.mark_running(s, run_id=run.id) is False
        s.commit()
        s.expire_all()
        fetched = repo.get_run(s, tenant_id=tenant.id, run_id=run.id)
        assert (fetched.status, fetched.error) == ("succeeded", None)
```

- [ ] **Step 2: Constater l'échec**
`cd core && uv run pytest tests/test_pipeline_repository.py -k "mark_running or reclaimed" -v`
Attendu : `test_mark_running_returns_true_from_queued` échoue (`None is True`), `…does_not_overwrite_a_cancelled_run` échoue (`None is False`), idem le 3e et le test « reclaimed » modifié.

- [ ] **Step 3: Implémenter** — remplacer `mark_running` (`repository.py:103-113`) par :

```python
def mark_running(session: Session, *, run_id: str) -> bool:
    """REV-275 (c) : transition conditionnelle `queued|pending -> running`
    (UPDATE ... WHERE status IN ...). Retourne False si le run n'est plus
    prenable — annulé entre-temps par `request_cancel`, déjà terminé, réclamé
    par `reclaim_stuck_runs`, ou inconnu : l'appelant sort alors sans
    exécuter. Remplace l'ancien écrasement inconditionnel (un `cancelled`
    repassait `running`)."""
    result = session.execute(
        update(PipelineRun)
        .where(PipelineRun.id == run_id, PipelineRun.status.in_(("queued", "pending")))
        .values(status="running", started_at=_now(), finished_at=None, error=None)
    )
    session.flush()
    return bool(result.rowcount)  # type: ignore[attr-defined]
```

- [ ] **Step 4: Constater le succès**
`cd core && uv run pytest tests/test_pipeline_repository.py -v`
Attendu : tout vert (dont `test_mark_running_then_succeeded`, `test_mark_running_sets_…` existants : leurs `repo.mark_running(...)` ignorent le retour).

- [ ] **Step 5: Commit**
```bash
git add core/app/pipelines/repository.py core/tests/test_pipeline_repository.py
git commit -m "fix(core): mark_running conditionnel au statut, un run annulé n'est plus écrasé (REV-275 c)

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

### Task L3b-2: Protocol `RunTracker`, implémentations et sortie sans exécution

**Files:**
- Modify: `core/app/pipelines/jobs.py:153` (Protocol), `:181-183` (`PostgresRunTracker.mark_running`), `:235` (appel dans `run_pipeline_task`)
- Modify: `core/app/pipelines/sidecar/tracker.py:56-62` (`InMemoryRunTracker.mark_running`) et `RunRegistry._update` (l.~42-47)
- Modify: `core/app/pipelines/sidecar/runner.py:34` (`_execute`)
- Modify: `core/tests/test_pipeline_run_tracker.py` (l.41-52 et l.80-88), `core/tests/test_pipeline_sidecar_tracker.py` (ajout), `core/tests/test_pipeline_jobs.py` (ajout, fixture `env` postgis)

**Interfaces:**
- Consumes: `pipelines_repo.mark_running -> bool` (Task L3b-1).
- Produces: `RunTracker.mark_running(self) -> bool` ; `PostgresRunTracker.mark_running -> bool` ; `InMemoryRunTracker.mark_running -> bool` (True seulement depuis `queued`) ; `RunRegistry._update_if_status(item_id, run_id, expected: str, **fields) -> bool`.

- [ ] **Step 1: Écrire les tests échouants**

Dans `core/tests/test_pipeline_run_tracker.py`, modifier `test_postgres_run_tracker_mark_running_sets_status_and_started_at` : remplacer `tracker.mark_running()` par `assert tracker.mark_running() is True`. Dans `test_postgres_run_tracker_mark_running_on_unknown_run_is_a_noop`, remplacer `tracker.mark_running()  # ne doit lever aucune exception` par `assert tracker.mark_running() is False  # inconnu : ne lève pas, refuse`. Ajouter :

```python
def test_postgres_run_tracker_mark_running_refuses_a_cancelled_run():
    # REV-275 (c) : le seam respecte la nouvelle sémantique conditionnelle.
    factory = _session_factory()
    tenant_id, run_id = _seed_run(factory)
    tracker = pipeline_jobs.PostgresRunTracker(factory, run_id=run_id, tenant_id=tenant_id)
    with factory() as session:
        run = pipelines_repo.get_run(session, tenant_id=tenant_id, run_id=run_id)
        pipelines_repo.request_cancel(session, run)
        session.commit()

    assert tracker.mark_running() is False

    with factory() as session:
        run = pipelines_repo.get_run(session, tenant_id=tenant_id, run_id=run_id)
        assert run.status == "cancelled"
```

Dans `core/tests/test_pipeline_sidecar_tracker.py`, ajouter :

```python
def test_tracker_mark_running_only_from_queued():
    registry = RunRegistry()
    run_id = registry.create("item-1")
    tracker = registry.tracker_for("item-1", run_id)
    assert tracker.mark_running() is True
    tracker.mark_cancelled()
    assert tracker.mark_running() is False
    assert registry.list("item-1", limit=10, offset=0)[0]["status"] == "cancelled"


def test_tracker_mark_running_on_unknown_run_returns_false():
    registry = RunRegistry()
    assert registry.tracker_for("item-1", "nope").mark_running() is False
```

Dans `core/tests/test_pipeline_jobs.py`, ajouter après `test_run_pipeline_task_marks_cancel_requested_run_cancelled` (fixture `env` postgis existante) :

```python
def test_run_pipeline_task_does_not_execute_a_run_cancelled_after_get_run(env, monkeypatch):
    # REV-275 (c) : annulation arrivant entre get_run (statut lu « queued ») et
    # mark_running — la garde `run.status == "cancelled"` ne la voit pas ; seul
    # le UPDATE conditionnel la ferme. Le run reste « cancelled », rien ne s'exécute.
    app, Session, tenant, user, item_id = env
    with Session() as s:
        run = pipelines_repo.create_run(s, tenant_id=tenant.id, pipeline_item_id=item_id)
        s.commit()
        run_id = run.id

    real_get_run = pipelines_repo.get_run
    calls = {"n": 0}

    def _get_run_then_cancel(session, *, tenant_id, run_id):
        run = real_get_run(session, tenant_id=tenant_id, run_id=run_id)
        calls["n"] += 1
        if calls["n"] == 1:  # lecture initiale de run_pipeline_task
            with Session() as other:
                fresh = real_get_run(other, tenant_id=tenant_id, run_id=run_id)
                pipelines_repo.request_cancel(other, fresh)
                other.commit()
        return run  # instantané périmé : status == "queued"

    def _must_not_run(*args, **kwargs):
        raise AssertionError("run_pipeline ne doit pas être appelé")

    monkeypatch.setattr(pipelines_repo, "get_run", _get_run_then_cancel)
    monkeypatch.setattr(pipeline_jobs, "run_pipeline", _must_not_run)

    pipeline_jobs.run_pipeline_task(run_id=run_id, tenant_id=tenant.id)

    monkeypatch.setattr(pipelines_repo, "get_run", real_get_run)
    with Session() as s:
        fetched = pipelines_repo.get_run(s, tenant_id=tenant.id, run_id=run_id)
        assert fetched.status == "cancelled"
        assert fetched.started_at is None
```

Dans `core/tests/test_pipeline_jobs.py:305`, `_boom` n'est pas modifié (il lève avant tout retour).

- [ ] **Step 2: Constater l'échec**
`cd core && uv run pytest tests/test_pipeline_run_tracker.py tests/test_pipeline_sidecar_tracker.py -v`
puis (postgis requis, `CORE_TEST_DATABASE_URL` posé) `cd core && uv run pytest tests/test_pipeline_jobs.py::test_run_pipeline_task_does_not_execute_a_run_cancelled_after_get_run -v`
Attendu : `mark_running()` renvoie `None` (`assert None is True` / `is False`) ; le test jobs échoue par `AssertionError: run_pipeline ne doit pas être appelé` (le run est écrasé en `running`).

- [ ] **Step 3: Implémenter**

`core/app/pipelines/jobs.py` — Protocol (l.153) :
```python
    def mark_running(self) -> bool:
        """True si le run a été pris en charge (queued -> running) ; False s'il
        n'est plus prenable (annulé, terminé, inconnu) : l'appelant ne doit
        alors rien exécuter (REV-275 c)."""
        ...
```
`PostgresRunTracker.mark_running` (l.181) :
```python
    def mark_running(self) -> bool:
        with request_scoped_session(self._session_factory) as session:
            return pipelines_repo.mark_running(session, run_id=self._run_id)
```
`run_pipeline_task` (l.235) : remplacer `tracker.mark_running()` par
```python
        if not tracker.mark_running():  # annulé entre get_run et ici (REV-275 c) : rien à exécuter
            return
```
(`item_id` reste `None` sur cette sortie : pas de notification, cohérent avec la garde `cancelled` existante, qui sort aussi sans notifier.)

`core/app/pipelines/sidecar/tracker.py` — dans `RunRegistry`, ajouter après `_update` :
```python
    def _update_if_status(
        self, item_id: str, run_id: str, expected: str, **fields: object
    ) -> bool:
        with self._lock:
            for record in self._records.get(item_id, []):
                if record["id"] == run_id:
                    if record["status"] != expected:
                        return False
                    record.update(fields)
                    return True
        return False
```
et remplacer `InMemoryRunTracker.mark_running` :
```python
    def mark_running(self) -> bool:
        return self._registry._update_if_status(
            self._item_id,
            self._run_id,
            "queued",
            status="running",
            startedAt=datetime.now(UTC).isoformat(),
        )
```
`core/app/pipelines/sidecar/runner.py:34` : remplacer `tracker.mark_running()` par
```python
    if not tracker.mark_running():
        return
```

- [ ] **Step 4: Constater le succès**
`cd core && uv run pytest tests/test_pipeline_run_tracker.py tests/test_pipeline_sidecar_tracker.py tests/test_pipeline_jobs.py tests/test_pipeline_repository.py -v`
Attendu : tout vert (dont `test_early_failure_before_item_id_bound_does_not_crash` : `_boom` lève toujours avant `item_id`). Lancer aussi les tests du sidecar : `cd core && uv run pytest tests -k "sidecar" -v`.

- [ ] **Step 5: Commit**
```bash
git add core/app/pipelines/jobs.py core/app/pipelines/sidecar/tracker.py core/app/pipelines/sidecar/runner.py core/tests/test_pipeline_run_tracker.py core/tests/test_pipeline_sidecar_tracker.py core/tests/test_pipeline_jobs.py
git commit -m "fix(core): RunTracker.mark_running retourne un bool, le run annulé n'est pas exécuté (REV-275 c)

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

### Task L3b-3: `cancel` idempotent (route)

**Files:**
- Modify: `core/app/pipelines/routes.py:130-132` (`cancel_pipeline_run_route`)
- Modify: `core/tests/test_pipeline_routes.py:~754-757` (`test_cancel_run_route_queued_then_conflict_when_terminal`)

**Interfaces:**
- Consumes: `pipelines_repo.get_run`, `_run_status`.
- Produces: `POST /v1/pipelines/{item_id}/runs/{run_id}/cancel` → 200 + `RunStatus` inchangé (sans nouvel audit) si le run est déjà `cancel_requested`/`cancelled` ; 409 inchangé pour `succeeded`/`failed`. Aucun changement de schéma OpenAPI.

- [ ] **Step 1: Écrire le test échouant** — dans `test_cancel_run_route_queued_then_conflict_when_terminal`, remplacer la ligne
`assert client.post(f"/v1/pipelines/{item_id}/runs/{queued_id}/cancel").status_code == 409`
par :
```python
    # REV-275 (c) : un 2e cancel sur cancelled / cancel_requested est idempotent.
    again = client.post(f"/v1/pipelines/{item_id}/runs/{queued_id}/cancel")
    assert again.status_code == 200 and again.json()["status"] == "cancelled"
    again = client.post(f"/v1/pipelines/{item_id}/runs/{running_id}/cancel")
    assert again.status_code == 200 and again.json()["status"] == "cancel_requested"
    # Un run réellement terminé reste en 409.
    with Session() as s:
        pipelines_repo.mark_succeeded(s, run_id=queued_id, node_stats={})
        s.commit()
    assert client.post(f"/v1/pipelines/{item_id}/runs/{queued_id}/cancel").status_code == 409
```
(`mark_succeeded` écrase un `cancelled` : c'est précisément pour obtenir un état terminal « succeeded » ; la fonction n'est pas conditionnelle.)

- [ ] **Step 2: Constater l'échec**
`cd core && uv run pytest tests/test_pipeline_routes.py::test_cancel_run_route_queued_then_conflict_when_terminal -v`
Attendu : `assert 409 == 200` sur le 2e cancel.

- [ ] **Step 3: Implémenter** — dans `routes.py`, remplacer le bloc
```python
    if run.status not in ("queued", "running"):
        raise HTTPException(status_code=409, detail=f"run is {run.status}, cannot be cancelled")
```
par :
```python
    if run.status in ("cancel_requested", "cancelled"):
        return _run_status(run)  # idempotent (REV-275 c) : déjà demandé, pas de nouvel audit
    if run.status not in ("queued", "running"):
        raise HTTPException(status_code=409, detail=f"run is {run.status}, cannot be cancelled")
```

- [ ] **Step 4: Constater le succès**
`cd core && uv run pytest tests/test_pipeline_routes.py -k cancel -v`
Attendu : vert.

- [ ] **Step 5: Commit**
```bash
git add core/app/pipelines/routes.py core/tests/test_pipeline_routes.py
git commit -m "fix(core): cancel d'un run déjà annulé ou en cours d'annulation répond 200 (REV-275 c)

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

Note à porter dans le commit/historique : l'annulation d'un run `running` n'est observée qu'entre deux lots par
`writer.collection`/`writer.dataset` ; `writer.export`/`writer.file` restent non interruptibles (documenté, pas de code).

### Task L3b-4: `mem_limit` du service `worker`

**Files:**
- Modify: `docker-compose.yml` (service `worker`, juste après `build: ./core`, ~l.476)
- Modify: `.env.example` (après `CORE_WORKER_CONCURRENCY=4`, l.164)
- Modify: `core/tests/test_deployability.py` (ajout d'un test après `test_core_env_default_cannot_silently_satisfy_the_mock_mode_guard`, l.~715)

**Interfaces:**
- Consumes: `services(BASE)`, `_resolve_effective_value(raw, var)` (valeur résolue, piège n°2), `documented_env_vars()`, `compose_substitutions()`.
- Produces: variable `WORKER_MEM_LIMIT` (défaut `2g`), substituée par le compose, documentée (la règle `test_every_compose_substitution_is_documented` et son sens inverse restent vertes car la ligne `.env.example` est active ET substituée).

- [ ] **Step 1: Écrire le test échouant** — dans `core/tests/test_deployability.py` :

```python
def test_worker_has_a_resolved_memory_limit():
    """REV-275 (d) : borner la mémoire du PROCESS worker (t03b-008 ne borne que
    l'écrivain). Vérifie la valeur RÉSOLUE sans `.env` (piège n°2 : une
    substitution déclarée mais jamais appliquée ne prouve rien) ET que le nom
    est documenté pour l'opérateur."""
    raw = services(BASE)["worker"].get("mem_limit")
    assert raw is not None, "service `worker` sans mem_limit"
    assert _resolve_effective_value(str(raw), "WORKER_MEM_LIMIT") == "2g"
    assert "WORKER_MEM_LIMIT" in documented_env_vars(include_commented=False)
```

- [ ] **Step 2: Constater l'échec**
`cd core && uv run pytest tests/test_deployability.py::test_worker_has_a_resolved_memory_limit -v`
Attendu : `AssertionError: service worker sans mem_limit`.

- [ ] **Step 3: Implémenter**
`docker-compose.yml`, service `worker` : après la ligne `    build: ./core` (celle qui précède le commentaire « `python -m procrastinate` »), insérer :
```yaml
    # REV-275 (d) : borne mémoire du process (DuckDB, pandas, geopandas des
    # runs de pipeline) — sans elle un run lourd peut faire OOM-killer l'hôte.
    # À dimensionner avec CORE_WORKER_CONCURRENCY (~1 job lourd par unité).
    mem_limit: ${WORKER_MEM_LIMIT:-2g}
```
`.env.example`, après `CORE_WORKER_CONCURRENCY=4` :
```
# Plafond mémoire du conteneur worker (compose `mem_limit`). Défaut 2g ; à
# relever avec CORE_WORKER_CONCURRENCY ou pour des pipelines volumineux.
WORKER_MEM_LIMIT=2g
```
Vérifier la résolution compose : `docker compose config | grep -A3 "worker:" | head` n'est pas nécessaire ; le test lit le YAML. Si Docker disponible : `docker compose config --format json | python3 -c "import json,sys; print(json.load(sys.stdin)['services']['worker']['mem_limit'])"` → `2147483648`.

- [ ] **Step 4: Constater le succès**
`cd core && uv run pytest tests/test_deployability.py -v`
Attendu : tout vert (dont `test_every_compose_substitution_is_documented` et `test_every_documented_env_var_is_wired_or_declared_inert`).

- [ ] **Step 5: Commit**
```bash
git add docker-compose.yml .env.example core/tests/test_deployability.py
git commit -m "feat(deploy): mem_limit du service worker, WORKER_MEM_LIMIT documenté (REV-275 d)

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

### Task L3b-5: groupe de limiteur `share-link` (clé IP seule)

**Files:**
- Modify: `core/app/ratelimit/limiter.py` (regex l.~50, `_BUDGETS` l.~58-66, `caller_key` l.~82-86, `route_group` l.~104-106)
- Modify: `core/tests/test_ratelimit.py` (ajouts en fin de fichier)

**Interfaces:**
- Consumes: `RateLimiter.allow(key, group)`, middleware `rate_limit_guard` (`core/app/main.py:312-334`, inchangé : il passe déjà `group`, `path`).
- Produces: `route_group("/v1/share-links/<token>", "GET", …) == "share-link"` ; budget `"share-link": 60` / 60 s ; `caller_key(<auth>, host, "share-link", path) == f"share:{host or 'unknown'}"` (ni jeton de lien ni `Authorization`, ni chemin dans la clé).

Jumelles auditées : `GET /v1/share-links/{token}` est la seule route du cœur dont le jeton figure dans le chemin
(`/embed/:token` est une route shell qui appelle précisément celle-ci). `POST /v1/items/{id}/share-links` (création) et
`DELETE …/share-links/{id}` sont authentifiées (clé `Authorization`), hors périmètre. L'usage d'un jeton de lien en
en-tête/paramètre sur les routes de lecture (`configs/guest_access.py`) passe par `Authorization`/requête déjà authentifiante côté clé et n'est pas ajouté.

NOTE de déploiement (aucun code) : `app.add_middleware(ProxyHeadersMiddleware, trusted_hosts="*")` (`core/app/main.py:529`)
rend `X-Forwarded-For` — donc la clé IP de ce groupe, comme celle de `webhook-trigger` et des anonymes — falsifiable par tout
client pouvant atteindre `core` sans passer par Traefik. Le restreindre au réseau Traefik (`trusted_hosts=<CIDR de gis-net>`)
est une décision de déploiement, reportée au lot L1 ; ce plan ne modifie pas ce réglage.

- [ ] **Step 1: Écrire les tests échouants** — ajouter à `core/tests/test_ratelimit.py` :

```python
def test_route_group_covers_share_link_resolution():
    # REV-275 (e) : route publique à jeton dans le chemin, jusque-là hors limiteur.
    assert route_group("/v1/share-links/abc.def", "GET", _EXPORT_PATH_RE) == "share-link"
    assert route_group("/v1/items/i1/share-links", "GET", _EXPORT_PATH_RE) is None
    assert route_group("/v1/share-links/abc.def", "POST", _EXPORT_PATH_RE) is None


def test_share_link_key_ignores_token_and_authorization():
    a = caller_key("Bearer a", "1.2.3.4", "share-link", "/v1/share-links/tok1")
    assert a == caller_key(None, "1.2.3.4", "share-link", "/v1/share-links/tok2")
    assert a == "share:1.2.3.4"
    assert a != caller_key(None, "5.6.7.8", "share-link", "/v1/share-links/tok1")


def test_share_link_budget_is_per_ip_and_not_bypassed_by_varying_tokens(monkeypatch):
    monkeypatch.setenv("CORE_AUTH_MODE", "mock")
    client = TestClient(create_app(), raise_server_exceptions=False)
    headers = {"X-Forwarded-For": "9.9.9.9"}
    # Jetons invalides tous différents (401 attendu, jamais 429, sur les 60 premiers).
    for i in range(60):
        r = client.get(f"/v1/share-links/bad-token-{i}", headers=headers)
        assert r.status_code != 429
    assert client.get("/v1/share-links/bad-token-60", headers=headers).status_code == 429
    # Une autre IP garde un budget frais.
    other = client.get(
        "/v1/share-links/bad-token-0", headers={"X-Forwarded-For": "8.8.8.8"}
    )
    assert other.status_code != 429
```

- [ ] **Step 2: Constater l'échec**
`cd core && uv run pytest tests/test_ratelimit.py -k share_link -v`
Attendu : `route_group(...)` renvoie `None` (≠ `"share-link"`) ; `caller_key` renvoie `"Bearer a"` ; le 61e appel ne renvoie pas 429.

- [ ] **Step 3: Implémenter** — dans `core/app/ratelimit/limiter.py` :

Après `_WEBHOOK_TRIGGER_RE` :
```python
# REV-275 (e) : GET /v1/share-links/{token} — route PUBLIQUE dont le jeton est
# dans le chemin ; clé IP seule (cf. caller_key), sinon varier le jeton
# contournerait le budget (même raisonnement que webhook-trigger, j06b-011).
_SHARE_LINK_RE = re.compile(r"^/v1/share-links/[^/]+$")
```
Dans `_BUDGETS`, après `"webhook-trigger": 30,` :
```python
    "share-link": 60,
```
Dans `caller_key`, après le `if group == "webhook-trigger": …` :
```python
    if group == "share-link":
        return f"share:{client_host or 'unknown'}"
```
(et ajouter « share-link » à la docstring : « idem pour share-link, indexée sur la seule IP ».)
Dans `route_group`, après la branche `webhook-trigger` :
```python
    if _SHARE_LINK_RE.match(path) and method == "GET":
        return "share-link"
```

- [ ] **Step 4: Constater le succès**
`cd core && uv run pytest tests/test_ratelimit.py -v`
Attendu : tout vert. Si le 61e test levait une erreur DB (get_session sans base) sur les 60 premiers appels : `raise_server_exceptions=False` convertit en 500, ≠ 429, le test reste valide.

- [ ] **Step 5: Commit**
```bash
git add core/app/ratelimit/limiter.py core/tests/test_ratelimit.py
git commit -m "fix(core): limiteur de débit sur la résolution publique des liens de partage (REV-275 e)

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```

### Task L3b-6: portes du lot

**Files:** aucun (vérification). Pas de changement de route/modèle : OpenAPI et types TS inchangés (diff vide attendu — piège n°1 ; `cancel` garde `RunStatus`). Pas de surface nouvelle : inventaire de fonctionnalités inchangé.

- [ ] **Step 1: Lint et format**
`cd core && uv run ruff check . && uv run ruff format --check .`
Attendu : « All checks passed » / « already formatted » (sinon `uv run ruff format app tests` puis relancer).

- [ ] **Step 2: Contrat de couches et typage**
`cd core && uv run lint-imports`
Attendu : tous les contrats tenus (aucun import ajouté entre domaines). `mypy --strict` ne couvre pas `app/pipelines` (modules listés : auth, secrets, analytics, copilot, admin_tools, roles) : `cd core && uv run mypy --strict app/auth app/secrets app/analytics app/copilot app/admin_tools app/roles` doit rester inchangé.

- [ ] **Step 3: Tests ciblés (postgis réel : `CORE_TEST_DATABASE_URL` posé, sinon les `postgis` skippent silencieusement)**
`cd core && uv run pytest tests/test_pipeline_repository.py tests/test_pipeline_run_tracker.py tests/test_pipeline_sidecar_tracker.py tests/test_pipeline_jobs.py tests/test_pipeline_routes.py tests/test_ratelimit.py tests/test_deployability.py -v`
Attendu : tout vert, aucun `skipped` sur `test_pipeline_jobs.py`.

- [ ] **Step 4: Dérive OpenAPI (vérification, diff vide attendu)**
```bash
cd core && PYTHONPATH=. CORE_SECRETS_MASTER_KEY="AAECAwQFBgcICQoLDA0ODxAREhMUFRYXGBkaGxwdHh8=" uv run python scripts/export_openapi.py openapi.json && git diff --stat -- openapi.json
```
Attendu : aucune différence.

- [ ] **Step 5: Documentation de clôture (si ce lot est le dernier à toucher REV-275)** — dans `docs/revue/2026-09-04-backlog.md`, REV-275 : passer (c)(d)(e) en « fermé par <commit> », laisser (a)(b) ouverts (L6) ; recompter le sommaire mécaniquement. Pas de commit séparé obligatoire : à regrouper avec la clôture documentaire du plan.

## Lot L2a — REV-185, REV-186, REV-197

Prérequis communs : `cd /home/lenen/projets/geostudio/core && uv sync`. Les tests `postgis`
exigent `CORE_TEST_DATABASE_URL` (piège SP-43 : sinon skip SILENCIEUX — vérifier que la sortie
pytest ne dit pas « skipped »). Les tests REST de REV-185 tournent sur SQLite (aucun postgis requis).

Les messages de commit ci-dessous se passent avec `git commit -m "$(cat <<'MSG' ... MSG)"` ; le
trailer `Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>` est obligatoire (vérifier
`git show --format=%B -s HEAD` après chaque commit, piège sdd-subagent-commit-hygiene).

### Task L2a-1: REV-185 — helper de porte de LECTURE `get_collection_for_read`

**Décision (spec §L2/REV-185) :** `can_manage_collections` (privilège `admin.collections.manage`)
s'applique aux routes de LECTURE seulement ; `_get_writable` (`features/routes.py:567`) et
`_get_writable_collection` (`attachments/routes.py:134`) restent INCHANGÉS (un porteur du privilège
sans droit d'écriture continue de recevoir 404 sur les écritures — épinglé par un test en L2a-2).

**Audit des jumelles (relevé 2026-10-03, `grep get_readable_collection|require_collection_read|get_collection(` sur `core/app`) :**

| Site | Verdict |
|---|---|
| `features/routes.py` 219 (items), 281 (aggregate), 336 (export agrégat), 410 (export items), 556 (feature unitaire) | **à corriger** (Task L2a-2) |
| `features/tiles.py:151` (MVT) | **à corriger** (Task L2a-3) |
| `attachments/routes.py` 283 (liste), 300 (lecture fichier) | **à corriger** (Task L2a-3). Les 181/206/340 sont des écritures via `_get_writable_collection` : inchangées. |
| MCP `query_features` (`mcp/tools/catalog.py:179`), `run_analytics_query` (`mcp/tools/analytics.py:104,205`), `list_attachments` (`mcp/tools/attachments.py:45`), `query_generation.py`, `configs.py:271` | **aucun changement** : tous passent par `require_collection_read` (`mcp/tools/identity.py:86`) qui calcule DÉJÀ `can_manage_collections = has_privilege(...)`. REST et MCP sont donc alignés après L2a-2/3. |
| `POST /analytics/sql` (`features/routes.py:480-487`) | **aucun changement** : n'utilise pas `get_readable_collection`, passe `can_see_all=has_privilege(..., ADMIN_COLLECTIONS_MANAGE)` à `list_visible_collections`. |
| `alerts/jobs._measure_value` (`alerts/jobs.py:150-175`) | **aucun changement** : la porte est `can(read)` sur l'item **dataset** (pas sur la collection) ; la collection est lue par `collections_repo.get_collection` sans verdict de visibilité par collection. Aligner sur le privilège élargirait la portée d'un évaluateur automatique sans besoin. |
| `stac/routes.py` (183, 227, 279), `dcat/routes.py:171`, `collections/routes.py` (600, 647, 731, 833, 899, 918) | déjà alignés (passent le flag). |

**Pourquoi un helper plutôt que le kwarg inline :** 8 sites (5 + tuiles + 2 pièces jointes) répéteraient
`bool(user and has_privilege(...))` ; `features/` et `attachments/` ne peuvent pas s'importer entre
eux, `collections/routes.py` est déjà leur dépendance commune. Conséquence à traiter (pièges) : le
détecteur de gardes du bilan (`GUARD_NAMES`) et 2 tests de tuiles qui monkeypatchent le NOM
`get_readable_collection` dans `tiles.py`.

**Files:**
- Modify: `core/app/collections/routes.py` (ajout après `get_readable_collection`, avant `@router.post("/collections", status_code=201)`, ~l.386)
- Modify: `core/scripts/feature_health/rest_surface.py:57` (GUARD_NAMES)
- Test: `core/tests/test_collections_routes.py` (fin de fichier)

**Interfaces:**
- Produces: `app.collections.routes.get_collection_for_read(session, user, collection_id, *, guest=None)` → `Collection` (404 si illisible, même contrat que `get_readable_collection`, `can_manage_collections` calculé depuis le rôle de `user`, `False` si `user is None`).
- Consumes: `app.roles.guards.has_privilege`, `app.roles.privileges.Privilege` (déjà importés dans `collections/routes.py:34-35`).

- [ ] **Step 1: Écrire le test échouant du helper**

Avant d'écrire : `grep -n "def create_collection" -A14 core/app/collections/repository.py` et `grep -n "^from\|^import" core/tests/test_collections_routes.py` ; ajuster les kwargs de `col_repo.create_collection(...)` à la signature réelle (noms `owner_id`/`is_public` non figés ici — piège n°3) et ajouter `import pytest` si absent. Ajouter à la fin de `core/tests/test_collections_routes.py` :

```python
def test_get_collection_for_read_lifts_visibility_only_with_the_privilege():
    """REV-185 : porteur de admin.collections.manage = lecture d'une collection
    privée non partagée ; sans le privilège (ou anonyme) = 404 non-fuyant."""
    from fastapi import HTTPException

    from app.collections import repository as col_repo
    from app.collections.routes import get_collection_for_read
    from app.db import init_db, make_engine, make_session_factory
    from app.roles.privileges import Privilege
    from app.roles.repository import create_role
    from app.tenants.repository import get_or_create_default_tenant
    from app.users.models import User
    from app.users.repository import get_or_create_user, set_user_role

    engine = make_engine("sqlite+pysqlite:///:memory:")
    init_db(engine)
    Session = make_session_factory(engine)
    with Session() as s:
        tenant = get_or_create_default_tenant(s)
        owner = get_or_create_user(
            s, tenant_id=tenant.id, oidc_sub="o", username="owner", email=None,
            first_name="", last_name="", bootstrap_admin=True,
        )
        other = get_or_create_user(
            s, tenant_id=tenant.id, oidc_sub="x", username="other", email=None,
            first_name="", last_name="",
        )
        col = col_repo.create_collection(
            s, tenant_id=tenant.id, table_name="priv", owner_id=owner.id, is_public=False,
        )
        s.commit()
        col_id, other_id, tenant_id = col.id, other.id, tenant.id

    with Session() as s:
        other = s.get(User, other_id)
        with pytest.raises(HTTPException) as exc:
            get_collection_for_read(s, other, col_id)
        assert exc.value.status_code == 404
        with pytest.raises(HTTPException):
            get_collection_for_read(s, None, col_id)

        role = create_role(
            s, tenant_id=tenant_id, name="Gestionnaire",
            privileges=[Privilege.ADMIN_COLLECTIONS_MANAGE.value],
        )
        set_user_role(s, tenant_id=tenant_id, user_id=other_id, role_id=role.id, role_slug=role.slug)
        s.commit()
        other = s.get(User, other_id)
        assert get_collection_for_read(s, other, col_id).id == col_id
```

- [ ] **Step 2: Lancer, constater l'échec**

Run: `cd /home/lenen/projets/geostudio/core && uv run pytest tests/test_collections_routes.py -k get_collection_for_read -q`
Expected: FAIL `ImportError: cannot import name 'get_collection_for_read'`.

- [ ] **Step 3: Implémenter le helper**

Dans `core/app/collections/routes.py`, juste après le `return col` final de `get_readable_collection` (avant `@router.post("/collections", status_code=201)`) :

```python
def get_collection_for_read(session, user, collection_id, *, guest=None):
    """Porte de LECTURE d'une collection (REV-185) : `get_readable_collection`
    avec `can_manage_collections` dérivé du rôle de `user` — un porteur de
    `admin.collections.manage` doit lire individuellement (items, agrégats,
    exports, tuiles, pièces jointes) toute collection qu'il voit déjà en
    liste, sinon 404 après un lien valide (pièges n°5/n°14). Anonyme/invité :
    `False` (la portée d'un jeton invité ne se délègue jamais, cf. docstring
    de `get_readable_collection`). NE PAS utiliser pour une écriture :
    `_get_writable` (features) et `_get_writable_collection` (attachments)
    restent volontairement sur `get_readable_collection` nu."""
    can_manage_collections = bool(
        user and has_privilege(session, user, Privilege.ADMIN_COLLECTIONS_MANAGE.value)
    )
    return get_readable_collection(
        session, user, collection_id, can_manage_collections=can_manage_collections, guest=guest
    )
```

- [ ] **Step 4: Lancer, constater le succès**

Run: `cd /home/lenen/projets/geostudio/core && uv run pytest tests/test_collections_routes.py -k get_collection_for_read -q`
Expected: `1 passed`.

- [ ] **Step 5: Déclarer le helper comme garde reconnue du bilan de fonctionnalités**

`core/scripts/feature_health/rest_surface.py:57`, dans `GUARD_NAMES`, ajouter après `"get_readable_collection",` :

```python
        "get_collection_for_read",  # REV-185 : wrapper de get_readable_collection (lecture)
```

- [ ] **Step 6: Commit**

```bash
cd /home/lenen/projets/geostudio && git add core/app/collections/routes.py core/scripts/feature_health/rest_surface.py core/tests/test_collections_routes.py && git commit -m "$(cat <<'MSG'
fix(core): helper get_collection_for_read (porte de lecture avec admin.collections.manage, REV-185)

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>
MSG
)"
```

### Task L2a-2: REV-185 — les 5 sites de lecture de `features/routes.py` + test de bout en bout

**Files:**
- Modify: `core/app/features/routes.py:40` (import), `:219`, `:281`, `:336`, `:410`, `:556`
- Create: `core/tests/test_features_collections_manage_read.py`

**Interfaces:**
- Consumes: `get_collection_for_read(session, user, collection_id, *, guest=None)` (L2a-1) ; fixtures `env`, `_register`, `_seed`, `_as` de `core/tests/test_features_export_routes.py` (`env` = `(app, client, admin, regular, tmp_path, tenant_id, Session)` ; repo d'items factice en mémoire, DuckDB réel, `get_rls_scope` neutralisé, SQLite).
- Produces: aucune nouvelle signature.

- [ ] **Step 1: Écrire le test échouant**

Créer `core/tests/test_features_collections_manage_read.py` :

```python
# SPDX-License-Identifier: Apache-2.0
"""REV-185 : admin.collections.manage ouvre la LECTURE (items, feature unitaire,
agrégat, 2 exports, tuiles, pièces jointes) d'une collection privée non
partagée — jamais l'écriture. Sans le privilège : 404 non-fuyant partout."""

from app.roles.privileges import Privilege
from app.roles.repository import create_role
from app.tenants.repository import get_or_create_default_tenant
from app.users.models import User
from app.users.repository import set_user_role
from tests.test_features_export_routes import _as, _register, _seed, env  # noqa: F401

FEATURE = {
    "type": "Feature",
    "properties": {"region": "Nord", "pop": 10},
    "geometry": {"type": "Point", "coordinates": [0, 0]},
}


def _manager(Session, regular):
    """`regular` rechargé avec un rôle sur mesure porteur du seul privilège
    admin.collections.manage (is_admin reste False)."""
    with Session() as s:
        tenant = get_or_create_default_tenant(s)
        role = create_role(
            s,
            tenant_id=tenant.id,
            name="Gestionnaire de collections",
            privileges=[Privilege.ADMIN_COLLECTIONS_MANAGE.value],
        )
        set_user_role(
            s, tenant_id=tenant.id, user_id=regular.id, role_id=role.id, role_slug=role.slug
        )
        s.commit()
        user = s.get(User, regular.id)
        assert user is not None and user.is_admin is False
        s.expunge(user)
    return user


def _read_calls(col_id):
    agg = {"groupBy": "region", "agg": "sum", "field": "pop"}
    return [
        ("GET", f"/v1/collections/{col_id}/items", None),
        ("GET", f"/v1/collections/{col_id}/items/1", None),
        ("POST", f"/v1/collections/{col_id}/aggregate", agg),
        ("POST", f"/v1/collections/{col_id}/export?format=csv", agg),
        ("GET", f"/v1/collections/{col_id}/export/items?format=geojson", None),
        ("GET", f"/v1/collections/{col_id}/items/1/attachments", None),
        # z=99 : le 400 (coords invalides) n'est atteint QU'APRÈS la porte de lecture.
        ("GET", f"/v1/collections/{col_id}/tiles/99/0/0.mvt", None),
    ]


def _seeded_private_collection(env):  # noqa: F811
    app, client, admin, regular, tmp_path, tenant_id, Session = env
    col = _register(app, client, admin, public=False)
    _seed(tmp_path, tenant_id, col["id"])
    assert client.post(f"/v1/collections/{col['id']}/items", json=FEATURE).status_code == 201
    return app, client, regular, Session, col["id"]


def _call(client, method, url, body):
    return client.get(url) if method == "GET" else client.post(url, json=body)


def test_privilege_alone_reads_a_private_collection_everywhere(env):  # noqa: F811
    app, client, regular, Session, col_id = _seeded_private_collection(env)
    _as(app, _manager(Session, regular))
    for method, url, body in _read_calls(col_id):
        resp = _call(client, method, url, body)
        assert resp.status_code != 404, f"{method} {url} -> 404 malgré admin.collections.manage"
        assert resp.status_code in (200, 400), f"{method} {url} -> {resp.status_code}"


def test_without_the_privilege_every_read_is_a_404(env):  # noqa: F811
    app, client, regular, _Session, col_id = _seeded_private_collection(env)
    _as(app, regular)
    for method, url, body in _read_calls(col_id):
        assert _call(client, method, url, body).status_code == 404, f"{method} {url}"


def test_privilege_does_not_open_writes(env):  # noqa: F811
    # _get_writable inchangé (décision REV-185) : le voile 404 reste sur l'écriture.
    app, client, regular, Session, col_id = _seeded_private_collection(env)
    _as(app, _manager(Session, regular))
    assert client.post(f"/v1/collections/{col_id}/items", json=FEATURE).status_code == 404
```

Les routes tuiles/pièces jointes sont dans ce test dès maintenant mais ne changent qu'en L2a-3 : le test « everywhere » échouera donc encore sur ces 2 URL après ce Task — voulu (un seul test de bout en bout pour les 7 sites). Si une route renvoie un code non-404 autre que 200/400 sur la fixture SQLite (ex. 422), lire la réponse, vérifier que la porte est bien franchie, et n'élargir la tolérance qu'à CE code.

- [ ] **Step 2: Lancer, constater l'échec**

Run: `cd /home/lenen/projets/geostudio/core && uv run pytest tests/test_features_collections_manage_read.py -q`
Expected: `test_privilege_alone_reads_a_private_collection_everywhere` FAIL (`GET /v1/collections/.../items -> 404 malgré admin.collections.manage`) ; les 2 autres PASS.

- [ ] **Step 3: Implémenter — les 5 sites de `features/routes.py`**

Ligne 40, remplacer :
```python
from app.collections.routes import get_introspector, get_readable_collection
```
par :
```python
from app.collections.routes import (
    get_collection_for_read,
    get_introspector,
    get_readable_collection,
)
```
(`get_readable_collection` reste importé : `_get_writable`, l.568.)

Remplacer EXACTEMENT :
- l.219, l.281, l.556 : `col = get_readable_collection(session, user, collection_id, guest=guest)` → `col = get_collection_for_read(session, user, collection_id, guest=guest)`
- l.336, l.410 : `col = get_readable_collection(session, user, collection_id)` → `col = get_collection_for_read(session, user, collection_id)`
- l.568 (`_get_writable`) : NE PAS toucher.

Vérifier : `grep -n "get_readable_collection\|get_collection_for_read" app/features/routes.py` → 1 import de chaque + 5 appels `get_collection_for_read` + 1 appel `get_readable_collection` (dans `_get_writable`).

- [ ] **Step 4: Lancer**

Run: `cd /home/lenen/projets/geostudio/core && uv run pytest tests/test_features_collections_manage_read.py -q`
Expected: items/feature/aggregate/exports franchissent la porte ; « everywhere » échoue encore UNIQUEMENT sur `/attachments` (puis `/tiles`), corrigés en L2a-3 ; les 2 autres PASS.

- [ ] **Step 5: Non-régression des suites features**

Run: `cd /home/lenen/projets/geostudio/core && uv run pytest tests/test_features_routes_read.py tests/test_features_aggregate_routes.py tests/test_features_export_routes.py tests/test_features_guest_access_routes.py tests/test_features_sensitive_fields_integration.py -q`
Expected: tout vert.

- [ ] **Step 6: Commit**

```bash
cd /home/lenen/projets/geostudio && git add core/app/features/routes.py core/tests/test_features_collections_manage_read.py && git commit -m "$(cat <<'MSG'
fix(core): admin.collections.manage ouvre la lecture des 5 routes features (REV-185)

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>
MSG
)"
```

### Task L2a-3: REV-185 — jumelles tuiles MVT et pièces jointes (lecture)

**Files:**
- Modify: `core/app/features/tiles.py:21`, `:151`
- Modify: `core/app/attachments/routes.py:35`, `:283`, `:300`
- Modify: `core/tests/test_features_tiles.py:158`, `core/tests/test_features_tiles_cache.py:59` (cible du monkeypatch)
- Modify: `core/tests/test_feature_health_rest_surface.py:186,195` (nom de garde attendu)

**Interfaces:**
- Consumes: `get_collection_for_read` (L2a-1). Signature des lambdas de test : `lambda s, u, c, *, guest=None: col`.

- [ ] **Step 1: Le test échouant existe déjà** (`test_privilege_alone_reads_a_private_collection_everywhere`). Le relancer :

Run: `cd /home/lenen/projets/geostudio/core && uv run pytest tests/test_features_collections_manage_read.py -k everywhere -q`
Expected: FAIL sur `/attachments` (404) puis `/tiles/99/0/0.mvt`.

- [ ] **Step 2: Tuiles** — `core/app/features/tiles.py`

Ligne 21 : `from app.collections.routes import get_introspector, get_readable_collection` → `from app.collections.routes import get_collection_for_read, get_introspector`.
Ligne 151 : `col = get_readable_collection(session, user, collection_id, guest=guest)` → `col = get_collection_for_read(session, user, collection_id, guest=guest)`.

- [ ] **Step 3: Pièces jointes (lecture seule)** — `core/app/attachments/routes.py`

Ligne 35 : `from app.collections.routes import get_readable_collection` → `from app.collections.routes import get_collection_for_read, get_readable_collection` (le second reste utilisé par `_get_writable_collection`, l.137).
Lignes 283 et 300 : `col = get_readable_collection(session, user, collection_id, guest=guest)` → `col = get_collection_for_read(session, user, collection_id, guest=guest)`.
Ne PAS toucher l.137 (`_get_writable_collection`).

- [ ] **Step 4: Adapter les tests qui visaient l'ancien nom**

- `core/tests/test_features_tiles.py:158` et `core/tests/test_features_tiles_cache.py:59` :
  `monkeypatch.setattr(tiles_module, "get_readable_collection", lambda s, u, c, *, guest=None: col)` →
  `monkeypatch.setattr(tiles_module, "get_collection_for_read", lambda s, u, c, *, guest=None: col)`.
- `core/tests/test_feature_health_rest_surface.py:195` : `assert "get_readable_collection" in fact.guards` → `assert "get_collection_for_read" in fact.guards` ; dans la docstring (l.186) remplacer `get_readable_collection(...)` par `get_collection_for_read(...)` (wrapper de `get_readable_collection`).

- [ ] **Step 5: Lancer**

Run: `cd /home/lenen/projets/geostudio/core && uv run pytest tests/test_features_collections_manage_read.py tests/test_features_tiles.py tests/test_features_tiles_cache.py tests/test_feature_health_rest_surface.py tests/test_attachments_read_routes.py tests/test_attachments_guest_access_routes.py tests/test_features_tiles_guest_access_postgis.py -q`
Expected: tout vert (les `postgis` doivent s'exécuter, pas skip).

- [ ] **Step 6: Porte du bilan de fonctionnalités (le nom de garde reconnue a changé)**

Run: `cd /home/lenen/projets/geostudio/core && PYTHONPATH=. uv run python scripts/feature_health_cli.py --repo .. --check`
Expected: sortie 0. En cas d'échec « santé médiane sous plancher » : `GUARD_NAMES` (L2a-1 Step 5) n'est pas pris en compte — relire `_called_names` dans `scripts/feature_health/rest_surface.py`. Ne PAS lancer `--write` ici (régénération faite une seule fois à la clôture du plan).

- [ ] **Step 7: Commit**

```bash
cd /home/lenen/projets/geostudio && git add core/app/features/tiles.py core/app/attachments/routes.py core/tests/test_features_tiles.py core/tests/test_features_tiles_cache.py core/tests/test_feature_health_rest_surface.py && git commit -m "$(cat <<'MSG'
fix(core): tuiles MVT et pièces jointes (lecture) alignées sur admin.collections.manage (REV-185)

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>
MSG
)"
```

### Task L2a-4: REV-186 — `apply_collection_ddl(..., sensitive_fields=...)`

**Files:**
- Modify: `core/app/collections/ddl.py:129-147`
- Test: `core/tests/test_collections_ddl.py` (marqueur module `postgis`, fixtures `pg_table`/`pg_session_factory`)

**Interfaces:**
- Produces: `apply_collection_ddl(session: Session, table_name: str, *, tenant_id: str = DEFAULT_TENANT_SLUG, sensitive_fields: list[str] | None = None) -> None` — `None`/vide = comportement actuel.
- Appelants inchangés (`collections/routes.py:184` via `get_ddl_applier`, `ingestion/importer.py:316`, `provisioning.py`) : aucun ne ré-applique la DDL sur une collection déjà sensible ; le défaut vide est correct pour eux.

- [ ] **Step 1: Écrire le test échouant** (fin de `tests/test_collections_ddl.py`, même style que `test_sync_masked_role_grants_revokes_sensitive_column`)

```python
def test_reapplying_ddl_with_sensitive_fields_keeps_the_column_masked(pg_table, pg_session_factory):
    """REV-186 : apply_collection_ddl codait `[]` en dur → ré-appliquer la DDL
    sur une collection sensible rouvrait la colonne à gis_rls_masked."""
    with pg_session_factory() as session:
        apply_collection_ddl(session, pg_table)
        session.execute(text("ALTER TABLE t_rls ADD COLUMN salary integer"))
        sync_masked_role_grants(session, pg_table, ["salary"])
        # Ré-application de la DDL (idempotente) en déclarant le champ sensible.
        apply_collection_ddl(session, pg_table, sensitive_fields=["salary"])
        session.execute(
            text("INSERT INTO t_rls (titre, tenant_id, salary) VALUES ('a', 'default', 100)")
        )
        session.commit()
    with pg_session_factory() as session:
        session.execute(text("SELECT set_config('app.tenant_id', 'default', true)"))
        session.execute(text("SET LOCAL ROLE gis_rls_masked"))
        assert session.execute(text("SELECT titre FROM t_rls")).scalar() == "a"
        import sqlalchemy.exc

        with pytest.raises(sqlalchemy.exc.DBAPIError):
            session.execute(text("SELECT salary FROM t_rls")).first()
```

- [ ] **Step 2: Lancer, constater l'échec**

Run: `cd /home/lenen/projets/geostudio/core && uv run pytest tests/test_collections_ddl.py -k reapplying_ddl_with_sensitive -q`
Expected: FAIL `TypeError: apply_collection_ddl() got an unexpected keyword argument 'sensitive_fields'`.

- [ ] **Step 3: Implémenter** — `core/app/collections/ddl.py`

Remplacer la signature (l.129-131) :
```python
def apply_collection_ddl(
    session: Session, table_name: str, *, tenant_id: str = DEFAULT_TENANT_SLUG
) -> None:
```
par :
```python
def apply_collection_ddl(
    session: Session,
    table_name: str,
    *,
    tenant_id: str = DEFAULT_TENANT_SLUG,
    sensitive_fields: list[str] | None = None,
) -> None:
```
et l.147 `sync_masked_role_grants(session, table_name, [])` par :
```python
    # REV-186 : jamais `[]` en dur — une ré-application sur une collection
    # sensible rouvrirait la colonne à gis_rls_masked (GAP-22).
    sync_masked_role_grants(session, table_name, sensitive_fields or [])
```

- [ ] **Step 4: Lancer**

Run: `cd /home/lenen/projets/geostudio/core && uv run pytest tests/test_collections_ddl.py -q`
Expected: tout vert, aucun skip.

- [ ] **Step 5: Commit**

```bash
cd /home/lenen/projets/geostudio && git add core/app/collections/ddl.py core/tests/test_collections_ddl.py && git commit -m "$(cat <<'MSG'
fix(core): apply_collection_ddl accepte sensitive_fields au lieu de coder [] en dur (REV-186)

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>
MSG
)"
```

### Task L2a-5: REV-197 — `bucketUrl` dans les 3 payloads blob (schémas + validation à l'écriture)

**Files:**
- Modify: `core/app/secrets/schemas.py` (imports l.8, classes l.195-248, `SecretCreate`/`SecretUpdate` l.~281-287)
- Test: `core/tests/test_secrets_schemas.py`

**Interfaces:**
- Produces : `S3CredentialsPayload.bucketUrl`, `AzureBlobCredentialsPayload.bucketUrl`, `GcsCredentialsPayload.bucketUrl` : `str | None = None` (nullable pour qu'un secret blob EXISTANT, chiffré sans ce champ, reste décodable par `SECRET_PAYLOAD_ADAPTER` — « reste lisible », spec). Format validé quand présent : schéma `s3`/`az`/`gs` selon le kind, hôte (bucket/conteneur) non vide, pas de query/fragment, pas de segment `..`.
- `SecretCreate`/`SecretUpdate` : `bucketUrl` OBLIGATOIRE pour ces 3 kinds (422 sinon) — les nouveaux secrets sont toujours scopés ; seuls les anciens sont nullables. (`SECRET_PAYLOAD_ADAPTER.validate_python` est le seul chemin de lecture, `secrets/repository.py:154`.)

- [ ] **Step 1: Écrire les tests échouants** (fin de `tests/test_secrets_schemas.py`, imports déjà présents : `pytest`, `ValidationError`, `SECRET_PAYLOAD_ADAPTER`, `SecretCreate`)

```python
from app.secrets.schemas import SecretUpdate  # noqa: E402

_BLOB_BODIES = {
    "s3_credentials": {"awsAccessKeyId": "AKIA", "awsSecretAccessKey": "x", "bucketUrl": "s3://b/p"},
    "azure_blob_credentials": {"accountName": "a", "accountKey": "k", "bucketUrl": "az://c/p"},
    "gcs_credentials": {"serviceAccountInfo": {"type": "service_account"}, "bucketUrl": "gs://b"},
}


@pytest.mark.parametrize("kind", sorted(_BLOB_BODIES))
def test_blob_secret_round_trips_with_bucket_url(kind):
    body = {"kind": kind, **_BLOB_BODIES[kind]}
    created = SecretCreate.model_validate({"name": "x", "payload": body})
    assert created.payload.bucketUrl == _BLOB_BODIES[kind]["bucketUrl"]


@pytest.mark.parametrize("kind", sorted(_BLOB_BODIES))
def test_blob_secret_creation_requires_bucket_url(kind):
    body = {"kind": kind, **{k: v for k, v in _BLOB_BODIES[kind].items() if k != "bucketUrl"}}
    with pytest.raises(ValidationError, match="bucketUrl"):
        SecretCreate.model_validate({"name": "x", "payload": body})
    with pytest.raises(ValidationError, match="bucketUrl"):
        SecretUpdate.model_validate({"payload": body})


@pytest.mark.parametrize("kind", sorted(_BLOB_BODIES))
def test_legacy_blob_secret_without_bucket_url_still_decodes(kind):
    # Un secret chiffré avant REV-197 doit rester lisible (l'exécution, elle, échoue
    # avec un message explicite — cf. connector_runtime).
    body = {"kind": kind, **{k: v for k, v in _BLOB_BODIES[kind].items() if k != "bucketUrl"}}
    assert SECRET_PAYLOAD_ADAPTER.validate_python(body).bucketUrl is None


@pytest.mark.parametrize(
    "kind, bad",
    [
        ("s3_credentials", "az://b/p"),  # mauvais schéma pour le kind
        ("s3_credentials", "s3://"),  # pas de bucket
        ("s3_credentials", "s3://b/../other"),  # traversée
        ("s3_credentials", "s3://b/p?x=1"),  # query
        ("azure_blob_credentials", "s3://c"),
        ("gcs_credentials", "gs:///p"),
    ],
)
def test_blob_bucket_url_format_is_validated(kind, bad):
    body = {"kind": kind, **_BLOB_BODIES[kind], "bucketUrl": bad}
    with pytest.raises(ValidationError):
        SecretCreate.model_validate({"name": "x", "payload": body})
```

- [ ] **Step 2: Lancer, constater l'échec**

Run: `cd /home/lenen/projets/geostudio/core && uv run pytest tests/test_secrets_schemas.py -q`
Expected: FAIL (`AttributeError ... bucketUrl` / `DID NOT RAISE`).

- [ ] **Step 3: Implémenter** — `core/app/secrets/schemas.py`

Imports : `from pydantic import BaseModel, Field, TypeAdapter` → `from pydantic import BaseModel, Field, TypeAdapter, field_validator` ; ajouter `from urllib.parse import urlsplit` (bloc stdlib, avant `from typing import ...` par ordre alphabétique `typing` < `urllib` : placer APRÈS `from typing import …`).

Avant `class S3CredentialsPayload`, ajouter :

```python
_BLOB_KIND_SCHEME = {
    "s3_credentials": "s3",
    "azure_blob_credentials": "az",
    "gcs_credentials": "gs",
}


def _check_bucket_url(value: str | None, scheme: str) -> str | None:
    """REV-197 : `bucketUrl` = bucket (+ préfixe optionnel) auquel le secret est
    lié. `None` toléré UNIQUEMENT pour décoder un secret antérieur à REV-197 ;
    l'écriture l'exige (SecretCreate/SecretUpdate)."""
    if value is None:
        return value
    parts = urlsplit(value)
    if (
        parts.scheme != scheme
        or not parts.netloc
        or parts.query
        or parts.fragment
        or ".." in parts.path.split("/")
    ):
        raise ValueError(
            f"bucketUrl must look like '{scheme}://<bucket>[/<prefix>]' "
            "(no query, fragment or '..' segment)"
        )
    return value
```

Dans chacune des 3 classes, ajouter le champ et son validateur après les champs existants (littéral `"s3"` / `"az"` / `"gs"` selon la classe) :

```python
    bucketUrl: str | None = None  # bucket/préfixe auquel le secret est lié (REV-197)

    @field_validator("bucketUrl")
    @classmethod
    def _bucket_url(cls, v: str | None) -> str | None:
        return _check_bucket_url(v, "s3")
```
et ajouter à chaque docstring : « `bucketUrl` lie le secret à un bucket/préfixe : `params.path` d'un `reader.connector.blob` doit en porter le préfixe (REV-197). »

Remplacer `SecretCreate`/`SecretUpdate` (fin de fichier) par :

```python
def _require_bucket_url(payload: Any) -> Any:
    if payload.kind in _BLOB_KIND_SCHEME and payload.bucketUrl is None:
        raise ValueError(
            "bucketUrl is required for blob secrets "
            f"(e.g. '{_BLOB_KIND_SCHEME[payload.kind]}://my-bucket/prefix')"
        )
    return payload


class SecretCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    payload: SecretPayload

    @field_validator("payload")
    @classmethod
    def _bucket_scoped(cls, v: Any) -> Any:
        return _require_bucket_url(v)


class SecretUpdate(BaseModel):
    payload: SecretPayload

    @field_validator("payload")
    @classmethod
    def _bucket_scoped(cls, v: Any) -> Any:
        return _require_bucket_url(v)
```

- [ ] **Step 4: Lancer**

Run: `cd /home/lenen/projets/geostudio/core && uv run pytest tests/test_secrets_schemas.py tests/test_secrets_routes.py tests/test_secrets_repository.py tests/test_mcp_tools_secrets.py -q`
Expected: tout vert.

- [ ] **Step 5: Commit**

```bash
cd /home/lenen/projets/geostudio && git add core/app/secrets/schemas.py core/tests/test_secrets_schemas.py && git commit -m "$(cat <<'MSG'
feat(core): bucketUrl obligatoire à l'écriture des secrets blob s3/azure/gcs (REV-197)

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>
MSG
)"
```

### Task L2a-6: REV-197 — `materialize_blob_connector` exige que `params.path` soit dans `bucketUrl`

**Files:**
- Modify: `core/app/pipelines/connector_runtime.py` (nouveau helper avant `materialize_blob_connector` l.589 ; appel après le contrôle de kind l.628 ; docstring)
- Modify: `core/app/pipelines/ops/schemas.py:268-300` (docstring `ReaderConnectorBlobParams`)
- Test: `core/tests/test_pipeline_connector_runtime.py` (payloads existants l.~1010-1160 + nouveaux tests)

**Interfaces:**
- Produces: `_assert_path_within_bucket(payload, path: str) -> None` (lève `ConnectorRuntimeError`). Ordre des contrôles dans `materialize_blob_connector` : schéma → kind → **bucketUrl** → egress endpoint → credentials. Les tests « mauvais kind » et « schéma non supporté » lèvent avant : inchangés.
- Jumelles auditées (aucun changement de code) : `materialize_postgres/mssql/snowflake/oracle/bigquery_connector` — la cible réseau est le DSN du secret, `params` ne porte que `query` : déjà liés au secret. `materialize_rest_connector` — `params.baseUrl` est libre et un secret (bearer/api-key/basic) y est envoyé : même classe de problème, hors périmètre REV-197 ; à consigner comme nouvelle entrée du backlog (pas de correctif ici).

- [ ] **Step 1: Adapter les tests existants et écrire les nouveaux (échouants)**

Dans `core/tests/test_pipeline_connector_runtime.py`, ajouter `bucketUrl` aux payloads des secrets blob nominaux :
- `test_materialize_blob_connector_builds_aws_credentials_and_splits_path` : `"bucketUrl": "s3://bucket/prefix",`
- `test_materialize_blob_connector_blocks_internal_s3_endpoint` : `"bucketUrl": "s3://bucket",`
- `test_materialize_blob_connector_builds_azure_credentials` : `"bucketUrl": "az://container",`
- `test_materialize_blob_connector_builds_gcs_credentials` : `payload={"kind": "gcs_credentials", "serviceAccountInfo": service_account_info, "bucketUrl": "gs://bucket"}`
(le payload de `test_materialize_blob_connector_unsupported_scheme_raises` reste sans `bucketUrl` : il lève avant.)

Ajouter après `test_materialize_blob_connector_builds_gcs_credentials` :

```python
def _blob_s3_secret(session, tenant, user, **extra):
    _create_secret(
        session,
        tenant,
        user,
        name="s3-scoped",
        kind="s3_credentials",
        payload={
            "kind": "s3_credentials",
            "awsAccessKeyId": "AKIA123",
            "awsSecretAccessKey": "shh",
            **extra,
        },
    )


@pytest.mark.parametrize(
    "path",
    [
        "s3://other-bucket/prefix/data.csv",  # autre bucket
        "s3://bucket-evil/prefix/data.csv",  # préfixe de nom de bucket
        "s3://bucket/other/data.csv",  # même bucket, hors préfixe
        "s3://bucket/prefix/../other/data.csv",  # traversée
        "s3://bucket/prefixe/data.csv",  # préfixe de chaîne, pas de segment
    ],
)
def test_materialize_blob_connector_refuses_path_outside_bucket_url(
    monkeypatch, conn, session, tenant, user, path
):
    _blob_s3_secret(session, tenant, user, bucketUrl="s3://bucket/prefix")
    captured: dict = {}
    _patch_blob_internals(monkeypatch, captured)
    params = ReaderConnectorBlobParams(secretName="s3-scoped", path=path, format="csv")
    with pytest.raises(connector_runtime.ConnectorRuntimeError, match="outside"):
        connector_runtime.materialize_blob_connector(
            conn,
            secret_resolver=connector_runtime.PostgresSecretResolver(session, tenant.id, user),
            node_id="bo",
            params=params,
            view_name="node_bo",
        )
    assert "bucket_url" not in captured  # jamais allé jusqu'à filesystem()


def test_materialize_blob_connector_accepts_path_inside_bucket_url(
    monkeypatch, conn, session, tenant, user
):
    _blob_s3_secret(session, tenant, user, bucketUrl="s3://bucket/prefix/")
    captured: dict = {}
    _patch_blob_internals(monkeypatch, captured)
    params = ReaderConnectorBlobParams(
        secretName="s3-scoped", path="s3://bucket/prefix/sub/data.csv", format="csv"
    )
    connector_runtime.materialize_blob_connector(
        conn,
        secret_resolver=connector_runtime.PostgresSecretResolver(session, tenant.id, user),
        node_id="bi",
        params=params,
        view_name="node_bi",
    )
    assert captured["bucket_url"] == "s3://bucket"
    assert captured["file_glob"] == "prefix/sub/data.csv"


def test_materialize_blob_connector_legacy_secret_without_bucket_url_fails_clearly(
    monkeypatch, conn, session, tenant, user
):
    _blob_s3_secret(session, tenant, user)  # secret chiffré avant REV-197
    _patch_blob_internals(monkeypatch, {})
    params = ReaderConnectorBlobParams(
        secretName="s3-scoped", path="s3://bucket/data.csv", format="csv"
    )
    with pytest.raises(connector_runtime.ConnectorRuntimeError, match="bucketUrl"):
        connector_runtime.materialize_blob_connector(
            conn,
            secret_resolver=connector_runtime.PostgresSecretResolver(session, tenant.id, user),
            node_id="bl",
            params=params,
            view_name="node_bl",
        )
```

- [ ] **Step 2: Lancer, constater l'échec**

Run: `cd /home/lenen/projets/geostudio/core && uv run pytest tests/test_pipeline_connector_runtime.py -k blob -q`
Expected: les 5 cas `refuses_path_outside` et `legacy_secret` FAIL (`DID NOT RAISE`) ; `accepts_path_inside` et les 4 tests nominaux PASS.

- [ ] **Step 3: Implémenter** — `core/app/pipelines/connector_runtime.py`

Ajouter juste avant `def materialize_blob_connector(` :

```python
def _assert_path_within_bucket(payload, path: str) -> None:
    """REV-197 : le secret est LIÉ à `payload.bucketUrl` ; `params.path` (écrit
    par l'auteur du pipeline) doit en porter le préfixe, sinon un secret S3
    pourrait lire n'importe quel bucket accessible à ses clés. Comparaison sur
    un préfixe terminé par `/` (« s3://bucket » ne couvre pas « s3://bucket-evil »)
    et rejet de tout segment `..`."""
    bucket_url = payload.bucketUrl
    if not bucket_url:
        raise ConnectorRuntimeError(
            "reader.connector.blob: this secret has no 'bucketUrl' (required since REV-197) — "
            "edit the secret to set the bucket/prefix it is scoped to "
            "(e.g. 's3://my-bucket/prefix')"
        )
    scope = bucket_url.rstrip("/") + "/"
    if ".." in urlsplit(path).path.split("/") or not path.startswith(scope):
        raise ConnectorRuntimeError(
            f"reader.connector.blob: path '{path}' is outside the bucket scope "
            f"of the secret ('{bucket_url}')"
        )
```

Dans `materialize_blob_connector`, juste après le bloc `if payload.kind != expected_kind: raise ...` et avant `if payload.kind == "s3_credentials":` :

```python
    _assert_path_within_bucket(payload, params.path)
```
Dans sa docstring, après « Le secret doit être du kind attendu… », ajouter : « Le secret porte un `bucketUrl` (bucket + préfixe optionnel) et `params.path` doit être sous ce préfixe (REV-197) : un secret blob est lié à un bucket, pas à tout ce que ses clés peuvent atteindre. »

- [ ] **Step 4: Docstring `ReaderConnectorBlobParams`** — `core/app/pipelines/ops/schemas.py`

Dans la docstring, remplacer « résolu par un secret de connexion pré-configuré au bucket — jamais un upload ni une URL arbitraire » par « résolu par un secret de connexion lié à un bucket (champ `bucketUrl` du secret, REV-197) — jamais un upload ni une URL arbitraire : `path` doit être sous ce `bucketUrl`, sinon `ConnectorRuntimeError` à l'exécution ». Ajouter à la fin du paragraphe « Le fournisseur est résolu… » : « Un secret créé avant REV-197 (sans `bucketUrl`) reste lisible mais l'exécution échoue avec un message demandant de le renseigner. »

- [ ] **Step 5: Lancer**

Run: `cd /home/lenen/projets/geostudio/core && uv run pytest tests/test_pipeline_connector_runtime.py tests/test_secrets_schemas.py -q`
Expected: tout vert. Puis `grep -rln "s3_credentials\|azure_blob_credentials\|gcs_credentials" tests --include=*.py` : tout autre test qui CRÉE un secret blob via la route (hors fichiers déjà traités) doit recevoir un `bucketUrl` ; confirmer par `uv run pytest tests -q -k "blob or secret or connector"`.

- [ ] **Step 6: Commit**

```bash
cd /home/lenen/projets/geostudio && git add core/app/pipelines/connector_runtime.py core/app/pipelines/ops/schemas.py core/tests/test_pipeline_connector_runtime.py && git commit -m "$(cat <<'MSG'
fix(core): reader.connector.blob lié au bucketUrl du secret, chemin hors bucket refusé (REV-197)

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>
MSG
)"
```

### Task L2a-7: REV-197 — OpenAPI + types TS + type `SecretPayload` du shell

**Files:**
- Modify (généré) : `core/openapi.json`, `shell/src/api/generated/core-schema.d.ts`
- Modify: `shell/src/api/types.ts:802-808`

- [ ] **Step 1: Régénérer la spec OpenAPI** (commande exacte de CLAUDE.md)

```bash
cd /home/lenen/projets/geostudio/core && PYTHONPATH=. \
  CORE_SECRETS_MASTER_KEY="AAECAwQFBgcICQoLDA0ODxAREhMUFRYXGBkaGxwdHh8=" \
  uv run python scripts/export_openapi.py openapi.json
cd ../shell && npm run gen:api-types
```
Expected : `git diff --stat` montre `core/openapi.json` et `shell/src/api/generated/core-schema.d.ts` modifiés ; `grep -c bucketUrl src/api/generated/core-schema.d.ts` ≥ 3 (`bucketUrl?: string | null` sur s3/azure/gcs).

- [ ] **Step 2: Type shell** — `shell/src/api/types.ts` : remplacer les variantes s3/azure/gcs de `SecretPayload` (l.802-808) par :

```ts
  | {
      kind: "s3_credentials";
      awsAccessKeyId: string;
      awsSecretAccessKey: string;
      endpointUrl?: string;
      bucketUrl: string;
    }
  | { kind: "azure_blob_credentials"; accountName: string; accountKey: string; bucketUrl: string }
  | { kind: "gcs_credentials"; serviceAccountInfo: Record<string, unknown>; bucketUrl: string };
```

- [ ] **Step 3: Commit** (ne pas lancer `tsc` ici : `SecretParamSelect.tsx` ne compile plus tant que L2a-8 n'est pas faite — enchaîner).

```bash
cd /home/lenen/projets/geostudio && git add core/openapi.json shell/src/api/generated/core-schema.d.ts shell/src/api/types.ts && git commit -m "$(cat <<'MSG'
chore(api): OpenAPI et types TS régénérés, bucketUrl sur les secrets blob (REV-197)

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>
MSG
)"
```

### Task L2a-8: REV-197 — champ « Bucket et préfixe » du formulaire de secret (shell)

**Files:**
- Modify: `shell/src/builder/pipeline/SecretParamSelect.tsx` (`buildPayload` l.176-190, JSX juste avant `{kind === "smtp" && (`)
- Modify: `shell/src/i18n/catalog.fr.ts` (après `secretParamSelect.endpointUrlPlaceholder`, l.~1514)
- Test: `shell/src/builder/pipeline/SecretParamSelect.test.tsx`

**Interfaces:** Consumes `SecretPayload` (types.ts, L2a-7). `SecretParamSelect.tsx` est le seul composant de création de secret (seul appelant de `createSecret` côté UI, vérifié par grep).

- [ ] **Step 1: Tests échouants** — dans `SecretParamSelect.test.tsx`, remplacer le test s3 existant (« un secret s3_credentials créé est immédiatement sélectionné », l.128-157) par la version ci-dessous et ajouter les tests azure et gcs :

```tsx
test("un secret s3_credentials créé est immédiatement sélectionné (Vague 2, reader.connector.blob)", async () => {
  const createSecret = vi.fn().mockResolvedValue({
    id: "s11",
    name: "s3-prod",
    kind: "s3_credentials",
    createdAt: "",
    updatedAt: "",
  });
  const { onChange } = renderSelect({ kindFilter: "s3_credentials" }, { createSecret });
  await userEvent.click(screen.getByText("Créer un secret"));
  await userEvent.type(screen.getByLabelText("Nom"), "s3-prod");
  await userEvent.type(screen.getByLabelText("Access key ID"), "AKIA123");
  await userEvent.type(screen.getByLabelText("Secret access key"), "sekret");
  await userEvent.type(screen.getByLabelText("Bucket et préfixe"), "s3://mon-bucket/data");
  await userEvent.click(screen.getByText("Créer"));

  await waitFor(() => expect(onChange).toHaveBeenCalledWith("s3-prod"));
  expect(createSecret).toHaveBeenCalledWith({
    name: "s3-prod",
    payload: {
      kind: "s3_credentials",
      awsAccessKeyId: "AKIA123",
      awsSecretAccessKey: "sekret",
      endpointUrl: undefined,
      bucketUrl: "s3://mon-bucket/data",
    },
  });
});

test("un secret azure_blob_credentials porte son bucketUrl (REV-197)", async () => {
  const createSecret = vi.fn().mockResolvedValue({
    id: "s12",
    name: "az-prod",
    kind: "azure_blob_credentials",
    createdAt: "",
    updatedAt: "",
  });
  renderSelect({ kindFilter: "azure_blob_credentials" }, { createSecret });
  await userEvent.click(screen.getByText("Créer un secret"));
  await userEvent.type(screen.getByLabelText("Nom"), "az-prod");
  await userEvent.type(screen.getByLabelText("Nom du compte"), "moncompte");
  await userEvent.type(screen.getByLabelText("Clé du compte"), "k==");
  await userEvent.type(screen.getByLabelText("Bucket et préfixe"), "az://conteneur");
  await userEvent.click(screen.getByText("Créer"));

  await waitFor(() => expect(createSecret).toHaveBeenCalled());
  expect(createSecret.mock.calls[0][0].payload).toEqual({
    kind: "azure_blob_credentials",
    accountName: "moncompte",
    accountKey: "k==",
    bucketUrl: "az://conteneur",
  });
});

test("un secret gcs_credentials porte son bucketUrl (REV-197)", async () => {
  const createSecret = vi.fn().mockResolvedValue({
    id: "s13",
    name: "gcs-prod",
    kind: "gcs_credentials",
    createdAt: "",
    updatedAt: "",
  });
  renderSelect({ kindFilter: "gcs_credentials" }, { createSecret });
  await userEvent.click(screen.getByText("Créer un secret"));
  await userEvent.type(screen.getByLabelText("Nom"), "gcs-prod");
  await userEvent.click(screen.getByLabelText("JSON du compte de service"));
  await userEvent.paste('{"type":"service_account"}');
  await userEvent.type(screen.getByLabelText("Bucket et préfixe"), "gs://mon-bucket");
  await userEvent.click(screen.getByText("Créer"));

  await waitFor(() => expect(createSecret).toHaveBeenCalled());
  expect(createSecret.mock.calls[0][0].payload).toEqual({
    kind: "gcs_credentials",
    serviceAccountInfo: { type: "service_account" },
    bucketUrl: "gs://mon-bucket",
  });
});
```

- [ ] **Step 2: Lancer, constater l'échec**

Run: `cd /home/lenen/projets/geostudio/shell && npx vitest run src/builder/pipeline/SecretParamSelect.test.tsx`
Expected: les 3 tests FAIL (`Unable to find a label with the text of: Bucket et préfixe`).

- [ ] **Step 3: i18n** — `shell/src/i18n/catalog.fr.ts`, après la ligne `"secretParamSelect.endpointUrlPlaceholder": ...` :

```ts
  "secretParamSelect.bucketUrlLabel": "Bucket et préfixe",
  "secretParamSelect.bucketUrlAria": "Bucket et préfixe",
  "secretParamSelect.bucketUrlHelp":
    "Le secret n'ouvre que ce bucket (et ce préfixe) : le chemin d'un lecteur blob doit en faire partie.",
  "secretParamSelect.bucketUrlPlaceholderS3": "s3://mon-bucket/prefixe",
  "secretParamSelect.bucketUrlPlaceholderAz": "az://mon-conteneur/prefixe",
  "secretParamSelect.bucketUrlPlaceholderGs": "gs://mon-bucket/prefixe",
```

- [ ] **Step 4: Composant** — `SecretParamSelect.tsx`

`buildPayload` :
- `case "s3_credentials"` : ajouter `bucketUrl: field("bucketUrl"),` après `endpointUrl: ...,`
- `case "azure_blob_credentials"` : `return { kind, accountName: field("accountName"), accountKey: field("accountKey"), bucketUrl: field("bucketUrl") };`
- `case "gcs_credentials"` : `return { kind, serviceAccountInfo: parsed, bucketUrl: field("bucketUrl") };`

Au-dessus du composant (près de `KIND_LABELS`) :

```tsx
const BUCKET_PLACEHOLDER_KEYS = {
  s3_credentials: "secretParamSelect.bucketUrlPlaceholderS3",
  azure_blob_credentials: "secretParamSelect.bucketUrlPlaceholderAz",
  gcs_credentials: "secretParamSelect.bucketUrlPlaceholderGs",
} as const;
```

Juste avant `{kind === "smtp" && (` insérer :

```tsx
      {(kind === "s3_credentials" ||
        kind === "azure_blob_credentials" ||
        kind === "gcs_credentials") && (
        <div className="flex flex-col gap-1 text-xs">
          <label className="flex flex-col gap-1">
            {t("secretParamSelect.bucketUrlLabel")}
            <input
              aria-label={t("secretParamSelect.bucketUrlAria")}
              placeholder={t(BUCKET_PLACEHOLDER_KEYS[kind])}
              required
              className="h-8 rounded border border-control bg-surface px-2 text-ink"
              value={field("bucketUrl")}
              onChange={(e) => setFieldValue("bucketUrl", e.target.value)}
            />
          </label>
          <span className="text-ink-2">{t("secretParamSelect.bucketUrlHelp")}</span>
        </div>
      )}
```

- [ ] **Step 5: Lancer**

Run: `cd /home/lenen/projets/geostudio/shell && npx vitest run src/builder/pipeline/SecretParamSelect.test.tsx && npm run lint && npx tsc --noEmit`
Expected: tests verts, lint sans erreur (détecteur i18n : pas de français en dur), `tsc` sans erreur. Si `StaticItemClient.ts`/`DesktopItemClient.ts`/`api/itemClient.test.ts` construisent un `SecretPayload` blob, `tsc` l'indiquera : ajouter `bucketUrl` à ces littéraux.

- [ ] **Step 6: Commit**

```bash
cd /home/lenen/projets/geostudio && git add shell/src/builder/pipeline/SecretParamSelect.tsx shell/src/builder/pipeline/SecretParamSelect.test.tsx shell/src/i18n/catalog.fr.ts && git commit -m "$(cat <<'MSG'
feat(shell): champ « Bucket et préfixe » sur les secrets blob s3/azure/gcs (REV-197)

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>
MSG
)"
```

### Task L2a-9: Alignement CLAUDE.md, CHANGELOG et inventaire (REV-185/186/197)

**Files:**
- Modify: `CLAUDE.md` (entrée « Vague 2 lecteurs DuckDB (SQL + objet/stockage) »)
- Modify: `CHANGELOG.md` (`[Unreleased]`)

- [ ] **Step 1: CLAUDE.md** — dans l'entrée « **Vague 2 lecteurs DuckDB (SQL + objet/stockage)** », remplacer EXACTEMENT :

`par un secret de connexion pré-configuré au bucket, jamais un upload ni une URL arbitraire.`

par :

`par un secret de connexion lié à un bucket (`bucketUrl` du secret, préfixe imposé à `params.path`, REV-197), jamais un upload ni une URL arbitraire ; un secret blob antérieur sans `bucketUrl` reste lisible mais son exécution échoue avec un message explicite.`

(Une seule ligne, règle « une ligne par chantier ».) Puis :
`cd /home/lenen/projets/geostudio && python3 scripts/check_claude_md_size.py CLAUDE.md .claude-md-size-threshold` → exit 0 (si le seuil est franchi, raccourcir la phrase, ne pas relever le seuil).

- [ ] **Step 2: CHANGELOG.md** — lire d'abord `## [Unreleased]` ; y ajouter (créer `### Security` / `### Changed` s'ils n'existent pas) :

```markdown
- **Rupture (secrets blob)** : les secrets `s3_credentials` / `azure_blob_credentials` /
  `gcs_credentials` portent désormais un `bucketUrl` obligatoire à la création/modification, et
  `reader.connector.blob` refuse tout `path` hors de ce bucket/préfixe (REV-197). Un secret existant
  sans `bucketUrl` reste lisible mais les pipelines qui l'utilisent échouent avec un message
  demandant de le renseigner : éditer le secret (aucune migration automatique).
- **Sécurité** : `admin.collections.manage` ouvre la lecture des items, agrégats, exports, tuiles et
  pièces jointes d'une collection (REV-185) ; une ré-application de la DDL ne rouvre plus une
  colonne sensible à `gis_rls_masked` (REV-186).
```

- [ ] **Step 3: Inventaire** — aucune surface nouvelle (ni route, ni outil MCP, ni route shell) : vérifier.

Run: `cd /home/lenen/projets/geostudio/core && uv run pytest tests/test_feature_inventory.py -q`
Expected: vert.

- [ ] **Step 4: Commit**

```bash
cd /home/lenen/projets/geostudio && git add CLAUDE.md CHANGELOG.md && git commit -m "$(cat <<'MSG'
docs: aligner CLAUDE.md et CHANGELOG sur le scoping des secrets blob et la lecture admin.collections.manage

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>
MSG
)"
```

### Task L2a-10: Vérification des portes du lot L2a

- [ ] **Step 1: Qualité statique cœur**

Run:
```bash
cd /home/lenen/projets/geostudio/core && uv run ruff check . && uv run ruff format --check . \
  && uv run mypy --strict app/auth app/secrets app/analytics app/copilot app/admin_tools app/roles \
  && uv run lint-imports
```
Expected: tout vert. Si `ruff format --check` signale les fichiers de test écrits dans ce lot (ex. lignes > 100 colonnes dans `test_secrets_schemas.py` / `test_collections_routes.py`), lancer `uv run ruff format <fichier>` puis commit `style(core): ruff format (L2a)` avec le trailer. `lint-imports` : `collections/routes.py` n'ajoute aucun import de niveau module ; `attachments/routes.py` et `features/tiles.py` importaient déjà `app.collections.routes`. `mypy --strict app/secrets` couvre `schemas.py` (validateurs typés `Any`).

- [ ] **Step 2: Suites touchées**

Run:
```bash
cd /home/lenen/projets/geostudio/core && uv run pytest tests/test_collections_routes.py tests/test_collections_ddl.py tests/test_features_collections_manage_read.py tests/test_features_tiles.py tests/test_features_tiles_cache.py tests/test_features_routes_read.py tests/test_attachments_read_routes.py tests/test_secrets_schemas.py tests/test_secrets_routes.py tests/test_pipeline_connector_runtime.py tests/test_feature_health_rest_surface.py tests/test_feature_inventory.py tests/test_stac_routes.py tests/test_dcat_routes.py -q
```
Expected: tout vert, aucun `skipped` sur `test_collections_ddl.py` (sinon `CORE_TEST_DATABASE_URL` absent : piège SP-43).

- [ ] **Step 3: Dérive OpenAPI vide** (piège n°1)

Relancer la commande de la Task L2a-7 Step 1, puis :
`cd /home/lenen/projets/geostudio && git status --short core/openapi.json shell/src/api/generated/core-schema.d.ts`
Expected: aucune modification (déjà régénéré en L2a-7, aucune route changée depuis).

- [ ] **Step 4: Shell**

Run: `cd /home/lenen/projets/geostudio/shell && npm run lint && npm run format:check && npx tsc --noEmit && npx vitest run src/builder/pipeline src/api`
Expected: vert. Si `format:check` signale `SecretParamSelect.tsx` ou son test : `npx prettier --write <fichier>` puis commit `style(shell): prettier (L2a)`. Seuil de couverture et `npm run build` : rejoués une seule fois à la clôture du plan complet.

## Fragment L2b — REV-290, REV-272(b), REV-271, REV-272(c)

Ordre : L2b-1 (290) → L2b-2 (272b, dépend de 1 pour le test croisé) → L2b-3 (271 cœur/MCP, indépendant) → L2b-4 (271 socle shell commun) → L2b-5…L2b-9 (un domaine + son éditeur par tâche, chacun dépend de L2b-4) → L2b-10 (272c E2E) → L2b-11 (portes + clôture backlog).

Décisions figées (spec §L2) : 290 = **lever** (aucune requête, aucun appel `getToken`) ; `rollback_config` (REST + `ConfigHistoryPanel`) reste **sans `If-Match`** (action explicite « restaurer cette version », l'éditeur relit ensuite la version) ; copilote = jumelle déjà couverte (il exclut `save_app_config`, cf. `core/app/copilot/tools_allowlist.py`) ; `pipelines/runtime.py:1087` = écrivain interne, sans garde (documenté). L'assistant requête visuelle (`VisualQueryWizardPage`) régénère le pipeline/dataset depuis son état, ce n'est pas un lecture-modification-écriture : il reste sans `If-Match` (`baseVersion` absent → comportement historique).

Vérifié dans le code (piège n°12) : toutes les URL des mocks E2E (`shell/e2e/mocks.ts`) sont `https://core.test/v1/…` = `VITE_CORE_URL` + `/v1` (`shell/.env.e2e`, `playwright.config.ts:37`) ; les mocks de config ne renvoient pas de `version` → aucun `If-Match` émis, aucune adaptation E2E nécessaire pour 290 ni 271.

---

### Task L2b-1: REV-290 — `authFetch` lève hors de l'origine du cœur

**Files:**
- Modify: `shell/src/api/base.ts` (ajout de `toCoreHref` après `fetchWithTimeout` l.~30 ; `authFetch` l.328-346 ; suppression de `isCoreServed` l.445-453 ; `fetchGeoJsonPage` l.466)
- Modify: `shell/src/api/baseRenew.test.ts` (test P30.03 l.69-83 à adapter + 3 tests neufs)

**Interfaces:**
- Consumes: `createBase({ coreUrl, getToken, getShareLinkToken?, onUnauthorized? })` (`coreUrl` interne = `${opts.coreUrl}/v1`).
- Produces: `authFetch(url, init?, timeoutMs?)` **rejette** `Error("authFetch: URL not served by the core, refused: <url>")` avant tout `getToken()`/`fetch` si l'URL, résolue contre `coreUrl`, n'a pas la même origine ET un chemin `=== /v1` ou `/v1/…`. Une URL relative (`/v1/items`) est résolue contre le cœur et c'est l'URL **résolue** qui est envoyée. `fetchUrl(url, { authenticated: true })` hérite du refus ; `fetchUrl(url)` (sans `authenticated`) reste une requête nue.

Audit des appelants (déjà fait, à ne pas refaire à l'aveugle — relancer `grep -rnE "authFetch|[^a-zA-Z.]fetch\(" shell/src --include=*.ts --include=*.tsx | grep -v test` pour confirmer) : tous les `authFetch` (`base.ts` 488/515/532/547, `domains/layers.ts` 145/172/202, `items.ts` 177/185, `features.ts` 13, `exportsIngestion.ts` 19, `extensionsAdminTools.ts` 38/67) construisent `${coreUrl}/…` ⇒ inchangés. `fetchUrl(…, {authenticated:true})` n'est appelé que derrière `isHostedCollectionUrl` (`LayersPanel.tsx:263`, `geojsonIntrospect.ts:16`) ⇒ URL du cœur. Les `fetch` nus n'envoient jamais de jeton : PUT présignés S3 (`Tileset3DUploadButton.tsx:106`, `form.tsx:295`, `exportsIngestion.ts:78`, `Terrain3DUploadButton` via `client.uploadToPresignedUrl`), `embed/resolveShareLink.ts:15` (route publique), `staticExport/entry.tsx:58,86` (JSON relatifs), `desktop/DesktopItemClient.ts:46` (sidecar). `pages/*` et `LayerPicker` n'ont aucun `fetch` direct (LayerPicker passe par `fetchFeatureCollection` → `client.fetchUrl`).

- [ ] **Step 1: Écrire les tests qui échouent**

Dans `shell/src/api/baseRenew.test.ts`, remplacer le test `"P30.03 fetchUrl : jeton et lien de partage seulement si authenticated"` par la version ci-dessous (l'URL authentifiée doit désormais être sous `/v1`) et ajouter les trois tests à la suite :

```ts
it("P30.03 fetchUrl : jeton et lien de partage seulement si authenticated", async () => {
  const fetchSpy = vi.fn().mockResolvedValue(ok());
  vi.stubGlobal("fetch", fetchSpy);
  const base = createBase({
    coreUrl: "http://c",
    getToken: () => "tok",
    getShareLinkToken: () => "share",
  });
  await base.fetchUrl("http://c/v1/collections/x/tiles/0/0/0.mvt", { authenticated: true });
  const h = fetchSpy.mock.calls[0][1].headers as Headers;
  expect(h.get("Authorization")).toBe("Bearer tok");
  expect(h.get("X-Share-Link-Token")).toBe("share");
  await base.fetchUrl("http://evil.example/x.geojson");
  expect(fetchSpy.mock.calls[1][1].headers).toBeUndefined();
});

it("REV-290 : authFetch lève hors du cœur, sans requête ni lecture du jeton", async () => {
  const fetchSpy = vi.fn().mockResolvedValue(ok());
  vi.stubGlobal("fetch", fetchSpy);
  const getToken = vi.fn().mockReturnValue("tok");
  const base = createBase({ coreUrl: "http://c", getToken });
  for (const url of [
    "https://evil.example/x",
    "http://c.evil.example/v1/x", // hôte voisin
    "http://c:81/v1/x", // autre port = autre origine
    "http://c/v1evil/x", // préfixe de chemin voisin
    "http://c/other", // même origine, hors /v1
    "http://c/v1/../admin", // traversée normalisée hors /v1
    "//evil.example/v1/x", // protocole-relatif
  ]) {
    await expect(base.authFetch(url), url).rejects.toThrow(/not served by the core/);
  }
  expect(fetchSpy).not.toHaveBeenCalled();
  expect(getToken).not.toHaveBeenCalled();
});

it("REV-290 : authFetch accepte l'URL absolue du cœur et l'URL relative résolue contre lui", async () => {
  const fetchSpy = vi.fn().mockResolvedValue(ok());
  vi.stubGlobal("fetch", fetchSpy);
  const base = createBase({ coreUrl: "http://c", getToken: () => "tok" });
  await base.authFetch("http://c/v1/items?x=1");
  await base.authFetch("/v1/items");
  expect(fetchSpy.mock.calls[0][0]).toBe("http://c/v1/items?x=1");
  expect(fetchSpy.mock.calls[1][0]).toBe("http://c/v1/items");
  for (const call of fetchSpy.mock.calls) {
    expect((call[1].headers as Headers).get("Authorization")).toBe("Bearer tok");
  }
});

it("REV-290 : fetchUrl authenticated vers un hôte tiers est refusé (jamais de jeton hors cœur)", async () => {
  const fetchSpy = vi.fn().mockResolvedValue(ok());
  vi.stubGlobal("fetch", fetchSpy);
  const base = createBase({ coreUrl: "http://c", getToken: () => "tok" });
  await expect(
    base.fetchUrl("http://evil.example/x.geojson", { authenticated: true }),
  ).rejects.toThrow(/not served by the core/);
  expect(fetchSpy).not.toHaveBeenCalled();
});
```

- [ ] **Step 2: Lancer et constater l'échec**

Run: `cd shell && npx vitest run src/api/baseRenew.test.ts`
Expected: FAIL — `REV-290 : authFetch lève hors du cœur…` (la promesse se résout au lieu de rejeter, `fetchSpy` appelé), idem pour `fetchUrl authenticated` ; le test P30.03 adapté et le test « accepte » peuvent déjà passer.

- [ ] **Step 3: Implémenter**

Dans `shell/src/api/base.ts`, ajouter juste après `fetchWithTimeout` (après l'accolade fermante l.~31) :

```ts
// REV-290 : une URL n'est « servie par le cœur » que si, résolue contre
// `coreUrl` (déjà suffixé /v1), elle a la même origine ET un chemin `/v1` ou
// `/v1/…` (le `startsWith` nu acceptait `/v1evil`). Renvoie l'URL résolue (à
// envoyer telle quelle : une URL relative fetchée brute viserait l'origine de
// la page, pas celle du cœur) ou null.
function toCoreHref(coreUrl: string, url: string): string | null {
  try {
    const core = new URL(coreUrl);
    const target = new URL(url, core);
    const base = core.pathname.replace(/\/+$/, "");
    const inBase = target.pathname === base || target.pathname.startsWith(`${base}/`);
    return target.origin === core.origin && inBase ? target.href : null;
  } catch {
    return null;
  }
}
```

Remplacer le corps de `authFetch` (l.328-346) par :

```ts
  async function authFetch(
    url: string,
    init: RequestInit = {},
    timeoutMs?: number,
  ): Promise<Response> {
    // REV-290 : jamais de jeton hors du cœur — on lève AVANT getToken()/fetch.
    const href = toCoreHref(coreUrl, url);
    if (href === null) {
      throw new Error(`authFetch: URL not served by the core, refused: ${url}`);
    }
    const send = (tok: string | undefined) => {
      const headers = new Headers(init.headers);
      if (tok) headers.set("Authorization", `Bearer ${tok}`);
      return fetchWithTimeout(href, { ...init, headers }, timeoutMs);
    };
    const token = getToken();
    let res = await send(token);
    if (res.status === 401 && token && onUnauthorized) {
      const fresh = await renewOnce();
      if (fresh) res = await send(fresh);
    }
    return res;
  }
```

Supprimer la fonction `isCoreServed` (l.445-453) et, dans `fetchGeoJsonPage`, remplacer `const res = isCoreServed(url)` par :

```ts
    const res = toCoreHref(coreUrl, url) !== null
```

(la suite `? await authFetch(url, { headers }) : await fetchWithTimeout(url, { headers });` est inchangée).

- [ ] **Step 4: Constater le succès + non-régression du client**

Run: `cd shell && npx vitest run src/api src/map`
Expected: PASS (tous). Si un test d'`itemClient.test.ts` ou `src/map` échoue avec `not served by the core`, c'est un appelant à URL non-cœur : le corriger (URL `https://core.test/v1/…`) — ne jamais assouplir `toCoreHref`.

- [ ] **Step 5: Commit**

```bash
cd /home/lenen/projets/geostudio && git add shell/src/api/base.ts shell/src/api/baseRenew.test.ts && git commit -m "$(cat <<'EOF'
fix(shell): authFetch lève hors de l'origine du cœur (REV-290)

Le jeton de session ne part plus jamais vers une URL qui n'est pas servie
par le cœur : l'URL est résolue contre coreUrl (origine + chemin /v1) avant
toute lecture du jeton ; fetchUrl authenticated hérite du refus.

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>
EOF
)"
```

---

### Task L2b-2: REV-272(b) — `VITE_CORE_URL` relatif

**Files:**
- Modify: `shell/src/config.ts` (ajout `resolveCoreUrl` avant `loadConfig` ; ligne `coreUrl: merged.VITE_CORE_URL!,` l.53)
- Modify: `shell/src/staticExport/entry.tsx` (import + `buildClient` l.78)
- Test: `shell/src/config.test.ts`

**Interfaces:**
- Produces: `export function resolveCoreUrl(value: string): string` — une valeur commençant par `/` est résolue contre `window.location.origin` (`new URL(value, window.location.origin).href`, slash final retiré) ; toute autre valeur est rendue telle quelle. `loadConfig(...).coreUrl` est donc **toujours absolu** pour une valeur `/…`.
- Pourquoi à la source : toutes les jumelles (`toCoreHref` de L2b-1, `hostedCoreUrl.isHostedCoreUrl`, URL de tuiles/MVT `${coreUrl}/collections/…`, `getCoreUrl()`, `publicThumbnail.ts`, `EmbedPage`/`resolveShareLink`) font `new URL(coreUrl)` qui **lève** sur `/api` → jeton jamais attaché ; en absolu elles marchent sans modification.

- [ ] **Step 1: Écrire les tests qui échouent**

Dans `shell/src/config.test.ts`, ajouter en tête `import { vi } from "vitest";` puis les imports `import { createBase } from "./api/base";` et `import { isHostedCollectionUrl } from "./map/hostedCoreUrl";`, et en fin de fichier :

```ts
test("REV-272b : un VITE_CORE_URL relatif est résolu contre l'origine de la page", () => {
  expect(loadConfig({ ...base, VITE_CORE_URL: "/api" }).coreUrl).toBe(
    `${window.location.origin}/api`,
  );
  expect(loadConfig({ ...base, VITE_CORE_URL: "/api/" }).coreUrl).toBe(
    `${window.location.origin}/api`,
  );
  expect(loadConfig({ ...base, VITE_CORE_URL: "/" }).coreUrl).toBe(window.location.origin);
});

test("REV-272b : une URL absolue reste inchangée (runtime env compris)", () => {
  expect(loadConfig(base).coreUrl).toBe("https://core.test");
  expect(loadConfig(base, { VITE_CORE_URL: "https://prod.example/api" }).coreUrl).toBe(
    "https://prod.example/api",
  );
});

test("REV-272b : le client bâti sur un coreUrl relatif résolu garde le jeton sur les URL du cœur", async () => {
  const { coreUrl } = loadConfig({ ...base, VITE_CORE_URL: "/api" });
  const client = createBase({ coreUrl, getToken: () => "tok" });
  const tile = `${client.coreUrl}/collections/c/tiles/0/0/0.mvt`;
  expect(client.coreUrl).toBe(`${window.location.origin}/api/v1`);
  expect(isHostedCollectionUrl(tile, client.coreUrl)).toBe(true);
  const fetchSpy = vi.fn().mockResolvedValue(new Response("{}"));
  vi.stubGlobal("fetch", fetchSpy);
  try {
    await client.fetchUrl(tile, { authenticated: true });
    expect((fetchSpy.mock.calls[0][1].headers as Headers).get("Authorization")).toBe("Bearer tok");
  } finally {
    vi.unstubAllGlobals();
  }
});
```

- [ ] **Step 2: Constater l'échec**

Run: `cd shell && npx vitest run src/config.test.ts`
Expected: FAIL — `received "/api", expected "http://localhost:3000/api"` (origine jsdom) sur le 1er test ; le 3e échoue (`authFetch: URL not served by the core` car `new URL("/api/v1")` lève).

- [ ] **Step 3: Implémenter**

Dans `shell/src/config.ts`, ajouter avant `export function loadConfig` :

```ts
// REV-272b : `VITE_CORE_URL=/api` (cœur servi sous le même hôte que le shell,
// derrière un reverse-proxy) est une configuration légitime. Toute la chaîne
// aval (`new URL(coreUrl)` dans client/hostedCoreUrl/tuiles) exige une URL
// absolue : on la résout ici, une seule fois, contre l'origine de la page.
export function resolveCoreUrl(value: string): string {
  if (!value.startsWith("/")) return value;
  return new URL(value, window.location.origin).href.replace(/\/+$/, "");
}
```

et remplacer `coreUrl: merged.VITE_CORE_URL!,` par `coreUrl: resolveCoreUrl(merged.VITE_CORE_URL!),`.

Dans `shell/src/staticExport/entry.tsx` : ajouter `import { resolveCoreUrl } from "../config";` (grouper avec les imports existants ; `AppConfig` y est déjà importé depuis ce module si c'est le cas — fusionner en `import { resolveCoreUrl, type AppConfig } from "../config";` pour éviter un import dupliqué) et dans `buildClient` :

```ts
    return createItemClient({
      coreUrl: resolveCoreUrl(connection.coreUrl),
      getToken: () => undefined,
    });
```

(`geostudio-connection.json` est écrit par le cœur à l'export ; un chemin relatif y est possible pour un export servi sous le même hôte.)

- [ ] **Step 4: Constater le succès**

Run: `cd shell && npx vitest run src/config.test.ts src/api && npx tsc --noEmit`
Expected: PASS ; `tsc` sans erreur.

- [ ] **Step 5: Commit**

```bash
cd /home/lenen/projets/geostudio && git add shell/src/config.ts shell/src/config.test.ts shell/src/staticExport/entry.tsx && git commit -m "$(cat <<'EOF'
fix(shell): VITE_CORE_URL relatif résolu contre l'origine de la page (REV-272b)

resolveCoreUrl() rend absolu un coreUrl commençant par « / » à la source
(loadConfig et connexion d'export Connecté) : les jumelles qui font
new URL(coreUrl) (isHostedCoreUrl, tuiles, garde authFetch) fonctionnent
sans autre changement.

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>
EOF
)"
```

---

### Task L2b-3: REV-271 — MCP `save_app_config` accepte `expectedVersion` (cœur)

**Files:**
- Modify: `core/app/mcp/tools/configs.py` (`save_app_config` l.170-187)
- Modify: `core/app/configs/routes.py` (docstring de `rollback_config`, l.274-283 — documentation de l'exception, aucun changement de comportement)
- Test: `core/tests/test_mcp_tools_configs.py` (ajout après `test_save_app_config_updates_and_bumps_version`, l.177-189)

**Interfaces:**
- Consumes: `configs_repo.update_config(session, config_id, config, *, tenant_id, expected_version: int | None = None) -> ConfigRead | None` (lève `StaleConfigVersion(current)`) ; `ConfigRead.version` déjà renvoyé par `get_app_config`.
- Produces: outil MCP `save_app_config(itemId: str, config: BuilderConfig, expectedVersion: int | None = None) -> ConfigRead`. `expectedVersion` absent = comportement historique (dernier écrivain gagne). Version périmée → l'outil échoue avec `ValueError("stale version: the config is now at version N; re-read it with get_app_config and retry")` ; rien n'est écrit (le `update_config` lève avant l'écriture, la session est annulée).
- Jumelles (piège n°14) : `rollback_config` REST = sans garde, par décision (action « restaurer » explicite) ; copilote = n'expose pas `save_app_config` ; `pipelines/runtime.py:1087` = écrivain interne.

- [ ] **Step 1: Écrire le test qui échoue**

Ajouter dans `core/tests/test_mcp_tools_configs.py` :

```python
def test_save_app_config_expected_version_guards_stale_writes(app_client):
    item_id, _ = _seed_config(app_client, owner_id=app_client.mock_user.id)

    with app_client:
        read = call_tool(app_client, "get_app_config", {"itemId": item_id})
        assert read["version"] == 1

        # version lue = version courante : accepté, la version avance
        ok = call_tool(
            app_client,
            "save_app_config",
            {"itemId": item_id, "config": _config_body(widget="table"), "expectedVersion": 1},
        )
        assert ok["version"] == 2

        # même version lue rejouée : périmée, refusée, rien n'est écrit
        error_text = call_tool_expecting_error(
            app_client,
            "save_app_config",
            {"itemId": item_id, "config": _config_body(widget="map"), "expectedVersion": 1},
        )
        assert "stale version" in error_text
        assert "version 2" in error_text

        # sans expectedVersion : comportement historique (dernier écrivain gagne)
        last = call_tool(
            app_client,
            "save_app_config",
            {"itemId": item_id, "config": _config_body(widget="list")},
        )
        assert last["version"] == 3

    with app_client.session_factory() as session:
        current = configs_repo.get_config_by_item(session, item_id)
    assert current is not None
    assert current.version == 3
    assert current.config.layout["items"][0]["widget"] == "list"
```

(`BuilderConfig.layout` est un dict libre dans les tests voisins ; si l'attribut est typé, relire via `current.config.model_dump()["layout"]["items"][0]["widget"]`.)

- [ ] **Step 2: Constater l'échec**

Run: `cd core && uv run pytest tests/test_mcp_tools_configs.py -k expected_version -v`
Expected: FAIL — `AssertionError: expected tool save_app_config to error` (l'argument `expectedVersion` est ignoré, la 2ᵉ sauvegarde réussit).

- [ ] **Step 3: Implémenter**

Dans `core/app/mcp/tools/configs.py`, remplacer la signature, la docstring et l'appel à `update_config` de `save_app_config` :

```python
    @server.tool()
    @write_tool
    async def save_app_config(
        ctx: Context,
        itemId: str,
        config: BuilderConfig,
        expectedVersion: int | None = None,
    ) -> ConfigRead:
        """Save (and version) the app/dashboard config for an item — mirrors
        PUT /configs/by-item/{id}. Pass `expectedVersion` (the `version` read
        with get_app_config) to refuse the write when someone else saved in
        between (same guard as the REST If-Match header); omit it to
        overwrite unconditionally."""
```

et, à la place de l'appel actuel :

```python
            try:
                result = configs_repo.update_config(
                    session,
                    existing.id,
                    config,
                    tenant_id=user.tenant_id,
                    expected_version=expectedVersion,
                )
            except configs_repo.StaleConfigVersion as exc:
                raise ValueError(
                    f"stale version: the config is now at version {exc.current}; "
                    "re-read it with get_app_config and retry"
                ) from None
```

Dans `core/app/configs/routes.py`, compléter le commentaire d'en-tête de `rollback_config` (juste après la signature, avant le premier `existing = …`) :

```python
    # REV-271 : volontairement SANS garde If-Match. Restaurer une révision est
    # un geste explicite qui remplace l'état courant par une version choisie
    # dans l'historique ; il ne peut pas « écraser sans le savoir ». Les
    # éditeurs du shell relisent la config (donc la nouvelle version) dans
    # `onRestored` pour que leur prochain PUT porte la bonne version.
```

- [ ] **Step 4: Constater le succès + portes**

Run: `cd core && uv run pytest tests/test_mcp_tools_configs.py tests/test_mcp_configs_privilege_guard.py tests/test_configs_if_match.py -v && uv run ruff check app/mcp/tools/configs.py app/configs/routes.py && uv run ruff format --check app/mcp/tools/configs.py app/configs/routes.py && uv run lint-imports`
Expected: PASS ; ruff propre ; `lint-imports` Contracts kept. (Aucune route ni modèle HTTP ne change : pas de régénération OpenAPI.)

- [ ] **Step 5: Commit**

```bash
cd /home/lenen/projets/geostudio && git add core/app/mcp/tools/configs.py core/app/configs/routes.py core/tests/test_mcp_tools_configs.py && git commit -m "$(cat <<'EOF'
fix(core): save_app_config accepte expectedVersion et refuse une écriture périmée (REV-271)

Même garde que l'en-tête If-Match de PUT /configs, transmise à update_config ;
sans expectedVersion le comportement historique est conservé. Exception
documentée : rollback_config reste sans garde (restauration explicite).

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>
EOF
)"
```

---

### Task L2b-4: REV-271 — socle shell commun (en-tête `If-Match`, détection du 412, avis de conflit)

**Files:**
- Create: `shell/src/api/ifMatch.ts`, `shell/src/api/ifMatch.test.ts`
- Modify: `shell/src/api/ApiError.ts` (ajout de `isConflictError` en fin de fichier)
- Create: `shell/src/builder/SaveConflictNotice.tsx`, `shell/src/builder/SaveConflictNotice.test.tsx`
- Modify: `shell/src/i18n/catalog.fr.ts` (après `"common.save": "Enregistrer",` l.460)
- Modify: `shell/src/api/domains/apps.ts` (l.~110 : utiliser le helper)
- Modify: `shell/src/pages/AppBuilderPage.tsx` (import l.51, `isConflict` l.136, bloc JSX du conflit ~l.631-648)

**Interfaces:**
- Produces:
  - `ifMatchHeader(baseVersion: number | undefined): Record<string, string> | undefined` — `{ "If-Match": '"3"' }` ou `undefined` (à passer en 5ᵉ argument `extraHeaders` de `base.request`).
  - `isConflictError(err: unknown): err is ApiError` — `ApiError` de statut 412.
  - `SaveConflictNotice({ onReload, message?, reloadLabel? })` — `<div role="alert">` message + bouton « Recharger la dernière version » (clés `common.saveConflict` / `common.saveConflictReload`).
- Convention commune à tous les éditeurs (L2b-5…9) : le domaine lit `version` du `GET /configs/by-item/{pk}` dans un champ `baseVersion?: number` du payload ; l'éditeur le garde dans un `useRef` (jamais dans l'état d'annulation), l'envoie à l'enregistrement, le remplace par la version renvoyée par le `PUT`, et sur 412 affiche `SaveConflictNotice` dont `onReload` relit la config, remplace le brouillon et la version.

- [ ] **Step 1: Écrire les tests qui échouent**

`shell/src/api/ifMatch.test.ts` :

```ts
// SPDX-License-Identifier: Apache-2.0
import { expect, test } from "vitest";
import { ifMatchHeader } from "./ifMatch";

test("ifMatchHeader : version connue → If-Match entre guillemets ; inconnue → aucun en-tête", () => {
  expect(ifMatchHeader(3)).toEqual({ "If-Match": '"3"' });
  expect(ifMatchHeader(0)).toEqual({ "If-Match": '"0"' });
  expect(ifMatchHeader(undefined)).toBeUndefined();
});
```

`shell/src/builder/SaveConflictNotice.test.tsx` :

```tsx
// SPDX-License-Identifier: Apache-2.0
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, test, vi } from "vitest";
import { ApiError, isConflictError } from "../api/ApiError";
import { t } from "../i18n";
import { SaveConflictNotice } from "./SaveConflictNotice";

test("isConflictError ne reconnaît que le 412", () => {
  expect(isConflictError(new ApiError(412, { detail: "stale" }))).toBe(true);
  expect(isConflictError(new ApiError(422))).toBe(false);
  expect(isConflictError(new Error("x"))).toBe(false);
  expect(isConflictError(undefined)).toBe(false);
});

test("SaveConflictNotice annonce le conflit (role=alert) et déclenche le rechargement", async () => {
  const onReload = vi.fn();
  render(<SaveConflictNotice onReload={onReload} />);
  expect(screen.getByRole("alert")).toHaveTextContent(t("common.saveConflict"));
  await userEvent.click(screen.getByRole("button", { name: t("common.saveConflictReload") }));
  expect(onReload).toHaveBeenCalledTimes(1);
});

test("SaveConflictNotice accepte un message et un libellé propres à l'éditeur", () => {
  render(<SaveConflictNotice onReload={() => {}} message="Autre texte" reloadLabel="Relire" />);
  expect(screen.getByText("Autre texte")).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Relire" })).toBeInTheDocument();
});
```

- [ ] **Step 2: Constater l'échec**

Run: `cd shell && npx vitest run src/api/ifMatch.test.ts src/builder/SaveConflictNotice.test.tsx`
Expected: FAIL — modules `./ifMatch` / `./SaveConflictNotice` introuvables, `isConflictError` non exporté.

- [ ] **Step 3: Implémenter**

`shell/src/api/ifMatch.ts` :

```ts
// SPDX-License-Identifier: Apache-2.0
// P09.04/REV-271 : `If-Match: "<version lue>"` fait refuser (412) par le cœur
// une écriture de config issue d'une version périmée. `undefined` = client
// qui ne connaît pas de version (historique) : pas d'en-tête, dernier
// écrivain gagne. À passer en `extraHeaders` de `base.request`.
export function ifMatchHeader(baseVersion: number | undefined): Record<string, string> | undefined {
  return baseVersion === undefined ? undefined : { "If-Match": `"${baseVersion}"` };
}
```

Fin de `shell/src/api/ApiError.ts` :

```ts

// REV-271 : 412 = le cœur a refusé une écriture dont `If-Match` n'est plus la
// version courante (conflit d'édition) — distinct d'un échec d'enregistrement.
export function isConflictError(err: unknown): err is ApiError {
  return err instanceof ApiError && err.status === 412;
}
```

`shell/src/builder/SaveConflictNotice.tsx` :

```tsx
// SPDX-License-Identifier: Apache-2.0
import { Button } from "../ui/kit/Button";
import { t } from "../i18n";

// UX de conflit 412 commune à tous les éditeurs de config (extraite du
// builder d'app, commit 5ed004d1) : message accessible + « Recharger ».
export function SaveConflictNotice({
  onReload,
  message,
  reloadLabel,
}: {
  onReload: () => void;
  message?: string;
  reloadLabel?: string;
}) {
  return (
    <div role="alert" className="flex flex-col gap-1 text-sm text-danger">
      <span>{message ?? t("common.saveConflict")}</span>
      <Button size="sm" variant="outline" className="w-fit" onClick={onReload}>
        {reloadLabel ?? t("common.saveConflictReload")}
      </Button>
    </div>
  );
}
```

`shell/src/i18n/catalog.fr.ts`, après `"common.save": "Enregistrer",` :

```ts
  "common.saveConflict":
    "Cet objet a été modifié ailleurs depuis votre ouverture : votre enregistrement a été refusé pour ne pas écraser ces changements.",
  "common.saveConflictReload": "Recharger la dernière version",
```

`shell/src/api/domains/apps.ts` : `import { ifMatchHeader } from "../ifMatch";` et remplacer l'argument
`config.baseVersion === undefined ? undefined : { "If-Match": \`"${config.baseVersion}"\` },` par `ifMatchHeader(config.baseVersion),`.

`shell/src/pages/AppBuilderPage.tsx` : remplacer `import { ApiError } from "../api/ApiError";` par `import { isConflictError } from "../api/ApiError";` et ajouter `import { SaveConflictNotice } from "../builder/SaveConflictNotice";` ; remplacer `const isConflict = save.error instanceof ApiError && save.error.status === 412;` par `const isConflict = isConflictError(save.error);` ; remplacer le bloc `{isConflict && ( <div role="alert" …> … </div> )}` par :

```tsx
                  {isConflict && (
                    <SaveConflictNotice
                      message={t("appBuilder.conflict")}
                      reloadLabel={t("appBuilder.conflictReload")}
                      onReload={() =>
                        void client.getAppConfig(pk).then((latest) => {
                          resetDraft(latest);
                          baseVersionRef.current = latest.baseVersion;
                          save.reset();
                        })
                      }
                    />
                  )}
```

(`Button` reste utilisé ailleurs dans le fichier ; vérifier `grep -n "Button" shell/src/pages/AppBuilderPage.tsx` avant de toucher aux imports.)

- [ ] **Step 4: Constater le succès (filet = tests existants du builder d'app)**

Run: `cd shell && npx vitest run src/api/ifMatch.test.ts src/builder/SaveConflictNotice.test.tsx src/pages/AppBuilderPage.test.tsx src/api/itemClient.test.ts -t "" && npx tsc --noEmit`
Expected: PASS, dont `shows a conflict message and reloads the latest version on a 412 (P09.05)` et `saveAppConfig sends the loaded version as If-Match…` (non-régression de la refactorisation) ; `tsc` propre.

- [ ] **Step 5: Commit**

```bash
cd /home/lenen/projets/geostudio && git add shell/src/api/ifMatch.ts shell/src/api/ifMatch.test.ts shell/src/api/ApiError.ts shell/src/builder/SaveConflictNotice.tsx shell/src/builder/SaveConflictNotice.test.tsx shell/src/i18n/catalog.fr.ts shell/src/api/domains/apps.ts shell/src/pages/AppBuilderPage.tsx && git commit -m "$(cat <<'EOF'
feat(shell): socle commun du conflit 412 — ifMatchHeader, isConflictError, SaveConflictNotice (REV-271)

Extrait l'UX de conflit du builder d'app (5ed004d1) en composant partagé et
factorise l'en-tête If-Match ; le builder d'app les consomme, comportement
inchangé.

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>
EOF
)"
```

---

### Task L2b-5: REV-271 — cartes (`domains/layers.ts` + `MapEditorPage`)

**Files:**
- Modify: `shell/src/api/types.ts` (`MapConfig` l.352-358 ; `ItemClient.saveMapConfig` l.578)
- Modify: `shell/src/api/domains/layers.ts` (`getMapConfig` l.~65-115 ; `saveMapConfig` l.120-127 ; import `ifMatchHeader`)
- Modify: `shell/src/pages/MapEditorPage.tsx` (imports ; refs ; effet l.80-82 ; `onRestored` l.286 ; bouton Enregistrer l.290-302)
- Test: `shell/src/api/itemClient.test.ts` (fin de fichier), `shell/src/pages/MapEditorPage.test.tsx` (après `"surfaces a save failure"` l.270-280)

**Interfaces:**
- `MapConfig.baseVersion?: number` — « version serveur lue au chargement, jamais persistée dans le corps ».
- `getMapConfig(pk): Promise<MapConfig>` renseigne `baseVersion` = `version` du `ConfigRead` (**chemin de lecture, piège n°5** : sans ce champ la version ne survit pas au rechargement de l'éditeur).
- `saveMapConfig(pk, config): Promise<number | undefined>` — envoie `If-Match: "<config.baseVersion>"` si défini, retire `baseVersion` du corps, renvoie la nouvelle `version`. Un 412 remonte en `ApiError(412)`.

- [ ] **Step 1: Écrire les tests qui échouent**

Fin de `shell/src/api/itemClient.test.ts` :

```ts
test("REV-271 : getMapConfig expose la version lue ; saveMapConfig l'envoie en If-Match, ne la persiste pas et rend la nouvelle ; 412 → ApiError", async () => {
  let ifMatch: string | null = "unset";
  let body: any;
  server.use(
    http.get("https://core.test/v1/configs/by-item/77", () =>
      HttpResponse.json({
        id: "cfg-1",
        itemId: "77",
        kind: "map",
        version: 3,
        config: {
          kind: "map",
          map: { basemap: { style: "s" }, view: { center: [0, 0], zoom: 3 }, layers: [] },
        },
      }),
    ),
    http.put("https://core.test/v1/configs/by-item/77", async ({ request }) => {
      ifMatch = request.headers.get("If-Match");
      body = await request.json();
      return HttpResponse.json({ id: "cfg-1", itemId: "77", kind: "map", version: 4 });
    }),
  );
  const client = makeClient();
  const loaded = await client.getMapConfig("77");
  expect(loaded.baseVersion).toBe(3);
  expect(await client.saveMapConfig("77", loaded)).toBe(4);
  expect(ifMatch).toBe('"3"');
  expect("baseVersion" in body).toBe(false);
  expect("baseVersion" in body.map).toBe(false);
  // client sans version connue : pas d'en-tête (dernier écrivain gagne)
  await client.saveMapConfig("77", { ...loaded, baseVersion: undefined });
  expect(ifMatch).toBeNull();
  server.use(
    http.put("https://core.test/v1/configs/by-item/77", () =>
      HttpResponse.json(
        { title: "Precondition Failed", detail: "stale version: the config is now at version 5" },
        { status: 412 },
      ),
    ),
  );
  await expect(client.saveMapConfig("77", loaded)).rejects.toMatchObject({ status: 412 });
});
```

`shell/src/pages/MapEditorPage.test.tsx`, après le test `"surfaces a save failure"` :

```tsx
test("REV-271 : envoie la version lue à l'enregistrement puis celle que le cœur renvoie", async () => {
  const saveMapConfig = vi.fn().mockResolvedValueOnce(4).mockResolvedValueOnce(5);
  renderEditor({
    getMapConfig: vi
      .fn()
      .mockResolvedValueOnce({ ...config, baseVersion: 3 })
      .mockResolvedValueOnce({ ...config, baseVersion: 4 })
      .mockResolvedValue({ ...config, baseVersion: 5 }),
    saveMapConfig,
    listLayerSources: vi.fn().mockResolvedValue([]),
  });
  await screen.findAllByText("Couche A");
  await userEvent.click(screen.getByRole("button", { name: "Enregistrer" }));
  await waitFor(() => expect(saveMapConfig).toHaveBeenCalledTimes(1));
  expect(saveMapConfig.mock.calls[0][1].baseVersion).toBe(3);
  await userEvent.click(screen.getByRole("button", { name: "Enregistrer" }));
  await waitFor(() => expect(saveMapConfig).toHaveBeenCalledTimes(2));
  expect(saveMapConfig.mock.calls[1][1].baseVersion).toBe(4);
});

test("REV-271 : un 412 affiche le conflit ; « Recharger » reprend la dernière version du cœur", async () => {
  const saveMapConfig = vi
    .fn()
    .mockRejectedValueOnce(new ApiError(412, { detail: "stale" }))
    .mockResolvedValue(8);
  renderEditor({
    getMapConfig: vi
      .fn()
      .mockResolvedValueOnce({ ...config, baseVersion: 1 })
      .mockResolvedValue({ ...config, baseVersion: 7 }),
    saveMapConfig,
    listLayerSources: vi.fn().mockResolvedValue([]),
  });
  await screen.findAllByText("Couche A");
  await userEvent.click(screen.getByRole("button", { name: "Enregistrer" }));
  await screen.findByText(t("common.saveConflict"));
  expect(screen.queryByText(/échec de l'enregistrement/i)).toBeNull();
  await userEvent.click(screen.getByRole("button", { name: t("common.saveConflictReload") }));
  await waitFor(() => expect(screen.queryByText(t("common.saveConflict"))).toBeNull());
  await userEvent.click(screen.getByRole("button", { name: "Enregistrer" }));
  await waitFor(() => expect(saveMapConfig).toHaveBeenCalledTimes(2));
  expect(saveMapConfig.mock.calls[1][1].baseVersion).toBe(7);
});
```

- [ ] **Step 2: Constater l'échec**

Run: `cd shell && npx vitest run src/api/itemClient.test.ts src/pages/MapEditorPage.test.tsx -t "REV-271"`
Expected: FAIL — `loaded.baseVersion` `undefined` (domaine) ; `baseVersion` `undefined` dans les appels de page ; `Unable to find an element with the text: Cet objet a été modifié ailleurs…`.

- [ ] **Step 3: Implémenter**

`shell/src/api/types.ts` — dans `MapConfig` ajouter :

```ts
  // Version serveur lue au chargement (REV-271) : renvoyée en `If-Match` à
  // l'enregistrement pour que le cœur refuse (412) une écriture périmée.
  // Jamais persistée dans le corps de la config.
  baseVersion?: number;
```
et `saveMapConfig(pk: string, config: MapConfig): Promise<number | undefined>;`.

`shell/src/api/domains/layers.ts` : `import { ifMatchHeader } from "../ifMatch";` ; dans le type de la réponse de `getMapConfig`, ajouter `version?: number;` au même niveau que `config?:` ; dans l'objet retourné ajouter `baseVersion: data.version,` (après `printLayout`) ; remplacer `saveMapConfig` par :

```ts
    async saveMapConfig(pk: string, config: MapConfig): Promise<number | undefined> {
      const { printLayout, baseVersion, ...map } = config;
      const saved = await request<{ version?: number }>(
        "PUT",
        `/configs/by-item/${pk}`,
        { version: 1, kind: "map", map, printLayout: printLayout ?? null },
        undefined,
        ifMatchHeader(baseVersion),
      );
      return saved?.version;
    },
```

`shell/src/pages/MapEditorPage.tsx` :
1. `import { ConfigHistoryPanel } …` → ajouter `import { isConflictError } from "../api/ApiError";` et `import { SaveConflictNotice } from "../builder/SaveConflictNotice";`.
2. Après `const [draft, setDraft] = useState<MapConfig | null>(null);` ajouter `const baseVersionRef = useRef<number | undefined>(undefined);`.
3. Remplacer l'effet `if (query.data) setDraft(query.data);` (l.80-82) par :

```tsx
  useEffect(() => {
    if (query.data) {
      setDraft(query.data);
      // Le brouillon EST l'état serveur à cette version (cet effet réécrase
      // le brouillon à chaque nouvelle donnée) : la version suit.
      baseVersionRef.current = query.data.baseVersion;
    }
  }, [query.data]);
```
4. Juste avant le `return (` final du composant (après les gardes de chargement), ajouter :

```tsx
  const isConflict = isConflictError(save.error);
  async function reloadLatest() {
    const latest = await client.getMapConfig(pk);
    setDraft(latest);
    baseVersionRef.current = latest.baseVersion;
    setHasUnsavedChanges(false);
    save.reset();
  }
```
5. `onRestored` :

```tsx
                onRestored={async () => {
                  const restored = await client.getMapConfig(pk);
                  updateDraft(restored);
                  baseVersionRef.current = restored.baseVersion;
                }}
```
6. Bouton et alertes :

```tsx
                onClick={() =>
                  save.mutate(
                    { ...draft, baseVersion: baseVersionRef.current },
                    {
                      onSuccess: (version) => {
                        baseVersionRef.current = version;
                        setHasUnsavedChanges(false);
                      },
                    },
                  )
                }
```
puis `{save.isError && !isConflict && ( <p role="alert" …>{t("actions.saveFailed")}</p> )}` suivi de `{isConflict && <SaveConflictNotice onReload={() => void reloadLatest()} />}`.

- [ ] **Step 4: Constater le succès**

Run: `cd shell && npx vitest run src/api/itemClient.test.ts src/pages/MapEditorPage.test.tsx && npx tsc --noEmit`
Expected: PASS (dont les tests historiques `loads the config and saves edits`, `saving after only changing a layer keeps…`) ; `tsc` propre (les clients `Desktop`/`Static` renvoient `unsupported()` : `Promise<never>` compatible).

- [ ] **Step 5: Commit**

```bash
cd /home/lenen/projets/geostudio && git add shell/src/api/types.ts shell/src/api/domains/layers.ts shell/src/pages/MapEditorPage.tsx shell/src/pages/MapEditorPage.test.tsx shell/src/api/itemClient.test.ts && git commit -m "$(cat <<'EOF'
fix(shell): l'éditeur de carte envoie la version lue et gère le conflit 412 (REV-271)

getMapConfig expose baseVersion, saveMapConfig envoie If-Match et rend la
nouvelle version ; MapEditorPage suit la version et affiche l'avis de
conflit commun avec « Recharger ».

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>
EOF
)"
```

---

### Task L2b-6: REV-271 — datasets (`domains/datasets.ts` + `DatasetEditPage` + cache après rollback)

**Files:**
- Modify: `shell/src/api/types.ts` (`DatasetConfig` l.866-884 ; `ItemClient.saveDatasetConfig` l.627)
- Modify: `shell/src/api/base.ts` (`ResolvedDataset` l.~163 : champ `version?: number` ; `resolveDataset` : type de réponse + `resolved`)
- Modify: `shell/src/api/domains/datasets.ts` (`getDatasetConfig` l.225-246 ; `saveDatasetConfig` l.250-268 ; import `ifMatchHeader`)
- Modify: `shell/src/api/domains/items.ts` (`rollbackConfig` l.268-271)
- Modify: `shell/src/pages/DatasetEditPage.tsx` (import `useRef` l.2 ; effet de seed l.45-47 ; `onRestored` l.336 ; bouton l.355-362)
- Test: `shell/src/api/itemClient.test.ts`, `shell/src/pages/DatasetEditPage.test.tsx`

**Interfaces:**
- `DatasetConfig = (… | …) & { baseVersion?: number }` ; `ResolvedDataset.version?: number`.
- `getDatasetConfig` → `baseVersion` = version du `resolveDataset` (cache 5 min) ; `saveDatasetConfig` → `Promise<number | undefined>`, envoie `If-Match`, **met à jour le cache avec la nouvelle version** (sinon la lecture suivante, servie par le cache, rendrait l'ancienne version) ; `rollbackConfig` invalide désormais `datasetCache[pk]` (bug latent : `onRestored` relisait le cache d'avant rollback).
- Piège : l'éditeur ne seed son brouillon qu'**une fois** (`d ?? configQuery.data`) ⇒ la version se pose une fois (comme `AppBuilderPage`), et « Recharger » doit invalider le cache dataset avant de relire (`client.invalidateDatasetCache(pk)`).

- [ ] **Step 1: Écrire les tests qui échouent**

Fin de `shell/src/api/itemClient.test.ts` :

```ts
test("REV-271 : getDatasetConfig expose la version, saveDatasetConfig l'envoie en If-Match et la met en cache ; rollbackConfig invalide le cache", async () => {
  let reads = 0;
  let ifMatch: string | null = "unset";
  server.use(
    http.get("https://core.test/v1/configs/by-item/ds-71", () => {
      reads += 1;
      return HttpResponse.json({
        id: "cfg-ds71",
        itemId: "ds-71",
        kind: "dataset",
        version: reads,
        config: { kind: "dataset", dataset: { source: "collection", collectionId: "parcs" } },
      });
    }),
    http.put("https://core.test/v1/configs/by-item/ds-71", async ({ request }) => {
      ifMatch = request.headers.get("If-Match");
      return HttpResponse.json({ id: "cfg-ds71", itemId: "ds-71", kind: "dataset", version: 10 });
    }),
    http.post("https://core.test/v1/configs/cfg-ds71/rollback", () =>
      HttpResponse.json({ id: "cfg-ds71", itemId: "ds-71", kind: "dataset", version: 11 }),
    ),
  );
  const client = makeClient();
  const loaded = await client.getDatasetConfig("ds-71");
  expect(loaded.baseVersion).toBe(1);
  expect(await client.saveDatasetConfig("ds-71", loaded)).toBe(10);
  expect(ifMatch).toBe('"1"');
  // la lecture suivante (cache) voit la version écrite, pas l'ancienne
  expect((await client.getDatasetConfig("ds-71")).baseVersion).toBe(10);
  expect(reads).toBe(1);
  // rollbackConfig relit by-item (reads=2) puis invalide le cache dataset
  await client.rollbackConfig("ds-71", 1);
  expect((await client.getDatasetConfig("ds-71")).baseVersion).toBe(3);
  // le corps PUT ne contient jamais baseVersion
  let body: any;
  server.use(
    http.put("https://core.test/v1/configs/by-item/ds-71", async ({ request }) => {
      body = await request.json();
      return HttpResponse.json({ version: 12 });
    }),
  );
  await client.saveDatasetConfig("ds-71", loaded);
  expect("baseVersion" in body.dataset).toBe(false);
});
```

`shell/src/pages/DatasetEditPage.test.tsx` — ajouter `import { ApiError } from "../api/ApiError";` en tête, puis en fin de fichier :

```tsx
test("REV-271 : envoie la version lue puis celle que le cœur renvoie", async () => {
  const saveDatasetConfig = vi.fn().mockResolvedValueOnce(4).mockResolvedValueOnce(5);
  renderPage({
    getItem: vi.fn().mockResolvedValue(item),
    getDatasetConfig: vi.fn().mockResolvedValue({ ...datasetConfig, baseVersion: 3 }),
    getCollectionSchema: vi.fn().mockResolvedValue(schema),
    saveDatasetConfig,
  });
  await screen.findByLabelText("Libellé de nom");
  await userEvent.click(screen.getByRole("button", { name: "Enregistrer les colonnes" }));
  await waitFor(() => expect(saveDatasetConfig).toHaveBeenCalledTimes(1));
  expect(saveDatasetConfig.mock.calls[0][1].baseVersion).toBe(3);
  await userEvent.click(screen.getByRole("button", { name: "Enregistrer les colonnes" }));
  await waitFor(() => expect(saveDatasetConfig).toHaveBeenCalledTimes(2));
  expect(saveDatasetConfig.mock.calls[1][1].baseVersion).toBe(4);
});

test("REV-271 : un 412 affiche le conflit ; « Recharger » invalide le cache dataset et reprend la version du cœur", async () => {
  const saveDatasetConfig = vi
    .fn()
    .mockRejectedValueOnce(new ApiError(412, { detail: "stale" }))
    .mockResolvedValue(8);
  const invalidateDatasetCache = vi.fn();
  const getDatasetConfig = vi
    .fn()
    .mockResolvedValueOnce({ ...datasetConfig, baseVersion: 1 })
    .mockResolvedValue({ ...datasetConfig, baseVersion: 7 });
  renderPage({
    getItem: vi.fn().mockResolvedValue(item),
    getDatasetConfig,
    invalidateDatasetCache,
    getCollectionSchema: vi.fn().mockResolvedValue(schema),
    saveDatasetConfig,
  });
  await screen.findByLabelText("Libellé de nom");
  await userEvent.click(screen.getByRole("button", { name: "Enregistrer les colonnes" }));
  await screen.findByText(t("common.saveConflict"));
  await userEvent.click(screen.getByRole("button", { name: t("common.saveConflictReload") }));
  await waitFor(() => expect(screen.queryByText(t("common.saveConflict"))).toBeNull());
  expect(invalidateDatasetCache).toHaveBeenCalledWith("ds-1");
  await userEvent.click(screen.getByRole("button", { name: "Enregistrer les colonnes" }));
  await waitFor(() => expect(saveDatasetConfig).toHaveBeenCalledTimes(2));
  expect(saveDatasetConfig.mock.calls[1][1].baseVersion).toBe(7);
});
```

- [ ] **Step 2: Constater l'échec**

Run: `cd shell && npx vitest run src/api/itemClient.test.ts src/pages/DatasetEditPage.test.tsx -t "REV-271"`
Expected: FAIL — `loaded.baseVersion` `undefined` ; page : `baseVersion` `undefined`, texte de conflit introuvable.

- [ ] **Step 3: Implémenter**

`types.ts` : transformer la déclaration en `export type DatasetConfig = (| { source: "collection"; … } | { source: "arcgis"; … }) & { baseVersion?: number };` (conserver les deux membres existants tels quels, avec le commentaire `// Version serveur lue au chargement (REV-271) — jamais persistée.`), et `saveDatasetConfig(pk: string, config: DatasetConfig): Promise<number | undefined>;`.

`base.ts` : dans `ResolvedDataset` ajouter `version?: number;` ; dans le type de réponse de `resolveDataset` ajouter `version?: number;` au même niveau que `config?:` ; dans l'objet `resolved` ajouter `version: data.version,`.

`domains/datasets.ts` : `import { ifMatchHeader } from "../ifMatch";` ; dans les deux `return` de `getDatasetConfig` ajouter `baseVersion: resolved.version,` ; remplacer `saveDatasetConfig` par :

```ts
    async saveDatasetConfig(pk: string, config: DatasetConfig): Promise<number | undefined> {
      const { baseVersion, ...dataset } = config;
      const saved = await request<{ version?: number }>(
        "PUT",
        `/configs/by-item/${pk}`,
        { version: 1, kind: "dataset", dataset },
        undefined,
        ifMatchHeader(baseVersion),
      );
      datasetCache.set(pk, {
        source: config.source,
        collectionId: config.source === "collection" ? config.collectionId : null,
        arcgisItemId: config.source === "arcgis" ? config.arcgisItemId : null,
        columns: config.columns,
        timeField: config.timeField ?? null,
        reactsToExtent: config.reactsToExtent ?? false,
        crossFilterLinks: config.crossFilterLinks ?? [],
        sourcePipelineId: config.sourcePipelineId ?? null,
        version: saved?.version,
      });
      return saved?.version;
    },
```

`domains/items.ts`, `rollbackConfig` :

```ts
    async rollbackConfig(pk: string, version: number): Promise<void> {
      const { id } = await request<{ id: string }>("GET", `/configs/by-item/${pk}`);
      await request<unknown>("POST", `/configs/${id}/rollback`, { version });
      // REV-271 : le cache dataset (5 min) porte l'ancien contenu ET l'ancienne
      // version — sans cette invalidation `onRestored` relirait l'état d'avant.
      base.invalidateDatasetCache(pk);
    },
```

`DatasetEditPage.tsx` : `import { useEffect, useRef, useState } from "react";` ; ajouter `import { isConflictError } from "../api/ApiError";` et `import { SaveConflictNotice } from "../builder/SaveConflictNotice";` ; après la déclaration de `draft` :

```tsx
  const baseVersionRef = useRef<number | undefined>(undefined);
  const versionSeededRef = useRef(false);
```
remplacer l'effet de seed par :

```tsx
  useEffect(() => {
    if (!configQuery.data) return;
    setDraft((d) => d ?? configQuery.data);
    // Le brouillon n'est seedé qu'une fois : la version de base est celle du
    // chargement initial, jamais celle d'un refetch (cf. AppBuilderPage).
    if (!versionSeededRef.current) {
      versionSeededRef.current = true;
      baseVersionRef.current = configQuery.data.baseVersion;
    }
  }, [configQuery.data]);
```
après `const readOnly = …` ajouter :

```tsx
  const isConflict = isConflictError(save.error);
  async function reloadLatest() {
    client.invalidateDatasetCache(pk); // sinon getDatasetConfig relit le cache (5 min)
    const latest = await client.getDatasetConfig(pk);
    setDraft(latest);
    baseVersionRef.current = latest.baseVersion;
    setHasUnsavedChanges(false);
    save.reset();
  }
```
`onRestored` :

```tsx
                onRestored={async () => {
                  const restored = await client.getDatasetConfig(pk);
                  updateDraft(restored);
                  baseVersionRef.current = restored.baseVersion;
                }}
```
bouton + alertes :

```tsx
                onClick={() =>
                  save.mutate(
                    { ...draft, baseVersion: baseVersionRef.current },
                    {
                      onSuccess: (version) => {
                        baseVersionRef.current = version;
                        setHasUnsavedChanges(false);
                      },
                    },
                  )
                }
```
`{save.isError && !isConflict && (<p role="alert" …>{t("actions.saveFailed")}</p>)}` puis `{isConflict && <SaveConflictNotice onReload={() => void reloadLatest()} />}`.

- [ ] **Step 4: Constater le succès**

Run: `cd shell && npx vitest run src/api src/pages/DatasetEditPage.test.tsx src/pages/VisualQueryWizardPage.test.tsx && npx tsc --noEmit`
Expected: PASS (le wizard appelle `saveDatasetConfig` sans `baseVersion` : comportement historique inchangé).

- [ ] **Step 5: Commit**

```bash
cd /home/lenen/projets/geostudio && git add shell/src/api/types.ts shell/src/api/base.ts shell/src/api/domains/datasets.ts shell/src/api/domains/items.ts shell/src/pages/DatasetEditPage.tsx shell/src/pages/DatasetEditPage.test.tsx shell/src/api/itemClient.test.ts && git commit -m "$(cat <<'EOF'
fix(shell): l'éditeur de dataset envoie la version lue et gère le conflit 412 (REV-271)

La version traverse le cache dataset (lue, mise à jour à l'écriture) ;
rollbackConfig invalide ce cache (onRestored relisait l'état d'avant) ;
DatasetEditPage affiche l'avis de conflit commun.

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>
EOF
)"
```

---

### Task L2b-7: REV-271 — pipelines (`domains/pipelines.ts` + `PipelineBuilderPage` + client desktop)

**Files:**
- Modify: `shell/src/api/types.ts` (`PipelinePayload` l.1145-1150 ; `ItemClient.savePipelineConfig` l.592)
- Modify: `shell/src/api/domains/pipelines.ts` (`getPipelineConfig` l.58-66 ; `savePipelineConfig` l.68-74 ; `previewPipeline` l.~104-114 ; import)
- Modify: `shell/src/desktop/DesktopItemClient.ts` (`savePipelineConfig` l.92-95)
- Modify: `shell/src/pages/PipelineBuilderPage.tsx` (imports ; refs/état près l.93-110 ; effet de seed l.156-162 ; `onSave` l.355-387 ; `onRestored` l.543 ; zone d'erreur l.~571-575)
- Test: `shell/src/api/itemClient.test.ts`, `shell/src/pages/PipelineBuilderPage.test.tsx`

**Interfaces:**
- `PipelinePayload.baseVersion?: number` ; `getPipelineConfig` → `{ ...pipeline, baseVersion: version }` ; `savePipelineConfig(pk, payload): Promise<number | undefined>` envoie `If-Match` et **retire `baseVersion` du corps** ; `previewPipeline(pk, nodeId, draft?)` **retire aussi `baseVersion`** de `{ pipeline: draft }` (le brouillon l'embarque désormais).
- Le brouillon est annulable (`useUndoableDraft`) : la version vit dans un `useRef` (patron `AppBuilderPage`), jamais lue depuis un état d'annulation.
- Hors périmètre : `VisualQueryWizardPage` (régénère le pipeline depuis son état, `baseVersion` absent → inchangé), `resolvePipelineEditorPath` (lecture seule), `pipelines/runtime.py:1087` (écrivain interne).

- [ ] **Step 1: Écrire les tests qui échouent**

Fin de `shell/src/api/itemClient.test.ts` :

```ts
test("REV-271 : getPipelineConfig expose la version, savePipelineConfig l'envoie en If-Match sans la persister ; previewPipeline ne l'envoie pas", async () => {
  let ifMatch: string | null = "unset";
  let putBody: any;
  let previewBody: any;
  const graph = { nodes: [], edges: [] };
  server.use(
    http.get("https://core.test/v1/configs/by-item/p-71", () =>
      HttpResponse.json({
        id: "cfg-p71",
        itemId: "p-71",
        kind: "pipeline",
        version: 6,
        config: { kind: "pipeline", pipeline: graph },
      }),
    ),
    http.put("https://core.test/v1/configs/by-item/p-71", async ({ request }) => {
      ifMatch = request.headers.get("If-Match");
      putBody = await request.json();
      return HttpResponse.json({ id: "cfg-p71", itemId: "p-71", kind: "pipeline", version: 7 });
    }),
    http.post("https://core.test/v1/pipelines/p-71/preview", async ({ request }) => {
      previewBody = await request.json();
      return HttpResponse.json([]);
    }),
  );
  const client = makeClient();
  const loaded = await client.getPipelineConfig("p-71");
  expect(loaded.baseVersion).toBe(6);
  expect(await client.savePipelineConfig("p-71", loaded)).toBe(7);
  expect(ifMatch).toBe('"6"');
  expect(putBody).toEqual({ version: 1, kind: "pipeline", pipeline: graph });
  await client.previewPipeline("p-71", "n1", loaded);
  expect(previewBody).toEqual({ pipeline: graph });
  await client.savePipelineConfig("p-71", { ...loaded, baseVersion: undefined });
  expect(ifMatch).toBeNull();
});
```

`shell/src/pages/PipelineBuilderPage.test.tsx` — en fin de fichier :

```tsx
const TWO_NODE_GRAPH: PipelinePayload = {
  nodes: [
    {
      id: "r1",
      kind: "reader",
      op: "reader.collection",
      x: 0,
      y: 0,
      params: { collectionId: "villes" },
      title: "Villes",
    },
    {
      id: "w1",
      kind: "writer",
      op: "writer.collection",
      x: 300,
      y: 0,
      params: { collectionId: "villes_propres" },
      title: "Écriture",
    },
  ],
  edges: [{ id: "e1", from: "r1", to: "w1" }],
};

test("REV-271 : envoie la version lue puis celle que le cœur renvoie", async () => {
  const savePipelineConfig = vi.fn().mockResolvedValueOnce(4).mockResolvedValueOnce(5);
  renderPage("p-1", {
    getPipelineConfig: vi.fn().mockResolvedValue({ ...TWO_NODE_GRAPH, baseVersion: 3 }),
    savePipelineConfig,
    listConfigRevisions: vi.fn().mockResolvedValue([]),
  });
  await waitFor(() => expect(screen.getByRole("button", { name: "Enregistrer" })).toBeEnabled());
  await userEvent.click(screen.getByRole("button", { name: "Enregistrer" }));
  await waitFor(() => expect(savePipelineConfig).toHaveBeenCalledTimes(1));
  expect(savePipelineConfig.mock.calls[0][1].baseVersion).toBe(3);
  await userEvent.click(screen.getByRole("button", { name: "Enregistrer" }));
  await waitFor(() => expect(savePipelineConfig).toHaveBeenCalledTimes(2));
  expect(savePipelineConfig.mock.calls[1][1].baseVersion).toBe(4);
});

test("REV-271 : un 412 affiche le conflit ; « Recharger » reprend la version du cœur", async () => {
  const savePipelineConfig = vi
    .fn()
    .mockRejectedValueOnce(new ApiError(412, { detail: "stale" }))
    .mockResolvedValue(8);
  renderPage("p-1", {
    getPipelineConfig: vi
      .fn()
      .mockResolvedValueOnce({ ...TWO_NODE_GRAPH, baseVersion: 1 })
      .mockResolvedValue({ ...TWO_NODE_GRAPH, baseVersion: 7 }),
    savePipelineConfig,
    listConfigRevisions: vi.fn().mockResolvedValue([]),
  });
  await waitFor(() => expect(screen.getByRole("button", { name: "Enregistrer" })).toBeEnabled());
  await userEvent.click(screen.getByRole("button", { name: "Enregistrer" }));
  await screen.findByText(t("common.saveConflict"));
  await userEvent.click(screen.getByRole("button", { name: t("common.saveConflictReload") }));
  await waitFor(() => expect(screen.queryByText(t("common.saveConflict"))).toBeNull());
  await waitFor(() => expect(screen.getByRole("button", { name: "Enregistrer" })).toBeEnabled());
  await userEvent.click(screen.getByRole("button", { name: "Enregistrer" }));
  await waitFor(() => expect(savePipelineConfig).toHaveBeenCalledTimes(2));
  expect(savePipelineConfig.mock.calls[1][1].baseVersion).toBe(7);
});
```

- [ ] **Step 2: Constater l'échec**

Run: `cd shell && npx vitest run src/api/itemClient.test.ts src/pages/PipelineBuilderPage.test.tsx -t "REV-271"`
Expected: FAIL — `loaded.baseVersion` `undefined`, `previewBody` contient `baseVersion`/pas de `If-Match`, texte de conflit introuvable.

- [ ] **Step 3: Implémenter**

`types.ts` : dans `PipelinePayload` ajouter `baseVersion?: number; // version serveur lue (REV-271), jamais persistée` ; `savePipelineConfig(pk: string, payload: PipelinePayload): Promise<number | undefined>;`.

`domains/pipelines.ts` : `import { ifMatchHeader } from "../ifMatch";` ; ajouter au-dessus de `createPipelinesMethods` :

```ts
// `baseVersion` est un détail de transport (If-Match) : jamais dans un corps.
function withoutBaseVersion(payload: PipelinePayload): PipelinePayload {
  const rest = { ...payload };
  delete rest.baseVersion;
  return rest;
}
```
remplacer `getPipelineConfig`, `savePipelineConfig` et l'argument de corps de `previewPipeline` :

```ts
    async getPipelineConfig(pk: string): Promise<PipelinePayload> {
      const data = await request<{ version?: number; config?: { pipeline?: PipelinePayload } }>(
        "GET",
        `/configs/by-item/${pk}`,
      );
      if (!data.config?.pipeline)
        throw new Error("getPipelineConfig: config has no pipeline payload");
      return { ...data.config.pipeline, baseVersion: data.version };
    },

    async savePipelineConfig(pk: string, payload: PipelinePayload): Promise<number | undefined> {
      const saved = await request<{ version?: number }>(
        "PUT",
        `/configs/by-item/${pk}`,
        { version: 1, kind: "pipeline", pipeline: withoutBaseVersion(payload) },
        undefined,
        ifMatchHeader(payload.baseVersion),
      );
      return saved?.version;
    },
```
et dans `previewPipeline` : `draft !== undefined ? { pipeline: withoutBaseVersion(draft) } : undefined,`.

`desktop/DesktopItemClient.ts` :

```ts
    async savePipelineConfig(pk: string, payload: PipelinePayload): Promise<number | undefined> {
      localPayloads.set(pk, payload);
      await sidecarFetch<void>("PUT", `/pipelines/${pk}`, payload);
      return undefined; // le sidecar n'a pas de versionnage de config
    },
```

`PipelineBuilderPage.tsx` : ajouter `import { isConflictError } from "../api/ApiError";` et `import { SaveConflictNotice } from "../builder/SaveConflictNotice";` ; près de `const [saveError, setSaveError] …` :

```tsx
  const baseVersionRef = useRef<number | undefined>(undefined);
  const versionSeededRef = useRef(false);
  const [conflict, setConflict] = useState(false);
```
effet de seed :

```tsx
  useEffect(() => {
    if (pk === null) {
      seedDraft(EMPTY_PAYLOAD);
      return;
    }
    if (configQuery.data) {
      seedDraft(configQuery.data);
      // Version du chargement initial seulement : un refetch (autre onglet) est
      // précisément le conflit que le cœur doit détecter (cf. AppBuilderPage).
      if (!versionSeededRef.current) {
        versionSeededRef.current = true;
        baseVersionRef.current = configQuery.data.baseVersion;
      }
    }
  }, [pk, configQuery.data, seedDraft]);
```
dans `onSave`, remplacer la branche persistée et le `catch` :

```tsx
      const version = await savePipeline.mutateAsync({
        ...currentDraft,
        baseVersion: baseVersionRef.current,
      });
      baseVersionRef.current = version;
      setConflict(false);
      setHasUnsavedChanges(false);
    } catch (e) {
      if (isConflictError(e)) {
        setConflict(true);
        return;
      }
      setSaveError(e instanceof Error ? e.message : t("actions.saveFailed"));
    }
```
ajouter avant `return (` :

```tsx
  async function reloadLatest() {
    if (pk === null) return;
    const latest = await client.getPipelineConfig(pk);
    resetDraft(latest);
    baseVersionRef.current = latest.baseVersion;
    setConflict(false);
  }
```
`onRestored` :

```tsx
                    onRestored={async () => {
                      const restored = await client.getPipelineConfig(pk);
                      resetDraft(restored);
                      baseVersionRef.current = restored.baseVersion;
                    }}
```
et sous le bloc `{saveError && (…)}` ajouter `{conflict && <SaveConflictNotice onReload={() => void reloadLatest()} />}`.

- [ ] **Step 4: Constater le succès**

Run: `cd shell && npx vitest run src/api src/pages/PipelineBuilderPage.test.tsx src/pages/VisualQueryWizardPage.test.tsx src/desktop && npx tsc --noEmit`
Expected: PASS (tests historiques `toHaveBeenCalledWith("p-1", payload)` : `baseVersion: undefined` est ignoré par l'égalité récursive de `toHaveBeenCalledWith`).

- [ ] **Step 5: Commit**

```bash
cd /home/lenen/projets/geostudio && git add shell/src/api/types.ts shell/src/api/domains/pipelines.ts shell/src/desktop/DesktopItemClient.ts shell/src/pages/PipelineBuilderPage.tsx shell/src/pages/PipelineBuilderPage.test.tsx shell/src/api/itemClient.test.ts && git commit -m "$(cat <<'EOF'
fix(shell): l'éditeur de pipeline envoie la version lue et gère le conflit 412 (REV-271)

baseVersion voyage dans le payload lu mais jamais dans un corps (save et
preview le retirent) ; la version vit dans un ref côté éditeur (brouillon
annulable) ; avis de conflit commun avec « Recharger ».

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>
EOF
)"
```

---

### Task L2b-8: REV-271 — rapports planifiés (`domains/reports.ts` + `ReportEditPage`)

**Files:**
- Modify: `shell/src/api/types.ts` (`ReportSchedulePayload` l.1189-1193 ; `ItemClient.saveReportScheduleConfig` l.623)
- Modify: `shell/src/api/domains/reports.ts` (`getReportScheduleConfig` l.~50-57 ; `saveReportScheduleConfig` l.~59-65 ; import)
- Modify: `shell/src/pages/ReportEditPage.tsx` (import `useRef` l.3 ; refs ; effet l.~86-88 ; `onSave` l.~123-131 ; `onRestored` l.182 ; zone d'erreur l.~195-199)
- Test: `shell/src/api/itemClient.test.ts`, `shell/src/pages/ReportEditPage.test.tsx`

**Interfaces:**
- `ReportSchedulePayload.baseVersion?: number` ; `getReportScheduleConfig` → `{ ...report, baseVersion: version }` ; `saveReportScheduleConfig(pk, payload): Promise<number | undefined>` (If-Match, `baseVersion` retiré du corps). Le chemin de création (`pk === null`, `createReportScheduleItem`) n'a jamais de `baseVersion`.
- L'éditeur réécrase son brouillon à chaque nouvelle donnée (`setDraft(configQuery.data)`) : la version suit `configQuery.data` (comme `MapEditorPage`).

- [ ] **Step 1: Écrire les tests qui échouent**

Fin de `shell/src/api/itemClient.test.ts` :

```ts
test("REV-271 : getReportScheduleConfig expose la version, saveReportScheduleConfig l'envoie en If-Match sans la persister", async () => {
  let ifMatch: string | null = "unset";
  let body: any;
  const report = {
    bookmarkItemId: "bm-1",
    refreshPolicy: { enabled: true, cron: "0 8 * * MON" },
    channels: [],
  };
  server.use(
    http.get("https://core.test/v1/configs/by-item/r-71", () =>
      HttpResponse.json({
        id: "cfg-r71",
        itemId: "r-71",
        kind: "report",
        version: 2,
        config: { kind: "report", report },
      }),
    ),
    http.put("https://core.test/v1/configs/by-item/r-71", async ({ request }) => {
      ifMatch = request.headers.get("If-Match");
      body = await request.json();
      return HttpResponse.json({ id: "cfg-r71", itemId: "r-71", kind: "report", version: 3 });
    }),
  );
  const client = makeClient();
  const loaded = await client.getReportScheduleConfig("r-71");
  expect(loaded.baseVersion).toBe(2);
  expect(await client.saveReportScheduleConfig("r-71", loaded)).toBe(3);
  expect(ifMatch).toBe('"2"');
  expect(body).toEqual({ version: 1, kind: "report", report });
  await client.saveReportScheduleConfig("r-71", { ...loaded, baseVersion: undefined });
  expect(ifMatch).toBeNull();
});
```

`shell/src/pages/ReportEditPage.test.tsx` (`ApiError` y est déjà importé), en fin de fichier :

```tsx
const REPORT_PAYLOAD: ReportSchedulePayload = {
  bookmarkItemId: "bm-1",
  refreshPolicy: { enabled: true, cron: "0 8 * * MON" },
  channels: [{ kind: "webhook", url: "" }],
};

test("REV-271 : persisted mode envoie la version lue puis celle que le cœur renvoie", async () => {
  const saveReportScheduleConfig = vi.fn().mockResolvedValueOnce(4).mockResolvedValueOnce(5);
  renderPage("r-1", {
    getItem: vi.fn().mockResolvedValue(item),
    getReportScheduleConfig: vi
      .fn()
      .mockResolvedValueOnce({ ...REPORT_PAYLOAD, baseVersion: 3 })
      .mockResolvedValueOnce({ ...REPORT_PAYLOAD, baseVersion: 4 })
      .mockResolvedValue({ ...REPORT_PAYLOAD, baseVersion: 5 }),
    listConfigRevisions: vi.fn().mockResolvedValue([]),
    saveReportScheduleConfig,
  });
  await userEvent.click(await screen.findByRole("button", { name: "Enregistrer" }));
  await waitFor(() => expect(saveReportScheduleConfig).toHaveBeenCalledTimes(1));
  expect(saveReportScheduleConfig.mock.calls[0][1].baseVersion).toBe(3);
  await userEvent.click(screen.getByRole("button", { name: "Enregistrer" }));
  await waitFor(() => expect(saveReportScheduleConfig).toHaveBeenCalledTimes(2));
  expect(saveReportScheduleConfig.mock.calls[1][1].baseVersion).toBe(4);
});

test("REV-271 : persisted mode — un 412 affiche le conflit ; « Recharger » reprend la version du cœur", async () => {
  const saveReportScheduleConfig = vi
    .fn()
    .mockRejectedValueOnce(new ApiError(412, { detail: "stale" }))
    .mockResolvedValue(8);
  renderPage("r-1", {
    getItem: vi.fn().mockResolvedValue(item),
    getReportScheduleConfig: vi
      .fn()
      .mockResolvedValueOnce({ ...REPORT_PAYLOAD, baseVersion: 1 })
      .mockResolvedValue({ ...REPORT_PAYLOAD, baseVersion: 7 }),
    listConfigRevisions: vi.fn().mockResolvedValue([]),
    saveReportScheduleConfig,
  });
  await userEvent.click(await screen.findByRole("button", { name: "Enregistrer" }));
  await screen.findByText(t("common.saveConflict"));
  await userEvent.click(screen.getByRole("button", { name: t("common.saveConflictReload") }));
  await waitFor(() => expect(screen.queryByText(t("common.saveConflict"))).toBeNull());
  await userEvent.click(screen.getByRole("button", { name: "Enregistrer" }));
  await waitFor(() => expect(saveReportScheduleConfig).toHaveBeenCalledTimes(2));
  expect(saveReportScheduleConfig.mock.calls[1][1].baseVersion).toBe(7);
});
```

- [ ] **Step 2: Constater l'échec**

Run: `cd shell && npx vitest run src/api/itemClient.test.ts src/pages/ReportEditPage.test.tsx -t "REV-271"`
Expected: FAIL — `baseVersion` `undefined` ; conflit introuvable.

- [ ] **Step 3: Implémenter**

`types.ts` : dans `ReportSchedulePayload` ajouter `baseVersion?: number; // version serveur lue (REV-271), jamais persistée` ; `saveReportScheduleConfig(pk: string, payload: ReportSchedulePayload): Promise<number | undefined>;`.

`domains/reports.ts` : `import { ifMatchHeader } from "../ifMatch";` ; remplacer les deux méthodes :

```ts
    async getReportScheduleConfig(pk: string): Promise<ReportSchedulePayload> {
      const data = await request<{ version?: number; config?: { report?: ReportSchedulePayload } }>(
        "GET",
        `/configs/by-item/${pk}`,
      );
      if (!data.config?.report)
        throw new Error("getReportScheduleConfig: config has no report payload");
      return { ...data.config.report, baseVersion: data.version };
    },

    async saveReportScheduleConfig(
      pk: string,
      payload: ReportSchedulePayload,
    ): Promise<number | undefined> {
      const { baseVersion, ...report } = payload;
      const saved = await request<{ version?: number }>(
        "PUT",
        `/configs/by-item/${pk}`,
        { version: 1, kind: "report", report },
        undefined,
        ifMatchHeader(baseVersion),
      );
      return saved?.version;
    },
```

`ReportEditPage.tsx` : `import { useEffect, useRef, useState } from "react";` ; `import { isConflictError } from "../api/ApiError";` ; `import { SaveConflictNotice } from "../builder/SaveConflictNotice";` ; après `const [saveError, …]` :

```tsx
  const baseVersionRef = useRef<number | undefined>(undefined);
  const [conflict, setConflict] = useState(false);
```
effet :

```tsx
  useEffect(() => {
    if (pk !== null && configQuery.data) {
      setDraft(configQuery.data);
      baseVersionRef.current = configQuery.data.baseVersion;
    }
  }, [pk, configQuery.data]);
```
dans `onSave` remplacer `await saveReport.mutateAsync(draft); setHasUnsavedChanges(false);` et le `catch` :

```tsx
      const version = await saveReport.mutateAsync({
        ...draft,
        baseVersion: baseVersionRef.current,
      });
      baseVersionRef.current = version;
      setConflict(false);
      setHasUnsavedChanges(false);
    } catch (e) {
      if (isConflictError(e)) {
        setConflict(true);
        return;
      }
      setSaveError(e instanceof Error ? e.message : t("actions.saveFailed"));
    }
```
(le `setSaveError(null)` initial de `onSave` reste ; ajouter aussi `setConflict(false)` n'est pas nécessaire.) Avant `return (` :

```tsx
  async function reloadLatest() {
    if (pk === null) return;
    const latest = await client.getReportScheduleConfig(pk);
    setDraft(latest);
    baseVersionRef.current = latest.baseVersion;
    setConflict(false);
    setHasUnsavedChanges(false);
  }
```
`onRestored` :

```tsx
                  onRestored={async () => {
                    const restored = await client.getReportScheduleConfig(pk);
                    updateDraft(restored);
                    baseVersionRef.current = restored.baseVersion;
                  }}
```
et sous `{saveError && (…)}` : `{conflict && <SaveConflictNotice onReload={() => void reloadLatest()} />}`.

- [ ] **Step 4: Constater le succès**

Run: `cd shell && npx vitest run src/api src/pages/ReportEditPage.test.tsx && npx tsc --noEmit`
Expected: PASS (`toHaveBeenCalledWith("r-1", payload)` historique reste vert).

- [ ] **Step 5: Commit**

```bash
cd /home/lenen/projets/geostudio && git add shell/src/api/types.ts shell/src/api/domains/reports.ts shell/src/pages/ReportEditPage.tsx shell/src/pages/ReportEditPage.test.tsx shell/src/api/itemClient.test.ts && git commit -m "$(cat <<'EOF'
fix(shell): l'éditeur de rapport planifié envoie la version lue et gère le conflit 412 (REV-271)

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>
EOF
)"
```

---

### Task L2b-9: REV-271 — alertes (domaine seul : aucun éditeur d'alerte existante)

**Files:**
- Modify: `shell/src/api/types.ts` (`AlertRulePayload` l.1160 ; `ItemClient.saveAlertRuleConfig` l.613)
- Modify: `shell/src/api/domains/alerts.ts` (`getAlertRuleConfig` l.~50-56 ; `saveAlertRuleConfig` l.~58-64 ; import)
- Test: `shell/src/api/itemClient.test.ts` (à côté de `saveAlertRuleConfig PUTs…` l.3532)

**Interfaces:**
- `AlertRulePayload.baseVersion?: number` ; `getAlertRuleConfig` → `{ ...alert, baseVersion: version }` ; `saveAlertRuleConfig(pk, payload): Promise<number | undefined>` (If-Match ; `baseVersion` retiré du corps).
- Constat vérifié (piège n°12) : `saveAlertRuleConfig` n'a **aucun appelant UI** (`AlertRuleEditor` ne sait que créer/lister/évaluer ; `getAlertRuleConfig` n'est lu que par `shell/useOpenItem.ts:67` pour naviguer). Le garde est donc posé au niveau client (un futur éditeur d'alerte hérite du patron L2b-4 : `baseVersionRef` + `SaveConflictNotice`) ; **pas de tâche d'éditeur**. `createAlertRuleItem` n'envoie jamais de `baseVersion`.

- [ ] **Step 1: Écrire le test qui échoue**

```ts
test("REV-271 : getAlertRuleConfig expose la version, saveAlertRuleConfig l'envoie en If-Match sans la persister", async () => {
  let ifMatch: string | null = "unset";
  let body: any;
  const alert = {
    datasetItemId: "ds-1",
    query: { agg: "count" },
    condition: { expr: "value > 100" },
    refreshPolicy: { enabled: true, cron: "*/5 * * * *" },
    channels: [{ kind: "webhook" as const, url: "https://example.test/hook" }],
    messageTemplate: "Alert {ruleName}",
  };
  server.use(
    http.get("https://core.test/v1/configs/by-item/a-71", () =>
      HttpResponse.json({
        id: "cfg-a71",
        itemId: "a-71",
        kind: "alert",
        version: 5,
        config: { kind: "alert", alert },
      }),
    ),
    http.put("https://core.test/v1/configs/by-item/a-71", async ({ request }) => {
      ifMatch = request.headers.get("If-Match");
      body = await request.json();
      return HttpResponse.json({ id: "cfg-a71", itemId: "a-71", kind: "alert", version: 6 });
    }),
  );
  const client = makeClient();
  const loaded = await client.getAlertRuleConfig("a-71");
  expect(loaded.baseVersion).toBe(5);
  expect(await client.saveAlertRuleConfig("a-71", loaded)).toBe(6);
  expect(ifMatch).toBe('"5"');
  expect(body).toEqual({ version: 1, kind: "alert", alert });
});
```

- [ ] **Step 2: Constater l'échec**

Run: `cd shell && npx vitest run src/api/itemClient.test.ts -t "REV-271 : getAlertRuleConfig"`
Expected: FAIL — `expected undefined to be 5`.

- [ ] **Step 3: Implémenter**

`types.ts` : dans `AlertRulePayload` ajouter `baseVersion?: number; // version serveur lue (REV-271), jamais persistée` ; `saveAlertRuleConfig(pk: string, payload: AlertRulePayload): Promise<number | undefined>;`.

`domains/alerts.ts` : `import { ifMatchHeader } from "../ifMatch";` ; remplacer :

```ts
    async getAlertRuleConfig(pk: string): Promise<AlertRulePayload> {
      const data = await request<{ version?: number; config?: { alert?: AlertRulePayload } }>(
        "GET",
        `/configs/by-item/${pk}`,
      );
      if (!data.config?.alert) throw new Error("getAlertRuleConfig: config has no alert payload");
      return { ...data.config.alert, baseVersion: data.version };
    },

    async saveAlertRuleConfig(pk: string, payload: AlertRulePayload): Promise<number | undefined> {
      const { baseVersion, ...alert } = payload;
      const saved = await request<{ version?: number }>(
        "PUT",
        `/configs/by-item/${pk}`,
        { version: 1, kind: "alert", alert },
        undefined,
        ifMatchHeader(baseVersion),
      );
      return saved?.version;
    },
```

- [ ] **Step 4: Constater le succès**

Run: `cd shell && npx vitest run src/api src/builder/AlertRuleEditor.test.tsx src/shell && npx tsc --noEmit`
Expected: PASS (le test historique `saveAlertRuleConfig PUTs the alert payload wrapped…` renvoie `{}` : `saved?.version` = `undefined`, ok).

- [ ] **Step 5: Commit**

```bash
cd /home/lenen/projets/geostudio && git add shell/src/api/types.ts shell/src/api/domains/alerts.ts shell/src/api/itemClient.test.ts && git commit -m "$(cat <<'EOF'
fix(shell): le client d'alertes lit la version et envoie If-Match (REV-271)

Aucun éditeur d'alerte existante n'appelle saveAlertRuleConfig : le garde
est posé au niveau du domaine pour le futur éditeur.

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>
EOF
)"
```

---

### Task L2b-10: REV-272(c) — parcours E2E P14.14, lien de partage à échéance (nominal / expiré / révoqué)

**Files:**
- Create: `shell/e2e/journeys/j01/embed-share-link.spec.ts`

**Interfaces:**
- Consumes (existants, vérifiés) : `apiFor("creator")` (`e2e/journeys/j03/api.ts`, jeton Keycloak réel, `Api.get/send`), `mkItem(api, title, config)` / `TAG` / `appConfig()` (`e2e/journeys/j13/helpers.ts`), `psql(sql)` (`e2e/journeys/j02/helpers.ts`, conteneur `geostudio-postgis-1`), `CORE_URL` (`_fixtures/env.ts`). Cœur : `POST /v1/items/{pk}/share-links {ttlDays}` → 201 `{url, expiresAt, token}` ; `GET /v1/items/{pk}/share-links` → `[{id, expiresAt, revoked, …}]` ; `DELETE /v1/items/{pk}/share-links/{id}` → 204 ; `GET /v1/share-links/{token}` public → 200 ou 401 `invalid or expired share link` (`core/app/items/routes.py:365`, `sharing/repository.py:239 get_active_share_link` : ligne révoquée OU `expires_at <= now` ⇒ 401, **avant** le TTL du jeton). Page : `/embed/:token` (`EmbedPage.tsx`) → texte `embed.linkExpiredOrRevoked` en `role="alert"`.
- Échéance « courte » : `ttlDays` minimum = 1 (bornes 1..30, test j13) ⇒ l'échéance est forcée en base (`expires_at` reculé d'une heure), le jeton signé étant par ailleurs encore valide : c'est exactement la vérification « la ligne prime sur le TTL du jeton ».
- Ce parcours suit la convention des journeys d'audit : **stack réelle requise** (`scripts/audit/stack-reset.sh reset --auth oidc`, personas), `playwright.journeys.config.ts`, un worker. Son exécution réelle et la bascule `bug(`→`test(` du lot sont L6 (hors plan) ; ici on livre la spec et on prouve qu'elle compile/est découverte.

- [ ] **Step 1: Écrire la spec (elle ne peut échouer que sur stack)**

`shell/e2e/journeys/j01/embed-share-link.spec.ts` :

```ts
/* eslint-disable @typescript-eslint/no-explicit-any -- corps JSON du cœur, forme libre */
import { test, expect, type Page } from "@playwright/test";
import { CORE_URL } from "../_fixtures/env";
import { apiFor, type Api } from "../j03/api";
import { appConfig, mkItem, TAG } from "../j13/helpers";
import { psql } from "../j02/helpers";

// P14.14 (j01-010) : un Créateur crée un lien de partage à échéance, un
// visiteur ANONYME le rejoue sur /embed/:token — nominal, expiré, révoqué.
// Visiteur anonyme = page sans login (aucun persona), comme j01/anonymous.
const TEXT = "Contenu embed j01-010";
const EXPIRED_OR_REVOKED = "Ce lien de partage est expiré ou révoqué.";

let creator: Api;
test.beforeAll(async () => {
  creator = await apiFor("creator");
});

async function embeddableApp(title: string) {
  const config = {
    ...appConfig(),
    layout: {
      type: "grid",
      breakpoints: {},
      items: [{ id: "w1", widget: "text", x: 0, y: 0, w: 4, h: 2, props: { text: TEXT } }],
    },
  };
  return mkItem(creator, title, config);
}

async function createLink(pk: string): Promise<{ token: string; id: string }> {
  const r = await creator.send("POST", `/v1/items/${pk}/share-links`, { ttlDays: 1 });
  expect(r.status).toBe(201);
  const list = await creator.get(`/v1/items/${pk}/share-links`);
  expect(list.status).toBe(200);
  expect(list.body).toHaveLength(1);
  return { token: r.body.token as string, id: list.body[0].id as string };
}

async function resolveAnon(token: string): Promise<number> {
  const doFetch = () => fetch(`${CORE_URL}/v1/share-links/${encodeURIComponent(token)}`);
  const r = await doFetch().catch(() => doFetch());
  await r.text();
  return r.status;
}

function trackAuthorization(page: Page) {
  const withAuth: string[] = [];
  page.on("request", (req) => {
    if (req.url().startsWith(CORE_URL) && "authorization" in req.headers()) {
      withAuth.push(req.url());
    }
  });
  return withAuth;
}

test.describe("j01-010 lien de partage à échéance rejoué en anonyme", () => {
  test("nominal : l'embed rend l'app sans jamais envoyer Authorization", async ({ page }) => {
    const it = await embeddableApp(`${TAG}-embed-ok`);
    const { token } = await createLink(it.pk);
    expect(await resolveAnon(token)).toBe(200);
    const withAuth = trackAuthorization(page);
    await page.goto(`/embed/${token}`);
    await expect(page.getByText(TEXT)).toBeVisible();
    await expect(page.getByRole("alert")).toHaveCount(0);
    expect(withAuth).toEqual([]);
  });

  test("expiré : la ligne expirée prime sur le TTL encore valide du jeton → 401 et message", async ({
    page,
  }) => {
    const it = await embeddableApp(`${TAG}-embed-exp`);
    const { token, id } = await createLink(it.pk);
    expect(await resolveAnon(token)).toBe(200);
    psql(
      `UPDATE share_link SET expires_at = (now() at time zone 'utc') - interval '1 hour' WHERE id = '${id}'`,
    );
    expect(await resolveAnon(token)).toBe(401);
    const withAuth = trackAuthorization(page);
    await page.goto(`/embed/${token}`);
    await expect(page.getByRole("alert")).toHaveText(EXPIRED_OR_REVOKED);
    await expect(page.getByText(TEXT)).toHaveCount(0);
    expect(withAuth).toEqual([]);
  });

  test("révoqué : un lien qui fonctionnait cesse de résoudre dès la révocation", async ({
    page,
  }) => {
    const it = await embeddableApp(`${TAG}-embed-rev`);
    const { token, id } = await createLink(it.pk);
    expect(await resolveAnon(token)).toBe(200);
    expect((await creator.send("DELETE", `/v1/items/${it.pk}/share-links/${id}`)).status).toBe(
      204,
    );
    expect(await resolveAnon(token)).toBe(401);
    const withAuth = trackAuthorization(page);
    await page.goto(`/embed/${token}`);
    await expect(page.getByRole("alert")).toHaveText(EXPIRED_OR_REVOKED);
    await expect(page.getByText(TEXT)).toHaveCount(0);
    expect(withAuth).toEqual([]);
  });
});
```

- [ ] **Step 2: Vérifier que la spec est découverte et correcte statiquement**

Run: `cd shell && npx playwright test -c playwright.journeys.config.ts e2e/journeys/j01/embed-share-link.spec.ts --list && npx tsc --noEmit && npx eslint e2e/journeys/j01/embed-share-link.spec.ts && npx prettier --check e2e/journeys/j01/embed-share-link.spec.ts`
Expected: 3 tests listés (`j01-010 lien de partage à échéance rejoué en anonyme › nominal|expiré|révoqué`) ; `tsc`/`eslint`/`prettier` propres. (Si `tsc` n'inclut pas `e2e/`, `--list` compile déjà le fichier.)

- [ ] **Step 3: Rejeu sur stack réelle (si la stack tourne ; sinon laissé à L6, à consigner dans le ledger)**

Run: `cd shell && SHELL_URL=http://localhost:8300 CORE_URL=http://localhost:8200 npx playwright test -c playwright.journeys.config.ts e2e/journeys/j01 -g "j01-010"`
Expected: 3 passed. Falsification obligatoire (piège n°10) : retirer temporairement le `psql(...)` de « expiré » ⇒ le test doit ÉCHOUER à `expect(await resolveAnon(token)).toBe(401)` ; le remettre.

- [ ] **Step 4: Commit**

```bash
cd /home/lenen/projets/geostudio && git add shell/e2e/journeys/j01/embed-share-link.spec.ts && git commit -m "$(cat <<'EOF'
test(shell): parcours d'audit P14.14 — lien de partage à échéance rejoué en anonyme (REV-272c)

Nominal, expiré (échéance de la ligne reculée en base, jeton encore valide)
et révoqué, côté API publique et page /embed/:token, sans Authorization.

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>
EOF
)"
```

---

### Task L2b-11: portes de qualité du fragment et clôture backlog

**Files:**
- Modify: `docs/revue/2026-09-04-backlog.md` (entrées `REV-271` l.3150-3157, `REV-272` l.3159-3166, `REV-290` l.3321-3328 ; sommaire de la ligne ~113 recalculé par l'intégrateur du lot, pas ici)

- [ ] **Step 1: Portes shell (mêmes invocations qu'en CI)**

Run: `cd shell && npm run lint && npm run format:check && npm run test && npm run build`
Expected: tout vert (couverture ≥ `shell/.coverage-threshold` ; nettoyer `dist/` et `dist-export/` avant de mesurer). Piège : le watchdog mémoire peut tuer un `npm run test` en arrière-plan sous contention — le lancer en avant-plan.

- [ ] **Step 2: E2E mockés des surfaces touchées (filet de L2b-1, L2b-2, L2b-5…9)**

Run: `cd shell && npx playwright test e2e/config-history.spec.ts e2e/embed.spec.ts e2e/app-builder.spec.ts e2e/map-popup.spec.ts e2e/alert-rule.spec.ts e2e/pipeline-builder.spec.ts e2e/dataset-export.spec.ts`
Expected: tout vert. Si un spec échoue sur `not served by the core`, un mock vise une URL hors `https://core.test/v1` : corriger le mock (jamais `toCoreHref`). Puis la suite complète avant clôture du plan : `cd shell && npm run e2e` (piège n°6).

- [ ] **Step 3: Portes cœur**

Run: `cd core && uv run pytest tests/test_mcp_tools_configs.py tests/test_configs_if_match.py tests/test_configs_if_match_race.py tests/test_mcp_configs_privilege_guard.py -v && uv run ruff check . && uv run ruff format --check . && uv run lint-imports`
Expected: PASS. Aucune route/modèle HTTP modifié ⇒ **diff OpenAPI/types TS attendu vide** (vérifier : `cd core && PYTHONPATH=. CORE_SECRETS_MASTER_KEY="AAECAwQFBgcICQoLDA0ODxAREhMUFRYXGBkaGxwdHh8=" uv run python scripts/export_openapi.py openapi.json && git diff --stat openapi.json` vide). Pas de nouvelle surface inventoriée (paramètre optionnel d'un outil MCP existant) ⇒ pas de `feature_health_cli.py --write` pour ce fragment.

- [ ] **Step 4: Mettre à jour le backlog**

Dans `docs/revue/2026-09-04-backlog.md` :
- `REV-290` : `- **État :** ouvert.` → `- **État :** fermé — \`authFetch\` lève hors de l'origine du cœur (résolution contre \`coreUrl\`, chemin \`/v1\`), tests \`baseRenew.test.ts\` (backlog Plan A, lot L2).`
- `REV-271` : `- **État :** ouvert.` → `- **État :** fermé — \`If-Match\` + UX de conflit 412 commune sur cartes, datasets, pipelines, rapports (alertes : garde au niveau du domaine, aucun éditeur d'alerte existante) ; MCP \`save_app_config\` gagne \`expectedVersion\` ; exceptions documentées : \`rollback_config\` (restauration explicite), \`pipelines/runtime.py\` (écrivain interne), assistant requête visuelle (régénère depuis son état).`
- `REV-272` : `- **État :** ouvert.` → `- **État :** partiel — (b) fermé (\`resolveCoreUrl\`, \`config.ts\`) et (c) fermé (\`e2e/journeys/j01/embed-share-link.spec.ts\`, rejeu stack = L6) ; (a) tombstone RGPD reste ouvert, bloqué par la décision DPO.`

- [ ] **Step 5: Commit**

```bash
cd /home/lenen/projets/geostudio && git add docs/revue/2026-09-04-backlog.md && git commit -m "$(cat <<'EOF'
docs(revue): clôture REV-290, REV-271 et REV-272 (b)(c) au backlog

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>
EOF
)"
```

## Fragment L2c — REV-273 (b)(c)(d)(e) : connecteurs, coffre de secrets, egress

**Périmètre :** REV-273 sous-points (b) plafonds/délai du lecteur blob, (c) 409 de `delete_secret_unless_used` filtré par `can()`, (d) TOCTOU DNS dans la couche d'egress commune + jumelles, (e) STARTTLS/SMTP_SSL + validation à la création du secret. (a) rejeu j06-004 → L6, hors plan.

**Ordre recommandé vs REV-197 (autre fragment) : exécuter REV-197 AVANT les tâches L2c-4 et L2c-9.** Ces deux tâches ne touchent que le bloc final de `materialize_blob_connector` (la construction de `resource = filesystem(...) | reader`) et un nouveau helper `_blob_fs_kwargs` ; REV-197 réécrit la dérivation de `bucket_url`/le contrôle de préfixe juste au-dessus. Les ancres ci-dessous sont des extraits de code (pas des numéros de ligne) pour survivre au décalage. Les tâches L2c-1, 2, 3, 5, 6, 7, 8 sont indépendantes de REV-197 (aucune ne touche `secrets/schemas.py` hors `SmtpCredentialsPayload`/`SecretCreate`/`SecretUpdate`, ni `connector_runtime.py` hors `_stream_sql` + imports). Si REV-197 passe après, rejouer la suite `tests/test_pipeline_connector_runtime.py` : le faux `filesystem` de `_patch_blob_internals` est modifié ici (accepte `kwargs`).

**Conventions de ce fragment :** tous les chemins sont relatifs à `/home/lenen/projets/geostudio`; les commandes pytest se lancent depuis `core/`. Chaque commit se termine par `Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>`. Rappel piège n°14 (jumelles de garde) : (d) se déploie sur les CINQ copies de la garde (`pipelines`, `alerts`, `harvest`, `copilot`, `search`), pas sur la seule `pipelines`.

**Conception (d), lue dans le code réel :**
- Les 5 modules `app/{pipelines,alerts,harvest,copilot,search}/egress.py` dupliquent `assert_egress_allowed(url)` (résolution `socket.getaddrinfo` + refus des plages non globales + allowlist). La vérification et la connexion résolvent le DNS séparément : fenêtre TOCTOU (rebinding DNS public → 127.0.0.1).
- Le contrat de couches interdit à `alerts`/`harvest`/`pipelines` de s'importer entre eux ; on ne partage donc que du code **sans dépendance applicative** : nouveau module racine `core/app/net_pin.py` (n'importe que `requests`/`urllib3`/`httpx`).
- Correctif : `assert_egress_allowed` **retourne l'IP validée** (`str`) ; la couche de transport (adaptateur `requests` / transport `httpx`) **se connecte à cette IP** en conservant le nom d'hôte pour `Host` et SNI/vérification de certificat. Une seconde résolution a lieu au moment de la connexion et passe par la même garde : un rebinding entre le contrôle de `send()` et la connexion est donc **refusé** (EgressBlockedError), et une connexion légitime vise exactement l'adresse validée.
  - `requests`/urllib3 2.8 (vérifié sur la source installée) : `HTTPConnection._new_conn` lit `self._dns_host` ; `host` (donc `Host:` et `server_hostname` TLS) est dérivé de la même variable ⇒ on la substitue **le temps de `_new_conn()` seulement**, puis on la restaure. Prototype exécuté : `Host: pinned.invalid:PORT` préservé, connexion à 127.0.0.1.
  - `httpx` : `request.url = url.copy_with(host=ip)`, l'en-tête `Host` reste celui construit à l'init, `request.extensions["sni_hostname"] = nom` (lu par httpcore, vérifié dans `httpcore/_sync/connection.py`). Prototype exécuté.
  - DSN Postgres : paramètre libpq `hostaddr` (le `host` reste utilisé pour la vérification TLS `verify-full`) via `connect_args`. mssql/oracle : pas d'équivalent fiable (descripteur TNS/ODBC) → limite documentée (`ponytail:`), non corrigée.
  - Endpoint S3 compatible : s3fs → aiobotocore → aiohttp ; `config_kwargs={"connector_args": {"resolver": PinnedAioResolver()}}` (vérifié : `s3fs.S3FileSystem(config_kwargs=…)`, `AioConfig(connector_args=…)` ; dlt transmet `filesystem(kwargs=…)` au constructeur fsspec). **À rejouer sur une stack réelle (lot L6)** : le câblage dlt→s3fs→aiohttp n'est testé ici qu'aux frontières (arguments transmis + résolveur isolé).
  - Proxys : un `ProxyManager` de `requests` (variables `HTTP(S)_PROXY`) n'est pas concerné par `pool_classes_by_scheme` du `PoolManager` : comportement inchangé (la garde `send()` reste en place). Documenté en `ponytail:`.
- Les fixtures de tests existants neutralisent `assert_egress_allowed` par `lambda url: None` : le retour `None` ⇒ **pas d'épinglage** (les tests contre un `pytest-httpserver` sur 127.0.0.1 continuent de passer, sans modification de ces fixtures).

---

### Task L2c-1: 409 de `delete_secret_unless_used` filtré par `can()` (REV-273c)

**Files:**
- Modify: `core/app/secrets/repository.py:1-14` (imports), `core/app/secrets/repository.py:116-123` (`delete_secret_unless_used`)
- Modify: `core/app/secrets/routes.py:126` (appel), `core/app/mcp/tools/secrets.py:48` (appel)
- Test: `core/tests/test_secrets_routes.py` (ajout en fin de fichier), `core/tests/test_secrets_repository.py` (aucun appel existant à adapter : `grep -rn delete_secret_unless_used tests` ne trouve rien)

**Interfaces:**
- Consumes: `app.items.repository.get_access_facts_by_ids(session, *, tenant_id: str, item_ids: list[str]) -> dict[str, ItemAccessFacts]`; `app.sharing.authorization.can(session, *, user_id: str, action: Action, item: AccessFacts, kind="item", actor_is_admin=False) -> bool` (couche : `app.secrets` est AU-DESSUS de `items`/`sharing` dans le contrat, import autorisé) ; `find_usages(session, *, tenant_id, name) -> list[dict[str, str]]` (inchangé).
- Produces: `delete_secret_unless_used(session: Session, secret: ConnectorSecret, *, user: User) -> None` ; `SecretInUseError.args[0]` = `"secret encore utilisé par : <titres lisibles> et N autre(s) objet(s) non visible(s)"`. Les deux appelants (REST, MCP) bénéficient du filtre sans autre changement (les deux ont déjà `user`).

- [ ] **Step 1: Écrire le test échouant (route)** — ajouter à la fin de `core/tests/test_secrets_routes.py` :

```python
def test_rev273c_409_lists_only_items_the_caller_can_read(env):
    from app.configs.models import Config, ConfigRevision
    from app.items.repository import create_item

    app, client, Session, admin, _regular = env
    with Session() as s:
        bob = get_or_create_user(
            s,
            tenant_id=admin.tenant_id,
            oidc_sub="b",
            username="bob",
            email=None,
            first_name="",
            last_name="",
        )
        s.commit()
        s.refresh(bob)
    _as(app, bob)
    sid = client.post("/v1/secrets", json=BEARER_BODY).json()["id"]
    with Session() as s:
        for n, (title, owner) in enumerate([("Mine", bob.id), ("Theirs", admin.id)]):
            item = create_item(
                s,
                tenant_id=admin.tenant_id,
                owner_id=owner,
                resource_type="pipeline",
                title=title,
            )
            s.add(Config(id=f"c{n}", tenant_id=admin.tenant_id, kind="pipeline", item_id=item.id))
            s.add(
                ConfigRevision(
                    tenant_id=admin.tenant_id,
                    config_id=f"c{n}",
                    version=1,
                    data={"nodes": [{"params": {"secretName": "weather-api"}}]},
                )
            )
        s.commit()
    r = client.delete(f"/v1/secrets/{sid}")
    assert r.status_code == 409
    detail = r.json()["detail"]
    assert "Mine" in detail
    assert "Theirs" not in detail
    assert "1 autre objet non visible" in detail
```

- [ ] **Step 2: Lancer, constater l'échec** — `cd core && uv run pytest tests/test_secrets_routes.py::test_rev273c_409_lists_only_items_the_caller_can_read -v`. Attendu : FAIL (`"Theirs" not in detail` — l'actuel `detail` liste les deux titres).

- [ ] **Step 3: Implémenter** — dans `core/app/secrets/repository.py`, ajouter aux imports (ordre alphabétique ruff) `from app.items.repository import get_access_facts_by_ids` (après `from app.items.models import Item`) et `from app.sharing.authorization import can` (après `app.secrets.schemas`), puis remplacer `delete_secret_unless_used` :

```python
def delete_secret_unless_used(session: Session, secret: ConnectorSecret, *, user: User) -> None:
    """Refuse (SecretInUseError) si une config cite encore le secret (P16.05).
    REV-273c : le message ne liste que les objets que `user` peut lire
    (`can(read)`) ; les autres sont comptés, jamais nommés."""
    usages = find_usages(session, tenant_id=secret.tenant_id, name=secret.name)
    if not usages:
        delete_secret(session, secret)
        return
    facts = get_access_facts_by_ids(
        session, tenant_id=secret.tenant_id, item_ids=[u["itemId"] for u in usages]
    )
    visible = [
        u["title"]
        for u in usages
        if (f := facts.get(u["itemId"])) is not None
        and can(session, user_id=user.id, action="read", item=f)
    ]
    hidden = len(usages) - len(visible)
    parts: list[str] = []
    if visible:
        parts.append(", ".join(visible))
    if hidden:
        s = "s" if hidden > 1 else ""
        parts.append(f"{hidden} autre{s} objet{s} non visible{s}")
    raise SecretInUseError("secret encore utilisé par : " + " et ".join(parts))
```
Dans `secrets/routes.py` ligne 126 : `repo.delete_secret_unless_used(session, secret, user=user)`. Dans `mcp/tools/secrets.py` ligne 48 : `repo.delete_secret_unless_used(session, secret, user=user)`.

- [ ] **Step 4: Succès** — `cd core && uv run pytest tests/test_secrets_routes.py tests/test_mcp_tools_secrets.py tests/test_secrets_repository.py -v`. Attendu : tout vert, y compris `test_p16_05_…` (admin propriétaire de l'item : « Pipe X » reste listé).

- [ ] **Step 5: Garde import** — `cd core && uv run lint-imports`. Attendu : contrats respectés (si une violation `app.secrets -> app.items.repository` apparaît, c'est une erreur de lecture du contrat : stopper et lire `pyproject.toml [[tool.importlinter.contracts]]`, ne pas ajouter d'`ignore_imports` sans arbitrage).

- [ ] **Step 6: Commit** — `fix(core): le 409 de suppression de secret ne nomme que les objets lisibles (REV-273c)` + trailer.

---

### Task L2c-2: refuser `useTls=false` hors localhost à la création/mise à jour du secret SMTP (REV-273e, 1/2)

**Files:**
- Modify: `core/app/secrets/schemas.py:8` (import pydantic), `core/app/secrets/schemas.py:68` (après `SmtpCredentialsPayload`), `core/app/secrets/schemas.py:282-288` (`SecretCreate`, `SecretUpdate`)
- Test: `core/tests/test_secrets_schemas.py`, `core/tests/test_secrets_routes.py`

**Interfaces:**
- Produces: `SMTP_LOCAL_HOSTS: frozenset[str]` ; `smtp_tls_violation(payload: SmtpCredentialsPayload) -> str | None` (message d'erreur ou `None`) — consommés par L2c-3 (`alerts/notify.py`). Validation active uniquement sur `SecretCreate`/`SecretUpdate` (écriture) ; **`SECRET_PAYLOAD_ADAPTER` (lecture/déchiffrement) reste permissif** : un secret existant `useTls=false` doit rester lisible (compatibilité, aucune bascule silencieuse).
- Aucun changement de schéma OpenAPI attendu (validateur Pydantic sans `json_schema_extra`) : voir la tâche de portes pour la preuve par régénération.

- [ ] **Step 1: Tests échouants (schémas)** — ajouter à `core/tests/test_secrets_schemas.py` :

```python
_SMTP = {
    "kind": "smtp",
    "host": "smtp.example.test",
    "port": 25,
    "username": "u",
    "password": "p",
    "useTls": False,
    "fromAddress": "a@example.test",
}


def test_secret_create_rejects_smtp_without_tls_on_a_remote_host():
    from pydantic import ValidationError

    from app.secrets.schemas import SecretCreate

    with pytest.raises(ValidationError, match="useTls"):
        SecretCreate(name="m", payload=_SMTP)


def test_secret_update_rejects_smtp_without_tls_on_a_remote_host():
    from pydantic import ValidationError

    from app.secrets.schemas import SecretUpdate

    with pytest.raises(ValidationError, match="useTls"):
        SecretUpdate(payload=_SMTP)


@pytest.mark.parametrize("host", ["localhost", "127.0.0.1", "::1", "LocalHost"])
def test_secret_create_accepts_smtp_without_tls_on_localhost(host):
    from app.secrets.schemas import SecretCreate

    SecretCreate(name="m", payload={**_SMTP, "host": host})


def test_stored_smtp_payload_without_tls_still_decodes():
    # Compat : un secret déjà chiffré avec useTls=false doit rester lisible.
    from app.secrets.schemas import SECRET_PAYLOAD_ADAPTER

    assert SECRET_PAYLOAD_ADAPTER.validate_python(_SMTP).useTls is False
```
(si `pytest` n'est pas déjà importé en tête de ce fichier, ajouter `import pytest`.)

- [ ] **Step 2: Échec attendu** — `cd core && uv run pytest tests/test_secrets_schemas.py -k "smtp" -v`. Attendu : les 2 tests `rejects` FAIL (`DID NOT RAISE`), les 4 autres PASS.

- [ ] **Step 3: Implémenter** — dans `core/app/secrets/schemas.py` : `from pydantic import BaseModel, Field, TypeAdapter, model_validator` ; après la classe `SmtpCredentialsPayload` :

```python
SMTP_LOCAL_HOSTS = frozenset({"localhost", "127.0.0.1", "::1"})


def smtp_tls_violation(payload: SmtpCredentialsPayload) -> str | None:
    """REV-273e : sans TLS, identifiants et courrier transitent en clair —
    toléré uniquement vers la machine locale (relais de dev)."""
    if not payload.useTls and payload.host.lower() not in SMTP_LOCAL_HOSTS:
        return "useTls=false n'est autorisé que pour localhost : activez TLS (STARTTLS ou SMTPS)"
    return None


def _check_smtp_payload(payload: object) -> None:
    if isinstance(payload, SmtpCredentialsPayload):
        message = smtp_tls_violation(payload)
        if message:
            raise ValueError(message)
```
Puis remplacer `SecretCreate`/`SecretUpdate` par :

```python
class SecretCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    payload: SecretPayload

    @model_validator(mode="after")
    def _smtp_tls(self) -> "SecretCreate":
        _check_smtp_payload(self.payload)
        return self


class SecretUpdate(BaseModel):
    payload: SecretPayload

    @model_validator(mode="after")
    def _smtp_tls(self) -> "SecretUpdate":
        _check_smtp_payload(self.payload)
        return self
```

- [ ] **Step 4: Succès (schémas)** — même commande ; attendu 6 PASS.

- [ ] **Step 5: Test de route** — ajouter à `core/tests/test_secrets_routes.py` :

```python
def test_rev273e_post_smtp_without_tls_remote_is_422_and_does_not_echo_password(env):
    app, client, _, admin, _regular = env
    _as(app, admin)
    smtp = {
        "kind": "smtp",
        "host": "smtp.example.test",
        "port": 25,
        "username": "u",
        "password": "ultra-secret-pw",
        "useTls": False,
        "fromAddress": "a@example.test",
    }
    r = client.post("/v1/secrets", json={"name": "smtp-clear", "payload": smtp})
    assert r.status_code == 422
    assert "useTls" in r.text and "ultra-secret-pw" not in r.text
    ok = client.post(
        "/v1/secrets",
        json={"name": "smtp-local", "payload": {**smtp, "host": "localhost"}},
    )
    assert ok.status_code == 201
```
Lancer : `cd core && uv run pytest tests/test_secrets_routes.py::test_rev273e_post_smtp_without_tls_remote_is_422_and_does_not_echo_password -v`. Attendu : PASS. **Si FAIL sur `ultra-secret-pw not in r.text`** : le gestionnaire 422 global renvoie l'`input` de l'erreur ; ne pas affaiblir le test — lire comment `test_p16_06_07_validation_errors_do_not_echo_values_and_reject_empty` obtient son anonymisation (gestionnaire d'erreurs de validation de `app/main.py`) et y ajouter le cas ; sinon le validateur `mode="after"` expose l'objet entier dans `input`.

- [ ] **Step 6: Suite voisine** — `cd core && uv run pytest tests/test_secrets_schemas.py tests/test_secrets_routes.py tests/test_mcp_tools_secrets.py -v`. Attendu : vert.

- [ ] **Step 7: Commit** — `fix(core): refuser un secret SMTP sans TLS hors localhost dès la création (REV-273e)` + trailer.

---

### Task L2c-3: envoi SMTP — `SMTP_SSL` sur 465, STARTTLS vérifié, refus explicite des secrets existants sans TLS (REV-273e, 2/2)

**Files:**
- Modify: `core/app/alerts/notify.py:20-33` (imports), `core/app/alerts/notify.py:128-137` (bloc d'envoi de `send_email`)
- Test: `core/tests/test_alert_notify.py`

**Interfaces:**
- Consumes: `smtp_tls_violation(payload: SmtpCredentialsPayload) -> str | None` (L2c-2). `app.alerts` est au-dessus de `app.secrets` : import autorisé (déjà importé : `from app.secrets import repository as secrets_repo`).
- Produces: comportement de `send_email` : (1) `useTls=False` hors localhost → `NotifyError("secret '<nom>' : useTls=false n'est autorisé que pour localhost … mettez à jour le secret (PUT /v1/secrets/{id}) avec useTls=true")` **sans ouvrir de connexion** ; (2) `useTls=True` + port 465 → `smtplib.SMTP_SSL(host, 465, timeout=10, context=ctx)` sans `starttls` ; (3) `useTls=True` autre port → `SMTP` + `starttls(context=ctx)` avec `ctx = ssl.create_default_context()` (par défaut `starttls()` n'authentifie pas le certificat : vérifié dans `smtplib.py` → `ssl._create_stdlib_context()`).

- [ ] **Step 1: Tests échouants** — dans `core/tests/test_alert_notify.py`, ajouter une fixture paramétrable (le fixture existant `smtp_secret_session` code `host=smtp.example.test`, `port=587`, `useTls=True` en dur ; ne pas le modifier) puis les tests :

```python
@pytest.fixture()
def smtp_variant_session(monkeypatch, request):
    """Comme smtp_secret_session mais host/port/useTls pilotés par request.param."""
    host, port, use_tls = request.param
    monkeypatch.setenv("CORE_SECRETS_MASTER_KEY", TEST_KEY_B64)
    engine = make_engine("sqlite+pysqlite:///:memory:")
    init_db(engine)
    Session = make_session_factory(engine)
    with Session() as s:
        tenant = get_or_create_default_tenant(s)
        user = get_or_create_user(
            s,
            tenant_id=tenant.id,
            oidc_sub="a",
            username="alice",
            email=None,
            first_name="",
            last_name="",
        )
        # Construit via model_construct : simule un secret STOCKÉ avant L2c-2
        # (la validation d'écriture de SecretCreate ne s'applique pas à la lecture).
        payload = SmtpCredentialsPayload.model_construct(
            kind="smtp",
            host=host,
            port=port,
            username="alerts@example.test",
            password="s3cret",
            useTls=use_tls,
            fromAddress="alerts@example.test",
        )
        ciphertext, nonce = secrets_crypto.encrypt(SECRET_PAYLOAD_ADAPTER.dump_python(payload))
        secrets_repo.create_secret(
            s,
            tenant_id=tenant.id,
            created_by=user.id,
            name="smtp-main",
            kind="smtp",
            ciphertext=ciphertext,
            nonce=nonce,
        )
        from app.items import repository as items_repo

        item_id = items_repo.create_item(
            s, tenant_id=tenant.id, owner_id=user.id, resource_type="alert", title="rule"
        ).id
        s.commit()
        tenant_id = tenant.id
    yield Session, tenant_id, item_id
    engine.dispose()


def _send(Session, tenant_id, item_id):
    channel = AlertChannelEmail(to="ops@example.test", smtpSecretName="smtp-main")
    with Session() as s:
        send_email(
            s, tenant_id=tenant_id, item_id=item_id, channel=channel, subject="A", body="b"
        )


@pytest.mark.parametrize("smtp_variant_session", [("smtp.example.test", 25, False)], indirect=True)
def test_send_email_refuses_stored_secret_without_tls_on_remote_host(smtp_variant_session):
    with patch("app.alerts.notify.smtplib.SMTP") as smtp_cls, patch(
        "app.alerts.notify.smtplib.SMTP_SSL"
    ) as ssl_cls:
        with pytest.raises(NotifyError, match="useTls=false.*PUT /v1/secrets"):
            _send(*smtp_variant_session)
    smtp_cls.assert_not_called()
    ssl_cls.assert_not_called()


@pytest.mark.parametrize("smtp_variant_session", [("smtp.example.test", 465, True)], indirect=True)
def test_send_email_uses_smtp_ssl_on_port_465(smtp_variant_session):
    with patch("app.alerts.notify.smtplib.SMTP") as smtp_cls, patch(
        "app.alerts.notify.smtplib.SMTP_SSL"
    ) as ssl_cls:
        server = ssl_cls.return_value.__enter__.return_value
        _send(*smtp_variant_session)
    smtp_cls.assert_not_called()
    assert ssl_cls.call_args.kwargs["context"] is not None
    server.starttls.assert_not_called()
    server.login.assert_called_once_with("alerts@example.test", "s3cret")
    server.send_message.assert_called_once()


@pytest.mark.parametrize("smtp_variant_session", [("smtp.example.test", 587, True)], indirect=True)
def test_send_email_starttls_verifies_the_certificate(smtp_variant_session):
    import ssl

    with patch("app.alerts.notify.smtplib.SMTP") as smtp_cls:
        server = smtp_cls.return_value.__enter__.return_value
        _send(*smtp_variant_session)
    ctx = server.starttls.call_args.kwargs["context"]
    assert ctx.verify_mode == ssl.CERT_REQUIRED and ctx.check_hostname is True


@pytest.mark.parametrize("smtp_variant_session", [("localhost", 25, False)], indirect=True)
def test_send_email_allows_plain_smtp_on_localhost(smtp_variant_session):
    with patch("app.alerts.notify.smtplib.SMTP") as smtp_cls:
        server = smtp_cls.return_value.__enter__.return_value
        _send(*smtp_variant_session)
    server.starttls.assert_not_called()
    server.send_message.assert_called_once()
```
(NB : `model_construct` contourne la validation de champ ; `SECRET_PAYLOAD_ADAPTER.dump_python` sérialise tout de même le modèle.)

- [ ] **Step 2: Échec attendu** — `cd core && uv run pytest tests/test_alert_notify.py -k "refuses_stored or smtp_ssl or verifies_the or plain_smtp" -v`. Attendu : FAIL (le premier : pas de `NotifyError`, l'envoi part en clair ; le 2e : `SMTP` utilisé ; le 3e : `starttls()` sans `context` → `KeyError`).

- [ ] **Step 3: Implémenter** — dans `core/app/alerts/notify.py` : ajouter `import ssl` (après `import smtplib`) et `from app.secrets.schemas import smtp_tls_violation` (après `from app.secrets import repository as secrets_repo`). Remplacer le bloc final de `send_email` (de `try:\n        with smtplib.SMTP(` jusqu'à la fin) par :

```python
    violation = smtp_tls_violation(payload)
    if violation:
        # Secret stocké avant la validation d'écriture (REV-273e) : refus explicite,
        # jamais de bascule silencieuse vers TLS (le serveur peut ne pas le supporter).
        raise NotifyError(
            f"secret '{channel.smtpSecretName}' : {violation} — "
            "mettez à jour le secret (PUT /v1/secrets/{id}) avec useTls=true"
        )

    ctx = ssl.create_default_context()
    try:
        if payload.useTls and payload.port == 465:
            server_cm = smtplib.SMTP_SSL(payload.host, payload.port, timeout=10, context=ctx)
        else:
            server_cm = smtplib.SMTP(payload.host, payload.port, timeout=10)
        with server_cm as smtp:
            if payload.useTls and payload.port != 465:
                smtp.starttls(context=ctx)
            smtp.login(payload.username, payload.password)
            smtp.send_message(message)
    except (smtplib.SMTPException, OSError) as exc:
        raise NotifyError(f"email delivery failed: {exc}") from exc
```
(le littéral `{id}` du message n'est PAS un f-string : la 2e ligne est une chaîne simple — garder tel quel.)

- [ ] **Step 4: Succès** — `cd core && uv run pytest tests/test_alert_notify.py -v`. Attendu : tout vert (dont `test_send_email_delivers_via_smtp_secret` : `starttls.assert_called_once()` reste vrai).

- [ ] **Step 5: Commit** — `fix(core): SMTP_SSL sur 465, STARTTLS vérifié, refus explicite des secrets SMTP sans TLS (REV-273e)` + trailer.

---

### Task L2c-4: plafonds de fichiers/octets/lignes/durée et délais fsspec du lecteur blob (REV-273b)

**Files:**
- Modify: `core/app/pipelines/connector_runtime.py:17-23` (imports : `import time`), `:140-146` (après `_max_pages`), fin de `materialize_blob_connector` (l'ancre est le bloc `resource = (\n        filesystem(bucket_url=bucket_url, credentials=credentials, file_glob=file_glob)\n        | _BLOB_READERS[params.format]()\n    )\n    resource.apply_hints(...)`)
- Modify: `.env.example:317-318`, `docker-compose.yml:323-324` (service `core`) et `:546-547` (service `worker`)
- Test: `core/tests/test_pipeline_connector_runtime.py` (adapter `_FakeBlobResource`/`_fake_filesystem` ; nouveaux tests)

**Interfaces:**
- Produces (module `connector_runtime`) :
  - `_blob_max_files() -> int` (env `CORE_PIPELINES_BLOB_MAX_FILES`, défaut 100), `_blob_max_bytes() -> int` (`CORE_PIPELINES_BLOB_MAX_BYTES`, défaut 1_073_741_824), `_blob_timeout_s() -> int` (`CORE_PIPELINES_BLOB_TIMEOUT_S`, défaut 600) ;
  - `_blob_resource(files, reader) -> DltResource` : applique `files.add_map(file_guard)` (compte + octets via `size_in_bytes`, échéance) puis `(files | reader).add_map(row_guard)` (lignes vs `_max_rows()` + échéance), avec compteurs frais par appel. Messages : `plafond de {n} fichiers dépassé`, `plafond de {n} octets dépassé`, `plafond de {n} lignes dépassé`, `délai de {n}s dépassé`, tous `ConnectorRuntimeError` (sérialisés par `_run_dlt_and_attach` en `reader.connector extraction failed: …plafond…`, comme le plafond REST existant) ;
  - `_blob_fs_kwargs(payload) -> dict` : `{"kwargs": {...}}` à passer à `filesystem(**…)` ; s3 → `config_kwargs={"connect_timeout": t, "read_timeout": q}` ; azure (adlfs) → `connection_timeout`/`read_timeout` ; gcs (gcsfs) → `requests_timeout`. Étendu par L2c-9 (résolveur S3).
- Consumes : `_connect_timeout_s()`, `_query_timeout_s()`, `_max_rows()` (existants, `connector_runtime.py:132-142`).
- Limite assumée (`ponytail:`) : les gardes agissent entre éléments ; un fichier unique géant lu d'un bloc n'est borné que par `_blob_max_bytes()` (taille annoncée par le listing) et les délais réseau fsspec, pas par un budget CPU.

- [ ] **Step 1: Tests échouants (plafonds, vraie chaîne dlt sur dossier local)** — ajouter dans `core/tests/test_pipeline_connector_runtime.py` (après les tests blob existants) :

```python
def _local_csv_files(tmp_path, sizes):
    """sizes = {nom: nb_lignes}. Retourne un `filesystem` dlt réel sur un dossier local
    (le gardien n'a pas à connaître le schéma d'URL : seul le builder d'URL est blob-only)."""
    from dlt.sources.filesystem import filesystem

    for name, n in sizes.items():
        (tmp_path / name).write_text("x\n" + "\n".join(str(i) for i in range(n)) + "\n")
    return filesystem(bucket_url=str(tmp_path), file_glob="*.csv")


def _run_capped(conn, tmp_path, sizes):
    files = _local_csv_files(tmp_path, sizes)
    resource = connector_runtime._blob_resource(files, connector_runtime.read_csv())
    resource.apply_hints(table_name="records", write_disposition="replace")
    connector_runtime._run_dlt_and_attach(conn, resource, node_id="cap", view_name="node_cap")


def test_blob_file_cap(conn, tmp_path, monkeypatch):
    monkeypatch.setenv("CORE_PIPELINES_BLOB_MAX_FILES", "2")
    with pytest.raises(connector_runtime.ConnectorRuntimeError, match="plafond de 2 fichiers"):
        _run_capped(conn, tmp_path, {"a.csv": 1, "b.csv": 1, "c.csv": 1})


def test_blob_byte_cap(conn, tmp_path, monkeypatch):
    monkeypatch.setenv("CORE_PIPELINES_BLOB_MAX_BYTES", "10")
    with pytest.raises(connector_runtime.ConnectorRuntimeError, match="plafond de 10 octets"):
        _run_capped(conn, tmp_path, {"a.csv": 50})


def test_blob_row_cap(conn, tmp_path, monkeypatch):
    monkeypatch.setenv("CORE_PIPELINES_CONNECTOR_MAX_ROWS", "3")
    with pytest.raises(connector_runtime.ConnectorRuntimeError, match="plafond de 3 lignes"):
        _run_capped(conn, tmp_path, {"a.csv": 10})


def test_blob_deadline(conn, tmp_path, monkeypatch):
    monkeypatch.setenv("CORE_PIPELINES_BLOB_TIMEOUT_S", "-1")  # échéance déjà passée
    with pytest.raises(connector_runtime.ConnectorRuntimeError, match="délai de -1s dépassé"):
        _run_capped(conn, tmp_path, {"a.csv": 2})


def test_blob_under_caps_loads_all_rows(conn, tmp_path):
    _run_capped(conn, tmp_path, {"a.csv": 4, "b.csv": 3})
    assert conn.execute("SELECT count(*) FROM node_cap").fetchone()[0] == 7
```

- [ ] **Step 2: Échec attendu** — `cd core && uv run pytest tests/test_pipeline_connector_runtime.py -k "blob_file_cap or blob_byte_cap or blob_row_cap or blob_deadline or blob_under_caps" -v`. Attendu : FAIL `AttributeError: module … has no attribute '_blob_resource'`.

- [ ] **Step 3: Implémenter les plafonds** — `connector_runtime.py` : ajouter `import time` aux imports stdlib ; après `_max_pages()` :

```python
def _blob_max_files() -> int:
    return _env_int("CORE_PIPELINES_BLOB_MAX_FILES", 100)


def _blob_max_bytes() -> int:
    return _env_int("CORE_PIPELINES_BLOB_MAX_BYTES", 1_073_741_824)


def _blob_timeout_s() -> int:
    return _env_int("CORE_PIPELINES_BLOB_TIMEOUT_S", 600)


def _blob_resource(files, reader):
    """REV-273b : plafonds fichiers/octets/lignes + échéance globale sur la
    chaîne filesystem → reader. dlt applique `add_map` ligne par ligne (y
    compris sur les pages) ; compteurs frais à chaque appel.
    ponytail: gardes entre éléments ; un fichier unique géant n'est borné que
    par sa taille annoncée et les délais réseau fsspec (`_blob_fs_kwargs`)."""
    max_files, max_bytes = _blob_max_files(), _blob_max_bytes()
    max_rows, budget = _max_rows(), _blob_timeout_s()
    deadline = time.monotonic() + budget
    state = {"files": 0, "bytes": 0, "rows": 0}

    def _check_deadline() -> None:
        if time.monotonic() > deadline:
            raise ConnectorRuntimeError(f"délai de {budget}s dépassé")

    def _file_guard(item):
        _check_deadline()
        state["files"] += 1
        if state["files"] > max_files:
            raise ConnectorRuntimeError(f"plafond de {max_files} fichiers dépassé")
        state["bytes"] += int(item["size_in_bytes"])
        if state["bytes"] > max_bytes:
            raise ConnectorRuntimeError(f"plafond de {max_bytes} octets dépassé")
        return item

    def _row_guard(row):
        _check_deadline()
        state["rows"] += 1
        if state["rows"] > max_rows:
            raise ConnectorRuntimeError(f"plafond de {max_rows} lignes dépassé")
        return row

    files.add_map(_file_guard)
    resource = files | reader
    resource.add_map(_row_guard)
    return resource


def _blob_fs_kwargs(payload) -> dict:
    """Délais réseau fsspec par fournisseur (P16.03, REV-273b). Noms vérifiés
    contre les signatures installées : s3fs `config_kwargs` → botocore Config ;
    adlfs `connection_timeout`/`read_timeout` ; gcsfs `requests_timeout`."""
    t, q = _connect_timeout_s(), _query_timeout_s()
    if payload.kind == "s3_credentials":
        return {"kwargs": {"config_kwargs": {"connect_timeout": t, "read_timeout": q}}}
    if payload.kind == "azure_blob_credentials":
        return {"kwargs": {"connection_timeout": t, "read_timeout": q}}
    return {"kwargs": {"requests_timeout": q}}
```
et remplacer, à la fin de `materialize_blob_connector`, le bloc

```python
    resource = (
        filesystem(bucket_url=bucket_url, credentials=credentials, file_glob=file_glob)
        | _BLOB_READERS[params.format]()
    )
```
par

```python
    files = filesystem(
        bucket_url=bucket_url,
        credentials=credentials,
        file_glob=file_glob,
        **_blob_fs_kwargs(payload),
    )
    resource = _blob_resource(files, _BLOB_READERS[params.format]())
```
(`resource.apply_hints(...)` et `_run_dlt_and_attach(...)` restent inchangés.)

- [ ] **Step 4: Succès des plafonds** — même commande qu'au Step 2. Attendu : 5 PASS. Si `test_blob_row_cap` échoue avec un autre message, lire la cause chaînée : la valeur observée en prototype est que `add_map` reçoit **une ligne à la fois** même sur une page-liste (`[{'a':1},…]` → 4 appels pour 4 lignes).

- [ ] **Step 5: Adapter les faux blob existants et tester le câblage** — dans `_FakeBlobResource` ajouter `def add_map(self, fn): return self` ; dans `_patch_blob_internals`, remplacer la signature du faux par `def _fake_filesystem(*, bucket_url, credentials=None, file_glob="*", kwargs=None):` et ajouter `captured["fs_kwargs"] = kwargs` dans son corps. Ajouter :

```python
def test_materialize_blob_connector_passes_provider_timeouts(
    monkeypatch, conn, session, tenant, user
):
    monkeypatch.setenv("CORE_PIPELINES_CONNECT_TIMEOUT_S", "7")
    monkeypatch.setenv("CORE_PIPELINES_QUERY_TIMEOUT_S", "42")
    _create_secret(
        session,
        tenant,
        user,
        name="s3-t",
        kind="s3_credentials",
        payload={
            "kind": "s3_credentials",
            "awsAccessKeyId": "AKIA123",
            "awsSecretAccessKey": "shh",
        },
    )
    captured: dict = {}
    _patch_blob_internals(monkeypatch, captured)
    connector_runtime.materialize_blob_connector(
        conn,
        secret_resolver=connector_runtime.PostgresSecretResolver(session, tenant.id, user),
        node_id="bt",
        params=ReaderConnectorBlobParams(
            secretName="s3-t", path="s3://bucket/data.csv", format="csv"
        ),
        view_name="node_bt",
    )
    cfg = captured["fs_kwargs"]["config_kwargs"]
    assert cfg["connect_timeout"] == 7 and cfg["read_timeout"] == 42
```
Lancer : `cd core && uv run pytest tests/test_pipeline_connector_runtime.py -v -k "blob"`. Attendu : tous PASS (anciens tests blob compris).

- [ ] **Step 6: Câblage des variables (piège n°2)** — dans `.env.example`, après la ligne `CORE_PIPELINES_CONNECTOR_MAX_PAGES=1000` : `CORE_PIPELINES_BLOB_MAX_FILES=100`, `CORE_PIPELINES_BLOB_MAX_BYTES=1073741824`, `CORE_PIPELINES_BLOB_TIMEOUT_S=600` ; dans `docker-compose.yml`, après chaque ligne `CORE_PIPELINES_CONNECTOR_MAX_PAGES:` (deux occurrences : service `core` ~l.324 et service `worker` ~l.547) :
```yaml
      CORE_PIPELINES_BLOB_MAX_FILES: ${CORE_PIPELINES_BLOB_MAX_FILES:-100}
      CORE_PIPELINES_BLOB_MAX_BYTES: ${CORE_PIPELINES_BLOB_MAX_BYTES:-1073741824}
      CORE_PIPELINES_BLOB_TIMEOUT_S: ${CORE_PIPELINES_BLOB_TIMEOUT_S:-600}
```
Lancer `cd core && uv run pytest tests/test_deployability.py -v` (chaque substitution doit être documentée dans `.env.example`) et `docker compose config | grep -c CORE_PIPELINES_BLOB` (attendu : 6 — 3 variables × 2 services).

- [ ] **Step 7: Commit** — `fix(core): plafonds de fichiers/octets/lignes/durée et délais fsspec sur reader.connector.blob (REV-273b)` + trailer.

---

### Task L2c-5: `assert_egress_allowed` retourne l'adresse validée, sur les 5 copies de la garde (REV-273d, 1/5)

**Files:**
- Modify: `core/app/pipelines/egress.py:49` et `:71` ; `core/app/alerts/egress.py:37` et fin de fonction ; `core/app/harvest/egress.py:55` et fin ; `core/app/copilot/egress.py:59` et fin ; `core/app/search/egress.py:65` et fin
- Create: `core/tests/test_egress_dns_pinning.py`

**Interfaces:**
- Produces, dans chacun des 5 modules : `assert_egress_allowed(url: str) -> str` — retourne `str(addresses[0])` (IP validée, IPv4/IPv6 littérale ou résolue) ; lève `EgressBlockedError` comme avant. Tous les appelants existants ignorent le retour : aucun changement. Consommé par L2c-6/7/8/9.

- [ ] **Step 1: Test échouant (double résolveur au niveau garde)** — créer `core/tests/test_egress_dns_pinning.py` :

```python
# SPDX-License-Identifier: Apache-2.0
"""REV-273d : épinglage DNS de la couche d'egress (5 copies de la garde)."""

import importlib
import socket

import pytest

EGRESS_MODULES = [
    "app.pipelines.egress",
    "app.alerts.egress",
    "app.harvest.egress",
    "app.copilot.egress",
    "app.search.egress",
]
PUBLIC = "93.184.216.34"


def _resolver(*answers):
    """getaddrinfo qui renvoie successivement `answers` (le dernier se répète)."""
    calls = {"n": 0}

    def fake(host, *args, **kwargs):
        ip = answers[min(calls["n"], len(answers) - 1)]
        calls["n"] += 1
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (ip, 0))]

    return fake, calls


@pytest.mark.parametrize("modname", EGRESS_MODULES)
def test_assert_returns_the_validated_address(monkeypatch, modname):
    mod = importlib.import_module(modname)
    fake, _ = _resolver(PUBLIC)
    monkeypatch.setattr(socket, "getaddrinfo", fake)
    assert mod.assert_egress_allowed("https://public.example.com/x") == PUBLIC
    assert mod.assert_egress_allowed("https://93.184.216.34:8443/x") == PUBLIC


@pytest.mark.parametrize("modname", EGRESS_MODULES)
def test_second_resolution_to_loopback_is_refused(monkeypatch, modname):
    """Double résolveur : 1re réponse publique (contrôle), 2e réponse 127.0.0.1
    (rebinding au moment de la connexion) → la 2e passe par la même garde."""
    mod = importlib.import_module(modname)
    fake, _ = _resolver(PUBLIC, "127.0.0.1")
    monkeypatch.setattr(socket, "getaddrinfo", fake)
    assert mod.assert_egress_allowed("https://rebind.example.com/x") == PUBLIC
    with pytest.raises(mod.EgressBlockedError):
        mod.assert_egress_allowed("https://rebind.example.com/x")
```

- [ ] **Step 2: Échec attendu** — `cd core && uv run pytest tests/test_egress_dns_pinning.py -v`. Attendu : 5 FAIL sur `returns_the_validated_address` (`None == '93.184.216.34'`) ; les 5 `second_resolution` PASS (comportement déjà correct).

- [ ] **Step 3: Implémenter** — dans **chacun des cinq fichiers** : changer la signature `def assert_egress_allowed(url: str) -> None:` en `def assert_egress_allowed(url: str) -> str:` et ajouter, après la ligne `raise EgressBlockedError(f"hôte hors allowlist d'egress : {host!r}")` (dernière du corps), une ligne finale :

```python
    return str(addresses[0])  # REV-273d : adresse validée, à utiliser pour se connecter
```
(Les 5 corps sont identiques sur ce point — vérifié — et `addresses` est toujours non vide : un `getaddrinfo` vide lèverait avant ; si `getaddrinfo` renvoyait `[]`, la boucle ne lève rien et `addresses[0]` lèverait `IndexError` : ajouter dans chaque fichier, juste avant `for ip in addresses:`, `if not addresses:\n        raise EgressBlockedError(f"hôte non résoluble : {host!r}")`.)

- [ ] **Step 4: Succès** — `cd core && uv run pytest tests/test_egress_dns_pinning.py tests/test_pipeline_egress.py tests/test_alert_egress.py tests/test_harvest_egress.py tests/test_copilot_egress.py tests/test_search_egress.py -v`. Attendu : vert.

- [ ] **Step 5: Commit** — `refactor(core): assert_egress_allowed retourne l'adresse validée (REV-273d)` + trailer.

---

### Task L2c-6: connexion épinglée sur l'IP validée pour `requests` — pipelines et alerts (REV-273d, 2/5)

**Files:**
- Create: `core/app/net_pin.py`
- Modify: `core/app/pipelines/egress.py:15-23` (imports), `:93-101` (`_GuardedHTTPAdapter`) ; `core/app/alerts/egress.py` (même motif : classe `_GuardedHTTPAdapter` du fichier, ligne ~60)
- Test: `core/tests/test_net_pin.py` (nouveau), `core/tests/test_pipeline_egress.py`, `core/tests/test_alert_egress.py`

**Interfaces:**
- Produces (`app.net_pin`, module racine sans dépendance applicative, donc hors contrat de couches) :
  - `pinned_adapter(base: type[HTTPAdapter], resolve: Callable[[str], str | None]) -> type[HTTPAdapter]` : sous-classe dont les connexions TCP (http et https) visent `resolve(host)` si non `None` ; `Host:` et SNI/vérification TLS conservent le nom d'origine (substitution de `_dns_host` limitée à `_new_conn()`).
  - `pin_httpx_request(request: httpx.Request, ip: str | None) -> None` (utilisé par L2c-7).
- Consumes : `assert_egress_allowed(url) -> str` (L2c-5).
- Dans chaque module d'egress : `def _pin_ip(host: str) -> str` (privé, appelle `assert_egress_allowed` **par nom global** pour rester neutralisable par les fixtures existantes), puis `class _GuardedHTTPAdapter(pinned_adapter(requests.adapters.HTTPAdapter, _pin_ip))`.

- [ ] **Step 1: Tests échouants** — créer `core/tests/test_net_pin.py` :

```python
# SPDX-License-Identifier: Apache-2.0
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import httpx
import requests
from requests.adapters import HTTPAdapter

from app.net_pin import pin_httpx_request, pinned_adapter


def test_pinned_adapter_connects_to_resolved_ip_and_keeps_host_header():
    seen: dict = {}

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            seen["host"] = self.headers["Host"]
            self.send_response(200)
            self.send_header("Content-Length", "2")
            self.end_headers()
            self.wfile.write(b"ok")

        def log_message(self, *args):
            pass

    srv = HTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    port = srv.server_address[1]
    asked: list[str] = []

    def resolve(host: str) -> str:
        asked.append(host)
        return "127.0.0.1"

    try:
        session = requests.Session()
        session.mount("http://", pinned_adapter(HTTPAdapter, resolve)())
        # `.invalid` ne résout jamais : sans épinglage la requête échouerait.
        resp = session.get(f"http://pinned.invalid:{port}/", timeout=5)
    finally:
        srv.shutdown()
    assert resp.status_code == 200
    assert seen["host"] == f"pinned.invalid:{port}"
    assert asked == ["pinned.invalid"]


def test_pinned_adapter_without_pin_falls_back_to_normal_dns():
    session = requests.Session()
    session.mount("http://", pinned_adapter(HTTPAdapter, lambda host: None)())
    try:
        session.get("http://pinned.invalid:9/", timeout=2)
    except requests.exceptions.ConnectionError:
        pass  # DNS réel : échec attendu, preuve qu'aucune IP n'a été imposée
    else:
        raise AssertionError("pinned.invalid ne devrait pas résoudre")


def test_pin_httpx_request_rewrites_target_keeps_host_and_sni():
    req = httpx.Request("GET", "https://example.test:8443/x?y=1")
    pin_httpx_request(req, "93.184.216.34")
    assert req.url.host == "93.184.216.34" and req.url.port == 8443
    assert req.url.path == "/x" and req.url.query == b"y=1"
    assert req.headers["host"] == "example.test:8443"
    assert req.extensions["sni_hostname"] == "example.test"


def test_pin_httpx_request_none_is_a_noop():
    req = httpx.Request("GET", "https://example.test/x")
    pin_httpx_request(req, None)
    assert req.url.host == "example.test" and "sni_hostname" not in req.extensions
```
Ajouter à `core/tests/test_pipeline_egress.py` (ce fichier ne neutralise pas la garde) :

```python
def test_guarded_session_refuses_dns_rebinding_between_check_and_connect(monkeypatch):
    """Double résolveur : le contrôle de send() voit une IP publique, la
    résolution faite au moment de connecter voit 127.0.0.1 → refus."""
    answers = iter(["93.184.216.34", "127.0.0.1"])

    def fake_getaddrinfo(host, *args, **kwargs):
        ip = next(answers, "127.0.0.1")
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (ip, 0))]

    monkeypatch.setattr(socket, "getaddrinfo", fake_getaddrinfo)
    session = build_guarded_session()
    with pytest.raises(EgressBlockedError):
        session.get("http://rebind.example.com:9/x", timeout=1.0)
```
et le pendant dans `core/tests/test_alert_egress.py` (avec `from app.alerts.egress import build_guarded_session`, `EgressBlockedError` ; ajouter `import socket`/`import pytest` s'ils manquent) : même corps, `build_guarded_session` d'`app.alerts.egress`, nom `test_alert_guarded_session_refuses_dns_rebinding_between_check_and_connect`.

- [ ] **Step 2: Échec attendu** — `cd core && uv run pytest tests/test_net_pin.py tests/test_pipeline_egress.py::test_guarded_session_refuses_dns_rebinding_between_check_and_connect tests/test_alert_egress.py -k "pin or rebinding" -v`. Attendu : `test_net_pin.py` FAIL à l'import (`ModuleNotFoundError: app.net_pin`) ; les tests rebinding FAIL (`ConnectionError`/`NameResolutionError` au lieu de `EgressBlockedError` : la connexion refait sa propre résolution, non gardée).

- [ ] **Step 3: Implémenter `core/app/net_pin.py`**

```python
# SPDX-License-Identifier: Apache-2.0
"""Épinglage de la connexion sur l'adresse validée par la garde d'egress
(REV-273d, anti-TOCTOU DNS). Module sans dépendance applicative : partagé
par les 5 copies de la garde (pipelines/alerts/harvest/copilot/search) que
le contrat de couches empêche de s'importer entre elles.

`resolve(host)` doit appliquer la garde d'egress et retourner l'IP validée
(ou None pour ne rien imposer, ex. garde neutralisée en test) ; une
adresse interne lève EgressBlockedError. Le nom d'hôte d'origine reste
utilisé pour `Host:` et pour le SNI/la vérification du certificat."""

from collections.abc import Callable

import httpx
from requests.adapters import HTTPAdapter
from urllib3.connection import HTTPConnection, HTTPSConnection
from urllib3.connectionpool import HTTPConnectionPool, HTTPSConnectionPool

Resolve = Callable[[str], str | None]


def pinned_adapter(base: type[HTTPAdapter], resolve: Resolve) -> type[HTTPAdapter]:
    """Sous-classe de `base` dont les connexions TCP visent `resolve(host)`.
    urllib3 2.x : `host` (donc Host: et server_hostname TLS) est dérivé de
    `_dns_host` ; on le substitue le temps de `_new_conn()` seulement.
    ponytail: première adresse validée uniquement (pas de repli sur les
    suivantes) ; ProxyManager (variables HTTP(S)_PROXY) non épinglé, la
    garde de send() y reste la seule protection."""

    def _pin(conn_cls):
        class Pinned(conn_cls):  # type: ignore[misc, valid-type]
            def _new_conn(self):
                real = self._dns_host
                ip = resolve(real)
                if ip:
                    self._dns_host = ip
                try:
                    return super()._new_conn()
                finally:
                    self._dns_host = real

        return Pinned

    class _HTTPPool(HTTPConnectionPool):
        ConnectionCls = _pin(HTTPConnection)

    class _HTTPSPool(HTTPSConnectionPool):
        ConnectionCls = _pin(HTTPSConnection)

    class PinnedAdapter(base):  # type: ignore[misc, valid-type]
        def init_poolmanager(self, *args, **kwargs):
            super().init_poolmanager(*args, **kwargs)
            self.poolmanager.pool_classes_by_scheme = {"http": _HTTPPool, "https": _HTTPSPool}

    return PinnedAdapter


def pin_httpx_request(request: httpx.Request, ip: str | None) -> None:
    """Redirige `request` vers `ip` en gardant `Host:` (déjà posé à la
    construction) et le SNI/la vérification TLS (extension httpcore
    `sni_hostname`)."""
    if not ip:
        return
    request.extensions["sni_hostname"] = request.url.host
    request.url = request.url.copy_with(host=ip)
```

- [ ] **Step 4: Câbler pipelines et alerts** — `core/app/pipelines/egress.py` : ajouter `from app.net_pin import pinned_adapter` aux imports ; avant `_GuardedHTTPAdapter` :

```python
def _pin_ip(host: str) -> str:
    # Lookup du nom global à l'appel : reste neutralisable par les fixtures
    # de tests (`assert_egress_allowed` remplacé par un lambda → None → pas d'épinglage).
    return assert_egress_allowed(f"http://[{host}]" if ":" in host else f"http://{host}")
```
et `class _GuardedHTTPAdapter(pinned_adapter(requests.adapters.HTTPAdapter, _pin_ip)):`. Dans `core/app/alerts/egress.py` : mêmes deux ajouts (import `from app.net_pin import pinned_adapter`, `_pin_ip` identique, base de `_GuardedHTTPAdapter` remplacée). Typage : `_pin_ip` renvoie `str` (la neutralisation en test renvoie `None`, hors typage).

- [ ] **Step 5: Succès** — `cd core && uv run pytest tests/test_net_pin.py tests/test_pipeline_egress.py tests/test_alert_egress.py tests/test_alert_notify.py tests/test_pipeline_connector_runtime.py -v`. Attendu : vert (les tests REST contre `pytest-httpserver` 127.0.0.1 passent : la garde neutralisée renvoie `None` → pas d'épinglage ; `test_guarded_session_blocks_before_connection` inchangé).

- [ ] **Step 6: Contrat de couches** — `cd core && uv run lint-imports`. Attendu : OK (`app.net_pin` n'importe rien d'`app.*`). Si le contrat « layers » refuse un module racine non listé, l'ajouter au bas des `layers` dans `pyproject.toml` à côté de `app.sql_ident` (même cas : module racine utilitaire).

- [ ] **Step 7: Commit** — `fix(core): connexion épinglée sur l'IP validée (requests : pipelines, alerts) — anti-TOCTOU DNS (REV-273d)` + trailer.

---

### Task L2c-7: transport `httpx` épinglé — harvest, search, copilot (REV-273d, 3/5)

**Files:**
- Modify: `core/app/harvest/egress.py:5-20` (imports) et `_GuardedTransport.handle_request` (~l.84-86) ; `core/app/search/egress.py` (`_GuardedTransport.handle_request`) ; `core/app/copilot/egress.py` (`_GuardedAsyncTransport.handle_async_request`)
- Test: `core/tests/test_egress_dns_pinning.py`

**Interfaces:**
- Consumes : `assert_egress_allowed(url) -> str` (L2c-5), `pin_httpx_request(request, ip)` (L2c-6).
- Produces : dans les trois transports, `ip = assert_egress_allowed(str(request.url)); pin_httpx_request(request, ip)` avant l'appel de `self._inner`. Les redirections httpx repassent par le transport (chaque saut re-validé et re-épinglé).

- [ ] **Step 1: Tests échouants** — ajouter à `core/tests/test_egress_dns_pinning.py` :

```python
import asyncio

import httpx


class _Recorder(httpx.BaseTransport):
    def __init__(self):
        self.seen: list[httpx.Request] = []

    def handle_request(self, request):
        self.seen.append(request)
        return httpx.Response(200, content=b"ok", request=request)


class _AsyncRecorder(httpx.AsyncBaseTransport):
    def __init__(self):
        self.seen: list[httpx.Request] = []

    async def handle_async_request(self, request):
        self.seen.append(request)
        return httpx.Response(200, content=b"ok", request=request)


@pytest.mark.parametrize(
    ("modname", "cls"),
    [
        ("app.harvest.egress", "_GuardedTransport"),
        ("app.search.egress", "_GuardedTransport"),
    ],
)
def test_sync_httpx_transport_connects_to_validated_ip(monkeypatch, modname, cls):
    mod = importlib.import_module(modname)
    fake, _ = _resolver(PUBLIC)
    monkeypatch.setattr(socket, "getaddrinfo", fake)
    inner = _Recorder()
    client = httpx.Client(transport=getattr(mod, cls)(inner))
    assert client.get("https://api.example.com:8443/v1/x").status_code == 200
    req = inner.seen[0]
    assert req.url.host == PUBLIC and req.url.port == 8443
    assert req.headers["host"] == "api.example.com:8443"
    assert req.extensions["sni_hostname"] == "api.example.com"


def test_copilot_async_transport_connects_to_validated_ip(monkeypatch):
    from app.copilot import egress as mod

    fake, _ = _resolver(PUBLIC)
    monkeypatch.setattr(socket, "getaddrinfo", fake)
    inner = _AsyncRecorder()

    async def go():
        async with httpx.AsyncClient(transport=mod._GuardedAsyncTransport(inner)) as client:
            return await client.get("https://llm.example.com/v1/chat")

    assert asyncio.run(go()).status_code == 200
    req = inner.seen[0]
    assert req.url.host == PUBLIC
    assert req.headers["host"] == "llm.example.com"
    assert req.extensions["sni_hostname"] == "llm.example.com"


def test_httpx_transport_neutralised_guard_does_not_pin(monkeypatch):
    """Garde remplacée (fixtures de tests existantes) → None → pas d'épinglage."""
    from app.harvest import egress as mod

    monkeypatch.setattr(mod, "assert_egress_allowed", lambda url: None)
    inner = _Recorder()
    httpx.Client(transport=mod._GuardedTransport(inner)).get("http://127.0.0.1:1234/x")
    assert inner.seen[0].url.host == "127.0.0.1"
    assert "sni_hostname" not in inner.seen[0].extensions
```

- [ ] **Step 2: Échec attendu** — `cd core && uv run pytest tests/test_egress_dns_pinning.py -k "httpx or async_transport" -v`. Attendu : `…connects_to_validated_ip` FAIL (`req.url.host == 'api.example.com'`), `neutralised` PASS.

- [ ] **Step 3: Implémenter** — dans `harvest/egress.py`, `search/egress.py`, `copilot/egress.py` : ajouter `from app.net_pin import pin_httpx_request` (ordre alphabétique des imports `app.*` de chaque fichier) et remplacer la ligne `assert_egress_allowed(str(request.url))` de la méthode de transport par :

```python
        pin_httpx_request(request, assert_egress_allowed(str(request.url)))
```
(identique dans `handle_request` — harvest, search — et `handle_async_request` — copilot ; le reste, dont le plafond de taille de réponse de harvest, est inchangé).

- [ ] **Step 4: Succès** — `cd core && uv run pytest tests/test_egress_dns_pinning.py tests/test_harvest_egress.py tests/test_copilot_egress.py tests/test_search_egress.py tests/test_harvest_stac_connector.py tests/test_harvest_arcgis_connector.py -v`. Attendu : vert.

- [ ] **Step 5: Commit** — `fix(core): transports httpx épinglés sur l'IP validée (harvest, search, copilot) — anti-TOCTOU DNS (REV-273d)` + trailer.

---

### Task L2c-8: DSN Postgres — `hostaddr` épinglé sur l'IP validée (REV-273d, 4/5)

**Files:**
- Modify: `core/app/pipelines/egress.py` (ajout après `assert_dsn_egress_allowed`, ~l.91), `core/app/pipelines/connector_runtime.py:49-54` (import) et `_stream_sql` (ligne `engine = sa.create_engine(dsn, connect_args=_timeout_connect_args(backend))`)
- Test: `core/tests/test_pipeline_egress.py`, `core/tests/test_pipeline_connector_runtime.py`

**Interfaces:**
- Produces : `dsn_pin_connect_args(dsn: str) -> dict[str, str]` dans `app.pipelines.egress` : `{"hostaddr": "<ip validée>"}` pour un DSN `postgresql*` à hôte unique **nom** (pas littéral IP, pas socket unix, pas de `host`/`hostaddr` en query) ; `{}` sinon. `host` reste le nom d'origine (vérification `verify-full` conservée par libpq). Lève `EgressBlockedError` si la résolution du moment est interne (rebinding).
- Limite assumée (`ponytail:` dans le code) : mssql/oracle (descripteur TNS/ODBC, déjà refusés quand l'hôte passe par un paramètre de pilote) n'ont pas d'équivalent `hostaddr` fiable → seule la garde en amont s'applique ; snowflake/bigquery sont hors garde d'hôte (`_NO_HOST_BACKENDS`).

- [ ] **Step 1: Tests échouants** — ajouter à `core/tests/test_pipeline_egress.py` (importer `dsn_pin_connect_args` dans le bloc `from app.pipelines.egress import (...)` du haut) :

```python
def _seq_getaddrinfo(*ips):
    it = iter(ips)

    def fake(host, *args, **kwargs):
        ip = next(it, ips[-1])
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (ip, 0))]

    return fake


def test_dsn_pin_sets_hostaddr_to_the_validated_ip(monkeypatch):
    monkeypatch.setattr(socket, "getaddrinfo", _seq_getaddrinfo("93.184.216.34"))
    assert dsn_pin_connect_args("postgresql://u:p@db.example.com:5432/d") == {
        "hostaddr": "93.184.216.34"
    }


def test_dsn_pin_refuses_rebinding_to_loopback(monkeypatch):
    # 1re résolution (assert_dsn_egress_allowed) publique, 2e (épinglage) = 127.0.0.1
    monkeypatch.setattr(socket, "getaddrinfo", _seq_getaddrinfo("93.184.216.34", "127.0.0.1"))
    dsn = "postgresql://u:p@db.example.com/d"
    assert_dsn_egress_allowed(dsn)
    with pytest.raises(EgressBlockedError):
        dsn_pin_connect_args(dsn)


@pytest.mark.parametrize(
    "dsn",
    [
        "postgresql://u:p@93.184.216.34/d",  # littéral IP : rien à épingler
        "postgresql://u:p@/d?host=/var/run/postgresql",  # socket unix
        "postgresql://u:p@db.example.com/d?hostaddr=93.184.216.34",  # déjà épinglé
        "mssql+pymssql://u:p@db.example.com/d",  # pas d'équivalent hostaddr
    ],
)
def test_dsn_pin_is_empty_when_not_applicable(dsn, monkeypatch):
    monkeypatch.setattr(socket, "getaddrinfo", _seq_getaddrinfo("93.184.216.34"))
    assert dsn_pin_connect_args(dsn) == {}
```
(`assert_dsn_egress_allowed` à ajouter à l'import de ce fichier s'il n'y est pas.) Ajouter à `core/tests/test_pipeline_connector_runtime.py` le test de câblage :

```python
def test_stream_sql_passes_hostaddr_pin_to_the_driver(monkeypatch):
    seen: dict = {}

    def fake_create_engine(dsn, connect_args=None, **kw):
        seen["connect_args"] = connect_args
        raise RuntimeError("stop")

    monkeypatch.setattr(connector_runtime.sa, "create_engine", fake_create_engine)
    monkeypatch.setattr(
        connector_runtime, "dsn_pin_connect_args", lambda dsn: {"hostaddr": "93.184.216.34"}
    )
    with pytest.raises(RuntimeError, match="stop"):
        list(connector_runtime._stream_sql("postgresql://u:p@db.example.com/d", "SELECT 1"))
    assert seen["connect_args"]["hostaddr"] == "93.184.216.34"
    assert "connect_timeout" in seen["connect_args"]  # les délais P16.03 sont conservés
```

- [ ] **Step 2: Échec attendu** — `cd core && uv run pytest tests/test_pipeline_egress.py -k dsn_pin tests/test_pipeline_connector_runtime.py::test_stream_sql_passes_hostaddr_pin_to_the_driver -v` (si pytest refuse deux sélecteurs avec `-k`, lancer en deux commandes). Attendu : `ImportError: cannot import name 'dsn_pin_connect_args'`.

- [ ] **Step 3: Implémenter** — `pipelines/egress.py`, après `assert_dsn_egress_allowed` :

```python
def dsn_pin_connect_args(dsn: str) -> dict[str, str]:
    """REV-273d : épingle la connexion Postgres sur l'IP validée par la garde
    (paramètre libpq `hostaddr` ; `host` reste le nom → `verify-full` intact).
    `{}` quand il n'y a rien à épingler. ponytail: mssql/oracle sans
    équivalent fiable (descripteur TNS/ODBC) — seule la garde amont s'applique."""
    url = make_url(dsn)
    host = url.host or ""
    if (
        not url.get_backend_name().startswith("postgresql")
        or not host
        or host.startswith("/")
        or "," in host
        or "host" in url.query
        or "hostaddr" in url.query
    ):
        return {}
    try:
        ipaddress.ip_address(host)
        return {}  # littéral : déjà validé par assert_dsn_egress_allowed
    except ValueError:
        pass
    ip = assert_egress_allowed(f"http://{host}")
    return {"hostaddr": ip} if ip else {}
```
`connector_runtime.py` : ajouter `dsn_pin_connect_args` au bloc `from app.pipelines.egress import (...)` (ordre alphabétique) ; dans `_stream_sql` remplacer la création de l'engine par :

```python
    connect_args = {**_timeout_connect_args(backend), **dsn_pin_connect_args(dsn)}
    engine = sa.create_engine(dsn, connect_args=connect_args)
```
(`dsn_pin_connect_args` n'est appelé que dans le `if backend not in _NO_HOST_BACKENDS` implicite : pour snowflake/bigquery, `get_backend_name()` ne commence pas par `postgresql` donc retourne `{}` sans résolution.)

- [ ] **Step 4: Succès** — `cd core && uv run pytest tests/test_pipeline_egress.py tests/test_pipeline_connector_runtime.py -v`. Attendu : vert (les tests postgres réels, `pg_engine`, passent : DSN sur 127.0.0.1 littéral → `{}`).

- [ ] **Step 5: Commit** — `fix(core): DSN Postgres épinglé sur l'IP validée via hostaddr (REV-273d)` + trailer.

---

### Task L2c-9: endpoint S3 compatible — résolveur aiohttp épinglé (REV-273d, 5/5)

**Files:**
- Modify: `core/app/pipelines/egress.py` (import `socket`/`AbstractResolver` en tête, classe en fin de fichier), `core/app/pipelines/connector_runtime.py:49-54` (import) et `_blob_fs_kwargs` (L2c-4)
- Test: `core/tests/test_pipeline_egress.py`, `core/tests/test_pipeline_connector_runtime.py`

**Interfaces:**
- Consumes : `_blob_fs_kwargs(payload) -> dict` (L2c-4), `_pin_ip(host) -> str` (L2c-6), `assert_egress_allowed` (L2c-5). **Dépend de L2c-4 ; à exécuter après REV-197 si possible** (même fonction `materialize_blob_connector`, mais cette tâche ne touche que `_blob_fs_kwargs`).
- Produces : `class PinnedAioResolver(aiohttp.abc.AbstractResolver)` dans `app.pipelines.egress` : `async resolve(host, port=0, family=socket.AF_INET) -> list[dict]` renvoie l'IP validée (`hostname` = nom d'origine, donc SNI/certificat inchangés) ; lève `EgressBlockedError` sur adresse interne au moment de la résolution aiohttp. `_blob_fs_kwargs` ajoute `connector_args={"resolver": PinnedAioResolver()}` à `config_kwargs` du s3 **quand `payload.endpointUrl` est défini** (endpoint = cible réseau libre ; le S3 AWS standard n'est pas concerné).
- **Hors de portée de ce plan (à rejouer en L6)** : le chemin réel dlt → fsspec → s3fs → aiobotocore → aiohttp avec un vrai MinIO. Ici : (a) le résolveur est testé isolément, (b) on vérifie que `filesystem(...)` reçoit bien `kwargs.config_kwargs.connector_args.resolver` (noms vérifiés dans les sources installées : `s3fs.S3FileSystem.__init__(config_kwargs=…)`, `aiobotocore.config.AioConfig(connector_args=…)`).

- [ ] **Step 1: Tests échouants** — `core/tests/test_pipeline_egress.py` (importer `asyncio` et `PinnedAioResolver`) :

```python
def test_pinned_aio_resolver_returns_the_validated_ip_and_keeps_hostname(monkeypatch):
    monkeypatch.setattr(socket, "getaddrinfo", _seq_getaddrinfo("93.184.216.34"))
    infos = asyncio.run(PinnedAioResolver().resolve("minio.example.com", 9000))
    assert infos[0]["host"] == "93.184.216.34"
    assert infos[0]["hostname"] == "minio.example.com"
    assert infos[0]["port"] == 9000 and infos[0]["family"] == socket.AF_INET


def test_pinned_aio_resolver_refuses_an_internal_answer(monkeypatch):
    monkeypatch.setattr(socket, "getaddrinfo", _seq_getaddrinfo("127.0.0.1"))
    with pytest.raises(EgressBlockedError):
        asyncio.run(PinnedAioResolver().resolve("minio.example.com", 9000))
```
`core/tests/test_pipeline_connector_runtime.py` :

```python
def test_materialize_blob_connector_pins_the_s3_endpoint_resolver(
    monkeypatch, conn, session, tenant, user
):
    from app.pipelines.egress import PinnedAioResolver

    _create_secret(
        session,
        tenant,
        user,
        name="s3-pin",
        kind="s3_credentials",
        payload={
            "kind": "s3_credentials",
            "awsAccessKeyId": "AKIA123",
            "awsSecretAccessKey": "shh",
            "endpointUrl": "http://minio.local:9000",
        },
    )
    captured: dict = {}
    _patch_blob_internals(monkeypatch, captured)
    connector_runtime.materialize_blob_connector(
        conn,
        secret_resolver=connector_runtime.PostgresSecretResolver(session, tenant.id, user),
        node_id="bp",
        params=ReaderConnectorBlobParams(
            secretName="s3-pin", path="s3://bucket/data.csv", format="csv"
        ),
        view_name="node_bp",
    )
    cfg = captured["fs_kwargs"]["config_kwargs"]
    assert isinstance(cfg["connector_args"]["resolver"], PinnedAioResolver)


def test_materialize_blob_connector_without_endpoint_has_no_custom_resolver(
    monkeypatch, conn, session, tenant, user
):
    _create_secret(
        session,
        tenant,
        user,
        name="s3-aws",
        kind="s3_credentials",
        payload={
            "kind": "s3_credentials",
            "awsAccessKeyId": "AKIA123",
            "awsSecretAccessKey": "shh",
        },
    )
    captured: dict = {}
    _patch_blob_internals(monkeypatch, captured)
    connector_runtime.materialize_blob_connector(
        conn,
        secret_resolver=connector_runtime.PostgresSecretResolver(session, tenant.id, user),
        node_id="ba",
        params=ReaderConnectorBlobParams(
            secretName="s3-aws", path="s3://bucket/data.csv", format="csv"
        ),
        view_name="node_ba",
    )
    assert "connector_args" not in captured["fs_kwargs"]["config_kwargs"]
```

- [ ] **Step 2: Échec attendu** — `cd core && uv run pytest tests/test_pipeline_egress.py -k aio_resolver -v` puis `uv run pytest tests/test_pipeline_connector_runtime.py -k "pins_the_s3 or without_endpoint" -v`. Attendu : `ImportError PinnedAioResolver` / `KeyError: 'connector_args'`.

- [ ] **Step 3: Implémenter** — `pipelines/egress.py` : en tête `from aiohttp.abc import AbstractResolver` ; en fin de fichier :

```python
class PinnedAioResolver(AbstractResolver):
    """Résolveur aiohttp (donc aiobotocore/s3fs, endpoint S3 compatible) qui
    n'accepte que les adresses validées par la garde d'egress au moment même
    de la connexion (REV-273d). `hostname` reste le nom d'origine : SNI et
    vérification de certificat inchangés. aiohttp ne passe pas par le
    résolveur pour un littéral IP (celui-ci est validé en amont par
    assert_egress_allowed(endpointUrl))."""

    async def resolve(self, host, port=0, family=socket.AF_INET):
        ip = _pin_ip(host)
        return [
            {
                "hostname": host,
                "host": ip,
                "port": port,
                "family": socket.AF_INET6 if ":" in ip else socket.AF_INET,
                "proto": 0,
                "flags": socket.AI_NUMERICHOST,
            }
        ]

    async def close(self) -> None:
        return None
```
(`_pin_ip` défini en L2c-6 est placé avant `_GuardedHTTPAdapter` : il reste référencé par nom à l'appel.) `connector_runtime.py` : ajouter `PinnedAioResolver` à l'import `from app.pipelines.egress import (...)` ; dans `_blob_fs_kwargs` (branche s3), remplacer le `return` s3 par :

```python
    if payload.kind == "s3_credentials":
        cfg: dict = {"connect_timeout": t, "read_timeout": q}
        if payload.endpointUrl:  # cible réseau libre : épingler la résolution (REV-273d)
            cfg["connector_args"] = {"resolver": PinnedAioResolver()}
        return {"kwargs": {"config_kwargs": cfg}}
```

- [ ] **Step 4: Succès** — `cd core && uv run pytest tests/test_pipeline_egress.py tests/test_pipeline_connector_runtime.py -v`. Attendu : vert.

- [ ] **Step 5: Commit** — `fix(core): résolveur aiohttp épinglé pour l'endpoint S3 compatible (REV-273d)` + trailer.

---

### Task L2c-10: portes de qualité du fragment L2c

**Files:** aucun (vérification) ; éventuels correctifs de format sur les fichiers des tâches L2c-1 à 9.

- [ ] **Step 1: Lint/format** — `cd core && uv run ruff check . && uv run ruff format --check .`. Attendu : propre ; sinon `uv run ruff format app tests` puis amender dans un commit `style(core): ruff format (L2c)`.
- [ ] **Step 2: mypy strict sur le module touché** — `cd core && uv run mypy --strict app/auth app/secrets app/analytics app/copilot app/admin_tools app/roles`. Attendu : `Success`. Points sensibles : `delete_secret_unless_used` (walrus + `facts.get`), `smtp_tls_violation`, validateurs `-> "SecretCreate"` ; `app/copilot/egress.py` est aussi sous `--strict` : `assert_egress_allowed -> str` doit renvoyer `str(addresses[0])` sur tous les chemins, et l'appel `pin_httpx_request(request, assert_egress_allowed(...))` doit typer (`Resolve`/`str | None` accepte `str`).
- [ ] **Step 3: Contrat de couches** — `cd core && uv run lint-imports`. Attendu : tous les contrats tenus (40 entrées + `app.net_pin` non listé).
- [ ] **Step 4: OpenAPI + types TS (preuve de non-régression)** — aucun schéma d'API n'est censé changer (validateurs Pydantic sans effet sur le JSON Schema ; `SecretInUseError` → 409 texte). Rejouer quand même l'incantation exacte de CLAUDE.md :
```bash
cd core && PYTHONPATH=. \
  CORE_SECRETS_MASTER_KEY="AAECAwQFBgcICQoLDA0ODxAREhMUFRYXGBkaGxwdHh8=" \
  uv run python scripts/export_openapi.py openapi.json
cd ../shell && npm run gen:api-types
cd .. && git status --short core/openapi.json shell/src/api/generated/core-schema.d.ts
```
Attendu : aucun fichier modifié (diff vide, légitime). Si un diff apparaît (p. ex. description de `SmtpCredentialsPayload` si la docstring a été retouchée), le committer : `chore(api): régénérer OpenAPI et types TS (L2c)`.
- [ ] **Step 5: Suite ciblée complète du fragment** — `cd core && uv run pytest tests/test_secrets_routes.py tests/test_secrets_schemas.py tests/test_secrets_repository.py tests/test_mcp_tools_secrets.py tests/test_alert_notify.py tests/test_alert_egress.py tests/test_pipeline_egress.py tests/test_pipeline_connector_runtime.py tests/test_harvest_egress.py tests/test_copilot_egress.py tests/test_search_egress.py tests/test_egress_dns_pinning.py tests/test_net_pin.py tests/test_deployability.py -v`. Attendu : vert. (`CORE_TEST_DATABASE_URL` doit pointer le `postgis-test` réel pour les tests `pg_engine` : sinon ils skippent silencieusement — piège SP-43 ; relever le nombre de `skipped`.)
- [ ] **Step 6: Inventaire** — aucune route/outil MCP/route shell nouvelle (modification de comportement seulement) : pas de ligne à ajouter à `docs/revue/inventaire-fonctionnalites.jsonl` ; ne PAS relancer `feature_health_cli.py --write` pour ce fragment (à faire une fois à la clôture du plan, section Transverse de la spec).
- [ ] **Step 7: Notes de clôture à consigner** (ledger `.superpowers/sdd/backlogA-L2c-*`, archive d'exécution, REV-273) : (b)(c)(d)(e) livrés ; limites assumées — mssql/oracle sans épinglage, proxys non épinglés, première IP seulement, gardes blob entre éléments ; **à rejouer en L6 sur stack réelle** : chemin S3 `PinnedAioResolver` avec un vrai MinIO, STARTTLS/SMTPS contre un vrai relais, `hostaddr` + `sslmode=verify-full` contre un vrai Postgres ; secrets SMTP existants `useTls=false` : messages d'erreur à l'envoi, à signaler dans le `CHANGELOG.md` (`### Changed` sous `[Unreleased]`) ; nouvelles variables `CORE_PIPELINES_BLOB_MAX_FILES|MAX_BYTES|TIMEOUT_S` documentées.

### Task CLOSE: Clôture du plan A

**Files:**
- Modify: `CLAUDE.md` (§ `### Livré`, UNE ligne ajoutée après la dernière puce « Audit pré-release P22/P23/P26/P30/P32/P35/P36 … »)
- Modify: `docs/superpowers/2026-08-27-historique-execution-continu.md` (entrée détaillée en fin de fichier)
- Modify: `docs/revue/2026-09-04-backlog.md` (états REV du plan A + sommaire)
- Modify: `docs/revue/inventaire-fonctionnalites.jsonl` (seulement si une route REST/outil MCP/route shell nouvelle a été livrée par L2/L3 ; `save_app_config.expectedVersion` = paramètre, pas une surface nouvelle)
- Regénérer: `docs/revue/bilan-fonctionnalites.{html,md}`, `docs/revue/historique-sante.jsonl` (sortie de la commande)
- Modify: `docs/revue/2026-09-04-analyse-gaps.md` (GAP-nn concernés, s'il y en a : GAP-82 « can_manage_collections » est la jumelle de REV-185 → vérifier son état, voir Step 3)

**Interfaces:**
- Consumes: tout le plan A (L0, L2, L3) mergé sur `dev`, suites vertes. REV-269 reste une checklist (Task L0-6).
- Produces: documentation alignée sur le code (règle CLAUDE.md « obligatoire dans le même geste »).

- [ ] **Step 1: Vérifier la fermeture par le code, pas par le récit (piège n°12)**

Pour chaque REV candidate à `fermé`, vérifier AVANT d'éditer qu'un commit du plan la livre :
```bash
git log --oneline e820ee88..HEAD | grep -iE 'REV-(111|116|185|186|195|196|197|198|199|239|271|272|273|275|290)'
```
Chaque REV du tableau Step 2 doit apparaître dans ≥ 1 sujet de commit (convention de commit du plan : `REV-nnn` dans le sujet ou le corps). Une REV sans commit = ne pas la fermer, la laisser dans son état précédent.

- [ ] **Step 2: Mettre à jour la ligne `**État :**` de chaque REV du plan A**

États attendus (Edit sur la première ligne `- **État` sous chaque `### REV-nnn`) ; remplacer `ouvert.` par :

| REV | État final | Texte à écrire |
|---|---|---|
| 111 | fermé | déjà fait (Task L0-2) |
| 116 | fermé | déjà fait (Task L0-3) |
| 185 | fermé | `fermé (2026-10-03, plan A lot L2) — \`get_readable_collection()\` reçoit \`can_manage_collections=has_privilege(user, Privilege.ADMIN_COLLECTIONS_MANAGE)\` sur les 5 sites de lecture de \`core/app/features/routes.py\` et sur les jumelles (tuiles, pièces jointes, MCP \`query_features\`/\`run_analytics_query\`, SQL analyste, \`alerts/jobs._measure_value\`) ; écriture (\`_get_writable\`) volontairement inchangée.` |
| 186 | fermé | `fermé (2026-10-03, plan A lot L2) — \`apply_collection_ddl\` accepte \`sensitive_fields\` (défaut vide) et le transmet à \`sync_masked_role_grants\` au lieu de \`[]\` en dur ; test postgis de non-régression du REVOKE.` |
| 187 | observation | déjà fait (Task L0-3) |
| 188 | observation | déjà fait (Task L0-3) |
| 195 | fermé | `fermé (2026-10-03, plan A lot L3) — \`groupBy: list[str] = []\` optionnel sur \`transform.triangulate\`/\`transform.minimumBoundingCircle\` ; vide = comportement global antérieur.` |
| 196 | fermé | `fermé (2026-10-03, plan A lot L3) — géométries NULL filtrées, DataFrame vide court-circuité, \`triangulate\` sur non-point → \`PipelineRuntimeError\` (400 en preview, plus de 500).` |
| 197 | fermé | `fermé (2026-10-03, plan A lot L2) — \`bucketUrl\` ajouté aux 3 payloads blob (s3/azure/gcs), \`params.path\` doit en porter le préfixe sinon \`ConnectorRuntimeError\` ; un secret existant sans \`bucketUrl\` reste lisible mais l'exécution échoue avec un message explicite (pas de migration silencieuse).` |
| 198 | fermé | `fermé (2026-10-03, plan A lot L3) — \`_JOIN_PARAM_MODELS\` dérivé de \`OP_PARAMS\` ∩ \`BINARY_OPS\` ; test d'inclusion (l'égalité stricte du backlog était fausse).` |
| 199 | fermé | `fermé (2026-10-03, plan A lot L3) — M1-M6 et M8-M12 corrigés ; M7 (message de commit historique) non corrigeable, consigné.` — **à n'écrire que si les 12 Minor sont réellement traités** (vérifier chacun au Step 1) ; sinon `partiellement fermé` avec la liste des Mx restants. |
| 239 | fermé | déjà fait (Task L0-4) |
| 269 | **ouvert** (inchangé) | checklist proposée (Task L0-6), aucune action exécutée |
| 271 | fermé | `fermé (2026-10-03, plan A lot L2) — \`If-Match\`/\`version\` sur les éditeurs carte/dataset/pipeline/rapport/alerte (UX de conflit 412 commune), \`save_app_config.expectedVersion\` (MCP), jumelles \`rollback_config\`/copilote ; \`pipelines/runtime.py\` = écrivain interne, exception documentée.` |
| 272 | **partiellement fermé** | `partiellement fermé (2026-10-03, plan A lot L2) — (b) \`VITE_CORE_URL\` relatif résolu par \`new URL\` et (c) parcours E2E du lien de partage à échéance faits ; (a) tombstone RGPD (sha256 nu → HMAC ou colonne dédiée) bloqué par décision DPO, hors plan.` |
| 273 | **partiellement fermé** | `partiellement fermé (2026-10-03, plan A lots L2/L3) — (b) plafonds du lecteur blob, (c) 409 de suppression de secret filtré par \`can()\`, (d) TOCTOU DNS fermé dans la couche d'egress commune, (e) STARTTLS/SMTP_SSL faits ; (a) rejeu j06-004 sur stack réelle reporté au lot L6.` |
| 275 | **partiellement fermé** | `partiellement fermé (2026-10-03, plan A lot L3) — (c) \`mark_running\` conditionnel + \`cancel\` idempotent, (d) \`mem_limit\` du worker, (e) \`/v1/share-links/{token}\` sous limiteur par IP (60/min) faits ; (a)(b) rejeu \`j06b\` + bascule \`bug(\`→\`test(\` reportés au lot L6 (ne pas basculer sans rejeu). Reste noté : \`ProxyHeadersMiddleware(trusted_hosts="*")\` rend la clé IP falsifiable — décision de déploiement (L1).` |
| 290 | fermé | `fermé (2026-10-03, plan A lot L2) — \`authFetch\` vérifie \`isCoreServed\` (URL relatives résolues via \`new URL(url, coreUrl)\`) et lève hors cœur sans émettre de requête ; vitest + E2E verts.` |

Pour chaque REV non fermée (269, 272, 273, 275) conserver le renvoi existant ; ne rien inventer de plus que la colonne « Texte ».

- [ ] **Step 3: GAP-nn concernés dans `analyse-gaps.md`**

Run : `grep -n "GAP-82" docs/revue/2026-09-04-analyse-gaps.md | cut -c1-160`
GAP-82 (« `get_readable_collection()` sans `can_manage_collections` », jumelle de REV-185) : s'il est listé « 🔴 Ouvert » et que REV-185 est fermée au Step 2, le faire passer en « ✅ Fermé » : déplacer sa ligne de la table Ouvert vers la table Fermé avec le texte `fermé le 2026-10-03 par le plan A (lot L2), REV-185 : lecture seulement, écriture inchangée`, et mettre à jour les effectifs du titre `## État des 83 gaps` (63→ +1 fermé, −1 ouvert) en recomptant à la main les lignes de table. Si GAP-82 est déjà fermé : ne rien changer. Aucun autre GAP n'est touché par le plan A (GAP-17/GAP-22 : Tasks L0-2/L0-3).

- [ ] **Step 4: Recomptage mécanique final du sommaire du backlog**

```bash
sh .superpowers/sdd/backlogA-count-etat.sh docs/revue/2026-09-04-backlog.md
sh .superpowers/sdd/backlogA-count-etat.sh docs/revue/2026-09-04-backlog.md lists
```
Sortie attendue si les 12 REV (111, 116, 185, 186, 195, 196, 197, 198, 199, 239, 271, 290) sont `fermé`, 272/273/275 `partiel` et 269 `ouvert` : `ferme 231`, `observation 2`, `ouvert 38`, `partiel 22`, `total 293`
(arithmétique : 219 + 12 = 231 ; 19 + 3 = 22 ; 53 − 15 = 38 ; 2 observations). Si REV-199 reste partielle : `ferme 230`, `partiel 23`. Reporter exactement les effectifs mesurés, jamais ceux attendus, dans :
- la phrase `**222 fermées, 19 partiellement fermées, 50 ouvertes, 2 observations** sur 293 entrées` (devenue `231 / 22 / 38 / 2` par défaut) avec la mention `2026-10-03, clôture du plan A (lots L0/L2/L3)` et la liste des REV changées d'état ;
- les titres `### ✅ Fermé (n)`, `### 🟡 Partiellement fermé (n)`, `### 🔴 Ouvert (n)`, `### 👁 Observation (2)` et les 3 listes d'ids (copier la sortie `lists`).
Vérification : somme des 4 nombres = 293 et `grep -c '^### REV-' docs/revue/2026-09-04-backlog.md` = 293.

- [ ] **Step 5: Ligne CLAUDE.md § `### Livré` (UNE ligne)**

Insérer, juste après la puce « **Audit pré-release P22/P23/P26/P30/P32/P35/P36 (clôture …** » :
```
- **Backlog plan A (L0 clôtures, L2 sécurité/intégrité, L3 pipelines)** — ferme REV-111/116/185/186/195/196/197/198/199/239/271/290 (`can_manage_collections` en lecture, `bucketUrl` du secret blob, `authFetch` borné au cœur, `If-Match` généralisé, `groupBy` + entrées dégénérées des transformers géométriques), reclasse REV-187/188 en observation ; REV-269/272/273/275 restent partielles (checklist release, DPO, rejeu stack réelle → lot L6).
```
Une seule ligne de puce, aucun récit (règle « une ligne par chantier »). Adapter la liste entre parenthèses aux seules REV réellement fermées au Step 2.

- [ ] **Step 6: Entrée détaillée dans l'archive d'exécution**

Ajouter à la FIN de `docs/superpowers/2026-08-27-historique-execution-continu.md` une section :
```
## Backlog plan A — lots L0/L2/L3 (2026-10-03)

Spec `docs/superpowers/specs/2026-10-03-backlog-lots-l0-l2-l3-design.md`, plan `docs/superpowers/plans/2026-10-03-backlog-lots-l0-l2-l3.md`.

- **L0 (documentaire)** : REV-111 (SP-62) et REV-116 (GAP-22 + P15) fermées, `analyse-gaps.md` aligné (trois endroits chacune) ; REV-187/188 reclassées `observation` ; REV-239 fermée pour D56 (historique local + confirmation au clic). Sommaire du backlog recompté par script (méthode : première ligne `- **État` après chaque `### REV-nnn`, effectifs <mesurés>).
- **L2** : <reprendre, REV par REV, ce que la revue finale a trouvé, les écarts plan/réalité et les jumelles traitées — à remplir à partir des ledgers `.superpowers/sdd/backlogA-*`>
- **L3** : <idem>
- **Revue finale** : <défauts trouvés/corrigés ; nombre de Critical/Important>
- **Non-faits** : REV-269 (checklist proposée, aucune action GitHub/tag exécutée), REV-272(a) (décision DPO), REV-273(a)/REV-275(a)(b) (rejeu stack réelle, lot L6), restriction de `ProxyHeadersMiddleware` (décision de déploiement, L1).
```
Les crochets `<…>` DOIVENT être remplacés par le contenu réel avant commit (aucun `<` ne doit subsister : `grep -n '<reprendre\|<idem\|<défauts\|<mesurés' docs/superpowers/2026-08-27-historique-execution-continu.md` → aucune sortie).

- [ ] **Step 7: Inventaire + bilan de fonctionnalités**

Si le plan a ajouté une route REST, un outil MCP ou une route shell : ajouter sa ligne à `docs/revue/inventaire-fonctionnalites.jsonl` (même schéma que les lignes voisines). Sinon ne rien ajouter (le groupe de limiteur `share-link` n'est pas une surface). Puis, dans tous les cas (porte CI et snapshot) :
```bash
cd core && PYTHONPATH=. uv run python scripts/feature_health_cli.py --repo .. --write
PYTHONPATH=. uv run python scripts/feature_health_cli.py --repo .. --check
```
Sortie attendue : `--write` régénère `docs/revue/bilan-fonctionnalites.{html,md}` et ajoute une ligne à `historique-sante.jsonl` ; `--check` sort avec le code 0 (aucune surface non inventoriée, santé médiane ≥ plancher de `core/scripts/feature_health_thresholds.json`). Si `test_feature_health_*` échoue sur un décompte épinglé périmé (REV-291), recaler le décompte dans le test, pas le code.

- [ ] **Step 8: Gardes finales**

```bash
cd /home/lenen/projets/geostudio
python3 scripts/check_claude_md_size.py CLAUDE.md .claude-md-size-threshold
cd core && uv run python -c "print('ok')" && uv run pytest tests/test_feature_inventory.py -q
cd .. && uvx pre-commit run --all-files
git status --short
```
Sorties attendues : `CLAUDE.md : <N> lignes (plancher : 900)` avec N ≤ 900 (baseline mesurée 829) ; `test_feature_inventory.py` vert ; `pre-commit` : tous les hooks `Passed` ; `git status` ne liste que les fichiers de doc de ce plan (aucun `.superpowers/` : gitignoré).

- [ ] **Step 9: Commit de clôture**

```bash
git add CLAUDE.md docs/superpowers/2026-08-27-historique-execution-continu.md docs/revue/
git commit -m "docs(revue): clôture du plan A — états REV, sommaire, bilan, CLAUDE.md

Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>"
```
Puis, avant tout push : `git fetch && git rev-list --left-right --count origin/dev...dev` (un commit CI-bot a déjà divergé en cours de plan long). Promotion vers `main` = PR `origin/dev` → `origin/main`, sur demande de Tanguy.
