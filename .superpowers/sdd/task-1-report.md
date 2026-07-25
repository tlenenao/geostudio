# Task 1 Report: install.sh — mode non-interactif par variables d'environnement

## Summary

Successfully modified `scripts/install.sh` to support non-interactive mode via environment variables while maintaining full backward compatibility with interactive mode. All 4 functions modified as specified in task-1-brief.md.

## Implementation Details

### Functions Modified

1. **`prompt_profiles` (lines 113-165)**
   - Added support for `INSTALL_PROFILES` environment variable (comma-separated profile list)
   - Added support for `INSTALL_SEED_DEMO` environment variable (value "1" to enable)
   - Both use `${VAR+x}` syntax to distinguish "not provided" from "provided empty"
   - Interactive else branch identical to original: `confirm` calls + `SELECTED_PROFILES` array

2. **`prompt_public_host` (lines 187-236)**
   - Added support for `GEOSTUDIO_PUBLIC_HOST` environment variable
   - Uses `${VAR+x}` syntax; supports both set-with-value and set-empty cases
   - Interactive else branch: exact same `read -r -p` as original
   - Rest of function unchanged, already consuming `PUBLIC_HOST_INPUT` correctly

3. **`prompt_backup_target` (lines 246-276)**
   - Added support for `BACKUP_S3_ENDPOINT`, `BACKUP_S3_ACCESS_KEY`, `BACKUP_S3_SECRET_KEY`, `BACKUP_S3_BUCKET`
   - Uses `${VAR+x}` syntax with `${VAR:-}` fallbacks for optional keys
   - Refactored to declare local variables upfront for clarity
   - Interactive else branch: exact same read sequence as original (endpoint, access key, secret key, bucket)
   - `set_env_var` calls moved outside if/else to apply in both cases (correct)

4. **`prompt_admin` (lines 281-289)**
   - Added support for `INSTALL_ADMIN_EMAIL` environment variable
   - Uses `-n` test (non-empty required), not `+x` — email is mandatory field
   - ADMIN_EMAIL remains global variable (not `local`), as required
   - Interactive else branch: exact same `read -r -p` as original

## Verification Results

### Step 5: Bash Syntax Check
```bash
bash -n scripts/install.sh
```
**Result:** ✓ No output, exit code 0 (success)

### Step 6: Shellcheck Verification
```bash
docker run --rm --user "$(id -u):$(id -g)" -v "$PWD":/mnt -w /mnt \
  koalaman/shellcheck:stable scripts/install.sh
```
**Result:** ✓ No output (no new warnings introduced)

### Step 7: Manual Non-Regression Review

All 4 modified functions verified:

- **`prompt_profiles` else branch** (lines 140-148): Exact copy of original interactive loop + confirm logic
- **`prompt_profiles` demo section** (line 162): Original `confirm` call preserved in elif clause
- **`prompt_public_host` else branch** (line 197): Exact same `read -r -p` as original
- **`prompt_backup_target` else branch** (lines 256-263): All 4 read calls identical to original sequence
- **`prompt_admin` else branch** (line 287): Exact same `read -r -p` as original

**Conclusion:** All else branches reproduce original interactive behavior exactly. ✓

## Files Changed

- `scripts/install.sh`: 62 insertions, 16 deletions (net +46 lines)
  - No lines removed from interactive paths
  - Environment variable checks added using idiomatic bash patterns

## Commit

```
1e552bb feat(deploy): install.sh — mode non-interactif par variables d'environnement (SP-Deploy-e)
```

## Self-Review Findings

✓ All 4 replacements applied exactly as specified in brief
✓ No accidental edits beyond the 4 functions
✓ Bash syntax valid
✓ No new shellcheck warnings introduced
✓ Non-regression: all else branches preserve original behavior
✓ Commit message exact match to brief specification
✓ Variable naming conventions consistent with brief (INSTALL_*, GEOSTUDIO_*, BACKUP_*)
✓ Test syntax correct: `${VAR+x}` for presence test, `-n` for mandatory fields

## Issues/Concerns

None. Task completed successfully with all verification steps passing.
