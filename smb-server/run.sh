#!/bin/bash

cd /home/ubuntu/infra
git pull

cd /tmp

nmbd --daemon

smbd --foreground \
     --log-stdout \
     --no-process-group \
     --configfile /home/ubuntu/infra/smb-server/smb.conf
