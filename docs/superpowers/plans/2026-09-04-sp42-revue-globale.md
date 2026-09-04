# SP-42 — Revue globale, matrice de fonctionnalités et refonte du README

> **Pour les agents exécutants :** SOUS-SKILL REQUISE — utiliser
> `superpowers:subagent-driven-development` (recommandé) ou
> `superpowers:executing-plans` pour exécuter ce plan tâche par tâche. Les
> étapes utilisent la syntaxe à cases (`- [ ]`).

**Objectif :** produire une photo complète et prouvée du projet — revue de code
de tout le dépôt avec correction des défauts sérieux, matrice de fonctionnalités,
analyse des manques, README réécrit — et les quatre suites opérationnelles
(backlog, spec de refactorisation, feuille de route révisée, `CLAUDE.md`
dégonflé).

**Architecture :** trois vagues d'agents. Vague 1, huit cartographes produisent
chacun un fragment de matrice en JSONL, avec preuve `chemin:ligne` obligatoire.
Vague 2, seize réviseurs attaquent chacun un axe **en partant de la matrice
consolidée**, et rendent leurs trouvailles en JSONL. Vague 3, chaque trouvaille
sérieuse est falsifiée par un agent tiers avant tout correctif, puis les
livrables sont rédigés depuis les deux jeux de JSONL — une seule source pour la
matrice Markdown et pour l'Artifact HTML, donc pas de divergence possible.

**Pile technique :** Python 3.12 / FastAPI / SQLAlchemy / Alembic / pytest côté
cœur ; React 19 / TypeScript / Vite / Vitest / Playwright côté shell ; Docker
Compose, GitHub Actions, `ruff`, `mypy`, `import-linter`, ESLint, Prettier.

## Contraintes globales

- **Spec de référence :** `docs/superpowers/specs/2026-09-04-sp42-revue-globale-design.md`.
  Toute divergence entre ce plan et la spec se tranche en faveur de la spec, en
  le consignant dans le commit.
- **Base de revue :** `dev` à `aef9e65e` ou plus récent. SP-41 est **figé et
  inclus** dans le périmètre ; aucun travail SP-41 nouveau n'est engagé.
- **Preuve obligatoire :** toute ligne de matrice et toute trouvaille porte une
  référence `chemin:ligne` vérifiée dans le code. `CLAUDE.md`, les specs et les
  plans sont des récits d'intention, **jamais** une source de vérité.
- **Aucun Minor corrigé.** Ils vont au backlog. Aucun refactor structurel
  exécuté : SP-42 écrit la spec de SP-43, il ne redécoupe aucun fichier.
- **Aucun fichier de `docs/vision/` existant n'est modifié.**
- **Nommage des fichiers de travail :** tout sous `.superpowers/sdd/sp42-*`
  (répertoire gitignoré, vérifié : `.gitignore:5`, zéro fichier suivi). Jamais
  de nom générique type `task-N-report.md` — une contamination entre sessions
  concurrentes a déjà été observée sur ce dépôt.
- **Commits :** conventional, sur `dev`, sans PR, un sujet par commit, suffixe
  `(SP-42)`. `pre-commit` tourne à chaque commit (commitlint inclus).
- **Documents en français**, identifiants et code en anglais.
- **Régénération OpenAPI/types** dès qu'une route ou un modèle change, avec
  l'incantation complète (`PYTHONPATH=.` + `CORE_SECRETS_MASTER_KEY` de test) —
  classe d'oubli n°1 du dépôt.
- **Écart assumé vis-à-vis de la spec :** ce plan ajoute un onzième livrable non
  listé au §8 de la spec, `docs/revue/2026-09-04-rapport-revue.md` — la trace de
  ce que la revue a établi, distincte du backlog qui, lui, ne porte que ce qui
  reste à faire. Consigné ici plutôt que d'amender la spec.
- **Ne jamais recopier un compte de tests depuis un rapport d'agent.** Les
  comptes se mesurent, et les résultats E2E se lisent dans
  `shell/test-results/.last-run.json`, jamais dans la fin de sortie du reporter
  `list`, qui tronque et induit en erreur.

---

## Structure des fichiers

**Fichiers de travail, non versionnés (`.superpowers/sdd/`) :**

| Fichier | Responsabilité |
|---|---|
| `sp42-baseline.md` | comptes de tests et de couverture mesurés à l'ouverture |
| `sp42-matrice-fragment-<1..8>.jsonl` | un fragment de matrice par cartographe |
| `sp42-matrice.jsonl` | matrice consolidée, source unique des deux rendus |
| `sp42-finding-<axe>.jsonl` | trouvailles d'un réviseur |
| `sp42-findings.jsonl` | trouvailles consolidées et dédupliquées |
| `sp42-falsification-<id>.md` | preuve de reproduction d'une trouvaille |
| `sp42-progress.md` | journal d'avancement du plan |

**Fichiers livrés, versionnés :**

| Fichier | Responsabilité |
|---|---|
| `docs/revue/2026-09-04-matrice-fonctionnalites.md` | la matrice, rendu Markdown |
| `docs/revue/2026-09-04-analyse-gaps.md` | les manques, `GAP-nn` |
| `docs/revue/2026-09-04-backlog.md` | le backlog unique, `REV-nnn` |
| `docs/revue/2026-09-04-rapport-revue.md` | ce que la revue a trouvé et ce qui a été corrigé |
| `docs/superpowers/specs/2026-09-04-sp43-refactorisation-structurelle-design.md` | inventaire de refactorisation |
| `docs/vision/2026-09-04-feuille-de-route-revisee.md` | phasage SP-43+ |
| `README.md` | réécrit, vitrine open-source |
| `CLAUDE.md` | dégonflé, entrée SP-42 |
| `docs/superpowers/2026-08-27-historique-execution-sp0-sp26.md` | reçoit l'historique déplacé |

**Schéma d'une ligne de matrice** (une par ligne dans le JSONL, sans saut de
ligne interne) :

```json
{
  "domaine": "Cartes",
  "fonctionnalite": "Symbologie classée (quantile, intervalle égal, Jenks)",
  "description": "Colorer une couche par classes calculées sur un attribut numérique",
  "etat": "livre",
  "surfaces": { "ui": true, "api": false, "mcp": false, "cli": false },
  "tests": { "unit": true, "integration": false, "e2e": true, "ref": "shell/e2e/map-symbology.spec.ts" },
  "activation": "aucune",
  "preuve": "shell/src/map/MapSymbologyEditor.tsx:214",
  "origine": "SP-25",
  "note": ""
}
```

`etat` ∈ `livre` | `partiel` | `inerte` | `prevu` | `absent`. `activation` vaut
`aucune` ou la liste des prérequis (`CORE_ETL_ENABLED`, `profil observability`,
`sidecar QGIS`, …). `note` explique l'état quand il n'est pas `livre` — pour
`partiel` et `inerte`, elle est **obligatoire** et dit précisément ce qui manque.

**Schéma d'une trouvaille** :

```json
{
  "id": "F-securite-rls-03",
  "axe": "securite-rls",
  "severite": "important",
  "titre": "Le scope RLS n'est pas réappliqué après un rollback de transaction",
  "fichier": "core/app/features/rls.py",
  "ligne": 88,
  "scenario_echec": "Deux requêtes dans la même session après une erreur SQL : la seconde s'exécute sans scope tenant",
  "preuve": "core/app/features/rls.py:88-96, aucun SET LOCAL après le rollback de core/app/db.py:41",
  "correctif_propose": "Réémettre le SET LOCAL dans le gestionnaire de rollback"
}
```

`severite` ∈ `critical` | `important` | `minor`.

---

## Tâche 1 : baseline mesurée et amorçage des artefacts

**Fichiers :**
- Créer : `.superpowers/sdd/sp42-baseline.md`
- Créer : `.superpowers/sdd/sp42-progress.md`

Rien n'est commité par cette tâche : elle établit les chiffres auxquels la
vérification finale (Tâche 18) se comparera. Les comptes de `CLAUDE.md` sont
périmés et ne servent pas de référence.

- [ ] **Étape 1 : figer le commit de base**

```bash
cd /home/lenen/projets/geostudio
mkdir -p .superpowers/sdd docs/revue
git rev-parse --short HEAD
git status --short
```

Attendu : la branche est `dev`, l'arbre ne contient que
`?? deploy/postgis/pg_hba.conf` et `?? test-results/`. Si d'autres modifications
apparaissent, **s'arrêter** et le signaler : une session concurrente travaille
sur l'arbre.

