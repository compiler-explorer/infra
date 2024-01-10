# Resizing the Conan data volume

Our Conan instance has an extra volume just to store the Conan packages.

This is a volume with the ID: `vol-0a99526fcf7bcfc11`

AWS says it's connected as `/dev/xvdb` in linux, but that's not actually correct, so ignore that.

## Enlarging the volume in AWS

If you click on the volume in the AWS console, you can click on Modify and enter a new Size in GiB.

## Recognizing the new size in Linux

* Login to the server with `ce conan login`
* Double check the device name with `sudo lsblk -f`, it should be `/dev/nvme1n1` (and ext4)
* Just to be sure type `sudo fdisk --list` and see if `/dev/nvme1n1` (not nvme0!) is indeed the new size
* `sudo growpart /dev/nvme1n1 1`
* `sudo pvresize /dev/nvme1n1p1`
* Check with `sudo pvs` that the PV has a new size now
* `sudo lvextend -l +100%FREE /dev/mapper/data-datavol`
* Check with `sudo lvs` that the LV has a new size now
* `sudo resize2fs /dev/mapper/data-datavol`
* Check with `df -h` if the mount has a new size

## To start/restart conan if it had failed because of no diskspace

* From the admin node: `ce conan restart`
