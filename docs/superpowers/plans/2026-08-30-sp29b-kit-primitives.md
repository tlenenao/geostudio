# SP-29b — Kit de primitives headless — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Construire le kit de ~40 primitives headless (Radix UI + tokens
GeoStudio) qui servira de référence visuelle à SP-30 pour basculer les 83
`<select>`, 159 `<input>` et 139 `<button>` bruts du shell.

**Architecture:** ~40 primitives headless (Radix UI Primitives, MIT,
compatibilité React 19 vérifiée) enveloppées dans `shell/src/ui/kit/`, habillées
exclusivement par les tokens `--gs-*` déjà définis dans `tokens.css` (complété
ici d'une famille `--shadow-*` manquante), **additives** à côté des fichiers
`shell/src/ui/*` existants qui restent intouchés, aboutissant à une page de
galerie interne réservée aux administrateurs qui sert de référence visuelle à
SP-30 pour le basculement des surfaces brutes.

**Tech Stack:** React 19, Radix UI Primitives (18 paquets, versions figées
ci-dessous), lucide-react 1.37.0, Tailwind v4 `@theme inline`,
class-variance-authority + tailwind-merge (`cn()`, déjà présents), Vitest +
Testing Library + `user-event` (déjà présents).

## Contexte et décisions de périmètre

Le découpage de la spec (`docs/superpowers/specs/2026-08-29-refonte-ui-triptyque-design.md`
§9) scinde en exécution l'ancien "SP-29" en SP-29a (clos le 2026-08-30 —
permissions, tokens de couleur, i18n) et SP-29b (ce plan) : le reste du §10.3,
le kit de primitives lui-même, plus les critères de sortie §10.5 que SP-29a a
explicitement laissés ouverts (le kit et sa galerie).

**Décision de périmètre non négociable — ne pas toucher aux fichiers `ui/*`
existants.** `shell/src/ui/{button,card,input,dialog,ConfirmDialog}.tsx`
existent déjà, stylés en classes Tailwind `slate-*` codées en dur (pas de
tokens), et sont déjà câblés sur de vrais écrans (`ConfirmDialog` est utilisé
par le flux de suppression d'`ItemActions`). Les restyler maintenant
changerait des écrans réels avant SP-30 et violerait le critère de sortie
§10.5.4 de la spec (« aucune capture d'écran des seize pages existantes ne
diffère ») — un héritage direct de la contrainte « rien n'a changé à l'écran »
de SP-29a, que SP-29b doit honorer aussi, précisément parce que la spec
assigne explicitement « leur remplacement effectif » à SP-30, pas à SP-29
(§10.3). Le nouveau kit vit **à côté**, dans un nouveau dossier
`shell/src/ui/kit/`, un fichier par primitive (PascalCase, ex. `Button.tsx`,
`Checkbox.tsx`), chacun avec son `ComponentName.test.tsx` frère, tous
réexportés depuis un barrel `shell/src/ui/kit/index.ts` complété tâche après
tâche. SP-30 basculera les points d'appel réels sur `ui/kit/*` et retirera les
anciens fichiers `ui/*` — hors périmètre ici.

**Ne pas confondre** les nouveaux `Tabs`/`Drawer`/`Menu` du kit avec les
fichiers préexistants et sans rapport `shell/src/builder/widgets/{tabs,drawer,ExplorerMenu}.tsx`
— ce sont des composants du runtime de widgets d'app (`AppRenderer`,
`kind="tabs"` etc., consommés par les apps utilisateur), explicitement hors
périmètre par la spec §12 (« Refonte de `AppRenderer` et des 41 widgets
(A9) »). Le nommage sous `ui/kit/` évite toute collision de nom ; il n'y a
rien à fusionner entre les deux systèmes.

**Décision bibliothèque d'icônes (spec §10.3, « à arbitrer au plan selon le
poids mesuré »).** Retenu : **`lucide-react`**, nouvelle dépendance runtime,
pour les petites icônes d'interaction du kit (chevrons, coche, croix,
loupe…), importées par nom ESM (`import { ChevronDown } from "lucide-react"`)
— pas de registre central, pas de `dangerouslySetInnerHTML`. Mesuré réellement
le 2026-08-30 : build de production de référence, chunk principal =
3 033 490 octets bruts / 844,27 kB gzip ; avec `lucide-react@1.37.0` installé
et 5 icônes réellement importées et rendues sur une route réelle
(`ChevronDown, ChevronRight, X, Check, Search`), chunk principal =
3 035 500 octets bruts / 845,10 kB gzip — **delta : +2 010 octets bruts /
+0,83 kB gzip pour 5 icônes** (~400 octets/icône brut), sans commune mesure
avec le delta de `@radix-ui/react-select` seul mesuré au spike de SP-29a
(+84 937 octets bruts). Le tree-shaking fonctionne, le coût par icône est
négligeable. Ce choix unifie le vocabulaire d'icônes du kit avec le catalogue
Lucide curaté de SP-27, comme suggéré par la spec — **mais le mécanisme reste
volontairement différent** : le pipeline `lucide-static` + SVG générées de
SP-27 (`app/mapicons/`, `lucideIconSvgs.generated.ts`) rend des icônes de
carte téléversées par le tenant sur un canvas (deck.gl), une cible de rendu
totalement différente du DOM du chrome studio — ce pipeline n'est pas touché,
hors périmètre.

## Global Constraints

- Ne jamais modifier `shell/src/ui/button.tsx`, `card.tsx`, `input.tsx`,
  `dialog.tsx`, `ConfirmDialog.tsx` — additif uniquement, sous `ui/kit/`.
- Aucune classe Tailwind de palette codée en dur
  (`/\b(?:bg|text|border|ring|fill|stroke)-(?:slate|gray|zinc|neutral|stone|red|blue|green|yellow|amber|lime|emerald|indigo|violet|purple|fuchsia|pink|rose|sky|cyan|orange|teal)-\d{2,3}\b/`)
  dans aucun fichier de `ui/kit/` — uniquement les tokens `--gs-*` via les
  classes `bg-surface`, `text-ink`, `border-rule`, `bg-accent`, `bg-danger`,
  etc. Vérifié mécaniquement par `expectTokenizedClasses()` (Task 2) dans
  chaque fichier de test du kit.
- Versions figées exactes (vérifiées `npm view` le 2026-08-30, toutes MIT ou
  ISC, toutes `peerDependencies.react` couvrant `^19.0.0`) :
  `@radix-ui/react-select@2.3.7`, `@radix-ui/react-popover@1.1.23`,
  `@radix-ui/react-tabs@1.1.21`, `@radix-ui/react-checkbox@1.3.11`,
  `@radix-ui/react-radio-group@1.4.7`, `@radix-ui/react-switch@1.3.7`,
  `@radix-ui/react-slider@1.4.7`, `@radix-ui/react-toggle-group@1.1.19`,
  `@radix-ui/react-dropdown-menu@2.1.24`, `@radix-ui/react-tooltip@1.2.16`,
  `@radix-ui/react-toast@1.2.23`, `@radix-ui/react-avatar@1.2.6`,
  `@radix-ui/react-progress@1.1.16`, `@radix-ui/react-dialog@1.1.23`,
  `@radix-ui/react-collapsible@1.1.20`,
  `@radix-ui/react-visually-hidden@1.2.11`, `@radix-ui/react-toolbar@1.1.19`,
  `lucide-react@1.37.0`.
- Seuils de couverture non régressifs : 85 côté cœur (non concerné par ce
  plan), 88 côté shell — mesuré **après** nettoyage de `dist/` et
  `dist-export/` (piège documenté 4 fois).
- `npm run e2e` doit rester vert **et non modifié** — aucune des 113 specs
  E2E existantes ne doit changer.
- Toute chaîne visible à l'utilisateur passe par `t()` +
  `shell/src/i18n/catalog.fr.ts` — jamais de chaîne française codée en dur
  dans un composant neuf.

---

### Task 1: Compléter le contrat de tokens — élévation (`--shadow-*`)

**Files:**
- Modify: `shell/src/styles/tokens.css`
- Modify: `shell/src/styles/tokens.test.ts`

**Interfaces:**
- Consumes: rien (fondation).
- Produces: classes Tailwind `shadow-sm`, `shadow-md`, `shadow-lg` résolues via
  `var(--gs-shadow-sm|md|lg)`, consommées par `Panel` (Task 17), `Popover`
  (Task 20), `Menu` (Task 21), `Tooltip` (Task 22), `Dialog`/`ConfirmDialog`
  (Task 23), `Drawer` (Task 24).

Le contrat de tokens §5.1 de la spec liste `--color-*`, `--font-*`, `--text-*`,
`--radius-*`, `--space-*`, `--shadow-*`. SP-29a n'a livré que `--color-*`,
`--font-*`, `--radius-*` (zéro occurrence de "shadow" dans son plan). `--text-*`
et `--space-*` n'ont besoin d'aucun token maison : les valeurs par défaut de
Tailwind v4 installées (`node_modules/tailwindcss/theme.css` : `--spacing:
0.25rem`, `--text-{xs..9xl}` + `--text-*--line-height` associé) suffisent déjà
à tout consommateur actuel ou prévu, et ni l'un ni l'autre n'est configurable
par tenant (§5.4 : seuls accent et rayon le sont) — laissés tels quels, YAGNI.
Seul `--shadow-*` manque réellement et est nécessaire (élévation des
recouvrements Popover/Menu/Tooltip/Drawer/Dialog), et doit varier par ambiance
comme tout autre token (§5.2).

- [ ] **Step 1: Ajouter les tokens d'ombre dans les trois blocs d'ambiance**

Dans `shell/src/styles/tokens.css`, ajouter à la fin du bloc `:root { ... }`
(juste avant l'accolade fermante, après le bloc "Carte") :

```css
  /* Élévation — Task 1 SP-29b */
  --gs-shadow-sm: 0 1px 2px rgba(14, 26, 32, 0.08);
  --gs-shadow-md: 0 4px 12px rgba(14, 26, 32, 0.12);
  --gs-shadow-lg: 0 12px 32px rgba(14, 26, 32, 0.18);
```

Dans le bloc `@media (prefers-color-scheme: dark) { :root:not([data-theme="light"]) { ... } }`,
juste avant son accolade fermante :

```css
    --gs-shadow-sm: 0 1px 2px rgba(0, 0, 0, 0.4);
    --gs-shadow-md: 0 4px 12px rgba(0, 0, 0, 0.5);
    --gs-shadow-lg: 0 12px 32px rgba(0, 0, 0, 0.6);
```

Dans le bloc `:root[data-theme="dark"] { ... }`, juste avant son accolade
fermante, les mêmes trois lignes (valeurs identiques au bloc sombre système
ci-dessus) :

```css
  --gs-shadow-sm: 0 1px 2px rgba(0, 0, 0, 0.4);
  --gs-shadow-md: 0 4px 12px rgba(0, 0, 0, 0.5);
  --gs-shadow-lg: 0 12px 32px rgba(0, 0, 0, 0.6);
```

- [ ] **Step 2: Exposer les tokens à Tailwind**

Dans le bloc `@theme inline { ... }`, ajouter après les trois lignes
`--radius-*` :

```css

  --shadow-sm: var(--gs-shadow-sm);
  --shadow-md: var(--gs-shadow-md);
  --shadow-lg: var(--gs-shadow-lg);
```

`--shadow-*` prend directement une valeur `box-shadow` complète — vérifié
contre le `theme.css` réel de `tailwindcss@4.3.3` installé
(`node_modules/tailwindcss/theme.css:406-408`, ex.
`--shadow-sm: 0 1px 3px 0 rgb(0 0 0 / 0.1), 0 1px 2px -1px rgb(0 0 0 / 0.1);`)
— même forme que ci-dessus, ce n'est pas une supposition.

- [ ] **Step 3: Étendre le test de contrat**

Dans `shell/src/styles/tokens.test.ts`, ajouter un test après celui qui
vérifie les tokens de carte (« expose les tokens de carte, qui ne peuvent pas
être dérivés ») :

```ts
  it("expose les tokens d'élévation", () => {
    for (const name of ["shadow-sm", "shadow-md", "shadow-lg"]) {
      expect(LIGHT.has(name), `token d'élévation absent : --gs-${name}`).toBe(true);
    }
  });
```

Les tests génériques déjà présents (`tokensOf`/`block`) couvrent
automatiquement la parité des nouveaux tokens entre les trois blocs et
l'absence de couleur codée en dur hors bloc (les `rgba(...)` ne sont pas des
hexadécimaux, le test existant `not.toMatch(/#[0-9a-fA-F]{3,8}\b/)` passe sans
modification).

- [ ] **Step 4: Lancer les tests**

Run: `cd shell && npm run test -- src/styles/tokens.test.ts`
Expected: PASS, 6 tests (5 existants + 1 nouveau).

- [ ] **Step 5: Build de contrôle**

Run: `cd shell && npm run build`
Expected: succès, aucune régression (les tokens ajoutés ne sont consommés par
rien encore).

- [ ] **Step 6: Commit**

```bash
cd shell
git add src/styles/tokens.css src/styles/tokens.test.ts
git commit -m "feat(shell): tokens d'élévation --shadow-* dans les deux ambiances"
```

### Task 2: Dépendances Radix/lucide-react + scaffolding du kit

**Files:**
- Modify: `shell/package.json`, `shell/package-lock.json` (via `npm install`)
- Create: `shell/src/ui/kit/index.ts`
- Create: `shell/src/ui/kit/testUtils.ts`
- Create: `shell/src/ui/kit/testUtils.test.ts`

**Interfaces:**
- Consumes: rien.
- Produces: `expectTokenizedClasses(container: HTMLElement): void`, importée
  par tous les fichiers de test des Tasks 3 à 30 (`import { expectTokenizedClasses } from "../testUtils"`).
  Barrel `shell/src/ui/kit/index.ts` que chaque tâche suivante complète avec
  une ligne `export { X } from "./X";`.

- [ ] **Step 1: Installer les 18 paquets, versions figées**

Run:
```bash
cd shell
npm install \
  @radix-ui/react-select@2.3.7 \
  @radix-ui/react-popover@1.1.23 \
  @radix-ui/react-tabs@1.1.21 \
  @radix-ui/react-checkbox@1.3.11 \
  @radix-ui/react-radio-group@1.4.7 \
  @radix-ui/react-switch@1.3.7 \
  @radix-ui/react-slider@1.4.7 \
  @radix-ui/react-toggle-group@1.1.19 \
  @radix-ui/react-dropdown-menu@2.1.24 \
  @radix-ui/react-tooltip@1.2.16 \
  @radix-ui/react-toast@1.2.23 \
  @radix-ui/react-avatar@1.2.6 \
  @radix-ui/react-progress@1.1.16 \
  @radix-ui/react-dialog@1.1.23 \
  @radix-ui/react-collapsible@1.1.20 \
  @radix-ui/react-visually-hidden@1.2.11 \
  @radix-ui/react-toolbar@1.1.19 \
  lucide-react@1.37.0
```
Expected: `package.json`/`package-lock.json` modifiés, aucune erreur de
résolution de peer dependency (React 19 est couvert par les 18 paquets,
vérifié `npm view ... peerDependencies.react` le 2026-08-30).

- [ ] **Step 2: Vérifier les versions réellement installées**

Run: `cd shell && node -e "for (const p of ['@radix-ui/react-select','@radix-ui/react-checkbox','lucide-react']) console.log(p, require(p+'/package.json').version)"`
Expected: `@radix-ui/react-select 2.3.7`, `@radix-ui/react-checkbox 1.3.11`,
`lucide-react 1.37.0` (si une version diffère, corriger avant de continuer —
le pin exact est une contrainte, pas une suggestion).

- [ ] **Step 3: Créer le dossier et le barrel initial**

Créer `shell/src/ui/kit/index.ts` :

```ts
// SPDX-License-Identifier: Apache-2.0
// Barrel du kit de primitives SP-29b. Chaque tâche du plan
// 2026-08-30-sp29b-kit-primitives.md ajoute sa ligne d'export ici.
// Ne pas réexporter shell/src/ui/{button,card,input,dialog,ConfirmDialog}.tsx
// (existants, intouchés) : ce sont deux systèmes distincts tant que SP-30
// n'a pas basculé les points d'appel.

export { Gate } from "../../auth/Gate";
```

- [ ] **Step 4: Créer le helper de test partagé**

Créer `shell/src/ui/kit/testUtils.ts` :

```ts
// SPDX-License-Identifier: Apache-2.0
const HARDCODED_COLOR_CLASS =
  /\b(?:bg|text|border|ring|fill|stroke)-(?:slate|gray|zinc|neutral|stone|red|blue|green|yellow|amber|lime|emerald|indigo|violet|purple|fuchsia|pink|rose|sky|cyan|orange|teal)-\d{2,3}\b/;

/**
 * Toute classe Tailwind de palette codée en dur (au lieu d'un token --gs-*)
 * casse l'ambiance sombre : cette assertion sert de proxy "testé dans les
 * deux ambiances" (jsdom ne peut pas rasteriser un rendu réel).
 */
export function expectTokenizedClasses(container: HTMLElement): void {
  if (HARDCODED_COLOR_CLASS.test(container.innerHTML)) {
    throw new Error(
      "classe Tailwind de palette codée en dur détectée — utiliser un token --gs-* (bg-surface, text-ink, border-rule, bg-accent, …) à la place",
    );
  }
}
```

- [ ] **Step 5: Test du helper lui-même**

Créer `shell/src/ui/kit/testUtils.test.ts` :

```ts
// SPDX-License-Identifier: Apache-2.0
import { expect, test } from "vitest";
import { expectTokenizedClasses } from "./testUtils";

test("ne lève rien pour des classes tokenisées", () => {
  const div = document.createElement("div");
  div.innerHTML = '<button class="bg-surface text-ink border-rule">ok</button>';
  expect(() => expectTokenizedClasses(div)).not.toThrow();
});

test("lève pour une classe de palette codée en dur", () => {
  const div = document.createElement("div");
  div.innerHTML = '<button class="bg-slate-900 text-white">non</button>';
  expect(() => expectTokenizedClasses(div)).toThrow(/codée en dur/);
});
```

- [ ] **Step 6: Lancer les tests**

Run: `cd shell && npm run test -- src/ui/kit/testUtils.test.ts`
Expected: PASS, 2 tests.

- [ ] **Step 7: Commit**

```bash
cd shell
git add package.json package-lock.json src/ui/kit/index.ts src/ui/kit/testUtils.ts src/ui/kit/testUtils.test.ts
git commit -m "feat(shell): dépendances Radix/lucide-react + scaffolding du kit de primitives"
```

### Task 3: Button, IconButton

**Files:**
- Create: `shell/src/ui/kit/Button.tsx`
- Create: `shell/src/ui/kit/Button.test.tsx`
- Create: `shell/src/ui/kit/IconButton.tsx`
- Create: `shell/src/ui/kit/IconButton.test.tsx`
- Modify: `shell/src/ui/kit/index.ts`

**Interfaces:**
- Consumes: `cn` from `shell/src/lib/utils.ts` (déjà existant).
- Produces: `Button` (`variant?: "default"|"outline"|"ghost"|"danger"`,
  `size?: "default"|"sm"|"icon"`, `ButtonProps` type), `IconButton`
  (`icon: React.ReactNode`, `"aria-label": string` **requis**,
  `size?: "default"|"sm"`) — consommés par `IconButton` lui-même (Button),
  `NumberField` (Task 11, boutons +/-), `Splitter` n'en a pas besoin,
  `ConfirmDialog`/`Drawer` (Tasks 23-24, bouton de fermeture).

- [ ] **Step 1: Test de Button**

Créer `shell/src/ui/kit/Button.test.tsx` :

```tsx
// SPDX-License-Identifier: Apache-2.0
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, test, vi } from "vitest";
import { Button } from "./Button";
import { expectTokenizedClasses } from "./testUtils";

test("rend un bouton cliquable", async () => {
  const onClick = vi.fn();
  const { container } = render(<Button onClick={onClick}>Valider</Button>);
  await userEvent.click(screen.getByRole("button", { name: "Valider" }));
  expect(onClick).toHaveBeenCalledTimes(1);
  expectTokenizedClasses(container);
});

test("respecte disabled", async () => {
  const onClick = vi.fn();
  render(
    <Button disabled onClick={onClick}>
      Valider
    </Button>,
  );
  await userEvent.click(screen.getByRole("button", { name: "Valider" }));
  expect(onClick).not.toHaveBeenCalled();
});

test("variant danger applique la classe bg-danger", () => {
  render(<Button variant="danger">Supprimer</Button>);
  expect(screen.getByRole("button", { name: "Supprimer" })).toHaveClass("bg-danger");
});

test("size icon est carrée", () => {
  render(<Button size="icon">×</Button>);
  expect(screen.getByRole("button")).toHaveClass("w-9", "h-9");
});
```

- [ ] **Step 2: Vérifier l'échec**

Run: `cd shell && npm run test -- src/ui/kit/Button.test.tsx`
Expected: FAIL — `Cannot find module './Button'`

- [ ] **Step 3: Implémenter Button**

Créer `shell/src/ui/kit/Button.tsx` :

