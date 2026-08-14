#!/bin/bash

KEEP_LAST=5
S3=s3://compiler-explorer/opt/

for compiler_prefix in $(aws s3 ls ${S3} | grep -oE '[-a-zA-Z0-9_]+-(main|trunk|master)-' | sort -u); do
  echo "Considering prefix ${compiler_prefix}"
  aws s3 ls "${S3}${compiler_prefix}"
  # Look for anything with a datelike bit going on for extra safety.
  for old_file in $(aws s3 ls "${S3}${compiler_prefix}" | grep -E '[0-9]{8}\.tar'| awk '{print $4}' | sort | head -n -${KEEP_LAST}); do
    echo Removing "${S3}${old_file}"
    aws s3 rm "${S3}${old_file}"
  done
done
