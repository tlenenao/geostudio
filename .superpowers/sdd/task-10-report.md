# Task 10 report: `deploy/appexport-standalone/Dockerfile`

## What was done

1. Created `deploy/appexport-standalone/Dockerfile` with the exact content
   given in the brief (verbatim, no deviations) — a two-stage build:
   - Stage `shell-runtime` (`node:20-slim`): `npm ci` + `npm run
     build:export-runtime` (runs `vite build --config
     vite.export.config.ts`) producing `dist-export/`, then renames
     `index.export.html` → `index.html` so `StaticFiles(html=True)` in
     `core/app/appexport/miniserver/main.py` serves it for `/`.
   - Stage 2 (`python:3.12-slim`): minimal pip install (`fastapi`,
     `uvicorn[standard]`, `pydantic`, `duckdb`, `sqlalchemy`), installs the
     DuckDB `spatial` extension at build time, copies `core/app` → `/app/app`
     and the built runtime from stage 1 → `/runtime`, sets
     `APPEXPORT_STANDALONE_DATA_DIR=/data` and
     `APPEXPORT_STANDALONE_RUNTIME_DIR=/runtime`, exposes port 8000, and
     runs `uvicorn app.appexport.miniserver.main:app --host 0.0.0.0 --port
     8000`.

2. Verified pre-conditions before building (not in the brief, done as a
   sanity check): `shell/package.json` has the `build:export-runtime`
   script (`vite build --config vite.export.config.ts`),
   `shell/vite.export.config.ts` exists, and
   `core/app/appexport/miniserver/main.py` exists (from earlier tasks in
   this plan).

3. **Ran the real build** from the repo root:
   ```
   docker build -f deploy/appexport-standalone/Dockerfile -t geostudio-appexport-standalone:local .
   ```
   Build succeeded end-to-end on the first attempt, no retries needed, no
   Dockerfile changes required. Total wall time roughly 45s (image layers
   for `node:20-slim`/`python:3.12-slim` were partly cached from prior
   builds in this environment; `npm ci` ~20s, `npm run build:export-runtime`
   ~14.5s, `pip install` ~18.6s, DuckDB spatial extension install ~5.4s).

4. Confirmed the image was actually produced:
   ```
   $ docker images | grep geostudio-appexport-standalone
   geostudio-appexport-standalone:local   f0e6e388ba1f   482MB   120MB
   ```

5. Committed **only** the new Dockerfile, staged explicitly by path (not
   `git add -A`/`.`/`-a`), per the brief's Step 3 instructions and the
   controller's explicit warning about unrelated uncommitted scratch files
   under `.superpowers/sdd/` in this working tree:
   ```
   git add deploy/appexport-standalone/Dockerfile
   git commit -m "feat(deploy): standalone mini-server Docker image (SP-18c)"
   ```
   Commit: `913e906ca9c311dc38fb8d1f6bcbf20c36f5b51e` on branch `dev`.
   `git show --stat HEAD` confirms exactly one file changed:
   ```
   deploy/appexport-standalone/Dockerfile | 44 ++++++++++++++++++++++++++++++++++
   1 file changed, 44 insertions(+)
   ```
   Verified via `git status --porcelain` immediately after `git add` that
   only `deploy/appexport-standalone/Dockerfile` showed as staged (`A`);
   all the pre-existing modified `.superpowers/sdd/*.md` files remained
   unstaged and were untouched by the commit.

## Deviations from the brief

None. The Dockerfile content matches the brief's Step 1 code block
verbatim, and Steps 2 and 3 were followed exactly as written.

## Full `docker build` output

