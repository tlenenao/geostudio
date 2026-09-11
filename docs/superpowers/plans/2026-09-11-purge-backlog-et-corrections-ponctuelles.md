# Purge backlog + REV-094/REV-176 — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remettre `docs/revue/2026-09-04-backlog.md` en cohérence avec l'état réel du code
(13 entrées déjà fermées mais toujours marquées `ouvert`), puis fermer réellement les 2 dernières
entrées de bonne foi (REV-094, REV-176).

**Architecture:** Aucun changement d'architecture. Tâche 1 = édition mécanique d'un fichier Markdown
via un script Python jetable (pas de nouvel outil permanent). Tâches 2-3 = corrections shell
ciblées (un composant UI, un token CSS). Tâche 4 = recalcul manuel d'une section de sommaire.

**Tech Stack:** Python 3 (script jetable, non committé), TypeScript/React/Radix UI (shell), CSS
(tokens), Vitest + Playwright (tests).

## Global Constraints

- Spec de référence : `docs/superpowers/specs/2026-09-11-purge-backlog-et-corrections-ponctuelles-design.md`.
- Avant d'écrire une ligne de fermeture dans `backlog.md`, vérifier le commit cité avec
  `git merge-base --is-ancestor <sha> dev` — ne jamais recopier une affirmation sans la revérifier
  (le dépôt continue de bouger).
