# Contributing to GeoStudio

Thanks for your interest in GeoStudio! This document covers everything you
need to get a local environment running, run the test suites, and open a
pull request.

GeoStudio is developed under the Apache-2.0 license (see [`LICENSE`](LICENSE)).
By contributing, you agree that your contributions will be licensed under the
same terms.

## Prerequisites

- Docker 24+ and Docker Compose
- Node.js 20+
- Python 3.12, managed via [`uv`](https://docs.astral.sh/uv/)

## Running the project locally

```bash
cp .env.example .env       # fill in the passwords
docker compose up -d       # full stack (see README.md "Démarrage rapide" for service URLs)
```

See the README's ["Démarrage rapide (dev)"](README.md#démarrage-rapide-dev)
section for service URLs and how to verify the real `oidc` auth mode. A more
complete install guide is planned as part of a separate SP-9 sub-part
(install & secrets hardening).

## Running the tests

**Shell** (`shell/`, React/TypeScript):

```bash
cd shell
npm ci
npm run test    # Vitest unit tests
npm run e2e     # Playwright E2E specs (VITE_AUTH_MODE=mock, no external services needed)
npm run build   # tsc --noEmit + vite build
```

**Core** (`core/`, Python/FastAPI):

```bash
cd core
uv sync
uv run pytest        # tests marked `postgis` are skipped unless CORE_TEST_DATABASE_URL
                      # points at a disposable Postgres+pgvector instance
                      # (see deploy/postgis/Dockerfile)
uv run lint-imports   # enforces the module-boundary contracts in pyproject.toml
```

All four commands (`npm run test`, `npm run e2e`, `npm run build`, `uv run
pytest`, `uv run lint-imports`) must be green before opening a pull request.

## Commit convention

This repo uses [Conventional Commits](https://www.conventionalcommits.org/):
`type(scope): summary`, imperative mood, one subject per commit. Examples
from this repo's actual history:

```
feat(shell): /admin/collections route, split Administration nav link into Extensions/Collections
fix(e2e): admin-collections delete state + edit DOM assertions (review fix)
test(e2e): admin collections lifecycle (register/edit/share/delete) + non-admin guard
docs: CLAUDE.md — SP-9 gestion des collections livré et clos
chore(api): regenerate openapi.json / core-schema.d.ts after Task 1
```

Common `type`s: `feat`, `fix`, `test`, `docs`, `chore`, `refactor`. Common
`scope`s: `shell`, `core`, `e2e`, `api`.

## Pull request process

1. Branch from `dev` (not `main` — `main` only receives stable, merged states).
2. Keep commits small and focused, one subject each.
3. Make sure the test commands above are green.
4. Open the PR against `dev` with a description of what changed and why.
5. Link the relevant spec/plan under `docs/superpowers/` if the change follows
   one.

## Where to find context

- [`CLAUDE.md`](CLAUDE.md) — the project's working guide: architecture rules,
  frozen decisions, current state.
- [`docs/vision/`](docs/vision/) — roadmap and product vision documents.
- [`docs/superpowers/specs/`](docs/superpowers/specs/) and
  [`docs/superpowers/plans/`](docs/superpowers/plans/) — dated spec/plan pairs
  for each sub-project.

## Reporting a bug or proposing a feature

Open a [GitHub issue](https://github.com/tlenenao/geostudio/issues). Include:

- **Bug report**: what you did, what you expected, what happened instead,
  steps to reproduce, and your environment (OS, browser if relevant, whether
  you're using `docker compose up` or a manual setup).
- **Feature request**: the problem you're trying to solve and, if you have
  one, a sketch of the solution. Check
  [`docs/vision/2026-07-04-feuille-de-route-geostudio.md`](docs/vision/2026-07-04-feuille-de-route-geostudio.md)
  first — your idea may already be scoped into a future phase.

## License headers

New source files under `core/app/`, `core/tests/`, or `shell/src/` (excluding
generated files under `shell/src/api/generated/`) should start with an SPDX
header:

- Python: `# SPDX-License-Identifier: Apache-2.0`
- TypeScript/TSX: `// SPDX-License-Identifier: Apache-2.0`

This is a reviewer convention, not an automated check — please add the header
by hand when creating a new file in these directories.

## Code of Conduct

This project follows the [Contributor Covenant](CODE_OF_CONDUCT.md). By
participating, you're expected to uphold it.