```
#0 building with "default" instance using docker driver

#1 [internal] load build definition from Dockerfile
#1 transferring dockerfile: 2.50kB done
#1 DONE 0.0s

#2 [internal] load metadata for docker.io/library/node:20-slim
#2 DONE 0.9s

#3 [internal] load metadata for docker.io/library/python:3.12-slim
#3 DONE 2.0s

#4 [internal] load .dockerignore
#4 transferring context: 2B done
#4 DONE 0.0s

#5 [stage-1 1/6] FROM docker.io/library/python:3.12-slim@sha256:dd29372629eeba2dd003fd9e9d35a5b8236c44727875a0364254b5127af88e65
#5 resolve docker.io/library/python:3.12-slim@sha256:dd29372629eeba2dd003fd9e9d35a5b8236c44727875a0364254b5127af88e65 0.0s done
#5 DONE 3.1s

#6 [shell-runtime 1/7] FROM docker.io/library/node:20-slim@sha256:2cf067cfed83d5ea958367df9f966191a942351a2df77d6f0193e162b5febfc0
#6 resolve docker.io/library/node:20-slim@sha256:2cf067cfed83d5ea958367df9f966191a942351a2df77d6f0193e162b5febfc0 0.0s done
#6 CACHED

#7 [shell-runtime 2/7] WORKDIR /build
#7 DONE 0.1s

#8 [internal] load build context
#8 transferring context: 225.37MB 5.0s
#8 transferring context: 480.71MB 8.0s done
#8 DONE 8.1s

#9 [stage-1 2/6] WORKDIR /app
#9 DONE 0.5s

#10 [stage-1 3/6] RUN pip install --no-cache-dir fastapi 'uvicorn[standard]' pydantic duckdb sqlalchemy
#10 17.48 Successfully installed annotated-doc-0.0.5 annotated-types-0.8.0 anyio-4.14.2 click-8.4.2 duckdb-1.5.5 fastapi-0.141.1 greenlet-3.5.5 h11-0.16.0 httptools-0.8.0 idna-3.18 pydantic-2.13.4 pydantic-core-2.46.4 python-dotenv-1.2.2 pyyaml-6.0.3 sqlalchemy-2.0.52 starlette-1.6.0 typing-extensions-4.16.0 typing-inspection-0.4.4 uvicorn-0.52.3 uvloop-0.22.1 watchfiles-1.2.0 websockets-17.0.1
#10 17.48 WARNING: Running pip as the 'root' user can result in broken permissions and conflicting behaviour with the system package manager, possibly rendering your system unusable. It is recommended to use a virtual environment instead: https://pip.pypa.io/warnings/venv. Use the --root-user-action option if you know what you are doing and want to suppress this warning.
#10 DONE 18.6s

#11 [shell-runtime 3/7] COPY shell/package.json shell/package-lock.json ./
#11 DONE 0.6s

#12 [shell-runtime 4/7] RUN npm ci
#12 1.475 npm warn EBADENGINE Unsupported engine {
#12 1.475 npm warn EBADENGINE   package: '@mapbox/jsonlint-lines-primitives@2.0.3',
#12 1.475 npm warn EBADENGINE   required: { node: '>= 22' },
#12 1.475 npm warn EBADENGINE   current: { node: 'v20.20.2', npm: '10.8.2' }
#12 1.475 npm warn EBADENGINE }
#12 3.067 npm warn deprecated whatwg-encoding@3.1.1: Use @exodus/bytes instead for a more spec-conformant and faster implementation
#12 19.75 added 534 packages, and audited 535 packages in 19s
#12 19.79 16 vulnerabilities (7 moderate, 9 high)
#12 DONE 19.9s

#13 [stage-1 4/6] RUN python -c "import duckdb; c = duckdb.connect(); c.execute('INSTALL spatial')"
#13 5.143 100% ▕██████████████████████████████████████▏ (00:00:04.66 elapsed)
#13 DONE 5.4s

#14 [stage-1 5/6] COPY core/app ./app
#14 DONE 0.1s

#15 [shell-runtime 5/7] COPY shell/ .
#15 DONE 9.4s

#16 [shell-runtime 6/7] RUN npm run build:export-runtime
#16 0.590 > geostudio-shell@0.1.0 build:export-runtime
#16 0.590 > vite build --config vite.export.config.ts
#16 0.894 vite v6.4.3 building for production...
#16 0.958 transforming...
#16 13.21 ✓ 3918 modules transformed.
#16 14.02 rendering chunks...
#16 14.26 computing gzip size...
#16 14.31 dist-export/index.export.html                    0.43 kB │ gzip:   0.30 kB
#16 14.31 dist-export/assets/index-C3NnytiJ.css           22.01 kB │ gzip:   5.20 kB
#16 14.31 dist-export/assets/MapView-PhPnDjd-.css         65.47 kB │ gzip:   9.22 kB
#16 14.31 dist-export/assets/index.export-DPmQ9Jjs.js    607.47 kB │ gzip: 180.86 kB
#16 14.31 dist-export/assets/EChart-DeAawO0k.js          825.08 kB │ gzip: 277.25 kB
#16 14.31 dist-export/assets/MapView-nSMZL_0T.js       1,871.72 kB │ gzip: 522.18 kB
#16 14.32 (!) Some chunks are larger than 500 kB after minification. Consider:
#16 14.32 - Using dynamic import() to code-split the application
#16 14.32 - Use build.rollupOptions.output.manualChunks to improve chunking: https://rollupjs.org/configuration-options/#output-manualchunks
#16 14.32 - Adjust chunk size limit for this warning via build.chunkSizeWarningLimit.
#16 14.32 ✓ built in 13.39s
#16 DONE 14.5s

#17 [shell-runtime 7/7] RUN mv dist-export/index.export.html dist-export/index.html
#17 DONE 0.6s

#18 [stage-1 6/6] COPY --from=shell-runtime /build/dist-export /runtime
#18 DONE 0.1s

#19 exporting to image
#19 exporting layers 4.1s done
#19 exporting manifest sha256:e1c0dadc6e591c27bab70b45a06e41f602906a81f43d8acd0aa65cbc9c805080 0.0s done
#19 exporting config sha256:1e114deabb5d6e802d9877c145f81326b1f3b3e6a7eeba42535331ee0e59d4b7 0.0s done
#19 exporting attestation manifest sha256:e5f1dd5cb9686a31b673289fabc0e6e5d0f20d1e7b84ecb5ea1f675c8b1fe0cc 0.0s done
#19 exporting manifest list sha256:f0e6e388ba1fa92aff81bb0be426c5a46ad5cad031da2133611c12bbd1ec4b62 0.0s done
#19 naming to docker.io/library/geostudio-appexport-standalone:local done
#19 unpacking to docker.io/library/geostudio-appexport-standalone:local 1.7s done
#19 DONE 5.9s
```

