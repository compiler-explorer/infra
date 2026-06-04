# Resizing the Conan data volume

Our Conan instance has an extra volume just to store the Conan packages.

It's `vol-0a99526fcf7bcfc11`, defined as `aws_ebs_volume.conan_data` in
`terraform/ec2.tf` and tagged `Name=CEConanServerVol1`. The resource has
`lifecycle { prevent_destroy = true }` so a stray `terraform destroy` can't
nuke it.

You can resize everything while the server is online and the disk is mounted.

## Enlarging the volume in AWS

Bump `size` on `aws_ebs_volume.conan_data` in `terraform/ec2.tf`, open a PR,
and `terraform apply`. You don't have to merge first — apply from the branch
if you're working under time pressure, and merge afterwards. EBS volume size
modifications are online: no detach, no instance restart.

Wait for the modification to reach state `optimizing` before running the
host-side steps below — that's when the new size becomes visible to the
kernel. Check with:

```sh
aws ec2 describe-volumes-modifications --volume-ids vol-0a99526fcf7bcfc11
```

## Recognizing the new size in Linux

* Login to the server with `ce conan login`
* Confirm the device with `sudo lsblk -f`. On the current Nitro instance it's
  `/dev/nvme1n1` with one partition `/dev/nvme1n1p1` carrying the LVM PV.
  (AWS reports the attachment as `/dev/xvdb`; ignore that, it's a legacy
  alias the kernel doesn't actually use on Nitro.)
* `sudo growpart /dev/nvme1n1 1` — grows the partition to fill the device
* `sudo pvresize /dev/nvme1n1p1` — grows the LVM PV to fill the partition
* `sudo lvextend -l +100%FREE /dev/data/datavol` — grows the LV
* `sudo resize2fs /dev/mapper/data-datavol` — grows the ext4 filesystem
* `df -h /home/ce/.conan_server` — sanity check the new size

All of these are online and non-disruptive; ce-conan keeps serving throughout.

## To start/restart conan if it had failed because of no diskspace

* From the admin node: `ce conan restart`
