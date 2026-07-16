# SP-9 — Gouvernance & légal Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give an unknown visitor of the GitHub repo a clear, actionable picture — in under a minute — of the project's license, how to contribute, and how to report a code-of-conduct violation; and put an Apache-2.0 SPDX header on every applicative source file.

**Architecture:** Four static/tooling deliverables, no runtime code: `CONTRIBUTING.md` and `CODE_OF_CONDUCT.md` at the repo root, a one-time idempotent Python script (`scripts/add-license-headers.py`) that stamps SPDX headers across `core/app/`, `core/tests/`, and `shell/src/` (excluding generated files), and a short "Contribuer" paragraph added to `README.md`.

**Tech Stack:** Markdown, Python 3.12 stdlib only (`pathlib`) for the header script — no new dependency.

## Global Constraints

- Spec of record: `docs/superpowers/specs/2026-07-15-sp9-gouvernance-legale-design.md`.
- `CONTRIBUTING.md` and `CODE_OF_CONDUCT.md` are written in **English** (GitHub governance-doc convention for this project — explicit exception to the "docs in French" rule in `CLAUDE.md`).
- `CODE_OF_CONDUCT.md` is the Contributor Covenant v2.1 text **verbatim**, not rewritten — only the contact email is filled in.
- Contact email for the Code of Conduct: `lenenaon.tanguy@gmail.com`.
- No CLA/DCO, no CI header linter, no translation of the two governance docs — all explicitly out of scope (spec §2).
- SPDX header script touches `core/app/**/*.py`, `core/tests/**/*.py`, `shell/src/**/*.ts`, `shell/src/**/*.tsx` — excludes `shell/src/api/generated/` entirely.
- The header script is a one-time tool left in the repo (`scripts/add-license-headers.py`), not a hook, not a CI job.
- No new automated test suite for this sub-part (spec §5) — verification is manual: diff inspection, idempotence re-run, and confirming `npm run build` / `uv run pytest` / `uv run lint-imports` stay green.
- Repository: `https://github.com/tlenenao/geostudio` (used for the "open an issue" link in `CONTRIBUTING.md`).
- Commit convention already in use in this repo: `type(scope): summary` (e.g. `docs: …`, `feat(shell): …`, `fix(core): …`) — reuse it for this branch's commits too.

---

## File Structure

- Create `CONTRIBUTING.md` (repo root) — contributor guide: prerequisites, running the project, running tests, commit convention, PR process, where to find context, how to file issues, SPDX header convention for new files.
- Create `CODE_OF_CONDUCT.md` (repo root) — Contributor Covenant v2.1 verbatim, contact email filled in.
- Modify `README.md` — insert a new `## Contribuer` section between the existing `## Documentation` (ends line 180) and `## Licence` (line 182) sections, pointing to `CONTRIBUTING.md` and `CODE_OF_CONDUCT.md`.
- Create `scripts/add-license-headers.py` — idempotent SPDX header inserter, run once against the working tree.

---

### Task 1: `CONTRIBUTING.md` + README "Contribuer" paragraph

**Files:**
- Create: `CONTRIBUTING.md`
- Modify: `README.md` (insert new section between line 180 and line 182)

**Interfaces:**
- Consumes: nothing (static doc).
- Produces: `CONTRIBUTING.md` is linked to by `README.md` and (later, informally) by `CODE_OF_CONDUCT.md`'s sibling status at repo root — no code interface.

- [ ] **Step 1: Create `CONTRIBUTING.md`**

```markdown
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
```

- [ ] **Step 2: Insert the "Contribuer" section into `README.md`**

Read `README.md` lines 171-184 first to confirm the exact current text of the
`## Documentation` and `## Licence` sections (they must not shift before you
edit). Then insert a new section immediately after the `## Documentation`
table and its trailing blank line, and immediately before `## Licence`:

```markdown
## Contribuer

Les instructions pour lancer les tests, la convention de commits et le
processus de pull request sont dans
[`CONTRIBUTING.md`](CONTRIBUTING.md). Le code de conduite du projet est dans
[`CODE_OF_CONDUCT.md`](CODE_OF_CONDUCT.md).

```

