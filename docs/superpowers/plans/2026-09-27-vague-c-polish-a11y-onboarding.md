# Vague C : polish, a11y AA, perf perçue, onboarding — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fermer les 27 défauts (D-codes) de
`docs/superpowers/specs/2026-09-27-vague-c-polish-a11y-onboarding-design.md`
sur 6 sous-chantiers indépendants (SP-C1 → SP-C6) : accessibilité
clavier/focus du builder et de la carte (SP-C1), couverture mécanique de
l'audit a11y automatisé + respect de `prefers-reduced-motion` (SP-C2),
cohérence visuelle du design system — tailles de texte, segmented-control,
dernières pages `ui/*` legacy (SP-C3), onboarding — palette de commandes,
aide contextuelle, visibilité des quotas (SP-C4), ergonomie de SQL Lab —
éditeur de code, erreurs DuckDB lisibles (SP-C5), et finitions transverses
de cohérence texte/carte — pluriel grammatical, widget carte, pipeline en
lecture seule, historique du copilote, déclenchement manuel d'alerte
(SP-C6).

**Architecture:** Shell React seul pour l'essentiel des tâches (la clôture, Tâche 40, mise à part)
(corrections ciblées réutilisant les primitives `ui/kit/*` et les patrons
déjà en place, aucun nouveau moteur) ; deux tâches seulement touchent le
cœur : Tâche 18 (`UsageSnapshotResponse` étendu, SP-C4/D08) et Tâche 39
(nouvelle route `POST /alerts/{item_id}/evaluate`, SP-C6/D04) — chacune
suivie de sa propre régénération OpenAPI/TS.

**Tech Stack:** React 18 + TypeScript, Vitest + Testing Library +
`@testing-library/user-event`, Playwright + `@axe-core/playwright`, Radix
UI (`ui/kit/*`), Tailwind v4 (`@theme inline`, `shell/src/styles/tokens.css`),
i18n maison (`t()` / `catalog.fr.ts`, pas de react-i18next), FastAPI +
Pydantic + SQLAlchemy (cœur, Tâches 18-20 et 39 seulement),
`@uiw/react-codemirror` + `@codemirror/lang-sql` (nouvelle dépendance,
Tâches 25-26).

## Global Constraints

- TDD rouge → vert systématique sur chaque tâche : écrire le test, le
  lancer et constater l'échec, implémenter, relancer et constater le
  succès.
- Commits conventionnels, petits, un sujet par commit (`feat(shell): …`,
  `fix(shell): …`, `test(shell): …`, ou sans scope `shell`/`core` pour un
  commit touchant les deux). Chaque message se termine par
  `Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>`.
- Tout texte visible ou `aria-label` nouveau passe par `t("clé", {...})` +
  une entrée neuve dans `shell/src/i18n/catalog.fr.ts` — jamais de chaîne
  française en dur (`npm run lint` fait échouer `lint:i18n` sinon).
  `MessageKey` est dérivé de `typeof fr` : une clé absente du catalogue est
  une erreur de compilation dès qu'elle est utilisée.
- Stub d'API navigateur (`window.matchMedia`, `ResizeObserver`,
  `hasPointerCapture`, `scrollIntoView`, `PointerEvent`…) toujours **local
  au fichier de test** — jamais `shell/src/test/setup.ts` (piège n°10 de
  `CLAUDE.md` : jsdom ne les implémente pas, un stub global y a déjà cassé
  des tests sans rapport).
- Un correctif de filet de test (Tâches 3, 9 notamment) doit être vérifié
  par falsification quand c'est bon marché de le faire : injecter
  délibérément le défaut visé, confirmer que le test échoue, puis retirer
  — « les tests passent toujours » ne prouve rien seul (piège n°10 de
  `CLAUDE.md`).
- Toute route/modèle cœur modifié (Tâches 18-20, 39) déclenche la
  régénération OpenAPI/TS (piège n°1 de `CLAUDE.md`) :
  ```bash
  cd core && PYTHONPATH=. \
    CORE_SECRETS_MASTER_KEY="AAECAwQFBgcICQoLDA0ODxAREhMUFRYXGBkaGxwdHh8=" \
    uv run python scripts/export_openapi.py openapi.json
  cd ../shell && npm run gen:api-types
  ```
  Diff vide attendu et légitime uniquement si la surface est derrière un
  flag éteint en CI — non applicable ici (aucune des deux tâches n'est
  gardée par un flag).
- Toute nouvelle surface REST/MCP/route shell doit être ajoutée à
  `docs/revue/inventaire-fonctionnalites.jsonl` avant de clore la tâche qui
  l'introduit (porte CI `core/tests/test_feature_inventory.py`). Seule la
  Tâche 39 (D04) introduit une surface réellement nouvelle ; la Tâche 18
  étend une route déjà inventoriée (pas de nouvelle entrée, vérifié en
  lisant le test — il compare des `surface_id` route+méthode, indifférent
  à la forme de la réponse).
- `cd shell && npx vitest run` doit rester entièrement vert, couverture ≥
  seuil (`shell/.coverage-threshold`, 88 — mesurer après nettoyage de
  `dist/`/`dist-export/`). `cd core && uv run pytest` doit rester
  entièrement vert, couverture ≥ seuil (`core/.coverage-threshold`, 85) sur
  les tâches qui touchent `core/`.
- `npm run lint` (shell) doit rester vert à la fin de chaque tâche qui le
  touche — ne jamais câbler un nouveau script de garde-fou (Tâche 12) tant
  que le code qu'il vérifie n'est pas déjà conforme. Côté cœur :
  `uv run ruff check . && uv run ruff format --check . && uv run lint-imports`.
- Le mode `template` d'un popup carte (gabarit libre `${expr}`) reste hors
  périmètre de tout formatage fr-FR (Tâche 30) — seuls le mode `fields` et
  le widget table le sont ; documenté en commentaire au point d'insertion.
- Docs/commentaires en français, identifiants/code en anglais (doctrine du
  dépôt).

## Ordre d'exécution

Ordre suggéré par la spec (« C1+C2 → C3 → C4∥C5 → C6 »), reflété par la
numérotation continue des tâches :

1. **SP-C1 (Tâches 1-5)** puis **SP-C2 (Tâches 6-10)** — a11y clavier/focus
   puis couverture d'audit + mouvement. Aucune dépendance croisée, mais
   même famille de défauts (a11y) : les traiter dans cet ordre garde le
   contexte a11y frais d'une tranche à l'autre.
2. **SP-C3 (Tâches 11-17)** — cohérence visuelle du design system,
   indépendant des deux précédents.
3. **SP-C4 (Tâches 18-22)** en parallèle de **SP-C5 (Tâches 23-27)** —
   onboarding et SQL Lab n'ont aucune dépendance croisée entre eux. À
   l'intérieur de SP-C4 : Tâche 18 (D08 cœur) avant 19 (régénération
   OpenAPI/TS) avant 20 (D08 shell), puis 21 (D07), puis 22 (D49) — D49
   touche `SqlLabPage.tsx` (ajout d'une aide contextuelle en tête de
   formulaire) mais des lignes différentes de celles touchées par SP-C5
   (Tâches 23-26, affichage d'erreur et éditeur de requête) : **ne pas
   exécuter la Tâche 22 et les Tâches 23-26 strictement en parallèle sur ce
   fichier précis** (même si SP-C4 et SP-C5 restent par ailleurs
   indépendants) — les enchaîner en série sur `SqlLabPage.tsx` évite tout
   conflit de merge, en committant chacune avant de démarrer la suivante
   sur ce fichier.
4. **SP-C6 (Tâches 28-39)** en dernier — le plus mécanique/indépendant,
   aucune dépendance croisée avec les 5 chantiers précédents (vérifié :
   SP-C6 ne touche pas `SqlLabPage.tsx`, ni aucun fichier des Tâches 1-27).
5. **Tâche 40** — clôture : suites complètes, régénération, documentation.

---


## État réel du code vérifié avant rédaction (écarts avec la spec)

- `shell/src/builder/widgets/form.tsx` : `errorId`/`errorProps` sont bien
  aux lignes 385-386 (comme annoncé), mais les branches de `FieldInput`
  sont décalées de quelques lignes par rapport à la spec (boolean
  398-410, integer/number 411-424, date 425-438, datetime 439-452, enum
  453-472, texte 473-485 ; attachment 388-397 exclu comme prévu). Le
  contenu et la structure sont identiques à ce que la spec décrit, seuls
  les numéros de ligne exacts diffèrent légèrement — le plan ci-dessous
  utilise les numéros réels.
- `FieldOverrides` : `reorder()` (lignes 58-64), poignée `⠿` (lignes
  87-89), tout confirmé identique à la spec.
- Le `<form>` de `FormComponent` est bien sans `noValidate` (lignes
  647-650 réelles, spec disait ligne 647 — juste le tag d'ouverture).
- `shell/src/map/MapPopup.tsx` : `role="dialog"` bien ligne 42 (41 dans
  la version lue ici, décalage d'une ligne dû à un commentaire), composant
  purement présentationnel confirmé, aucun `useEffect`/`ref` existant.
- **Écart réel avec la spec** : `shell/src/ui/kit/Drawer.test.tsx`
  **existe déjà** (la spec envisageait de le créer). Il contient déjà un
  test « Échap appelle onOpenChange(false) » mais **aucun test de
  restauration de focus**. La Tâche 3 ajoute son test au fichier
  existant, elle n'en crée pas un nouveau.
- `Drawer.tsx` n'a toujours aucune surcharge de `onCloseAutoFocus`/
  `onEscapeKeyDown`/`modal` — confirmé, cohérent avec la spec.
- `catalog.fr.ts` n'est **pas** strictement alphabétique : les clés sont
  groupées par usage (ex. toutes les clés `*Aria` de `FieldOverrides` se
  suivent, lignes 886-891, sans ordre alphabétique interne — `hideFieldAria`
  précède `requireFieldAria` qui précède `minFieldAria`/`maxFieldAria`/
  `patternFieldAria`). Les nouvelles clés `moveFieldUpAria`/
  `moveFieldDownAria` s'insèrent dans ce même groupe, après
  `requireFieldAria`, avant `minFieldAria` — pas de recherche d'ordre
  alphabétique global à faire.
- `shell/src/shell/NewItemButton.tsx`/`.test.tsx` fournissent un vrai
  patron de « trigger externe + `Drawer` contrôlé » déjà en production
  (bouton « Nouveau » + `usePanelTrigger`), utile pour concevoir le test
  de falsification de la Tâche 3 (bien qu'il ne soit *pas* modifié ni
  requis par cette tâche — le test ajouté à `Drawer.test.tsx` construit
  son propre déclencheur minimal, cf. Tâche 3).

---

## Tâche 1 — SP-C1 : D32 — `aria-required` sur `FieldInput` + `noValidate` sur le `<form>`

**Files:**
- Modify: `shell/src/builder/widgets/form.tsx:365-485` (fonction
  `FieldInput`), `shell/src/builder/widgets/form.tsx:647-650` (balise
  `<form>` de `FormComponent`)
- Test: `shell/src/builder/widgets/form.test.tsx`

**Interfaces:**
- Consumes : `FormField.required: boolean` (déjà existant, type défini
  ligne 22 du fichier), `t(key, params?)` de `../../i18n`.
- Produces : rien de nouveau consommé par une tâche suivante de ce plan
  (Tâche 5/filet consomme le même comportement, pas une nouvelle
  fonction).

- [ ] **Step 1: Écrire le test qui échoue (champ requis texte → `aria-required`)**

Ajouter à la fin de `shell/src/builder/widgets/form.test.tsx` (après le
dernier test du fichier, `"un champ list n'apparaît ni dans le rendu ni
dans la soumission du formulaire"`) :

```tsx
test("D32 : un champ requis (texte) porte aria-required, un champ non requis ne le porte pas", () => {
  renderForm();
  expect(screen.getByLabelText("Titre")).toHaveAttribute("aria-required", "true");
  expect(screen.getByLabelText("Victimes")).not.toHaveAttribute("aria-required");
});

test("D32 : le <form> porte noValidate (garde contre le court-circuit de la validation navigateur native)", () => {
  const { container } = renderForm();
  expect(container.querySelector("form")).toHaveAttribute("novalidate");
});
```

`renderForm()` sans argument utilise déjà `visibleFields` (défini plus
haut dans ce même fichier) : `titre` (string, `required: true`),
`gravite` (enum, `required: true`), `nb_victimes` (integer, label
« Victimes », `required: false`).

- [ ] **Step 2: Lancer les tests et constater l'échec**

```bash
cd shell && npx vitest run src/builder/widgets/form.test.tsx -t "D32"
```

Attendu : 2 échecs — `aria-required` absent sur "Titre" (pas encore posé),
et `container.querySelector("form")` n'a pas l'attribut `novalidate`.

- [ ] **Step 3: Ajouter `requiredProps` et le spread sur les 6 branches non-attachment de `FieldInput`**

Remplacer toute la fonction `FieldInput` (lignes 365-485 actuelles) par :

```tsx
function FieldInput({
  field,
  value,
  onChange,
  onBlur,
  collectionId,
  fid,
  client,
  error,
}: {
  field: FormField;
  value: unknown;
  onChange: (v: unknown) => void;
  onBlur: () => void;
  collectionId: string;
  fid: string | null;
  client: ReturnType<typeof useItemClient>;
  error: string | null;
}) {
  const fieldId = `field-${field.name}`;
  const errorId = `field-${field.name}-error`;
  const errorProps = error ? { "aria-invalid": "true" as const, "aria-describedby": errorId } : {};
  // D32 : `aria-required` seul (jamais l'attribut natif `required`) —
  // annonce le caractère requis aux lecteurs d'écran sans réactiver la
  // validation navigateur native, qui court-circuiterait le flux
  // touched/validateField existant et, pour la branche boolean,
  // forcerait `checked=true` alors que `false` explicite est une valeur
  // valide (validateField, ligne 221).
  const requiredProps = field.required ? { "aria-required": "true" as const } : {};

  if (field.type === "attachment") {
    return (
      <AttachmentFieldInput
        collectionId={collectionId}
        fid={fid}
        fieldKey={field.name}
        client={client}
      />
    );
  }
  if (field.type === "boolean") {
    return (
      <input
        id={fieldId}
        type="checkbox"
        aria-label={field.label}
        checked={Boolean(value)}
        onChange={(e) => onChange(e.target.checked)}
        onBlur={onBlur}
        {...errorProps}
        {...requiredProps}
      />
    );
  }
  if (field.type === "integer" || field.type === "number") {
    return (
      <input
        id={fieldId}
        type="number"
        aria-label={field.label}
        className={fieldInputCls}
        value={value === undefined ? "" : String(value)}
        onChange={(e) => onChange(e.target.value === "" ? undefined : Number(e.target.value))}
        onBlur={onBlur}
        {...errorProps}
        {...requiredProps}
      />
    );
  }
  if (field.type === "date") {
    return (
      <input
        id={fieldId}
        type="date"
        aria-label={field.label}
        className={fieldInputCls}
        value={String(value ?? "")}
        onChange={(e) => onChange(e.target.value)}
        onBlur={onBlur}
        {...errorProps}
        {...requiredProps}
      />
    );
  }
  if (field.type === "datetime") {
    return (
      <input
        id={fieldId}
        type="datetime-local"
        aria-label={field.label}
        className={fieldInputCls}
        value={String(value ?? "")}
        onChange={(e) => onChange(e.target.value)}
        onBlur={onBlur}
        {...errorProps}
        {...requiredProps}
      />
    );
  }
  if (field.type === "enum") {
    return (
      <select
        id={fieldId}
        aria-label={field.label}
        className={fieldInputCls}
        value={String(value ?? "")}
        onChange={(e) => onChange(e.target.value)}
        onBlur={onBlur}
        {...errorProps}
        {...requiredProps}
      >
        <option value=""></option>
        {(field.values ?? []).map((v) => (
          <option key={v} value={v}>
            {v}
          </option>
        ))}
      </select>
    );
  }
  return (
    <input
      id={fieldId}
      type="text"
      aria-label={field.label}
      className={fieldInputCls}
      value={String(value ?? "")}
      onChange={(e) => onChange(e.target.value)}
      onBlur={onBlur}
      {...errorProps}
      {...requiredProps}
    />
  );
}
```

- [ ] **Step 4: Ajouter `noValidate` sur le `<form>` de `FormComponent`**

Dans `FormComponent`, remplacer :

```tsx
    <form
      className="flex h-full flex-col gap-2 overflow-auto text-sm"
      onSubmit={(e) => void handleSubmit(e)}
    >
```

par :

```tsx
    <form
      className="flex h-full flex-col gap-2 overflow-auto text-sm"
      onSubmit={(e) => void handleSubmit(e)}
      noValidate
    >
```

- [ ] **Step 5: Relancer les tests et constater le succès**

```bash
cd shell && npx vitest run src/builder/widgets/form.test.tsx -t "D32"
```

Attendu : PASS (2 tests).

- [ ] **Step 6: Lancer tout le fichier pour vérifier l'absence de régression**

```bash
cd shell && npx vitest run src/builder/widgets/form.test.tsx
```

Attendu : tous les tests du fichier passent (y compris les tests
existants sur `aria-invalid`/`aria-describedby`, inchangés par ce
correctif).

- [ ] **Step 7: Commit**

```bash
cd shell && git add src/builder/widgets/form.tsx src/builder/widgets/form.test.tsx
git commit -m "$(cat <<'EOF'
fix(shell): pose aria-required sur les champs requis du widget Formulaire (D32)

FieldInput annonçait le caractère requis d'un champ uniquement par un
suffixe visuel (" *"), jamais aux technologies d'assistance. Ajoute
aria-required (jamais l'attribut natif required, qui court-circuiterait
la validation existante et forcerait `checked=true` sur un booléen
explicitement false) sur les 6 branches non-attachment, et noValidate
sur le <form> en garde-fou.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
)"
```

---

## Tâche 2 — SP-C1 : D41 — Échap ferme la popup carte, focus posé à l'ouverture

**Files:**
- Modify: `shell/src/map/MapPopup.tsx`
- Test: `shell/src/map/MapPopup.test.tsx`

**Interfaces:**
- Consumes : rien de nouveau — `onClose: () => void` déjà une prop
  existante de `MapPopup`.
- Produces : aucun changement d'API publique de `MapPopup` (mêmes props),
  donc aucun appelant (`MapView.tsx`) à modifier.

- [ ] **Step 1: Écrire les tests qui échouent**

Ajouter à la fin de `shell/src/map/MapPopup.test.tsx` :

```tsx
test("D41 : Échap ferme la popup", async () => {
  const onClose = vi.fn();
  render(
    <MapPopup
      content={{ title: "Tulle", rows: [{ label: "Habitants", value: "14000" }], html: null }}
      x={0}
      y={0}
      onClose={onClose}
    />,
  );
  await userEvent.keyboard("{Escape}");
  expect(onClose).toHaveBeenCalledOnce();
});

test("D41 : le focus est posé sur le premier élément interactif (bouton Fermer) au montage", () => {
  render(
    <MapPopup
      content={{ title: "Tulle", rows: [{ label: "Habitants", value: "14000" }], html: null }}
      x={0}
      y={0}
      onClose={() => {}}
    />,
  );
  expect(screen.getByRole("button", { name: "Fermer" })).toHaveFocus();
});
```

- [ ] **Step 2: Lancer les tests et constater l'échec**

```bash
cd shell && npx vitest run src/map/MapPopup.test.tsx -t "D41"
```

Attendu : 2 échecs — `onClose` jamais appelé sur Échap (aucun listener
clavier), et le bouton Fermer n'a pas le focus (aucun focus géré au
montage).

- [ ] **Step 3: Implémenter le `useEffect` de fermeture/focus clavier**

Dans `shell/src/map/MapPopup.tsx`, ajouter l'import `useEffect`/`useRef` :

```tsx
// SPDX-License-Identifier: Apache-2.0
import { useEffect, useRef } from "react";
import type { AttachmentSummary } from "../api/types";
import type { PopupContent } from "./popupContent";
import { t } from "../i18n";
```

Puis, dans le corps du composant, juste après le calcul de `hasHtml`/
`empty` (avant le `return`), ajouter :

```tsx
  const containerRef = useRef<HTMLDivElement>(null);

  // D41 : composant présentationnel sans Radix (positionné en x/y absolus
  // sur une feature carte, coexiste avec l'interaction carte derrière) —
  // pas de FocusScope automatique. Gère lui-même Échap et le focus initial
  // au montage : premier élément focusable réel (bouton Fermer en
  // pratique, toujours en tête du DOM). Pas de restauration de focus à la
  // fermeture : le déclencheur est un clic sur une feature carte, une
  // cible de restauration ambiguë (hors périmètre D41, cf. spec SP-C1).
  useEffect(() => {
    containerRef.current?.querySelector<HTMLElement>("button, a, [tabindex]")?.focus();
    function handleKeyDown(e: KeyboardEvent) {
      if (e.key === "Escape") onClose();
    }
    document.addEventListener("keydown", handleKeyDown);
    return () => document.removeEventListener("keydown", handleKeyDown);
    // eslint-disable-next-line react-hooks/exhaustive-deps -- volontairement au montage seul (cf. commentaire ci-dessus)
  }, []);
```

Puis poser `ref={containerRef}` sur le conteneur `role="dialog"` :

```tsx
    <div
      ref={containerRef}
      role="dialog"
      aria-label={t("mapPopup.attributesAria")}
      className="absolute z-20 max-h-64 max-w-xs -translate-x-1/2 -translate-y-full overflow-auto rounded-md bg-surface p-2 text-xs text-ink shadow-lg"
      style={{ left: `${x}px`, top: `${y}px` }}
    >
```

- [ ] **Step 4: Relancer les tests et constater le succès**

```bash
cd shell && npx vitest run src/map/MapPopup.test.tsx -t "D41"
```

Attendu : PASS (2 tests).

- [ ] **Step 5: Lancer tout le fichier pour vérifier l'absence de régression**

```bash
cd shell && npx vitest run src/map/MapPopup.test.tsx
```

Attendu : tous les tests du fichier passent (y compris le test existant
« closes on the close button », le clic manuel n'étant pas affecté par
l'ajout du listener clavier).

- [ ] **Step 6: Commit**

```bash
cd shell && git add src/map/MapPopup.tsx src/map/MapPopup.test.tsx
git commit -m "$(cat <<'EOF'
fix(shell): Échap ferme la popup carte et pose le focus à l'ouverture (D41)

MapPopup est un composant présentationnel sans Radix (positionnement x/y
absolu sur une feature carte) : aucune touche clavier ne la fermait et le
focus n'était jamais posé à son apparition. Ajoute un useEffect local
(listener Échap + focus du premier élément interactif, sans restauration
au déclencheur — cible ambiguë, un clic sur la carte).

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
)"
```

---

## Tâche 3 — SP-C1 : D48 — filet de falsification sur la restauration de focus du `Drawer`

**Files:**
- Test: `shell/src/ui/kit/Drawer.test.tsx` (existe déjà — ce fichier est
  modifié, pas recréé)
- Modify (conditionnel, seulement si le test échoue) :
  `shell/src/ui/kit/Drawer.tsx`

**Interfaces:**
- Consumes : `Drawer` déjà exporté (`open`, `onOpenChange`, `title`,
  `side?`, `id?`, `children`).
- Produces : aucune nouvelle API. Ce test devient le filet de
  non-régression permanent pour la restauration de focus (table des
  filets transverses de la spec).

Le diagnostic (D48) affirmait, par test clavier manuel, que le focus ne
revient pas au déclencheur après une fermeture au clavier (Échap) d'un
`Drawer`. La lecture statique de `Drawer.tsx` ne trouve **aucune**
surcharge du comportement par défaut de Radix (`onCloseAutoFocus`,
`modal={false}`, `onEscapeKeyDown` : zéro occurrence dans tout le dépôt) —
Radix restaure normalement le focus via son `FocusScope` interne, sans
avoir besoin d'un `DialogPrimitive.Trigger` explicite (la restauration
porte sur l'élément qui avait le focus au moment de l'ouverture, pas sur
un composant Trigger particulier). **Ce désaccord entre l'observation
manuelle et la lecture statique doit être tranché par un test qui
s'exécute réellement, pas par une nouvelle lecture de code.**

- [ ] **Step 1: Écrire le test de falsification**

Ajouter à la fin de `shell/src/ui/kit/Drawer.test.tsx` :

```tsx
test("D48 : le focus revient sur le déclencheur externe après une fermeture au clavier (Échap) — filet de non-régression", async () => {
  function Harness() {
    const [open, setOpen] = useState(false);
    return (
      <>
        <button type="button" onClick={() => setOpen(true)}>
          Ouvrir
        </button>
        <Drawer open={open} onOpenChange={setOpen} title="Explorateur">
          <p>Contenu</p>
        </Drawer>
      </>
    );
  }
  render(<Harness />);
  const trigger = screen.getByRole("button", { name: "Ouvrir" });
  await userEvent.click(trigger);
  expect(screen.getByRole("dialog", { name: "Explorateur" })).toBeInTheDocument();
  await userEvent.keyboard("{Escape}");
  await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
  expect(document.activeElement).toBe(trigger);
});
```

Ajouter les imports manquants en tête de fichier — remplacer :

```tsx
import { render, screen } from "@testing-library/react";
```

par :

```tsx
import { render, screen, waitFor } from "@testing-library/react";
```

et ajouter, juste après les imports existants :

```tsx
import { useState } from "react";
```

- [ ] **Step 2: Lancer le test et observer le résultat réel — bifurcation obligatoire**

```bash
cd shell && npx vitest run src/ui/kit/Drawer.test.tsx -t "D48"
```

**Cas A — le test passe du premier coup :** D48 est déjà correct (Radix
restaure bien le focus par défaut, contrairement à ce qu'affirmait le
diagnostic manuel). **Ne modifier aucun code de `Drawer.tsx`.** Passer
directement au Step 4 (commit) avec ce seul test comme filet — c'est le
résultat attendu d'après la lecture statique.

**Cas B — le test échoue :** avant d'imputer un vrai bug à `Drawer`,
éliminer la classe de piège n°10 (`CLAUDE.md`) : jsdom ne fait jamais
converger le repositionnement `@floating-ui/react-dom` et n'implémente
pas plusieurs API consommées par Radix (`hasPointerCapture`,
`PointerEvent`, `scrollIntoView`). Vérifier d'abord si l'échec est un
timing de montage/démontage (essayer un `waitFor` plus long, ou vérifier
si `document.activeElement` vaut `document.body` — signe d'un défaut de
polyfill jsdom plutôt qu'un vrai défaut Radix) avant de conclure à un
défaut réel de `Drawer.tsx`. Si un vrai défaut est confirmé (le focus part
ailleurs qu'au `<body>` et qu'au trigger, de façon reproductible), l'étape
3 ci-dessous (à réaliser dans ce cas seulement) documente le correctif ;
sinon, consigner l'échec exact rencontré (message, `document.activeElement`
au moment de l'échec) dans le message de commit du Step 4 et remonter
l'incertitude à la revue plutôt que de deviner un correctif.

- [ ] **Step 3 (seulement si Cas B confirmé — vrai défaut Drawer) : corriger `Drawer.tsx`**

Ce plan ne préjuge pas du correctif exact tant que le Cas B n'est pas
confirmé empiriquement (aucune preuve à ce jour qu'il ait lieu — la
lecture statique de `Drawer.tsx` ne montre aucune surcharge du
comportement Radix par défaut). Si le Step 2 confirme un vrai défaut, la
piste la plus probable au vu du code actuel est l'absence de tout gain de
focus initial dans `DialogPrimitive.Content` qui déplacerait le focus hors
du document au montage (par exemple si `children` ne contient aucun
élément focusable et que Radix retombe sur le `Content` lui-même, jamais
retracé au trigger) — investiguer avec `superpowers:systematic-debugging`
avant de coder un correctif, ne pas deviner à l'aveugle.

- [ ] **Step 4: Commit**

Si Cas A (test passe, aucun correctif de code) :

```bash
cd shell && git add src/ui/kit/Drawer.test.tsx
git commit -m "$(cat <<'EOF'
test(shell): filet de falsification sur la restauration de focus du Drawer (D48)

Le diagnostic manuel affirmait que le focus ne revenait pas au
déclencheur après une fermeture Échap. La lecture statique de Drawer.tsx
ne trouvait aucune surcharge du comportement par défaut de Radix
(onCloseAutoFocus/modal/onEscapeKeyDown : zéro occurrence). Ce test
falsifie l'affirmation : il passe tel quel — Radix restaure bien le
focus par défaut. Reste comme filet de non-régression permanent, aucun
correctif de code nécessaire.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
)"
```

Si Cas B (correctif réel appliqué), adapter le message pour décrire le
défaut trouvé et le correctif appliqué, en gardant le même sujet
`fix(shell): ...` et la même ligne d'attribution.

---

## Tâche 4 — SP-C1 : D34 — boutons Monter/Descendre clavier-accessibles sur `FieldOverrides`

**Files:**
- Modify: `shell/src/builder/widgets/form.tsx:68-154` (fonction
  `FieldOverrides`)
- Modify: `shell/src/i18n/catalog.fr.ts` (2 nouvelles clés)
- Test: `shell/src/builder/widgets/form.test.tsx`

**Interfaces:**
- Consumes : `reorder(fromIndex: number, toIndex: number): void` déjà
  défini dans `FieldOverrides` (lignes 58-64), inchangé par cette tâche.
- Produces : aucune nouvelle fonction exportée — changement de rendu
  uniquement (2 `<button>` par `<li>`).

Le diagnostic affirmait à tort que `PipelinePalette.tsx` (REV-060) était
« le même patron déjà fermé » à copier. Vérifié faux : REV-060 corrigeait
l'**ajout** d'une opération (palette → canevas), pas un
**réordonnancement** de liste. `grep draggable` dans tout le dépôt ne
trouve que `form.tsx` et `PipelineCanvas.tsx` — aucun précédent de
réordonnancement clavier-accessible n'existe. Ce qui suit est donc un
motif neuf, minimal (deux boutons), pas une copie.

- [ ] **Step 1: Ajouter les 2 clés i18n**

Dans `shell/src/i18n/catalog.fr.ts`, repérer le groupe de clés `*Aria` de
`FieldOverrides` (`fieldLabelAria`, `hideFieldAria`, `requireFieldAria`,
`minFieldAria`, `maxFieldAria`, `patternFieldAria`, dans cet ordre non
alphabétique — groupées par usage, pas par nom). Remplacer :

```ts
  "widgetForm.fieldLabelAria": "Label du champ {name}",
  "widgetForm.hideFieldAria": "Masquer {name}",
  "widgetForm.requireFieldAria": "Requis {name}",
  "widgetForm.minFieldAria": "Min {name}",
```

par :

```ts
  "widgetForm.fieldLabelAria": "Label du champ {name}",
  "widgetForm.hideFieldAria": "Masquer {name}",
  "widgetForm.requireFieldAria": "Requis {name}",
  "widgetForm.moveFieldUpAria": "Monter {name}",
  "widgetForm.moveFieldDownAria": "Descendre {name}",
  "widgetForm.minFieldAria": "Min {name}",
```

- [ ] **Step 2: Écrire les tests qui échouent**

Ajouter à la fin de `shell/src/builder/widgets/form.test.tsx` :

```tsx
test("D34 : le bouton Descendre réordonne le champ vers le bas (clavier-accessible)", async () => {
  const { onChange } = renderPanel({
    dataSourceId: "ds1",
    fields: loadedFields,
    submitLabel: "Enregistrer",
    geometryType: "Point",
  });
  await userEvent.click(await screen.findByRole("button", { name: "Descendre titre" }));
  const lastCall = onChange.mock.calls[onChange.mock.calls.length - 1][0];
  expect(lastCall.fields.map((f: { name: string; order: number }) => [f.name, f.order])).toEqual([
    ["gravite", 0],
    ["titre", 1],
    ["nb_victimes", 2],
  ]);
});

test("D34 : le bouton Monter du premier champ et Descendre du dernier sont désactivés", async () => {
  renderPanel({
    dataSourceId: "ds1",
    fields: loadedFields,
    submitLabel: "Enregistrer",
    geometryType: "Point",
  });
  expect(await screen.findByRole("button", { name: "Monter titre" })).toBeDisabled();
  expect(screen.getByRole("button", { name: "Descendre nb_victimes" })).toBeDisabled();
  expect(screen.getByRole("button", { name: "Monter nb_victimes" })).not.toBeDisabled();
  expect(screen.getByRole("button", { name: "Descendre titre" })).not.toBeDisabled();
});
```

`loadedFields` (défini plus haut dans le même fichier) est trié
`titre` (order 0), `gravite` (order 1), `nb_victimes` (order 2).

- [ ] **Step 3: Lancer les tests et constater l'échec**

```bash
cd shell && npx vitest run src/builder/widgets/form.test.tsx -t "D34"
```

Attendu : 2 échecs — aucun bouton nommé « Descendre titre »/« Monter
titre »/etc. n'existe encore dans le DOM.

- [ ] **Step 4: Ajouter les 2 boutons dans `FieldOverrides`**

Dans `shell/src/builder/widgets/form.tsx`, à l'intérieur du `.map((f, i) =>
...)` de `FieldOverrides`, remplacer :

```tsx
          <div className="flex flex-wrap items-center gap-1">
            <span className="text-[10px] text-ink-2" aria-hidden="true">
              ⠿
            </span>
            <input
              aria-label={t("widgetForm.fieldLabelAria", { name: f.name })}
              className={overrideInputCls}
              value={f.label}
              onChange={(e) => patch(f.name, { label: e.target.value })}
            />
```

par :

```tsx
          <div className="flex flex-wrap items-center gap-1">
            <span className="text-[10px] text-ink-2" aria-hidden="true">
              ⠿
            </span>
            <button
              type="button"
              className="rounded border border-rule px-1 text-xs disabled:opacity-50"
              aria-label={t("widgetForm.moveFieldUpAria", { name: f.name })}
              disabled={i === 0}
              onClick={() => reorder(i, i - 1)}
            >
              ↑
            </button>
            <button
              type="button"
              className="rounded border border-rule px-1 text-xs disabled:opacity-50"
              aria-label={t("widgetForm.moveFieldDownAria", { name: f.name })}
              disabled={i === sorted.length - 1}
              onClick={() => reorder(i, i + 1)}
            >
              ↓
            </button>
            <input
              aria-label={t("widgetForm.fieldLabelAria", { name: f.name })}
              className={overrideInputCls}
              value={f.label}
              onChange={(e) => patch(f.name, { label: e.target.value })}
            />
```

`reorder`, `sorted` et `i` sont déjà dans la portée du `.map` — aucun
autre changement de signature.

- [ ] **Step 5: Relancer les tests et constater le succès**

```bash
cd shell && npx vitest run src/builder/widgets/form.test.tsx -t "D34"
```

Attendu : PASS (2 tests).

- [ ] **Step 6: Lancer tout le fichier pour vérifier l'absence de régression**

```bash
cd shell && npx vitest run src/builder/widgets/form.test.tsx
```

Attendu : tous les tests passent, y compris le test de
drag-and-drop existant (« dragging a field row onto another reorders the
list… ») — `reorder()` n'est pas modifié, seul un second chemin d'appel
est ajouté.

- [ ] **Step 7: Commit**

```bash
cd shell && git add src/builder/widgets/form.tsx src/i18n/catalog.fr.ts src/builder/widgets/form.test.tsx
git commit -m "$(cat <<'EOF'
feat(shell): boutons Monter/Descendre clavier-accessibles sur FieldOverrides (D34)

FieldOverrides ne réordonnait les champs qu'au glisser-déposer natif
(draggable/onDragStart/onDrop), aucun chemin clavier. Ajoute 2 boutons
par ligne réutilisant reorder() déjà générique, désactivés en bout de
liste. Nouveau motif (aucun précédent clavier-accessible de
réordonnancement dans le dépôt, PipelinePalette.tsx/REV-060 corrigeait
un ajout, pas un réordonnancement).

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
)"
```

---

## Tâche 5 — SP-C1 : Filet transverse — contrat `aria-required` sur les 6 branches de `FieldInput`

**Files:**
- Test: `shell/src/builder/widgets/form.test.tsx`

**Interfaces:**
- Consumes : `renderForm(fields?: FormField[], ctx?: Partial<WidgetContext>)`
  déjà défini dans ce fichier (Tâche 1 ne le modifie pas), `FormField`
  déjà exporté par `./form`.
- Produces : rien — pur filet de non-régression, table de la spec
  (« Champ généré sans aria-required »).

Ce test est distinct de celui de la Tâche 1 : la Tâche 1 ne prouve la
propriété que sur le champ texte (`titre`) et le champ non-requis
`nb_victimes`. Celui-ci couvre l'intégralité des 6 branches non-attachment
de `FieldInput` (boolean/integer/date/datetime/enum/texte) dans un seul
test paramétré, pour qu'une régression future sur une branche spécifique
(ex. quelqu'un retire le spread sur la seule branche `date`) soit
détectée même si la Tâche 1 continue de passer sur ses deux champs.

- [ ] **Step 1: Écrire le test qui échoue**

Ajouter à la fin de `shell/src/builder/widgets/form.test.tsx` :

```tsx
const allTypesFields: FormField[] = [
  { name: "actif", type: "boolean", label: "Actif", order: 0, hidden: false, required: true },
  { name: "date_debut", type: "date", label: "Date de début", order: 1, hidden: false, required: true },
  {
    name: "horodatage",
    type: "datetime",
    label: "Horodatage",
    order: 2,
    hidden: false,
    required: true,
  },
  {
    name: "gravite",
    type: "enum",
    label: "Gravité",
    order: 3,
    hidden: false,
    required: true,
    values: ["faible", "haute"],
  },
  { name: "titre", type: "string", label: "Titre", order: 4, hidden: false, required: true },
  { name: "nb", type: "integer", label: "Nombre", order: 5, hidden: false, required: false },
];

test("filet : aria-required posé sur les 6 branches non-attachment de FieldInput, selon le schéma", () => {
  renderForm(allTypesFields);
  expect(screen.getByLabelText("Actif")).toHaveAttribute("aria-required", "true");
  expect(screen.getByLabelText("Date de début")).toHaveAttribute("aria-required", "true");
  expect(screen.getByLabelText("Horodatage")).toHaveAttribute("aria-required", "true");
  expect(screen.getByLabelText("Gravité")).toHaveAttribute("aria-required", "true");
  expect(screen.getByLabelText("Titre")).toHaveAttribute("aria-required", "true");
  expect(screen.getByLabelText("Nombre")).not.toHaveAttribute("aria-required");
});
```

- [ ] **Step 2: Lancer le test — vérifier qu'il passe déjà (la Tâche 1 l'a déjà rendu vert)**

```bash
cd shell && npx vitest run src/builder/widgets/form.test.tsx -t "filet : aria-required posé sur les 6 branches"
```

Attendu : **PASS** — ce test ne fait qu'étendre la couverture de la
Tâche 1 à 4 branches supplémentaires (boolean/date/datetime/enum) déjà
corrigées par le même changement de code. Si ce test échoue à ce stade,
la Tâche 1 n'a pas été appliquée correctement sur l'une de ces branches
(ne pas continuer sans revenir corriger la Tâche 1 d'abord — ne pas
dupliquer le correctif ici).

- [ ] **Step 3: Falsifier le filet (vérifier qu'il détecterait bien une régression)**

Retirer temporairement `{...requiredProps}` de la seule branche `date`
dans `shell/src/builder/widgets/form.tsx` (Tâche 1, Step 3), relancer :

```bash
cd shell && npx vitest run src/builder/widgets/form.test.tsx -t "filet : aria-required posé sur les 6 branches"
```

Attendu : **FAIL** sur l'assertion « Date de début ». Confirme que ce
filet détecte réellement une régression ciblée (cf. piège n°10,
`CLAUDE.md` : un filet doit être vérifié par falsification, jamais
supposé correct parce qu'il passe). Remettre `{...requiredProps}` en
place immédiatement après ce test manuel, puis relancer une dernière fois
pour confirmer le retour au vert :

```bash
cd shell && npx vitest run src/builder/widgets/form.test.tsx -t "filet : aria-required posé sur les 6 branches"
```

Attendu : PASS.

- [ ] **Step 4: Lancer tout le fichier une dernière fois**

```bash
cd shell && npx vitest run src/builder/widgets/form.test.tsx
```

Attendu : tous les tests du fichier passent.

- [ ] **Step 5: Commit**

```bash
cd shell && git add src/builder/widgets/form.test.tsx
git commit -m "$(cat <<'EOF'
test(shell): filet de contrat aria-required sur les 6 branches de FieldInput

Couvre boolean/date/datetime/enum en plus des 2 branches déjà vérifiées
par le correctif D32 (texte/nombre) — une régression future limitée à
une seule branche (ex. un spread retiré sur la branche date) est
désormais détectée. Vérifié par falsification (piège n°10, CLAUDE.md) :
retrait temporaire du spread sur la branche date, confirmation que le
test échoue, remise en place.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
)"
```

---

### Notes de vérification — SP-C1 (vérification finale de branche, à refaire lors de la revue finale de la Vague C)

- [ ] **Suite complète shell** : `cd shell && npm run test` — doit rester
  entièrement vert (aucune régression cross-tâches, cf. piège n°6
  `CLAUDE.md`).
- [ ] **Lint i18n** : `cd shell && npm run lint` — vérifie entre autres
  qu'aucune chaîne française n'a été laissée en dur (`lint:i18n`) et
  qu'aucune couleur Tailwind brute n'a été introduite (`lint:colors`,
  sans objet ici, aucune couleur touchée).
- [ ] **Build** : `cd shell && npm run build` — `tsc --noEmit` doit
  passer (les 6 branches de `FieldInput` restent bien typées après
  l'ajout de `requiredProps`).
- [ ] **Régénération OpenAPI/TS** : sans objet pour ce plan — aucune
  route ni modèle du cœur n'est touché (piège n°1 `CLAUDE.md`, vérifié
  non applicable ici).

---

## Correspondance avec la spec

| Tâche de ce plan | Fait référence à |
|---|---|
| Tâche 6 | D43, nouveau filet de couverture |
| Tâche 7 | D43, 10 des 12 routes manquantes (fixtures triviales à copier) |
| Tâche 8 | D43, la 11e route manquante (`/datasets/visual-query/:pipelinePk/edit`), fixture neuve non triviale — scindée de la Tâche 7 comme la spec l'anticipe |
| Tâche 9 | D42, règle CSS globale |
| Tâche 10 | D42, bascule carte `matchMedia` |

**Écart trouvé contre la spec (Étape 1 de la commande ayant produit ce plan) :**
la spec dit "10 autres routes ont déjà une fixture E2E à copier" dans son
corps de texte (section D43), mais le prompt qui demandait ce plan
paraphrasait ce chiffre à "11". Vérification directe du code (comptage des
`<Route path="...">` dans `routes.tsx` = 29, des `page.goto("...")` dans
`a11y-audit.spec.ts` = 17, conversion des segments `:param` en RegExp et
recoupement) confirme le chiffre du corps de la spec : **12 routes non
auditées, dont `/internal/kit-gallery` est une exemption (dev-only, jamais
en production) et `/datasets/visual-query/:pipelinePk/edit` la seule à
nécessiter une fixture neuve — 10 routes restent donc à câbler dans la
Tâche 7**, pas 11. Le reste des comptages de la spec (29 routes, 17 `goto`,
12 manquantes, la liste nominative des 12) a été vérifié exact contre le code
réel.

---

## Tâche 6 — SP-C2 : Filet de couverture D43 (`a11yAuditCoverage.test.ts`)

**Files:**
- Create: `shell/src/shell/a11yAuditCoverage.test.ts`
- Read (ne pas modifier) : `shell/src/shell/routes.tsx`, `shell/e2e/a11y-audit.spec.ts`, `shell/src/shell/routeReachability.test.ts` (patron d'extraction à reprendre)

**Interfaces:**
- Consumes: rien d'un autre fichier de code — lit `routes.tsx` et
  `a11y-audit.spec.ts` en texte brut via `node:fs`.
- Produces: un test Vitest qui échoue tant que la Tâche 7 et la Tâche 8 ne
  sont pas terminées (12 routes manquantes moins 1 exemption = 11 lignes de
  différence attendues au premier run, puis 1 seule après la Tâche 7, puis 0
  après la Tâche 8). Aucune autre tâche ne consomme de fonction exportée par
  ce fichier — c'est un test terminal.

- [ ] **Step 1: Écrire le test (échec attendu)**

Créer `shell/src/shell/a11yAuditCoverage.test.ts` :

```ts
// SPDX-License-Identifier: Apache-2.0
// Filet anti-régression D43 (docs/superpowers/specs/
// 2026-09-27-vague-c-polish-a11y-onboarding-design.md, SP-C2) :
// shell/e2e/a11y-audit.spec.ts n'auditait que 17 des 29 routes déclarées
// dans routes.tsx (12 manquantes, trouvées en revue de code — le diagnostic
// d'origine ne les comptait pas). Même patron d'extraction mécanique que
// routeReachability.test.ts (D01/GAP-80) : lire les deux fichiers en texte
// brut, jamais monter le routeur ni exécuter Playwright ici — ce test ne
// prouve pas qu'un audit passe, il prouve qu'un audit EXISTE pour chaque
// route déclarée, ou qu'elle est listée dans une allowlist explicite avec sa
// raison.
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { test, expect } from "vitest";

