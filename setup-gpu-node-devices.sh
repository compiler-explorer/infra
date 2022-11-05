#!/bin/bash

if /sbin/modprobe nvidia; then
  # Count the number of NVIDIA controllers found.
  NVDEVS=$(lspci | grep -i NVIDIA)
  N3D=$(echo "$NVDEVS" | grep -c "3D controller")
  NVGA=$(echo "$NVDEVS" | grep -c "VGA compatible controller")

  N=$((N3D + NVGA - 1))
  for i in $(seq 0 $N); do
    mknod -m 666 "/dev/nvidia$i" c 195 "$i"
  done

  mknod -m 666 /dev/nvidiactl c 195 255
else
  exit 1
fi

if /sbin/modprobe nvidia-uvm; then
  # Find out the major device number used by the nvidia-uvm driver
  D=$(grep nvidia-uvm /proc/devices | awk '{print $1}')

  mknod -m 666 /dev/nvidia-uvm c "$D" 0
else
  exit 1
fi

# /dev/nvidia-modeset
/bin/nvidia-modprobe -m