- [ ] **Étape 2 : découvrir le DSN de test réel du cœur**

Ne pas deviner la chaîne de connexion — la lire dans le code et vérifier le
conteneur :

```bash
grep -rn "CORE_TEST_DATABASE_URL" core/tests/conftest.py core/app/db.py | head
docker ps --format '{{.Names}}\t{{.Ports}}' | grep -i postgis
```

Le pilote attendu est `+psycopg`, **pas** `+psycopg2` : ce dernier fait échouer à
tort `test_cdc_consumer_postgis.py`. Sans conteneur `postgis-test` accessible,
168 tests se sautent silencieusement au lieu des 5 sauts `qgis` légitimes — le
noter dans la baseline si c'est le cas.

- [ ] **Étape 3 : mesurer la suite du cœur**

```bash
cd core && CORE_TEST_DATABASE_URL="<DSN découvert à l'étape 2>" uv run pytest -q 2>&1 | tail -20
```

Relever le triplet `passed / skipped / failed`. Deux échecs préexistants
possibles, à ne pas imputer à SP-42 :
`test_features_rls.py::test_scope_preserves_original_sql_error` (intermittent)
et `test_deployability.py::test_every_compose_substitution_is_documented`.

- [ ] **Étape 4 : mesurer la suite du shell et sa couverture**

Nettoyer d'abord les artefacts gitignorés, que la configuration `vitest` de ce
dépôt compte à tort comme source non couverte — piège documenté quatre fois :

```bash
cd ../shell && rm -rf dist dist-export coverage
npx vitest run --coverage 2>&1 | tail -20
node scripts/check-coverage.mjs coverage/coverage-summary.json .coverage-threshold
```

- [ ] **Étape 5 : mesurer la suite E2E**

```bash
cd shell && npm run e2e 2>&1 | tail -5
cat test-results/.last-run.json
```

Le verdict se lit dans `.last-run.json` (`status`, `failedTests`), jamais dans la
fin de sortie du reporter.

- [ ] **Étape 6 : mesurer les portes de qualité**

```bash
cd core && uv run ruff check . && uv run ruff format --check .
uv run mypy --strict app/auth app/secrets app/analytics app/copilot app/admin_tools app/roles
uv run lint-imports
cd ../shell && npm run lint && npm run format:check && npx tsc --noEmit
```

- [ ] **Étape 7 : écrire la baseline**

Consigner dans `.superpowers/sdd/sp42-baseline.md` : commit de base, DSN utilisé,
les trois triplets de tests, le pourcentage de couverture shell, l'état de
chaque porte de qualité, et la liste nominative des échecs préexistants avec
leur raison. Amorcer `.superpowers/sdd/sp42-progress.md` avec la liste des 18
tâches.

---

## Tâche 2 : vague 1 — huit cartographes

**Fichiers :**
- Créer : `.superpowers/sdd/sp42-matrice-fragment-1.jsonl` … `-8.jsonl`

**Interfaces :**
- Consomme : la baseline de la Tâche 1 (pour connaître les suites disponibles).
- Produit : huit fragments au schéma de la section « Structure des fichiers »,
  consommés par la Tâche 3.

- [ ] **Étape 1 : dispatcher les huit cartographes en parallèle**

Un seul message, huit appels d'agent. Chaque brief reprend **mot pour mot** le
modèle ci-dessous, en substituant le numéro et la tranche.

```
Tu es cartographe n°<N> de la revue globale SP-42 du dépôt GeoStudio
(/home/lenen/projets/geostudio, branche dev).

Ta tranche : <TRANCHE>

Ta mission : inventorier toutes les FONCTIONNALITÉS UTILISATEUR portées par
cette tranche, et rendre un fragment de matrice.

Règles non négociables :
1. Une ligne = une fonctionnalité du point de vue d'un utilisateur, PAS un
   module, PAS un endpoint. « Publier un item » est une fonctionnalité ;
   « POST /items/{id}/publish » est sa preuve.
2. Toute ligne porte une preuve chemin:ligne que tu as réellement lue. Tu n'as
   PAS le droit de dériver une ligne de CLAUDE.md, d'une spec ou d'un plan : ce
   sont des récits d'intention, régulièrement faux. Lis le code.
3. Pour chaque fonctionnalité, cherche activement si elle est ATTEIGNABLE :
   - un flag CORE_*_ENABLED est-il réellement câblé dans docker-compose.yml,
     dans l'environment: du bon service ? (vérifier par valeur, pas par
     présence dans .env.example)
   - un écran a-t-il un lien de navigation qui y mène ?
   - un hook, une fonction, une branche a-t-elle un consommateur réel ?
   - une capacité déclarée par GET /me ou GET /instance est-elle consommée ?
   Si le code existe, est testé, est mergé, mais que rien ne l'atteint :
   l'état est "inerte" et la note dit précisément pourquoi. C'est la classe de
   défaut la plus importante de cette mission ; ce dépôt l'a payée au moins
   cinq fois.
4. Pour chaque fonctionnalité, cherche sa jumelle : livrée dans l'éditeur mais
   pas dans le widget, en API mais pas en MCP, en lecture mais pas en écriture.
   Une jumelle manquante donne l'état "partiel".
5. Couverture de test : cherche le fichier de test qui exerce réellement la
   fonctionnalité et nomme-le. Un test qui monte un composant sans exercer le
   comportement ne compte pas.

Sortie : écris /home/lenen/projets/geostudio/.superpowers/sdd/sp42-matrice-fragment-<N>.jsonl
Une ligne JSON par fonctionnalité, sans saut de ligne interne, au schéma exact :

{"domaine":"...","fonctionnalite":"...","description":"...","etat":"livre|partiel|inerte|prevu|absent","surfaces":{"ui":bool,"api":bool,"mcp":bool,"cli":bool},"tests":{"unit":bool,"integration":bool,"e2e":bool,"ref":"chemin ou vide"},"activation":"aucune ou liste","preuve":"chemin:ligne","origine":"SP-xx ou inconnu","note":""}

La note est OBLIGATOIRE et précise pour tout état différent de "livre".

Ne modifie aucun fichier du dépôt. N'écris que ton fragment.
Rends en réponse finale : le nombre de lignes écrites, la répartition par état,
et les trois observations qui t'ont le plus surpris.
```

Tranches à substituer :

| N | Tranche |
|---|---|
| 1 | Cœur — identité : `core/app/{auth,roles,users,tenants,sharing,audit,instance}` |
| 2 | Cœur — contenu : `core/app/{items,collections,features,configs,catalog,public}`, `core/app/schemas_routes.py` |
| 3 | Cœur — données et fédération : `core/app/{analytics,cdc,dcat,stac,harvest,search}` |
| 4 | Cœur — automatisation et annexes : `core/app/{pipelines,ingestion,export,appexport,reports,alerts,notifications,secrets,attachments,mapicons,terrain3d,tileset3d,extensions,admin_tools,copilot,mcp,ratelimit}`, `core/app/jobs.py` |
| 5 | Shell — pages, routes, chrome, `capabilities`, i18n : `shell/src/{pages,shell,i18n}` |
| 6 | Shell — builder : `shell/src/builder` (54 widgets, runtime, actions, CEL, variables), `shell/src/staticExport` |
| 7 | Shell — carte et couche API : `shell/src/map`, `shell/src/api` |
| 8 | Infra : `docker-compose.yml`, `docker-compose.prod.yml`, `.env.example`, `.github/workflows`, `scripts/`, `core/tests/test_deployability.py`, `deploy/` |

- [ ] **Étape 2 : vérifier que les huit fragments existent et sont bien formés**

```bash
cd /home/lenen/projets/geostudio
for n in 1 2 3 4 5 6 7 8; do
  f=".superpowers/sdd/sp42-matrice-fragment-$n.jsonl"
  printf '%s : ' "$f"
  if [ -f "$f" ]; then
    python3 -c "
import json,sys
n=0
for i,l in enumerate(open('$f'),1):
    l=l.strip()
    if not l: continue
    try: json.loads(l)
    except Exception as e: print('LIGNE',i,'INVALIDE',e); sys.exit(1)
    n+=1
print(n,'lignes valides')
"
  else echo "MANQUANT"; fi
done
```

Attendu : huit fichiers, zéro ligne invalide. Relancer tout cartographe dont le
fragment manque ou est mal formé.

