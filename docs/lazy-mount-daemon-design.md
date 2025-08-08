# Lazy Mount Daemon Design Document

## Problem Statement

Mounting 2000+ squashfs compiler images at boot causes severe performance issues on Ubuntu 24.04:

- Boot takes 120+ seconds
- systemd consumes 200% CPU during mounting
- Most compilers are never accessed
- Ubuntu 24.04 is 2x slower than 22.04

## Proposed Solution

Monitor file access to `/opt/compiler-explorer/` and mount the corresponding squashfs image on first access.

1. Use bpftrace to monitor `openat` syscalls for `/opt/compiler-explorer/` paths
2. Extract compiler name from access path (e.g., `/opt/compiler-explorer/gcc-15.1.0/bin/gcc` → `gcc-15.1.0`)
3. Mount corresponding squashfs image over NFS directory
4. If mount fails, underlying NFS content remains accessible

## Technical Design

- **Monitor**: bpftrace subprocess monitors `sys_enter_openat` tracepoint with `strncmp` filter for `/opt/compiler-explorer/` prefix
- **Map**: Extract compiler name from path (second component after `/opt/compiler-explorer/`)
- **Mount**: File locking prevents races, mount squashfs over NFS directory

### Implementation

1. Start daemon before Compiler Explorer service
2. Start bpftrace subprocess with `sys_enter_openat` tracepoint
3. Process bpftrace output line-by-line to detect compiler access
4. Mount corresponding squashfs images on-demand

```python
def handle_access(path):
    # Extract compiler from path: /opt/compiler-explorer/gcc-15.1.0/... -> gcc-15.1.0
    if path.startswith("/opt/compiler-explorer/"):
        remainder = path[len("/opt/compiler-explorer/"):]
        if "/" in remainder:
            compiler = remainder.split("/")[0]

            with file_lock(f"/tmp/mount-{compiler}.lock"):
                if not is_already_mounted(compiler):
                    mount_squashfs(f"/efs/squash-images/{compiler}.img",
                                 f"/opt/compiler-explorer/{compiler}")
```

Error handling: log failures, underlying NFS content remains accessible

## Benefits

- Fast boot (no upfront mounting)
- No systemd CPU spikes during boot
- Only mount used compilers (~60% reduction)
- Underlying NFS remains accessible if daemon fails

## Risks

- First access to each compiler slower (mount time)
- New daemon to monitor and debug
- Requires root permissions (bpftrace needs root access)
- Dependency on bpftrace being available
- bpftrace subprocess overhead

## Implementation Plan

1. Basic bpftrace-based daemon with mount logic
2. systemd service integration
3. Logging and monitoring
4. Optional: unmount unused compilers after timeout

## Rollout

1. Test in development
2. Deploy to staging
3. Gradual production rollout

## Success Metrics

- Boot time <10s (eliminating 120+ second mount time)
- First access latency <2s (individual mount time)
- Significant reduction in mounted filesystems (only mount on actual use)
- Handle 118+ events/sec reliably

## Alternatives Considered

1. systemd namespace isolation - complex, limited benefit
2. CEFS FUSE solution - has race conditions
3. Kernel patches - too risky
4. Parallel mounting - still hits systemd limits

## Discussion Points

1. Acceptable first-access latency?
2. Required monitoring/metrics?
3. Daemon failure handling?
4. Implementation timeline and ownership?

## Technical Details

**Proven Approach**: Testing confirmed that bpftrace successfully detects NFS file access where fanotify completely failed. The `sys_enter_openat` tracepoint captures all file opens, including those on network filesystems.

**bpftrace Command**:
```bash
bpftrace -e 'tracepoint:syscalls:sys_enter_openat {
    if (strncmp(str(args->filename), "/opt/compiler-explorer/", 23) == 0) {
        printf("%s\n", str(args->filename));
    }
}'
```
- Uses `strncmp` for efficient prefix matching (avoids BPF stack issues)
- Must set `BPFTRACE_STRLEN=200` environment variable for full paths
- Filtering in kernel reduces event volume by 65%

**Subprocess Configuration**:
```python
env = os.environ.copy()
env['BPFTRACE_STRLEN'] = '200'
process = subprocess.Popen(
    bpftrace_cmd,
    stdout=subprocess.PIPE,
    stderr=subprocess.STDOUT,
    text=True,
    bufsize=0,  # Unbuffered for real-time processing
    env=env
)
```

**Path Processing**: Compiler name extraction from paths like `/opt/compiler-explorer/gcc-15.1.0/lib/...` is reliable since the compiler directory is the second path component.

**Mount Operations**: Atomic - either succeed completely or fail with no changes. Mounting over NFS directories hides original contents but preserves them.

**Failure Mode**: "Fail open" approach - if daemon crashes, existing mounts work and underlying NFS content remains accessible.


## Production Test Results

Testing on a production node during normal usage (60 seconds, midday):

**Without filtering:**
- 343 events/sec total
- 158 events/sec (46%) were compiler-related
- Python handled the volume easily

**With bpftrace filtering** (`strncmp` for `/opt/compiler-explorer/` prefix):
- **118 events/sec** - all compiler-related
- **Only 11 unique compilers accessed in 60 seconds** out of 2000+ available
- **Zero processing overhead** - filtering happens in kernel via eBPF
- Compilers accessed: arm64, clang-20.1.0, clang-trunk, dotnet-v6.0.36, gcc-14.x, gcc-15.1.0, rust-1.89.0, etc.

**Key Findings:**
- **✓ NFS Monitoring Works**: bpftrace captures all NFS file access (fanotify failed completely)
- **✓ Efficient Filtering**: In-kernel filtering reduces events by 65% (343→118 events/sec)
- **✓ Path Length Sufficient**: 200-char limit handles all compiler paths
- **✓ Significant Mount Reduction**: Only 11 compilers accessed in 60-second test period
- **✓ Python Performance**: Easily handles 118 events/sec with headroom

## Next Steps

1. Team review and approval of bpftrace approach
2. Build production daemon with mount logic
3. Integration testing with actual compiler workloads
4. Production deployment planning
