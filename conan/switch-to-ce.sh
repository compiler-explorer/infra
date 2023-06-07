#!/bin/bash

ROOT_DIR=$(readlink -f "$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")/..")

cp ~/.conan/settings.yml $ROOT_DIR/conan/backup_settings.yml
conan remote list --raw > $ROOT_DIR/conan/backup_remotes.txt
cp $ROOT_DIR/init/settings.yml ~/.conan/settings.yml

# this should reflect what the library-builder does as well in https://github.com/compiler-explorer/library-builder/blob/main/Dockerfile
conan remote clean
conan remote add ceserver https://conan.compiler-explorer.com/ True
