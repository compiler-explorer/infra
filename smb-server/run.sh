#!/bin/bash

cd /infra
git pull

cd /tmp

nmbd --daemon

smbd --foreground \
     --log-stdout \
     --no-process-group \
     --configfile /infra/smb-server/smb.conf
