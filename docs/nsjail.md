# nsjail in Compiler Explorer

## Overview

Compiler Explorer uses [nsjail](https://github.com/google/nsjail) to sandbox compilation and execution processes. nsjail provides secure containerization using Linux namespaces and cgroups, isolating untrusted code compilation from the host system.

## CE's Fork

Compiler Explorer maintains a fork at https://github.com/compiler-explorer/nsjail with patches for:

1. Better signal handling for improved signal forwarding for compilation processes
2. Mount propagation support for autofs/CEFS compatibility (see [PR #2](https://github.com/compiler-explorer/nsjail/pulls/2))

The main CE nsjail configuration is at `/etc/nsjail/compilers-and-tools.cfg`.

## Mount Propagation for CEFS

### The Problem

Compiler Explorer's [CEFS](cefs.md) uses autofs for on-demand mounting of SquashFS images. When a compilation process accesses `/cefs/4c/4cdeadbeef/library`, autofs automatically mounts the corresponding SquashFS image at `/efs/squash-images/4c/4cdeadbeef.sqfs`.

However, in containers with default mount namespace settings, these autofs-created mounts don't propagate into the container, causing ["Too many levels of symbolic links"](https://unix.stackexchange.com/questions/141436/too-many-levels-of-symbolic-links) errors.

### Root Cause: Mount Propagation Inheritance

Linux [mount propagation](https://www.kernel.org/doc/Documentation/filesystems/sharedsubtree.txt) follows an inheritance model:

1. [Systemd](https://www.freedesktop.org/software/systemd/man/systemd.mount.html) sets most mounts (including `/cefs`) as `MS_SHARED` by default
2. When nsjail creates a new mount namespace, it initially sets the root filesystem propagation type
3. Child mounts inherit propagation settings from their parent

The key insight is that mount propagation relationships must be established when mounts are created, not after.

### Why Root Needs `MS_SLAVE`

```
Host: /cefs (MS_SHARED - can propagate events)
       └── /cefs/4c (created by autofs)

Container: / (MS_PRIVATE - blocks all propagation)
            └── /cefs (inherits MS_PRIVATE - cannot receive events)
```

When the container root is `MS_PRIVATE`, the `/cefs` bind mount inherits `MS_PRIVATE` and cannot receive mount propagation events from the host, even if we try to change it to `MS_SLAVE` later.

### The Solution

Set the container root to `MS_SLAVE` when any mount needs propagation:

```
Host: /cefs (MS_SHARED - can propagate events)
       └── /cefs/4c (created by autofs)
              ↓ (propagation)
Container: / (MS_SLAVE - can receive propagation)
            └── /cefs (inherits MS_SLAVE - receives mount events)
                └── /cefs/4c (appears via propagation)
```

This is implemented via the `needs_mount_propagation` flag in nsjail configuration:

```protobuf
mount {
    src: "/cefs"
    dst: "/cefs"
    is_bind: true
    needs_mount_propagation: true
}
```

### Security Implications

Setting root to `MS_SLAVE` has the following characteristics:

- Security is maintained since containers cannot affect host mounts (one-way propagation)
- All bind mounts become slaves to the host, not just `/cefs`
- This matches Docker/runc standard practice

#### Why This Is Safe for CE

CE's compilation containers are short-lived (seconds to minutes) and each gets a fresh mount namespace. The security implications are minimal:

- Each container starts with whatever the host root namespace contains at that moment
- Containers don't run long enough for mount changes to matter
- `MS_SLAVE` prevents containers from affecting the host
- In practice, this only affects autofs trap mounts

As noted by CE's security review: *"given our containers aren't long lived, it's perfectly safe and cromulent to 'just' always use MS_SLAVE - every time a new container starts it will pick up whatever the root mount namespace has anyway; so the only thing this really impacts is the autofs trap mounts"*.

#### Alternative: Always Use `MS_SLAVE`

Given the safety for short-lived containers, an alternative approach would be to always use `MS_SLAVE` by default rather than requiring the `needs_mount_propagation` flag. This would simplify configuration, match Docker/runc defaults exactly, eliminate any future autofs/systemd mount issues, and have zero additional security impact for CE's use case.

From runc's source (`libcontainer/rootfs_linux.go`):
```go
flag := unix.MS_SLAVE | unix.MS_REC  // Default for container runtimes
```

### Industry Context

This behavior matches container runtimes like Docker and [runc](https://github.com/opencontainers/runc), which default to `MS_SLAVE` for the root filesystem to support Kubernetes volume mounts, autofs filesystems, systemd-managed mounts, and container orchestration requiring mount visibility.

The alternative (`MS_PRIVATE`) is known to cause issues with container orchestration and is generally avoided in production container runtimes.

### Configuration Files

The main production configuration is in Compiler Explorer's own repo in `etc/nsjail`, with `compilers-and-tools.cfg` used for compilers and tools and `user-execution.cfg` for sandboxing user code. The configuration schema is defined in `config.proto` in the nsjail source, and mount propagation logic is handled in `mnt.cc`.

## Future Documentation

This document will be expanded to cover other aspects of nsjail configuration, security policies, resource limits, and troubleshooting.