- [ ] **Étape 3 : consigner l'avancement**

Ajouter à `.superpowers/sdd/sp42-progress.md` le nombre de lignes par fragment
et les observations remontées.

---

## Tâche 3 : consolidation de la matrice et audit de complétude

**Fichiers :**
- Créer : `.superpowers/sdd/sp42-matrice.jsonl`

**Interfaces :**
- Consomme : les huit fragments de la Tâche 2.
- Produit : `sp42-matrice.jsonl`, source unique de la Tâche 10 (Markdown) et de
  la Tâche 11 (Artifact), et carte de départ des Tâches 4 et 5.

- [ ] **Étape 1 : fusionner et dédupliquer**

```bash
cd /home/lenen/projets/geostudio
python3 - <<'PY'
import json, glob, collections
lignes = []
for f in sorted(glob.glob(".superpowers/sdd/sp42-matrice-fragment-*.jsonl")):
    for l in open(f):
        l = l.strip()
        if l:
            lignes.append(json.loads(l))
# doublon = même domaine + même libellé de fonctionnalité
vus = {}
for e in lignes:
    cle = (e["domaine"].strip().lower(), e["fonctionnalite"].strip().lower())
    vus.setdefault(cle, []).append(e)
doublons = {k: v for k, v in vus.items() if len(v) > 1}
print("lignes:", len(lignes), "| uniques:", len(vus), "| doublons:", len(doublons))
for k, v in doublons.items():
    print("  DOUBLON", k, "->", [e["preuve"] for e in v])
print("par état:", collections.Counter(e["etat"] for e in lignes))
print("sans preuve:", [e["fonctionnalite"] for e in lignes if not e.get("preuve")])
print("note manquante:", [e["fonctionnalite"] for e in lignes
                          if e["etat"] in ("partiel","inerte") and not e.get("note")])
PY
```

- [ ] **Étape 2 : arbitrer chaque doublon à la main**

Un doublon entre deux tranches est le plus souvent une vraie information : la
même fonctionnalité vue côté cœur et côté shell. Fusionner en une ligne unique
qui porte **les deux preuves** et l'union des surfaces. Un doublon dont les deux
copies divergent sur l'état est un signal fort : vérifier soi-même dans le code
lequel est juste, ne pas trancher au hasard.

- [ ] **Étape 3 : écrire la matrice consolidée**

Écrire `.superpowers/sdd/sp42-matrice.jsonl`, une ligne par fonctionnalité
unique, triée par domaine puis par libellé. Corriger sur place toute ligne sans
preuve ou sans note obligatoire, en relisant le code — ne pas la supprimer.

- [ ] **Étape 4 : audit de complétude**

Vérifier que la matrice couvre bien la surface réelle, en la confrontant à trois
décomptes mécaniques :

```bash
cd /home/lenen/projets/geostudio
echo "endpoints: $(grep -rEn '@router\.(get|post|patch|put|delete)' core/app --include='*.py' | wc -l)"
echo "pages shell: $(ls shell/src/pages/*.tsx | grep -v test | wc -l)"
echo "widgets: $(ls shell/src/builder/widgets/*.ts* | grep -v test | wc -l)"
# la forme de déclaration des outils MCP se lit dans le fichier, elle ne se devine pas :
grep -nE '@|^def |^async def ' core/app/mcp/tools.py | head -20   # puis compter avec le motif réel
```

Toute page, tout widget, tout outil MCP doit être rattachable à au moins une
ligne de matrice. Les orphelins sont soit une fonctionnalité oubliée par un
cartographe — à ajouter en la vérifiant soi-même — soit du code inerte, ce qui
est une trouvaille en soi : la consigner comme ligne d'état `inerte`.

- [ ] **Étape 5 : consigner**

Reporter dans `.superpowers/sdd/sp42-progress.md` : nombre de lignes finales,
répartition par état, liste des lignes `inerte` (elles alimenteront directement
la Tâche 12), et les orphelins trouvés à l'étape 4.

---

## Tâche 4 : vague 2, lot A — sécurité, cœur, migrations (8 réviseurs)

**Fichiers :**
- Créer : `.superpowers/sdd/sp42-finding-<axe>.jsonl` pour huit axes

**Interfaces :**
- Consomme : `.superpowers/sdd/sp42-matrice.jsonl` (Tâche 3).
- Produit : huit fichiers de trouvailles, consommés par la Tâche 6.

- [ ] **Étape 1 : dispatcher les huit réviseurs en parallèle**

Un seul message, huit appels d'agent, brief commun ci-dessous.

```
Tu es réviseur de l'axe <AXE> dans la revue globale SP-42 du dépôt GeoStudio
(/home/lenen/projets/geostudio, branche dev). Le dépôt est en français pour les
docs, en anglais pour le code.

Ton périmètre : <PERIMETRE>
Ce que tu cherches en priorité : <FOCUS>

Avant de commencer, lis .superpowers/sdd/sp42-matrice.jsonl et filtre les lignes
de ton périmètre : elles te disent quelles fonctionnalités existent, lesquelles
sont marquées inerte ou partiel, et lesquelles n'ont pas de filet E2E. Pars de
là plutôt que de redécouvrir le terrain.

Règles :
1. Tu cherches des DÉFAUTS RÉELS, pas des préférences de style. Pour chaque
   trouvaille, tu dois pouvoir écrire un scénario d'échec concret : quelles
   entrées, quel état, quel résultat faux ou quel plantage.
2. Toute trouvaille porte une preuve chemin:ligne que tu as lue.
3. Sévérité : "critical" = faille de sécurité, perte de données, ou
   fonctionnalité fausse pour tout utilisateur ; "important" = défaut réel avec
   conséquence utilisateur, ou incohérence entre deux surfaces jumelles ;
   "minor" = tout le reste (style, duplication, commentaire faux sans
   conséquence, dette).
4. Un commentaire ou une docstring qui attribue une garde de sécurité au mauvais
   composant après un déplacement est un défaut réel, pas du style : ce dépôt
   l'a payé Important deux fois.
5. Ne corrige RIEN. Ne modifie aucun fichier du dépôt. Tu écris seulement ton
   fichier de trouvailles.

Sortie : /home/lenen/projets/geostudio/.superpowers/sdd/sp42-finding-<AXE>.jsonl
Une ligne JSON par trouvaille, schéma exact :

{"id":"F-<AXE>-01","axe":"<AXE>","severite":"critical|important|minor","titre":"...","fichier":"...","ligne":123,"scenario_echec":"...","preuve":"chemin:ligne","correctif_propose":"..."}

Rends en réponse finale : le compte par sévérité et un résumé d'une ligne par
trouvaille critical ou important.
```

Axes du lot A :

| Axe | Périmètre | Focus |
|---|---|---|
| `securite-autorisation` | `core/app/{auth,roles,sharing}`, tous les appels `can()`, `decide()`, `require_privilege`, `has_privilege` | une route sans garde ; une garde qui ne correspond pas à la visibilité servie ; un privilège contournable par un chemin de service (connexion, bootstrap) sans passer par la garde HTTP ; anti-lockout |
| `securite-tenant-rls` | `core/app/{tenants,features,collections}`, `rls_scope`, toute requête portant `tenant_id` | une requête qui résout le tenant depuis `user.tenant_id` au lieu de l'objet ; un scope RLS non réappliqué ; une fuite inter-tenant sur une route publique, STAC, DCAT ou de tuiles |
| `securite-surfaces` | `core/app/{secrets,attachments,mapicons,harvest,admin_tools,ratelimit}`, gardes d'egress, uploads, cookie admin, CSP dans `docker-compose.prod.yml` | SSRF et contournements de la garde d'egress ; validation de noms de fichiers et de types ; injection d'en-tête ; durée de vie et portée du cookie ; ce que le rate limiter ne protège pas |
| `coeur-contenu` | `core/app/{items,collections,features,configs,catalog,public}` | round-trip incomplet d'un champ de config ; validation absente ou asymétrique entre création et mise à jour ; suppression sans cascade ; pagination et tri |
| `coeur-analytique` | `core/app/{analytics,cdc}` et le module DuckDB | agrégats faux sur cas limite ; grains temporels ; bac à sable SQL contournable ; cohérence CDC → GeoParquet ; plafonds et délais |
| `coeur-automatisation` | `core/app/{pipelines,ingestion,export,appexport,reports,alerts,notifications}`, `core/app/jobs.py` | variable référencée avant affectation dans une branche d'échec ; transaction partagée entre l'écriture d'un statut de job et une écriture annexe ; sondage sans annulation ; idempotence d'une tâche rejouée |
| `coeur-federation` | `core/app/{harvest,stac,dcat,search,mcp}` | un document dont les liens mènent à un 404 pour le rôle qui vient de le lire ; connecteur qui fait confiance à une réponse distante ; outil MCP dont la permission servie contredit l'action qui vient de réussir |
| `migrations` | `core/alembic/versions` (33 migrations), `core/app/**/models.py` | `downgrade()` qui ne passe que sur base vide ; colonne ajoutée sans valeur par défaut sur table non vide ; divergence entre le modèle SQLAlchemy et la migration ; index manquant sur une clé étrangère chaude |