const ROUTES_FILE = join(__dirname, "routes.tsx");
const A11Y_AUDIT_FILE = join(__dirname, "..", "..", "e2e", "a11y-audit.spec.ts");

// Routes volontairement hors périmètre de l'audit a11y automatisé — chaque
// entrée nomme la raison, jamais un simple "TODO". Ne pas ajouter une route
// ici pour faire taire ce test sans avoir vérifié qu'elle est vraiment hors
// périmètre.
const ALLOWLIST: Record<string, string> = {
  "/internal/kit-gallery":
    "galerie interne de développement (SP-29b), jamais exposée en production",
};

function extractDeclaredRoutePaths(): string[] {
  const content = readFileSync(ROUTES_FILE, "utf-8");
  return [...content.matchAll(/<Route\s+path="([^"]+)"/g)].map((m) => m[1]);
}

function extractAuditedGotoPaths(): string[] {
  const content = readFileSync(A11Y_AUDIT_FILE, "utf-8");
  // Volontairement strict : seuls les littéraux "page.goto("...")" entre
  // guillemets doubles sont reconnus (patron déjà suivi par toutes les
  // routes de ce fichier, y compris celles ajoutées par ce plan) — un futur
  // ajout en template literal (`page.goto(\`/x/${y}\`)`) ne serait pas
  // détecté, choix assumé pour rester aussi simple que routeReachability.
  return [...content.matchAll(/page\.goto\("([^"]+)"\)/g)].map((m) => m[1]);
}

// Convertit un chemin déclaré ("/apps/:pk/:pageId?") en RegExp de
// correspondance contre un `page.goto("...")` littéral ("/apps/1"). Un
// segment ":nom" est un paramètre requis (n'importe quelle valeur, jamais
// "/"), un segment ":nom?" un paramètre optionnel final (React Router v6 —
// seule route de ce dépôt à en porter un : "/apps/:pk/:pageId?") : son "/"
// précédent devient optionnel avec lui.
function routePathToRegex(path: string): RegExp {
  const OPTIONAL_MARKER = "\u0000OPTIONAL\u0000";
  const segments = path.split("/").map((segment) => {
    if (segment.startsWith(":") && segment.endsWith("?")) return OPTIONAL_MARKER;
    if (segment.startsWith(":")) return "[^/]+";
    return segment.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  });
  const joined = segments.join("/").replace(new RegExp(`/${OPTIONAL_MARKER}`, "g"), "(?:/[^/]+)?");
  return new RegExp(`^${joined}$`);
}

test("chaque route de routes.tsx a un page.goto(...) dans a11y-audit.spec.ts, ou une exemption listée", () => {
  const declared = extractDeclaredRoutePaths();
  const audited = extractAuditedGotoPaths();
  const uncovered = declared.filter((path) => {
    if (path in ALLOWLIST) return false;
    const regex = routePathToRegex(path);
    return !audited.some((goto) => regex.test(goto));
  });
  expect(uncovered).toEqual([]);
});

test("l'allowlist ne porte que des routes réellement déclarées", () => {
  // Filet inverse : une entrée d'allowlist qui survit à un renommage/retrait
  // de route dans routes.tsx ne doit pas rester une exemption silencieuse
  // pour une route qui n'existe plus.
  const declared = new Set(extractDeclaredRoutePaths());
  for (const path of Object.keys(ALLOWLIST)) {
    expect(declared.has(path), `route allowlistée introuvable : ${path}`).toBe(true);
  }
});
```

- [ ] **Step 2: Lancer le test, vérifier l'échec attendu**

Run: `cd shell && npx vitest run src/shell/a11yAuditCoverage.test.ts`

Expected: FAIL sur le premier test, avec une liste `uncovered` de 11 chemins
(les 12 routes non couvertes moins `/internal/kit-gallery`, qui est déjà
exemptée) :
`/bookmarks`, `/reports`, `/pipelines/new`, `/reports/new`,
`/admin/compliance`, `/settings`, `/apps/:pk/:pageId?`, `/embed/:token`,
`/public/items/:pk`, `/public/datasets/:collectionId`,
`/datasets/visual-query/:pipelinePk/edit`.
Le second test ("l'allowlist ne porte que...") doit PASSER dès ce premier
run (aucune dépendance sur les tâches suivantes).

- [ ] **Step 3: Commit (test rouge, intentionnel)**

```bash
cd shell && git add src/shell/a11yAuditCoverage.test.ts
git commit -m "$(cat <<'EOF'
test(shell): ajoute le filet de couverture de l'audit a11y (D43)

routes.tsx déclare 29 routes, a11y-audit.spec.ts n'en auditait que 17.
Ce filet dérive mécaniquement la liste des routes manquantes (même patron
que routeReachability.test.ts, D01/GAP-80) au lieu de compter à la main —
rouge intentionnellement tant que les Tâches 2 et 3 de ce plan n'ont pas
ajouté les page.goto manquants.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
)"
```

---

## Tâche 7 — SP-C2 : Ajouter les 10 `page.goto` manquants à fixture triviale

**Files:**
- Modify: `shell/e2e/a11y-audit.spec.ts` (ajout de 10 `test(...)` dans le `describe` existant)
- Read (ne pas modifier) : `shell/e2e/mocks.ts` (fixtures réutilisées : item "1"/"8", collection "parcs", route `/notifications/preference`)

**Interfaces:**
- Consumes: `mockCore`, `mockMe`, `ADMIN_ME` (déjà importés en haut du
  fichier), `runAxeAudit(page, pageName)` (déjà défini dans ce fichier).
- Produces: 10 nouveaux `page.goto("...")` littéraux (chemins exacts listés
  ci-dessous) — consommés par le test de la Tâche 6, qui doit passer de 11
  chemins manquants à 1 seul (`/datasets/visual-query/:pipelinePk/edit`,
  traité en Tâche 8) une fois cette tâche terminée.

- [ ] **Step 1: Ajouter les 10 tests, chacun avec sa fixture minimale**

Ajouter, juste avant le `});` qui ferme le `describe("audit d'accessibilité (axe-core)", ...)` de `shell/e2e/a11y-audit.spec.ts` (après le test `"HarvestSourcesAdminPage"` existant) :

```ts
  // --- Tâche 7/SP-C2 (D43) : routes jusqu'ici non auditées, fixture triviale
  // (déjà mockée ailleurs par mockCore()/mocks.ts, ou réutilisant une
  // fixture d'une autre spec E2E telle quelle). -----------------------------

  test("BookmarksRoute (CatalogPage filtré sur les signets, état vide)", async ({ page }) => {
    await mockCore(page);
    await page.goto("/bookmarks");
    await expect(page.getByText("Aucun élément pour l'instant")).toBeVisible();
    await runAxeAudit(page, "BookmarksRoute");
  });

  test("ReportsRoute (CatalogPage filtré sur les rapports, état vide)", async ({ page }) => {
    await mockCore(page);
    await page.goto("/reports");
    await expect(page.getByText("Aucun élément pour l'instant")).toBeVisible();
    await runAxeAudit(page, "ReportsRoute");
  });

  test("PipelineNewRoute (brouillon de pipeline vierge)", async ({ page }) => {
    await mockCore(page);
    // Même patron que le test "PipelineBuilderPage" plus haut dans ce
    // fichier : /instance et /pipelines/ops doivent répondre avant que le
    // garde etlEnabled ne laisse passer le rendu (sinon spinner infini,
    // cf. le commentaire "D09" de PipelineBuilderPage.tsx).
    await page.route("https://core.test/v1/instance", async (route) => {
      await route.fulfill({ json: { readOnly: false, etlEnabled: true } });
    });
    await page.route("https://core.test/v1/pipelines/ops", async (route) => {
      await route.fulfill({
        json: {
          "reader.collection": {
            kind: "reader",
            paramsSchema: {
              properties: { collectionId: { type: "string", format: "collection-id" } },
              required: ["collectionId"],
            },
          },
          "writer.collection": {
            kind: "writer",
            paramsSchema: {
              properties: { collectionId: { type: "string", format: "collection-id" } },
              required: ["collectionId"],
            },
          },
        },
      });
    });
    await page.goto("/pipelines/new");
    await expect(page.getByRole("heading", { name: "Pipeline" })).toBeVisible();
    await runAxeAudit(page, "PipelineNewRoute");
  });

  test("ReportNewRoute (brouillon de rapport planifié vierge)", async ({ page }) => {
    await mockCore(page);
    // pk === null : ReportEditPage ne fait aucune requête conditionnelle à
    // un item/config existant (garde `enabled: pk !== null`) — mockCore()
    // seul suffit.
    await page.goto("/reports/new");
    await expect(page.getByRole("heading", { name: "Programmer un rapport" })).toBeVisible();
    await runAxeAudit(page, "ReportNewRoute");
  });

  test("ComplianceAdminPage (famille Administration — conformité RGPD)", async ({ page }) => {
    await mockCore(page);
    // Même profil que compliance-admin.spec.ts : compliance.manage n'est
    // porté par aucun rôle prédéfini, y compris Administrateur (SP-58) —
    // ajouté explicitement au profil admin de test.
    await mockMe(page, { ...ADMIN_ME, privileges: [...ADMIN_ME.privileges, "compliance.manage"] });
    await page.goto("/admin/compliance");
    await expect(page.getByText("Purger toutes les données du tenant")).toBeVisible();
    await runAxeAudit(page, "ComplianceAdminPage");
  });

  test("SettingsPage (Paramètres, profil courant)", async ({ page }) => {
    await mockCore(page);
    // Seule route que mockCore() ne fournit pas par défaut pour cette page
    // (settings-page.spec.ts la mocke explicitement, elle aussi).
    await page.route("https://core.test/v1/notifications/preference", async (route) => {
      await route.fulfill({ json: { value: "all" } });
    });
    await page.goto("/settings");
    await expect(page.getByRole("link", { name: "Général →" })).toBeVisible();
    await runAxeAudit(page, "SettingsPage");
  });

  test("AppRuntimeRoute (App publiée en mode exécution, hors édition)", async ({ page }) => {
    await mockCore(page);
    // Item "1" (Alpha, resourceType app) porte déjà APP_CONFIG_V2 par
    // défaut dans mocks.ts (le même fixture que le test "AppBuilderPage"
    // plus haut, en lecture-exécution plutôt qu'en édition) — zéro mock
    // nouveau, comme anticipé par la spec.
    await page.goto("/apps/1");
    await expect(page.getByText("Titre version 2")).toBeVisible();
    await runAxeAudit(page, "AppRuntimeRoute");
  });

  test("EmbedRoute (App intégrée via un jeton de partage invité)", async ({ page }) => {
    // Repris tel quel du premier test de embed.spec.ts (pas de mockCore() :
    // EmbedPage n'authentifie jamais, elle ne parle qu'au jeton de partage).
    await page.route("**/v1/share-links/*", async (route) => {
      await route.fulfill({
        json: {
          itemId: "app-1",
          title: "App de démo",
          resourceType: "app",
          expiresAt: "2099-01-01",
        },
      });
    });
    await page.route("**/v1/configs/by-item/app-1*", async (route) => {
      await route.fulfill({
        json: {
          config: {
            kind: "app",
            theme: {},
            dataSources: [
              { id: "ds1", type: "features", service: "core", layer: "incidents", query: {} },
            ],
            messages: [],
            layout: {
              type: "grid",
              items: [
                { id: "w1", widget: "table", x: 0, y: 0, w: 4, h: 4, props: { dataSourceId: "ds1" } },
              ],
            },
          },
        },
      });
    });
    await page.route("**/v1/collections/incidents/schema*", async (route) => {
      await route.fulfill({
        json: { collection: "incidents", pk: "id", geometry: null, fields: [] },
      });
    });
    await page.route("**/v1/collections/incidents/items*", async (route) => {
      await route.fulfill({
        json: { type: "FeatureCollection", features: [], numberMatched: 0, numberReturned: 0 },
      });
    });
    await page.goto("/embed/e2e-audit-embed-token");
    await expect(page.locator("body")).not.toContainText("Chargement");
    await runAxeAudit(page, "EmbedRoute");
  });

  test("PublicItemRoute (item publié consulté en anonyme)", async ({ page }) => {
    await mockCore(page);
    // Item "8" (GALLERY_ITEM, config texte "Detail de l'article") est déjà
    // mocké par défaut dans mocks.ts pour le parcours Gallery → vignette →
    // PublicItemPage (SP-16b) — PublicItemPage n'appelle que
    // getPublicAppConfig(pk), déjà satisfait.
    await page.goto("/public/items/8");
    await expect(page.getByText("Detail de l'article")).toBeVisible();
    await runAxeAudit(page, "PublicItemRoute");
  });

  test("DatasetRoute (fiche dataset publique, consultation anonyme)", async ({ page }) => {
    await mockCore(page);
    // "parcs" est déjà publique par défaut dans mocks.ts (collection +
    // schema + items), réutilisée telle quelle par
    // sites-portal-dataset.spec.ts pour ce même chemin.
    await page.goto("/public/datasets/parcs");
    await expect(page.getByRole("heading", { name: "Parcs" })).toBeVisible();
    await runAxeAudit(page, "DatasetRoute");
  });
```

- [ ] **Step 2: Lancer le filet de couverture, vérifier qu'il ne reste qu'une route**

Run: `cd shell && npx vitest run src/shell/a11yAuditCoverage.test.ts`

Expected: le premier test échoue encore, mais avec une seule entrée :
`["/datasets/visual-query/:pipelinePk/edit"]`.

- [ ] **Step 3: Lancer les 10 nouveaux tests Playwright**

Run: `cd shell && npm run e2e -- e2e/a11y-audit.spec.ts`

Expected: PASS sur les 27 tests du fichier (17 existants + 10 nouveaux).
Si un des 10 échoue sur une violation axe-core réelle (`critical`/`serious`
non listée dans `EXCLUSIONS`), corriger le défaut d'accessibilité trouvé
avant de continuer (ne jamais ajouter une exclusion pour faire taire un vrai
défaut) — consigner le défaut et son correctif dans le message de commit.

- [ ] **Step 4: Commit**

```bash
cd shell && git add e2e/a11y-audit.spec.ts
git commit -m "$(cat <<'EOF'
test(shell): audite 10 routes jusqu'ici hors périmètre a11y (D43)

Bookmarks/Reports (CatalogPage filtrée), brouillons Pipeline/Rapport,
conformité RGPD, Paramètres, App en exécution, intégration via jeton,
item et dataset publics — 10 des 11 routes restantes après le filet de
couverture (a11yAuditCoverage.test.ts), toutes à fixture triviale
(mockCore() seul ou une route déjà mockée ailleurs dans mocks.ts).
Reste /datasets/visual-query/:pipelinePk/edit, traitée séparément
(fixture non triviale).

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
)"
```

---

## Tâche 8 — SP-C2 : Audit de `/datasets/visual-query/:pipelinePk/edit` (fixture neuve)

**Files:**
- Modify: `shell/e2e/a11y-audit.spec.ts` (ajout d'un dernier `test(...)`)
- Read (ne pas modifier) : `shell/src/pages/VisualQueryWizardPage.tsx`, `shell/src/builder/visualQuery/compilePipeline.ts` (fonction `decompilePipelineToWizardState`), `shell/e2e/mocks.ts` (`mockCollection`)

**Interfaces:**
- Consumes: `mockCore`, `mockCollection`, `runAxeAudit` (déjà importés).
- Produces: le dernier `page.goto` manquant — après cette tâche, les deux
  tests de la Tâche 6 passent tous les deux au vert sans aucune allowlist
  supplémentaire.

Cette route est scindée de la Tâche 7 parce que `VisualQueryWizardPage` en
mode édition (`pipelinePk !== null`) dépend de
`decompilePipelineToWizardState()` : un pipeline minimal ne suffit pas
n'importe comment — il doit avoir **exactement** un nœud `reader.collection`,
un nœud `writer.dataset` (jamais `writer.collection`), et un unique lien
direct entre les deux pour que la décompilation réussisse (sinon la page
affiche seulement un message d'erreur avec un lien, un rendu dégénéré qui ne
vaut pas la peine d'être audité).

- [ ] **Step 1: Ajouter le test**

Ajouter, à la toute fin du `describe("audit d'accessibilité (axe-core)", ...)`, après les 10 tests de la Tâche 7 :

```ts
  test("VisualQueryWizardEditPage (assistant Filtrer→Joindre→Résumer, mode édition)", async ({
    page,
  }) => {
    await mockCore(page);
    await page.route("https://core.test/v1/instance", async (route) => {
      await route.fulfill({ json: { readOnly: false, etlEnabled: true } });
    });
    await page.route("https://core.test/v1/collections*", async (route) => {
      await route.fulfill({
        json: {
          collections: [
            mockCollection({ id: "villes", title: "Villes", tableName: "villes" }),
            mockCollection({
              id: "villes-out",
              title: "Villes filtrées (sortie)",
              tableName: "villes_out",
            }),
          ],
        },
      });
    });
    await page.route("https://core.test/v1/collections/villes/schema", async (route) => {
      await route.fulfill({
        json: { collection: "villes", pk: "id", geometry: null, fields: [{ name: "nom", type: "string" }] },
      });
    });
    await page.route("https://core.test/v1/collections/villes-out/schema", async (route) => {
      await route.fulfill({
        json: { collection: "villes-out", pk: "id", geometry: null, fields: [{ name: "nom", type: "string" }] },
      });
    });
    // Pipeline minimal décompilable par decompilePipelineToWizardState :
    // exactement 1 reader.collection -> 1 writer.dataset, un seul lien
    // direct entre les deux (aucun filtre/jointure/résumé — la fonction ne
    // les exige pas, elle boucle simplement sur les arêtes sortantes).
    await page.route("https://core.test/v1/configs/by-item/pipe-vq-1", async (route) => {
      await route.fulfill({
        json: {
          id: "cfg-pipe-vq-1",
          itemId: "pipe-vq-1",
          kind: "pipeline",
          config: {
            kind: "pipeline",
            pipeline: {
              nodes: [
                {
                  id: "r1",
                  kind: "reader",
                  op: "reader.collection",
                  x: 0,
                  y: 0,
                  params: { collectionId: "villes" },
                  title: "reader.collection",
                },
                {
                  id: "w1",
                  kind: "writer",
                  op: "writer.dataset",
                  x: 300,
                  y: 0,
                  params: { collectionId: "villes-out", datasetId: "dataset-vq-1" },
                  title: "writer.dataset",
                },
              ],
              edges: [{ id: "e1", from: "r1", to: "w1" }],
            },
          },
        },
      });
    });
    // Item du dataset de sortie — préremplit le champ Titre et le panneau
    // "browse" (type + date de modification). itemQuery(pipelinePk) n'a pas
    // besoin d'un mock dédié : le filet générique "/items/{id}" de
    // mockCore() renvoie déjà permissions.write=true pour tout id non
    // explicitement mocké.
    await page.route("https://core.test/v1/items/dataset-vq-1", async (route) => {
      await route.fulfill({
        json: {
          pk: "dataset-vq-1",
          resourceType: "dataset",
          title: "Villes filtrées",
          abstract: "",
          owner: "mockuser",
          thumbnailUrl: null,
          date: "2026-01-01",
          configId: null,
          isPublished: false,
          keywords: [],
          permissions: { read: true, write: true, delete: true, share: true },
          updatedAt: "2026-01-02T00:00:00Z",
        },
      });
    });
    await page.goto("/datasets/visual-query/pipe-vq-1/edit");
    await expect(page.getByRole("heading", { name: "Modifier la requête" })).toBeVisible();
    await runAxeAudit(page, "VisualQueryWizardEditPage");
  });
```

- [ ] **Step 2: Lancer le filet de couverture, vérifier le passage au vert**

Run: `cd shell && npx vitest run src/shell/a11yAuditCoverage.test.ts`

Expected: PASS (les deux tests).

- [ ] **Step 3: Lancer la suite E2E complète du fichier**

Run: `cd shell && npm run e2e -- e2e/a11y-audit.spec.ts`

Expected: PASS sur les 28 tests. Même consigne qu'à la Tâche 7 : un échec
axe-core réel se corrige, ne se masque jamais par une exclusion.

- [ ] **Step 4: Commit**

```bash
cd shell && git add e2e/a11y-audit.spec.ts
git commit -m "$(cat <<'EOF'
test(shell): audite la dernière route manquante, la requête visuelle (D43)

/datasets/visual-query/:pipelinePk/edit était la seule des 12 routes non
auditées à nécessiter une fixture neuve (VisualQueryWizardPage en mode
édition dépend de decompilePipelineToWizardState, qui exige un pipeline
reader.collection -> writer.dataset minimal mais structurellement valide).
Ferme a11yAuditCoverage.test.ts au vert : les 29 routes de routes.tsx sont
désormais toutes auditées ou explicitement exemptées (D43 complet).

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
)"
```

---

## Tâche 9 — SP-C2 : Règle CSS globale `prefers-reduced-motion` (D42)

**Files:**
- Modify: `shell/src/styles/tokens.css` (ajout en fin de fichier, après le bloc `@theme inline { ... }`)
- Modify: `shell/src/styles/tokens.test.ts` (ajout d'un `describe` de contrat)
- Read (ne pas modifier, vérification seule) : `shell/src/builder/pipeline/PipelineCanvas.tsx:95`, `shell/src/ui/kit/LoadingState.tsx:8`, `shell/src/ui/kit/Skeleton.tsx:5`, `shell/src/ui/kit/Spinner.tsx:7`, `shell/src/ui/kit/Switch.tsx:31`, `shell/src/ui/kit/Tree.tsx:48`, `shell/src/ui/kit/Progress.tsx:22`

**Interfaces:**
- Consumes: rien.
- Produces: une règle CSS `@media (prefers-reduced-motion: reduce)` globale
  — aucun des 7 fichiers listés ci-dessus n'a besoin d'être modifié (leurs
  classes Tailwind `animate-*`/`transition-transform` restent inchangées,
  neutralisées par la cascade CSS). Rien d'autre dans ce plan ne dépend de
  cette tâche.

Confirmation faite en lecture directe (pas seulement contre la spec) : les 7
sites et leurs numéros de ligne sont exacts. Aucun composant Dialog/Drawer/
Toast/Popover/Menu/Select/Combobox/Tooltip n'a de transition d'ouverture à
exempter (`grep -rn "animate-\|transition-transform"` sur `ui/kit/` et
`builder/pipeline/` ne remonte que ces 7 occurrences).

- [ ] **Step 1: Écrire le test (échec attendu)**

Ajouter à la fin de `shell/src/styles/tokens.test.ts` (après le dernier
`});` du fichier) :

```ts

describe("réduction de mouvement (D42, prefers-reduced-motion)", () => {
  it("neutralise globalement animations et transitions quand le visiteur préfère un mouvement réduit", () => {
    const mediaBlock = block("@media (prefers-reduced-motion: reduce)");
    expect(mediaBlock).toMatch(/animation-duration:\s*0\.01ms\s*!important/);
    expect(mediaBlock).toMatch(/transition-duration:\s*0\.01ms\s*!important/);
  });
});
```

- [ ] **Step 2: Lancer le test, vérifier l'échec**

Run: `cd shell && npx vitest run src/styles/tokens.test.ts`

Expected: FAIL — `block()` lève `bloc introuvable : @media (prefers-reduced-motion: reduce)` (le sélecteur n'existe pas encore dans `tokens.css`).

- [ ] **Step 3: Ajouter la règle CSS**

Ajouter à la toute fin de `shell/src/styles/tokens.css`, après l'accolade
fermante du bloc `@theme inline { ... }` :

```css

/* D42 (Vague C, SP-C2) : neutralise globalement animations/transitions pour
 * tout visiteur ayant activé "réduire les animations" côté système —
 * couvre les 7 sites `animate-*`/`transition-transform` du dépôt
 * (PipelineCanvas.tsx, LoadingState.tsx, Skeleton.tsx, Spinner.tsx,
 * Switch.tsx, Tree.tsx, Progress.tsx) sans modifier un seul de ces
 * fichiers — la cascade CSS suffit. Aucun Dialog/Drawer/Toast/Popover/Menu/
 * Select/Combobox/Tooltip n'a de transition d'ouverture à exempter (vérifié,
 * grep sur ui/kit/).
 *
 * Insuffisant pour la carte : maplibre-gl `flyTo`/`fitBounds` sont pilotés
 * en JS, invisibles à une media query CSS — cf. MapView.tsx, bascule dédiée
 * sur `window.matchMedia`.
 */
@media (prefers-reduced-motion: reduce) {
  *,
  *::before,
  *::after {
    animation-duration: 0.01ms !important;
    transition-duration: 0.01ms !important;
  }
}
```

- [ ] **Step 4: Lancer le test, vérifier qu'il passe**

Run: `cd shell && npx vitest run src/styles/tokens.test.ts`

Expected: PASS (tous les tests du fichier, y compris les préexistants — la
nouvelle règle est hors des trois blocs d'ambiance `:root`/`:not([data-theme="light"])`/`[data-theme="dark"]` et ne contient aucune couleur en dur, donc ne casse pas le test "ne déclare aucune couleur en dur hors des trois blocs d'ambiance").

- [ ] **Step 5: Commit**

```bash
cd shell && git add src/styles/tokens.css src/styles/tokens.test.ts
git commit -m "$(cat <<'EOF'
fix(shell): respecte prefers-reduced-motion sur les animations CSS (D42)

Règle globale dans tokens.css : neutralise animation-duration/
transition-duration pour tout visiteur ayant activé la réduction de
mouvement côté système. Couvre les 7 sites animate-*/transition-transform
du dépôt sans modifier un seul fichier consommateur — la cascade suffit.
Insuffisant pour maplibre-gl (piloté en JS), traité séparément.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
)"
```

---

## Tâche 10 — SP-C2 : Bascule `flyTo` → `jumpTo` sur `prefers-reduced-motion` (D42, carte)

**Files:**
- Modify: `shell/src/map/MapView.tsx:1287-1328` (méthode `flyTo` de `useImperativeHandle`)
- Modify: `shell/src/map/MapView.test.tsx` (nouveau test + stub `matchMedia` local sur le test existant qui exerce `flyTo`)

**Interfaces:**
- Consumes: `MapViewHandle.flyTo(opts)` (inchangé — signature identique,
  `{ center, zoom, ... }` passé tel quel à `jumpTo`/`flyTo` du SDK
  maplibre-gl).
- Produces: rien de nouveau consommé ailleurs — `MapEditorPage.tsx` (seul
  appelant de production, `mapViewRef.current?.flyTo({...})`) continue de
  fonctionner sans changement de signature.

**Contexte vérifié en lecture directe :** `MapView.tsx` bascule déjà
`flyTo`→`jumpTo` quand `mapRef.current?.getTerrain()` est non-null
(contournement d'une régression maplibre-gl v6 sur la transition de pitch
avec terrain actif). Il n'existe **aucun** stub `window.matchMedia` dans
`MapView.test.tsx` aujourd'hui — jsdom ne l'implémente pas nativement (piège
n°10). Le seul test qui appelle `ref.current.flyTo(...)` aujourd'hui
("exposes an imperative flyTo that drives the map", ligne 441) va donc lever
`TypeError: window.matchMedia is not a function` dès que l'implémentation
interroge `matchMedia` — ce test doit être mis à jour dans la même tâche
(stub local, patron déjà utilisé par `useNarrowViewport.test.ts`/
`App.test.tsx`), sans quoi cette tâche casserait un test qui passe
aujourd'hui.

`shell/src/test/MockMaplibreMap.ts` enregistre `flyTo` et `jumpTo` dans le
**même** tableau `flyToArgs` (commentaire ligne 117-121 du mock) : on ne peut
donc pas distinguer laquelle des deux méthodes a été appelée en inspectant
seulement `flyToArgs`. Le nouveau test espionne directement les méthodes de
l'instance (`vi.spyOn(map, "flyTo")` / `vi.spyOn(map, "jumpTo")`) plutôt que
de modifier le mock partagé (moins de risque de régression sur les tests
existants qui lisent déjà `flyToArgs`).

- [ ] **Step 1: Écrire les tests (un test modifié, un test nouveau) — échec attendu sur le nouveau**

Dans `shell/src/map/MapView.test.tsx`, ajouter juste avant le test existant
`"exposes an imperative flyTo that drives the map"` (ligne 441) :

```ts
function mockMatchMedia(matches: boolean) {
  vi.stubGlobal(
    "matchMedia",
    vi.fn().mockReturnValue({
      matches,
      addEventListener: () => {},
      removeEventListener: () => {},
    }),
  );
}

```

Puis remplacer le test existant :

```ts
test("exposes an imperative flyTo that drives the map", () => {
  const ref = createRef<MapViewHandle>();
  render(<MapView ref={ref} config={config} />);
  ref.current!.flyTo({ center: [5, 6], zoom: 12 });
  expect(mapInstances[0].flyToArgs).toContainEqual({ center: [5, 6], zoom: 12 });
});
```

par (ajout du stub, comportement inchangé sinon) :

```ts
test("exposes an imperative flyTo that drives the map", () => {
  mockMatchMedia(false);
  const ref = createRef<MapViewHandle>();
  render(<MapView ref={ref} config={config} />);
  ref.current!.flyTo({ center: [5, 6], zoom: 12 });
  expect(mapInstances[0].flyToArgs).toContainEqual({ center: [5, 6], zoom: 12 });
});

