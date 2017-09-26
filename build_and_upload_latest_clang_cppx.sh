#!/bin/bash

docker run --rm -v$HOME/.s3cfg:/root/.s3cfg:ro mattgodbolt/clang-builder bash build-cppx.sh trunk s3://compiler-explorer/opt/