```tsx
// SPDX-License-Identifier: Apache-2.0
import { cva, type VariantProps } from "class-variance-authority";
import { cn } from "../../lib/utils";

const buttonVariants = cva(
  "inline-flex items-center justify-center gap-2 rounded-md text-sm font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent focus-visible:ring-offset-2 disabled:pointer-events-none disabled:opacity-50",
  {
    variants: {
      variant: {
        default: "bg-accent text-surface hover:bg-accent-ink",
        outline: "border border-rule bg-surface text-ink hover:bg-sunken",
        ghost: "text-ink hover:bg-sunken",
        danger: "bg-danger text-surface hover:opacity-90",
      },
      size: {
        default: "h-9 px-4 py-2",
        sm: "h-8 px-3 text-xs",
        icon: "h-9 w-9",
      },
    },
    defaultVariants: { variant: "default", size: "default" },
  },
);

export type ButtonProps = React.ButtonHTMLAttributes<HTMLButtonElement> &
  VariantProps<typeof buttonVariants>;

export function Button({ className, variant, size, ...props }: ButtonProps) {
  return <button className={cn(buttonVariants({ variant, size }), className)} {...props} />;
}
```

- [ ] **Step 4: Vérifier le succès**

Run: `cd shell && npm run test -- src/ui/kit/Button.test.tsx`
Expected: PASS, 4 tests.

- [ ] **Step 5: Test d'IconButton**

Créer `shell/src/ui/kit/IconButton.test.tsx` :

```tsx
// SPDX-License-Identifier: Apache-2.0
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { X } from "lucide-react";
import { expect, test, vi } from "vitest";
import { IconButton } from "./IconButton";
import { expectTokenizedClasses } from "./testUtils";

test("expose un accessible name via aria-label, pas de texte visible", async () => {
  const onClick = vi.fn();
  const { container } = render(<IconButton icon={<X />} aria-label="Fermer" onClick={onClick} />);
  const button = screen.getByRole("button", { name: "Fermer" });
  await userEvent.click(button);
  expect(onClick).toHaveBeenCalledTimes(1);
  expectTokenizedClasses(container);
});
```

- [ ] **Step 6: Vérifier l'échec puis implémenter**

Run: `cd shell && npm run test -- src/ui/kit/IconButton.test.tsx` → FAIL.

Créer `shell/src/ui/kit/IconButton.tsx` :

```tsx
// SPDX-License-Identifier: Apache-2.0
import { Button, type ButtonProps } from "./Button";

export type IconButtonProps = Omit<ButtonProps, "size" | "children"> & {
  icon: React.ReactNode;
  "aria-label": string;
  size?: "default" | "sm";
};

export function IconButton({ icon, size = "default", ...props }: IconButtonProps) {
  return (
    <Button size={size === "sm" ? "sm" : "icon"} {...props}>
      {icon}
    </Button>
  );
}
```

- [ ] **Step 7: Vérifier le succès**

Run: `cd shell && npm run test -- src/ui/kit/IconButton.test.tsx`
Expected: PASS, 1 test.

- [ ] **Step 8: Compléter le barrel**

