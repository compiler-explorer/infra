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
- A pattern match of the target name

```bash
# Matches any installable with "gcc" in the path OR named "gcc"
ce_install list gcc

# Matches any installable with "boost" in the path OR named "boost"
ce_install list boost

# Wildcard patterns
ce_install list "assertions-*"    # Any assertions build
ce_install list "14.*"            # Any 14.x version

# Negative patterns
ce_install list "!cross"          # Exclude cross-compilers
ce_install list "!assertions-*"   # Exclude assertion builds

# Version ranges
ce_install list ">=14.0"          # Version 14.0 and newer
ce_install list "~=1.70.0"        # Version 1.70.x (tilde range)
```

### Two Word Filters
Space-separated words create a context+target filter:
- First word: matches context (pattern)
- Second word: matches target (pattern)

```bash
# Matches installables with "gcc" in path AND target exactly "14.1.0"
ce_install list "gcc 14.1.0"

# Matches installables with "gcc" in path AND any 14.x version
ce_install list "gcc 14.*"

# Wildcard context with version range
ce_install list "*/gcc >=14.0"

# Exclude specific versions
ce_install list "clang !assertions-*"
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

#### Wildcard Matching
Use `*` for glob-style pattern matching:
```bash
# Any path ending with "gcc"
ce_install list "*/gcc"

# Any path with "c++" in the middle
ce_install list "*/c++/*"

# Cross-compilers for any architecture
ce_install list "cross/*/*"
```

## Advanced Filter Features

### Wildcard Patterns
Use `*` for pattern matching in both context and target:

```bash
# All assertion builds (any version)
ce_install list "assertions-*"

# All GCC 14.x versions
ce_install list "14.*"

# Any cross-compiler ending in specific pattern
ce_install list "cross/* *-arm-*"
```

### Negative Filters
Use `!` prefix to exclude matches:

```bash
# All non-cross-compiler GCC
ce_install list "gcc !cross"

# Everything except assertion builds
ce_install list "!assertions-*"

# GCC without version 14.x
ce_install list "gcc !14.*"
```

### Version Range Matching
Use comparison operators for semantic version filtering:

```bash
# GCC version 14.0 and newer
ce_install list "gcc >=14.0"

# Boost versions before 1.75
ce_install list "boost <1.75"

# All 1.70.x versions (tilde range)
ce_install list "boost ~=1.70.0"

# Exact version matching
ce_install list "gcc ==14.1.0"

# Exclude specific version
ce_install list "gcc !=14.1.0"

# Version range combinations
ce_install list "gcc >=14.0"
ce_install list "clang <=15.0"

# Compound constraints
ce_install list "gcc >=14.0,<15.0"
```

**Version Range Operators:**
- `>=` - Greater than or equal
- `>` - Greater than
- `<=` - Less than or equal
- `<` - Less than
- `==` - Exactly equal
- `!=` - Not equal
- `~=` - Tilde range (matches major.minor.x)

**Compound Constraints:**
Combine multiple version constraints with commas:
```bash
# Version 14.x but before 15.0
ce_install list "gcc >=14.0,<15.0"

# Boost between 1.70 and 1.80
ce_install list "boost >=1.70.0,<1.80.0"
```

### Complex Combinations
Combine multiple features for precise filtering:

```bash
# Non-cross GCC with version 14.x
ce_install list "gcc !cross" "14.*" --filter-match-all

# Either assertions OR version 14+
ce_install list "assertions-*" ">=14.0" --filter-match-any

# All C++ libraries except Boost
ce_install list "libraries/c++" "!boost" --filter-match-all
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

# All GCC 14.x versions
ce_install list "gcc 14.*"

# GCC 14.0 and newer
ce_install list "gcc >=14.0"

# Cross-compilers only
ce_install list "cross/gcc"

# All C++ compilers except cross-compilers
ce_install list "c++" "!cross"

# All compilers (vs libraries)
ce_install list "/compilers"
```

### Finding Libraries
```bash
# All libraries
ce_install list "/libraries"

# All C++ libraries
ce_install list "libraries/c++"

# All Boost 1.70.x versions
ce_install list "boost ~=1.70.0"

# Recent Boost versions (1.75+)
ce_install list "boost >=1.75"

# All fmt library versions
ce_install list fmt

# Exclude specific library versions
ce_install list "boost !1.64.0"
```

### Architecture-Specific
```bash
# ARM-related installables
ce_install list arm

# Any ARM cross-compiler
ce_install list "*/arm/*"

# Cross-compilers for specific architecture and version range
ce_install list "cross/gcc/arm >=12.0"

# Specific version only
ce_install list "gcc ==14.1.0"

# Everything except a specific version
ce_install list "gcc !=13.1.0"
```

### Assertion and Specialized Builds
```bash
# All assertion builds
ce_install list "assertions-*"

# Assertion builds for specific compiler
ce_install list "clang assertions-*"

# All builds except assertions
ce_install list "!assertions-*"

# Specific assertion version range
ce_install list "assertions->=10.0"
```

## Common Pitfalls

### Pattern vs Exact Matching
```bash
# Without wildcards, target matching is still exact
ce_install list "gcc 14"        # Only matches target exactly "14"
ce_install list "gcc 14.*"      # Matches any 14.x version

# Use wildcards for flexible matching
ce_install list "14"            # Finds path with "14" OR target "14"
ce_install list "14.*"          # Finds 14.x versions anywhere
```

### Negative Filter Scope
```bash
# Single negative excludes from both context AND target
ce_install list "!cross"        # No "cross" in path AND target not "cross"

# Two-word negative only applies to the specified part
ce_install list "gcc !cross"    # Has gcc in path AND target not cross
ce_install list "!cross gcc"    # No cross in path AND target is gcc
```

### Version Range Limitations
```bash
# Version ranges only work on numeric parts
ce_install list ">=assertions-3.0"  # Works - extracts "3.0"
ce_install list ">=gcc"             # No effect - no numbers

# Tilde ranges compare major.minor only
ce_install list "~=1.70.0"      # Matches 1.70.0, 1.70.5, not 1.71.0
```

### Wildcard Behavior
```bash
# Wildcards use glob matching, not regex
ce_install list "14.*"          # Matches 14.1.0, 14.anything
ce_install list "14\..*"        # Literal dot - won't match versions

# Context wildcards match full path
ce_install list "*/gcc"         # Matches any path ending in "gcc"
ce_install list "*gcc*"         # Matches any path containing "gcc"
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
