## CEFS "Compiler Explorer FileSystem"

#### State as of August 2025

CE has a ton of mostly immutable compilers, libraries and tools on NFS. Latency is high on NFS and caching only gets us so far. We install to NFS, but then create SquashFS images, one per compiler/library/whatever in an offline process. The resulting image is written to `/efs/squash-images/path/to/compiler.sqfs`. At boot we statically mount all compilers using `find | xargs mount` (effectively). This takes ages and eats up a decent amount of RAM.

We do this as the access times via the cacheable, compressed SquashFS images are much faster, so including things like boost etc becomes viable (though we've moved to using a different approach for boost post 1.84). We don't want to lose this nice ability, but a minute or two of startup is painful.

We've tried [many](https://github.com/compiler-explorer/cefs) [different](https://github.com/compiler-explorer/infra/pull/798) [approaches](https://github.com/compiler-explorer/infra/pull/1741) to improve this but all hit issues.

XXX TODO
- should we pony up and go 2-3 level fs in autofs before we make any decisions
- "unpack" command to let us make ad hoc changes (unpack squashfs; replace symlink with contents)

## CEFS v2 Approach

Short version - symlink dirs from NFS to `/cefs/HASH`

- Use autofs exactly as [planned for the first cefs attempt](https://github.com/compiler-explorer/infra/pull/798) (already installed in all clusters)
- Drop the complex "root file system" part (which had issues with simultaneous changes to the filesystem)
- Symlink directories from `/opt/compiler-explorer/...` on NFS directly to `/cefs/HASH`

## Autofs Configuration

Autofs automatically mounts squashfs images on demand:

```
# /etc/auto.cefs
* -fstype=squashfs,loop,nosuid,nodev,ro :/efs/cefs-images/&.sqfs

# /etc/auto.master.d/cefs.autofs
/cefs /etc/auto.cefs --negative-timeout 1
```

First access to `/cefs/HASH` triggers mount of `/efs/cefs-images/HASH.sqfs`.

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
- [x] Simple config loader
- [x] Write "port" code to move existing images over
- [x] Update installers to (optionally, based on config) install this way (even works for nightly)
- [x] CLI commands for setup, conversion, and rollback
- [ ] Disable squashing and enable the cefs install
- [ ] Test with a single compiler or library
- [ ] Slowly move older things over
- [ ] Write consolidation tooling and run it

## Implementation Notes

#### CLI Commands

- `ce cefs setup` - Configure autofs for local testing (replicates production setup_cefs())
- `ce cefs convert FILTER` - Convert existing squashfs images to CEFS with hash-based storage
- `ce cefs rollback FILTER` - Undo conversions by restoring from .bak directories
- `ce cefs status` - Show current configuration

#### Migration Process

1. Hash existing squashfs image and copy to `/efs/cefs-images/${HASH}.sqfs`
2. Backup NFS directory and create symlink to `/cefs/${HASH}`
3. First access triggers autofs mount of the CEFS image

This is implemented in the `ce cefs convert`.

#### Migration Strategy

- Start with least-used compilers (gcc-4.x, deprecated versions)
- Monitor logs for errors after migration
- Remove `.bak` directories after validation

Once a few of these have been done and we're happy with the results, we set the `/opt/compiler-explorer/config.yaml` to start installing the new way.

## Future Work

**Consolidation**: Combine multiple individual squashfs images into consolidated images with subdirectories to reduce mount overhead while maintaining content-addressable benefits.
