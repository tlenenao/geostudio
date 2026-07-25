# SP-Deploy-d — Étude comparée des modalités grand public : plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Un document autonome qui documente/tranche la matrice de décision des modalités de déploiement grand public (installeur guidé, YunoHost, Coolify/Dokploy/CapRover, CasaOS/Umbrel, boutons cloud, managé/SaaS) et la séquence d'adoption recommandée — **rien de construit** au-delà de l'installeur guidé (SP-Deploy-c), conformément à la spec (§6, D7 : « toutes les autres modalités étudiées/comparées, non construites »).

**Architecture:** Aucun code. Un document de vision daté (`docs/vision/`, même série que les autres documents de référence listés en tête de `CLAUDE.md`), qui reprend et argumente la matrice déjà esquissée dans la spec SP-Deploy (§6), plus une mise à jour de `CLAUDE.md` (feuille de route) et de `README.md` (section déploiement) une fois SP-Deploy-a/b/c exécutés.

**Tech Stack:** aucun — travail éditorial.

## Global Constraints

- **Copier verbatim les valeurs et invariants du spec** `docs/superpowers/specs/2026-07-23-sp-deploy-strategies-design.md` (§6, §9).
- **Ne rien construire** : ce sous-plan ne touche à aucun fichier de code, compose, ou script — seulement de la documentation.
- **Cette tâche s'exécute en dernier**, après SP-Deploy-a/b/c (elle documente l'état une fois construit — sections README/CLAUDE.md pointant vers des fichiers/commandes que ces trois sous-plans ont créés : `docker-compose.prod.yml`, `scripts/install.sh`, `docs/runbooks/2026-07-24-restauration-sauvegardes.md`).
- **Pas de suite de test** — vérification par relecture + `cd shell && npm run build` (confirme qu'aucun Markdown référencé par le code n'est cassé, aucun autre effet possible) et `cd core && uv run pytest` (non-régression pure, aucun fichier `core/` touché).
- **Docs en français**, conformément à `CLAUDE.md`.

---

### Task 1 : document de vision — matrice comparée + séquence d'adoption

**Files:**
- Create: `docs/vision/2026-07-24-etude-modalites-deploiement-grand-public.md`

**Interfaces:** aucune — document terminal, ne produit rien consommé par du code.

- [ ] **Step 1: Écrire le document**

Créer `docs/vision/2026-07-24-etude-modalites-deploiement-grand-public.md` :

```markdown
# Étude comparée des modalités de déploiement grand public

> Issu du brainstorm SP-Deploy du 2026-07-23 (`docs/superpowers/specs/2026-07-23-sp-deploy-strategies-design.md`,
> §6). Seul l'installeur guidé (SP-Deploy-c) est construit ; les modalités
> ci-dessous sont étudiées/comparées pour trancher plus tard (D7).

## Matrice de décision

| Modalité | Public | Dette solo | Alignement projet | Verdict |
|---|---|---|---|---|
| **Installeur guidé** (`scripts/install.sh`) | Tous auto-hébergeurs | Faible | ★★★ | **Construit** (SP-Deploy-c) |
| **YunoHost** | Non-technique, FR/souverain | Moyenne (format de packaging propre à suivre) | ★★★ | Piste **prioritaire** post-déploiement |
| **Coolify / Dokploy / CapRover** | Hobbyiste self-host | Faible (réutilise le compose existant) | ★★ | Piste **facile**, quasi gratuite |
| **CasaOS / Umbrel** | Home-server clé en main | Moyenne (2 app-stores distincts à suivre) | ★★ | Possible, à la demande |
| **Bouton « Deploy to » (Railway/Render/Fly)** | Développeurs | Moyenne (spécifique à chaque plateforme) | ★ (s'éloigne du self-host souverain) | Différé |
| **Offre managée / SaaS** | Non-hébergeurs | **Élevée** (ops continue) | — (modèle d'affaires, pas une question technique) | Hors périmètre solo |

### Critères de notation

- **Public visé** : à qui s'adresse la modalité.
- **Dette de maintenance solo** : coût récurrent pour un mainteneur seul
  (format de packaging à suivre, releases à répercuter, cassures upstream).
- **Alignement souveraineté** : cohérence avec la fibre Apache-2.0 / RGPD /
  self-host du projet (cf. `CLAUDE.md`, décisions figées).
- **Effort de packaging initial** et **portée d'adoption**.

## Séquence d'adoption recommandée

1. **Installeur guidé** (construit, SP-Deploy-c) — socle universel, ne
   dépend d'aucune plateforme tierce.
2. **Template Coolify/Dokploy** — quasi gratuit (réutilise `docker-compose.prod.yml`
   tel quel), premier levier hobbyiste ; à construire si une demande réelle
   émerge (pas dans ce chantier).
3. **YunoHost** — si traction dans l'écosystème FR/souverain (public
   non-technique, fort alignement) ; nécessite un format de packaging
   YunoHost dédié (manifest, scripts d'installation propres à cet
   écosystème) — effort non négligeable, à ne lancer que sur signal clair.
4. **CasaOS/Umbrel, boutons cloud** — à la demande uniquement.
5. **Managé/SaaS** — hors périmètre d'un mainteneur solo (modèle d'affaires,
   ops continue) ; mentionné pour complétude, non retenu.

## Hors périmètre (explicite, cf. spec §9)

Construction effective de YunoHost / Coolify / CasaOS / boutons cloud /
managé — seule la matrice ci-dessus est livrée ; toute construction future
est un chantier à part entière, à spécifier quand le signal (Q2 : premiers
utilisateurs réels, cf. comparatif) le justifiera.
```

