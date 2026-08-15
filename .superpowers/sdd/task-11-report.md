# Task 11: publish `geostudio-appexport-standalone` to ghcr.io

## Summary
Successfully modified `.github/workflows/release.yml` to add the 4th image (`geostudio-appexport-standalone`) to the release matrix and added explicit Dockerfile paths to the `docker/build-push-action` step for all 4 matrix entries.

## Changes Made

### Step 1: Matrix Block (Lines 78-92)
Replaced the 3-image matrix with a 4-image matrix, adding the `dockerfile` field to each entry:

**Old matrix** (3 entries):
- geostudio-core: context=./core
- geostudio-shell: context=./shell
- geostudio-postgis: context=./deploy/postgis

**New matrix** (4 entries):
- geostudio-core: context=./core, dockerfile=Dockerfile
- geostudio-shell: context=./shell, dockerfile=Dockerfile
- geostudio-postgis: context=./deploy/postgis, dockerfile=Dockerfile
- geostudio-appexport-standalone: context=., dockerfile=deploy/appexport-standalone/Dockerfile

### Step 2: docker/build-push-action Step (Line 104)
Added the `file:` parameter to resolve the Dockerfile path dynamically from matrix variables:

```yaml
file: ${{ matrix.context }}/${{ matrix.dockerfile }}
```

## YAML Validation
Ran validation command: `python3 -c "import yaml; yaml.safe_load(open('.github/workflows/release.yml'))"`

**Result:** YAML parsing successful ✓

No exceptions encountered. The file is syntactically valid.

## Self-Review: Dockerfile Path Resolution

Verified each of the 4 matrix entries resolves correctly:

1. **geostudio-core**:
   - context=`./core`, dockerfile=`Dockerfile`
   - Resolves to: `./core/Dockerfile` ✓
   - Identical to today's implicit default

2. **geostudio-shell**:
   - context=`./shell`, dockerfile=`Dockerfile`
   - Resolves to: `./shell/Dockerfile` ✓
   - Identical to today's implicit default

3. **geostudio-postgis**:
   - context=`./deploy/postgis`, dockerfile=`Dockerfile`
   - Resolves to: `./deploy/postgis/Dockerfile` ✓
   - Identical to today's implicit default

4. **geostudio-appexport-standalone** (new):
   - context=`.`, dockerfile=`deploy/appexport-standalone/Dockerfile`
   - Resolves to: `./deploy/appexport-standalone/Dockerfile` ✓
   - New image, Dockerfile created in Task 10

## Deviations from Brief
None. All steps followed exactly as specified.

## Commit Details
- **Commit hash:** c496bba
- **Commit message:** `ci(release): publish geostudio-appexport-standalone to ghcr.io (SP-18c)`
- **Files staged:** Only `.github/workflows/release.yml` (`.superpowers/sdd/` files correctly excluded)
- **Branch:** dev

## Notes
- The actual build-and-push path will be exercised the next time a release tag is pushed, per the brief's expectation that this repo has no tag to trigger a real CI run.
- All 3 existing images retain identical Dockerfile paths to their implicit defaults, ensuring no behavioral change for existing builds.
- The new 4th image references the Dockerfile created in Task 10 at `deploy/appexport-standalone/Dockerfile`.
