#!/bin/sh

sudo -u ce mkdir /home/ce/.conan_server
echo "/dev/data/datavol       /home/ce/.conan_server   ext4   defaults,user=ce                0 0" >> /etc/fstab

mount -a

sudo -u ce /home/ce/.local/bin/gunicorn -b 0.0.0.0:9300 -w 4 -t 300 conans.server.server_launcher:app