- Ne jamais marquer une entrée `fermé`/`partiellement fermé` dans `backlog.md` avant que son
  correctif réel (s'il y en a un) ne soit dans le même commit ou un commit antérieur déjà mergé.
- Commits conventionnels (`docs(revue): …`, `fix(shell): …`), un sujet par commit, message se
  terminant par le trailer `Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>`.
- Code en anglais, commentaires/docs/messages de commit en français (convention du dépôt).
- TDD : test falsifié avant tout correctif de code (Tâches 2-3).
- Ne pas toucher REV-102, REV-111, ni les 12 gaps benchmark non retenus (REV-104, 112-117,
  119-121) — hors périmètre explicite de ce plan.

---

## Task 1: Bookkeeping — 13 entrées déjà fermées dans le code

**Files:**
- Modify: `docs/revue/2026-09-04-backlog.md`

**Interfaces:**
- Consumes: rien (tâche indépendante).
- Produces: rien consommé par une autre tâche — Task 4 relira l'état final du fichier après les
  Tâches 1-3, mais ne dépend d'aucune interface de code.

- [ ] **Step 1: Vérifier chaque commit cité avant d'écrire quoi que ce soit**

Run:
```bash
cd /home/lenen/projets/geostudio
for sha in 6101e9eb e0119c79 c721c3fa 7a2f9414 e11fda2b 163a0278 e7133941 44f1d228 95267b68 ff018dc3 edff7592 346e9bb9 a1579cd3 802d4daa; do
  if git merge-base --is-ancestor "$sha" dev; then
    echo "OK  $sha"
  else
    echo "MANQUANT $sha — ARRÊTER, revérifier avant de continuer"
  fi
done
```
Expected: les 14 lignes affichent toutes `OK`. Si une seule affiche `MANQUANT`, ne pas continuer
cette tâche — le commit a pu être réécrit ou n'est pas sur `dev` ; ré-enquêter (`git log --oneline
--all -S "<texte du commit>"`) avant de reprendre.

- [ ] **Step 2: Vérifier l'état actuel des 13 lignes `État` avant remplacement**

Run:
```bash
for n in 003 005 011 042 098 110 128 149 174 175 178 180 181; do
  echo "--- REV-$n ---"
  awk -v n="REV-$n" '$0 ~ "^### "n" " {f=1} f && /État/ {print; exit}' docs/revue/2026-09-04-backlog.md
done
```
Expected: chaque bloc affiche encore `- **État :** ouvert...` (pas déjà `fermé`). Si une entrée
affiche déjà `fermé`/`partiellement fermé`, une session concurrente l'a déjà traitée entre
l'écriture de ce plan et son exécution — la retirer du script du Step 3 plutôt que de l'écraser.

- [ ] **Step 3: Écrire et exécuter le script de remplacement des 13 lignes `État`**

Run:
```bash
cd /home/lenen/projets/geostudio
python3 - <<'PY'
import re

path = "docs/revue/2026-09-04-backlog.md"
text = open(path, encoding="utf-8").read()

updates = {
    "REV-003": "- **État :** fermé — commit `6101e9eb` (2026-09-06) : vérification bout-en-bout "
        "Keycloak réelle documentée dans `shell/src/builder/copilot/useMcpToken.ts` "
        "(`signinSilent({forceIframeAuth:true})` réussit malgré `X-Frame-Options: DENY`, aucun "
        "contournement nécessaire).",
    "REV-005": "- **État :** fermé — commit `e0119c79` (intégration SP-45, GAP-61.c) : `_cache` de "
        "`live_query.py` gagne un TTL + un `_sweep` périodique (patron `RateLimiter._sweep`) ; 2 des "
        "4 routes ArcGIS live-query rattachées au groupe rate-limit `harvest`, les 2 autres déjà "
        "couvertes par le groupe `jobs` via `_EXPORT_PATH_RE`.",
    "REV-011": "- **État :** fermé — commit `c721c3fa` : `register_collection` vérifie un conflit "
        "d'id cross-tenant (409 explicite via `get_collection_by_id_any_tenant`) ; "
        "`list_candidate_tables` exclut les tables déjà enregistrées par tout tenant.",
    "REV-042": "- **État :** fermé — commit `7a2f9414` : `OpenAICompatibleProvider.embed` construit "
        "son client via `build_guarded_client()` (`app.search.egress`) au lieu d'un `httpx.post` nu.",
    "REV-098": "- **État :** fermé — commit `e11fda2b` : job CI `stac-conformance` (`stac-api-validator` "
        "sur core/collections/features, bloquant ; item-search en `continue-on-error`, non bloquant).",
    "REV-110": "- **État :** partiellement fermé — commits `163a0278`/`e7133941`/`44f1d228`/`95267b68` : "
        "Snowflake livré et testé manuellement (`reader.connector.snowflake`, jamais câblé en CI "
        "faute d'émulateur) ; Redshift compatible par construction avec `reader.connector.postgres`, "
        "jamais vérifié contre un cluster réel ; Databricks mécaniquement faisable, non fait ; "
        "BigQuery bloqué par la conception actuelle de `SecretPayload` (DSN texte, incompatible "
        "avec un compte de service JSON).",
    "REV-128": "- **État :** fermé — commit `ff018dc3` : `showScaleBar`/`showNorthArrow` retirés du "
        "schéma `PrintLayout` (option retenue : retrait, pas implémentation du rendu).",
    "REV-149": "- **État :** fermé — commit `edff7592` : `shell/src/builder/NavigationPanel.tsx` ne "
        "construit un payload `{center:[lon,lat]}` que pour l'action `flyTo`.",
    "REV-174": "- **État :** fermé — commit `346e9bb9` : `save_app_config` (MCP) exécute désormais la "
        "même séquence de gardes de capacité + validateurs par kind que `PUT /configs/by-item/{id}`.",
    "REV-175": "- **État :** fermé — commit `a1579cd3` : spike mené sur Postgres+pgvector jetable — "
        "les 2 formes `Index()` SQLAlchemy équivalentes émettent un DDL byte-pour-byte identique au "
        "DDL brut existant, mais Alembic (`compare_metadata()`) est structurellement aveugle à toute "
        "dérive réelle sur `postgresql_ops`/`postgresql_with`. Décision actée : ne pas matérialiser "
        "en `Base.metadata`, le filtre nommé `_KNOWN_FUNCTIONAL_INDEXES` reste en l'état.",
    "REV-178": "- **État :** partiellement fermé — commit `802d4daa` : échantillon d'audit a11y élargi "
        "de 9 à 17 pages, `eslint-plugin-jsx-a11y` ajouté en complément statique. Reste hors "
        "périmètre, assumé : exhaustivité du catalogue de routes, navigation clavier exhaustive, "
        "contraste en mode sombre.",
    "REV-180": "- **État :** fermé — commit `e11fda2b` : `bilan.js` lit `priorite_source` (badge "
        "nuancé + tuile de synthèse « priorités encore amorcées »). `render_md.py` reste sans "
        "colonne dédiée, jugé non bloquant.",
    "REV-181": "- **État :** fermé — commit `e11fda2b` : `feature_health_cli.py` gagne un mode "
        "`--check-fresh`, câblé dans le job CI dédié.",
}

# Découpe le fichier en blocs commençant chacun exactement à une entête "### REV-".
# Lookahead zero-width : splits[0] = préambule avant la première entête,
# splits[i] (i>=1) commence par "### REV-NNN " et va jusqu'à l'entête suivante (ou EOF).
splits = re.split(r"(?=^### REV-\d+ )", text, flags=re.MULTILINE)

rev_header_re = re.compile(r"^### (REV-\d+) ")
applied = set()
for idx in range(1, len(splits)):
    chunk = splits[idx]
    m = rev_header_re.match(chunk)
    if not m:
        continue
    rev = m.group(1)
    if rev not in updates:
        continue
    new_chunk, n = re.subn(
        r"^- \*\*État :\*\*.*$", updates[rev], chunk, count=1, flags=re.MULTILINE
    )
    if n != 1:
        raise SystemExit(f"{rev}: attendu exactement 1 ligne État, trouvé {n}")
    splits[idx] = new_chunk
    applied.add(rev)

missing = set(updates) - applied
if missing:
    raise SystemExit(f"blocs REV introuvables : {sorted(missing)}")

open(path, "w", encoding="utf-8").write("".join(splits))
print(f"OK — {len(applied)} entrées mises à jour")
PY
```
Expected: `OK — 13 entrées mises à jour`.

- [ ] **Step 4: Vérifier le résultat**

Run:
```bash
for n in 003 005 011 042 098 110 128 149 174 175 178 180 181; do
  echo "--- REV-$n ---"
  awk -v n="REV-$n" '$0 ~ "^### "n" " {f=1} f && /État/ {print; exit}' docs/revue/2026-09-04-backlog.md
done
grep -c "^- \*\*État :\*\* ouvert$" docs/revue/2026-09-04-backlog.md
```
Expected: les 13 blocs affichent chacun leur nouvelle ligne `fermé`/`partiellement fermé` ; le
`grep -c` final (qui compte les lignes `ouvert` sans aucune parenthèse — celles de REV-003/005/
011/042/174/175/178/180/181) est descendu de 9 à 0 (les 4 autres, REV-098/110/128/149, avaient un
suffixe entre parenthèses donc ne comptaient pas dans ce grep précis — ne pas s'inquiéter s'il ne
baisse pas de 13 exactement).

- [ ] **Step 5: Commit**

```bash
git add docs/revue/2026-09-04-backlog.md
git commit -m "$(cat <<'EOF'
docs(revue): ferme 13 entrées du backlog déjà résolues dans le code

Le backlog listait ces 13 entrées comme ouvertes alors que des commits
du 2026-09-06/07 (REV-003/005/011/042/098/110/128/149/174/175/178/180/
181) les avaient déjà fermées sans que leur champ État ne soit jamais
mis à jour (piège n°12 appliqué au backlog plutôt qu'à la matrice de
fonctionnalités). Vérifié commit par commit contre dev avant réécriture.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
)"
```

---

## Task 2: REV-094 — migrer les 2 derniers consommateurs de `ui/dialog.tsx`

**Files:**
- Modify: `shell/src/ui/kit/Dialog.tsx`
- Modify: `shell/src/ui/kit/Dialog.test.tsx`
- Modify: `shell/src/pages/AppRuntimePage.tsx`
- Modify: `shell/src/builder/widgets/modal.tsx`
- Delete: `shell/src/ui/dialog.tsx`
- Delete: `shell/src/ui/dialog.test.tsx`
- Modify: `docs/revue/2026-09-04-backlog.md`

**Interfaces:**
- Consumes: rien (tâche indépendante de la Task 1, peut s'exécuter en parallèle).
- Produces: `Dialog` (`shell/src/ui/kit/Dialog.tsx`) expose désormais une prop optionnelle
  `size?: "md" | "lg"` (défaut `"md"`) en plus de `open`/`onOpenChange`/`title`/`children` déjà
  existants — toute tâche future qui touche `ui/kit/Dialog` doit connaître cette prop.

- [ ] **Step 1: Écrire le test qui échoue pour la prop `size`**

Ajouter à la fin de `shell/src/ui/kit/Dialog.test.tsx` (après le test existant "le focus est piégé
dans la boîte de dialogue à l'ouverture") :

```tsx
test("size='lg' rend une largeur plus grande que le défaut 'md'", () => {
  const { rerender } = render(
    <Dialog open onOpenChange={() => {}} title="T" size="lg">
      <p>corps</p>
    </Dialog>,
  );
  expect(screen.getByRole("dialog")).toHaveClass("max-w-2xl");

  rerender(
    <Dialog open onOpenChange={() => {}} title="T">
      <p>corps</p>
    </Dialog>,
  );
  expect(screen.getByRole("dialog")).toHaveClass("max-w-md");
});
```

- [ ] **Step 2: Vérifier que le test échoue**

Run: `cd shell && npx vitest run src/ui/kit/Dialog.test.tsx`
Expected: FAIL — `Dialog` ne connaît pas de prop `size`, TypeScript refuse la compilation du test
(`Property 'size' does not exist on type...`) ou, si le test passe la vérification de type malgré
tout (props non typées strictement en JSX), la classe `max-w-2xl` n'apparaît jamais sur l'élément.

- [ ] **Step 3: Implémenter la prop `size` dans `ui/kit/Dialog.tsx`**

Remplacer tout le contenu de `shell/src/ui/kit/Dialog.tsx` par :

```tsx
// SPDX-License-Identifier: Apache-2.0
import * as DialogPrimitive from "@radix-ui/react-dialog";

