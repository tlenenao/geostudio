import js from "@eslint/js";
import tseslint from "typescript-eslint";
import reactHooks from "eslint-plugin-react-hooks";
import eslintConfigPrettier from "eslint-config-prettier";
import globals from "globals";

// NOTE (SP-22 Task 3, continuation — Option A, décision Tanguy 2026-08-20) :
// le brief d'origine prescrivait `...tseslint.configs.recommendedTypeChecked`,
// qui active 26 règles de sûreté de type au-delà des deux que cette tâche
// vise (`no-floating-promises`/`no-misused-promises`) — 845 violations dont
// 89% hors périmètre. Resserré ici à `tseslint.configs.recommended` (base non
// type-checkée) + les deux règles de promesses ajoutées explicitement, qui
// nécessitent quand même `parserOptions.project` — d'où le bloc dédié
// ci-dessous, scopé à `src/**` + `vite.config.ts` (= exactement le
// `include` de tsconfig.json) pour ne pas produire de parse-errors sur les
// fichiers hors du projet TS (e2e/, scripts/, playwright.config.ts, etc. —
// ceux-là restent couverts par le bloc `tseslint.configs.recommended` global
// ci-dessus, non type-checké, donc sans avoir besoin d'un second bloc dédié).
// Détail complet : .superpowers/sdd/task-3-report.md, section « Continuation
// — narrowed config (Option A) ».
export default tseslint.config(
  {
    ignores: [
      "dist",
      "dist-export",
      "coverage",
      "src/api/generated",
      "test-results",
      "playwright-report",
    ],
  },
  js.configs.recommended,
  ...tseslint.configs.recommended,
  {
    // `_`-prefixé = convention déjà en usage dans le dépôt pour signaler un
    // paramètre délibérément inutilisé (ex. StaticItemClient.ts, ~83 méthodes
    // "unsupported" avec `(..._args: unknown[])`). `no-unused-vars` (activé
    // par `tseslint.configs.recommended`, pas seulement TypeChecked) ne
    // reconnaît pas cette convention sans configuration explicite — pur
    // ajustement de config, aucun changement de comportement.
    rules: {
      "@typescript-eslint/no-unused-vars": [
        "error",
        { argsIgnorePattern: "^_", varsIgnorePattern: "^_" },
      ],
    },
  },
  {
    // Fichiers Node hors du `tsconfig.json` (scripts CLI, serveur e2e
    // utilitaire) : `no-undef` (actif via `js.configs.recommended`) ne
    // connaît pas les globals Node (`process`/`console`/`URL`/...) sans
    // déclaration explicite.
    files: ["scripts/**/*.mjs", "e2e/external-widget-server.mjs"],
    languageOptions: { globals: globals.node },
  },
  {
    // Fixtures de widgets tiers servies telles quelles au navigateur (E2E),
    // et `env-config.template.js` (injecté tel quel dans `index.html`,
    // exécuté côté navigateur — `window.__GEOSTUDIO_ENV__ = ...`) : même
    // lacune que ci-dessus, mais côté globals navigateur
    // (`window`/`HTMLElement`/`document`/`customElements`/...).
    files: ["public/fixtures/**/*.js", "env-config.template.js"],
    languageOptions: { globals: globals.browser },
  },
  {
    files: ["src/**/*.{ts,tsx}", "vite.config.ts"],
    languageOptions: {
      parserOptions: {
        project: ["./tsconfig.json"],
        tsconfigRootDir: import.meta.dirname,
      },
    },
    plugins: { "react-hooks": reactHooks },
    rules: {
      ...reactHooks.configs.recommended.rules,
      "@typescript-eslint/no-floating-promises": "error",
      "@typescript-eslint/no-misused-promises": "error",
      "no-restricted-syntax": [
        "error",
        {
          selector: "JSXAttribute[name.name='dangerouslySetInnerHTML']",
          message:
            "dangerouslySetInnerHTML interdit hors richSection.tsx — passer par sanitizeMarkdown() d'abord.",
        },
      ],
    },
  },
  {
    // Deux consommateurs légitimes de sanitizeMarkdown() : le widget
    // RichSection et le popup de carte (SP-24). Tout autre fichier reste
    // interdit par la règle no-restricted-syntax ci-dessus.
    files: ["src/builder/widgets/richSection.tsx", "src/map/MapPopup.tsx"],
    rules: { "no-restricted-syntax": "off" },
  },
  {
    // `no-explicit-any` (activé par `tseslint.configs.recommended`, hors
    // périmètre de cette tâche — cf. task-3-report.md, section
    // « Continuation ») déclenche 28 fois sur 4 fichiers `*.test.ts(x)`,
    // toujours sur le même idiome de mock (corps de requête MSW capturé en
    // `any` avant assertion, ou test-double `DataTransfer` indexé
    // dynamiquement). Corriger "pour de vrai" demanderait d'inventer un
    // type par forme de payload observée dans ~25 sites, dans un fichier de
    // test de 2000+ lignes pour la majorité d'entre eux — du travail de
    // typage réel plutôt que void/await/.catch(), donc hors périmètre au
    // même titre que les 26 règles déjà écartées avec `recommendedTypeChecked`.
    // Zéro risque de comportement (les annotations de type sont effacées à
    // la compilation) : carve-out documenté plutôt que remédiation.
    files: ["**/*.test.{ts,tsx}"],
    rules: { "@typescript-eslint/no-explicit-any": "off" },
  },
  eslintConfigPrettier,
);