- [ ] **Step 3: Verify the links resolve and the commands are accurate**

Run each command block copy-pasted from `CONTRIBUTING.md` once, from a clean
shell, to confirm none of them are stale:

```bash
cd shell && npm ci && npm run build
cd ../core && uv sync && uv run lint-imports
```

Expected: both complete without error (full `npm run test`/`npm run e2e`/`uv
run pytest` are re-verified in Task 3's regression step, no need to re-run the
full suites here).

- [ ] **Step 4: Commit**

```bash
git add CONTRIBUTING.md README.md
git commit -m "docs: add CONTRIBUTING.md, link it from README"
```

---

### Task 2: `CODE_OF_CONDUCT.md`

**Files:**
- Create: `CODE_OF_CONDUCT.md`

**Interfaces:**
- Consumes: nothing.
- Produces: linked from `CONTRIBUTING.md` (Task 1) and from the README's new
  "Contribuer" section (Task 1) — both links already point at
  `CODE_OF_CONDUCT.md` at repo root, matching the filename created here.

- [ ] **Step 1: Create `CODE_OF_CONDUCT.md`**

```markdown
# Contributor Covenant Code of Conduct

## Our Pledge

We as members, contributors, and leaders pledge to make participation in our
community a harassment-free experience for everyone, regardless of age, body
size, visible or invisible disability, ethnicity, sex characteristics, gender
identity and expression, level of experience, education, socio-economic status,
nationality, personal appearance, race, caste, color, religion, or sexual
identity and orientation.

We pledge to act and interact in ways that contribute to an open, welcoming,
diverse, inclusive, and healthy community.

## Our Standards

Examples of behavior that contributes to a positive environment for our
community include:

* Demonstrating empathy and kindness toward other people
* Being respectful of differing opinions, viewpoints, and experiences
* Giving and gracefully accepting constructive feedback
* Accepting responsibility and apologizing to those affected by our mistakes,
  and learning from the experience
* Focusing on what is best not just for us as individuals, but for the overall
  community

Examples of unacceptable behavior include:

* The use of sexualized language or imagery, and sexual attention or advances of
  any kind
* Trolling, insulting or derogatory comments, and personal or political attacks
* Public or private harassment
* Publishing others' private information, such as a physical or email address,
  without their explicit permission
* Other conduct which could reasonably be considered inappropriate in a
  professional setting

## Enforcement Responsibilities

Community leaders are responsible for clarifying and enforcing our standards of
acceptable behavior and will take appropriate and fair corrective action in
response to any behavior that they deem inappropriate, threatening, offensive,
or harmful.

Community leaders have the right and responsibility to remove, edit, or reject
comments, commits, code, wiki edits, issues, and other contributions that are
not aligned to this Code of Conduct, and will communicate reasons for
moderation decisions when appropriate.

## Scope

This Code of Conduct applies within all community spaces, and also applies when
an individual is officially representing the community in public spaces.
Examples of representing our community include using an official e-mail
address, posting via an official social media account, or acting as an
appointed representative at an online or offline event.

## Enforcement

Instances of abusive, harassing, or otherwise unacceptable behavior may be
reported to the community leaders responsible for enforcement at
lenenaon.tanguy@gmail.com.
All complaints will be reviewed and investigated promptly and fairly.

All community leaders are obligated to respect the privacy and security of the
reporter of any incident.

## Enforcement Guidelines

Community leaders will follow these Community Impact Guidelines in determining
the consequences for any action they deem in violation of this Code of Conduct:

### 1. Correction

**Community Impact**: Use of inappropriate language or other behavior deemed
unprofessional or unwelcome in the community.

**Consequence**: A private, written warning from community leaders, providing
clarity around the nature of the violation and an explanation of why the
behavior was inappropriate. A public apology may be requested.

### 2. Warning

**Community Impact**: A violation through a single incident or series of
actions.

**Consequence**: A warning with consequences for continued behavior. No
interaction with the people involved, including unsolicited interaction with
those enforcing the Code of Conduct, for a specified period of time. This
includes avoiding interactions in community spaces as well as external channels
like social media. Violating these terms may lead to a temporary or permanent
ban.

### 3. Temporary Ban

**Community Impact**: A serious violation of community standards, including
sustained inappropriate behavior.

**Consequence**: A temporary ban from any sort of interaction or public
communication with the community for a specified period of time. No public or
private interaction with the people involved, including unsolicited interaction
with those enforcing the Code of Conduct, is allowed during this period.
Violating these terms may lead to a permanent ban.

### 4. Permanent Ban

**Community Impact**: Demonstrating a pattern of violation of community
standards, including sustained inappropriate behavior, harassment of an
individual, or aggression toward or disparagement of classes of individuals.

**Consequence**: A permanent ban from any sort of public interaction within the
community.

## Attribution

This Code of Conduct is adapted from the [Contributor Covenant][homepage],
version 2.1, available at
[https://www.contributor-covenant.org/version/2/1/code_of_conduct.html][v2.1].

Community Impact Guidelines were inspired by
[Mozilla's code of conduct enforcement ladder][Mozilla CoC].

For answers to common questions about this code of conduct, see the FAQ at
[https://www.contributor-covenant.org/faq][FAQ]. Translations are available at
[https://www.contributor-covenant.org/translations][translations].

[homepage]: https://www.contributor-covenant.org
[v2.1]: https://www.contributor-covenant.org/version/2/1/code_of_conduct.html
[Mozilla CoC]: https://github.com/mozilla/diversity
[FAQ]: https://www.contributor-covenant.org/faq
[translations]: https://www.contributor-covenant.org/translations
```

