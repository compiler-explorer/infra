#!/bin/bash

KEEP_LAST=5
S3=s3://compiler-explorer/opt/

remove_older() {
    local compiler=$1
    for old_file in $(aws s3 ls ${S3} | grep -oE "${compiler}"'-trunk-[0-9]+.*' | sort | head -n -${KEEP_LAST}); do
        echo Removing ${S3}${old_file}
        aws s3 rm ${S3}${old_file}
    done
}

remove_older clang
remove_older clang-cppx-trunk
remove_older clang-concepts-trunk
remove_older gcc
