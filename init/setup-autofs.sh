#!/bin/bash
# Setup autofs for Compiler Explorer squashfs mounts

set -euo pipefail

# Copy the mounter script
cp "$(dirname "$0")/autofs-ce-mounter.sh" /etc/autofs/ce-mounter.sh
chmod 755 /etc/autofs/ce-mounter.sh

# Create the auto.ce map file
cat > /etc/auto.ce <<'EOF'
# Indirect map for Compiler Explorer
# Uses a program map to dynamically determine mount options
*    -fstype=auto    :/etc/autofs/ce-mounter.sh &
EOF

# Add entry to auto.master if not already present
if ! grep -q "^/opt/compiler-explorer" /etc/auto.master 2>/dev/null; then
    echo "Adding autofs entry to auto.master..."
    cat >> /etc/auto.master <<'EOF'

# Compiler Explorer dynamic mounts
/opt/compiler-explorer    /etc/auto.ce    --timeout=300 --ghost
EOF
fi

# Reload autofs configuration
echo "Reloading autofs configuration..."
systemctl reload autofs

echo "Autofs setup complete!"