Pour l'axe `migrations`, le brief ajoute :

```
Éprouve réellement les migrations sur une base Postgres NON VIDE, dans les deux
sens. Ne lance jamais alembic contre le conteneur postgis-test partagé : son
schéma est construit par Base.metadata.create_all() et ne porte pas de table
alembic_version. Crée une base jetable dans le même conteneur, insère des
lignes réelles (tenant, rôle, utilisateur, item, collection), puis fais
upgrade head → downgrade -1 → upgrade head, et détruis-la. Ce dépôt a déjà vu
des downgrade() qui ne passaient que parce que la CI teste sur base vide.
```

- [ ] **Étape 2 : vérifier les huit sorties**

```bash
cd /home/lenen/projets/geostudio
for a in securite-autorisation securite-tenant-rls securite-surfaces coeur-contenu coeur-analytique coeur-automatisation coeur-federation migrations; do
  f=".superpowers/sdd/sp42-finding-$a.jsonl"
  printf '%s : ' "$a"
  [ -f "$f" ] && python3 -c "
import json
n={'critical':0,'important':0,'minor':0}
for l in open('$f'):
    l=l.strip()
    if l: n[json.loads(l)['severite']]+=1
print(n)
" || echo MANQUANT
done
git status --short
```

Attendu : huit fichiers présents, et `git status` inchangé — aucun réviseur n'a
le droit de modifier le dépôt. Si un fichier suivi a bougé, l'annuler
(`git checkout -- <fichier>`) et le signaler.

---

## Tâche 5 : vague 2, lot B — shell et transverse (8 réviseurs)

**Fichiers :**
- Créer : `.superpowers/sdd/sp42-finding-<axe>.jsonl` pour huit axes de plus

**Interfaces :**
- Consomme : `.superpowers/sdd/sp42-matrice.jsonl`.
- Produit : huit fichiers de trouvailles de plus, consommés par la Tâche 6.

- [ ] **Étape 1 : dispatcher les huit réviseurs en parallèle**

Même brief que la Tâche 4, étape 1, avec les axes suivants.

| Axe | Périmètre | Focus |
|---|---|---|
| `shell-builder` | `shell/src/builder` (widgets, runtime, actions, CEL, variables), `shell/src/staticExport` | un widget dont une propriété ne survit pas à un rechargement ; une action dont l'annulation ne restaure pas l'état ; une expression CEL dont l'erreur casse le rendu ; divergence entre mode édition, aperçu et exécution |
| `shell-carte` | `shell/src/map`, `shell/src/builder/widgets/mapSymbology.ts` | un champ de symbologie ou de popup absent de `toFrontLayer()` dans `shell/src/api/itemClient.ts`, donc perdu au rechargement — piège n°5, déjà payé trois fois ; divergence entre l'éditeur de carte et le widget carte ; couche `vector` contre couche `feature` |
| `shell-pages` | `shell/src/pages`, `shell/src/shell` | une page qui propose une action produisant un 403 ; une requête gardée par un privilège différent de celui de sa route, d'où un écran blanc ; un état d'erreur non traité ; un écran sans lien de navigation |
| `shell-api` | `shell/src/api` (`itemClient.ts` 1741 l., `hooks.ts`, `types.ts`, `generated/`) | dérive entre les types générés et l'OpenAPI réel ; mutation sans invalidation de cache ; hook mort ; conversion qui perd un champ dans un sens ou dans l'autre |
| `tests` | `core/tests`, `shell/src/**/*.test.tsx`, `shell/e2e` | **filets vacants** : un test qui ne peut pas échouer pour la raison qu'il annonce, une assertion sur un conteneur jamais rendu, un `toPass` qui s'arrête au premier sondage, un stub global non désinstallé créant une dépendance d'ordre. Prouve chaque filet vacant par falsification réelle avant de le rapporter |
| `performances` | cœur et shell | N+1 (`GET /users` en est un connu) ; requête par ligne au lieu d'une par page ; absence de plafond ou de délai sur une route coûteuse ; sondage sans annulation ; taille de bundle |
| `i18n-a11y` | `shell/src/i18n`, `shell/src/ui/kit`, toutes les pages | chaîne française hors `t()` ; clé absente du catalogue ; `aria-label` interpolant un nœud arbitraire ; déclencheur de panneau sans `aria-expanded`/`aria-controls` ; contraste d'un fond tokenisé sans couleur de texte associée ; navigation au clavier |
| `infra-ci` | `docker-compose.yml`, `docker-compose.prod.yml`, `.env.example`, `.github/workflows`, `scripts/`, `core/tests/test_deployability.py` | une variable substituée mais absente de l'`environment:` du bon service — vérifier **par valeur** avec `docker compose config` ; un port publié en production qui contourne une garde ; une image non épinglée ; une porte de qualité absente de la CI ; un service sans healthcheck |

Pour l'axe `tests`, le brief ajoute :

```
Un filet vacant ne se rapporte pas sur intuition : tu dois le PROUVER. Injecte
délibérément le défaut que le test prétend attraper, lance le test, constate
qu'il passe quand même, puis restaure exactement l'état d'origine
(git checkout -- <fichier>) et vérifie que git status est propre. Consigne la
commande et la sortie dans le champ preuve. « Le test m'a l'air faible » n'est
pas une trouvaille.
```

Pour l'axe `infra-ci`, le brief ajoute :

```
Vérifie le câblage PAR VALEUR, pas par présence :
  docker compose config | grep -A40 'service-name:'
Une variable présente dans .env.example et substituée dans docker-compose.yml
peut n'être dans l'environment: d'aucun service : ce dépôt a déjà rendu une
capacité entière inactivable de cette façon. Ne démarre pas la stack, lis la
configuration résolue.
```

- [ ] **Étape 2 : vérifier les huit sorties**

Même vérification qu'à la Tâche 4, étape 2, avec la liste d'axes du lot B.
`git status --short` doit être inchangé, à l'exception attendue de rien du tout :
l'axe `tests` restaure ce qu'il a modifié.

---

## Tâche 6 : consolidation et hiérarchisation des trouvailles

**Fichiers :**
- Créer : `.superpowers/sdd/sp42-findings.jsonl`

**Interfaces :**
- Consomme : les seize fichiers de trouvailles des Tâches 4 et 5.
- Produit : `sp42-findings.jsonl` dédupliqué, consommé par les Tâches 7, 8, 9 et 14.

- [ ] **Étape 1 : fusionner et détecter les recoupements**

```bash
cd /home/lenen/projets/geostudio
python3 - <<'PY'
import json, glob, collections
t = []
for f in sorted(glob.glob(".superpowers/sdd/sp42-finding-*.jsonl")):
    for l in open(f):
        l = l.strip()
        if l:
            t.append(json.loads(l))
print("total:", len(t), collections.Counter(e["severite"] for e in t))
par_fichier = collections.defaultdict(list)
for e in t:
    par_fichier[e["fichier"]].append(e)
for f, es in sorted(par_fichier.items()):
    if len(es) > 1:
        print("MÊME FICHIER", f)
        for e in es:
            print("   ", e["id"], e["severite"], e["ligne"], e["titre"][:80])
PY
```

- [ ] **Étape 2 : arbitrer les recoupements**

Deux trouvailles sur le même fichier aux mêmes lignes sont un doublon : garder
la plus précise, citer l'autre identifiant en note. Deux trouvailles sur le même
fichier à des lignes différentes ne sont pas un doublon. Une trouvaille dont le
scénario d'échec ne dit ni entrée ni résultat faux est déclassée en `minor` — un
défaut sans conséquence démontrable n'est pas sérieux.

- [ ] **Étape 3 : écrire les trouvailles consolidées**

