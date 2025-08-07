#!/bin/bash

set -euo pipefail

IMG_DIR=/efs/squash-images
MOUNT_DIR=/opt/compiler-explorer
LOG_FILE=/tmp/mount-all-img-$(date +%Y%m%d-%H%M%S).log
MOUNT_SCRIPT=/tmp/mount-wrapper-$$.sh

# Function to log with timestamp
log_time() {
    echo "$(date +%s.%N) $*" >> "$LOG_FILE"
}

log_time "Starting mount-all-img.sh"
log_time "Kernel: $(uname -r)"
log_time "Ubuntu: $(lsb_release -d 2>/dev/null | cut -f2 || echo 'Unknown')"
log_time "Parallel mounts: 16"

shopt -s globstar
declare -A mounts
mount_count=0

log_time "Scanning for images in $IMG_DIR"
scan_start=$(date +%s.%N)

for img_file in "${IMG_DIR}"/**/*.img; do
  dst_path=${img_file/${IMG_DIR}/${MOUNT_DIR}}
  dst_path=${dst_path%.img}
  if mountpoint -q "$dst_path"; then
    echo "$dst_path is mounted already, skipping"
  else
    mounts["$img_file"]="$dst_path"
    ((mount_count++))
  fi
done

scan_end=$(date +%s.%N)
scan_time=$(echo "$scan_end - $scan_start" | bc)
log_time "Scan completed in ${scan_time}s, found $mount_count images to mount"

if [ -z "${!mounts[*]}" ]; then
  log_time "Nothing to do, stopping"
  echo "Nothing to do, stopping"
  exit
fi

# Create a wrapper script for instrumented mounting
cat > "$MOUNT_SCRIPT" << 'WRAPPER_EOF'
#!/bin/bash
LOG_FILE=$1
shift
IMG_FILE=$1
DST_PATH=$2

# Log before mount
start_time=$(date +%s.%N)
echo "$(date +%s.%N) MOUNT_START: ${IMG_FILE##*/} -> ${DST_PATH##*/}" >> "$LOG_FILE"

# Do the mount
mount -v -t squashfs "${IMG_FILE}" "${DST_PATH}" -o ro,nodev,relatime

# Log after mount
end_time=$(date +%s.%N)
mount_time=$(echo "$end_time - $start_time" | bc)
echo "$(date +%s.%N) MOUNT_END: ${IMG_FILE##*/} took ${mount_time}s" >> "$LOG_FILE"

# Log if mount was particularly slow
if (( $(echo "$mount_time > 1.0" | bc -l) )); then
    echo "$(date +%s.%N) SLOW: Mount took ${mount_time}s for ${IMG_FILE##*/}" >> "$LOG_FILE"
fi
WRAPPER_EOF

chmod +x "$MOUNT_SCRIPT"

echo "Mounting $mount_count squashfs images in parallel (16 workers)..."
echo "Logging to: $LOG_FILE"

# If we try and do this in the loop, the mountpoint and mount commands effectively
# serialise and we end up blocking until the whole thing's done.
mount_start=$(date +%s.%N)

for img_file in "${!mounts[@]}"; do
  dst_path="${mounts[$img_file]}"
  echo "$MOUNT_SCRIPT '$LOG_FILE' '$img_file' '$dst_path'"
done | xargs -d'\n' -n1 -P16 sh -c

mount_end=$(date +%s.%N)
mount_time=$(echo "$mount_end - $mount_start" | bc)

log_time "All mounts completed in ${mount_time}s"
echo "All mounts completed in ${mount_time}s"
echo "Log file: $LOG_FILE"

# Cleanup
rm -f "$MOUNT_SCRIPT"

# Summary statistics
{
    echo ""
    echo "=== Summary ==="
    echo "Total mounts: $mount_count"
    echo "Total time: ${mount_time}s"
    echo "Average time per mount: $(echo "scale=3; $mount_time / $mount_count" | bc)s"
    echo ""
    echo "=== Slow mounts (>1s) ==="
    grep "SLOW:" "$LOG_FILE" 2>/dev/null | head -20 || echo "No slow mounts detected"
    slow_count=$(grep -c "SLOW:" "$LOG_FILE" 2>/dev/null || echo "0")
    if [ "$slow_count" -gt 20 ]; then
        echo "... and $((slow_count - 20)) more slow mounts"
    fi
} >> "$LOG_FILE"
