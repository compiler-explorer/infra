#!/bin/bash

docker run --rm -v$HOME/.s3cfg:/root/.s3cfg:ro mattgodbolt/clang-builder bash build-concepts.sh trunk s3://compiler-explorer/opt/
