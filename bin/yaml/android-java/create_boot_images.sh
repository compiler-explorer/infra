#!/bin/bash

set -euo pipefail

DIR_FOR_BOOT_IMAGE=app/system/framework    # Using /app directory, which is used for creating oat output in the compilation commands
declare -a instruction_sets=("arm" "arm64" "x86" "x86_64" "riscv64")

for instruction_set in "${instruction_sets[@]}"
do
    mkdir -p $DIR_FOR_BOOT_IMAGE/"$instruction_set"
x86_64/bin/dex2oat64 \
    --runtime-arg -Xms64m \
    --runtime-arg -Xmx512m \
    --runtime-arg -Xgc:CMC \
    --runtime-arg -Xbootclasspath:bootjars/core-oj.jar:bootjars/core-libart.jar:bootjars/okhttp.jar:bootjars/bouncycastle.jar:bootjars/apache-xml.jar \
    --runtime-arg -Xbootclasspath-locations:/apex/com.android.art/javalib/core-oj.jar:/apex/com.android.art/javalib/core-libart.jar:/apex/com.android.art/javalib/okhttp.jar:/apex/com.android.art/javalib/bouncycastle.jar:/apex/com.android.art/javalib/apache-xml.jar \
    --instruction-set=arm64 \
    --compiler-filter=speed \
    --dex-file=bootjars/core-oj.jar \
    --dex-file=bootjars/core-libart.jar \
    --dex-file=bootjars/okhttp.jar \
    --dex-file=bootjars/bouncycastle.jar \
    --dex-file=bootjars/apache-xml.jar \
    --dex-location=/apex/com.android.art/javalib/core-oj.jar \
    --dex-location=/apex/com.android.art/javalib/core-libart.jar \
    --dex-location=/apex/com.android.art/javalib/okhttp.jar \
    --dex-location=/apex/com.android.art/javalib/bouncycastle.jar \
    --dex-location=/apex/com.android.art/javalib/apache-xml.jar \
    --image=$DIR_FOR_BOOT_IMAGE/"$instruction_set"/boot.art \
    --oat-file=$DIR_FOR_BOOT_IMAGE/"$instruction_set"/boot.oat \
    --output-vdex=$DIR_FOR_BOOT_IMAGE/"$instruction_set"/boot.vdex \
    --android-root=out/empty \
    --abort-on-hard-verifier-error \
    --no-abort-on-soft-verifier-error \
    --compilation-reason=cloud \
    --image-format=lz4 \
    --force-determinism \
    --resolve-startup-const-strings=true \
    --avoid-storing-invocation \
    --generate-mini-debug-info \
    --force-allow-oj-inlines \
    --no-watch-dog \
    --single-image \
    --base=0x70000000
done