- [ ] **Step 2: Verify the contact email is correct**

```bash
grep -n "lenenaon.tanguy@gmail.com" CODE_OF_CONDUCT.md
```

Expected: exactly one match, in the `## Enforcement` section.

- [ ] **Step 3: Commit**

```bash
git add CODE_OF_CONDUCT.md
git commit -m "docs: add CODE_OF_CONDUCT.md (Contributor Covenant v2.1)"
```

---

### Task 3: SPDX license headers on applicative source files

**Files:**
- Create: `scripts/add-license-headers.py`
- Modify (via running the script, not by hand): every file under
  `core/app/**/*.py`, `core/tests/**/*.py`, `shell/src/**/*.ts`,
  `shell/src/**/*.tsx`, except anything under `shell/src/api/generated/`.

**Interfaces:**
- Consumes: nothing (standalone script, stdlib only).
- Produces: nothing consumed by other tasks — this is the last task.

- [ ] **Step 1: Write `scripts/add-license-headers.py`**

```python
#!/usr/bin/env python3
"""Insère un en-tête SPDX Apache-2.0 dans les fichiers source applicatifs.

Idempotent : ignore les fichiers qui portent déjà l'en-tête. Usage ponctuel,
pas un hook ni un job CI — voir
docs/superpowers/specs/2026-07-15-sp9-gouvernance-legale-design.md.
"""
from __future__ import annotations

import pathlib
import sys

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent

HEADER_BY_SUFFIX = {
    ".py": "# SPDX-License-Identifier: Apache-2.0\n",
    ".ts": "// SPDX-License-Identifier: Apache-2.0\n",
    ".tsx": "// SPDX-License-Identifier: Apache-2.0\n",
}

TARGET_GLOBS = [
    ("core/app", "**/*.py"),
    ("core/tests", "**/*.py"),
    ("shell/src", "**/*.ts"),
    ("shell/src", "**/*.tsx"),
]

EXCLUDE_DIRS = [REPO_ROOT / "shell" / "src" / "api" / "generated"]


def iter_target_files() -> "set[pathlib.Path]":
    found: set[pathlib.Path] = set()
    for base, pattern in TARGET_GLOBS:
        for path in (REPO_ROOT / base).glob(pattern):
            if any(excluded in path.parents for excluded in EXCLUDE_DIRS):
                continue
            found.add(path)
    return found


def add_header(path: pathlib.Path) -> str:
    header = HEADER_BY_SUFFIX[path.suffix]
    text = path.read_text(encoding="utf-8")
    if header.strip() in text.splitlines()[:3]:
        return "skipped"
    lines = text.splitlines(keepends=True)
    insert_at = 1 if lines and lines[0].startswith("#!") else 0
    lines.insert(insert_at, header)
    path.write_text("".join(lines), encoding="utf-8")
    return "updated"


def main() -> int:
    counts = {"updated": 0, "skipped": 0}
    for path in sorted(iter_target_files()):
        counts[add_header(path)] += 1
    print(f"{counts['updated']} fichier(s) mis à jour, {counts['skipped']} déjà à jour.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 2: Dry-run the file selection before writing anything**

Temporarily verify the target set looks right by counting matches without
running the mutating part yet:

```bash
cd /home/lenen/projets/geostudio
python3 -c "
import pathlib
root = pathlib.Path('.').resolve()
globs = [('core/app','**/*.py'), ('core/tests','**/*.py'), ('shell/src','**/*.ts'), ('shell/src','**/*.tsx')]
exclude = root / 'shell' / 'src' / 'api' / 'generated'
found = set()
for base, pattern in globs:
    for p in (root / base).glob(pattern):
        if exclude in p.parents:
            continue
        found.add(p)
