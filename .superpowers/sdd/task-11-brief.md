### Task 11: publish `geostudio-appexport-standalone` to ghcr.io

**Files:**
- Modify: `.github/workflows/release.yml`

**Interfaces:**
- Produces: on a `v*.*.*` tag push, `release.yml`'s `build-and-push` job
  also builds and pushes `ghcr.io/tlenenao/geostudio-appexport-standalone`.

- [ ] **Step 1: Add `dockerfile` to every matrix entry and add the 4th image**

In `.github/workflows/release.yml`, replace:

```yaml
      matrix:
        include:
          - image: geostudio-core
            context: ./core
          - image: geostudio-shell
            context: ./shell
          - image: geostudio-postgis
            context: ./deploy/postgis
```

with:

```yaml
      matrix:
        include:
          - image: geostudio-core
            context: ./core
            dockerfile: Dockerfile
          - image: geostudio-shell
            context: ./shell
            dockerfile: Dockerfile
          - image: geostudio-postgis
            context: ./deploy/postgis
            dockerfile: Dockerfile
          - image: geostudio-appexport-standalone
            context: .
            dockerfile: deploy/appexport-standalone/Dockerfile
```

- [ ] **Step 2: Pass the resolved Dockerfile path to `docker/build-push-action`**

In the same file, replace:

```yaml
      - uses: docker/build-push-action@v6
        with:
          context: ${{ matrix.context }}
          push: true
          tags: |
            ghcr.io/tlenenao/${{ matrix.image }}:${{ github.ref_name }}
            ghcr.io/tlenenao/${{ matrix.image }}:latest
```

with:

```yaml
      - uses: docker/build-push-action@v6
        with:
          context: ${{ matrix.context }}
          file: ${{ matrix.context }}/${{ matrix.dockerfile }}
          push: true
          tags: |
            ghcr.io/tlenenao/${{ matrix.image }}:${{ github.ref_name }}
            ghcr.io/tlenenao/${{ matrix.image }}:latest
```

(For `geostudio-core`: `context=./core` + `dockerfile=Dockerfile` →
`file=./core/Dockerfile`, identical to today's implicit default. For the
new image: `context=.` + `dockerfile=deploy/appexport-standalone/Dockerfile`
→ `file=./deploy/appexport-standalone/Dockerfile`.)

- [ ] **Step 3: Validate the workflow YAML parses**

Run: `python3 -c "import yaml; yaml.safe_load(open('.github/workflows/release.yml'))"`
Expected: no exception. (This repo has no tag to push and trigger a real
run — parsing is the only automated check available here; the actual
build-and-push path is exercised for real the next time Tanguy cuts a
release, same gap already documented for `geostudio-core`/`shell`/`postgis`.)

- [ ] **Step 4: Commit**

```bash
git add .github/workflows/release.yml
git commit -m "ci(release): publish geostudio-appexport-standalone to ghcr.io (SP-18c)"
```

---

