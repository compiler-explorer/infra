## CEFS "Compiler Explorer FileSystem"

#### State as of August 2025

CE has a ton of mostly immutable compilers, libraries and tools on NFS. Latency is high on NFS and caching only gets us so far. We install to NFS, but then create SquashFS images, one per compiler/library/whatever in an offline process. The resulting image is written to `/efs/squash-images/path/to/compiler.sqfs`. At boot we statically mount all compilers using `find | xargs mount` (effectively). This takes ages and eats up a decent amount of RAM.

We do this as the access times via the cacheable, compressed SquashFS images are much faster, so including things like boost etc becomes viable (though we've moved to using a different approach for boost post 1.84). We don't want to lose this nice ability, but a minute or two of startup is painful.

We've tried [many](https://github.com/compiler-explorer/cefs) [different](https://github.com/compiler-explorer/infra/pull/798) [approaches](https://github.com/compiler-explorer/infra/pull/1741) to improve this but all hit issues.

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

**Re-consolidation of Sparse Consolidated Images**: As items are updated/reinstalled, consolidated images may become sparse (e.g., if we consolidate X, Y, Z but later Y and Z are reinstalled individually, the consolidated image only serves X). The manifest system enables detecting such cases and re-consolidating remaining items to maintain efficiency. This ties into the garbage collection process as the old consolidated image would need cleanup after re-consolidation.