test("D42 : bascule sur jumpTo (jamais flyTo) quand le visiteur préfère un mouvement réduit", () => {
  mockMatchMedia(true);
  const ref = createRef<MapViewHandle>();
  render(<MapView ref={ref} config={config} />);
  const map = mapInstances[0];
  const flyToSpy = vi.spyOn(map, "flyTo");
  const jumpToSpy = vi.spyOn(map, "jumpTo");
  ref.current!.flyTo({ center: [5, 6], zoom: 12 });
  expect(jumpToSpy).toHaveBeenCalledWith({ center: [5, 6], zoom: 12 });
  expect(flyToSpy).not.toHaveBeenCalled();
});
```

`vi.unstubAllGlobals()` est déjà appelé dans l'`afterEach` existant du
fichier (ligne 54) — aucun nettoyage supplémentaire à ajouter.

- [ ] **Step 2: Lancer les tests, vérifier l'état attendu**

Run: `cd shell && npx vitest run src/map/MapView.test.tsx`

Expected: le test "exposes an imperative flyTo..." PASSE (comportement
inchangé, juste un stub ajouté). Le nouveau test "D42 : bascule sur
jumpTo..." ÉCHOUE : `jumpToSpy` n'a pas été appelé (l'implémentation ne
regarde pas encore `matchMedia`), `flyToSpy` a été appelé à sa place.

- [ ] **Step 3: Lire `MapView.tsx` autour de la méthode `flyTo`**

Le bloc à modifier (lignes 1287-1307 environ) :

```tsx
  useImperativeHandle(
    ref,
    () => ({
      flyTo: (opts) => {
        // maplibre-gl v6 regression, confirmed by e2e (with vs. without
        // terrain, with `flyTo` vs. `easeTo` vs. `jumpTo` — only the
        // animated forms fail, only when a terrain is currently set): an
        // animated pitch transition (`flyTo`/`easeTo`) while `map.getTerrain()`
        // is non-null lands the camera near pitch≈0 instead of the
        // requested value, regardless of target — repeatable, not a race.
        // `jumpTo` (no animation, no curve/elevation sampling) is
        // unaffected, so it's the fallback exactly when terrain is active;
        // `flyTo`'s scenic arc stays the default the rest of the time
        // (searched-location and explorer navigation, the other two
        // MapViewHandle.flyTo call sites, never touch terrain state).
        if (mapRef.current?.getTerrain()) {
          mapRef.current.jumpTo(opts);
        } else {
          mapRef.current?.flyTo(opts);
        }
      },
```

- [ ] **Step 4: Implémenter la bascule**

Remplacer ce bloc par :

```tsx
  useImperativeHandle(
    ref,
    () => ({
      flyTo: (opts) => {
        // maplibre-gl v6 regression, confirmed by e2e (with vs. without
        // terrain, with `flyTo` vs. `easeTo` vs. `jumpTo` — only the
        // animated forms fail, only when a terrain is currently set): an
        // animated pitch transition (`flyTo`/`easeTo`) while `map.getTerrain()`
        // is non-null lands the camera near pitch≈0 instead of the
        // requested value, regardless of target — repeatable, not a race.
        // `jumpTo` (no animation, no curve/elevation sampling) is
        // unaffected, so it's the fallback exactly when terrain is active;
        // `flyTo`'s scenic arc stays the default the rest of the time
        // (searched-location and explorer navigation, the other two
        // MapViewHandle.flyTo call sites, never touch terrain state).
        //
        // D42 (Vague C, SP-C2) : même bascule vers jumpTo, motif différent
        // — un visiteur ayant activé prefers-reduced-motion ne doit jamais
        // recevoir l'arc animé de flyTo. Interrogé à chaque appel (jamais
        // mis en cache dans un state/ref) : un changement de préférence
        // système en cours de session doit être respecté au prochain
        // flyTo, pas seulement à celui qui suit le montage.
        const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
        if (mapRef.current?.getTerrain() || reducedMotion) {
          mapRef.current?.jumpTo(opts);
        } else {
          mapRef.current?.flyTo(opts);
        }
      },
```

- [ ] **Step 5: Lancer les tests, vérifier qu'ils passent**

Run: `cd shell && npx vitest run src/map/MapView.test.tsx`

Expected: PASS (tous les tests du fichier).

- [ ] **Step 6: Falsifier le correctif (piège n°10 de `CLAUDE.md`)**

Revenir temporairement en arrière sur le Step 4 (remettre
`if (mapRef.current?.getTerrain()) { mapRef.current.jumpTo(opts); } else { mapRef.current?.flyTo(opts); }`,
sans la condition `|| reducedMotion`), relancer
`cd shell && npx vitest run src/map/MapView.test.tsx` et confirmer que
**seul** le nouveau test "D42 : bascule sur jumpTo..." échoue (le reste de
la suite doit rester vert). Puis restaurer le Step 4 tel quel et relancer une
dernière fois pour confirmer le retour au vert complet.

- [ ] **Step 7: Lancer la suite complète du fichier une dernière fois et la suite E2E carte**

Run: `cd shell && npx vitest run src/map/MapView.test.tsx`

Expected: PASS.

Run: `cd shell && npm run e2e -- e2e/map-popup.spec.ts e2e/map-3d.spec.ts`

Expected: PASS (ces deux specs exercent `MapEditorPage`/`MapView` en dehors
du chunk mocké — `window.matchMedia` existe réellement dans le navigateur
Playwright, aucun stub requis là).

- [ ] **Step 8: Commit**

```bash
cd shell && git add src/map/MapView.tsx src/map/MapView.test.tsx
git commit -m "$(cat <<'EOF'
fix(shell): la carte respecte prefers-reduced-motion (D42)

MapViewHandle.flyTo bascule déjà sur jumpTo quand un terrain est actif
(contournement d'une régression maplibre-gl v6) — réutilise exactement la
même primitive quand le visiteur a activé la réduction de mouvement
système, interrogée à chaque appel via window.matchMedia. tokens.css
(tâche précédente) ne peut rien pour la carte : flyTo/fitBounds sont
pilotés en JS, invisibles à une media query CSS.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
)"
```

---

### Notes de vérification — SP-C2 (self-review de l'agent de recherche)

**1. Couverture de la spec SP-C2 :**
- D43 (couverture d'audit) : Tâches 1+2+3 — filet mécanique + 11 routes
  manquantes câblées (10 triviales + 1 fixture neuve). Couvert.
- D42 (mouvement) : Tâche 9 (CSS globale, 7 sites Tailwind) + Tâche 10
  (carte, primitive JS dédiée). Couvert.
- Le tableau "Filets anti-régression transverses" de la spec ligne
  "Route de routes.tsx non auditée par axe-core → a11yAuditCoverage.test.ts"
  correspond exactement à la Tâche 6.

**2. Recherche de placeholders :** aucun "TBD"/"TODO"/"similaire à la tâche
N" — chaque étape porte le code réel, chaque commande de test est explicite
avec sa sortie attendue.

**3. Cohérence des types/signatures :** `MapViewHandle.flyTo` inchangé (pas
de nouveau paramètre) ; `runAxeAudit(page, pageName)`, `mockCore(page)`,
`mockMe(page, overrides)`, `mockCollection(overrides)` utilisés avec
exactement les signatures déjà présentes dans `mocks.ts` (vérifiées par
lecture directe, pas supposées) ; `ALLOWLIST`/`routePathToRegex` de la
Tâche 6 ne sont consommés par aucune autre tâche (fichier terminal).

**Écart trouvé et corrigé pendant la rédaction (au-delà de celui déjà
signalé plus haut) :** aucun autre — tous les numéros de ligne cités par la
spec pour D42 (7 fichiers) et pour la bascule `flyTo`/`jumpTo` de
`MapView.tsx` (spec : lignes 1290-1306 ; code réel : méthode `flyTo`
lignes 1290-1307 à l'intérieur du bloc `useImperativeHandle` 1287-1328) ont
été vérifiés exacts.

---

## Tâche 11 — SP-C3 : token `--text-2xs` + script de garde-fou `check-arbitrary-text-size.mjs` (non câblé)

**Contexte vérifié** : `shell/scripts/check-raw-colors.mjs` est le patron
exact à répliquer (script autonome, tolérance zéro, marche manuelle
`readdirSync`/`statSync` pour rester compatible Node 20 en CI, pragma en
ligne). `shell/src/styles/tokens.css` a un bloc `@theme inline` (lignes
170-208) qui expose déjà des tokens non-couleur sans duplication par
ambiance claire/sombre (`--radius-sm`, `--font-ui`, `--shadow-sm`, …) — le
test `tokens.test.ts` ne contraint que les tokens `--gs-*` (couleurs
d'ambiance) à exister dans les trois blocs ; un token `--text-2xs` n'a donc
besoin d'être déclaré qu'une seule fois dans `@theme inline`, pas dupliqué.

**Files:**
- Modify: `shell/src/styles/tokens.css:196` (bloc `@theme inline`)
- Create: `shell/scripts/check-arbitrary-text-size.mjs`

**Interfaces:**
- Produces: token Tailwind `text-2xs` (via `--text-2xs` dans `@theme
  inline`) ; fonction `main()` exportée par
  `check-arbitrary-text-size.mjs` (même contrat que `check-raw-colors.mjs`),
  invocable en CLI (`node scripts/check-arbitrary-text-size.mjs`).
- Consumes: rien de nouveau — lit `shell/src/**/*.tsx` sur le disque.

- [ ] **Step 1: Ajouter le token `--text-2xs` dans `tokens.css`**

Dans le bloc `@theme inline`, juste après `--color-map-road` et avant les
tokens de police (ligne 196) :

```css
  --color-map-road: var(--gs-map-road);

  --text-2xs: 0.6875rem;

  --font-ui: "Archivo Variable", "Helvetica Neue", Arial, sans-serif;
```

- [ ] **Step 2: Créer `shell/scripts/check-arbitrary-text-size.mjs`**

```js
#!/usr/bin/env node
// SPDX-License-Identifier: Apache-2.0
//
// Garde-fou anti-régression (SP-C3/D46) : signale une classe Tailwind de
// taille de texte ARBITRAIRE (`text-[10px]`, `text-[9px]`, etc.) hors test.
// L'échelle typographique Tailwind v4 par défaut n'a aucun palier entre
// `text-xs` (12px) et rien — ces occurrences ponctuelles contournaient
// toujours le contrat de tokens (cf. tokens.css, `--text-2xs` ajouté par la
// même tâche pour les badges dont la taille est contrainte). Même patron
// architectural que check-raw-colors.mjs (SP-B12d) : parcourt le code
// source, échoue si une occurrence n'est pas couverte par un pragma
// explicite — câblé dans `npm run lint`.
//
// Contrairement à check-raw-colors.mjs, AUCUN répertoire n'est exclu :
// `map/` n'a pas ici la légitimité qu'il a pour les couleurs de symbologie
// choisies par l'utilisateur final (check-raw-colors.mjs) — une taille de
// texte arbitraire dans `map/` (ex. MapSymbologyEditor.tsx) est le même
// défaut qu'ailleurs, pas un choix produit.
//
// Choix d'implémentation identique à check-raw-colors.mjs : parcours manuel
// `readdirSync`/`statSync` (pas de glob — `.github/workflows/ci.yml` lance
// Node 20 sur tous les jobs shell, `node:fs` `globSync` nécessite Node >=
// 22).
//
// Allowlist — pragma EN LIGNE, pas un allowlist par fichier (même raison
// que check-raw-colors.mjs : un allowlist par fichier laisserait un nouvel
// offenseur non lié se glisser, non détecté, dans un fichier déjà
// exempté) : `// gs-arbitrary-text-size-ok: <raison>` sur la même ligne
// physique que l'occurrence, ou sur la ligne immédiatement précédente SI ET
// SEULEMENT SI celle-ci, une fois retirée des espaces en bordure, est un
// commentaire pur.
import { readFileSync, readdirSync, statSync } from "node:fs";
import { join, extname } from "node:path";

const ROOT = "src";

const ARBITRARY_TEXT_SIZE_RE = /\btext-\[[0-9]+px\]/;

const PRAGMA_RE = /gs-arbitrary-text-size-ok/;

/**
 * Parcours récursif de `dir` (sans dépendance de glob), retourne la liste
 * des fichiers `.tsx` non-test.
 */
function walk(dir, out = []) {
  for (const entry of readdirSync(dir)) {
    const full = join(dir, entry);
    const st = statSync(full);
    if (st.isDirectory()) {
      walk(full, out);
    } else if (extname(full) === ".tsx" && !entry.endsWith(".test.tsx")) {
      out.push(full);
    }
  }
  return out;
}

/**
 * Retourne les lignes de `file` qui portent une taille de texte Tailwind
 * arbitraire sans pragma `gs-arbitrary-text-size-ok` (sur la ligne
 * elle-même, ou sur la ligne précédente si et seulement si celle-ci est un
 * commentaire pur — même garde anti-fuite que check-raw-colors.mjs).
 */
function findOffenders(file) {
  const content = readFileSync(file, "utf8");
  const lines = content.split("\n");
  const offenders = [];
  lines.forEach((line, index) => {
    if (!ARBITRARY_TEXT_SIZE_RE.test(line)) return;
    const coveredBySameLine = PRAGMA_RE.test(line);
    const prevLine = index > 0 ? lines[index - 1] : "";
    const prevLineTrimmed = prevLine.trim();
    const coveredByPrecedingLine =
      prevLineTrimmed.startsWith("//") && PRAGMA_RE.test(prevLineTrimmed);
    if (coveredBySameLine || coveredByPrecedingLine) return;
    offenders.push(`${file}:${index + 1}: ${line.trim()}`);
  });
  return offenders;
}

export function main() {
  const files = walk(ROOT).sort();
  const offenders = files.flatMap(findOffenders);

  if (offenders.length > 0) {
    console.error(
      "Tailles de texte Tailwind arbitraires détectées (text-[Npx]), sans pragma gs-arbitrary-text-size-ok :",
    );
    offenders.forEach((o) => console.error(`  ${o}`));
    console.error(
      "\nUtiliser un token sémantique (text-xs, ou text-2xs pour un badge dont la taille " +
        "est contrainte) au lieu d'une taille littérale, ou documenter l'exception avec " +
        "`// gs-arbitrary-text-size-ok: <raison>` sur la même ligne ou la ligne précédente " +
        "si l'exception est délibérée et revue.",
    );
    process.exit(1);
  }
  console.log(
    `OK : aucune taille de texte Tailwind arbitraire hors tests et pragma gs-arbitrary-text-size-ok (${files.length} fichier(s) scanné(s)).`,
  );
}

const isMain = process.argv[1] && import.meta.url === `file://${process.argv[1]}`;
if (isMain) {
  main();
}
```

- [ ] **Step 3: Exécuter le script manuellement (rouge attendu — preuve qu'il détecte bien les 24 occurrences réelles)**

Run: `cd shell && node scripts/check-arbitrary-text-size.mjs`
Expected: sortie listant exactement 24 lignes offensantes sur 14 fichiers
(`src/builder/DatasetDownloadButtons.tsx:50`,
`src/builder/ExplorerDrawer.tsx:198`, `src/builder/NavigationPanel.tsx:94`,
`src/builder/pipeline/PipelineCanvas.tsx` ×5,
`src/builder/pipeline/PipelineNodeInspector.tsx` ×2,
`src/builder/pipeline/PipelinePalette.tsx` ×2,
`src/builder/pipeline/PipelinePreviewMap.tsx:141`,
`src/builder/widgets/data.tsx:336`, `src/builder/widgets/form.tsx` ×3,
`src/builder/widgets/gallery.tsx:138`, `src/builder/widgets/index.tsx:89`,
`src/builder/widgets/navigation.tsx:33`, `src/map/MapSymbologyEditor.tsx`
×3, `src/shell/chrome/StatusBar.tsx:8`), `process.exit(1)`. **Ne pas
corriger ici** — cette étape documente l'état actuel, la Tâche 12 fait le
remap. Ne pas encore ajouter le script à `package.json` (il casserait `npm
run lint` pour tout le dépôt tant que Tâche 12 n'est pas passée).

- [ ] **Step 4: Commit**

```bash
git add shell/src/styles/tokens.css shell/scripts/check-arbitrary-text-size.mjs
git commit -m "feat(shell): ajoute le token --text-2xs et le script de garde check-arbitrary-text-size

Script pas encore câblé dans npm run lint (24 occurrences réelles
restent à remapper, Tâche suivante) — cf. plan SP-C3.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

## Tâche 12 — SP-C3 : remap des 24 occurrences vers `text-xs`/`text-2xs` + câblage du script dans `npm run lint`

**Files:**
- Modify: `shell/src/builder/DatasetDownloadButtons.tsx:50`
- Modify: `shell/src/builder/ExplorerDrawer.tsx:198`
- Modify: `shell/src/builder/NavigationPanel.tsx:94`
- Modify: `shell/src/builder/pipeline/PipelineCanvas.tsx:72,78,86,101,113`
- Modify: `shell/src/builder/pipeline/PipelineNodeInspector.tsx:244,254`
- Modify: `shell/src/builder/pipeline/PipelinePalette.tsx:89,136`
- Modify: `shell/src/builder/pipeline/PipelinePreviewMap.tsx:141`
- Modify: `shell/src/builder/widgets/data.tsx:336`
- Modify: `shell/src/builder/widgets/form.tsx:87,96,106`
- Modify: `shell/src/builder/widgets/gallery.tsx:138`
- Modify: `shell/src/builder/widgets/index.tsx:89`
- Modify: `shell/src/builder/widgets/navigation.tsx:33`
- Modify: `shell/src/map/MapSymbologyEditor.tsx:644,668,685`
- Modify: `shell/src/shell/chrome/StatusBar.tsx:8`
- Modify: `shell/package.json` (script `lint`, nouvelle entrée
  `lint:arbitrary-text-size`)

**Interfaces:**
- Consumes: `main()` de `check-arbitrary-text-size.mjs` (Tâche 11).

- [ ] **Step 1: Remap texte libre → `text-xs` (20 occurrences, 13 fichiers)**

`shell/src/builder/DatasetDownloadButtons.tsx:50` :
```diff
-        <p className="w-full text-[10px] text-ink-3">{t("datasetDownload.tooLarge")}</p>
+        <p className="w-full text-xs text-ink-3">{t("datasetDownload.tooLarge")}</p>
```

`shell/src/builder/ExplorerDrawer.tsx:198` :
```diff
-          <div className="mt-auto flex items-center justify-between pt-2 text-[10px] text-[var(--gs-color-muted)]">
+          <div className="mt-auto flex items-center justify-between pt-2 text-xs text-[var(--gs-color-muted)]">
```

`shell/src/builder/NavigationPanel.tsx:94` :
```diff
-          <p className="text-[10px] text-ink-2">
+          <p className="text-xs text-ink-2">
```

`shell/src/builder/pipeline/PipelineCanvas.tsx:72` (op sous le titre du
nœud — texte libre, aucune contrainte de taille, cf. écart documenté en
tête de plan) :
```diff
-      <div className="text-[10px] text-ink-2">{node.op}</div>
+      <div className="text-xs text-ink-2">{node.op}</div>
```

`shell/src/builder/pipeline/PipelineNodeInspector.tsx:244` :
```diff
-            <h4 className="text-[10px] font-semibold uppercase text-ink-2">
+            <h4 className="text-xs font-semibold uppercase text-ink-2">
```
(première occurrence ; répéter à l'identique pour la seconde, ligne 254 —
même motif exact.)

`shell/src/builder/pipeline/PipelinePalette.tsx:89` :
```diff
-                          <span className="text-[10px] text-ink-2">{description}</span>
+                          <span className="text-xs text-ink-2">{description}</span>
```

`shell/src/builder/pipeline/PipelinePalette.tsx:136` :
```diff
-                      {description && <span className="text-[10px] text-ink-2">{description}</span>}
+                      {description && <span className="text-xs text-ink-2">{description}</span>}
```

`shell/src/builder/pipeline/PipelinePreviewMap.tsx:141` :
```diff
-        <div className="flex gap-3 text-[10px] text-ink-2">
+        <div className="flex gap-3 text-xs text-ink-2">
```

`shell/src/builder/widgets/data.tsx:336` :
```diff
-            <div className="mt-auto flex items-center justify-between pt-1 text-[10px] text-[var(--gs-color-muted)]">
+            <div className="mt-auto flex items-center justify-between pt-1 text-xs text-[var(--gs-color-muted)]">
```

`shell/src/builder/widgets/form.tsx:87` :
```diff
-            <span className="text-[10px] text-ink-2" aria-hidden="true">
+            <span className="text-xs text-ink-2" aria-hidden="true">
```

`shell/src/builder/widgets/form.tsx:96` et `:106` (même motif exact aux
deux lignes) :
```diff
-              <label className="flex items-center gap-1 whitespace-nowrap text-[10px]">
+              <label className="flex items-center gap-1 whitespace-nowrap text-xs">
```

`shell/src/builder/widgets/gallery.tsx:138` :
```diff
-                        className="rounded-full bg-[var(--gs-color-background)] px-2 py-0.5 text-[10px] text-[var(--gs-color-muted)]"
+                        className="rounded-full bg-[var(--gs-color-background)] px-2 py-0.5 text-xs text-[var(--gs-color-muted)]"
```

`shell/src/builder/widgets/index.tsx:89` :
```diff
-        <p className="text-[10px] text-ink-2">{t("widgetIndex.interpolationHelp")}</p>
+        <p className="text-xs text-ink-2">{t("widgetIndex.interpolationHelp")}</p>
```

`shell/src/builder/widgets/navigation.tsx:33` :
```diff
-        <p className="text-[10px] text-ink-2">{t("widgetNavigation.autoPagesHelp")}</p>
+        <p className="text-xs text-ink-2">{t("widgetNavigation.autoPagesHelp")}</p>
```

`shell/src/map/MapSymbologyEditor.tsx:644` :
```diff
-                  <h4 className="text-[10px] uppercase text-ink-3">{category}</h4>
+                  <h4 className="text-xs uppercase text-ink-3">{category}</h4>
```

`shell/src/map/MapSymbologyEditor.tsx:668` :
```diff
-                  <h4 className="text-[10px] uppercase text-ink-3">
+                  <h4 className="text-xs uppercase text-ink-3">
```

`shell/src/map/MapSymbologyEditor.tsx:685` :
```diff
-                            className="text-[10px] text-danger underline"
+                            className="text-xs text-danger underline"
```

`shell/src/shell/chrome/StatusBar.tsx:8` (le seul `text-[9px]`, pas
`text-[10px]`) :
```diff
-    <div className="flex h-[21px] items-center gap-3 border-t border-rule px-2 font-mono text-[9px] text-ink-3">
+    <div className="flex h-[21px] items-center gap-3 border-t border-rule px-2 font-mono text-xs text-ink-3">
```
(`h-[21px]` reste inchangé — ce n'est pas une taille de texte, hors
périmètre de ce garde-fou et de cette tâche.)

- [ ] **Step 2: Remap badges contraints → `text-2xs` (4 occurrences, `PipelineCanvas.tsx` uniquement)**

`shell/src/builder/pipeline/PipelineCanvas.tsx:78` :
```diff
-          className="absolute -left-2 -top-2 flex h-4 w-4 items-center justify-center rounded-full bg-danger text-[10px] text-surface"
+          className="absolute -left-2 -top-2 flex h-4 w-4 items-center justify-center rounded-full bg-danger text-2xs text-surface"
```

`shell/src/builder/pipeline/PipelineCanvas.tsx:86` :
```diff
-          className="absolute -right-2 -top-2 rounded-full bg-ok px-1.5 py-0.5 text-[10px] text-surface"
+          className="absolute -right-2 -top-2 rounded-full bg-ok px-1.5 py-0.5 text-2xs text-surface"
```

`shell/src/builder/pipeline/PipelineCanvas.tsx:101` :
```diff
-        className="absolute -bottom-2 -right-2 flex h-4 w-4 items-center justify-center rounded-full border border-rule bg-surface text-[10px] leading-none text-ink-2 hover:bg-sunken hover:text-danger"
+        className="absolute -bottom-2 -right-2 flex h-4 w-4 items-center justify-center rounded-full border border-rule bg-surface text-2xs leading-none text-ink-2 hover:bg-sunken hover:text-danger"
```

`shell/src/builder/pipeline/PipelineCanvas.tsx:113` :
```diff
-        className="absolute -bottom-2 -left-2 flex h-4 w-4 items-center justify-center rounded-full border border-rule bg-surface text-[10px] leading-none text-ink-2 hover:bg-sunken"
+        className="absolute -bottom-2 -left-2 flex h-4 w-4 items-center justify-center rounded-full border border-rule bg-surface text-2xs leading-none text-ink-2 hover:bg-sunken"
```

- [ ] **Step 3: Vérifier visuellement l'absence de débordement (D46 le demande explicitement)**

Lancer le shell en dev (`cd shell && npm run dev`), ouvrir un pipeline avec
au moins un nœud en erreur (`nodeStat`/`errorCount`) pour voir les 4 badges
`text-2xs` dans `h-4 w-4` — vérifier à l'œil qu'aucun chiffre/glyphe ne
déborde du cercle. Documenter le résultat dans le message de commit
(Step 5) même si "rien à signaler".

- [ ] **Step 4: Exécuter le script — vert attendu**

Run: `cd shell && node scripts/check-arbitrary-text-size.mjs`
Expected: `OK : aucune taille de texte Tailwind arbitraire hors tests et pragma gs-arbitrary-text-size-ok (N fichier(s) scanné(s)).` et code de sortie 0.

- [ ] **Step 5: Câbler le script dans `npm run lint`**

Dans `shell/package.json`, ajouter la ligne (après `lint:no-window-confirm`) :

```json
    "lint:arbitrary-text-size": "node scripts/check-arbitrary-text-size.mjs",
```

Et étendre la commande composite `lint` :

```diff
-    "lint": "eslint . && npm run lint:i18n && npm run lint:aria-panel && npm run lint:colors && npm run lint:no-window-confirm",
+    "lint": "eslint . && npm run lint:i18n && npm run lint:aria-panel && npm run lint:colors && npm run lint:no-window-confirm && npm run lint:arbitrary-text-size",
```

- [ ] **Step 6: Run complet du lint et de la suite unitaire**

Run: `cd shell && npm run lint`
Expected: toutes les portes passent (exit 0), y compris la nouvelle.

Run: `cd shell && npm run test`
Expected: entièrement vert (le remap est purement cosmétique, aucune
assertion de test existante ne dépend d'une classe `text-[10px]`/`text-[9px]`
littérale — à vérifier : `grep -rn "text-\[10px\]\|text-\[9px\]" shell/src/**/*.test.tsx`
ne doit rien retourner avant de committer).

- [ ] **Step 7: Commit**

```bash
git add shell/src/builder/DatasetDownloadButtons.tsx shell/src/builder/ExplorerDrawer.tsx \
  shell/src/builder/NavigationPanel.tsx shell/src/builder/pipeline/PipelineCanvas.tsx \
  shell/src/builder/pipeline/PipelineNodeInspector.tsx shell/src/builder/pipeline/PipelinePalette.tsx \
  shell/src/builder/pipeline/PipelinePreviewMap.tsx shell/src/builder/widgets/data.tsx \
  shell/src/builder/widgets/form.tsx shell/src/builder/widgets/gallery.tsx \
  shell/src/builder/widgets/index.tsx shell/src/builder/widgets/navigation.tsx \
  shell/src/map/MapSymbologyEditor.tsx shell/src/shell/chrome/StatusBar.tsx shell/package.json
git commit -m "fix(shell): remplace les tailles de texte Tailwind arbitraires par des tokens

20 occurrences texte libre -> text-xs, 4 badges PipelineCanvas.tsx
(taille contrainte h-4 w-4 ou pastille numérique) -> le nouveau
--text-2xs. check-arbitrary-text-size.mjs câblé dans npm run lint.

Écart vs la spec SP-C3/D46 : PipelinePalette.tsx (2 occurrences) était
absent des deux listes de la spec ; les 3 occurrences de
MapSymbologyEditor.tsx classées 'badge h-4 w-4' par la spec sont en
réalité des titres de section/un lien, sans contrainte de taille -> text-xs
comme le reste du texte libre, pas text-2xs.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

## Tâche 13 — SP-C3 : segmented-control pour le toggle Édition/Aperçu et les boutons de largeur d'écran (D47)

**Contexte vérifié** : `shell/src/pages/AppBuilderPage.tsx` a 3 occurrences
du même idiome `variant={cond ? "default" : "outline"}` (toggle mode, lignes
397/404 ; boutons de largeur, ligne 422) — `Button` (`shell/src/ui/kit/
Button.tsx`) n'a que 4 variants (`default`/`outline`/`ghost`/`danger`), pas
de variant "actif dans un groupe". `ui/kit/Segmented.tsx` existe (Radix
`ToggleGroup`) mais son état actif est câblé en dur sur `bg-accent` plein
(`data-[state=on]:bg-accent`) — l'exact anti-patron que D47 corrige — et n'a
aucun consommateur de production (seul `KitGalleryPage.tsx`, galerie
interne) : le réutiliser demanderait de le restyler d'abord, hors périmètre
de cette tâche (blast radius plus large que nécessaire). Cette tâche
compose donc `Button variant="outline"` + une classe `bg-sunken`
conditionnelle sur l'état actif (`cn`/twMerge fait déjà gagner la classe
passée en `className` sur celle du variant, comportement déjà vérifié dans
`Button.tsx`/`lib/utils.ts`) — ce qui obtient exactement le style demandé
("outline + surbrillance bg-sunken sur l'état actif, jamais bg-accent
plein") sans toucher `Segmented`/`Button`.

**Files:**
- Modify: `shell/src/pages/AppBuilderPage.tsx:394-429`
- Test: `shell/src/pages/AppBuilderPage.test.tsx`

**Interfaces:**
- Consumes: `Button` (`variant`, `size`, `className`) — inchangé,
  `shell/src/ui/kit/Button.tsx`.
- Produces: aucune nouvelle interface — comportement de clic identique
  (`onClick={() => setMode(...)}`/`setBreakpoint(...)`), seul le style
  change.

- [ ] **Step 1: Écrire le test (rouge attendu)**

Ajouter à la fin de `shell/src/pages/AppBuilderPage.test.tsx` :

```ts
test("D47 : le toggle Édition/Aperçu et les boutons de largeur d'écran ne sont jamais bg-accent plein", async () => {
  renderPage({ getAppConfig: vi.fn().mockResolvedValue(config) });
  const editButton = await screen.findByRole("button", { name: t("appBuilder.editMode") });
  const previewButton = screen.getByRole("button", { name: t("appBuilder.previewMode") });
  const lgButton = screen.getByRole("button", {
    name: t("appBuilder.editBreakpointAria", { bp: "lg" }),
  });
  const saveButton = screen.getByRole("button", { name: t("appBuilder.save") });

  // État initial : mode "edit" et breakpoint "lg" actifs par défaut.
  expect(editButton.className).not.toMatch(/\bbg-accent\b/);
  expect(editButton.className).toContain("bg-sunken");
  expect(previewButton.className).not.toMatch(/\bbg-accent\b/);
  expect(previewButton.className).not.toContain("bg-sunken");
  expect(lgButton.className).not.toMatch(/\bbg-accent\b/);
  expect(lgButton.className).toContain("bg-sunken");

  // Enregistrer reste le seul bg-accent plein légitime de cet écran.
  expect(saveButton.className).toMatch(/\bbg-accent\b/);

  await userEvent.click(previewButton);
  expect(previewButton.className).toContain("bg-sunken");
  expect(editButton.className).not.toContain("bg-sunken");
  expect(previewButton.className).not.toMatch(/\bbg-accent\b/);
});
```

- [ ] **Step 2: Lancer le test, vérifier qu'il échoue**

Run: `cd shell && npx vitest run src/pages/AppBuilderPage.test.tsx -t "D47"`
Expected: FAIL — `editButton.className` contient encore `bg-accent`
(variant `"default"` actuel).

- [ ] **Step 3: Démoter le toggle mode et les boutons de largeur**

Dans `shell/src/pages/AppBuilderPage.tsx`, remplacer (lignes 394-408) :

```diff
                 <div className="flex flex-wrap items-center gap-2 border-b border-rule p-2">
                   <Button
                     size="sm"
-                    variant={mode === "edit" ? "default" : "outline"}
+                    variant="outline"
+                    className={mode === "edit" ? "bg-sunken" : undefined}
                     onClick={() => setMode("edit")}
                   >
                     {t("appBuilder.editMode")}
                   </Button>
                   <Button
                     size="sm"
-                    variant={mode === "preview" ? "default" : "outline"}
+                    variant="outline"
+                    className={mode === "preview" ? "bg-sunken" : undefined}
                     onClick={() => setMode("preview")}
                   >
                     {t("appBuilder.previewMode")}
                   </Button>
```

Et (lignes 417-429) :

```diff
                   <div className="ml-2 flex items-center gap-1">
                     {BREAKPOINTS.map((bp) => (
                       <Button
                         key={bp}
                         size="sm"
-                        variant={breakpoint === bp ? "default" : "outline"}
+                        variant="outline"
+                        className={breakpoint === bp ? "bg-sunken" : undefined}
                         aria-label={t("appBuilder.editBreakpointAria", { bp })}
                         onClick={() => setBreakpoint(bp)}
                       >
                         {bp}
                       </Button>
                     ))}
                   </div>
```

Le bouton Enregistrer (lignes 567-576, sans `variant` explicite → `default`
CVA par défaut) et les boutons Undo/Redo/Capturer une miniature (déjà
`variant="outline"` sans état actif) restent inchangés.

- [ ] **Step 4: Lancer le test, vérifier qu'il passe**

Run: `cd shell && npx vitest run src/pages/AppBuilderPage.test.tsx -t "D47"`
Expected: PASS.

- [ ] **Step 5: Run complet du fichier de test**

Run: `cd shell && npx vitest run src/pages/AppBuilderPage.test.tsx`
Expected: tous les tests existants restent verts (aucun n'affirmait sur
`bg-accent`/`variant="default"` du toggle ou des boutons de largeur — vérifié
par grep avant cette tâche).

- [ ] **Step 6: Commit**

```bash
git add shell/src/pages/AppBuilderPage.tsx shell/src/pages/AppBuilderPage.test.tsx
git commit -m "fix(shell): démote le toggle Édition/Aperçu et la largeur d'écran en segmented-control

Enregistrer reste le seul bouton bg-accent plein de l'écran (D47) —
le toggle mode et les 3 boutons de largeur passent en outline +
surbrillance bg-sunken sur l'état actif.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

## Tâche 14 — SP-C3 : `ItemCard` — relocaliser vers `ui/kit/`, migrer `CatalogPage.tsx` (D10)

**Contexte vérifié** : `shell/src/ui/ItemCard.tsx` (+ `ItemCard.test.tsx`)
n'importe déjà QUE des primitives `ui/kit/*` (`./kit/Button`, `./kit/Panel`)
— seul son adresse (`ui/` au lieu de `ui/kit/`) est "legacy". Zéro autre
consommateur dans le dépôt que `CatalogPage.tsx` (vérifié par grep global).
`ui/kit/index.ts` est le barrel où chaque primitive du kit a sa ligne
d'export (dernière ligne actuelle : `export { Kbd } from "./Kbd";`).

**Files:**
- Move: `shell/src/ui/ItemCard.tsx` → `shell/src/ui/kit/ItemCard.tsx`
- Move: `shell/src/ui/ItemCard.test.tsx` → `shell/src/ui/kit/ItemCard.test.tsx`
- Modify: `shell/src/ui/kit/index.ts`
- Modify: `shell/src/pages/CatalogPage.tsx:7`

**Interfaces:**
- Produces: `ItemCard` désormais exporté par `shell/src/ui/kit/ItemCard.tsx`
  (et par le barrel `shell/src/ui/kit/index.ts`), signature inchangée
  (`{ item: Item; onOpen: (pk, type) => void; actions?: React.ReactNode }`).

- [ ] **Step 1: Déplacer les fichiers**

```bash
git mv shell/src/ui/ItemCard.tsx shell/src/ui/kit/ItemCard.tsx
git mv shell/src/ui/ItemCard.test.tsx shell/src/ui/kit/ItemCard.test.tsx
```

- [ ] **Step 2: Corriger les imports relatifs de `ItemCard.tsx`**

```diff
-import type { Item, ResourceType } from "../api/types";
-import { RESOURCE_TYPE_LABELS } from "../api/resourceTypes";
-import { Button } from "./kit/Button";
-import { Panel } from "./kit/Panel";
+import type { Item, ResourceType } from "../../api/types";
+import { RESOURCE_TYPE_LABELS } from "../../api/resourceTypes";
+import { Button } from "./Button";
+import { Panel } from "./Panel";
```

- [ ] **Step 3: Corriger les imports relatifs de `ItemCard.test.tsx`**

```diff
-import type { Item } from "../api/types";
+import type { Item } from "../../api/types";
 import { ItemCard } from "./ItemCard";
-import { OWNER_PERMISSIONS } from "../auth/permissions";
+import { OWNER_PERMISSIONS } from "../../auth/permissions";
```

- [ ] **Step 4: Ajouter l'export au barrel**

Dans `shell/src/ui/kit/index.ts`, après `export { Kbd } from "./Kbd";` :

```ts
export { ItemCard } from "./ItemCard";
```

- [ ] **Step 5: Migrer l'import dans `CatalogPage.tsx`**

```diff
-import { ItemCard } from "../ui/ItemCard";
+import { ItemCard } from "../ui/kit/ItemCard";
```

- [ ] **Step 6: Vérifier que le test déplacé passe toujours (refactor pur, pas de nouveau comportement)**

Run: `cd shell && npx vitest run src/ui/kit/ItemCard.test.tsx`
Expected: PASS (7 tests, identiques à avant le déplacement).

Run: `cd shell && npx vitest run src/pages/CatalogPage.test.tsx`
Expected: PASS (aucune assertion de ce fichier ne dépend du chemin
d'import d'`ItemCard`, seulement de son rendu).

- [ ] **Step 7: Vérifier qu'aucun import legacy `ui/ItemCard` ne subsiste**

Run: `cd shell && grep -rn "ui/ItemCard[\"']" src/`
Expected: aucune sortie.

- [ ] **Step 8: Commit**

```bash
git add shell/src/ui/kit/ItemCard.tsx shell/src/ui/kit/ItemCard.test.tsx \
  shell/src/ui/ItemCard.tsx shell/src/ui/ItemCard.test.tsx \
  shell/src/ui/kit/index.ts shell/src/pages/CatalogPage.tsx
git commit -m "refactor(shell): relocalise ItemCard sous ui/kit/ (D10)

ItemCard n'importait déjà que des primitives ui/kit/* — seule son
adresse était legacy. CatalogPage.tsx est son seul consommateur.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

## Tâche 15 — SP-C3 : `MetadataForm` + `ThumbnailUpload` — relocaliser vers `ui/kit/`, migrer `ItemDetailPage.tsx` et `DatasetEditPage.tsx` (D10)

**Contexte vérifié** : même situation qu'`ItemCard` — `MetadataForm.tsx`
n'importe que `./kit/Button`/`./kit/Input`/`./kit/Select` ;
`ThumbnailUpload.tsx` n'a aucun import `ui/kit/*` (composant nu, `<input
type="file">` natif) mais est listé par la spec comme legacy à porter au
même titre. Zéro consommateur hors `ItemDetailPage.tsx` (les deux) et
`DatasetEditPage.tsx` (`MetadataForm` seul) — vérifié par grep global.

**Files:**
- Move: `shell/src/ui/MetadataForm.tsx` → `shell/src/ui/kit/MetadataForm.tsx`
- Move: `shell/src/ui/MetadataForm.test.tsx` → `shell/src/ui/kit/MetadataForm.test.tsx`
- Move: `shell/src/ui/ThumbnailUpload.tsx` → `shell/src/ui/kit/ThumbnailUpload.tsx`
- Move: `shell/src/ui/ThumbnailUpload.test.tsx` → `shell/src/ui/kit/ThumbnailUpload.test.tsx`
- Modify: `shell/src/ui/kit/index.ts`
- Modify: `shell/src/pages/ItemDetailPage.tsx:7-8`
- Modify: `shell/src/pages/DatasetEditPage.tsx:17`

**Interfaces:**
- Produces: `MetadataForm`/`ThumbnailUpload` exportés depuis
  `shell/src/ui/kit/`, signatures inchangées.

- [ ] **Step 1: Déplacer les fichiers**

```bash
git mv shell/src/ui/MetadataForm.tsx shell/src/ui/kit/MetadataForm.tsx
git mv shell/src/ui/MetadataForm.test.tsx shell/src/ui/kit/MetadataForm.test.tsx
git mv shell/src/ui/ThumbnailUpload.tsx shell/src/ui/kit/ThumbnailUpload.tsx
git mv shell/src/ui/ThumbnailUpload.test.tsx shell/src/ui/kit/ThumbnailUpload.test.tsx
```

- [ ] **Step 2: Corriger les imports relatifs de `MetadataForm.tsx`**

```diff
 import { useState } from "react";
-import { t } from "../i18n";
-import { Button } from "./kit/Button";
-import { Input } from "./kit/Input";
-import { Select } from "./kit/Select";
+import { t } from "../../i18n";
+import { Button } from "./Button";
+import { Input } from "./Input";
+import { Select } from "./Select";
```

`MetadataForm.test.tsx` n'importe rien via `../` (seulement `./MetadataForm`
et des libs externes) — aucun changement nécessaire.

- [ ] **Step 3: Corriger l'import relatif de `ThumbnailUpload.tsx`**

```diff
 import { useState } from "react";
-import { t } from "../i18n";
+import { t } from "../../i18n";
```

`ThumbnailUpload.test.tsx` n'importe rien via `../` — aucun changement
nécessaire.

- [ ] **Step 4: Ajouter les exports au barrel**

Dans `shell/src/ui/kit/index.ts`, après la ligne `ItemCard` ajoutée par la
tâche précédente :

```ts
export { MetadataForm } from "./MetadataForm";
export { ThumbnailUpload } from "./ThumbnailUpload";
```

- [ ] **Step 5: Migrer les imports dans `ItemDetailPage.tsx`**

```diff
-import { MetadataForm } from "../ui/MetadataForm";
-import { ThumbnailUpload } from "../ui/ThumbnailUpload";
+import { MetadataForm } from "../ui/kit/MetadataForm";
+import { ThumbnailUpload } from "../ui/kit/ThumbnailUpload";
```

- [ ] **Step 6: Migrer l'import dans `DatasetEditPage.tsx`**

```diff
-import { MetadataForm } from "../ui/MetadataForm";
+import { MetadataForm } from "../ui/kit/MetadataForm";
```

- [ ] **Step 7: Vérifier que les tests déplacés et les pages consommatrices passent toujours**

Run: `cd shell && npx vitest run src/ui/kit/MetadataForm.test.tsx src/ui/kit/ThumbnailUpload.test.tsx`
Expected: PASS (9 tests au total, identiques à avant le déplacement).

Run: `cd shell && npx vitest run src/pages/ItemDetailPage.test.tsx src/pages/DatasetEditPage.test.tsx`
Expected: PASS.

- [ ] **Step 8: Vérifier qu'aucun import legacy ne subsiste**

Run: `cd shell && grep -rn "ui/MetadataForm[\"']\|ui/ThumbnailUpload[\"']" src/`
Expected: aucune sortie.

- [ ] **Step 9: Commit**

```bash
git add shell/src/ui/kit/MetadataForm.tsx shell/src/ui/kit/MetadataForm.test.tsx \
  shell/src/ui/kit/ThumbnailUpload.tsx shell/src/ui/kit/ThumbnailUpload.test.tsx \
  shell/src/ui/MetadataForm.tsx shell/src/ui/MetadataForm.test.tsx \
  shell/src/ui/ThumbnailUpload.tsx shell/src/ui/ThumbnailUpload.test.tsx \
  shell/src/ui/kit/index.ts shell/src/pages/ItemDetailPage.tsx shell/src/pages/DatasetEditPage.tsx
git commit -m "refactor(shell): relocalise MetadataForm et ThumbnailUpload sous ui/kit/ (D10)

Consommateurs : ItemDetailPage.tsx (les deux), DatasetEditPage.tsx
(MetadataForm seul) — les deux derniers hors AppRuntimePage.tsx
(Tâche suivante) à mélanger encore ui/* legacy et ui/kit/*.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

## Tâche 16 — SP-C3 : `AppRuntimePage.tsx` — migrer `ui/button`/`ui/input` legacy vers `ui/kit/Button`/`ui/kit/Input` (D10)

**Contexte vérifié** : `AppRuntimePage.tsx` est la seule page qui importe
encore `ui/button.tsx`/`ui/input.tsx` (legacy, API identique à
`ui/kit/Button`/`ui/kit/Input` — mêmes props spread, mêmes variants
`default`/`outline`/`ghost` utilisés ici). Après cette tâche, `ui/button.tsx`
et `ui/input.tsx` n'ont plus aucun consommateur de production (même sort que
`ui/card.tsx`, déjà orphelin et assumé comme tel par son propre test) — ils
ne sont PAS supprimés dans cette tâche (hors périmètre D10, qui ne demande
que la migration des imports des pages, pas la suppression des fichiers
legacy eux-mêmes). `AppRuntimePage.test.tsx` (lignes 582, 592) commente
explicitement les chemins `../ui/button.tsx`/`../ui/input.tsx` — ces
commentaires deviennent faux après la migration et sont corrigés dans le
même geste.

**Files:**
- Modify: `shell/src/pages/AppRuntimePage.tsx:14,16`
- Modify: `shell/src/pages/AppRuntimePage.test.tsx:582,592`

**Interfaces:**
- Consumes: `Button`/`Input` de `shell/src/ui/kit/{Button,Input}.tsx` (déjà
  utilisés partout ailleurs dans le dépôt), signatures compatibles avec
  l'usage actuel (`variant="outline"` ; `size="sm"` ; `aria-label`, `value`,
  `onChange` sur `Input`).

- [ ] **Step 1: Migrer les imports**

```diff
-import { Button } from "../ui/button";
+import { Button } from "../ui/kit/Button";
 import { Dialog } from "../ui/kit/Dialog";
-import { Input } from "../ui/input";
+import { Input } from "../ui/kit/Input";
```

- [ ] **Step 2: Corriger les commentaires de test devenus faux**

Dans `shell/src/pages/AppRuntimePage.test.tsx` :

```diff
-  // `Button` (../ui/button.tsx) was out-of-scope for SP-B12a/b (it still
-  // hardcoded bg-slate-900/border-slate-300/etc by default) — fixed since by
-  // SP-B12c, so the whole action-bar subtree can now be scanned instead of
-  // just the div's own className.
+  // `Button` (../ui/kit/Button.tsx since SP-C3/D10, previously ../ui/button.tsx)
+  // was out-of-scope for SP-B12a/b (it still hardcoded bg-slate-900/
+  // border-slate-300/etc by default) — fixed since by SP-B12c, so the whole
+  // action-bar subtree can now be scanned instead of just the div's own
+  // className.
```

```diff
-  // Le dialogue (Radix Portal, hors `container`) porte `Input` (../ui/input.tsx)
-  // et deux `Button` — les trois désormais tokenisés (SP-B12c) : vérifiable en
-  // un coup sur baseElement plutôt qu'un className ciblé par élément.
+  // Le dialogue (Radix Portal, hors `container`) porte `Input`
+  // (../ui/kit/Input.tsx since SP-C3/D10, previously ../ui/input.tsx) et deux
+  // `Button` — les trois désormais tokenisés (SP-B12c) : vérifiable en un
+  // coup sur baseElement plutôt qu'un className ciblé par élément.
```

- [ ] **Step 3: Run complet du fichier de test**

Run: `cd shell && npx vitest run src/pages/AppRuntimePage.test.tsx`
Expected: PASS (y compris `"action-bar border and save-failed alert use
semantic tokens, not literal Tailwind colors (SP-B12a)"`, qui scanne
`baseElement` sans dépendre du chemin d'import).

- [ ] **Step 4: Vérifier qu'aucun import legacy ne subsiste**

Run: `cd shell && grep -rn "ui/button[\"']\|ui/input[\"']" src/`
Expected: aucune sortie (les deux fichiers `ui/button.tsx`/`ui/input.tsx`
restent sur le disque, orphelins — non supprimés dans cette tâche).

- [ ] **Step 5: Commit**

```bash
git add shell/src/pages/AppRuntimePage.tsx shell/src/pages/AppRuntimePage.test.tsx
git commit -m "refactor(shell): migre AppRuntimePage.tsx de ui/button et ui/input legacy vers ui/kit (D10)

Dernière page à mélanger ui/* legacy et ui/kit/* (cf. Tasks 4-5 pour
ItemCard/MetadataForm/ThumbnailUpload) — ui/button.tsx et ui/input.tsx
n'ont plus de consommateur de production après cette tâche (non
supprimés, hors périmètre D10).

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

## Tâche 17 — SP-C3 : câbler `printLayout.showLegend` dans l'overlay d'export d'`AppRuntimePage.tsx` (finition SP-B12/D14)

**Contexte vérifié** : `PrintLayoutConfig.showLegend` (`shell/src/api/
types.ts:298`) existe et est déjà authorable (`PrintLayoutPanel.tsx`,
consommé par `AppBuilderPage.tsx` via `<PrintLayoutPanel value={draft.
printLayout ?? null} onChange={setPrintLayout} />`) et déjà câblé côté
`MapEditorPage.tsx:166-175` (export d'une carte standalone, `kind: "map"`) —
mais jamais lu par `AppRuntimePage.tsx` (export d'une app/dashboard, `kind:
"app"`), qui ne mirrorait jusqu'ici que `title`/`cartouche` (lignes
197-208). `MapConfig` a un tableau `layers` de premier niveau ; `AppConfig`
n'en a pas — une app/dashboard porte ses couches à l'intérieur des
widgets `"map"` de sa page courante (`WidgetItem.props.layers: MapLayer[]`,
même forme que `MapConfig.layers`, cf. `mapWidget.tsx:295`). La légende de
cette tâche liste donc les couches visibles de TOUS les widgets `"map"` de
la page actuellement affichée (`pageId`), pas un concept générique
d'app — c'est la seule interprétation qui a un sens pour un type de
document qui n'est pas une carte.

**Files:**
- Modify: `shell/src/pages/AppRuntimePage.tsx`
- Test: `shell/src/pages/AppRuntimePage.test.tsx`

**Interfaces:**
- Consumes: `getPageLayout(config: AppConfig, pageId: string): AppLayout`
  (`shell/src/builder/pages.ts:13`) ; type `MapLayer`
  (`shell/src/api/types.ts:247-292`, champs communs à toutes les variantes :
  `id: string`, `title: string`, `visible: boolean`).
- Produces: aucune nouvelle interface exportée — chrome de rendu
  export-only supplémentaire, gardé par `isExportRender &&
  query.data.printLayout?.showLegend`.

- [ ] **Step 1: Écrire les tests (rouge attendu)**

Ajouter à `shell/src/pages/AppRuntimePage.test.tsx`, juste après le bloc
`registerWidget("__ctx_probe__", ...)` existant (avant le premier `test(`) :

```ts
// Stub le vrai widget "map" (mapWidget.tsx, qui lazy-charge MapView/
// maplibre-gl — poids inutile pour des tests qui n'exercent que le
// câblage de printLayout.showLegend dans AppRuntimePage.tsx, pas le rendu
// de la carte elle-même). registerWidget() écrase l'entrée du registre
// (registry.ts:47-50, avertit puis remplace) — sûr ici, aucun test de ce
// fichier n'exerce le vrai widget carte.
registerWidget({
  type: "map",
  label: "map (stub de test)",
  defaultProps: { layers: [] },
  defaultSize: { w: 4, h: 4 },
  PropsPanel: () => null,
  Component: () => <div data-testid="map-widget-stub" />,
});
```

Puis, après le bloc de tests `printLayout title/cartouche` (après la ligne
`});` qui clôt `"the printLayout overlay does not render outside of
exportRender"`) :

```ts
// Finition SP-B12/D14 : showLegend n'avait jamais été câblé côté
// app/dashboard (seul MapEditorPage.tsx le faisait) malgré CLAUDE.md
// marquant SP-B12 clos — cf. plan SP-C3, décision de scope.
const legendLayout = {
  type: "grid" as const,
  breakpoints: {},
  items: [
    {
      id: "m1",
      widget: "map",
      x: 0,
      y: 0,
      w: 4,
      h: 4,
      props: {
        layers: [
          { id: "l1", title: "Parcelles", visible: true, kind: "raster", tilesUrl: "https://x" },
          {
            id: "l2",
            title: "Hors périmètre",
            visible: false,
            kind: "raster",
            tilesUrl: "https://x",
          },
        ],
      },
    },
  ],
};
const legendConfig: AppConfig = {
  kind: "app",
  theme: {},
  dataSources: [],
  messages: [],
  layout: legendLayout,
  pages: [{ id: "page-1", name: "Accueil", layout: legendLayout }],
  printLayout: { showLegend: true },
};

test("exportRender=1 renders the printLayout legend overlay listing the page's visible map layers (finition SP-B12/D14)", async () => {
  renderRuntime(
    {
      getItem: vi.fn().mockResolvedValue(okItem),
      getAppConfig: vi.fn().mockResolvedValue(legendConfig),
    },
    ["/apps/9/page-1?exportRender=1"],
  );
  expect(await screen.findByText("Parcelles")).toBeInTheDocument();
  expect(screen.queryByText("Hors périmètre")).not.toBeInTheDocument();
});

test("the legend overlay does not render when showLegend is false, even during export", async () => {
  renderRuntime(
    {
      getItem: vi.fn().mockResolvedValue(okItem),
      getAppConfig: vi
        .fn()
        .mockResolvedValue({ ...legendConfig, printLayout: { showLegend: false } }),
    },
    ["/apps/9/page-1?exportRender=1"],
  );
  await screen.findByTestId("map-widget-stub");
  expect(screen.queryByText("Parcelles")).not.toBeInTheDocument();
});

test("the legend overlay does not render outside of exportRender even when showLegend is true", async () => {
  renderRuntime({
    getItem: vi.fn().mockResolvedValue(okItem),
    getAppConfig: vi.fn().mockResolvedValue(legendConfig),
  });
  await screen.findByTestId("map-widget-stub");
  expect(screen.queryByText("Parcelles")).not.toBeInTheDocument();
});
```

- [ ] **Step 2: Lancer les tests, vérifier qu'ils échouent**

Run: `cd shell && npx vitest run src/pages/AppRuntimePage.test.tsx -t "finition SP-B12/D14"`
Expected: FAIL sur le premier test (`findByText("Parcelles")` ne trouve
rien — l'overlay n'existe pas encore).

- [ ] **Step 3: Ajouter les imports nécessaires**

```diff
 import type { AnalyticsContextState } from "../builder/AnalyticsContext";
 import { EXTENT_DEBOUNCE_MS } from "../builder/AnalyticsContext";
+import { getPageLayout } from "../builder/pages";
+import type { MapLayer } from "../api/types";
```

(Emplacement exact : ajouter ces deux lignes à côté des imports existants
de `../builder/AnalyticsContext` et `../api/hooks` en tête de fichier —
respecter l'ordre d'imports déjà en place, pas de contrainte de tri
particulière dans ce fichier au-delà de "après les imports React/routeur".)

- [ ] **Step 4: Calculer les couches visibles de la page courante et rendre la légende**

Après le calcul de `showActionBar` (juste avant le `return`), ajouter :

```ts
// Finition SP-B12/D14 (cf. plan SP-C3) : une app/dashboard n'a pas de
// `layers` de premier niveau comme MapConfig — ses couches vivent dans les
// widgets "map" de la page actuellement affichée. `pageId` est absent sur
// la route racine `/apps/:pk` (config mono-page) : dans ce cas
// `query.data.layout` EST déjà la page unique (invariant documenté dans
// builder/pages.ts).
const legendLayout = pageId ? getPageLayout(query.data, pageId) : query.data.layout;
const legendLayers: MapLayer[] = legendLayout.items
  .filter((item) => item.widget === "map")
  .flatMap((item) => (item.props.layers as MapLayer[] | undefined) ?? [])
  .filter((layer) => layer.visible);
```

Puis, entre le bloc `title` et le bloc `cartouche` (entre les lignes 202 et
203 actuelles) :

```diff
       {isExportRender && query.data.printLayout?.title && (
         // gs-raw-color-ok: bg-white/90, cf. commentaire plus haut
         <div className="absolute left-2 top-2 rounded bg-white/90 px-2 py-1 text-sm font-medium">
           {query.data.printLayout.title}
         </div>
       )}
+      {isExportRender && query.data.printLayout?.showLegend && legendLayers.length > 0 && (
+        // gs-raw-color-ok: bg-white/90, cf. commentaire plus haut
+        <ul className="absolute bottom-2 left-2 rounded bg-white/90 px-2 py-1 text-xs">
+          {legendLayers.map((layer) => (
+            <li key={layer.id}>{layer.title}</li>
+          ))}
+        </ul>
+      )}
       {isExportRender && query.data.printLayout?.cartouche && (
         // gs-raw-color-ok: bg-white/90, cf. commentaire plus haut
         <div className="absolute bottom-2 right-2 rounded bg-white/90 px-2 py-1 text-xs">
           {query.data.printLayout.cartouche}
         </div>
       )}
```

Note : `legendLayers.length > 0` est un garde ajouté délibérément — au-delà
du "même patron" (`MapEditorPage.tsx` rend le `<ul>` inconditionnellement
dès que `showLegend` est vrai, même vide), une app/dashboard sans widget
carte sur sa page rendrait sinon un encart blanc flottant vide sur tout
export non cartographique. Documenté ici comme déviation volontaire.

- [ ] **Step 5: Lancer les tests, vérifier qu'ils passent**

Run: `cd shell && npx vitest run src/pages/AppRuntimePage.test.tsx -t "finition SP-B12/D14"`
Expected: PASS (3 tests).

- [ ] **Step 6: Run complet du fichier et de la suite**

Run: `cd shell && npx vitest run src/pages/AppRuntimePage.test.tsx`
Expected: entièrement vert.

Run: `cd shell && npm run test`
Expected: entièrement vert, couverture ≥ seuil (`.coverage-threshold`).

Run: `cd shell && npm run lint && npm run build`
Expected: les deux passent (tsc --noEmit + vite build + filet de taille de
bundle) — cette tâche n'ajoute aucune dépendance, le risque de bundle est
nul.

- [ ] **Step 7: Commit**

```bash
git add shell/src/pages/AppRuntimePage.tsx shell/src/pages/AppRuntimePage.test.tsx
git commit -m "fix(shell): câble printLayout.showLegend dans l'overlay d'export d'AppRuntimePage

Referme réellement SP-B12/D14 : seul MapEditorPage.tsx le faisait
jusqu'ici (CLAUDE.md marquait SP-B12 clos à tort). La légende liste
les couches visibles des widgets carte de la page actuellement
affichée (une app/dashboard n'a pas de layers de premier niveau comme
MapConfig).

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

### Notes de vérification — SP-C3 (self-review de l'agent de recherche, pas un sous-agent)

**Couverture de la spec SP-C3** :
- D46 (token + 24 occurrences + script de garde) → Tasks 1-2. ✓ (avec
  correction de classification documentée en tête de plan et dans le
  message de commit de Tâche 12 — écart vérifié contre le code, pas contre
  la spec).
- D47 (segmented-control) → Tâche 13. ✓
- D10 (4 pages, imports legacy `ui/ItemCard`/`ui/MetadataForm`/
  `ui/ThumbnailUpload`/`ui/button`/`ui/input`) → Tasks 4-6. ✓ (clés i18n
  orphelines explicitement hors périmètre, conforme à la décision de
  scope de la spec et à l'instruction reçue).
- Finition SP-B12/D14 (`printLayout.showLegend` sur `AppRuntimePage.tsx`)
  → Tâche 17. ✓

**Scan de placeholders** : aucun "TBD"/"gérer les cas limites"/"tests
similaires à..." — chaque étape porte son code exact, ses chemins de
fichiers exacts et ses commandes de vérification.

**Cohérence des types/signatures entre tâches** : `ItemCard`/
`MetadataForm`/`ThumbnailUpload` gardent des signatures identiques
(Tasks 4-5, simple déplacement) ; `Button`/`Input` de `ui/kit/` ont une API
strictement compatible avec `ui/button.tsx`/`ui/input.tsx` (vérifié Tâche 16,
mêmes props spread) ; `MapLayer`/`getPageLayout` (Tâche 17) sont les
signatures réelles lues dans `shell/src/api/types.ts`/`shell/src/builder/
pages.ts`, pas inventées.

### Incertitudes restantes — SP-C3 (pour l'exécutant)

- Tâche 12, Step 3 (vérification visuelle des 4 badges `text-2xs`) ne peut
  pas être automatisée dans ce plan — nécessite un `npm run dev` et un œil
  humain (ou une capture Playwright manuelle), non scriptée ici.
- Tâche 17 : le choix de garder `legendLayers.length > 0` comme garde
  supplémentaire (au lieu du mirroring strict de `MapEditorPage.tsx`, qui
  rend le `<ul>` même vide) est une décision d'ingénierie prise dans ce
  plan, pas explicitement tranchée par la spec — à confirmer/contester en
  revue si un désaccord produit existe.

---

### Constats de recherche — SP-C4 (D07+D49+D08, onboarding)

- Le hook `ui/kit/IconButton.tsx` avec `size="sm"` est **déjà** le patron
  établi pour un bouton d'aide inline circulaire : `KitGalleryPage.tsx:213`
  (`<IconButton icon={<span>?</span>} aria-label={t("kitGallery.helpAria")}
  size="sm" />`). Utilisé tel quel pour D49, pas de nouveau patron à
  inventer.
- `GET /admin/usage` (core/app/quotas/routes.py) répond déjà
  `{itemCount, collectionCount, userCount, storageBytes}`, testé par
  `core/tests/test_quotas_routes.py` (2 tests : 403 sans privilège,
  200+forme exacte avec `settings.instance.manage`). `max_items_per_tenant()`/
  `max_collections_per_tenant()`/`max_storage_bytes_per_tenant()` existent
  déjà dans `app/quotas/service.py:141-153`, lisent
  `CORE_QUOTA_MAX_ITEMS_PER_TENANT`/`CORE_QUOTA_MAX_COLLECTIONS_PER_TENANT`/
  `CORE_QUOTA_MAX_STORAGE_BYTES_PER_TENANT` (`None` si vide). Confirmé :
  zéro consommateur shell de cette route à ce jour (aucun hit hors
  `core-schema.d.ts` généré).
- `core/tests/test_feature_inventory.py` vérifie des **routes/outils/routes
  shell** déclarés, pas la forme de leur réponse — étendre
  `UsageSnapshotResponse` avec 3 champs sur une route déjà inventoriée
  n'ajoute aucune surface : **pas de nouvelle entrée
  `inventaire-fonctionnalites.jsonl` requise**, confirmé en lisant le test
  (`test_every_rest_route_is_claimed_by_an_inventory_entry` compare des
  `surface_id` route+méthode, indifférent au schéma de réponse).
- `AdminInfrastructurePage.tsx` n'a **aucun** hook de données propre à cette
  page aujourd'hui (seulement `useInstanceInfo`/`useLaunchAdminTool`) — le
  bloc MinIO existant se termine ligne 79 (`{t("infrastructure.minioNote")}`
  suivi de `</p>`), insertion juste après, avant `{launch.isError && ...}`.
- `ItemClient` agrège ses méthodes par fichier `api/domains/<nom>.ts` +
  `<nom>.hooks.ts`, réexporté par le barrel `api/hooks.ts`
  (`export * from "./domains/<nom>.hooks"`) et enregistré dans
  `itemClient.ts` (`...create<Nom>Methods(base)`). `getInstanceInfo` est
  l'exception : posé directement dans `domains/items.ts` plutôt que dans
  un fichier dédié — **pas** le patron à suivre pour un usage nouveau. Un
  nouveau petit domaine `domains/quotaUsage.ts` (+`.hooks.ts`) est plus
  cohérent avec le reste (usage/secrets/tiles3d ont chacun leur fichier).
- `navigableDomains(profile)` retourne `{domain, state}` où `state` peut
  être `"visible"` **ou** `"locked"` (jamais `"hidden"`, déjà filtré) — la
  palette ne doit lister que les entrées `"visible"` (une entrée
  `"locked"` mène à une route qui affichera un message de capacité coupée,
  décision : ne pas la proposer comme raccourci, cohérent avec
  `DomainBar` qui rend les `"locked"` en `<span>` non cliquable).
- **Aucun bus d'événements DOM (`CustomEvent`) n'existe dans ce dépôt** pour
  faire communiquer deux composants de chrome indépendants (`grep
  CustomEvent`/`dispatchEvent` : 2 hits, tous deux dans le sandbox Web
  Components `builder/wc/`, sans rapport). `NewItemButton` gère son
  `open` en état local privé, jamais levé au parent (`TopBar` le monte
  sans props de contrôle). Décision de conception pour l'action "Nouvel
  élément" de la palette : donner un `id="new-item-trigger"` stable au
  `<Button>` déclencheur de `NewItemButton.tsx` (ligne 212) et faire
  `document.getElementById("new-item-trigger")?.click()` depuis la
  palette — réutilise tel quel tout le state/garde/formulaire existants,
  aucune duplication de logique de création. Visibilité de l'entrée dans
  la liste de la palette : dupliquer la même garde grossière que
  `NewItemButton` (`apps.manage`/`maps.manage`/`data.manage`/
  `automation.manage`) via `useMe()`, un doublon minimal assumé plutôt
  qu'un refactor de `NewItemButton` (hors périmètre D07).

## Tâche 18 — SP-C4 : cœur : `UsageSnapshotResponse` porte les plafonds (D08 volet 1)

**Files:**
- Modify: `core/app/quotas/routes.py`
- Test: `core/tests/test_quotas_routes.py`

**Interfaces:**
- Consumes: `max_items_per_tenant()`/`max_collections_per_tenant()`/
  `max_storage_bytes_per_tenant()` (`app/quotas/service.py`, existants,
  signature `() -> int | None`).
- Produces: `UsageSnapshotResponse` gagne 3 champs optionnels
  `maxItems: int | None`, `maxCollections: int | None`,
  `maxStorageBytes: int | None` — consommé par la Tâche 20 (régénération
  OpenAPI/TS) puis la Tâche 21 (shell).

- [ ] **Step 1: Test rouge — la réponse porte les plafonds configurés**

  Dans `core/tests/test_quotas_routes.py`, ajouter :

  ```python
  def test_get_usage_includes_configured_limits(env, monkeypatch):
      app, client, admin, _regular = env
      _as(app, admin)
      monkeypatch.setenv("CORE_QUOTA_MAX_ITEMS_PER_TENANT", "500")
      monkeypatch.setenv("CORE_QUOTA_MAX_STORAGE_BYTES_PER_TENANT", "1000000")
      resp = client.get("/v1/admin/usage")
      assert resp.status_code == 200
      body = resp.json()
      assert body["maxItems"] == 500
      assert body["maxCollections"] is None
      assert body["maxStorageBytes"] == 1000000


  def test_get_usage_limits_are_null_when_unconfigured(env):
      app, client, admin, _regular = env
      _as(app, admin)
      resp = client.get("/v1/admin/usage")
      assert resp.status_code == 200
      body = resp.json()
      assert body["maxItems"] is None
      assert body["maxCollections"] is None
      assert body["maxStorageBytes"] is None
  ```

  Adapter aussi l'assertion de forme existante
  (`test_get_usage_returns_snapshot_shape_for_privileged_admin`) : le
  `set(body)` doit désormais inclure les 3 nouvelles clés.

  Run: `cd core && CORE_SECRETS_MASTER_KEY="AAECAwQFBgcICQoLDA0ODxAREhMUFRYXGBkaGxwdHh8=" uv run pytest tests/test_quotas_routes.py -v`
  Expected: FAIL — `KeyError`/assertion sur `maxItems` absent de `body`.

- [ ] **Step 2: Implémentation minimale**

  Dans `core/app/quotas/routes.py` :

  ```python
  from app.quotas.service import (
      max_collections_per_tenant,
      max_items_per_tenant,
      max_storage_bytes_per_tenant,
      usage_for_tenant,
  )
  ```

  ```python
  class UsageSnapshotResponse(BaseModel):
      itemCount: int
      collectionCount: int
      userCount: int
      storageBytes: int
      maxItems: int | None
      maxCollections: int | None
      maxStorageBytes: int | None
  ```

  ```python
  @router.get("/admin/usage", response_model=UsageSnapshotResponse)
  def get_usage(
      user: User = Depends(get_current_user),
      session: Session = Depends(get_session),
      s3=Depends(get_s3_client),
  ) -> UsageSnapshotResponse:
      require_privilege(session, user, Privilege.SETTINGS_INSTANCE_MANAGE.value)
      snapshot = usage_for_tenant(session, s3, user.tenant_id)
      return UsageSnapshotResponse(
          itemCount=snapshot.item_count,
          collectionCount=snapshot.collection_count,
          userCount=snapshot.user_count,
          storageBytes=snapshot.storage_bytes,
          maxItems=max_items_per_tenant(),
          maxCollections=max_collections_per_tenant(),
          maxStorageBytes=max_storage_bytes_per_tenant(),
      )
  ```

- [ ] **Step 3: Test vert**

  Run: `cd core && CORE_SECRETS_MASTER_KEY="AAECAwQFBgcICQoLDA0ODxAREhMUFRYXGBkaGxwdHh8=" uv run pytest tests/test_quotas_routes.py -v`
  Expected: PASS (4 tests).

- [ ] **Step 4: Commit**

  ```bash
  git add core/app/quotas/routes.py core/tests/test_quotas_routes.py
  git commit -m "$(cat <<'EOF'
  feat(core): expose les plafonds de quota configurés dans GET /admin/usage

  Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
  EOF
  )"
  ```

## Tâche 19 — SP-C4 : régénération OpenAPI + types TS (D08 volet 2)

**Files:**
- Modify: `core/openapi.json`
- Modify: `shell/src/api/generated/core-schema.d.ts`

**Interfaces:**
- Consumes: schéma `UsageSnapshotResponse` étendu par la Tâche 18.
- Produces: types TS à jour, consommés par la Tâche 21
  (`domains/quotaUsage.ts`).

- [ ] **Step 1: Régénérer**

  Piège n°1 CLAUDE.md — la commande nue échoue en
  `ModuleNotFoundError: app` :

  ```bash
  cd core && PYTHONPATH=. \
    CORE_SECRETS_MASTER_KEY="AAECAwQFBgcICQoLDA0ODxAREhMUFRYXGBkaGxwdHh8=" \
    uv run python scripts/export_openapi.py openapi.json
  cd ../shell && npm run gen:api-types
  ```

- [ ] **Step 2: Vérifier le diff**

  Run: `git diff --stat core/openapi.json shell/src/api/generated/core-schema.d.ts`
  Expected: diff non vide, limité à l'ajout de `maxItems`/`maxCollections`/
  `maxStorageBytes` (`number | null`) sur le schéma `UsageSnapshotResponse`
  — aucune autre route ne doit apparaître dans le diff (sinon une
  régénération antérieure a été oubliée par une tâche précédente : à
  investiguer avant de committer).

- [ ] **Step 3: Commit**

  ```bash
  git add core/openapi.json shell/src/api/generated/core-schema.d.ts
  git commit -m "$(cat <<'EOF'
  chore(shell): régénère OpenAPI + types TS (plafonds de quota)

  Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
  EOF
  )"
  ```

## Tâche 20 — SP-C4 : shell : `useQuotaUsage()` + affichage dans `AdminInfrastructurePage` (D08 volet 3)

**Files:**
- Create: `shell/src/api/domains/quotaUsage.ts`
- Create: `shell/src/api/domains/quotaUsage.hooks.ts`
- Modify: `shell/src/api/types.ts`
- Modify: `shell/src/api/itemClient.ts`
- Modify: `shell/src/api/hooks.ts`
- Modify: `shell/src/pages/AdminInfrastructurePage.tsx`
- Modify: `shell/src/i18n/catalog.fr.ts`
- Test: `shell/src/pages/AdminInfrastructurePage.test.tsx`

**Interfaces:**
- Consumes: `GET /admin/usage` (Tâche 18/19), `ItemClientBase.request`
  (`api/base.ts`, patron déjà suivi par tous les fichiers
  `domains/*.ts`).
- Produces: `QuotaUsage` (type), `getQuotaUsage(): Promise<QuotaUsage>`
  (méthode `ItemClient`), `useQuotaUsage()` (hook React Query,
  `queryKey: ["quota-usage"]`).

- [ ] **Step 1: Type + méthode client**

  Dans `shell/src/api/types.ts`, à côté de `UsageSummary`/`UsageTask`
  (lignes ~127-166) :

  ```ts
  export type QuotaUsage = {
    itemCount: number;
    collectionCount: number;
    userCount: number;
    storageBytes: number;
    maxItems: number | null;
    maxCollections: number | null;
    maxStorageBytes: number | null;
  };
  ```

  Sur l'interface `ItemClient` (à côté de `getInstanceInfo(): Promise<InstanceInfo>;`) :

  ```ts
  getQuotaUsage(): Promise<QuotaUsage>;
  ```

  Créer `shell/src/api/domains/quotaUsage.ts` :

  ```ts
  // SPDX-License-Identifier: Apache-2.0
  import type { ItemClient, QuotaUsage } from "../types";
  import type { ItemClientBase } from "../base";

  type QuotaUsageMethods = Pick<ItemClient, "getQuotaUsage">;

  export function createQuotaUsageMethods(base: ItemClientBase): QuotaUsageMethods {
    const { request } = base;
    return {
      async getQuotaUsage(): Promise<QuotaUsage> {
        return request<QuotaUsage>("GET", "/admin/usage");
      },
    };
  }
  ```

  Créer `shell/src/api/domains/quotaUsage.hooks.ts` :

  ```ts
  // SPDX-License-Identifier: Apache-2.0
  import { useQuery } from "@tanstack/react-query";
  import { useItemClient as useItemClientInternal } from "../ItemClientProvider";

  export function useQuotaUsage(options: { enabled?: boolean } = {}) {
    const client = useItemClientInternal();
    return useQuery({
      queryKey: ["quota-usage"],
      queryFn: () => client.getQuotaUsage(),
      enabled: options.enabled ?? true,
    });
  }
  ```

  Dans `shell/src/api/hooks.ts`, ajouter :

  ```ts
  export * from "./domains/quotaUsage.hooks";
  ```

  Dans `shell/src/api/itemClient.ts` :

  ```ts
  import { createQuotaUsageMethods } from "./domains/quotaUsage";
  ```

  ```ts
    ...createQuotaUsageMethods(base),
  ```

  (à côté de `...createUsageMethods(base),`).

- [ ] **Step 2: Clés i18n**

  Dans `shell/src/i18n/catalog.fr.ts`, section `infrastructure.*` :

  ```ts
  "infrastructure.usageHeading": "Utilisation",
  "infrastructure.usageItems": "Éléments : {count}",
  "infrastructure.usageItemsWithLimit": "Éléments : {count} / {limit}",
  "infrastructure.usageCollections": "Collections : {count}",
  "infrastructure.usageCollectionsWithLimit": "Collections : {count} / {limit}",
  "infrastructure.usageStorage": "Stockage : {size}",
  "infrastructure.usageStorageWithLimit": "Stockage : {size} / {limitSize}",
  "infrastructure.usageNoLimit": "pas de limite configurée",
  ```

- [ ] **Step 3: Test rouge — le bloc usage s'affiche avec et sans plafond**

  Dans `shell/src/pages/AdminInfrastructurePage.test.tsx` (suivre le mock
  `useItemClient`/`ItemClientProvider` déjà en tête du fichier existant),
  ajouter :

  ```tsx
  it("affiche l'utilisation avec les plafonds configurés", async () => {
    mockClient.getQuotaUsage = vi.fn().mockResolvedValue({
      itemCount: 12,
      collectionCount: 3,
      userCount: 5,
      storageBytes: 2_000_000,
      maxItems: 100,
      maxCollections: null,
      maxStorageBytes: 10_000_000,
    });
    render(<AdminInfrastructurePage />, { wrapper });
    expect(await screen.findByText("Éléments : 12 / 100")).toBeInTheDocument();
    expect(screen.getByText(/Collections : 3/)).toBeInTheDocument();
    expect(screen.getByText(/pas de limite configurée/)).toBeInTheDocument();
  });
  ```

  Adapter le nom du mock client (`mockClient`) et `wrapper` à ceux
  réellement déclarés dans le fichier de test existant de cette page.

  Run: `cd shell && npx vitest run src/pages/AdminInfrastructurePage.test.tsx`
  Expected: FAIL — aucun texte "Éléments" rendu (bloc absent).

- [ ] **Step 4: Implémentation**

  Dans `shell/src/pages/AdminInfrastructurePage.tsx`, ajouter l'import et
  le hook :

  ```tsx
  import { useInstanceInfo, useLaunchAdminTool, useQuotaUsage } from "../api/hooks";
  ```

  ```tsx
  const usageQuery = useQuotaUsage();
  const usage = usageQuery.data;

  function formatBytes(bytes: number): string {
    const mb = bytes / (1024 * 1024);
    return mb >= 1024 ? `${(mb / 1024).toFixed(1)} Go` : `${mb.toFixed(1)} Mo`;
  }
  ```

  Insérer après le `</p>` du bloc MinIO (ligne 79, avant
  `{launch.isError && ...}`) :

  ```tsx
  {usage && (
    <div className="flex flex-col gap-1 text-sm text-ink-2">
      <p className="font-medium text-ink">{t("infrastructure.usageHeading")}</p>
      <p>
        {usage.maxItems === null
          ? t("infrastructure.usageItems", { count: usage.itemCount })
          : t("infrastructure.usageItemsWithLimit", {
              count: usage.itemCount,
              limit: usage.maxItems,
            })}
      </p>
      <p>
        {usage.maxCollections === null
          ? t("infrastructure.usageCollections", { count: usage.collectionCount })
          : t("infrastructure.usageCollectionsWithLimit", {
              count: usage.collectionCount,
              limit: usage.maxCollections,
            })}
      </p>
      <p>
        {usage.maxStorageBytes === null
          ? `${t("infrastructure.usageStorage", { size: formatBytes(usage.storageBytes) })} (${t("infrastructure.usageNoLimit")})`
          : t("infrastructure.usageStorageWithLimit", {
              size: formatBytes(usage.storageBytes),
              limitSize: formatBytes(usage.maxStorageBytes),
            })}
      </p>
    </div>
  )}
  ```

  Note : quand `max*` est `null`, le gabarit `usageItems`/`usageCollections`
  ne mentionne déjà aucune limite (pas besoin du suffixe `usageNoLimit`
  pour ces deux-là) ; seul le stockage l'affiche explicitement, cf. la
  décision de scope de la spec ("repli 'pas de limite configurée'").
  Ajuster le test Step 3 en conséquence s'il visait un texte différent
  pour Items/Collections.

- [ ] **Step 5: Test vert**

  Run: `cd shell && npx vitest run src/pages/AdminInfrastructurePage.test.tsx`
  Expected: PASS.

- [ ] **Step 6: Commit**

  ```bash
  git add shell/src/api/domains/quotaUsage.ts shell/src/api/domains/quotaUsage.hooks.ts \
    shell/src/api/types.ts shell/src/api/itemClient.ts shell/src/api/hooks.ts \
    shell/src/pages/AdminInfrastructurePage.tsx shell/src/i18n/catalog.fr.ts \
    shell/src/pages/AdminInfrastructurePage.test.tsx
  git commit -m "$(cat <<'EOF'
  feat(shell): affiche l'utilisation et les plafonds de quota dans Infrastructure

  Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
  EOF
  )"
  ```

## Tâche 21 — SP-C4 : `ui/kit/CommandPalette.tsx` + raccordement ⌘K (D07)

**Files:**
- Create: `shell/src/ui/kit/CommandPalette.tsx`
- Create: `shell/src/ui/kit/CommandPalette.test.tsx`
- Modify: `shell/src/shell/NewItemButton.tsx`
- Modify: `shell/src/shell/AppLayout.tsx`
- Modify: `shell/src/shell/chrome/TopBar.tsx`
- Modify: `shell/src/i18n/catalog.fr.ts`

**Interfaces:**
- Consumes: `Dialog` (`ui/kit/Dialog.tsx`, props `{open, onOpenChange,
  title, children}`), `Input` (`ui/kit/Input.tsx`), `navigableDomains`/
  `Profile` (`auth/capabilities.ts`), `DOMAIN_PATHS`
  (`shell/chrome/domainRoutes.ts`), `SETTINGS_LINKS`-équivalent (7
  destinations admin, dupliquées localement — `SettingsNav.tsx` ne les
  exporte pas, cf. Step 1), `useMe()` (`api/hooks`), `Kbd`
  (`ui/kit/Kbd.tsx`).
- Produces: `CommandPalette` (composant, props `{open, onOpenChange,
  profile}`), consommé uniquement par `AppLayout.tsx`.

- [ ] **Step 1: Exporter les destinations admin depuis `SettingsNav.tsx`**

  `SETTINGS_LINKS` est déclaré `const` non exportée
  (`shell/src/shell/chrome/SettingsNav.tsx:12`). Dans ce fichier, changer :

  ```ts
  const SETTINGS_LINKS: readonly { to: string; labelKey: MessageKey; privilege?: string }[] = [
  ```

  en :

  ```ts
  export const SETTINGS_LINKS: readonly {
    to: string;
    labelKey: MessageKey;
    privilege?: string;
  }[] = [
  ```

  (aucun autre changement dans ce fichier — `SettingsNav()` continue de
  l'utiliser tel quel).

- [ ] **Step 2: `id` stable sur le déclencheur de `NewItemButton`**

  Dans `shell/src/shell/NewItemButton.tsx`, ligne 212 :

  ```tsx
  <Button size="sm" {...drawerPanel.triggerProps} onClick={() => setOpen(true)}>
  ```

  devient :

  ```tsx
  <Button
    id="new-item-trigger"
    size="sm"
    {...drawerPanel.triggerProps}
    onClick={() => setOpen(true)}
  >
  ```

  (le bouton reste absent du DOM quand `hasAnyCreatableKind` est faux —
  `NewItemButton` retourne déjà `null` ligne 132 dans ce cas, donc l'`id`
  n'existe que quand l'action est réellement possible).

- [ ] **Step 3: Test rouge — navigation clavier + action + fermeture**

  Créer `shell/src/ui/kit/CommandPalette.test.tsx` :

  ```tsx
  // SPDX-License-Identifier: Apache-2.0
  import { describe, expect, it, vi } from "vitest";
  import { render, screen, waitFor } from "@testing-library/react";
  import userEvent from "@testing-library/user-event";
  import { MemoryRouter } from "react-router-dom";
  import { CommandPalette } from "./CommandPalette";
  import type { Profile } from "../../auth/capabilities";

  const navigateMock = vi.fn();
  vi.mock("react-router-dom", async () => {
    const actual = await vi.importActual("react-router-dom");
    return { ...actual, useNavigate: () => navigateMock };
  });

  vi.mock("../../api/hooks", () => ({
    useMe: () => ({ data: { privileges: ["apps.manage", "admin.users.manage"] } }),
  }));

  const profile: Profile = {
    privileges: new Set(["apps.manage", "admin.users.manage"]),
    capabilities: {
      readOnly: false,
      etlEnabled: false,
      exportEnabled: false,
      appExportEnabled: false,
      tileset3dEnabled: false,
      terrain3dEnabled: false,
      copilotEnabled: false,
      quotasEnabled: false,
    },
  };

  describe("CommandPalette", () => {
    it("navigue vers le domaine sélectionné au clavier puis se ferme", async () => {
      const onOpenChange = vi.fn();
      render(
        <MemoryRouter>
          <CommandPalette open onOpenChange={onOpenChange} profile={profile} />
        </MemoryRouter>,
      );
      const input = screen.getByRole("combobox");
      await userEvent.type(input, "Apps");
      await userEvent.keyboard("{Enter}");
      await waitFor(() => expect(navigateMock).toHaveBeenCalledWith("/?type=app"));
      expect(onOpenChange).toHaveBeenCalledWith(false);
    });

    it("propose Nouvel élément et clique le vrai déclencheur du DOM", async () => {
      document.body.innerHTML = '<button id="new-item-trigger">Nouveau</button>';
      const realButton = document.getElementById("new-item-trigger")!;
      const clickSpy = vi.spyOn(realButton, "click");
      render(
        <MemoryRouter>
          <CommandPalette open onOpenChange={vi.fn()} profile={profile} />
        </MemoryRouter>,
      );
      const input = screen.getByRole("combobox");
      await userEvent.type(input, "Nouvel");
      await userEvent.keyboard("{Enter}");
      expect(clickSpy).toHaveBeenCalled();
    });

    it("ferme sur Échap sans naviguer", async () => {
      const onOpenChange = vi.fn();
      render(
        <MemoryRouter>
          <CommandPalette open onOpenChange={onOpenChange} profile={profile} />
        </MemoryRouter>,
      );
      await userEvent.keyboard("{Escape}");
      expect(onOpenChange).toHaveBeenCalledWith(false);
      expect(navigateMock).not.toHaveBeenCalled();
    });
  });
  ```

  Run: `cd shell && npx vitest run src/ui/kit/CommandPalette.test.tsx`
  Expected: FAIL — `Cannot find module './CommandPalette'`.

- [ ] **Step 4: Implémentation**

  Créer `shell/src/ui/kit/CommandPalette.tsx` :

  ```tsx
  // SPDX-License-Identifier: Apache-2.0
  import { useEffect, useMemo, useState } from "react";
  import { useNavigate } from "react-router-dom";
  import { Dialog } from "./Dialog";
  import { Input } from "./Input";
  import { navigableDomains, type Profile } from "../../auth/capabilities";
  import { DOMAIN_PATHS } from "../../shell/chrome/domainRoutes";
  import { SETTINGS_LINKS } from "../../shell/chrome/SettingsNav";
  import { useMe } from "../../api/hooks";
  import { t } from "../../i18n";

  type CommandItem = { id: string; label: string; run: () => void };

  const CREATE_PRIVILEGES = [
    "apps.manage",
    "maps.manage",
    "data.manage",
    "automation.manage",
  ] as const;

  export function CommandPalette({
    open,
    onOpenChange,
    profile,
  }: {
    open: boolean;
    onOpenChange: (open: boolean) => void;
    profile: Profile;
  }) {
    const navigate = useNavigate();
    const meQuery = useMe();
    const [query, setQuery] = useState("");
    const [activeIndex, setActiveIndex] = useState(0);

    useEffect(() => {
      if (open) {
        setQuery("");
        setActiveIndex(0);
      }
    }, [open]);

    const items = useMemo<CommandItem[]>(() => {
      const out: CommandItem[] = [];
      for (const { domain } of navigableDomains(profile)) {
        out.push({
          id: `domain:${domain.id}`,
          label: t(domain.labelKey),
          run: () => navigate(DOMAIN_PATHS[domain.id]),
        });
      }
      // Duplique volontairement la garde grossière de NewItemButton.tsx
      // (privilège de création, pas la capacité etlEnabled du pipeline —
      // le clic réel sur le bouton du DOM refait la vérification complète
      // et n'ouvre le tiroir que si elle passe) : éviter un couplage direct
      // à l'état interne de ce composant, hors périmètre de cette tâche.
      const privileges = meQuery.data?.privileges ?? [];
      if (CREATE_PRIVILEGES.some((p) => privileges.includes(p))) {
        out.push({
          id: "action:new-item",
          label: t("commandPalette.newItemAction"),
          run: () => document.getElementById("new-item-trigger")?.click(),
        });
      }
      for (const link of SETTINGS_LINKS) {
        if (link.privilege !== undefined && !privileges.includes(link.privilege)) continue;
        out.push({
          id: `settings:${link.to}`,
          label: t(link.labelKey),
          run: () => navigate(link.to),
        });
      }
      return out;
    }, [profile, meQuery.data, navigate]);

    const filtered = useMemo(
      () => items.filter((i) => i.label.toLowerCase().includes(query.toLowerCase())),
      [items, query],
    );

    function commit(item: CommandItem) {
      item.run();
      onOpenChange(false);
    }

    return (
      <Dialog open={open} onOpenChange={onOpenChange} title={t("commandPalette.title")}>
        <Input
          role="combobox"
          aria-label={t("commandPalette.searchAria")}
          aria-expanded={open}
          autoFocus
          autoComplete="off"
          value={query}
          onChange={(e) => {
            setQuery(e.target.value);
            setActiveIndex(0);
          }}
          onKeyDown={(e) => {
            if (e.key === "ArrowDown") {
              e.preventDefault();
              setActiveIndex((i) => Math.min(i + 1, filtered.length - 1));
            } else if (e.key === "ArrowUp") {
              e.preventDefault();
              setActiveIndex((i) => Math.max(i - 1, 0));
            } else if (e.key === "Enter") {
              e.preventDefault();
              if (filtered[activeIndex]) commit(filtered[activeIndex]);
            } else if (e.key === "Escape") {
              onOpenChange(false);
            }
          }}
        />
        <ul role="listbox" className="mt-2 flex max-h-80 flex-col gap-0.5 overflow-y-auto">
          {filtered.map((item, index) => (
            <li key={item.id}>
              <button
                type="button"
                role="option"
                aria-selected={index === activeIndex}
                onClick={() => commit(item)}
                className={
                  index === activeIndex
                    ? "w-full rounded-md bg-sunken px-2 py-1.5 text-left text-sm text-ink"
                    : "w-full rounded-md px-2 py-1.5 text-left text-sm text-ink hover:bg-sunken"
                }
              >
                {item.label}
              </button>
            </li>
          ))}
        </ul>
      </Dialog>
    );
  }
  ```

  Clés i18n (`shell/src/i18n/catalog.fr.ts`) :

  ```ts
  "commandPalette.title": "Palette de commandes",
  "commandPalette.searchAria": "Rechercher une action",
  "commandPalette.newItemAction": "Nouvel élément",
  ```

  Note : la garde `useMe` du test mocke `../../api/hooks` — vérifier que
  le chemin d'import relatif dans `CommandPalette.tsx`
  (`../../api/hooks`) correspond bien à celui mocké par le test (les deux
  fichiers sont à la même profondeur `ui/kit/`).

- [ ] **Step 5: Test vert**

  Run: `cd shell && npx vitest run src/ui/kit/CommandPalette.test.tsx`
  Expected: PASS (3 tests).

- [ ] **Step 6: Raccordement `AppLayout.tsx` + bouton `TopBar.tsx`**

  Dans `shell/src/shell/AppLayout.tsx`, ajouter en tête (à côté des
  autres imports) :

  ```tsx
  import { lazy, Suspense, useEffect, useState } from "react";
  ```

  ```tsx
  const CommandPalette = lazy(() =>
    import("../ui/kit/CommandPalette").then((m) => ({ default: m.CommandPalette })),
  );
  ```

  Dans le corps du composant, après le calcul de `profile` :

  ```tsx
  const [paletteOpen, setPaletteOpen] = useState(false);

  useEffect(() => {
    function onKeyDown(e: KeyboardEvent) {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        setPaletteOpen(true);
      }
    }
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, []);
  ```

  Et dans le JSX rendu, avant `<StatusBar />` (ou juste après `<TopBar
  .../>`) :

  ```tsx
  {paletteOpen && (
    <Suspense fallback={null}>
      <CommandPalette open={paletteOpen} onOpenChange={setPaletteOpen} profile={profile} />
    </Suspense>
  )}
  ```

  (montage conditionnel sur `paletteOpen` : le chunk lazy n'est demandé
  qu'au premier Ctrl/Cmd+K, jamais au chargement initial — patron déjà
  posé par SP-60 pour les routes, ici appliqué à un composant hors route.)

  Dans `shell/src/shell/chrome/TopBar.tsx`, ajouter un bouton visible à
  côté de `NewItemButton` :

  ```tsx
  import { Kbd } from "../../ui/kit/Kbd";
  ```

  ```tsx
  <button
    type="button"
    onClick={() => window.dispatchEvent(new KeyboardEvent("keydown", { key: "k", metaKey: true }))}
    className="flex items-center gap-1.5 rounded-md border border-rule px-2 py-1 text-xs text-ink-2 hover:bg-sunken"
  >
    {t("commandPalette.triggerLabel")}
    <Kbd>⌘K</Kbd>
  </button>
  ```

  Clé i18n : `"commandPalette.triggerLabel": "Rechercher"`.

  **Alternative plus simple à considérer en exécution** : plutôt que de
  synthétiser un `KeyboardEvent`, exposer directement `setPaletteOpen`
  via un `onOpenPalette` prop de `TopBar` — préférable si `TopBar` accepte
  déjà de recevoir des callbacks (il reçoit déjà `tileset3dEnabled` en
  prop) ; trancher au moment de coder plutôt que de garder la synthèse
  d'événement, plus fragile (dépend de ce que `AppLayout`'s listener
  vérifie exactement sur l'event).

- [ ] **Step 7: Vérification manuelle + suite complète**

  Run: `cd shell && npx vitest run src/shell/AppLayout.test.tsx src/shell/chrome/TopBar.test.tsx src/ui/kit/CommandPalette.test.tsx`
  Expected: PASS. Si `AppLayout.test.tsx`/`TopBar.test.tsx` n'existent pas
  encore avec cette forme, vérifier qu'aucun test existant ne casse
  (`npx vitest run src/shell/`).

- [ ] **Step 8: Commit**

  ```bash
  git add shell/src/ui/kit/CommandPalette.tsx shell/src/ui/kit/CommandPalette.test.tsx \
    shell/src/shell/NewItemButton.tsx shell/src/shell/AppLayout.tsx \
    shell/src/shell/chrome/TopBar.tsx shell/src/shell/chrome/SettingsNav.tsx \
    shell/src/i18n/catalog.fr.ts
  git commit -m "$(cat <<'EOF'
  feat(shell): palette de commandes ⌘K (domaines, nouvel élément, admin)

  Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
  EOF
  )"
  ```

## Tâche 22 — SP-C4 : aide contextuelle `Popover`+`HelpCircle` sur 4 sites + fix i18n `SqlLabPage` (D49)

**Files:**
- Modify: `shell/src/builder/PropsPanel.tsx`
- Modify: `shell/src/pages/AppBuilderPage.tsx`
- Modify: `shell/src/pages/PipelineBuilderPage.tsx`
- Modify: `shell/src/pages/SqlLabPage.tsx`
- Modify: `shell/src/i18n/catalog.fr.ts`
- Test: `shell/src/builder/PropsPanel.test.tsx` (1 des 4 sites, patron
  répliqué manuellement sur les 3 autres — pas de composant partagé
  nouveau, `Popover`+`IconButton` existent déjà tels quels)

**Interfaces:**
- Consumes: `Popover` (`ui/kit/Popover.tsx`, props `{trigger, children,
  "aria-label"?, side?}`), `IconButton` (`ui/kit/IconButton.tsx`, props
  `{icon, "aria-label", size?}`), `HelpCircle` (`lucide-react`, déjà
  dépendance directe).
- Produces: aucune nouvelle interface.

- [ ] **Step 1: Test rouge — CEL (`PropsPanel.tsx`)**

  Dans `shell/src/builder/PropsPanel.test.tsx` (fichier existant, suivre
  son patron de rendu/props factices) :

  ```tsx
  it("propose une aide contextuelle sur la condition d'affichage CEL", async () => {
    render(<PropsPanel item={item} dataSources={[]} onChange={vi.fn()} onVisibleWhenChange={vi.fn()} />);
    const helpButton = screen.getByRole("button", { name: t("propsPanel.visibleWhenHelpAria") });
    await userEvent.click(helpButton);
    expect(await screen.findByText(t("propsPanel.visibleWhenHelpBody"))).toBeInTheDocument();
  });
  ```

  Adapter `item`/imports (`render`, `screen`, `userEvent`, `t`) à ceux
  déjà déclarés en tête du fichier de test existant.

  Run: `cd shell && npx vitest run src/builder/PropsPanel.test.tsx`
  Expected: FAIL — bouton d'aide introuvable.

- [ ] **Step 2: Implémentation CEL**

  Dans `shell/src/builder/PropsPanel.tsx` :

  ```tsx
  import { HelpCircle } from "lucide-react";
  import { IconButton } from "../ui/kit/IconButton";
  import { Popover } from "../ui/kit/Popover";
  ```

  ```tsx
      <label className="flex flex-col gap-1 text-sm">
        <span className="flex items-center gap-1">
          {t("propsPanel.visibleWhenLabel")}
          <Popover
            aria-label={t("propsPanel.visibleWhenHelpAria")}
            trigger={
              <IconButton
                icon={<HelpCircle size={14} />}
                aria-label={t("propsPanel.visibleWhenHelpAria")}
                size="sm"
              />
            }
          >
            {t("propsPanel.visibleWhenHelpBody")}
          </Popover>
        </span>
        <textarea
  ```

  (remplace la ligne `{t("propsPanel.visibleWhenLabel")}` seule par ce
  bloc ; le reste de `<textarea .../>` et son gestionnaire d'erreur
  inchangés).

  Clés i18n :

  ```ts
  "propsPanel.visibleWhenHelpAria": "Aide sur la condition d'affichage",
  "propsPanel.visibleWhenHelpBody": "Expression CEL évaluée avec les variables de l'app : le widget n'est visible que si elle est vraie. Laisser vide pour toujours afficher.",
  ```

- [ ] **Step 3: Test vert (CEL)**

  Run: `cd shell && npx vitest run src/builder/PropsPanel.test.tsx`
  Expected: PASS.

- [ ] **Step 4: Répliquer sur les 3 autres sites (sans test dédié —
  même composant déjà couvert par le test Step 1, patron identique)**

  `shell/src/pages/AppBuilderPage.tsx` (import `HelpCircle`/`IconButton`/
  `Popover` en tête), lignes 465-467 :

  ```tsx
                <p className="mb-1 flex items-center gap-1 text-xs font-medium text-ink-2">
                  {t("appBuilder.propertiesLabel")}
                  <Popover
                    aria-label={t("appBuilder.propertiesHelpAria")}
                    trigger={
                      <IconButton
                        icon={<HelpCircle size={14} />}
                        aria-label={t("appBuilder.propertiesHelpAria")}
                        size="sm"
                      />
                    }
                  >
                    {t("appBuilder.propertiesHelpBody")}
                  </Popover>
                </p>
  ```

  Clés :

  ```ts
  "appBuilder.propertiesHelpAria": "Aide sur les propriétés du widget",
  "appBuilder.propertiesHelpBody": "Réglages visuels et de données du widget sélectionné sur le canevas. Rien de sélectionné : ce panneau reste vide.",
  ```

  `shell/src/pages/PipelineBuilderPage.tsx`, lignes 350-353 — le `<h2>`
  et les boutons Undo/Redo partagent un parent `flex items-center
  justify-between` : envelopper le titre dans un sous-groupe pour ne pas
  casser la répartition gauche/droite :

  ```tsx
              <div className="flex items-center justify-between border-b border-rule p-2">
                <div className="flex items-center gap-1.5">
                  <h2 className="text-lg font-semibold text-ink">
                    {initialTitle ?? t("pipelineBuilder.defaultTitle")}
                  </h2>
                  <Popover
                    aria-label={t("pipelineBuilder.helpAria")}
                    trigger={
                      <IconButton
                        icon={<HelpCircle size={14} />}
                        aria-label={t("pipelineBuilder.helpAria")}
                        size="sm"
                      />
                    }
                  >
                    {t("pipelineBuilder.helpBody")}
                  </Popover>
                </div>
                <div className="flex items-center gap-1">
  ```

  Clés :

  ```ts
  "pipelineBuilder.helpAria": "Aide sur le pipeline",
  "pipelineBuilder.helpBody": "Chaque nœud transforme les données du précédent. Connectez-les dans l'ordre d'exécution, puis planifiez ou exécutez le pipeline depuis l'onglet Exécutions.",
  ```

  `shell/src/pages/SqlLabPage.tsx`, ligne 92 — **corriger dans le même
  geste le littéral français non traduit** (trouvaille annexe D49) :

  ```tsx
              <div className="flex items-center gap-1.5">
                <h1 className="text-lg font-bold text-ink">{t("sqlLab.heading")}</h1>
                <Popover
                  aria-label={t("sqlLab.helpAria")}
                  trigger={
                    <IconButton
                      icon={<HelpCircle size={14} />}
                      aria-label={t("sqlLab.helpAria")}
                      size="sm"
                    />
                  }
                >
                  {t("sqlLab.helpBody")}
                </Popover>
              </div>
  ```

  Clés (`sqlLab.heading` remplace le littéral `SQL Lab`) :

  ```ts
  "sqlLab.heading": "SQL Lab",
  "sqlLab.helpAria": "Aide sur SQL Lab",
  "sqlLab.helpBody": "Requêtes SQL en lecture seule sur les jeux de données exposés (DuckDB). Le résultat est tronqué au-delà d'un certain nombre de lignes.",
  ```

- [ ] **Step 5: Suite complète des 4 pages touchées**

  Run: `cd shell && npx vitest run src/builder/PropsPanel.test.tsx src/pages/AppBuilderPage.test.tsx src/pages/PipelineBuilderPage.test.tsx src/pages/SqlLabPage.test.tsx`
  Expected: PASS — en particulier vérifier qu'aucun test existant de
  `SqlLabPage.test.tsx` n'attendait le texte littéral `SQL Lab` via un
  sélecteur autre que `t("sqlLab.heading")` (sinon échec local à corriger
  dans ce même test, cf. Global Constraint i18n).

- [ ] **Step 6: `npm run lint` (détecteur de littéraux français)**

  Run: `cd shell && npm run lint`
  Expected: 0 erreur — confirme qu'aucun texte français en dur ne
  subsiste sur les 4 sites touchés.

- [ ] **Step 7: Commit**

  ```bash
  git add shell/src/builder/PropsPanel.tsx shell/src/builder/PropsPanel.test.tsx \
    shell/src/pages/AppBuilderPage.tsx shell/src/pages/PipelineBuilderPage.tsx \
    shell/src/pages/SqlLabPage.tsx shell/src/i18n/catalog.fr.ts
  git commit -m "$(cat <<'EOF'
  feat(shell): aide contextuelle (CEL, propriétés, pipeline, SQL Lab)

  Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
  EOF
  )"
  ```

### Incertitudes restantes — SP-C4

1. **Câblage précis du bouton ⌘K de `TopBar.tsx` (Tâche 21, Step 6)** :
   l'implémentation par synthèse de `KeyboardEvent` fonctionne mais est
   fragile (couplée à la forme exacte du listener d'`AppLayout`).
   L'alternative propre (prop `onOpenPalette` remontée depuis
   `AppLayout` → `TopBar`) est probablement préférable ; à trancher par
   l'exécutant, pas bloquant pour le reste du plan.
2. **`AdminInfrastructurePage.test.tsx` / `AppBuilderPage.test.tsx` /
   `PipelineBuilderPage.test.tsx` / `SqlLabPage.test.tsx`** : non lus en
   détail (seulement grep/ligne ciblée) — le nom exact du mock client et
   du wrapper de test dans chacun peut différer légèrement de ce qui est
   écrit ci-dessus ; l'exécutant doit lire le fichier de test existant
   avant d'ajouter le nouveau test, comme rappelé inline à chaque étape.
3. **Répartition alphabétique locale de `catalog.fr.ts`** : les blocs de
   clés ci-dessus sont donnés groupés par préfixe (convention observée),
   mais l'ordre exact au sein du fichier réel (autour de
   `appBuilder.*`/`pipelineBuilder.*`/`sqlLab.*`/`propsPanel.*`/
   `infrastructure.*`/`commandPalette.*`) n'a pas été vérifié ligne par
   ligne — respecter l'ordre local déjà en place au moment d'insérer.
4. **`formatBytes` (Tâche 20)** : arrondi simple Mo/Go, pas de test dédié
   écrit ici pour les cas limites (0 octet, exactement 1024 Mo) — à
   ajouter si l'exécutant le juge utile, non bloquant pour D08.

---

### Constats de recherche — SP-C5 (SQL Lab, état réel du code au 2026-09-27)

- `shell/src/pages/SqlLabPage.tsx` : `<textarea>` brut lignes 95-100 ;
  affichage d'erreur `(run.error as Error).message` dans un `<p role="alert"
  className="text-sm text-danger">` lignes 110-114 ; `useCollectionsAdmin({
  enabled: copilotEnabled })` ligne 36 (PAS 36 exactement mais très proche,
  confirmé) ; le composant est déjà chargé en `lazy()` dans `routes.tsx:69-70`.
- `shell/src/api/domains/exportsIngestion.ts` : `requestAnalyticsSql` (lignes
  13-35) fait son propre `fetch` brut vers `${coreUrl}/analytics/sql`, PAS
  via `base.request()`. Branche 400 : parse `data.errors?.[0]?.message` →
  `SqlQueryError`. Branche générique (`!res.ok`) : `throw new Error(\`Request
  failed: ${res.status} POST /analytics/sql\`)` — confirmé, c'est bien ce
  message générique que D51 doit remplacer par `ApiError`.
- `shell/src/api/base.ts` : `parseErrorResponse(res): Promise<ApiError>`
  (lignes 58-75) construit l'`ApiError` depuis le corps RFC 7807
  (`title`/`detail`) + `Retry-After`. **Elle n'est actuellement PAS
  exportée** (pas de mot-clé `export` devant `async function
  parseErrorResponse`) — il faut l'exporter pour que `exportsIngestion.ts`
  puisse la réutiliser sans dupliquer sa logique.
- `core/app/features/routes.py` : la route `POST /analytics/sql` (lignes
  463-519+) lève `_validation_error([{"field": "sql", "code": "sql_error",
  "message": str(exc)}])` → `ValidationHTTPException(errors=..., status_code=
  400)`. Le handler global (`core/app/main.py:144-154`) sérialise ÇA en RFC
  7807 avec **`detail` toujours générique = `"validation failed"`** et le
  détail utile dans un membre d'extension `errors` au premier niveau (pas
  imbriqué sous `detail`). Donc pour la route SQL, `ApiError.detail` ne
  contiendrait PAS le message DuckDB utile — la branche 400 doit **rester**
  une lecture manuelle de `body.errors[0].message`, seule la branche non-400
  doit passer par `ApiError`/`parseErrorResponse`.
- `shell/src/ui/kit/Banner.tsx` existe déjà : `<Banner variant="danger">` pose
  `role="alert"` automatiquement (ligne 23, `variant === "danger" ?
  "alert" : undefined`) — **c'est le "cadre d'erreur" à réutiliser**, pas un
  nouveau composant à créer. `variant="danger"` = `border-danger-soft
  bg-danger-soft text-danger`.
- `shell/src/api/domains/collectionsAdmin.hooks.ts` : `useCollectionsAdmin`
  retourne `useQuery` sur `client.listCollections(...)` → items `{id, title,
  ...}` (confirmé par `SqlLabPage.tsx` : `collections={(collectionsQuery.data
  ?? []).map((c) => ({id: c.id, title: c.title}))}`).
- `shell/src/api/domains/datasets.hooks.ts` : `useCollectionSchema(collectionId,
  options?)` → `useQuery` sur `client.getCollectionSchema(collectionId):
  Promise<CollectionSchema>`. `CollectionSchema = {collection, pk, geometry,
  fields: CollectionSchemaField[]}`, `CollectionSchemaField = {name, type,
  required, maxLength?, values?, itemType?, label?}` (`shell/src/api/
  types.ts:336-351`).
- **`@uiw/react-codemirror`/`@codemirror/lang-sql` absents de
  `shell/package.json`** (confirmé, `grep codemirror package.json` = rien).
- `shell/scripts/check-bundle-size.mjs` : mesure UNIQUEMENT le graphe
  `entry.imports` (récursif) + `entry.css` de l'entrée Vite — le commentaire
  du fichier lui-même dit explicitement "volontairement PAS
  entry.dynamicImports". `SqlLabPage` est chargée par `lazy(() =>
  import("../pages/SqlLabPage")...)` dans `routes.tsx` → chunk asynchrone,
  hors mesure. Confirme l'hypothèse de la spec : CodeMirror ne devrait pas
  toucher `.bundle-size-threshold` (actuellement `695` Ko), à vérifier
  empiriquement après `npm run build` quand même (Tâche 27).

### Trouvaille non documentée par la spec — SP-C5 (à corriger dans le même geste)

`shell/src/test/setup.ts:6` configure
`server.listen({ onUnhandledRequest: "error" })` — toute requête MSW non
mockée fait échouer le test. `shell/src/test/msw/handlers.ts` (handlers
partagés) **ne définit aucun handler par défaut pour `GET /v1/collections`**.
`SqlLabPage.test.tsx` a 9 tests ; seuls 2 (les tests copilote, lignes
203-257) enregistrent `mockCollectionsList()` via `server.use(...)`. Si la
Tâche 26 (D54a) rend `useCollectionsAdmin` inconditionnel (au lieu de
`enabled: copilotEnabled`), **les 7 autres tests existants du fichier
casseront** (requête `/v1/collections` non mockée → erreur MSW). Deux fixs
possibles : (a) ajouter `mockCollectionsList()` dans chaque test restant,
ou (b) ajouter un handler par défaut vide à `shell/src/test/msw/handlers.ts`
(cohérent avec le patron déjà présent dans ce fichier pour `GET /items` qui
retourne une liste vide par défaut). **Option (b) retenue** dans la Tâche 26
ci-dessous : moins de sites à toucher, comportement par défaut sain pour
tout futur test qui rendrait un composant appelant `useCollectionsAdmin`
sans le mocker explicitement.

### Décision D54b — SP-C5 (autocomplétion colonnes, lazy par table détectée)

Pas de hook batch existant, et précharger le schéma de **toutes** les
collections visibles au montage ferait un nombre de requêtes proportionnel
au nombre de collections du tenant (pas borné, potentiellement dizaines) dès
l'ouverture de SQL Lab, avant même que l'utilisateur ait tapé quoi que ce
soit. Retenu : **fetch lazy par table référencée dans le texte SQL en cours
de frappe**, pas de préchargement. Mécanisme : un `useEffect` qui observe
`sql` (débit brut, pas besoin de debounce vu que `getCollectionSchema` est
déjà mis en cache par React Query avec une clé stable `["collection-schema",
id]` — un second appel sur le même id ne refait pas de requête réseau), en
extrayant les identifiants de collection réellement connus (croisés avec
`collectionsQuery.data`, pas un parsing SQL général) et en déclenchant
`client.getCollectionSchema(id)` pour chaque id nouvellement détecté et pas
encore en cache local. Le résultat alimente une `Map<string, string[]>`
(nom de collection → noms de colonnes) passée à l'extension `sql({schema})`
de CodeMirror. `useCollectionSchema()` (le hook) n'est PAS appelable en
boucle (règle des Hooks React) — on appelle donc `client.getCollectionSchema`
directement (méthode du client, pas le hook), comme le fait déjà
`resolveDataset`/tout code impératif de ce dépôt qui a besoin d'un accès
hors-hook au même client.

---

## Tâche 23 — SP-C5 : D51a — `parseDuckDbError` + affichage encadré

**Files:**
- Create: `shell/src/lib/parseDuckDbError.ts`
- Test: `shell/src/lib/parseDuckDbError.test.ts`
- Modify: `shell/src/pages/SqlLabPage.tsx` (import `Banner`, remplacer le
  `<p role="alert">` par un affichage structuré)
- Modify: `shell/src/pages/SqlLabPage.test.tsx` (le test existant ligne 96-113
  doit continuer à passer tel quel : `findByRole("alert")` doit toujours
  matcher, `toHaveTextContent("Parser Error: syntax error")` doit rester vrai
  — ce message n'a pas de `LINE n:`, donc `parseDuckDbError` doit retomber sur
  le message brut sans `line`/`column`, et l'affichage doit quand même rendre
  ce texte intégralement dans l'élément `role="alert"`)

**Interfaces:**
- Produces : `parseDuckDbError(message: string): {category: string | null,
  message: string, line: number | null, column: number | null, sqlSnippet:
  string | null}` — `category`/`line`/`column`/`sqlSnippet` sont `null` si le
  message ne matche pas le format DuckDB détaillé (fallback : `message`
  = texte tel quel, tout le reste `null`).

- [ ] **Step 1 : test rouge — messages DuckDB réels**

  Créer `shell/src/lib/parseDuckDbError.test.ts` :

  ```ts
  // SPDX-License-Identifier: Apache-2.0
  import { describe, expect, test } from "vitest";
  import { parseDuckDbError } from "./parseDuckDbError";

  describe("parseDuckDbError", () => {
    test("extrait catégorie/ligne/colonne d'un message DuckDB avec position", () => {
      const message =
        "Parser Error: syntax error at or near \"fro\"\n\nLINE 1: select * fro x\n                ^";
      const parsed = parseDuckDbError(message);
      expect(parsed.category).toBe("Parser Error");
      expect(parsed.message).toBe('syntax error at or near "fro"');
      expect(parsed.line).toBe(1);
      expect(parsed.column).toBe(17);
      expect(parsed.sqlSnippet).toBe("select * fro x");
    });

    test("retombe sur le message brut sans position (ex. erreur sans LINE)", () => {
      const message = "Parser Error: syntax error";
      const parsed = parseDuckDbError(message);
      expect(parsed.category).toBeNull();
      expect(parsed.message).toBe("Parser Error: syntax error");
      expect(parsed.line).toBeNull();
      expect(parsed.column).toBeNull();
      expect(parsed.sqlSnippet).toBeNull();
    });

    test("retombe sur le message brut si le format est totalement inattendu", () => {
      const parsed = parseDuckDbError("boom");
      expect(parsed).toEqual({
        category: null,
        message: "boom",
        line: null,
        column: null,
        sqlSnippet: null,
      });
    });
  });
  ```

  Run: `cd shell && npx vitest run src/lib/parseDuckDbError.test.ts`
  Expected: FAIL (`Cannot find module './parseDuckDbError'`).

- [ ] **Step 2 : implémentation minimale**

  Créer `shell/src/lib/parseDuckDbError.ts` :

  ```ts
  // SPDX-License-Identifier: Apache-2.0
  export type ParsedDuckDbError = {
    category: string | null;
    message: string;
    line: number | null;
    column: number | null;
    sqlSnippet: string | null;
  };

  // Format DuckDB (vérifié empiriquement, spec Vague C §SP-C5) :
  // "<Catégorie> Error: <message>\n\nLINE <n>: <sql tronqué>\n<espaces>^"
  // La position du "^" (2e ligne suivant LINE) donne la colonne (1-indexée).
  const HEADER_RE = /^([A-Za-z ]+ Error): (.*?)(?:\n\n|$)/s;
  const LINE_RE = /^LINE (\d+): (.*)$/m;

  export function parseDuckDbError(message: string): ParsedDuckDbError {
    const headerMatch = HEADER_RE.exec(message);
    const lineMatch = LINE_RE.exec(message);
    if (!headerMatch || !lineMatch) {
      return { category: null, message, line: null, column: null, sqlSnippet: null };
    }
    const lineIndex = message.indexOf(lineMatch[0]);
    const afterLine = message.slice(lineIndex + lineMatch[0].length);
    const caretMatch = /\n(\s*)\^/.exec(afterLine);
    const column = caretMatch ? caretMatch[1].length + 1 : null;
    return {
      category: headerMatch[1],
      message: headerMatch[2].trim(),
      line: Number(lineMatch[1]),
      column,
      sqlSnippet: lineMatch[2],
    };
  }
  ```

  Run: `cd shell && npx vitest run src/lib/parseDuckDbError.test.ts`
  Expected: les 3 tests passent. **Si le 1er test échoue sur `column`** :
  ajuster `caretMatch[1].length` (± décalage selon que le préfixe
  `"LINE 1: "` compte ou non dans l'alignement du `^` — vérifier
  empiriquement avec un vrai message DuckDB si possible plutôt que deviner,
  piège n°3 CLAUDE.md).

- [ ] **Step 3 : brancher l'affichage sur `Banner` + `parseDuckDbError`**

  Dans `shell/src/pages/SqlLabPage.tsx`, ajouter l'import :

  ```ts
  import { Banner } from "../ui/kit/Banner";
  import { parseDuckDbError } from "../lib/parseDuckDbError";
  ```

  Remplacer (lignes 110-114) :

  ```tsx
  {run.isError && (
    <p role="alert" className="text-sm text-danger">
      {(run.error as Error).message}
    </p>
  )}
  ```

  par :

  ```tsx
  {run.isError &&
    (() => {
      const parsed = parseDuckDbError((run.error as Error).message);
      return (
        <Banner variant="danger">
          {parsed.category && (
            <p className="font-semibold">{parsed.category}</p>
          )}
          <p>{parsed.message}</p>
          {parsed.line !== null && (
            <p className="mt-1 font-mono text-xs">
              {t("sqlLab.errorLineLabel", { line: parsed.line })}
              {parsed.sqlSnippet}
            </p>
          )}
        </Banner>
      );
    })()}
  ```

  Ajouter dans `shell/src/i18n/catalog.fr.ts` (bloc `sqlLab.*`, ordre
  alphabétique local après `sqlLab.emptyHistory`) :

  ```ts
  "sqlLab.errorLineLabel": "Ligne {line} : ",
  ```

- [ ] **Step 4 : vérifier le test existant + ajouter un test structuré**

  Le test `SqlLabPage.test.tsx` ligne 96-113 doit rester vert tel quel
  (`findByRole("alert")` matche toujours car `Banner variant="danger"` pose
  `role="alert"` ; `toHaveTextContent("Parser Error: syntax error")` reste
  vrai car le texte complet du message est rendu, réparti sur
  catégorie+message mais `toHaveTextContent` concatène le texte de tous les
  enfants).

  Ajouter un nouveau test dans le même fichier, après le test existant
  (ligne ~113) :

  ```tsx
  test("affiche la ligne et l'extrait SQL quand le message DuckDB porte une position", async () => {
    server.use(
      http.post("https://core.test/v1/analytics/sql", () =>
        HttpResponse.json(
          {
            errors: [
              {
                field: "sql",
                code: "sql_error",
                message:
                  'Parser Error: syntax error at or near "fro"\n\nLINE 1: select * fro x\n                ^',
              },
            ],
          },
          { status: 400 },
        ),
      ),
    );
    render(<Harness />);
    const textarea = await screen.findByLabelText("Requête SQL");
    await userEvent.type(textarea, "select * fro x");
    await userEvent.click(screen.getByRole("button", { name: "Exécuter" }));
    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("Parser Error");
    expect(alert).toHaveTextContent('syntax error at or near "fro"');
    expect(alert).toHaveTextContent("Ligne 1");
    expect(alert).toHaveTextContent("select * fro x");
  });
  ```

  Run: `cd shell && npx vitest run src/pages/SqlLabPage.test.tsx`
  Expected: tous les tests passent (10 au total).

- [ ] **Step 5 : commit**

  ```bash
  git add shell/src/lib/parseDuckDbError.ts shell/src/lib/parseDuckDbError.test.ts \
    shell/src/pages/SqlLabPage.tsx shell/src/pages/SqlLabPage.test.tsx \
    shell/src/i18n/catalog.fr.ts
  git commit -m "$(cat <<'EOF'
  feat(shell): affiche les erreurs SQL Lab en cadre structuré (ligne/colonne)

  Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
  EOF
  )"
  ```

---

## Tâche 24 — SP-C5 : D51b — `runAnalyticsSql` sur `ApiError`/RFC 7807 hors 400

**Files:**
- Modify: `shell/src/api/base.ts` (exporter `parseErrorResponse`)
- Modify: `shell/src/api/domains/exportsIngestion.ts` (`requestAnalyticsSql`)
- Test: `shell/src/api/domains/exportsIngestion.test.ts` (créer s'il n'existe
  pas déjà — vérifier d'abord avec `ls shell/src/api/domains/
  exportsIngestion.test.ts`)

**Interfaces:**
- Consumes : `parseErrorResponse(res: Response): Promise<ApiError>` (export
  nouveau depuis `base.ts`), `ApiError` (déjà exporté depuis `./ApiError`).
- Produces : aucun changement de signature publique — `runAnalyticsSql`
  jette toujours une erreur, mais `ApiError` au lieu d'`Error` générique sur
  tout statut `!ok` autre que 400.

- [ ] **Step 1 : exporter `parseErrorResponse`**

  Dans `shell/src/api/base.ts`, changer :

  ```ts
  async function parseErrorResponse(res: Response): Promise<ApiError> {
  ```

  en :

  ```ts
  export async function parseErrorResponse(res: Response): Promise<ApiError> {
  ```

  (Aucune autre ligne de ce fichier à toucher — `requestBlob`/`request` en
  interne continuent d'appeler la même fonction, juste maintenant exportée.)

- [ ] **Step 2 : test rouge — statut non-400 devient une `ApiError`**

  Vérifier d'abord si `shell/src/api/domains/exportsIngestion.test.ts`
  existe : `ls shell/src/api/domains/exportsIngestion.test.ts`. S'il
  n'existe pas, le créer avec ce contenu minimal (s'il existe, ajouter le
  test dans le fichier existant en suivant son patron de harness) :

  ```ts
  // SPDX-License-Identifier: Apache-2.0
  import { expect, test } from "vitest";
  import { http, HttpResponse } from "msw";
  import { server } from "../../test/msw/server";
  import { createItemClient } from "../itemClient";
  import { ApiError } from "../ApiError";

  test("runAnalyticsSql jette une ApiError sur un statut serveur non-400", async () => {
    server.use(
      http.post("https://core.test/v1/analytics/sql", () =>
        HttpResponse.json(
          { type: "about:blank", title: "Internal Server Error", status: 500, detail: "boom" },
          { status: 500 },
        ),
      ),
    );
    const client = createItemClient({ coreUrl: "https://core.test", getToken: () => "t" });
    await expect(client.runAnalyticsSql("select 1")).rejects.toMatchObject({
      name: "ApiError",
      status: 500,
      detail: "boom",
    });
  });

  test("runAnalyticsSql jette toujours SqlQueryError sur un 400 (comportement inchangé)", async () => {
    server.use(
      http.post("https://core.test/v1/analytics/sql", () =>
        HttpResponse.json(
          { errors: [{ field: "sql", code: "sql_error", message: "Parser Error: x" }] },
          { status: 400 },
        ),
      ),
    );
    const client = createItemClient({ coreUrl: "https://core.test", getToken: () => "t" });
    await expect(client.runAnalyticsSql("select x")).rejects.toMatchObject({
      name: "SqlQueryError",
      message: "Parser Error: x",
    });
  });
  ```

  Run: `cd shell && npx vitest run src/api/domains/exportsIngestion.test.ts`
  Expected: le 1er test échoue (`ApiError` attendu, `Error` générique reçu
  avec message `"Request failed: 500 POST /analytics/sql"`) ; le 2e test
  passe déjà (comportement 400 inchangé).

- [ ] **Step 3 : implémentation — brancher la branche non-400 sur `ApiError`**

  Dans `shell/src/api/domains/exportsIngestion.ts`, ajouter l'import :

  ```ts
  import { SqlQueryError, parseErrorResponse } from "../base";
  ```

  Remplacer :

  ```ts
  if (!res.ok) {
    throw new Error(`Request failed: ${res.status} POST /analytics/sql`);
  }
  ```

  par :

  ```ts
  if (!res.ok) {
    throw await parseErrorResponse(res);
  }
  ```

  (Le bloc `if (res.status === 400) { ... }` juste au-dessus reste
  identique et inchangé — il intercepte le 400 avant ce nouveau branchement,
  donc `parseErrorResponse` ne voit jamais un 400 sur cette route.)

- [ ] **Step 4 : run tests**

  Run: `cd shell && npx vitest run src/api/domains/exportsIngestion.test.ts`
  Expected: PASS (2/2).

  Run aussi la suite complète du module base pour non-régression :
  `cd shell && npx vitest run src/api/base.test.ts` (si ce fichier existe —
  sinon `npx vitest run src/api/`).
  Expected: PASS.

- [ ] **Step 5 : commit**

  ```bash
  git add shell/src/api/base.ts shell/src/api/domains/exportsIngestion.ts \
    shell/src/api/domains/exportsIngestion.test.ts
  git commit -m "$(cat <<'EOF'
  fix(shell): runAnalyticsSql jette une ApiError RFC 7807 hors statut 400

  Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
  EOF
  )"
  ```

---

## Tâche 25 — SP-C5 : D54a — CodeMirror remplace le `<textarea>` + collections inconditionnelles

**Files:**
- Modify: `shell/package.json` (+ `@uiw/react-codemirror`, `@codemirror/lang-sql`)
- Modify: `shell/src/pages/SqlLabPage.tsx`
- Modify: `shell/src/test/msw/handlers.ts` (handler par défaut `/collections`)
- Modify: `shell/src/pages/SqlLabPage.test.tsx` (adapter les sélecteurs de
  saisie — un `<CodeMirror>` ne s'interagit pas comme un `<textarea>` via
  `userEvent.type` sur un rôle `textbox` standard)

**Interfaces:**
- Consumes : rien de nouveau côté domaine.
- Produces : `SqlLabPage` garde le même comportement observable (onChange
  du SQL, bouton Exécuter, historique) — seul le contrôle de saisie change
  de nature DOM.

- [ ] **Step 1 : installer les dépendances**

  ```bash
  cd shell && npm install @uiw/react-codemirror @codemirror/lang-sql
  ```

  Vérifier après coup : `grep codemirror package.json` doit lister les 2
  paquets + leurs sous-dépendances transitives éventuelles déjà présentes
  (`@codemirror/state`, `@codemirror/view` — normalement tirées
  automatiquement).

- [ ] **Step 2 : ajouter le handler MSW par défaut `/collections` (corrige le
  gap trouvé en recherche, cf. section "Trouvaille non documentée" plus haut)**

  Dans `shell/src/test/msw/handlers.ts`, ajouter (après le handler
  `GET /items` existant lignes 25-27, même style de liste vide par défaut) :

  ```ts
  http.get(`${CORE}/collections`, () =>
    HttpResponse.json({ collections: [], numberMatched: 0, numberReturned: 0 }),
  ),
  ```

  Ce handler par défaut ne casse aucun test existant ailleurs dans le
  dépôt : `server.use(...)` dans un test individuel prend toujours priorité
  sur ce handler de base (comportement MSW standard), donc tout test qui
  mockait déjà `/collections` explicitement (ex. `mockCollectionsList()`
  dans `SqlLabPage.test.tsx`) continue de voir SA réponse, pas celle-ci.

- [ ] **Step 3 : test rouge — le SQL se tape désormais dans un éditeur CodeMirror**

  Dans `shell/src/pages/SqlLabPage.test.tsx`, `userEvent.type(textarea, ...)`
  suppose un vrai `<textarea>`. Un `<CodeMirror>` rend un `<div
  role="textbox" contenteditable>` — `userEvent.type` fonctionne aussi sur un
  élément `contenteditable` avec `role="textbox"`, mais **la sélection par
  `getByLabelText("Requête SQL")` ne matchera plus** (un `contenteditable`
  n'est pas nativement labellisable par un `<label>` englobant comme un
  input). Modifier CHAQUE test qui fait `screen.findByLabelText("Requête
  SQL")` (9 occurrences dans le fichier) pour utiliser
  `screen.findByRole("textbox", { name: "Requête SQL" })` à la place — ce
  sélecteur fonctionne pour les deux implémentations (avant/après ce
  changement), donc le remplacer AVANT d'implémenter est le test rouge :

  Run: `cd shell && npx vitest run src/pages/SqlLabPage.test.tsx`
  (après avoir fait le remplacement `findByLabelText("Requête SQL")` →
  `findByRole("textbox", { name: "Requête SQL" })` dans les 9 tests, texte
  encore inchangé côté composant)
  Expected: PASS inchangé pour l'instant (le `<textarea>` avec
  `aria-label={t("sqlLab.sqlQueryLabel")}` satisfait déjà ce rôle+nom — ce
  step ne fait que préparer le terrain, pas encore de rouge réel tant que le
  composant n'a pas changé). Passer directement au Step 4 pour le vrai test
  rouge du remplacement d'éditeur.

- [ ] **Step 4 : implémentation — CodeMirror + activation inconditionnelle des collections**

  Dans `shell/src/pages/SqlLabPage.tsx`, remplacer les imports en tête :

  ```ts
  import CodeMirror from "@uiw/react-codemirror";
  import { sql, SQLite } from "@codemirror/lang-sql";
  ```

  Remplacer :

  ```ts
  const collectionsQuery = useCollectionsAdmin({ enabled: copilotEnabled });
  ```

  par :

  ```ts
  // D54 (Vague C) : la liste des collections alimente désormais aussi
  // l'autocomplétion SQL (Tâche 26, D54b), plus seulement le panneau
  // copilote — appel inconditionnel.
  const collectionsQuery = useCollectionsAdmin();
  ```

  Remplacer le bloc `<label>...<textarea>...</label>` (lignes 93-101) par :

  ```tsx
  <div className="flex flex-col gap-1 text-sm text-ink">
    <span id="sql-lab-editor-label">{t("sqlLab.sqlQueryLabel")}</span>
    <CodeMirror
      value={sql}
      height="8rem"
      extensions={[sql({ dialect: SQLite })]}
      onChange={(value) => setSql(value)}
      aria-label={t("sqlLab.sqlQueryLabel")}
      className="rounded-md border border-rule text-xs"
    />
  </div>
  ```

  Note : `@uiw/react-codemirror` transmet `aria-label` au conteneur
  `role="textbox"` sous-jacent de CodeMirror 6 — **à vérifier
  empiriquement en lançant le test du Step 5** (piège n°3 CLAUDE.md, ne
  jamais faire confiance à la doc/mémoire sur la forme exacte d'une lib
  tierce) ; si `aria-label` n'atteint pas le bon élément, passer par
  `basicSetup`/`extensions` avec un `EditorView.contentAttributes.of({
  "aria-label": ... })` à la place.

- [ ] **Step 5 : run tests**

  Run: `cd shell && npx vitest run src/pages/SqlLabPage.test.tsx`
  Expected: PASS (12 tests : les 10 précédents + les 2 tests ajoutés Tâche 23
  Step 4). Si le sélecteur `findByRole("textbox", { name: "Requête SQL" })`
  ne trouve rien, ajuster la Step 4 selon la note ci-dessus jusqu'à ce que
  ça passe — ne pas deviner, itérer sur l'échec réel.

- [ ] **Step 6 : commit**

  ```bash
  git add shell/package.json shell/package-lock.json shell/src/pages/SqlLabPage.tsx \
    shell/src/pages/SqlLabPage.test.tsx shell/src/test/msw/handlers.ts
  git commit -m "$(cat <<'EOF'
  feat(shell): remplace le textarea SQL Lab par un éditeur CodeMirror

  Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
  EOF
  )"
  ```

---

## Tâche 26 — SP-C5 : D54b — autocomplétion colonnes (fetch lazy par table détectée)

**Files:**
- Modify: `shell/src/pages/SqlLabPage.tsx`
- Modify: `shell/src/pages/SqlLabPage.test.tsx`

**Interfaces:**
- Consumes : `client.getCollectionSchema(collectionId): Promise<
  CollectionSchema>` (via `useItemClient()`, déjà importé dans ce fichier
  sous le nom `client`), `CollectionSchema.fields[].name`.
- Produces : rien de nouveau exposé — comportement d'autocomplétion interne
  à la page.

- [ ] **Step 1 : test rouge — l'éditeur propose les colonnes d'une collection référencée**

  Ajouter dans `SqlLabPage.test.tsx` (après `mockCollectionsList()`,
  réutiliser cette fonction) :

  ```tsx
  test("propose les colonnes de la collection référencée dans la requête", async () => {
    server.use(
      mockCollectionsList(),
      http.get("https://core.test/v1/collections/parcs/schema", () =>
        HttpResponse.json({
          collection: "parcs",
          pk: "id",
          geometry: { column: "geom", type: "Point", srid: 4326 },
          fields: [
            { name: "nom", type: "text", required: true },
            { name: "surface", type: "number", required: false },
          ],
        }),
      ),
    );
    render(<Harness />);
    const editor = await screen.findByRole("textbox", { name: "Requête SQL" });
    await userEvent.type(editor, "select nom from parcs");
    // CodeMirror charge le schéma de "parcs" en arrière-plan dès que le nom
    // de collection apparaît dans le texte ; on vérifie l'appel réseau
    // plutôt que le popup natif de complétion (non fiable en jsdom).
    await waitFor(() =>
      expect(schemaFetchedFor("parcs")).toBe(true),
    );
  });
  ```

  (`schemaFetchedFor` : petit helper à définir en tête de fichier, un `Set<string>`
  rempli par un handler MSW dédié qui enregistre les ids demandés — pattern
  déjà utilisé ailleurs dans le dépôt pour vérifier "un appel a bien eu
  lieu" sans dépendre du rendu du popup CodeMirror lui-même, à vérifier avec
  `grep -rn "let.*fetched\|const.*Set()" shell/src/pages/*.test.tsx` pour
  copier le patron exact déjà en usage.)

  Run: `cd shell && npx vitest run src/pages/SqlLabPage.test.tsx`
  Expected: FAIL (aucun appel à `/collections/parcs/schema` déclenché —
  fonctionnalité pas encore implémentée).

- [ ] **Step 2 : implémentation — détection lazy + reconfiguration de l'extension `sql()`**

  Dans `shell/src/pages/SqlLabPage.tsx`, ajouter un état local pour le cache
  de schémas et un effet de détection :

  ```ts
  const [schemaByCollection, setSchemaByCollection] = useState<Record<string, string[]>>({});
  const knownCollectionIds = (collectionsQuery.data ?? []).map((c) => c.id);

  useEffect(() => {
    const referenced = knownCollectionIds.filter(
      (id) => sql.includes(id) && !(id in schemaByCollection),
    );
    if (referenced.length === 0) return;
    let cancelled = false;
    Promise.all(
      referenced.map((id) =>
        client.getCollectionSchema(id).then((schema) => [id, schema] as const),
      ),
    ).then((pairs) => {
      if (cancelled) return;
      setSchemaByCollection((prev) => {
        const next = { ...prev };
        for (const [id, schema] of pairs) {
          next[id] = schema.fields.map((f) => f.name);
        }
        return next;
      });
    });
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps -- knownCollectionIds recalculé chaque rendu depuis collectionsQuery.data, l'inclure re-déclencherait l'effet inutilement à chaque frappe
  }, [sql]);
  ```

  Reconfigurer l'extension `sql()` avec le schéma accumulé :

  ```ts
  extensions={[sql({ dialect: SQLite, schema: schemaByCollection })]}
  ```

  **Vérifier empiriquement** (piège n°3 CLAUDE.md) la forme exacte attendue
  par `schema` de `@codemirror/lang-sql` une fois le paquet installé — la
  signature documentée est `schema?: SQLNamespace` où `SQLNamespace` accepte
  notamment `Record<string, readonly string[]>` (table → colonnes), ce qui
  correspond à `schemaByCollection` tel que construit ci-dessus ; si le
  typage réel diverge (version installée différente), ajuster la forme
  produite par `setSchemaByCollection` en conséquence, pas l'inverse.

- [ ] **Step 3 : run tests**

  Run: `cd shell && npx vitest run src/pages/SqlLabPage.test.tsx`
  Expected: PASS. Si le test du Step 1 reste rouge parce que
  `schemaFetchedFor` ne peut pas être fiabilisé simplement, remplacer
  l'assertion par une vérification directe sur `schemaByCollection` exposée
  via un test-id ou en observant le nombre d'appels MSW capturés par un
  compteur local dans le `http.get` — adapter au patron réel du dépôt trouvé
  au Step 1, ne pas laisser un test qui ne vérifie rien (piège n°10 CLAUDE.md,
  falsifier : retirer temporairement l'effet, confirmer que ce test précis
  échoue, le remettre).

- [ ] **Step 4 : commit**

  ```bash
  git add shell/src/pages/SqlLabPage.tsx shell/src/pages/SqlLabPage.test.tsx
  git commit -m "$(cat <<'EOF'
  feat(shell): autocomplétion SQL Lab sur les colonnes des tables référencées

  Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
  EOF
  )"
  ```

---

## Tâche 27 — SP-C5 : vérification empirique du bundle après installation de CodeMirror

**Files:**
- Modify (conditionnel) : `shell/.bundle-size-threshold`

**Interfaces:** aucune (tâche de vérification pure).

- [ ] **Step 1 : build réel et mesure**

  ```bash
  cd shell && rm -rf dist dist-export && npm run build
  ```

  La sortie de `check-bundle-size.mjs` (appelé par `npm run build`, voir
  `CLAUDE.md`) affiche : `Charge JS/CSS initiale mesurée : X.X Ko (seuil :
  695 Ko)`.

- [ ] **Step 2 : décision conditionnelle**

  - Si `X.X <= 695` : **ne rien changer**, noter dans le message de commit
    (ou dans le rapport de tâche) la mesure exacte observée, confirmant
    l'hypothèse de la spec (CodeMirror tombe dans le chunk asynchrone de
    `SqlLabPage`, jamais dans l'entrée statique).
  - Si `X.X > 695` (l'hypothèse s'avère fausse — par ex. un import statique
    caché quelque part réintroduit CodeMirror dans l'entrée) : investiguer
    D'ABORD pourquoi avant de remonter le seuil (`grep -rn "codemirror"
    shell/src --include="*.ts" --include="*.tsx"` pour trouver un import
    hors de `SqlLabPage.tsx` ou de ses dépendances lazy) ; ne remonter
    `.bundle-size-threshold` que si l'augmentation est jugée légitime après
    investigation, jamais en réflexe.

- [ ] **Step 3 : commit (uniquement si le seuil a dû changer)**

  ```bash
  git add shell/.bundle-size-threshold
  git commit -m "$(cat <<'EOF'
  chore(shell): ajuste le seuil de bundle après mesure réelle post-CodeMirror

  Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
  EOF
  )"
  ```

  (Si la mesure ne dépasse pas le seuil, ce commit n'a pas lieu d'être —
  la Tâche 27 se termine au Step 2 sans modification de fichier.)

---

### Résumé des écarts trouvés — SP-C5 (pour mémoire)

1. `parseErrorResponse` (base.ts) n'est pas exportée aujourd'hui — export à
   ajouter, un seul mot-clé.
2. Le corps 400 de `POST /analytics/sql` **n'est PAS** un RFC 7807 exploitable
   pour le message utile : `detail` vaut toujours la chaîne générique
   `"validation failed"` (`ValidationHTTPException`/handler `main.py`), le
   vrai message DuckDB vit dans `errors[0].message`. La lecture manuelle du
   400 existante DOIT être conservée telle quelle — seule la branche non-400
   passe par `ApiError`.
3. **Gap non documenté par la spec, cassant sinon** : rendre
   `useCollectionsAdmin` inconditionnel dans `SqlLabPage.tsx` casse 7 des 9
   tests existants du fichier faute de handler MSW par défaut pour
   `GET /v1/collections` (`onUnhandledRequest: "error"` dans
   `src/test/setup.ts`). Fix : handler par défaut ajouté à
   `shell/src/test/msw/handlers.ts` (Tâche 25, Step 2).
4. `Banner.tsx` (`ui/kit`) est déjà le "cadre d'erreur" attendu par D51 —
   pas de nouveau composant à créer, contrairement à ce que la spec
   suggérait ("aucun 'erreur encadrée' existant à réutiliser tel quel" —
   faux, vérifié par lecture directe).
5. Décision D54b documentée : fetch lazy par table détectée dans le texte
   SQL (pas de préchargement), en appelant `client.getCollectionSchema`
   directement (pas le hook, qui ne peut pas s'appeler en boucle).

### Incertitudes restantes — SP-C5

- La position exacte du `^` dans un vrai message DuckDB (offset par rapport
  à `"LINE 1: "` inclus ou non dans l'alignement) n'a pas pu être vérifiée
  contre une exécution DuckDB réelle dans cette session de recherche — le
  Step 2 de la Tâche 23 prévoit un ajustement empirique si le test échoue.
- La forme exacte acceptée par l'option `schema` de `@codemirror/lang-sql`
  et par la prop `aria-label` de `@uiw/react-codemirror` n'a pas pu être
  vérifiée contre le code réel du paquet (non installé au moment de cette
  recherche) — les Steps concernés (Tâche 25 Step 4, Tâche 26 Step 2)
  demandent explicitement une vérification empirique post-installation
  plutôt qu'une confiance aveugle dans la doc mémorisée.
- Le patron exact "vérifier qu'un appel réseau a eu lieu sans dépendre du
  rendu du popup CodeMirror" (Tâche 26 Step 1, `schemaFetchedFor`) n'a pas pu
  être confirmé contre un exemple réel du dépôt dans cette recherche — à
  chercher activement à l'exécution (`grep -rn "let.*fetched\|const.*Set()"
  shell/src/pages/*.test.tsx`) plutôt qu'inventé sans précédent.

---

### Constats de recherche — SP-C6 (résumé, détail par tâche plus bas)

- **D11+D12** : le code porte un commentaire explicite datant d'un chantier
  antérieur ("N'étend PAS availableFields de MapSymbologyEditor... hors
  périmètre de ce correctif", `mapWidget.tsx:189`) qui devient FAUX avec
  cette tâche — le commentaire doit être retiré/remplacé, pas seulement le
  code changé.
- **D15** : confirmé que `LayerSymbology.color/size.domain` est **figé**
  (invariant SP-25, jamais recalculé au rendu) — `buildLegend` peut donc
  être appelé directement sur `layer.symbology` dans `MapEditorPage.tsx`
  sans aucune requête réseau ni sampling, juste comme `mapWidget.tsx` le
  fait déjà. `MapLayer` (variant `vector`) porte déjà un champ
  `geometryKind?: "point"|"line"|"polygon"` (`api/types.ts:257`) — pas
  besoin de le déduire.
- **D50** : la convention retenue est **`<clé>One`/`<clé>Many`** (jamais de
  bare pluriel ni suffixe `(s)`) + un petit sélecteur `plural(n, one, many)`
  dans `i18n/index.ts` — le bug réel n'est pas cosmétique : `"{n} entités"`
  affiche littéralement "1 entités" pour n=1, faute grammaticale visible,
  pas juste un choix de style.
- **D56** : `CopilotChat.tsx` ne remonte le texte de la requête utilisateur
  à aucun appelant (`onClientOps` ne reçoit que les `ops`, pas `message`) —
  un nouveau callback optionnel `onExchange` est nécessaire pour que
  `CopilotPanel.tsx` puisse persister un historique utile (prompt inclus,
  pas seulement les opérations).
- **D04** : la route à ajouter tombe sous `v1_router` (déjà monté,
  `core/app/main.py:295`) — pas de nouveau montage nécessaire. Le module
  `alerts/routes.py` n'importe pas encore `alerts/jobs.py` (import à
  ajouter, aucun risque de cycle : `jobs.py` n'importe pas `routes.py`).
  `core/tests/test_feature_inventory.py` exige bien une entrée — la route
  s'ajoute au tableau `surfaces.rest` de l'entrée JSONL existante
  `automatisation-definir-une-regle-d-alerte-de-seuil-sur-un-dataset`
  (même module, même écran `AlertRuleEditor.tsx`), pas une nouvelle entrée.

### Incertitudes restantes — SP-C6 (à trancher par le plan final ou en exécutant)

- **D35** : le formatage fr-FR n'est possible que là où le type de champ du
  schéma est connu. Pour `data.tsx` (widget "table"), c'est direct
  (`ctx.data.collectionId` + `useCollectionSchema`). Pour le popup carte
  (`popupContent.ts`/`resolvePopupContent`), c'est possible en **mode
  `fields`** (liste de champs nommés) en threadant le schéma depuis
  `MapView.tsx` (qui connaît déjà `layer.collectionId`) — mais **pas** en
  mode `template` (gabarit libre, `${expr}` arbitraire) où le type d'une
  sous-expression n'est pas inférable sans un vrai typeur CEL. Le brouillon
  ci-dessous ne couvre que `cellValue()` (data.tsx) + le mode `fields` de
  `resolvePopupContent` ; le mode `template` reste non formaté (comme les
  saisies natives, déjà hors périmètre par la spec) — **à confirmer que
  c'est un scope acceptable**, sinon Tâche 30 grossit.
- **D16** : par construction (spec), le test peut ne rien trouver à
  corriger — Tâche 36 est écrite pour ce cas (test seul, filet).

### Convention grammaticale D50 retenue — SP-C6

**`<clé>One` / `<clé>Many`**, jamais de pluriel nu ni de suffixe `(s)`.
Nouveau sélecteur dans `i18n/index.ts` :

```ts
export function plural(n: number, one: MessageKey, many: MessageKey): MessageKey {
  return n === 1 ? one : many;
}
```

Appliqué aux 5 clés existantes (renommées) + tests associés mis à jour.

---

## Tâche 28 — SP-C6 : D50 — pluriel grammatical + titre/description dynamiques manquants

**Files:**
- Modify: `shell/src/i18n/index.ts`
- Modify: `shell/src/i18n/catalog.fr.ts`
- Modify: `shell/src/i18n/index.test.ts`
- Modify: `shell/src/pages/CatalogPage.tsx` (ligne 354)
- Modify: `shell/src/pages/DatasetPage.tsx` (ligne 90)
- Modify: `shell/src/builder/widgets/datasetCard.tsx` (ligne 91)
- Modify: `shell/src/map/LayerPicker.tsx` (ligne 153)
- Modify: `shell/src/shell/ImportFileButton.tsx` (ligne 473)
- Modify: `shell/src/pages/PublicItemPage.tsx`
- Test: `shell/src/pages/PublicItemPage.test.tsx` (existant ou à créer sur
  le patron de `SitePublicPage.test.tsx`)

**Interfaces:**
- Produces: `plural(n: number, one: MessageKey, many: MessageKey): MessageKey`
  exporté de `i18n/index.ts`, réutilisable par toute tâche future avec un
  compte variable.

- [ ] **Step 1: Test rouge — `plural()` choisit la bonne clé**

  Dans `i18n/index.test.ts` :
  ```ts
  import { plural, t } from "./index";

  test("plural choisit le singulier à n=1, le pluriel sinon", () => {
    expect(t(plural(1, "catalog.countOne", "catalog.countMany"), { n: 1 })).toBe("1 élément");
    expect(t(plural(0, "catalog.countOne", "catalog.countMany"), { n: 0 })).toBe("0 éléments");
    expect(t(plural(68, "catalog.countOne", "catalog.countMany"), { n: 68 })).toBe("68 éléments");
  });
  ```
  Remplacer l'ancien test (ligne 24, `t("catalog.count", ...)`) par celui-ci
  — `catalog.count` n'existe plus après ce correctif.

  Run: `cd shell && npx vitest run src/i18n/index.test.ts`
  Expected: FAIL (`plural` n'existe pas, `catalog.countOne`/`countMany`
  absents du catalogue).

- [ ] **Step 2: Ajouter `plural()` à `i18n/index.ts`**

  ```ts
  export function plural(n: number, one: MessageKey, many: MessageKey): MessageKey {
    return n === 1 ? one : many;
  }
  ```

- [ ] **Step 3: Renommer les 5 clés dans `catalog.fr.ts`**

  Remplacer chaque clé unique par une paire `One`/`Many`, à sa place
  alphabétique locale :
  ```ts
  "catalog.countOne": "{n} élément",
  "catalog.countMany": "{n} éléments",
  ```
  (retirer `"catalog.count"`), et de même :
  ```ts
  "datasetPage.featureCountOne": "{n} entité",
  "datasetPage.featureCountMany": "{n} entités",
  "widgetDatasetCard.featureCountOne": "{n} entité",
  "widgetDatasetCard.featureCountMany": "{n} entités",
  "layerPicker.featureCountTemplateOne": "{n} entité",
  "layerPicker.featureCountTemplateMany": "{n} entités",
  "importFile.layerOptionTemplateOne": "{name} ({count} entité)",
  "importFile.layerOptionTemplateMany": "{name} ({count} entités)",
  ```

- [ ] **Step 4: Mettre à jour les 5 sites d'appel**

  `CatalogPage.tsx:354` — remplacer
  ```tsx
  {t("catalog.count", { n: query.data?.total ?? 0 })}
  ```
  par
  ```tsx
  {(() => {
    const n = query.data?.total ?? 0;
    return t(plural(n, "catalog.countOne", "catalog.countMany"), { n });
  })()}
  ```
  Même patron pour `DatasetPage.tsx:90` (`datasetPage.featureCount*`),
  `datasetCard.tsx:91` (`widgetDatasetCard.featureCount*`),
  `LayerPicker.tsx:153` (`layerPicker.featureCountTemplate*`) et
  `ImportFileButton.tsx:473` (`importFile.layerOptionTemplate*`, variable
  `l.featureCount`). Importer `plural` depuis `../i18n` (ou `../../i18n`
  selon la profondeur du fichier) dans chacun.

- [ ] **Step 5: Run test, vérifier vert**

  Run: `cd shell && npx vitest run src/i18n/index.test.ts src/pages/CatalogPage.test.tsx src/pages/DatasetPage.test.tsx src/builder/widgets/datasetCard.test.tsx src/map/LayerPicker.test.tsx src/shell/ImportFileButton.test.tsx`
  Expected: PASS. Si un test existant asserte encore l'ancien texte brut
  ("X entités" pour X=1 par exemple), corriger l'assertion — c'est
  exactement le bug que Tâche 28 corrige.

- [ ] **Step 6: `useDocumentMeta` sur `PublicItemPage.tsx`**

  `PublicItemPage.tsx` n'a pas de titre/description dynamiques
  (`SitePublicPage.tsx` les a déjà, même patron à répliquer). Il lui manque
  l'item (`configQuery` seul ne porte pas de titre) — ajouter une requête
  `getItem(pk)` :
  ```tsx
  import { useDocumentMeta } from "../shell/useDocumentMeta";
  // ...
  export function PublicItemPage({ pk }: { pk: string }) {
    const client = useItemClient();
    const itemQuery = useQuery({
      queryKey: ["public-item", pk],
      queryFn: () => client.getItem(pk),
      retry: false,
    });
    const configQuery = useQuery({
      queryKey: ["public-item-config", pk],
      queryFn: () => client.getPublicAppConfig(pk),
      retry: false,
    });
    useDocumentMeta({
      title: itemQuery.data?.title ?? "GeoStudio",
      description: itemQuery.data?.abstract ?? "",
      canonicalUrl: `${window.location.origin}/public/items/${pk}`,
    });
    if (configQuery.isLoading) {
      return <LoadingState />;
    }
    // ... reste inchangé
  }
  ```
  Test (nouveau ou étendu `PublicItemPage.test.tsx`, patron
  `SitePublicPage.test.tsx`) : mocker `getItem` à renvoyer
  `{title: "Mon jeu de données", abstract: "Une description"}`, monter le
  composant, asserter `document.title === "Mon jeu de données"` et
  `document.querySelector('meta[name="description"]')?.getAttribute("content") === "Une description"`.

- [ ] **Step 7: Commit**

  ```bash
  git add shell/src/i18n/index.ts shell/src/i18n/catalog.fr.ts shell/src/i18n/index.test.ts \
    shell/src/pages/CatalogPage.tsx shell/src/pages/DatasetPage.tsx \
    shell/src/builder/widgets/datasetCard.tsx shell/src/map/LayerPicker.tsx \
    shell/src/shell/ImportFileButton.tsx shell/src/pages/PublicItemPage.tsx \
    shell/src/pages/PublicItemPage.test.tsx
  git commit -m "fix(shell): pluriel grammatical fr + méta document sur PublicItemPage

  Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
  ```

---

## Tâche 29 — SP-C6 : D52 — copier lien de partage / snippet embed

**Files:**
- Modify: `shell/src/shell/ShareForm.tsx` (lignes ~116-131)
- Modify: `shell/src/i18n/catalog.fr.ts`
- Test: `shell/src/shell/ShareForm.test.tsx`

**Interfaces:**
- Consumes: `lucide-react` `Copy`/`Check` icônes (déjà dépendance directe,
  cf. D49).
- Produces: aucune nouvelle interface publique.

- [ ] **Step 1: Test rouge — bouton copier sur le lien et sur le snippet embed**

  ```tsx
  test("copie le lien de partage dans le presse-papiers", async () => {
    const writeText = vi.fn().mockResolvedValue(undefined);
    Object.assign(navigator, { clipboard: { writeText } });
    render(<ShareForm ... />); // patron existant du fichier de test
    // ... déclencher lastCreatedUrl (mock createLink.mutate résolu)
    await userEvent.click(screen.getByRole("button", { name: t("shareForm.copyLinkAria") }));
    expect(writeText).toHaveBeenCalledWith(expect.stringContaining("/embed/") /* ou l'URL affichée */);
  });
  ```
  Adapter au patron réel du fichier de test (mock de `useCreateShareLink`
  déjà en place). Run: `npx vitest run src/shell/ShareForm.test.tsx`.
  Expected: FAIL (bouton absent).

- [ ] **Step 2: Clés i18n**

  ```ts
  "shareForm.copyLinkAria": "Copier le lien",
  "shareForm.copyEmbedAria": "Copier le code d'intégration",
  "shareForm.copiedFeedback": "Copié !",
  ```

- [ ] **Step 3: Implémentation — helper + boutons**

  Dans `ShareForm.tsx`, ajouter en tête de fichier (ou juste avant le
  composant) :
  ```tsx
  async function copyToClipboard(text: string): Promise<void> {
    if (navigator.clipboard?.writeText) {
      await navigator.clipboard.writeText(text);
      return;
    }
    // Repli navigateur sans Clipboard API (contexte non sécurisé, vieux
    // navigateur) : execCommand est dépréciée mais fonctionne encore.
    const el = document.createElement("textarea");
    el.value = text;
    el.style.position = "fixed";
    el.style.opacity = "0";
    document.body.appendChild(el);
    el.select();
    document.execCommand("copy");
    document.body.removeChild(el);
  }
  ```
  Ajouter un état `const [copiedField, setCopiedField] = useState<"link" | "embed" | null>(null);`
  puis, aux deux sites (~116-131) :
  ```tsx
  {lastCreatedUrl && (
    <p className="flex items-center gap-1 text-xs text-ink">
      {t("shareForm.linkCreatedPrefix")}
      <span className="break-all">{lastCreatedUrl}</span>
      <button
        type="button"
        aria-label={t("shareForm.copyLinkAria")}
        className="text-ink-2 hover:text-ink"
        onClick={() => {
          void copyToClipboard(lastCreatedUrl);
          setCopiedField("link");
          setTimeout(() => setCopiedField(null), 2000);
        }}
      >
        {copiedField === "link" ? <Check size={14} /> : <Copy size={14} />}
      </button>
    </p>
  )}
  ```
  et, dans le bloc embed (~122-131), un bouton identique
  (`aria-label={t("shareForm.copyEmbedAria")}`, copie du même
  `<iframe ...>` déjà construit dans `value={...}`, `copiedField === "embed"`).
  Importer `Copy`, `Check` de `lucide-react`.

- [ ] **Step 4: Run test, vérifier vert**

  Run: `npx vitest run src/shell/ShareForm.test.tsx` → PASS.

- [ ] **Step 5: Commit**

  ```bash
  git add shell/src/shell/ShareForm.tsx shell/src/shell/ShareForm.test.tsx shell/src/i18n/catalog.fr.ts
  git commit -m "feat(shell): bouton copier sur le lien de partage et le snippet embed

  Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
  ```

---

## Tâche 30 — SP-C6 : D35 — erreurs CEL lisibles + formatage fr-FR des valeurs

**Files:**
- Create: `shell/src/builder/celError.ts`
- Create: `shell/src/builder/celError.test.ts`
- Modify: `shell/src/builder/expr.ts` (aucun changement de signature,
  seulement consommé différemment par les 4 sites)
- Modify: `shell/src/builder/PropsPanel.tsx` (~44-48)
- Modify: `shell/src/builder/NavigationPanel.tsx` (~100)
- Modify: `shell/src/builder/ActionsPanel.tsx` (~77)
- Modify: `shell/src/map/PopupEditor.tsx` (~30)
- Modify: `shell/src/builder/widgets/data.tsx` (`cellValue()`, ligne ~28-40)
- Modify: `shell/src/map/popupContent.ts` (`resolvePopupContent`/`display()`)
- Modify: `shell/src/map/MapView.tsx` (site d'appel de `resolvePopupContent`)
- Test: `shell/src/builder/widgets/data.test.tsx`,
  `shell/src/map/popupContent.test.ts`

**Interfaces:**
- Produces: `formatFieldValue(value: unknown, fieldType?: CollectionFieldType): string`
  (nouveau, `shell/src/builder/fieldFormat.ts`) — fr-FR pour
  `integer`/`number` (`Intl.NumberFormat("fr-FR")`) et `date`/`datetime`
  (`Intl.DateTimeFormat("fr-FR")`), `String(value)` sinon. Consommé par
  `cellValue()` (data.tsx) et `display()` (popupContent.ts, mode `fields`
  seulement).
- Produces: `formatCelError(raw: string): string` (`celError.ts`) — pas de
  traduction technique impossible (messages `cel-js` restent en l'état côté
  contenu), seulement mise en forme visuelle (voir Step 2).

**Décision de scope propagée depuis "Incertitudes restantes" ci-dessus** :
le mode `template` d'un popup (gabarit libre `${expr}`) n'est PAS formaté
fr-FR par cette tâche — seul le mode `fields` (liste de champs nommés,
`resolvePopupContent`) et le widget table (`cellValue`) le sont. Documenté
en commentaire au point d'insertion.

- [ ] **Step 1: Test rouge — `formatFieldValue`**

  `shell/src/builder/fieldFormat.test.ts` (nouveau) :
  ```ts
  import { formatFieldValue } from "./fieldFormat";

  test("formate un nombre en fr-FR", () => {
    expect(formatFieldValue(1234.5, "number")).toBe("1 234,5");
  });
  test("formate une date en fr-FR", () => {
    expect(formatFieldValue("2026-09-27", "date")).toBe(
      new Intl.DateTimeFormat("fr-FR").format(new Date("2026-09-27")),
    );
  });
  test("passe une chaîne inchangée", () => {
    expect(formatFieldValue("abc", "string")).toBe("abc");
  });
  test("sans type de champ, comportement String() historique", () => {
    expect(formatFieldValue(42, undefined)).toBe("42");
  });
  ```
  Run: `npx vitest run src/builder/fieldFormat.test.ts` → FAIL (module absent).

- [ ] **Step 2: `fieldFormat.ts`**

  ```ts
  // SPDX-License-Identifier: Apache-2.0
  import type { CollectionFieldType } from "../api/types";

  const NUMBER_FORMAT = new Intl.NumberFormat("fr-FR");
  const DATE_FORMAT = new Intl.DateTimeFormat("fr-FR");

  export function formatFieldValue(value: unknown, fieldType?: CollectionFieldType): string {
    if (value === null || value === undefined) return "";
    if ((fieldType === "integer" || fieldType === "number") && typeof value === "number") {
      return NUMBER_FORMAT.format(value);
    }
    if ((fieldType === "date" || fieldType === "datetime") && typeof value === "string") {
      const parsed = new Date(value);
      if (!Number.isNaN(parsed.getTime())) return DATE_FORMAT.format(parsed);
    }
    return String(value);
  }
  ```

- [ ] **Step 3: Brancher `cellValue()` (data.tsx) sur le schéma**

  La colonne calculée CEL (`isCalculatedColumn`) n'a pas de type de champ
  connu (résultat d'expression) — seul un nom de champ simple en a un.
  Dans `registerDataWidgets()`, widget "table" : ajouter la résolution du
  schéma comme le fait déjà `mapWidget.tsx:194-198` :
  ```tsx
  const schemaQuery = useQuery({
    queryKey: ["collection-schema", ctx.data?.collectionId],
    queryFn: () => client.getCollectionSchema(ctx.data!.collectionId!),
    enabled: Boolean(ctx.data?.collectionId),
  });
  const fieldTypes = new Map(
    (schemaQuery.data?.fields ?? []).map((f) => [f.name, f.type] as const),
  );
  ```
  (nécessite `useItemClient()` déjà importé dans le fichier pour d'autres
  widgets — vérifier l'import en tête, l'ajouter si absent pour ce widget
  précis). Modifier `cellValue()` pour accepter `fieldTypes` :
  ```ts
  function cellValue(
    c: TableColumn,
    r: DataRecord,
    ctx: Pick<WidgetContext, "variables" | "user">,
    fieldTypes: Map<string, CollectionFieldType>,
  ): string {
    if (!isCalculatedColumn(c)) return formatFieldValue(r.properties[c], fieldTypes.get(c));
    const value = evaluateExpression(c.expr, {
      vars: ctx.variables ?? {},
      record: r.properties,
      user: ctx.user ?? { name: "" },
    });
    return value === undefined || value === null ? "" : String(value);
  }
  ```
  Propager `fieldTypes` à `toDataTableColumns(columns, ctx, fieldTypes)` et
  à son appelant.

- [ ] **Step 4: Brancher `resolvePopupContent` (mode `fields`)**

  `popupContent.ts` : ajouter un paramètre optionnel `schema` :
  ```ts
  export function resolvePopupContent(
    config: PopupConfig | undefined,
    properties: Record<string, unknown>,
    schema?: CollectionSchemaField[],
  ): PopupContent {
    const fieldTypes = new Map((schema ?? []).map((f) => [f.name, f.type] as const));
    function display(value: unknown, fieldName?: string): string {
      if (value === null || value === undefined) return EMPTY;
      if (typeof value === "object") return stringifyObject(value);
      return fieldName ? formatFieldValue(value, fieldTypes.get(fieldName)) : String(value);
    }
    // ... reste inchangé, mais les deux appels de display() dans le mode
    // `fields` passent maintenant le nom du champ :
    // title: display(properties[config.titleField], config.titleField)
    // rows: ... value: display(properties[n], n)
    // Le mode `template` (html renderPopupTemplate) reste NON formaté —
    // hors périmètre (cf. commentaire de tête du fichier).
  }
  ```

- [ ] **Step 5: `MapView.tsx` passe le schéma au popup**

  Au site d'appel (`resolvePopupContent(popupConfig, popup.properties)`),
  passer le schéma de la collection de la couche cliquée — `MapView.tsx`
  connaît déjà `layer.collectionId` pour la couche vecteur active ; ajouter
  (si pas déjà présent) un `useQuery(["collection-schema", collectionId], ...)`
  par couche visible avec `collectionId`, réutilisé ici. Si cette
  plomberie s'avère plus lourde que prévu en l'implémentant (plusieurs
  couches simultanées, cache par couche), se limiter à la couche du popup
  actif (résolue au clic, pas préchargée pour toutes les couches).

- [ ] **Step 6: Erreurs CEL lisibles — `celError.ts`**

  ```ts
  // SPDX-License-Identifier: Apache-2.0
  export function formatCelError(raw: string): string {
    // cel-js renvoie des messages techniques concaténés par "; " —
    // un seul par ligne est plus lisible qu'un unique bloc de prose.
    return raw
      .split("; ")
      .map((part) => `• ${part}`)
      .join("\n");
  }
  ```
  Test :
  ```ts
  test("un message par ligne, préfixé", () => {
    expect(formatCelError("erreur A; erreur B")).toBe("• erreur A\n• erreur B");
  });
  ```
  Aux 4 sites (`PropsPanel.tsx:44-48`, `NavigationPanel.tsx:100`,
  `ActionsPanel.tsx:77`, `map/PopupEditor.tsx:30`), remplacer l'affichage
  brut de `error`/`err` par :
  ```tsx
  <p role="alert" className="whitespace-pre-line text-xs text-danger">
    {formatCelError(error)}
  </p>
  ```
  (adapter le nom de variable/JSX exact à chaque fichier — vérifier le
  wrapper actuel avant de le remplacer, ne pas dupliquer `role="alert"` si
  déjà posé par un parent).

- [ ] **Step 7: Run tests, vérifier vert**

  Run: `npx vitest run src/builder/fieldFormat.test.ts src/builder/celError.test.ts src/builder/widgets/data.test.tsx src/map/popupContent.test.ts src/builder/PropsPanel.test.tsx src/builder/NavigationPanel.test.tsx src/builder/ActionsPanel.test.tsx src/map/PopupEditor.test.tsx`

- [ ] **Step 8: Commit**

  ```bash
  git add shell/src/builder/fieldFormat.ts shell/src/builder/fieldFormat.test.ts \
    shell/src/builder/celError.ts shell/src/builder/celError.test.ts \
    shell/src/builder/widgets/data.tsx shell/src/map/popupContent.ts shell/src/map/MapView.tsx \
    shell/src/builder/PropsPanel.tsx shell/src/builder/NavigationPanel.tsx \
    shell/src/builder/ActionsPanel.tsx shell/src/map/PopupEditor.tsx
  git commit -m "fix(shell): erreurs CEL lisibles et valeurs formatées fr-FR (table + popup)

  Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
  ```

---

## Tâche 31 — SP-C6 : D36 — statut par fichier sur l'upload de pièce jointe

**Files:**
- Modify: `shell/src/builder/widgets/form.tsx` (`AttachmentFieldInput`,
  ~245-360)
- Modify: `shell/src/i18n/catalog.fr.ts`
- Test: `shell/src/builder/widgets/form.test.tsx`

**Interfaces:**
- Produces: aucune nouvelle interface publique — état interne uniquement.

- [ ] **Step 1: Test rouge — statut par fichier affiché pendant l'upload**

  ```tsx
  test("affiche un statut par fichier pendant l'upload de plusieurs fichiers", async () => {
    // mock client.presignAttachmentUpload / fetch / confirmAttachmentUpload
    // avec des promesses contrôlées pour observer l'état intermédiaire
    const file1 = new File(["a"], "a.txt");
    const file2 = new File(["b"], "b.txt");
    render(<AttachmentFieldInput ... />);
    await userEvent.upload(screen.getByLabelText(t("widgetForm.addFilesAria")), [file1, file2]);
    expect(screen.getByText(t("widgetForm.attachmentUploading", { filename: "a.txt" }))).toBeInTheDocument();
  });
  ```
  Adapter au patron de mock déjà présent dans `form.test.tsx` pour
  `AttachmentFieldInput`. Run → FAIL (statut par fichier non affiché,
  seul un état global existe).

- [ ] **Step 2: Clé i18n**

  ```ts
  "widgetForm.attachmentUploading": "Envoi de {filename}…",
  "widgetForm.attachmentError": "Échec de l'envoi de {filename}",
  ```

- [ ] **Step 3: Remplacer le booléen par une map de statuts**

  ```tsx
  const [fileStatus, setFileStatus] = useState<
    Record<string, "uploading" | "done" | "error">
  >({});

  async function handleFiles(files: FileList | null) {
    if (!files || fid === null) return;
    for (const file of Array.from(files)) {
      setFileStatus((s) => ({ ...s, [file.name]: "uploading" }));
      try {
        const { uploadUrl, key } = await client.presignAttachmentUpload(collectionId, fid, {
          fieldKey,
          filename: file.name,
          contentType: file.type || "application/octet-stream",
        });
        await fetch(uploadUrl, {
          method: "PUT",
          body: file,
          headers: { "Content-Type": file.type },
        });
        await client.confirmAttachmentUpload(collectionId, fid, {
          key,
          fieldKey,
          filename: file.name,
          contentType: file.type || "application/octet-stream",
        });
        setFileStatus((s) => ({ ...s, [file.name]: "done" }));
      } catch {
        setFileStatus((s) => ({ ...s, [file.name]: "error" }));
      }
    }
    void queryClient.invalidateQueries({
      queryKey: ["attachments", collectionId, fid, fieldKey],
    });
  }
  ```
  Remplacer les usages de `uploading`/`setUploading` (disable de l'input,
  ligne ~358) par `Object.values(fileStatus).some((s) => s === "uploading")`.
  Rendre la liste des statuts sous l'input :
  ```tsx
  {Object.entries(fileStatus)
    .filter(([, status]) => status !== "done")
    .map(([filename, status]) => (
      <p key={filename} className="text-xs text-ink-2">
        {status === "uploading"
          ? t("widgetForm.attachmentUploading", { filename })
          : t("widgetForm.attachmentError", { filename })}
      </p>
    ))}
  ```

- [ ] **Step 4: Run test, vérifier vert**

  Run: `npx vitest run src/builder/widgets/form.test.tsx`

- [ ] **Step 5: Commit**

  ```bash
  git add shell/src/builder/widgets/form.tsx shell/src/i18n/catalog.fr.ts shell/src/builder/widgets/form.test.tsx
  git commit -m "feat(shell): statut d'upload par fichier sur le champ pièce jointe

  Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
  ```

---

## Tâche 32 — SP-C6 : D38 — label ambigu sur `AttachmentFieldInput`

**Files:**
- Modify: `shell/src/builder/widgets/form.tsx` (site d'appel ~646-664,
  `AttachmentFieldInput` ~316-318)
- Test: `shell/src/builder/widgets/form.test.tsx`

- [ ] **Step 1: Test rouge — le texte de label n'enveloppe plus les contrôles**

  ```tsx
  test("le label d'un champ pièce jointe n'est pas un <label> englobant", async () => {
    render(<FormWidget ... />); // avec un champ attachment
    const labelText = screen.getByText("Photos"); // f.label du champ
    expect(labelText.tagName).not.toBe("LABEL");
    const list = screen.getByRole("list", { name: "Photos" });
    expect(list).toBeInTheDocument();
  });
  ```
  Adapter aux fixtures réelles du fichier (nom de champ/label utilisé dans
  les tests existants d'attachment). Run → FAIL (`<label>` actuel).

- [ ] **Step 2: Séparer le texte de label de `AttachmentFieldInput`**

  Au site d'appel (`form.tsx:651-664`), traiter la branche attachment à
  part :
  ```tsx
  {fields.map((f) =>
    f.type === "attachment" ? (
      <div key={f.name} className="flex flex-col gap-1">
        <span id={`field-${f.name}-label`}>
          {f.label}
          {f.required ? " *" : ""}
        </span>
        <AttachmentFieldInput
          collectionId={collectionId}
          fid={editingId === null ? null : String(editingId)}
          fieldKey={f.name}
          client={client}
          labelledBy={`field-${f.name}-label`}
        />
      </div>
    ) : (
      <label key={f.name} className="flex flex-col gap-1">
        {f.label}
        {f.required ? " *" : ""}
        <FieldInput
          field={f}
          value={values[f.name]}
          onChange={(v) => setValues((old) => ({ ...old, [f.name]: v }))}
          onBlur={() => setTouched((t) => ({ ...t, [f.name]: true }))}
          collectionId={collectionId}
          fid={editingId === null ? null : String(editingId)}
          client={client}
          error={errorFor(f)}
        />
      </label>
    ),
  )}
  ```
  Dans `AttachmentFieldInput` (~316-318), accepter `labelledBy: string` et
  poser `aria-labelledby={labelledBy}` + `role="list"`/`aria-label`
  implicite sur le conteneur `<ul>` :
  ```tsx
  <ul className="flex flex-col gap-1" aria-labelledby={labelledBy}>
  ```
  (`FieldInput` n'est plus appelé pour la branche `attachment` — sa propre
  branche `if (field.type === "attachment")` dans `FieldInput` devient
  morte : la retirer pour ne pas laisser un chemin dupliqué non exercé.
  Vérifier qu'aucun autre appelant de `FieldInput` ne dépend de cette
  branche avant de la supprimer.)

- [ ] **Step 3: Run test, vérifier vert**

  Run: `npx vitest run src/builder/widgets/form.test.tsx`

- [ ] **Step 4: Commit**

  ```bash
  git add shell/src/builder/widgets/form.tsx shell/src/builder/widgets/form.test.tsx
  git commit -m "fix(shell): sépare le label du champ pièce jointe de ses contrôles

  Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
  ```

---

## Tâche 33 — SP-C6 : D39 — placeholders sur `SecretParamSelect`/`SecretCreateForm`

**Files:**
- Modify: `shell/src/builder/pipeline/SecretParamSelect.tsx` (23 sites)
- Modify: `shell/src/i18n/catalog.fr.ts`
- Test: `shell/src/builder/pipeline/SecretParamSelect.test.tsx`

- [ ] **Step 1: Test rouge — un placeholder représentatif par variante**

  ```tsx
  test("le champ dsn a un placeholder d'exemple", () => {
    render(<SecretCreateForm kindFilter="postgres_dsn" ... />);
    expect(screen.getByLabelText(t("secretParamSelect.dsnAria"))).toHaveAttribute(
      "placeholder",
      "postgresql://user:pass@host:5432/db",
    );
  });
  test("le champ host SMTP a un placeholder d'exemple", () => {
    render(<SecretCreateForm kindFilter="smtp" ... />);
    expect(screen.getByLabelText(t("secretParamSelect.hostAria"))).toHaveAttribute(
      "placeholder",
      "smtp.example.com",
    );
  });
  ```
  Run → FAIL (aucun `placeholder` posé aujourd'hui).

- [ ] **Step 2: 23 clés i18n**

  ```ts
  "secretParamSelect.namePlaceholder": "mon-secret",
  "secretParamSelect.keyPlaceholder": "X-Api-Key",
  "secretParamSelect.valuePlaceholder": "sk_live_…",
  "secretParamSelect.tokenPlaceholder": "eyJhbGciOi…",
  "secretParamSelect.usernamePlaceholder": "utilisateur",
  "secretParamSelect.passwordPlaceholder": "••••••••",
  "secretParamSelect.tokenUrlPlaceholder": "https://auth.example.com/oauth/token",
  "secretParamSelect.clientIdPlaceholder": "client-id",
  "secretParamSelect.clientSecretPlaceholder": "client-secret",
  "secretParamSelect.dsnPlaceholder": "postgresql://user:pass@host:5432/db",
  "secretParamSelect.awsAccessKeyIdPlaceholder": "AKIAIOSFODNN7EXAMPLE",
  "secretParamSelect.awsSecretAccessKeyPlaceholder": "wJalrXUtnFEMI/K7MDENG…",
  "secretParamSelect.endpointUrlPlaceholder": "https://s3.eu-west-1.amazonaws.com",
  "secretParamSelect.accountNamePlaceholder": "moncompte",
  "secretParamSelect.accountKeyPlaceholder": "clé de compte Azure",
  "secretParamSelect.serviceAccountInfoPlaceholder": "{\"type\": \"service_account\", …}",
  "secretParamSelect.hostPlaceholder": "smtp.example.com",
  "secretParamSelect.portPlaceholder": "587",
  "secretParamSelect.fromAddressPlaceholder": "no-reply@example.com",
  ```
  (19 clés distinctes couvrent les 23 sites : `username`/`password`
  réutilisées entre `basic_auth` et `smtp` — même libellé, même
  placeholder, une seule clé chacune ; `dsn` réutilisée par les 5 variantes
  DSN.)

- [ ] **Step 3: Poser `placeholder={t(...)}` sur les 23 `<input>`/`<textarea>`**

  Un seul patron répété, ex. (ligne ~220, champ name) :
  ```tsx
  <input
    aria-label={t("secretParamSelect.nameAria")}
    placeholder={t("secretParamSelect.namePlaceholder")}
    className="h-8 rounded border border-rule bg-surface px-2 text-ink"
    value={name}
    onChange={(e) => setName(e.target.value)}
  />
  ```
  Appliquer la même addition d'attribut aux 22 autres champs listés dans
  la spec (lignes 230/248/260/269/282/295/304/318/327/336/353/366/375/385/
  398/407/420/432/441/451/460/470 du fichier réel), chacun avec sa clé
  `xxxPlaceholder` correspondante (`username`/`password` réutilisent la
  même clé aux deux occurrences).

- [ ] **Step 4: Run test, vérifier vert**

  Run: `npx vitest run src/builder/pipeline/SecretParamSelect.test.tsx`

- [ ] **Step 5: Commit**

  ```bash
  git add shell/src/builder/pipeline/SecretParamSelect.tsx \
    shell/src/i18n/catalog.fr.ts shell/src/builder/pipeline/SecretParamSelect.test.tsx
  git commit -m "feat(shell): placeholders d'exemple sur les 23 champs de secret connecteur

  Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
  ```

---

## Tâche 34 — SP-C6 : D11+D12 — widget carte — champs disponibles réels + vue par défaut configurable

**Files:**
- Modify: `shell/src/builder/widgets/mapWidget.tsx` (lignes ~189, 223-225,
  277-279, 216-222, 371-373)
- Modify: `shell/src/i18n/catalog.fr.ts`
- Test: `shell/src/builder/widgets/mapWidget.test.tsx`

- [ ] **Step 1: Test rouge — `availableFields` reflète le schéma réel**

  ```tsx
  test("MapSymbologyEditor reçoit les champs non-attachment du schéma", async () => {
    // mock client.getCollectionSchema résolvant {fields: [{name:"pop",type:"number"}, {name:"photo",type:"attachment"}]}
    const { getByTestId } = renderPropsPanel({ ... }); // patron existant du fichier
    await waitFor(() => {
      expect(capturedSymbologyEditorProps.availableFields).toEqual(["pop"]);
    });
  });
  test("le PropsPanel expose des champs Centre/Zoom qui alimentent la vue par défaut", async () => {
    const onChange = vi.fn();
    render(<PropsPanel props={{ center: [1, 2], zoom: 8 }} onChange={onChange} ... />);
    await userEvent.clear(screen.getByLabelText(t("widgetMap.defaultZoomAria")));
    await userEvent.type(screen.getByLabelText(t("widgetMap.defaultZoomAria")), "10");
    expect(onChange).toHaveBeenCalledWith(expect.objectContaining({ zoom: 10 }));
  });
  ```
  Adapter aux fixtures réelles de `mapWidget.test.tsx` (le fichier expose
  déjà `renderPropsPanel`/un moyen de capturer les props passées aux
  sous-composants, cf. commentaires du fichier source citant
  `mapWidget.test.tsx:126`). Run → FAIL.

- [ ] **Step 2: `availableFields` réel (D11)**

  Ligne ~223-225 :
  ```tsx
  <MapSymbologyEditor
    value={props.symbology as LayerSymbology | undefined}
    availableFields={
      schemaQuery.data?.fields.filter((f) => f.type !== "attachment").map((f) => f.name) ?? []
    }
    themeColors={theme?.colors}
    ...
  ```
  Ligne ~277-279, même changement sur `PopupEditor` :
  ```tsx
  <PopupEditor
    value={props.popup as PopupConfig | undefined}
    availableFields={
      schemaQuery.data?.fields.filter((f) => f.type !== "attachment").map((f) => f.name) ?? []
    }
    attachmentFields={attachmentFields}
    onChange={(popup) => onChange({ ...props, popup })}
  />
  ```
  **Retirer le commentaire devenu faux à la ligne 189** ("N'étend PAS
  availableFields de MapSymbologyEditor... hors périmètre de ce
  correctif") — le remplacer par une note courte expliquant que
  `schemaQuery` sert maintenant aux deux (attachments ET
  availableFields), pour ne pas laisser un commentaire contredire le code.

- [ ] **Step 3: Vue par défaut configurable (D12)**

  Dans le `PropsPanel`, à côté de `CameraControls` (~216-222), ajouter deux
  champs numériques :
  ```tsx
  <div className="flex gap-2">
    <label className="flex flex-col gap-1 text-xs">
      {t("widgetMap.defaultCenterLngLabel")}
      <input
        type="number"
        aria-label={t("widgetMap.defaultCenterLngAria")}
        className={fieldInputCls}
        value={Number((props.center as [number, number] | undefined)?.[0] ?? 2.4)}
        onChange={(e) =>
          onChange({
            ...props,
            center: [Number(e.target.value), (props.center as [number, number] | undefined)?.[1] ?? 46.6],
          })
        }
      />
    </label>
    <label className="flex flex-col gap-1 text-xs">
      {t("widgetMap.defaultCenterLatLabel")}
      <input
        type="number"
        aria-label={t("widgetMap.defaultCenterLatAria")}
        className={fieldInputCls}
        value={Number((props.center as [number, number] | undefined)?.[1] ?? 46.6)}
        onChange={(e) =>
          onChange({
            ...props,
            center: [(props.center as [number, number] | undefined)?.[0] ?? 2.4, Number(e.target.value)],
          })
        }
      />
    </label>
    <label className="flex flex-col gap-1 text-xs">
      {t("widgetMap.defaultZoomLabel")}
      <input
        type="number"
        aria-label={t("widgetMap.defaultZoomAria")}
        className={fieldInputCls}
        value={Number(props.zoom ?? 5)}
        onChange={(e) => onChange({ ...props, zoom: Number(e.target.value) })}
      />
    </label>
  </div>
  ```
  (`fieldInputCls` n'existe pas forcément dans ce fichier — utiliser la
  classe déjà en place pour les autres champs numériques du même
  PropsPanel, ex. `h-9 rounded-md border border-rule px-2 text-sm`.)
  Puis, dans le `Component` runtime (~371-373), lire les props au lieu du
  littéral :
  ```tsx
  view: {
    center: (props.center as [number, number] | undefined) ?? [2.4, 46.6],
    zoom: Number(props.zoom ?? 5),
    pitch: Number(props.cameraPitch ?? 0),
    bearing: Number(props.cameraBearing ?? 0),
  },
  ```
  Clés i18n :
  ```ts
  "widgetMap.defaultCenterLngLabel": "Longitude",
  "widgetMap.defaultCenterLngAria": "Longitude par défaut",
  "widgetMap.defaultCenterLatLabel": "Latitude",
  "widgetMap.defaultCenterLatAria": "Latitude par défaut",
  "widgetMap.defaultZoomLabel": "Zoom",
  "widgetMap.defaultZoomAria": "Niveau de zoom par défaut",
  ```

- [ ] **Step 4: Run test, vérifier vert**

  Run: `npx vitest run src/builder/widgets/mapWidget.test.tsx`

- [ ] **Step 5: Commit**

  ```bash
  git add shell/src/builder/widgets/mapWidget.tsx shell/src/i18n/catalog.fr.ts \
    shell/src/builder/widgets/mapWidget.test.tsx
  git commit -m "fix(shell): champs disponibles réels + vue par défaut configurable du widget carte

  Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
  ```

---

## Tâche 35 — SP-C6 : D15 — légende de symbologie sur l'éditeur de carte standalone

**Files:**
- Create: `shell/src/map/MapSymbologyLegend.tsx`
- Modify: `shell/src/builder/widgets/mapWidget.tsx` (retirer la définition
  locale ~46, importer la nouvelle)
- Modify: `shell/src/pages/MapEditorPage.tsx` (onglet "map", ~203-216)
- Test: `shell/src/map/MapSymbologyLegend.test.tsx`,
  `shell/src/pages/MapEditorPage.test.tsx`

**Interfaces:**
- Produces: `MapSymbologyLegend({ legend: LegendSpec }): JSX.Element`
  (déplacé tel quel de `mapWidget.tsx:46`, aucun changement de comportement).

- [ ] **Step 1: Test rouge — extraction pure (comportement inchangé)**

  ```tsx
  // MapSymbologyLegend.test.tsx — reprend un cas déjà couvert par
  // mapWidget.test.tsx pour la même fonction, juste importé d'ailleurs.
  test("rend une entrée de légende catégorielle", () => {
    render(<MapSymbologyLegend legend={{ color: { kind: "categorical", field: "type", entries: [{ value: "A", color: "#ff0000" }] } }} />);
    expect(screen.getByText("A")).toBeInTheDocument();
  });
  ```
  Run → FAIL (fichier absent).

- [ ] **Step 2: Extraire `MapSymbologyLegend` dans son propre fichier**

  Couper le composant de `mapWidget.tsx` (ligne 46 et son corps jusqu'à la
  fermeture) tel quel dans `map/MapSymbologyLegend.tsx`, avec ses imports
  (`LegendSpec` de `../builder/widgets/mapSymbology`). Dans
  `mapWidget.tsx`, remplacer la définition locale par :
  ```ts
  import { MapSymbologyLegend } from "../../map/MapSymbologyLegend";
  ```
  Le site d'usage (ligne ~436, `{legend && <MapSymbologyLegend legend={legend} />}`)
  ne change pas.

- [ ] **Step 3: Test rouge — légende affichée dans `MapEditorPage`**

  ```tsx
  test("affiche la légende de symbologie de chaque couche vecteur visible", () => {
    render(<MapEditorPage pk="m1" />, { wrapper }); // draft avec 1 couche vector + symbology catégorielle
    expect(screen.getByText("Résidentiel")).toBeInTheDocument(); // valeur catégorielle du fixture
  });
  ```
  Run → FAIL (rien n'affiche encore la légende de symbologie sur cette page).

- [ ] **Step 4: Brancher dans l'onglet "map" de `MapEditorPage.tsx`**

  Importer `buildLegend`, `symbologyToPaintInputs` de
  `../builder/widgets/mapSymbology` et `MapSymbologyLegend` de
  `../map/MapSymbologyLegend`. Dans le contenu de l'onglet `work` (~203-216),
  à côté du `<MapView>` :
  ```tsx
  <div className="pointer-events-none absolute bottom-2 left-2 z-10 flex flex-col gap-2">
    {draft.layers
      .filter((l): l is Extract<MapLayer, { kind: "vector" }> => l.kind === "vector" && l.visible)
      .map((l) => {
        if (!l.symbology) return null;
        const { encodings, colorDomain, sizeDomain, palette, stroke } = symbologyToPaintInputs(
          l.symbology,
          undefined,
        );
        const legend = buildLegend(
          encodings,
          colorDomain,
          sizeDomain,
          l.geometryKind ?? "polygon",
          palette,
          { stroke, icon: l.symbology.icon },
        );
        return legend ? <MapSymbologyLegend key={l.id} legend={legend} /> : null;
      })}
  </div>
  ```

- [ ] **Step 5: Run tests, vérifier vert**

  Run: `npx vitest run src/map/MapSymbologyLegend.test.tsx src/builder/widgets/mapWidget.test.tsx src/pages/MapEditorPage.test.tsx`

- [ ] **Step 6: Commit**

  ```bash
  git add shell/src/map/MapSymbologyLegend.tsx shell/src/map/MapSymbologyLegend.test.tsx \
    shell/src/builder/widgets/mapWidget.tsx shell/src/pages/MapEditorPage.tsx \
    shell/src/pages/MapEditorPage.test.tsx
  git commit -m "feat(shell): légende de symbologie partagée, branchée dans l'éditeur de carte standalone

  Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
  ```

---

## Tâche 36 — SP-C6 : D16 — audit tactile de la carte (test seul, correctif conditionnel)

**Files:**
- Create: `shell/e2e/map-touch.spec.ts`
- Modify: `shell/playwright.config.ts` (nouveau projet mobile)

- [ ] **Step 1: Ajouter un projet mobile à `playwright.config.ts`**

  ```ts
  import { devices } from "@playwright/test";
  // ... dans `projects: [...]`
  {
    name: "mobile-touch",
    use: { ...devices["iPhone 13"], hasTouch: true },
    testMatch: /map-touch\.spec\.ts/,
  },
  ```

- [ ] **Step 2: Écrire `map-touch.spec.ts`**

  ```ts
  import { test, expect } from "@playwright/test";

  test("le tap sur une entité ouvre son popup", async ({ page }) => {
    await page.goto("/maps/m1"); // fixture existante à réutiliser (patron des autres specs carte)
    await page.waitForSelector("canvas.maplibregl-canvas");
    await page.tap("canvas.maplibregl-canvas", { position: { x: 200, y: 200 } });
    await expect(page.getByRole("dialog")).toBeVisible();
  });

  test("la barre d'outil de mesure a une cible tactile d'au moins 24x24px", async ({ page }) => {
    await page.goto("/maps/m1");
    const button = page.getByRole("button", { name: /mesure/i });
    const box = await button.boundingBox();
    expect(box?.width).toBeGreaterThanOrEqual(24);
    expect(box?.height).toBeGreaterThanOrEqual(24);
  });
  ```
  (adapter la route/fixture exacte au patron des autres specs `e2e/map-*.spec.ts`
  déjà existantes dans le dépôt — reprendre leur URL et leur setup de mock).

- [ ] **Step 3: Exécuter et constater**

  Run: `cd shell && npx playwright test map-touch.spec.ts --project=mobile-touch`
  - Si PASS : D16 est déjà correct, ce test reste comme filet — pas de
    correctif de code, passer au Step 4 directement.
  - Si FAIL : lire l'échec, corriger le défaut réel trouvé (taille de
    cible CSS insuffisante, ou gestionnaire de tap manquant sur la carte)
    dans le fichier concerné, puis rejouer jusqu'à PASS. Ne pas deviner le
    correctif à l'avance — le défaut réel n'est pas connu tant que ce test
    n'a pas tourné.

- [ ] **Step 4: Commit**

  ```bash
  git add shell/e2e/map-touch.spec.ts shell/playwright.config.ts
  # + tout fichier corrigé si Step 3 a trouvé un vrai défaut
  git commit -m "test(shell): audit tactile de la carte (tap popup, cible mesure)

  Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
  ```

---

## Tâche 37 — SP-C6 : D55 — lecture seule effective sur le canevas de pipeline

**Files:**
- Modify: `shell/src/builder/pipeline/PipelineCanvas.tsx` (`PipelineCanvasInner`
  ~267-297 pour la prop, `onConnect` ~303-321, `handleNodesChange` ~322+)
- Modify: `shell/src/pages/PipelineBuilderPage.tsx` (site d'appel ~378,
  boutons Undo/Redo ~355-359, raccourci clavier ~147)
- Test: `shell/src/builder/pipeline/PipelineCanvas.test.tsx`,
  `shell/src/pages/PipelineBuilderPage.test.tsx`

- [ ] **Step 1: Test rouge — un canevas en lecture seule refuse connexion/suppression**

  ```tsx
  test("readOnly empêche onConnect de créer une arête", () => {
    const onEdgesChange = vi.fn();
    render(<PipelineCanvasInner readOnly nodes={[...]} edges={[]} onEdgesChange={onEdgesChange} ... />);
    // simuler un connect via l'API réactflow exposée par le test existant du fichier
    // (patron déjà présent pour tester onConnect)
    expect(onEdgesChange).not.toHaveBeenCalled();
  });
  test("readOnly désactive Undo/Redo et Ctrl+Z dans PipelineBuilderPage", async () => {
    render(<PipelineBuilderPage pk="p1" />, { wrapper }); // itemQuery mocké sans permission "write"
    expect(screen.getByRole("button", { name: t("pipelineCanvas.undoAria") })).toBeDisabled();
    await userEvent.keyboard("{Control>}z{/Control}");
    // pas d'assertion d'appel possible directement sans espionner `undo` —
    // vérifier plutôt qu'aucun changement de draft n'a eu lieu (state inchangé)
  });
  ```
  Adapter aux patrons de test déjà en place dans les deux fichiers. Run →
  FAIL (`readOnly` n'existe pas encore sur `PipelineCanvasInner`).

- [ ] **Step 2: Ajouter `readOnly` à `PipelineCanvasInner`**

  Dans la signature de props (~267-283) :
  ```tsx
  function PipelineCanvasInner({
    nodes,
    edges,
    selectedNodeId,
    onSelectNode,
    onNodesChange,
    onEdgesChange,
    onInsertOnEdge,
    opsCatalog,
    nodeStats,
    runStatus,
    nodeErrors,
    notes,
    onNotesChange,
    readOnly,
  }: {
    // ... champs existants inchangés
    readOnly?: boolean;
  }) {
  ```
  Gater `onConnect` (~303-321) : ajouter en tête du callback
  ```tsx
  const onConnect: OnConnect = useCallback(
    (connection) => {
      if (readOnly) return;
      // ... corps existant inchangé
    },
    [/* dépendances existantes */, readOnly],
  );
  ```
  Gater `handleNodesChange` de même — filtrer les `changes` de type
  `"remove"`/`"add"` avant traitement quand `readOnly` :
  ```tsx
  const handleNodesChange = useCallback(
    (changes: NodeChange[]) => {
      const effectiveChanges = readOnly
        ? changes.filter((c) => c.type !== "remove" && c.type !== "add")
        : changes;
      // ... corps existant, mais opérant sur `effectiveChanges` au lieu de `changes`
    },
    [/* dépendances existantes */, readOnly],
  );
  ```
  (vérifier le nom réel du paramètre du callback existant avant de
  renommer — l'essentiel est d'intercaler le filtre avant le traitement
  actuel, pas de réécrire toute la fonction).

- [ ] **Step 3: Propager `readOnly` depuis `PipelineBuilderPage.tsx`**

  Site d'appel (~378) :
  ```tsx
  <PipelineCanvas
    // ... props existantes inchangées
    readOnly={readOnly}
  />
  ```
  Boutons Undo/Redo (~355-359) :
  ```tsx
  <Button size="sm" variant="outline" disabled={!canUndo || readOnly} onClick={undo}>
  ...
  <Button size="sm" variant="outline" disabled={!canRedo || readOnly} onClick={redo}>
  ```
  Raccourci clavier (~147) — dans le `useEffect` de l'écouteur keydown,
  ajouter la garde en tête du handler :
  ```tsx
  if (readOnly) return;
  if (!(e.metaKey || e.ctrlKey) || e.key.toLowerCase() !== "z") return;
  ```

- [ ] **Step 4: Run tests, vérifier vert**

  Run: `npx vitest run src/builder/pipeline/PipelineCanvas.test.tsx src/pages/PipelineBuilderPage.test.tsx`

- [ ] **Step 5: Commit**

  ```bash
  git add shell/src/builder/pipeline/PipelineCanvas.tsx shell/src/pages/PipelineBuilderPage.tsx \
    shell/src/builder/pipeline/PipelineCanvas.test.tsx shell/src/pages/PipelineBuilderPage.test.tsx
  git commit -m "fix(shell): lecture seule effective sur le canevas de pipeline

  Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
  ```

---

## Tâche 38 — SP-C6 : D56 — historique persistant du copilote (App Builder)

**Files:**
- Create: `shell/src/lib/copilotHistory.ts`
- Create: `shell/src/lib/copilotHistory.test.ts`
- Modify: `shell/src/builder/copilot/CopilotChat.tsx` (nouveau callback
  optionnel `onExchange`)
- Modify: `shell/src/builder/copilot/CopilotPanel.tsx`
- Test: `shell/src/builder/copilot/CopilotPanel.test.tsx`

**Interfaces:**
- Produces: `readCopilotHistory()`/`appendCopilotHistory(entry)` (clé
  `geostudio.copilot.history`, même forme que `sqlLabHistory.ts` : 20
  entrées max, try/catch silencieux).
- Produces: `CopilotChat`'s nouvelle prop optionnelle
  `onExchange?: (entry: { message: string; opsCount: number; status: "ok" | "error" }) => void`
  — additive, tout appelant existant qui ne la passe pas garde son
  comportement actuel inchangé.

- [ ] **Step 1: Test rouge — `copilotHistory.ts`**

  ```ts
  import { appendCopilotHistory, readCopilotHistory } from "./copilotHistory";

  test("persiste et relit une entrée d'historique du copilote", () => {
    appendCopilotHistory({ message: "ajoute une carte", opsCount: 1, status: "ok" });
    const history = readCopilotHistory();
    expect(history[0].message).toBe("ajoute une carte");
    expect(history[0].status).toBe("ok");
  });
  test("plafonne à 20 entrées", () => {
    for (let i = 0; i < 25; i++) appendCopilotHistory({ message: `m${i}`, opsCount: 0, status: "ok" });
    expect(readCopilotHistory()).toHaveLength(20);
  });
  ```
  Run → FAIL (module absent).

- [ ] **Step 2: `copilotHistory.ts` (copie du patron `sqlLabHistory.ts`)**

  ```ts
  // SPDX-License-Identifier: Apache-2.0
  export type CopilotHistoryEntry = {
    id: string;
    message: string;
    opsCount: number;
    status: "ok" | "error";
    executedAt: string;
  };

  const STORAGE_KEY = "geostudio.copilot.history";
  const MAX_ENTRIES = 20;

  export function readCopilotHistory(): CopilotHistoryEntry[] {
    try {
      const raw = localStorage.getItem(STORAGE_KEY);
      if (!raw) return [];
      const parsed = JSON.parse(raw);
      return Array.isArray(parsed) ? (parsed as CopilotHistoryEntry[]) : [];
    } catch {
      return [];
    }
  }

  export function appendCopilotHistory(
    entry: Omit<CopilotHistoryEntry, "id" | "executedAt">,
  ): CopilotHistoryEntry[] {
    const withMeta: CopilotHistoryEntry = {
      ...entry,
      id: crypto.randomUUID(),
      executedAt: new Date().toISOString(),
    };
    const next = [withMeta, ...readCopilotHistory()].slice(0, MAX_ENTRIES);
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(next));
    } catch {
      // localStorage indisponible — dégrade silencieusement, même patron
      // que sqlLabHistory.ts.
    }
    return next;
  }
  ```

- [ ] **Step 3: Nouveau callback `onExchange` sur `CopilotChat`**

  Ajouter à la signature de props (additif, optionnel) :
  ```tsx
  onExchange?: (entry: { message: string; opsCount: number; status: "ok" | "error" }) => void;
  ```
  Dans `send()`, après le bloc `try` (succès, juste après avoir construit
  `lastOpsSummary` dans les deux branches `if`/`else` du `result.clientOps.length > 0`) :
  ```tsx
  onExchange?.({ message, opsCount: result.clientOps.length, status: "ok" });
  ```
  et dans le bloc `catch` :
  ```tsx
  } catch {
    setError(t("copilot.requestFailed"));
    onExchange?.({ message, opsCount: 0, status: "error" });
  } finally {
  ```

- [ ] **Step 4: Brancher dans `CopilotPanel.tsx`**

  ```tsx
  import { appendCopilotHistory } from "../../lib/copilotHistory";
  // ...
  return (
    <CopilotChat
      itemId={itemId}
      surface="app_builder"
      contextPayload={config}
      clientTools={buildClientToolSchemas()}
      opLabels={OP_LABELS}
      onClientOps={handleClientOps}
      onExchange={(entry) => appendCopilotHistory(entry)}
    />
  );
  ```

- [ ] **Step 5: Run tests, vérifier vert**

  Run: `npx vitest run src/lib/copilotHistory.test.ts src/builder/copilot/CopilotChat.test.tsx src/builder/copilot/CopilotPanel.test.tsx`

- [ ] **Step 6: Commit**

  ```bash
  git add shell/src/lib/copilotHistory.ts shell/src/lib/copilotHistory.test.ts \
    shell/src/builder/copilot/CopilotChat.tsx shell/src/builder/copilot/CopilotPanel.tsx \
    shell/src/builder/copilot/CopilotPanel.test.tsx
  git commit -m "feat(shell): persiste l'historique des échanges du copilote App Builder

  Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
  ```

---

## Tâche 39 — SP-C6 : D04 — déclenchement manuel d'une règle d'alerte (route REST + bouton)

**Files:**
- Modify: `core/app/alerts/routes.py`
- Modify: `core/tests/alerts/test_routes.py` (ou chemin réel du fichier de
  test des routes alerts — vérifier le nom exact avant d'écrire dedans)
- Modify: `shell/src/api/types.ts` (ajouter `evaluateAlertRule` à
  `ItemClient`)
- Modify: `shell/src/api/domains/alerts.ts`
- Modify: `shell/src/api/domains/alerts.hooks.ts`
- Modify: `shell/src/builder/AlertRuleEditor.tsx` (`AlertRuleRow`, ~19-42)
- Modify: `shell/src/i18n/catalog.fr.ts`
- Modify: `docs/revue/inventaire-fonctionnalites.jsonl` (entrée
  `automatisation-definir-une-regle-d-alerte-de-seuil-sur-un-dataset`,
  ajouter `"POST /v1/alerts/{item_id}/evaluate"` à `surfaces.rest`)
- Test: `shell/src/builder/AlertRuleEditor.test.tsx`

**Interfaces:**
- Produces (cœur) : `POST /alerts/{item_id}/evaluate` → `202`
  `{"evaluationId": str}`, garde `can(..., "write")`.
- Produces (shell) : `ItemClient.evaluateAlertRule(itemId: string): Promise<{ evaluationId: string }>`,
  hook `useEvaluateAlertRule()`.

- [ ] **Step 1: Test rouge — cœur, route refuse en lecture seule, réussit en écriture**

  Dans le fichier de test des routes alerts (localiser avec
  `grep -rn "get_alert_evaluations\|list_alerts_for_dataset" core/tests/`
  pour trouver le fichier réel avant d'écrire) :
  ```python
  def test_evaluate_alert_requires_write(client, alert_rule_read_only_token):
      resp = client.post(
          f"/v1/alerts/{alert_rule_read_only_token.item_id}/evaluate",
          headers=alert_rule_read_only_token.headers,
      )
      assert resp.status_code == 404  # même repli 404 que _require_alert_read_access

  def test_evaluate_alert_defers_evaluation(client, alert_rule_write_token, mocker):
      deferred = mocker.patch("app.alerts.jobs.evaluate_alert_task.defer")
      resp = client.post(
          f"/v1/alerts/{alert_rule_write_token.item_id}/evaluate",
          headers=alert_rule_write_token.headers,
      )
      assert resp.status_code == 202
      assert "evaluationId" in resp.json()
      deferred.assert_called_once()
  ```
  Adapter aux fixtures réelles du fichier de test choisi (noms de
  fixtures/tokens à vérifier — reprendre le patron déjà utilisé par les
  tests existants de `get_alert_evaluations`/`list_alerts_for_dataset`
  dans le même fichier). Run → FAIL (route absente, 404 générique).

- [ ] **Step 2: Route cœur**

  Dans `core/app/alerts/routes.py`, ajouter l'import :
  ```python
  from app.alerts import jobs as alerts_jobs
  ```
  puis, après `get_alert_evaluations` :
  ```python
  class EvaluateAlertResponse(BaseModel):
      evaluationId: str


  def _require_alert_write_access(session: Session, *, user: User, item_id: str) -> None:
      facts = items_repo.get_access_facts(session, tenant_id=user.tenant_id, item_id=item_id)
      if facts is None or not can(session, user_id=user.id, action="write", item=facts):
          raise HTTPException(status_code=404, detail="alert rule not found")


  @router.post(
      "/alerts/{item_id}/evaluate", response_model=EvaluateAlertResponse, status_code=202
  )
  def evaluate_alert_now(
      item_id: str,
      session: Session = Depends(get_session),
      user: User = Depends(get_current_user),
  ) -> EvaluateAlertResponse:
      _require_alert_write_access(session, user=user, item_id=item_id)
      evaluation = alerts_repo.create_evaluation(
          session, tenant_id=user.tenant_id, alert_rule_item_id=item_id
      )
      session.commit()
      alerts_jobs.evaluate_alert_task.defer(evaluation_id=evaluation.id, tenant_id=user.tenant_id)
      return EvaluateAlertResponse(evaluationId=evaluation.id)
  ```

- [ ] **Step 3: Run test cœur, vérifier vert**

  Run: `cd core && uv run pytest <chemin réel du fichier de test> -v`

- [ ] **Step 4: Régénérer OpenAPI + types TS (piège n°1 CLAUDE.md)**

  ```bash
  cd core && PYTHONPATH=. \
    CORE_SECRETS_MASTER_KEY="AAECAwQFBgcICQoLDA0ODxAREhMUFRYXGBkaGxwdHh8=" \
    uv run python scripts/export_openapi.py openapi.json
  cd ../shell && npm run gen:api-types
  ```
  Vérifier le diff de `src/api/generated/core-schema.d.ts` — attendu :
  une nouvelle opération `POST /alerts/{item_id}/evaluate`.

- [ ] **Step 5: Entrée d'inventaire de fonctionnalités**

  Dans `docs/revue/inventaire-fonctionnalites.jsonl`, sur la ligne de
  l'entrée `automatisation-definir-une-regle-d-alerte-de-seuil-sur-un-dataset`,
  ajouter `"POST /v1/alerts/{item_id}/evaluate"` au tableau
  `surfaces.rest` existant (à côté des deux routes GET déjà présentes).
  Ne PAS créer de nouvelle entrée — même module, même écran.
  Vérifier : `cd core && PYTHONPATH=. uv run python scripts/feature_health_cli.py --repo .. --check`
  ne signale plus cette route comme non inventoriée (le `--write` complet
  de régénération du bilan se fait à la clôture de la vague entière, pas
  tâche par tâche).

- [ ] **Step 6: Test rouge — shell, `evaluateAlertRule` + bouton**

  ```tsx
  test("evaluateAlertRule appelle POST /alerts/:id/evaluate", async () => {
    const client = makeClient(); // patron existant itemClient.test.ts
    mockFetchOnce({ evaluationId: "e1" });
    const result = await client.evaluateAlertRule("a1");
    expect(result.evaluationId).toBe("e1");
    expect(lastRequest().method).toBe("POST");
    expect(lastRequest().url).toContain("/alerts/a1/evaluate");
  });
  ```
  Et dans `AlertRuleEditor.test.tsx` :
  ```tsx
  test("le bouton Exécuter maintenant déclenche une évaluation", async () => {
    const evaluate = vi.fn().mockResolvedValue({ evaluationId: "e1" });
    render(<AlertRuleEditor ... />, { client: { evaluateAlertRule: evaluate } });
    await userEvent.click(screen.getByRole("button", { name: t("alertRule.evaluateNowButton") }));
    expect(evaluate).toHaveBeenCalledWith("<itemId de la fixture>");
  });
  ```
  Run → FAIL (méthode/bouton absents).

- [ ] **Step 7: `ItemClient.evaluateAlertRule` (shell)**

  `api/types.ts`, ajouter à l'interface `ItemClient` (à côté de
  `getAlertEvaluations`) :
  ```ts
  evaluateAlertRule(itemId: string): Promise<{ evaluationId: string }>;
  ```
  `api/domains/alerts.ts`, ajouter à `AlertsMethods` et à l'implémentation :
  ```ts
  type AlertsMethods = Pick<
    ItemClient,
    | "createAlertRuleItem"
    | "getAlertRuleConfig"
    | "saveAlertRuleConfig"
    | "listAlertRulesForDataset"
    | "getAlertEvaluations"
    | "evaluateAlertRule"
  >;
  // ... dans createAlertsMethods(base), après getAlertEvaluations:
  async evaluateAlertRule(itemId: string): Promise<{ evaluationId: string }> {
    return request<{ evaluationId: string }>("POST", `/alerts/${itemId}/evaluate`);
  },
  ```

- [ ] **Step 8: Hook + bouton**

  `api/domains/alerts.hooks.ts`, ajouter :
  ```ts
  export function useEvaluateAlertRule() {
    const client = useItemClientInternal();
    const queryClient = useQueryClient();
    return useMutation({
      mutationFn: (alertItemId: string) => client.evaluateAlertRule(alertItemId),
      onSuccess: (_result, alertItemId) => {
        void queryClient.invalidateQueries({ queryKey: ["alert-evaluations", alertItemId] });
      },
    });
  }
  ```
  Clé i18n :
  ```ts
  "alertRule.evaluateNowButton": "Exécuter maintenant",
  ```
  Dans `AlertRuleEditor.tsx`, `AlertRuleRow` (~19-42), ajouter le bouton à
  côté du badge d'état :
  ```tsx
  function AlertRuleRow({ rule }: { rule: AlertRuleSummary }) {
    const [limit, setLimit] = useState(EVALUATIONS_PAGE_SIZE);
    const evaluationsQuery = useAlertEvaluations(rule.itemId, { limit });
    const evaluateNow = useEvaluateAlertRule();
    const evaluations = evaluationsQuery.data ?? [];
    const latest = evaluations[0];
    return (
      <div className="flex flex-col gap-1 border-t border-rule py-1 text-xs">
        <div className="flex items-center justify-between gap-2">
          <span>{rule.title}</span>
          <div className="flex items-center gap-2">
            <span className={latest?.state === "firing" ? "font-semibold text-danger" : "text-ink-2"}>
              {latest ? latest.state : "—"}
            </span>
            <Button
              type="button"
              variant="outline"
              size="sm"
              disabled={evaluateNow.isPending}
              onClick={() => evaluateNow.mutate(rule.itemId)}
            >
              {t("alertRule.evaluateNowButton")}
            </Button>
          </div>
        </div>
        {/* ... reste du composant inchangé */}
  ```
  Importer `useEvaluateAlertRule` depuis `../api/hooks` (ou son chemin
  réel de ré-export, à vérifier — `useAlertEvaluations`/`useCreateAlertRule`
  sont déjà importés depuis `"../api/hooks"` en tête de fichier ligne 3,
  confirmer que ce fichier re-exporte bien `alerts.hooks.ts`).

- [ ] **Step 9: Run tests shell, vérifier vert**

  Run: `npx vitest run src/api/itemClient.test.ts src/builder/AlertRuleEditor.test.tsx`

- [ ] **Step 10: Commit**

  ```bash
  git add core/app/alerts/routes.py <chemin réel du test cœur> \
    core/openapi.json shell/src/api/generated/core-schema.d.ts \
    shell/src/api/types.ts shell/src/api/domains/alerts.ts shell/src/api/domains/alerts.hooks.ts \
    shell/src/builder/AlertRuleEditor.tsx shell/src/builder/AlertRuleEditor.test.tsx \
    shell/src/api/itemClient.test.ts shell/src/i18n/catalog.fr.ts \
    docs/revue/inventaire-fonctionnalites.jsonl
  git commit -m "feat: déclenchement manuel d'une évaluation d'alerte (route + bouton)

  Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
  ```

---

### Notes d'intégration — SP-C6

- Tâche 30 (D35) est la plus incertaine — si le plan final juge le
  threading de schéma dans `MapView.tsx` (Step 5) trop invasif pour cette
  vague, replier sur : formater seulement `cellValue()` (Tâche 30
  Steps 1-3) et laisser `resolvePopupContent` inchangé, en documentant
  explicitement le popup carte comme hors périmètre (comme le mode
  `template` l'est déjà).
- Tâche 35 (D15) suppose que `symbologyToPaintInputs`/`buildLegend` sont
  bien exportés (confirmé) et que `layer.geometryKind` est toujours posé
  sur une couche vecteur ayant une `symbology` (à vérifier : si un layer
  vecteur peut avoir une `symbology` sans `geometryKind` renseigné, le
  repli `?? "polygon"` déjà utilisé par `MapView.tsx:416` ailleurs dans le
  même fichier est le même repli à reprendre ici).
- Aucune tâche de ce brouillon ne touche `check-raw-colors.mjs`/
  `check-arbitrary-text-size.mjs` (SP-C3) ni `a11yAuditCoverage.test.ts`
  (SP-C2) — zéro dépendance croisée avec les autres chantiers de la Vague
  C, sauf Tâche 39 qui partage `SqlLabPage.tsx`... non, en fait Tâche 39 ne
  touche pas `SqlLabPage.tsx` (c'est D49/SP-C4 et D51/SP-C5 qui le
  partagent, pas SP-C6) — SP-C6 est bien indépendant des 5 autres chantiers
  de la vague, conformément à l'ordre d'exécution suggéré par la spec
  ("C6 en dernier... le plus mécanique/indépendant").

---

## Tâche 40 — Clôture : suites complètes, régénération, documentation

**Files:**
- Modify: `CLAUDE.md` (une ligne `### Livré`)
- Modify: `docs/revue/2026-09-04-analyse-gaps.md` (statuts des GAP-nn fermés
  par cette vague, si le document en référence — vérifier avant d'éditer ;
  la spec Vague C ne cite explicitement aucun GAP-nn, seulement des D-codes
  du diagnostic UI/UX, donc ce fichier peut n'avoir rien à changer)
- Modify: `docs/revue/inventaire-fonctionnalites.jsonl` (déjà mis à jour à
  la Tâche 39, Step 5 — vérifié ici, pas modifié à nouveau sauf écart)

- [ ] **Step 1: Suite complète shell + build**

  Run: `cd shell && npx vitest run`
  Expected: entièrement vert, couverture ≥ 88
  (`node scripts/check-coverage.mjs coverage/coverage-summary.json .coverage-threshold`
  après nettoyage de `dist/`/`dist-export/`).

  Run: `cd shell && npm run build`
  Expected: `tsc --noEmit` propre, `vite build` réussit, filet de taille de
  bundle (`node scripts/check-bundle-size.mjs`) sous le seuil — porter une
  attention particulière au seuil après l'installation de
  `@uiw/react-codemirror`/`@codemirror/lang-sql` (Tâche 25) : la Tâche 27
  a déjà mesuré et ajusté si besoin, revérifier ici que rien n'a bougé
  depuis (un import statique introduit par une tâche ultérieure pourrait
  avoir fait fuir CodeMirror hors du chunk asynchrone de `SqlLabPage`).

- [ ] **Step 2: Suite E2E complète**

  Run: `cd shell && VITE_AUTH_MODE=mock npm run e2e`
  Expected: entièrement vert (0 échec — `CLAUDE.md` rappelle qu'il n'y a
  plus d'échec « connu » à imputer). Porter une attention particulière à
  `e2e/a11y-audit.spec.ts` (Tâches 6-8), `e2e/map-touch.spec.ts` (Tâche 36,
  nouveau projet Playwright `mobile-touch`) et à tout parcours de pipeline
  builder (Tâche 37, lecture seule).

- [ ] **Step 3: Suite cœur**

  Run: `cd core && uv run pytest` (avec `CORE_TEST_DATABASE_URL` pointant
  un `postgis-test` réel, sinon les tests marqués `@pytest.mark.postgis`
  skippent silencieusement — piège `CLAUDE.md`).
  Expected: entièrement vert, couverture ≥ 85.

  Run: `cd core && uv run ruff check . && uv run ruff format --check . && uv run lint-imports`
  Expected: propre.

  Run: `cd core && uv run mypy --strict app/auth app/secrets app/analytics app/copilot app/admin_tools app/roles`
  Expected: propre (aucune des Tâches 18/39 ne touche ces 6 modules, mais
  le mypy strict reste une porte globale de la CI à revérifier avant de
  clore).

- [ ] **Step 4: Vérifier l'inventaire de fonctionnalités**

  Run: `cd core && PYTHONPATH=. uv run python scripts/feature_health_cli.py --repo .. --check`
  Expected: passe sans modification de
  `docs/revue/inventaire-fonctionnalites.jsonl` au-delà de ce que la
  Tâche 39/Step 5 a déjà ajouté. Si la commande échoue en signalant une
  surface non inventoriée, l'ajouter avant de continuer (ne pas supposer —
  lire le message d'erreur réel).

  Run: `cd core && PYTHONPATH=. uv run python scripts/feature_health_cli.py --repo .. --write`
  Expected: régénère `docs/revue/bilan-fonctionnalites.{html,md}` ; committer
  le résultat avec les autres fichiers de clôture.

- [ ] **Step 5: OpenAPI/types TS**

  Run:
  ```bash
  cd core && PYTHONPATH=. CORE_SECRETS_MASTER_KEY="AAECAwQFBgcICQoLDA0ODxAREhMUFRYXGBkaGxwdHh8=" \
    uv run python scripts/export_openapi.py /tmp/openapi-final.json
  diff openapi.json /tmp/openapi-final.json
  ```
  Expected: diff vide (déjà régénéré aux Tâches 19 et 39/Step 4, revérifié
  ici après toutes les autres tâches qui ne touchent pas le cœur). Si non
  vide, régénérer `openapi.json` et `cd shell && npm run gen:api-types`
  avant de committer.

- [ ] **Step 6: `pre-commit` complet**

  Run: `uvx pre-commit run --all-files`
  Expected: 5 hooks passent.

- [ ] **Step 7: `CLAUDE.md` § Livré**

  Ajouter une ligne sous `### Livré`, style identique aux entrées
  existantes (une seule ligne, détail complet réservé à
  `docs/superpowers/2026-08-27-historique-execution-continu.md`) :

  ```
  - **Vague C polish, a11y AA, perf perçue, onboarding** — 6 chantiers
    (SP-C1→SP-C6, 27 défauts D-codes) : a11y clavier/focus (formulaire,
    popup carte, `Drawer`, réordonnancement de champs), filet de couverture
    d'audit a11y automatisé + respect de `prefers-reduced-motion`,
    cohérence visuelle (tokens de taille de texte, segmented-control,
    dernières pages `ui/*` legacy migrées), onboarding (palette de
    commandes ⌘K, aide contextuelle, quotas visibles), éditeur CodeMirror +
    erreurs DuckDB lisibles sur SQL Lab, finitions transverses (pluriel
    grammatical fr, widget carte, pipeline en lecture seule, historique du
    copilote, déclenchement manuel d'une évaluation d'alerte).
  ```

  Vérifier le garde-fou de taille avant de committer :
  Run: `python3 scripts/check_claude_md_size.py CLAUDE.md .claude-md-size-threshold`
  Expected: sous le seuil.

- [ ] **Step 8: Commit de clôture**

  ```bash
  cd /home/lenen/projets/geostudio
  git add CLAUDE.md docs/revue/bilan-fonctionnalites.html docs/revue/bilan-fonctionnalites.md
  git commit -m "$(cat <<'EOF'
  docs: clôture Vague C (polish, a11y AA, perf perçue, onboarding)

  Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
  EOF
  )"
  ```

---

---

## Self-Review

**Couverture de la spec** (27 D-codes de
`docs/superpowers/specs/2026-09-27-vague-c-polish-a11y-onboarding-design.md`,
mappés un par un) :

| D-code | Tâche(s) |
|---|---|
| D32 | Tâche 1 |
| D41 | Tâche 2 |
| D48 | Tâche 3 |
| D34 | Tâche 4 |
| D43 | Tâches 6, 7, 8 |
| D42 | Tâches 9, 10 |
| D46 | Tâches 11, 12 |
| D47 | Tâche 13 |
| D10 | Tâches 14, 15, 16 |
| (finition SP-B12/D14) | Tâche 17 |
| D08 | Tâches 18, 19, 20 |
| D07 | Tâche 21 |
| D49 | Tâche 22 |
| D51 | Tâches 23, 24 |
| D54 | Tâches 25, 26 (+ 27, vérification empirique du bundle) |
| D50 | Tâche 28 |
| D52 | Tâche 29 |
| D35 | Tâche 30 |
| D36 | Tâche 31 |
| D38 | Tâche 32 |
| D39 | Tâche 33 |
| D11 + D12 | Tâche 34 |
| D15 | Tâche 35 |
| D16 | Tâche 36 |
| D55 | Tâche 37 |
| D56 | Tâche 38 |
| D04 | Tâche 39 |

27 D-codes, tous mappés à au moins une tâche. La Tâche 5 (filet transverse
`aria-required`) et la Tâche 40 (clôture) n'ont pas de D-code propre —
la première consolide D32 sur les branches non couvertes par la Tâche 1,
la seconde est la clôture de branche standard (cf. précédent Vague B,
Tâche 34).

**Recherche de placeholders :** scanné pour `TBD`/`TODO` (hors mentions
prose légitimes : ligne ~1088 décrit le format du pragma d'exemption
lui-même, qui interdit justement un simple « TODO » comme motif ; les deux
« Scan de placeholders » aux Tâches 5 et 12 sont les self-reviews des
agents de recherche eux-mêmes rapportant qu'ils n'en ont trouvé aucun) et
pour « similaire à la tâche N » — aucune occurrence réelle de placeholder
non résolu. Chaque Step de code contient du code complet, pas de
signature vide ni de commentaire différant l'implémentation.

**Cohérence des types/noms across tâches** — vérifié par grep sur le
document assemblé :
- `UsageSnapshotResponse.{maxItems,maxCollections,maxStorageBytes}`
  (créés Tâche 18) : mêmes noms de champs (`int | None` côté Pydantic,
  `number | null` côté TS) dans la Tâche 18 (cœur), la Tâche 19
  (régénération, schéma TS attendu) et la Tâche 20 (`useQuotaUsage`,
  `AdminInfrastructurePage`).
- `parseErrorResponse` (exporté Tâche 24) : même signature
  `(res: Response): Promise<ApiError>` à l'export (`base.ts`) et à la
  consommation (`exportsIngestion.ts`).
- `evaluateAlertRule(itemId: string): Promise<{ evaluationId: string }>`
  (Tâche 39) : même signature sur l'interface `ItemClient`,
  l'implémentation `AlertsMethods`, le hook `useEvaluateAlertRule`, et le
  test du bouton `AlertRuleEditor`.
- `onExchange?: (entry: { message: string; opsCount: number; status: "ok" | "error" }) => void`
  (Tâche 38) : même forme sur la prop de `CopilotChat` et sur le callback
  passé par `CopilotPanel`.
- `formatFieldValue(value: unknown, fieldType?: CollectionFieldType): string`
  et `formatCelError(raw: string): string` (Tâche 30) : mêmes signatures à
  la définition (`fieldFormat.ts`/`celError.ts`) et aux 2+4 sites de
  consommation (`cellValue()`, `resolvePopupContent`, `PropsPanel`,
  `NavigationPanel`, `ActionsPanel`, `PopupEditor`).
- `id="new-item-trigger"` (Tâche 21) : même identifiant au site de pose
  (`NewItemButton.tsx`) et aux 3 sites de consommation (palette + test).
- `navigableDomains(profile)` (Tâche 21) : même signature d'import et
  d'usage (filtrage sur `state === "visible"`) cohérente avec sa
  définition existante (`auth/capabilities.ts`, non modifiée par ce plan).
- Rôle de test CodeMirror `findByRole("textbox", { name: "Requête SQL" })`
  (Tâche 25) : même sélecteur réutilisé par la Tâche 26 (autocomplétion),
  cohérent.

**Point de croisement de fichier signalé pour l'exécution** (cf. section
« Ordre d'exécution » du header) : Tâche 22 (SP-C4/D49) et Tâches 23-24
(SP-C5/D51) touchent toutes `shell/src/pages/SqlLabPage.tsx`, à des
zones différentes du fichier (aide contextuelle en tête de formulaire vs.
affichage d'erreur) — aucun conflit de nom/signature entre les deux, mais
les enchaîner en série (committer l'une avant de commencer l'autre) évite
un conflit de merge inutile si elles sont exécutées par deux agents en
parallèle.

**Incertitudes assumées, non résolues par la recherche** (documentées à
leur tâche, avec la vérification empirique explicitement prévue plutôt
qu'une supposition — piège n°3 de `CLAUDE.md`) :
- Tâche 23 (D51a) : position exacte du `^` dans un message DuckDB réel —
  ajustement empirique prévu si le test échoue au premier run.
- Tâches 25-26 (D54) : forme exacte de la prop `aria-label` sur
  `@uiw/react-codemirror` et de l'option `schema` sur `@codemirror/lang-sql`
  — vérification empirique post-installation prévue.
- Tâche 30 (D35) : le mode `template` d'un popup carte reste hors
  périmètre du formatage fr-FR (décision de scope documentée en Global
  Constraints) ; si le threading du schéma dans `MapView.tsx` (Step 5)
  s'avère trop invasif à l'exécution, replier sur `cellValue()` seul
  (Steps 1-3) est explicitement prévu comme repli.
- Tâche 36 (D16) : le test tactile peut ne rien trouver à corriger — Step
  3 documente la branche « déjà correct, le test reste comme filet ».

Aucun gap de couverture de spec résiduel trouvé après cette relecture.
