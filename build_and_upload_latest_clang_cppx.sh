#!/bin/bash

docker run --rm --name clang-cppx.build -v$HOME/.s3cfg:/root/.s3cfg:ro mattgodbolt/clang-builder bash build-cppx.sh trunk s3://compiler-explorer/opt/
