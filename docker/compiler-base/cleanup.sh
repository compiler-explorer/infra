#!/bin/bash
set -ex

rm /root/.s3cfg

apt-get purge -y curl s3cmd openjdk-6-jre-lib
apt-get autoremove -y
apt-get clean
rm -rf /var/lib/apt/lists/* /tmp/* /var/tmp/*
