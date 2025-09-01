## CEFS "Compiler Explorer FileSystem"

#### State as of August 2025

CE has a ton of mostly immutable compilers, libraries and tools on NFS. Latency is high on NFS and caching only gets us so far. We install to NFS, but then create SquashFS images, one per compiler/library/whatever in an offline process. The resulting image is written to `/efs/squash-images/path/to/compiler.sqfs`. At boot we statically mount all compilers using `find | xargs mount` (effectively). This takes ages and eats up a decent amount of RAM.

We do this as the access times via the cacheable, compressed SquashFS images are much faster, so including things like boost etc becomes viable (though we've moved to using a different approach for boost post 1.84). We don't want to lose this nice ability, but a minute or two of startup is painful.

We've tried [many](https://github.com/compiler-explorer/cefs) [different](https://github.com/compiler-explorer/infra/pull/798) [approaches](https://github.com/compiler-explorer/infra/pull/1741) to improve this but all hit issues.

## System Constraints and Assumptions

**CRITICAL**: These constraints fundamentally shape the CEFS design and safety mechanisms.

### Multi-Machine NFS Environment
- **Constraint**: Multiple EC2 instances share the same NFS filesystem (`/opt/compiler-explorer/` and `/efs/`)
- **Implication**: Any instance can read/write/delete files at any time
- **Design Impact**: Cannot use file locking (NFS locking is unreliable and not available)
- **Solution**: Use atomic operations and careful ordering of operations

### No Distributed Locking
- **Constraint**: No distributed locking mechanism available (no Redis, no DynamoDB locks, etc.)
- **Implication**: Cannot prevent concurrent operations on the same resources
- **Design Impact**: Must be safe even if multiple machines run GC, install, or convert simultaneously
- **Solution**: Idempotent operations, atomic renames, and marker files (`.yaml.inprogress`)

### Atomic Operations Available
- **Available**:
  - File creation is atomic (O_CREAT | O_EXCL)
  - Rename within same filesystem is atomic
  - Symlink creation is atomic
- **Not Atomic**:
  - Multi-step operations (copy + write manifest + create symlink)
  - Reading directory + making decisions based on contents
- **Design Impact**: Use rename for state transitions, use marker files for incomplete operations

### Content-Addressable Storage
- **Assumption**: Files with same hash have identical contents
- **Implication**: Safe to skip copying if file with same hash already exists
- **Risk**: Hash collision would cause wrong content to be served
- **Mitigation**: Use SHA256 (collision probability negligible)

### Autofs Behavior
- **Assumption**: Autofs will mount images on first access to `/cefs/XX/HASH`
- **Implication**: Can have "dangling" symlinks that work when accessed
- **Risk**: Autofs failure would make symlinks broken
- **Mitigation**: Test autofs is working in `ce cefs setup`

### Rollback Mechanism
- **Implementation**: `.bak` symlinks created during installation/conversion
- **Assumption**: Users rely on `.bak` for rollback via `ce cefs rollback`
- **Implication**: GC must NEVER delete images referenced by `.bak` symlinks
- **Design Impact**: Always check both main and `.bak` symlinks

### Eventually Consistent Operations
- **Reality**: Between writing image and creating symlink, system is inconsistent
- **Risk**: GC during this window could delete in-use image
- **Solution**: `.yaml.inprogress` pattern - mark operation incomplete until symlink exists
- **Cleanup**: Orphaned `.yaml.inprogress` files indicate failed operations (require manual review)

## CEFS v2 Approach

Short version - symlink dirs from NFS to `/cefs/HASH`

- Use autofs exactly as [planned for the first cefs attempt](https://github.com/compiler-explorer/infra/pull/798) (already installed in all clusters)
- Drop the complex "root file system" part (which had issues with simultaneous changes to the filesystem)
- Symlink directories from `/opt/compiler-explorer/...` on NFS directly to `/cefs/XX/XXYYZZZ..._descriptive_suffix` (where `XXYYZZZ...` is a 24-character hash, as described below)
- For every squashfs image, keep a manifest explaining what it is and how it was created

## Autofs Configuration

Autofs automatically mounts squashfs images on demand:

```
# /etc/auto.cefs (first-level: handles /cefs/XX -> nested autofs)
* -fstype=autofs program:/etc/auto.cefs.sub

# /etc/auto.cefs.sub (executable script: handles /cefs/XX/HASH -> squashfs mount)
#!/bin/bash
key="$1"
subdir="${key:0:2}"
echo "-fstype=squashfs,loop,nosuid,nodev,ro :/efs/cefs-images/${subdir}/${key}.sqfs"

# /etc/auto.master.d/cefs.autofs
/cefs /etc/auto.cefs --negative-timeout 1
```

CEFS uses a hierarchical directory structure to avoid filesystem performance issues with thousands of files in a single directory. Hash-based paths are structured as `/cefs/XX/XXYYZZZ...` where XX is the first two characters of the SHA256 hash. This provides up to 256 subdirectories (00-ff for hexadecimal hashes), distributing files evenly across the filesystem.

The two-level autofs configuration works as follows:
1. First access to `/cefs/XX` creates a nested autofs mount using the executable script `/etc/auto.cefs.sub`
2. Second access to `/cefs/XX/XXYYZZZ` calls the script with the hash as argument
3. The script extracts the first two characters from the hash and returns mount options for `/efs/cefs-images/XX/XXYYZZZ.sqfs`
4. Autofs mounts the squashfs image at the requested location

## mount-all-img.sh Integration

Currently `mount-all-img.sh` globs all `*.img` files in `/efs/squash-images/` and unconditionally mounts them over `/opt/compiler-explorer/...` paths.

The modified script now skips mounting when the destination is already a symlink, allowing gradual migration without breaking existing mounts.

## Work

- [x] Investigate what I've forgotten about getting this to work
  - [x] Update builder to 22.04 and cefs support
  - [x] Runner too
- [x] "Squash verify" to check current squash images are in fact "correct"
  - [x] in progress
  - [x] fix up anything found that mismatches
- [x] Update `mount-all-img.sh` to do the Right Thing, test it, and rebuild and deploy all the AMIs
  - [x] make the change in main
  - [x] build and deploy staging
  - [x] build and deploy prod
  - [x] build and deploy gpu
  - [x] build and deploy aarch64staging
  - [x] build and deploy aarch64prod
  - [x] build beta
- [ ] Fix up automounter/general config
  - [x] fix in main
  - [x] install in admin
  - [x] staging, beta, prod script update and AMI
  - [x] aarch64 ditto
  - [x] gpu ditto
  - [x] windows rebuild just to pick up the other changes
  - [x] builder
  - [x] runner
  - [ ] ce-ci too?
- [x] Simple config loader
- [x] Write "port" code to move existing images over
- [x] Update installers to (optionally, based on config) install this way (even works for nightly)
- [x] CLI commands for setup, conversion, and rollback
- [x] Test with a single compiler or library
- [ ] Disable squashing and enable the cefs install
- [ ] Slowly move older things over
- [ ] Write consolidation tooling and run it
- [ ] Write an `unpack` tool that lets us unpack a mountpoint and replace the symlink with the "real" data for patching.

## Implementation Notes

#### CLI Commands

- `ce cefs setup` - Configure autofs for local testing (replicates production setup_cefs())
- `ce cefs convert FILTER` - Convert existing squashfs images to CEFS with hash-based storage
- `ce cefs rollback FILTER` - Undo conversions by restoring from .bak directories
- `ce cefs status` - Show current configuration

#### Migration Process

1. Hash existing squashfs image and copy to `/efs/cefs-images/${HASH:0:2}/${HASH}.sqfs`
2. Backup NFS directory and create symlink to `/cefs/${HASH:0:2}/${HASH}`
3. First access triggers autofs mount of the CEFS image

This is implemented in the `ce cefs convert`.

#### Migration Strategy

- Start with least-used compilers (gcc-4.x, deprecated versions)
- Monitor logs for errors after migration
- Remove `.bak` directories after validation

Once a few of these have been done and we're happy with the results, we set the `/opt/compiler-explorer/config.yaml` to start installing the new way.

## Future Work

**Consolidation**: Combine multiple individual squashfs images into consolidated images with subdirectories to reduce mount overhead while maintaining content-addressable benefits.

**Manifest System**: All CEFS images have a YAML manifest containing:
- List of all installables with their full name and destination paths
- Git SHA of the producing `ce_install`
- Command-line that created the image
- Human-readable description
- Operation type (install/convert/consolidate)
- Creation timestamp

Each installable entry in the manifest contains:
- `name`: Full installable name including version (e.g., "compilers/c++/x86/gcc 10.1.0")
- `destination`: Installation path (e.g., "/opt/compiler-explorer/gcc-10.1.0")

The manifest enables robust garbage collection by checking if symlinks at each destination still point back to the image. Manifests are written alongside the `.sqfs` file for easy access without mounting.

**Image Structure**:
- **New installations**: Symlinks point directly to `/cefs/HASH`.
- **Conversions**: Manifest is written alongside the image file.
- **Consolidations**: Subdirectories for each consolidated item. Symlinks point to `/cefs/HASH/subdir_name`.

**Improved Naming Convention**: CEFS images use a 24 hexadecimal character (96 bits) hash plus descriptive suffix format:
- `HASH24_consolidated.sqfs` - for consolidated images
- `HASH24_converted_path_to_img.sqfs` - for conversions (path components joined with underscores)
- `HASH24_path_to_root.sqfs` - for regular installs (destination path components joined with underscores)

Examples:
- `9da642f654bc890a12345678_libs_fusedkernellibrary_Beta-0.1.9.sqfs`
- `abcdef1234567890abcdef12_consolidated.sqfs`
- `123456789abcdef012345678_converted_arm_gcc-10.2.0.sqfs`

**Garbage Collection**: Implement automated cleanup of unused CEFS images using the manifest system. The process:
1. Read `manifest.yaml` from each image directory
2. For each destination in the manifest contents, check if the symlink points back to this image
3. If no symlinks reference the image, it can be safely removed
4. The manifest provides full traceability for debugging and validation

### Garbage Collection Algorithm

#### Design Principles

1. **Manifest-Based Discovery**: Use manifest files to determine where symlinks *should* exist, rather than scanning entire filesystem
   - **Rationale**: Scanning 3.8M+ files is expensive and slow
   - **Trade-off**: Only works for images with manifests (newer images)
   - **Fallback**: For images without manifests, scan common locations

2. **Conservative Deletion**: When in doubt, keep the image
   - **Rationale**: Storage is cheap, data loss is expensive
   - **Implementation**: Multiple safety checks before deletion

3. **No Assumptions About Exclusivity**: GC can run on multiple machines simultaneously
   - **Rationale**: No way to prevent concurrent execution
   - **Implementation**: Operations must be safe even if racing with other GC instances

#### Algorithm Steps

1. **Discovery Phase**:
   - Scan `/efs/cefs-images/` for all `.sqfs` files
   - For each image, check for `.yaml` manifest (complete) or `.yaml.inprogress` (incomplete)
   - Read manifests to determine expected symlink locations

2. **Reference Checking Phase**:
   - For each image with manifest: check if expected symlinks exist and point to this image
   - For each image without manifest: scan common locations for any symlinks
   - **CRITICAL**: Always check both main path and `.bak` path

3. **Filtering Phase**:
   - Skip images with `.yaml.inprogress` (never delete incomplete operations)
   - Skip images newer than `--min-age` threshold
   - Skip images that have valid references

4. **Deletion Phase**:
   - Double-check each image is still unreferenced (guard against concurrent operations)
   - Delete image file
   - Delete manifest file if it exists

### Garbage Collection Safety Requirements

**Critical**: The GC implementation must handle concurrent operations safely in a multi-machine NFS environment without file locking.

#### Race Condition Prevention

To prevent deletion of in-progress installations, the system uses `.yaml.inprogress` markers:

1. **Installation/Conversion Order**:
   - Create and copy squashfs image to `/efs/cefs-images/`
   - Write `manifest.yaml.inprogress` (operation incomplete)
   - Create symlink(s) in `/opt/compiler-explorer/`
   - Atomically rename `.yaml.inprogress` → `.yaml` (operation complete)

2. **Consolidation Order**:
   - Create consolidated image with subdirectories
   - Write `manifest.yaml.inprogress`
   - Update ALL symlinks one by one
   - Only after all succeed: rename `.yaml.inprogress` → `.yaml`

3. **GC Behavior**:
   - ONLY process images with `.yaml` files (proven complete)
   - NEVER delete images with `.yaml.inprogress` (in-progress or failed)
   - Report `.yaml.inprogress` files for manual investigation

#### Backup Protection

**Critical**: GC must protect `.bak` symlinks to preserve rollback capability.

When checking if an image is referenced:
1. Check the primary destination from the manifest
2. **Always** also check the `.bak` version of that destination
3. Image is considered referenced if either symlink points to it

Example: After `ce install gcc-15`, we have:
- `/opt/compiler-explorer/gcc-15` → `/cefs/aa/new_hash` (new)
- `/opt/compiler-explorer/gcc-15.bak` → `/cefs/bb/old_hash` (backup)

Both `new_hash` and `old_hash` images must be preserved.

#### Additional Safety Measures

1. **Age Threshold**: Add `--min-age` option (default 1 hour) to skip recently created images
2. **Double-Check**: Re-verify images are unreferenced immediately before deletion
3. **Manual Investigation**: Provide tools to analyze `.yaml.inprogress` files:
   - Show age of incomplete operations
   - Compare expected vs actual symlinks
   - Suggest remediation actions

#### Handling Failed Operations

Images with `.yaml.inprogress` markers indicate incomplete or failed operations:
- **DO NOT** auto-delete these images (may be partially in use)
- For consolidations: Some symlinks may already point to the image
- Require manual investigation and decision
- Future tool: `ce cefs check-failed` to analyze and remediate

**Re-consolidation of Sparse Consolidated Images**: As items are updated/reinstalled, consolidated images may become sparse (e.g., if we consolidate X, Y, Z but later Y and Z are reinstalled individually, the consolidated image only serves X). The manifest system enables detecting such cases and re-consolidating remaining items to maintain efficiency. This ties into the garbage collection process as the old consolidated image would need cleanup after re-consolidation.

### Edge Cases and Failure Scenarios

#### What if GC runs during installation?
- **Scenario**: Instance A is installing gcc-15 while Instance B runs GC
- **Timeline**:
  1. A: Copies image to `/efs/cefs-images/`
  2. A: Writes `.yaml.inprogress`
  3. B: GC scans and finds image with `.yaml.inprogress`
  4. B: Skips image (never deletes `.yaml.inprogress`)
  5. A: Creates symlink
  6. A: Renames `.yaml.inprogress` → `.yaml`
- **Result**: Image protected throughout installation

#### What if installation fails after creating image?
- **Scenario**: Installation crashes after copying image but before creating symlink
- **State**: Image exists with `.yaml.inprogress` but no symlink
- **GC Behavior**: Will never delete (has `.yaml.inprogress`)
- **Resolution**: Manual cleanup required (intentional - failed operations need investigation)

#### What if two GCs run simultaneously?
- **Scenario**: Instance A and B both run `ce cefs gc` at same time
- **Behavior**:
  - Both scan same images
  - Both check same symlinks
  - Both identify same unreferenced images
  - Both try to delete same files
- **Result**: One succeeds, other gets "file not found" (harmless)
- **Safety**: Double-check before deletion prevents race conditions

#### What if symlink is created during GC?
- **Scenario**: GC identifies image as unreferenced, then user installs something using that image
- **Protection 1**: `--min-age` prevents deletion of recent images (default 1 hour)
- **Protection 2**: Double-check immediately before deletion
- **Timeline**:
  1. GC: Identifies image X as unreferenced
  2. User: Creates symlink to image X
  3. GC: Double-checks image X
  4. GC: Finds new symlink, skips deletion
- **Result**: Image protected

#### What if rollback happens during GC?
- **Scenario**: User runs `ce cefs rollback` while GC is running
- **Behavior**:
  - Rollback swaps `.bak` symlink with main symlink
  - GC always checks both main and `.bak`
  - Both old and new images remain protected
- **Result**: Safe - both images preserved

#### What if manifest is corrupted?
- **Scenario**: Manifest file exists but contains invalid YAML or missing fields
- **Behavior**:
  - Warning logged
  - Image treated as having no manifest
  - Falls back to filesystem scanning
- **Result**: Conservative - image only deleted if no symlinks found anywhere

#### What if NFS has split-brain?
- **Scenario**: Network partition causes different instances to see different NFS state
- **Reality**: This would break everything, not just GC
- **Mitigation**: AWS EFS has strong consistency guarantees
- **Design**: Even with inconsistency, operations remain safe (might keep extra images)

### Safety Review Summary

#### Key Safety Principles
- **Conservative deletion**: When in doubt, keep the image
- **Multiple protection layers**: No single point of failure
- **No assumptions about exclusivity**: Safe even with concurrent operations
- **Failed operations require human review**: Not automatic cleanup

#### Protection Mechanisms and Their Tests
1. **`.bak` symlink protection**
   - Code: `_check_symlink_points_to_image()` always checks both main and `.bak`
   - Test: `test_check_symlink_protects_bak()`
   - Purpose: Preserves rollback capability

2. **`.yaml.inprogress` pattern**
   - Code: `scan_cefs_images_with_manifests()` skips incomplete operations
   - Test: `test_scan_with_inprogress_files()`
   - Purpose: Prevents deletion during installation/conversion

3. **Age filtering**
   - Code: `--min-age` option (default 1 hour)
   - Purpose: Additional safety margin for recent operations

4. **Double-check verification**
   - Code: Re-verify each image before deletion (lines 851-872 in cli/cefs.py)
   - Purpose: Guard against races between scan and deletion

#### Why Not Use File Locking?
- NFS file locking is unreliable and not available in our environment
- Would require distributed lock service (adds complexity/failure modes)
- Our solution: Order of operations + atomic operations + marker files

#### Monitoring and Manual Intervention
The GC provides detailed logging for troubleshooting:
- Reports `.yaml.inprogress` files with age
- Shows images skipped due to age threshold
- Logs double-check saves

Manual intervention required for:
- `.yaml.inprogress` files older than expected (investigate failed operations)
- Consistently growing image count (review if GC is too conservative)
- Disk space concerns (can reduce `--min-age` if needed)