print(len(found))
print(sorted(str(p.relative_to(root)) for p in found if 'generated' in str(p))[:5])
"
```

Expected: a count in the low hundreds (core/app + core/tests + shell/src, no
`shell/src/api/generated/core-schema.d.ts` in the sample list — the second
printed list must be empty, confirming the exclusion works).

- [ ] **Step 3: Run the script**

```bash
chmod +x scripts/add-license-headers.py
python3 scripts/add-license-headers.py
```

Expected output: `N fichier(s) mis à jour, 0 déjà à jour.` with `N` matching
the count from Step 2.

- [ ] **Step 4: Review the diff — headers only, no content changes**

```bash
git diff --stat
git diff shell/src/api/generated/ | head -5   # must print nothing
```

Read through `git diff` in full (not just `--stat`): every hunk must be a
single added line (`+# SPDX-License-Identifier: Apache-2.0` or
`+// SPDX-License-Identifier: Apache-2.0`) at the very top of the file, with
no other line touched. If any file shows more than a one-line addition,
investigate before proceeding — do not commit an unreviewed diff.

- [ ] **Step 5: Verify idempotence**

```bash
python3 scripts/add-license-headers.py
git diff --stat
```

Expected: script prints `0 fichier(s) mis à jour, N déjà à jour.` (same `N`
as Step 3) and `git diff --stat` shows no change from Step 4's state (running
it twice produced an empty second diff).

- [ ] **Step 6: Regression — shell and core stay green**

```bash
cd shell && npm run build
cd ../core && uv run pytest
cd .. && cd core && uv run lint-imports
```

Expected: all three commands pass with no new failures (the header is a
comment/no-op for both the Python and TypeScript compilers — this step
confirms that empirically rather than assuming it).

- [ ] **Step 7: Commit**

```bash
git add scripts/add-license-headers.py core/app core/tests shell/src
git commit -m "chore: add SPDX Apache-2.0 headers to core/app, core/tests, shell/src"
```

---

## Final verification (acceptance criteria, spec §6)

- [ ] `CONTRIBUTING.md` and `CODE_OF_CONDUCT.md` exist at repo root with real,
  actionable content (not skeletons) — confirmed by Tasks 1-2.
- [ ] Every applicative source file under `core/app/`, `core/tests/`, and
  `shell/src/` (excluding `shell/src/api/generated/`) carries an SPDX
  Apache-2.0 header — confirmed by Task 3, Steps 2-5.
- [ ] `README.md` links to `CONTRIBUTING.md` — confirmed by Task 1, Step 2.
- [ ] `npm run test`, `npm run build` (shell) and `uv run pytest`, `uv run
  lint-imports` (core) all stay green — confirmed by Task 3, Step 6 (build/
  pytest/lint-imports) plus a final full run below:

```bash
cd shell && npm run test
cd ../core && uv run pytest
```

Expected: both green, no new failures introduced by this branch.
