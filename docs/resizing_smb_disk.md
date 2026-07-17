# Resizing the SMB server disk

The SMB server's root EBS volume (`vol-009eda63cd3ab5254`, a single ext4
filesystem on the boot disk) fills up as its contents grow. Unlike the Conan
volume there's no LVM in the way, so resizing is just four steps.

Everything is online: no detach, no reboot, no unmount.

## Enlarge the volume in AWS

In the EC2 console, find the volume, Actions -> Modify Volume, and set the new
size. You can only increase, and AWS enforces a ~6 hour cooldown before the
same volume can be modified again, so leave headroom. Billing changes to the
new size as soon as the modification starts.

## Grow the partition and filesystem

From the admin node, log into the server with `ce smb login`, then:

* `lsblk` — confirm the device shows the new size (`/dev/nvme0n1`)
* `sudo growpart /dev/nvme0n1 1` — grows partition 1 to fill the device
* `sudo resize2fs /dev/nvme0n1p1` — grows the ext4 filesystem
* `df -h /` — sanity check the new size

The Linux filesystem lives on partition 1 (`nvme0n1p1`); the small EFI
partition (`nvme0n1p15`) sits before it and is left alone. You can run these as
soon as the modification reaches the `optimizing` state.

If the disk is completely full, `growpart` may fail needing a little scratch
space in `/tmp` — free some first (e.g. clear old logs), then retry.
