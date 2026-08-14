# Task 8: Shell types report

## Status: DONE

## Summary

All 4 type edits to `shell/src/api/types.ts` completed successfully. The build now fails in the expected way (missing 4 required ItemClient methods that Task 9 will implement).

## Implementation

Made exactly the 4 edits specified in the brief:

1. **ResourceType** (line 2): Added `"tileset3d"` to the union
2. **LayerSource** (lines 84-93): Added `"tileset3d"` to service union and `"tiles3d"` to kind union
3. **InstanceInfo** (line 35): Added `tileset3dEnabled: boolean` field
4. **ItemClient** (lines 213-227): Added 4 required methods + 1 optional method:
   - `createTileset3DUpload(input: { filename: string; title: string }): Promise<{ jobId: string }>`
   - `presignTileset3DUploadPart(jobId: string, partNumber: number): Promise<{ uploadUrl: string }>`
   - `completeTileset3DUpload(jobId: string, parts: { partNumber: number; etag: string }[]): Promise<void>`
   - `getTileset3DUploadJob(jobId: string): Promise<...>`
   - `getAuthToken?(): string | undefined` (optional)

## Build Verification

**Step 1 (Baseline):** PASS ✓
```
dist/index.html                     0.44 kB │ gzip:   0.28 kB
dist/assets/index-BZ529637.css    103.25 kB │ gzip:  16.53 kB
dist/assets/EChart-B2XkyCBj.js    825.07 kB │ gzip: 276.48 kB
dist/assets/index-Br4m-UiB.js   2,971.88 kB │ gzip: 844.22 kB
✓ built in 14.83s
```

**Step 6 (After edits):** FAIL (Expected) ✓
```
src/api/itemClient.ts(328,3): error TS2739: Type '{ listItems(...); ... }' 
is missing the following properties from type 'ItemClient': 
createTileset3DUpload, presignTileset3DUploadPart, completeTileset3DUpload, 
getTileset3DUploadJob
```

The error confirms the 4 required methods are missing from `itemClient.ts`'s implementation, which is exactly what the brief expects. Task 9 will implement these methods and restore a green build.

## Commit

- **Commit:** `09bcce1` — `feat(shell): types for hosted tileset3d items and upload client`
- **File changed:** `shell/src/api/types.ts` (+16 lines, -4 lines)

## Self-Review

✓ Completeness: All 4 edits made exactly as specified
✓ Quality: Types match brief verbatim (exact union members, optional/required markers)
✓ Discipline: Only `types.ts` edited, no extra fields or changes outside the brief
✓ Build check: Failure message correctly names all 4 required ItemClient methods as missing
✓ No concerns

## Notes

- `getAuthToken` is optional and does not appear in the build error (correct behavior)
- The build failure is the intended sequencing; Task 9 implements the missing methods
- No changes to any other files; no modifications to test files or documentation
