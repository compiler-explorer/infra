#!/bin/bash

set -euo pipefail

IMG_DIR=/efs/squash-images
MOUNT_DIR=/opt/compiler-explorer

shopt -s globstar
declare -A mounts
for img_file in "${IMG_DIR}"/**/*.img; do
  dst_path=${img_file/${IMG_DIR}/${MOUNT_DIR}}
  dst_path=${dst_path%.img}
  if mountpoint -q "$dst_path"; then
    echo "$dst_path is mounted already, skipping"
  else
    mounts["$img_file"]="$dst_path"
  fi
done

if [ -z "${!mounts[*]}" ]; then
  echo "Nothing to do, stopping"
  exit
fi

# Sort image files by modification time (most recent first)
sorted_files=$(printf '%s\0' "${!mounts[@]}" | xargs -0 ls -1t)

echo "Mounting $(echo "$sorted_files" | wc -l) squashfs images sequentially..."

# Mount one at a time, most recent first
while IFS= read -r img_file; do
  dst_path="${mounts[$img_file]}"
  echo "Mounting: $img_file -> $dst_path"
  mount -v -t squashfs "${img_file}" "${dst_path}" -o ro,nodev,relatime
  sleep 0.5
done <<< "$sorted_files"

echo "All mounts completed"