- [ ] **Step 2: Commit**

```bash
git add docs/vision/2026-07-24-etude-modalites-deploiement-grand-public.md
git commit -m "docs(vision): étude comparée des modalités de déploiement grand public (SP-Deploy §6)"
```

---

### Task 2 : mise à jour de la feuille de route et du README

**Files:**
- Modify: `docs/vision/2026-07-04-feuille-de-route-geostudio.md`
- Modify: `CLAUDE.md`
- Modify: `README.md`

**Interfaces:** consomme les artefacts livrés par SP-Deploy-a/b/c (`docker-compose.prod.yml`, `scripts/install.sh`, `docs/runbooks/2026-07-24-restauration-sauvegardes.md`) — **à n'exécuter qu'une fois ces trois sous-plans réellement terminés**, sans quoi cette tâche documenterait un état qui n'existe pas encore.

- [ ] **Step 1: Inscrire SP-Deploy dans la feuille de route**

Dans `docs/vision/2026-07-04-feuille-de-route-geostudio.md`, ajouter une entrée `SP-Deploy` au tableau des jalons/phases (même format que l'entrée `SP-15` déjà ajoutée le 2026-07-22 — chercher `| SP-15 |` pour le patron exact de ligne à répliquer), avec le jalon **« M-Deploy dogfood réel »** et la référence à la spec `2026-07-23-sp-deploy-strategies-design.md`.

- [ ] **Step 2: Mettre à jour `CLAUDE.md` — section « Fait »**

Ajouter, à la suite de l'entrée `SP-13` (Portails & Sites) dans la section
« Fait » de `CLAUDE.md`, une entrée :

```markdown
- **SP-Deploy** (a→d) — déploiement dogfood réel : stack prod
  (`docker-compose.prod.yml`, images GHCR, tunnel Tailscale Funnel, hostname
  source unique), durabilité (service `backup` chiffré + restauration
  réellement testée), installeur guidé universel (`scripts/install.sh`),
  étude comparée des modalités grand public.
```

- [ ] **Step 3: Section README — déploiement en production**

Ajouter à `README.md`, après la section « Démarrage rapide (dev) » existante,
une nouvelle section :

```markdown
## Déploiement en production (dogfood)

```bash
git clone https://github.com/tlenenao/geostudio.git && cd geostudio
./scripts/install.sh
```

Détecte/installe Docker si besoin (avec confirmation explicite), propose un
menu de profils (observabilité, ETL à venir), découvre un nom d'hôte public
via Tailscale Funnel (ou en accepte un fourni), crée le premier compte
administrateur, et démarre la stack complète
(`docker-compose.prod.yml`) — sans port ouvert, TLS terminé par le tunnel.

Sauvegardes quotidiennes chiffrées (Postgres + MinIO + realm Keycloak) vers
une cible hors-site S3-compatible, si configurée. Procédure de restauration :
`docs/runbooks/2026-07-24-restauration-sauvegardes.md`.
```

- [ ] **Step 4: Vérifier la non-régression**

```bash
cd shell && npm run build
cd ../core && uv run pytest && uv run lint-imports
```

Expected : tous verts (aucun fichier de code touché par cette tâche).

- [ ] **Step 5: Commit**

```bash
git add docs/vision/2026-07-04-feuille-de-route-geostudio.md CLAUDE.md README.md
git commit -m "docs: SP-Deploy dans la feuille de route, CLAUDE.md et README"
```
