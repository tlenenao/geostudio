# SP-29a Task 1 — Spike : bibliothèque de primitives headless

Relevé de mesures reproductibles, exécuté le 2026-08-29 dans une branche
jetable `spike/primitives-sp29a` (supprimée après le relevé), sur
`shell/` (`react@19.2.7`). Aucune trace de code ne subsiste dans `dev` — seul
ce document est commité.

## Candidats écartés et pourquoi

Aucun des trois candidats n'a été écarté par les critères de la Step 2
(React 19 + licence compatible Apache-2.0) : les trois passent.

Sortie réelle de `npm view` (2026-08-29) :

| Paquet | Version | `peerDependencies.react` | Licence |
|---|---|---|---|
| `@radix-ui/react-select` | 2.3.7 | `^16.8 \|\| ^17.0 \|\| ^18.0 \|\| ^19.0 \|\| ^19.0.0-rc` | MIT |
| `@base-ui-components/react` | 1.0.0-rc.0 | `^17 \|\| ^18 \|\| ^19` | MIT |
| `@ark-ui/react` | 5.39.1 | `>=18.0.0` | MIT |

Les trois admettent React 19 et sont MIT (compatible Apache-2.0). Radix a
donc été retenu conformément au candidat de départ désigné par le brief
(§Contexte), faute de critère de cette spike forçant un report vers une
alternative. Base UI (`1.0.0-rc.0`, encore en release candidate) et Ark UI
restent des alternatives viables si Radix posait un problème non anticipé
en usage réel (SP-29b) — à re-mesurer alors, pas à re-débattre ici.