const SIZE_CLASSES: Record<"md" | "lg", string> = {
  md: "max-w-md",
  lg: "max-w-2xl",
};

export function Dialog({
  open,
  onOpenChange,
  title,
  size = "md",
  children,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  title: string;
  size?: "md" | "lg";
  children: React.ReactNode;
}) {
  return (
    <DialogPrimitive.Root open={open} onOpenChange={onOpenChange}>
      <DialogPrimitive.Portal>
        <DialogPrimitive.Overlay className="fixed inset-0 z-50 bg-ink/40" />
        <DialogPrimitive.Content
          className={`fixed left-1/2 top-1/2 z-50 w-full ${SIZE_CLASSES[size]} -translate-x-1/2 -translate-y-1/2 rounded-lg border border-rule bg-raised p-6 shadow-lg`}
        >
          <DialogPrimitive.Title className="mb-4 text-lg font-semibold text-ink">
            {title}
          </DialogPrimitive.Title>
          {children}
        </DialogPrimitive.Content>
      </DialogPrimitive.Portal>
    </DialogPrimitive.Root>
  );
}
```

- [ ] **Step 4: Vérifier que le test passe**

Run: `cd shell && npx vitest run src/ui/kit/Dialog.test.tsx`
Expected: PASS (4 tests : les 3 existants + le nouveau).

- [ ] **Step 5: Migrer `AppRuntimePage.tsx`**

Dans `shell/src/pages/AppRuntimePage.tsx`, remplacer :
```tsx
import { Dialog } from "../ui/dialog";
```
par :
```tsx
import { Dialog } from "../ui/kit/Dialog";
```

Et remplacer :
```tsx
      <Dialog
        open={saveDialogOpen}
        onClose={() => setSaveDialogOpen(false)}
        title={t("appRuntime.saveView")}
      >
