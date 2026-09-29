# Orchestration de l'audit — 2026-09-29

Spec : `docs/superpowers/specs/2026-09-29-audit-multi-agents-design.md`. Plan vague 0 : `docs/superpowers/plans/2026-09-29-audit-multi-agents-vague0.md`.

## Pré-requis (une fois)

1. `docker compose up -d` : les services par défaut `healthy` (12 dans CLAUDE.md) ; `docker inspect geostudio-worker-1 --format '{{.RestartCount}}'` stable.
2. Bootstrap des personas et snapshot de référence (exécuté **une seule fois** au début de la vague 2). Les tables Keycloak vivent dans le schéma `public` de la base `gis`, que `reset` supprime et restaure : les personas doivent donc exister **avant** le snapshot. Ordre impératif :
   1. `scripts/audit/seed-personas.sh` (crée les 4 personas Keycloak)
   2. `scripts/audit/stack-reset.sh snapshot` (snapshot initial, personas inclus)
   3. `scripts/audit/stack-reset.sh reset --auth oidc` (reset avec OIDC prêt ; c'est `reset`, et non `snapshot`, qui échoue avec « aucun snapshot » sur machine vierge)
   4. Premier login de chaque persona : `cd shell && AUDIT_AUTH=oidc npx playwright test -c playwright.journeys.config.ts e2e/journeys/_witness/personas.spec.ts`
   5. `scripts/audit/seed-personas.sh --set-roles` (assigne les rôles, une fois les utilisateurs créés côté cœur)
   6. `scripts/audit/stack-reset.sh snapshot` (snapshot définitif)
3. `cd core && PYTHONPATH=. uv run python scripts/audit_prompts.py render --out ../docs/revue/audit-2026-09-29/prompts`.

## Pré-requis techniques (Chromium cross-origin)

Chromium se lance avec `--disable-web-security` car le shell (:8300) appelle le cœur (:8200) sans CORS.
L'option est déjà configurée dans le fichier partagé `shell/playwright.journeys.config.ts` (clé `launchOptions.args`).
Les agents ne doivent **jamais** surcharger cette option dans leurs specs.

## Ordre d'exécution

| Vague | Agents | Parallélisme |
|---|---|---|
| 1 | c01…c09, d01 (sans stack, lecture seule) | jusqu'à 4 en parallèle |
| 2 | j01, j02, …, j13 (séquentiels ; j01 en mock, les autres en oidc) | **1 à la fois** |
| 3 | t01…t04 (séquentiels ; t02 en dernier : `docker stop` ciblés) | **1 à la fois** |
| 4 | v01 (rejeu 100 % des S1/S2 verified) | 1 |
| 5 | k01 (consolidation) | 1 |

Les vagues 1 et 2 peuvent se chevaucher (les agents C ne touchent pas la stack). Les agents
Playwright (2, 3) sont strictement séquentiels.

## Cycle d'un agent Playwright (A/B)

1. `scripts/audit/stack-reset.sh reset --auth <mode de l'agent>`
2. Worktree éphémère : branche `audit/<id>` (voir `superpowers:using-git-worktrees`). Un worktree neuf n'a pas de `shell/node_modules` : `cd <worktree>/shell && npm ci` (choix retenu : installation propre, pas de lien symbolique).
3. Dispatcher l'agent avec `docs/revue/audit-2026-09-29/prompts/<id>.md`.
4. À la fin, **dans le worktree** (avant la fusion), avec `--repo-root` à la racine du worktree : `cd <worktree>/core && PYTHONPATH=. uv run python scripts/audit_findings.py validate ../docs/revue/audit-2026-09-29/<id> --repo-root ..` ; si rouge, renvoyer l'erreur à l'agent.
5. Fusionner la branche dans `dev`, supprimer le worktree et la branche.

## Après la vague 3

`cd core && PYTHONPATH=. uv run python scripts/audit_findings.py dedup ../docs/revue/audit-2026-09-29 --out ../docs/revue/audit-2026-09-29/merged.jsonl --repo-root ..`