Note annexe (non un critère d'élimination, mais réel et vérifié) : Radix
distribue chaque primitive comme paquet séparé (`@radix-ui/react-select`,
`@radix-ui/react-popover`, `@radix-ui/react-tabs`, …), pas un seul paquet
« tout compris » comme `@ark-ui/react` ou `@base-ui-components/react` — ce
qui explique pourquoi le surcoût mesuré plus bas isole proprement le coût
d'un seul composant.

## Bibliothèque retenue, version épinglée

**Radix UI Primitives**, un paquet par composant, versions exactes
installées et vérifiées (`node -e "require('.../package.json').version"`) :

- `@radix-ui/react-select@2.3.7`
- `@radix-ui/react-popover@1.1.23`
- `@radix-ui/react-tabs@1.1.21`

## Surcoût mesuré en octets

Mesuré avec `cd shell && rm -rf dist && npm run build && du -sb dist` +
`find dist/assets -name '*.js' -printf '%f %s\n' | sort -k2 -rn | head -5`.

**Référence (avant tout candidat installé) :**

| | octets |
|---|---|
| `dist` total | 3 957 384 |
| `index-oO_zfLhd.js` (chunk principal) | 3 030 774 |
| `EChart-0BJGybqr.js` | 819 495 |

**Avec `@radix-ui/react-select` importé et rendu** (`Popover`/`Tabs`
installés en `package.json` mais **non importés** nulle part — un composant
`src/spike/SpikeSelect.tsx` monté sur une route temporaire `/spike`) :

| | octets |
|---|---|
| `dist` total | 4 042 321 |
| `index-C1soodbI.js` (chunk principal) | 3 115 711 |
| `EChart-B1u0iXRi.js` (inchangé) | 819 495 |

**Delta : +84 937 octets bruts** (soit +29,10 kB gzip : gzip du chunk
principal passe de 843,52 kB à 872,62 kB dans la sortie `vite build`) pour
**un seul composant Select**. Vérifié par grep que le code de
`@radix-ui/react-popover`/`@radix-ui/react-tabs` n'apparaît **pas** dans le
bundle produit (`grep -c "react-popover\|react-tabs" dist/assets/index-*.js`
→ 0) : installés mais jamais importés, ils sont totalement absents du
build — le tree-shaking de Vite fonctionne comme attendu, la mesure
ci-dessus isole donc bien le coût de `Select` seul, pas des trois
primitives cumulées.

## Licence

MIT pour les trois paquets Radix installés (vérifié par `npm view … license`
et présent dans `node_modules/@radix-ui/react-*/LICENSE`) — compatible avec
Apache-2.0.

## Rendu headless : verdict

**Ça marche.** Vérifié en conditions réelles :

1. `npm run dev` démarré avec un `.env` temporaire minimal
   (`VITE_AUTH_MODE=mock`, `VITE_CORE_URL=https://core.test` — requis par
   `src/config.ts:loadConfig`, sans rapport avec Radix) et une route `/spike`
   temporaire montant `SpikeSelect` (Select fermé, valeur par défaut
   `"b"`, hors du `ProtectedLayout`/`RequireAuth`).
2. `npx playwright screenshot --viewport-size=900,600 http://localhost:5173/spike …`
   (Chromium headless présent et fonctionnel dans cet environnement,
   `playwright 1.62.1`) : le `Select` **fermé** se rend correctement
   (« Option B ▾ » visible).
3. Script Playwright (`page.click('[data-testid="spike-select-trigger"]')`
   — un clic synthétique réel, pas un forçage JS de l'état ouvert) suivi
   d'un `page.screenshot({ fullPage: true })` — **exactement** l'appel
   utilisé par le worker d'export réel
   (`core/app/export/rendering.py:36`, `page.screenshot(full_page=True)`) :
   les trois options (« Option A », « Option B », « Option C ») apparaissent
   dans la capture. Le clic ouvre le contenu — ce n'est pas une interaction
   hover-only.
4. Inspection DOM (`page.evaluate`) : le contenu ouvert du `Select`
   (`[data-testid="spike-select-content"]`) est un **enfant direct de
   `<body>`, pas de `#root`** (`document.getElementById('root').contains(el)`
   → `false`) — Radix porte bien son contenu hors de l'arbre React monté,
   comme le redoutait le brief. **Mais** ce portail ne casse pas la capture
   Playwright : `page.screenshot()` (avec ou sans `fullPage: true`) rend
   **toute la page visible**, quel que soit le sous-arbre DOM d'appartenance
   d'un élément — la capture n'est pas bornée à `#root`. Le risque anticipé
   (« portail hors du conteneur capturé ») ne se matérialise donc pas ici,
   *tant que le worker capture par `page.screenshot()` et non par un
   `locator('#root').screenshot()` scopé — ce qui est le cas actuel de
   `core/app/export/rendering.py`.*
5. Fait annexe utile pour SP-29b : `Tabs` (`@radix-ui/react-tabs`) ne
   porte **pas** son contenu — `TabsContent` reste dans le flux normal du
   DOM (pas de `Portal` dans ses exports, cf. squelette ci-dessous) ; seuls
   `Select` et `Popover` utilisent un portail.

## Forme de `@theme` supportée

`tailwindcss@4.3.3` (`npm ls tailwindcss` → `@tailwindcss/vite@4.3.3` →
`tailwindcss@4.3.3`, dédupliqué).

`@theme inline` **existe et est un mot-clé de premier ordre** dans cette
version : `node_modules/tailwindcss/dist/lib.d.mts` définit
`ThemeOptions.INLINE` dans l'enum interne du moteur, et le propre
`theme.css` du paquet l'utilise lui-même (`@theme default inline reference`,
ligne 503).

Vérifié en compilant réellement un CSS de test à travers le moteur installé
(`import { compile } from "tailwindcss"`, avec un `loadStylesheet` qui
résout vraiment `@import "tailwindcss"` vers
`node_modules/tailwindcss/index.css`) :

```css
@import "tailwindcss";
:root {
  --gs-color-primary: #336699;
}
@theme inline {
  --color-primary: var(--gs-color-primary);
}
```

compilé avec les candidats `["bg-primary", "text-primary"]` produit
réellement :

```css
@layer utilities {
  .bg-primary {
    background-color: var(--gs-color-primary);
  }
  .text-primary {
    color: var(--gs-color-primary);
  }
}
:root {
  --gs-color-primary: #336699;
}
```

**Confirmé : la construction `@theme inline { --color-x: var(--gs-x) }`
fonctionne telle quelle** dans la version installée — les utilitaires
générés référencent directement `var(--gs-color-primary)` au lieu de la
valeur résolue, ce qui est précisément le mécanisme qui permet de
commuter les tokens entre ambiances (changer `--gs-color-primary` sur
`:root`/`[data-theme]` sans recompiler). **La prémisse du plan de Task 9
est correcte pour cette version : rien à corriger.**

## Squelettes réels de `Select`, `Popover`, `Tabs`

Les README des trois paquets installés (`node_modules/@radix-ui/react-{select,popover,tabs}/README.md`)
sont des stubs de deux lignes pointant vers la doc en ligne — **pas** de
squelette de composition dedans (déviation par rapport à la prémisse du
brief « copier depuis le README »). Squelettes reconstruits à partir des
exports réels des `.d.mts` installés (noms de composants et props
vérifiés, pas de mémoire) :

**Select** (`@radix-ui/react-select@2.3.7`, exports vérifiés dans
`dist/index.d.mts` : `Root, Trigger, Value, Icon, Portal, Content, Viewport,
Group, Label, Item, ItemText, ItemIndicator, ScrollUpButton,
ScrollDownButton, Separator, Arrow`) :

```tsx
import * as Select from "@radix-ui/react-select";

<Select.Root defaultValue="b">
  <Select.Trigger aria-label="…">
    <Select.Value placeholder="Choisir…" />
    <Select.Icon>▾</Select.Icon>
  </Select.Trigger>
  <Select.Portal>
    <Select.Content>
      <Select.Viewport>
        <Select.Item value="a">
          <Select.ItemText>Option A</Select.ItemText>
          <Select.ItemIndicator>✓</Select.ItemIndicator>
        </Select.Item>
      </Select.Viewport>
    </Select.Content>
  </Select.Portal>
</Select.Root>;
```

**Popover** (`@radix-ui/react-popover@1.1.23`, exports vérifiés :
`Root, Anchor, Trigger, Portal, Content, Close, Arrow`) :

```tsx
import * as Popover from "@radix-ui/react-popover";

<Popover.Root>
  <Popover.Trigger>Ouvrir</Popover.Trigger>
  <Popover.Portal>
    <Popover.Content>
      Contenu du popover
      <Popover.Close>Fermer</Popover.Close>
      <Popover.Arrow />
    </Popover.Content>
  </Popover.Portal>
</Popover.Root>;
```

**Tabs** (`@radix-ui/react-tabs@1.1.21`, exports vérifiés :
`Root, List, Trigger, Content` — **pas de `Portal`**, `Content` reste dans
le flux DOM normal) :

```tsx
import * as Tabs from "@radix-ui/react-tabs";

<Tabs.Root defaultValue="tab1">
  <Tabs.List>
    <Tabs.Trigger value="tab1">Onglet 1</Tabs.Trigger>
    <Tabs.Trigger value="tab2">Onglet 2</Tabs.Trigger>
  </Tabs.List>
  <Tabs.Content value="tab1">Contenu 1</Tabs.Content>
  <Tabs.Content value="tab2">Contenu 2</Tabs.Content>
</Tabs.Root>;
```
