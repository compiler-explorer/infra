#!/bin/bash
# Mount /opt with autofs instead of mounting all squashfs images at boot
# This replaces the mount-all-img.sh approach with on-demand mounting

set -euo pipefail

# First, unmount any existing squashfs mounts
echo "Unmounting existing squashfs mounts..."
mount | grep -E "^/efs/squash-images/.*\.img on /opt/compiler-explorer" | \
    awk '{print $3}' | \
    xargs -r -n1 umount || true

# Setup autofs
echo "Setting up autofs for /opt/compiler-explorer..."
"$(dirname "$0")/setup-autofs.sh"

echo "Autofs mount setup complete!"

# Optional: Pre-populate commonly used mounts
# This can help reduce first-access latency for critical compilers
if [[ -f "/etc/ce-common-compilers.txt" ]]; then
    echo "Pre-populating common compiler mounts..."
    while IFS= read -r compiler; do
        # Just access the directory to trigger mount
        ls "/opt/compiler-explorer/${compiler}" > /dev/null 2>&1 || true
    done < "/etc/ce-common-compilers.txt"
fi
