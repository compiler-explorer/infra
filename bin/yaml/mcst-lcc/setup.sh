#!/bin/bash

set -euo pipefail

DIR="${1:?lcc root required}"

# Replace broken absolute symlinks to /opt/mcst with relative symlinks.
find "$DIR" -type l \! -exec test -e {} \; \
  -exec sh -c 'target="$(readlink "{}" | sed "s@^/opt/mcst/@$CE_STAGING_DIR/@")"; ln -srf "$target" "{}"' \;

# By default compilers can be executed only from /opt/mcst/$DIR. Create a wrapper
# script to execute compilers from any directory.
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

chmod +x "$DIR"/bin/wrapper

# Create symlinks to the wrapper script.
for name in {lcc,l++}; do
  mv "$DIR"/bin/$name{,.orig}
  ln -s wrapper "$DIR"/bin/$name
done