(Full untruncated log saved during the session at
`/tmp/claude-1000/-home-lenen-projets-geostudio/49a68433-b728-410b-b8ce-d2818586d011/scratchpad/task10-build.log`,
240 lines — the above is the complete content minus a handful of
interleaved progress-percentage lines from concurrent build stages that
carry no additional information.)

Warnings present (all non-blocking, pre-existing/expected, no action
taken):
- `npm warn EBADENGINE` for `@mapbox/jsonlint-lines-primitives@2.0.3`
  wanting Node >=22 while the stage uses `node:20-slim` — pre-existing
  shell dependency constraint, not something this Dockerfile controls or
  the brief flagged.
- `npm audit`: 16 vulnerabilities (7 moderate, 9 high) in shell
  dependencies — pre-existing, out of scope for this task.
- Vite chunk-size warning (chunks >500kB) — pre-existing shell build
  characteristic, out of scope.
- `pip install` running as root warning — expected/standard for a
  Docker image build, no virtualenv needed in a container.

None of these are build failures; the build completed successfully both
stages, `exporting to image` succeeded, and the image was tagged
`geostudio-appexport-standalone:local`.

## Confirmation the image was actually built

```
$ docker images | grep geostudio-appexport-standalone
geostudio-appexport-standalone:local   f0e6e388ba1f   482MB   120MB
```

Image present locally, tagged as expected, non-zero size (482MB virtual /
120MB unique layers reported by the human-readable `docker images`
output).

## Commit

```
$ git show --stat HEAD
commit 913e906ca9c311dc38fb8d1f6bcbf20c36f5b51e
Author: Tanguy <lenenaon.tanguy@gmail.com>
Date:   Sat Aug 15 20:01:56 2026 +0200

    feat(deploy): standalone mini-server Docker image (SP-18c)

 deploy/appexport-standalone/Dockerfile | 44 ++++++++++++++++++++++++++++++++++
 1 file changed, 44 insertions(+)
```

Only `deploy/appexport-standalone/Dockerfile` was staged and committed
(verified via `git status --porcelain` right after `git add`, before
`git commit`). The unrelated uncommitted `.superpowers/sdd/*.md` scratch
files noted by the controller remain untouched and unstaged in the
working tree.

## Status: DONE