Dans `shell/src/ui/kit/index.ts`, ajouter (avant la ligne `Gate`, ordre
alphabétique non requis, juste après le commentaire d'en-tête) :

```ts
export { Button, type ButtonProps } from "./Button";
export { IconButton, type IconButtonProps } from "./IconButton";
```

- [ ] **Step 9: Commit**

```bash
cd shell
git add src/ui/kit/Button.tsx src/ui/kit/Button.test.tsx src/ui/kit/IconButton.tsx src/ui/kit/IconButton.test.tsx src/ui/kit/index.ts
git commit -m "feat(shell): kit — Button, IconButton"
```

### Task 4: Field, Input, Textarea

**Files:**
- Create: `shell/src/ui/kit/Field.tsx`, `Field.test.tsx`
- Create: `shell/src/ui/kit/Input.tsx`, `Input.test.tsx`
- Create: `shell/src/ui/kit/Textarea.tsx`, `Textarea.test.tsx`
- Modify: `shell/src/ui/kit/index.ts`

**Interfaces:**
- Produces: `Input` (`React.InputHTMLAttributes<HTMLInputElement>`),
  `Textarea` (`React.TextareaHTMLAttributes<HTMLTextAreaElement>`), `Field`
  (`label: string; htmlFor: string; error?: string; hint?: string; children:
  React.ReactNode`) — `Input`/`Textarea` consommés par `ColorField` (Task 10),
  `NumberField` (Task 11), `Combobox` (Task 13). `Field` consommé par la
  galerie (Task 30) pour chaque contrôle de formulaire.

- [ ] **Step 1: Test d'Input**

Créer `shell/src/ui/kit/Input.test.tsx` :

```tsx
// SPDX-License-Identifier: Apache-2.0
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, test } from "vitest";
import { Input } from "./Input";
import { expectTokenizedClasses } from "./testUtils";

test("saisie contrôlée", async () => {
  const { container } = render(<Input aria-label="Titre" defaultValue="" />);
  const input = screen.getByRole("textbox", { name: "Titre" });
  await userEvent.type(input, "abc");
  expect(input).toHaveValue("abc");
  expectTokenizedClasses(container);
});

test("disabled empêche la saisie", async () => {
  render(<Input aria-label="Titre" disabled defaultValue="" />);
  const input = screen.getByRole("textbox", { name: "Titre" });
  expect(input).toBeDisabled();
});
```

- [ ] **Step 2: Implémenter Input**

Créer `shell/src/ui/kit/Input.tsx` :

```tsx
// SPDX-License-Identifier: Apache-2.0
import { cn } from "../../lib/utils";

export function Input({
  className,
  ...props
}: React.InputHTMLAttributes<HTMLInputElement>) {
  return (
    <input
      className={cn(
        "h-9 w-full rounded-md border border-rule bg-surface px-3 text-sm text-ink placeholder:text-ink-3 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent disabled:cursor-not-allowed disabled:opacity-50",
        className,
      )}
      {...props}
    />
  );
}
```

- [ ] **Step 3: Lancer, vérifier PASS (2 tests)**

Run: `cd shell && npm run test -- src/ui/kit/Input.test.tsx`

- [ ] **Step 4: Test de Textarea**

Créer `shell/src/ui/kit/Textarea.test.tsx` :

```tsx
// SPDX-License-Identifier: Apache-2.0
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, test } from "vitest";
import { Textarea } from "./Textarea";
import { expectTokenizedClasses } from "./testUtils";

test("saisie multiligne contrôlée", async () => {
  const { container } = render(<Textarea aria-label="Description" defaultValue="" />);
  const textarea = screen.getByRole("textbox", { name: "Description" });
  await userEvent.type(textarea, "ligne 1{enter}ligne 2");
  expect(textarea).toHaveValue("ligne 1\nligne 2");
  expectTokenizedClasses(container);
});
```

- [ ] **Step 5: Implémenter Textarea**

Créer `shell/src/ui/kit/Textarea.tsx` :

```tsx
// SPDX-License-Identifier: Apache-2.0
import { cn } from "../../lib/utils";

export function Textarea({
  className,
  ...props
}: React.TextareaHTMLAttributes<HTMLTextAreaElement>) {
  return (
    <textarea
      className={cn(
        "min-h-20 w-full rounded-md border border-rule bg-surface px-3 py-2 text-sm text-ink placeholder:text-ink-3 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent disabled:cursor-not-allowed disabled:opacity-50",
        className,
      )}
      {...props}
    />
  );
}
```

- [ ] **Step 6: Lancer, vérifier PASS**

Run: `cd shell && npm run test -- src/ui/kit/Textarea.test.tsx`

- [ ] **Step 7: Test de Field**

Créer `shell/src/ui/kit/Field.test.tsx` :

```tsx
// SPDX-License-Identifier: Apache-2.0
import { render, screen } from "@testing-library/react";
import { expect, test } from "vitest";
import { Field } from "./Field";
import { Input } from "./Input";
import { expectTokenizedClasses } from "./testUtils";

test("associe le label au contrôle via htmlFor/id", () => {
  const { container } = render(
    <Field label="Titre" htmlFor="titre">
      <Input id="titre" />
    </Field>,
  );
  expect(screen.getByLabelText("Titre")).toBeInTheDocument();
  expectTokenizedClasses(container);
});

test("affiche l'erreur avec role=alert quand fournie", () => {
  render(
    <Field label="Titre" htmlFor="titre" error="Champ requis">
      <Input id="titre" />
    </Field>,
  );
  expect(screen.getByRole("alert")).toHaveTextContent("Champ requis");
});

test("affiche l'indice quand fourni et pas d'erreur", () => {
  render(
    <Field label="Titre" htmlFor="titre" hint="Visible dans le catalogue">
      <Input id="titre" />
    </Field>,
  );
  expect(screen.getByText("Visible dans le catalogue")).toBeInTheDocument();
  expect(screen.queryByRole("alert")).not.toBeInTheDocument();
});
```

- [ ] **Step 8: Implémenter Field**

Créer `shell/src/ui/kit/Field.tsx` :

```tsx
// SPDX-License-Identifier: Apache-2.0
export function Field({
  label,
  htmlFor,
  error,
  hint,
  children,
}: {
  label: string;
  htmlFor: string;
  error?: string;
  hint?: string;
  children: React.ReactNode;
}) {
  return (
    <div className="flex flex-col gap-1">
      <label htmlFor={htmlFor} className="text-sm font-medium text-ink">
        {label}
      </label>
      {children}
      {error ? (
        <p role="alert" className="text-xs text-danger">
          {error}
        </p>
      ) : hint ? (
        <p className="text-xs text-ink-3">{hint}</p>
      ) : null}
    </div>
  );
}
```

- [ ] **Step 9: Lancer tous les tests de la tâche**

Run: `cd shell && npm run test -- src/ui/kit/Field.test.tsx src/ui/kit/Input.test.tsx src/ui/kit/Textarea.test.tsx`
Expected: PASS, 7 tests.

- [ ] **Step 10: Compléter le barrel**

```ts
export { Field } from "./Field";
export { Input } from "./Input";
export { Textarea } from "./Textarea";
```

- [ ] **Step 11: Commit**

```bash
cd shell
git add src/ui/kit/Field.tsx src/ui/kit/Field.test.tsx src/ui/kit/Input.tsx src/ui/kit/Input.test.tsx src/ui/kit/Textarea.tsx src/ui/kit/Textarea.test.tsx src/ui/kit/index.ts
git commit -m "feat(shell): kit — Field, Input, Textarea"
```

### Task 5: Checkbox (`@radix-ui/react-checkbox`) — gabarit des primitives Radix suivantes

**Files:**
- Create: `shell/src/ui/kit/Checkbox.tsx`, `Checkbox.test.tsx`
- Modify: `shell/src/ui/kit/index.ts`

**Interfaces:**
- Consumes: `cn`, `expectTokenizedClasses`.
- Produces: `Checkbox` (`checked?: boolean; onCheckedChange?: (checked:
  boolean) => void; disabled?: boolean; "aria-label"?: string`) — consommé par
  `DataTable` (Task 16, sélection de ligne).

Cette tâche sert de **gabarit visible** à toutes les tâches suivantes qui
enveloppent un primitive Radix (Radio, Switch, Slider, Segmented, Select,
Tabs, Popover, Menu, Tooltip, Dialog, Drawer, Avatar, Progress, Toast,
Toolbar) : passthrough contrôlé (`checked`/`onCheckedChange`), passthrough
`disabled`, icône d'indicateur `lucide-react`, classes tokenisées, test réel
au clic **et** au clavier (Espace), `expectTokenizedClasses`. Reproduire
exactement cette forme dans les tâches suivantes, pas une variante.

- [ ] **Step 1: Écrire le test**

Créer `shell/src/ui/kit/Checkbox.test.tsx` :

```tsx
// SPDX-License-Identifier: Apache-2.0
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, test, vi } from "vitest";
import { Checkbox } from "./Checkbox";
import { expectTokenizedClasses } from "./testUtils";

test("clic bascule l'état et appelle onCheckedChange", async () => {
  const onCheckedChange = vi.fn();
  const { container } = render(
    <Checkbox aria-label="Sélectionner" checked={false} onCheckedChange={onCheckedChange} />,
  );
  const box = screen.getByRole("checkbox", { name: "Sélectionner" });
  expect(box).toHaveAttribute("aria-checked", "false");
  await userEvent.click(box);
  expect(onCheckedChange).toHaveBeenCalledWith(true);
  expectTokenizedClasses(container);
});

test("la barre espace bascule l'état au clavier", async () => {
  const onCheckedChange = vi.fn();
  render(<Checkbox aria-label="Sélectionner" checked={false} onCheckedChange={onCheckedChange} />);
  const box = screen.getByRole("checkbox", { name: "Sélectionner" });
  box.focus();
  await userEvent.keyboard(" ");
  expect(onCheckedChange).toHaveBeenCalledWith(true);
});

test("checked=true affiche l'indicateur", () => {
  render(<Checkbox aria-label="Sélectionner" checked onCheckedChange={() => {}} />);
  expect(screen.getByRole("checkbox", { name: "Sélectionner" })).toHaveAttribute(
    "aria-checked",
    "true",
  );
});

test("disabled empêche le changement", async () => {
  const onCheckedChange = vi.fn();
  render(
    <Checkbox aria-label="Sélectionner" checked={false} disabled onCheckedChange={onCheckedChange} />,
  );
  const box = screen.getByRole("checkbox", { name: "Sélectionner" });
  expect(box).toBeDisabled();
  await userEvent.click(box);
  expect(onCheckedChange).not.toHaveBeenCalled();
});
```

- [ ] **Step 2: Vérifier l'échec**

Run: `cd shell && npm run test -- src/ui/kit/Checkbox.test.tsx` → FAIL, module
introuvable.

- [ ] **Step 3: Implémenter**

Créer `shell/src/ui/kit/Checkbox.tsx` :

```tsx
// SPDX-License-Identifier: Apache-2.0
import * as CheckboxPrimitive from "@radix-ui/react-checkbox";
import { Check } from "lucide-react";
import { cn } from "../../lib/utils";

export function Checkbox({
  className,
  checked,
  onCheckedChange,
  disabled,
  ...props
}: {
  className?: string;
  checked?: boolean;
  onCheckedChange?: (checked: boolean) => void;
  disabled?: boolean;
} & Omit<React.ComponentPropsWithoutRef<typeof CheckboxPrimitive.Root>, "checked" | "onCheckedChange">) {
  return (
    <CheckboxPrimitive.Root
      checked={checked}
      onCheckedChange={(state) => onCheckedChange?.(state === true)}
      disabled={disabled}
      className={cn(
        "flex h-4 w-4 items-center justify-center rounded-sm border border-rule bg-surface data-[state=checked]:border-accent data-[state=checked]:bg-accent focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent disabled:cursor-not-allowed disabled:opacity-50",
        className,
      )}
      {...props}
    >
      <CheckboxPrimitive.Indicator className="text-surface">
        <Check size={12} strokeWidth={3} />
      </CheckboxPrimitive.Indicator>
    </CheckboxPrimitive.Root>
  );
}
```

- [ ] **Step 4: Vérifier le succès**

Run: `cd shell && npm run test -- src/ui/kit/Checkbox.test.tsx`
Expected: PASS, 4 tests.

- [ ] **Step 5: Compléter le barrel, commit**

```ts
export { Checkbox } from "./Checkbox";
```

```bash
cd shell
git add src/ui/kit/Checkbox.tsx src/ui/kit/Checkbox.test.tsx src/ui/kit/index.ts
git commit -m "feat(shell): kit — Checkbox (gabarit Radix)"
```

### Task 6: Radio (`@radix-ui/react-radio-group`)

**Files:**
- Create: `shell/src/ui/kit/Radio.tsx`, `Radio.test.tsx`
- Modify: `shell/src/ui/kit/index.ts`

**Interfaces:**
- Produces: `RadioGroup` (`value: string; onValueChange: (value: string) =>
  void; disabled?: boolean; "aria-label": string; children`), `RadioItem`
  (`value: string; children: React.ReactNode`), exportés comme `Radio =
  { Group: RadioGroup, Item: RadioItem }` pour l'usage `<Radio.Group>`/
  `<Radio.Item>` demandé par la spec de cette tâche.

- [ ] **Step 1: Écrire le test**

Créer `shell/src/ui/kit/Radio.test.tsx` :

```tsx
// SPDX-License-Identifier: Apache-2.0
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, test, vi } from "vitest";
import { Radio } from "./Radio";
import { expectTokenizedClasses } from "./testUtils";

test("sélectionne une option au clic et notifie onValueChange", async () => {
  const onValueChange = vi.fn();
  const { container } = render(
    <Radio.Group aria-label="Rôle" value="lecteur" onValueChange={onValueChange}>
      <Radio.Item value="lecteur">Lecteur</Radio.Item>
      <Radio.Item value="editeur">Éditeur</Radio.Item>
    </Radio.Group>,
  );
  await userEvent.click(screen.getByRole("radio", { name: "Éditeur" }));
  expect(onValueChange).toHaveBeenCalledWith("editeur");
  expectTokenizedClasses(container);
});

test("la navigation clavier flèche bas déplace la sélection", async () => {
  const onValueChange = vi.fn();
  render(
    <Radio.Group aria-label="Rôle" value="lecteur" onValueChange={onValueChange}>
      <Radio.Item value="lecteur">Lecteur</Radio.Item>
      <Radio.Item value="editeur">Éditeur</Radio.Item>
    </Radio.Group>,
  );
  screen.getByRole("radio", { name: "Lecteur" }).focus();
  await userEvent.keyboard("{ArrowDown}");
  expect(onValueChange).toHaveBeenCalledWith("editeur");
});

test("disabled empêche la sélection", async () => {
  const onValueChange = vi.fn();
  render(
    <Radio.Group aria-label="Rôle" value="lecteur" onValueChange={onValueChange} disabled>
      <Radio.Item value="lecteur">Lecteur</Radio.Item>
      <Radio.Item value="editeur">Éditeur</Radio.Item>
    </Radio.Group>,
  );
  await userEvent.click(screen.getByRole("radio", { name: "Éditeur" }));
  expect(onValueChange).not.toHaveBeenCalled();
});
```

- [ ] **Step 2: Vérifier l'échec, implémenter**

Run: `cd shell && npm run test -- src/ui/kit/Radio.test.tsx` → FAIL.

Créer `shell/src/ui/kit/Radio.tsx` :

```tsx
// SPDX-License-Identifier: Apache-2.0
import * as RadioGroupPrimitive from "@radix-ui/react-radio-group";
import { cn } from "../../lib/utils";

function RadioGroup({
  className,
  ...props
}: React.ComponentPropsWithoutRef<typeof RadioGroupPrimitive.Root>) {
  return (
    <RadioGroupPrimitive.Root className={cn("flex flex-col gap-2", className)} {...props} />
  );
}

function RadioItem({
  value,
  children,
}: {
  value: string;
  children: React.ReactNode;
}) {
  const id = `radio-${value}`;
  return (
    <div className="flex items-center gap-2">
      <RadioGroupPrimitive.Item
        id={id}
        value={value}
        aria-label={typeof children === "string" ? children : undefined}
        className="flex h-4 w-4 items-center justify-center rounded-full border border-rule bg-surface data-[state=checked]:border-accent focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent disabled:cursor-not-allowed disabled:opacity-50"
      >
        <RadioGroupPrimitive.Indicator className="block h-2 w-2 rounded-full bg-accent" />
      </RadioGroupPrimitive.Item>
      <label htmlFor={id} className="text-sm text-ink">
        {children}
      </label>
    </div>
  );
}

export const Radio = { Group: RadioGroup, Item: RadioItem };
```

- [ ] **Step 3: Vérifier le succès**

Run: `cd shell && npm run test -- src/ui/kit/Radio.test.tsx`
Expected: PASS, 3 tests.

Note : `aria-label` sur `RadioGroupPrimitive.Item` couplé au `<label
htmlFor>` externe donne un nom accessible identique aux deux (le label
externe est nécessaire pour la zone cliquable, `aria-label` sur l'item pour
que `getByRole("radio", { name })` matche même si le label n'est pas un
`<label>` associé par défaut par Radix) — les deux tests ci-dessus le
confirment déjà, aucune étape supplémentaire n'est nécessaire.

- [ ] **Step 4: Compléter le barrel, commit**

```ts
export { Radio } from "./Radio";
```

```bash
cd shell
git add src/ui/kit/Radio.tsx src/ui/kit/Radio.test.tsx src/ui/kit/index.ts
git commit -m "feat(shell): kit — Radio"
```

### Task 7: Switch (`@radix-ui/react-switch`)

**Files:**
- Create: `shell/src/ui/kit/Switch.tsx`, `Switch.test.tsx`
- Modify: `shell/src/ui/kit/index.ts`

**Interfaces:**
- Produces: `Switch` (`checked?: boolean; onCheckedChange?: (checked:
  boolean) => void; disabled?: boolean; "aria-label"?: string`).

- [ ] **Step 1: Écrire le test**

Créer `shell/src/ui/kit/Switch.test.tsx` :

```tsx
// SPDX-License-Identifier: Apache-2.0
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, test, vi } from "vitest";
import { Switch } from "./Switch";
import { expectTokenizedClasses } from "./testUtils";

test("clic bascule l'état", async () => {
  const onCheckedChange = vi.fn();
  const { container } = render(
    <Switch aria-label="Activer" checked={false} onCheckedChange={onCheckedChange} />,
  );
  const toggle = screen.getByRole("switch", { name: "Activer" });
  expect(toggle).toHaveAttribute("aria-checked", "false");
  await userEvent.click(toggle);
  expect(onCheckedChange).toHaveBeenCalledWith(true);
  expectTokenizedClasses(container);
});

test("barre espace bascule au clavier", async () => {
  const onCheckedChange = vi.fn();
  render(<Switch aria-label="Activer" checked={false} onCheckedChange={onCheckedChange} />);
  screen.getByRole("switch", { name: "Activer" }).focus();
  await userEvent.keyboard(" ");
  expect(onCheckedChange).toHaveBeenCalledWith(true);
});

test("disabled empêche le changement", async () => {
  const onCheckedChange = vi.fn();
  render(<Switch aria-label="Activer" checked={false} disabled onCheckedChange={onCheckedChange} />);
  expect(screen.getByRole("switch", { name: "Activer" })).toBeDisabled();
});
```

- [ ] **Step 2: Vérifier l'échec, implémenter**

Créer `shell/src/ui/kit/Switch.tsx` :

```tsx
// SPDX-License-Identifier: Apache-2.0
import * as SwitchPrimitive from "@radix-ui/react-switch";
import { cn } from "../../lib/utils";

export function Switch({
  className,
  checked,
  onCheckedChange,
  disabled,
  ...props
}: {
  className?: string;
  checked?: boolean;
  onCheckedChange?: (checked: boolean) => void;
  disabled?: boolean;
} & Omit<React.ComponentPropsWithoutRef<typeof SwitchPrimitive.Root>, "checked" | "onCheckedChange">) {
  return (
    <SwitchPrimitive.Root
      checked={checked}
      onCheckedChange={onCheckedChange}
      disabled={disabled}
      className={cn(
        "relative h-5 w-9 rounded-full bg-sunken data-[state=checked]:bg-accent focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent disabled:cursor-not-allowed disabled:opacity-50",
        className,
      )}
      {...props}
    >
      <SwitchPrimitive.Thumb className="block h-4 w-4 translate-x-0.5 rounded-full bg-surface transition-transform data-[state=checked]:translate-x-[18px]" />
    </SwitchPrimitive.Root>
  );
}
```

- [ ] **Step 3: Vérifier le succès**

Run: `cd shell && npm run test -- src/ui/kit/Switch.test.tsx`
Expected: PASS, 3 tests.

- [ ] **Step 4: Compléter le barrel, commit**

```ts
export { Switch } from "./Switch";
```

```bash
cd shell
git add src/ui/kit/Switch.tsx src/ui/kit/Switch.test.tsx src/ui/kit/index.ts
git commit -m "feat(shell): kit — Switch"
```

### Task 8: Slider (`@radix-ui/react-slider`)

**Files:**
- Create: `shell/src/ui/kit/Slider.tsx`, `Slider.test.tsx`
- Modify: `shell/src/ui/kit/index.ts`

**Interfaces:**
- Produces: `Slider` (`value: number[]; onValueChange: (value: number[]) =>
  void; min?: number; max?: number; step?: number; disabled?: boolean;
  "aria-label"?: string`).

- [ ] **Step 1: Écrire le test**

Créer `shell/src/ui/kit/Slider.test.tsx` :

```tsx
// SPDX-License-Identifier: Apache-2.0
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, test, vi } from "vitest";
import { Slider } from "./Slider";
import { expectTokenizedClasses } from "./testUtils";

test("flèche droite augmente la valeur d'un pas", async () => {
  const onValueChange = vi.fn();
  const { container } = render(
    <Slider aria-label="Opacité" value={[50]} min={0} max={100} step={10} onValueChange={onValueChange} />,
  );
  const thumb = screen.getByRole("slider", { name: "Opacité" });
  expect(thumb).toHaveAttribute("aria-valuenow", "50");
  thumb.focus();
  await userEvent.keyboard("{ArrowRight}");
  expect(onValueChange).toHaveBeenCalledWith([60]);
  expectTokenizedClasses(container);
});

test("disabled empêche le déplacement", async () => {
  const onValueChange = vi.fn();
  render(
    <Slider aria-label="Opacité" value={[50]} min={0} max={100} step={10} disabled onValueChange={onValueChange} />,
  );
  const thumb = screen.getByRole("slider", { name: "Opacité" });
  thumb.focus();
  await userEvent.keyboard("{ArrowRight}");
  expect(onValueChange).not.toHaveBeenCalled();
});
```

- [ ] **Step 2: Vérifier l'échec, implémenter**

Créer `shell/src/ui/kit/Slider.tsx` :

```tsx
// SPDX-License-Identifier: Apache-2.0
import * as SliderPrimitive from "@radix-ui/react-slider";
import { cn } from "../../lib/utils";

export function Slider({
  className,
  value,
  onValueChange,
  min = 0,
  max = 100,
  step = 1,
  disabled,
  ...props
}: {
  className?: string;
  value: number[];
  onValueChange: (value: number[]) => void;
  min?: number;
  max?: number;
  step?: number;
  disabled?: boolean;
} & Omit<
  React.ComponentPropsWithoutRef<typeof SliderPrimitive.Root>,
  "value" | "onValueChange" | "min" | "max" | "step"
>) {
  return (
    <SliderPrimitive.Root
      className={cn("relative flex h-5 w-full touch-none items-center", className)}
      value={value}
      onValueChange={onValueChange}
      min={min}
      max={max}
      step={step}
      disabled={disabled}
      {...props}
    >
      <SliderPrimitive.Track className="relative h-1 grow rounded-full bg-sunken">
        <SliderPrimitive.Range className="absolute h-full rounded-full bg-accent" />
      </SliderPrimitive.Track>
      <SliderPrimitive.Thumb className="block h-4 w-4 rounded-full border border-accent bg-surface focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent disabled:cursor-not-allowed disabled:opacity-50" />
    </SliderPrimitive.Root>
  );
}
```

- [ ] **Step 3: Vérifier le succès, compléter le barrel, commit**

Run: `cd shell && npm run test -- src/ui/kit/Slider.test.tsx`
Expected: PASS, 2 tests.

```ts
export { Slider } from "./Slider";
```

```bash
cd shell
git add src/ui/kit/Slider.tsx src/ui/kit/Slider.test.tsx src/ui/kit/index.ts
git commit -m "feat(shell): kit — Slider"
```

### Task 9: Segmented (`@radix-ui/react-toggle-group`, type="single")

**Files:**
- Create: `shell/src/ui/kit/Segmented.tsx`, `Segmented.test.tsx`
- Modify: `shell/src/ui/kit/index.ts`

**Interfaces:**
- Produces: `Segmented` (`value: string; onValueChange: (value: string) =>
  void; options: { value: string; label: string }[]; "aria-label": string`).

- [ ] **Step 1: Écrire le test**

Créer `shell/src/ui/kit/Segmented.test.tsx` :

```tsx
// SPDX-License-Identifier: Apache-2.0
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, test, vi } from "vitest";
import { Segmented } from "./Segmented";
import { expectTokenizedClasses } from "./testUtils";

const OPTIONS = [
  { value: "quantile", label: "Quantile" },
  { value: "jenks", label: "Jenks" },
];

test("clic sélectionne une option exclusive", async () => {
  const onValueChange = vi.fn();
  const { container } = render(
    <Segmented aria-label="Méthode" value="quantile" onValueChange={onValueChange} options={OPTIONS} />,
  );
  await userEvent.click(screen.getByRole("radio", { name: "Jenks" }));
  expect(onValueChange).toHaveBeenCalledWith("jenks");
  expectTokenizedClasses(container);
});

test("l'option active porte aria-checked=true", () => {
  render(
    <Segmented aria-label="Méthode" value="quantile" onValueChange={() => {}} options={OPTIONS} />,
  );
  expect(screen.getByRole("radio", { name: "Quantile" })).toHaveAttribute("aria-checked", "true");
  expect(screen.getByRole("radio", { name: "Jenks" })).toHaveAttribute("aria-checked", "false");
});
```

- [ ] **Step 2: Vérifier l'échec, implémenter**

`@radix-ui/react-toggle-group` en mode `type="single"` expose chaque item
avec `role="radio"` dans un groupe (vérifié dans
`node_modules/@radix-ui/react-toggle-group/dist/index.d.mts` : le composant
délègue à `RovingFocusGroup` avec le rôle radiogroup pour `type="single"`,
comportement Radix documenté et cohérent avec le rôle déjà utilisé par
`Radio`, Task 6).

Créer `shell/src/ui/kit/Segmented.tsx` :

```tsx
// SPDX-License-Identifier: Apache-2.0
import * as ToggleGroupPrimitive from "@radix-ui/react-toggle-group";
import { cn } from "../../lib/utils";

export function Segmented({
  className,
  value,
  onValueChange,
  options,
  ...props
}: {
  className?: string;
  value: string;
  onValueChange: (value: string) => void;
  options: { value: string; label: string }[];
} & Omit<
  React.ComponentPropsWithoutRef<typeof ToggleGroupPrimitive.Root>,
  "type" | "value" | "onValueChange"
>) {
  return (
    <ToggleGroupPrimitive.Root
      type="single"
      value={value}
      onValueChange={(next) => {
        if (next) onValueChange(next);
      }}
      className={cn("inline-flex rounded-md border border-rule bg-surface p-0.5", className)}
      {...props}
    >
      {options.map((option) => (
        <ToggleGroupPrimitive.Item
          key={option.value}
          value={option.value}
          className="rounded-sm px-3 py-1 text-sm text-ink data-[state=on]:bg-accent data-[state=on]:text-surface focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent"
        >
          {option.label}
        </ToggleGroupPrimitive.Item>
      ))}
    </ToggleGroupPrimitive.Root>
  );
}
```

- [ ] **Step 3: Vérifier le succès**

Run: `cd shell && npm run test -- src/ui/kit/Segmented.test.tsx`
Expected: PASS, 2 tests. Si le rôle réel diffère de `"radio"` (à confirmer à
l'exécution contre la version installée, pas seulement contre les types),
ajuster le test — piège n°3, vérifier contre la sortie réelle du test, pas
contre cette note.

- [ ] **Step 4: Compléter le barrel, commit**

```ts
export { Segmented } from "./Segmented";
```

```bash
cd shell
git add src/ui/kit/Segmented.tsx src/ui/kit/Segmented.test.tsx src/ui/kit/index.ts
git commit -m "feat(shell): kit — Segmented"
```

### Task 10: ColorField (composant maison, pas de primitive Radix)

**Files:**
- Create: `shell/src/ui/kit/ColorField.tsx`, `ColorField.test.tsx`
- Modify: `shell/src/ui/kit/index.ts`

**Interfaces:**
- Consumes: `Input` (Task 4).
- Produces: `ColorField` (`value: string; onValueChange: (value: string) =>
  void; "aria-label": string`) — `value` est un hexadécimal `#rrggbb`.

Aucune primitive Radix de couleur n'existe : composition maison d'un
`<input type="color">` (le sélecteur natif du navigateur) et d'un champ texte
hexadécimal synchronisés dans les deux sens.

- [ ] **Step 1: Écrire le test**

Créer `shell/src/ui/kit/ColorField.test.tsx` :

```tsx
// SPDX-License-Identifier: Apache-2.0
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, test, vi } from "vitest";
import { ColorField } from "./ColorField";
import { expectTokenizedClasses } from "./testUtils";

test("la saisie du champ texte notifie onValueChange avec un hex valide", async () => {
  const onValueChange = vi.fn();
  const { container } = render(
    <ColorField aria-label="Couleur d'accent" value="#0b6e77" onValueChange={onValueChange} />,
  );
  const text = screen.getByRole("textbox", { name: "Couleur d'accent" });
  await userEvent.clear(text);
  await userEvent.type(text, "#336699");
  expect(onValueChange).toHaveBeenLastCalledWith("#336699");
  expectTokenizedClasses(container);
});

test("un hex incomplet ne notifie pas onValueChange", async () => {
  const onValueChange = vi.fn();
  render(<ColorField aria-label="Couleur d'accent" value="#0b6e77" onValueChange={onValueChange} />);
  const text = screen.getByRole("textbox", { name: "Couleur d'accent" });
  await userEvent.clear(text);
  await userEvent.type(text, "#336");
  expect(onValueChange).not.toHaveBeenCalled();
});

test("le sélecteur natif porte la même valeur", () => {
  render(<ColorField aria-label="Couleur d'accent" value="#0b6e77" onValueChange={() => {}} />);
  const swatch = screen.getByLabelText("Couleur d'accent (sélecteur)");
  expect(swatch).toHaveValue("#0b6e77");
});
```

- [ ] **Step 2: Vérifier l'échec, implémenter**

Créer `shell/src/ui/kit/ColorField.tsx` :

```tsx
// SPDX-License-Identifier: Apache-2.0
import { useState } from "react";
import { Input } from "./Input";

const HEX_COLOR = /^#[0-9a-fA-F]{6}$/;

export function ColorField({
  value,
  onValueChange,
  "aria-label": ariaLabel,
}: {
  value: string;
  onValueChange: (value: string) => void;
  "aria-label": string;
}) {
  const [text, setText] = useState(value);

  return (
    <div className="flex items-center gap-2">
      <input
        type="color"
        aria-label={`${ariaLabel} (sélecteur)`}
        value={value}
        onChange={(e) => {
          setText(e.target.value);
          onValueChange(e.target.value);
        }}
        className="h-9 w-9 cursor-pointer rounded-md border border-rule bg-surface p-0.5"
      />
      <Input
        aria-label={ariaLabel}
        value={text}
        onChange={(e) => {
          setText(e.target.value);
          if (HEX_COLOR.test(e.target.value)) {
            onValueChange(e.target.value);
          }
        }}
        className="w-28 font-mono"
      />
    </div>
  );
}
```

- [ ] **Step 3: Vérifier le succès**

Run: `cd shell && npm run test -- src/ui/kit/ColorField.test.tsx`
Expected: PASS, 3 tests.

- [ ] **Step 4: Compléter le barrel, commit**

```ts
export { ColorField } from "./ColorField";
```

```bash
cd shell
git add src/ui/kit/ColorField.tsx src/ui/kit/ColorField.test.tsx src/ui/kit/index.ts
git commit -m "feat(shell): kit — ColorField"
```

### Task 11: NumberField (composant maison, pas de primitive Radix)

**Files:**
- Create: `shell/src/ui/kit/NumberField.tsx`, `NumberField.test.tsx`
- Modify: `shell/src/ui/kit/index.ts`

**Interfaces:**
- Consumes: `Input` (Task 4), `IconButton` (Task 3).
- Produces: `NumberField` (`value: number; onValueChange: (value: number) =>
  void; min?: number; max?: number; step?: number; "aria-label": string`).

- [ ] **Step 1: Écrire le test**

Créer `shell/src/ui/kit/NumberField.test.tsx` :

```tsx
// SPDX-License-Identifier: Apache-2.0
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, test, vi } from "vitest";
import { NumberField } from "./NumberField";
import { expectTokenizedClasses } from "./testUtils";

test("le bouton + incrémente d'un pas", async () => {
  const onValueChange = vi.fn();
  const { container } = render(
    <NumberField aria-label="Zoom" value={5} step={1} onValueChange={onValueChange} />,
  );
  await userEvent.click(screen.getByRole("button", { name: "Augmenter" }));
  expect(onValueChange).toHaveBeenCalledWith(6);
  expectTokenizedClasses(container);
});

test("le bouton - décrémente d'un pas et respecte min", async () => {
  const onValueChange = vi.fn();
  render(<NumberField aria-label="Zoom" value={0} min={0} step={1} onValueChange={onValueChange} />);
  await userEvent.click(screen.getByRole("button", { name: "Diminuer" }));
  expect(onValueChange).not.toHaveBeenCalled();
});

test("la saisie directe d'un nombre valide notifie onValueChange", async () => {
  const onValueChange = vi.fn();
  render(<NumberField aria-label="Zoom" value={5} onValueChange={onValueChange} />);
  const input = screen.getByRole("spinbutton", { name: "Zoom" });
  await userEvent.clear(input);
  await userEvent.type(input, "12");
  expect(onValueChange).toHaveBeenLastCalledWith(12);
});
```

- [ ] **Step 2: Vérifier l'échec, implémenter**

Ajouter les deux libellés au catalogue `shell/src/i18n/catalog.fr.ts` (à la
fin, avant l'accolade fermante `} as const;` — ou `};` selon la forme exacte
du fichier, vérifier avant d'insérer) :

```ts
  "kit.numberField.increase": "Augmenter",
  "kit.numberField.decrease": "Diminuer",
```

Créer `shell/src/ui/kit/NumberField.tsx` :

```tsx
// SPDX-License-Identifier: Apache-2.0
import { Minus, Plus } from "lucide-react";
import { t } from "../../i18n";
import { IconButton } from "./IconButton";
import { Input } from "./Input";

export function NumberField({
  value,
  onValueChange,
  min,
  max,
  step = 1,
  "aria-label": ariaLabel,
}: {
  value: number;
  onValueChange: (value: number) => void;
  min?: number;
  max?: number;
  step?: number;
  "aria-label": string;
}) {
  const clamp = (n: number) => {
    let clamped = n;
    if (min !== undefined) clamped = Math.max(min, clamped);
    if (max !== undefined) clamped = Math.min(max, clamped);
    return clamped;
  };

  return (
    <div className="flex items-center gap-1">
      <IconButton
        icon={<Minus size={14} />}
        aria-label={t("kit.numberField.decrease")}
        size="sm"
        disabled={min !== undefined && value <= min}
        onClick={() => {
          const next = clamp(value - step);
          if (next !== value) onValueChange(next);
        }}
      />
      <Input
        type="number"
        aria-label={ariaLabel}
        value={value}
        min={min}
        max={max}
        step={step}
        onChange={(e) => {
          const parsed = Number(e.target.value);
          if (!Number.isNaN(parsed)) onValueChange(clamp(parsed));
        }}
        className="w-20 text-center"
      />
      <IconButton
        icon={<Plus size={14} />}
        aria-label={t("kit.numberField.increase")}
        size="sm"
        disabled={max !== undefined && value >= max}
        onClick={() => {
          const next = clamp(value + step);
          if (next !== value) onValueChange(next);
        }}
      />
    </div>
  );
}
```

- [ ] **Step 3: Vérifier le succès**

Run: `cd shell && npm run test -- src/ui/kit/NumberField.test.tsx`
Expected: PASS, 3 tests.

- [ ] **Step 4: Compléter le barrel, commit**

```ts
export { NumberField } from "./NumberField";
```

```bash
cd shell
git add src/ui/kit/NumberField.tsx src/ui/kit/NumberField.test.tsx src/i18n/catalog.fr.ts src/ui/kit/index.ts
git commit -m "feat(shell): kit — NumberField"
```

### Task 12: Select (`@radix-ui/react-select`)

**Files:**
- Create: `shell/src/ui/kit/Select.tsx`, `Select.test.tsx`
- Modify: `shell/src/ui/kit/index.ts`

**Interfaces:**
- Produces: `Select` (`value: string; onValueChange: (value: string) => void;
  options: { value: string; label: string }[]; placeholder?: string;
  disabled?: boolean; "aria-label": string`).

Point de départ : le squelette déjà vérifié fonctionnel par le spike de
SP-29a (`docs/superpowers/plans/2026-08-29-sp29a-spike-primitives.md`,
section « Squelettes réels de Select ») — exports `Root, Trigger, Value,
Icon, Portal, Content, Viewport, Item, ItemText, ItemIndicator` confirmés
contre le `.d.mts` réellement installé. Le contenu ouvert porte hors de
`#root` (portail sur `document.body`, confirmé par le spike) : c'est attendu,
pas un défaut.

- [ ] **Step 1: Écrire le test**

Créer `shell/src/ui/kit/Select.test.tsx` :

```tsx
// SPDX-License-Identifier: Apache-2.0
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, test, vi } from "vitest";
import { Select } from "./Select";
import { expectTokenizedClasses } from "./testUtils";

const OPTIONS = [
  { value: "a", label: "Option A" },
  { value: "b", label: "Option B" },
];

test("affiche le libellé de la valeur sélectionnée", () => {
  const { container } = render(
    <Select aria-label="Format" value="a" onValueChange={() => {}} options={OPTIONS} />,
  );
  expect(screen.getByRole("combobox", { name: "Format" })).toHaveTextContent("Option A");
  expectTokenizedClasses(container);
});

test("ouvre au clic et sélectionne une option au clic", async () => {
  const onValueChange = vi.fn();
  render(<Select aria-label="Format" value="a" onValueChange={onValueChange} options={OPTIONS} />);
  await userEvent.click(screen.getByRole("combobox", { name: "Format" }));
  await userEvent.click(await screen.findByRole("option", { name: "Option B" }));
  expect(onValueChange).toHaveBeenCalledWith("b");
});

test("disabled empêche l'ouverture", () => {
  render(
    <Select aria-label="Format" value="a" onValueChange={() => {}} options={OPTIONS} disabled />,
  );
  expect(screen.getByRole("combobox", { name: "Format" })).toBeDisabled();
});
```

- [ ] **Step 2: Vérifier l'échec, implémenter**

Créer `shell/src/ui/kit/Select.tsx` :

```tsx
// SPDX-License-Identifier: Apache-2.0
import * as SelectPrimitive from "@radix-ui/react-select";
import { Check, ChevronDown } from "lucide-react";
import { cn } from "../../lib/utils";

export function Select({
  className,
  value,
  onValueChange,
  options,
  placeholder,
  disabled,
  "aria-label": ariaLabel,
}: {
  className?: string;
  value: string;
  onValueChange: (value: string) => void;
  options: { value: string; label: string }[];
  placeholder?: string;
  disabled?: boolean;
  "aria-label": string;
}) {
  return (
    <SelectPrimitive.Root value={value} onValueChange={onValueChange} disabled={disabled}>
      <SelectPrimitive.Trigger
        aria-label={ariaLabel}
        className={cn(
          "flex h-9 w-full items-center justify-between gap-2 rounded-md border border-rule bg-surface px-3 text-sm text-ink focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent disabled:cursor-not-allowed disabled:opacity-50",
          className,
        )}
      >
        <SelectPrimitive.Value placeholder={placeholder} />
        <SelectPrimitive.Icon>
          <ChevronDown size={16} />
        </SelectPrimitive.Icon>
      </SelectPrimitive.Trigger>
      <SelectPrimitive.Portal>
        <SelectPrimitive.Content className="overflow-hidden rounded-md border border-rule bg-raised shadow-md">
          <SelectPrimitive.Viewport className="p-1">
            {options.map((option) => (
              <SelectPrimitive.Item
                key={option.value}
                value={option.value}
                className="flex cursor-pointer items-center justify-between gap-2 rounded-sm px-2 py-1.5 text-sm text-ink data-[highlighted]:bg-sunken data-[highlighted]:outline-none"
              >
                <SelectPrimitive.ItemText>{option.label}</SelectPrimitive.ItemText>
                <SelectPrimitive.ItemIndicator>
                  <Check size={14} />
                </SelectPrimitive.ItemIndicator>
              </SelectPrimitive.Item>
            ))}
          </SelectPrimitive.Viewport>
        </SelectPrimitive.Content>
      </SelectPrimitive.Portal>
    </SelectPrimitive.Root>
  );
}
```

- [ ] **Step 3: Vérifier le succès**

Run: `cd shell && npm run test -- src/ui/kit/Select.test.tsx`
Expected: PASS, 3 tests.

- [ ] **Step 4: Compléter le barrel, commit**

```ts
export { Select } from "./Select";
```

```bash
cd shell
git add src/ui/kit/Select.tsx src/ui/kit/Select.test.tsx src/ui/kit/index.ts
git commit -m "feat(shell): kit — Select"
```

### Task 13: Combobox (composé Popover + listbox maison — Radix n'a pas de Combobox)

**Files:**
- Create: `shell/src/ui/kit/Combobox.tsx`, `Combobox.test.tsx`
- Modify: `shell/src/ui/kit/index.ts`

**Interfaces:**
- Consumes: `@radix-ui/react-popover` (déjà une dépendance, Task 2), `Input`
  (Task 4).
- Produces: `Combobox` (`value: string; onValueChange: (value: string) =>
  void; options: { value: string; label: string }[]; "aria-label": string`).

**Il n'existe pas de `@radix-ui/react-combobox`** — ne pas chercher à
l'installer. Ce composant compose `Popover` (déjà disponible) avec un champ
texte filtrant et un motif ARIA `listbox`/`option` construit à la main, avec
une vraie navigation clavier (flèches, Entrée, Échap) — pas de simulation.
C'est le fichier de test le plus poussé des contrôles de formulaire de ce
plan.

- [ ] **Step 1: Écrire le test**

Créer `shell/src/ui/kit/Combobox.test.tsx` :

```tsx
// SPDX-License-Identifier: Apache-2.0
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, test, vi } from "vitest";
import { Combobox } from "./Combobox";
import { expectTokenizedClasses } from "./testUtils";

const OPTIONS = [
  { value: "a", label: "Alpha" },
  { value: "b", label: "Beta" },
  { value: "c", label: "Gamma" },
];

test("filtre les options en tapant, affiche uniquement les correspondances", async () => {
  const onValueChange = vi.fn();
  const { container } = render(
    <Combobox aria-label="Collection" value="" onValueChange={onValueChange} options={OPTIONS} />,
  );
  const input = screen.getByRole("combobox", { name: "Collection" });
  await userEvent.click(input);
  await userEvent.type(input, "ga");
  expect(screen.getByRole("option", { name: "Gamma" })).toBeInTheDocument();
  expect(screen.queryByRole("option", { name: "Alpha" })).not.toBeInTheDocument();
  expectTokenizedClasses(container);
});

test("flèche bas puis Entrée sélectionne l'option surlignée", async () => {
  const onValueChange = vi.fn();
  render(<Combobox aria-label="Collection" value="" onValueChange={onValueChange} options={OPTIONS} />);
  const input = screen.getByRole("combobox", { name: "Collection" });
  await userEvent.click(input);
  await userEvent.keyboard("{ArrowDown}{Enter}");
  expect(onValueChange).toHaveBeenCalledWith("a");
});

test("Échap ferme la liste sans sélectionner", async () => {
  const onValueChange = vi.fn();
  render(<Combobox aria-label="Collection" value="" onValueChange={onValueChange} options={OPTIONS} />);
  const input = screen.getByRole("combobox", { name: "Collection" });
  await userEvent.click(input);
  expect(screen.getByRole("listbox")).toBeInTheDocument();
  await userEvent.keyboard("{Escape}");
  expect(screen.queryByRole("listbox")).not.toBeInTheDocument();
  expect(onValueChange).not.toHaveBeenCalled();
});
```

- [ ] **Step 2: Vérifier l'échec, implémenter**

Créer `shell/src/ui/kit/Combobox.tsx` :

```tsx
// SPDX-License-Identifier: Apache-2.0
import * as PopoverPrimitive from "@radix-ui/react-popover";
import { useMemo, useState } from "react";
import { cn } from "../../lib/utils";
import { Input } from "./Input";

export function Combobox({
  value,
  onValueChange,
  options,
  "aria-label": ariaLabel,
}: {
  value: string;
  onValueChange: (value: string) => void;
  options: { value: string; label: string }[];
  "aria-label": string;
}) {
  const selectedLabel = options.find((o) => o.value === value)?.label ?? "";
  const [query, setQuery] = useState(selectedLabel);
  const [open, setOpen] = useState(false);
  const [activeIndex, setActiveIndex] = useState(0);

  const filtered = useMemo(
    () => options.filter((o) => o.label.toLowerCase().includes(query.toLowerCase())),
    [options, query],
  );

  const commit = (option: { value: string; label: string }) => {
    onValueChange(option.value);
    setQuery(option.label);
    setOpen(false);
  };

  return (
    <PopoverPrimitive.Root open={open} onOpenChange={setOpen}>
      <PopoverPrimitive.Anchor asChild>
        <Input
          role="combobox"
          aria-label={ariaLabel}
          aria-expanded={open}
          aria-controls="combobox-listbox"
          value={query}
          onChange={(e) => {
            setQuery(e.target.value);
            setActiveIndex(0);
            setOpen(true);
          }}
          onFocus={() => setOpen(true)}
          onKeyDown={(e) => {
            if (e.key === "ArrowDown") {
              e.preventDefault();
              setOpen(true);
              setActiveIndex((i) => Math.min(i + 1, filtered.length - 1));
            } else if (e.key === "ArrowUp") {
              e.preventDefault();
              setActiveIndex((i) => Math.max(i - 1, 0));
            } else if (e.key === "Enter") {
              e.preventDefault();
              if (open && filtered[activeIndex]) commit(filtered[activeIndex]);
            } else if (e.key === "Escape") {
              setOpen(false);
            }
          }}
        />
      </PopoverPrimitive.Anchor>
      <PopoverPrimitive.Portal>
        <PopoverPrimitive.Content
          id="combobox-listbox"
          role="listbox"
          onOpenAutoFocus={(e) => e.preventDefault()}
          className="w-[var(--radix-popover-trigger-width)] rounded-md border border-rule bg-raised p-1 shadow-md"
        >
          {filtered.length === 0 ? (
            <p className="px-2 py-1.5 text-sm text-ink-3">Aucun résultat</p>
          ) : (
            filtered.map((option, index) => (
              <div
                key={option.value}
                role="option"
                aria-selected={index === activeIndex}
                onMouseDown={(e) => {
                  e.preventDefault();
                  commit(option);
                }}
                className={cn(
                  "cursor-pointer rounded-sm px-2 py-1.5 text-sm text-ink",
                  index === activeIndex && "bg-sunken",
                )}
              >
                {option.label}
              </div>
            ))
          )}
        </PopoverPrimitive.Content>
      </PopoverPrimitive.Portal>
    </PopoverPrimitive.Root>
  );
}
```

- [ ] **Step 3: Vérifier le succès**

Run: `cd shell && npm run test -- src/ui/kit/Combobox.test.tsx`
Expected: PASS, 3 tests. `PopoverPrimitive.Anchor asChild` avec `Input` (qui
rend un simple `<input>`) doit transmettre correctement `ref`/props — si le
test échoue sur ce point précis, vérifier que `Input` n'enveloppe pas
l'élément dans un fragment ou un wrapper supplémentaire (ce n'est pas le cas
dans l'implémentation de Task 4, mais à re-vérifier contre le fichier réel si
ce test échoue).

- [ ] **Step 4: Compléter le barrel, commit**

```ts
export { Combobox } from "./Combobox";
```

```bash
cd shell
git add src/ui/kit/Combobox.tsx src/ui/kit/Combobox.test.tsx src/ui/kit/index.ts
git commit -m "feat(shell): kit — Combobox (composé, pas de primitive Radix dédiée)"
```

### Task 14: Tabs (`@radix-ui/react-tabs`)

**Files:**
- Create: `shell/src/ui/kit/Tabs.tsx`, `Tabs.test.tsx`
- Modify: `shell/src/ui/kit/index.ts`

**Interfaces:**
- Produces: `Tabs` (`defaultValue: string; tabs: { value: string; label:
  string; content: React.ReactNode }[]; "aria-label"?: string`).

Point de départ : squelette déjà vérifié par le spike de SP-29a. Rappel du
spike : `TabsContent` **ne porte pas** son contenu dans un portail (pas de
`Portal` dans ses exports) — reste dans le flux DOM normal, contrairement à
`Select`/`Popover`.

- [ ] **Step 1: Écrire le test**

Créer `shell/src/ui/kit/Tabs.test.tsx` :

```tsx
// SPDX-License-Identifier: Apache-2.0
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, test } from "vitest";
import { Tabs } from "./Tabs";
import { expectTokenizedClasses } from "./testUtils";

const TABS = [
  { value: "info", label: "Informations", content: <p>Contenu info</p> },
  { value: "perms", label: "Permissions", content: <p>Contenu permissions</p> },
];

test("affiche le contenu de l'onglet par défaut", () => {
  const { container } = render(<Tabs defaultValue="info" tabs={TABS} />);
  expect(screen.getByText("Contenu info")).toBeInTheDocument();
  expect(screen.queryByText("Contenu permissions")).not.toBeInTheDocument();
  expectTokenizedClasses(container);
});

test("clic sur un onglet change le contenu affiché", async () => {
  render(<Tabs defaultValue="info" tabs={TABS} />);
  await userEvent.click(screen.getByRole("tab", { name: "Permissions" }));
  expect(screen.getByText("Contenu permissions")).toBeInTheDocument();
  expect(screen.queryByText("Contenu info")).not.toBeInTheDocument();
});

test("flèche droite déplace le focus vers l'onglet suivant", async () => {
  render(<Tabs defaultValue="info" tabs={TABS} />);
  screen.getByRole("tab", { name: "Informations" }).focus();
  await userEvent.keyboard("{ArrowRight}");
  expect(screen.getByRole("tab", { name: "Permissions" })).toHaveFocus();
});
```

- [ ] **Step 2: Vérifier l'échec, implémenter**

Créer `shell/src/ui/kit/Tabs.tsx` :

```tsx
// SPDX-License-Identifier: Apache-2.0
import * as TabsPrimitive from "@radix-ui/react-tabs";
import { cn } from "../../lib/utils";

export function Tabs({
  className,
  defaultValue,
  tabs,
  "aria-label": ariaLabel,
}: {
  className?: string;
  defaultValue: string;
  tabs: { value: string; label: string; content: React.ReactNode }[];
  "aria-label"?: string;
}) {
  return (
    <TabsPrimitive.Root defaultValue={defaultValue} className={cn("flex flex-col gap-2", className)}>
      <TabsPrimitive.List aria-label={ariaLabel} className="flex gap-1 border-b border-rule">
        {tabs.map((tab) => (
          <TabsPrimitive.Trigger
            key={tab.value}
            value={tab.value}
            className="border-b-2 border-transparent px-3 py-2 text-sm text-ink data-[state=active]:border-accent data-[state=active]:text-accent focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent"
          >
            {tab.label}
          </TabsPrimitive.Trigger>
        ))}
      </TabsPrimitive.List>
      {tabs.map((tab) => (
        <TabsPrimitive.Content key={tab.value} value={tab.value}>
          {tab.content}
        </TabsPrimitive.Content>
      ))}
    </TabsPrimitive.Root>
  );
}
```

- [ ] **Step 3: Vérifier le succès**

Run: `cd shell && npm run test -- src/ui/kit/Tabs.test.tsx`
Expected: PASS, 3 tests.

- [ ] **Step 4: Compléter le barrel, commit**

```ts
export { Tabs } from "./Tabs";
```

```bash
cd shell
git add src/ui/kit/Tabs.tsx src/ui/kit/Tabs.test.tsx src/ui/kit/index.ts
git commit -m "feat(shell): kit — Tabs"
```

### Task 15: Tree (composé de `@radix-ui/react-collapsible` par nœud — pas de Tree Radix)

**Files:**
- Create: `shell/src/ui/kit/Tree.tsx`, `Tree.test.tsx`
- Modify: `shell/src/ui/kit/index.ts`

**Interfaces:**
- Produces: `Tree` (`nodes: TreeNode[]; onSelect?: (id: string) => void;
  selectedId?: string`), type exporté `TreeNode = { id: string; label:
  string; children?: TreeNode[] }`.

Il n'existe pas de primitive Radix « Tree » — composition récursive de
`@radix-ui/react-collapsible` par nœud pour l'affichage/repli.

- [ ] **Step 1: Écrire le test**

Créer `shell/src/ui/kit/Tree.test.tsx` :

```tsx
// SPDX-License-Identifier: Apache-2.0
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, test, vi } from "vitest";
import { Tree, type TreeNode } from "./Tree";
import { expectTokenizedClasses } from "./testUtils";

const NODES: TreeNode[] = [
  {
    id: "carte",
    label: "Cartes",
    children: [{ id: "carte-1", label: "Carte topo" }],
  },
  { id: "app", label: "Apps" },
];

test("les enfants sont repliés par défaut", () => {
  const { container } = render(<Tree nodes={NODES} />);
  expect(screen.queryByText("Carte topo")).not.toBeInTheDocument();
  expectTokenizedClasses(container);
});

test("clic sur un nœud parent déplie ses enfants", async () => {
  render(<Tree nodes={NODES} />);
  await userEvent.click(screen.getByRole("button", { name: "Cartes" }));
  expect(screen.getByText("Carte topo")).toBeInTheDocument();
});

test("clic sur une feuille appelle onSelect avec son id", async () => {
  const onSelect = vi.fn();
  render(<Tree nodes={NODES} onSelect={onSelect} />);
  await userEvent.click(screen.getByText("Apps"));
  expect(onSelect).toHaveBeenCalledWith("app");
});
```

- [ ] **Step 2: Vérifier l'échec, implémenter**

Créer `shell/src/ui/kit/Tree.tsx` :

```tsx
// SPDX-License-Identifier: Apache-2.0
import * as CollapsiblePrimitive from "@radix-ui/react-collapsible";
import { ChevronRight } from "lucide-react";
import { cn } from "../../lib/utils";

export type TreeNode = {
  id: string;
  label: string;
  children?: TreeNode[];
};

function TreeNodeRow({
  node,
  depth,
  selectedId,
  onSelect,
}: {
  node: TreeNode;
  depth: number;
  selectedId?: string;
  onSelect?: (id: string) => void;
}) {
  const hasChildren = (node.children?.length ?? 0) > 0;
  const paddingLeft = depth * 16;

  if (!hasChildren) {
    return (
      <button
        type="button"
        onClick={() => onSelect?.(node.id)}
        style={{ paddingLeft: paddingLeft + 20 }}
        className={cn(
          "flex w-full items-center rounded-sm py-1 text-left text-sm text-ink hover:bg-sunken",
          selectedId === node.id && "bg-accent-soft text-accent-ink",
        )}
      >
        {node.label}
      </button>
    );
  }

  return (
    <CollapsiblePrimitive.Root>
      <CollapsiblePrimitive.Trigger
        style={{ paddingLeft }}
        className="flex w-full items-center gap-1 rounded-sm py-1 text-left text-sm font-medium text-ink hover:bg-sunken [&[data-state=open]>svg]:rotate-90"
      >
        <ChevronRight size={14} className="transition-transform" />
        {node.label}
      </CollapsiblePrimitive.Trigger>
      <CollapsiblePrimitive.Content>
        {node.children!.map((child) => (
          <TreeNodeRow
            key={child.id}
            node={child}
            depth={depth + 1}
            selectedId={selectedId}
            onSelect={onSelect}
          />
        ))}
      </CollapsiblePrimitive.Content>
    </CollapsiblePrimitive.Root>
  );
}

export function Tree({
  nodes,
  selectedId,
  onSelect,
}: {
  nodes: TreeNode[];
  selectedId?: string;
  onSelect?: (id: string) => void;
}) {
  return (
    <div role="tree" className="flex flex-col">
      {nodes.map((node) => (
        <TreeNodeRow key={node.id} node={node} depth={0} selectedId={selectedId} onSelect={onSelect} />
      ))}
    </div>
  );
}
```

- [ ] **Step 3: Vérifier le succès**

Run: `cd shell && npm run test -- src/ui/kit/Tree.test.tsx`
Expected: PASS, 3 tests.

- [ ] **Step 4: Compléter le barrel, commit**

```ts
export { Tree, type TreeNode } from "./Tree";
```

```bash
cd shell
git add src/ui/kit/Tree.tsx src/ui/kit/Tree.test.tsx src/ui/kit/index.ts
git commit -m "feat(shell): kit — Tree"
```

### Task 16: Table, DataTable (maison, native `<table>` — pas de nouvelle dépendance)

**Files:**
- Create: `shell/src/ui/kit/Table.tsx`, `Table.test.tsx`
- Create: `shell/src/ui/kit/DataTable.tsx`, `DataTable.test.tsx`
- Modify: `shell/src/ui/kit/index.ts`

**Interfaces:**
- Consumes: `Checkbox` (Task 5).
- Produces: `Table` (`columns: string[]; children: React.ReactNode` — wrapper
  bas niveau, `<thead>`/`<tbody>` fournis par l'appelant via des sous-parties
  `Table.Head`, `Table.Row`, `Table.Cell` exportées en propriétés statiques),
  `DataTable<T>` (`columns: { key: string; label: string; render: (row: T) =>
  React.ReactNode }[]; rows: T[]; getRowId: (row: T) => string;
  selectedIds?: Set<string>; onSelectedIdsChange?: (ids: Set<string>) =>
  void; sortKey?: string; sortDirection?: "asc" | "desc"; onSortChange?:
  (key: string) => void`).

- [ ] **Step 1: Écrire le test de Table**

Créer `shell/src/ui/kit/Table.test.tsx` :

```tsx
// SPDX-License-Identifier: Apache-2.0
import { render, screen } from "@testing-library/react";
import { expect, test } from "vitest";
import { Table } from "./Table";
import { expectTokenizedClasses } from "./testUtils";

test("rend un tableau accessible avec en-têtes de colonne", () => {
  const { container } = render(
    <Table>
      <Table.Head columns={["Nom", "Type"]} />
      <tbody>
        <Table.Row>
          <Table.Cell>Carte topo</Table.Cell>
          <Table.Cell>map</Table.Cell>
        </Table.Row>
      </tbody>
    </Table>,
  );
  expect(screen.getByRole("table")).toBeInTheDocument();
  expect(screen.getByRole("columnheader", { name: "Nom" })).toBeInTheDocument();
  expect(screen.getByText("Carte topo")).toBeInTheDocument();
  expectTokenizedClasses(container);
});
```

- [ ] **Step 2: Implémenter Table**

Créer `shell/src/ui/kit/Table.tsx` :

```tsx
// SPDX-License-Identifier: Apache-2.0
import { cn } from "../../lib/utils";

function TableRoot({ className, ...props }: React.TableHTMLAttributes<HTMLTableElement>) {
  return (
    <table className={cn("w-full border-collapse text-left text-sm text-ink", className)} {...props} />
  );
}

function TableHead({ columns }: { columns: string[] }) {
  return (
    <thead>
      <tr className="border-b border-rule">
        {columns.map((col) => (
          <th key={col} className="px-3 py-2 font-medium text-ink-2">
            {col}
          </th>
        ))}
      </tr>
    </thead>
  );
}

function TableRow({ className, ...props }: React.HTMLAttributes<HTMLTableRowElement>) {
  return <tr className={cn("border-b border-rule-2", className)} {...props} />;
}

function TableCell({ className, ...props }: React.TdHTMLAttributes<HTMLTableCellElement>) {
  return <td className={cn("px-3 py-2", className)} {...props} />;
}

export const Table = Object.assign(TableRoot, {
  Head: TableHead,
  Row: TableRow,
  Cell: TableCell,
});
```

- [ ] **Step 3: Lancer, vérifier PASS**

Run: `cd shell && npm run test -- src/ui/kit/Table.test.tsx`
Expected: PASS, 1 test.

- [ ] **Step 4: Écrire le test de DataTable**

Créer `shell/src/ui/kit/DataTable.test.tsx` :

```tsx
// SPDX-License-Identifier: Apache-2.0
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, test, vi } from "vitest";
import { DataTable } from "./DataTable";
import { expectTokenizedClasses } from "./testUtils";

type Row = { id: string; name: string; kind: string };

const ROWS: Row[] = [
  { id: "1", name: "Carte topo", kind: "map" },
  { id: "2", name: "App suivi", kind: "app" },
];

const COLUMNS = [
  { key: "name", label: "Nom", render: (r: Row) => r.name },
  { key: "kind", label: "Type", render: (r: Row) => r.kind },
];

test("clic sur un en-tête de colonne triable notifie onSortChange", async () => {
  const onSortChange = vi.fn();
  const { container } = render(
    <DataTable columns={COLUMNS} rows={ROWS} getRowId={(r) => r.id} onSortChange={onSortChange} />,
  );
  await userEvent.click(screen.getByRole("columnheader", { name: "Nom" }));
  expect(onSortChange).toHaveBeenCalledWith("name");
  expectTokenizedClasses(container);
});

test("cocher une ligne ajoute son id à selectedIds", async () => {
  const onSelectedIdsChange = vi.fn();
  render(
    <DataTable
      columns={COLUMNS}
      rows={ROWS}
      getRowId={(r) => r.id}
      selectedIds={new Set()}
      onSelectedIdsChange={onSelectedIdsChange}
    />,
  );
  await userEvent.click(screen.getByRole("checkbox", { name: "Sélectionner Carte topo" }));
  expect(onSelectedIdsChange).toHaveBeenCalledWith(new Set(["1"]));
});
```

- [ ] **Step 5: Implémenter DataTable**

Créer `shell/src/ui/kit/DataTable.tsx` :

```tsx
// SPDX-License-Identifier: Apache-2.0
import { Checkbox } from "./Checkbox";
import { Table } from "./Table";

export function DataTable<T>({
  columns,
  rows,
  getRowId,
  selectedIds,
  onSelectedIdsChange,
  sortKey,
  onSortChange,
}: {
  columns: { key: string; label: string; render: (row: T) => React.ReactNode }[];
  rows: T[];
  getRowId: (row: T) => string;
  selectedIds?: Set<string>;
  onSelectedIdsChange?: (ids: Set<string>) => void;
  sortKey?: string;
  sortDirection?: "asc" | "desc";
  onSortChange?: (key: string) => void;
}) {
  const selectable = selectedIds !== undefined && onSelectedIdsChange !== undefined;

  return (
    <Table>
      <thead>
        <tr className="border-b border-rule">
          {selectable && <th className="w-8 px-3 py-2" />}
          {columns.map((col) => (
            <th
              key={col.key}
              className="cursor-pointer px-3 py-2 font-medium text-ink-2"
              onClick={() => onSortChange?.(col.key)}
              aria-sort={sortKey === col.key ? "ascending" : "none"}
            >
              {col.label}
            </th>
          ))}
        </tr>
      </thead>
      <tbody>
        {rows.map((row) => {
          const id = getRowId(row);
          return (
            <Table.Row key={id}>
              {selectable && (
                <Table.Cell>
                  <Checkbox
                    aria-label={`Sélectionner ${columns[0].render(row)}`}
                    checked={selectedIds!.has(id)}
                    onCheckedChange={(checked) => {
                      const next = new Set(selectedIds);
                      if (checked) next.add(id);
                      else next.delete(id);
                      onSelectedIdsChange!(next);
                    }}
                  />
                </Table.Cell>
              )}
              {columns.map((col) => (
                <Table.Cell key={col.key}>{col.render(row)}</Table.Cell>
              ))}
            </Table.Row>
          );
        })}
      </tbody>
    </Table>
  );
}
```

- [ ] **Step 6: Vérifier le succès**

Run: `cd shell && npm run test -- src/ui/kit/DataTable.test.tsx`
Expected: PASS, 2 tests.

- [ ] **Step 7: Compléter le barrel, commit**

```ts
export { Table } from "./Table";
export { DataTable } from "./DataTable";
```

```bash
cd shell
git add src/ui/kit/Table.tsx src/ui/kit/Table.test.tsx src/ui/kit/DataTable.tsx src/ui/kit/DataTable.test.tsx src/ui/kit/index.ts
git commit -m "feat(shell): kit — Table, DataTable"
```

### Task 17: Panel, Section, Breadcrumb

**Files:**
- Create: `shell/src/ui/kit/Panel.tsx`, `Panel.test.tsx`
- Create: `shell/src/ui/kit/Section.tsx`, `Section.test.tsx`
- Create: `shell/src/ui/kit/Breadcrumb.tsx`, `Breadcrumb.test.tsx`
- Modify: `shell/src/ui/kit/index.ts`, `shell/src/i18n/catalog.fr.ts`

**Interfaces:**
- Produces: `Panel` (`children: React.ReactNode; className?: string`),
  `Section` (`title: string; children: React.ReactNode`), `Breadcrumb`
  (`items: { label: string; href?: string }[]`).

- [ ] **Step 1: Écrire les trois tests**

Créer `shell/src/ui/kit/Panel.test.tsx` :

```tsx
// SPDX-License-Identifier: Apache-2.0
import { render, screen } from "@testing-library/react";
import { expect, test } from "vitest";
import { Panel } from "./Panel";
import { expectTokenizedClasses } from "./testUtils";

test("rend son contenu avec l'ombre d'élévation md", () => {
  const { container } = render(
    <Panel>
      <p>Contenu</p>
    </Panel>,
  );
  expect(screen.getByText("Contenu")).toBeInTheDocument();
  expect(container.firstChild).toHaveClass("shadow-md");
  expectTokenizedClasses(container);
});
```

Créer `shell/src/ui/kit/Section.test.tsx` :

```tsx
// SPDX-License-Identifier: Apache-2.0
import { render, screen } from "@testing-library/react";
import { expect, test } from "vitest";
import { Section } from "./Section";
import { expectTokenizedClasses } from "./testUtils";

test("rend un titre de section et son contenu", () => {
  const { container } = render(
    <Section title="Permissions">
      <p>Détail</p>
    </Section>,
  );
  expect(screen.getByRole("heading", { name: "Permissions" })).toBeInTheDocument();
  expect(screen.getByText("Détail")).toBeInTheDocument();
  expectTokenizedClasses(container);
});
```

Créer `shell/src/ui/kit/Breadcrumb.test.tsx` :

```tsx
// SPDX-License-Identifier: Apache-2.0
import { render, screen } from "@testing-library/react";
import { expect, test } from "vitest";
import { Breadcrumb } from "./Breadcrumb";
import { expectTokenizedClasses } from "./testUtils";

test("rend une navigation avec le fil d'Ariane, dernier élément non lien", () => {
  const { container } = render(
    <Breadcrumb items={[{ label: "Catalogue", href: "/" }, { label: "Carte topo" }]} />,
  );
  expect(screen.getByRole("navigation", { name: "Fil d'Ariane" })).toBeInTheDocument();
  expect(screen.getByRole("link", { name: "Catalogue" })).toHaveAttribute("href", "/");
  expect(screen.queryByRole("link", { name: "Carte topo" })).not.toBeInTheDocument();
  expect(screen.getByText("Carte topo")).toBeInTheDocument();
  expectTokenizedClasses(container);
});
```

- [ ] **Step 2: Vérifier l'échec des trois**

Run: `cd shell && npm run test -- src/ui/kit/Panel.test.tsx src/ui/kit/Section.test.tsx src/ui/kit/Breadcrumb.test.tsx`
Expected: FAIL — modules introuvables.

- [ ] **Step 3: Ajouter la clé i18n**

Dans `shell/src/i18n/catalog.fr.ts` :

```ts
  "kit.breadcrumb.label": "Fil d'Ariane",
```

- [ ] **Step 4: Implémenter les trois**

Créer `shell/src/ui/kit/Panel.tsx` :

```tsx
// SPDX-License-Identifier: Apache-2.0
import { cn } from "../../lib/utils";

export function Panel({
  className,
  children,
}: {
  className?: string;
  children: React.ReactNode;
}) {
  return (
    <div className={cn("rounded-lg border border-rule bg-raised p-4 shadow-md", className)}>
      {children}
    </div>
  );
}
```

Créer `shell/src/ui/kit/Section.tsx` :

```tsx
// SPDX-License-Identifier: Apache-2.0
export function Section({
  title,
  children,
}: {
  title: string;
  children: React.ReactNode;
}) {
  return (
    <section className="flex flex-col gap-2">
      <h3 className="text-sm font-semibold text-ink">{title}</h3>
      {children}
    </section>
  );
}
```

Créer `shell/src/ui/kit/Breadcrumb.tsx` :

```tsx
// SPDX-License-Identifier: Apache-2.0
import { t } from "../../i18n";

export function Breadcrumb({ items }: { items: { label: string; href?: string }[] }) {
  return (
    <nav aria-label={t("kit.breadcrumb.label")}>
      <ol className="flex items-center gap-1 text-sm text-ink-3">
        {items.map((item, index) => (
          <li key={item.label} className="flex items-center gap-1">
            {index > 0 && <span aria-hidden="true">/</span>}
            {item.href ? (
              <a href={item.href} className="hover:text-accent hover:underline">
                {item.label}
              </a>
            ) : (
              <span className="text-ink">{item.label}</span>
            )}
          </li>
        ))}
      </ol>
    </nav>
  );
}
```

- [ ] **Step 5: Vérifier le succès**

Run: `cd shell && npm run test -- src/ui/kit/Panel.test.tsx src/ui/kit/Section.test.tsx src/ui/kit/Breadcrumb.test.tsx`
Expected: PASS, 3 tests.

- [ ] **Step 6: Compléter le barrel, commit**

```ts
export { Panel } from "./Panel";
export { Section } from "./Section";
export { Breadcrumb } from "./Breadcrumb";
```

```bash
cd shell
git add src/ui/kit/Panel.tsx src/ui/kit/Panel.test.tsx src/ui/kit/Section.tsx src/ui/kit/Section.test.tsx src/ui/kit/Breadcrumb.tsx src/ui/kit/Breadcrumb.test.tsx src/ui/kit/index.ts src/i18n/catalog.fr.ts
git commit -m "feat(shell): kit — Panel, Section, Breadcrumb"
```

### Task 18: Toolbar (`@radix-ui/react-toolbar`)

**Files:**
- Create: `shell/src/ui/kit/Toolbar.tsx`, `Toolbar.test.tsx`
- Modify: `shell/src/ui/kit/index.ts`

**Interfaces:**
- Produces: `Toolbar` (`children: React.ReactNode; "aria-label": string`),
  `ToolbarButton` (`children: React.ReactNode; onClick?: () => void;
  disabled?: boolean`), `ToolbarSeparator`, exportés comme `Toolbar =
  { Root, Button, Separator }`.

Exports réels vérifiés le 2026-08-30 contre le paquet installé
(`node_modules/@radix-ui/react-toolbar/dist/index.d.mts`) : `Root, Button,
Link, ToggleGroup, ToggleItem, Separator` — `Button` rend un vrai `<button>`
avec navigation clavier à tabindex-roulant (roving tabindex) entre les
éléments du toolbar, ce qui est le comportement recherché ici.

- [ ] **Step 1: Écrire le test**

Créer `shell/src/ui/kit/Toolbar.test.tsx` :

```tsx
// SPDX-License-Identifier: Apache-2.0
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, test, vi } from "vitest";
import { Toolbar } from "./Toolbar";
import { expectTokenizedClasses } from "./testUtils";

test("clic sur un bouton du toolbar déclenche son action", async () => {
  const onClick = vi.fn();
  const { container } = render(
    <Toolbar.Root aria-label="Actions carte">
      <Toolbar.Button onClick={onClick}>Mesurer</Toolbar.Button>
      <Toolbar.Separator />
      <Toolbar.Button onClick={() => {}}>Croquis</Toolbar.Button>
    </Toolbar.Root>,
  );
  await userEvent.click(screen.getByRole("button", { name: "Mesurer" }));
  expect(onClick).toHaveBeenCalledTimes(1);
  expectTokenizedClasses(container);
});

test("flèche droite déplace le focus au bouton suivant (tabindex roulant)", async () => {
  render(
    <Toolbar.Root aria-label="Actions carte">
      <Toolbar.Button onClick={() => {}}>Mesurer</Toolbar.Button>
      <Toolbar.Button onClick={() => {}}>Croquis</Toolbar.Button>
    </Toolbar.Root>,
  );
  screen.getByRole("button", { name: "Mesurer" }).focus();
  await userEvent.keyboard("{ArrowRight}");
  expect(screen.getByRole("button", { name: "Croquis" })).toHaveFocus();
});
```

- [ ] **Step 2: Vérifier l'échec, implémenter**

Créer `shell/src/ui/kit/Toolbar.tsx` :

```tsx
// SPDX-License-Identifier: Apache-2.0
import * as ToolbarPrimitive from "@radix-ui/react-toolbar";
import { cn } from "../../lib/utils";

function ToolbarRoot({
  className,
  ...props
}: React.ComponentPropsWithoutRef<typeof ToolbarPrimitive.Root>) {
  return (
    <ToolbarPrimitive.Root
      className={cn("flex items-center gap-1 rounded-md border border-rule bg-surface p-1", className)}
      {...props}
    />
  );
}

function ToolbarButtonItem({
  className,
  ...props
}: React.ComponentPropsWithoutRef<typeof ToolbarPrimitive.Button>) {
  return (
    <ToolbarPrimitive.Button
      className={cn(
        "rounded-sm px-2 py-1 text-sm text-ink hover:bg-sunken focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent disabled:cursor-not-allowed disabled:opacity-50",
        className,
      )}
      {...props}
    />
  );
}

function ToolbarSeparatorItem() {
  return <ToolbarPrimitive.Separator className="mx-1 h-5 w-px bg-rule" />;
}

export const Toolbar = {
  Root: ToolbarRoot,
  Button: ToolbarButtonItem,
  Separator: ToolbarSeparatorItem,
};
```

- [ ] **Step 3: Vérifier le succès**

Run: `cd shell && npm run test -- src/ui/kit/Toolbar.test.tsx`
Expected: PASS, 2 tests.

- [ ] **Step 4: Compléter le barrel, commit**

```ts
export { Toolbar } from "./Toolbar";
```

```bash
cd shell
git add src/ui/kit/Toolbar.tsx src/ui/kit/Toolbar.test.tsx src/ui/kit/index.ts
git commit -m "feat(shell): kit — Toolbar"
```

### Task 19: Splitter (maison, redimensionnement par pointeur — pas de Splitter Radix)

**Files:**
- Create: `shell/src/ui/kit/Splitter.tsx`, `Splitter.test.tsx`
- Modify: `shell/src/ui/kit/index.ts`

**Interfaces:**
- Produces: `Splitter` (`first: React.ReactNode; second: React.ReactNode;
  defaultFirstWidth?: number; min?: number; max?: number`).

Il n'existe pas de primitive Radix « Splitter ». Implémentation maison par
écouteurs `pointerdown`/`pointermove`/`pointerup` réels sur une poignée de
redimensionnement `role="separator"` avec `aria-valuenow`/`aria-orientation`.
`userEvent` de Testing Library **n'a pas** de helper de glisser-déposer par
pointeur — les tests utilisent `fireEvent.pointerDown/pointerMove/pointerUp`
directement.

- [ ] **Step 1: Écrire le test**

Créer `shell/src/ui/kit/Splitter.test.tsx` :

```tsx
// SPDX-License-Identifier: Apache-2.0
import { fireEvent, render, screen } from "@testing-library/react";
import { expect, test } from "vitest";
import { Splitter } from "./Splitter";
import { expectTokenizedClasses } from "./testUtils";

test("expose un séparateur avec la largeur courante en aria-valuenow", () => {
  const { container } = render(
    <Splitter first={<div>Gauche</div>} second={<div>Droite</div>} defaultFirstWidth={300} />,
  );
  const handle = screen.getByRole("separator");
  expect(handle).toHaveAttribute("aria-orientation", "vertical");
  expect(handle).toHaveAttribute("aria-valuenow", "300");
  expectTokenizedClasses(container);
});

test("glisser la poignée change la largeur du premier panneau, bornée par min/max", () => {
  render(
    <Splitter
      first={<div>Gauche</div>}
      second={<div>Droite</div>}
      defaultFirstWidth={300}
      min={200}
      max={500}
    />,
  );
  const handle = screen.getByRole("separator");
  fireEvent.pointerDown(handle, { clientX: 300 });
  fireEvent.pointerMove(handle, { clientX: 350 });
  fireEvent.pointerUp(handle);
  expect(handle).toHaveAttribute("aria-valuenow", "350");
});

test("le glissement est borné par max", () => {
  render(
    <Splitter
      first={<div>Gauche</div>}
      second={<div>Droite</div>}
      defaultFirstWidth={300}
      min={200}
      max={400}
    />,
  );
  const handle = screen.getByRole("separator");
  fireEvent.pointerDown(handle, { clientX: 300 });
  fireEvent.pointerMove(handle, { clientX: 1000 });
  fireEvent.pointerUp(handle);
  expect(handle).toHaveAttribute("aria-valuenow", "400");
});
```

- [ ] **Step 2: Vérifier l'échec, implémenter**

Créer `shell/src/ui/kit/Splitter.tsx` :

```tsx
// SPDX-License-Identifier: Apache-2.0
import { useRef, useState } from "react";

export function Splitter({
  first,
  second,
  defaultFirstWidth = 280,
  min = 160,
  max = 640,
}: {
  first: React.ReactNode;
  second: React.ReactNode;
  defaultFirstWidth?: number;
  min?: number;
  max?: number;
}) {
  const [width, setWidth] = useState(defaultFirstWidth);
  const dragStart = useRef<{ pointerX: number; startWidth: number } | null>(null);

  const clamp = (w: number) => Math.min(max, Math.max(min, w));

  const onPointerDown = (e: React.PointerEvent<HTMLDivElement>) => {
    dragStart.current = { pointerX: e.clientX, startWidth: width };
  };
  const onPointerMove = (e: React.PointerEvent<HTMLDivElement>) => {
    if (!dragStart.current) return;
    const delta = e.clientX - dragStart.current.pointerX;
    setWidth(clamp(dragStart.current.startWidth + delta));
  };
  const onPointerUp = () => {
    dragStart.current = null;
  };

  return (
    <div className="flex h-full w-full">
      <div style={{ width }} className="min-w-0 overflow-auto">
        {first}
      </div>
      <div
        role="separator"
        aria-orientation="vertical"
        aria-valuenow={width}
        aria-valuemin={min}
        aria-valuemax={max}
        onPointerDown={onPointerDown}
        onPointerMove={onPointerMove}
        onPointerUp={onPointerUp}
        className="w-1 shrink-0 cursor-col-resize bg-rule hover:bg-accent"
      />
      <div className="min-w-0 flex-1 overflow-auto">{second}</div>
    </div>
  );
}
```

- [ ] **Step 3: Vérifier le succès**

Run: `cd shell && npm run test -- src/ui/kit/Splitter.test.tsx`
Expected: PASS, 3 tests.

- [ ] **Step 4: Compléter le barrel, commit**

```ts
export { Splitter } from "./Splitter";
```

```bash
cd shell
git add src/ui/kit/Splitter.tsx src/ui/kit/Splitter.test.tsx src/ui/kit/index.ts
git commit -m "feat(shell): kit — Splitter"
```

### Task 20: Popover (`@radix-ui/react-popover`)

**Files:**
- Create: `shell/src/ui/kit/Popover.tsx`, `Popover.test.tsx`
- Modify: `shell/src/ui/kit/index.ts`

**Interfaces:**
- Produces: `Popover` (`trigger: React.ReactNode; children: React.ReactNode;
  "aria-label"?: string`).

Point de départ : squelette déjà vérifié par le spike de SP-29a — `Root,
Trigger, Portal, Content, Close, Arrow`. Le spike a confirmé que le contenu
ouvert porte hors de `#root` (portail sur `document.body`) et qu'un clic réel
(`userEvent.click`, pas un forçage d'état) l'ouvre correctement.

- [ ] **Step 1: Écrire le test**

Créer `shell/src/ui/kit/Popover.test.tsx` :

```tsx
// SPDX-License-Identifier: Apache-2.0
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, test } from "vitest";
import { Popover } from "./Popover";
import { expectTokenizedClasses } from "./testUtils";

test("un clic réel sur le déclencheur ouvre le contenu, porté hors de #root", async () => {
  const root = document.createElement("div");
  root.id = "root";
  document.body.appendChild(root);
  const { container } = render(<Popover trigger={<button>Ouvrir</button>}>Contenu du popover</Popover>, {
    container: root,
  });
  expect(screen.queryByText("Contenu du popover")).not.toBeInTheDocument();
  await userEvent.click(screen.getByRole("button", { name: "Ouvrir" }));
  const content = await screen.findByText("Contenu du popover");
  expect(content).toBeInTheDocument();
  expect(root.contains(content)).toBe(false);
  expectTokenizedClasses(container);
  document.body.removeChild(root);
});

test("Échap ferme le popover ouvert", async () => {
  render(<Popover trigger={<button>Ouvrir</button>}>Contenu</Popover>);
  await userEvent.click(screen.getByRole("button", { name: "Ouvrir" }));
  expect(await screen.findByText("Contenu")).toBeInTheDocument();
  await userEvent.keyboard("{Escape}");
  expect(screen.queryByText("Contenu")).not.toBeInTheDocument();
});
```

- [ ] **Step 2: Vérifier l'échec, implémenter**

Créer `shell/src/ui/kit/Popover.tsx` :

```tsx
// SPDX-License-Identifier: Apache-2.0
import * as PopoverPrimitive from "@radix-ui/react-popover";

export function Popover({
  trigger,
  children,
  "aria-label": ariaLabel,
}: {
  trigger: React.ReactNode;
  children: React.ReactNode;
  "aria-label"?: string;
}) {
  return (
    <PopoverPrimitive.Root>
      <PopoverPrimitive.Trigger asChild>{trigger}</PopoverPrimitive.Trigger>
      <PopoverPrimitive.Portal>
        <PopoverPrimitive.Content
          aria-label={ariaLabel}
          sideOffset={4}
          className="rounded-md border border-rule bg-raised p-3 text-sm text-ink shadow-md"
        >
          {children}
        </PopoverPrimitive.Content>
      </PopoverPrimitive.Portal>
    </PopoverPrimitive.Root>
  );
}
```

- [ ] **Step 3: Vérifier le succès**

Run: `cd shell && npm run test -- src/ui/kit/Popover.test.tsx`
Expected: PASS, 2 tests.

- [ ] **Step 4: Compléter le barrel, commit**

```ts
export { Popover } from "./Popover";
```

```bash
cd shell
git add src/ui/kit/Popover.tsx src/ui/kit/Popover.test.tsx src/ui/kit/index.ts
git commit -m "feat(shell): kit — Popover"
```

### Task 21: Menu (`@radix-ui/react-dropdown-menu`)

**Files:**
- Create: `shell/src/ui/kit/Menu.tsx`, `Menu.test.tsx`
- Modify: `shell/src/ui/kit/index.ts`

**Interfaces:**
- Produces: `Menu` (`trigger: React.ReactNode; items: { label: string;
  onSelect: () => void; disabled?: boolean; danger?: boolean }[]`).

- [ ] **Step 1: Écrire le test**

Créer `shell/src/ui/kit/Menu.test.tsx` :

```tsx
// SPDX-License-Identifier: Apache-2.0
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, test, vi } from "vitest";
import { Menu } from "./Menu";
import { expectTokenizedClasses } from "./testUtils";

test("clic sur le déclencheur ouvre le menu, clic sur un item l'exécute et ferme", async () => {
  const onSelect = vi.fn();
  const { container } = render(
    <Menu
      trigger={<button>Actions</button>}
      items={[
        { label: "Modifier", onSelect: () => {} },
        { label: "Supprimer", onSelect, danger: true },
      ]}
    />,
  );
  await userEvent.click(screen.getByRole("button", { name: "Actions" }));
  const item = await screen.findByRole("menuitem", { name: "Supprimer" });
  await userEvent.click(item);
  expect(onSelect).toHaveBeenCalledTimes(1);
  expect(screen.queryByRole("menuitem", { name: "Supprimer" })).not.toBeInTheDocument();
  expectTokenizedClasses(container);
});

test("un item disabled n'appelle pas onSelect", async () => {
  const onSelect = vi.fn();
  render(
    <Menu
      trigger={<button>Actions</button>}
      items={[{ label: "Publier", onSelect, disabled: true }]}
    />,
  );
  await userEvent.click(screen.getByRole("button", { name: "Actions" }));
  const item = await screen.findByRole("menuitem", { name: "Publier" });
  expect(item).toHaveAttribute("aria-disabled", "true");
  await userEvent.click(item);
  expect(onSelect).not.toHaveBeenCalled();
});
```

- [ ] **Step 2: Vérifier l'échec, implémenter**

Créer `shell/src/ui/kit/Menu.tsx` :

```tsx
// SPDX-License-Identifier: Apache-2.0
import * as DropdownMenuPrimitive from "@radix-ui/react-dropdown-menu";
import { cn } from "../../lib/utils";

export function Menu({
  trigger,
  items,
}: {
  trigger: React.ReactNode;
  items: { label: string; onSelect: () => void; disabled?: boolean; danger?: boolean }[];
}) {
  return (
    <DropdownMenuPrimitive.Root>
      <DropdownMenuPrimitive.Trigger asChild>{trigger}</DropdownMenuPrimitive.Trigger>
      <DropdownMenuPrimitive.Portal>
        <DropdownMenuPrimitive.Content
          sideOffset={4}
          className="min-w-40 rounded-md border border-rule bg-raised p-1 shadow-md"
        >
          {items.map((item) => (
            <DropdownMenuPrimitive.Item
              key={item.label}
              disabled={item.disabled}
              onSelect={item.onSelect}
              className={cn(
                "cursor-pointer rounded-sm px-2 py-1.5 text-sm text-ink data-[highlighted]:bg-sunken data-[highlighted]:outline-none data-[disabled]:pointer-events-none data-[disabled]:opacity-50",
                item.danger && "text-danger",
              )}
            >
              {item.label}
            </DropdownMenuPrimitive.Item>
          ))}
        </DropdownMenuPrimitive.Content>
      </DropdownMenuPrimitive.Portal>
    </DropdownMenuPrimitive.Root>
  );
}
```

- [ ] **Step 3: Vérifier le succès**

Run: `cd shell && npm run test -- src/ui/kit/Menu.test.tsx`
Expected: PASS, 2 tests.

- [ ] **Step 4: Compléter le barrel, commit**

```ts
export { Menu } from "./Menu";
```

```bash
cd shell
git add src/ui/kit/Menu.tsx src/ui/kit/Menu.test.tsx src/ui/kit/index.ts
git commit -m "feat(shell): kit — Menu"
```

### Task 22: Tooltip (`@radix-ui/react-tooltip`) — nécessite un Provider global

**Files:**
- Create: `shell/src/ui/kit/Tooltip.tsx`, `Tooltip.test.tsx`
- Modify: `shell/src/ui/kit/index.ts`, `shell/src/App.tsx`

**Interfaces:**
- Produces: `Tooltip` (`content: string; children: React.ReactNode`).
- Consumes: rien de nouveau, mais requiert un ancêtre `Tooltip.Provider` —
  câblé dans `App.tsx` par cette même tâche.

Vérifié réellement le 2026-08-30 contre le paquet installé
(`node_modules/@radix-ui/react-tooltip/dist/index.d.mts`) :
`TooltipProvider: React.FC<TooltipProviderProps>`, dont les seules props sont
`children`, `delayDuration`, `skipDelayDuration`, `disableHoverableContent` —
aucune prop de rendu (`className`, `style`…), donc **aucun élément DOM
propre** : c'est un fournisseur de contexte React pur. L'ajouter à la racine
de `App.tsx` ne peut donc pas modifier une capture d'écran existante — c'est
ce qui rend cette modification de `App.tsx` sûre au regard du critère de
sortie « aucune capture ne diffère ».

- [ ] **Step 1: Écrire le test**

Créer `shell/src/ui/kit/Tooltip.test.tsx` :

```tsx
// SPDX-License-Identifier: Apache-2.0
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, test } from "vitest";
import * as TooltipPrimitive from "@radix-ui/react-tooltip";
import { Tooltip } from "./Tooltip";
import { expectTokenizedClasses } from "./testUtils";

function renderWithProvider(ui: React.ReactElement) {
  return render(<TooltipPrimitive.Provider delayDuration={0}>{ui}</TooltipPrimitive.Provider>);
}

test("le survol du déclencheur affiche le contenu du tooltip", async () => {
  const { container } = renderWithProvider(
    <Tooltip content="Verrouillé — modification réservée aux éditeurs">
      <button>×</button>
    </Tooltip>,
  );
  await userEvent.hover(screen.getByRole("button"));
  expect(
    await screen.findByText("Verrouillé — modification réservée aux éditeurs"),
  ).toBeInTheDocument();
  expectTokenizedClasses(container);
});
```

- [ ] **Step 2: Vérifier l'échec, implémenter**

Créer `shell/src/ui/kit/Tooltip.tsx` :

```tsx
// SPDX-License-Identifier: Apache-2.0
import * as TooltipPrimitive from "@radix-ui/react-tooltip";

export function Tooltip({
  content,
  children,
}: {
  content: string;
  children: React.ReactElement;
}) {
  return (
    <TooltipPrimitive.Root>
      <TooltipPrimitive.Trigger asChild>{children}</TooltipPrimitive.Trigger>
      <TooltipPrimitive.Portal>
        <TooltipPrimitive.Content
          sideOffset={4}
          className="rounded-md border border-rule bg-ink px-2 py-1 text-xs text-surface shadow-sm"
        >
          {content}
          <TooltipPrimitive.Arrow className="fill-ink" />
        </TooltipPrimitive.Content>
      </TooltipPrimitive.Portal>
    </TooltipPrimitive.Root>
  );
}
```

- [ ] **Step 3: Vérifier le succès**

Run: `cd shell && npm run test -- src/ui/kit/Tooltip.test.tsx`
Expected: PASS, 1 test.

- [ ] **Step 4: Câbler le Provider dans l'app réelle**

Lire `shell/src/App.tsx` pour repérer l'élément racine du JSX rendu (l'arbre
actuel, probablement `<AuthProvider>`/`<QueryClientProvider>` puis
`<AppRoutes />`). Envelopper tout l'arbre existant, sans rien retirer ni
réordonner d'autre, avec `TooltipPrimitive.Provider` :

```tsx
import * as TooltipPrimitive from "@radix-ui/react-tooltip";
```

puis, autour du JSX déjà présent (exemple de forme, à adapter à l'arbre réel
du fichier — ne pas changer l'ordre des providers déjà en place, seulement en
ajouter un englobant) :

```tsx
<TooltipPrimitive.Provider>{/* arbre existant inchangé */}</TooltipPrimitive.Provider>
```

- [ ] **Step 5: Vérifier qu'aucun écran ne change**

Run: `cd shell && npm run test`
Expected: tous les tests existants passent toujours (aucune capture, aucun
rendu ne dépend d'un ancêtre `Tooltip.Provider`, donc son ajout est neutre).

- [ ] **Step 6: Compléter le barrel, commit**

```ts
export { Tooltip } from "./Tooltip";
```

```bash
cd shell
git add src/ui/kit/Tooltip.tsx src/ui/kit/Tooltip.test.tsx src/ui/kit/index.ts src/App.tsx
git commit -m "feat(shell): kit — Tooltip + Tooltip.Provider global"
```

### Task 23: Dialog (base interne partagée), ConfirmDialog

**Files:**
- Create: `shell/src/ui/kit/Dialog.tsx`, `Dialog.test.tsx`
- Create: `shell/src/ui/kit/ConfirmDialog.tsx`, `ConfirmDialog.test.tsx`
- Modify: `shell/src/ui/kit/index.ts`

**Interfaces:**
- Produces: `Dialog` (`open: boolean; onOpenChange: (open: boolean) => void;
  title: string; children: React.ReactNode` — plomberie interne, pas un des
  ~40 items nommés du kit mais requise par `ConfirmDialog` ici et `Drawer`
  Task 24), `ConfirmDialog` (`open: boolean; title: string; message: string;
  confirmLabel: string; onConfirm: () => void; onCancel: () => void;
  pending?: boolean` — **prop shape identique** à l'ancien
  `shell/src/ui/ConfirmDialog.tsx`, pour que SP-30 puisse basculer les points
  d'appel par un simple changement d'import, sans réécrire les props).

Exports réels vérifiés le 2026-08-30 contre `@radix-ui/react-dialog@1.1.23`
installé (`dist/index.d.mts`) : `Root(=Dialog), Trigger, Portal, Overlay,
Content, Title, Description, Close`.

- [ ] **Step 1: Écrire le test de Dialog**

Créer `shell/src/ui/kit/Dialog.test.tsx` :

```tsx
// SPDX-License-Identifier: Apache-2.0
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, test, vi } from "vitest";
import { Dialog } from "./Dialog";
import { expectTokenizedClasses } from "./testUtils";

test("ne rend rien quand fermé", () => {
  render(
    <Dialog open={false} onOpenChange={() => {}} title="T">
      <p>corps</p>
    </Dialog>,
  );
  expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
});

test("rend le contenu et le titre quand ouvert, Échap ferme", async () => {
  const onOpenChange = vi.fn();
  const { container } = render(
    <Dialog open onOpenChange={onOpenChange} title="Titre">
      <p>corps</p>
    </Dialog>,
  );
  expect(screen.getByRole("dialog", { name: "Titre" })).toBeInTheDocument();
  expect(screen.getByText("corps")).toBeInTheDocument();
  await userEvent.keyboard("{Escape}");
  expect(onOpenChange).toHaveBeenCalledWith(false);
  expectTokenizedClasses(container);
});

test("le focus est piégé dans la boîte de dialogue à l'ouverture", async () => {
  render(
    <Dialog open onOpenChange={() => {}} title="Titre">
      <button>Premier</button>
      <button>Second</button>
    </Dialog>,
  );
  await userEvent.tab();
  expect(screen.getByRole("button", { name: "Premier" })).toHaveFocus();
});
```

- [ ] **Step 2: Vérifier l'échec, implémenter**

Créer `shell/src/ui/kit/Dialog.tsx` :

```tsx
// SPDX-License-Identifier: Apache-2.0
import * as DialogPrimitive from "@radix-ui/react-dialog";

export function Dialog({
  open,
  onOpenChange,
  title,
  children,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  title: string;
  children: React.ReactNode;
}) {
  return (
    <DialogPrimitive.Root open={open} onOpenChange={onOpenChange}>
      <DialogPrimitive.Portal>
        <DialogPrimitive.Overlay className="fixed inset-0 z-50 bg-ink/40" />
        <DialogPrimitive.Content className="fixed left-1/2 top-1/2 z-50 w-full max-w-md -translate-x-1/2 -translate-y-1/2 rounded-lg border border-rule bg-raised p-6 shadow-lg">
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

- [ ] **Step 3: Vérifier le succès**

Run: `cd shell && npm run test -- src/ui/kit/Dialog.test.tsx`
Expected: PASS, 3 tests.

- [ ] **Step 4: Écrire le test de ConfirmDialog**

Créer `shell/src/ui/kit/ConfirmDialog.test.tsx` :

```tsx
// SPDX-License-Identifier: Apache-2.0
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, test, vi } from "vitest";
import { ConfirmDialog } from "./ConfirmDialog";
import { expectTokenizedClasses } from "./testUtils";

test("clic sur Annuler appelle onCancel", async () => {
  const onCancel = vi.fn();
  const { container } = render(
    <ConfirmDialog
      open
      title="Supprimer"
      message="Supprimer « Carte topo » ? Cette action est irréversible."
      confirmLabel="Supprimer"
      onConfirm={() => {}}
      onCancel={onCancel}
    />,
  );
  await userEvent.click(screen.getByRole("button", { name: "Annuler" }));
  expect(onCancel).toHaveBeenCalledTimes(1);
  expectTokenizedClasses(container);
});

test("clic sur le bouton de confirmation appelle onConfirm", async () => {
  const onConfirm = vi.fn();
  render(
    <ConfirmDialog
      open
      title="Supprimer"
      message="Confirmer ?"
      confirmLabel="Supprimer"
      onConfirm={onConfirm}
      onCancel={() => {}}
    />,
  );
  await userEvent.click(screen.getByRole("button", { name: "Supprimer" }));
  expect(onConfirm).toHaveBeenCalledTimes(1);
});

test("pending désactive le bouton de confirmation", () => {
  render(
    <ConfirmDialog
      open
      title="Supprimer"
      message="Confirmer ?"
      confirmLabel="Supprimer"
      onConfirm={() => {}}
      onCancel={() => {}}
      pending
    />,
  );
  expect(screen.getByRole("button", { name: "Supprimer" })).toBeDisabled();
});
```

- [ ] **Step 5: Implémenter ConfirmDialog**

Créer `shell/src/ui/kit/ConfirmDialog.tsx` :

```tsx
// SPDX-License-Identifier: Apache-2.0
import { Button } from "./Button";
import { Dialog } from "./Dialog";

export function ConfirmDialog({
  open,
  title,
  message,
  confirmLabel,
  onConfirm,
  onCancel,
  pending,
}: {
  open: boolean;
  title: string;
  message: string;
  confirmLabel: string;
  onConfirm: () => void;
  onCancel: () => void;
  pending?: boolean;
}) {
  return (
    <Dialog open={open} onOpenChange={(next) => !next && onCancel()} title={title}>
      <p className="mb-4 text-sm text-ink-2">{message}</p>
      <div className="flex justify-end gap-2">
        <Button type="button" variant="outline" size="sm" onClick={onCancel}>
          Annuler
        </Button>
        <Button type="button" variant="danger" size="sm" disabled={pending} onClick={onConfirm}>
          {confirmLabel}
        </Button>
      </div>
    </Dialog>
  );
}
```

- [ ] **Step 6: Vérifier le succès**

Run: `cd shell && npm run test -- src/ui/kit/ConfirmDialog.test.tsx`
Expected: PASS, 3 tests.

- [ ] **Step 7: Compléter le barrel, commit**

```ts
export { Dialog } from "./Dialog";
export { ConfirmDialog } from "./ConfirmDialog";
```

```bash
cd shell
git add src/ui/kit/Dialog.tsx src/ui/kit/Dialog.test.tsx src/ui/kit/ConfirmDialog.tsx src/ui/kit/ConfirmDialog.test.tsx src/ui/kit/index.ts
git commit -m "feat(shell): kit — Dialog (base interne), ConfirmDialog"
```

### Task 24: Drawer (`@radix-ui/react-dialog`, glissant depuis un bord)

**Files:**
- Create: `shell/src/ui/kit/Drawer.tsx`, `Drawer.test.tsx`
- Modify: `shell/src/ui/kit/index.ts`

**Interfaces:**
- Produces: `Drawer` (`open: boolean; onOpenChange: (open: boolean) => void;
  title: string; side?: "left" | "right"; children: React.ReactNode`).

Fichier distinct de `Dialog`/`ConfirmDialog` (Task 23) : même primitive Radix
sous-jacente, mais positionnement/animation de panneau glissant différents,
pas de recouvrement centré.

- [ ] **Step 1: Écrire le test**

Créer `shell/src/ui/kit/Drawer.test.tsx` :

```tsx
// SPDX-License-Identifier: Apache-2.0
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, test, vi } from "vitest";
import { Drawer } from "./Drawer";
import { expectTokenizedClasses } from "./testUtils";

test("rend le contenu à droite par défaut", () => {
  const { container } = render(
    <Drawer open onOpenChange={() => {}} title="Explorateur">
      <p>Contenu</p>
    </Drawer>,
  );
  expect(screen.getByRole("dialog", { name: "Explorateur" })).toHaveClass("right-0");
  expectTokenizedClasses(container);
});

test("side=left positionne le panneau à gauche", () => {
  render(
    <Drawer open onOpenChange={() => {}} title="Explorateur" side="left">
      <p>Contenu</p>
    </Drawer>,
  );
  expect(screen.getByRole("dialog", { name: "Explorateur" })).toHaveClass("left-0");
});

test("Échap appelle onOpenChange(false)", async () => {
  const onOpenChange = vi.fn();
  render(
    <Drawer open onOpenChange={onOpenChange} title="Explorateur">
      <p>Contenu</p>
    </Drawer>,
  );
  await userEvent.keyboard("{Escape}");
  expect(onOpenChange).toHaveBeenCalledWith(false);
});
```

- [ ] **Step 2: Vérifier l'échec, implémenter**

Créer `shell/src/ui/kit/Drawer.tsx` :

```tsx
// SPDX-License-Identifier: Apache-2.0
import * as DialogPrimitive from "@radix-ui/react-dialog";
import { cn } from "../../lib/utils";

export function Drawer({
  open,
  onOpenChange,
  title,
  side = "right",
  children,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  title: string;
  side?: "left" | "right";
  children: React.ReactNode;
}) {
  return (
    <DialogPrimitive.Root open={open} onOpenChange={onOpenChange}>
      <DialogPrimitive.Portal>
        <DialogPrimitive.Overlay className="fixed inset-0 z-50 bg-ink/40" />
        <DialogPrimitive.Content
          className={cn(
            "fixed top-0 z-50 h-full w-full max-w-sm border-rule bg-raised p-4 shadow-lg",
            side === "right" ? "right-0 border-l" : "left-0 border-r",
          )}
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

- [ ] **Step 3: Vérifier le succès**

Run: `cd shell && npm run test -- src/ui/kit/Drawer.test.tsx`
Expected: PASS, 3 tests.

- [ ] **Step 4: Compléter le barrel, commit**

```ts
export { Drawer } from "./Drawer";
```

```bash
cd shell
git add src/ui/kit/Drawer.tsx src/ui/kit/Drawer.test.tsx src/ui/kit/index.ts
git commit -m "feat(shell): kit — Drawer"
```

### Task 25: Badge, Chip

**Files:**
- Create: `shell/src/ui/kit/Badge.tsx`, `Badge.test.tsx`
- Create: `shell/src/ui/kit/Chip.tsx`, `Chip.test.tsx`
- Modify: `shell/src/ui/kit/index.ts`

**Interfaces:**
- Produces: `Badge` (`variant?: "default"|"ok"|"warn"|"danger";
  children: React.ReactNode` — étiquette non interactive, ex. statut
  « Publié »/« Brouillon »), `Chip` (`children: React.ReactNode; onRemove?:
  () => void` — étiquette interactive avec fermeture optionnelle, ex. un
  filtre actif).

- [ ] **Step 1: Écrire les deux tests**

Créer `shell/src/ui/kit/Badge.test.tsx` :

```tsx
// SPDX-License-Identifier: Apache-2.0
import { render, screen } from "@testing-library/react";
import { expect, test } from "vitest";
import { Badge } from "./Badge";
import { expectTokenizedClasses } from "./testUtils";

test("variant danger applique bg-danger-soft", () => {
  const { container } = render(<Badge variant="danger">Erreur</Badge>);
  expect(screen.getByText("Erreur")).toHaveClass("bg-danger-soft");
  expectTokenizedClasses(container);
});

test("variant par défaut applique bg-sunken", () => {
  render(<Badge>Brouillon</Badge>);
  expect(screen.getByText("Brouillon")).toHaveClass("bg-sunken");
});
```

Créer `shell/src/ui/kit/Chip.test.tsx` :

```tsx
// SPDX-License-Identifier: Apache-2.0
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, test, vi } from "vitest";
import { Chip } from "./Chip";
import { expectTokenizedClasses } from "./testUtils";

test("clic sur le bouton de retrait appelle onRemove", async () => {
  const onRemove = vi.fn();
  const { container } = render(<Chip onRemove={onRemove}>type: map</Chip>);
  await userEvent.click(screen.getByRole("button", { name: "Retirer type: map" }));
  expect(onRemove).toHaveBeenCalledTimes(1);
  expectTokenizedClasses(container);
});

test("sans onRemove, aucun bouton de retrait n'est rendu", () => {
  render(<Chip>type: map</Chip>);
  expect(screen.queryByRole("button")).not.toBeInTheDocument();
});
```

- [ ] **Step 2: Vérifier l'échec, implémenter**

Créer `shell/src/ui/kit/Badge.tsx` :

```tsx
// SPDX-License-Identifier: Apache-2.0
import { cva, type VariantProps } from "class-variance-authority";
import { cn } from "../../lib/utils";

const badgeVariants = cva("inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium", {
  variants: {
    variant: {
      default: "bg-sunken text-ink-2",
      ok: "bg-ok-soft text-ok",
      warn: "bg-warn-soft text-warn",
      danger: "bg-danger-soft text-danger",
    },
  },
  defaultVariants: { variant: "default" },
});

export function Badge({
  className,
  variant,
  children,
}: { className?: string; children: React.ReactNode } & VariantProps<typeof badgeVariants>) {
  return <span className={cn(badgeVariants({ variant }), className)}>{children}</span>;
}
```

Créer `shell/src/ui/kit/Chip.tsx` :

```tsx
// SPDX-License-Identifier: Apache-2.0
import { X } from "lucide-react";

export function Chip({
  children,
  onRemove,
}: {
  children: React.ReactNode;
  onRemove?: () => void;
}) {
  return (
    <span className="inline-flex items-center gap-1 rounded-full border border-rule bg-surface px-2 py-0.5 text-xs text-ink">
      {children}
      {onRemove && (
        <button
          type="button"
          aria-label={`Retirer ${children}`}
          onClick={onRemove}
          className="text-ink-3 hover:text-danger"
        >
          <X size={12} />
        </button>
      )}
    </span>
  );
}
```

- [ ] **Step 3: Vérifier le succès**

Run: `cd shell && npm run test -- src/ui/kit/Badge.test.tsx src/ui/kit/Chip.test.tsx`
Expected: PASS, 4 tests.

- [ ] **Step 4: Compléter le barrel, commit**

```ts
export { Badge } from "./Badge";
export { Chip } from "./Chip";
```

```bash
cd shell
git add src/ui/kit/Badge.tsx src/ui/kit/Badge.test.tsx src/ui/kit/Chip.tsx src/ui/kit/Chip.test.tsx src/ui/kit/index.ts
git commit -m "feat(shell): kit — Badge, Chip"
```

### Task 26: Toast (`@radix-ui/react-toast`) — nécessite un Provider + Viewport globaux

**Files:**
- Create: `shell/src/ui/kit/Toast.tsx`, `Toast.test.tsx`
- Modify: `shell/src/ui/kit/index.ts`, `shell/src/App.tsx`

**Interfaces:**
- Produces: `Toast` (`open: boolean; onOpenChange: (open: boolean) => void;
  title: string; description?: string; action?: { label: string; onClick: ()
  => void }`) — un toast **contrôlé** unique ; ce plan ne construit pas de
  gestionnaire de file/hook impératif (`useToast()`), hors périmètre YAGNI —
  chaque appelant possède son propre état `open`.

Exports réels vérifiés le 2026-08-30 contre `@radix-ui/react-toast@1.2.23`
installé : `Provider, Viewport, Root, Title, Description, Action, Close`.
**`Viewport` rend un vrai `<ol>`** (`Primitive.ol`, pas un composant inerte
sans DOM comme `Tooltip.Provider`) — pour qu'il n'ait aucun effet visuel sur
les écrans existants, il doit être positionné en `fixed` (hors du flux
normal du document) : c'est ce que fait le style ci-dessous, vérifié
nécessaire précisément parce que `<ol>` porte des marges/paddings par défaut
du navigateur qui, en flux normal, décaleraient visiblement le contenu
environnant.

- [ ] **Step 1: Écrire le test**

Créer `shell/src/ui/kit/Toast.test.tsx` :

```tsx
// SPDX-License-Identifier: Apache-2.0
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import * as ToastPrimitive from "@radix-ui/react-toast";
import { expect, test, vi } from "vitest";
import { Toast } from "./Toast";
import { expectTokenizedClasses } from "./testUtils";

function renderWithProvider(ui: React.ReactElement) {
  return render(
    <ToastPrimitive.Provider>
      {ui}
      <ToastPrimitive.Viewport />
    </ToastPrimitive.Provider>,
  );
}

test("affiche titre et description quand ouvert", () => {
  const { container } = renderWithProvider(
    <Toast open onOpenChange={() => {}} title="Enregistré" description="Les modifications sont sauvegardées." />,
  );
  expect(screen.getByText("Enregistré")).toBeInTheDocument();
  expect(screen.getByText("Les modifications sont sauvegardées.")).toBeInTheDocument();
  expectTokenizedClasses(container);
});

test("clic sur l'action l'exécute", async () => {
  const onClick = vi.fn();
  renderWithProvider(
    <Toast open onOpenChange={() => {}} title="Supprimé" action={{ label: "Annuler", onClick }} />,
  );
  await userEvent.click(screen.getByRole("button", { name: "Annuler" }));
  expect(onClick).toHaveBeenCalledTimes(1);
});
```

- [ ] **Step 2: Vérifier l'échec, implémenter**

Créer `shell/src/ui/kit/Toast.tsx` :

```tsx
// SPDX-License-Identifier: Apache-2.0
import * as ToastPrimitive from "@radix-ui/react-toast";
import { t } from "../../i18n";

export function Toast({
  open,
  onOpenChange,
  title,
  description,
  action,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  title: string;
  description?: string;
  action?: { label: string; onClick: () => void };
}) {
  return (
    <ToastPrimitive.Root
      open={open}
      onOpenChange={onOpenChange}
      className="rounded-md border border-rule bg-raised p-3 shadow-md"
    >
      <ToastPrimitive.Title className="text-sm font-medium text-ink">{title}</ToastPrimitive.Title>
      {description && (
        <ToastPrimitive.Description className="mt-1 text-xs text-ink-2">
          {description}
        </ToastPrimitive.Description>
      )}
      {action && (
        <ToastPrimitive.Action altText={action.label} asChild>
          <button onClick={action.onClick} className="mt-2 text-xs font-medium text-accent">
            {action.label}
          </button>
        </ToastPrimitive.Action>
      )}
      <ToastPrimitive.Close aria-label={t("kit.toast.close")} className="absolute right-2 top-2 text-ink-3">
        ×
      </ToastPrimitive.Close>
    </ToastPrimitive.Root>
  );
}
```

Ajouter au catalogue `shell/src/i18n/catalog.fr.ts` :

```ts
  "kit.toast.close": "Fermer la notification",
```

- [ ] **Step 3: Vérifier le succès**

Run: `cd shell && npm run test -- src/ui/kit/Toast.test.tsx`
Expected: PASS, 2 tests.

- [ ] **Step 4: Câbler Provider + Viewport dans l'app réelle**

Dans `shell/src/App.tsx`, à côté du `TooltipPrimitive.Provider` ajouté en
Task 22, envelopper l'arbre existant dans `ToastPrimitive.Provider` et
ajouter un unique `<ToastPrimitive.Viewport>` positionné hors flux :

```tsx
import * as ToastPrimitive from "@radix-ui/react-toast";
```

```tsx
<ToastPrimitive.Provider>
  {/* arbre existant, y compris TooltipPrimitive.Provider */}
  <ToastPrimitive.Viewport className="fixed bottom-4 right-4 z-[100] flex w-80 flex-col gap-2 outline-none" />
</ToastPrimitive.Provider>
```

`position: fixed` (via la classe `fixed`) retire l'élément du flux normal du
document — sans toast ouvert, la liste est vide et n'occupe donc aucun
espace visible sur aucun écran existant, ce qui préserve le critère de
sortie « aucune capture ne diffère ».

- [ ] **Step 5: Vérifier qu'aucun écran ne change**

Run: `cd shell && npm run test`
Expected: tous les tests existants passent toujours.

- [ ] **Step 6: Compléter le barrel, commit**

```ts
export { Toast } from "./Toast";
```

```bash
cd shell
git add src/ui/kit/Toast.tsx src/ui/kit/Toast.test.tsx src/ui/kit/index.ts src/App.tsx src/i18n/catalog.fr.ts
git commit -m "feat(shell): kit — Toast + Toast.Provider/Viewport globaux"
```

### Task 27: Skeleton, Spinner, Progress (`@radix-ui/react-progress` pour Progress uniquement)

**Files:**
- Create: `shell/src/ui/kit/Skeleton.tsx`, `Skeleton.test.tsx`
- Create: `shell/src/ui/kit/Spinner.tsx`, `Spinner.test.tsx`
- Create: `shell/src/ui/kit/Progress.tsx`, `Progress.test.tsx`
- Modify: `shell/src/ui/kit/index.ts`

**Interfaces:**
- Produces: `Skeleton` (`className?: string`), `Spinner` (`"aria-label":
  string`), `Progress` (`value: number; max?: number; "aria-label": string`).

Exports réels vérifiés le 2026-08-30 contre `@radix-ui/react-progress@1.1.16`
installé : `Root, Indicator`.

- [ ] **Step 1: Écrire les trois tests**

Créer `shell/src/ui/kit/Skeleton.test.tsx` :

```tsx
// SPDX-License-Identifier: Apache-2.0
import { render } from "@testing-library/react";
import { expect, test } from "vitest";
import { Skeleton } from "./Skeleton";
import { expectTokenizedClasses } from "./testUtils";

test("rend un bloc animé tokenisé", () => {
  const { container } = render(<Skeleton className="h-4 w-32" />);
  expect(container.firstChild).toHaveClass("animate-pulse", "bg-sunken", "h-4", "w-32");
  expectTokenizedClasses(container);
});
```

Créer `shell/src/ui/kit/Spinner.test.tsx` :

```tsx
// SPDX-License-Identifier: Apache-2.0
import { render, screen } from "@testing-library/react";
import { expect, test } from "vitest";
import { Spinner } from "./Spinner";
import { expectTokenizedClasses } from "./testUtils";

test("expose role=status avec un nom accessible", () => {
  const { container } = render(<Spinner aria-label="Chargement" />);
  expect(screen.getByRole("status", { name: "Chargement" })).toBeInTheDocument();
  expectTokenizedClasses(container);
});
```

Créer `shell/src/ui/kit/Progress.test.tsx` :

```tsx
// SPDX-License-Identifier: Apache-2.0
import { render, screen } from "@testing-library/react";
import { expect, test } from "vitest";
import { Progress } from "./Progress";
import { expectTokenizedClasses } from "./testUtils";

test("expose la valeur courante via aria-valuenow", () => {
  const { container } = render(<Progress aria-label="Import" value={40} max={100} />);
  const bar = screen.getByRole("progressbar", { name: "Import" });
  expect(bar).toHaveAttribute("aria-valuenow", "40");
  expect(bar).toHaveAttribute("aria-valuemax", "100");
  expectTokenizedClasses(container);
});
```

- [ ] **Step 2: Vérifier l'échec des trois, implémenter**

Créer `shell/src/ui/kit/Skeleton.tsx` :

```tsx
// SPDX-License-Identifier: Apache-2.0
import { cn } from "../../lib/utils";

export function Skeleton({ className }: { className?: string }) {
  return <div className={cn("animate-pulse rounded-sm bg-sunken", className)} />;
}
```

Créer `shell/src/ui/kit/Spinner.tsx` :

```tsx
// SPDX-License-Identifier: Apache-2.0
export function Spinner({ "aria-label": ariaLabel }: { "aria-label": string }) {
  return (
    <div
      role="status"
      aria-label={ariaLabel}
      className="h-4 w-4 animate-spin rounded-full border-2 border-rule border-t-accent"
    />
  );
}
```

Créer `shell/src/ui/kit/Progress.tsx` :

```tsx
// SPDX-License-Identifier: Apache-2.0
import * as ProgressPrimitive from "@radix-ui/react-progress";

export function Progress({
  value,
  max = 100,
  "aria-label": ariaLabel,
}: {
  value: number;
  max?: number;
  "aria-label": string;
}) {
  return (
    <ProgressPrimitive.Root
      aria-label={ariaLabel}
      value={value}
      max={max}
      className="h-2 w-full overflow-hidden rounded-full bg-sunken"
    >
      <ProgressPrimitive.Indicator
        style={{ transform: `translateX(-${100 - (value / max) * 100}%)` }}
        className="h-full w-full bg-accent transition-transform"
      />
    </ProgressPrimitive.Root>
  );
}
```

- [ ] **Step 3: Vérifier le succès des trois**

Run: `cd shell && npm run test -- src/ui/kit/Skeleton.test.tsx src/ui/kit/Spinner.test.tsx src/ui/kit/Progress.test.tsx`
Expected: PASS, 3 tests.

- [ ] **Step 4: Compléter le barrel, commit**

```ts
export { Skeleton } from "./Skeleton";
export { Spinner } from "./Spinner";
export { Progress } from "./Progress";
```

```bash
cd shell
git add src/ui/kit/Skeleton.tsx src/ui/kit/Skeleton.test.tsx src/ui/kit/Spinner.tsx src/ui/kit/Spinner.test.tsx src/ui/kit/Progress.tsx src/ui/kit/Progress.test.tsx src/ui/kit/index.ts
git commit -m "feat(shell): kit — Skeleton, Spinner, Progress"
```

### Task 28: EmptyState, Banner

**Files:**
- Create: `shell/src/ui/kit/EmptyState.tsx`, `EmptyState.test.tsx`
- Create: `shell/src/ui/kit/Banner.tsx`, `Banner.test.tsx`
- Modify: `shell/src/ui/kit/index.ts`

**Interfaces:**
- Produces: `EmptyState` (`title: string; description?: string; action?:
  React.ReactNode`), `Banner` (`variant?: "info"|"warn"|"danger"; children:
  React.ReactNode`).

- [ ] **Step 1: Écrire les deux tests**

Créer `shell/src/ui/kit/EmptyState.test.tsx` :

```tsx
// SPDX-License-Identifier: Apache-2.0
import { render, screen } from "@testing-library/react";
import { expect, test } from "vitest";
import { EmptyState } from "./EmptyState";
import { Button } from "./Button";
import { expectTokenizedClasses } from "./testUtils";

test("rend titre, description et l'action fournie", () => {
  const { container } = render(
    <EmptyState
      title="Aucun résultat"
      description="Essayez un autre filtre."
      action={<Button>Réinitialiser</Button>}
    />,
  );
  expect(screen.getByText("Aucun résultat")).toBeInTheDocument();
  expect(screen.getByText("Essayez un autre filtre.")).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Réinitialiser" })).toBeInTheDocument();
  expectTokenizedClasses(container);
});
```

Créer `shell/src/ui/kit/Banner.test.tsx` :

```tsx
// SPDX-License-Identifier: Apache-2.0
import { render, screen } from "@testing-library/react";
import { expect, test } from "vitest";
import { Banner } from "./Banner";
import { expectTokenizedClasses } from "./testUtils";

test("variant danger porte role=alert", () => {
  const { container } = render(<Banner variant="danger">Échec de l'enregistrement.</Banner>);
  expect(screen.getByRole("alert")).toHaveTextContent("Échec de l'enregistrement.");
  expectTokenizedClasses(container);
});

test("variant info ne porte pas role=alert", () => {
  render(<Banner variant="info">Mode démonstration.</Banner>);
  expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  expect(screen.getByText("Mode démonstration.")).toBeInTheDocument();
});
```

- [ ] **Step 2: Vérifier l'échec, implémenter**

Créer `shell/src/ui/kit/EmptyState.tsx` :

```tsx
// SPDX-License-Identifier: Apache-2.0
export function EmptyState({
  title,
  description,
  action,
}: {
  title: string;
  description?: string;
  action?: React.ReactNode;
}) {
  return (
    <div className="flex flex-col items-center gap-2 rounded-lg border border-dashed border-rule p-8 text-center">
      <p className="text-sm font-medium text-ink">{title}</p>
      {description && <p className="text-sm text-ink-3">{description}</p>}
      {action}
    </div>
  );
}
```

Créer `shell/src/ui/kit/Banner.tsx` :

```tsx
// SPDX-License-Identifier: Apache-2.0
import { cva, type VariantProps } from "class-variance-authority";
import { cn } from "../../lib/utils";

const bannerVariants = cva("rounded-md border p-3 text-sm", {
  variants: {
    variant: {
      info: "border-accent-soft bg-accent-soft text-accent-ink",
      warn: "border-warn-soft bg-warn-soft text-warn",
      danger: "border-danger-soft bg-danger-soft text-danger",
    },
  },
  defaultVariants: { variant: "info" },
});

export function Banner({
  variant,
  children,
}: { children: React.ReactNode } & VariantProps<typeof bannerVariants>) {
  return (
    <div className={cn(bannerVariants({ variant }))} role={variant === "danger" ? "alert" : undefined}>
      {children}
    </div>
  );
}
```

- [ ] **Step 3: Vérifier le succès**

Run: `cd shell && npm run test -- src/ui/kit/EmptyState.test.tsx src/ui/kit/Banner.test.tsx`
Expected: PASS, 3 tests.

- [ ] **Step 4: Compléter le barrel, commit**

```ts
export { EmptyState } from "./EmptyState";
export { Banner } from "./Banner";
```

```bash
cd shell
git add src/ui/kit/EmptyState.tsx src/ui/kit/EmptyState.test.tsx src/ui/kit/Banner.tsx src/ui/kit/Banner.test.tsx src/ui/kit/index.ts
git commit -m "feat(shell): kit — EmptyState, Banner"
```

### Task 29: Avatar (`@radix-ui/react-avatar`), Kbd

**Files:**
- Create: `shell/src/ui/kit/Avatar.tsx`, `Avatar.test.tsx`
- Create: `shell/src/ui/kit/Kbd.tsx`, `Kbd.test.tsx`
- Modify: `shell/src/ui/kit/index.ts`

**Interfaces:**
- Produces: `Avatar` (`src?: string; alt: string; fallback: string`), `Kbd`
  (`children: React.ReactNode`).

Exports réels vérifiés le 2026-08-30 contre `@radix-ui/react-avatar@1.2.6`
installé : `Root, Image, Fallback`.

- [ ] **Step 1: Écrire les deux tests**

Créer `shell/src/ui/kit/Avatar.test.tsx` :

```tsx
// SPDX-License-Identifier: Apache-2.0
import { render, screen } from "@testing-library/react";
import { expect, test } from "vitest";
import { Avatar } from "./Avatar";
import { expectTokenizedClasses } from "./testUtils";

test("affiche le repli tant que l'image n'a pas chargé (jsdom ne charge aucune image)", () => {
  const { container } = render(<Avatar src="/photo.jpg" alt="Tanguy" fallback="TL" />);
  expect(screen.getByText("TL")).toBeInTheDocument();
  expectTokenizedClasses(container);
});

test("sans src, affiche directement le repli", () => {
  render(<Avatar alt="Tanguy" fallback="TL" />);
  expect(screen.getByText("TL")).toBeInTheDocument();
});
```

Créer `shell/src/ui/kit/Kbd.test.tsx` :

```tsx
// SPDX-License-Identifier: Apache-2.0
import { render, screen } from "@testing-library/react";
import { expect, test } from "vitest";
import { Kbd } from "./Kbd";
import { expectTokenizedClasses } from "./testUtils";

test("rend un élément kbd tokenisé", () => {
  const { container } = render(<Kbd>⌘K</Kbd>);
  expect(screen.getByText("⌘K").tagName).toBe("KBD");
  expectTokenizedClasses(container);
});
```

- [ ] **Step 2: Vérifier l'échec, implémenter**

Créer `shell/src/ui/kit/Avatar.tsx` :

```tsx
// SPDX-License-Identifier: Apache-2.0
import * as AvatarPrimitive from "@radix-ui/react-avatar";

export function Avatar({
  src,
  alt,
  fallback,
}: {
  src?: string;
  alt: string;
  fallback: string;
}) {
  return (
    <AvatarPrimitive.Root className="flex h-8 w-8 items-center justify-center overflow-hidden rounded-full bg-sunken">
      {src && <AvatarPrimitive.Image src={src} alt={alt} className="h-full w-full object-cover" />}
      <AvatarPrimitive.Fallback className="text-xs font-medium text-ink-2" delayMs={0}>
        {fallback}
      </AvatarPrimitive.Fallback>
    </AvatarPrimitive.Root>
  );
}
```

Créer `shell/src/ui/kit/Kbd.tsx` :

```tsx
// SPDX-License-Identifier: Apache-2.0
export function Kbd({ children }: { children: React.ReactNode }) {
  return (
    <kbd className="rounded border border-rule bg-sunken px-1.5 py-0.5 font-mono text-xs text-ink-2">
      {children}
    </kbd>
  );
}
```

Note (`Avatar.tsx`) : `AvatarPrimitive.Fallback` a un `delayMs` par défaut
qui retarde son affichage tant que `Image` n'a pas eu le temps de tenter son
chargement — mis à `0` ici pour un rendu déterministe en test (jsdom ne
charge jamais réellement une image, donc `onLoadingStatusChange` ne passera
jamais à `"loaded"`, mais un délai non nul rendrait le premier test flaky
selon le scheduler de test) ; comportement à revérifier visuellement dans la
galerie (Task 30) où un vrai navigateur peut réellement charger l'image.

- [ ] **Step 3: Vérifier le succès**

Run: `cd shell && npm run test -- src/ui/kit/Avatar.test.tsx src/ui/kit/Kbd.test.tsx`
Expected: PASS, 3 tests.

- [ ] **Step 4: Compléter le barrel, commit**

```ts
export { Avatar } from "./Avatar";
export { Kbd } from "./Kbd";
```

```bash
cd shell
git add src/ui/kit/Avatar.tsx src/ui/kit/Avatar.test.tsx src/ui/kit/Kbd.tsx src/ui/kit/Kbd.test.tsx src/ui/kit/index.ts
git commit -m "feat(shell): kit — Avatar, Kbd"
```

### Task 30: Galerie interne du kit (critère de sortie §10.5.5)

**Files:**
- Create: `shell/src/pages/KitGalleryPage.tsx`, `KitGalleryPage.test.tsx`
- Modify: `shell/src/shell/routes.tsx`
- Modify: `shell/src/ui/kit/index.ts` (réexport de `Gate`)

**Interfaces:**
- Consumes: la totalité du barrel `shell/src/ui/kit` (Tasks 1-29), `useMe`
  depuis `shell/src/api/hooks` (déjà utilisé par `AdminExtensionsPage.tsx`).
- Produces: route `/internal/kit-gallery`, aucune interface consommée par une
  tâche suivante (dernière tâche de contenu du plan).

Gate d'accès : même patron que `shell/src/pages/AdminExtensionsPage.tsx`
(vérifié réellement le 2026-08-30, lignes 1-19 du fichier) — vérification
`meQuery.data?.isAdmin !== true` **dans le composant de page**, pas au niveau
de la route (aucune des routes `/admin/*` existantes ne fait de vérification
au niveau de la route non plus). Pas de tentative d'exclusion par
`import.meta.env.DEV` : non vérifiée contre la version de Vite/Rollup
installée, alors que le patron admin ci-dessus est déjà prouvé et testé.

Ambiance : `tokens.css` définit ses overrides sombres avec le sélecteur
`:root[data-theme="dark"]` (vérifié : `shell/src/styles/tokens.css:112`) —
l'attribut ne peut donc être forcé que sur `document.documentElement`, jamais
sur un `<div>` imbriqué de la page.

- [ ] **Step 1: Écrire le test de la page**

Créer `shell/src/pages/KitGalleryPage.test.tsx` :

```tsx
// SPDX-License-Identifier: Apache-2.0
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { expect, test, vi } from "vitest";
import { KitGalleryPage } from "./KitGalleryPage";

vi.mock("../api/hooks", () => ({
  useMe: () => ({ isLoading: false, data: { isAdmin: true } }),
}));

function renderPage() {
  const client = new QueryClient();
  return render(
    <QueryClientProvider client={client}>
      <KitGalleryPage />
    </QueryClientProvider>,
  );
}

test("rend sans lever pour les primitives du kit", () => {
  expect(() => renderPage()).not.toThrow();
  expect(screen.getByRole("heading", { name: "Galerie de primitives" })).toBeInTheDocument();
});

test("le bouton d'ambiance bascule document.documentElement.dataset.theme", async () => {
  renderPage();
  const toggle = screen.getByRole("button", { name: "Ambiance sombre" });
  expect(document.documentElement.dataset.theme).toBeUndefined();
  await userEvent.click(toggle);
  expect(document.documentElement.dataset.theme).toBe("dark");
  await userEvent.click(screen.getByRole("button", { name: "Ambiance claire" }));
  expect(document.documentElement.dataset.theme).toBe("light");
});
```

- [ ] **Step 2: Vérifier l'échec, implémenter**

Créer `shell/src/pages/KitGalleryPage.tsx` :

```tsx
// SPDX-License-Identifier: Apache-2.0
import { useState } from "react";
import { useMe } from "../api/hooks";
import {
  Avatar,
  Badge,
  Banner,
  Breadcrumb,
  Button,
  Checkbox,
  Chip,
  ColorField,
  Combobox,
  ConfirmDialog,
  DataTable,
  Drawer,
  EmptyState,
  Field,
  Gate,
  IconButton,
  Input,
  Kbd,
  Menu,
  NumberField,
  Panel,
  Popover,
  Progress,
  Radio,
  Section,
  Segmented,
  Select,
  Skeleton,
  Slider,
  Spinner,
  Splitter,
  Switch,
  Table,
  Tabs,
  Textarea,
  Toast,
  Toolbar,
  Tooltip,
  Tree,
} from "../ui/kit";

const WIDTHS = [390, 768, 1280];

function GalleryContent() {
  const [checked, setChecked] = useState(false);
  const [radioValue, setRadioValue] = useState("lecteur");
  const [switchOn, setSwitchOn] = useState(false);
  const [sliderValue, setSliderValue] = useState([50]);
  const [segmentedValue, setSegmentedValue] = useState("quantile");
  const [color, setColor] = useState("#0b6e77");
  const [number, setNumber] = useState(5);
  const [selectValue, setSelectValue] = useState("a");
  const [comboValue, setComboValue] = useState("");
  const [confirmOpen, setConfirmOpen] = useState(false);
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [toastOpen, setToastOpen] = useState(false);

  return (
    <div className="flex flex-col gap-6 p-4">
      <Field label="Titre" htmlFor="gallery-input">
        <Input id="gallery-input" defaultValue="" />
      </Field>
      <Field label="Description" htmlFor="gallery-textarea">
        <Textarea id="gallery-textarea" defaultValue="" />
      </Field>
      <Input disabled placeholder="Désactivé" aria-label="Champ désactivé" />
      <Checkbox aria-label="Case à cocher" checked={checked} onCheckedChange={setChecked} />
      <Radio.Group aria-label="Rôle" value={radioValue} onValueChange={setRadioValue}>
        <Radio.Item value="lecteur">Lecteur</Radio.Item>
        <Radio.Item value="editeur">Éditeur</Radio.Item>
      </Radio.Group>
      <Switch aria-label="Activer" checked={switchOn} onCheckedChange={setSwitchOn} />
      <Slider aria-label="Opacité" value={sliderValue} onValueChange={setSliderValue} />
      <Segmented
        aria-label="Méthode"
        value={segmentedValue}
        onValueChange={setSegmentedValue}
        options={[
          { value: "quantile", label: "Quantile" },
          { value: "jenks", label: "Jenks" },
        ]}
      />
      <ColorField aria-label="Couleur d'accent" value={color} onValueChange={setColor} />
      <NumberField aria-label="Zoom" value={number} onValueChange={setNumber} />
      <Select
        aria-label="Format"
        value={selectValue}
        onValueChange={setSelectValue}
        options={[
          { value: "a", label: "Option A" },
          { value: "b", label: "Option B" },
        ]}
      />
      <Combobox
        aria-label="Collection"
        value={comboValue}
        onValueChange={setComboValue}
        options={[
          { value: "a", label: "Alpha" },
          { value: "b", label: "Beta" },
        ]}
      />
      <Tabs
        defaultValue="info"
        tabs={[
          { value: "info", label: "Informations", content: <p>Contenu</p> },
          { value: "perms", label: "Permissions", content: <p>Contenu</p> },
        ]}
      />
      <Tree nodes={[{ id: "a", label: "Cartes", children: [{ id: "a-1", label: "Carte topo" }] }]} />
      <DataTable
        columns={[{ key: "name", label: "Nom", render: (r: { name: string }) => r.name }]}
        rows={[{ name: "Carte topo" }]}
        getRowId={(r) => r.name}
      />
      <Panel>
        <Section title="Section">
          <p className="text-sm text-ink">Contenu de section</p>
        </Section>
      </Panel>
      <Breadcrumb items={[{ label: "Catalogue", href: "/" }, { label: "Carte topo" }]} />
      <Toolbar.Root aria-label="Actions">
        <Toolbar.Button onClick={() => {}}>Mesurer</Toolbar.Button>
        <Toolbar.Separator />
        <Toolbar.Button onClick={() => {}} disabled>
          Croquis
        </Toolbar.Button>
      </Toolbar.Root>
      <div className="h-32">
        <Splitter first={<div>Gauche</div>} second={<div>Droite</div>} />
      </div>
      <Popover trigger={<Button variant="outline">Ouvrir un popover</Button>}>Contenu du popover</Popover>
      <Menu
        trigger={<Button variant="outline">Menu</Button>}
        items={[
          { label: "Modifier", onSelect: () => {} },
          { label: "Supprimer", onSelect: () => {}, danger: true },
        ]}
      />
      <Tooltip content="Aide contextuelle">
        <IconButton icon={<span>?</span>} aria-label="Aide" size="sm" />
      </Tooltip>
      <Button onClick={() => setConfirmOpen(true)}>Ouvrir ConfirmDialog</Button>
      <ConfirmDialog
        open={confirmOpen}
        title="Supprimer"
        message="Confirmer la suppression ?"
        confirmLabel="Supprimer"
        onConfirm={() => setConfirmOpen(false)}
        onCancel={() => setConfirmOpen(false)}
      />
      <Button onClick={() => setDrawerOpen(true)}>Ouvrir Drawer</Button>
      <Drawer open={drawerOpen} onOpenChange={setDrawerOpen} title="Explorateur">
        <p className="text-sm text-ink">Contenu du panneau</p>
      </Drawer>
      <Button onClick={() => setToastOpen(true)}>Déclencher un toast</Button>
      <Toast open={toastOpen} onOpenChange={setToastOpen} title="Enregistré" description="OK" />
      <Badge variant="ok">Publié</Badge>
      <Chip onRemove={() => {}}>type: map</Chip>
      <Skeleton className="h-4 w-32" />
      <Spinner aria-label="Chargement" />
      <Progress aria-label="Import" value={40} />
      <EmptyState title="Aucun résultat" description="Essayez un autre filtre." />
      <Banner variant="warn">Bannière d'avertissement</Banner>
      <Avatar alt="Tanguy" fallback="TL" />
      <Kbd>⌘K</Kbd>
      <Gate
        on={{ permissions: { read: true, write: false, delete: false, share: false } }}
        can="write"
      >
        <Button>Action verrouillée si non éditeur</Button>
      </Gate>
    </div>
  );
}

export function KitGalleryPage() {
  const meQuery = useMe();
  const [theme, setTheme] = useState<"light" | "dark" | undefined>(undefined);

  if (meQuery.isLoading) {
    return <p role="status">Chargement…</p>;
  }
  if (meQuery.data?.isAdmin !== true) {
    return (
      <p role="alert" className="text-sm text-danger">
        Accès réservé aux administrateurs.
      </p>
    );
  }

  const toggleTheme = () => {
    const next = theme === "dark" ? "light" : "dark";
    setTheme(next);
    document.documentElement.dataset.theme = next;
  };

  return (
    <div className="flex flex-col gap-4 p-4">
      <div className="flex items-center justify-between">
        <h1 className="text-lg font-bold text-ink">Galerie de primitives</h1>
        <Button onClick={toggleTheme}>
          {theme === "dark" ? "Ambiance claire" : "Ambiance sombre"}
        </Button>
      </div>
      <div className="flex flex-col gap-4">
        {WIDTHS.map((width) => (
          <div key={width} className="overflow-x-auto">
            <p className="mb-2 text-xs text-ink-3">{width}px</p>
            <div style={{ width, minWidth: width }} className="border border-dashed border-rule">
              <GalleryContent />
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
```

Note : la signature de `Gate` ci-dessus (`on`/`can`, pas `has`/`onItem`) est
celle réellement vérifiée contre `shell/src/auth/Gate.tsx` et
`shell/src/auth/permissions.ts` (livrés par SP-29a) — `on: HasPermissions`
(`{ permissions: Record<PermissionAction, boolean> }`), `can: PermissionAction`
(`"read" | "write" | "delete" | "share"`).

- [ ] **Step 3: Ajouter la route**

Dans `shell/src/shell/routes.tsx`, ajouter l'import :

```tsx
import { KitGalleryPage } from "../pages/KitGalleryPage";
```

et, dans le même bloc `<Route element={<ProtectedLayout />}>` que
`/admin/harvest`, juste après cette ligne :

```tsx
        <Route path="/internal/kit-gallery" element={<KitGalleryPage />} />
```

- [ ] **Step 4: Vérifier le succès**

Run: `cd shell && npm run test -- src/pages/KitGalleryPage.test.tsx`
Expected: PASS, 2 tests.

- [ ] **Step 5: Compléter le barrel avec Gate (déjà existant, réexport seul)**

Confirmer que `shell/src/ui/kit/index.ts` exporte déjà `Gate` depuis
`../../auth/Gate` (ajouté au Step 3 de Task 2) — aucune modification
supplémentaire nécessaire ici.

- [ ] **Step 6: Commit**

```bash
cd shell
git add src/pages/KitGalleryPage.tsx src/pages/KitGalleryPage.test.tsx src/shell/routes.tsx
git commit -m "feat(shell): galerie interne du kit de primitives (/internal/kit-gallery)"
```

### Task 31: Portes de qualité + revue de branche

**Files:** aucun fichier neuf — vérification uniquement.

- [ ] **Step 1: Suite de tests shell complète**

Run: `cd shell && npm run test`
Expected: tous les tests passent, y compris les ~65 nouveaux fichiers de
test du kit et les fichiers existants inchangés.

- [ ] **Step 2: E2E inchangée**

Run: `cd shell && npm run e2e`
Expected: les 113 specs existantes passent, **aucune n'a été modifiée par ce
plan** (seuls deux Providers invisibles ont été ajoutés à `App.tsx`, Tasks 22
et 26 — s'il y a une régression E2E, chercher d'abord un effet de bord de ces
deux Providers, pas une primitive du kit qu'aucun écran ne consomme encore).

- [ ] **Step 3: Build de production**

Run: `cd shell && rm -rf dist && npm run build`
Expected: succès. Puis vérifier qu'aucune des anciennes implémentations
`ui/{button,card,input,dialog,ConfirmDialog}.tsx` n'a changé de contenu
compilé :

Run: `cd shell && git diff --stat HEAD~30 -- src/ui/button.tsx src/ui/card.tsx src/ui/input.tsx src/ui/dialog.tsx src/ui/ConfirmDialog.tsx`
Expected: sortie vide (aucun de ces cinq fichiers n'a été touché par les 30
tâches précédentes) — un diff non vide ici signale une violation de la
décision de périmètre de ce plan, à corriger avant de continuer.

- [ ] **Step 4: Lint, format, couverture**

Run:
```bash
cd shell
npm run lint
npm run format:check
rm -rf dist dist-export
npm run test -- --coverage
node scripts/check-coverage.mjs coverage/coverage-summary.json .coverage-threshold
```
Expected: aucune erreur de lint/format, couverture ≥ 88 (seuil non
régressif, mesuré après nettoyage de `dist/`/`dist-export/`).

- [ ] **Step 5: pre-commit**

Run: `uvx pre-commit run --all-files`
Expected: les 5 hooks passent.

- [ ] **Step 6: Aucune régénération OpenAPI/TS attendue**

Ce plan ne touche à aucun fichier de `core/` — aucune route, aucun modèle
Pydantic n'a changé. `openapi.json`/`core-schema.d.ts` restent donc
identiques : **c'est le résultat attendu**, pas un oubli (piège n°1 du
dépôt) — ne pas lancer la régénération, un diff apparaîtrait sans rapport
réel avec ce plan.

- [ ] **Step 7: Revue finale de branche**

Suivre `superpowers:subagent-driven-development` (ou
`superpowers:requesting-code-review`) pour une revue de branche complète,
en insistant sur les défauts de croisement entre tâches (piège n°4) propres
à ce plan : cohérence des classes tokenisées entre les ~40 fichiers (aucune
régression `expectTokenizedClasses` cachée par un `className` externe
fusionné avec `cn()` qui réintroduirait une couleur en dur côté appelant),
usage cohérent de `lucide-react` (pas de mélange accidentel avec
`lucide-static`), et confirmation qu'aucun fichier `ui/*` pré-existant n'a
été modifié (Step 3 ci-dessus).

## Self-Review (fait par l'auteur du plan avant remise)

**Couverture de la spec (§10.3) :** Formulaire — `Field`(4), `Input`(4),
`Textarea`(4), `Select`(12), `Combobox`(13), `Checkbox`(5), `Radio`(6),
`Switch`(7), `Slider`(8), `Segmented`(9), `ColorField`(10), `NumberField`(11)
— 12/12. Structure — `Tabs`(14), `Tree`(15), `Table`/`DataTable`(16),
`Panel`/`Section`(17), `Toolbar`(18), `Breadcrumb`(17), `Splitter`(19) —
9/9 (Table+DataTable comptés séparément). Surfaces — `Popover`(20),
`Menu`(21), `Tooltip`(22), `Drawer`(24), `ConfirmDialog`(23) — 5/5. États —
`Badge`(25), `Chip`(25), `Toast`(26), `Skeleton`(27), `EmptyState`(28),
`Banner`(28), `Progress`(27), `Spinner`(27) — 8/8. Divers — `Button`(3),
`IconButton`(3), `Avatar`(29), `Kbd`(29), `Gate`(déjà livré SP-29a,
réexporté Task 2/30) — 5/5. **Total : 39 primitives nommées + Gate déjà
existant = 40, conforme au compte de la spec §10.5.5.**

**Balayage des placeholders :** aucune occurrence de "TBD"/"à définir"/
"gérer les cas limites" dans les 31 tâches ; chaque étape de code contient
l'implémentation réelle, chaque test contient des assertions concrètes.
Une note de vérification explicite reste volontairement ouverte : le rôle
ARIA réel rendu par `@radix-ui/react-toggle-group` (Task 9, Step 3) dépend
de la sortie du test une fois le paquet installé, pas d'un fichier lisible
maintenant — ce n'est pas un placeholder de contenu, mais une instruction de
vérification contre la source réelle avant de considérer l'étape terminée,
cohérente avec le piège n°3 documenté par ce dépôt. La signature de `Gate`
(Task 30, Step 2), initialement laissée à vérifier pour la même raison, a
depuis été relue contre `shell/src/auth/{Gate,permissions}.tsx` réels et
corrigée dans le plan (`on`/`can`, pas `has`/`onItem`).

**Cohérence des types/signatures entre tâches :** `Dialog` (Task 23,
`open/onOpenChange/title/children`) est consommé à l'identique par `Drawer`
(Task 24, même primitive Radix, props locales `side` en plus) — `Drawer`
n'importe pas `Dialog` (fichier séparé par choix explicite, cf. Task 24) mais
réutilise la même forme de props, vérifié cohérent. `ConfirmDialog` (Task 23)
reproduit exactement les sept props de l'ancien
`shell/src/ui/ConfirmDialog.tsx` (`open, title, message, confirmLabel,
onConfirm, onCancel, pending`), condition posée dans le contexte du plan.
`Checkbox` (Task 5) est consommé par `DataTable` (Task 16) avec la signature
`checked`/`onCheckedChange` définie à la Task 5, sans divergence. `Button`
(Task 3) est consommé par `IconButton` (Task 3, même tâche),
`NumberField` (Task 11), `ConfirmDialog`/`Drawer` (Tasks 23-24) et la galerie
(Task 30) avec les mêmes `variant`/`size` que définis à la Task 3.
