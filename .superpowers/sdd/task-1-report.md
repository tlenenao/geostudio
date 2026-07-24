# Task 1 Report: SP-Deploy-c — Squelette + Détection/Installation des Prérequis Docker

## Summary
Task 1 of SP-Deploy-c completed successfully. The install script skeleton was created with Docker detection and interactive confirmation utilities that will be reused by Tasks 2, 3, and 4 in this SP.

## What Was Implemented

### File Created: `scripts/install.sh`
- **SPDX-License-Identifier**: Apache-2.0 header as required by brief
- **Skeleton**: `set -euo pipefail`, changes to repo root via `"$(dirname "$0")/.."`, defines `COMPOSE` variable for reuse
- **confirm() function**: Interactive y/N confirmation with automatic `yes` when `INSTALL_YES=1` (non-interactive mode for automation)
- **ensure_docker() function**: Detects Docker + Docker Compose v2, handles platform-specific installation guidance (Linux via get.docker.com, macOS manual steps, other OS guidance)
- **Entry point**: Calls `ensure_docker()` at script end
- **Total lines**: 58 (fits on single page for review)

### Code Structure
Exactly as specified in brief:
- Container for confirmation logic with INSTALL_YES override
- Docker detection via `command -v docker` and `docker compose version` (the correct check for Compose v2 plugin)
- Graceful handling of three cases: detected, Linux install available, macOS/other unsupported
- User-facing messages in French, identifiers/functions in English per project rules

## Testing

### Test Location
Test executed in **throwaway clone** as required (not in working repo):
- `git clone` to `/tmp/geostudio-install-test`
- Script made executable
- Run in isolated environment

### Nominal Case Test Results
**Expected behavior**: Docker already installed (environment has Docker Compose v5.1.3)

**Actual output**:
```
═══ GeoStudio — installeur guidé ═══
✓ Docker + Docker Compose détectés (5.1.3).
```

**Verification**:
- Header printed correctly
- Docker and Compose v2 plugin detected
- Version string extracted and displayed correctly
- Script exited cleanly (exit code 0)
- No subsequent code executed (Task 2 will add more logic after this point)

### Test Cleanup
- Throwaway clone removed: `rm -rf /tmp/geostudio-install-test`
- No modifications to working repo during testing

## Files Changed

### Created
- `scripts/install.sh` (58 lines)

### Commit Details
- **SHA**: 42f8900
- **Message**: `feat(deploy): installeur guidé — squelette + détection Docker`
- **Date**: 2026-07-24

## Self-Review Findings

### Completeness
- [x] Step 1: Skeleton + helpers implemented exactly as specified
- [x] Step 2: ensure_docker() function implemented exactly as specified
- [x] Step 3: Nominal case verified in throwaway clone (Docker already present)
- [x] Step 4: Committed with exact message from brief

### Code Quality
- Script header follows SPDX requirement
- `set -euo pipefail` prevents silent failures
- Proper quoting throughout (safe with spaces/special chars)
- confirm() correctly implements INSTALL_YES=1 override for CI/automation
- Functions designed for reuse (will be called by Tasks 2, 3, 4)
- No hardcoded paths outside scope of Task 1

### Discipline
- No scope creep (no menu, Q&A, or launch logic added)
- No stubs for future tasks (lean implementation)
- Follows brief's exact wording for user-facing messages
- Global Constraints met: confirmation before actions, no silent installs

### Verification Quality
- Test executed in throwaway directory (not in real repo, preventing accidental damage)
- Test covered nominal path (Docker already present) with real output shown
- Cleanup performed properly on test clone

## Issues or Concerns
None. Task completed as specified.

**Script is ready for Task 2 and subsequent tasks to append additional functions to `scripts/install.sh`.**

---

## Review Fixes Applied (2026-07-24 - Later Session)

Two findings from code review were fixed and verified:

### Finding 1: Missing Executable Bit

**Status**: FIXED

- **Original state**: File committed as mode 100644 (non-executable)
- **Fix applied**: `chmod +x scripts/install.sh && git add scripts/install.sh`
- **Verification**: `git ls-files -s` shows `100755` after staging; commit diff confirms mode change from 100644 to 100755
- **Impact**: Users can now run `./scripts/install.sh` directly without manual `chmod +x`

### Finding 2: Incomplete Confirmation Message

**Status**: FIXED

- **Original state**: Confirmation prompt only mentioned "Installer Docker maintenant via le script officiel get.docker.com ?" but the `confirm()` call gates BOTH the Docker installation (curl get.docker.com) AND `sudo usermod -aG docker "$USER"` (system group modification)
- **Fix applied**: Updated line 35 message to: "Installer Docker via le script officiel et ajouter l'utilisateur au groupe docker ?"
- **Verification**: Grep confirms both actions are now explicitly disclosed in the single confirm prompt (line 35)
- **Compliance**: Aligns with spec §5.1 requirement that "any action that installs a package or modifies system groups must be preceded by an explicit message"

### Verification Tests

1. **Syntax check**: `bash -n scripts/install.sh` ✓ Pass
2. **Nominal execution**: Script runs and correctly detects Docker 5.1.3, exits cleanly with code 0 ✓ Pass
3. **Message text**: Grep confirms message now discloses both actions (install + group membership) ✓ Pass
4. **Cleanup**: Test clone removed ✓ Pass

### Commit Details

- **SHA**: 2d18792
- **Message**: `fix(deploy): installeur — bit exécutable + confirmation explicite usermod (revue Task 1)`
- **Changes**: 
  - Mode change: 100644 → 100755 (executable bit)
  - Content change: Line 35 confirmation message updated

---

**Date**: 2026-07-24  
**Status**: DONE
