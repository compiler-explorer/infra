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
- [ ] Simple config loader
- [ ] Disable squashing
- [ ] Update installers to (optionally, based on config) install this way (even works for nightly; and `tar` installers etc can skip the middle man and just turn `tar` etc into a squashfs image maybe? or doesn't matter using local disk)
- [ ] Write "port" code to move existing images over
- [ ] Slowly move older things over
- [ ] Write consolidation tooling and run it
