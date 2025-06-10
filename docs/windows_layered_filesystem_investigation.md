# Windows Layered Filesystem Investigation for Compiler Hosting

## Executive Summary

This document investigates potential solutions for hosting Windows compilers (MSVC) in a memory-efficient manner using layered or union filesystem approaches. The goal is to implement read-only compiler installations that can be shared across multiple compiler versions while using standard disk locations for compilation output.

## Key Constraints

- Maximum 16GB memory budget
- Read-only compiler and Windows SDK installations
- Normal disk usage for temporary files and compilation output
- No access to proprietary solutions like Arsenal Image Mounter
- Need for multiple compiler version support

## Windows Filesystem Technologies Overview

### 1. Reparse Points and Sparse Files

Windows NTFS provides two key technologies that enable overlay-like functionality:

- **Reparse Points**: User-defined data attached to files/directories that can redirect I/O operations
- **Sparse Files**: Files that don't allocate physical disk space for empty regions

These technologies are already used by Windows features like:
- Windows Overlay Filter (WOF) for CompactOS
- Symbolic links and junction points
- Volume mount points

### 2. File System Minifilter Drivers

Minifilter drivers intercept and potentially modify file I/O operations. They operate through the Filter Manager framework and can:
- Monitor file access patterns
- Redirect read/write operations
- Implement copy-on-write semantics
- Create virtual file views

## Existing Solutions and Implementations

### Open Source Projects

#### 1. **WinFsp (Windows File System Proxy)**
- **License**: GPLv3 with FLOSS exception
- **Description**: FUSE for Windows, allows user-mode filesystems
- **GitHub**: https://github.com/winfsp/winfsp
- **Pros**: 
  - Mature and well-maintained
  - Supports FUSE2/FUSE3 APIs
  - User-mode development (no kernel programming needed)
- **Cons**: 
  - Performance overhead of user-kernel transitions
  - Not a true union/overlay filesystem out of the box

#### 2. **Dokany**
- **License**: LGPL 3.0
- **Description**: User-mode file system library for Windows
- **Pros**: 
  - Active community
  - Compatible with many FUSE filesystems
- **Cons**: 
  - Similar limitations to WinFsp
  - Requires additional work for union functionality

#### 3. **LazyCopy**
- **GitHub**: https://github.com/aleksk/LazyCopy
- **Description**: NTFS minifilter that downloads file content on first access
- **Relevant Features**:
  - Uses reparse points for placeholder files
  - Implements on-demand file hydration
  - Good example of minifilter development

#### 4. **Microsoft VFSForGit**
- **License**: MIT (but PrjFlt driver is closed source)
- **Description**: Virtual filesystem for Git repositories
- **Key Concepts**:
  - Five file states: Virtual, Placeholder, Hydrated, Full, Tombstone
  - Uses ProjFS (Windows Projected File System)
  - Efficient for large repositories

### Commercial Solutions

- **CallbackFS**: Commercial FUSE port, expensive licensing
- **Various minifilter frameworks**: EaseFilter SDK, etc.

## Windows Driver Development APIs

### Core Minifilter APIs

```c
// Key functions for minifilter development
FltRegisterFilter()      // Register the minifilter with Filter Manager
FltStartFiltering()      // Begin filtering I/O operations
FltUnregisterFilter()    // Unregister the minifilter

// Callback registration structure
CONST FLT_OPERATION_REGISTRATION Callbacks[] = {
    { IRP_MJ_CREATE,          0, PreCreate,  PostCreate },
    { IRP_MJ_READ,            0, PreRead,    PostRead },
    { IRP_MJ_WRITE,           0, PreWrite,   PostWrite },
    { IRP_MJ_DIRECTORY_CONTROL, 0, PreDirCtrl, PostDirCtrl },
    { IRP_MJ_OPERATION_END }
};
```

### Key I/O Request Packets (IRPs)

- `IRP_MJ_CREATE`: File/directory open operations
- `IRP_MJ_READ`: Read operations
- `IRP_MJ_WRITE`: Write operations
- `IRP_MJ_DIRECTORY_CONTROL`: Directory enumeration
- `IRP_MJ_QUERY_INFORMATION`: File metadata queries
- `IRP_MJ_SET_INFORMATION`: File metadata updates

### Development Requirements

1. **Windows Driver Kit (WDK)**: Latest version 10.0.26100.3323
2. **Visual Studio 2022**: With Windows driver development workload
3. **Test signing certificate**: For driver installation during development
4. **Windows SDK**: For user-mode support libraries

## Proposed Implementation Approach

### Architecture Overview

```
┌─────────────────────────────────────────┐
│          Application (cl.exe)           │
├─────────────────────────────────────────┤
│         Win32 File System API           │
├─────────────────────────────────────────┤
│     Compiler Explorer Minifilter        │
│  (Redirects reads to compressed store)  │
├─────────────────────────────────────────┤
│         NTFS File System                │
└─────────────────────────────────────────┘
```