Écrire `.superpowers/sdd/sp42-findings.jsonl`, triées `critical`, puis
`important`, puis `minor`. Ajouter à chaque entrée un champ
`"statut":"a_falsifier"` pour les deux premières sévérités et
`"statut":"backlog"` pour les `minor`.

- [ ] **Étape 4 : consigner et rendre compte**

Reporter dans `.superpowers/sdd/sp42-progress.md` le compte par sévérité et la
liste des `critical` et `important`. **Présenter cette liste à Tanguy avant de
lancer la Tâche 7** : c'est le moment où le volume de correction devient
visible, et où un arbitrage de périmètre peut être nécessaire.

---

## Tâche 7 : falsification des trouvailles sérieuses

**Fichiers :**
- Créer : `.superpowers/sdd/sp42-falsification-<id>.md`, un par trouvaille
- Modifier : `.superpowers/sdd/sp42-findings.jsonl` (champ `statut`)

**Interfaces :**
- Consomme : `sp42-findings.jsonl`, entrées `critical` et `important`.
- Produit : le même fichier, chaque entrée passée à `confirme` ou `declasse`.

Aucune correction n'est écrite avant cette tâche. Ce dépôt a déjà accepté des
correctifs sur des trouvailles qui ne se reproduisaient pas, et des filets de
test « réparés » qui ne vérifiaient rien.

- [ ] **Étape 1 : dispatcher un falsificateur par trouvaille, par lots de huit**

Chaque falsificateur doit être **un agent différent de celui qui a trouvé** la
trouvaille. Brief :

```
Tu vérifies UNE trouvaille de la revue SP-42 du dépôt GeoStudio
(/home/lenen/projets/geostudio, branche dev).

Trouvaille : <JSON de l'entrée>

Ta mission : établir si ce défaut est RÉEL et REPRODUCTIBLE. Tu n'écris pas le
correctif.

Méthode :
1. Lis le code cité et son contexte.
2. Écris un test qui échoue à cause de ce défaut — ou, si le défaut est de
   configuration ou d'infrastructure, une commande qui en démontre l'effet.
3. Lance-le. Il DOIT échouer, et échouer pour la raison annoncée par la
   trouvaille, pas pour une autre. Copie la sortie.
4. Si tu n'arrives pas à le faire échouer : la trouvaille est déclassée. C'est
   un résultat parfaitement acceptable et attendu sur une partie d'entre elles.
   Dis pourquoi elle ne se reproduit pas.
5. Restaure l'arbre : git checkout -- <fichiers touchés>, puis vérifie que
   git status est propre. Ton test de démonstration reste dans ton rapport,
   pas dans le dépôt.

Sortie : écris /home/lenen/projets/geostudio/.superpowers/sdd/sp42-falsification-<ID>.md
contenant : le verdict (CONFIRMÉ ou DÉCLASSÉ), le test ou la commande utilisée,
la sortie réelle obtenue, et — si confirmé — le correctif minimal que tu
recommandes, avec le fichier de test qui devra le prouver.

Rends en réponse finale : CONFIRMÉ ou DÉCLASSÉ, en une ligne, avec la raison.
```

- [ ] **Étape 2 : reporter les verdicts**

Mettre à jour `statut` dans `.superpowers/sdd/sp42-findings.jsonl` :
`confirme` ou `declasse`. Une trouvaille déclassée n'est pas jetée : elle part au
backlog en observation, avec la raison du déclassement.

- [ ] **Étape 3 : consigner**

```bash
cd /home/lenen/projets/geostudio
python3 -c "
import json, collections
t=[json.loads(l) for l in open('.superpowers/sdd/sp42-findings.jsonl') if l.strip()]
print(collections.Counter((e['severite'],e.get('statut')) for e in t))
"
```

---

## Tâche 8 : correctifs du cœur

**Fichiers :**
- Modifier : les fichiers `core/app/**` cités par les trouvailles confirmées
- Test : les fichiers `core/tests/**` correspondants

**Interfaces :**
- Consomme : `sp42-findings.jsonl`, entrées `statut=confirme` dont le fichier est
  sous `core/`.
- Produit : des commits `fix(core): … (SP-42)`, un par trouvaille ou par groupe
  de trouvailles partageant une racine unique.

- [ ] **Étape 1 : ordonner les correctifs**

Traiter les `critical` avant les `important`. Grouper les trouvailles qui
partagent une racine commune : un même défaut sur deux surfaces jumelles se
corrige en un commit, pas deux.

- [ ] **Étape 2 : pour chaque correctif, écrire d'abord le test qui échoue**

Le test vient du rapport de falsification correspondant — il existe déjà et sa
sortie d'échec est connue. Le porter dans le fichier de test réel :

```bash
cd core && CORE_TEST_DATABASE_URL="<DSN>" uv run pytest <chemin>::<test> -v
```

Attendu : ÉCHEC, avec le message annoncé par le rapport de falsification. Si le
test passe du premier coup, le correctif n'a pas lieu d'être : revenir à la
trouvaille.

- [ ] **Étape 3 : écrire le correctif minimal**

Minimal veut dire : ce qui fait passer le test, rien de plus. Aucune
amélioration opportuniste, aucun renommage, aucun Minor corrigé au passage — la
contrainte globale l'interdit.

- [ ] **Étape 4 : vérifier**

```bash
cd core && CORE_TEST_DATABASE_URL="<DSN>" uv run pytest <chemin> -v
uv run ruff check . && uv run ruff format --check .
uv run mypy --strict app/auth app/secrets app/analytics app/copilot app/admin_tools app/roles
uv run lint-imports
```

- [ ] **Étape 5 : régénérer OpenAPI et les types si une route ou un modèle a bougé**

```bash
cd core && PYTHONPATH=. \
  CORE_SECRETS_MASTER_KEY="AAECAwQFBgcICQoLDA0ODxAREhMUFRYXGBkaGxwdHh8=" \
  uv run python scripts/export_openapi.py openapi.json
cd ../shell && npm run gen:api-types
cd .. && git diff --stat core/openapi.json shell/src/api/generated/core-schema.d.ts
```

Un diff vide est un résultat légitime — et attendu — quand le correctif ne
touche ni une route ni un modèle. Un diff non vide se commite avec le correctif.

- [ ] **Étape 6 : commiter**

```bash
git add <fichiers> && git commit -m "fix(core): <ce que le correctif répare> (SP-42)"
```

- [ ] **Étape 7 : relancer la suite complète du cœur après le dernier correctif**

```bash
cd core && CORE_TEST_DATABASE_URL="<DSN>" uv run pytest -q 2>&1 | tail -20
```

Comparer au triplet de la baseline (Tâche 1). Toute régression se corrige avant
de passer à la Tâche 9.

---

## Tâche 9 : correctifs du shell

**Fichiers :**
- Modifier : les fichiers `shell/src/**` cités par les trouvailles confirmées
- Test : les `*.test.tsx` correspondants, et `shell/e2e/*.spec.ts` si le défaut
  n'est visible qu'en navigateur

**Interfaces :**
- Consomme : `sp42-findings.jsonl`, entrées `statut=confirme` sous `shell/`.
- Produit : des commits `fix(shell): … (SP-42)`.

- [ ] **Étape 1 : ordonner et grouper**

Même règle qu'à la Tâche 8, étape 1.

- [ ] **Étape 2 : porter le test qui échoue**

```bash
cd shell && npx vitest run src/<chemin>.test.tsx -t "<nom du test>"
```

Attendu : ÉCHEC. Pour un défaut de mise en page ou d'atteignabilité réelle,
jsdom ne suffit pas — il ne calcule aucune géométrie : passer par un spec
Playwright. Ce dépôt a déjà laissé passer du contenu inatteignable que les deux
filets de test déclaraient vert.

- [ ] **Étape 3 : écrire le correctif minimal**

- [ ] **Étape 4 : vérifier le fichier, puis les voisins**

```bash
cd shell && npx vitest run src/<chemin>.test.tsx
npx tsc --noEmit && npm run lint && npm run format:check
```

- [ ] **Étape 5 : commiter**

```bash
git add <fichiers> && git commit -m "fix(shell): <ce que le correctif répare> (SP-42)"
```

- [ ] **Étape 6 : relancer les suites complètes du shell après le dernier correctif**

```bash
cd shell && rm -rf dist dist-export coverage
npx vitest run --coverage 2>&1 | tail -10
node scripts/check-coverage.mjs coverage/coverage-summary.json .coverage-threshold
npm run e2e 2>&1 | tail -5 && cat test-results/.last-run.json
```

