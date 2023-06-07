#!/bin/bash

ROOT_DIR=$(readlink -f "$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")/..")

# this restores the "default" settings.yml
rm ~/.conan/settings.yml
conan config init

# removes our custom remote
conan remote clean

# load the backed up remotes
while read line; do
  conan remote add $line
done <$ROOT_DIR/conan/backup_remotes.txt

# conan remote add conancenter https://center.conan.io True