### Design Principles

1. **Read-Only Base Layer**: Compressed compiler installations stored as WIM or custom format
2. **Sparse File Placeholders**: Empty files with reparse points in the visible filesystem
3. **On-Demand Decompression**: Decompress only accessed files into memory cache
4. **Shared Memory Pool**: Common headers/libraries shared across compiler instances

### Implementation Strategy

#### Phase 1: Prototype with WinFsp
1. Implement a user-mode filesystem using WinFsp
2. Create union mount logic for multiple compiler versions
3. Test performance and memory usage
4. Validate approach before kernel development

#### Phase 2: Minifilter Development (if needed)
1. Develop custom minifilter driver
2. Implement reparse point handling
3. Add compressed file store backend
4. Optimize for compiler access patterns

#### Phase 3: Optimization
1. Implement intelligent caching for hot files
2. Add prefetching for common include paths
3. Memory-map shared components
4. Profile and tune based on real usage

## Technical Implementation Details

### File State Management

```c
typedef enum _CE_FILE_STATE {
    CE_FILE_VIRTUAL,      // Exists only in metadata
    CE_FILE_PLACEHOLDER,  // Sparse file with reparse point
    CE_FILE_CACHED,       // Decompressed in memory cache
    CE_FILE_MODIFIED      // Written by compiler (in temp)
} CE_FILE_STATE;
```

### Reparse Point Structure

```c
typedef struct _CE_REPARSE_DATA {
    ULONG  ReparseTag;           // Custom tag for CE
    USHORT ReparseDataLength;
    USHORT Reserved;
    GUID   CompilerVersionId;    // Which compiler version
    ULONG  CompressedOffset;     // Offset in store
    ULONG  CompressedSize;       // Compressed size
    ULONG  UncompressedSize;     // Original size
    WCHAR  OriginalPath[1];      // Variable length
} CE_REPARSE_DATA;
```

### Memory Management Strategy

1. **LRU Cache**: Keep frequently accessed files in memory
2. **Shared Pages**: Use memory mapping for identical files
3. **Compression**: Use LZMS or custom algorithm optimized for code
4. **Preload Lists**: Common headers loaded at startup

## Alternative Approaches

### 1. Modified WIM Mounting
- Use Windows Imaging Format with custom modifications
- Implement partial mounting with lazy loading
- Leverage existing WOF driver infrastructure

### 2. Container-Based Solution
- Use Windows Containers with volume mounting
- Implement custom storage driver
- Higher overhead but better isolation

### 3. User-Mode Proxy
- Intercept compiler file operations at application level
- Redirect to compressed storage
- No driver needed but requires compiler modifications

## Performance Considerations

### Expected Bottlenecks
1. Initial file access (decompression overhead)
2. Memory pressure with multiple active compilers
3. Cache invalidation and eviction

### Optimization Strategies
1. Parallel decompression using multiple cores
2. Predictive prefetching based on include patterns
3. Tiered caching (hot, warm, cold)
4. Background cache warming

## Security Considerations

1. **Driver Signing**: Must be properly signed for production
2. **Access Control**: Ensure read-only enforcement
3. **Cache Isolation**: Prevent cache poisoning
4. **Update Mechanism**: Safe compiler version updates

## Development Roadmap

### Milestone 1: Proof of Concept (2-3 weeks)
- [ ] WinFsp-based prototype
- [ ] Basic union filesystem logic
- [ ] Performance benchmarking

### Milestone 2: Production Design (3-4 weeks)
- [ ] Minifilter driver skeleton
- [ ] Compression backend
- [ ] Cache management

### Milestone 3: Integration (2-3 weeks)
- [ ] Compiler Explorer integration
- [ ] Multi-version support
- [ ] Production hardening

### Milestone 4: Optimization (2-3 weeks)
- [ ] Performance tuning
- [ ] Memory optimization
- [ ] Stress testing

## Conclusion

A Windows layered filesystem for compiler hosting is technically feasible using either:
1. User-mode implementation with WinFsp (faster development, some overhead)
2. Kernel-mode minifilter driver (optimal performance, complex development)

The recommended approach is to start with WinFsp for rapid prototyping and validation, then consider a minifilter implementation if performance requirements demand it. The key technologies (reparse points, sparse files, compression) are well-established in Windows and suitable for this use case.

## References

- [Windows Driver Samples](https://github.com/microsoft/Windows-driver-samples)
- [WinFsp Documentation](https://github.com/winfsp/winfsp)
- [Windows Driver Kit Documentation](https://learn.microsoft.com/en-us/windows-hardware/drivers/)
- [File System Minifilter Drivers](https://learn.microsoft.com/en-us/windows-hardware/drivers/ifs/)
- [NTFS Reparse Points](https://learn.microsoft.com/en-us/windows/win32/fileio/reparse-points)