La suite E2E complète est obligatoire ici, même si aucun spec n'a été touché :
les régressions croisées entre correctifs ne se voient qu'à ce moment — ce dépôt
l'a constaté à cinq reprises, dont une fois à 121 échecs sur 135.

---

## Tâche 10 : la matrice, rendu Markdown

**Fichiers :**
- Créer : `docs/revue/2026-09-04-matrice-fonctionnalites.md`

**Interfaces :**
- Consomme : `.superpowers/sdd/sp42-matrice.jsonl`.
- Produit : le document de référence versionné, et la même source alimente la
  Tâche 11.

- [ ] **Étape 1 : générer le corps du document depuis le JSONL**

```bash
cd /home/lenen/projets/geostudio
python3 - <<'PY' > /tmp/sp42-matrice-corps.md
import json, collections
e = [json.loads(l) for l in open(".superpowers/sdd/sp42-matrice.jsonl") if l.strip()]
LIB = {"livre":"livré","partiel":"partiel","inerte":"**inerte**","prevu":"prévu","absent":"absent"}
def surf(s):
    return " ".join(n for n, k in (("UI","ui"),("API","api"),("MCP","mcp"),("CLI","cli")) if s.get(k)) or "—"
def tst(t):
    v = " ".join(n for n, k in (("U","unit"),("I","integration"),("E","e2e")) if t.get(k)) or "—"
    return f"{v}<br>`{t['ref']}`" if t.get("ref") else v
for d in sorted({x["domaine"] for x in e}):
    print(f"\n## {d}\n")
    print("| Fonctionnalité | État | Surfaces | Tests | Activation | Preuve | Origine |")
    print("|---|---|---|---|---|---|---|")
    for x in sorted((x for x in e if x["domaine"] == d), key=lambda x: x["fonctionnalite"]):
        note = f"<br>*{x['note']}*" if x.get("note") else ""
        print(f"| {x['fonctionnalite']}{note} | {LIB[x['etat']]} | {surf(x['surfaces'])} "
              f"| {tst(x['tests'])} | {x['activation']} | `{x['preuve']}` | {x['origine']} |")
print("\n## Décompte\n")
c = collections.Counter(x["etat"] for x in e)
print("| État | Nombre |\n|---|---|")
for k in ("livre","partiel","inerte","prevu","absent"):
    print(f"| {LIB[k]} | {c.get(k,0)} |")
print(f"| **total** | **{len(e)}** |")
PY
head -30 /tmp/sp42-matrice-corps.md
```

- [ ] **Étape 2 : rédiger l'en-tête et assembler**

L'en-tête, écrit à la main, dit : la date, le commit de base, la méthode (huit
cartographes, preuve `chemin:ligne` obligatoire, rien dérivé de `CLAUDE.md`), la
définition des cinq états — en insistant sur `inerte` — et la limite de
l'exercice : la matrice reflète un instant du dépôt, elle se périme.

Puis :

```bash
cat /tmp/sp42-matrice-corps.md >> docs/revue/2026-09-04-matrice-fonctionnalites.md
```

- [ ] **Étape 3 : vérifier le rendu**

Contrôler qu'aucune cellule ne contient de barre verticale non échappée, qui
casserait le tableau, et que le décompte final correspond au nombre de lignes du
JSONL.

- [ ] **Étape 4 : commiter**

```bash
git add docs/revue/2026-09-04-matrice-fonctionnalites.md
git commit -m "docs(revue): matrice des fonctionnalités livrées, partielles et inertes (SP-42)"
```

---

## Tâche 11 : la matrice, Artifact HTML

**Fichiers :**
- Créer : `/tmp/claude-1000/-home-lenen-projets-geostudio/56c578ef-7775-4eb4-8748-08e19c48cc81/scratchpad/sp42-matrice.html`

**Interfaces :**
- Consomme : `.superpowers/sdd/sp42-matrice.jsonl` — la même source que la
  Tâche 10, donc aucune divergence possible entre les deux rendus.

- [ ] **Étape 1 : charger la skill de design d'artifact**

Obligatoire avant d'écrire le fichier : `artifact-design`.

- [ ] **Étape 2 : écrire la page**

