# Post-mortem : extraction `packages/ui-kit` + `packages/app-builder` (chantier A)

**Statut : tenté puis abandonné, intégralement annulé (`git reset --hard` sur
`dev`, retour à `98da34b9`).** Aucune trace sur la branche `dev` — ce document
est la seule mémoire de la tentative. Le plan et le spec de design restent sur
disque pour référence :
- [`docs/superpowers/specs/2026-09-07-app-builder-package-extraction-design.md`](2026-09-07-app-builder-package-extraction-design.md)
- [`docs/superpowers/plans/2026-09-07-app-builder-package-extraction.md`](../plans/2026-09-07-app-builder-package-extraction.md)

## Pourquoi abandonné

L'objectif du chantier était de rendre `shell/src/ui/kit` et `shell/src/builder`
consommables par un second projet (`finance`) via un workspace npm. Sans ce
besoin de réutilisation externe, le découpage en packages n'apporte **aucun
bénéfice propre à GeoStudio** : le monolithe `shell/` était plus simple, avait
moins de surface de configuration (un seul lockfile, une seule CI, un seul
contexte Docker) et ne pouvait structurellement pas produire les classes de
bugs listées ci-dessous. Décision : ne pas poursuivre tant que le besoin de
réutilisation par `finance` n'est pas confirmé et concret.

## Ce qui a été exécuté avant l'abandon

Tâches 1 à 5 du plan (sur 12) : mise en place du workspace npm, déplacement de
`ui/kit` vers `packages/ui-kit`, extraction des types `AppConfig` et des ports
(`BuilderDataClient`/`IdentityPort`/`I18nPort`) + `AppBuilderProvider` vers
`packages/app-builder`, et l'adaptateur `ItemClient` → `BuilderDataClient`.
Chaque tâche a été implémentée, revue (spec + qualité) et corrigée par des
subagents dédiés (méthode `superpowers:subagent-driven-development`).

## Problèmes concrets identifiés (à connaître avant de retenter ce chantier)

1. **Tailwind v4 ne scanne pas `packages/*` par défaut.** Sa racine de
   détection de sources est la racine du projet Vite (`shell/`) ; tout ce qui
   vit sous un package externe (même consommé via un symlink de workspace)
   est ignoré. Résultat : des classes utilitaires utilisées **uniquement**
   par les composants déplacés (`cursor-col-resize`, `bg-ink/40`,
   `data-[highlighted]:bg-sunken`, etc.) disparaissent silencieusement du CSS
   de production — ni `tsc` ni aucun test ne le détecte, seule une inspection
   du bundle construit le révèle. Correctif : une directive `@source
   "../../packages/*/src/**/*";` dans `shell/src/index.css`.

2. **Un workspace npm rend `shell/package-lock.json` orphelin et casse
   `npm ci`.** Dans un workspace, seul le lockfile racine doit exister ;
   celui de `shell/` doit être supprimé, et **tout** endroit qui lance
   `npm ci`/`npm install` avec `working-directory: shell` (CI, trois
   Dockerfiles, `docker-compose.yml`, `CONTRIBUTING.md`, `CLAUDE.md`) doit
   être répointé vers la racine du dépôt. C'est une cascade de changements
   dans des fichiers qui n'ont, à première vue, aucun rapport avec un
   déplacement de composants React.

3. **Chaque nouveau package doit recevoir tout son outillage à la main** :
   config eslint/prettier/tsconfig, scripts `lint`/`typecheck`/`format`/
   `test`/`test:coverage`, seuil de couverture, et un job CI dédié. Rien de
   tout ça n'est hérité automatiquement du monorepo — sans vigilance
   explicite, les tests et le lint du nouveau package tournent dans
   **aucune** pipeline automatisée (découvert en revue de Task 2 : 106 tests
   de `ui-kit` non exécutés par la CI).

4. **Le seuil de couverture de `shell` doit être recalibré** quand des
   fichiers bien testés quittent son périmètre pour un package séparé — la
   couverture ne « suit » pas le code déplacé, elle chute simplement côté
   `shell` et remonte (ou apparaît) côté nouveau package.

5. **Collision `git mv` quand une tâche crée un fichier-pont temporaire à
   l'emplacement qu'une tâche ultérieure doit occuper.** Rencontré deux fois
   (le composant `Spike.tsx`/`index.ts` de la Task 1 de spike, puis les
   stubs de types `mapSymbology.ts`/`palette.ts` créés en Task 3 pour
   satisfaire une référence anticipée du plan vers du code que seule la
   Task 8 devait déplacer). Un `git mv` direct échoue sur un chemin de
   destination déjà occupé — il faut supprimer le stub avant de déplacer le
   vrai fichier.

6. **La conception d'un « port » d'interface doit être vérifiée contre les
   signatures réelles, pas devinée.** Le port `BuilderDataClient` (Task 4)
   déclarait 4 groupes de capacités optionnelles (`icons`, `attachments`,
   `terrain3d`, `features` CRUD) censées être satisfaites par une simple
   délégation vers `ItemClient`. En Task 5, aucun des 4 groupes ne
   correspondait réellement : paramètres manquants ou en trop, champs
   renommés, types de retour incompatibles. Un port écrit à partir d'une
   lecture superficielle du client réel (noms de méthodes seulement, pas
   leurs signatures complètes) produit une interface qui semble correcte
   jusqu'à ce qu'on tente réellement de l'implémenter.

7. **`npm 9.2.0` de ce dépôt ne supporte pas le protocole `workspace:`**
   (convention pnpm/Yarn Berry) — utiliser `"*"` pour une dépendance de
   workspace npm classique.

## Si ce chantier est relancé un jour

- Relire ce document avant de ré-écrire le plan — plusieurs de ces pièges
  sont réapparus une seconde fois (git mv, outillage manquant) alors qu'ils
  avaient déjà été trouvés et documentés une première fois dans la même
  tentative, faute d'avoir été anticipés dans les tâches suivantes du plan.
- Vérifier que le besoin de réutilisation par `finance` est concret et
  imminent avant de relancer — sinon le rapport coût/bénéfice reste
  défavorable pour GeoStudio seul (cf. « Pourquoi abandonné » ci-dessus).
