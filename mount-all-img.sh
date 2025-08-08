#!/bin/bash

# Ubuntu 24.04 has a severe systemd performance regression when handling many mounts.
# Without this workaround, mounting 2000+ squashfs images takes 100+ seconds with systemd
# pegged at 200% CPU, making the machine unresponsive during boot.
#
# Root cause: Both main systemd (PID 1) and user systemd processes consume excessive
# CPU processing mount events. Testing showed:
# - Normal: 96-101 seconds
# - Frozen user systemd: 43 seconds (57% improvement)
# - Mount namespace (isolated from systemd): 34 seconds
#
# This temporarily freezes the user systemd process during mounting, reducing
# boot time significantly while keeping the system stable.
kill -STOP "$(pidof systemd | head -1)"
python3 "$(dirname "$0")/mount-all-img.py" "$@"
kill -CONT  "$(pidof systemd | head -1)"