Une page autonome, données JSON embarquées en dur dans le fichier (aucune
ressource externe n'est chargeable). Elle offre : recherche plein texte, filtres
par domaine, par état et par surface, tri par colonne, un bandeau de décompte,
et un code couleur qui met `inerte` et `partiel` en évidence. Palette en deux
ambiances via les jetons `:root` et `prefers-color-scheme`, tableau dans un
conteneur `overflow-x: auto`.

- [ ] **Étape 3 : publier**

Titre : « Matrice GeoStudio ». Description : une phrase. Favicon : deux émoji.

- [ ] **Étape 4 : consigner l'URL**

Ajouter l'URL publiée en tête de
`docs/revue/2026-09-04-matrice-fonctionnalites.md`, puis :

```bash
git add docs/revue/2026-09-04-matrice-fonctionnalites.md
git commit -m "docs(revue): lie la matrice à sa version consultable (SP-42)"
```

---

## Tâche 12 : analyse des manques

**Fichiers :**
- Créer : `docs/revue/2026-09-04-analyse-gaps.md`

**Interfaces :**
- Consomme : `sp42-matrice.jsonl` (lignes `inerte`, `partiel`, `prevu`),
  `docs/vision/*`, et une recherche web pour le benchmark.
- Produit : des entrées `GAP-nn`, consommées par les Tâches 14 et 16.

- [ ] **Étape 1 : référentiel 1 — feuille de route interne**

Confronter la matrice à `docs/vision/2026-07-04-feuille-de-route-geostudio.md`
(SP-1→SP-20, les 40 arbitrages du §8, les jalons M1→M16) et à
`docs/vision/2026-08-20-revue-projet-et-plan-daction.md` (vagues 0-6). Lister ce
qui est promis et non livré, ou livré partiellement. Les éléments déjà connus —
les cinq tests `@pytest.mark.qgis` jamais exécutés qui bloquent M14, la garde
d'egress absente sur l'appel LLM sortant, les cinq privilèges qui n'imposent rien
— y figurent avec leur état vérifié, pas leur état supposé.

- [ ] **Étape 2 : référentiel 2 — benchmark concurrentiel**

Dispatcher un agent de recherche :

```
Établis ce que proposent GeoNode, Felt, ArcGIS Online/Enterprise, Superset,
Metabase, FME et CKAN sur les axes suivants, en 2026 : catalogue et métadonnées,
édition de données, cartographie et symbologie, tableaux de bord et analytique,
ETL, collaboration et partage, administration, extensibilité, API et
automatisation.

Pour chaque capacité que ces produits ont, rends une ligne : le produit, la
capacité, ce qu'elle apporte à l'utilisateur, et une source consultable.

Ne juge pas GeoStudio, tu ne le connais pas. Tu établis seulement l'état de
l'art. Distingue clairement ce que tu as lu d'une documentation officielle de ce
que tu déduis.
```

Croiser ensuite ce retour avec la matrice pour produire les `GAP-nn` du
référentiel 2. **Marquer ces gaps comme non vérifiables dans le code** : ils
reposent sur de la documentation externe.

- [ ] **Étape 3 : référentiel 3 — cohérence interne**

Extraire mécaniquement les asymétries de la matrice :

```bash
cd /home/lenen/projets/geostudio
python3 - <<'PY'
import json, collections
e = [json.loads(l) for l in open(".superpowers/sdd/sp42-matrice.jsonl") if l.strip()]
print("== INERTES ==")
for x in e:
    if x["etat"] == "inerte":
        print(f"  [{x['domaine']}] {x['fonctionnalite']} — {x['note']} ({x['preuve']})")
print("\n== PARTIELS ==")
for x in e:
    if x["etat"] == "partiel":
        print(f"  [{x['domaine']}] {x['fonctionnalite']} — {x['note']}")
print("\n== API SANS MCP ==")
for x in e:
    if x["surfaces"]["api"] and not x["surfaces"]["mcp"] and x["etat"] == "livre":
        print(f"  {x['fonctionnalite']}")
print("\n== SANS AUCUN TEST ==")
for x in e:
    t = x["tests"]
    if not (t["unit"] or t["integration"] or t["e2e"]):
        print(f"  [{x['domaine']}] {x['fonctionnalite']} ({x['preuve']})")
PY
```

Compléter à la main par les asymétries que le décompte ne voit pas : un type
d'item sans historique de versions, un domaine sans écran d'administration, une
capacité déclarée sans écran de réglage.

- [ ] **Étape 4 : référentiel 4 — exigences de production**

Couvrir : restauration de sauvegarde jamais rejouée de bout en bout ; CSP jamais
basculée en enforcing et ses quatre bloqueurs documentés ; absence de quotas par
tenant ; purge des données et droit à l'effacement ; rétention et exportabilité
de l'`audit_log` ; procédure de rotation des secrets ; supervision des jobs en
échec ; la clé `age` de test présente dans l'historique public.

- [ ] **Étape 5 : rédiger et commiter**

Un tableau par référentiel : `GAP-nn` · manque · impact (bloquant, sérieux,
confort) · coût estimé (jours-homme grossiers) · référentiel · preuve ou source.
Une section finale classe les gaps par impact décroissant, tous référentiels
confondus.

```bash
git add docs/revue/2026-09-04-analyse-gaps.md
git commit -m "docs(revue): analyse des manques sur quatre référentiels (SP-42)"
```

---

## Tâche 13 : réécriture du README

**Fichiers :**
- Modifier : `README.md` (222 lignes, à réécrire, pas à rapiécer)

**Interfaces :**
- Consomme : `docs/revue/2026-09-04-matrice-fonctionnalites.md` — le README ne
  promet que des fonctionnalités dont la matrice dit `livre`.

Le README actuel est faux sur quatre points au moins : statut « pré-v0.1 »,
tableau de jalons M1→M10 périmé, cœur décrit comme « naissant », liste de
fonctionnalités qui s'arrête au builder.

- [ ] **Étape 1 : vérifier ce que le lecteur peut réellement faire**

```bash
cd /home/lenen/projets/geostudio
grep -n "version" core/pyproject.toml | head -3
git tag | tail -5
grep -n "image:" docker-compose.yml | head -20
sed -n '1,60p' CONTRIBUTING.md
```

Les commandes de démarrage annoncées par le README doivent être celles qui
marchent réellement — piège n°3 : ne pas les recopier de l'ancien README.

- [ ] **Étape 2 : écrire le nouveau README**

Structure, pour un visiteur GitHub :

1. Titre, une phrase de positionnement, badges (licence, CI, version).
2. « Ce que fait GeoStudio » — six à huit puces concrètes, orientées usage, pas
   architecture. Chacune adossée à une ligne `livre` de la matrice.
3. Captures ou GIF si des ressources existent dans le dépôt ; sinon, une phrase
   décrivant l'interface et un renvoi vers la démo.
4. « Essayer en cinq minutes » — la vraie séquence vérifiée à l'étape 1.
5. « Architecture en bref » — un paragraphe, un schéma texte des services.
6. « État du projet » — la version publiée, ce qui est stable, ce qui ne l'est
   pas. Honnête, sans jalons internes.
7. « Aller plus loin » — renvois vers `docs/`, `CONTRIBUTING.md`,
   `CODE_OF_CONDUCT.md`, `CHANGELOG.md`, la matrice de fonctionnalités.
8. Licence Apache-2.0.

Ce qui disparaît : le tableau M1→M10, le statut « pré-v0.1 », la mention du fork
`gis-project` comme statut courant, la description du cœur comme naissant.

- [ ] **Étape 3 : vérifier chaque commande annoncée**

Exécuter réellement les commandes du README dans un répertoire propre, ou à
défaut vérifier leur existence (`ls scripts/bootstrap-env.sh`, cible npm présente
dans `shell/package.json`). Un README qui ment sur sa commande d'installation est
pire que pas de README.

- [ ] **Étape 4 : commiter**

```bash
git add README.md
git commit -m "docs: réécrit le README pour l'état réel du projet (SP-42)"
```

---

## Tâche 14 : le backlog unique

**Fichiers :**
- Créer : `docs/revue/2026-09-04-backlog.md`
- Créer : `docs/revue/2026-09-04-rapport-revue.md`

**Interfaces :**
- Consomme : `sp42-findings.jsonl` (les `minor`, et les `declasse`), les `GAP-nn`
  non retenus, et les suivis Minor encore ouverts listés dans `CLAUDE.md`.
- Produit : des entrées `REV-nnn`, citables par toute session future.

- [ ] **Étape 1 : écrire le rapport de revue**

`docs/revue/2026-09-04-rapport-revue.md` : la méthode (trois vagues, falsification
obligatoire), les comptes par sévérité, la liste des trouvailles confirmées avec
ce qui a été corrigé et par quel commit, la liste des déclassées avec leur
raison. C'est la trace de ce que la revue a réellement établi.

- [ ] **Étape 2 : générer les entrées de backlog**

```bash
cd /home/lenen/projets/geostudio
python3 - <<'PY' > /tmp/sp42-backlog-corps.md
import json
t = [json.loads(l) for l in open(".superpowers/sdd/sp42-findings.jsonl") if l.strip()]
r = [e for e in t if e["severite"] == "minor" or e.get("statut") == "declasse"]
print("| Id | Sévérité | Sujet | Fichier | Origine |")
print("|---|---|---|---|---|")
for i, e in enumerate(sorted(r, key=lambda x: (x["severite"], x["axe"])), 1):
    s = "observation" if e.get("statut") == "declasse" else e["severite"]
    print(f"| REV-{i:03d} | {s} | {e['titre']} | `{e['fichier']}:{e['ligne']}` | {e['axe']} |")
PY
wc -l /tmp/sp42-backlog-corps.md
```

- [ ] **Étape 3 : absorber la dette héritée**

Reprendre les suivis Minor encore ouverts de `CLAUDE.md` (hérités SP-29b→SP-40 :
`DataTable.sortDirection` mort, identifiants DOM dupliqués dans la galerie,
`Drawer` sans `overflow-y-auto`, absence de garde `busy` sur
`ImportFileButton`/`NewItemButton`, `aria-expanded` absent sur cinq
déclencheurs, doctrines de mode démo divergentes, `GET /users` en N+1, …) et leur
attribuer un `REV-nnn`. **Vérifier chacun dans le code avant de l'inscrire** :
certains ont pu être fermés en chemin sans que la note soit mise à jour.

- [ ] **Étape 4 : ajouter les gaps non retenus**

Les `GAP-nn` que la feuille de route révisée (Tâche 16) ne prend pas entrent au
backlog avec un renvoi vers l'analyse.

- [ ] **Étape 5 : assembler, ordonner, commiter**

Le document s'ouvre sur son mode d'emploi : chaque entrée porte un identifiant
stable, une sévérité, un coût estimé, une preuve, et l'état `ouvert` ou `fermé`
avec le commit qui l'a fermée. Sections par thème, entrées triées par
impact/coût décroissant.

```bash
git add docs/revue/2026-09-04-backlog.md docs/revue/2026-09-04-rapport-revue.md
git commit -m "docs(revue): rapport de revue et backlog unique REV-nnn (SP-42)"
```

---

## Tâche 15 : spec de refactorisation structurelle (SP-43)

**Fichiers :**
- Créer : `docs/superpowers/specs/2026-09-04-sp43-refactorisation-structurelle-design.md`

**Interfaces :**
- Consomme : les trouvailles `minor` de duplication et de patrons divergents, et
  les mesures ci-dessous.
- Produit : une spec prête à devenir un plan. **Aucun code n'est refactorisé.**

- [ ] **Étape 1 : mesurer les fichiers trop gros**

```bash
cd /home/lenen/projets/geostudio
find core/app -name '*.py' | xargs wc -l | sort -rn | head -20
find shell/src -name '*.tsx' -o -name '*.ts' | grep -v -e test -e generated | xargs wc -l | sort -rn | head -20
```

Repères connus : `core/app/mcp/tools.py` 1058 l., `core/app/pipelines/runtime.py`
894 l., `shell/src/api/itemClient.ts` 1741 l., `shell/src/map/MapView.tsx`
1425 l., `shell/src/api/types.ts` 970 l., `shell/src/map/MapSymbologyEditor.tsx`
809 l. Un fichier gros n'est pas un défaut en soi : la spec doit dire ce que
**chacun** fait de trop, pas seulement sa taille.

- [ ] **Étape 2 : relever la duplication qui a déjà coûté**

Chercher ce qui est répété trois fois ou plus **et** a déjà causé un défaut :
les privilèges du rôle Créateur triplement dupliqués sans lien mécanique, le
boilerplate `create_role`/`set_user_role` des tests, les recettes de contrôles de
formulaire divergentes entre pages sœurs, les trois littéraux `GET /me` des
mocks E2E, les patrons de page du triptyque. Chaque entrée cite l'occurrence du
défaut qu'elle a produit.

- [ ] **Étape 3 : relever les patrons divergents entre pages sœurs**

Les neuf familles SP-30 ont produit des divergences documentées et jamais
tranchées : ordre alertes/bouton, séparateur `border-t` conditionnel ou non,
gestion ou non de `isError`, `<main>`/`<aside>`/`<div>`, hauteurs de contrôles.
Les inventorier, et pour chacune, proposer la forme unique à retenir.

- [ ] **Étape 4 : écrire la spec**

Sections : motivation adossée aux défauts réellement payés ; inventaire par
fichier avec ce qu'il fait de trop et le découpage proposé ; abstractions à
extraire ; ordre de découpage, du moins risqué au plus risqué ; **pour chaque
étape, le filet de test qui doit exister avant de commencer** ; risques de
régression ; ce qui est explicitement hors périmètre.

- [ ] **Étape 5 : commiter**

```bash
git add docs/superpowers/specs/2026-09-04-sp43-refactorisation-structurelle-design.md
git commit -m "docs(spec): inventaire de refactorisation structurelle (SP-43)"
```

---

## Tâche 16 : feuille de route révisée

**Fichiers :**
- Créer : `docs/vision/2026-09-04-feuille-de-route-revisee.md`

**Interfaces :**
- Consomme : `docs/revue/2026-09-04-analyse-gaps.md`.
- Produit : un phasage SP-43+.

Aucun document existant de `docs/vision/` n'est modifié : celui-ci les cite.

- [ ] **Étape 1 : sélectionner les gaps qui deviennent des SP**

Retenir ceux dont l'impact justifie le coût. Chaque gap non retenu part au
backlog (Tâche 14, étape 4) — aucun ne disparaît silencieusement.

- [ ] **Étape 2 : phaser**

Un tableau : numéro de SP proposé, titre, gaps couverts, dépendances,
prérequis, coût estimé. SP-43 est déjà pris par la refactorisation structurelle
(Tâche 15) ; la numérotation démarre donc à SP-44. Les dépendances sont
explicites : un SP qui suppose une capacité livrée par un autre le dit.

- [ ] **Étape 3 : expliciter ce qui reste non arbitré**

Les questions produit ouvertes du comparatif — Q2 (premiers utilisateurs réels,
la seule qui puisse réordonner le phasage), Q10 (temps réel), Q11 (hors ligne) —
et les arbitrages que cette revue a fait remonter sans les trancher. Une feuille
de route qui prétend tout savoir est fausse.

- [ ] **Étape 4 : commiter**

```bash
git add docs/vision/2026-09-04-feuille-de-route-revisee.md
git commit -m "docs(vision): feuille de route révisée SP-44+ issue de la revue globale (SP-42)"
```

---

## Tâche 17 : dégonflement de `CLAUDE.md`

**Fichiers :**
- Modifier : `CLAUDE.md`
- Modifier : `docs/superpowers/2026-08-27-historique-execution-sp0-sp26.md`

`CLAUDE.md` est chargé intégralement à chaque session. Il porte aujourd'hui des
récits d'exécution de plusieurs centaines de lignes qui ne changent le
comportement d'aucune session.

- [ ] **Étape 1 : mesurer**

```bash
wc -l CLAUDE.md docs/superpowers/2026-08-27-historique-execution-sp0-sp26.md
```

- [ ] **Étape 2 : déplacer, ne pas supprimer**

Verser dans le fichier d'historique les récits détaillés de `### Livré` — ce que
chaque revue finale a trouvé, les rounds de correction, les comptes de tests
historiques. Chaque SP ne garde dans `CLAUDE.md` qu'**une à trois lignes** : ce
qu'il a livré, et le seul fait qui changerait le comportement d'une session
future.

Le critère de tri, appliqué ligne par ligne : *est-ce que cette phrase changerait
ce que je fais dans une session future ?* Si non, elle part à l'historique. Le
récit d'un correctif fermé n'y résiste pas ; un piège de commande, une contrainte
d'environnement, un arbitrage figé, oui.

- [ ] **Étape 3 : remplacer la liste de suivis par un renvoi**

La section `### À venir` et les listes de Minor hérités laissent place à un
renvoi vers `docs/revue/2026-09-04-backlog.md`. Vérifier qu'aucun élément n'est
perdu au passage : chaque suivi supprimé doit exister comme `REV-nnn`.

- [ ] **Étape 4 : mettre à jour les comptes et ajouter l'entrée SP-42**

Actualiser les comptes de tests des sections « Commandes » avec les valeurs
mesurées à la Tâche 18, et ajouter l'entrée SP-42 dans `### Livré`, en trois à
six lignes : ce que la revue a trouvé, ce qui a été corrigé, où sont les
livrables.

- [ ] **Étape 5 : vérifier la réduction et commiter**

```bash
wc -l CLAUDE.md
grep -c "REV-" docs/revue/2026-09-04-backlog.md
git add CLAUDE.md docs/superpowers/2026-08-27-historique-execution-sp0-sp26.md
git commit -m "docs: dégonfle CLAUDE.md et verse l'historique détaillé à l'archive (SP-42)"
```

---

## Tâche 18 : vérification finale

**Fichiers :** aucun créé ; corrections éventuelles selon les résultats.

- [ ] **Étape 1 : suite complète du cœur**

```bash
cd core && CORE_TEST_DATABASE_URL="<DSN>" uv run pytest -q 2>&1 | tail -20
```

Comparer au triplet de la baseline. Les deux échecs préexistants connus ne
comptent pas comme régression ; tout autre écart, si.

- [ ] **Étape 2 : suites complètes du shell**

```bash
cd ../shell && rm -rf dist dist-export coverage
npx vitest run --coverage 2>&1 | tail -10
node scripts/check-coverage.mjs coverage/coverage-summary.json .coverage-threshold
npm run build
```

- [ ] **Étape 3 : suite E2E complète**

```bash
cd shell && npm run e2e 2>&1 | tail -5
cat test-results/.last-run.json
```

Le verdict se lit dans `.last-run.json`. Un run dure une quinzaine de minutes ;
la fin de sortie du reporter `list` est tronquée et a déjà induit en erreur.

- [ ] **Étape 4 : portes de qualité**

```bash
cd core && uv run ruff check . && uv run ruff format --check .
uv run mypy --strict app/auth app/secrets app/analytics app/copilot app/admin_tools app/roles
uv run lint-imports
uv run python scripts/check_coverage.py coverage.xml .coverage-threshold
cd ../shell && npm run lint && npm run format:check
cd .. && uvx pre-commit run --all-files
```

- [ ] **Étape 5 : diff OpenAPI et types**

```bash
cd core && PYTHONPATH=. \
  CORE_SECRETS_MASTER_KEY="AAECAwQFBgcICQoLDA0ODxAREhMUFRYXGBkaGxwdHh8=" \
  uv run python scripts/export_openapi.py openapi.json
cd ../shell && npm run gen:api-types
cd .. && git status --short core/openapi.json shell/src/api/generated/core-schema.d.ts
```

Attendu : rien à commiter. Un diff ici signale une régénération oubliée par les
Tâches 8 ou 9 — ou une dérive laissée par une session concurrente, à vérifier
avant d'imputer à SP-42.

- [ ] **Étape 6 : contrôler la présence des dix livrables**

```bash
cd /home/lenen/projets/geostudio
ls -l docs/revue/2026-09-04-{matrice-fonctionnalites,analyse-gaps,backlog,rapport-revue}.md \
      docs/superpowers/specs/2026-09-04-sp4{2-revue-globale,3-refactorisation-structurelle}-design.md \
      docs/vision/2026-09-04-feuille-de-route-revisee.md README.md CLAUDE.md
git log --oneline --grep="SP-42" | cat
```

- [ ] **Étape 7 : rendre compte**

Présenter à Tanguy : les trois triplets de tests mesurés face à la baseline, la
couverture, l'état des portes de qualité, le compte de trouvailles par sévérité
et par statut, le nombre de lignes de matrice par état, le nombre d'entrées de
backlog, et la liste des commits SP-42. Ce qui n'a pas pu être vérifié dans cet
environnement est dit explicitement, jamais présenté comme acquis.
