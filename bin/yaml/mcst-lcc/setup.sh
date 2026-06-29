#!/bin/bash

set -euo pipefail

DIR="${1:?lcc root required}"

if [ ${CE_MCST_LCC_KEEP_GDB-"0"} == "0" ]; then
  # Remove unused files to save disk space.
  rm -rf "$DIR"/gdb
fi

# Replace broken absolute symlinks to /opt/mcst with relative symlinks.
find "$DIR" -type l \! -exec test -e {} \; \
  -exec sh -c 'target="$(readlink "{}" | sed "s@^/opt/mcst/@$CE_STAGING_DIR/@")"; ln -srf "$target" "{}"' \;

# Create a wrapper script to execute compilers from any directory.
#
# Does not fully work with 1.19 and 1.20 versions. Required symlinks for binary support:
#   /opt/mcst/fs -> /opt/compiler-explorer/lcc-1.19.11.e2k-generic.2.6.33/fs
#   /opt/mcst/lcc-1.20.17.e2k-generic.3.14 -> /opt/compiler-explorer/lcc-1.20.17.e2k-generic.3.14
#
# This symlink will fix warning in --help:
#   /opt/mcst/lcc-home -> /opt/compiler-explorer/lcc-1.19.11.e2k-generic.2.6.33/lcc-home
#
# Workarounds for output encodings.
case "$DIR" in
  *lcc-1.19.*|*lcc-1.20.*)
    # These versions generate a very buggy output. It's better to get output in
    # Russian than some random garbage.
    cat >"$DIR"/bin/wrapper <<EOF
#!/bin/bash
name=\$(basename "\$0")
wrapper=\$(readlink -f "\$0")
root="\${wrapper%/bin/wrapper}"
exec env LC_MESSAGES=ru_RU.UTF-8 "\$root/bin/\$name.orig" \\
  -set-home-dir "\$root/lcc-home" \\
  -set-binutils-dir "\$root/binutils" \\
  -set-fs-dir "\$root/fs" "\$@"
EOF
    ;;
  *lcc-1.23.*)
    # These versions generate output in KOI8-R for --help and some error messages.
    cat >"$DIR"/bin/wrapper <<EOF
#!/bin/bash
name=\$(basename "\$0")
wrapper=\$(readlink -f "\$0")
root="\${wrapper%/bin/wrapper}"
{ { exec env LC_MESSAGES=en_US.UTF-8 "\$root/bin/\$name.orig" \\
      -set-home-dir "\$root/lcc-home" \\
      -set-binutils-dir "\$root/binutils" \\
      --sysroot "\$root/fs" "\$@" 2>&3 \\
  | iconv -f KOI8-R -t UTF-8; } 3>&1 1>&2 \\
  | iconv -f KOI8-R -t UTF-8; } 3>&2 2>&1 1>&3
EOF
    ;;
  *)
    cat >"$DIR"/bin/wrapper <<EOF
#!/bin/bash
name=\$(basename "\$0")
wrapper=\$(readlink -f "\$0")
root="\${wrapper%/bin/wrapper}"
exec "\$root/bin/\$name.orig" \\
  -set-home-dir "\$root/lcc-home" \\
  -set-binutils-dir "\$root/binutils" \\
  --sysroot "\$root/fs" "\$@"
EOF
    ;;
esac

chmod +x "$DIR"/bin/wrapper

# Create symlinks to the wrapper script.
for name in {lcc,l++,lfortran}; do
  if [ -e "$DIR"/bin/$name ]; then
    if [ -L "$DIR"/bin/$name ]; then
      ln -s lcc.orig "$DIR"/bin/$name.orig
      ln -sf wrapper "$DIR"/bin/$name
    else
      mv "$DIR"/bin/$name{,.orig}
      ln -s wrapper "$DIR"/bin/$name
    fi
  fi
done