```
par :
```tsx
      <Dialog
        open={saveDialogOpen}
        onOpenChange={setSaveDialogOpen}
        title={t("appRuntime.saveView")}
      >
```

- [ ] **Step 6: Migrer `modal.tsx`**

Dans `shell/src/builder/widgets/modal.tsx`, remplacer :
```tsx
import { Dialog } from "../../ui/dialog";
```
par :
```tsx
import { Dialog } from "../../ui/kit/Dialog";
```

Et remplacer :
```tsx
      return (
        <Dialog open={open} onClose={() => setOpen(false)} title={title} wide={wide}>
```
par :
```tsx
      return (
        <Dialog open={open} onOpenChange={setOpen} title={title} size={wide ? "lg" : "md"}>
```

- [ ] **Step 7: Lancer les tests des deux fichiers migrés**

Run: `cd shell && npx vitest run src/pages/AppRuntimePage.test.tsx src/builder/widgets/modal.test.tsx`
Expected: PASS, sans modification de ces deux fichiers de test (les assertions existantes utilisent
déjà `getByRole("dialog", {...})`/`findByRole` de façon générique, indépendante de l'implémentation
du composant). Si un échec apparaît lié à une API navigateur manquante dans jsdom
(`ResizeObserver`/`hasPointerCapture`/`PointerEvent`, cf. CLAUDE.md piège n°10) : ajouter un
polyfill **local à `modal.test.tsx` uniquement** (jamais dans `shell/src/test/setup.ts`), au même
patron qu'un fichier de test existant consommant un composant Radix (`grep -rl "hasPointerCapture"
shell/src` pour trouver un exemple à copier).

- [ ] **Step 8: Supprimer `ui/dialog.tsx`, devenu orphelin**

Run:
```bash
cd shell
grep -rn 'ui/dialog"' src --include=*.tsx
```
Expected: aucune ligne (les deux seuls consommateurs ont été migrés aux Steps 5-6).

Puis :
```bash
git rm src/ui/dialog.tsx src/ui/dialog.test.tsx
```

- [ ] **Step 9: Suite complète shell**

Run: `cd shell && npm run test && npm run build`
Expected: PASS / build propre.

- [ ] **Step 10: Commit du code**

```bash
git add shell/src/ui/kit/Dialog.tsx shell/src/ui/kit/Dialog.test.tsx \
  shell/src/pages/AppRuntimePage.tsx shell/src/builder/widgets/modal.tsx
git commit -m "$(cat <<'EOF'
fix(shell): migre les 2 derniers usages de ui/dialog.tsx vers ui/kit/Dialog (REV-094)

ui/kit/Dialog gagne une prop size ("md"/"lg", défaut "md") pour ne pas
perdre le réglage "wide" du widget Modale (max-w-2xl) lors de la
migration. ui/dialog.tsx (l'ancien composant) est retiré, orphelin.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
)"
```

- [ ] **Step 11: Capturer le sha et mettre à jour `backlog.md`**

Run:
```bash
cd /home/lenen/projets/geostudio
SHA=$(git rev-parse --short HEAD)
echo "$SHA"
```

Dans `docs/revue/2026-09-04-backlog.md`, dans le bloc `### REV-094 ...`, remplacer :
```
- **État :** ouvert (doctrine assumée, pas une régression)
```
par (en substituant `<SHA>` par la valeur affichée ci-dessus) :
```
- **État :** fermé — commit `<SHA>` : `ui/kit/Dialog` gagne une prop `size`, les deux derniers
  consommateurs de `ui/dialog.tsx` (`AppRuntimePage.tsx`, `builder/widgets/modal.tsx`) migrés,
  `ui/dialog.tsx` retiré (orphelin).
```

- [ ] **Step 12: Commit du bookkeeping**

```bash
git add docs/revue/2026-09-04-backlog.md
git commit -m "$(cat <<'EOF'
docs(revue): ferme REV-094 (migration ui/dialog.tsx terminée)

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
)"
```

---

## Task 3: REV-176 — contraste du token `--gs-ink-3`

**Files:**
- Modify: `shell/src/styles/tokens.css`
- Modify: `shell/e2e/a11y-audit.spec.ts`
- Modify: `docs/revue/2026-09-04-backlog.md`

**Interfaces:**
- Consumes: rien (tâche indépendante des Tasks 1-2, peut s'exécuter en parallèle).
- Produces: `--gs-ink-3` (ambiance claire) vaut désormais `#5f6f75` au lieu de `#6e8087` — toute
  tâche future qui capture une référence visuelle de l'ambiance claire doit s'attendre à ce
  changement (léger assombrissement du texte le plus atténué de la hiérarchie).

**Valeurs vérifiées avant d'écrire cette tâche (calcul WCAG relative luminance, pas une
approximation)** : ambiance claire, fond `--gs-background: #eff2f1` — `#6e8087` actuel = 3.65:1 ;
`#5f6f75` choisi = 4.64:1 (marge au-dessus du seuil 4.5:1) ; `--gs-ink-2: #3b4c54` = 7.94:1, donc
`#5f6f75` reste bien strictement moins contrasté que `--gs-ink-2` (hiérarchie préservée). Ambiance
sombre : `--gs-ink-3: #7c8f94` sur fond `--gs-background: #0a1316` mesure déjà 5.56:1 — **au-dessus
du seuil AA, aucun changement nécessaire côté sombre.**

- [ ] **Step 1: Falsification préalable — confirmer que le test a11y échoue bien avec la valeur actuelle une fois l'exclusion retirée**

Dans `shell/e2e/a11y-audit.spec.ts`, remplacer temporairement :
```tsx
const EXCLUSIONS: Exclusion[] = [
  {
    rule: "color-contrast",
    nodeIncludes: "foreground color: #6e8087",
    reason:
      "Token --gs-ink-3 (le plus atténué de l'ambiance) : 3.65:1 sur fond " +
      "--gs-background, sous le seuil AA de 4.5:1 pour du texte normal. " +
      'Ressort sur plusieurs pages (StatusBar "v0.1.0 · demo", compteur ' +
      '"N entités" de LayersPanel, …) car c\'est le même token de couleur, ' +
      "réutilisé par ~20 fichiers (Combobox, Chip, Toast, Breadcrumb, …). " +
      "Retoucher sa valeur corrigerait ces occurrences mais changerait " +
      "l'ambiance visuelle de tout le shell, hors budget de ce SP (spec " +
      "SP-57a §3.3). Suivi : REV-176 (docs/revue/2026-09-04-backlog.md).",
  },
];
```
par :
```tsx
const EXCLUSIONS: Exclusion[] = [];
```

Run: `cd shell && npm run e2e -- e2e/a11y-audit.spec.ts`
Expected: FAIL — au moins un test (StatusBar sur une page de l'échantillon, ou `LayersPanel` sur
`MapEditorPage`) échoue avec une violation `color-contrast` non exclue. C'est la preuve que
l'exclusion retirée protégeait bien un vrai défaut, avant de le corriger.

- [ ] **Step 2: Corriger le token dans `tokens.css`**

Dans `shell/src/styles/tokens.css`, dans le bloc `:root` (ambiance claire, PAS les deux blocs
sombres plus bas), remplacer :
```css
  --gs-ink: #0e1a20;
  --gs-ink-2: #3b4c54;
  --gs-ink-3: #6e8087;
```
par :
```css
  --gs-ink: #0e1a20;
  --gs-ink-2: #3b4c54;
  --gs-ink-3: #5f6f75;
```
Ne pas toucher aux deux occurrences de `--gs-ink-3: #7c8f94;` (ambiance sombre, `@media
(prefers-color-scheme: dark)` et `[data-theme="dark"]`) — déjà conformes (5.56:1).

- [ ] **Step 3: Relancer le test a11y (exclusion toujours vide) — doit maintenant passer**

Run: `cd shell && npm run e2e -- e2e/a11y-audit.spec.ts`
Expected: PASS — plus aucune violation `color-contrast` liée à `--gs-ink-3` sur les 17 pages de
l'échantillon.

- [ ] **Step 4: Vérification visuelle manuelle (non automatisable)**

Lancer le shell en dev (`cd shell && npm run dev`), ouvrir `/internal/kit-gallery` en ambiance
claire ET sombre (bascule système ou `data-theme`), confirmer que le texte le plus atténué reste
lisible et cohérent avec la hiérarchie `--gs-ink` > `--gs-ink-2` > `--gs-ink-3`. Confirmer la même
chose sur `StatusBar` (pied de page, mention de version) et `LayersPanel` (compteur d'entités) d'une
carte. Aucune assertion automatisée ne couvre ce step — c'est une revue à l'œil, à consigner dans le
message du commit final si un ajustement visuel a été nécessaire.

- [ ] **Step 5: Retirer l'entrée `Exclusion` devenue inutile pour de bon**

L'`EXCLUSIONS: Exclusion[] = []` du Step 1 est déjà l'état final souhaité — ne rien changer de plus
ici, juste confirmer par relecture du fichier que l'exclusion REV-176 n'existe plus nulle part
ailleurs dans `a11y-audit.spec.ts` :
```bash
grep -n "REV-176\|6e8087" shell/e2e/a11y-audit.spec.ts
```
Expected: aucune ligne.

- [ ] **Step 6: Suite complète shell + build**

Run: `cd shell && npm run test && npm run build`
Expected: PASS / build propre (aucun test Vitest ne référence `--gs-ink-3` directement — si l'un
d'eux échoue de façon inattendue, vérifier qu'il ne s'agit pas d'un test de contraste ailleurs dans
le dépôt avant de conclure que ce changement en est la cause).

- [ ] **Step 7: Commit du code**

```bash
git add shell/src/styles/tokens.css shell/e2e/a11y-audit.spec.ts
git commit -m "$(cat <<'EOF'
fix(shell): assombrit --gs-ink-3 (ambiance claire) pour atteindre le seuil AA (REV-176)

#6e8087 mesurait 3.65:1 sur --gs-background (seuil WCAG AA 4.5:1 pour
texte normal). #5f6f75 atteint 4.64:1 tout en restant strictement moins
contrasté que --gs-ink-2 (7.94:1) — hiérarchie de texte préservée.
Ambiance sombre déjà conforme (5.56:1), non touchée. Exclusion a11y
retirée, falsifiée avant correction (Step 1 : le test échouait bien
sans l'exclusion et avec l'ancienne valeur).

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
)"
```

- [ ] **Step 8: Capturer le sha et mettre à jour `backlog.md`**

Run:
```bash
cd /home/lenen/projets/geostudio
SHA=$(git rev-parse --short HEAD)
echo "$SHA"
```

Dans `docs/revue/2026-09-04-backlog.md`, dans le bloc `### REV-176 ...`, remplacer :
```
- **État :** ouvert
```
par (en substituant `<SHA>` par la valeur affichée ci-dessus) :
```
- **État :** fermé — commit `<SHA>` : `--gs-ink-3` (ambiance claire) passé de `#6e8087` (3.65:1) à
  `#5f6f75` (4.64:1), hiérarchie de texte préservée (`--gs-ink-2` reste à 7.94:1). Ambiance sombre
  déjà conforme (5.56:1), non touchée. Exclusion retirée de `a11y-audit.spec.ts`.
```

- [ ] **Step 9: Commit du bookkeeping**

```bash
git add docs/revue/2026-09-04-backlog.md
git commit -m "$(cat <<'EOF'
docs(revue): ferme REV-176 (contraste --gs-ink-3 corrigé)

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
)"
```

---

## Task 4: Recalcul de la section « Répartition par statut »

**Files:**
- Modify: `docs/revue/2026-09-04-backlog.md`

**Interfaces:**
- Consumes: l'état final du fichier après les Tasks 1, 2 et 3 (doit s'exécuter après elles, pas en
  parallèle).
- Produces: rien consommé ailleurs — dernière tâche du plan.

- [ ] **Step 1: Recompter mécaniquement les trois listes actuelles**

Run:
```bash
cd /home/lenen/projets/geostudio
python3 - <<'PY'
import re

text = open("docs/revue/2026-09-04-backlog.md", encoding="utf-8").read()
splits = re.split(r"(?=^### REV-\d+ )", text, flags=re.MULTILINE)
rev_header_re = re.compile(r"^### (REV-\d+) ")

closed, partial, open_ = [], [], []
for chunk in splits[1:]:
    m = rev_header_re.match(chunk)
    if not m:
        continue
    rev = m.group(1)
    etat_m = re.search(r"^- \*\*État :\*\*\s*(.*)$", chunk, flags=re.MULTILINE)
    etat = etat_m.group(1) if etat_m else ""
    if etat.startswith("fermé"):
        closed.append(rev)
    elif etat.startswith("partiellement fermé"):
        partial.append(rev)
    elif etat.startswith("ouvert"):
        open_.append(rev)
    else:
        raise SystemExit(f"{rev}: état non reconnu : {etat!r}")

def numkey(rev):
    return int(rev.split("-")[1])

closed.sort(key=numkey)
partial.sort(key=numkey)
open_.sort(key=numkey)

print("FERMÉ", len(closed))
print(", ".join(closed))
print()
print("PARTIEL", len(partial))
print(", ".join(partial))
print()
print("OUVERT", len(open_))
print(", ".join(open_))
print()
print("TOTAL", len(closed) + len(partial) + len(open_))
PY
```
Expected : `FERMÉ 157`, `PARTIEL 13`, `OUVERT 12`, `TOTAL 182` (cf. §2.1 de la spec — si un nombre
diverge, une des Tasks 1-3 n'a pas produit l'état attendu ; ne pas continuer cette tâche avant
d'avoir compris pourquoi).

- [ ] **Step 2: Remplacer les trois listes et les trois en-têtes dans `backlog.md`**

Ouvrir `docs/revue/2026-09-04-backlog.md`, section `## Répartition par statut`. Remplacer l'en-tête
`### ✅ Fermé (143)` par `### ✅ Fermé (157)`, puis la liste qui suit par la liste `FERMÉ` imprimée
au Step 1 (format identique : REV séparées par `, `, retour à la ligne libre). Remplacer l'en-tête
`### 🟡 Partiellement fermé (11)` par `### 🟡 Partiellement fermé (13)`, puis sa liste par la liste
`PARTIEL`. Remplacer l'en-tête `### 🔴 Ouvert (28)` par `### 🔴 Ouvert (12)`, puis sa liste par la
liste `OUVERT` (elle doit contenir exactement REV-102, 104, 111, 112, 113, 114, 115, 116, 117, 119,
120, 121 — sinon une des Tasks 1-3 a laissé une entrée dans un état inattendu, investiguer avant de
continuer).

- [ ] **Step 3: Mettre à jour la phrase de synthèse en tête de section**

Remplacer la phrase :
```
**144 fermées, 11 partiellement fermées, 27 ouvertes** sur 182 entrées (2026-09-11 : REV-182 fermée
```
par (en gardant le reste de la phrase inchangé après cette clause) :
```
**157 fermées, 13 partiellement fermées, 12 ouvertes** sur 182 entrées (2026-09-11 : purge des 13
entrées stales REV-003/005/011/042/098/110/128/149/174/175/178/180/181 + fermeture réelle de
REV-094/REV-176 — 21 sessions/tâches concurrentes avaient fermé ces entrées dans le code sans
jamais mettre à jour ce champ, cf. `docs/superpowers/specs/
2026-09-11-purge-backlog-et-corrections-ponctuelles-design.md` ; compte précédent : 2026-09-11,
REV-182 fermée
```

- [ ] **Step 4: Vérifier qu'aucune autre occurrence des anciens comptes ne traîne**

Run:
```bash
grep -n "144 fermées\|✅ Fermé (143)\|🔴 Ouvert (28)" docs/revue/2026-09-04-backlog.md
```
Expected: aucune ligne (tout a été remplacé au Step 2-3).

- [ ] **Step 5: Commit**

```bash
git add docs/revue/2026-09-04-backlog.md
git commit -m "$(cat <<'EOF'
docs(revue): recalcule la répartition par statut du backlog (157/13/12)

Après la purge de 13 entrées stales et la fermeture réelle de
REV-094/REV-176 (cette même branche), la section de sommaire n'était
plus cohérente avec le champ État de chaque entrée. Recompte mécanique
(script Python, pas une réédition manuelle) plutôt qu'une transcription
à la main — la cause documentée de la dérive précédente.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
)"
```

---

## Self-Review (fait à l'écriture de ce plan)

**Couverture de la spec** : §2 (bookkeeping 13 entrées) → Task 1. §2.1 (recalcul répartition) →
Task 4. §3 (REV-094) → Task 2. §4 (REV-176) → Task 3. §5 (tests) → intégré dans chaque tâche. §6
(hors périmètre) → respecté, aucune tâche ne touche REV-102/111/104/112-117/119-121.

**Placeholders** : aucun `TBD`/`TODO` ; les deux `<SHA>` (Tasks 2 et 3) sont des valeurs à capturer
via une commande donnée explicitement (`git rev-parse --short HEAD`), pas des inconnues laissées à
deviner — inévitable puisqu'un commit ne peut pas connaître son propre hash avant d'exister.

**Cohérence des types/noms** : `Dialog` garde exactement `open`/`onOpenChange`/`title`/`children`
déjà utilisés par son unique test existant, `size` est la seule prop ajoutée, utilisée à l'identique
dans les Steps 3, 5, 6 de la Task 2.

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-09-11-purge-backlog-et-corrections-ponctuelles.md`. Two execution options:

1. **Subagent-Driven (recommended)** - I dispatch a fresh subagent per task, review between tasks, fast iteration
2. **Inline Execution** - Execute tasks in this session using executing-plans, batch execution with checkpoints

Which approach?
