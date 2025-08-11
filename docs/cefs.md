## CEFS "Compiler Explorer FileSystem"

#### State as of August 2025

CE has a ton of mostly immutable compilers, libraries and tools on NFS. Latency is high on NFS and caching only gets us so far. We install to NFS, but then create SquashFS images, one per compiler/library/whatever in an offline process. The resulting image is written to `/efs/squash-images/path/to/compiler.sqfs`. At boot we statically mount all compilers using `find | xargs mount` (effectively). This takes ages and eats up a decent amount of RAM.

We do this as the access times via the cacheable, compressed SquashFS images are much faster, so including things like boost etc becomes viable (though we've moved to using a different approach for boost post 1.84). We don't want to lose this nice ability, but a minute or two of startup is painful.

We've tried [many](https://github.com/compiler-explorer/cefs) [different](https://github.com/compiler-explorer/infra/pull/798) [approaches](https://github.com/compiler-explorer/infra/pull/1741) to improve this but all hit issues.

## This time

Short version - symlink dirs from NFS to `/cefs/HASH`

- Use autofs exactly as planned for the first cefs attempt (it's already installed in all clusters including the `runner` node (but NOT `builder` yet))
- Drop the complex "root file system" part (which had issues with simultaneous changes to the filesystem, and general admin ease of "just make changes on NFS")
- Symlink directories from `/opt/compiler-explorer/...` on NFS directly to `/cefs/HASH`

## Initial implementation

- Disable "squashing" for new images (for now)
- Port each sqfs image one at a time:
  - Check contents are identical to NFS (alert if not; we know we have a few that need fixing)
  - `shasum` it and move it (or copy) from `/efs/squash-images/path/to/sq.img` to `/efs/cefs-images/HASH.img`
    - may need to force unmount it from all live images to prevent issues?
      - `rm /path` then
      - `ce --env prod exec_all sudo umount /path`
      - (brief window where Bad Things Happen, and we fall back to regular NFS)
  - move the `/opt/compiler-explorer/path/to/sq` to a `/opt/compiler-explorer/path/to/sq.old` (to allow for rollback)
  - symlink `/opt/compiler-explorer/path/to/sq` to `/efs/cefs-images/HASH`
- This lets us move one at a time (give or take the unmount from images etc)

Installation looks like:

- Install to temp dir
  - Some care for stupid non-moveable things like python ve stuff
  - could consider `unshare` bindmounts (`userbindmount`) to solve that
- squash the temp dir
- move it in place
- symlink the thing!

We could even move installation over first, and then port after that.

Down the line we can "consolidate" images, like point all old GCCs into one image. That's transparent to everyone.

## Configuration

I suggest we make a `/opt/compiler-explorer/config.yaml` or something that stores "are we squashfsing or not" for `ce_install`. That way by default we continue "just" installing (for local installs), but `ce_install` on the admin machine will Do The Right Thing™. (not a dotfile else a rebuild of the admin machine will maybe lose that setting)

## Work

- [ ] Investigate what I've forgotten about getting this to work
  - [ ] Update builder to 22.04 and cefs support
- [ ] "Squash verify" to check current squash images are in fact "correct"
- [ ] Simple config loader
- [ ] Disable squashing
- [ ] Update installers to (optionally, based on config) install this way (even works for nightly; and `tar` installers etc can skip the middle man and just turn `tar` etc into a squashfs image maybe? or doesn't matter using local disk)
- [ ] Write "port" code to move existing images over
- [ ] Slowly move older things over
- [ ] Write consolidation tooling and run it

## Claude Implementation Notes

### Migration

The migration from current squashfs mounts to CEFS symlinks requires careful handling of the directory-to-symlink transition. Since POSIX doesn't support atomic replacement of a directory with a symlink, we accept a brief unavailability window.

#### The Challenge

- `/opt/compiler-explorer/gcc-13.1.0/` is currently a mount point (squashfs mounted over NFS directory)
- We want it to become a symlink to `/cefs/HASH`
- Cannot atomically replace a directory with a symlink
- Bind mounts won't work as we'd need to coordinate across 40 machines simultaneously

#### Migration Sequence

The key insight: the NFS directory underneath the mount is NOT empty - it contains the actual compiler files. When we unmount the squashfs, the NFS contents become visible again, providing a fallback during migration.

```bash
# 1. Unmount everywhere - falls back to NFS (slower but works)
ce --env prod exec_all sudo umount /opt/compiler-explorer/some/compiler

# 2. Move the image so new instances won't mount it
HASH=$(sha256sum /efs/squash-images/some/compiler.img | cut -d' ' -f1)
mv /efs/squash-images/some/compiler.img /efs/cefs-images/${HASH}.img

# 3. Move the actual NFS directory (NOT empty, contains all compiler files)
mv /opt/compiler-explorer/some/compiler /opt/compiler-explorer/some/compiler.bak

# 4. === BRIEF UNAVAILABILITY WINDOW ===
# Any access to /opt/compiler-explorer/some/compiler gets ENOENT
# Window duration: milliseconds (mv and ln -s are both inode operations)

# 5. Create symlink to autofs mount point
ln -s /cefs/${HASH} /opt/compiler-explorer/some/compiler

# 6. First access triggers autofs mount of /efs/cefs-images/${HASH}.img to /cefs/${HASH}
```

#### What Happens During Migration

1. **After unmount (step 1)**: Compiler still accessible via NFS (slower but functional)
2. **After image move (step 2)**: New instances won't mount the squashfs, will use NFS
3. **During window (between steps 3-5)**: ENOENT errors - CE retry logic should handle
4. **After symlink (step 5)**: Autofs transparently mounts on first access

#### Verification and Rollback

```bash
# Quick verification after migration
if /opt/compiler-explorer/some/compiler/bin/gcc --version > /dev/null 2>&1; then
    echo "Migration successful"
    # Keep .bak for 24 hours before cleanup
else
    echo "Migration failed, rolling back"
    rm /opt/compiler-explorer/some/compiler
    mv /opt/compiler-explorer/some/compiler.bak /opt/compiler-explorer/some/compiler
    mv /efs/cefs-images/${HASH}.img /efs/squash-images/some/compiler.img
fi
```

#### Migration Strategy

1. **Order**: Migrate least-used compilers first (gcc-4.x, deprecated versions)
2. **Timing**: Popular compilers during night/weekend
3. **Monitoring**: Watch for ENOENT errors in logs during migration
4. **Cleanup**: Remove `.bak` directories after 24 hours of successful operation

#### Edge Cases

- **Compilation in progress**: Already loaded in memory, continues running
- **New compilation starting**: Gets ENOENT, CE retry logic handles
- **Directory listing**: Briefly won't show the compiler
- **New instances spinning up**: See either NFS version, symlink, or brief ENOENT

### Consolidation

After initial migration to CEFS, we can reduce mount overhead by combining multiple individual squashfs images into consolidated images with subdirectories. This amortizes the cost of mounting while maintaining the benefits of content-addressable storage.

#### Design Principle: Filesystem as Truth

No metadata database needed. The filesystem tells us everything:
- Symlinks in `/opt/compiler-explorer/` show what's in use
- Link targets reveal if using individual (`/cefs/HASH`) or consolidated (`/cefs/HASH/subdir`) images
- Orphaned subdirs in consolidated images are discovered by scanning

#### Consolidation Process

1. **Find candidates**: Walk `/opt/compiler-explorer/` for symlinks pointing to individual images (paths like `/cefs/HASH` rather than `/cefs/HASH/subdir`)

2. **Batch by size**: Group candidates together staying under size limits (e.g., 2GB compressed, 8GB uncompressed)

3. **Build consolidated image**: Unpack individual images into subdirectories of a working directory, then create a new squashfs image from that directory

4. **Update symlinks**: Atomically update each symlink to point to the appropriate subdirectory within the consolidated image

#### Patching Strategy

When a compiler in a consolidated image needs updating:

1. Create new individual image with the update
2. Update symlink to point to the new individual image
3. Old subdirectory inside consolidated image becomes orphaned (wastes space temporarily)
4. Next consolidation run detects the orphan and rebuilds without it

This approach trades temporary space waste for simplicity and immediate updates.

#### Orphan Detection

Periodic scans find unused subdirectories in consolidated images by:
- Listing all subdirectories within each consolidated image
- Checking if any symlink in `/opt/compiler-explorer/` references each subdirectory
- Marking unreferenced subdirectories as orphans for cleanup in the next consolidation run

#### Benefits of No-Metadata Approach

1. **Always correct**: Filesystem state cannot lie
2. **No synchronization issues**: No separate database to maintain
3. **Simple debugging**: `ls -la` shows everything
4. **Easy recovery**: Just examine symlinks and images
5. **Stateless operations**: Each consolidation run starts fresh

#### Consolidation Guidelines

- **Size limits**: Keep consolidated images reasonable (2GB compressed, 8GB uncompressed)
- **Exclusions**: Never consolidate trunk/nightly/snapshot compilers
- **Timing**: Run during low-usage periods
- **Validation**: Test each consolidated image before updating symlinks
- **Cleanup**: Remove orphaned individual images after successful consolidation

#### Future Optimizations

- **Multi-tier consolidation**: Could consolidate consolidated images for very cold data
- **Smart grouping**: Analyze access patterns to group frequently co-accessed compilers
- **Differential updates**: Use overlayfs for minor patches to avoid rebuilding
