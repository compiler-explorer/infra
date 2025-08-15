# CE Install Filter System

The `ce_install` command supports a flexible filter system to match installation targets based on their context (path) and target name (version). This document explains how filters work and provides practical examples.

## Installable Structure

Each installable has two components:
- **Context**: The hierarchical path (e.g., `compilers/c++/gcc`)
- **Target**: The version or specific name (e.g., `14.1.0`)

Examples:
```
compilers/c++/gcc 14.1.0
libraries/c++/boost 1.70.0
compilers/ada/gnat/arm 10.3.0-2
```

## Filter Syntax

### Single Word Filters
A single word matches if it appears as:
- A substring anywhere in the context path, OR
- An exact match of the target name

```bash
# Matches any installable with "gcc" in the path OR named "gcc"
ce_install list gcc

# Matches any installable with "boost" in the path OR named "boost"
ce_install list boost
```

### Two Word Filters
Space-separated words create a context+target filter:
- First word: matches context (substring)
- Second word: matches target (exact)

```bash
# Matches installables with "gcc" in path AND target exactly "14.1.0"
ce_install list "gcc 14.1.0"

# Matches installables with "boost" in path AND target exactly "1.70.0"
ce_install list "boost 1.70.0"
```

### Path Matching Rules

Context matching supports path-based filtering:

#### Substring Matching
```bash
# Matches paths containing "cross/gcc" anywhere
ce_install list "cross/gcc"
```

#### Root Path Matching
Leading `/` requires the path to start with the specified prefix:
```bash
# Only matches paths starting with "compilers/"
ce_install list "/compilers"

# Only matches paths starting with "libraries/"
ce_install list "/libraries"
```

## Multiple Filters

### Match All (Default)
By default, all filters must match (AND logic):
```bash
# Must contain "gcc" AND target "14.1.0"
ce_install list gcc 14.1.0
```

### Match Any
Use `--filter-match-any` for OR logic:
```bash
# Contains "gcc" OR target "14.1.0"
ce_install --filter-match-any list gcc 14.1.0
```

## Common Examples

### Finding Compilers
```bash
# All GCC compilers
ce_install list gcc

# Specific GCC version across all architectures
ce_install list "gcc 14.1.0"

# Cross-compilers only
ce_install list "cross/gcc"

# All C++ compilers
ce_install list "c++"

# All compilers (vs libraries)
ce_install list "/compilers"
```

### Finding Libraries
```bash
# All libraries
ce_install list "/libraries"

# All C++ libraries
ce_install list "libraries/c++"

# All Boost versions
ce_install list boost

# Specific Boost version
ce_install list "boost 1.70.0"

# All fmt library versions
ce_install list fmt
```

### Architecture-Specific
```bash
# ARM-related installables
ce_install list arm

# Cross-compilers for specific architecture
ce_install list "cross/gcc/arm"
```

### Version Patterns
```bash
# Find any version 14.x
ce_install list 14

# Find specific version across all compilers
ce_install list 14.1.0
```

## Common Pitfalls

### Target Matching Is Exact
```bash
# This finds items with "14" anywhere in path OR exactly named "14"
ce_install list 14

# This does NOT find "14.1.0" - target must match exactly
ce_install list "gcc 14"

# This DOES find "14.1.0"
ce_install list "gcc 14.1.0"
```

### Substring vs Exact Matching
```bash
# Context: substring match - finds gcc-assertions, gcc-arm, etc.
ce_install list gcc

# Target: exact match - only finds items named exactly "gcc"
ce_install list "anything gcc"
```

### Special Characters
```bash
# The "+" in "c++" works as expected in context
ce_install list "c++"

# Version patterns with dots work as exact matches
ce_install list "fmt 10.0.0"
```

## Advanced Usage

### Combining Filters
```bash
# Multiple context requirements (must match ALL)
ce_install list gcc cross arm

# Multiple possibilities (match ANY)
ce_install --filter-match-any list gcc clang
```

### Empty Filters
```bash
# No filter - lists everything (2300+ items)
ce_install list

# Filter with libraries and specific version
ce_install list libraries 1.0.0
```

## Performance Notes

With over 2300 installables, specific filters perform better than broad ones. Use the most specific filter possible for your needs.

Example counts:
- `ce_install list` - 2313 items
- `ce_install list gcc` - ~500 items
- `ce_install list "gcc 14.1.0"` - 24 items
- `ce_install list "libraries/c++/boost 1.70.0"` - 1 item
