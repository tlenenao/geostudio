# Orchestration de l'audit — 2026-09-29

Spec : `docs/superpowers/specs/2026-09-29-audit-multi-agents-design.md`. Plan vague 0 : `docs/superpowers/plans/2026-09-29-audit-multi-agents-vague0.md`.

## Pré-requis (une fois)

1. `docker compose up -d` : 11 services healthy ; `docker inspect geostudio-worker-1 --format '{{.RestartCount}}'` stable.
2. Bootstrap des personas et snapshot de référence (exécuté **une seule fois** au début de la vague 2) :
   - `scripts/audit/stack-reset.sh snapshot` (créer le snapshot de base ; échoue sur machine vierge avec « aucun snapshot », c'est normal)
   - `scripts/audit/seed-personas.sh` (crée les 4 personas Keycloak)
   - `scripts/audit/stack-reset.sh reset --auth oidc` (reset avec OIDC prêt)
   - Premier login de chaque persona pour initialiser les sessions
   - `scripts/audit/seed-personas.sh --set-roles` (assigne les rôles aux personas)
   - `scripts/audit/stack-reset.sh snapshot` (sauvegarde définitive)
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
2. Worktree éphémère : branche `audit/<id>` (voir `superpowers:using-git-worktrees`).
3. Dispatcher l'agent avec `docs/revue/audit-2026-09-29/prompts/<id>.md`.
4. À la fin : `cd core && PYTHONPATH=. uv run python scripts/audit_findings.py validate ../docs/revue/audit-2026-09-29/<id> --repo-root ..` ; si rouge, renvoyer l'erreur à l'agent.
5. Fusionner la branche dans `dev`, supprimer le worktree et la branche.

## Après la vague 3

`cd core && PYTHONPATH=. uv run python scripts/audit_findings.py dedup ../docs/revue/audit-2026-09-29 --out ../docs/revue/audit-2026-09-29/merged.jsonl --repo-root ..`
