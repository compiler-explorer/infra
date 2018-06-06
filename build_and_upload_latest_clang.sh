#!/bin/bash

docker run --rm --name clang.build -v$HOME/.s3cfg:/root/.s3cfg:ro mattgodbolt/clang-builder bash build.sh trunk s3://compiler-explorer/opt/
